"""Parse the National List of Essential Medicines 2022 into structured rows.

Source: Data/India/nlem2022.xlsx — a PDF-to-Excel table extraction of
nlem2022.pdf (MoHFW). It is a conversion, not a clean dataset, and it has to be
treated as one. What the conversion does to the document:

* **30 sheets**, `Table 1` … `Table 30`, one per table the converter detected.
  Sheet boundaries are page-layout artefacts and carry no meaning.
* **`Table 1` is two documents in one sheet.** The first ~40 rows are the table
  of contents; the rest is Sections 1-3 of the medicine list. Skipping the sheet
  as an artefact silently loses Anaesthetics, Analgesics and Antiallergics. The
  contents rows are dropped instead by the level-of-care filter below, since
  only real medicine rows carry a `P`/`S`/`T` value.
* **`Table 20` changes meaning halfway down.** Rows 0-12 are the last real
  medicines (Sections 23-30). Row 13 begins "Alphabetical List of Medicines
  Added to NLEM 2022" — a bare numbered name list — and row 59 begins
  "Medicines Deleted from ... NLEM 2015", which runs on through `Table 26`.
* **`Tables 27-30` are the page index** ("Clotrimazole, 27, 32, ...").

So the current NLEM 2022 catalogue is `Table 2` through `Table 20` row 12, and
nothing else. Loading past that point would put *deleted* medicines into the
catalogue as if they were current — the single most damaging error available
here, and one that fails silently.

Further conversion damage this module has to undo:

* **Section codes became dates.** `7.1.11` was parsed by the converter as
  7 January 2011. Recovered as `day.month.two-digit-year`.
* **Header rows repeat** at every subsection, so columns cannot be read from a
  single header. Column positions are re-read from each header row encountered.
* **Column layout shifts between sheets** (4 to 13 columns) with blank spacer
  columns, so fixed column indices do not work.
* **Therapeutic category is a section header row, not a column**, and must be
  carried down onto the rows beneath it.
* **Footnote markers are glued to names** — `Atropine*`, `Morphine***`.
* **One medicine spans several rows** when it has multiple dosage forms; the
  continuation rows have a blank medicine cell.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

NLEM_XLSX = (
    Path(__file__).resolve().parent.parent / "Data" / "India" / "nlem2022.xlsx"
)

# Sheets that hold current medicines. Everything after is deleted-medicine
# appendix or index.
FIRST_DATA_SHEET = "Table 1"
LAST_DATA_SHEET = "Table 20"

# Everything from this marker onward is no longer the current catalogue.
STOP_MARKERS = (
    "alphabetical list of",
    "medicines deleted from",
    "index",
)

# "P", "S,T", "P,S,T" — Primary / Secondary / Tertiary level of healthcare.
LEVEL_RE = re.compile(r"^[PST](\s*,\s*[PST])*$", re.I)

# "Section 6 Anti-infective..." / "6.2-Antibacterials" / "6.2.1 Beta-lactam".
# The number must not be followed by a dot, or "Section 5.1-Anticonvulsants"
# would be read as section 5 named ".1-Anticonvulsants".
SECTION_RE = re.compile(r"^section\s+(\d+)(?!\.\d)\s*[-–:]?\s*(.*)$", re.I | re.S)
SUBSECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*[-–]?\s*(.+)$", re.S)


def _clean(value) -> str:
    """Normalise a cell to a single-line trimmed string."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (dt.datetime, pd.Timestamp)):
        # A section code the converter mangled into a date: 7.1.11 -> 2011-01-07
        return f"{value.day}.{value.month}.{value.year % 100}"
    text = str(value).replace("\n", " ").strip()
    return "" if text.lower() in ("nan", "nat") else re.sub(r"\s+", " ", text)


def _strip_footnotes(name: str) -> str:
    """`Morphine***` -> `Morphine`. The asterisks are footnote markers."""
    return re.sub(r"[*†‡]+", "", name).strip(" .,-")


def _is_header_row(cells: list[str]) -> bool:
    lowered = [c.lower() for c in cells]
    return any(c == "medicine" for c in lowered) and any(
        "level of" in c for c in lowered
    )


