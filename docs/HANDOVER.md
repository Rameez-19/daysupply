# StockPulse — Project Handover

> **This file is current state** — what is real, what is generated, what is
> broken, and every open decision. It is not the spec and not the figure
> source: **no number here overrides `docs/CLAIMS.md`.**
>
> **Document hierarchy — four files, four jobs:**
>
> | File | Authority |
> |---|---|
> | **`docs/MASTER_PROMPT.md`** | **Governing spec.** What we are building, and the constraints it must respect |
> | **`docs/CLAIMS.md`** | **Source of truth for every figure.** If a number is not in there, it is not evidence and does not go in front of a judge |
> | **`docs/HANDOVER.md`** | **Current state.** What is real, what is generated, what is broken, and every open decision |
> | **`docs/PROGRESS.md`** | **A dated log. Not authoritative.** It records what was true on a date; superseded figures are left as written |
>
> **Naming:** the project was renamed mid-build. **StockPulse** is current.
> "DaySupply" survives in the repo name and the Cloud Run URL. See §9.

---

## 1. Read this first — what is real and what is not

This section matters more than anything else in this document. The product looks
substantially more complete than it is, and anyone continuing without knowing the
difference will overclaim in the submission.

> **Revised 30 August 2026, after Block A.** The previous version of this
> section was wrong on a central point — it said there was no BigQuery in the
> stack and that the facilities had never been loaded. Both claims were false
> when written. Corrected below.

| Component | Status | Notes |
|---|---|---|
| Gemini extraction (voice + chat + register photo) | **REAL, WORKING IN PROD** | Since 2026-09-30 through **Vertex AI** (service identity, billed to the project, no API key): gemini-3.5-flash in Mumbai, then gemini-2.5-flash in Mumbai, then gemini-3.6-flash global, 25 s timeout per call. The AI Studio key hit its quota and made phone voice notes take 140-176 s. Verified live in Telugu (voice), Bengali, Marathi and Telugu (text) |
| Spoken read-back | **REAL** | Cloud Text-to-Speech in five Indian voices (`app/speech.py`); the phone's own engine is the fallback |
| Officer pages: lean view | **REAL** | Explanations hidden by default behind one Explain switch (remembered per browser); Today opens with a task bar of live counts, change since the last visit on each tile, and a 5-minute auto-refresh. Report page and Evidence are exempt |
| **Capture persistence** | **BROKEN** | Extraction works; storage does not. The Firestore database does not exist, and nothing reads `pending_events` into BigQuery even if it did. `captures_today` therefore stays 0. See §9c |
| Offline queue + sync | **REAL** | Service Worker + IndexedDB, genuinely works offline. Queues both recordings and rows the worker already confirmed; the Report page shows the count waiting |
| Report page (tap / voice / photo / scan / type / staff / beds) | **REAL** | Built 2026-09-18. Preview-then-confirm on every model-read mode; Hindi/English; centre remembered on the phone. See CLAIMS §7g |
| Sixth state: Uttar Pradesh | **REAL inputs, GENERATED ledger, as for the other five** | Added 2026-09-23 with `docs/ONBOARD_A_STATE.md`: 75 PHCs, 3,818 series in total. The original 200 centres' stock lines did not change status. See CLAIMS §0 and Data/README §20 |
| Report page languages | **REAL** | English, Hindi, Marathi, Telugu, Bengali. The three new dictionaries were written without a native-speaker review; the test guide asks testers to flag wording |
| Escalation note drafting (Gemini) | **REAL** | `app/brief.py`. Grounded on the row, number-checked, flagged if it strays. See CLAIMS §7g |
| PWA / dashboard UI | **REAL** | Vanilla JS, Chart.js, deployed and functional |
| Barcode scanning | **REAL** | `html5-qrcode` |
| Review queue | **REAL** | Confidence-threshold routing. Only real held extractions from Firestore; the three invented "worked examples" and `app/demo_data.py` were removed 2026-09-18, and an empty queue says it is empty |
| Cloud Run deployment | **REAL** | Live, containerised, `asia-south1` |
| Haversine distance maths | **REAL** | Correct calculation |
| **Facility data** | **REAL** | All 200,438 facilities in BigQuery; dashboard queries them directly |
| **Facility counts / geography** | **REAL** | 37 states, **701 districts** (state×district pairs; 668 distinct names), from `daysupply.facilities` |
| **HMIS seasonality reference** | **REAL** | `demand_reference`, **34,524 rows, 137 districts, 5 states**, 21 drivers selected by HMIS item code |
| **Item catalogue** | **REAL** | Full NLEM 2022: **385 medicines, 264 with ATC codes**, 39 with real demand drivers |
| **Demand forecast** | **REAL** | BigQuery ML ARIMA_PLUS, 2,794 series, served via `ML.FORECAST` |
| **Stock-out alerts** | **REAL** | Lead-time reorder points, VEN-weighted. `get_demo_alerts` deleted |
| **Transfer recommendations** | **REAL** | FEFO batch selection, ATC substitution. `get_demo_recommendations` deleted |
| **Reporting consistency** | **REAL** | Measured from `count` events in the ledger |
| **Waste avoided** | **REAL** | 26,612 units (44.7%), measured against a FIFO replay. Supersedes 94,542, which predates the Block D+ driver corrections and the ledger regeneration that followed |
| **Lead times** | **REAL DISTANCE, ASSUMED CONVERSION** | Distance to district HQ is real; days-per-km is a documented proxy |
| **VEN classification** | **DERIVED** | Ours, not MoHFW's — NLEM does not publish VEN |
| **Daily stock events** | **GENERATED** | Anchored to real HMIS demand; see `Data/README.md` §9 |
| **`captures_today`** | **REAL BUT STUCK AT 0** | Counted from capture-sourced ledger events, which is correct. It reads 0 not because nothing has been captured but because captures never reach the ledger — see §9c |

