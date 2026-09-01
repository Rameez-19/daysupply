# Data provenance and methodology

This file records where every number in StockPulse comes from, and — more
importantly — which numbers are measured and which are derived or generated.
Read it before quoting any figure from this system.

Scope note: the project is **India-only**. `Data/Brazil/` and
`ingestion/load_brazil.py` remain on disk from an earlier framing — they are the
evidence that the `config/` layer makes another country a configuration change
rather than a rewrite — but nothing Brazilian is loaded or built against. The
50,697 Brazilian rows that had survived in `facilities` were **deleted on
2026-09-01**, so `SELECT COUNT(*) FROM facilities` now returns exactly the
200,438 this document publishes.

---

## 1. Facility master — REAL, fully loaded

| | |
|---|---|
| Source | `Data/India/geocode_health_centre.csv` |
| Provenance | NHM / MoHFW health-centre directory (via Kaggle, "All India Health Centres Directory") |
| Rows | **200,438 — all of them.** Nothing sampled, nothing filtered |
| Coverage | 37 states/UTs, **701 state×district pairs** across 668 distinct district names |
| Loaded by | `ingestion/load_facilities.py` → `daysupply.facilities` (`asia-south1`) |

Facility type breakdown as loaded:

| Type | Count |
|---|---|
| `sub_cen` (sub-centre) | 163,131 |
| `phc` (primary health centre) | 29,733 |
| `chc` (community health centre) | 5,389 |
| `s_t_h` (state hospital) | 1,251 |
| `dis_h` (district hospital) | 934 |

**Real fields:** facility name, state, district, subdistrict, facility type,
latitude, longitude. These are taken from the source file unmodified apart from
whitespace trimming and lowercasing of the facility-type code.

**Known gaps in the source data:**

- **Two different coordinate-gap figures exist and they are not the same number.
  Quote whichever the claim needs, and say which.**

  | Figure | Meaning |
  |---|---|
  | **80** | latitude or longitude is blank or non-numeric in the source |
  | **553** | a value is present but falls outside plausible bounds for India |
  | **633** | `has_valid_coords = FALSE` — the sum, and the count actually excluded from distance maths |

  All 633 are still loaded; dropping them would break the row-count guarantee.
  They are excluded from every distance calculation, which is why transfer and
  referral coverage is quoted against the facilities that have usable
  coordinates, not against all 200,438. Coordinates are **never corrected** —
  inferring that a Mizoram row reading `92.41, 23.25` was meant to be
  `23.25, 92.41` is a guess, and guesses do not go into a government dataset.
  Surfaced at `GET /api/v1/data-quality`.
- One state value is `Andhra Pradesh Old`, a pre-bifurcation artefact present in
  the source. It is preserved as-is rather than silently merged into
  `Andhra Pradesh`; merging would misstate what the government file actually says.

**`facility_id`** is `IN-<zero-based row index of the source CSV>`. It is stable
as long as the source file is not re-ordered, and the loader asserts uniqueness.

**Row-count assertion.** `load_facilities.py` compares the count in BigQuery
against the count in the source file and exits non-zero on any mismatch. The load
deletes and replaces only `country_code = 'IN'` rows, so re-running it can never
double-count.

---

## 2. `population_served` — REAL SOURCE, DERIVED PER FACILITY

**This is an assumption, not a measurement.** State it that way.

| | |
|---|---|
| Source | `Data/India/rural-population-centre_2017.csv` |
| Provenance | Rural Health Statistics 2017, average rural population per centre (Census 2011 base) |
| Granularity of source | **State-level, not facility-level** |

The source file gives, per state/UT, the *average* rural population covered by a
sub-centre, by a PHC, and by a CHC. There is no published per-facility catchment
for India. So:

> **Decision:** `population_served` is the average for that facility's
> **state × facility type**. Every PHC in Telangana therefore carries 31,328;
> every sub-centre in Telangana carries 4,500.

Consequences, stated plainly:

- It is correct in aggregate and wrong for any individual facility.
- It is used **only as a demand-scaling denominator** — a facility covering
  30,000 people is modelled as dispensing more than one covering 5,000. It is
  never presented as that facility's real catchment.
- Within one state and one facility type it carries no information, so it cannot
  by itself explain variation between neighbouring facilities of the same type.

**Type mapping.** District hospitals (`dis_h`) and state hospitals (`s_t_h`) have
no published catchment average. They are assigned the CHC average as a floor,
since they serve at least a CHC-sized population. This understates them.

**Name reconciliation.** Two state spellings differ between the two files and are
mapped explicitly in `STATE_ALIASES`: `A & N Islands` → `A & N Island`, and
`Andhra Pradesh Old` → `Andhra Pradesh` for population purposes only.

**Gaps.** 73 facilities have no population value — all of them Delhi CHCs,
district hospitals and state hospitals, because the source file records `NA` for
Delhi's CHC average. These are left NULL rather than being filled with a guess.

---

## 3. Demo facilities — selection rule

`is_demo_facility = TRUE` where `facility_type = 'phc'` **and** the state is one
of Telangana, Maharashtra, Rajasthan, Delhi, Assam.

That is **7,092 facilities**.

Every one of the 200,438 facilities is loaded, searchable and filterable. The
demo flag marks the subset that carries generated usage history. The honest
framing for the submission is exactly this sentence:

> Every health facility in India is loaded and searchable; daily usage history
> exists for PHCs in five states.

---

## 4. Seasonality reference — REAL

| | |
|---|---|
| Source | `Data/India/<State>.xls` × 36 and `All_India.xls` |
| Provenance | HMIS 2019-20, MoHFW (`hmis.mohfw.gov.in` → Standard Reports → C2) |
| Loaded by | `ingestion/parse_hmis.py` → `daysupply.demand_reference` |

These files are **not Excel**. They are SAS-generated HTML with an `.xls`
extension, `latin-1` encoded, up to ~260 MB each. They are parsed with
`pandas.read_html` / BeautifulSoup, not `openpyxl`.

Structure: districts × data items × 12 months, split Public/Private and
Urban/Rural. The indicators used are outpatient counts for diabetes,
hypertension, epilepsy, mental illness, dental, ophthalmic, acute heart disease
and stroke; malaria positives by species (microscopy and RDT); childhood
diseases; and inpatient counts.

Each forecast item names one of these as its `demand_driver`, so monthly demand
shape is taken from real reported incidence rather than invented.

**Five states are parsed** — the same five flagged `is_demo_facility`:

| State | Districts | Rows |
|---|---|---|
| Maharashtra | 35 | 4,620 |
| Rajasthan | 33 | 4,356 |
| Telangana | 31 | 4,092 |
| Assam | 27 | 3,564 |
| Delhi | 11 | 1,452 |
| **Total** | **137** | **18,084** |

**6,989 of the 7,092 demo PHCs (98.5%) join to real HMIS data** on
`admin_l1` + `district_key`. `admin_l1` is essential: 33 district names recur
across states, so a district-only join would silently mix states.

`district_key` is the reconciled join key; `admin_l2` keeps the value exactly as
the government file reports it. One reconciliation exists so far —
Maharashtra's `Ahmadnagar` (HMIS) against `Ahmednagar` (facility master), worth
103 PHCs. It is listed in `DISTRICT_ALIASES` in `parse_hmis.py`, not applied by
silently rewriting the source value.

