# DaySupply — Master Build Prompt (v2)

> Replaces v1. Deadline extended to **30 September 2026**.
> Keep at `/docs/MASTER_PROMPT.md`. Attach as standing context every session.
> **Personal target: 20 September.** The final ten days are buffer, not build time.

---

## 0. Working agreement

You are helping build a hackathon submission across roughly **five weekends**,
around a full-time job and an MBA semester. Optimise for a working deployed
system that survives a live demo.

Rules:

1. **The deployed URL stays live at all times.** It is already deployed. Never
   leave it broken between sessions.
2. **One block per instruction.** Do not scaffold ahead. Blocks are defined in §16.
3. **Commit after every working slice**, push to GitHub every session.
4. **Refactors are allowed now** — but only at the start of a session, never
   mid-feature, and never across more than two files at once.
5. **Ask before adding a dependency.** Each one is a deployment risk.
6. **Flag expensive operations before running them** — anything that scans more
   than ~10 GB in BigQuery or trains more than ~5,000 time series.
7. **Every session ends with:** a green `/healthz`, a pushed commit, and a
   one-line note in `docs/PROGRESS.md` on what's done and what's next.

---

## 1. What we are building

**DaySupply** — a voice-first medicine stock reporting and redistribution system
for primary health centres, designed to work across countries.

**The problem.** Public health systems know what they hold in aggregate and
almost nothing about where it is right now. A district warehouse can hold six
months of a drug while a health centre 40 km away turns patients away. The root
cause is *capture*, not analytics: the person expected to record stock is a
pharmacist or nurse running a clinic alone, often without connectivity, for whom
data entry is unpaid overtime. Entries are late, batched, or fabricated — and
every dashboard above them inherits that.

**The thesis.** Existing systems start at the dashboard and hope data arrives.
This starts at the person holding the register and works upward.

**Four moves:**

1. Make capture cost nothing — a 30-second voice note in the local language,
   works offline, syncs later
2. Forecast at the facility, not the district — days of cover with a date
3. Recommend the transfer, don't just show the gap — a specific quantity between
   two named facilities
4. Share the model, not the patients — countries exchange demand patterns, never
   records

---

## 2. The golden path

Everything must serve this sequence:

1. A health worker records a voice note in Hindi (or Portuguese) describing what
   was dispensed or what is left
2. Captured offline, queued locally, syncs when connectivity returns
3. Gemini converts the audio to a structured stock record
4. Record lands in Firestore, streams to BigQuery
5. Forecast refreshes for that facility × item
6. Days-of-cover falls below threshold → stock-out warning fires
7. Engine matches the deficit against a nearby surplus facility
8. Output: transfer N units from B to A, with distance and post-transfer cover
   for both
9. District officer sees it on a map with an approve action
10. Switching country config runs the same flow in Portuguese with Brazilian
    administrative structure

**Out of scope, permanently:** patient records, procurement workflows, cold
chain, batch/expiry tracking, native mobile apps, multi-tenancy, real approval
routing, production authentication.

---

## 3. Hackathon requirements

Submission to **Build with AI: Code for Communities, 2nd Edition**, track
*Smart Health & Supply Chain Resilience* (BRICS theme: Resilience).
**Submission closes 30 September 2026.**

**Mandatory build criteria:**

| Requirement | How we satisfy it |
|---|---|
| Functioning end-to-end flow | The golden path in §2, demoable in one unbroken take |
| Google AI integration | Gemini for audio→structured extraction **and** BigQuery ML ARIMA_PLUS for forecasting |
| Real or realistic data | Real facility, population and demand data from both countries; simulated usage history, disclosed |
| Cross-border applicability | Country is a config file, not a fork. India + Brazil on one codebase |
| Multilingual / voice | Hindi and Portuguese voice capture |

**Judging weights:**

- AI/Technical Execution 25%
- Deployability & Scalability 20%
- Cross-Border Applicability 20%
- Problem–Solution Fit 20%
- Impact 10%
- Presentation 5%

**Submission package:** source code (GitHub, private with access granted), demo
video 3–5 min, pitch deck 10–12 slides, 2–3 line description, live deployed link.