def _column_map(cells: list[str]) -> dict[str, int]:
    """Read column positions from a header row."""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(cells):
        low = cell.lower()
        if low == "medicine" and "medicine" not in mapping:
            mapping["medicine"] = idx
        elif "level of" in low and "level" not in mapping:
            mapping["level"] = idx
        elif "dosage form" in low and "dosage" not in mapping:
            mapping["dosage"] = idx
    return mapping


def _find_level(cells: list[str]) -> int | None:
    for idx, cell in enumerate(cells):
        if cell and LEVEL_RE.match(cell):
            return idx
    return None


def parse_nlem(path: Path = NLEM_XLSX) -> pd.DataFrame:
    """Return one row per medicine × dosage form in the current NLEM 2022."""
    book = pd.ExcelFile(path)
    sheets = book.sheet_names
    start = sheets.index(FIRST_DATA_SHEET)
    end = sheets.index(LAST_DATA_SHEET)

    records: list[dict] = []
    section_no = section_name = subsection = ""
    columns: dict[str, int] = {}
    stopped = False

    for sheet in sheets[start:end + 1]:
        if stopped:
            break
        frame = book.parse(sheet, header=None)

        for _, raw in frame.iterrows():
            cells = [_clean(v) for v in raw]
            joined = " ".join(c for c in cells if c)
            if not joined:
                continue

            low = joined.lower()
            if any(low.startswith(marker) for marker in STOP_MARKERS):
                stopped = True
                break

            if _is_header_row(cells):
                columns = _column_map(cells)
                continue

            level_idx = _find_level(cells)

            if level_idx is None:
                # No level-of-care value, so this is a section or subsection
                # heading (or a footnote). Carry the therapeutic category down.
                match = SECTION_RE.match(joined)
                if match:
                    section_no, section_name = match.group(1), match.group(2)
                    section_name = re.sub(
                        r"\(now in section.*?\)", "", section_name, flags=re.I
                    ).strip(" -–:")
                    subsection = ""
                    continue
                sub = SUBSECTION_RE.match(joined)
                if sub and not joined.lower().startswith("nil"):
                    subsection = sub.group(2).strip()
                continue

            # --- A medicine row -------------------------------------------
            med_idx = columns.get("medicine")
            dose_idx = columns.get("dosage")

            name = _clean(cells[med_idx]) if (
                med_idx is not None and med_idx < len(cells)
            ) else ""
            # Fall back to the nearest text cell left of the level column.
            if not name:
                for idx in range(level_idx - 1, -1, -1):
                    candidate = cells[idx]
                    if candidate and not re.fullmatch(
                        r"[\d.]+", candidate
                    ) and len(candidate) > 2:
                        name = candidate
                        break

            dosage = ""
            if dose_idx is not None and dose_idx < len(cells):
                dosage = cells[dose_idx]
            if not dosage:
                for idx in range(len(cells) - 1, level_idx, -1):
                    if cells[idx]:
                        dosage = cells[idx]
                        break

            name = _strip_footnotes(name)
            if not name or re.fullmatch(r"[\d.]+", name):
                # Continuation row: another dosage form of the previous item.
                if records:
                    records[-1]["dosage_forms"].append(dosage)
                continue

            records.append({
                "medicine": name,
                "level_of_care": cells[level_idx].upper().replace(" ", ""),
                "dosage_forms": [dosage] if dosage else [],
                "section_no": section_no,
                "section_name": section_name,
                "subsection": subsection,
                "sheet": sheet,
            })

    frame = pd.DataFrame(records)
    frame["dosage_forms"] = frame["dosage_forms"].apply(
        lambda forms: " | ".join(f for f in forms if f)
    )
    return frame


if __name__ == "__main__":
    df = parse_nlem()
    print(f"Rows parsed: {len(df)}")
    print(f"Distinct medicines: {df['medicine'].nunique()}")
    print(f"Sections: {df['section_no'].nunique()}")
    print(f"Primary-care (P) medicines: "
          f"{df['level_of_care'].str.contains('P').sum()}")
    print()
    print(df.head(15).to_string(max_colwidth=40))