⚠️ **2019-20 means April 2019 – March 2020.** February and March 2020 are
COVID-affected. Use April–December or smooth those two months explicitly.

---

## 5. Item master — REAL

The **complete** National List of Essential Medicines 2022 — 385 medicines
across 27 therapeutic sections. Full detail, including the conversion traps in
the source file and the confident-or-null ATC rule, is in §8.

ATC codes are what make therapeutic substitution possible: when an exact item is
unavailable, items sharing an ATC class are surfaced as alternatives.

---

## 6. Deck evidence only — not product data

These are cited in the pitch, never loaded into the product:

- `pharmacists-PHCS-CHCS_2017.csv` — pharmacist counts and vacancies. Evidence
  that the person expected to keep stock records frequently is not there.
- `facilities-PHCS_2017.csv`, `facilities-CHCS_2017.csv` — infrastructure and
  functioning status.
- `rural-area-covered-centre_2017.csv` — area per centre.

---

## 7. Summary — real vs generated

| Component | Status |
|---|---|
| Facility identity, location, administrative hierarchy | **Real**, 200,438 rows, unmodified |
| Facility type breakdown | **Real** |
| `population_served` | **Real source, derived**: state × type average (§2) |
| Monthly demand seasonality | **Real**, HMIS 2019-20 |
| Item list and ATC codes | **Real**, NLEM 2022 + WHO ATC |
| Item list | **Real**, all 385 NLEM 2022 medicines (§8) |
| ATC codes | **Real where assigned**, 264 of 385; NULL rather than guessed (§8) |
| VEN classification | **Derived** — ours, not MoHFW's (§8) |
| Daily stock events | **Generated** from real anchors (§9) |
| Forecasts | **Real** — BigQuery ML ARIMA_PLUS, 3,649 series (§10) |

---

*Section 11 (lead-time proxy) is added by Block C.*

---

## 8. Item catalogue — REAL, complete NLEM 2022

| | |
|---|---|
| Source | `Data/India/nlem2022.xlsx` (a PDF-to-Excel conversion of `nlem2022.pdf`) |
| Provenance | National List of Essential Medicines 2022, MoHFW |
| Loaded by | `ingestion/parse_nlem.py` → `ingestion/build_items.py` → `daysupply.items` |
| Result | **385 medicines across 27 therapeutic sections** |

The conversion is not a clean dataset and is documented in full in the
`parse_nlem.py` docstring. The consequential findings:

- **`Table 1` is two documents in one sheet** — table of contents, then
  Sections 1-3. Skipping it as an artefact silently loses Anaesthetics,
  Analgesics and Antiallergics.
- **`Table 20` changes meaning halfway down.** Rows 0-12 are real medicines;
  row 13 begins "Alphabetical List of Medicines Added"; row 59 begins
  **"Medicines Deleted from NLEM 2015"**, running on through `Table 26`.
  Loading past that point would put *deleted* medicines into the catalogue as
  though they were current. This is the highest-consequence trap in the file.
- **`Tables 27-30` are the page index**, not data.
- **Section codes were silently converted to dates.** `7.1.11` became
  7 January 2011. Recovered as `day.month.two-digit-year`.
- Therapeutic category is a **section heading row, not a column**, and header
  rows repeat at every subsection with shifting column positions.

Official NLEM 2022 contains 384 medicines; the parser yields 385 distinct name
strings. The difference is spelling variants of cross-listed medicines, not
extra drugs.

### ATC codes — REAL, PARTIAL

**NLEM does not publish ATC codes.** They are attached by hand in
`ingestion/atc_map.py` under a confident-or-null rule: **264 of 385 (69%)** have
a code and 121 are NULL. A wrong ATC code is worse than a missing one, because
ATC class is what drives therapeutic substitution — a bad code would surface the
wrong drug as an equivalent. Combination products are keyed in full rather than
resolved to their first ingredient, since a combination's ATC genuinely differs
from its parts.

### VEN classification — DERIVED

`ven_class` is Vital / Essential / Desirable per WHO and MoHFW practice: 109
Vital, 249 Essential, 27 Desirable. It is **our classification, not MoHFW's** —
NLEM does not publish VEN. It is assigned as an NLEM-section default with
per-medicine overrides, both listed in `build_items.py`. NLEM sections are
already organised by clinical purpose, which makes the section a defensible
starting point; the overrides carry sections that mix criticality.

---

## 9. Stock events — GENERATED, from real anchors

| | |
|---|---|
| Built by | `ingestion/generate_usage.py` |
| Scope | 200 PHCs × 39 items × 365 days |
| Rows | ~1.86M, partitioned by `DATE(event_ts)`, clustered by `facility_id` |
| Seed | Fixed (`20260830`) — reruns are identical |

**Real anchors:**

1. **Which facilities** — 200 real PHCs flagged `is_forecast_facility`.
2. **Demand scale** — the district's real HMIS patient volume for that item's
   `demand_driver`, divided by the real number of PHCs in the district. District
   volumes vary 12× to 1750× across Telangana, so this carries genuine
   geographic variation.
3. **Seasonality** — the month-by-month shape of the same real HMIS series,
   joined per district.

> **Corrected.** This section previously read: "Generated antimalarial demand
> peaks in September at 1.53x baseline against the real HMIS figure of 1.58x."
> The match was real, but both sides of it were the seasonality of **blood
> smears collected**, not of malaria. The driver was 99.8% testing effort — see
> §16.1. Against confirmed cases the September index is **1.61x** and the
> annual amplitude is 3.9x rather than 1.6x, so the corrected model carries
> roughly three times the monsoon swing the old one did.

**Why Telangana only.** `demand_reference` holds HMIS 2019-20 for 31 Telangana
districts and nowhere else, because only `Telangana.xls` has been parsed. A
facility outside Telangana has no real demand signal to join to. Rather than
fall back to a synthetic seasonal curve, the forecast set is restricted to where
the real signal exists. All 817 Telangana PHCs join on a case-insensitive
district match.

**Generated, and why:**

| Element | Why it is not real |
|---|---|
| Within-district facility variation | `population_served` is a state × type average (§2), identical for every Telangana PHC. No per-facility catchment is published. A deterministic log-normal multiplier stands in |
| Day-of-week shape | No HMIS data is daily |
| Daily noise | Poisson around the expected value |
| Units per patient | Clinical dosing convention, not data |
| Indent cycle and fill rates | Standard 30-day PHC indent practice |

**The ledger is internally consistent.** `received` events are emitted on the
indent cycle alongside `dispensed` ones, so on-hand is a real computation —
`SUM(received) − SUM(dispensed)` — not a number reconstructed after the fact.
The indent is a **top-up to a 40-day target**, which is how public health supply
chains actually order; a fixed multiple of demand would compound and every
facility would drift into permanent surplus.

A facility that runs out **cannot dispense**. Demand it cannot serve is counted
as unmet rather than allowed to drive stock negative: **348,372 units, 1.0% of
total demand**, were unserved. Zero facility-item balances are negative.

Resulting distribution: 4,894 healthy (14+ days cover), 1,175 low, 1,387
critical, mean 22.1 days.

**Engineered demo scenarios.** Three facilities are put into deficit by a
supply-side failure — they order correctly and the warehouse delivers 35% — each
paired with a same-district donor over-supplied at 230%:

