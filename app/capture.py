import os
import json
import uuid
from datetime import datetime, timezone
import google.generativeai as genai
from google.cloud import firestore
from pydantic import ValidationError

from app import items
from app.models import GeminiExtractionItem, StockEvent, ReviewQueueItem

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel('gemini-1.5-pro')

SYSTEM_PROMPT = """
You extract pharmacy stock updates from voice notes recorded by health
workers at primary health centres. The speaker may use Hindi, English,
Portuguese, or a mix, with local drug names and informal quantities.

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
- If quantity is unclear, return the item with quantity null
- Never invent items that were not mentioned
- Transcribe the drug name as spoken; do not translate or correct it
"""

db = None
def get_db():
    global db
    if db is None:
        # Assumes Application Default Credentials if not explicitly provided
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
    return db

def match_item(local_name: str) -> str | None:
    """Fuzzy-match a spoken name against the full NLEM catalogue."""
    return items.match(local_name)

def process_audio(audio_bytes: bytes, mime_type: str = "audio/mp3") -> str:
    """Sends audio to Gemini and returns raw JSON text."""
    prompt = [
        SYSTEM_PROMPT,
        {"mime_type": mime_type, "data": audio_bytes}
    ]
    response = model.generate_content(prompt)
    return response.text.strip()

def handle_capture(audio_bytes: bytes, facility_id: str, mime_type: str = "audio/mp3") -> dict:
    try:
        raw_json_str = process_audio(audio_bytes, mime_type)
        if raw_json_str.startswith("```"):
            raw_json_str = raw_json_str.strip("` \njson")
            
        data = json.loads(raw_json_str)
        if not isinstance(data, list):
            data = [data]
            
        results = {"events": [], "review_queue": [], "errors": []}
        db_client = get_db()
        
        for item_data in data:
            try:
                extraction = GeminiExtractionItem(**item_data)
                
                event_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc)
                
                if extraction.confidence < 0.6:
                    review_item = ReviewQueueItem(
                        event_id=event_id,
                        facility_id=facility_id,
                        local_name=extraction.local_name,
                        event_type=extraction.event_type,
                        quantity=extraction.quantity,
                        unit=extraction.unit,
                        confidence=extraction.confidence,
                        raw_transcript=raw_json_str,
                        event_ts=now
                    )
                    db_client.collection("review_queue").document(event_id).set(review_item.model_dump(mode='json'))
                    results["review_queue"].append(review_item.model_dump(mode='json'))
                else:
                    item_id = match_item(extraction.local_name)
                    if not item_id:
                        review_item = ReviewQueueItem(
                            event_id=event_id,
                            facility_id=facility_id,
                            local_name=extraction.local_name,
                            event_type=extraction.event_type,
                            quantity=extraction.quantity,
                            unit=extraction.unit,
                            confidence=extraction.confidence,
                            raw_transcript=raw_json_str,
                            event_ts=now
                        )
                        db_client.collection("review_queue").document(event_id).set(review_item.model_dump(mode='json'))
                        results["review_queue"].append(review_item.model_dump(mode='json'))
                        continue

                    event = StockEvent(
                        event_id=event_id,
                        facility_id=facility_id,
                        item_id=item_id,
                        event_type=extraction.event_type,
                        quantity=extraction.quantity,
                        event_ts=now,
                        source="voice",
                        confidence=extraction.confidence,
                        raw_transcript=raw_json_str
                    )
                    
                    db_client.collection("pending_events").document(event_id).set(event.model_dump(mode='json'))
                    results["events"].append(event.model_dump(mode='json'))
                    
            except ValidationError as e:
                results["errors"].append({"data": item_data, "error": str(e)})
                
        return results
        
    except Exception as e:
        return {"error": str(e), "events": [], "review_queue": []}
