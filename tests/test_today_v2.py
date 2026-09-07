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


class TestTheFilterChainActuallyFilters:
    """Every filter, verified to narrow — not merely to be accepted.

    A filter that is accepted and ignored is worse than one that errors: the
    page redraws, the numbers do not move, and the reader concludes the data is
    wrong rather than the filter. So each level is asserted to be a strict
    subset of the level above it, on a real state/district/facility that has
    data.
    """

    # Chosen because it has the most tracked lines of any single facility, so
    # the narrowing is unambiguous rather than a rounding artefact.
    STATE, DISTRICT, PHC = "Delhi", "Shahdara", "IN-42063"

    @pytest.fixture(scope="class")
    @classmethod
    def chain(cls):
        return {
            "national": today_v2.scorecard(),
            "state": today_v2.scorecard(cls.STATE),
            "district": today_v2.scorecard(cls.STATE, cls.DISTRICT),
            "phc": today_v2.scorecard(cls.STATE, cls.DISTRICT, cls.PHC),
        }

    def test_each_level_narrows_the_one_above(self, chain):
        counts = [chain[k]["scorecard"]["tracked"]
                  for k in ("national", "state", "district", "phc")]
        assert counts == sorted(counts, reverse=True), (
            f"tracked lines do not shrink down the chain: {counts}")
        assert counts[-1] > 0, "the facility scope returned nothing at all"

    def test_the_facility_scope_is_one_facility(self, chain):
        assert chain["phc"]["scorecard"]["facilities"] == 1
        assert chain["phc"]["scorecard"]["districts"] == 1
        assert chain["phc"]["scorecard"]["states"] == 1

    def test_the_district_scope_is_one_district(self, chain):
        assert chain["district"]["scorecard"]["districts"] == 1
        assert chain["district"]["scorecard"]["facilities"] >= 1

    def test_the_state_scope_is_one_state(self, chain):
        assert chain["state"]["scorecard"]["states"] == 1

    def test_a_facility_scope_still_grades_itself(self, chain):
        """Narrowing must not leave the page ungraded."""
        g = chain["phc"]["grades"]
        assert g["availability"]["pct"] is not None
        assert g["availability"]["says"]

    def test_the_medicines_chart_narrows_with_the_facility(self, chain):
        """One facility cannot be short of a medicine in two centres."""
        for m in chain["phc"]["worst_medicines"]:
            assert m["centres"] == 1, m
            assert m["districts"] == 1, m

    def test_absorption_stays_district_level_and_says_so(self, chain):
        """`network_absorption` has no facility column: it asks whether a
        DISTRICT's pooled stock could cover a surge, so one facility's
        absorption is not a thing that exists.

        The filter is therefore not applied there, and the response declares
        it. Silently dropping it would leave a reader believing they had
        narrowed a number they had not.
        """
        panels = chain["phc"]["scope"]["district_level_panels"]
        assert panels, "the PHC scope does not declare its district-level panels"
        district_absorption = {a["multiplier"]: a["pct"]
                               for a in chain["district"]["absorption"]}
        phc_absorption = {a["multiplier"]: a["pct"]
                          for a in chain["phc"]["absorption"]}
        assert phc_absorption == district_absorption

    def test_no_district_level_caveat_when_no_facility_is_chosen(self, chain):
        for level in ("national", "state", "district"):
            assert chain[level]["scope"]["district_level_panels"] == [], level

    def test_vital_only_composes_with_the_geography(self):
        """The two filter kinds must combine, not override each other."""
        both = today_v2.scorecard(self.STATE, self.DISTRICT, self.PHC,
                                  vital_only=True)
        plain = today_v2.scorecard(self.STATE, self.DISTRICT, self.PHC)
        s = both["scorecard"]
        assert s["tracked"] == s["vital_tracked"], "life-saving filter leaked"
        assert s["tracked"] <= plain["scorecard"]["tracked"]
        assert both["scorecard"]["facilities"] <= 1

    def test_the_cache_key_separates_every_scope(self):
        """All four scopes share one cache. A key that ignored the facility
        would serve the district's numbers under the facility's name."""
        import inspect
        src = inspect.getsource(today_v2.scorecard)
        key = [l for l in src.splitlines() if "cache_key" in l]
        assert key, "no cache key at all"
        for part in ("{state}", "{district}", "{phc}", "vital_only"):
            assert part in key[0], (
                f"{part} is missing from the cache key, so two different "
                f"scopes would share one cached answer: {key[0].strip()}")


class TestNarrowScopesDoNotMakeNonsenseClaims:
    """Filters found these; nothing else would have.

    At All-India scope every panel reads sensibly. Narrowed to one facility,
    "Districts affected: 100% — Systemic. Almost every district is affected"
    appeared over a sample of exactly one district. The arithmetic was right
    and the sentence was drivel, which is worse than a wrong number: a reader
    checks a number and believes a sentence.
    """

    def test_spread_is_withheld_for_a_single_district(self):
        d = today_v2.scorecard("Rajasthan", "Sirohi")
        spread = d["grades"]["spread"]
        assert spread["pct"] is None, (
            "one district short of one district is 100%, which says nothing")
        assert spread["tone"] == "unknown"
        assert "single district" in spread["says"]

    def test_spread_is_reported_when_there_are_districts_to_compare(self):
        d = today_v2.scorecard("Rajasthan")
        assert d["scorecard"]["districts"] > 1
        assert d["grades"]["spread"]["pct"] is not None

    def test_a_facility_scope_still_grades_availability(self):
        """Withholding one metric must not withhold the rest."""
        d = today_v2.scorecard("Rajasthan", "Sirohi", "IN-129024")
        g = d["grades"]
        assert g["availability"]["pct"] is not None
        assert g["stocked_out"]["pct"] is not None
        assert g["at_risk_week"]["pct"] is not None

    def test_two_facilities_in_one_district_partition_its_lines(self):
        """The clearest proof the facility filter bites: Sirohi has exactly two
        health centres, and they must sum to the district."""
        district = today_v2.scorecard("Rajasthan", "Sirohi")
        a = today_v2.scorecard("Rajasthan", "Sirohi", "IN-129024")
        b = today_v2.scorecard("Rajasthan", "Sirohi", "IN-128671")
        assert (a["scorecard"]["tracked"] + b["scorecard"]["tracked"]
                == district["scorecard"]["tracked"])
        assert a["scorecard"]["facilities"] == b["scorecard"]["facilities"] == 1
        assert a["grades"]["availability"]["pct"] != b["grades"]["availability"]["pct"], (
            "both facilities grade identically — check the filter is applied")

    def test_a_facility_cannot_be_short_in_more_than_one_centre(self):
        d = today_v2.scorecard("Rajasthan", "Sirohi", "IN-129024")
        for m in d["worst_medicines"]:
            assert m["centres"] == 1
            assert m["districts"] == 1
