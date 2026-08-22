# DaySupply — Master Build Prompt

> Paste this as the standing context for the build session.
> Keep it in the repo at `/docs/MASTER_PROMPT.md`.

---

## 0. Working agreement (read first)

You are helping build a hackathon submission in a **five-day window with roughly
20 hours of working time**. Optimise for a working deployed demo, not for
architectural elegance.

Rules:

1. **Deploy on day one.** Get an end-to-end stubbed path live before making any
   single component real. There must never be a day where nothing is submittable.
2. **One task at a time.** Build one endpoint or one function per instruction.
   Do not scaffold the whole application in one pass.
3. **Commit after every working slice.** A bad generation should be a rollback,
   not a debugging session.
4. **No cross-file refactors** during the build week. Ugly code that works beats
   clean code that doesn't.
5. **Ask before adding a dependency.** Every library is a deployment risk.
6. **Cost discipline is a hard requirement** — see §6. If an instruction would
   create a large BigQuery scan or a long-running training job, say so before
   running it.

---

## 1. What we are building

**DaySupply** — a voice-first medicine stock reporting and redistribution system
for primary health centres, designed to work across countries.

**The problem.** Public health systems know what they hold in aggregate and
almost nothing about where it is right now. A district warehouse can hold six
months of a drug while a health centre 40 km away turns patients away. The root
cause is *capture*, not analytics: the person expected to record stock is a
pharmacist or nurse running a clinic alone, often without connectivity, for whom
data entry is unpaid overtime. So entries are late, batched, or fabricated — and
every dashboard above them inherits that.

**The thesis.** Existing systems start at the dashboard and hope data arrives.
This starts at the person holding the register and works upward.

**Four moves:**

1. Make capture cost nothing — a 30-second voice note in the local language,
   works offline, syncs later.
2. Forecast at the facility, not the district — days of cover with a date.
3. Recommend the transfer, don't just show the gap — a specific quantity between
   two named facilities.
4. Share the model, not the patients — countries exchange demand patterns, never
   records.

---

## 2. The golden path

Everything built must serve this sequence. If a feature is not on this path, it
is not in scope.

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

**Explicitly out of scope:** authentication beyond a demo login, procurement
workflows, patient records, cold chain, batch/expiry tracking, native mobile
apps, multi-tenancy, real approval routing.

---

## 3. Hackathon requirements (non-negotiable)

This is a submission to **Build with AI: Code for Communities, 2nd Edition**,
track: *Smart Health & Supply Chain Resilience* (BRICS theme: Resilience).

**Mandatory build criteria — all five must be demonstrably true:**

| Requirement | How we satisfy it |
|---|---|
| Functioning end-to-end flow | The golden path in §2, demoable in one unbroken take |
| Google AI integration (mandatory) | Gemini for audio→structured extraction **and** BigQuery ML for forecasting — two categories, not one |
| Real or realistic data | Real facility, population and demand data from both countries; simulated usage history, disclosed |
| Cross-border applicability | Country is a config file, not a fork. India + Brazil on one codebase |
| Multilingual / voice support | Hindi and Portuguese voice capture |

**Judging weights — build to these:**

- AI/Technical Execution 25%
- Deployability & Scalability 20%
- Cross-Border Applicability 20%
- Problem–Solution Fit 20%
- Impact 10%
- Presentation 5%

Execution + deployability = 45%. **A live deployed URL matters more than a
polished narrative.** Presentation at 5% means do not spend build time on visual
refinement.

**Submission package:** source code (GitHub, access-granted), demo video 3–5 min,
pitch deck 10–12 slides, 2–3 line description, live deployed link.

---

## 4. Tech stack

**Use:**

| Layer | Choice | Why |
|---|---|---|
| Capture AI | Gemini API (multimodal audio) | One call: speech → translation → structured JSON. Handles Hindi and Portuguese |
| Forecasting | BigQuery ML `ARIMA_PLUS` | Trains in SQL, minutes not hours, no serving infrastructure |
| Operational DB | Firestore | Offline persistence and sync are built in |
| Analytics store | BigQuery | Named on the hackathon tooling page |
| Compute | Cloud Run (containerised FastAPI) | Gives the live public URL |
| Frontend | Single-page PWA served by Cloud Run | Service worker for offline. No build toolchain |
| Map | Google Maps Platform JS API | The one visual this track otherwise lacks |

**Do not use, and be ready to justify:**