### What was actually wrong with the previous version

The `daysupply` dataset existed in `asia-south1` the whole time, with three
populated tables: `facilities`, `items` (15 rows) and `demand_reference`
(4,092 rows). India's 200,438 facilities **had** been loaded. So had Brazil's
50,697 — the table held **251,135 rows**, because `ingestion/load_india.py` used
`WRITE_APPEND` with no preceding delete, and had been run more than once.

The real gap was never ingestion. It was that **nothing in the application
queried any of it** — `app/demo_data.py` held a hardcoded five-state hierarchy
and the dashboard read from that. Block A closed the wiring gap, not a data gap.

Two smaller corrections:

- The facility master has **80 rows with missing coordinates**, not 15 — and a
  further 553 whose coordinates are present but implausible, for **633 excluded
  from distance maths** in total. All are loaded regardless. See
  `docs/CLAIMS.md` §10 for the reconciliation.
- The venv was missing `google-generativeai`, `google-cloud-firestore` and
  `thefuzz`, so **the app could not start locally at all**. `requirements.txt`
  was correct; only the environment was stale. Reinstall with
  `.venv/Scripts/python -m pip install -r requirements.txt`.

### Current state after Block A

`daysupply.facilities` holds exactly 200,438 rows, all Indian: 37 states,
**701 state×district pairs** across **668 distinct district names**. The pair
count is the real district count — names such as Aurangabad and Bilaspur recur
across states, so counting distinct names alone undercounts by 33. 50,697
Brazilian rows were deleted on 2026-09-01 so that an unscoped `COUNT(*)` returns
the figure we publish; `load_facilities.py` now asserts it. `is_demo_facility` is
TRUE for **7,092** rows: PHCs in Telangana, Maharashtra, Rajasthan, Delhi, Assam.
`daysupply.geo_summary` is a ~738-row derived table backing the dropdowns.

> **Superseded.** This section previously ended "there is no trained model —
> until Block B lands, 'AI forecasting' must not appear in the deck". Block B
> landed. **BigQuery ML ARIMA_PLUS is trained on 2,794 series in 21.8 seconds**
> against real HMIS seasonality, and `ML.FORECAST` serves it. "AI forecasting"
> is now an accurate claim, provided it is said as: a real model, trained on a
> ledger generated from real government demand drivers.

---

## 2. What the product is

**StockPulse** — a voice-first medicine stock reporting and redistribution system
for Primary Health Centres in India.

**The problem.** Public health systems know what they hold in aggregate and
almost nothing about where it is right now. A district warehouse can hold six
months of a drug while a PHC 40 km away turns patients away. Evidence: overall
essential-medicine availability measured at 45.2% in Punjab and 51.1% in Haryana;
41.3% in Delhi; one survey found 13% of PHCs had no essential medicines and
insufficient stock in 75% of those surveyed.

