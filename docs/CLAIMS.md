# CLAIMS — the single source of truth for every number

> **This file is the source of truth for every figure.**
> The governing spec is `docs/MASTER_PROMPT.md`; current state is
> `docs/HANDOVER.md`; `docs/PROGRESS.md` is a dated log and is not
> authoritative for any number.
>
> **Document hierarchy — four files, four jobs:**
>
> | File | Authority |
> |---|---|
> | **`docs/MASTER_PROMPT.md`** | **Governing spec.** What we are building, and the constraints it must respect |
> | **`docs/CLAIMS.md`** | **Source of truth for every figure.** If a number is not in there, it is not evidence and does not go in front of a judge |
> | **`docs/HANDOVER.md`** | **Current state.** What is real, what is generated, what is broken, and every open decision |
> | **`docs/PROGRESS.md`** | **A dated log. Not authoritative.** It records what was true on a date; superseded figures are left as written |


**Rule: if a figure is not in this file, it does not go in front of a judge.**
Not in the deck, not in the video, not in the README, not spoken aloud.

Every row gives the figure, what it is derived from, whether the inputs are
**real** or **generated**, and where in the code it is computed. Anything that
cannot be traced to code is marked **UNTRACEABLE** and must not be used.

Verified against the live BigQuery dataset on **2026-09-02**, after
`current_stock` and `reorder_status` became views.

> ### Some figures are now LIVE and will move
>
> `current_stock` and `reorder_status` are views derived from the ledger at
> read time, so **every capture changes the stock position**. Alert counts,
> recommendation counts, units to move and total on-hand are *current values,
> not constants* — quoting them means quoting them as of a moment.
>
> Rows below marked **LIVE** move when anyone speaks into the app. Everything
> else is stable between ingestion runs. Re-run
> `scratchpad/verify_claims.py`-style checks before the deck is finalised, and
> **do not hardcode a LIVE figure into a test** — one test did, and it broke
> the first time a real capture landed.

**Status vocabulary:**

| | |
|---|---|
| **REAL** | every input is published government data, loaded unmodified |
| **REAL SOURCE, DERIVED** | a published figure applied at a granularity the source does not publish |
| **GENERATED** | synthesised by us, anchored to a real driver, disclosed as such |
| **MEASURED** | computed by us from the ledger, including generated inputs — the *method* is real, the inputs may not be |

---

## 0. Six states — the current figures (2026-09-23)

> **Read this first.** Uttar Pradesh was added on 2026-09-23 (runbook:
> `docs/ONBOARD_A_STATE.md`; disclosure: `Data/README.md` §20). Sections 1 to
> 10 below were measured on the original five states and are kept as the
> record of that run. **Where this table gives a figure, this table is
> current and the older one is superseded.** Quote the six-state figure.

| Figure | Five states (superseded) | **Six states (current)** | Status | Computed in |
|---|---|---|---|---|
| States running forecasts | 5 | **6** (Assam, Delhi, Maharashtra, Rajasthan, Telangana, Uttar Pradesh) | REAL selection | `set_forecast_facilities.py --add-state` |
| Forecast PHCs | 200 | **275** | REAL selection | same |
| Districts with forecast PHCs | 116 | **191** | REAL | same |
| HMIS districts loaded | 137 | **212** (Uttar Pradesh adds 75; 18,900 rows) | REAL | `parse_hmis.py` |
| People in the demand-data footprint | 151.7 million | **260.8 million** (7,781 rural PHCs, 180 districts) | REAL SOURCE, DERIVED | `build_population_reach.py` |
| People served by operating PHCs | 4.8 million | **7.5 million** (230 rural forecast PHCs) | REAL SOURCE, DERIVED | same |
| National addressable | 793.7 million | **793.7 million** (unchanged) | REAL SOURCE, DERIVED | same |
| ARIMA_PLUS series | 2,794 | **3,818** (76.4% of the 5,000 ceiling) | MEASURED | `train_forecast.py`; `ML.ARIMA_EVALUATE` |
| Series with a weekly cycle | 2,149 (76.9%) | **2,951 (77.3%)** | MEASURED | same |
| Distinct ARIMA orders chosen | 12 | **12** | MEASURED | same |
| Stock lines (facility × medicine) | 2,794 | **3,818** | MEASURED | `build_supply_plan.py` |
| Shortages (below reorder point) | 597 | **765** — LIVE | MEASURED | `reorder_status` |
| Completely out | 69 | **89** (2.3%) — LIVE | MEASURED | same |
| Medicines available (scorecard) | 78.6% | **80.0%** — LIVE | MEASURED | `today_v2.scorecard` |
| Life-saving medicines available | 77.7% | **80.3%** — LIVE | MEASURED | same |
| Gone within a week | 10.2% | **9.9%** — LIVE | MEASURED | same |
| Districts affected | 87.9% | **80.6%** (154 of 191) — LIVE | MEASURED | same |
| Transfer recommendations | 527 | **685** — LIVE | MEASURED | `recommendations` |
| Units to move | 64,218 | **88,578** — LIVE | MEASURED | same |
| Life-saving transfers | 116 | **150** — LIVE | MEASURED | same |
| Transfers crossing a district line | 362 of 527 | **520 of 685** — LIVE | MEASURED | same |
| Therapeutic substitutions | 1 | **1** | MEASURED | same |
| Action queue split: move / order / escalate | 525 / 33 / 39 | **685 / 36 / 44** — LIVE (6 of the 44 life-saving, 14 already at zero) | MEASURED | `action_queue.triage` |
| Pattern exchange: flat wMAPE | 19.4% | **21.1%** | MEASURED | `build_pattern_exchange.py` |
| Pattern exchange: pooled wMAPE | 14.4% | **15.6%** (5.5 points, 26% relative, better than flat) | MEASURED | same |
| Pattern exchange: same-state twin | 16.4% | **18.6%** | MEASURED | same |
| Pattern exchange: twin in another state | 71.2% | **46.5%** (25.4 points worse than flat) | MEASURED | same |
| Predictions scored | — | **49,134**, 191 districts, 36 classes | MEASURED | same |
| Brihan Mumbai antimalarials, January | 2,345 vs 987.8 expected, 2.37×, modified z 6.54 | **2,345 vs 938.4 expected, 2.50×, modified z 8.49**, classical z 2.72; a flat average says 1.67× (unchanged) | MEASURED on REAL HMIS | `surge_signals` |
| Largest modified z / classical z | 166.7 / 3.17 | **306.5 / 3.18** (the classical figure is the 3.175 bound, rounded) | MEASURED | same |
| Surge series-months scanned | 58,932 | **90,780** | MEASURED | `build_surge_signals.py` |
| Surges detected | 1,295 | **2,352** (2.6%) | MEASURED | same |
| District-classes that hold a 2× / 3× / 5× surge | 59.0% / 30.1% / 4.3% | **62.8% / 34.1% / 4.8%** of 2,601 | MEASURED | `network_absorption` |
| Needs reorder, steady → under surge | 100 → 198 (98 newly at risk) | **208 → 447** (239 newly at risk) | MEASURED | `surge_supply_impact` |
| Surge-hit lines an order cannot reach in time | 145 of 322 | **331 of 673** | MEASURED | same, `lead_time_decisive` |
| Surge transfers | 101, 5,881 units | **247**, 12,140 units, 54 rationed by donor stock | MEASURED | `build_surge_supply.py` |
| Waste avoided by FEFO, at NPPA ceiling prices | Rs 29,268 · Rs 146 per PHC per year | **Rs 49,786 · Rs 181 per PHC per year** (on modelled units; 50,868 units, 39.9% of what FIFO would have expired) | MEASURED on modelled units | `build_waste_value.py`, `impact_metrics_parts` |
| Reporting consistency | — | **51%** mean; 48 complete, 185 partial, 42 silent | MEASURED on generated reporting | `build_facility_metrics.py` |
| Lead times | 7–19 days | **7–19 days** | REAL DISTANCE, ASSUMED CONVERSION | `set_lead_times.py` |
| Lead-time gradient in surge transfer-only share (6–10 / 11–15 / >15 days) | 43.5% / 47.9% / 80.0% | **49.8% / 45.4% / 80.0% — WITHDRAWN, do not quote.** It is no longer monotone, and the >15-day band is 5 lines | MEASURED | `surge_supply_impact` |
| Staff posts filled | 77.8% | **71.6%** of 1,361 sanctioned posts, 23 state-and-cadre roles | REAL SOURCE, DERIVED | `today_v2.staff_scorecard` |
| Worst state and role | Rajasthan pharmacist, 56.2% vacant | **Uttar Pradesh health assistant, 81.5% vacant** | REAL (RHS 2021-22) | same |
| Nurses below the bed norm | 11 | **86** | REAL SOURCE, DERIVED | same |
| Gemini backend and models | AI Studio API key; gemini-3.6-flash, fallback gemini-2.5-flash | **Vertex AI, as the Cloud Run service identity. Newest Flash first (prompts/models.json): gemini-3.8, 3.7, 3.6-flash (global), then gemini-3.5 and 2.5-flash (asia-south1, Mumbai).** SDK-internal retries off; the chain is the only retry policy The API key's quota ran out on 2026-09-30 and voice notes took 140-176 s; each call now has a 25 s timeout | REAL config | `app/capture.py` |
| Languages verified end to end through Vertex AI, 2026-09-30 | — | **Telugu voice; Bengali, Marathi and Telugu text: every medicine extracted and matched to the catalogue.** Names now come back in Latin letters; in Telugu script they failed to match | MEASURED (live calls) | `app/capture.py` SYSTEM_PROMPT |
| Spoken read-back | the phone's own speech engine | **Cloud Text-to-Speech in en-IN, hi-IN, mr-IN, te-IN, bn-IN**, phone engine as fallback. Phones lacked Telugu, Marathi and Bengali voices and read only the digits | REAL feature | `app/speech.py`, `POST /api/v1/speak` |
| Extraction prompt, 20 edge cases (`evals/extraction_cases.json`) | 17/20 before refinement, gemini-3.5-flash, 4.0 s mean | **20/20 after refinement on gemini-3.8-flash, 7.5 s mean**; 19/20 on gemini-3.5-flash (the miss was a dropped connection, not a wrong answer). Fixed: a negation recorded as a receipt of 0, a question held as a report, "iron ki goli dedh sau" not recognised | MEASURED (live calls, 2026-09-30) | `scripts/eval_prompts.py`, `prompts/extraction_system.txt` |
| Report page languages | Hindi, English | **English, Hindi, Marathi, Telugu, Bengali** | REAL feature | `web/report.js` |

