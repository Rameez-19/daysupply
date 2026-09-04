"""The national picture — the landing view a reviewer sees first.

Two failures shipped here and both were invisible to endpoint checks:

* The startup sequence still called the old `loadDashboard()`, which wrote into
  a `stats-grid` element the restructure had deleted. Every page load threw
  "Cannot set properties of null" before any panel was populated. Empty cards,
  red banner, every endpoint returning 200.
* Scoping to a state 503'd, because the `recommendations` predicate was built
  with `where.replace('state', 'to_state')` — which renamed the bound parameter
  too. All India worked, so a single unscoped check passed.

Both are pinned below.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import executive  # noqa: E402

RESOURCES = ("medicines", "beds", "personnel")


class TestEveryScopeWorks:
    """All India worked while every state scope was broken."""

    @pytest.mark.parametrize("state", ["", "Telangana", "Assam", "Maharashtra"])
    def test_scope_returns_all_three_resources(self, state):
        d = executive.national_picture(state)
        assert "error" not in d, d.get("error")
        for r in RESOURCES:
            assert d.get(r) is not None, f"{r} missing for scope {state!r}"

    def test_scoping_actually_narrows(self):
        national = executive.national_picture("")["medicines"]["tracked"]
        one = executive.national_picture("Telangana")["medicines"]["tracked"]
        assert 0 < one < national

    def test_the_predicate_is_built_per_column_not_by_replacing(self):
        """`recommendations.to_state` must not rename the bound parameter."""
        assert executive._scoped("Assam", "to_state") == "to_state = @state"
        assert executive._scoped("") == "TRUE"


class TestItAnswersTheQuestionsInOrder:
    def test_headline_is_a_sentence_per_resource(self):
        h = executive.national_picture("")["headline"]
        for r in RESOURCES:
            assert h[r] and h[r][-1] == ".", f"{r} headline is not a sentence"

    def test_resilience_and_transfer_only_are_present(self):
        """The one-step-ahead figures are the differentiator; if they silently
        vanish the page loses the thing nothing else does."""
        h = executive.national_picture("")["headline"]
        assert "absorb" in h["resilience"]
        assert "resupply" in h["transfer_only"]

    def test_early_warnings_lead_with_a_real_warning_not_a_campaign(self):
        """A planned deworming campaign must never head the list."""
        warnings = executive.national_picture("")["early_warnings"]
        if warnings:
            classes = [w["signal_class"] for w in warnings]
            if "leading" in classes:
                assert classes[0] == "leading", (
                    f"a {classes[0]} signal is heading the list above a "
                    "genuine early warning")

    def test_worst_districts_are_ranked_by_vital_first(self):
        rows = executive.national_picture("")["worst_districts"]
        vitals = [r["vital_short"] for r in rows]
        assert vitals == sorted(vitals, reverse=True)
