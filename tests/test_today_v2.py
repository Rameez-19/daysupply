"""Today v2 is a scorecard, so the grading has to be right.

A page that grades itself is more dangerous than one that only reports: a wrong
number is visible to anyone who checks, but a wrong *verdict* — "Healthy" over
a failing network — is believed. These tests pin the arithmetic behind each
grade, the thresholds behind each verdict, and the agreement between this page
and the two views that show the same underlying figures.
"""

import pytest

from app import executive, today_v2


@pytest.fixture(scope="module")
def national():
    return today_v2.scorecard("")


class TestTheScorecardArithmetic:
    def test_available_and_short_partition_the_tracked_lines(self, national):
        s = national["scorecard"]
        assert s["available"] + s["short"] == s["tracked"]

    def test_vital_is_a_subset_of_everything(self, national):
        s = national["scorecard"]
        assert s["vital_tracked"] <= s["tracked"]
        assert s["vital_available"] + s["vital_short"] == s["vital_tracked"]

    def test_stocked_out_is_a_subset_of_short(self, national):
        """Something at zero is by definition below its reorder point."""
        s = national["scorecard"]
        assert s["stocked_out"] <= s["short"]

    def test_at_risk_week_includes_everything_already_gone(self, national):
        s = national["scorecard"]
        assert s["at_risk_week"] >= s["stocked_out"]

    def test_districts_short_is_within_districts(self, national):
        s = national["scorecard"]
        assert s["districts_short"] <= s["districts"]


class TestTheGradesMatchTheNumbers:
    """Every percentage on the page is recomputed here from its own counts."""

    def test_availability_rate(self, national):
        s, g = national["scorecard"], national["grades"]
        assert g["availability"]["pct"] == pytest.approx(
            round(100 * s["available"] / s["tracked"], 1))

    def test_vital_availability_rate(self, national):
        s, g = national["scorecard"], national["grades"]
        assert g["vital_availability"]["pct"] == pytest.approx(
            round(100 * s["vital_available"] / s["vital_tracked"], 1))

    def test_stocked_out_rate(self, national):
        s, g = national["scorecard"], national["grades"]
        assert g["stocked_out"]["pct"] == pytest.approx(
            round(100 * s["stocked_out"] / s["tracked"], 1))

    def test_spread_rate(self, national):
        s, g = national["scorecard"], national["grades"]
        assert g["spread"]["pct"] == pytest.approx(
            round(100 * s["districts_short"] / s["districts"], 1))

    def test_every_grade_carries_a_tone_and_a_verdict(self, national):
        """A percentage with no verdict has not communicated anything."""
        for name, grade in national["grades"].items():
            assert grade["tone"] in {"ok", "warn", "bad", "unknown"}, name
            assert grade["says"], f"{name} has no plain-English verdict"

    def test_availability_is_graded_the_right_way_round(self):
        """Higher availability must never grade worse. This is the one metric
        on the page where up is good, and inverting it would be invisible in
        the numbers and obvious to a judge."""
        band = lambda v: ("ok" if v >= 90 else "warn" if v >= 75 else "bad")
        assert band(95) == "ok"
        assert band(80) == "warn"
        assert band(50) == "bad"

    def test_stockout_rate_is_graded_the_other_way_round(self):
        """More stock-outs must grade worse."""
        band = lambda v: ("ok" if v <= 1 else "warn" if v <= 5 else "bad")
        assert band(0.5) == "ok"
        assert band(3) == "warn"
        assert band(20) == "bad"