- *Vertex AI AutoML* — long training runs, credit-hungry, no gain over ARIMA_PLUS
- *Dialogflow* — days of intent config to do worse than one Gemini call
- *Vertex AI Vision* — no use case in this track
- *Separate Speech-to-Text + Translation chain* — Gemini does it in one hop

---

## 5. The data

All files are under `DaySupply/Data/<country>/`. **Load all real reference data.**
Do not sample the facility, population or medicines tables.

### India — `Data/India/`

| File | Contents | Notes |
|---|---|---|
| `geocode_health_centre.csv` | 200,438 facilities, all states | **Primary facility master.** 29,733 PHCs, 5,389 CHCs, 163,131 sub-centres. Columns: State Name, District Name, Subdistrict Name, Facility Type, Facility Name, Latitude, Longitude, Location Type, Type Of Facility. Only 15 rows missing coordinates |
| `<StateName>.xls` (36 files) | HMIS 2019-20 monthly data | **These are NOT Excel files.** SAS-generated HTML with an `.xls` extension, ~120 MB each. Parse with `pandas.read_html` or BeautifulSoup, encoding `latin-1`. Structure: districts × data items × 12 months, split Public/Private and Urban/Rural |
| `All_India.xls` | HMIS national rollup | Use this for the national picture rather than parsing all 36 state files |
| `rural-population-centre_2017.xls` | Population covered per centre | Population denominator for demand scaling |
| `pharmacists-PHCS-CHCS_2017.xls` | Pharmacist counts and vacancies | Evidence for the deck, not product data |
| `facilities-PHCS_2017.xls` | PHC infrastructure/functioning | Evidence for the deck |
| `nlem2022.pdf` | National List of Essential Medicines 2022 | Extract ~15 common primary-care drugs |

**HMIS data items that matter:** `Outpatient - Diabetes`, `Outpatient -
Hypertension`, `Outpatient - Epilepsy`, `Outpatient - Mental illness`,
`Outpatient - Dental`, `Outpatient - Ophthalmic Related`, `Outpatient - Acute
Heart Diseases`, `Outpatient - Stroke`, plus Malaria (microscopy and RDT
positives, by species), Childhood Diseases, and Inpatient counts.

These map onto drug categories — hypertension outpatients drive antihypertensive
demand, malaria positives drive antimalarial demand. **This is the real
seasonality signal for the whole system.**

⚠️ 2019-20 runs April 2019 to March 2020, so Feb–Mar 2020 is COVID-affected.
Prefer April–December, or smooth those months.

### Brazil — `Data/Brazil/`

| File | Contents | Notes |
|---|---|---|
| `cnes_estabelecimentos.csv` | 632,726 establishments, 36 columns | **Primary facility master.** Semicolon-delimited, `latin-1` encoding. Filter: `TP_UNIDADE in ('1','2')` (Posto de Saúde, Centro de Saúde/UBS), `CO_MOTIVO_DESAB` null (still active) → 50,697 primary-care facilities |
| `cnes_coord.csv` | 574,172 rows | Comma-delimited, UTF-8. Provides `municipio` **names** (5,297) and `uf`, which the main file lacks. Join on CNES code |
| `brazil_municipalities_population.csv` | 5,570 municipalities, 1970–2022 | Filter to `year == 2022` (census year) before joining, or rows multiply |
| `RENAME-2022.pdf` | National essential medicines list | Brazilian drug names. 2024 PDF was not retrievable; 2022 is equivalent for our 15 drugs |

### Join gotchas — get these right or joins fail silently

1. **CNES codes:** `cnes_coord.co_cnes` is unpadded; `cnes_estabelecimentos.CO_CNES`
   has leading zeros. Strip leading zeros on both sides before joining.
2. **IBGE codes:** `brazil_municipalities_population.id_municipality` is 7 digits
   (`3118304`); CNES `CO_IBGE` is 6 digits (`311830`). The 7th digit is a check
   digit — truncate it.
3. **Brazilian decimals:** some exports use a comma as decimal separator. Check
   before casting latitude/longitude to float.
4. **Latin-1:** both CNES files and the HMIS `.xls` files. Reading as UTF-8 will
   corrupt accented names.

---

## 6. Cost constraints — HARD LIMITS

Budget is near-zero. Google Cloud free tiers plus a $10/month Google Developer
Program credit (from AI Pro). Treat these as build requirements:

1. **Set a BigQuery budget alert before the first query.**
2. **Load all real reference data** (facilities, population, medicines) — a few
   GB, inside the 10 GB free storage tier.
