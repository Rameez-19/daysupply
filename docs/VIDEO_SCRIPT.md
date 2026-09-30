# Demo video script — one video, then the audience tries it

**How the demo runs**

1. **Play the video** (about 4 min 45 s). One screen recording on the
   desktop, explaining the product page by page with the live data. No phone
   on camera.
2. **Then, live: "Now try it yourself."** The audience opens StockPulse on
   their own phones and makes a report, while the big screen shows it land.

Written so that anyone, a fifteen-year-old included, can follow the problem
and how StockPulse solves it. The **voice** stays in plain words. The
**caption** puts the technical name on screen for judges. Every figure is
from [`CLAIMS.md`](CLAIMS.md) §0 unless marked. Live figures move as reports
arrive: check the screen and say what it shows.

---

## The live test data (keep it; the video uses it)

Real reports made through the app during testing. They are in the live
ledger and review queue, and they show on screen. Do not delete them.

| Centre | What was reported | Where it shows |
|---|---|---|
| **Salchapra MPHC**, Cachar, Assam | Typed in Hindi: "paracetamol ki ek hazaar tablet aayi hain", 1,000 received | Paracetamol is its one medicine at a safe level. The video reports here next |
| **Addakal**, Mahbubnagar, Telangana | Typed in Hindi: Paracetamol and Zinc received, "ORS ka aadha dabba", amoxicillin finished, 50 Paracetamol broken | Two folic-acid notes waiting in the review queue |
| A barcode scan, 8901234567890 | A code with no match in the catalogue | The third note waiting in the review queue |
| **Moilan PHC**, Wokha, Nagaland | Voice, tap, staff on duty and beds in use, 29–30 Sept | Reporting works at any of India's 29,733 PHCs, even outside the six forecasting states |
| **Dharmapuri**, Karim Nagar, Telangana | A register photo (Cefixime), and "Salbutamol ke pachas tablet khatam ho gaye" | Photo and typed reports from the field |
| **Moterjhar SD → Fokirgonj MPHC**, Dhubri, Assam | An ORS transfer, dispatched and received | The transfer lifecycle on the ledger |

The Today task bar's **"Check held reports: 3"** is these three waiting
notes (before the video adds one).

## Before recording

- Open the site in a desktop browser, keep the **Explain** switch off, and
  send one typed report in preview a minute before recording. The first
  Gemini call after a deploy can be slow.
- On the **Report** page, choose **Salchapra MPHC** (Assam → Cachar),
  language English, mode **Type**.
- The sentence the video types, checked live on 30 Sept (three runs out of
  three: Salbutamol saved, ORS held): *"Salbutamol ki pachas goli aayi hain,
  ORS ka aadha dabba bacha hai."*
- **Retake?** The first take fixes Salbutamol at Salchapra. For another take
  type *"Zinc sulphate ki sau goli aayi hain, ORS ka aadha dabba bacha hai"*
  (also checked; Zinc is also out there).
- Salchapra before the take: **1 of 18** medicines at a safe level, **14**
  completely out. After it: **2 of 18** and **13**. If a report has landed
  there since, read the screen instead.

---

# The video

## 0:00 – 0:25 · The empty shelf

*On screen:* the deck's title slide, then the problem slide (200,438).

*Voice:* "Imagine walking two hours to a health centre with a sick child and
being told the medicine ran out last week. Nobody knew it was running out:
not the centre, not the district. India's register lists 200,438 health
facilities, and not one of them publishes a daily count of its medicines.
StockPulse fixes that. Reporting takes seconds, and then the system works
out what will run out, where spare stock is, and what to do about it."

*Caption:* StockPulse · Build with AI: Code for Communities · Resilience,
Track 3

## 0:25 – 1:30 · Reporting takes seconds

*On screen:* the Report page, Salchapra MPHC. Switch the language to हिंदी;
the whole page changes. Flick through मराठी, తెలుగు, বাংলা, back to हिंदी.

*Voice:* "This is the page a health worker uses, here at Salchapra, a centre
in Assam. It speaks five languages: English, Hindi, Marathi, Telugu and
Bengali. They can tap a medicine and a number, photograph the paper
register, scan a barcode, or just say it."

*On screen:* in **Type** mode, enter *"Salbutamol ki pachas goli aayi hain,
ORS ka aadha dabba bacha hai"* and send.

*Voice (while Gemini reads it):* "I will write it the way a pharmacist would
tell a colleague: fifty Salbutamol tablets came in, and about half a box of
ORS is left. Google's Gemini AI turns that sentence into a stock report."

*On screen:* the read-back appears and is spoken aloud: Salbutamol 50 to
save, ORS held.

*Voice:* "It reads it back out loud. Fifty Salbutamol: clear. But 'half a
box' is not a number, so instead of guessing, it holds the ORS for the
pharmacist to check. When the AI is not sure, a person decides."

*On screen:* click **"हाँ, सेव करें"**. Scroll to the review queue.

*Voice:* "Nothing is saved until the worker says yes. The ORS joins the
reports waiting for a pharmacist, next to real notes from our field tests.
It even works without internet: reports wait on the phone and send
themselves when the signal returns."

*Caption:* Gemini on Vertex AI · matched to all 385 essential medicines ·
Cloud Text-to-Speech read-back · review queue in Firestore

## 1:30 – 2:05 · The district officer's to-do list

