# Prompts and model configuration

Every instruction the app gives Gemini is a plain-text file here, loaded by the
code at start-up. To try or refine one, open Google AI Studio, paste the file
into **System instructions**, pick the model named in `models.json`, and type a
report as a health worker would.

| File | Used for | Loaded by |
|---|---|---|
| `extraction_system.txt` | Turns a voice note, typed note or register photo into stock events (JSON) | `app/capture.py` |
| `chat_instruction.txt` | Prefix for a typed note | `app/capture.py` |
| `photo_instruction.txt` | Tells the model how a stock register page is laid out | `app/capture.py` |
| `escalation_note_system.txt` | Drafts the escalation note for a shortage nothing routine will fix | `app/brief.py` |
| `models.json` | The Gemini model chain, newest Flash first, with locations and timeout | `app/capture.py` |

## Testing a change

`evals/extraction_cases.json` holds 20 edge cases: corrections ("200, nahi
nahi, 150"), negations ("ORS nahi aaya"), questions, chatter, brand and
colloquial names, vague ranges, fraction words ("dedh sau"), native numerals,
Telugu, Bengali and Marathi. Score the prompt against them:

```
python -m scripts.eval_prompts
python -m scripts.eval_prompts --model gemini-3.5-flash@asia-south1
```

Results on 2026-09-30:

| Prompt | Model | Passed | Mean time per report |
|---|---|---|---|
| Before refinement | gemini-3.5-flash, Mumbai | 17 / 20 | 4.0 s |
| After refinement | gemini-3.8-flash, global | 20 / 20 | 7.5 s |
| After refinement, thinking level low | gemini-3.8-flash, global | 20 / 20 | 3.2 s |

The three cases the refinement fixed: a negation recorded as a receipt of 0,
a question held as if it were a report, and "iron ki goli dedh sau" (150
iron-folic acid tablets) not recognised.

`models.json` sets `thinking_level` to `low` for the Gemini 3 models. Reading
a stock report needs little reasoning: the score held at 20 / 20 and the
time per report more than halved. At the default level, gemini-3.8-flash
overran the 25-second timeout on escalation notes.

The escalation note prompt has one edge case of its own: when a centre has
0 days of cover it now says the shelf is empty and asks for a decision
today, instead of "within 0 days".
