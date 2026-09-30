# Submission — Build with AI: Code for Communities, 2nd Edition

Theme: **Resilience** · Track 3, Smart Health & Supply Chain Resilience ·
solo submission.

## Mandatory checklist

| Requirement | Where it is met |
|---|---|
| **Theme alignment** | Resilience, Track 3. Every line of the track's brief maps to a working feature: medicine stock, beds and staff, demand forecasting, early warning, cross-district redistribution, and modelling shared across states. See the deck, slide 4. |
| **Public GitHub repository**, with the app logic, prompt configuration and running instructions | App logic in [`app/`](../app) and [`web/`](../web); every Gemini prompt and the model chain in [`prompts/`](../prompts), with an edge-case eval in [`evals/`](../evals); running instructions in [README → Running StockPulse](../README.md#running-stockpulse); every dataset in [`DATA_SOURCES.md`](DATA_SOURCES.md) |
| **Architecture overview**: Google Cloud (Cloud Run, Firebase) with the Gemini API | [`ARCHITECTURE.md`](ARCHITECTURE.md): Cloud Run hosts the app and API, Gemini on Vertex AI reads reports and drafts notes, Firestore (Firebase) holds the review queue, BigQuery and BigQuery ML hold the ledger and the forecasts, Cloud Text-to-Speech reads reports back. Diagram: [`architecture-google-cloud.png`](architecture-google-cloud.png). Deck, slide 7. |
| **Project pitch deck** | 14 slides and a 4-slide appendix (data sources, all of India, what is real, every tool), organised by the judging criteria (kept outside the repository with the video) |

Before submitting:

```bash
python -m scripts.smoke_test     # 22/22: the web app and the Cloud Run backend talk end to end
python -m scripts.eval_prompts   # 20/20: the extraction prompt on its edge cases
```

Every figure below is taken from [`CLAIMS.md`](CLAIMS.md), which names the
query or script each one comes from. If a number is not in that file, it is
not evidence and is not used here.

## The 2–3 line description

> **StockPulse** lets a health worker at any of India's primary health centres
> report medicine stock, beds in use and staff on duty by tapping, speaking,
> photographing the register or texting, in Hindi, Marathi, Telugu, Bengali or English, and turns those
> reports into a BigQuery ML forecast, an early warning when demand has begun
> to surge, and a worked-out transfer or order for every shortage. It runs on
> the real 200,438-facility government register and real HMIS demand, and
> districts improve each other's forecasts by exchanging seasonal shape, not
> data: pooling cuts forecast error from 21.1% to 15.6% across six states.

## Deployed link

https://daysupply-898541549182.asia-south1.run.app

Cloud Run, `asia-south1`, one warm instance for the submission window. The
service and GCP project are named `daysupply`; the product is StockPulse.

## Source code

This repository. Start at [`README.md`](../README.md), then
[`HANDOVER.md`](HANDOVER.md) for what is real and what is not, and
[`CLAIMS.md`](CLAIMS.md) for every figure.

## What to open in the demo

| Page | What it shows | Figure to say |
|---|---|---|
| **Report** | The health worker's page: tap, speak, photo, scan, type, staff, beds. Read-back in five languages before anything is written. | 39 tiles; nothing written unconfirmed |
| **Today** | The supply chain as a scorecard, national to a single centre. | 80.0% availability; 80.3% for life-saving medicines |
| **Plan ahead** | Demand outlook from ARIMA_PLUS; early warnings; scenario mode against real stock. | 3,818 series; 2,352 surges from 90,780 series-months |
| **Action queue** | Every shortage sorted by what can be done: moved, ordered, or neither. Draft note on each escalation. | 765 shortages: 685 transfers, 44 need escalation |
| **Map** | Every centre in the register, and the transfers between them. | 34,935 centres drawn; 520 of 685 transfers cross a district line |
| **Evidence** | The ARIMA_PLUS chain, the four-arm hold-out, the lead-time contrast. | 21.1% → 15.6% |

## Language rules (from CLAIMS §11a)

- Say "districts exchange seasonal shape, not data", never "federated learning".
- Say "we detect that a surge has begun, earlier and more reliably than a
  3-sigma rule, which on twelve monthly observations cannot fire above 3.175".
  Never "predicts outbreaks".
- Say "21 HMIS drivers loaded, 20 used".
- Say "701 districts", not 668.
- Say "260.8 million people in the demand-data footprint"; 793.7 million is
  *addressable* and must be said with that word.
- Bed occupancy is modelled from real admission volumes; say so when it is
  on screen. The daily stock ledger is generated from real drivers because no
  country publishes per-facility daily stock, and that is the gap the
  product exists to close.