**The root cause is capture, not analytics.** The person expected to record stock
is a pharmacist or ANM running a clinic alone, often without connectivity, for
whom data entry is unpaid overtime. Entries are late, batched at month-end, or
fabricated. Every dashboard above them inherits that.

**The thesis.** Existing systems start at the dashboard and hope data arrives.
StockPulse starts at the person holding the register and works upward.

**Design precedent.** Tamil Nadu's TNMSC — India's best-functioning public health
supply chain — succeeded partly on a "passbook" system, explicitly modelled on
banking, because it borrowed a mental model people already had. The voice
interface is the same move applied to the last mile.

---

## 3. Hackathon context

**Build with AI: Code for Communities, 2nd Edition** (hack2skill + Google Cloud).
Track 3: **Smart Health & Supply Chain Resilience**.

- **Submission closes 30 September 2026** (extended from 24 August; confirmed by
  email from the Google DevRel program manager). Personal target: **20 September**.
- Solo entry. Registered.

**⚠️ Scope changed mid-build:** the BRICS/global framing was removed. The event is
now India-only. The criterion **"Cross-Border Applicability" no longer exists** —
it is now **"Depth & Reach Across India"** at the same ~20% weight.

Consequences:
- Do not build a Brazil config. Brazilian data stays unused on disk.
- Federated exchange becomes **cross-district within India**.
- Remove "Global South" and similar phrasing from all copy.

**Judging weights:** Technical Execution 25%, Deployability & Scalability 20%,
Depth & Reach Across India ~20%, Problem–Solution Fit 20%, Impact 10%,
Presentation 5%.

**Submission package:** source code (GitHub, private with access granted), demo
video 3–5 min, pitch deck 10–12 slides, 2–3 line description, live deployed link.

**Known competitor in the same cohort:** "Sanjeevani Grid" — same core idea
(ASHA worker voice → Gemini extraction → transfer recommendation), India-only,
and its own description says its forecasting is *simulated via Vertex AI*. Our
differentiation must therefore be: real national-scale government data, a really
trained model, offline-first capture, and consultant-grade supply chain logic.

---

## 4. Architecture

```
Health worker (PWA, offline-first)
   │  voice note | barcode scan | chat text
   ▼
Cloud Run — FastAPI (asia-south1)
   ├─► Gemini API           audio/text → structured JSON       [REAL]
   ├─► BigQuery facilities  200,438 rows, all geography        [REAL]
   ├─► BigQuery geo_summary ~738-row dropdown cache            [REAL]
   ├─► BigQuery items       item catalogue                     [15 rows; full NLEM is Block B]
   ├─► BigQuery demand_ref  HMIS 2019-20 seasonality           [REAL, Telangana only]
   ├─► app/demo_data.py     operational counters only          [TO BE REPLACED, Block B]
   └─► BigQuery ML          ARIMA_PLUS                         [NOT BUILT — Block B]
   ▼
Dashboard — Chart.js, cascading state/district/PHC filters
```

**Target architecture after Block B:** the same, with `app/demo_data.py` removed
and BigQuery as the single source of truth for stock events, forecasts and
recommendations as well as facilities.

### Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML5/CSS3/JS, PWA (`sw.js` + IndexedDB), Chart.js, `html5-qrcode` |
| Backend | Python, FastAPI, containerised |
| AI | Google Gemini (extraction). BigQuery ML ARIMA_PLUS **planned, not built** |
| Hosting | Google Cloud Run, region `asia-south1` |

**Deliberately not used:** Vertex AI AutoML (credit-hungry, no gain over
ARIMA_PLUS here), Dialogflow (Gemini does it in one call), separate
Speech-to-Text + Translation chain (three failure points instead of one).

---

## 5. Repo structure