*On screen:* **Today**, national. The task bar, then the tiles. Then filter
Assam → Cachar → Salchapra MPHC.

*Voice:* "This is what a district officer opens every morning. Across the
top, a to-do list: shortages to escalate, transfers to approve, orders to
place, early warnings, and reports waiting for a check. Below, the network:
across 275 centres in six states, 80 percent of medicines are at a safe
level. And here is Salchapra, seconds after that report: completely out has
dropped from 14 to 13."

*Caption:* 275 PHCs, 6 states · availability 80.0%, life-saving 80.3% · one
ledger in BigQuery, updated as reports arrive

## 2:05 – 2:30 · Which districts need help first

*On screen:* **Network**, the two tables side by side.

*Voice:* "The network page ranks every district. On the left, the ones that
need help first; on the right, the ones doing best. Available is the share
of a district's medicines at a safe level. Life-saving is the same for the
medicines that save lives. Out is the share with nothing on the shelf at
all. Red means under 60 percent."

*Caption:* districts with at least eight tracked medicine lines · ranked
worst first

## 2:30 – 3:10 · Seeing trouble coming

*On screen:* **Plan ahead**, the demand outlook, then **Early warnings**.

*Voice:* "Next, a forecast. Like a weather forecast, but for medicines: how
many tablets each centre will need in the coming weeks, based on real
government records of which illnesses rise in which months. And an early
warning. With just twelve months of data, the usual alarm cannot ring at
all, so StockPulse uses a smarter test that catches the weak signal, when
cases are rising but have not exploded. Deworming Day is labelled a planned
campaign, not an emergency. We do not predict outbreaks; we notice early
that one has begun."

*Caption:* BigQuery ML ARIMA_PLUS, 3,818 forecasts · modified z-score; a
3-sigma rule cannot exceed 3.175 on twelve points · 2,352 surges found

## 3:10 – 3:50 · Fixing every shortage

*On screen:* **Action queue**. Click **Draft** on the first escalation. Then
the **Map**.

*Voice:* "Every shortage comes with a plan. Today there are 765. For 685,
another centre nearby has spare stock, so it is moved, the batch that
expires soonest first. For 36, an order arrives in time. For 44, neither
works, so Gemini drafts an escalation note from that shortage's own
numbers, and every number is checked. The AI drafts; the officer decides.
On the map, most transfers cross a district border, something one district
could never arrange alone."

*Caption:* 685 move · 36 order · 44 escalate · 520 of 685 transfers cross a
district line

## 3:50 – 4:10 · Districts learning from each other

*On screen:* **Evidence**, the four-bar chart.

*Voice:* "Districts also improve each other's forecasts. They share only the
shape of their year, when demand rises and falls, never anyone's records.
That cut forecast mistakes from about 21 percent to under 16."

*Caption:* forecast error 21.1% → 15.6% · seasonal shape, not data

## 4:10 – 4:45 · How it is built, and your turn

*On screen:* the architecture poster, then the QR code and URL.

*Voice:* "All of it runs on Google Cloud: Gemini reads the reports, BigQuery
holds the data and the forecasts, and Cloud Run serves the app. It uses real
government data and says plainly which parts are estimated. Data for every
state in India is already in hand; six states run today. A health worker
reports in seconds, and the system does the rest. Now, try it yourself."

*End card:* the QR code (`StockPulse - Try it QR.png`) ·
daysupply-898541549182.asia-south1.run.app

---

# Live, after the video: "Now try it yourself"

Keep the QR code on the big screen, and a second tab on **Today** with the
task bar visible.

*Say:* "Scan the code, or type the address. Open **Report stock**. Pick any
primary health centre, even one near your home: all 29,733 in India are
there. Choose your language, tap **Type** or the microphone, and tell it
some stock came in."

Sentences that are checked to work (each tested live on 30 Sept):

| Language | Say or type | What happens |
|---|---|---|
| English | Paracetamol 200 tablets came in, ORS half a box left | Paracetamol saved; ORS held for a check |
| Hindi | Paracetamol ke do sau tablet aaye hain | Paracetamol 200 received |
| Marathi | पॅरासिटामॉलच्या दोनशे गोळ्या आल्या | Paracetamol 200 received |
| Telugu | పారాసిటమాల్ రెండు వందల మాత్రలు వచ్చాయి | Paracetamol 200 received |
| Bengali | প্যারাসিটামল ২০০টা ট্যাবলেট এসেছে | Paracetamol 200 received |

*Say, while they try:* "It reads your report back before anything is saved.
Tap **Yes, save** to keep it, or **No, start again** to throw it away. If you
said something vague, watch it wait for a pharmacist instead of guessing."

*Show on the big screen:* refresh **Today**. The **Check held reports** count
goes up as the audience's vague reports arrive; the Report page's review
queue lists them.

**Good to know**

- Say "came in", not "given out". Giving out more than a centre has is held
  for a check, which is right, but confusing in a live demo.
- A voice note takes about 8–13 seconds to read and a register photo about
  15. Tell people to wait for the read-back.
- The first time, the phone asks for the microphone; allow it.

---

## Words to use, and words to avoid

- Say "we notice early that a surge has begun". **Never** "predicts
  outbreaks".
- Say "districts share the shape of their year, not their data". **Never**
  "federated learning".
- The daily stock ledger is generated from real drivers, because no one
  publishes one. If asked, say so plainly; it is on the Evidence page and in
  `Data/README.md`.
