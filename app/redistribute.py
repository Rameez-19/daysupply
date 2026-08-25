import math
import uuid
from typing import List, Dict, Optional

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes distance in km between two lat/lon pairs."""
    R = 6371.0 # Earth radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def compute_transfer(
    receiver_on_hand: int,
    receiver_daily_demand: float,
    donor_on_hand: int,
    donor_daily_demand: float,
    threshold_days: int
) -> int:
    """Calculates safe transfer quantity."""
    # Units receiver needs to reach 2x threshold
    target_cover = 2 * threshold_days
    receiver_needed = max(0, int(target_cover * receiver_daily_demand) - receiver_on_hand)
    
    # Units donor can give while maintaining 2x threshold
    donor_available = max(0, donor_on_hand - int(target_cover * donor_daily_demand))
    
    return min(receiver_needed, donor_available)

def get_recommendations(
    inventory_data: List[Dict],
    facilities_metadata: Dict[str, Dict],
    threshold_days: int,
    transfer_max_km: float
) -> List[Dict]:
    """
    inventory_data: list of dicts with:
       facility_id, item_id, on_hand, daily_demand
    facilities_metadata: dict mapping facility_id -> {lat, lon, name}
    """
    
    # 1. Compute days of cover
    enriched = []
    for row in inventory_data:
        doc = float('inf')
        if row['daily_demand'] > 0:
            doc = row['on_hand'] / row['daily_demand']
        row['days_of_cover'] = doc
        enriched.append(row)
        
    # 2. Deficit and surplus separation
    deficits = [r for r in enriched if r['days_of_cover'] < threshold_days]
    surpluses = [r for r in enriched if r['days_of_cover'] > 3 * threshold_days]
    
    recommendations = []
    
    for deficit in deficits:
        item_id = deficit['item_id']
        fac_a = deficit['facility_id']
        meta_a = facilities_metadata.get(fac_a)
        if not meta_a:
            continue
            
        best_candidate = None
        best_score = -1.0
        best_transfer_qty = 0
        best_donor_post_cover = 0.0
        best_receiver_post_cover = 0.0
        best_dist = 0.0
        
        # 3. Find matching surplus facilities
        for surplus in surpluses:
            if surplus['item_id'] != item_id:
                continue
                
            fac_b = surplus['facility_id']
            meta_b = facilities_metadata.get(fac_b)
            if not meta_b:
                continue
                
            dist_km = haversine(
                meta_a['lat'], meta_a['lon'], 
                meta_b['lat'], meta_b['lon']
            )
            
            if dist_km > transfer_max_km or dist_km == 0:
                continue
                
            # 5. Transfer quantity
            qty = compute_transfer(
                deficit['on_hand'], deficit['daily_demand'],
                surplus['on_hand'], surplus['daily_demand'],
                threshold_days
            )
            
            if qty <= 0:
                continue
                
            donor_post_on_hand = surplus['on_hand'] - qty
            donor_post_cover = donor_post_on_hand / surplus['daily_demand'] if surplus['daily_demand'] > 0 else float('inf')
            
            # 4. Score: surplus_days_after_transfer x (1 / distance_km)
            score = donor_post_cover * (1.0 / dist_km)
            
            if score > best_score:
                best_score = score
                receiver_post_on_hand = deficit['on_hand'] + qty
                best_receiver_post_cover = receiver_post_on_hand / deficit['daily_demand'] if deficit['daily_demand'] > 0 else float('inf')
                best_transfer_qty = qty
                best_candidate = surplus
                best_donor_post_cover = donor_post_cover
                best_dist = dist_km
                
        # 6. Emit best recommendation for this deficit
        if best_candidate:
            recommendations.append({
                "recommendation_id": str(uuid.uuid4()),
                "item_id": item_id,
                "from_facility_id": best_candidate['facility_id'],
                "to_facility_id": fac_a,
                "quantity": best_transfer_qty,
                "distance_km": round(best_dist, 2),
                "donor_post_cover": round(best_donor_post_cover, 1),
                "receiver_post_cover": round(best_receiver_post_cover, 1),
                "score": round(best_score, 2),
                "status": "pending"
            })
            
    return sorted(recommendations, key=lambda x: x['score'], reverse=True)