```
daysupply/
├── app/
│   ├── main.py          FastAPI, all /api/v1/... endpoints
│   ├── today_v2.py      Today: the scorecard, one round trip (executive.py retired 2026-09-18)
│   ├── mapview.py       district nodes + redistribution arcs, one round trip
│   ├── capture.py       Gemini audio → structured JSON
│   ├── demo_data.py     ⚠️ seeded generator — TO BE REPLACED by BigQuery
│   └── ...
├── web/
│   ├── index.html       SPA: dashboard, filters, charts
│   ├── app.js           views, Chart.js, MediaRecorder, IndexedDB queue
│   ├── surge.js         surge banner and signal badges
│   ├── map.js           Leaflet map: risk / headroom layers, flow arcs
│   ├── styles.css       "Deep Blue" NHM-style design system
│   └── sw.js            Service Worker, offline cache
├── ingestion/           load_facilities.py, build_geo_summary.py, parse_nlem.py, ...
├── config/              country abstraction (India only in use)
├── docs/
│   ├── MASTER_PROMPT.md governing spec
│   ├── HANDOVER.md      this file
│   ├── PROGRESS.md      one line per session
│   ├── pitch_deck.md    ⚠️ currently OUTSIDE the repo — move it in
│   └── video_script.md  ⚠️ currently OUTSIDE the repo — move it in
├── Data/                raw files gitignored; Data/README.md IS tracked — see §6
├── Dockerfile
└── .gitignore
```

`ingestion/` is named that way deliberately: Windows treats `Data/` and `data/`
as the same folder, so raw data and ingestion code cannot share a name.

---

## 6. Data inventory

Raw files under `Data/` are **gitignored**. `Data/README.md` is tracked and records provenance. `cnes_estabelecimentos.csv`
alone is 229 MB and GitHub rejects files over 100 MB.

### India — `Data/India/` (all currently unused by the application)

| File | Contents | Gotchas |
|---|---|---|
| `geocode_health_centre.csv` | **200,438 facilities**, 37 states, 668 districts. 29,733 PHCs, 5,389 CHCs, 163,131 sub-centres | Only 15 rows lack coordinates. Columns: State Name, District Name, Subdistrict Name, Facility Type, Facility Name, Latitude, Longitude, ActiveFlag_C, Location Type, Type Of Facility |
| `<State>.xls` × 36 + `All_India.xls` | HMIS 2019-20 monthly data, ~120 MB each | **NOT Excel.** SAS-generated HTML with `.xls` extension, `latin-1`. Parse with `pandas.read_html` / BeautifulSoup. Districts × data items × 12 months, split Public/Private and Urban/Rural |
| `rural-population-centre_2017.csv` | Population covered per centre | **State-level, not facility-level.** Applied as a state x facility-type average — see `Data/README.md` §2 |
| `pharmacists-PHCS-CHCS_2017.xls` | Pharmacist counts and vacancies | Deck evidence only |
| `facilities-PHCS_2017.xls` | PHC infrastructure/functioning | Deck evidence only |
| `nlem2022.pdf` / `nlem2022.xlsx` | National List of Essential Medicines 2022 | Use the **.xlsx**. 30 sheets, a PDF table extraction — see `ingestion/parse_nlem.py` for its many conversion artefacts |

**Usable HMIS indicators:** `Outpatient - Diabetes`, `- Hypertension`,
`- Epilepsy`, `- Mental illness`, `- Dental`, `- Ophthalmic Related`,
`- Acute Heart Diseases`, `- Stroke (Paralysis)`; Malaria microscopy and RDT
positives by species; Childhood Diseases; Inpatient counts.

These map to drug categories — hypertension outpatients drive antihypertensive
demand, malaria positives drive antimalarial demand. **This is the real
seasonality signal.**

> **Read §16 of `Data/README.md` before trusting any driver.** The first
> implementation selected indicators by matching words in the HMIS label, and
> that was wrong in three places. The malaria driver summed *blood smears
> examined* with *cases confirmed*, making it 99.8% testing effort; "Childhood
> Diseases" averaged fourteen unrelated conditions; "Inpatient counts" added
> deaths to admissions. Drivers are now selected by **item code** in
> `ingestion/hmis_drivers.py`, each with its clinical rationale.
>
> Three items previously recorded as having no available driver — paracetamol,
> ibuprofen and IFA — turned out to have exact indicators in the same file that
> had simply never been parsed. The full file carries 368 data items, not 11.

⚠️ 2019-20 = April 2019 to March 2020. Feb–Mar 2020 is COVID-affected. Use
April–December or smooth explicitly.

### Brazil — `Data/Brazil/` (**no longer in scope**, retain on disk)

