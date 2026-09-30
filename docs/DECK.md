# StockPulse — pitch deck (14 slides and a 4-slide appendix)

Slide-by-slide content. Every figure is from [`CLAIMS.md`](CLAIMS.md) §0
unless another section is given, so a slide can be checked before it is
shown. Speaker notes are in *italics*.

**How the slides are built.** The deck follows the judging criteria in
order. Every slide that presents part of the solution opens with a band of
two halves: **the problem** it answers, and **how StockPulse solves it**.
The rest of the slide is the proof: a live screen, a figure, or both.

---

## 1. Title

**StockPulse.** The stock report a health worker can make with a thumb, and
the forecast, early warning and transfer that come out of it.

Build with AI: Code for Communities · Theme: Resilience · Track 3, Smart
Health & Supply Chain. 200,438 facilities · 6 states, 275 PHCs · 5 languages
· Gemini on Vertex AI, BigQuery ML, Cloud Run.

## 2. How this deck maps to the judging criteria

| Criterion | Weight | Slides |
|---|---|---|
| Problem-Solution Fit | 20% | 3 – 6 |
| AI / Technical Execution | 25% | 7 – 10 |
| Depth & Reach Across India | 20% | 11 – 12 |
| Impact Potential | 15% | 13 |
| Deployability & Scalability | 20% | 14, 16 |

Appendix, slides 15 – 18: every data source; all of India is in hand; what
is real and what is not; every tool and technology.

## 3. The shelf empties before anyone knows

- No daily stock data exists: public data stops at the district and month.
- The reporter is at the end of a shift, in a language that is not the form's.
- Demand has a shape a flat rule misses: Albendazole **22.64×** its mean on
  National Deworming Day; malaria swings **4.52×** across the year [§6].
- **200,438** facilities in the register; none publishes a daily stock position.

## 4. The challenge, answered line by line

| Track 3 asks for | StockPulse | Live proof |
|---|---|---|
| Real-time visibility of medicine stock | Five ways to report, offline too; the live stock position moves within seconds | 3,818 lines at 275 PHCs |
| Bed availability and staff attendance | Same pipeline; real RHS 2021-22 establishment | 1,361 posts, 71.6% filled |
| Forecast demand | ARIMA_PLUS per centre and medicine, real HMIS drivers | 3,818 series |
| Early warning | Catches the weak signal a 3-sigma rule misses; names it; reruns supply | 2,352 surges in 90,780 series-months |
| Cross-district redistribution | Expiry-first transfers within 150 km; move, order or escalate | 685 transfers, 520 cross a district line |
| Shared modelling across states | Seasonal shape, not data | 21.1% → 15.6% |

## 5. The solution, end to end

**Problem:** the stock position is never captured. **Solves:** capture in
seconds, then forecast, warn and act on one ledger.
Report → Gemini reads → worker confirms → BigQuery ledger → ARIMA_PLUS →
act. Reorder point **μ × L + 1.65 σ √L**, L from straight-line distance to
the district headquarters.

## 6. Who it serves

ASHA or pharmacist (Report), medical officer (Review queue), district
officer (Today, Action queue: a task bar and changes since the last visit),
state cell (Plan ahead, Map). Screen: the lean Today page.

## 7. Architecture: Google Cloud, end to end

**Problem:** a state needs something it can run, secure and afford.
**Solves:** one Cloud Run service on managed Google AI and data.
Phone and browser → Cloud Run → Gemini on Vertex AI (3.8 → 3.7 → 3.6 → 3.5 →
2.5), Cloud Text-to-Speech, BigQuery · BigQuery ML · GIS, Firestore.
Prompts are files; **20/20** edge cases; **22/22** live endpoint checks.

## 8. Gemini reads reports, writes notes

**Problem:** reports come in the worker's own words, language and
handwriting. **Solves:** Gemini reads speech, text and photos, and drafts the
escalation note. Guards: the catalogue decides the drug; below 0.6
confidence a person decides; every number in a note is checked.

## 9. BigQuery ML forecasts every line

**Problem:** a flat reorder rule misses deworming day and the malaria season.
**Solves:** one ARIMA_PLUS forecast per centre and medicine.
**3,818** series; **12** orders; **2,951** with a weekly cycle; **21 HMIS
drivers loaded, 20 used**. Screen: Evidence (`ML.ARIMA_EVALUATE`).

## 10. Early warning that catches the weak signal

**Problem:** on twelve monthly points a 3-sigma rule can never fire, and a
deworming campaign looks like an outbreak. **Solves:** a modified-z
detector that catches the weak signal, names what fired, and reruns supply.

- **Catches the weak signal:** the classical z is capped at **3.175**; the
  modified z reached **306.5**. **2,352** surges in **90,780** series-months.
- **Names what fired:** early warning (a clinical sign before treatment),
  happening now, or planned campaign. Deworming day is a campaign, not an
  outbreak (`ingestion/build_signal_labels.py`).
- **Says what it does to supply:** needs-reorder **208 → 447**; in **331 of
  673** surge-hit lines only a transfer arrives in time.
- Brihan Mumbai antimalarials, January: **2,345 vs 938.4** expected,
  **2.50×**; a flat average says 1.67×.

*We do not predict outbreaks. We detect that one has begun, earlier and more
reliably than a 3-sigma rule.*

## 11. Built for India's states and languages

**Problem:** a tool in English, for one state, that needs a signal, reaches
almost no one. **Solves:** six states, five languages, offline, any phone.
6 states · 191 districts · 5 languages · **260.8 million** people in the
demand-data footprint.

## 12. States share seasonal shape, not data

**Problem:** a new district has no history, and states cannot pool records.
**Solves:** twelve numbers per medicine class, never records.
**21.1% → 15.6%**; cross-state look-alike **46.5%**; **49,134** predictions.

## 13. Impact: every shortage gets a route to a fix

**765** shortages: **685** move · **36** order · **44** escalate with a
drafted note. **88,578** units; **Rs 49,786** waste avoided (modelled units);
**331** lines only a transfer reaches. Screen: the Map.

## 14. Deployable in weeks, in any state

Uttar Pradesh added in one working session; none of the original 2,794 stock
lines changed status. Five steps, one `gcloud run deploy`. All of India's
data is in hand; six states run by design (Appendix B).

---

## Appendix A. Every data source

Facility directory (NHM, MoHFW) · HMIS 2019-20 (MoHFW) · NLEM 2022 · WHO
ATC · NPPA Compendium of Prices 2022 · Rural Health Statistics 2021-22 and
2017 · IPHS 2022. Generated and disclosed: the daily stock ledger, bed
occupancy, VEN class. Detail: [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Appendix B. All of India's data is in hand; six states run by design

The facility directory is loaded in full; HMIS files for every state and UT
are on disk; staffing, prices, bed norms and medicines are national. The
build runs under a cost guard of **5,000** ARIMA_PLUS series; six states use
**3,818** (76.4%). Every PHC in India would be about **413,000** trained
series, over 80 times the guard. National scale needs per-state models on
reserved BigQuery capacity, a partitioned ledger, Cloud Run and Vertex AI
capacity, and a state's own stock feed. None of it is a redesign.

## Appendix C. What is real, and what is not

Real: the facility directory, HMIS morbidity, NLEM, NPPA prices, RHS
staffing, IPHS norms, and every captured report. Generated or modelled, and
disclosed: the daily stock ledger, bed occupancy, the days-per-km conversion,
VEN class.

## Appendix D. Every tool and technology

The full architecture poster
([`architecture-google-cloud.png`](architecture-google-cloud.png)).
