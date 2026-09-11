"""Extract the rural staffing tables from Rural Health Statistics 2021-22.

## Why this exists

`load_staffing.py` ran on the **2017** edition, whose own docstring flagged the
vintage: "it should be refreshed before any real deployment". This reads the
2021-22 edition — manpower as on **31 March 2022**, five years newer — and
writes CSVs in exactly the schema the 2017 files used, so the loader changes
only in which files it points at.

## Where the source came from

MoHFW blocks automated access to mohfw.gov.in at the edge (Akamai returns
"Access Denied" to both curl and headless Chrome), and data.gov.in returns 403.
The People's Archive of Rural India mirror on archive.org serves the same
publication:

    https://archive.org/download/PARI.rural-health-statistics-2021-22
        /rural-health-statistics-2021-22.pdf          (30 MB, 270 pages)

**Do not use archive.org's `_djvu.txt`.** Their OCR destroys these tables —
state names vanish and the columns collapse into a bare digit stream
("8 5 6 3 4 1 3 4 1 1 2"). The PDF carries its own embedded text layer, which
extracts at full fidelity. That difference is the whole reason this script
reads the PDF rather than the text file sitting next to it.

The one edition newer still — "Health Dynamics of India (Infrastructure and
Human Resources) 2022-23", as on 31 March 2023 — is the same series under a new
name and is **not** machine-fetchable. A human with a browser has to download
it. The table layout is unlikely to have changed between consecutive editions,
so this extractor should take it with only PAGES updated.

## What changed between editions, and what it costs

**Pharmacists and Nursing staff are now published separately for PHC and CHC.**
The 2017 files combined them, which forced the loader to divide by PHCs *plus*
CHCs; its docstring warns that dividing by PHCs alone "would overstate per-PHC
staffing by about 18%". Every forecast facility we hold is a PHC, so the split
lets us use the PHC figure directly and that whole hazard disappears.

**Health assistants are now published combined [Male + Female].** 2017 had them
separate, and "Health assistant (male), 38.4% vacant" was the worst-cadre
headline. That split is not in this edition, so it is gone rather than carried
forward from stale data at a different vintage.

## Validation

Every table carries its own "All India / Total" row. Each extracted table is
summed and checked against it, so a dropped or misparsed state fails here
rather than downstream. The doctors table cross-checks a second way: the
document's own prose says allopathic doctors at PHCs "increased from 20308 in
2005 to 30640 in 2022", and the table's In Position total is 30640.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from pypdf import PdfReader

DATA_DIR = Path(__file__).resolve().parent.parent / "Data" / "India"
SOURCE_LABEL = "2021-22"

# PDF page index -> (output stem, the title that must appear on that page).
# Located by title rather than trusted blindly: the assertion is what stops a
# future edition's re-pagination writing the wrong cadre's numbers into a file
# named for this one.
# Every pattern ends in "in Rural Areas". The same six cadres are tabulated
# again for urban and for tribal areas later in the document, so a pattern that
# only named the cadre would accept the wrong population without complaint.
PAGES: dict[int, tuple[str, str]] = {
    150: ("assistant-PHCS",
          r"HEALTH ASSISTANT\s+at PHCs\s+in Rural Areas"),
    151: ("allo-doc-PHCS",
          r"DOCTORS.{0,3}\s+AT PRIMARY HEALTH CENTRES\s+in Rural Areas"),
    164: ("pharmacists-PHCS",
          r"PHARMACISTS\s+at PHCs\s+in Rural Areas"),
    165: ("pharmacists-CHCS",
          r"PHARMACISTS\s+at CHCs\s+in Rural Areas"),
    168: ("nursing-staff-PHCS",
          r"NURSING STAFF\s+\(STAFF NURSE\)\s+at PHCs\s+in Rural Areas"),
    169: ("nursing-staff-CHCS",
          r"NURSING STAFF\s+at CHCs\s+in Rural Areas"),
}

HEADER = ["S. No.", "State/ UT", "Required - [R]", "Sanctioned - [S]",
          "In Position - [P]", "Vacant - [S-P]", "Shortfall - [R-P]"]

# A data row is "<n> <State name> <five values>". Values are an integer, NA,
# N App, a bare "*" (surplus) or "-" (not reported) — all of which the 2017
# files also carry, so downstream coercion is unchanged.
VALUE = r"(?:\d+|NA|N App|[*+]|-)"
ROW = re.compile(rf"^\s*(\d{{1,2}})\s+(.+?)\s+({VALUE})\s+({VALUE})\s+({VALUE})"
                 rf"\s+({VALUE})\s+({VALUE})\s*$")
TOTAL = re.compile(rf"^\s*All India.*?\s+({VALUE})\s+({VALUE})\s+({VALUE})"
                   rf"\s+({VALUE})\s+({VALUE})\s*$")


def _rows(text: str) -> tuple[list[list[str]], list[str]]:
    """Parse one page into data rows plus the page's own All India total.

    Rows wrap unpredictably. Most are one line, but a long state name can be
    split across up to five: on the Health Assistant page, serial 31 sits alone
    on its own line, "Dadra & Nagar / Haveli and Daman & / Diu" occupies three
    more, and its five values land on a fifth.

    So rather than guessing how deep a wrap goes, everything from one serial up
    to the next is joined and matched as a unit. A serial-led line is one that
    is a bare number, or a number followed by something that is not a digit —
    which is what keeps a values-only continuation line like "24 2 2 0 22" from
    being mistaken for the start of row 24.
    """
    rows: list[list[str]] = []
    total: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        m = ROW.match(re.sub(r"\s+", " ", " ".join(buf)).strip())
        if m:
            serial, state, *vals = m.groups()
            rows.append([serial, state.strip(), *vals])

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = TOTAL.match(line)
        if m:
            flush()
            buf = []
            total = list(m.groups())
            continue
        if re.match(r"^\d{1,2}$", line) or re.match(r"^\d{1,2}\s+\D", line):
            flush()
            buf = [line]
        elif buf:
            buf.append(line)
    flush()
    return rows, total


def _n(v: str) -> int:
    """Only real integers count toward a total. NA / * / N App are absences,
    and the source's own All India row excludes them the same way."""
    return int(v) if v.isdigit() else 0


