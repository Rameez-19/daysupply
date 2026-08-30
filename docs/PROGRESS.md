# DaySupply — Progress Log

| Date | Block | What's done | What's next |
|------|-------|------------|-------------|
| 2026-08-22 | 1 ✅ | FastAPI skeleton, Dockerfile, Cloud Run ready, GitHub pushed | Block 2: facility ingestion |
| 2026-08-22 | 2 ✅ | India (200,438) + Brazil (50,697) facility loaders, dry-run tested | GCP setup, then BigQuery upload |
| 2026-08-22 | 3 ✅ | 15-item master with ATC crosswalk. HMIS parser → `demand_reference` | Block 4: Gemini voice capture |
| 2026-08-25 | 4 ✅ | Voice capture API, Pydantic models, Gemini prompt & Fuzzy matching | Block 5: Generator |
| 2026-08-25 | 5 ✅ | 1.1M usage generator, BigQuery ARIMA_PLUS SQL, Days of Cover | Block 6: Redistribution Engine |
| 2026-08-25 | 6 ✅ | Haversine distance matching, strict donor safety thresholds, scoring | Block 7: Vanilla JS PWA |
| 2026-08-25 | 7 ✅ | Vanilla JS PWA, IndexedDB Offline queue, static mount in FastAPI | Block 8: Federated Pattern Exchange |
| 2026-08-25 | 8 ✅ | `app/patterns.py` and `POST /api/v1/patterns` endpoints added | Block 9: Submission Package |
| 2026-08-25 | 9 ✅ | Project `README.md` and complete Walkthrough finalized | Submit! |
| 2026-08-29 | A ✅ | All 200,438 real facilities in BigQuery (37 states, 668 districts, 7,092 demo PHCs). Dashboard geography rewired to BigQuery — no hardcoded arrays. Cost guard rails + caching. `Data/README.md` now tracked | Block B: real ARIMA_PLUS forecasting |
| 2026-08-30 | A+ ✅ | `geo_summary` pre-aggregate + startup prewarm: dropdown reads 10.9 MB → 21.6 KB, 1.7–6.5s → <1 ms. Corrected handover §1 (BigQuery did exist; 251,135 rows from a double-append) | Block B: NLEM catalogue, usage generator, ARIMA_PLUS |
| 2026-08-30 | B ✅ | Full NLEM 2022 catalogue (385 items, 264 ATC, VEN). 200 Telangana PHCs × 39 items × 365d = 1.86M stock_events with REAL HMIS seasonality join. **ARIMA_PLUS trained: 3,649 series in 15.5s.** ML.FORECAST serving; sine wave, JS-hardcoded charts and random expiry all deleted | Block C: lead-time reorder points, VEN alert ranking, FEFO |
| 2026-08-30 | B+ ✅ | HMIS widened to 5 states: 137 districts, 18,084 rows (was Telangana only). 200 forecast PHCs now span 5 states / 116 districts. Retrained: **4,295 series in 15.4s** — 86% of the 5,000 ceiling | Block C: reorder points, VEN, FEFO, substitution |
| 2026-08-30 | C ✅ | Lead-time reorder points (7-19d from distance to district HQ), VEN-weighted alerts, FEFO with expiry write-offs, ATC substitution, reporting consistency. **get_demo_alerts and get_demo_recommendations deleted.** FEFO avoids 94,542 units of waste (57%, measured vs FIFO) | Block D: cross-district exchange, export endpoint, architecture diagram |
| 2026-08-30 | D ✅ | Cross-district exchange: 4-arm hold-out shows demographic matching LOSES (45.1% vs 25.8% flat); pooled vector wins at 23.2%. Export endpoint + architecture.png. Chat mode built, barcode routed through the server — three modes now genuinely share one pipeline. Two-stage matcher handles embedded drug names. `captures_today` real (0). Data quality surfaced at /api/v1/data-quality | GEMINI_API_KEY not set on Cloud Run — voice/chat 403 in production |
