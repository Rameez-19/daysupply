# StockPulse — Project Handover

> Supersedes the agent-written handover. Now at `docs/HANDOVER.md`.
> Read alongside `docs/MASTER_PROMPT.md` (governing spec) and
> `BUILD_PROMPT_BLOCKS_A-E.md` (the work queue).
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
| Gemini voice extraction | **REAL, BLOCKED IN PROD** | Code and tests are real; the production call returns 403. Cause not yet settled — leading hypothesis is the SDK (`google-generativeai` vs the current `google-genai`), not the key. See §9.9 |
| Offline queue + sync | **REAL** | Service Worker + IndexedDB, genuinely works offline |
| PWA / dashboard UI | **REAL** | Vanilla JS, Chart.js, deployed and functional |
| Barcode scanning | **REAL** | `html5-qrcode` |
| Review queue | **REAL** | Confidence-threshold routing. Falls back to three **labelled** worked examples when nothing real is pending (`is_example_data: true`) |
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
| **`captures_today`** | **REAL** | Counted from capture-sourced ledger events. Currently **0**, and legitimately so |

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
│   ├── capture.py       Gemini audio → structured JSON
│   ├── demo_data.py     ⚠️ seeded generator — TO BE REPLACED by BigQuery
│   └── ...
├── web/
│   ├── index.html       SPA: dashboard, filters, charts
│   ├── app.js           views, Chart.js, MediaRecorder, IndexedDB queue
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
  --min-instances 0 --allow-unauthenticated
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
   (degradation hierarchy: barcode → voice → chat). Expiry needs Block C to earn
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


9. **⚠️ BLOCKING FOR THE DEMO — voice and chat return 403 in production.**
   Verified on the live service, 2026-09-01. `GEMINI_API_KEY` **is** set on
   Cloud Run, so the previously logged "key not set" issue is closed.

   Symptom: `403 … API_KEY_SERVICE_BLOCKED` from `/api/v1/voice-note` and
   `/api/v1/chat-note`. Everything else in the capture pipeline is fine —
   barcode works end to end and correctly routes an unrecognised code to the
   review queue with a reason.

   **The full diagnosis, including a correction to an earlier wrong reading of
   the key format, is in §9.9 below.** Short version: `AQ.` is the *current* AI
   Studio key format, not a GCP-console marker, and the leading hypothesis is
   the SDK (`google-generativeai` vs `google-genai`) rather than the key.

   Two fixes, either sufficient — full commands in `README.md` under
   *Environment*:
   - **A (simplest):** issue a key at `aistudio.google.com/apikey` and set it.
   - **B (stay in this project):**
     `gcloud services enable generativelanguage.googleapis.com --project daysupply`,
     then add that service to the key's API restrictions.

   **Until this is fixed the demo video cannot show a live voice capture.** The
   three capture modes degrade as designed — barcode still works — but voice is
   the headline of the product and it must be working before recording.

10. **Deck and video are still outside the repo and must be rebuilt against
    `docs/CLAIMS.md`.** Several figures in any existing draft are now wrong:
    FEFO waste is 26,612 (44.7%) not 94,542 (57%); wMAPE is 19.4/71.2/16.4/14.4
    not 25.8/45.1/32.5/23.2; malaria amplitude is 4.52x not 3.9x; Albendazole is
    22.64x with a 5.66x August spike, not 22.3x and 6.24x; the district count is
    701, not 668. `docs/CLAIMS.md` is the single source of truth — anything not
    in it does not go in front of a judge.

9. **Voice and chat capture return 403 in production — diagnosis open.**
   `GEMINI_API_KEY` **is** set on the Cloud Run service, so the older "not set"
   note is out of date. `/api/v1/voice-note` and `/api/v1/chat-note` return
   `403 API_KEY_SERVICE_BLOCKED` from `generativelanguage.googleapis.com`.

   **Key format — a correction.** Current Google AI Studio keys begin with
   **`AQ.`**, the Auth key format Google migrated to in June 2026; the older
   `AIza` Standard keys are being rejected outright from September 2026. An
   earlier version of this section read the `AQ.` prefix as evidence that the
   key came from the GCP console rather than AI Studio. **That was wrong** —
   AI Studio issues only `AQ.` keys now, so the prefix says the key is current.
   The reasoning was also unsound independently of the format question: it read
   one key out of `gcloud services api-keys list` and assumed it was the one
   deployed, without matching them.

   **Leading hypothesis: the SDK, not the key or the API.** `app/capture.py`
   uses `google-generativeai`, the older library, and `AQ.` keys are widely
   reported to fail against it. The current library is **`google-genai`**.

   **Test that separates the two cases**, run before changing anything:
   ```
   curl.exe -H "x-goog-api-key: AQ.KEY" "https://generativelanguage.googleapis.com/v1beta/models"
   ```

   | Result | Meaning | Fix |
   |---|---|---|
   | Model list | Key and API are fine; the SDK is the problem | Migrate `app/capture.py` to `google-genai` |
   | 403 | The API is genuinely blocked for this key | Enable `generativelanguage.googleapis.com` and/or widen the key's API restrictions |

   **No SDK change has been made** — it waits on that result.

   **If the migration is the fix, the surface is small.** The entire Gemini
   dependency is five lines in `app/capture.py`:

   | Line | Now |
   |---|---|
   | `capture.py:5` | `import google.generativeai as genai` |
   | `capture.py:13` | `genai.configure(api_key=...)` |
   | `capture.py:15` | `genai.GenerativeModel('gemini-1.5-pro')` |
   | `capture.py:57` | `model.generate_content([...])` — audio |
   | `capture.py:71` | `model.generate_content(...)` — text |

   plus `google-generativeai` in `requirements.txt:6`. Nothing else imports the
   SDK. `app/capture_pipeline.py` holds the matching, confidence gate and
   routing — all model-independent, all covered by tests that never call
   Gemini, so a migration cannot silently damage the extraction logic.

   **Review the pinned model at the same time.** `gemini-1.5-pro` is several
   generations old; if `app/capture.py` is being opened anyway, that is the
   moment to move to a current model rather than porting the old pin forward.

   **Barcode is unaffected** and verified working in production — an
   unrecognised code correctly routes to the review queue with a reason. The
   extraction pipeline, matcher and confidence gate are exercised by 186
   passing tests; only the production model call fails.

   **This must be fixed before the demo video is recorded.** Voice is the
   product's opening claim.

10. **Deck and video still to build**, and both must draw every figure from
    `docs/CLAIMS.md`. Any number not in that file does not go in front of a
    judge.
