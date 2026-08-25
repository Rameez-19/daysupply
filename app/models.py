from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class GeminiExtractionItem(BaseModel):
    local_name: str
    event_type: str  # "dispensed" | "received" | "count"
    quantity: Optional[int] = None
    unit: str  # "tablet" | "strip" | "vial" | "bottle" | "unknown"
    confidence: float = Field(..., ge=0.0, le=1.0)

class StockEvent(BaseModel):
    event_id: str
    facility_id: str
    item_id: str
    event_type: str
    quantity: Optional[int]
    event_ts: datetime
    source: str  # "voice" | "photo" | "seed" | "manual"
    confidence: float
    raw_transcript: Optional[str] = None

class ReviewQueueItem(BaseModel):
    event_id: str
    facility_id: str
    local_name: str
    event_type: str
    quantity: Optional[int]
    unit: str
    confidence: float
    raw_transcript: Optional[str] = None
    event_ts: datetime
    status: str = "pending"  # "pending", "resolved", "rejected"
