"""Gemini extraction — the only module in the app that talks to a model.

Everything downstream of `parse_model_json` is model-independent: matching, the
confidence gate, routing and the review queue all live in
`app/capture_pipeline.py` and are covered by tests that never call Gemini. That
boundary is deliberate, and it is what made this migration cheap.

## Models — verified 2026-09-30

Gemini is called through **Vertex AI**, authenticated as the Cloud Run
service's own identity and billed to the project: no API key. The chain lives
in `prompts/models.json`, newest Flash model first: `gemini-3.8-flash`,
`3.7-flash` and `3.6-flash` from the `global` endpoint (the only place Vertex
AI serves them), then `gemini-3.5-flash` and `gemini-2.5-flash` in
`asia-south1` (Mumbai). One attempt per model, a hard timeout per call, and a
retired model (404) is skipped at once.

The prompts live in `prompts/` as plain text. `scripts/eval_prompts.py` scores
the extraction prompt against the edge cases in `evals/`.
"""

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

from google import genai
from google.genai import types

from app import capture_pipeline
from app import items

log = logging.getLogger(__name__)

# See the module docstring for why these models and this order.
BACKEND = os.getenv("GEMINI_BACKEND", "vertex")
PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
_MODELS = json.loads((Path(__file__).resolve().parent.parent / "prompts" / "models.json")
                     .read_text(encoding="utf-8"))
_primary_name, _, _primary_loc = os.getenv("GEMINI_MODEL", _MODELS["primary"]).partition("@")
MODEL = _primary_name
LOCATION = os.getenv("GEMINI_LOCATION", _primary_loc or "asia-south1")
# Tried in order after the primary fails. Every switch is logged, so a silent
# degradation is still a visible one.
FALLBACK_MODELS = [m.strip() for m in (
    os.getenv("GEMINI_FALLBACK_MODELS") or ",".join(_MODELS["fallbacks"])
).split(",") if m.strip()]
FALLBACK_MODEL = FALLBACK_MODELS[0]
# Per call. A voice note is a few seconds of audio; anything slower than this
# is better answered by the next model than waited for.
TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", str(_MODELS.get("timeout_ms", 25000))))
# Gemini 3 models think before answering by default. A stock report or a short
# note needs little of it, and at the default level gemini-3.8-flash overran
# the timeout on escalation notes. Gemini 2.5 takes no thinking level.
THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", _MODELS.get("thinking_level", "")) or None

_used = threading.local()


def split_model(entry: str) -> tuple[str, str]:
    """`gemini-3.6-flash@global` -> ("gemini-3.6-flash", "global")."""
    name, _, loc = entry.partition("@")
    return name, (loc or LOCATION)


def model_used() -> str:
    """The model that answered the last call on this thread, for the record."""
    return getattr(_used, "model", MODEL)

_clients: dict[str, genai.Client] = {}


def _get_client(location: str | None = None) -> genai.Client:
    """Build a client per location on first use, not at import.

    Constructing clients at import would make the app fail to start wherever
    credentials are absent, which includes the test suite.
    """
    loc = location or LOCATION
    key = f"{BACKEND}:{loc}"
    if key not in _clients:
        # The SDK's own retries are switched off: the model chain is the retry
        # policy. With both, a dropped connection was retried inside the SDK
        # for over nine minutes before the chain ever saw it.
        opts = types.HttpOptions(timeout=TIMEOUT_MS,
                                 retry_options=types.HttpRetryOptions(attempts=1))
        if BACKEND == "apikey":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_BACKEND=apikey needs GEMINI_API_KEY.")
            _clients[key] = genai.Client(api_key=api_key, http_options=opts)
        else:
            _clients[key] = genai.Client(vertexai=True, project=PROJECT,
                                         location=loc, http_options=opts)
    return _clients[key]

# The prompts live in prompts/ as plain text, so they can be read, reviewed
# and pasted into Google AI Studio without opening the code. Loaded once.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


SYSTEM_PROMPT = load_prompt("extraction_system.txt")

# The extraction prompt is shared by voice, chat and photo: the only
# difference is whether the model is handed audio, text or an image. Keeping
# one prompt is what makes the modes produce comparable records.
CHAT_INSTRUCTION = load_prompt("chat_instruction.txt")

