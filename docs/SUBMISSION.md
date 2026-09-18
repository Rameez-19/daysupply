# Submission — Build with AI: Code for Communities, 2nd Edition

Track 3 · Smart Health & Supply Chain Resilience · solo submission.

Every figure below is taken from [`CLAIMS.md`](CLAIMS.md), which names the
query or script each one comes from. If a number is not in that file, it is
not evidence and is not used here.

## The 2–3 line description

> **StockPulse** lets a health worker at any of India's primary health centres
> report medicine stock, beds in use and staff on duty by tapping, speaking,
> photographing the register or texting, in Hindi or English, and turns those
> reports into a BigQuery ML forecast, an early warning when demand has begun
> to surge, and a worked-out transfer or order for every shortage. It runs on
> the real 200,438-facility government register and real HMIS demand, and
> districts improve each other's forecasts by exchanging seasonal shape, not
> data: pooling cuts forecast error from 19.4% to 14.4%.

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
| **Report** | The health worker's page: tap, speak, photo, scan, type, staff, beds. Read-back in Hindi or English before anything is written. | 39 tiles; nothing written unconfirmed |
| **Today** | The supply chain as a scorecard, national to a single centre. | 78.6% availability; 77.7% for life-saving medicines |
| **Plan ahead** | Demand outlook from ARIMA_PLUS; early warnings; scenario mode against real stock. | 2,794 series; 1,295 surges from 58,932 series-months |
| **Action queue** | Every shortage sorted by what can be done: moved, ordered, or neither. Draft note on each escalation. | 597 shortages: 527 transfers, 39 need escalation |
| **Map** | Every centre in the register, and the transfers between them. | 34,935 centres drawn; 362 of 527 transfers cross a district line |
| **Evidence** | The ARIMA_PLUS chain, the four-arm hold-out, the lead-time contrast. | 19.4% → 14.4% |

## Language rules (from CLAIMS §11a)

- Say "districts exchange seasonal shape, not data", never "federated learning".
- Say "we detect that a surge has begun, earlier and more reliably than a
  3-sigma rule, which on twelve monthly observations cannot fire above 3.175".
  Never "predicts outbreaks".
- Say "21 HMIS drivers loaded, 20 used".
- Say "701 districts", not 668.
- Say "151.7 million people in the demand-data footprint"; 793.7 million is
  *addressable* and must be said with that word.
- Bed occupancy is modelled from real admission volumes; say so when it is
  on screen. The daily stock ledger is generated from real drivers because no
  country publishes per-facility daily stock, and that is the gap the
  product exists to close.
