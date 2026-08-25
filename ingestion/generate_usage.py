import os
import uuid
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")
DATASET_ID = "daysupply"
TABLE_ID = "stock_events"

def generate_usage():
    client = bigquery.Client(project=PROJECT_ID)
    
    # 1. Fetch demo facilities
    facilities_query = f"""
        SELECT facility_id, population_served 
        FROM `{PROJECT_ID}.{DATASET_ID}.facilities` 
        WHERE is_demo_facility = TRUE
        LIMIT 200
    """
    try:
        facilities_df = client.query(facilities_query).to_dataframe()
    except Exception as e:
        print(f"Could not fetch facilities, using dummy data for generation... Error: {e}")
        facilities_df = pd.DataFrame({
            'facility_id': [f"IN-DEMO-{i}" for i in range(200)],
            'population_served': np.random.randint(3000, 30000, 200)
        })

    # 2. Fetch items
    items_query = f"""
        SELECT item_id, demand_driver 
        FROM `{PROJECT_ID}.{DATASET_ID}.items`
    """
    try:
        items_df = client.query(items_query).to_dataframe()
    except Exception as e:
        print(f"Could not fetch items, using dummy data... Error: {e}")
        items_df = pd.DataFrame({
            'item_id': [f"ITEM-{str(i).zfill(3)}" for i in range(1, 16)],
            'demand_driver': ["Outpatient"] * 15
        })

    np.random.seed(42) # Deterministic seed
    
    start_date = datetime.utcnow() - timedelta(days=365)
    dates = [start_date + timedelta(days=i) for i in range(365)]
    
    events = []
    
    print("Generating events...")
    # Loop over facilities and items
    for _, fac in facilities_df.iterrows():
        fac_id = fac['facility_id']
        pop = fac['population_served'] or 5000
        pop_scale = pop / 5000.0  # Base line is 5k population
        
        for _, item in items_df.iterrows():
            item_id = item['item_id']
            driver = item['demand_driver']
            
            # Base daily demand for this item
            base_demand = np.random.uniform(5, 20) * pop_scale
            
            for d in dates:
                # 3. Day of week variation (weekends less busy)
                dow = d.weekday()
                dow_factor = 0.5 if dow >= 5 else 1.1
                
                # 4. Seasonality (dummy representation of HMIS seasonality)
                # In reality this would join against demand_reference
                month = d.month
                season_factor = 1.0 + (0.2 * np.sin(month * np.pi / 6))
                
                expected_demand = base_demand * dow_factor * season_factor
                
                # 5. Poisson noise
                actual_dispensed = np.random.poisson(expected_demand)
                
                if actual_dispensed > 0:
                    events.append({
                        "event_id": str(uuid.uuid4()),
                        "facility_id": fac_id,
                        "item_id": item_id,
                        "event_type": "dispensed",
                        "quantity": actual_dispensed,
                        "event_ts": d.isoformat(),
                        "source": "seed",
                        "confidence": 1.0,
                        "raw_transcript": None
                    })
                    
    df = pd.DataFrame(events)
    print(f"Generated {len(df)} events. Uploading to BigQuery...")
    
    # Upload to BigQuery partitioned by date, clustered by facility_id
    schema = [
        bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("facility_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("quantity", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("event_ts", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("confidence", "FLOAT", mode="REQUIRED"),
        bigquery.SchemaField("raw_transcript", "STRING", mode="NULLABLE")
    ]
    
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="event_ts",
        ),
        clustering_fields=["facility_id"]
    )
    
    table_ref = client.dataset(DATASET_ID).table(TABLE_ID)
    try:
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()
        print("Upload complete!")
    except Exception as e:
        print(f"Failed to upload to BigQuery: {e}")

if __name__ == "__main__":
    generate_usage()