**What adding Uttar Pradesh did not change.** All 2,794 of the original
stock lines are still there and none changed status. The original 200
centres are still short on 597 lines, 69 of them at zero. Refitting the
model moved 7 of their forecasts by about 1%, and 524 of their 527 transfers
came out identical. The other 8 changed because a Uttar Pradesh centre is now
the nearest donor or receiver across the Delhi border.

**Two errors the six-state run caught, both fixed on 2026-09-23.** The rupee
waste figure applied the original five states' waste-avoided share to six
states' expiries and divided by a hard-coded 200 centres; a first quote of
Rs 55,870 and Rs 279 per PHC was wrong and must not be used. And five queries
counted districts by name alone, so Pratapgarh in Rajasthan and Pratapgarh in
Uttar Pradesh counted as one district (190 instead of 191).

**What adding Uttar Pradesh did change, and why it is reported rather than
hidden.** At the default all-medicine scope on Plan ahead, the out-of-state
twin now scores 17.9% against a flat 19.0%, so it is no longer the worst arm
at every scope. Across every class it still is (46.5% against 21.1%), and
pooling still wins everywhere (12.4% at that scope). And life-saving
availability is now slightly *better* than overall availability (80.3%
against 80.0%). With five states it was worse, which Today called out in
words. The page computes that comparison rather than asserting it, so it
changed on its own.

---

## 1. Scale and coverage

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **200,438 facilities** | NHM/MoHFW health-centre directory, every row, nothing sampled | **REAL** | `ingestion/load_facilities.py` — asserts BigQuery count == source file count, *and* that an unscoped `COUNT(*)` equals it |
| **37 states/UTs** | `COUNT(DISTINCT admin_l1)` | **REAL** | `ingestion/build_geo_summary.py` |
| **701 districts** | `COUNT(DISTINCT admin_l1 ‖ admin_l2)` | **REAL** | `ingestion/build_geo_summary.py` |
| 668 distinct district *names* | `COUNT(DISTINCT admin_l2)` | **REAL** | same |
| **29,733 PHCs** | facility-type breakdown | **REAL** | `load_facilities.py` |
| 163,131 sub-centres · 5,389 CHCs · 1,251 state + 934 district hospitals | same | **REAL** | same |
| **200 forecast PHCs**, 116 districts, 5 states | `is_forecast_facility` | **REAL** selection | `ingestion/set_forecast_facilities.py` |

> ⚠️ **Say "701 districts", not 668.** 668 counts distinct district *names*, and
> names such as Aurangabad and Bilaspur recur across states, so it undercounts by
> 33. Both numbers are correct for different questions; only 701 answers "how
> many districts".

> ⚠️ **"668 districts" appears in older material.** It is not wrong, it is
> answering a different question. Do not mix the two in one sentence.

---

## 2. Population reach

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **793.7 million** — national addressable | Σ `population_served` over 24,759 **rural PHCs** | **REAL SOURCE, DERIVED** | `ingestion/build_population_reach.py`, tier `national_directory` |
| **151.7 million** — demand-data footprint | same, restricted to the 105 districts with loaded HMIS data | **REAL SOURCE, DERIVED** | same, tier `demand_data_footprint` |
| **4.8 million** — operating today | same, restricted to the 168 rural forecast PHCs | **REAL SOURCE, DERIVED** | same, tier `operating` |
| **95.2% tiling check** | 793,668,945 ÷ 833,748,852 (Census 2011 rural India) | **REAL** | same — the build **fails** outside [0.80, 1.05] |
| 2.92 billion (**3.50×** rural India) | Σ `population_served` over all facility types | **REJECTED — never quote** | recorded in the same module as the figure *not* used |

**What is assumed:** that each PHC serves its state's average rural catchment.
No per-facility catchment is published anywhere in India, so a state ×
facility-type average is the finest granularity that exists.

**What is excluded:** 4,974 urban PHCs contribute **zero** — the Rural Health
Statistics figure is a *rural* average and applying it to urban PHCs would be a
category error. Sub-centres, CHCs and hospitals are excluded because their
catchments nest inside or around PHC catchments.

**Direction of error:** Census 2011 base, fifteen years old. These figures
**understate** current reach. No growth factor applied.

**The headline to use is 151.7 million** — the footprint where demand is
grounded in real government data. 4.8M is what runs today; 793.7M is
*addressable*, and must be said with that word.

---

## 3. Item catalogue

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **385 NLEM 2022 medicines** | National List of Essential Medicines 2022, all 27 sections | **REAL** | `ingestion/parse_nlem.py` → `ingestion/build_items.py` |
| **264 with ATC codes** (68.6%) | WHO ATC crosswalk, confident-or-null rule | **REAL** | `ingestion/atc_map.py` |
| **39 forecast items** | items with a real HMIS demand driver | **REAL** | `build_items.py`, `FORECAST_DRIVERS` |
| **0 flat-baseline items** | every forecast item has a clinical driver | **REAL** | same |
| VEN classification (Vital / Essential / Desirable) | **ours, derived** — NLEM does not publish VEN | **DERIVED** | `build_items.py` |

> ⚠️ **VEN is ours, not MoHFW's.** Never present it as a government
> classification.

---

## 4. Forecasting

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **2,794 ARIMA_PLUS series** | BigQuery ML, `MIN_DAYS = 180`, `HORIZON = 30` | **REAL model on GENERATED ledger** | `ingestion/train_forecast.py`; logged in `docs/training_runs.json` |
| **21.8 seconds** training time | last run, 2026-08-31T14:34:54Z, job `b7806d15` | **REAL** | same |
| 757,319,928 bytes processed | same job | **REAL** | same |
| 55.9% of the 5,000-series ceiling | 2,794 ÷ 5,000 | **REAL** | — |
| **21 HMIS demand drivers** | selected by HMIS item **code**, never label substring | **REAL** | `ingestion/hmis_drivers.py` |
| **34,524 driver rows**, 137 districts, 5 states | HMIS 2019-20 | **REAL** | `ingestion/parse_hmis.py` |

> ⚠️ The model is genuinely trained on genuinely seasonal data. The **daily
> ledger it is trained on is generated**, anchored to real HMIS monthly volumes.
> Say "trained on a year of stock movements generated from real HMIS demand",
> never "trained on real stock data".

---

## 4a. ARIMA_PLUS — what it is, and what rests on it

*Last verified against the live deployment: **2026-09-11**.*

| Figure | Value | Status | Read from |
|---|---|---|---|
| Trained series | **2,794** | **MEASURED** | `ML.ARIMA_EVALUATE(demand_forecast)` |
| Series with a detected weekly cycle | **2,149** (76.9%) | **MEASURED** | same |
| Distinct (p,d,q) orders auto-ARIMA chose | **12** | **MEASURED** | same |
| Series with drift | **181** | **MEASURED** | same |
| Forecast horizon / prediction interval | 30 days / 80% | **CONFIGURED** | `app/forecast.py` |

The model is the most load-bearing thing in the system. The chain, and every
figure in it, is read back out of BigQuery by `/api/v1/model-evidence`:

```
ML.FORECAST(demand_forecast)              2,794 series
  -> demand_baseline.avg_daily_demand     = AVG(forecast_value), 2,794 lines
    -> reorder_status (VIEW)              200 facilities
         reorder_point = avg_daily_demand x lead_time_days
                       + 1.65 x sigma x SQRT(lead_time_days)
      -> needs_reorder                    597 shortages
        -> recommendations                527 moves
```

**Every shortage figure on every page is downstream of ARIMA_PLUS.** The action
queue's 525/33/39 split, the map arcs, nearest-help, the alerts and both Today
pages all resolve to `needs_reorder`, which is `on_hand` compared against a
reorder point whose demand term is `ML.FORECAST` output.

The 12 distinct orders matter: a single order across all 2,794 series would
mean auto-ARIMA selected nothing. The largest group is (1,1,1) with weekly
seasonality at 754 series.

> ⚠️ This is **not** the same thing as the Plan ahead forecast. ARIMA_PLUS runs
> at **facility x item x day** and sets reorder points. The pattern exchange
> (§5) runs at **district x ATC class x month** and answers "what is coming for
> this medicine class here". Neither replaces the other, and they must not be
> presented as two opinions on one question.

---

## 5. Pattern exchange — the four-arm hold-out

*Last verified against the live deployment: **2026-09-02**.*

| Arm | wMAPE | Status | Computed in |
|---|---|---|---|
| flat — own three months, no seasonality | **19.4%** | **MEASURED** | `ingestion/build_pattern_exchange.py` → `pattern_exchange_eval`; served at `/api/v1/exchange/evaluation` |
| demographic match, **different state** | **71.2%** (51.8pt worse) | **MEASURED** | same |
| demographic match, **same state** | **16.4%** (3.0pt better) | **MEASURED** | same |
| **pooled — mean vector, all districts** | **14.4%** (5.0pt better) | **MEASURED** | same |

31,322 held-out district-month-class predictions across 116 districts.
wMAPE = Σ|error| ÷ Σ|actual|.

> ⚠️ **These supersede 25.8 / 45.1 / 32.5 / 23.2, which must not be quoted.**
> The old figures were correct at Block D; the Block D+ driver corrections
> changed the underlying series and the evaluation was re-run. The conclusion is
> unchanged and the margins are wider.
>
> **One thing did change and the deck must reflect it:** same-state matching now
> **beats** the flat baseline, where before it lost. The story is no longer
> "demographic matching loses" flat — it is "**cross-state** demographic matching
> loses catastrophically (71.2% vs 19.4%), restricting to the same state fixes
> most of it (16.4%), and pooling beats both (14.4%)". That is a *better* story:
> it shows the mechanism is climate, not demography.

