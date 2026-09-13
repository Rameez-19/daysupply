"""The NPPA price extractor, and the four bugs that shaped it.

`build_waste_value.py` refused to publish a rupee figure because prices covered
26.9% of expired units and came from a secondary transcription. The fix was to
read the NPPA Compendium of Prices 2022 itself — the ceiling prices notified
under S.O. 1499(E) of 30.03.2022.

Most of these tests exercise pure functions with inline strings taken verbatim
from the PDF, so they run without it. The compendium is not in the repository
(`Data/` is gitignored, as the RHS and facility files are); the one test that
needs it skips when it is absent.

Each case below is a bug that actually shipped into a run:

* the name/form split required a capitalised dosage word, so sixteen rows —
  including Oral rehydration salts — lost their price;
* three vaccine lines split on their price instead of on "Each", because a
  heredoc wrote a **backspace byte** into the regex where ``\\b`` was meant,
  leaving `As` and `Each` unmatchable while `\\d` still worked;
* the guard asserted a magic row count instead of the real invariant, and
  passed 981 and 994 rows as "fine" until it was replaced;
* four items are priced per millilitre or per course while stock is counted in
  bottles or tablets, and converting them would mean inventing a pack size.
"""

import csv
from pathlib import Path

import pytest

from ingestion import extract_nppa_prices as ex

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "Data" / "India" / "Compendium-Prices-2022.pdf"
CSV = ROOT / "Data" / "India" / "nppa_ceiling_prices.csv"


class TestTheNameAndFormSplit:
    @pytest.mark.parametrize("line,name", [
        # The ordinary case: a capitalised dosage form separates the two.
        ("Atropine Ointment 1% 1 gm 4.20 1499(E) 30.03.2022", "Atropine"),
        ("Metformin Tablet 500 mg(Controlled", "Metformin"),
        # No dosage word at all. Every one of these lost its price when the
        # split required one.
        ("White Petrolatum Jelly 100% 1 gm 0.10 1499(E) 30.03.2022",
         "White Petrolatum Jelly"),
        ("Oral rehydration salts As licensed 1 gm 0.99 1499(E) 30.03.2022",
         "Oral rehydration salts"),
        ("BCG vaccine Each Dose 9.92 1499(E) 30.03.2022", "BCG vaccine"),
        ("Rabies vaccine Each Pack 379.43 1499(E) 30.03.2022", "Rabies vaccine"),
        ("DPT vaccine Per 0.5 ml 15.73 1499(E) 30.03.2022", "DPT vaccine"),
        ("Diphtheria antitoxin 10000 IU Each Pack 1455.21 1499(E) 30.03.2022",
         "Diphtheria antitoxin"),
    ])
    def test_the_medicine_is_separated_from_its_formulation(self, line, name):
        assert ex._split_name_form(line)[0] == name

    def test_the_word_boundaries_are_real_ones(self):
        """A heredoc turned ``\\b`` into a backspace byte (0x08), so `As` and
        `Each` could never match while `\\d` still did — every split silently
        fell through to the price. The pattern is checked directly because the
        corruption was invisible in the source."""
        assert "\x08" not in ex.FORMLESS_RE.pattern
        assert r"Each\b" in ex.FORMLESS_RE.pattern
        src = (ROOT / "ingestion" / "extract_nppa_prices.py").read_text(
            encoding="utf-8")
        assert not [c for c in src if ord(c) < 32 and c not in "\n\t"], (
            "a control character is embedded in the source")

    def test_a_name_with_no_formulation_stays_whole(self):
        """"Japanese encephalitis" wraps onto the next line; the split must not
        invent a form out of nothing."""
        assert ex._split_name_form("Japanese encephalitis") == (
            "Japanese encephalitis", "")