---

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Capture AI | Gemini API (multimodal audio) | One call: speech → translation → structured JSON |
| Forecasting | **BigQuery ML `ARIMA_PLUS`** | Reinstated — time and credits now permit it |
| Operational DB | Firestore | Offline persistence and sync built in |
| Analytics store | BigQuery | Partitioned and clustered per §7 |
| Compute | Cloud Run (containerised FastAPI) | Already deployed, region `asia-south1` |
| Frontend | PWA served by Cloud Run | Service worker for offline |
| Map | Google Maps Platform JS API | Transfer arrows between facilities |

**Do not use:** Vertex AI AutoML (no gain over ARIMA_PLUS here), Dialogflow
(Gemini does it better in one call), Vertex AI Vision (no use case), separate
Speech-to-Text + Translation chain (three failure points instead of one).

**Budget:** ₹28,694 Google Cloud trial credit (expires 21 Nov 2026) plus $30 in
Developer Program credits. Ample. Still avoid full-table scans.

---

## 5. The data

Files live under `Data/<country>/` (capital D). Ingestion code lives in
`ingestion/` at repo root — Windows treats `Data/` and `data/` as the same
folder, so they must not collide. `Data/` is gitignored.

### India — `Data/India/`

| File | Contents | Notes |
|---|---|---|
| `geocode_health_centre.csv` | 200,438 facilities, all 37 states, 668 districts | **Primary facility master.** 29,733 PHCs, 5,389 CHCs, 163,131 sub-centres. Columns: State Name, District Name, Subdistrict Name, Facility Type, Facility Name, Facility Address, Latitude, Longitude, ActiveFlag_C, Location Type, Type Of Facility. Only 15 rows lack coordinates |
| `<StateName>.xls` × 36 + `All_India.xls` | HMIS 2019-20 monthly data | **NOT Excel.** SAS-generated HTML with `.xls` extension, ~120 MB each, `latin-1`. Parse with `pandas.read_html` or BeautifulSoup. Structure: districts × data items × 12 months, split Public/Private and Urban/Rural |
| `rural-population-centre_2017.xls` | Population covered per centre | Demand-scaling denominator |
| `pharmacists-PHCS-CHCS_2017.xls` | Pharmacist counts and vacancies | Deck evidence |
| `facilities-PHCS_2017.xls` | PHC infrastructure/functioning | Deck evidence |
| `nlem2022.pdf` | National List of Essential Medicines 2022 | Source for 15 drugs |

**HMIS data items that matter:** `Outpatient - Diabetes`, `Outpatient -
Hypertension`, `Outpatient - Epilepsy`, `Outpatient - Mental illness`,
`Outpatient - Dental`, `Outpatient - Ophthalmic Related`, `Outpatient - Acute
Heart Diseases`, `Outpatient - Stroke (Paralysis)`, plus Malaria (microscopy and
RDT positives by species), Childhood Diseases, Inpatient counts.

These map onto drug categories — hypertension outpatients drive antihypertensive
demand, malaria positives drive antimalarial demand. **This is the real
seasonality signal for the whole system.**

⚠️ 2019-20 = April 2019 to March 2020. Feb–Mar 2020 is COVID-affected. Use
April–December, or smooth those months explicitly.

### Brazil — `Data/Brazil/`

| File | Contents | Notes |
|---|---|---|
| `cnes_estabelecimentos.csv` | 632,726 establishments, 36 cols | **Primary facility master.** Semicolon-delimited, `latin-1`. Filter `TP_UNIDADE in ('1','2')` and `CO_MOTIVO_DESAB` null → 50,697 primary-care facilities |
| `cnes_coord.csv` | 574,172 rows, comma-delimited UTF-8 | Supplies `municipio` **names** (5,297) and `uf`, which the main file lacks. Also full addresses |
| `brazil_municipalities_population.csv` | 5,570 municipalities, 1970–2022 | Filter `year == 2022` before joining or rows multiply 26× |
| `RENAME-2022.pdf` | National essential medicines list | Brazilian drug names |

### Join gotchas — these fail silently if ignored

1. **CNES codes:** `cnes_coord.co_cnes` unpadded; `cnes_estabelecimentos.CO_CNES`
   has leading zeros. Strip on both sides.
2. **IBGE codes:** population file uses 7 digits (`3118304`); CNES `CO_IBGE` uses
   6 (`311830`). The 7th is a check digit — truncate it.
3. **Brazilian decimals:** some exports use comma as decimal separator. Check
   before casting lat/long.
4. **Encoding:** CNES files and HMIS `.xls` are `latin-1`. UTF-8 corrupts accents.
5. **Write a row-count assertion after every join.** A join that silently drops
   to zero rows is the most likely bug in this codebase.

