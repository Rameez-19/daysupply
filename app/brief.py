"""A drafted escalation note for one shortage — Gemini writing, not deciding.

## What this is for

The action queue's top panel is the 39 shortages nothing routine will fix:
nothing within reach to move, and an order that would arrive after the shelf
is empty. Each one needs a decision a dashboard cannot make, and the officer
who makes it has to write it up — to the district programme officer, to the
state warehouse, to the referral hospital. This drafts that note.

## What it may not do

**Invent a figure.** The note is grounded on the row it is drafted from:
on-hand, reorder point, days of cover, lead time, distance to the district
headquarters. The model is told to use only those numbers, and the draft is
then checked: every number in the output must appear among the inputs. A
draft that mentions a figure the data does not contain is still returned —
suppressing it would hide the failure — but it comes back flagged, with the
foreign numbers listed, and the page says so beside the text.

**Pretend to know a cause.** Why the centre is short is not in the data, and
the prompt says so. The draft describes the position and the options, not the
reason.

**Replace the decision.** It ends with the two or three concrete options a
district officer actually has, and asks for the decision. It does not pick.
"""

from __future__ import annotations

import json
import logging
import re

from app import action_queue, capture

log = logging.getLogger(__name__)

LANGUAGES = {"en": "English", "hi": "Hindi (Devanagari script)",
             "mr": "Marathi (Devanagari script)",
             "te": "Telugu (Telugu script)",
             "bn": "Bengali (Bengali script)"}

SYSTEM = """
You draft short escalation notes for district health officers in India about
a medicine shortage at one primary health centre. You are given the facts as
JSON. Write the note in the language requested.

Rules, none of which may be broken:
- Use ONLY the numbers in the facts. Do not introduce any other number, date,
  percentage, distance or quantity. If a fact is null, do not mention it.
- Do not state or guess WHY the centre is short. That is not in the facts.
- Do not name any person, supplier, warehouse, scheme or hospital that is not
  in the facts.
- Structure: (1) one sentence saying what is short, where, and how many days
  of stock remain; (2) one or two sentences saying why the routine fixes do
  not work here — no transfer is available within reach, and the delivery
  lead time is longer than the days of cover; (3) the concrete options a
  district officer has, as a short list: an emergency indent with the lead
  time stated, moving patients or referring them, and a therapeutic substitute
  only if the facts list one; (4) one sentence asking for the decision and by
  when, using the days of cover as the deadline.
- Under 140 words. Plain, formal, no greeting, no sign-off, no markdown.
"""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Every number in a text, normalised so 1,250, 1250 and 1250.0 compare
    equal. The facts arrive with BigQuery's floats ("13.0" days); the model
    writes "13"."""
    out = set()
    for n in _NUMBER.findall(text or ""):
        n = n.replace(",", "")
        try:
            f = float(n)
            out.add(str(int(f)) if f == int(f) else str(f))
        except ValueError:
            out.add(n)
    return out


def _facts(row: dict) -> dict:
    keep = ("facility_name", "district", "state", "item_name", "ven_class",
            "unit", "on_hand", "reorder_point", "shortfall", "days_of_cover",
            "lead_time_days", "lead_time_is_estimated", "distance_to_hq_km",
            "status")
    facts = {k: row.get(k) for k in keep}
    if facts.get("distance_to_hq_km") is not None:
        facts["distance_to_hq_km"] = round(float(facts["distance_to_hq_km"]))
    for k in ("days_of_cover", "on_hand", "reorder_point"):
        if isinstance(facts.get(k), float) and facts[k] == int(facts[k]):
            facts[k] = int(facts[k])
    return facts


def find_row(facility_id: str, item_id: str) -> dict | None:
    """The shortage as the action queue has it — the same query, same cache."""
    data = action_queue.triage(phc=facility_id)
    for r in data["all_shortages"]:
        if r["facility_id"] == facility_id and r["item_id"] == item_id:
            group = ("escalate" if r["too_late_to_order"]
                     else "transfer" if r["has_transfer"] else "order")
            return {**r, "group": group}
    return None


def draft(facility_id: str, item_id: str, lang: str = "en") -> dict:
    row = find_row(facility_id, item_id)
    if row is None:
        return {"error": f"no open shortage of {item_id} at {facility_id}"}
    lang = lang if lang in LANGUAGES else "en"
    facts = _facts(row)
    prompt = (f"Language: {LANGUAGES[lang]}.\n"
              f"Shortage group: {row['group']} "
              f"({'nothing routine works' if row['group'] == 'escalate' else row['group']}).\n"
              f"Facts:\n{json.dumps(facts, ensure_ascii=False)}")
    try:
        text = capture._generate(prompt, system_instruction=SYSTEM)
    except capture.ModelUnavailable as exc:
        return {"error": str(exc), "retryable": True, "facts": facts}
    except Exception as exc:  # a non-retryable API error
        return {"error": str(exc), "retryable": False, "facts": facts}

    allowed = _numbers(json.dumps(facts))
    foreign = sorted(_numbers(text) - allowed)
    if foreign:
        log.warning("Brief for %s/%s mentions numbers not in the facts: %s",
                    facility_id, item_id, foreign)
    return {
        "facility_id": facility_id,
        "item_id": item_id,
        "lang": lang,
        "group": row["group"],
        "note": text.strip(),
        "facts": facts,
        "numbers_checked": not foreign,
        "unverified_numbers": foreign,
        "model": capture.MODEL,
        "basis": ("Drafted by Gemini from the row's own figures. Every number "
                  "in the draft was checked against them."
                  if not foreign else
                  "Drafted by Gemini. It mentions figures that are not in the "
                  "data; treat those as unverified."),
    }