| Deficit facility | District | Cover | Donor | Cover |
|---|---|---|---|---|
| Jahanuma | Hyderabad | 0.1 d | Gaddianaram | 47.2 d |
| Kundaram | Adilabad | 0.2 d | Tiryani | 47.2 d |
| UHC Jangaon | Karim Nagar | 0.3 d | Gopalpoor | 32.3 d |

---

## 10. Forecast model — REAL

| | |
|---|---|
| Model | `daysupply.demand_forecast`, BigQuery ML `ARIMA_PLUS` |
| Trained by | `ingestion/train_forecast.py`; every run logged to `docs/training_runs.json` |
| Series | 3,649 of 7,456 |
| Duration | **15.5 s** (1.23 GB processed) |
| Horizon | 30 days, 80% prediction interval |

`auto_arima=TRUE`, `data_frequency='DAILY'`, series id `facility_id|item_id`.

**Why 3,649 and not 7,456.** Only series with at least 300 observed days are
trained. The rest are genuinely sparse — their HMIS driver reports close to zero
patients in that district; several Telangana districts record an average of one
acute heart disease outpatient a month. A model fitted to that would be worse
than saying nothing. This also keeps training under the 5,000-series ceiling in
MASTER_PROMPT §6.

The model recovers the weekly pattern from the data without being told about it:
a Sunday forecast of 67.8 units against 430.5 the following Monday.

**Nothing in the forecast path is generated at request time.** `app/forecast.py`
queries `ML.FORECAST`; `app/stock_health.py` derives days of cover from that
model and the real ledger. The sine wave that used to produce the dashboard
curve, and the hardcoded JavaScript arrays behind the stock-health and shortage
charts, are gone.

**The expiry tracker has been removed**, not fixed. It was `random.randint` over
a data source that does not exist. It returns in Block C, backed by real batch
expiry data for FEFO.

---

## 11. Lead time — REAL DISTANCE, ASSUMED CONVERSION

**This is a documented proxy, not a measurement.** Say so whenever it is shown.

India publishes no facility-level replenishment lead times. What the facility
master does give is real coordinates for every facility, including the district
and state hospitals that sit at the district headquarters where the drug
warehouse is. So the *distance* is real; the conversion from distance to days
is an assumption.

**District HQ proxy.** The warehouse is taken to be the district hospital.
Where a district has none the chain falls back to state hospital, then
community health centre. Among candidates of the best available type, the one
closest to the district's facility centroid is chosen — the most central
facility is the most likely to sit in the district town. All 116 forecast
districts resolve.

**Distance to days.**

    lead_time_days = clamp(7 + 0.08 x distance_km, 7, 30)

Seven days is order processing and picking, paid by every facility whatever its
distance. The 0.08 slope puts a PHC 20 km out at 9 days and one 145 km out at
19 days. Built by `ingestion/set_lead_times.py`.

`indent_cycle_days` is a flat 30 — the standard monthly PHC indent — and is
derived from nothing. It is stored so the logic reads from data, not a literal.

### Coordinate quality — three real defects in the source

| Defect | Rows |
|---|---|
| Latitude or longitude missing | 80 |
| Latitude outside ±90 | 224 |
| Longitude outside ±180 | 248 |
| Inside the valid globe but outside India (some with lat/long transposed) | 287 |

These are flagged `has_valid_coords = FALSE` (633 facilities, one of them a demo
facility) and excluded from all distance maths. **They are not corrected.**
Inferring that a Mizoram row reading `92.41, 23.25` was meant to be
`23.25, 92.41` is a guess, and guesses do not go into a government dataset.

A fourth defect survives a bounding-box check: coordinates inside India but
hundreds of kilometres from their own district. Distances are orderly to the
95th percentile (97 km) and then jump to 2,230 km — further than Rajasthan is
wide. Anything over 200 km is treated as a bad coordinate rather than a remote
facility: the district's median PHC distance is substituted and the row is
marked `lead_time_is_estimated`. Four of the 200 forecast facilities.

---

## 12a. Therapeutic substitution — ATC LEVEL 4

Substitution matches on the **first five characters** of the ATC code (level 4,
chemical subgroup), not four.

Level 3 was wrong and the live output proved it: it paired Zinc Sulphate
(`A12CB01`) with Magnesium sulphate (`A12CC02`), because ATC level 3 `A12C` is
"other mineral supplements" — a heterogeneous bucket, not a therapeutic class.
Offering magnesium to a facility short of zinc is not a substitution.

At level 4 the substitutions that survive are genuine: Artemether-Lumefantrine
against Artesunate-Sulphadoxine-Pyrimethamine, Chloroquine against Primaquine —
all antimalarials. Both the requested and the supplied item are always shown,
and the UI states that clinical suitability must be confirmed before dispensing.

---

## 12. VEN classification — DERIVED, NOT PUBLISHED

Vital / Essential / Desirable per WHO and MoHFW practice: **109 Vital, 249
Essential, 27 Desirable**. NLEM does not publish VEN, so **this classification
is ours**. It is an NLEM-section default with per-medicine overrides, both
listed in `ingestion/build_items.py`. Alert priority is
`ven_weight x shortfall`, so a vital medicine outranks a desirable one at equal
days of cover.

---

## 13. Reporting consistency — REAL MEASUREMENT OVER GENERATED BEHAVIOUR

Share of expected stock counts that actually arrived in the last 90 days
(three 30-day periods). Computed from the ledger by
`ingestion/build_facility_metrics.py`: a facility that did not report has no
`count` events, and the absence *is* the measurement.

The reporting behaviour underneath is generated. Each facility gets a baseline
compliance probability (0.72–0.99) and a per-period decay (0–5.5pp), because
evaluations of comparable systems — South Africa's Stock Visibility System
among them — document compliance decaying a few months after rollout rather
than holding steady.

Result across the 200 forecast facilities: **35 complete, 139 partial, 26
silent; mean 52%**.

---

## 14. Waste and FEFO — MEASURED COUNTERFACTUAL

`stock_events` carries `expired` write-offs: stock that reached its expiry date
unused. A facility that has run out cannot dispense, and expired stock cannot
be dispensed either — an earlier version of the generator had no expiry step,
so short-dated stock was quietly handed to patients after its expiry date,
which made waste invisible.

Batch shelf life at receipt: **81%** at 12–24 months, **15%** short-dated at
2–5 months, **4% "dumped"** at 25–60 days — what district warehouses do when
clearing their own near-expiry stock downward.

**Waste avoided by FEFO is measured, not estimated.** The same year's ledger is
replayed issuing first-in-first-out instead of first-expiry-first-out and the
write-offs are differenced:

| | Units |
|---|---|
| Expired under FEFO (actual) | 32,893 |
| Expired under FIFO (counterfactual) | 59,505 |
| **Avoided by FEFO** | **26,612 (44.7%)** |

Stored in `daysupply.impact_metrics`, served at `/api/v1/impact`.

> **These figures superseded an earlier set (72,408 / 166,950 / 94,542 at 57%)
> and the earlier ones must not be quoted.** They were correct for the ledger as
> it stood at Block C. The Block D+ driver corrections — malaria moving from
> blood smears to confirmed cases, "childhood diseases" splitting into four real
> drivers, six flat-baseline items gaining drivers — changed the demand series,
> and `generate_usage.py` regenerated the whole ledger against them. Different
> demand produces different expiry under both policies. The current numbers are
> what `daysupply.impact_metrics` holds today; anything else is stale.