# A photograph of the stock register — the ruled ledger book every PHC keeps
# by hand. Each visible row becomes one object. Handwriting is read, never
# guessed at: an illegible figure is a null quantity, and a doubtful one is
# low confidence, so the worker corrects it on the read-back rather than the
# ledger inheriting a misread "7" for a "1". The model is told which column
# is which because the stock register's layout is standard across states.
PHOTO_INSTRUCTION = load_prompt("photo_instruction.txt").strip()


# Flash models return 503 "this model is currently experiencing high demand"
# under load. Observed on roughly half of a short burst of live requests on
# 2026-09-01 — always transient, always fine on retry. Without a retry a health
# worker loses the extraction and sees a raw API error, which is the worst of
# both outcomes.
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
# Default: two tries on the primary, then one on each fallback.
MAX_ATTEMPTS = int(os.getenv(
    "GEMINI_MAX_ATTEMPTS",
    str(int(os.getenv("GEMINI_FALLBACK_AFTER", str(_MODELS.get("attempts_on_primary", 1)))) + len(FALLBACK_MODELS))))
BACKOFF_BASE_SECONDS = float(os.getenv("GEMINI_BACKOFF_BASE", "0.6"))
BACKOFF_CAP_SECONDS = float(os.getenv("GEMINI_BACKOFF_CAP", "8.0"))
# After this many consecutive retryable failures on the pinned model, switch to
# the fallback for the remaining attempts. A congested model is better answered
# by a different model than by waiting longer for the same one.
FALLBACK_AFTER_ATTEMPTS = int(os.getenv("GEMINI_FALLBACK_AFTER", str(_MODELS.get("attempts_on_primary", 1))))

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
    name = type(exc).__name__.lower()
    if "timeout" in name or "timed out" in str(exc).lower():
        return True
    text = str(exc)
    return any(str(s) in text for s in RETRYABLE_STATUS) and (
        "UNAVAILABLE" in text or "RESOURCE_EXHAUSTED" in text
        or "high demand" in text or "INTERNAL" in text)


def _is_retired(exc: Exception) -> bool:
    """The model itself no longer exists for this key; try the next one."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    return (code == 404 or "404" in text[:5]) and (
        "NOT_FOUND" in text or "no longer available" in text)


def model_for_attempt(attempt: int) -> str:
    """The primary for the first attempts, then each fallback in turn."""
    if attempt <= FALLBACK_AFTER_ATTEMPTS or not FALLBACK_MODELS:
        return MODEL
    i = min(attempt - FALLBACK_AFTER_ATTEMPTS - 1, len(FALLBACK_MODELS) - 1)
    return FALLBACK_MODELS[i]


def config_for(model: str, system_instruction: str) -> types.GenerateContentConfig:
    """The call's config; the thinking level only where the model takes one."""
    if THINKING_LEVEL and model.startswith("gemini-3"):
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL))
    return types.GenerateContentConfig(system_instruction=system_instruction)


def _generate(contents, system_instruction: str = SYSTEM_PROMPT) -> str:
    """One extraction call, retried on transient failure, then degraded.

    Exponential backoff with jitter. After `FALLBACK_AFTER_ATTEMPTS` the model
    moves down `FALLBACK_MODELS` — a congested model is better answered by a
    different one than by waiting longer for the same one. A retired model
    (404) is skipped at once, without a wait. If every attempt
    fails, `ModelUnavailable` carries a message written for the person holding
    the phone; the raw status never reaches them.
    """
    last_error = ""
    # The extraction rules now travel as a system_instruction rather than as
    # the first element of `contents`. Done separately from the SDK migration
    # on purpose, so a change in library and a change in prompting could not be
    # confounded if the output shifted.
    retired: set[str] = set()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        entry = model_for_attempt(attempt)
        if entry in retired:
            continue
        model, location = split_model(entry)
        try:
            client = _get_client(location)
            response = client.models.generate_content(
                model=model, contents=contents,
                config=config_for(model, system_instruction))
            _used.model = model
            if attempt > 1:
                log.info("Extraction succeeded on attempt %d using %s",
                         attempt, model)
            return (response.text or "").strip()
        except Exception as exc:
            last_error = str(exc)
            if _is_retired(exc):
                log.warning("Gemini %s is retired (%s); moving to the next "
                            "model", model, last_error[:120])
                retired.add(entry)
                continue
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


