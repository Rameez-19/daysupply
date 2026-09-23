# StockPulse — pitch deck (11 slides)

Slide-by-slide content. Every figure is from [`CLAIMS.md`](CLAIMS.md); the
section is given in brackets so a slide can be checked before it is shown.
Speaker notes are in *italics*.

---

## 1. Title

**StockPulse**
The stock report a health worker can make with a thumb, and the forecast,
warning and transfer that come out of it.

Build with AI: Code for Communities, 2nd Edition · Track 3 · Smart Health &
Supply Chain Resilience

Live: https://daysupply-898541549182.asia-south1.run.app

*One line: India has 200,438 health facilities in its register and no
per-facility daily stock data anywhere. This is the layer that captures it and
the intelligence that runs on it.*

---

## 2. The problem

- A primary health centre runs out of a medicine, and nobody above it knows
  until a patient is turned away.
- The person who could report it is a pharmacist or an ASHA at the end of a
  shift, with a phone, in a language that is not the form's.
- Demand has a shape: Albendazole peaks at **22.64× its mean** on National
  Deworming Day; malaria demand swings **4.52×** across the year [§6]. A flat
  reorder rule cannot see either coming.
- Public data stops at the district and the month. The daily, per-centre
  position, the one that decides whether a shelf is empty tomorrow, is not
  published by anyone.

*The root cause is capture, not analytics. Until the report exists, nothing
downstream can be real.*

---

## 3. The solution in one picture

```
Report (tap · speak · photo · scan · type · SMS)
   → Gemini reads, the catalogue matches, the worker confirms
      → BigQuery ledger
         → ARIMA_PLUS forecast (3,818 series)
            → reorder point μ×L + 1.65σ√L
               → 765 shortages → 685 transfers, 36 orders, 44 escalations
                  → early warning when demand has begun to surge
```

Districts exchange **seasonal shape, not data**: pooling cuts forecast error
from **21.1% to 15.6%** wMAPE across six states [§0].

---

## 4. Who it serves

| Person | Page | What they get |
|---|---|---|
| Pharmacist / ASHA at a PHC | Report | 39 medicine tiles, the whole page in English, Hindi, Marathi, Telugu or Bengali, a keypad, a spoken read-back, and offline that says what is waiting |
| Medical officer | Report | The review queue: what the model held back and why |
| District programme officer | Today, Action queue | Availability **80.0%**, life-saving availability **80.3%**, and every shortage sorted by what can be done [§0] |
| State supply-chain cell | Plan ahead, Map, Network | Demand outlook, surge warnings, transfers across district lines (**520 of 685** cross one) [§0] |

**Reach:** 200,438 facilities, 37 states/UTs, 701 districts in the register;
**260.8 million people** in the demand-data footprint, across six states and 191 forecast districts [§0].

---

## 5. Google AI doing the work

| Where | What | Guard |
|---|---|---|
| **Gemini** (`gemini-3.6-flash`) | Speech and typed notes in Hindi, Marathi, Telugu, Bengali, English or a mix, and photographed register pages → structured stock events | The model never returns a drug code. Names are matched server-side against all 385 NLEM medicines; below 0.6 confidence a human decides [§3] |
| **Gemini** | Drafts the escalation note for each shortage nothing routine will fix | Every number in the draft is checked against the row; a stray figure is flagged, never hidden [§7g] |
| **BigQuery ML ARIMA_PLUS** | 3,818 demand series, 12 auto-selected orders, 2,951 with a detected weekly cycle | `ML.ARIMA_EVALUATE` on the Evidence page, not a screenshot [§4a] |
| **BigQuery GIS** | Distance to district HQ → lead time; 150 km transfer radius; the full register on the map | Days-per-km is a documented proxy and the page says so [§7] |

*If the model is unsure, it asks a person. If the draft strays from the data,
the page says so beside it.*

---

## 6. Capture: six ways in, one pipeline

- **Tap** what happened → which medicine → how many. No reading beyond a
  name, no typing beyond a number.
- **Speak** in Hindi, Marathi, Telugu, Bengali, English or a mix. **Type** it the same way.
- **Photograph** the stock register: every row shown for checking, never
  written unconfirmed.
- **Scan** a barcode. **SMS** to the endpoint a gateway would call.
- **Read back** in the chosen language, spoken by the phone, before anything
  is saved.
