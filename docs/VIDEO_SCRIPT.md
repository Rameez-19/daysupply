# Demo video script — 3 min 50 s

Screen recording of the live deployment, phone frame for the Report page and
desktop for the rest. Figures are from [`CLAIMS.md`](CLAIMS.md), section in
brackets. Timings are targets; cut the Evidence beat first if over.

Before recording: open the site once so the warm instance has answered; set
the Report page's centre; have a short Hindi-English sentence ready to speak.

---

**0:00 – 0:20 · Cold open (phone, Report page)**

*On screen:* the tap flow. Tap "Stock came in" → tap Paracetamol → type 200 →
the read-back appears and is spoken.

*Voice:* "This is a pharmacist at a primary health centre in India reporting
stock. Three taps, one number, and the phone reads it back before it saves.
No form, no code, and it works in Hindi."

Tap the language toggle; the page and the read-back switch to Hindi. Tap
"हाँ, सेव करें".

---

**0:20 – 0:45 · Why this matters**

*On screen:* Today, national scope, medicine scorecard.

*Voice:* "India's register has 200,438 health facilities [§1]. Nobody
publishes the daily stock position of any of them. So the first job is
capture, and the second is what you can do once the reports exist. Across
the 200 centres running today, availability is 78.6 percent, and for
life-saving medicines it is lower, 77.7 [§7c]. The page says that in words,
because it is the finding that should not be true."

---

**0:45 – 1:20 · The other ways in (phone)**

*On screen:* Speak: hold the mic, say "Paracetamol ke do sau tablet aaye hain,
ORS ke kuch packet khatam". Read-back shows Paracetamol 200 received, and ORS
held for the pharmacist because "kuch" is not a number.

*Voice:* "Gemini reads the speech. It is never asked for a drug code; the name
is matched server-side against all 385 medicines in the National List [§3],
and anything the model is unsure about waits for the pharmacist. Here it heard
'some packets' of ORS and held it rather than guess."

*On screen:* Photo mode, a register page; rows appear for checking. Then
Staff today with the five roles.

*Voice:* "A photograph of the stock register becomes rows to check, never a
direct write. And the same page takes who is on duty and how many beds are in
use, which are the only attendance and occupancy counts the system holds as
fact."

---

**1:20 – 1:50 · Forecast and early warning (desktop, Plan ahead)**

*On screen:* the demand outlook, then the early-warning list.

*Voice:* "Every report lands in BigQuery, where ARIMA_PLUS forecasts 2,794
series [§4]. Demand has a shape: real HMIS morbidity, 21 drivers loaded, 20
used. And when demand has begun to surge, we detect it earlier and more
reliably than a 3-sigma rule, which on twelve monthly points cannot fire above
3.175 [§9]. Brihan Mumbai in January: 2,345 observed against 987.8 expected.
A flat average would have called that 1.67 times; the pooled seasonal shape
says 2.37."

*On screen:* scenario mode, run at 3×.

*Voice:* "Scenario mode recomputes against real stock: at three times demand,
this is how many centres fail and how many can only be served by a transfer
because an order would arrive too late."

---

**1:50 – 2:30 · Redistribution (Action queue)**

*On screen:* the triage bar and the three panels.

*Voice:* "597 shortages, each in exactly one of three states [§7e]: 527 have
a transfer waiting, worked out by batch expiry within 150 kilometres; 33 can
be ordered in time; 39 cannot be fixed by either. Those 39 are the point."

*On screen:* click Draft note on the first escalation. The note appears with
the "every number checked" badge.

*Voice:* "For each of those, Gemini drafts the escalation note from the row's
own figures, and every number in the draft is checked against the row. If it
strays, the page flags it. It writes the note; the officer makes the call."

*On screen:* approve one transfer; the lifecycle advances.

---

**2:30 – 2:55 · Shape, not data (Evidence)**

*On screen:* the four-arm hold-out chart.

*Voice:* "Districts improve each other's forecasts by exchanging seasonal
shape, not data. Against a district's own flat baseline at 19.4 percent
error, pooling every district's shape gives 14.4 [§5]. Borrowing a look-alike
district from another state gives 71.2. Shape travels; raw data never has to
leave the district."

---

**2:55 – 3:25 · Map and reach**

*On screen:* the map, "Every centre" layer on, then transfers.

*Voice:* "The map draws all 34,935 primary and community health centres in
the register [§7a], and the 527 transfers between the ones reporting; 362 of
them cross a district line. 151.7 million people live in the footprint where
demand is grounded in real government data [§2]."

---

**3:25 – 3:50 · Close**

*On screen:* Evidence page, the "what is real" table, then the URL.

*Voice:* "Every figure you have seen is in one file in the repository with
the query it came from. What is modelled, the daily ledger and bed occupancy,
is labelled on the page and listed with its source. It runs on Cloud Run,
BigQuery and Gemini, on data a state already has, and a new state is the
ingestion scripts against its own register. StockPulse."

*End card:* StockPulse · https://daysupply-898541549182.asia-south1.run.app
