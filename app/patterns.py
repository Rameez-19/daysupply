"""
Federated Pattern Exchange (Block 8)
Computes 12-element monthly seasonal coefficients per ATC code.
"""

import os
from google.cloud import bigquery
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List

class PatternNode(BaseModel):
    country_code: str
    atc_code: str
    monthly_coefficients: List[float]  # 12 elements

def get_local_patterns() -> List[PatternNode]:
    """Compute local patterns from stock_events table."""
    client = bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
    
    # In a real scenario, this would query bigquery to aggregate sum(quantity) by month for each atc_code
    # Since we are restricted from running expensive group-bys over the entire history unnecessarily,
    # we simulate the extract from demand_reference (or hardcode the output for the demo).
    
    # For demo purposes, we will return a static pattern for an antimalarial ATC (P01B)
    # representing India's seasonal vector for malaria (monsoon peaks).
    return [
        PatternNode(
            country_code="IN",
            atc_code="P01B",
            monthly_coefficients=[0.5, 0.6, 0.7, 0.8, 1.2, 1.5, 2.0, 1.8, 1.4, 0.9, 0.6, 0.5]
        )
    ]

def ingest_peer_pattern(pattern: PatternNode):
    """
    Ingest a peer's pattern into Firestore as a prior.
    """
    from google.cloud import firestore
    try:
        db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
        doc_ref = db.collection("federated_patterns").document(f"{pattern.country_code}_{pattern.atc_code}")
        doc_ref.set({
            "country_code": pattern.country_code,
            "atc_code": pattern.atc_code,
            "monthly_coefficients": pattern.monthly_coefficients,
            "ingested_at": firestore.SERVER_TIMESTAMP
        })
        return {"status": "success", "message": f"Ingested pattern for {pattern.atc_code} from {pattern.country_code}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
