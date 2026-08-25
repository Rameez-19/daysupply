import pytest
from app.redistribute import compute_transfer, haversine, get_recommendations

def test_haversine():
    # Test distance between two known points (e.g., ~111km per degree latitude)
    # 0,0 and 1,0
    dist = haversine(0.0, 0.0, 1.0, 0.0)
    assert 110 < dist < 112

def test_compute_transfer_never_creates_donor_deficit():
    # Donor has 100 on hand, demand is 10/day. Threshold is 14. Target is 28.
    # Donor target cover is 280.
    # Wait, if donor target is 280, donor available = max(0, 100 - 280) = 0
    qty = compute_transfer(
        receiver_on_hand=0,
        receiver_daily_demand=10,
        donor_on_hand=100,
        donor_daily_demand=10,
        threshold_days=14
    )
    assert qty == 0

    # Donor has 500 on hand, demand is 10/day. Threshold is 14. Target is 280.
    # Donor available = 500 - 280 = 220
    # Receiver needs 280.
    # Qty should be 220.
    qty2 = compute_transfer(
        receiver_on_hand=0,
        receiver_daily_demand=10,
        donor_on_hand=500,
        donor_daily_demand=10,
        threshold_days=14
    )
    assert qty2 == 220
    
    # Donor has 1000 on hand. Donor available = 720. Receiver needs 280. Qty = 280.
    qty3 = compute_transfer(
        receiver_on_hand=0,
        receiver_daily_demand=10,
        donor_on_hand=1000,
        donor_daily_demand=10,
        threshold_days=14
    )
    assert qty3 == 280

def test_get_recommendations():
    inventory_data = [
        {"facility_id": "fac1", "item_id": "ITEM-1", "on_hand": 10, "daily_demand": 10}, # DOC = 1 (Deficit, needs 270 to reach 28)
        {"facility_id": "fac2", "item_id": "ITEM-1", "on_hand": 1000, "daily_demand": 10}, # DOC = 100 (Surplus, can give 720)
        {"facility_id": "fac3", "item_id": "ITEM-1", "on_hand": 1000, "daily_demand": 10}  # DOC = 100 (Surplus, but far away)
    ]
    
    facilities_metadata = {
        "fac1": {"lat": 0.0, "lon": 0.0, "name": "Deficit Clinic"},
        "fac2": {"lat": 0.1, "lon": 0.0, "name": "Surplus Clinic Close"},  # ~11km
        "fac3": {"lat": 1.0, "lon": 0.0, "name": "Surplus Clinic Far"}     # ~111km
    }
    
    # Test with max_km = 50
    recs = get_recommendations(inventory_data, facilities_metadata, threshold_days=14, transfer_max_km=50.0)
    
    assert len(recs) == 1
    rec = recs[0]
    assert rec['from_facility_id'] == 'fac2'
    assert rec['to_facility_id'] == 'fac1'
    assert rec['quantity'] == 270 # (28 * 10) - 10
    
    # Verify post cover calculations
    # Donor post: 1000 - 270 = 730 / 10 = 73 days
    # Receiver post: 10 + 270 = 280 / 10 = 28 days
    assert rec['donor_post_cover'] == 73.0
    assert rec['receiver_post_cover'] == 28.0