3. **Generated usage data must be scoped.** 200,438 facilities × 15 drugs × 365
   days = 1.1 billion rows and ~3 million ARIMA series. Do not attempt this.
   Generate usage for **200 demo facilities maximum** — roughly 200 × 15 × 365 ≈
   1.1M rows, which is free-tier territory.
4. **Never `SELECT *` on the facility tables.** Always project columns and filter.
5. **Partition `stock_events` by date, cluster by facility_id.**
6. **Train ARIMA_PLUS on the demo subset only.** If training exceeds a few
   minutes, stop and fall back (see §10).
7. **Cloud Run: min instances 0.** It must scale to zero when idle.
8. **Gemini: test one audio call before writing the capture pipeline.** Do not
   loop over audio files in testing.

**The honest framing for the demo:** every facility in both countries is loaded
and searchable. Usage history exists for the demo districts. Say exactly this —
do not imply nationwide simulated data.

---

## 7. Data model

### BigQuery tables

```sql
-- facilities: all real, both countries, fully loaded
facility_id       STRING   -- 'IN-<n>' or 'BR-<cnes>'
country_code      STRING   -- 'IN' | 'BR'
name              STRING
admin_l1          STRING   -- state / UF
admin_l2          STRING   -- district / município (NAME, not code)
admin_l3          STRING   -- subdistrict, nullable
facility_type     STRING
latitude          FLOAT64
longitude         FLOAT64
population_served INT64    -- India: rural-population-centre; Brazil: municipality population
is_demo_facility  BOOL     -- TRUE for the ~200 with generated usage

-- items: ~15 drugs, the cross-border join key
item_id           STRING
atc_code          STRING   -- WHO ATC — what makes India and Brazil comparable
display_name      STRING   -- English
local_name_in     STRING   -- NLEM name
local_name_br     STRING   -- RENAME name
spoken_variants   ARRAY<STRING>  -- what a health worker actually says
unit              STRING   -- 'tablet' | 'strip' | 'vial' | 'bottle'

-- demand_reference: real, from HMIS
country_code, admin_l2, month, indicator, value

-- stock_events: append-only fact table
-- PARTITION BY DATE(event_ts), CLUSTER BY facility_id
event_id, facility_id, item_id, event_type, quantity,
event_ts, source, confidence, raw_transcript
```

`event_type` ∈ `dispensed` | `received` | `count`.
`source` ∈ `voice` | `seed` | `manual`.

### Firestore

```
/facilities/{facility_id}      mirror for offline lookup (demo facilities only)
/pending_events/{event_id}     queued voice notes, synced when online
/alerts/{alert_id}             open stock-out warnings
/recommendations/{rec_id}      transfer suggestions + status
```

---

## 8. Country config

One YAML per country. **Adding a country must never require touching application
code.** Load by environment variable.

```yaml
# config/in.yaml
country_code: IN
languages: [hi, en]
admin_labels: {l1: State, l2: District, l3: Subdistrict}
facility_label: "Primary Health Centre"
data_sources: ["NHM Health Centres Directory", "HMIS 2019-20", "NLEM 2022"]
stockout_threshold_days: 14
transfer_max_km: 150

# config/br.yaml
country_code: BR
languages: [pt]
admin_labels: {l1: UF, l2: Município}
facility_label: "Unidade Básica de Saúde"
data_sources: ["CNES", "IBGE 2022", "RENAME 2022"]
stockout_threshold_days: 21
transfer_max_km: 300
```

---

## 9. Gemini capture contract

System prompt — keep it short, test it early, do not rewrite it without asking:

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

**Critical:** map `local_name → item_id` **server-side** with fuzzy matching
against the items table. Never ask Gemini to produce the drug code — a
hallucinated drug code is the worst failure this system can produce.

Records with confidence < 0.6 go to a **review queue**, not into the forecast.
Surface that queue in the UI.

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
  AND facility_id IN (SELECT facility_id FROM facilities WHERE is_demo_facility)
