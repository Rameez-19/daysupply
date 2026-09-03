# StockPulse — Progress Log

> **A dated log. NOT AUTHORITATIVE.**
> Each row records what was true on that date and is deliberately left
> as written when a figure is later superseded — rewriting history
> would destroy the record of what changed and when.
>
> **For any current figure, use `docs/CLAIMS.md`.** Several numbers
> below have since been restated; the footnote at the end names them.
>
> **Document hierarchy — four files, four jobs:**
>
> | File | Authority |
> |---|---|
> | **`docs/MASTER_PROMPT.md`** | **Governing spec.** What we are building, and the constraints it must respect |
> | **`docs/CLAIMS.md`** | **Source of truth for every figure.** If a number is not in there, it is not evidence and does not go in front of a judge |
> | **`docs/HANDOVER.md`** | **Current state.** What is real, what is generated, what is broken, and every open decision |
> | **`docs/PROGRESS.md`** | **A dated log. Not authoritative.** It records what was true on a date; superseded figures are left as written |


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
| 2026-08-30 | D+ ✅ | Parsed all 368 HMIS data items; drivers now selected by code, not label. Malaria driver was 99.8% blood smears (amplitude 1.6x → 3.9x). Childhood Diseases split into 4 real drivers; Albendazole reveals a 22.3x National Deworming Day spike. All 6 flat-baseline items converted. 21 drivers, 34,524 rows. Retrained 2,794 series (threshold 300d → 180d) | Corrected Block B validation claim; deck/video still outside repo |
| 2026-08-31 | F1 ✅ | Multi-resource schema: stock_events → resource_events (medicine/bed/personnel), stock_events kept as a view. Bed capacity from IPHS 2022 (29,733 PHCs, 178,398 beds) — real norm, 24x7 left unknown. Staffing from RHS 2017 with real vacancy (doctors 20.1%, male HA 46.0%). Beds → referrals, personnel → reallocation. **Medicine path byte-identical**; tests 113 → 143 | Part 2: surge detection |
| 2026-09-01 | F2 ✅ | Surge = departure from the **pooled** seasonal vector, not from flat. Classical z is bounded at 3.175 with 12 monthly points and measures 3.17 — saturated, so Iglewicz-Hoaglin modified z (3.5) fires instead, plus ratio ≥1.5 and ≥100 events. 1,295 surges / 58,932 series-months. Worked example: Brihan Mumbai malaria January, 2,345 vs 988 expected, 2.37×, modified z 6.54 vs classical 2.58 (a 3-sigma rule misses it). Under surge needs-reorder 100→198, 145 of 322 can only be served laterally; the transfer-only share rises monotonically with lead time (43.5→47.9→80.0%). Absorption: 59.0% of district-classes hold 2×, 30.1% hold 3×, 4.3% hold 5×. Scenario mode computes live at any multiplier. **Reach counted once: 151.7M across 105 districts / 5 states in the demand footprint, 793.7M national — 95.2% of Census 2011 rural India, the tiling check.** Series unchanged at 2,794 | Deploy, deck and video; 50,697 Brazil rows still in `facilities` |
| 2026-09-01 | Freeze prep | Brazil rows deleted: `COUNT(*)` on `facilities` is now 200,438 (was 251,135), one country code, asserted permanently in the loader. **docs/CLAIMS.md** added as the single source of truth for every judge-facing number. Verifying it found four stale figure sets, now corrected everywhere: FEFO waste **26,612 (44.7%)** not 94,542 (57%); wMAPE **19.4 / 71.2 / 16.4 / 14.4** not 25.8 / 45.1 / 32.5 / 23.2; malaria amplitude **4.52x** not 3.9x; Albendazole **22.64x / 5.66x August** not 22.3x / 6.24x. District count is **701** (state-district pairs), not 668 (distinct names). One claim marked UNTRACEABLE and replaced with a real transfer. Full production walk of 40 endpoints | **Voice and chat still 403 in production** — the key on Cloud Run is a GCP API key restricted to `aiplatform.googleapis.com`, and `generativelanguage.googleapis.com` is not enabled on the project. Deck and video still to build |
| 2026-09-02 | FREEZE | **Capture updates stock in real time.** `current_stock` and `reorder_status` are now views (measured: 149.6 MB / $0.00085 per query, ~$26/month); `ML.FORECAST` cannot live in a view so demand moved to a `demand_baseline` table. Verified live: capture -> counter 0->2, on-hand +1000, **alert cleared 18->17**. Vague-quantity prompt rule added as a `system_instruction` move: "teen char strip" now holds for review at 0.4 instead of writing through at 0.6. 503 retry with backoff and model fallback. Full walk of 40 endpoints, all 200; CLAIMS.md re-verified end to end and LIVE figures marked | Deck and video — every number from `docs/CLAIMS.md` |

> **Note on rows above.** The Block C and Block D rows record what was measured *at that time*. Two of those figures were later superseded when the Block D+ driver corrections regenerated the demand series and the ledger: FEFO waste avoided (94,542 / 57% became **26,612 / 44.7%**) and the pattern-exchange wMAPE arms (25.8 / 45.1 / 32.5 / 23.2 became **19.4 / 71.2 / 16.4 / 14.4**). The log is left as written because it is a log; `docs/CLAIMS.md` is the source of truth for anything quoted.
