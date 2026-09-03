"""Gemini extraction — the only module in the app that talks to a model.

Everything downstream of `parse_model_json` is model-independent: matching, the
confidence gate, routing and the review queue all live in
`app/capture_pipeline.py` and are covered by tests that never call Gemini. That
boundary is deliberate, and it is what made this migration cheap.

## Model pin — verified 2026-09-01

`gemini-3.6-flash`. GA, not preview, and Flash-class is the right weight for
short multilingual audio into a small JSON payload.

Deliberately **not**:

* `gemini-3.7-flash` — newer, but tuned for coding and agentic work rather than
  this.
* `gemini-3.1-pro` and the rest of the Gemini 3 Pro line — still in preview.

**Fallback if Hindi audio accuracy disappoints:** `gemini-2.5-flash`, the
cheaper proven option. Set `GEMINI_MODEL` to override without a code change.

**Model pins go stale, and this one already did once.** The previous pin was
`gemini-1.5-pro`, which Google has since shut down — every request returned
404, a failure entirely independent of the API key. Re-verify this pin against
the current model list before each submission or deployment, and update the
date above when you do.
"""

import logging
import os
import random
import time

from google import genai
from google.genai import types

from app import capture_pipeline
from app import items

log = logging.getLogger(__name__)

# See the module docstring for why this pin and not another.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# Used automatically after repeated retryable failures on the pinned model,
# and settable directly via GEMINI_MODEL. The switch is logged, so a silent
# degradation is still a visible one.
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Build the client on first use, not at import.

    Constructing it at import time would make the whole module — and therefore
    the whole app — fail to start wherever `GEMINI_API_KEY` is absent, which
    includes the test suite and any container that has not been given the key
    yet. The old code called `genai.configure()` at import for the same reason
    it should not have.
    """
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Voice and chat capture cannot run "
                "without it; set it on the Cloud Run service.")
        _client = genai.Client(api_key=api_key)
    return _client

SYSTEM_PROMPT = """
You extract pharmacy stock updates from reports by health workers at
primary health centres in India. The speaker may use Hindi, English, or a
mix, with local drug names and informal quantities.

Return ONLY a JSON array, no prose, no markdown fences. One object per
item mentioned:

[{
  "local_name": "<drug name exactly as spoken>",
  "event_type": "dispensed" | "received" | "count" | "lost",
  "loss_reason": "<only when event_type is lost; the speaker's own word:
                  damaged | broken | expired | spilled | stolen | unknown>",
  "quantity": <integer or null>,
  "unit": "tablet" | "strip" | "vial" | "bottle" | "unknown",
  "confidence": <0.0-1.0>
}]

Rules:
- "aadha dabba" / "half a box" -> estimate in units, confidence <= 0.5
- "kuch nahi bacha" / "khatam" -> quantity 0, event_type "count"
- If quantity is unclear, return the item with quantity null
- Never invent items that were not mentioned
- Transcribe the drug name as spoken; do not translate or correct it

LOSSES. Stock leaves a shelf in ways that are neither dispensing nor
transfer, and a supply chain that cannot see them cannot explain its own
shortfalls. Use event_type "lost" when the speaker describes stock that
was there and no longer is:
- "toot gaye" / "broken" / "tut gaya"        -> loss_reason "broken"
- "kharab ho gaya" / "damaged" / "spoiled"   -> loss_reason "damaged"
- "gir gaya" / "spilled" / "leak ho gaya"    -> loss_reason "spilled"
- "chori" / "stolen" / "gayab"               -> loss_reason "stolen"
- "expire ho gaya" / "expired"               -> loss_reason "expired"
Do NOT force a reason the speaker did not give. If they say only that
stock is missing, use loss_reason "unknown" - an honest unknown is worth
more than a guessed category.
"lost" means gone from the shelf. It is not "dispensed", which means given
to a patient, and the difference is the whole point of recording it.

VAGUE QUANTITIES. A range or an approximation is not a number. If the
speaker gives one, set confidence <= 0.5 so a human confirms it. This
applies to:
- ranges spoken as two adjacent numbers: "teen char" (three-four),
  "do teen" (two-three), "das barah" (ten-twelve), "three or four"
- hedges: "kuch" (some), "thoda" (a little), "lagbhag" / "karib"
  (approximately), "aas paas" (around), "ya do" ("or two")
