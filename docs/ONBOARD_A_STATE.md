# Adding a state

Uttar Pradesh was added on 2026-09-23 with the commands below, in one working
session. None of the original 200 centres' 2,794 stock lines changed status.
This is the runbook for the next state.

## What a state must already have

| Input | Where it comes from | Already loaded for all 37 states? |
|---|---|---|
| Facility register | NHM/MoHFW directory, `Data/India/geocode_health_centre.csv` | Yes, 200,438 rows |
| Distance to district HQ, lead time | `ingestion/set_lead_times.py`, computed for every facility in India | Yes |
| Staffing establishment | Rural Health Statistics 2021-22 | Yes, every state row |
| Bed capacity | IPHS 2022 norm applied to every PHC | Yes |
| **HMIS monthly indicators** | HMIS Standard Report C2 for the state, saved as `Data/India/<State>.xls` | **No. This is the one file to fetch** |

The HMIS files for all 36 states and UTs are already in `Data/India/`. Only
six are loaded.

## The commands

Run from the repository root with the project's virtual environment.

```
python -m ingestion.parse_hmis --state "<State>"
python -m ingestion.set_forecast_facilities --add-state "<State>"
python -m ingestion.generate_usage --add-state "<State>"
python -m ingestion.generate_bed_personnel --add-state "<State>"
python -m ingestion.train_forecast
python -m ingestion.build_supply_plan
python -m ingestion.build_facility_staffing
python -m ingestion.build_resource_status
python -m ingestion.build_facility_metrics
python -m ingestion.build_pattern_exchange
python -m ingestion.build_surge_signals
python -m ingestion.build_signal_labels
python -m ingestion.build_surge_supply
python -m ingestion.build_population_reach
python -m ingestion.build_waste_value
gcloud run deploy daysupply --source . --region asia-south1 --min-instances 1 --allow-unauthenticated
```

## What each `--add-state` step guarantees

- **`parse_hmis --state`** deletes and reloads only that state's rows, and
  fails unless every district carries all 21 drivers for all 12 months.
- **`set_forecast_facilities --add-state`** flags one PHC per district of the
  new state and never clears a flag elsewhere. It fails if any facility
  outside the state changed.
- **`generate_usage --add-state`** gives the new state its own random stream,
  replaces only that state's `source = 'seed'` rows, and fails if any medicine
  row outside the state changed. Captured reports are never deleted.
- **`generate_bed_personnel --add-state`** does the same for bed occupancy.

## Checks to run before training

The ARIMA_PLUS ceiling is **5,000 series**. Uttar Pradesh took the model from
2,794 to 3,818. Count what the new state would add before training:

```
python -m ingestion.generate_usage --add-state "<State>" --dry-run
```

The dry run prints the series it would generate. Roughly a third pass the
180-day training threshold. If the total would pass 5,000, stop and decide
which state or which items to drop first.

## What changed when Uttar Pradesh was added

| | Five states | Six states |
|---|---|---|
| Forecast PHCs | 200 | 275 |
| Districts | 116 | 191 |
| ARIMA_PLUS series | 2,794 | 3,818 |
| People in the demand-data footprint | 151.7 million | 260.8 million |
| Pattern exchange, flat → pooled wMAPE | 19.4% → 14.4% | 21.1% → 15.6% |

The original 200 PHCs kept all 2,794 stock lines. None changed status, and
the shortage count among them stayed at 597. Refitting moved 7 of their
forecasts by about 1%, and 524 of their 527 transfers came out identical.

## The one generated step, and how a real pilot replaces it

`generate_usage` produces a year of daily stock history, because no Indian
state publishes one. In a pilot, the state's own stock ledger, or a month of
reports through the Report page, replaces it. Every step after it reads
`resource_events` and does not care whether a row was generated or captured.

## One rule that applies only to added states

The facility register lists 6 PHCs in Pratapgarh and 8 in Siddharth Nagar,
against an Uttar Pradesh mean of 41 per district. Dividing a district's real
HMIS volume by 6 gave one PHC about 3,000 iron tablets a day. For added
states, a district listing fewer than half its state's mean PHCs per district
is treated as under-counted, and its denominator is raised to that floor.
Nine Uttar Pradesh districts were raised. The original five states keep their
exact method so their figures stay reproducible. See `Data/README.md` §20.