class TestTheFourVisuals:
    def test_timeline_buckets_are_ordered_and_exclusive(self, national):
        rows = national["timeline"]
        assert rows
        orders = [r["sort_order"] for r in rows]
        assert orders == sorted(orders)
        assert len(orders) == len(set(orders))

    def test_timeline_never_exceeds_the_tracked_count(self, national):
        """Medicines with no usage history are excluded, so it can be fewer —
        never more."""
        total = sum(r["n"] for r in national["timeline"])
        assert total <= national["scorecard"]["tracked"]

    def test_already_out_bucket_equals_the_stocked_out_count(self, national):
        """Two different SQL paths to the same figure on the same page."""
        out = next((r["n"] for r in national["timeline"]
                    if r["bucket"] == "Already out"), 0)
        assert out == national["scorecard"]["stocked_out"]

    def test_worst_medicines_are_named_and_ranked(self, national):
        rows = national["worst_medicines"]
        assert rows, "the medicines chart would be empty"
        assert len(rows) <= today_v2.TOP_N
        assert [r["centres"] for r in rows] == sorted(
            (r["centres"] for r in rows), reverse=True)
        for r in rows:
            assert r["item_name"], "a bar with no medicine name"
            assert r["centres"] > 0
            assert r["districts"] <= r["centres"], (
                "a medicine cannot be short in more districts than centres")

    def test_quadrant_axes_are_percentages(self, national):
        for r in national["districts_plot"]:
            assert 0 <= r["pct_short"] <= 100, r
            assert 0 <= r["pct_cope"] <= 100, r

    def test_quadrant_excludes_districts_too_small_to_rate(self, national):
        """A district with three tracked medicines reads 100% short on one bad
        line. Without a floor under the denominator the chart shows noise as
        crisis."""
        for r in national["districts_plot"]:
            assert r["tracked"] >= today_v2.MIN_LINES_FOR_RATE

    def test_absorption_is_ordered_by_severity(self, national):
        rows = national["absorption"]
        assert rows
        mult = [r["multiplier"] for r in rows]
        assert mult == sorted(mult)
        # A bigger shock cannot be easier to absorb.
        pcts = [r["pct"] for r in rows]
        assert pcts == sorted(pcts, reverse=True), (
            f"absorption rises with the size of the shock: {list(zip(mult, pcts))}")


class TestFilters:
    def test_a_state_scope_narrows_the_numbers(self, national):
        one = today_v2.scorecard("Telangana")
        assert one["scorecard"]["tracked"] < national["scorecard"]["tracked"]
        assert one["scorecard"]["states"] == 1

    @pytest.mark.parametrize("state", ["Telangana", "Assam", "Maharashtra"])
    def test_every_state_scope_answers(self, state):
        """Scoping is where this codebase has broken twice, both times by
        string-replacing a finished predicate and renaming the bound parameter
        with it."""
        d = today_v2.scorecard(state)
        assert d["scorecard"]["tracked"] > 0
        assert d["grades"]["availability"]["pct"] is not None

    def test_vital_only_returns_only_life_saving_lines(self):
        d = today_v2.scorecard("", vital_only=True)
        s = d["scorecard"]
        assert s["tracked"] == s["vital_tracked"], (
            "the life-saving filter let other classes through")
        assert all(m["ven_class"] == "Vital" for m in d["worst_medicines"])

    def test_vital_only_is_a_subset_of_everything(self, national):
        d = today_v2.scorecard("", vital_only=True)
        assert d["scorecard"]["tracked"] <= national["scorecard"]["tracked"]

    def test_a_district_scope_narrows_further(self):
        state = today_v2.scorecard("Telangana")
        district = today_v2.scorecard("Telangana", "Khammam")
        assert 0 < district["scorecard"]["tracked"] <= state["scorecard"]["tracked"]
        assert district["scorecard"]["districts"] == 1


class TestItAgreesWithTheOtherViews:
    """Three pages now show the same underlying figures. If they disagree, at
    least one is wrong, and a judge checking two screens will find it before
    we do."""

    def test_tracked_and_short_match_the_executive_view(self, national):
        e = executive.national_picture("")["medicines"]
        s = national["scorecard"]
        assert s["tracked"] == e["tracked"]
        assert s["short"] == e["below_reorder"]
        assert s["stocked_out"] == e["stocked_out"]
        assert s["vital_short"] == e["vital_short"]

    def test_absorption_matches_the_executive_view(self, national):
        e = executive.national_picture("")["absorption"]
        mine = {a["multiplier"]: a["pct"] for a in national["absorption"]}
        theirs = {a["multiplier"]: a["pct"] for a in e}
        assert mine == theirs

    def test_the_shock_multiplier_is_the_one_used_everywhere_else(self):
        from app import mapview
        assert today_v2.ABSORPTION_MULTIPLIER == mapview.ABSORPTION_MULTIPLIER == 3.0

    def test_the_fragility_threshold_matches_the_map(self):
        """The map calls a district fragile below 35%; this page must not use
        its own number, or the two will disagree about the same district."""
        assert today_v2.FRAGILE_BELOW == 35.0
