"""The drafted escalation note: grounded, checked, never silently wrong.

Gemini writes the note; these tests never call it. What they pin is the
contract around it — the facts it is given, the number check on what comes
back, and that a draft with a foreign figure is flagged rather than hidden.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import brief, capture  # noqa: E402

ROW = {
    "facility_id": "IN-1", "facility_name": "Sonawade PHC", "state": "Maharashtra",
    "district": "Sindhudurg", "item_id": "ALBENDAZOLE", "item_name": "Albendazole",
    "unit": "tablet", "ven_class": "Essential", "on_hand": 0, "reorder_point": 412.0,
    "shortfall": 412, "days_of_cover": 0.0, "lead_time_days": 13.0,
    "lead_time_is_estimated": True, "distance_to_hq_km": 61.7, "status": "stockout",
    "has_transfer": False, "too_late_to_order": True,
}


@pytest.fixture
def row(monkeypatch):
    monkeypatch.setattr(brief, "find_row", lambda f, i: {**ROW, "group": "escalate"})


def _model(monkeypatch, reply):
    calls = []

    def fake(contents, system_instruction=None):
        calls.append((contents, system_instruction))
        return reply
    monkeypatch.setattr(capture, "_generate", fake)
    return calls


class TestGrounding:
    def test_the_model_gets_only_the_rows_figures_and_the_rules(self, row, monkeypatch):
        calls = _model(monkeypatch, "Sonawade PHC has 0 days of Albendazole left.")
        brief.draft("IN-1", "ALBENDAZOLE")
        contents, system = calls[0]
        assert system is brief.SYSTEM
        assert '"on_hand": 0' in contents and '"lead_time_days": 13' in contents
        assert "Use ONLY the numbers in the facts" in system
        assert "Do not state or guess WHY" in system

    def test_the_distance_is_rounded_before_the_model_sees_it(self, row):
        facts = brief._facts(ROW)
        assert facts["distance_to_hq_km"] == 62
        assert facts["days_of_cover"] == 0 and facts["lead_time_days"] == 13.0

    def test_hindi_is_requested_by_name(self, row, monkeypatch):
        calls = _model(monkeypatch, "ठीक है")
        out = brief.draft("IN-1", "ALBENDAZOLE", lang="hi")
        assert "Hindi" in calls[0][0]
        assert out["lang"] == "hi"

    def test_an_unknown_language_falls_back_to_english(self, row, monkeypatch):
        _model(monkeypatch, "ok")
        assert brief.draft("IN-1", "ALBENDAZOLE", lang="xx")["lang"] == "en"


class TestTheNumberCheck:
    def test_a_draft_using_only_the_rows_numbers_passes(self, row, monkeypatch):
        _model(monkeypatch, "Sonawade PHC holds 0 tablets of Albendazole, 412 "
                           "below its reorder point; delivery takes 13 days and "
                           "the centre is 62 km from headquarters.")
        out = brief.draft("IN-1", "ALBENDAZOLE")
        assert out["numbers_checked"] is True
        assert out["unverified_numbers"] == []
        assert "checked against them" in out["basis"]

    def test_a_foreign_figure_is_flagged_not_hidden(self, row, monkeypatch):
        _model(monkeypatch, "Sonawade PHC has 0 days of cover; about 3,500 "
                           "patients a month depend on it and 2 nurses are on duty.")
        out = brief.draft("IN-1", "ALBENDAZOLE")
        assert out["numbers_checked"] is False
        assert out["unverified_numbers"] == ["2", "3500"]
        assert "not in the data" in out["basis"]
        assert "3,500" in out["note"]          # the draft is still returned

    def test_thousands_separators_do_not_fool_the_check(self):
        assert brief._numbers("1,250 and 1250 and 13.5") == {"1250", "13.5"}


class TestFailure:
    def test_a_missing_shortage_is_an_error_not_a_note(self, monkeypatch):
        monkeypatch.setattr(brief, "find_row", lambda f, i: None)
        out = brief.draft("IN-9", "NOTHING")
        assert out["error"].startswith("no open shortage")

    def test_a_busy_model_is_reported_as_retryable(self, row, monkeypatch):
        def boom(contents, system_instruction=None):
            raise capture.ModelUnavailable(4, "503")
        monkeypatch.setattr(capture, "_generate", boom)
        out = brief.draft("IN-1", "ALBENDAZOLE")
        assert out["retryable"] is True and out["facts"]["item_name"] == "Albendazole"


class TestFindRow:
    def test_the_group_is_named_from_the_triage_flags(self, monkeypatch):
        from app import action_queue
        monkeypatch.setattr(action_queue, "triage",
                            lambda **kw: {"all_shortages": [ROW]})
        assert brief.find_row("IN-1", "ALBENDAZOLE")["group"] == "escalate"
        assert brief.find_row("IN-1", "OTHER") is None
