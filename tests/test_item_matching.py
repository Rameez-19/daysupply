"""Item matching — the guard against a hallucinated drug code.

Gemini returns the drug name *as spoken*; the item_id is resolved server-side
against the catalogue. These tests pin both halves of that contract: real
spoken names resolve, and unrelated speech resolves to nothing so it lands in
the review queue instead of becoming a wrong stock record.

They query BigQuery for the catalogue, so they need credentials.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import items  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def catalog():
    items.reset()
    data = items.catalog()
    assert data, "Item catalogue is empty"
    return data


class TestCatalogue:
    def test_full_nlem_is_loaded(self, catalog):
        """The whole National List, not a shortlist."""
        assert len(catalog) > 350

    def test_every_item_has_required_fields(self, catalog):
        for item in catalog:
            assert item["item_id"]
            assert item["display_name"]
            assert item["unit"]
            assert item["ven_class"] in ("Vital", "Essential", "Desirable")

    def test_forecast_items_are_a_subset(self, catalog):
        forecast = [i for i in catalog if i["is_forecast_item"]]
        assert 25 <= len(forecast) <= 40, len(forecast)

    def test_every_forecast_item_has_a_real_driver(self, catalog):
        """No forecast item may fall back to a flat seasonal baseline.

        The allowed set is read from `hmis_drivers` rather than hardcoded, so
        this test cannot go stale the way its predecessor did — that version
        listed the original eleven indicators by name and would have passed a
        driver that no longer exists.
        """
        from ingestion.hmis_drivers import DRIVERS
        for item in catalog:
            if not item["is_forecast_item"]:
                continue
            driver = item["demand_driver"]
            assert driver, f"{item['item_id']} is forecast with no driver"
            assert driver in DRIVERS, f"{item['item_id']} -> unknown {driver!r}"

    def test_every_forecast_item_has_a_consumption_rate(self, catalog):
        for item in catalog:
            if item["is_forecast_item"]:
                assert item["units_per_driver_event"], item["item_id"]

    def test_every_driver_assignment_is_justified(self, catalog):
        """A mapping table alone is not defensible under questioning."""
        for item in catalog:
            if item["is_forecast_item"]:
                assert (item["driver_rationale"] or "").strip(), (
                    f"{item['item_id']} has a driver but no clinical rationale")

    def test_atc_codes_are_null_not_guessed(self, catalog):
        """Codes are present or absent; never blank strings."""
        for item in catalog:
            assert item["atc_code"] is None or len(item["atc_code"]) >= 4


class TestMatching:
    @pytest.mark.parametrize("spoken,expected", [
        ("paracetamol", "PARACETAMOL"),
        ("para", "PARACETAMOL"),
        ("pcm", "PARACETAMOL"),
        ("bukhar ki goli", "PARACETAMOL"),
        ("dolo 650", "PARACETAMOL"),
        ("amoxy", "AMOXICILLIN"),
        ("ORS ka packet", "ORAL-REHYDRATION-SALTS"),
        ("khoon ki goli", "FERROUS-SALT-FOLIC-ACID"),
        ("sugar ki goli", "METFORMIN"),
        ("asthalin", "SALBUTAMOL"),
        ("chloroquine", "CHLOROQUINE"),
    ])
    def test_spoken_names_resolve(self, spoken, expected):
        assert items.match(spoken) == expected

    @pytest.mark.parametrize("spoken", [
        "metformin 500", "metformin 500mg", "amlodipine 5mg",
        "ceftriaxone 1g",
    ])
    def test_strength_is_stripped(self, spoken):
        """A strength in the utterance must not prevent the match."""
        assert items.match(spoken) is not None

    @pytest.mark.parametrize("noise", [
        "banana",
        "hello there",
        "the patient came in",
        "xyzzy",
        "my name is ramesh",
        "aaj kuch nahi aaya",
        "500",
        "",
    ])
    def test_unrelated_speech_matches_nothing(self, noise):
        """A wrong item_id is worse than no item_id — this must stay None.

        Anything unmatched goes to the review queue for a human instead of
        becoming a stock record against the wrong drug.
        """
        assert items.match(noise) is None