**Per-transfer `waste_avoided_units` is currently 0, and that is honest.** FEFO
at the facility has already consumed everything short-dated, so every batch a
transfer would move has 500+ days of life. The metric is computed correctly and
will report a real figure when a donor holds stock it cannot consume in time;
it is not padded to look better.

---

## 15. What is real, after Block C

| Component | Status |
|---|---|
| Facilities, geography | **Real** — 200,438 rows, 37 states, 668 districts |
| HMIS seasonality | **Real** — 5 states, 137 districts, 18,084 rows |
| Item catalogue | **Real** — all 385 NLEM 2022 medicines |
| ATC codes | **Real where assigned** — 264 of 385, null never guessed |
| VEN classification | **Derived** — ours, not MoHFW's (§12) |
| Forecasts | **Real** — BigQuery ML ARIMA_PLUS, 2,794 series |
| Reorder points, safety stock | **Computed** from forecast, observed variance, lead time |
| Lead time | **Real distance, assumed conversion** (§11) |
| Alerts, transfers, substitutes | **Computed** — no fabricated path remains |
| Reporting consistency | **Measured** over generated reporting behaviour (§13) |
| Waste avoided | **Measured counterfactual** (§14) |
| Daily stock events | **Generated** from real anchors (§9) |
| `captures_today` | **Generated** — the only one left, and flagged in the API |

---

## 16. Demand driver corrections

The 11 indicators originally parsed were selected by matching words in the HMIS
label. The full file carries **368 distinct data items**; parsing all of them
revealed that substring matching had been quietly wrong in three places, and
that three items marked "no driver available" had exact indicators sitting
unparsed. Drivers are now defined by **item code** in
`ingestion/hmis_drivers.py`, and every item assignment carries a clinical
rationale in `ingestion/build_items.py`.

### 16.1 Malaria — the driver was 99.8% testing effort

The worst of the three, and it affected four **Vital** medicines.

`Malaria` matched any label containing the word. In Maharashtra that summed:

| Code | Item | Annual |
|---|---|---|
| 11.1.1.a | Total Blood Smears Examined for Malaria | 14,525,963 |
| 11.1.2.a | RDT conducted for Malaria | 1,087,554 |
| 11.1.1.b/c, 11.1.2.b/c | **Confirmed positives** | **24,831** |
| 10.10, 14.4.1, 16.8.1/2 | Childhood, inpatient, deaths | 12,220 |

**Confirmed cases were 0.16% of the total.** Antimalarial demand was being
forecast from how many blood smears a district collected — a function of
surveillance campaigns, not of disease. Substring matching cannot distinguish
"Total Blood Smears Examined for Malaria" from "Malaria (RDT) test positive".

Correcting it changes the answer, not just the provenance:

| Series | Apr | Jun | Aug | Sep | Dec | Feb | Amplitude |
|---|---|---|---|---|---|---|---|
| Old (tests-dominated) | 0.79 | 0.86 | 1.25 | 1.23 | 0.97 | 0.90 | **1.6x** |
| New (confirmed cases) | 0.53 | 0.91 | 1.72 | 1.90 | 0.76 | 0.55 | **4.52x** |

Monsoon antimalarial demand was understated roughly threefold.

**Species split: clinically ideal, rejected on data density.** India's NVBDCP
protocol is chloroquine plus 14-day primaquine for *P. vivax* and artemisinin
combination therapy for *P. falciparum*, so splitting the driver by species
would be more correct still. It was tested and rejected: *P. falciparum*
positives are **69-76% zero cells** at district-month level (6,833 cases across
35 districts x 12 months), and the resulting index carried a 4.25x January
spike that is small-number noise rather than seasonality. All four antimalarials
therefore share **combined confirmed positives**, and the species split is
carried in the per-item consumption rates instead — chloroquine is dosed for the
~71% of cases that are vivax, the ACTs for the ~29% that are falciparum.

### 16.2 "Childhood Diseases" was fourteen conditions in one number

`Childhood Diseases` summed 10.1-10.14: pneumonia, asthma, sepsis, diphtheria,
pertussis, tetanus, TB, AFP, measles, malaria, diarrhoea, dysentery, URI and
severe acute malnutrition. Four medicines shared it, none of which treats more
than one of those conditions.

| Item | Was | Now | Why |
|---|---|---|---|
| ORS, Zinc Sulphate | Childhood Diseases | 10.11 + 10.12 **diarrhoea** | Diarrhoea is the sole indication for both under the WHO/MoHFW protocol |
| Amoxicillin | Childhood Diseases | 10.1 + 10.13 **pneumonia and URI** | WHO first-line for childhood pneumonia |
| Vitamin A | Childhood Diseases | 9.8.1-9.8.3 **doses administered** | Counts the doses actually given; supplementation follows the immunisation calendar, not disease |
| Albendazole | Childhood Diseases | 9.10 **children dewormed** | Counts the doses actually given; deworming is a campaign |

The aggregate hid genuinely opposite seasonality. Diarrhoea peaks in the
pre-monsoon (Jul 1.41); pneumonia and URI peak in the cool months (Sep-Jan,
1.05-1.23). Averaging them produced a flat 1.4x curve that matched neither.

**Albendazole is the clearest case.** Against the aggregate it looked flat.
Against doses actually administered it has an amplitude of **22.64x**, with a
**5.66x spike in August** — National Deworming Day, which India runs on
10 August and 10 February. That is a real, planned, forecastable procurement
event that the old driver made invisible.

### 16.3 "Inpatient counts" summed admissions, deaths and bed-days

`Inpatient counts` matched anything containing "inpatient", which mixed
admissions (14.3.x), disease-specific admissions (14.4.x, double-counting the
same patients), inpatient deaths (14.9.x) and childhood diarrhoea inpatients.
Deaths are an outcome, not an admission, and adding them to admissions is not a
quantity that means anything.

| Item | Was | Now | Why |
|---|---|---|---|
| Ringer lactate, Sodium chloride | Inpatient counts | 14.3.1.a/b + 14.3.2.a/b **total admissions** | IV fluid use scales with bed occupancy regardless of diagnosis |
| Ceftriaxone | Inpatient counts | 14.4.1-14.4.8 **infectious admissions** | Empirical IV antibiotics go to infectious admissions, not the whole ward |

Splitting them matters: total admissions is nearly flat at 1.3x, while
infectious admissions swing 2.5x with a monsoon peak (Aug 1.49). Ceftriaxone
demand follows the second, not the first.

### 16.4 Three items had exact indicators that were never parsed

Block B recorded these as having "no plausible HMIS driver" and gave them a
flat seasonal baseline. That conclusion was drawn from the 11 selected
indicators, not from the file.

| Item | Was | Now | Amplitude |
|---|---|---|---|
| Paracetamol, Ibuprofen | flat baseline | 14.2.1 **Allopathic outpatient attendance** | 1.5x |
| Ferrous Salt + Folic acid | flat baseline | 1.2.4 **PW given the 180-tablet IFA course** | 1.1x |
| Oxytocin | flat baseline | 2.2 **Institutional deliveries** | 1.2x |
| Magnesium sulphate | flat baseline | 1.3.2 **Eclampsia cases managed** | 1.2x |
| Salbutamol | flat baseline | 10.2 + 14.4.4 **asthma and COPD** | 1.5x |