def extract(pdf: Path, out_dir: Path = DATA_DIR) -> list[tuple[str, int]]:
    reader = PdfReader(str(pdf))
    written: list[tuple[str, int]] = []

    for page, (stem, title) in sorted(PAGES.items()):
        text = reader.pages[page].extract_text() or ""
        if not re.search(title, text, re.I | re.S):
            raise SystemExit(
                f"p{page} does not carry '{title}'. The edition has been "
                f"re-paginated — fix PAGES rather than trusting the index.\n"
                f"  page begins: {text.strip()[:120]!r}")

        rows, total = _rows(text)
        if len(rows) < 30:
            raise SystemExit(f"p{page} ({stem}): only {len(rows)} states "
                             "parsed; expected 36")
        if not total:
            raise SystemExit(f"p{page} ({stem}): no All India row found, so "
                             "the extraction cannot be checked")

        # The page checks itself. Vacancy and shortfall are excluded: the
        # source footnote says those All India figures ignore surplus states,
        # so they are deliberately not the column sum.
        for idx, label in ((2, "Required"), (3, "Sanctioned"), (4, "In Position")):
            got = sum(_n(r[idx]) for r in rows)
            want = _n(total[idx - 2])
            if got != want:
                raise SystemExit(
                    f"p{page} ({stem}): {label} sums to {got:,} but the "
                    f"table's own All India row says {want:,}")

        path = out_dir / f"{stem}_{SOURCE_LABEL}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            w.writerows(rows)
        written.append((path.name, len(rows)))
        print(f"  {path.name:<34} {len(rows)} states  "
              f"in position {_n(total[2]):>7,}  "
              f"vacant {_n(total[3]):>6,}")
    return written


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_rhs_2122.py <rural-health-statistics-2021-22.pdf>")
    src = Path(sys.argv[1])
    if not src.exists():
        raise SystemExit(f"not found: {src}")
    print(f"Reading {src.name} ...")
    extract(src)
    print("Each table was checked against its own All India row.")