CNES establishments (632,726 rows, semicolon-delimited, `latin-1`), CNES
coordinates, IBGE municipality population 1970–2022, RENAME 2022. Keep for one
scalability slide; do not build against it.

### Sources

- India facilities: Kaggle — All India Health Centres Directory
- India primary health care data: Kaggle — India Primary Health Care Data
- HMIS: `hmis.mohfw.gov.in` → Standard Reports → C2 → All States and Districts
  Across Months → 2019-20
- NLEM 2022: MoHFW
- Brazil: CNES via `dadosabertos.saude.gov.br`; population via Kaggle; RENAME
  2022 via `gov.br/saude` publications

---

## 7. Environment and deployment

| Item | Value |
|---|---|
| GCP project | `daysupply` |
| Region | `asia-south1` (Mumbai) |
| Live URL | `https://daysupply-898541549182.asia-south1.run.app/` |
| Billing | Free trial, ₹28,694 credit, expires 21 Nov 2026, plus $30 Developer Program credits |
| APIs enabled | Cloud Run, BigQuery, Firestore, Generative Language (Gemini), Maps JavaScript |

**Environment variables** (`.env`, gitignored; `.env.example` in repo):
- `GEMINI_API_KEY`
- `GCP_PROJECT`

**Deploy:**
```
gcloud run deploy daysupply --source . --region asia-south1 \
  --min-instances 1 --allow-unauthenticated
# --min-instances 1 for the submission window; drop to 0 afterwards.
```

**Health check — read this before wiring any monitor.**

`/healthz` **does not work in production.** Google's frontend intercepts that
exact path and returns a Google-branded 404 without the request ever reaching
the container. The giveaway is that the 404 response carries no
`server: Google Frontend` header, while real responses do — and `/healthz2`,
`/healthz/` and `/health` all pass through normally.

| Path | Local | Cloud Run |
|---|---|---|
| `/healthz` | works | **intercepted, 404** |
| `/api/v1/healthz` | works | **works — use this** |

Both are served by the same handler in `app/main.py`. Probe
`/api/v1/healthz` in production and in any uptime check.

