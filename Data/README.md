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

Each of the 15 tracked items names one of these as its `demand_driver`, so
monthly demand shape is taken from real reported incidence rather than invented.

⚠️ **2019-20 means April 2019 – March 2020.** February and March 2020 are
COVID-affected. Use April–December or smooth those two months explicitly.

---

## 5. Item master — REAL

15 essential medicines, drawn from the **National List of Essential Medicines
2022** (`Data/India/nlem2022.pdf`, MoHFW) and cross-coded to **WHO ATC**.
Built by `ingestion/build_items.py` → `daysupply.items`.

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
| Daily stock events | **Generated** for demo facilities — see §8 once Block B lands |
| Forecasts | Pending Block B (BigQuery ML ARIMA_PLUS) |

---

*Sections 8+ (usage generation methodology, forecast model, lead-time proxy) are
added by Blocks B and C.*
