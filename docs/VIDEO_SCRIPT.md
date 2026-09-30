# Demo video script — about 4:50

Written so that anyone, a fifteen-year-old included, can follow what the
problem is and how StockPulse solves it. The **voice** stays in plain words.
The **caption** puts the technical name on screen for judges, so nothing is
lost by keeping the voice simple.

Screen recording of the live app: a phone frame for the Report page, desktop
for the rest. Every figure is from [`CLAIMS.md`](CLAIMS.md) §0 unless marked.
About 690 spoken words at an unhurried pace, inside the 5-minute limit. If
over time, cut the "learning from each other" beat first.

## Before recording

- Open the site and send one typed report in preview a minute before
  recording. The first Gemini call after a deploy can be slow; the ones after
  it take two to three seconds.
- On the Report page, pick the centre **Salchapra MPHC** (Cachar, Assam).
- Keep the Explain switch **off** on the officer pages, so the screen is clean.
- The voice line below was checked on 2026-09-30: three runs out of three
  saved the Paracetamol and held the ORS for review.

---

## 0:00 – 0:25 · The empty shelf

*On screen:* the Report page on a phone, still.

*Voice:* "Imagine walking two hours to a health centre with a sick child, and
being told the medicine ran out last week. Nobody knew it was running out.
Not the centre, not the district. That happens because in India, nobody keeps
a daily count of medicines at each health centre that anyone else can see."

*Caption:* StockPulse · Build with AI: Code for Communities · Resilience,
Track 3

---

## 0:25 – 1:00 · Why it keeps happening

*On screen:* the title slide's number, then the Today page.

*Voice:* "India's register lists 200,438 health facilities. The person who
knows what is on the shelf is a busy health worker, often facing a form in a
language that is not their own. And medicine demand is not steady: on
National Deworming Day, deworming tablets are needed at more than twenty
times the usual rate. So shelves go empty before anyone can react.

StockPulse fixes two things. It makes reporting take seconds, and then the
system does the thinking: what will run out, where spare stock is, and what
to do about it."

*Caption:* 200,438 facilities · Albendazole peaks at 22.64× its mean [§6]

---

## 1:00 – 1:55 · Reporting takes seconds

*On screen (phone):* tap "Stock came in" → Paracetamol → type 200. The phone
reads it back aloud.

*Voice:* "Here is a health worker reporting. Three taps and one number. The
phone reads it back out loud, and nothing is saved until they say yes."

*On screen:* switch the language to हिंदी; the whole page and the read-back
change. Flick through मराठी, తెలుగు, বাংলা, back to हिंदी, tap
"हाँ, सेव करें".

*Voice:* "It works in five languages: English, Hindi, Marathi, Telugu and
Bengali."

*On screen:* tap the microphone, say "Paracetamol ke do sau tablet aaye hain,
ORS ka aadha dabba bacha hai", tap again to stop. Paracetamol 200 is ready to
save; the ORS goes to review.

*Voice:* "They can also just talk, the way they would to a colleague. Google's
Gemini AI listens and turns the sentence into a stock report. Two hundred
Paracetamol tablets arrived: clear. But 'half a box' of ORS is not a number,
so instead of guessing, it asks the pharmacist to check. When the AI is not
sure, a person decides."

*On screen:* photo mode, a photographed register page turning into rows.

*Voice:* "They can even photograph the paper stock register, and it becomes
rows to check. It works without internet too: reports wait on the phone and
send themselves when the signal comes back."

*Caption:* Gemini on Vertex AI · matched to all 385 medicines on India's
Essential Medicines List [§3] · Cloud Text-to-Speech read-back

---

## 1:55 – 2:20 · The district officer's to-do list

*On screen (desktop):* the Today page, with the task bar across the top.

*Voice:* "Every report lands in one place, and the district officer sees it
as a to-do list: which shortages need escalating, which transfers to approve,
which orders to place. Below it, the health of the whole network. Across the
275 centres running today in six states, 80 percent of medicines are at a
safe level."

*Caption:* 275 PHCs, 6 states · availability 80.0%, life-saving 80.3%

---

## 2:20 – 3:10 · Seeing trouble coming

*On screen:* Plan ahead, the demand outlook chart.

*Voice:* "Next, a forecast. Like a weather forecast, but for medicines: how
many tablets each centre will need in the coming weeks, based on real
government records of which illnesses rise in which months."

*Caption:* BigQuery ML ARIMA_PLUS · 3,818 forecasts, one per centre and
medicine · real HMIS data

*On screen:* scroll to Early warnings: the three labels, then a card.

*Voice:* "And an early warning. Most alarms only ring when a number is wildly
off. With just twelve months of data, the usual alarm cannot ring at all. So
StockPulse uses a smarter test that catches the weak signal, when cases are
rising but have not exploded yet. In Mumbai one January, malaria medicine
demand hit two and a half times normal. It
also labels each warning. Deworming Day is a planned campaign, not an
outbreak, so it is never raised as an emergency. We do not predict outbreaks; we
notice early that one has begun."

*Caption:* modified z-score; a 3-sigma rule cannot exceed 3.175 on twelve
points · 2,352 surges found · Brihan Mumbai: 2,345 vs 938.4 expected, 2.50×

---

## 3:10 – 4:00 · Fixing every shortage

*On screen:* the Action queue, the three groups.

*Voice:* "Now the fix. Today there are 765 shortages, and each one comes with
a plan. For 685, another centre nearby has spare stock, so the medicine is
moved, the batch that expires soonest first, so nothing goes to waste. For 36, an order
will arrive in time. And for 44, neither works."

*On screen:* click "Draft" on the first escalation; the note appears with
"Every number checked against the row."

*Voice:* "For those, Gemini drafts an escalation note: what is short, why
the usual fixes will not work, and what the officer can do. It uses only
that shortage's own numbers, and every number in the note is checked. The AI
writes the draft; the officer makes the call."

*On screen:* the Map, with transfers drawn between centres.

*Voice:* "On the map, most transfers cross a district border: something
one district could never arrange alone."

*Caption:* 685 move · 36 order · 44 escalate · 520 of 685 transfers cross a
district line

---

## 4:00 – 4:20 · Districts learning from each other

*On screen:* the Evidence page, the four-bar chart.

*Voice:* "Districts also help each other's forecasts. They share only the
shape of their year, when demand goes up and when it goes down, never
anyone's records. Sharing that shape cut forecast mistakes from about 21
percent to under 16."

*Caption:* forecast error 21.1% → 15.6% (weighted MAPE) · seasonal shape,
not data

---

## 4:20 – 4:50 · How it is built, and where it goes next

*On screen:* the architecture poster, then the live URL.

*Voice:* "All of this runs on Google Cloud: Gemini for understanding reports,
BigQuery for the data and the forecasts, and Cloud Run to serve the app. It
uses real government data, and it tells you plainly which parts are
estimated. Data for every state in India is already in hand; six states run
today, and adding Uttar Pradesh, India's most populous state, took a single working
session. A health worker reports in seconds. The system does the rest. That
is StockPulse."

*End card:* StockPulse · https://daysupply-898541549182.asia-south1.run.app

---

## Words to use, and words to avoid

- Say "we notice early that a surge has begun". **Never** "predicts
  outbreaks".
- Say "districts share the shape of their year, not their data". **Never**
  "federated learning".
- 260.8 million people is the footprint where demand rests on real data. If
  it is used, say exactly that.
- The daily stock ledger is generated from real drivers, because no one
  publishes one. If a judge asks, say so plainly; it is on the Evidence page
  and in `Data/README.md`.
