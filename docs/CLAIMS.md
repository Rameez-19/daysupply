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

---

## 7b. The Today dashboard — what the charts say

*Last verified against the live deployment: **2026-09-04**.*

The landing view was ninety stacked text cards; it is now eight stat tiles,
two charts and two meters, with the prose kept underneath as the explanation
rather than the interface. Every figure below is served by `/api/v1/executive`
in the same single round trip.

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
disagree one of the headline numbers is wrong; `test_executive.py` fails first.

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
from Rural Health Statistics 2017, which publishes at state level. Measured:
**exactly one distinct value per state** — all 33 Rajasthan districts read
59.3%, all 27 Assam districts read 96.3%. A district table built on it would
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

**The three views must agree.** `test_today_v2.py` asserts that tracked, short,
stocked-out and vital-short match `/api/v1/executive` exactly, that absorption
matches it multiplier for multiplier, and that the 3x shock and the 35%
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
| Beds free on average | **69.5%** | Posts filled | **78.2%** |
| Centres over capacity | **22.5%** (45 of 200) | Actually on duty | **53.2%** |
| Patients turned away | **392** | Roles with a day nobody came | **94.3%** (875 of 928) |
| Centres turning people away | **22.5%** | Nurses below the bed norm | **11** |
| Districts affected | **25.9%** | Districts affected | **100%** |

The staff ranking is by **role, not by facility**: "male health assistants are
**38.4%** vacant, against doctors at **8.6%**" is a recruitment decision, and
no per-facility list adds up to that sentence.

**All three resources return one contract** — `kpis`, `labels`, `distribution`,
`ranking`, `quadrant`, `summary` — so a single front-end path renders any of
them. Three near-identical copies of each chart would have been three places
for one bug to be fixed twice and missed once; `TestAllThreeResourcesShareOneContract`
pins the shape.

**Beds and staff have no fourth question.** Medicines ask "could the network
take a shock"; there is no bed equivalent, so rather than invent one those two
get the provenance panel — which matters more for them anyway, because bed
occupancy and daily attendance are **modelled** while capacity (IPHS 2022) and
vacancy (RHS 2017) are real, and a reader would otherwise assume all four were
counted.

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

**The 35% threshold is deliberately the same one the executive view's
absorption bars use.** If the map had picked its own, the two views would
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