### Verified demo geography

- **India:** Mahbubnagar and Ranga Reddy districts, Telangana — 120 km apart.
  Alternative: two adjacent Maharashtra districts, which aligns facility data
  with the richest HMIS file.
- **Brazil:** Conselheiro Lafaiete (IBGE 3118304, pop 131,621) and Pará de Minas
  (IBGE 3147105, pop 97,139), Minas Gerais — 121 km apart.

Both pairs sit inside their config's `transfer_max_km`.

---

## 6. Cost discipline

Credits are ample but not infinite. Non-negotiable:

1. **Load all real reference data** — facilities, population, items. A few GB,
   inside free-tier storage.
2. **Generated usage: 200 demo facilities.** 200 × 15 items × 365 days ≈ 1.1M
   rows. Do NOT generate for all 200,438 facilities — that is 1.1 billion rows
   and 3 million ARIMA series.
3. **Never `SELECT *`** on facility tables. Project and filter.
4. **Partition `stock_events` by `DATE(event_ts)`, cluster by `facility_id`.**
5. **Train ARIMA_PLUS on demo facilities only** (`is_demo_facility = TRUE`).
6. **Cloud Run min-instances 0.**
7. **Cache Gemini responses during development** so re-runs don't re-bill.

**The honest framing:** every facility in both countries is loaded and
searchable; usage history exists for the demo districts. State exactly this.

---

## 7. Data model

```sql
-- facilities: all real, both countries, fully loaded
facility_id       STRING    -- 'IN-<n>' | 'BR-<cnes>'
country_code      STRING
name              STRING
admin_l1          STRING    -- state / UF
admin_l2          STRING    -- district / município NAME
admin_l3          STRING    -- subdistrict, nullable
facility_type     STRING
latitude          FLOAT64
longitude         FLOAT64
population_served INT64
is_demo_facility  BOOL

-- items: 15 drugs, the cross-border join key
item_id           STRING
atc_code          STRING    -- WHO ATC
display_name      STRING
local_name_in     STRING    -- NLEM
local_name_br     STRING    -- RENAME
spoken_variants   ARRAY<STRING>
unit              STRING
demand_driver     STRING    -- which HMIS indicator drives this item

-- demand_reference: real, parsed from HMIS
country_code, admin_l2, month, indicator, value

-- stock_events: append-only
-- PARTITION BY DATE(event_ts) CLUSTER BY facility_id
event_id, facility_id, item_id, event_type, quantity,
event_ts, source, confidence, raw_transcript

-- current_stock: latest on-hand per facility × item
facility_id, item_id, on_hand, last_updated
```

`event_type` ∈ `dispensed` | `received` | `count`
`source` ∈ `voice` | `photo` | `seed` | `manual`

### Firestore

```
/facilities/{facility_id}      demo facilities, offline lookup
/pending_events/{event_id}     queued voice notes
/alerts/{alert_id}             open stock-out warnings
/recommendations/{rec_id}      transfer suggestions + status
/review_queue/{event_id}       low-confidence extractions
```

---

## 8. Country config

One YAML per country. **Adding a country must never require code changes.**

```yaml
# config/in.yaml
country_code: IN
languages: [hi, en]
admin_labels: {l1: State, l2: District, l3: Subdistrict}
facility_label: "Primary Health Centre"
data_sources: ["NHM Health Centres Directory", "HMIS 2019-20", "NLEM 2022"]
stockout_threshold_days: 14
transfer_max_km: 150
demo_admin_l2: ["Mahbubnagar", "Ranga Reddy"]

# config/br.yaml
country_code: BR
languages: [pt]
admin_labels: {l1: UF, l2: Município}
facility_label: "Unidade Básica de Saúde"
data_sources: ["CNES", "IBGE 2022", "RENAME 2022"]
stockout_threshold_days: 21
transfer_max_km: 300
demo_admin_l2: ["Conselheiro Lafaiete", "Pará de Minas"]
```

---

## 9. Gemini capture contract

System prompt — do not rewrite without asking:

```
You extract pharmacy stock updates from voice notes recorded by health
workers at primary health centres. The speaker may use Hindi, English,
Portuguese, or a mix, with local drug names and informal quantities.

Return ONLY a JSON array, no prose, no markdown fences. One object per
item mentioned:

[{
  "local_name": "<drug name exactly as spoken>",
  "event_type": "dispensed" | "received" | "count",
  "quantity": <integer or null>,
  "unit": "tablet" | "strip" | "vial" | "bottle" | "unknown",
  "confidence": <0.0-1.0>
}]

Rules:
- "aadha dabba" / "half a box" -> estimate in units, confidence <= 0.5
- If quantity is unclear, return the item with quantity null
- Never invent items that were not mentioned
- Transcribe the drug name as spoken; do not translate or correct it
```

**Critical:** map `local_name → item_id` **server-side** via fuzzy match against
the items table. Never let the model produce the drug code — a hallucinated drug
code is the worst failure this system can produce.

Confidence < 0.6 → review queue, not the forecast. Surface the queue in the UI.

---

## 10. Forecasting

```sql
CREATE OR REPLACE MODEL `daysupply.demand_forecast`
OPTIONS(
  model_type='ARIMA_PLUS',
  time_series_timestamp_col='event_date',
  time_series_data_col='qty_dispensed',
  time_series_id_col='series_id',
  horizon=30,
  auto_arima=TRUE,
  data_frequency='DAILY'
) AS
SELECT
  DATE(event_ts) AS event_date,
  CONCAT(facility_id, '|', item_id) AS series_id,
  SUM(quantity) AS qty_dispensed
FROM `daysupply.stock_events`
WHERE event_type = 'dispensed'
  AND facility_id IN (
    SELECT facility_id FROM `daysupply.facilities` WHERE is_demo_facility
  )
GROUP BY 1, 2;
```

Days of cover = `on_hand / forecast_daily_demand`. Warn below the config
threshold.

3,000 series (200 facilities × 15 items) is a comfortable ARIMA_PLUS workload.
Time the first training run and record it in `docs/PROGRESS.md`.

**Fallback still documented:** 4-week moving average with day-of-week factor,
identical output shape. Keep the code path — it's a good comparison baseline for
the deck.

---

## 11. Usage data generator

`ingestion/generate_usage.py` — produces `stock_events` for 200 demo facilities,
15 items, 365 days. Anchor every number to something real:

1. **Scale by `population_served`** — a facility covering 30,000 dispenses ~6× one
   covering 5,000
2. **Seasonality from real HMIS monthly data** — each item's `demand_driver`
   points at an HMIS indicator; use its real monthly shape
3. **Day-of-week variation** — weekdays busier
4. **Poisson noise** around the expected value
5. **Deliberate scenarios** — engineer at least three facilities into deficit and
   matching nearby facilities into surplus, so the demo always has something to
   recommend
6. **Deterministic seed** so runs are reproducible

Document the methodology in `Data/README.md`: which fields are real, which
generated, and how. **This file is a credibility asset.**

---

## 12. Redistribution logic

Deterministic and readable — a judge should follow it in ten seconds.

```
1. Compute days_of_cover for every (facility, item)
2. deficit = cover < threshold_days
   surplus = cover > 3 x threshold_days
3. For each deficit, find surplus facilities where:
     same item (or same atc_code)
     distance <= transfer_max_km
4. Score: surplus_days_after_transfer x (1 / distance_km)
5. Transfer qty = min(
     units to bring deficit to 2x threshold,
     units donor can give while staying above 2x threshold)
6. Emit: from, to, item, qty, distance, post-transfer cover for BOTH
```

Never propose a transfer that pushes the donor into deficit.

---

## 13. Federated pattern exchange

Now a real implementation, not a stub.

Each country node computes aggregate seasonal coefficients per `atc_code` — a
12-element monthly multiplier vector derived from its own demand history — and
publishes only that vector. The peer node ingests it as a prior for series with
thin history.

**No patient data, no facility-level data, no raw records cross the border.**

Demonstrate: Brazil has sparse history for an antimalarial; it ingests India's
seasonal vector for the matching ATC code and produces a materially better
forecast. Show both curves side by side. That single screen is the strongest
cross-border evidence in the submission.

---

## 14. API surface