`14.2.1 Allopathic — Outpatient attendance` is a total-OPD count of 105 million
attendances in Maharashtra alone. The Block B note that "HMIS publishes no
total-OPD indicator, only disease-specific columns" was wrong.

**Magnesium sulphate is the clearest instance of choosing indication over
convenience.** Deliveries (2.2) would have been the obvious driver and is what
was first proposed. Magnesium sulphate treats eclampsia, not delivery: there
are 1,787,203 institutional deliveries in Maharashtra against 5,482 eclampsia
cases, so deliveries would have overstated demand roughly **300-fold**. The
narrower indicator is right even though it is a much smaller and noisier series.

**Ferrous Salt + Folic acid** now has the most direct relationship in the
catalogue: indicator 1.2.4 counts women given the full 180-tablet course, so
the driver counts the drug itself rather than a proxy for it.

### 16.5 Two marginal additions

Aspirin, glyceryl trinitrate and atorvastatin now also count acute cardiac
emergencies (14.6.5) alongside cardiac outpatients; clopidogrel also counts
cerebrovascular emergencies (14.6.7). Both drug groups are started in either
setting.

### 16.6 What is deliberately excluded, and why

Recorded so each exclusion is a decision on the record rather than an omission
(`DELIBERATE_EXCLUSIONS` in `ingestion/hmis_drivers.py`):

| Code | Excluded from | Because |
|---|---|---|
| 11.1.1.a, 11.1.2.a | Malaria | Testing effort, not cases |
| 14.9.1, 14.9.2 | Inpatient admissions | Deaths are an outcome, not an admission |
| 16.8.1, 16.8.2 | Malaria | Deaths are an outcome, not a case |
| 14.10 | Inpatient admissions | Bed-days; would double-count against admissions |
| 14.2.2 | Outpatient attendance | AYUSH is not served by the allopathic essential-medicines supply chain |

### 16.7 Consumption rates replaced the even split

The old generator split a driver's patients evenly between the items sharing it
and multiplied by a per-unit-type constant. That could not survive a total-OPD
driver: 105 million attendances and 5,482 eclampsia cases cannot be treated
alike. Each item now carries `units_per_driver_event` — how much of it one unit
of its driver consumes — combining the clinical course with the share of that
driver's patients who receive that particular drug. Every value and its
reasoning is in `FORECAST_DRIVERS` in `ingestion/build_items.py`.

A second assumption is separated out: `PHC_SHARE` in
`ingestion/hmis_drivers.py` records how much of a district's activity for each
driver actually flows through a PHC, since sub-centres do much of antenatal
care and district hospitals take most admissions. Keeping it separate means the
consumption rates stay clinically pure — 180 tablets is a course, not a blend.

### 16.8 Consequences

**The training threshold moved.** Correct drivers produce lower and more
realistic volumes: a PHC uses about seventeen ampoules of oxytocin a month, not
one a day. At the old 300-day threshold — calibrated when coarse aggregates
inflated volumes — only 1,421 series qualified and the Vital antimalarials
dropped out entirely. The threshold is now **180 days**, half the year showing
dispensing activity, giving **2,794 series**, 56% of the 5,000-series ceiling.

**Thirteen districts now generate no demand for a driver at all**, because they
reported zero for it in every month of the year — ten for confirmed malaria,
three for eclampsia. Those facility-item pairs produce no events and are not
forecast. That is the honest outcome of a narrow driver, not an error: a
district with no confirmed malaria has no antimalarial demand.

**Therapeutic substitution is now structurally limited.** At ATC level 4, only
one class — P01BA, chloroquine and primaquine — contains more than one forecast
item, so substitution has almost nothing to match on within the forecast subset.
The logic is implemented and correct; it simply fires rarely. Widening to ATC
level 3 would create matches, but that is exactly the change that paired zinc
with magnesium sulphate (§12a), so it stays at level 4.

---

## 17. Beds and personnel — the multi-resource dimension

`stock_events` became `resource_events` with a `resource_type` of `medicine`,
`bed` or `personnel`. Medicines are unchanged: every existing row became
`resource_type = 'medicine'`, a view named `stock_events` still serves exactly
what it served before, and the migration refused to finish until row counts,
quantity totals, facility counts and event types all matched on both sides.

Medicines remain the deep vertical. Beds and personnel ride the same table, the
same capture pipeline and the same redistribution shape — they are a dimension,
not a second product.

### 17.1 Bed capacity — REAL, the government's own norm

| | |
|---|---|
| Source | `Data/India/03_PHC_IPHS_Guidelines-2022.pdf`, pages 46-47 |
| Provenance | Indian Public Health Standards 2022, Volume III |

Quoted verbatim from page 46:

> "There should be two essential and four desirable beds in a PHC while six
> essential and four desirable beds [at 24x7 PHCs]"

and from the table on page 47: *2 Beds | 4 Beds | 2 Day care Beds | 6 Beds |
4 Beds*, with the note *"The desirable will be over and above the essential
beds."*

| Facility type | Essential | Desirable | Total |
|---|---|---|---|
| Rural PHC | 2 | 4 | 6 |
| Urban PHC | 2 day-care | 4 day-care | 6 day-care |
| 24x7 PHC | 6 | 4 | 10 |

This is **not an estimate**. It is the published standard applied to real
facilities using the facility master's own rural/urban flag: **29,733 PHCs,
178,398 beds, of which 148,554 are overnight** and 29,844 are day-care in
4,974 urban PHCs.

**Which PHCs run 24x7 is an explicit unknown.** Nothing in the facility master
records it and nothing else in the data implies it. Every PHC therefore carries
the standard 2+4 norm and `is_24x7` is left NULL. Applying the 6+4 norm to a
facility that does not run 24x7 would overstate its capacity threefold, and
there is no basis to choose. A test asserts `is_24x7` is never populated, so
this cannot be quietly filled in later.

`location_type` had to be backfilled: the original loader dropped the source
file's `Location Type` column. Two of the 200,438 rows carry `Public` in that
column — a value belonging to *Type Of Facility* that has leaked across — and
are left unclassified rather than assigned a location.

### 17.2 Bed occupancy — GENERATED, anchored to real admissions

Occupancy is generated and disclosed exactly as medicine consumption is. It is
driven by the district's real HMIS `Inpatient admissions - total` volume
(codes 14.3.1.a/b, 14.3.2.a/b), divided by the real number of PHCs and scaled by
the same `PHC_SHARE` assumption, converted to beds occupied by an assumed
average length of stay of 1.8 days. Urban day-care beds turn over three times a
day and are never counted as occupied overnight.

Occupancy is then **capped at capacity** — a PHC with six beds cannot have seven
occupied — and demand above capacity becomes a `turned_away` event. That is the
referral signal: **2,430 patients turned away across the year**, 392 in the last
30 days, at 45 of 200 facilities. Mean occupancy is 30.5%.

### 17.3 Personnel — establishment and vacancy REAL, attendance GENERATED

| | |
|---|---|
| Source | Rural Health Statistics 2017, `Data/India/*_2017.csv` |
| Loaded by | `ingestion/load_staffing.py` → `daysupply.staffing` |
| Coverage | 5 cadres x 36 states = 180 rows |

