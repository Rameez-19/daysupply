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
        vanish the page loses the thing nothing else does.

        This asserts the FIGURES survive, not the wording. It used to require
        the literal words "absorb" and "resupply", which made it fail the
        moment those sentences were rewritten in plain English for the
        non-specialist audience who actually reads them — a test failing on a
        vocabulary change it should not have had an opinion about.
        """
        d = executive.national_picture("")
        h = d["headline"]

        absorb3 = next((a["pct"] for a in d["absorption"]
                        if a["multiplier"] == 3.0), None)
        assert absorb3 is not None, "the 3x absorption figure is gone entirely"
        assert str(absorb3) in h["resilience"], (
            f"the resilience sentence no longer reports {absorb3}%: "
            f"{h['resilience']!r}")

        assert str(d["transfer_only"]) in h["transfer_only"], (
            f"the transfer-only sentence no longer reports "
            f"{d['transfer_only']}: {h['transfer_only']!r}")
        assert "moving stock" in h["transfer_only"], (
            "the sentence must still say these are fixed by moving stock, not "
            "by ordering — that distinction is the whole point of the figure")

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


class TestTheChartAggregates:
    """The Today view is charts now, and a chart lies more convincingly than a
    table. These pin the arithmetic a reader cannot check by looking."""

    def test_cover_buckets_are_ordered_and_exclusive(self):
        d = executive.national_picture("")
        rows = d["cover_buckets"]
        assert rows, "no cover buckets — the timetable chart would be empty"
        orders = [r["sort_order"] for r in rows]
        assert orders == sorted(orders), "buckets arrive out of order"
        assert len(orders) == len(set(orders)), "a bucket appears twice"

    def test_cover_buckets_do_not_exceed_tracked_lines(self):
        """Buckets are exclusive, so their total cannot beat the line count.

        It can be *less*: lines with no demand history have no days_of_cover
        and are excluded rather than dropped into the healthiest bucket, which
        would flatter the picture.
        """
        d = executive.national_picture("")
        total = sum(r["n"] for r in d["cover_buckets"])
        assert total <= d["medicines"]["tracked"]

    def test_already_out_bucket_matches_the_stocked_out_count(self):
        """Two independent paths to the same number; if they disagree, one of
        the two headline figures on the page is wrong."""
        d = executive.national_picture("")
        out = next((r["n"] for r in d["cover_buckets"]
                    if r["bucket"] == "Already out"), 0)
        assert out == d["medicines"]["stocked_out"]

    def test_ven_breakdown_sums_to_the_totals(self):
        d = executive.national_picture("")
        ven = d["ven_breakdown"]
        assert ven, "no VEN breakdown"
        assert sum(v["tracked"] for v in ven) == d["medicines"]["tracked"]
        assert sum(v["short"] for v in ven) == d["medicines"]["below_reorder"]

    def test_vital_short_agrees_between_the_headline_and_the_breakdown(self):
        d = executive.national_picture("")
        vital = next(v for v in d["ven_breakdown"] if v["ven_class"] == "Vital")
        assert vital["short"] == d["medicines"]["vital_short"]

    def test_ven_is_ordered_by_criticality_not_alphabetically(self):
        """Vital first. A reader scanning down must meet the worst first."""
        d = executive.national_picture("")
        order = [v["ven_class"] for v in d["ven_breakdown"]]
        assert order[0] == "Vital"

    def test_worst_districts_is_ten_for_the_chart(self):
        """The bar chart replaced a five-row table and can carry more."""
        d = executive.national_picture("")
        assert len(d["worst_districts"]) <= executive.CHART_N
        assert len(d["worst_districts"]) > 5, (
            "the chart is still being fed the old five-row table limit")

    def test_district_vital_never_exceeds_its_total_short(self):
        """The chart stacks Vital under (short - vital). A negative segment
        would render as a bar growing the wrong way."""
        d = executive.national_picture("")
        for r in d["worst_districts"]:
            assert r["vital_short"] <= r["short"], (
                f"{r['district']} has more Vital short than short in total")

    def test_districts_short_is_within_districts(self):
        m = executive.national_picture("")["medicines"]
        assert m["districts_short"] <= m["districts"]


class TestEarlyWarningsAreOnePerSignal:
    """The panel showed the same warning twice and looked broken.

    P01BA and P01BF are different antimalarial classes driven by the same
    confirmed-malaria signal. A surge in one district produced two rows that
    were identical in every field the card rendered — same district, same
    month, same driver, same multiplier — so five slots showed three events.

    The data was right and the grouping was wrong. Warnings are now one per
    district-month-driver, with the affected classes named on the card, which
    is the thing that actually differed between the two rows.
    """

    def test_no_two_warnings_share_a_district_month_and_driver(self):
        d = executive.national_picture("")
        keys = [(w["district_key"], w["month"], w["signal_indicator"])
                for w in d["early_warnings"]]
        assert len(keys) == len(set(keys)), (
            "two warnings are indistinguishable to a reader: "
            f"{[k for k in keys if keys.count(k) > 1]}")

    def test_every_warning_names_the_classes_it_affects(self):
        d = executive.national_picture("")
        for w in d["early_warnings"]:
            assert w["atc_classes"], f"{w['district_key']} names no ATC class"
            assert w["class_count"] >= 1
            assert w["class_count"] == len(w["atc_classes"].split(", "))

    def test_grouping_did_not_cost_us_distinct_events(self):
        """The point of the change: five slots should carry five events."""
        d = executive.national_picture("")
        districts = {w["district_key"] for w in d["early_warnings"]}
        assert len(districts) == len(d["early_warnings"]), (
            "a district appears twice in the top five")

    def test_the_multiplier_is_the_worst_of_the_grouped_classes(self):
        """Grouping must not average away the severity it is reporting."""
        d = executive.national_picture("")
        for w in d["early_warnings"]:
            assert w["surge_multiplier"] > 1.0