def process_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Send a photograph of the stock register through the same rules."""
    return _generate([
        PHOTO_INSTRUCTION,
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ])


def handle_capture(audio_bytes: bytes, facility_id: str,
                   mime_type: str = "audio/mp3", preview: bool = False) -> dict:
    """Voice capture. Audio in, structured records out, via the shared path.

    With `preview`, nothing is written: the records come back for the worker
    to hear read out and confirm, and `capture_pipeline.confirm()` writes
    them. Without it (the offline queue syncing hours later, with nobody
    holding the phone) the records go straight through the gate as before.
    """
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
    return _extract_and_route(raw, facility_id, "voice", preview=preview)


def handle_photo(image_bytes: bytes, facility_id: str,
                 mime_type: str = "image/jpeg") -> dict:
    """A photographed register page. Always a preview, never a direct write.

    Reading handwriting is the least certain input this system accepts, so a
    photo can only ever produce rows for the worker to check. There is no
    unattended path for it on purpose.
    """
    try:
        raw = process_image(image_bytes, mime_type)
    except ModelUnavailable as exc:
        return {"error": str(exc), "retryable": True,
                "attempts": exc.attempts, "technical_detail": exc.last_error,
                "events": [], "review_queue": [], "source": "photo"}
    except Exception as exc:
        return {"error": str(exc), "retryable": False,
                "events": [], "review_queue": [], "source": "photo"}
    return _extract_and_route(raw, facility_id, "photo", preview=True)


def handle_sms(sender: str, message: str) -> dict:
    """A text message, as a gateway would hand it over.

    No gateway is connected in this deployment; this is the endpoint one would
    post to. The first word of the message must be the facility id, because
    there is no phone-number register to look the sender up in and inventing
    one would be worse than asking. The reply is plain text a gateway can send
    straight back.
    """
    text = (message or "").strip()
    parts = text.split(None, 1)
    if not parts or not parts[0].upper().startswith("IN-") or len(parts) < 2:
        return {"error": "no facility id", "events": [], "review_queue": [],
                "source": "sms", "sender": sender,
                "reply": ("Start your message with your centre id, e.g. "
                          "IN-155740 paracetamol 200 tablet aaye")}
    facility_id, body = parts[0].upper(), parts[1]
    result = handle_chat(body, facility_id, source="sms")
    result["sender"] = sender
    result["reply"] = sms_reply(result)
    return result


def sms_reply(result: dict) -> str:
    """One line per record, short enough for a single SMS segment each."""
    if result.get("error"):
        return f"Not recorded: {result['error']}"
    lines = []
    for r in result.get("events", []):
        lines.append(f"OK {r.get('item_name') or r['local_name']} "
                     f"{r['quantity']} {r['unit']} {r['event_type']}")
    for r in result.get("review_queue", []):
        lines.append(f"HELD {r.get('item_name') or r['local_name']}: "
                     f"{r.get('review_reason')}")
    return "\n".join(lines) or "Nothing recognised as a stock update."


def handle_chat(message: str, facility_id: str, preview: bool = False,
                source: str = "chat") -> dict:
    """Chat capture. Same prompt, same matcher, same review queue."""
    if not (message or "").strip():
        return {"error": "Empty message", "events": [], "review_queue": [],
                "source": source}
    try:
        raw = process_text(message)
    except ModelUnavailable as exc:
        return {"error": str(exc), "retryable": True,
                "attempts": exc.attempts, "technical_detail": exc.last_error,
                "events": [], "review_queue": [], "source": source,
                "raw_transcript": message}
    except Exception as exc:
        return {"error": str(exc), "retryable": False,
                "events": [], "review_queue": [], "source": source}
    return _extract_and_route(raw, facility_id, source,
                              raw_transcript=message, preview=preview)


def _extract_and_route(raw_reply: str, facility_id: str, source: str,
                       raw_transcript: str | None = None,
                       preview: bool = False) -> dict:
    try:
        extractions = capture_pipeline.parse_model_json(raw_reply)
    except capture_pipeline.ExtractionError as exc:
        return {"error": str(exc), "events": [], "review_queue": [],
                "source": source, "raw_reply": raw_reply[:500]}
    if preview:
        return capture_pipeline.preview(
            extractions, facility_id, source,
            raw_transcript=raw_transcript or raw_reply)
    return capture_pipeline.describe(capture_pipeline.persist(
        capture_pipeline.route(
            extractions, facility_id, source,
            raw_transcript=raw_transcript or raw_reply,
        )))


def match_item(local_name: str) -> str | None:
    """Fuzzy-match a spoken name against the full NLEM catalogue."""
    return items.match(local_name)
