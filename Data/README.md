# Data provenance and methodology

This file records where every number in StockPulse comes from, and — more
importantly — which numbers are measured and which are derived or generated.
Read it before quoting any figure from this system.

Scope note: the project is **India-only**. `Data/Brazil/` remains on disk from an
earlier cross-border framing but is not loaded and not built against.

---

## 1. Facility master — REAL, fully loaded

| | |
|---|---|
| Source | `Data/India/geocode_health_centre.csv` |
| Provenance | NHM / MoHFW health-centre directory (via Kaggle, "All India Health Centres Directory") |
| Rows | **200,438 — all of them.** Nothing sampled, nothing filtered |
| Coverage | 37 states/UTs, 668 districts |
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

- **80 rows have no usable coordinates** (blank or non-numeric latitude/longitude).
  They are still loaded — dropping them would break the row-count guarantee. They
  are simply excluded from any distance calculation.
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
   joined per district. Generated antimalarial demand peaks in September at
   1.53× baseline against the real HMIS figure of 1.58×.

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
