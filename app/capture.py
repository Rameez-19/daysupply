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

import os
import json
import uuid
from datetime import datetime, timezone

from google import genai
from google.genai import types
from google.cloud import firestore
from pydantic import ValidationError

from app import capture_pipeline
from app import items

# See the module docstring for why this pin and not another.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# Documented, not wired in: switching is a one-line env change, and an
# automatic silent fallback would hide a model outage rather than surface it.
FALLBACK_MODEL = "gemini-2.5-flash"

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
  "event_type": "dispensed" | "received" | "count",
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
"""

# The extraction prompt is shared by voice and chat: the only difference is
# whether the model is handed audio or text. Keeping one prompt is what makes
# the two modes produce comparable records.
CHAT_INSTRUCTION = (
    "The health worker typed this message instead of recording it. "
    "Extract the same JSON array from the text.\n\nMessage: "
)


def process_audio(audio_bytes: bytes, mime_type: str = "audio/mp3") -> str:
    """Send audio to Gemini and return its raw reply.

    The prompt is passed inline rather than as a `system_instruction`, which
    the new SDK also supports. That is deliberate: this change is an SDK
    migration, and moving the prompt at the same time would confound a
    behaviour change with a library change. Worth revisiting separately.
    """
    response = _get_client().models.generate_content(
        model=MODEL,
        contents=[
            SYSTEM_PROMPT,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ],
    )
    return (response.text or "").strip()


def process_text(message: str) -> str:
    """Send a typed message through the same extraction prompt."""
    response = _get_client().models.generate_content(
        model=MODEL,
        contents=SYSTEM_PROMPT + CHAT_INSTRUCTION + message,
    )
    return (response.text or "").strip()


def handle_capture(audio_bytes: bytes, facility_id: str,
                   mime_type: str = "audio/mp3") -> dict:
    """Voice capture. Audio in, structured records out, via the shared path."""
    try:
        raw = process_audio(audio_bytes, mime_type)
    except Exception as exc:
        return {"error": str(exc), "events": [], "review_queue": [],
                "source": "voice"}
    return _extract_and_route(raw, facility_id, "voice")


def handle_chat(message: str, facility_id: str) -> dict:
    """Chat capture. Same prompt, same matcher, same review queue."""
    if not (message or "").strip():
        return {"error": "Empty message", "events": [], "review_queue": [],
                "source": "chat"}
    try:
        raw = process_text(message)
    except Exception as exc:
        return {"error": str(exc), "events": [], "review_queue": [],
                "source": "chat"}
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
