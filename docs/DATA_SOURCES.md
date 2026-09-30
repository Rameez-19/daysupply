# Data sources

Every dataset StockPulse uses, who publishes it, what it gives the product,
and how much of it is loaded. Figures are from [`CLAIMS.md`](CLAIMS.md); the
full provenance, parsing traps and methodology for each source are in
[`Data/README.md`](../Data/README.md).

## Public data, loaded

| # | Dataset | Publisher | What StockPulse uses it for | Loaded | Loaded by |
|---|---|---|---|---|---|
| 1 | **Health facility directory** (`geocode_health_centre.csv`) | National Health Mission, MoHFW (the "All India Health Centres Directory") | The register: every facility's name, type, state, district and coordinates. The map, distances, transfer partners | **All 200,438 facilities**, 37 states/UTs, 701 districts | `ingestion/load_facilities.py` → `facilities` |
| 2 | **HMIS 2019-20**, Standard Report C2 (`<State>.xls`) | Health Management Information System, MoHFW (hmis.mohfw.gov.in) | Monthly demand drivers per district: outpatient counts, confirmed malaria, childhood diarrhoea and pneumonia, admissions. Seasonality, forecasts, surge detection, the pattern exchange | **6 states, 212 districts**, 21 drivers loaded, 20 used. Files for every state and UT are on disk (see below) | `ingestion/parse_hmis.py` → `demand_reference` |
| 3 | **National List of Essential Medicines 2022** (`nlem2022.xlsx`) | MoHFW | The medicine catalogue every report is matched against, so the model never invents a drug | **All 385 medicines**, 27 therapeutic sections | `ingestion/parse_nlem.py`, `build_items.py` → `items` |
| 4 | **WHO ATC classification** | WHO Collaborating Centre for Drug Statistics Methodology | Groups medicines by therapeutic class, for substitution and for naming what a surge affects | Attached by hand where certain; left empty rather than guessed | `ingestion/atc_map.py` |
| 5 | **NPPA Compendium of Prices 2022** (ceiling prices, S.O. 1499(E), DPCO 2013) | National Pharmaceutical Pricing Authority | Prices the waste that expiry-first issuing avoids | 997 price lines extracted; 35 of 39 tracked medicines priced | `ingestion/extract_nppa_prices.py` → `nppa_ceiling_prices.csv` |
| 6 | **Rural Health Statistics 2021-22** (manpower as on 31 March 2022) | MoHFW | Sanctioned and filled posts for doctors, nurses, pharmacists and health assistants | **All 36 states**, 4 cadres | `ingestion/extract_rhs_2122.py`, `load_staffing.py` → `staffing` |
| 7 | **Rural Health Statistics 2017**, rural population per centre (Census 2011 base) | MoHFW | Population served, used to scale demand and to count people in reach | All states | `ingestion/load_facilities.py`, `build_population_reach.py` |
| 8 | **Indian Public Health Standards 2022**, Vol. III (PHC), pp. 46-47 | MoHFW | The bed norm per PHC: 2 essential and 4 desirable beds; 6 and 4 at a 24x7 PHC | Applied to all 29,733 PHCs | `ingestion/set_bed_capacity.py` |

Also on disk and used only as evidence, not loaded: Rural Health Statistics
2017 tables on pharmacists, infrastructure and area per centre; *Health
Dynamics of India 2023-24*, a newer edition of the RHS series that the
extractor cannot yet read; the IPHS 2022 CHC guidelines.

## Data the product creates

| Data | Where it comes from | Status |
|---|---|---|
| **Stock reports from the field** | Tap, voice, photo, scan and typed reports through the app, confirmed by the worker | **Real**, written to the `resource_events` ledger as they arrive |
| **Demand forecasts** | BigQuery ML ARIMA_PLUS trained on the ledger: 3,818 series | Real model, trained on the ledger below |
| **Lead times** | BigQuery GIS: real straight-line distance to the district headquarters, converted to 7-19 days | Real distance, assumed conversion |
| **Surge signals** | Modified z-score of each district-month against the pooled seasonal pattern, over real HMIS | Measured on real data |

## What is generated, and why

No one in India publishes a daily, per-facility stock position. That missing
dataset is the gap StockPulse exists to close, so until a state's own reports
flow in, it is generated and disclosed:

| Generated | Anchored to | Disclosed in |
|---|---|---|
| The daily stock ledger for the 275 forecast PHCs | The district's real HMIS volume for each medicine's driver, divided by its PHCs, shaped by that district's real monthly seasonality | `Data/README.md` §9, §20 |
| Bed occupancy | Real admission volumes and the IPHS bed norm | `Data/README.md` §17.2 |
| VEN class (Vital / Essential / Desirable) | NLEM section, with per-medicine overrides; NLEM does not publish VEN | `Data/README.md` §8 |

Staff attendance is **not** generated: the only attendance shown is what a
centre reports.

## All of India is in hand; six states run by design

| Dataset | Coverage on disk | Coverage live |
|---|---|---|
| Facility directory | All 37 states/UTs, 200,438 facilities | **All of it** |
| HMIS 2019-20 | Every state and UT, plus All-India | 6 states, 212 districts |
| NLEM 2022, NPPA prices, IPHS norms | National | National |
| Rural Health Statistics 2021-22 | All 36 states | All 36 states |
| Forecasting, ledger and early warning | — | 6 states, 191 districts, 275 PHCs, 3,818 series |

The only step not run for the remaining states is the per-state one: parse
that state's HMIS file, build its ledger and train its forecasts. It is a
runbook ([`ONBOARD_A_STATE.md`](ONBOARD_A_STATE.md)), and Uttar Pradesh went
through it in one working session without changing any other state's figures.

**Why it stops at six.** This build runs under a cost guard: at most 5,000
ARIMA_PLUS series and about 10 GB per BigQuery query, on one Cloud Run
instance. Six states use 3,818 series, 76.4% of it. All of India is 29,733
PHCs × 39 forecast medicines, over **1.1 million candidate series**; at
today's training rate about **413,000 trained series**, more than 80 times the
guard. That is a production deployment, not a hackathon one, and it needs:

- **Forecasting at scale:** one ARIMA_PLUS model per state, retrained on a
  schedule, on reserved BigQuery capacity rather than on-demand queries.
- **A ledger built for volume:** `resource_events` partitioned by date and
  clustered by state and facility.
- **Serving at volume:** Cloud Run scaling out across instances, and Vertex
  AI quota sized for every PHC's daily reports.
- **A state's own feeds:** its stock register (e-Aushadhi or DVDMS) replacing
  the generated ledger, its real lead times replacing the distance proxy, and
  an SMS gateway.

None of that changes the design; each is a capacity setting or a data feed.