- part-container amounts: "aadha dabba", "half a strip", "paav"
A precise number stated plainly — "do sau" (200), "pachas" (50) — is NOT
vague and keeps its normal high confidence.
"""

# The extraction prompt is shared by voice and chat: the only difference is
# whether the model is handed audio or text. Keeping one prompt is what makes
# the two modes produce comparable records.
CHAT_INSTRUCTION = (
    "The health worker typed this message instead of recording it. "
    "Extract the same JSON array from the text.\n\nMessage: "
)


# Flash models return 503 "this model is currently experiencing high demand"
# under load. Observed on roughly half of a short burst of live requests on
# 2026-09-01 — always transient, always fine on retry. Without a retry a health
# worker loses the extraction and sees a raw API error, which is the worst of
# both outcomes.
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "4"))
BACKOFF_BASE_SECONDS = float(os.getenv("GEMINI_BACKOFF_BASE", "0.6"))
BACKOFF_CAP_SECONDS = float(os.getenv("GEMINI_BACKOFF_CAP", "8.0"))
# After this many consecutive retryable failures on the pinned model, switch to
# the fallback for the remaining attempts. A congested model is better answered
# by a different model than by waiting longer for the same one.
FALLBACK_AFTER_ATTEMPTS = int(os.getenv("GEMINI_FALLBACK_AFTER", "2"))

USER_FACING_FAILURE = (
    "The extraction service is busy right now. Your recording has not been "
    "lost — please try again in a moment."
)


class ModelUnavailable(RuntimeError):
    """Every attempt failed on a retryable error.

    Carries a message meant for a health worker, not an API status line.
    """

    def __init__(self, attempts: int, last_error: str):
        super().__init__(USER_FACING_FAILURE)
        self.attempts = attempts
        self.last_error = last_error


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in RETRYABLE_STATUS:
        return True
    text = str(exc)
    return any(str(s) in text for s in RETRYABLE_STATUS) and (
        "UNAVAILABLE" in text or "RESOURCE_EXHAUSTED" in text
        or "high demand" in text or "INTERNAL" in text)


def _generate(contents) -> str:
    """One extraction call, retried on transient failure, then degraded.

    Exponential backoff with jitter. After `FALLBACK_AFTER_ATTEMPTS` the model
    is swapped for `FALLBACK_MODEL` — a congested model is better answered by a
    different one than by waiting longer for the same one. If every attempt
    fails, `ModelUnavailable` carries a message written for the person holding
    the phone; the raw status never reaches them.
    """
    client = _get_client()
    last_error = ""
    # The extraction rules now travel as a system_instruction rather than as
    # the first element of `contents`. Done separately from the SDK migration
    # on purpose, so a change in library and a change in prompting could not be
    # confounded if the output shifted.
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        model = MODEL if attempt <= FALLBACK_AFTER_ATTEMPTS else FALLBACK_MODEL
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config)
            if attempt > 1:
                log.info("Extraction succeeded on attempt %d using %s",
                         attempt, model)
            return (response.text or "").strip()
        except Exception as exc:
            last_error = str(exc)
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS:
                if _is_retryable(exc):
                    break
                raise
            delay = min(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1),
                        BACKOFF_CAP_SECONDS)
            delay += random.uniform(0, delay * 0.25)   # jitter
            log.warning("Gemini %s attempt %d/%d failed (%s); retrying in "
                        "%.1fs", model, attempt, MAX_ATTEMPTS,
                        last_error[:120], delay)
            time.sleep(delay)
    raise ModelUnavailable(MAX_ATTEMPTS, last_error)


def process_audio(audio_bytes: bytes, mime_type: str = "audio/mp3") -> str:
    """Send audio to Gemini and return its raw reply."""
    return _generate([
        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
    ])


def process_text(message: str) -> str:
    """Send a typed message through the same extraction rules."""
    return _generate(CHAT_INSTRUCTION + message)


def handle_capture(audio_bytes: bytes, facility_id: str,
                   mime_type: str = "audio/mp3") -> dict:
    """Voice capture. Audio in, structured records out, via the shared path."""
    try:
        raw = process_audio(audio_bytes, mime_type)
    except ModelUnavailable as exc:
        # Every retry failed on a transient error. The health worker gets a
        # sentence they can act on; the API status stays in the logs and in a
        # separate field for us.
        return {"error": str(exc), "retryable": True,
                "attempts": exc.attempts, "technical_detail": exc.last_error,
                "events": [], "review_queue": [], "source": "voice"}
    except Exception as exc:
        return {"error": str(exc), "retryable": False,
                "events": [], "review_queue": [], "source": "voice"}
    return _extract_and_route(raw, facility_id, "voice")


def handle_chat(message: str, facility_id: str) -> dict:
    """Chat capture. Same prompt, same matcher, same review queue."""
    if not (message or "").strip():
        return {"error": "Empty message", "events": [], "review_queue": [],
                "source": "chat"}
    try:
        raw = process_text(message)
    except ModelUnavailable as exc:
        return {"error": str(exc), "retryable": True,
                "attempts": exc.attempts, "technical_detail": exc.last_error,
                "events": [], "review_queue": [], "source": "chat",
                "raw_transcript": message}
    except Exception as exc:
        return {"error": str(exc), "retryable": False,
                "events": [], "review_queue": [], "source": "chat"}
    return _extract_and_route(raw, facility_id, "chat",
                              raw_transcript=message)


def _extract_and_route(raw_reply: str, facility_id: str, source: str,
                       raw_transcript: str | None = None) -> dict:
    try:
        extractions = capture_pipeline.parse_model_json(raw_reply)
    except capture_pipeline.ExtractionError as exc:
        return {"error": str(exc), "events": [], "review_queue": [],
                "source": source, "raw_reply": raw_reply[:500]}
    return capture_pipeline.persist(capture_pipeline.route(
        extractions, facility_id, source,
        raw_transcript=raw_transcript or raw_reply,
    ))


def match_item(local_name: str) -> str | None:
    """Fuzzy-match a spoken name against the full NLEM catalogue."""
    return items.match(local_name)