> ⚠️ **This panel was rendering a raw JSON blob until 2026-09-11.**
> `/api/v1/exchange/evaluation` returns flat keys — `flat_wmape`,
> `pooled_wmape` and so on — and never an `arms` array, but the Evidence page
> read `d.arms || d.evaluation || []` and fell through to a debug branch that
> printed `JSON.stringify(d).slice(0, 400)` into a paragraph. The page carrying
> the project's central claim showed its own payload. It went unnoticed because
> the blob contains the correct numbers.
>
> It also broke the layout: a JSON string has no spaces, so it cannot wrap, and
> it forced the whole Evidence view **319px wider than the viewport** — cutting
> every other panel on that page off at the right edge.

### 5a. The same four arms, per medicine class

*Last verified against the live deployment: **2026-09-11**.*

The figures above pool all 36 ATC classes. The Plan ahead page lets a reader
pick one, and the method does **not** hold up equally across them. Every number
here is `pattern_exchange_eval`, same table, same hold-out.

| Figure | Value | Status |
|---|---|---|
| Classes where pooling beats a flat average | **18 of 36** | **MEASURED** |
| Classes where it does not | **18 of 36** | **MEASURED** |
| Classes scoring above 40% wMAPE | **11 of 36** | **MEASURED** |
| Best class — Paracetamol / Ibuprofen (N02BE, M01AE) | **11.9%** vs 18.0% flat | **MEASURED** |
| Worst class — Albendazole (P02CA) | **83.5%** vs 83.4% flat | **MEASURED** |
| Vitamin A (A11CA) — flat wins by the widest margin | 73.6% vs **46.5%** flat | **MEASURED** |

Albendazole and Vitamin A are campaign-driven — National Deworming Day, and
Vitamin A dosing rounds. A monthly seasonal multiplier cannot fit a calendar
campaign, and the page says so on the panel rather than drawing the curve with
the same confidence as Paracetamol's.

**Do not quote 14.4% as "the" forecast error without saying it is the pooled
figure across all classes.** For roughly half the classes the honest statement
is that exchanging shape does not pay.

---

### 5b. `demo_in` / `demo_out` mean in-state and out-of-state

*Last verified against the live deployment: **2026-09-11**.*

Both arms take the **single closest district on demographic profile**. They
differ only in whether that district may sit in another state:

- `demo_out` — closest twin **anywhere in India, different state required**. 71.2%.
- `demo_in` — closest twin **inside the same state**. 16.4%.

`demo_out` is not a poor match. Amravati's is Ranga Reddy, Telangana, **0.323**
away on profile. Borrowing its seasonal shape is nearly four times worse than
using no seasonality at all.

> ⚠️ The Plan ahead page previously labelled `demo_out` **"a deliberately poor
> twin"** and headed its donor districts **"Who lends the seasonal shape"** —
> presenting the losing arm's donors as the source of the gain, and reducing
> the one genuinely surprising result in the project to a sanity check. Both
> are corrected. The finding to state is: *two districts can be demographically
> interchangeable and still have nothing to tell each other about **when**
> demand arrives, because monthly shape follows monsoon and season, which
> follow geography.* That is also the argument for pooling rather than pairing.

---

### 5c. The curve is in medicine units, not driver events

*Last verified against the live deployment: **2026-09-11**.*

`pattern_exchange_eval.actual` is the **HMIS demand driver** — outpatient
attendance, confirmed malaria cases, institutional deliveries — not units of
medicine. Classes sharing a driver therefore held byte-identical series:
N02BE matched M01AE on **all 928 rows**, and **9 such groups covered 26 of the
36 classes**, so a class dropdown offered 36 entries drawing 19 distinct curves
on an axis reading 33.8 million "tablets" that was really a count of visits.

`items.units_per_driver_event` is the documented conversion and is applied
before anything leaves the query: **1.2** paracetamol tablets per OPD visit,
**0.35** ibuprofen, **28** antimalarial tablets per confirmed case (18
chloroquine + 10 primaquine — a vivax case gets both).

This changes **no accuracy figure**: wMAPE is Σ|error| ÷ Σ|actual|, so a
constant multiplier cancels. 19.4% → 14.4% is identical before and after.

Two ties survive and both are arithmetic rather than the defect: Haloperidol
and Fluoxetine are both 7.5 tablets per mental-illness visit, Phenytoin and
Carbamazepine both 9.0 per epilepsy visit. Same driver and same course size
genuinely means the same tablet count. **34 distinct volumes across 36 classes.**

---

## 6. Driver corrections (Block D+)

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| Malaria driver was **99.8% blood smears** — 14.5M tests vs 24,831 confirmed | HMIS item codes | **REAL** | `ingestion/hmis_drivers.py`; written up in `Data/README.md` §16 |
| Corrected malaria amplitude **4.52×** (Sep 1.90 peak, Mar 0.42 trough) | monthly multiplier range, confirmed cases, 5 states | **REAL** | `parse_hmis.py` → `demand_reference` |
| Old blood-smear amplitude **1.6×** | the parse as it stood at Block D+ | **REAL, NOT RECOMPUTABLE** | blood smears are deliberately no longer loaded; figure stands as a record |
| **Albendazole amplitude 22.64×**, **August 5.66× mean** | doses administered, monthly multipliers | **REAL** | same |
| National Deworming Day — 10 August and 10 February | Government of India programme | **REAL, external fact** | not computed; cited |

> ⚠️ **Amplitude figures were restated on 2026-09-01.** Malaria **3.9× → 4.52×**;
> Albendazole **22.3× → 22.64×** and the August spike **6.24× → 5.66×**. The
> older figures predate the five-state HMIS widening. Use the current ones.

---

## 7. Supply chain

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **1,157,367 stock events**, 200 facilities × 39 items × 365 days | generated ledger, 2025-08-30 → 2026-08-29 | **GENERATED**, HMIS-anchored | `ingestion/generate_usage.py` |
| **Lead times 7–19 days** | real road distance to district HQ; days-per-km is a **documented proxy** | **REAL DISTANCE, ASSUMED CONVERSION** | `ingestion/set_lead_times.py` |
| **2,794 reorder rows** | one per forecast facility-item; stable | **MEASURED** | `ingestion/build_supply_plan.py` (view) |
| **597 open alerts** | `on_hand <= μ×L + 1.65σ√L` | **MEASURED — LIVE** | same; was 599 before two test captures cleared two |
| **527 transfer recommendations**, **64,218 units** | FEFO batch selection, donor protection, 150 km radius | **MEASURED — LIVE** | same; was 525 / 64,211 before captures added stock |
| **26,612 units of waste avoided (44.7%)** | FEFO 32,893 expired vs FIFO 59,505 counterfactual, ledger replayed both ways | **MEASURED** | `generate_usage.py` → `impact_metrics`; served at `/api/v1/impact` |
| Per-transfer `waste_avoided_units` = **0** | FEFO at the facility already consumed short-dated stock | **MEASURED, and honest** | `build_supply_plan.py` |
| **1 substitution** across 527 transfers | ATC **level 4** matching | **MEASURED — LIVE** | same |
| The `substitutes` table is **empty (0 rows)** | only **1 of 30** ATC classes in the forecast set contains two forecast items | **MEASURED — a real limit, not a failure** | `app/supply.py`, `substitution_constraint()`; `/api/v1/substitutes` returns the reason with the empty list |

> ⚠️ **26,612 supersedes 94,542, and 44.7% supersedes 57%.** The old figures were
> correct for the Block C ledger. The Block D+ driver corrections regenerated the
> ledger, and different demand produces different expiry under both policies.
> **94,542 must not appear anywhere.**

> ⚠️ Substitution firing once is not a bug — **only 1 of 30** ATC level-4
> classes in the forecast set contains two forecast items, so there is almost
> nothing to substitute *between*. Matching at ATC level 3 would produce many
> more candidates and some would be clinically wrong (it paired Zinc Sulphate
> with Magnesium Sulphate); the stricter rule is kept and the reach is the
> price. **Present it as a demonstrated capability with a stated limit, and say
> the limit out loud** — widening the forecast item set, not loosening the ATC
> level, is what would make it fire more.

### 7f. What the avoided waste is worth — REAL PRICES, MODELLED UNITS

*Last verified against the live deployment: **2026-09-13**.*

| Figure | Value | Status | Computed in |
|---|---|---|---|
| Ceiling-price coverage of expired units | **97.9%** (32,192 of 32,893) | **MEASURED** | `ingestion/build_waste_value.py` |
| Value of priced expiry | **Rs 64,051.77** | **MEASURED on modelled units** | same |
| Value of waste avoided by FEFO | **Rs 29,268** | **MEASURED on modelled units** | same |
| Per PHC per year | **Rs 146** | **MEASURED on modelled units** | same |
| Items priced | **35 of 39** | **MEASURED** | `ingestion/extract_nppa_prices.py` |
| Price source | NPPA **Compendium of Prices 2022**, S.O. **1499(E)** of 30.03.2022 | **REAL, primary** | same |

> ⚠️ **The prices are real; the units they multiply are not.** Expiry comes
> from the generated ledger anchored to real HMIS demand. Say this as *"on a
> modelled year of dispensing across 200 PHCs, at published DPCO ceiling
> prices"* — never as observed savings.

> ⚠️ **It understates, twice.** Ceiling prices exclude GST, and a ceiling is a
> maximum rather than a typical procurement price. Where a medicine has several
> pack sizes the **lowest** qualifying price is taken. A figure that understates
> can be defended; one that flatters cannot.

Until 2026-09-13 this module **refused to publish**: coverage was 26.9% from
six secondary-sourced rows, and Ferrous Salt + Folic acid — 34.5% of all expiry
on its own — had no price. Reading the compendium directly fixed both.
`COVERAGE_FLOOR` (80%) still gates the headline if the price list regresses.