GROUP BY 1, 2;
```

Days of cover = `current_on_hand / forecast_daily_demand`.
Warning when below the country threshold.

**Fallback (decide by Tuesday evening, do not straddle both):** 4-week moving
average with a day-of-week factor. Identical output shape, so nothing downstream
changes.

---

## 11. Usage data generator

Write a script that produces `stock_events` for the ~200 demo facilities,
15 items, 365 days. Anchor every number to something real:

1. **Scale by population served** — a facility covering 30,000 people dispenses
   roughly six times one covering 5,000
2. **Seasonality from real HMIS monthly data** — malaria positives and outpatient
   condition counts drive the monthly shape for matching ATC categories
3. **Day-of-week variation** — weekdays busier than weekends
4. **Random noise** — Poisson around the expected value
5. **Deliberate stock-outs** — engineer at least one facility into deficit and
   one nearby into surplus, so the demo has something to recommend

Write the methodology into `Data/README.md`: which fields are real, which are
generated, and how. **This file is a credibility asset — judges catch inflated
claims.**

---

## 12. Redistribution logic

Deterministic and readable. Not a model — a judge should follow it in ten
seconds, and it must never produce something embarrassing on camera.

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
6. Emit: from, to, item, qty, distance, post-transfer cover for BOTH facilities
```

Never propose a transfer that pushes the donor into deficit.

---

## 13. Federated pattern exchange (scope-capped)

Do **not** attempt real federated learning.

Each country node computes aggregate seasonal coefficients per `atc_code` and
publishes only that vector. The peer node ingests it as a prior for series with
thin history. No patient data, no facility-level data crosses the border.

One endpoint each way, one JSON payload, one screenshot. State that it
demonstrates the architecture rather than a production federation.

---

## 14. API surface

```
POST /api/v1/voice-note        multipart audio + facility_id -> extracted records
POST /api/v1/events            structured write (seeding)
GET  /api/v1/facilities        list, filtered by country config
GET  /api/v1/alerts            open stock-out warnings
GET  /api/v1/recommendations   transfer suggestions
POST /api/v1/recommendations/{id}/approve
GET  /api/v1/review-queue      low-confidence extractions
GET  /api/v1/patterns          aggregate seasonal coefficients
POST /api/v1/patterns          ingest peer node coefficients
GET  /healthz
```

---

## 15. Repo structure

```
daysupply/
├── app/
│   ├── main.py           FastAPI entry
│   ├── capture.py        Gemini call, JSON parsing, item matching
│   ├── forecast.py       BQML queries, days-of-cover
│   ├── redistribute.py   the algorithm in §12
│   ├── patterns.py       federated exchange
│   └── config.py         YAML loader
├── config/               in.yaml, br.yaml
├── web/                  index.html, app.js, sw.js  (PWA + map)
├── data/
│   ├── ingest/           loaders for each source file
│   ├── generate_usage.py the §11 generator
│   └── README.md         provenance: real vs generated
├── docs/                 spec.md, MASTER_PROMPT.md, architecture.png
├── Dockerfile
├── .gitignore            MUST exclude Data/ — CNES alone is 229 MB
└── README.md
```

**`.gitignore` on day one.** GitHub rejects files over 100 MB and several source
files exceed that.

---

## 16. Build order

| Day | Deliverable | Gate — must be true that night |
|---|---|---|
| **1** | Cloud Run deployed, all stages stubbed, Firestore connected, `.gitignore` set | A stranger can open the URL |
| **2** | Ingest real facility/population/items data to BigQuery. Gemini capture working. Offline queue + sync | Speak into it, see a real record |
| **3** | Usage generator, ARIMA_PLUS (or fallback), days-of-cover, redistribution | Real numbers drive a real recommendation |
| **4** | Brazil config, Portuguese voice note, map with transfer arrow, review queue | Everything demo-visible works — day 5 is not a build day |
| **5** | Freeze. Record video, finish deck, README, submit | Submitted early evening, not at the deadline |

---

## 17. Cut ladder

Behind schedule? Drop in this order, without renegotiating:

1. Register-photo capture (bonus only, never started unless ahead)
2. Federated exchange → architecture slide only
3. Map animation → static arrow
4. Second country → config file + one screenshot
5. ARIMA_PLUS → moving average

**Never cut:** deployed URL, voice capture, a specific transfer recommendation.
Those three are the submission.

---

## 18. Deck evidence (not product data)

- BNAFAR submission tracker: thousands of Brazilian municipalities transmit
  partially or not at all, despite daily submission being mandatory since the
  December 2024 ordinance. *Verify the denominator before quoting figures.*
- India pharmacist vacancy data — the person expected to keep stock records
  frequently isn't there
- South Africa's Stock Visibility System — real, deployed, and its evaluations
  document reporting compliance decay. Position against it rather than being
  asked about it
