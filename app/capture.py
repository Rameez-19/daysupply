import os
import json
import uuid
from datetime import datetime, timezone
import google.generativeai as genai
from google.cloud import firestore
from pydantic import ValidationError

from app import capture_pipeline
from app import items

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel('gemini-1.5-pro')

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
    """Send audio to Gemini and return its raw reply."""
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Voice and chat capture cannot run "
            "without it; set it on the Cloud Run service."
        )
    response = model.generate_content([
        SYSTEM_PROMPT,
        {"mime_type": mime_type, "data": audio_bytes},
    ])
    return response.text.strip()


def process_text(message: str) -> str:
    """Send a typed message through the same extraction prompt."""
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Voice and chat capture cannot run "
            "without it; set it on the Cloud Run service."
        )
    response = model.generate_content(
        SYSTEM_PROMPT + CHAT_INSTRUCTION + message)
    return response.text.strip()


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