- **Offline**: a sentence and a count of what the phone still holds.

Also captured: **staff on duty today** and **beds in use right now**, as the
only attendance and occupancy counts the system holds as fact [§7g, §8a].

---

## 7. Forecast and early warning

- **ARIMA_PLUS in BigQuery ML**, trained on the project's own ledger, 76.4%
  of the 5,000-series ceiling [§4].
- **21 HMIS drivers loaded, 20 used** by forecast items: real monthly
  morbidity from MoHFW shapes the demand [§4].
- **Early warning** when demand has begun to surge: a modified-z rule that
  fires where a 3-sigma rule cannot. On twelve monthly points the classical
  statistic is bounded at **3.175**; ours reached **306.5** [§0].
- **2,352 surges** from **90,780** district-month series (2.6%) [§0].
  Brihan Mumbai, January: **2,345 observed vs 938.4 expected**, 2.50×; a
  flat average would have said 1.67× [§0].
- Under a surge, needs-reorder goes **208 → 447**; in **331 of 673** surge-hit lines an order
  cannot arrive in time, so only a transfer can serve them [§0].

---

## 8. Redistribution and the action queue

- **765 shortages**, each in exactly one of three states [§0]:
  **685** a transfer is waiting · **36** an order arrives in time ·
  **44** nothing routine works.
- Transfers are FEFO by batch, donor-protected, within 150 km:
  **88,578 units**, 150 life-saving, 1 therapeutic substitution [§0].
- Every transfer has a lifecycle: approve → dispatch → receive, and stock
  moves in the ledger when it does.
- Waste avoided by FEFO, priced at NPPA ceilings: **Rs 49,786**, about
  **Rs 181 per PHC per year** on modelled units [§0].
- The 44 escalations each carry a **drafted note**, grounded and checked, in the officer's language.

---

## 9. What is real, and what is not

| Real | Modelled or generated, and disclosed |
|---|---|
| 200,438 facilities, every row [§1] | The daily stock ledger, generated from real drivers because no one publishes it [§12] |
| HMIS 2019-20 morbidity, 21 drivers [§4] | Bed occupancy, from real admission volumes × an assumed stay [§12] |
| 385 NLEM medicines; NPPA ceiling prices [§3, §7f] | Lead time: real distance, assumed days-per-km [§7] |
| Rural Health Statistics 2021-22 staffing [§8] | Nothing else. Generated attendance was deleted from the warehouse, not hidden [§8a] |

*Every generated element is listed in `Data/README.md` with its anchor.
A judge can check any figure on this deck against `docs/CLAIMS.md`.*

---

## 10. Deployable in weeks, in any state

- **Runs today** on Cloud Run with BigQuery, Firestore and Gemini; no
  servers to stand up. One `gcloud run deploy`.
- **Data a state already has**: the facility register, HMIS, the NLEM, its
  own stock register. Loading a new state is the ingestion scripts against
  those files; the country and geography abstraction is in `config/`.
- **Nothing to install on the phone**: a PWA that works offline, in five languages today; each further language
  is one dictionary.
- **Fits the workflow that exists**: the review queue is the pharmacist's
  check; the escalation note is what the district officer already writes;
  SMS is the endpoint a state's gateway would call.
- **Guard rails are in the code**: series ceiling, never `SELECT *` on the
  register, every figure traceable.

---

## 11. Scaling across India

- The forecast layer scales by series; the shape exchange is why a new
  district starts with a usable seasonal pattern before it has history:
  the pooled vector beat a district's own flat baseline by **5.5 points**
  and a cross-state twin lost by **25.4 points** [§0]. Shape travels; raw
  data does not have to.
- **Uttar Pradesh was added in one working session** with the runbook in
  `docs/ONBOARD_A_STATE.md`: 75 districts, 1,024 new series, and none of
  the original 2,794 stock lines changed status [§0].
- 275 forecast PHCs in 6 states run today; the register already holds all
  29,733 PHCs, and the map already draws 34,935 centres [§1, §7a].
- What would change first at national scale: per-facility catchments (none
  published), a phone-number register for SMS, and a state's real lead
  times replacing the distance proxy.

**StockPulse** · https://daysupply-898541549182.asia-south1.run.app