class TestThePackUnit:
    @pytest.mark.parametrize("form,unit", [
        ("Tablet 100 mg 1 Tablet", "tablet"),
        ("Capsule 250 mg 1 Capsule", "capsule"),
        ("Injection 0.6 mg/ml 1 ml", "vial"),
        ("As licensed 1 gm", "unit"),
        ("Injection 1000ml Each Pack", "vial"),
    ])
    def test_it_reads_the_unit_a_price_is_quoted_per(self, form, unit):
        assert ex.pack_unit(form) == unit

    def test_an_unreadable_pack_is_not_guessed(self):
        """"Injection 0.9% 1000ml Glass" ends in a container, not a unit. A
        price per 1000 ml glass bottle is not a price per vial, and pretending
        otherwise is how a fabricated figure gets into a rupee headline."""
        assert ex.pack_unit("Injection 0.9% 1000ml Glass") is None


class TestChoosingOnePricePerItem:
    ROWS = [
        {"medicine": "Paracetamol", "form": "Tablet 500 mg 1 Tablet", "price": 0.93},
        {"medicine": "Paracetamol", "form": "Tablet 650 mg 1 Tablet", "price": 1.21},
        {"medicine": "Paracetamol", "form": "Oral liquid 125 mg/5 ml 1 ml", "price": 0.35},
    ]

    def test_the_lowest_price_in_the_items_own_unit_wins(self):
        """Two rules, both stated rather than chosen case by case: the unit
        must match, and the cheapest qualifying pack wins. Taking the lowest
        understates the value of avoided waste, which is the direction this
        project already errs in deliberately."""
        chosen = ex.choose(self.ROWS, {"Paracetamol": "tablet"})
        assert len(chosen) == 1
        assert chosen[0]["ceiling_price_inr"] == 0.93
        assert chosen[0]["unit"] == "tablet"

    def test_a_price_in_another_unit_is_never_borrowed(self):
        """The 0.35 above is per millilitre. An item counted in bottles gets
        no price at all rather than a per-millilitre one."""
        assert ex.choose(self.ROWS, {"Paracetamol": "bottle"}) == []

    def test_every_row_carries_its_source_and_tier(self):
        chosen = ex.choose(self.ROWS, {"Paracetamol": "tablet"})[0]
        assert chosen["source_tier"] == "primary"
        assert "1499(E)" in chosen["source"] and "2022" in chosen["source"]


@pytest.fixture(scope="module")
def rows():
    with open(CSV, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.skipif(not CSV.exists(), reason="prices CSV is gitignored")
class TestTheExtractedPriceList:
    def test_every_price_is_primary_sourced(self, rows):
        """The old list was six rows transcribed from a summary of the DPCO
        schedule. Nothing in a rupee claim may rest on that again."""
        assert rows
        for r in rows:
            assert r["source_tier"] == "primary", r
            assert "NPPA" in r["source"] and "1499(E)" in r["source"]

    def test_the_largest_waste_item_is_priced(self, rows):
        """Ferrous Salt + Folic acid is 34.5% of all expiry on its own and had
        no price at all, which is why no headline could be published."""
        assert any(r["item_match"].lower().startswith("ferrous") for r in rows)

    def test_prices_are_positive_numbers(self, rows):
        for r in rows:
            assert float(r["ceiling_price_inr"]) > 0, r

    def test_the_unconvertible_items_are_absent_rather_than_guessed(self, rows):
        """Sodium chloride is priced per 1000 ml glass bottle, Chlorhexidine
        and Timolol per millilitre, Artesunate + Sulphadoxine per co-blistered
        course. Each would need a pack size this project does not hold, so
        each stays unpriced and `build_waste_value.py` counts it as uncovered.
        Together they are 701 units, 2.1% of expiry."""
        names = {r["item_match"].lower() for r in rows}
        for absent in ("chlorhexidine", "timolol", "sodium chloride"):
            assert absent not in names, (
                f"{absent} was priced; check a pack size was not invented")


@pytest.mark.skipif(not PDF.exists(), reason="compendium PDF is gitignored")
class TestTheExtractionInvariant:
    def test_every_priced_line_becomes_a_row(self):
        """The only check that catches this parser losing data. It failed at
        981 rows and again at 994 while the wrap handling was being written; a
        magic threshold would have passed both."""
        rows, priced_lines = ex.parse(PDF)
        assert len(rows) == priced_lines
        assert priced_lines > 900
