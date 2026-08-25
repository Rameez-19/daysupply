# DaySupply 📦🎙️

> **Voice-first medicine stock reporting & redistribution for primary health centres.**

Built for the **Build with AI: Code for Communities, 2nd Edition** hackathon.

## The Problem
Public health systems know what they hold in aggregate and almost nothing about where it is right now. A district warehouse can hold six months of a drug while a health centre 40 km away turns patients away. The root cause is *capture*, not analytics: the person expected to record stock is a pharmacist or nurse running a clinic alone, often without connectivity, for whom data entry is unpaid overtime. Entries are late, batched, or fabricated — and every dashboard above them inherits that.

## The Solution
**DaySupply** solves this from the ground up:
1. **Zero-friction capture**: A 30-second voice note in Hindi or Portuguese natively in the browser. Works offline via IndexedDB, syncs when online.
2. **Gemini Extraction**: Voice is converted directly to structured JSON inventory events.
3. **BigQuery ML Forecasting**: We forecast at the facility level using `ARIMA_PLUS` on real demand drivers to predict stockouts.
4. **Redistribution Engine**: We match imminent deficits with nearby surpluses and generate actionable transfer recommendations.
5. **Federated Pattern Exchange**: Countries exchange seasonal demand patterns (not patient data!) to improve forecasts globally.

## Architecture
- **Frontend**: Vanilla JS PWA (Service Workers, IndexedDB, MediaRecorder API).
- **Backend**: FastAPI on Google Cloud Run.
- **AI**: Gemini Multimodal Audio for extraction, BigQuery ML for forecasting.
- **Data**: Real facilities & population data from India and Brazil, simulated daily events.

## Setup & Running

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the FastAPI + Static File server
uvicorn app.main:app --reload

# 3. Open in browser
http://127.0.0.1:8000
```
