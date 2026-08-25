import os
from google.cloud import bigquery

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply")
DATASET_ID = "daysupply"

def train_forecast_model():
    """Trains the ARIMA_PLUS model in BigQuery."""
    client = bigquery.Client(project=PROJECT_ID)
    
    query = f"""
    CREATE OR REPLACE MODEL `{PROJECT_ID}.{DATASET_ID}.demand_forecast`
    OPTIONS(
      model_type='ARIMA_PLUS',
      time_series_timestamp_col='event_date',
      time_series_data_col='qty_dispensed',
      time_series_id_col='series_id',
      horizon=30,
      auto_arima=TRUE,
      data_frequency='DAILY'
    ) AS
    SELECT
      DATE(event_ts) AS event_date,
      CONCAT(facility_id, '|', item_id) AS series_id,
      SUM(quantity) AS qty_dispensed
    FROM `{PROJECT_ID}.{DATASET_ID}.stock_events`
    WHERE event_type = 'dispensed'
      AND facility_id IN (
        SELECT facility_id FROM `{PROJECT_ID}.{DATASET_ID}.facilities` WHERE is_demo_facility
      )
    GROUP BY 1, 2;
    """
    
    print("Training ARIMA_PLUS model... this may take a few minutes.")
    job = client.query(query)
    job.result()  # Waits for the query to finish
    print("ARIMA_PLUS model trained successfully!")
    return True

def get_forecast_daily_demand(facility_id: str, item_id: str) -> float:
    """Returns the forecasted daily demand for a given facility and item."""
    client = bigquery.Client(project=PROJECT_ID)
    series_id = f"{facility_id}|{item_id}"
    
    query = f"""
    SELECT AVG(forecast_value) as daily_demand
    FROM ML.FORECAST(MODEL `{PROJECT_ID}.{DATASET_ID}.demand_forecast`, STRUCT(30 AS horizon))
    WHERE series_id = @series_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("series_id", "STRING", series_id)
        ]
    )
    
    try:
        results = client.query(query, job_config=job_config).result()
        for row in results:
            if row.daily_demand is not None:
                return float(row.daily_demand)
    except Exception as e:
        # Fallback to moving average if model doesn't exist or errors
        print(f"ARIMA_PLUS forecast failed: {e}. Falling back to 30-day moving average.")
    
    # Fallback Moving Average
    fallback_query = f"""
    SELECT IFNULL(SUM(quantity) / 30.0, 0.0) as daily_demand
    FROM `{PROJECT_ID}.{DATASET_ID}.stock_events`
    WHERE facility_id = @facility_id 
      AND item_id = @item_id
      AND event_type = 'dispensed'
      AND event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("facility_id", "STRING", facility_id),
            bigquery.ScalarQueryParameter("item_id", "STRING", item_id)
        ]
    )
    
    try:
        results = client.query(fallback_query, job_config=job_config).result()
        for row in results:
            return float(row.daily_demand)
    except Exception as e:
        print(f"Fallback moving average failed: {e}")
        return 0.0
        
def compute_days_of_cover(on_hand: int, forecast_daily_demand: float) -> float:
    if forecast_daily_demand <= 0:
        return float('inf') # Infinite days of cover if no demand
    return float(on_hand) / forecast_daily_demand

def check_alert(facility_id: str, item_id: str, on_hand: int, threshold_days: int) -> dict:
    daily_demand = get_forecast_daily_demand(facility_id, item_id)
    doc = compute_days_of_cover(on_hand, daily_demand)
    
    alert = None
    if doc < threshold_days:
        alert = {
            "facility_id": facility_id,
            "item_id": item_id,
            "days_of_cover": round(doc, 1),
            "threshold": threshold_days,
            "status": "active",
            "daily_demand": round(daily_demand, 2)
        }
    return alert