Every file carries Required, Sanctioned, In Position, Vacant and Shortfall.
The vacancy rates are real, and they are the point — a vacant post cannot be
attended, so vacancy sets the ceiling on attendance before any behaviour is
modelled:

| Cadre | Sanctioned | In position | Vacancy |
|---|---|---|---|
| Doctor (allopathic), PHC | 33,968 | 27,124 | **20.1%** |
| Nursing staff, PHC+CHC | 77,956 | 70,738 | 9.3% |
| Pharmacist, PHC+CHC | 29,315 | 25,193 | 14.1% |
| Health assistant (male), PHC | 22,753 | 12,288 | **46.0%** |
| Health assistant (female), PHC | 21,748 | 14,267 | **34.4%** |

Pharmacists are the case the pitch already cites: sanctioned strength (29,315)
is *below* required (31,274), so even a fully staffed network is short.

**The denominator differs by cadre.** `allo-doc-PHCS` and the two
`assistant-*-PHCS` files count PHC posts and divide by PHCs;
`nursing-staff-PHCS-CHCS` and `pharmacists-PHCS-CHCS` cover PHCs **and** CHCs
and divide by both. Dividing the latter two by PHCs alone would overstate
per-PHC nursing and pharmacist strength by roughly 18%.

**Granularity is state-level, exactly like `population_served`.** Per-facility
sanctioned strength is a state x cadre average and is an assumption, not a
measurement.

**36 state-cadre rows report more staff in post than sanctioned posts** —
contractual NHM staff over and above sanctioned strength, across all five
cadres. Those are kept as reported rather than clipped. A related defect was
caught by a test: rounding the sanctioned and in-position ratios independently
can invert their order (1.4 sanctioned rounds to 1 while 1.6 in position rounds
to 2), which claimed staff for posts that do not exist. Attendance is now capped
at the establishment except where the source itself reports over-establishment.

**Vintage.** This is the 2017 edition. MoHFW now publishes the same series as
*Health Dynamics of India (Infrastructure and Human Resources)*. The 2017 data
is internally consistent and adequate for a vacancy baseline; it should be
refreshed before any real deployment, and `source_year` is carried on every row
so nothing can quote it as current.

**Attendance is generated:** a fixed-seed per-facility propensity, lower on
Sundays, with occasional multi-day absences for leave, training and deputation.
Network attendance runs at 56% of sanctioned posts — the product of real vacancy
and generated presence.

### 17.4 One nurse per six beds — the cross-resource link

CHC IPHS 2022, page 60:

> "As per the Indian Nursing Council (INC) regulations, there should be one
> nurse for every six beds in the [inpatient department]"

tabulated on page 118 as *Staff Nurses — Nurse:Bed ratio — IPD 1:6*.

**Attribution matters here.** This is an **Indian Nursing Council regulation**.
CHC IPHS 2022 quotes and tabulates it, but IPHS cites the INC rather than
originating the norm. It should be attributed to the INC everywhere it appears,
including in the deck and the video.

This makes a facility's nursing requirement a function of its bed capacity,
which is the cross-resource logic the brief asks for. It is a *different*
quantity from sanctioned strength: the bed-derived requirement is 1.0 nurse per
PHC, the sanctioned establishment averages 2.45. Both are carried, and no
forecast facility is sanctioned below the bed-based norm.

### 17.5 What each resource does when it is short

The three resources behave differently and produce different outputs:

| Resource | Shortage produces | Why |
|---|---|---|
| Medicine | **Transfer** between facilities | Stock moves |
| Bed | **Referral route** | A bed cannot be moved to a patient in useful time |
| Personnel | **Reallocation** of a person | Staff move, but as people |

Bed referrals: 24 facilities need one, 35 routes found, mean 33 km.

**Staff reallocation currently returns nothing, and that is the honest answer.**
Two things prevent it, both real:

1. **Four of the five cadres are sanctioned one post per PHC.** No facility can
   donate its only doctor, pharmacist or health assistant. Those vacancies need
   recruitment, not redistribution — reallocation is structurally the wrong
   instrument for them.
2. **The forecast facilities are deliberately far apart.** They were chosen to
   span 116 districts for geographic reach, so the nearest nursing-short and
   nursing-adequate pair is **1,218 km** apart against a 60 km limit.

The engine is correct and the API returns the reason rather than an empty list.
A district-dense deployment would produce candidates; this facility set cannot.

### 17.6 Beds and personnel are not ARIMA-forecast

Adding 200 bed series and 1,000 personnel series would take the trained model
from 2,794 to roughly 3,994 of the 5,000-series ceiling, for two quantities that
are bounded small integers — a PHC has six beds and about one doctor. A time
series model adds nothing over an occupancy rate and an attendance rate, and it
would spend most of the remaining headroom. **Medicines keep ARIMA; beds and
personnel use rule-based statistics.** The series count is unchanged at 2,794.

---

## 18. Surge detection and emergency early warning

### 18.1 A surge is a departure from the *pooled* pattern, not from flat

Section 16 established that the transferable signal between districts is a
twelve-number seasonal vector per ATC class, and that the **pooled** vector —
the mean across all districts — beats both a flat baseline and a demographically
matched donor. That vector is therefore the network's best available statement
of what a normal month looks like, and a surge is a month that departs from it:

```
expected(district, class, month) = baseline(district, class)
                                 × pooled_multiplier(class, month)
residual                         = observed − expected
```

`baseline` is the district's **own** twelve-month mean, so the expectation is
already scaled to how much malaria that district actually has. The pooled vector
contributes only the *shape* of the year. A surge is then "more than this
district's own level, seasonally adjusted, can explain" — which is a materially
harder test than "more than average", and it is the reason a monsoon peak in a
malaria-endemic district does not trip the alarm every July.

### 18.2 Why the obvious statistic does not work

The natural choice is a standardised residual and a three-sigma rule:

```
z_classical = (r − mean(r)) / stddev(r)
```

**It cannot work here, and the reason is arithmetic rather than clinical.**
Every series is exactly twelve monthly observations, and for a sample of size
*n* the largest attainable standardised residual is bounded:

```
z_max = (n − 1) / √n = 11 / √12 = 3.175
```

A single extreme month inflates the very standard deviation it is measured
against. Measured across all 58,932 series-months in this data, the observed
maximum is **3.17** — pinned to its own ceiling. A genuine 12× outbreak and a
mild 4× bump score identically, and a "3-sigma" threshold sits within 0.07 of
being unattainable. That is not a threshold, it is a ceiling. `z_classical` is
carried on every row for transparency and is shown in the UI, but it is not what
fires.

> An early version of the module divided the raw residual by its standard
> deviation *without centring it on the residual mean first*. That is not a
> standardised residual and is not bounded — it produced a maximum of 3.45. The
> ceiling assertion in `build_surge_signals.py` caught it, and the assertion
> stays in the build.

### 18.3 What actually fires: the modified z-score

Iglewicz & Hoaglin, *How to Detect and Handle Outliers*, ASQC Basic References
in Quality Control Volume 16, 1993, section 4.4. Median and median absolute
deviation replace mean and standard deviation:

```
MAD        = median(|r − median(r)|)
modified_z = 0.6745 × (r − median(r)) / MAD
```

