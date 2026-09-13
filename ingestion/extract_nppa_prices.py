"""Extract DPCO ceiling prices from the NPPA Compendium of Prices.

## Why this exists

`build_waste_value.py` converts avoided expiry into rupees, and refuses to
publish a headline because of two faults in the price data it had:

1. **Coverage was 26.9%** — prices existed for items covering 8,851 of 32,893
   expired units. The single largest waste item, Ferrous Salt + Folic acid at
   **34.5%** of all expiry on its own, had no price at all.
2. **The source was secondary** — six rows transcribed from a summary of the
   DPCO schedule rather than from NPPA itself, recorded as
   `source_tier: secondary` so the weakness was visible rather than assumed.

This reads the **NPPA Compendium of Prices 2022** directly: the ceiling prices
notified under S.O. 1499(E) of 30.03.2022, published by the National
Pharmaceutical Pricing Authority under the Drugs (Prices Control) Order 2013.
That is a primary source and the correct basis, because a ceiling price is what
a government purchaser may lawfully be charged.

    https://nppa.gov.in/storage/uploads/pdf/
        Compendium-Prices-2022pdf-464b22085495ff4e3f8700c0e00cf45d.pdf

Unlike mohfw.gov.in, nppa.gov.in serves this to a plain request, so the file is
fetched rather than hand-downloaded. It carries a real embedded text layer; no
OCR is involved.

## The shape of the table, and why a line-by-line parser fails

Each medicine appears once, numbered by its NLEM section, and its formulations
follow beneath it — the name is *not* repeated:

    29.5 Ringer lactate Injection (as per IP)
    Injection 1000ml Each Pack 88.57 1499(E) 30.03.2022
    Injection 100ml  Each Pack 23.19 1499(E) 30.03.2022

Both names and formulations wrap:

    10.1.3 Ferrous salt (A) + Folic
    acid (B)
    Tablet 45mg elemental iron
    (A) + 400 mcg (B)

    21.4.1.4 Metformin Tablet 500 mg(Controlled
    release)
    1 Tablet 2.13 1499(E) 30.03.2022

A parser matching one line at a time found 997 prices and missed six of our
thirty-nine items — including Ferrous Salt, the one that matters most. So this
carries the current medicine forward and completes a row when a price tail
arrives, which is the same correction the RHS extractor needed.

## Which price is taken

A medicine has several pack sizes at different ceiling prices. Two rules, both
stated rather than chosen case by case:

* only formulations whose unit matches the unit we count stock in, so a
  per-millilitre price is never applied to a tablet;
* the **lowest** qualifying ceiling price.

Taking the lowest understates the value of avoided waste, which is the
direction `build_waste_value.py` already errs in deliberately — ceiling prices
exclude GST, and a ceiling is a maximum rather than a typical procurement
price. A figure that understates can be defended; one that flatters cannot.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import sys
from pathlib import Path

from pypdf import PdfReader

# Run as a script from anywhere: the repo root carries `app/`, which
# `run()` needs for the item list.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "Data" / "India" / "nppa_ceiling_prices.csv"
HEADER = ["item_match", "strength", "unit", "ceiling_price_inr",
          "source", "source_tier", "retrieved"]
SOURCE = ("NPPA Compendium of Prices 2022, DPCO 2013 ceiling prices notified "
          "by S.O. 1499(E) dated 30.03.2022")

# An NLEM section number: 4.2.1, 21.4.1.4, 30.9.
SECTION = re.compile(r"^(\d+(?:\.\d+)+)\s+(.+)$")

# The tail every priced row ends with: pack unit, price, notification, date.
PRICE_TAIL = re.compile(
    r"^(?P<form>.*?)\s+(?P<price>[\d,]+\.\d{2})\s+(?P<so>\S*\(E\))\s+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})$")

# Where a medicine's name ends and its dosage form begins. The compendium puts
# them on one line with nothing but a space between.
FORMS = ("Tablet", "Capsule", "Injection", "Solution", "Syrup", "Oral liquid",
         "Oral Liquid", "Powder", "Drops", "Ointment", "Cream", "Inhalation",
         "Sachet", "Suspension", "Gel", "Spray", "Infusion", "Lotion",
         "Enema", "Pessary", "Suppository", "Patch", "Granules", "Elixir",
         "Dry powder", "Eye", "Ear", "Nasal", "Vaginal", "Rectal", "Cubic")
FORM_RE = re.compile(r"\b(" + "|".join(FORMS) + r")\b")

# The pack unit a price is quoted per, mapped to the unit we hold stock in.
UNIT_MAP = {
    "tablet": "tablet", "capsule": "capsule", "ml": "vial", "vial": "vial",
    "gm": "unit", "gram": "unit", "each pack": "vial", "pack": "unit",
    "unit": "unit", "bottle": "bottle", "cubic meter": "unit",
}


# Where the form begins when no dosage-form word is present: the first token
# that starts with a digit, or opens a pack description.
FORMLESS_RE = re.compile(r"(?:^|\s)(?=\d|As\b|Each\b|Per\b|%)")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _split_name_form(rest: str) -> tuple[str, str]:
    """Split a section line into the medicine and its first formulation.

    Most lines carry a capitalised dosage form to split on. Sixteen do not,
    and a parser that required one dropped their prices silently:

        14.6.2 White Petrolatum Jelly 100% 1 gm 0.10 ...
        17.2.3 Potassium permanganate Crystals for topical solution 1 gm ...
        20.6.1 Oral rehydration salts As licensed 1 gm 0.99 ...
        22.3.1.1 BCG vaccine Each Dose 9.92 ...
        22.2.4 Diphtheria antitoxin 10000 IU Each Pack 1455.21 ...

    Oral rehydration salts is one of the items this project tracks, so the gap
    was not academic. Falling back to the first digit, "As" or "Each" splits
    all five correctly.
    """
    form_at = FORM_RE.search(rest)
    if form_at:
        return _clean(rest[:form_at.start()]), rest[form_at.start():]
    loose = FORMLESS_RE.search(rest)
    if loose and loose.start() > 0:
        return _clean(rest[:loose.start()]), rest[loose.start():].strip()
    return _clean(rest), ""


def parse(pdf: Path) -> tuple[list[dict], int]:
    """Every priced formulation in the compendium, with its medicine.

    Returns the rows and the number of lines that carry a price on their own.
    Those two must be equal: every priced line has to become a row. It is the
    only invariant that catches this parser silently losing data, and it
    caught two regressions while it was being written - 981 rows when the name
    and form split required a capitalised dosage word, and 994 when three
    vaccine lines split on their price instead of on "Each".
    """
    reader = PdfReader(str(pdf))
    lines: list[str] = []
    for page in reader.pages:
        lines.extend((page.extract_text() or "").split("\n"))

    rows: list[dict] = []
    priced_lines = 0   # lines that carry a price with no help from the ones
                       # around them - the count every row must be matched by
    name = ""          # the medicine a formulation belongs to
    name_open = False  # the name itself is still wrapping
    pending = ""       # a formulation whose price has not arrived yet

    for raw in lines:
        line = _clean(raw)
        if not line or line.startswith(("(1)", "Section of", "S.O. No.")):
            continue
        if PRICE_TAIL.match(line):
            priced_lines += 1

        section = SECTION.match(line)
        rest = section.group(2) if section else line

        if section:
            # A new medicine. Its name runs up to the first dosage form on
            # the line, if any; otherwise the whole remainder is the name and
            # it may continue onto the next line.
            name, rest = _split_name_form(rest)
            name_open = not rest
            pending = ""
            if not rest:
                continue

        elif name_open and not FORM_RE.search(line) and not PRICE_TAIL.match(line):
            # Still the name: "10.1.3 Ferrous salt (A) + Folic" / "acid (B)".
            name = _clean(f"{name} {line}")
            continue

        if FORM_RE.search(rest) or pending:
            name_open = False

        candidate = _clean(f"{pending} {rest}") if pending else _clean(rest)
        priced = PRICE_TAIL.match(candidate)
        if priced:
            form = _clean(priced.group("form"))
            rows.append({
                "medicine": name,
                "form": form,
                "price": float(priced.group("price").replace(",", "")),
                "notification": priced.group("so"),
                "date": priced.group("date"),
            })
            pending = ""
        elif candidate:
            # A formulation whose price is on a later line.
            pending = candidate
    return rows, priced_lines


def pack_unit(form: str) -> str | None:
    """The unit a price is quoted per, from the tail of the formulation."""
    tail = form.lower()
    for token, unit in sorted(UNIT_MAP.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b\d*\s*{re.escape(token)}s?$", tail):
            return unit
    return None


def choose(rows: list[dict], items: dict[str, str]) -> list[dict]:
    """One price per item: the lowest that is quoted in the item's own unit."""
    out = []
    for display_name, unit in sorted(items.items()):
        key = display_name.split("(")[0].strip()
        matches = [r for r in rows
                   if key.lower() in r["medicine"].lower()
                   and pack_unit(r["form"]) == unit]
        if not matches:
            continue
        best = min(matches, key=lambda r: r["price"])
        out.append({
            "item_match": key,
            "strength": _clean(best["form"]),
            "unit": unit,
            "ceiling_price_inr": best["price"],
            "source": SOURCE,
            "source_tier": "primary",
            "retrieved": dt.date.today().isoformat(),
        })
    return out