**Four items are deliberately left unpriced** — 701 units, 2.1% of expiry.
Sodium chloride is notified per 1000 ml glass bottle; Chlorhexidine and Timolol
per millilitre; Artesunate + Sulphadoxine-Pyrimethamine per co-blistered
course. Stock is counted in vials, bottles and tablets, so each would need an
invented pack size. They count as uncovered instead.

---

## 7b. The Today dashboard — what the charts say

*Last verified against the live deployment: **2026-09-04**.*

The landing view was ninety stacked text cards; it became eight stat tiles,
two charts and two meters, and on 2026-09-18 it was retired in favour of Today
v2 (§7c), which now *is* Today. Every figure below is served by `/api/v1/today2`
in one round trip — `/api/v1/executive` and `app/executive.py` are gone. The
four panels only this view had (the network verdict, "What should we do
first?", the Vital/Essential/Desirable split and the surge banner) moved into
Today v2 with their renderers unchanged; the figures are the same.

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **285 stock lines run out within a week** (10% of tracked) | `days_of_cover <= 7`, plus `on_hand <= 0` | **MEASURED — LIVE** | `cover_buckets` |
| Cover buckets **69 / 216 / 363 / 1,246 / 900** | already out, ≤7d, 8–14d, 15–30d, >30d | **MEASURED — LIVE** | same |
| **102 of 116 districts** carry at least one shortage | `COUNT(DISTINCT IF(needs_reorder, district, NULL))` | **MEASURED — LIVE** | `medicines.districts_short` |
| VEN short: **Vital 126/566 (22.3%)**, **Essential 422/2,112 (20.0%)**, **Desirable 49/116 (42.2%)** | `reorder_status` grouped by `ven_class` | **MEASURED — LIVE** | `ven_breakdown` |
| Worst district **Cachar**: 5 Vital short, 14 already at zero | top 10 by Vital short | **MEASURED — LIVE** | `worst_districts` |

**Two cross-checks are asserted, not assumed.** The "Already out" bucket must
equal `medicines.stocked_out`, and the VEN rows must sum to `tracked` and
`below_reorder`. Both reach the page by different SQL paths, so if they ever
disagree one of the headline numbers is wrong; `test_today_v2.py` fails first
(`TestItAgreesWithTheOtherViews`).

**Desirable is the worst class proportionally (42.2%), not Vital.** That is a
real result and it is left visible rather than buried, because it is the
correct prioritisation story: the network is protecting its Vital lines better
than its Desirable ones, which is what should happen.

**Colour was validated, not chosen.** `#b91c1c` against `#0369a1` scores ΔE
20.6 under protanopia and 29.6 in normal vision, both clear of the floors, and
each clears 3:1 against the page surface. A five-step red→amber→green ramp was
tried for the cover chart and **failed**: five hues from one family score ΔE
2.9 under deuteranopia, and the amber sat at 1.87:1 on a near-white surface.
The chart uses emphasis instead — the two buckets needing action this week are
red, the rest recessive grey.

**A deploy that only half arrived.** Starlette's `StaticFiles` sends `ETag`
and `Last-Modified` but no `Cache-Control`, so Chrome applied heuristic
freshness and served `styles.css` from disk. The browser had the new
`index.html` and `app.js` with the old stylesheet, so the redesigned dashboard
rendered as a column of unstyled plain text — the new markup existed, the rules
for it did not. The service worker hid it rather than fixing it: its fetch
handler is network-first, but `fetch()` inside a worker uses the same HTTP
cache, so the "fresh" response was the stale copy, which it then wrote into
Cache Storage. Static assets now send `Cache-Control: no-cache`; the ETag turns
the revalidation into a 0-byte 304.

**Early warnings are one per district-month-driver, not per ATC class.** P01BA
and P01BF are different antimalarial classes driven by the same confirmed-
malaria signal, so a surge produced two rows identical in every field the card
showed. Five slots displayed three events and the panel looked broken. The data
was right and the grouping was wrong; the affected classes are now named on the
card, and the top five carry five distinct districts.

**Written for the people who actually read it.** The audience is district and
state health administrators, not analysts, so the landing view went from eight
stat tiles to five and the copy dropped the schema's vocabulary. "Stock line
below its reorder point" became "medicine running low"; "district-medicine-class
positions" became "district medicine stocks"; "facility-items" became
"medicines"; Personnel became Staff. **No figure changed** — the same numbers
from the same queries, in the words a district officer would use.

The five tiles answer, worst first: what is completely out (69), what is
life-saving and running low (126), how many in total (597), how far it has
spread (102 of 116 districts), and could we take a surge (30.1%). Beds and
staff moved out of that row and into the sentence cards directly beneath it,
which sit above the charts so all three resources are visible without
scrolling. `transfer_only` left the row because it was already the large red
figure in the verdict bar immediately above it.

**Early warnings name medicines, not codes.** "P01BA, P01BF" became
"Chloroquine, Primaquine", read from the tracked item names. Where a surging
class has no tracked item the card falls back to the code rather than inventing
a name.

**A test was pinning vocabulary rather than substance.**
`test_resilience_and_transfer_only_are_present` asserted the literal words
"absorb" and "resupply", so it failed the moment those sentences were rewritten
for the audience — a test with an opinion about wording it should not have had.
It now asserts the figures survive, which is what it was for.

**The page now says what to do, not only what is true.** It described the
situation a dozen ways and never once gave an instruction, which is the section
a person who runs services actually needs. "What should we do first?" gives
three numbered steps, all from figures already in the same round trip: approve
the **527** worked-out transfers (**64,218** units, **116** life-saving);
**145** of those cannot wait for an order because they would run out before a
delivery could physically arrive; start with **Cachar, Assam** (5 life-saving
running low, 14 completely out — the worst district). Nothing there is advice
we invented: step one is the transfer engine's own queue, step two is the
lead-time finding, step three is the district ranking. The page states them as
instructions instead of as statistics.

**Numbers a non-specialist cannot grade now carry the grade.** "3x demand —
30.1% hold" tells an analyst a great deal and a district officer nothing, since
nothing on the page said whether 30% was good. The rows read "If demand
tripled — 30.1% could cope", and the panel closes with "This is low. Most
district medicine stocks could not cope if demand tripled." The threshold is
the same 35% used everywhere else, so the wording cannot disagree with the bar.

**Section headings are the questions being asked**: "What should we do first?",
"How are medicines, beds and staff holding up?", "What is coming next?" — so
the page is navigated by question rather than by chart type.

**A count that was quietly wrong.** The front end never sent a `limit`, so the
alerts and recommendations endpoints returned their default 50 rows. The
Action queue promised "the whole queue" and showed 50 of 597, and Today's
hand-off read "Showing 5 of 50". It now requests more rows than exist, so the
returned count is the true total and the hand-off states it.

## 7d. Nearest help — where can a patient actually be treated?

*Last verified against the live deployment: **2026-09-10**.*

Served by `/api/v1/access` (`app/access.py`), drawn as a third layer on the map.
One BigQuery round trip, 0.166 GB.

Every other view answers a manager's question. This answers the one the person
at the counter has: **this centre does not have the medicine, so where is the
nearest one that does?** It is also the sharpest alert the product makes —
*"126 Vital lines below reorder"* is a statistic; *"Salchapra is at zero days of
Oxytocin and the nearest supply is 46.7 km away"* is an emergency with an
address.

| Figure | Value |
|---|---|
| Life-saving shortages | **126**, across **83** health centres |
| People behind those centres | **2,648,060** |
| Nearest supply, median | **45.9 km** |
| Within 25 km / 25–100 km / over 100 km | **29 / 86 / 11** |
| **With no source anywhere** | **0** |

**The zero is the finding.** Every one of the 126 life-saving shortages is
solvable by moving stock that already exists somewhere in the network — the
question is only how far. That is the case for redistribution stated as a
measurement rather than an argument.

**A source must be above its own reorder point**, not merely non-zero. Pulling
from a facility that is itself short just moves the shortage.

**Distances are straight-line** between two real geocoded points
(`ST_DISTANCE`), so every figure is a **floor** — the road journey is longer.
The page says so rather than implying a travel time that cannot be computed
without a road network. It is also not a referral recommendation: it says where
the stock is, not where a patient should be sent.

**Sources are not restricted to the filtered state.** The nearest supply is
wherever it is; confining it to the scope would invent a longer journey than
the real one, and a state border does not stop a van.

**Selecting a row flies the map to it.** Both tables — the recommended moves
and the shortages — drive the map: clicking a row lifts that one case out of
the other 125, zooms to it and its source, and opens its detail. The rest
**fade rather than hide**, because removing them would remove the context that
makes the selected one mean something: 353 km is only striking next to the ones
that are 20.

The identity carried is the row's own — facility plus medicine for a shortage,
the two districts for a move — so the table and the map cannot drift apart the
way index-based selection does the moment either list is re-sorted. Pinned by
`TestClickingARowReachesTheMap`, which executes the focus path against the real
payloads: every key the tables render must resolve to a drawn feature, the map
must actually move, and the unselected features must be faded rather than
removed. A table key with no matching feature is the way this breaks silently —
it simply looks like a dead click.

**The table is ordered by urgency, not distance.** The map already colours by
distance, so the table answers who runs out first — ordering it by distance
buried a centre with half a day of stock left at row eight. Population is
counted once per centre, not once per shortage.

## 7e. The action queue, triaged

*Last verified against the live deployment: **2026-09-10**.*

Served by `/api/v1/action-queue` (`app/action_queue.py`).

The page opened with "Everything that is failing" — all **597** shortages —
above a queue of 527 transfers. **525 of those 597 rows already appeared in the
queue below with an Approve button on them**, so the first list was **88% a
restatement of the second**, which is exactly why it read as a log with nothing
to do. What the duplication hid was the shortages no routine action fixes.

| Group | Count | The action |
|---|---|---|
| A transfer is waiting | **525** | Approve it — the stock exists nearby |
| Nothing to move, order arrives in time | **33** | Procure, with a deadline |
| **Nothing to move AND order arrives too late** | **39** | Escalate; nothing routine works |

**5 of the 39 are life-saving and 13 are already at zero.** The worst is
**Salchapra MPHC: 0 days of Vitamin A left, 8 days to deliver.** Thirty-nine of
those existed the whole time, in row three hundred of a list nobody could work
through.

**"Too late" means `days_of_cover < lead_time_days`** — the stock runs out
before a delivery could physically arrive. Lead time comes from real road
distance to the district headquarters with a documented days-per-km conversion:
the distance is real, the conversion is a stated proxy.

**Unknown cover is never called an emergency.** An unmeasured line is
unmeasured, and putting a guess at the top of the one panel that most needs to
be trusted would be the worst place in the product to do it.

**The split is mutually exclusive and exhaustive**, and tests assert all three:
the counts sum to the total, no row is in two groups, and no row is in none.
The failure mode of a triage is a shortage falling through the gap between two
panels and being seen by nobody.

**The full 597 is kept** behind a "Show all shortages" toggle — useful for
looking something up, useless as something to work through, and not the page's
opening content.

## 7b. Network — comparison, and who is judged unfairly

*Last verified against the live deployment: **2026-09-09**.*

Served by `/api/v1/network` (`app/network.py`), drawn by `web/network.js`.

The page it replaced was a resource switcher, a stock-health doughnut and a
critical-shortages bar — all three of which Today v2 now does better. It changed
job rather than being kept for the nav slot: Today v2 grades **one** scope, this
ranks **across** them, which nothing else does.

| Resource | Grain | Worst | Best | Gap |
|---|---|---|---|---|
| Medicines | district (110) | Lakhimpur, Assam **8.3%** | Warangal Urban, Telangana **100%** | 91.7 pts |
| Beds | district (116) | Tinsukia, Assam **0%** free | Thane, Maharashtra **100%** | 100 pts |
| Staff | **state (5)** | Rajasthan **59.3%** filled | Delhi **101.1%** | 41.8 pts |

**Staffing changes grain with the scope, and both are forced by the data.**
Unscoped it compares **states**. Scoped to one state it compares **roles**,
because narrowing a state-grain ranking to one state leaves a single row ranked
against itself — best, worst and typical all reading "Assam 96.3%", presented
as three findings about one place. Cadre is what varies inside a state, and it
varies sharply: Rajasthan runs from **28.6%** of male health assistant posts
filled to **89.4%** of doctor posts, with female health assistants typical at
53.4%. It is also the better question at that zoom — "which roles can we not
fill here" is a recruitment decision.

**Staffing is compared by STATE when unscoped, and that is forced by the data.** Vacancy comes
from Rural Health Statistics (2021-22 since 2026-09-11), which publishes at
state level. Measured: **exactly one distinct value per state** — all
33 Rajasthan districts read 69.3%, all 27 Assam districts
read 78.1% (2017 read 59.3% and 96.3%). A district table built on it would
rank 33 districts as jointly worst and invite a reader to blame Jaisalmer for a
Rajasthan statistic. `test_staff_vacancy_really_is_constant_within_a_state`
pins the measurement the decision rests on, so if it ever stops being true the
ranking can go back to districts.

**The distance finding, stated with its limit.** Mean availability falls
monotonically as resupply distance rises: **83.5%** under 9 days, **75.5%** at
9-12, **64.7%** at 12-15, **56.4%** past 15 — a 27-point spread across 110
districts. The correlation is **-0.296**, which explains under a tenth of the
variance, so the page says distance is *one* reason a district is behind and
never the whole reason. The furthest band holds **2 districts** and the count
travels with every band. Presenting distance as the explanation would be a
more comfortable story and would hand every badly run district an excuse.

**Best, typical, worst — three points, not two.** Two extremes cannot tell a
reader whether the worst is an outlier or whether the middle of the pack is
struggling too, and those need different responses: one district to rescue, or
a system to fix. The median is reported as a **named place**: medicines
**Medak, Telangana at 83.3%** with 53 districts above it and 55 below, so
Lakhimpur's 8.3% sits in a crowded bottom half rather than alone. A bare median
is a statistic; a named district is somewhere a reader can go and look at.

**Three guards against an unfair ranking.** Both ends are shown, because a
table of failures teaches nobody what good looks like. Districts under
**8 tracked lines** are excluded, so nothing tops or tails the table on one bad
reading. The distance panel sits under the ranking rather than after it.

**Two numbers deliberately not used.** `attendance_vs_sanctioned` is modelled
and the model is broken for whole states — **all 55 of Delhi's rows read zero
staff present across 30 reported days**, and 198 of Rajasthan's 330 are zero.
Ranking on it would publish a generator fault as a finding, so the staff
comparison uses **doctor vacancy** (real RHS data) instead. Assam has no doctor
rows and shows a dash rather than a zero.

## 7c. Today v2 — the supply chain as a scorecard

*Last verified against the live deployment: **2026-09-07**.*

Served by `/api/v1/today2` (`app/today_v2.py`), drawn by `web/today2.js`. One
BigQuery round trip, 0.158 GB on a dry run. **v1 is untouched** and both pages
run side by side until v2 replaces it.

Public-health logistics grades a supply chain on five questions, in this order,
and v2 follows that shape rather than v1's accreted list of findings.

| # | Question | Figure | Grade |
|---|---|---|---|
| 1 | **Availability** — what share is actually there? | **78.6%** (2,197 of 2,794) | warn |
| 2 | **Criticality** — is the gap in the things that kill? | **77.7%** life-saving available (440 of 566) | bad |
| 3 | **Failure** — what has already gone? | **2.5%** completely out (69) | warn |
| 4 | **Forward risk** — what goes next? | **10.2%** gone within a week (285) | warn |
| 5 | **Equity** — concentrated or systemic? | **87.9%** of districts affected (102 of 116) | bad |
| — | **Resilience** | **30.1%** could absorb a 3x surge | bad |

**Rates, not counts.** 597 short means nothing until you know whether it is out
of 600 or 6,000, and a district with more facilities always looks worse. Every
headline is a rate with its count beside it, so Telangana and Assam read on the
same scale.

**A finding v1 never surfaced: life-saving availability (77.7%) is WORSE than
overall availability (78.6%).** Vital medicines should be the last thing to run
short, not the same as everything else. The page says so in those words, and
the comparison is computed rather than asserted, so it will flip on its own if
the network improves.

**Four visuals, four questions, four forms.** *When* — time to stock-out (69
already out / 216 within a week / 363 / 1,246 / 900). *What* — medicines by
name, ranked by how many health centres are short (Vitamin A in 49 centres
across 40 districts; 2 of the top ten are life-saving). *Where* — every district
plotted by share running low against ability to absorb a tripling. *How robust*
— absorption at 2x, 3x, 5x.

**The quadrant is the one that earns its place hardest.** Shortage and
resilience are normally read separately, and separately they mislead: a district
can be short but able to cover itself from stock next door, or comfortable today
and unable to survive any surge. Plotted together, **16 districts fall in the
danger corner** — badly short *and* unable to cover themselves. The worst is
**Lakhimpur, Assam: 91.7% of its medicines running low, 0% able to cope with a
tripling of demand.** No ranked list on v1 puts that district in front of
anyone.

**Districts with fewer than 8 tracked medicines are excluded from the
quadrant** (`MIN_LINES_FOR_RATE`). A district with three lines reads 100% short
on one bad line, and a rate with no floor under its denominator shows noise as
crisis. 110 of 116 districts qualify.

**The views must agree.** With Today v1 gone the cross-check runs inside one
payload: `test_today_v2.py` asserts that the `medicines` block feeding the
verdict bar equals the `scorecard` struct feeding the tiles, that the VEN split
sums to the same totals by a second SQL path, and that the 3x shock and the 35%
fragility threshold are the same constants the map uses. Three pages showing
the same figures differently is a credibility risk, not a feature, unless they
provably agree.

**All four filters are verified to narrow, not merely to be accepted.** A
filter that is accepted and ignored is worse than one that errors: the page
redraws, the numbers do not move, and the reader concludes the data is wrong
rather than the filter. The chain measured live:

| Scope | Medicines | Centres | Availability |
|---|---|---|---|
| All India | 2,794 | 200 | 78.6% |
| Rajasthan | 660 | 46 | 79.7% |
| Rajasthan → Sirohi | 43 | 2 | 86.0% |
| → Jail Dispensary Sirohi | **22** | 1 | **90.9%** |
| → Alpa | **21** | 1 | **81.0%** |

Sirohi's two health centres are the decisive case: 22 + 21 = 43, and they grade
differently, so the facility filter provably bites rather than passing the
district's numbers through. Pinned by `test_two_facilities_in_one_district_partition_its_lines`.

**The PHC filter cannot apply to absorption, and the page says so.**
`network_absorption` has no facility column because it asks whether a
*district's* pooled stock could cover a surge — one facility's absorption is
not a thing that exists. Rather than drop the filter silently, the response
declares which panels stayed at district level and the scope line explains it.

**Two nonsense claims that only a narrow scope revealed.** At one facility,
"Districts affected: 100% — Systemic. Almost every district is affected" was
being stated over a sample of one district: the arithmetic was right and the
sentence was drivel, which is worse than a wrong number because a reader checks
a number and believes a sentence. The metric is now withheld below two
districts. The scope line was also printing the facility **id** rather than its
name when arrived at by link.

**Filters live in the URL** (`?state=&district=&phc=&vital=1`), which makes a
filtered view shareable and — the reason it was built — makes the controls
verifiable in a real browser, since headless Chrome cannot click a dropdown.
Without it the only evidence would have been that the endpoint behaves when
called directly, which tests the backend and not the page.

**The filters were never broken; the choices were.** The dropdowns were fed
from the facility register — **200,438 facilities across 668 districts** —
while only **200 facilities in 116 districts** report stock. Picking a health
centre therefore had roughly a **one in a thousand** chance of landing on one
with data, and every other pick emptied the page. `/api/v1/today2/geography`
now returns only what reports (5 states, 116 districts, 200 centres, with the
line count on each), which is also the honest presentation of the demo
footprint — it stops the product implying facility-level coverage of all
200,438. It is 200 rows, so it is fetched once and the cascade needs no further
round trips.

**The health-centre list is the register, not the reporting set.** Narrowing
it to the 200 reporting centres fixed blank pages and created a worse problem:
it hid the facility master. These five states hold **7,092 PHCs** and 200 of
them report, so a list of 200 made national government data look like a pilot
of two hundred clinics. The list now shows every PHC in the district in two
groups — **"Reporting stock"** first with each centre's line count, then
**"In the register, not yet reporting"**. Brihan Mumbai reads *2 reporting of
296*; Khammam *2 of 71*.

Both facts are worth showing and neither may be implied by the other: the
200,438-facility register is real government data, and the 200-centre reporting
footprint is the demo's. Picking a non-reporting centre is answered with a
sentence — *"Allapalli is in the national facility register but is not yet
reporting stock data"* — and answered without a round trip, because a centre
that does not report cannot have a scorecard.

Coverage by level, for the five demo states:

| Level | Reporting | In the register |
|---|---|---|
| States | 5 | 5 |
| Districts | 116 | 116 — **complete** |
| PHCs | **200** | **7,092** |

Districts are already complete (Assam 27/27, Delhi 11/11, Maharashtra 35/35,
Rajasthan 33/33, Telangana 10/10), so only the PHC level ever had a gap.

**One way the merge could fail invisibly:** a reporting centre missing from the
district's facility list would be unreachable — its data exists and no dropdown
could select it. `test_reporting_centres_appear_in_the_register_list` pins that
across three districts, and a companion test asserts all 200 are typed `phc`,
since the register list is fetched with that filter.

**A percentage can legitimately be null, and it was reaching the page as the
literal text "null%".** A facility with no life-saving medicines has no
life-saving availability. Handled once, inside the tile, so no tile added later
can reintroduce it; the affected scopes now render "—" with the sentence "No
life-saving medicines are tracked here."

**Beds and staff are graded, not deferred.**

| Beds | | Staff | |
|---|---|---|---|
| Beds free on average | **69.5%** | Posts filled | **77.8%** |
| Centres over capacity | **22.5%** (45 of 200) | Worst state and role | **56.2%** (Pharmacist, Rajasthan) |
| Patients turned away (30 days) | **392** | Roles 30% vacant or worse | **31.6%** (6 of 19) |
| Centres turning people away | **22.5%** | Nurses below the bed norm | **11** |
| Districts affected | **25.9%** | Sanctioned posts | **1,061** |

The staff ranking is by **role, not by facility**: "health assistants are
**32.9%** vacant, against doctors at **16.9%**" is a recruitment decision, and
no per-facility list adds up to that sentence.

**All three resources return one contract** — `kpis`, `labels`, `distribution`,
`ranking`, `quadrant`, `summary` — so a single front-end path renders any of
them. Three near-identical copies of each chart would have been three places
for one bug to be fixed twice and missed once; `TestAllThreeResourcesShareOneContract`
pins the shape.

**Beds and staff have no fourth question.** Medicines ask "could the network
take a shock"; there is no bed equivalent, so rather than invent one those two
get the provenance panel — which matters more for them anyway, because bed
occupancy is **modelled** while capacity (IPHS 2022) and vacancy (RHS
2021-22) are real — daily attendance is not shown at all — and a reader would
otherwise assume all three were counted.

*(Superseded: beds and staff are graded — see above.)*

## 7a. The map — geography of supply

*Last verified against the live deployment: **2026-09-04**.*

Served by `/api/v1/map` (`app/mapview.py`), drawn by `web/map.js`. One
BigQuery round trip, 0.162 GB scanned on a dry run, ~0.22 s warm.

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **116 districts plotted** | every district reporting stock; all 116 resolve to coordinates | **MEASURED** | `app/mapview.py` |
| **199,805 geocoded facilities** of 200,438 | `facilities.has_valid_coords` in the register | **REAL** | facility register |
| District position | **mean coordinate of the district's facilities** — the centre of care, not the polygon centroid | **REAL, DERIVED** | `coords` CTE |
| **64 of 116 districts short on a Vital line** | `reorder_status`, `ven_class = 'Vital' AND needs_reorder` | **MEASURED — LIVE** | `risk` CTE |
| **80 districts cannot absorb a 3x spike** | `network_absorption`, `multiplier = 3.0`, threshold **<35% of positions holding** | **MEASURED** | `headroom` CTE |
| **144 cross-district moves**, **35,905 units**, longest **148 km** | `recommendations` joined to the donor facility's district | **MEASURED — LIVE** | `flows` CTE |
| **362 of 527** recommendations cross a district boundary | the remaining 165 are intra-district and are not drawn — the arc would be a dot on the node | **MEASURED** | `flows` CTE |

**The 35% threshold is deliberately the same one Today's absorption bars
use.** If the map had picked its own, the two views would
disagree about the same district; `test_mapview.py` pins them together.

**A correction worth recording.** The flow layer first shipped empty. The query
filtered `recommendations.status = 'recommended'`, but that column holds the
*receiver's* stock condition — `critical` / `reorder` / `stocked_out` — not a
lifecycle state. It matched 0 of 527 rows, and the redistribution layer
vanished while the district layer looked perfect. The status is now ranked
rather than filtered, and colours each arc by how badly the receiving district
needs what is being sent. `test_flows_are_not_empty` exists so an empty layer
fails loudly rather than reading as a calm network.

**Not claimed:** the arcs are recommendations, not journeys. Nothing here says
a vehicle moved. Distance is straight-line between district centres, which
understates road distance — so any distance shown is a floor, never a boast.

### 7a-i. The register layer — every centre, not just the reporting ones

*Last verified against the live deployment: **2026-09-13**.*

| Figure | Value | Status | Computed in |
|---|---|---|---|
| PHCs and CHCs drawn | **34,935** | **MEASURED** | `app/mapview.py::facility_register` |
| ...of which primary health centres | **29,564** | **MEASURED** | same |
| ...of which community health centres | **5,371** | **MEASURED** | same |
| Reporting stock today | **200** (**0.6%**) | **MEASURED** | same — the forecast set every other view counts |
| Carry coordinates that cannot be placed | **173** | **MEASURED** | excluded and disclosed, not drawn |
| Payload | 687 KB, 0.58 s warm | **MEASURED** | fetched only when the layer is selected |

The other three layers draw the demonstration set — 116 district nodes, and on
Nearest help the 200 centres that report stock. A map showing only those
invites a reader to believe 200 centres are the network. This layer draws the
rest, so **national scale is visible rather than asserted**.

> ⚠️ **0.6% is the honest coverage figure and must not be rounded away.** The
> claim is not that 34,935 centres are live; it is that they are in the
> register and the platform would onboard them. The onboarding argument is the
> pattern exchange: a district joining brings three months of history, which is
> too little to find its own seasonality, so it borrows the pooled seasonal
> shape and is useful on day one (§5).

**Coordinates are filtered on the register's own `has_valid_coords` flag**, the
same rule the district centroids use. It matters: 173 of the 35,108 PHCs and
CHCs that carry coordinates carry impossible ones — a longitude of
**75,070,600,009**, a latitude equal to its own longitude (which lands in
Egypt), points in China and in the Arctic Ocean. A first version filtered only
for NULL and would have drawn every one of them. Measured, the flag is exactly
equivalent to an India bounding box here: nothing it admits falls outside,
nothing it rejects falls inside, so the two rules cannot drift apart unnoticed.

Rendered to a canvas with hit-detection off. 35,000 SVG nodes is a frozen tab.

---

## 7g. The Report page — what a health worker can do, and what is guaranteed

*Built 2026-09-18. Every fact here is checkable in `web/report.js`,
`app/capture_pipeline.py`, `app/capture.py` and `GET /api/v1/capture-modes`.*

| Claim | Where it is true |
|---|---|
| **Six ways in, one pipeline**: tap, barcode, voice, chat, register photo, SMS | `capture_pipeline.SOURCES`; every source ends in `route()` |
| **Nothing is written until the worker has heard it read back and said yes** — voice, chat and photo all preview first; `preview()` never persists | `capture_pipeline.preview()`; `tests/test_report_flow.py::TestPreviewNeverWrites` |
| The one exception is the **offline queue**, which syncs with nobody holding the phone and so goes straight through the confidence gate | `app.js syncQueue()`; `TestVoiceAndChatPreview::test_voice_without_preview_still_writes` |
| A **confirmed row cannot skip the gate**: an unrecognised item, an event type the ledger does not record, or a missing quantity is still held for the pharmacist | `TestConfirmWritesThroughTheGate` |
| A client-supplied item id is **verified against the catalogue, never trusted** | `route()`; `test_a_client_supplied_id_is_verified_not_trusted` |
| **A register photo can never write unconfirmed** — `handle_photo()` has no non-preview path | `app/capture.py`; `TestPhotoIsAlwaysAPreview` |
| **39 tap tiles** — the forecast items; **16 carry a Devanagari name** from the catalogue's `spoken_variants`, the rest show their shortest spoken variant. Nothing is machine-transliterated | `items.quick_list()`; `GET /api/v1/items/quick` |
| The page reads in **Hindi or English** from one dictionary; both languages carry the same keys, tested | `REPORT_STRINGS`; `TestTheReportPageStrings` |
| The read-back is **spoken** in the chosen language via the browser's speech synthesis (`hi-IN` / `en-IN`). No cloud TTS call is made | `speakReadback()` |
| The centre is **chosen once and remembered on the phone**; the old page posted every voice note against a hardcoded facility id | `report.js`; `test_the_page_no_longer_posts_against_a_hardcoded_centre` |
| **Offline** is a sentence and a count of what the phone still holds | `updateOfflineLine()` |
| **Staff on duty today** is captured as personnel `count` events through the same pipeline. It is the only attendance figure the system holds | `staffReadback()`; `test_staff_on_duty_goes_through_as_personnel` |
| **SMS**: `POST /api/v1/sms-note` accepts `sender` and `message`; the message must begin with the centre id; the reply is one plain line per record. **No gateway is connected**, and the docs and the endpoint both say so | `capture.handle_sms()`; `TestSms` |
| The review queue holds **only real extractions**; the invented worked examples are gone | §12 |
| **Beds in use right now** is captured the same way, as bed `count` events against the closed bed vocabulary | `bedsReadback()`; `capture_pipeline.BED_VOCABULARY` |
| Today's staff and bed views each carry a **"Centres reporting … today" tile counted from the ledger** (capture-sourced `count` events in the last 24 hours, in scope). It read **0** on 2026-09-18 and says so; nothing is modelled in its place | `today_v2.reported_today()`; `tests/test_today_v2.py` |
| **The action queue drafts the escalation note with Gemini**, grounded on the row's own figures. Every number in the draft is checked against the row; a draft that mentions a figure not in the data is returned **flagged with the foreign numbers listed**, never silently | `app/brief.py`; `POST /api/v1/action-queue/brief`; `tests/test_brief.py` |
| The draft is told not to state a cause (not in the data), not to name anyone or anything not in the facts, and to end by asking for the decision rather than making it | `brief.SYSTEM` |

**Not claimed:** that any ASHA has used it; that speech synthesis is available
on every handset (it is a browser feature, absent on some); that a photo of a
handwritten register reads accurately — every row is shown for checking
precisely because it may not.

## 8. Beds and personnel

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **178,398 beds** across 29,733 PHCs | IPHS 2022 Vol III pp. 46-47: 2 essential + 4 desirable | **REAL NORM, applied** | `ingestion/set_bed_capacity.py` |
| **148,554 overnight beds** | rural PHCs only; urban PHCs get day-care beds | **REAL NORM** | same |
| `is_24x7` = **NULL for every PHC** | nothing in the data records it | **EXPLICIT UNKNOWN** | same — a test asserts it stays unpopulated |
| **1 nurse per 6 beds** | **Indian Nursing Council regulation**, which CHC IPHS 2022 *cites* at p.60 and tabulates at p.118 | **REAL** | `set_bed_capacity.py`, `build_facility_staffing.py` |
| Doctor (allopathic) at PHCs vacancy **23.8%** (9,451 vacant of 39,669 sanctioned; 30,640 in position) | Rural Health Statistics **2021-22**, as on 31 Mar 2022, rural Table 16 | **REAL** | `ingestion/extract_rhs_2122.py` → `load_staffing.py` |
| Health assistant [M+F] at PHCs **37.0%** (6,580 / 17,796) — **one cadre now**; the 2017 male/female split is not published | same, Table 15 | **REAL** | same |
| Nursing at PHCs **23.8%** (10,776 / 45,310); at CHCs **22.3%** (12,174 / 54,698) — published separately now | same, Tables 33 and 34 | **REAL** | same |
| Pharmacist at PHCs **23.2%** (5,766 / 24,906); at CHCs **18.8%** (1,723 / 9,160) | same, Tables 29 and 30 | **REAL** | same |
| Pharmacists sanctioned (34,066) vs required (30,415), PHC+CHC | same | **REAL** | same — sanctioned now **exceeds** required; the 2017 'below required' claim no longer holds |
| **Telangana sanctions 0 health assistants at PHCs** against 1,156 required | same, Table 15 | **REAL** | no vacancy rate can exist; 20 centre-roles excluded rather than counted as zero |
| **35 bed referral routes**, 24 facilities, mean 33 km | occupancy vs capacity, 50 km limit | **MEASURED** on generated occupancy | `ingestion/build_resource_status.py` |
| **0 staff reallocations** | **2** of 4 cadres (health assistants, pharmacists) sanctioned at most one post per PHC under RHS 2021-22 — 3 of 5 under 2017; doctors and nursing carry more than one somewhere, 116 districts apart | **MEASURED — a real finding** | `app/resources.py`; the API returns the reason, not an empty list |

> ⚠️ **Attribute 1:6 to the Indian Nursing Council, not IPHS.** IPHS cites it;
> the INC originates it. This wording is required everywhere including the deck
> and video.

> ⚠️ Bed **occupancy** is generated. Bed **capacity** and staff **vacancy**
> are real. Do not blur them.

> ⚠️ **Turned away is a 30-day figure, not a year.** 392 patients in the 30
> days of reporting to 29 August 2026, at 45 centres. Three pages said "over the
> year"; corrected 2026-09-11. The same day a rebuild showed 339: `bed_status`
> anchored its window to the latest event of *any* resource, so medicine
> captures on 2-3 September slid it past the end of the bed data. The window is
> now anchored to the bed ledger itself.

> ⚠️ **Staff attendance was removed from the product on 2026-09-11.** It is not
> disclosed any more because it is not shown any more — see §8a.

### 8a. Staff attendance — removed, not disclosed

> **2026-09-18.** One attendance figure now exists again, and it is the only
> kind this system will hold: **what a centre reports**, through the Report
> page's *Staff today* form, as personnel `count` events in the ledger. The
> staff view carries a tile counting centres that reported in the last 24
> hours. On the day it was built it read 0, which is the truth. Nothing
> below this note has changed: the generated series is gone and stays gone.

*Last verified against the live deployment: **2026-09-11**.*

`ingestion/generate_bed_personnel.py` builds `mean_present` from a fixed-seed
random attendance propensity, lower on Sundays. Four surfaces reported it:

| Surface | What it said | Status |
|---|---|---|
| Today v2 | "Actually on duty **53.2%**" | **REMOVED** |
| Today v2 | "Roles with a day nobody came" and "Districts affected" | **REMOVED** |
| Today v1 national summary | "in **875** cases a role had a day with nobody on duty at all" | **REMOVED** |
| `/api/v1/personnel/reallocation` | proposed staff moves | **REMOVED** — each was the difference of two generated numbers, and the `status` values selecting donor and recipient (`unstaffed`, `adequate`) are thresholds on the same generated column |

It was also wrong on its own terms:

| Check | Result |
|---|---|
| Facility-cadres that are fully vacant | **0** |
| ...yet report zero present across all 30 days **with posts filled** | **278** |
| Rows with `days_none_present > 0` | **875 of 928 — 94%** |

A flag that fires on 94% of rows cannot separate a struggling centre from a
healthy one, and the 875 was a count of random draws.

**What replaced it is real, and narrower.** `vacancy_rate` takes one value per
state and cadre — **23** under RHS 2017, **20** under RHS 2021-22, where
health assistants became one cadre. It does **not vary by district or by
facility**.

> ⚠️ **No personnel figure may be reported per district or per facility.** The
> staffing scatter used to plot 116 districts from those 23 numbers, inviting a
> reader to compare districts carrying an identical figure — the same mistake
> already corrected once on the Network page. It now plots one point per
> **state and cadre** — 19 of them, Telangana's health assistants having
> no rate to plot.

Rates are weighted by sanctioned posts: a plain average gave Delhi's 11 posts
the same say as Maharashtra's several hundred. Under 2021-22, 0 centre-roles
in our five states are over establishment (2017 had 47; the cap at 100% filled
stays because the source reports it elsewhere), and 20 have no vacancy
rate because Telangana sanctions no health-assistant posts.

**The data layer, not just the pages.** The first pass hid generated attendance
at the API while `staff_status` was still *built from* it, with real vacancy
LEFT JOINed on. It is now built from the establishment: no generated column
exists in it, `staff_reallocation` is dropped, and the generator no longer
produces personnel. On **2026-09-12** the 338,720 generated attendance rows
were deleted from `resource_events` as well (**1,570,343 → 1,231,623**; bed
74,240 and medicine 1,157,383 untouched, and no captured personnel row existed
to lose), so nothing generated about personnel survives anywhere in the
warehouse. BigQuery time travel keeps a seven-day undo window on that table.

> ⚠️ **"Nurses below the bed norm" was described as per-facility and real. It
> was computed against generated attendance.** It now uses nurses in position —
> the state rate applied to each centre's posts — which is an estimate, and the
> tile says so.

**Live product figures after the 2021-22 refresh** (200 forecast PHCs):

| Figure | Value |
|---|---|
| Posts filled, weighted by establishment | **77.8%** |
| Worst state and role: Pharmacist | **56.2%** — Rajasthan; nationally the hardest role is health assistants at **32.9%** |
| Roles 30% vacant or worse | **31.6%** — 6 of 19 state-and-cadre pairs |
| Nurses below the bed norm | **11** |
| Sanctioned posts | **1,061** |
| National summary line | "22% of 1,061 sanctioned posts are unfilled across 200 health centres, and Health assistant is the hardest role to fill at 32.9%." |

---

## 9. Surge detection

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| Classical standardised residual is bounded at **3.175** for n=12 | (n−1)/√n | **REAL — arithmetic** | `ingestion/build_surge_signals.py`; assertion fails the build if exceeded |
| Observed maximum classical z = **3.17** | across 58,932 series-months | **MEASURED** | same |
| Modified z threshold **3.5** | Iglewicz & Hoaglin, *How to Detect and Handle Outliers*, ASQC 1993, §4.4 | **REAL — cited** | same, `SURGE_Z` |
| Observed maximum modified z = **166.7** | same data | **MEASURED** | same |
| **1,295 surges** from **58,932** series-months (2.2%) | all three conditions | **MEASURED** | same |
| 2,406 passed the statistic; **355** rejected on ratio, **756** on magnitude | condition flags per row | **MEASURED** | same |
| Median district-month for confirmed malaria = **3 cases** | why the magnitude floor exists | **REAL** | `demand_reference` |
| **Brihan Mumbai, January: 2,345 observed vs 987.8 expected** | baseline 1,400.5 × pooled 0.7053 | **REAL HMIS** | `surge_signals` |
| — surge multiplier **2.37×**, modified z **6.54**, classical z **2.58** | same row | **MEASURED** | same |
| — flat-average ratio would be only **1.67×** | 2,345 ÷ 1,400.5 | **MEASURED** | same |
| **Gadchiroli: 2.22× / 2.34× / 3.03× and never flagged** | winter-peaking vs monsoon-shaped pooled vector ⇒ large MAD | **MEASURED — the counter-example** | same |
| needs-reorder **100 → 198** under surge; **98 newly at risk** | surge reorder points | **MEASURED** | `ingestion/build_surge_supply.py` |
| **145 of 322** can only be served laterally | `days_to_stockout < lead_time_days` | **MEASURED** | same |
| Lead-time gradient **43.5% / 47.9% / 80.0%** (6-10d / 11-15d / >15d) | same | **MEASURED** | same |
| Absorption: **59.0%** hold 2×, **30.1%** hold 3×, **4.3%** hold 5× | 1,652 district-classes | **MEASURED** | same → `network_absorption` |
| **101 surge transfers**, 5,881 units, 29 rationed by donor capacity | Vital-first cumulative allocation, 300 km | **MEASURED** | same |
| Widening the radius 150 → 300 km unlocked **only 2** extra transfers | same | **MEASURED — a modest result, reported as such** | same |
| Brihan Mumbai antimalarials absorbs at most **0.86×** | 110 units ÷ (15.95/day × 8-day lead time) | **MEASURED — a network finding, not a model defect** | `app/surge.py`, `structurally_thin` |

> ⚠️ **The 0.86× must be framed as a finding about how thinly the district is
> stocked**, true before any surge is applied. It is not a bug and must not be
> presented as one. The API returns `structurally_thin_note` for exactly this
> reason.

---

## 10. Data quality — the exclusions we disclose

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Meaning | Status | Computed in |
|---|---|---|---|
| **633 facilities** excluded from distance maths | `has_valid_coords = FALSE` | **REAL** | `load_facilities.py`; served at `/api/v1/data-quality` |
| — of which **80** | latitude/longitude blank or non-numeric | **REAL** | same |
| — of which **553** | value present but outside plausible bounds for India | **REAL** | same |

> ⚠️ **The duplicated write-off id changes no published figure.** Both rows are
> genuine write-offs of different quantities from different batches. The balance
> sums quantities rather than ids, so ledger-to-batch reconciliation drift is
> **0 across all 7,728 facility-item pairs**;
> `impact_metrics.units_expired_fefo` (**32,893**) matches the ledger sum of
> expired quantities exactly; and FEFO batch keys come from `received` events,
> of which all **70,048 are unique**. The only fix is regenerating 1.16M rows to
> change no number, which was judged a bad trade before submission. Three tests
> pin the collision count at exactly 1 so it cannot grow unnoticed.

> ⚠️ **The categories at `/api/v1/data-quality` do not add up to 633, and that
> is correct.** They overlap: 80 missing + 224 latitude beyond ±90 + 248
> longitude beyond ±180 = 552, but **206 rows fail on both** latitude and
> longitude, giving 346 distinct; plus 287 inside the valid globe but outside
> India = **633**. If asked to reconcile them, give exactly that arithmetic.
| **73 facilities** with no `population_served` | Delhi CHCs and hospitals; source records `NA` | **REAL** | same |
| Coordinates are **never corrected** | inferring a swapped Mizoram lat/long is a guess | **policy** | same |
| `Ahmadnagar` (HMIS) vs `Ahmednagar` (facility master) | both spellings kept; reconciled via `district_key`; UI displays one | **REAL** | `parse_hmis.py`, `app/facilities.py` |
| 2019-20 HMIS = **April 2019 – March 2020** | Feb and Mar 2020 are COVID-affected | **REAL caveat** | `Data/README.md` §4 |
| **1 duplicated write-off id** in 770 expiry events | `generate_usage.py` builds write-off ids as `seed-x-{facility}-{item}-{date}` with no batch discriminator, so two batches of one item expiring at one facility on one day collide | **REAL, known, deliberately unfixed** | `ingestion/generate_usage.py:461`; pinned by `tests/test_supply_chain.py::TestKnownSeedDefects` |
| Rural Health Statistics vintage = **2021-22** (as on 31 Mar 2022; refreshed from 2017 on 2026-09-11) | a newer edition, *Health Dynamics of India 2023-24* (as on 31 Mar 2024), was obtained on 2026-09-15 and **deliberately not used**: its tables are vector outlines rather than text and cannot be parsed, and staying on 2021-22 was chosen over hand transcription | **REAL caveat** | `extract_rhs_2122.py`, `load_staffing.py`, `source_year` on every row |

---

## 11. UNTRACEABLE — do not use

*Last verified against the live deployment: **2026-09-02**.*

| Claim as stated | What was found | Verdict |
|---|---|---|
| **"Rohani / Jagji 1,381 vs 327, 476-tablet shortfall"** | **Jagji** is a real forecast PHC in Solapur, Maharashtra, with five real transfer recommendations. **Rohani is not a forecast facility** — the directory has `Rohania`, `Rohania Laxman` and `Rohania Maneng`, all in Rajasthan, none in the forecast set. No pair anywhere produces 1,381 / 327, and no shortfall equals 476. Jagji's deepest real shortfall is Metformin: 23 on hand against a 138.5 reorder point (115.5 short). | **Do not use.** Cannot be reproduced from any table. |

**Replacement, fully traceable —** use this as the transfer worked example:

> **Moterjhar SD → Fokirgonj MPHC, Dhubri district, Assam.**
> **5,783 units of Ferrous Salt**, moved **27.0 km**.
> Receiver: **completely stocked out** — 0 units on hand against a reorder point
> of 3,855 — goes from **0.0 to 14.2 days of cover**.
> Donor: **64.1 → 46.3 days**, still comfortably above its own reorder point.
>
> Computed in `ingestion/build_supply_plan.py`, row in
> `daysupply.recommendations`, served at `/api/v1/recommendations`.

This is the largest real transfer in the system and the receiver is genuinely at
zero, which is a stronger demo than the untraceable figure it replaces.

---

## 11a. Language — wording that must not drift

*Last verified against the live deployment: **2026-09-03**.*

These are not style preferences. Each one is a claim we cannot support, paired
with the one we can.

| Never say | Say instead | Why |
|---|---|---|
| "federated learning" | **"Districts exchange seasonal shape, not data"** — and pair it with the measured result: pooling cuts forecast error from **21.1% to 15.6% wMAPE** across six states (it was 19.4% to 14.4% across five; see §0) | There are no gradients, no secure aggregation and no client-side training. What crosses a boundary is twelve numbers per medicine class, from aggregate HMIS that is already public. The honest claim is stronger *and* measured |
| "predicts outbreaks" | **"We detect that one has begun, earlier and more reliably than a 3-sigma rule"** — which on twelve monthly observations cannot fire above **3.175** at all | We have no forward-looking outbreak model. What we have is a better detector, and the bounded-z finding is the evidence |
| "368 HMIS indicators available" | **"21 HMIS drivers loaded, 20 used by forecast items"** | 368 is the count of data items in the source file. It is not in this document, so it is not evidence. Stating it as capability implies we use them |
| cold chain, GS1 / GTIN serialisation | *nothing* — leave them off any roadmap surface | **eVIN** already does cold chain for vaccines and **DVDMS** already does barcode; listing them reads as not having checked what exists |

**Verified by grep across `.py`, `.md`, `.js` and `.html` on 2026-09-03:**

* "federated" survives in exactly three places, all correct: a comment in
  `app/main.py` explaining why the phrase is *not* used, the original
  `MASTER_PROMPT.md` instruction not to attempt it, and dated log entries in
  `PROGRESS.md`. The Firestore collection `federated_patterns` was renamed to
  `pattern_vectors` — it held no documents.
* "predicts outbreaks" appears twice, both times as the negation.
* "368" appears only as context about the source file, never as a capability
  claim.
* Cold chain and GS1 appear only in the original spec's out-of-scope list.

---

## 12. Figures that are still generated — say so every time

*Last verified against the live deployment: **2026-09-02**.*

> **Corrected 2026-09-02.** Two rows in this section were stale and described
> the system as it was before the capture loop was closed: `captures_today` was
> listed as "stuck at 0" when it reads 9, and the review queue as "3 worked
> examples" when it holds 4 real items. Staff attendance was listed at 56% and
> measures 53%. A judge checking our own honesty document against the live
> system would have found the contradiction — which costs more than any figure
> in it is worth. Every other section was re-verified at the same time; all 70
> checkable figures matched.

| Figure | Why it is generated |
|---|---|
| **1,157,367 daily stock events** | no per-facility daily stock data is published in India by anyone |
| Bed **occupancy** (2,430 turned away) | derived from real HMIS admission volumes × assumed 1.8-day length of stay. Since 2026-09-18 a centre can report **beds in use right now** from the Report page; the bed view's "Centres reporting beds today" tile counts those reports (0 at build) and the tile text says the occupancy figures beside it are modelled |
| ~~Staff **attendance** (53% of sanctioned)~~ | **REMOVED from the product 2026-09-11 — do not quote it at all.** It was a fixed-seed random draw, and 875 of 928 rows carried its "nobody on duty" flag. See §8a. |
| `captures_today` | **NOT generated — counted, and the loop is closed.** Reads **9** all-time (9 chat, 0 voice, 0 barcode), written straight into `resource_events` above the confidence gate. `is_generated: false`. It moves within seconds of a capture. |
| Review-queue items | **Only real held extractions** (4 on 2026-09-18: 3 chat, 1 barcode), `is_example_data` is always `false`. The three invented "worked examples" that used to fill an empty queue were removed on 2026-09-18 with `app/demo_data.py`; an empty queue now says it is empty. |

**The one sentence that must accompany any demo figure:**

> Every facility, every medicine, every demand driver, every bed norm and every
> vacancy rate is real published government data. The daily stock ledger is
> generated from those real drivers, because no country publishes per-facility
> daily stock — and that is exactly the gap this product exists to close.