The median and MAD are unaffected by the outlier under test, so the statistic is
unbounded and a 12× month scores far above a 4× month. The 0.6745 factor is the
0.75 quantile of the standard normal, which makes MAD a consistent estimator of
σ for normally distributed data, so the score reads on a familiar scale.
Iglewicz and Hoaglin recommend **3.5** as the cut and that is the default here.
Observed maximum in this data: **166.7**, against the classical statistic's 3.17.

### 18.4 Three conditions, not one

A statistical test alone flags a district that went from three cases to twelve.
That is a large modified z and clinically nothing. A month is a surge only if it
clears all three:

| Condition | Default | Env var | Why |
|---|---|---|---|
| `modified_z ≥ 3.5` | 3.5 | `SURGE_Z` | Iglewicz–Hoaglin; the statistical test |
| `observed / expected ≥ 1.5` | 1.5 | `SURGE_MIN_RATIO` | materially more, not a rounding artefact |
| `observed ≥ 100` | 100 | `SURGE_MIN_ABSOLUTE` | enough events to be worth acting on |

All three are recorded per row (`passes_statistic`, `passes_ratio`,
`passes_magnitude`) so a reviewer can see which condition excluded a near miss.
Where MAD is zero the modified z is undefined; those rows are excluded and
counted, never silently passed.

**Result: 1,295 surges from 58,932 series-months (2.2%).** 2,406 passed the
statistic; 355 were rejected on ratio and 756 on magnitude. The median
district-month for confirmed malaria is **3 cases**, which is precisely what the
magnitude floor is there to keep out.

### 18.5 Worked example — real HMIS, not a synthesised spike

**Brihan Mumbai, antimalarials (P01BA), January.**

| | |
|---|---|
| Observed confirmed malaria | **2,345** |
| District's own 12-month baseline | 1,400.5 |
| Pooled January multiplier | 0.7053 |
| Expected (1,400.5 × 0.7053) | **987.8** |
| Surge multiplier | **2.37×** |
| Modified z | **6.54** (fires at 3.5) |
| Classical z | **2.58** — *a 3-sigma rule misses it entirely* |

Note which way the pooled vector points. January is a **below-average** month
for antimalarials nationally — 0.71× — because the monsoon transmission season
is over. The seasonal model expected Brihan Mumbai to be *quiet*, and it
recorded more than twice what its own annual level would give even before the
seasonal discount. Against a flat district average the month is 1.67×,
unremarkable; against the pooled seasonal expectation it is 2.37×. That gap is
the entire argument for measuring surge against the pooled vector rather than
against a mean.

The rest of Brihan Mumbai's year sits between 0.26× and 1.16× of expectation.
January is the one month that does not, and the modified z separates it cleanly
while the classical statistic does not reach its own threshold.

**The counter-example matters as much.** **Gadchiroli** — a malaria-endemic
tribal district in eastern Maharashtra — hits 2.22×, 2.34× and 3.03× in
January, February and December, and is **never flagged**. Its malaria season is
winter-peaking against a monsoon-shaped pooled vector, so its residuals are
large all year and its MAD is large with them. A detector that called that
district "surging" every month would be measuring the mismatch between its
season and the pooled one, not an outbreak. Both behaviours are pinned by tests.

### 18.6 Surge changes the supply answer

The surge multiplier is run back through the **same** reorder-point formula the
steady-state plan uses, so the two are comparable line by line:

```
μ_surge = avg_daily_demand × m
σ_surge = demand_std_dev  × m
reorder_point_surge = μ_surge × L + 1.65 × σ_surge × √L
```

**Scaling σ proportionally is an assumption, and it is the conservative one.**
Poisson arrivals would give σ ∝ √m and a smaller safety stock; outbreak arrivals
are overdispersed and clustered rather than Poisson, so variability grows at
least as fast as the level. Proportional scaling errs towards holding more
stock. The Poisson alternative is available as `SURGE_SIGMA_EXPONENT=0.5`.

| Under detected surge | |
|---|---|
| Facility-items needing reorder, steady state | 100 |
| Facility-items needing reorder, under surge | **198** |
| **Newly** at risk — were fine before | **98** |
| Total shortfall | 20,623 units |

### 18.7 Lead time is what decides the answer

A reorder point tells a facility to order. Whether ordering *helps* is a
different question, and under surge it is the binding one:

```
days_to_stockout = on_hand / μ_surge
lead_time_decisive = days_to_stockout < lead_time_days
```

If a facility runs out **before an indent can physically arrive**, reordering is
still correct but cannot be the answer for this episode. Only stock already
inside the district reaches it in time. **145 of 322 facility-items are in that
position**, and the UI is required to say *"Transfer only — an indent cannot
arrive in time"* rather than showing an order quantity and implying the problem
is handled.

The gradient is monotonic in lead time, which is the claim the whole design
rests on:

| Lead time | Can only be served laterally |
|---|---|
| 6–10 days | 107 of 246 (**43.5%**) |
| 11–15 days | 34 of 71 (**47.9%**) |
| Over 15 days | 4 of 5 (**80.0%**) |

**The case worth showing.** Shivaji Nagar Health Post holds 27 units of
primaquine — 12.4 days of cover, comfortably `ok` at steady state. Under the
2.37× January surge that becomes **5.2 days against an 8-day lead time**, and
the status flips from `ok` straight to `transfer_only`. Nothing about the
facility changed; the demand did, and the lead time did the rest.

### 18.8 Surge redistribution differs in three deliberate ways

| | Steady state | Under surge |
|---|---|---|
| Transfer radius | 150 km | **300 km** (`SURGE_TRANSFER_MAX_KM`) |
| Donor stock | ranked per receiver | **allocated cumulatively, Vital first** |
| Donor protection | steady reorder point | **its own surge reorder point** |

1. **The radius widens.** At steady state a 150 km transfer is hard to justify
   against waiting for the next indent. For a facility that will stock out
   before an indent can arrive, a longer journey is the only option that exists.
2. **Vital claims stock first.** A donor's spare stock is finite. The
   steady-state engine ranks candidates per receiver and can promise the same
   units to several of them; under scarcity that is not acceptable. Claims are
   accumulated in VEN order and cut off when the donor is exhausted.
3. **The donor is protected against its own surge**, so the engine cannot strip
   a facility that is about to need the stock itself.

**Result: 101 transfers, 60 receivers, 50 donors, 5,881 units.** 68 are cases
where transfer is the *only* option. **29 are rationed by donor capacity** — the
priority order is doing real work, not decorating the output.

**Widening the radius unlocked only 2 additional transfers.** That is a modest
result and it is reported as one. The radius is not where the value is; the
priority ordering and the lead-time test are.

> **Alternative episodes, not a plan.** `surge_recommendations` holds a row for
> every detected surge month. Those months are *alternatives* — a donor's spare
> stock is one current position. Committing it in January and again in June is
> coherent; summing across all twelve months would promise the same units twelve
> times. Every read is therefore scoped to a single surge month, defaulting to
> the month the live stock sits in, and a test asserts the default read never
> spans more than one.

### 18.9 Network absorption

The facility question is "does this PHC hold". The district question — the one a
district programme officer actually asks — is "does the district hold":

```
absorption_days = district_on_hand / (district_daily_demand × k)
absorbs         = absorption_days ≥ slowest facility lead time in the district
```