def run(pdf: Path) -> None:
    from app.bq import run_query

    rows, priced_lines = parse(pdf)
    print(f"  priced formulations parsed: {len(rows):,} "
          f"(lines carrying a price: {priced_lines:,})")
    if len(rows) != priced_lines:
        raise SystemExit(
            f"{priced_lines - len(rows)} priced lines produced no row. Every "
            "line carrying a price must become one; anything else means the "
            "wrap handling is dropping data.")

    items = {r["display_name"]: r["unit"] for r in run_query(
        "SELECT display_name, unit FROM `daysupply.daysupply.items` "
        "WHERE is_forecast_item")}
    chosen = choose(rows, items)
    missing = sorted(set(items) - {c["item_match"] for c in chosen}
                     - {d for d in items
                        if d.split("(")[0].strip() in
                        {c["item_match"] for c in chosen}})

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        w.writerows(chosen)

    print(f"  items priced: {len(chosen)} of {len(items)}")
    for c in chosen[:8]:
        print(f"    {c['item_match'][:26]:<28} {c['ceiling_price_inr']:>8.2f} "
              f"per {c['unit']:<8} {c['strength'][:40]}")
    if missing:
        print(f"  no price found: {', '.join(m[:30] for m in missing)}")
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_nppa_prices.py <Compendium-Prices-2022.pdf>")
    src = Path(sys.argv[1])
    if not src.exists():
        raise SystemExit(f"not found: {src}")
    print(f"Reading {src.name} ...")
    run(src)