**Run locally:**
```
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Hard-refresh (`Ctrl+Shift+R`) when testing frontend changes — the Service Worker
caches aggressively.

**Cost rules:** never `SELECT *` on the facility table; flag before any query
scanning >10 GB or training >5,000 series; keep `--min-instances 0`.

---

## 8. Work queue

Full detail in `BUILD_PROMPT_BLOCKS_A-E.md`. Summary:

- **Block A — real data.** Load all 200,438 facilities into BigQuery, populate
  `population_served`, rewire dashboard filters and counts to query BigQuery,
  delete `app/demo_data.py`. Assert row counts and fail loudly. *Serves "Depth &
  Reach Across India" (~20%).*
- **Block B — real forecasting.** Generate `stock_events` for demo facilities
  only (partitioned by date, clustered by facility), train a real ARIMA_PLUS
  model, serve via `ML.FORECAST`, purge the word "simulated". *Serves Technical
  Execution (25%).*
- **Block C — supply-chain logic.** Lead-time-aware reorder points
  (`avg_daily_demand × lead_time + safety_stock`), VEN classification weighting
  alerts, FEFO in redistribution, therapeutic substitution via ATC codes,
  reporting-consistency score per facility.
- **Block D — positioning.** Cross-district pattern exchange; an export endpoint
  and architecture diagram showing StockPulse as a capture/intelligence layer
  **above** existing DVDMS/e-Aushadhi systems rather than a replacement.

**If time runs short, protect in this order:** deployed URL, voice capture, a
specific transfer recommendation, review queue. Then real BigQuery data, then
real ARIMA_PLUS, then lead-time-aware thresholds. Everything else is optional.

---

## 9. Open issues

1. **Naming inconsistency.** UI says StockPulse; repo, GCP project and URL say
   daysupply. Either redeploy under a `stockpulse` service name or add a line to
   the README explaining the rename. A judge will notice the mismatch.
2. **Expiry tracker has no data source.** Either drop it or implement FEFO
   (Block C) so it becomes part of the logic rather than decoration.
3. **Scope items not in the original spec** — barcode scanning, expiry tracking,
   five-state filter — were added during the UI sprint. Barcode is justified
   (degradation hierarchy: tap → barcode → voice → chat → photo → sms). Expiry needs Block C to earn
   its place.
4. **Deck and video script live outside the repo.** Move to `docs/`.
5. **"India and the Global South"** copy predates the scope change. Remove.
6. **Lead-time data does not exist publicly.** Block C derives it from distance
   to district HQ. This is a proxy and must be labelled as an assumption in
   `Data/README.md`, never presented as measured.
7. ~~`Data/README.md` does not exist yet.~~ **Done.** It records provenance and
   every real-vs-generated decision, and is now tracked in git.

8. ~~**50,697 Brazilian facility rows in `facilities`.**~~ **Resolved
   2026-09-01.** They predated the India-only scope change and survived the
   loader rewrite, because `load_facilities.py` deletes and re-appends only
   `country_code = 'IN'` — by design, so a re-run cannot touch anything else.
   They were **inert**: every application query filters, and none counted rows
   unfiltered, so no published figure was ever inflated by them. But
   `SELECT COUNT(*) FROM facilities` returned **251,135** against a published
   **200,438**, and explaining that costs more than the rows are worth.

   **Deleted.** `COUNT(*)` is now 200,438, one country code, 200,438 distinct
   facility ids. `load_facilities.py` asserts both conditions — the India rows
   match the source file *and* an unscoped `COUNT(*)` gives the same number —
   so the gap cannot reopen silently. `geo_summary` was rebuilt (738 → 738
   rows; it already filtered to India, so its figures were always correct).

   `Data/Brazil/` and `ingestion/load_brazil.py` are **retained on disk,
   untouched**. They are the evidence for the architecture claim that the
   `config/` layer makes another country a configuration change rather than a
   rewrite. That claim is about the code, and the code is still there; it never
   required foreign rows in a production table.


9. ~~**BLOCKING FOR THE DEMO — voice and chat return 403 in production.**~~
   **Resolved 2026-09-01.**

   There were **two independent failures**, and neither was visible from the
   other:

   1. **The SDK.** `app/capture.py` used `google-generativeai`, the older
      library. Current AI Studio keys begin with `AQ.` — the Auth key format
      Google migrated to in June 2026 — and they fail against that library.
      Migrated to `google-genai`.
   2. **The model was shut down.** The pin was `gemini-1.5-pro`, which Google
      has since retired; every request returned 404 whatever the key did. Even
      a perfect key against the right SDK would still have failed. Repinned to
      `gemini-3.6-flash`.

   **A wrong turn worth recording.** An earlier diagnosis here read the `AQ.`
   prefix as evidence the key was a GCP-console key rather than an AI Studio
   one, and concluded the fix was to enable `generativelanguage.googleapis.com`
   and widen the key's API restrictions. That was wrong in two ways: `AQ.` is
   the *current* AI Studio format, and the reasoning had also matched a key
   listed by `gcloud services api-keys list` against the deployed key without
   checking they were the same key. Neither project setting needed changing.

   Verified live after the fix — see §9a for the pin and its verification date.

9a. **Model pin — record the date, because pins go stale.**

   | | |
   |---|---|
   | **Pinned model** | `gemini-3.5-flash` (since 2026-09-29) |
   | **Verified working** | **2026-09-01**, against the live Cloud Run service |
   | **Fallback chain** | `gemini-3.6-flash`, then `gemini-3.1-flash-lite`. `gemini-2.5-flash` returned 404 "no longer available to new users" on 2026-09-29 and was removed; a 404 now skips to the next model |
   | **Override** | `GEMINI_MODEL` env var — no code change needed |
   | **SDK** | `google-genai` (the older `google-generativeai` is gone) |

   Why this one: GA rather than preview, and Flash-class is the right weight
   for short multilingual audio into a small JSON payload. Not `gemini-3.7-flash`,
   which is newer but tuned for coding and agentic work. Not the Gemini 3 Pro
   line, still in preview.

   **This pin already went stale once and it cost a working feature.** The
   previous pin was `gemini-1.5-pro`, which Google shut down; every request
   returned 404 regardless of the API key. That was a *second* failure sitting
   underneath the 403, and neither was visible from the other. **Re-verify the
   pin against the current model list before each deployment and before the
   submission, and update the date in this table when you do.** The same note
   is in the `app/capture.py` docstring.

   Dedicated speech models now exist (`gemini-3.5-transcribe`, 85+ languages,
   utterance-level language detection). Deliberately not used: we need
   structured extraction in one hop, not transcription followed by a second
   parse. Revisit only if Hindi accuracy proves poor.

9b. **⚠️ `gemini-3.6-flash` returned intermittent 503s during live testing.**
   `503 UNAVAILABLE — "This model is currently experiencing high demand"`, on
   roughly half the requests in a short burst on 2026-09-01. Verified transient:
   the same request succeeded on retry. **There is no retry in the code.** A
   capture that hits a 503 currently surfaces the raw error to the health
   worker and the extraction is lost.

   Two things follow, neither done:
   - **Add a bounded retry with backoff** around `process_audio` and
     `process_text`. This is the single highest-value robustness fix left.
   - **Do not record the demo video in one take against the live model.** A 503
     mid-demo is a coin flip. Either pre-record the capture segment, or have
     `GEMINI_MODEL=gemini-2.5-flash` ready as a fallback if 3.6 is congested.

9c. **⚠️ The capture loop is not closed — nothing a health worker captures ever
   reaches the ledger.** Two separate gaps, found while testing the migration:

   1. **The Firestore database does not exist.** Every capture returns
      `"persisted": false` with
      `404 The database (default) does not exist for project daysupply`.
      Extraction, matching, the confidence gate and routing all work — the
      result is simply never stored. Fix:
      `gcloud firestore databases create --location=asia-south1 --project daysupply`.

   2. **Even with Firestore created, there is no path from it to BigQuery.**
      `capture_pipeline.persist()` writes to the Firestore collections
      `pending_events` and `review_queue`. `pending_events` is **read by
      nothing** — `grep` finds exactly one reference, the write itself. Meanwhile
      `quality.captures_today()` counts from BigQuery `resource_events`.

   So `captures_today` reads **0** and would keep reading 0 even after Firestore
   exists. In a demo you can speak into the app, watch the extraction come back
   correctly, and the dashboard number never moves. **This is the most likely
   thing a judge notices**, because it is the one place the product's own story —
   capture flows upward into the supply chain — is not actually wired.

   Closing it needs a writer from `pending_events` into `resource_events` after
   review approval. Not built; it is a design decision about whether approval is
   synchronous or batched, and that is the owner's call.

9d. ~~**The capture loop is closed as far as the ledger, not as far as
   stock.**~~ **Closed fully, 2026-09-02.** Verified live: a capture moves the
   counter, on-hand *and* the alert.

   `current_stock` and `reorder_status` are now **views**, not tables:

   * `current_stock` derives FEFO batch positions from the ledger at read time.
     Measured cost **149.6 MB / $0.00085 per query**; a thousand dashboard
     queries a day is about **$26/month**, and `app/bq.py` caches on top. At
     this volume correctness is worth far more than the compute.
   * `reorder_status` had to be split, because `ML.FORECAST` is a table-valued
     function and BigQuery will not allow one inside a view. Demand and
     variability — slow-changing, model-derived — now live in a table,
     **`demand_baseline`**. Everything that depends on on-hand is computed in
     the view. Same name, same columns, current numbers.

   **A trap that would have made the view useless.** A captured receipt has no
   expiry date, and the old batch query filtered `expiry_date IS NOT NULL`. It
   would have dropped every captured receipt while still counting it in the
   ledger balance — permanently unreconcilable, and on-hand still frozen.
   Undated batches are now included and ordered **last** in FEFO (`NULLS LAST`),
   which is the conservative reading: a batch whose expiry is unknown cannot be
   claimed to expire soon.

   **A second trap, one layer up.** With the views correct, `/api/v1/alerts`
   still reported the facility stocked out while `reorder_status` said
   `on_hand = 1000, status = ok` — the API response was cached. `app/bq.py`
   now exposes `invalidate_stock_reads()`, called after every ledger write,
   which drops the stock-dependent cache prefixes and deliberately leaves the
   geography pre-aggregate alone (~0.8s to rebuild, and no capture can change
   it).

9e. **⚠️ DESIGN CONSTRAINT: do not build a delete or retract button.**

   Rows written by `insert_rows_json` sit in BigQuery's streaming buffer,
   queryable by `SELECT` immediately but **immune to `DELETE` and `UPDATE` for
   up to ~90 minutes**. This is not a bug to work around; it is how streaming
   inserts behave.

   Observed for real on 2026-09-02: a bad row was deleted, the `DELETE`
   reported success and affected rows, and the row was still there afterwards.

   So a retract button would *appear* to work and silently not — the worst
   possible failure for a correction feature, because the user believes the
   bad number is gone. **Nothing currently offers retraction, and nothing
   should.** If a correction workflow is ever needed, the honest shapes are:

   * a compensating event (a `dispensed` or adjustment row that nets it out),
     which is what an append-only ledger is for; or
   * a `status` column plus a filter, so a retracted row stays in the ledger
     and stops counting.

   Both keep the audit trail. Neither pretends a row can vanish.

9f. **A `count` event does not reset on-hand.** "Amoxicillin khatam ho gaya" —
   we are out of amoxicillin — extracts correctly as `quantity 0,
   event_type 'count'` and writes to the ledger, but the balance arithmetic
   only nets `received - dispensed - expired`. A stocktake that contradicts the
   ledger is therefore recorded and ignored.

   This is a genuine semantic gap, not a defect: making a stocktake authoritative
   means the ledger stops being purely additive, and that is a design decision
   about which source wins. Flagged rather than built. **In a demo, prefer
   "we received N" over "we're out of X"** — the first moves the dashboard, the
   second does not.

10. **Deck and video still to build**, and both must draw every figure from
    `docs/CLAIMS.md`. Any number not in that file does not go in front of a
    judge.

---

## Two front-end traps that cost a day each, and the tests that now pin them

Both shipped to production. Both left the page **parsing cleanly, every
endpoint returning 200 in under a second, and the landing view completely
blank.** They look identical to a slow backend, and both times that is what
they were mistaken for.

### 1. `window.x = () => x()` is infinite recursion, not an export

```js
window.loadExecutive = () => loadExecutive();   // NEVER DO THIS
```

A function declaration at the top level of a classic script is *already* a
property of `window`. The assignment therefore **replaces** it, and the
identifier inside the arrow resolves back through the scope chain to the global
object — which now holds the arrow. It calls itself until the stack dies.

All three of the landing view's loaders had this line: `loadExecutive`,
`loadAlerts`, `loadTransfers`. The `RangeError` is thrown at *call* time,
before the function body runs, so the `try` inside never caught it and
`setSyncState()` fired on neither the success nor the failure path — hence a
sync badge frozen on "Loading…".

`window.onStateChange = onStateChange` — a direct reference, no arrow — is
correct and unaffected. Pinned by `TestNoSelfReferentialGlobalWrapper`.

### 2. A DOM shim cannot find either of these

Two hand-written DOM shims reported the page rendering perfectly while it was
dead in the browser, because **a shim's `global.window` is an ordinary object,
not the real global object** — so the clobber above simply does not happen
there. A shim also has to stub `document.querySelector`, and stubbing it to
return the active view hardcodes the answer to the very question the dispatcher
asks.

**Use a real browser.** No install needed:

```bash
chrome --headless=new --disable-gpu --virtual-time-budget=25000 \
  --user-data-dir=/tmp/prof --enable-logging=stderr --v=1 \
  --dump-dom https://<service-url>/ > dom.html 2>err.txt
grep -i "Uncaught\|CONSOLE" err.txt
```

That surfaced the RangeError with its line number on the first run, after two
shims had said the code was fine. The `CacheStorage: Unexpected internal error`
line in that output is a headless-profile artefact, not a page bug.

### 3. Cross-file dependencies on the init path

`app.js` loads first and its init IIFE runs immediately, so anything it calls
must already exist. `loadExecutive()` called `signalBadge()` from `surge.js`,
loaded on the *next* script tag — a race that surge.js usually won, so the
failure looked intermittent. Either move the helper into `app.js` or guard the
call with `typeof x === 'function'`, as `loadSurge` and `loadSurgeBanner` do.
Pinned by `TestAppJsDoesNotDependOnAFileThatHasNotRunYet`.

**A related trap in the tests themselves:** the DOM checks read a hardcoded
`("app.js", "surge.js")`. Adding `map.js` made them fail on handlers that were
perfectly well defined — the test could not see the file. They now read
whatever `index.html` actually loads.
