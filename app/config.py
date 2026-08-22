import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict

class CountryConfig(BaseModel):
    country_code: str
    languages: List[str]
    admin_labels: Dict[str, str]
    facility_label: str
    data_sources: List[str]
    stockout_threshold_days: int
    transfer_max_km: int
    demo_admin_l2: List[str]

def load_config(country_code: str = None) -> CountryConfig:
    if not country_code:
        country_code = os.getenv("COUNTRY_CODE", "IN")
    
    file_name = f"{country_code.lower()}.yaml"
    config_path = Path(__file__).parent.parent / "config" / file_name
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    return CountryConfig(**data)

# Global active config instance
settings = load_config()
