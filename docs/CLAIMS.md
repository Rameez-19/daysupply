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

---

## 8. Beds and personnel

*Last verified against the live deployment: **2026-09-02**.*

| Figure | Derived from | Status | Computed in |
|---|---|---|---|
| **178,398 beds** across 29,733 PHCs | IPHS 2022 Vol III pp. 46-47: 2 essential + 4 desirable | **REAL NORM, applied** | `ingestion/set_bed_capacity.py` |
| **148,554 overnight beds** | rural PHCs only; urban PHCs get day-care beds | **REAL NORM** | same |
| `is_24x7` = **NULL for every PHC** | nothing in the data records it | **EXPLICIT UNKNOWN** | same — a test asserts it stays unpopulated |
| **1 nurse per 6 beds** | **Indian Nursing Council regulation**, which CHC IPHS 2022 *cites* at p.60 and tabulates at p.118 | **REAL** | `set_bed_capacity.py`, `build_facility_staffing.py` |
| Doctor vacancy **20.1%** (33,968 sanctioned / 27,124 in position) | Rural Health Statistics 2017 | **REAL** | `ingestion/load_staffing.py` |
| Health assistant (male) **46.0%** (22,753 / 12,288) | same | **REAL** | same |
| Health assistant (female) **34.4%** (21,748 / 14,267) | same | **REAL** | same |
| Pharmacist **14.1%** (29,315 / 25,193) | same — PHC **and** CHC denominator | **REAL** | same |
| Nursing **9.3%** (77,956 / 70,738) | same — PHC **and** CHC denominator | **REAL** | same |
| Pharmacist sanctioned (29,315) is **below** required (31,274) | same | **REAL** | same |
| **35 bed referral routes**, 24 facilities, mean 33 km | occupancy vs capacity, 50 km limit | **MEASURED** on generated occupancy | `ingestion/build_resource_status.py` |
| **0 staff reallocations** | 4 of 5 cadres sanctioned at one post per PHC; nearest nursing donor **1,218 km** | **MEASURED — a real finding** | same; the API returns the reason, not an empty list |

> ⚠️ **Attribute 1:6 to the Indian Nursing Council, not IPHS.** IPHS cites it;
> the INC originates it. This wording is required everywhere including the deck
> and video.

> ⚠️ Bed **occupancy** and staff **attendance** are generated. Bed **capacity**
> and staff **vacancy** are real. Do not blur them.

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
| Rural Health Statistics vintage = **2017** | superseded by *Health Dynamics of India* | **REAL caveat** | `load_staffing.py`, `source_year` on every row |

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
| "federated learning" | **"Districts exchange seasonal shape, not data"** — and pair it with the measured result: pooling cuts forecast error from **19.4% to 14.4% wMAPE** | There are no gradients, no secure aggregation and no client-side training. What crosses a boundary is twelve numbers per medicine class, from aggregate HMIS that is already public. The honest claim is stronger *and* measured |
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
| Bed **occupancy** (2,430 turned away) | derived from real HMIS admission volumes × assumed 1.8-day length of stay |
| Staff **attendance** (**53%** of sanctioned) | product of real vacancy and a generated presence model |
| `captures_today` | **NOT generated — counted, and the loop is closed.** Reads **9** all-time (9 chat, 0 voice, 0 barcode), written straight into `resource_events` above the confidence gate. `is_generated: false`. It moves within seconds of a capture. |
| Review-queue items | **Currently 4 REAL held extractions**, `is_example_data: false` — items the model was unsure about, awaiting a human. Three worked examples exist as a fallback *only* when nothing real is pending, and are then labelled `is_example_data: true` with a banner. **Check the flag before describing them.** |

**The one sentence that must accompany any demo figure:**

> Every facility, every medicine, every demand driver, every bed norm and every
> vacancy rate is real published government data. The daily stock ledger is
> generated from those real drivers, because no country publishes per-facility
> daily stock — and that is exactly the gap this product exists to close.