Stock is deliberately pooled across the district, because lateral transfer is
what makes pooled stock reachable. This is the capacity redistribution unlocks.

`absorption_days` is rounded to a tenth of a day for display, and **`absorbs`
and `units_short` are both derived from that rounded figure**. A verdict that
contradicts the number printed beside it is worse than a rounding error, and a
district can never be reported as absorbing the spike and short of stock at the
same time. Two tests pin this.

| Spike | District-classes that hold | Units short |
|---|---|---|
| 2× | 974 of 1,652 (**59.0%**) | 66,198 |
| 3× | 498 of 1,652 (**30.1%**) | 208,129 |
| 5× | 71 of 1,652 (**4.3%**) | 696,902 |

**Worked district: Brihan Mumbai, antimalarials.** 110 units on hand, 15.95
units/day of demand, slowest lead time 8 days. It absorbs a spike of at most
**0.86×**.

**That figure is a finding about the network, not a defect in the model, and it
must not be read as one.** A `max_multiplier_absorbed` below 1.0 means the
district's pooled stock does not cover even its *normal* demand across its own
lead time — which is true **before any surge is applied**. The scenario did not
produce it; the scenario revealed it. It is arithmetic over a real stock
position (110 units) and a real forecast demand (15.95 units/day) across a real
distance-derived lead time (8 days), and every one of those three numbers is
computed elsewhere in this document.

A district in that state is running on the assumption that resupply is
reliable and continuous. When it is, nothing visibly breaks. When it is not —
which is what resilience means — there is no buffer at all, and no amount of
forecasting improves it. The honest reading is that antimalarial stock in this
district is thin against its own lead time, and the model is doing its job by
saying so rather than smoothing it away.

`run_scenario()` returns `structurally_thin` and a `structurally_thin_note`
alongside the verdict, and the UI renders it under the heading *"A finding
about the network, not the model"*, so the distinction survives into the
demo rather than living only here.

### 18.10 Scenario mode is computed, not replayed

Scenario mode takes a district, an ATC class and **any** multiplier between 1
and 20, and evaluates the reorder point, each facility's day of stockout,
whether an indent can beat it, which transfers are recommended and whether the
district holds — live, against current stock, using the same formula as the
steady-state plan. It does **not** read the precomputed 2×/3×/5× rows. The UI
control is a continuous slider rather than three buttons, which is the honest
affordance for something that really does recompute.

The degradation is the point. Brihan Mumbai, antimalarials:

| | 2× | 3× |
|---|---|---|
| Facility-items failing | 3 of 4 | **4 of 4** |
| Cannot be resupplied in time | 3 | 3 |
| First stockout | 0.4 days | 0.2 days |
| District cover vs 8-day lead time | 3.4 days | 2.3 days |
| **Transfers available** | **2** | **0** |

At 2× the district can partly help itself: two 10 km transfers from Shivaji
Nagar to Hari Nagar Dispensary. At 3× the donor needs its own stock and there is
**no donor left** — the answer changes from "move stock within the district" to
"this needs stock from outside the district", and the API says so in those
words. That transition is not scripted; it falls out of the arithmetic.

### 18.11 Cost and scale

No new ARIMA series. Surge detection is arithmetic over the existing
`pattern_vectors` table, and the supply consequence is arithmetic over the
existing `reorder_status` table. **The trained model stays at 2,794 series of
the 5,000 ceiling (55.9%)**, unchanged from Part 1. Scenario mode is scoped to
one district and one ATC class per request — a few dozen rows — and goes through
the same `app.bq` guard rails as every other query.

---

## 19. Population reach — counted once

Impact has to be a number and the number has to survive being checked.

### 19.1 The trap: catchments are nested, not additive

`population_served` comes from Rural Health Statistics 2017, which publishes,
per State/UT, the *average rural population covered by* a sub-centre, a PHC and
a CHC. **Those three catchments cover the same people.** A villager is served by
a sub-centre, which reports to a PHC, which refers to a CHC.

Summing `population_served` across all 200,365 Indian facilities gives
**2,920,003,021 — 3.50× the rural population of India.** That figure is recorded
here so the discarded number is on the record rather than merely avoided. It is
not used anywhere.

**Only rural PHCs are counted.** PHC catchments tile the rural population once,
and the PHC is the level this system operates at.

### 19.2 The tiling check — the reason to believe the method

Summing the PHC catchment across all 24,759 rural PHCs gives **793,668,945**
against a Census 2011 rural population of **833,748,852** — **95.2%**.

That is what a correct once-only tiling should look like: close to the whole
rural population, slightly under because state averages times state counts do
not perfectly reproduce a national total. Had it come out at two or three times
the rural population, the method would have been wrong. `build_population_reach.py`
**fails the build** if the ratio leaves [0.80, 1.05], and a test asserts the same.

### 19.3 The figure, at three scopes

| Scope | Rural PHCs | Districts | States | Population |
|---|---|---|---|---|
| **Operating** — live forecasts, stock positions, transfer recommendations | 168 | 101 | 4 | **4.8 million** |
| **Demand-data footprint** — districts where real HMIS demand is loaded and seasonality is measured | 5,239 | 105 | 5 | **151.7 million** |
| **National directory** — every rural PHC already loaded | 24,759 | 686 | 37 | **793.7 million** |

The honest headline is the middle row: **151.7 million people across 105
districts in 5 states**, the footprint where the demand model is grounded in real
government data. The first row is what is running today. The third is the
addressable network, and it is addressable rather than achieved.

### 19.4 What is counted, what is assumed, what is excluded

**Counted, from published sources:** which facilities exist, where, and of what
type (national facility directory, 200,438 rows); the average rural population
covered by a PHC in each State/UT (RHS 2017, Census 2011 base); which districts
have real demand data (five HMIS 2019-20 state files).

**Assumed:** that each PHC serves its state's average. **There is no published
per-facility catchment anywhere in India**, so a state × facility-type average is
the finest granularity that exists. Real catchments vary widely within a state;
the total is sound, any individual facility's figure is an average. This is the
same limitation already disclosed for `population_served` in section 4.

**Excluded, deliberately:**

* **Urban PHCs (4,974).** The RHS figure is an average *rural* population;
  applying it to urban PHCs would be a category error. They contribute **zero**.
  This makes the number smaller and it is the correct treatment — 32 of the 200
  operating facilities are urban and are not counted.
* **Sub-centres (163,131), CHCs (5,389), district and state hospitals (2,185)** —
  nested catchments.

**Direction of error.** The population base is Census 2011, now fifteen years
old, and India's rural population has grown since. **These figures understate
current reach.** Nothing is rounded up and no growth factor has been applied.

### 19.5 What "meaningfully" means

Reach is not the same as impact, and a population count on its own says nothing
about whether anything improved. The measured claims attached to that population,
each from elsewhere in this document:

* **26,612 units of waste avoided** through FEFO batch attribution against a
  measured FIFO counterfactual (section 14) — not modelled, ledger-walked.
* **Reorder points that are each facility's own**, from its own lead time and
  demand variability, rather than a flat 14-day rule (section 11).
* **98 facility-items that a surge moves from safe to at risk**, and 145 where
  ordering physically cannot work in time (section 18.6–18.7).

MoHFW's own finding that a PHC serves **36,049 people on average against a
20–30,000 norm** is the context for all of it: these are facilities already
carrying more population than the standard assumes.
