import pandas as pd
from google.cloud import bigquery
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")
DATASET_ID = "daysupply"
TABLE_ID = "demand_reference"
FILE_PATH = Path("Data/India/Telangana.xls")

# Map of extracted HMIS indicators to our standard demand drivers
INDICATOR_MAP = {
    "Outpatient - Diabetes": "Outpatient - Diabetes",
    "Outpatient - Hypertension": "Outpatient - Hypertension",
    "Outpatient - Epilepsy": "Outpatient - Epilepsy",
    "Outpatient - Mental illness": "Outpatient - Mental illness",
    "Outpatient - Dental": "Outpatient - Dental",
    "Outpatient - Ophthalmic Related": "Outpatient - Ophthalmic Related",
    "Outpatient - Acute Heart Diseases": "Outpatient - Acute Heart Diseases",
    "Outpatient - Stroke (Paralysis)": "Outpatient - Stroke (Paralysis)",
    # These exact strings might need adjustment based on the actual HMIS data,
    # but we will fall back to partial matching if needed.
    "Malaria": "Malaria",
    "Childhood Diseases": "Childhood Diseases",
    "Total Inpatients": "Inpatient counts" 
}

def parse_hmis_file(file_path: Path) -> pd.DataFrame:
    print(f"Loading {file_path}... (This might take a minute)")
    with open(file_path, "r", encoding="latin-1") as f:
        df = pd.read_html(f)[0]
    
    print("Extracting data...")
    # The dataframe has a MultiIndex on columns.
    # Level 0 is the Month (or empty for metadata), Level 1 is the category (Total, Public, etc.)
    
    # Metadata columns are usually the first few. Let's find District and Indicator.
    # District is typically at iloc[:, 0] and Indicator at iloc[:, 2]
    districts = df.iloc[1:, 0]
    indicators = df.iloc[1:, 2]
    
    months = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]
    
    extracted_data = []
    
    # Iterate through all rows
    for idx in range(1, len(df)):
        district = districts.iloc[idx - 1]
        indicator = indicators.iloc[idx - 1]
        
        if pd.isna(district) or pd.isna(indicator):
            continue
            
        indicator = str(indicator).strip()
        
        # Match indicator
        mapped_driver = None
        for key in ["Outpatient - Diabetes", "Outpatient - Hypertension", "Outpatient - Epilepsy",
                   "Outpatient - Mental illness", "Outpatient - Dental", "Outpatient - Ophthalmic Related",
                   "Outpatient - Acute Heart Diseases", "Outpatient - Stroke (Paralysis)"]:
            if key.lower() in indicator.lower():
                mapped_driver = key
                break
                
        if not mapped_driver:
            if "malaria" in indicator.lower():
                mapped_driver = "Malaria"
            elif "child" in indicator.lower() and "disease" in indicator.lower():
                mapped_driver = "Childhood Diseases"
            elif "inpatient" in indicator.lower():
                mapped_driver = "Inpatient counts"
                
        if not mapped_driver:
            continue
            
        # Extract monthly totals
        for month in months:
            try:
                # Find the column for this month's Total
                val = df.loc[idx, (month, "Total [(A+B) or (C+D)]")]
                if pd.isna(val) or val == '':
                    val = 0
                else:
                    val = float(val)
                
                extracted_data.append({
                    "country_code": "IN",
                    "admin_l2": district,
                    "month": month,
                    "indicator": mapped_driver,
                    "value": val
                })
            except KeyError:
                pass
                
    return pd.DataFrame(extracted_data)

def upload_to_bigquery(df: pd.DataFrame):
    client = bigquery.Client(project=PROJECT_ID)
    dataset_ref = client.dataset(DATASET_ID)
    table_ref = dataset_ref.table(TABLE_ID)

    schema = [
        bigquery.SchemaField("country_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("admin_l2", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("month", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("indicator", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("value", "FLOAT", mode="REQUIRED"),
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )

    print(f"Uploading {len(df)} records to {PROJECT_ID}.{DATASET_ID}.{TABLE_ID}...")
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    print("HMIS data loaded successfully.")

if __name__ == "__main__":
    if not FILE_PATH.exists():
        print(f"Error: {FILE_PATH} not found.")
    else:
        df = parse_hmis_file(FILE_PATH)
        # We might have duplicate rows per district-month-indicator because some indicators
        # like Malaria might have multiple sub-indicators (e.g. Pf, Pv). We sum them up.
        if not df.empty:
            df_grouped = df.groupby(["country_code", "admin_l2", "month", "indicator"], as_index=False)["value"].sum()
            upload_to_bigquery(df_grouped)
        else:
            print("No matching data found.")