```
POST /api/v1/voice-note              multipart audio + facility_id
POST /api/v1/photo-register          register photo -> structured rows (Block 8)
POST /api/v1/events                  structured write (seeding)
GET  /api/v1/facilities              list/search, config-filtered
GET  /api/v1/facilities/{id}         detail + current stock
GET  /api/v1/alerts                  open stock-out warnings
GET  /api/v1/recommendations         transfer suggestions
POST /api/v1/recommendations/{id}/approve
GET  /api/v1/review-queue            low-confidence extractions
POST /api/v1/review-queue/{id}/resolve
GET  /api/v1/forecast/{facility}/{item}
GET  /api/v1/patterns                aggregate seasonal coefficients
POST /api/v1/patterns                ingest peer node coefficients
GET  /healthz
```

---

## 15. Repo structure

```
daysupply/
├── app/
│   ├── main.py            FastAPI entry
│   ├── capture.py         Gemini call, JSON parsing, item matching
│   ├── forecast.py        BQML, days-of-cover
│   ├── redistribute.py    §12
│   ├── patterns.py        §13
│   ├── config.py          YAML loader
│   └── models.py          Pydantic schemas
├── config/                in.yaml, br.yaml
├── web/                   index.html, app.js, sw.js, styles.css
├── ingestion/
│   ├── load_india.py
│   ├── load_brazil.py
│   ├── parse_hmis.py      the HTML-disguised .xls parser
│   ├── build_items.py     15-drug crosswalk
│   └── generate_usage.py  §11
├── docs/
│   ├── MASTER_PROMPT.md   this file
│   ├── PROGRESS.md        one line per session
│   └── architecture.png
├── tests/                 join assertions, redistribution unit tests
├── Data/                  GITIGNORED — raw source files
├── Dockerfile
├── .gitignore
└── README.md
```

---

## 16. Build plan — five weekends

**Personal deadline 20 September.** MBA assignment window 11–15 September is a
protected no-build zone.

| Block | Weekend | Deliverable | Gate |
|---|---|---|---|
| **1** ✅ | 22 Aug | Repo, Dockerfile, FastAPI skeleton, Cloud Run deployed | Public URL live |
| **2** | 23–24 Aug | Ingest facilities + population, both countries, to BigQuery. Row-count assertions | `SELECT COUNT(*)` returns 200,438 / 50,697 |
| **3** | 30–31 Aug | 15-item master with ATC crosswalk. HMIS parser → `demand_reference` | Items joinable across both countries |
| **4** | 30–31 Aug | Gemini capture: audio → JSON → item match → write. Review queue | Speak Hindi, see a correct record |
| **5** | 6–7 Sep | Usage generator, 200 facilities. ARIMA_PLUS trained. Days-of-cover | Real forecast numbers on demo facilities |
| **6** | 6–7 Sep | Redistribution engine + approve flow | A specific, sensible transfer recommendation |
| **7** | 13–14 Sep* | PWA: record button, offline queue, alerts, map with transfer arrows | Golden path runs in a browser |
| **8** | 19–20 Sep | Brazil config end-to-end. Federated exchange. Register-photo capture | Both countries live on one codebase |
| **9** | 19–20 Sep | Video, deck, README, `Data/README.md`, submit | Submitted |

\* Block 7 collides with the MBA assignment window. If assignments dominate, push
Block 7 into 19–20 Sep and drop register-photo capture from Block 8.

---

## 17. Cut ladder

If 20 September arrives and you're behind, drop in this order:

1. Register-photo capture
2. Federated exchange → static architecture slide
3. Map animation → static arrow
4. ARIMA_PLUS → moving average fallback
5. Brazil → config file + one screenshot rather than a live demo

**Never cut:** deployed URL, voice capture, a specific transfer recommendation,
the review queue. Those four are the submission.

---

## 18. Quality bar

With time available, these are now expected rather than optional:

- **Tests** in `tests/` for the redistribution algorithm and every data join
- **Row-count assertions** after every ingestion step, failing loudly
- **Error handling** on every Gemini call — timeout, malformed JSON, empty audio
- **A seeded demo reset endpoint** so a failed live demo can be recovered in
  seconds
- **`docs/PROGRESS.md`** updated every session

---

## 19. Deck evidence (not product data)

- **BNAFAR submission tracker** — thousands of Brazilian municipalities transmit
  partially or not at all despite daily submission being mandatory since the
  December 2024 ordinance. *Verify the denominator: the displayed figures exceed
  Brazil's 5,570 municipalities, so they likely count month-submissions.*
- **India pharmacist vacancy data** — the person expected to keep stock records
  frequently isn't there
- **South Africa's Stock Visibility System** — real and deployed; its evaluations
  document reporting-compliance decay. Position against it rather than being
  asked about it
