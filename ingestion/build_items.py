import pandas as pd
from google.cloud import bigquery
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")
DATASET_ID = "daysupply"
TABLE_ID = "items"

def get_items_data():
    return [
        {
            "item_id": "ITEM-001",
            "atc_code": "A10BA02",
            "display_name": "Metformin 500mg",
            "local_name_in": "Metformin 500mg Tablet",
            "local_name_br": "Cloridrato de Metformina 500 mg",
            "spoken_variants": ["metformin", "sugar pill", "diabetes tablet", "metformina"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Diabetes"
        },
        {
            "item_id": "ITEM-002",
            "atc_code": "C08CA01",
            "display_name": "Amlodipine 5mg",
            "local_name_in": "Amlodipine 5mg Tablet",
            "local_name_br": "Besilato de Anlodipino 5 mg",
            "spoken_variants": ["amlodipine", "bp pill", "blood pressure tablet", "anlodipino"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Hypertension"
        },
        {
            "item_id": "ITEM-003",
            "atc_code": "N03AB02",
            "display_name": "Phenytoin 100mg",
            "local_name_in": "Phenytoin Sodium 100mg Tablet",
            "local_name_br": "Fenitoína 100 mg",
            "spoken_variants": ["phenytoin", "epilepsy medicine", "fenitoina"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Epilepsy"
        },
        {
            "item_id": "ITEM-004",
            "atc_code": "N06AB03",
            "display_name": "Fluoxetine 20mg",
            "local_name_in": "Fluoxetine 20mg Capsule",
            "local_name_br": "Cloridrato de Fluoxetina 20 mg",
            "spoken_variants": ["fluoxetine", "depression pill", "fluoxetina"],
            "unit": "capsule",
            "demand_driver": "Outpatient - Mental illness"
        },
        {
            "item_id": "ITEM-005",
            "atc_code": "M01AE01",
            "display_name": "Ibuprofen 400mg",
            "local_name_in": "Ibuprofen 400mg Tablet",
            "local_name_br": "Ibuprofeno 400 mg",
            "spoken_variants": ["ibuprofen", "painkiller", "toothache pill", "ibuprofeno"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Dental"
        },
        {
            "item_id": "ITEM-006",
            "atc_code": "S01AE03",
            "display_name": "Ciprofloxacin Eye Drops",
            "local_name_in": "Ciprofloxacin 0.3% Eye Drops",
            "local_name_br": "Cloridrato de Ciprofloxacino 3,5 mg/g Pomada Oftálmica",
            "spoken_variants": ["ciprofloxacin", "eye drops", "eye infection", "ciprofloxacino", "colírio"],
            "unit": "bottle",
            "demand_driver": "Outpatient - Ophthalmic Related"
        },
        {
            "item_id": "ITEM-007",
            "atc_code": "B01AC06",
            "display_name": "Aspirin 75mg",
            "local_name_in": "Acetylsalicylic acid 75mg Tablet",
            "local_name_br": "Ácido Acetilsalicílico 100 mg",
            "spoken_variants": ["aspirin", "heart pill", "blood thinner", "aspirina"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Acute Heart Diseases"
        },
        {
            "item_id": "ITEM-008",
            "atc_code": "C10AA05",
            "display_name": "Atorvastatin 20mg",
            "local_name_in": "Atorvastatin 20mg Tablet",
            "local_name_br": "Atorvastatina Cálcica 20 mg",
            "spoken_variants": ["atorvastatin", "cholesterol pill", "atorvastatina"],
            "unit": "tablet",
            "demand_driver": "Outpatient - Stroke (Paralysis)"
        },
        {
            "item_id": "ITEM-009",
            "atc_code": "P01BA01",
            "display_name": "Chloroquine 150mg",
            "local_name_in": "Chloroquine Phosphate 150mg Tablet",
            "local_name_br": "Difosfato de Cloroquina 150 mg",
            "spoken_variants": ["chloroquine", "malaria pill", "cloroquina"],
            "unit": "tablet",
            "demand_driver": "Malaria"
        },
        {
            "item_id": "ITEM-010",
            "atc_code": "P01BF01",
            "display_name": "Artemether/Lumefantrine",
            "local_name_in": "Artemether 20mg + Lumefantrine 120mg Tablet",
            "local_name_br": "Arteméter + Lumefantrina 20 mg + 120 mg",
            "spoken_variants": ["artemether", "lumefantrine", "malaria combo", "arteméter"],
            "unit": "tablet",
            "demand_driver": "Malaria"
        },
        {
            "item_id": "ITEM-011",
            "atc_code": "A07CA",
            "display_name": "ORS Sachets",
            "local_name_in": "Oral Rehydration Salts",
            "local_name_br": "Sais para Reidratação Oral",
            "spoken_variants": ["ors", "rehydration", "sro", "soro", "ors packet", "ors sachet"],
            "unit": "sachet",
            "demand_driver": "Childhood Diseases"
        },
        {
            "item_id": "ITEM-012",
            "atc_code": "A12CB01",
            "display_name": "Zinc Sulfate 20mg",
            "local_name_in": "Zinc Sulfate 20mg Tablet",
            "local_name_br": "Sulfato de Zinco 20 mg",
            "spoken_variants": ["zinc", "zinc tablet", "zinco"],
            "unit": "tablet",
            "demand_driver": "Childhood Diseases"
        },
        {
            "item_id": "ITEM-013",
            "atc_code": "J01CA04",
            "display_name": "Amoxicillin 250mg",
            "local_name_in": "Amoxicillin 250mg Capsule",
            "local_name_br": "Amoxicilina 250 mg/5 mL Pó para Suspensão",
            "spoken_variants": ["amoxicillin", "antibiotic", "amoxicilina"],
            "unit": "capsule",
            "demand_driver": "Childhood Diseases"
        },
        {
            "item_id": "ITEM-014",
            "atc_code": "N02BE01",
            "display_name": "Paracetamol 500mg",
            "local_name_in": "Paracetamol 500mg Tablet",
            "local_name_br": "Paracetamol 500 mg",
            "spoken_variants": ["paracetamol", "fever pill", "crocin", "tylenol"],
            "unit": "tablet",
            "demand_driver": "Inpatient counts"
        },
        {
            "item_id": "ITEM-015",
            "atc_code": "J01DD04",
            "display_name": "Ceftriaxone 1g",
            "local_name_in": "Ceftriaxone 1g Injection",
            "local_name_br": "Ceftriaxona Sódica 1 g Pó para Solução Injetável",
            "spoken_variants": ["ceftriaxone", "injection", "severe antibiotic", "ceftriaxona"],
            "unit": "vial",
            "demand_driver": "Inpatient counts"
        }
    ]

def upload_items_to_bigquery():
    client = bigquery.Client(project=PROJECT_ID)
    dataset_ref = client.dataset(DATASET_ID)
    table_ref = dataset_ref.table(TABLE_ID)

    items = get_items_data()
    df = pd.DataFrame(items)

    schema = [
        bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("atc_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("display_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("local_name_in", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("local_name_br", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("spoken_variants", "STRING", mode="REPEATED"),
        bigquery.SchemaField("unit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("demand_driver", "STRING", mode="REQUIRED")
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )

    print(f"Uploading {len(df)} items to {PROJECT_ID}.{DATASET_ID}.{TABLE_ID}...")
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    print("Items loaded successfully.")

if __name__ == "__main__":
    upload_items_to_bigquery()
