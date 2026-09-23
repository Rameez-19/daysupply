"""The Plan ahead forecast, and the claim it is allowed to make.

This panel carries the challenge's "forecast demand" and "shared predictive
modelling across India's states" on its own. Two things therefore have to hold
and keep holding:

1. The curve must be in a unit. Units are per medicine class — tablets, vials,
   capsules — so a curve summed across classes is a number in no unit at all.
   The first version did exactly that and reported 70 million of nothing.

2. The 19.4% -> 14.4% figure must be arithmetic on held-out months, not a
   constant carried in the code. If the evaluation table changes, the page must
   change with it or say it cannot score.

The window is eight months, not twelve. April to June is the history each
district is allowed to see; it is the design, not missing data, and a test that
demanded twelve would be enforcing the wrong thing.
"""

import pytest

from app import forecast_view


@pytest.fixture(scope="module")
def national():
    return forecast_view.outlook()


class TestTheCurveIsInAUnit:
    def test_a_class_is_always_chosen(self, national):
        """Never aggregate across ATC classes — see the module docstring."""
        assert national["scope"]["atc_class"], national["scope"]

    def test_an_explicit_class_is_the_one_returned(self, national):
        chosen = national["classes"][1]["atc_class"]
        other = forecast_view.outlook(atc_class=chosen)
        assert other["scope"]["atc_class"] == chosen

    def test_the_default_is_the_busiest_class_in_scope(self, national):
        volumes = {c["atc_class"]: c["volume"] for c in national["classes"]}
        assert national["scope"]["atc_class"] == max(volumes, key=volumes.get)

    def test_the_curve_is_in_a_named_unit(self, national):
        """The series underneath counts clinic visits, not medicine. Without
        the conversion the axis reads 33.8 million of nothing."""
        assert national["scope"]["unit"], national["scope"]
        assert national["scope"]["units_per_event"] > 0
        assert national["scope"]["unit"] in national["summary"]["seasonality"]

    def test_no_two_classes_offer_the_same_curve(self, national):
        """`pattern_exchange_eval.actual` is the HMIS demand driver, so classes
        sharing a driver hold byte-identical rows — Paracetamol and Ibuprofen
        matched on all 928. Nine such groups covered 26 of 36 classes, and the
        dropdown offered 36 entries that drew 19 distinct curves. Multiplying
        by units_per_driver_event is what separates them; if that is ever
        dropped, this fails rather than the reader noticing."""
        curves = {}
        for c in national["classes"][:8]:
            d = forecast_view.outlook(atc_class=c["atc_class"])
            sig = tuple(r["actual"] for r in d["curve"])
            assert sig not in curves, (
                f"{c['atc_class']} ({c['medicines']}) draws exactly the same "
                f"curve as {curves[sig]}")
            curves[sig] = f"{c['atc_class']} ({c['medicines']})"

    def test_the_dropdown_opens_on_the_class_the_chart_drew(self, national):
        """Two classes sharing a driver tied at exactly 260,662,659 driver
        events, so which one "was busiest" came down to whichever row BigQuery
        returned first — and the dropdown could open on a different class from
        the one the chart had drawn. Both queries now rank on converted units
        and break any remaining tie on the class code, so they cannot disagree.
        """
        vols = [c["volume"] for c in national["classes"]]
        assert vols == sorted(vols, reverse=True)
        assert national["classes"][0]["atc_class"] ==             national["scope"]["atc_class"]

    def test_the_only_classes_left_tying_share_a_driver_and_a_course(
            self, national):
        """Two ties survive the conversion, and both are arithmetic rather than
        the old defect: Haloperidol and Fluoxetine are both 7.5 tablets per
        mental-illness outpatient visit, Phenytoin and Carbamazepine both 9.0
        per epilepsy visit. Same driver and same course size genuinely means
        the same number of tablets. What was wrong before was Paracetamol and
        Ibuprofen matching while needing 1.2 and 0.35 tablets per visit — the
        number was simply wrong for one of them.

        34 distinct volumes across 36 classes; if that falls, a conversion has
        gone missing again."""
        vols = [c["volume"] for c in national["classes"]]
        assert len(set(vols)) >= len(vols) - 2, (
            f"{len(vols) - len(set(vols))} classes tie on volume; only the two "
            "same-driver-same-course pairs are expected to")

    def test_every_offered_class_can_actually_be_drawn(self, national):
        """A dropdown entry that produces an empty chart is a dead control."""
        for c in national["classes"][:5]:
            d = forecast_view.outlook(atc_class=c["atc_class"])
            assert d["curve"], c


class TestTheMonthsAreTheFinancialYear:
    def test_the_curve_is_contiguous(self, national):
        """Ordered on the calendar year the held-out window splits in half and
        the chart grows a hole in the middle — a rendering artefact that reads
        as missing data."""
        order = list(forecast_view.MONTH_ORDER)
        got = [r["month"] for r in national["curve"]]
        idx = [order.index(m) for m in got]
        assert idx == list(range(idx[0], idx[0] + len(idx))), got

    def test_it_is_sorted(self, national):
        order = list(forecast_view.MONTH_ORDER)
        idx = [order.index(r["month"]) for r in national["curve"]]
        assert idx == sorted(idx)

    def test_the_observed_months_are_held_out_of_the_scoring(self, national):
        """April to June is the only history a district may see. Scoring a
        month the model was shown would inflate every figure on the panel."""
        scored = {r["month"] for r in national["curve"]}
        assert not (scored & set(forecast_view.OBSERVED_MONTHS)), scored

    def test_the_summary_counts_the_months_it_actually_has(self, national):
        assert national["summary"]["months"] == len(national["curve"])


class TestTheAccuracyClaimIsArithmetic:
    def test_all_four_arms_are_scored(self, national):
        keys = [a["key"] for a in national["accuracy"]]
        assert keys == [m[0] for m in forecast_view.METHODS]
        for a in national["accuracy"]:
            assert a["wmape"] is not None, a

    def test_borrowing_a_shape_beats_carrying_a_flat_average(self, national):
        s = national["summary"]
        assert s["pooled"] < s["flat"], s
        assert s["gain"] == pytest.approx(round(s["flat"] - s["pooled"], 1))

    def test_the_pooled_shape_beats_both_baselines(self, national):
        """The claim the panel's verdict line actually makes.

        Not "pooled beats all four": for Paracetamol the single most similar
        district scores 11.3% against the pool's 11.9%, and a test demanding
        otherwise would be enforcing a claim the product does not make. The
        pool is chosen for holding up across classes and scopes, not for
        winning every slice — and the panel prints all four so a reader can
        see the slice where it does not."""
        arms = {a["key"]: a["wmape"] for a in national["accuracy"]}
        assert arms["pooled"] < arms["flat"], arms
        assert arms["pooled"] < arms["demo_out"], arms

    def test_pooling_beats_a_twin_from_another_state(self, national):
        """The control is the argument that *which* shape is borrowed
        matters: one look-alike district from another state must not do as
        well as every district's shape pooled.

        This used to assert that the out-of-state twin was the worst arm of
        all. With Uttar Pradesh added it no longer is at every scope: here it
        scores 17.9% against a flat 19.0%, while pooling scores 12.4%. The
        claim that survives, and the one the page makes, is that pooling
        beats the twin. Across all classes the twin is still the worst arm by
        far; the next test pins that."""
        arms = {a["key"]: a["wmape"] for a in national["accuracy"]}
        assert arms["pooled"] < arms["demo_out"], arms

    def test_across_every_class_the_twin_is_the_worst_arm(self):
        from app.bq import run_query
        r = run_query("""
            SELECT SUM(flat_abs_error) / SUM(actual) AS flat,
                   SUM(demo_in_abs_error) / SUM(actual) AS demo_in,
                   SUM(demo_out_abs_error) / SUM(actual) AS demo_out,
                   SUM(pooled_abs_error) / SUM(actual) AS pooled
            FROM `daysupply.daysupply.pattern_exchange_eval`
        """)[0]
        assert r["demo_out"] == max(r.values()), r
        assert r["pooled"] == min(r.values()), r

    def test_the_headline_carries_the_numbers_it_computed(self, national):
        s = national["summary"]
        assert f"{s['flat']}%" in s["headline"]
        assert f"{s['pooled']}%" in s["headline"]
        assert str(s["gain"]) in s["headline"]

    def test_the_headline_never_says_federated_learning(self, national):
        """Districts exchange a twelve-number seasonal shape. Calling that
        federated learning would claim a mechanism this does not implement."""
        text = " ".join(str(v) for v in national["summary"].values()).lower()
        assert "federated" not in text


class TestTheDonorIsNamed:
    def test_donors_are_returned(self, national):
        assert national["donors"], "the cross-state claim has no evidence"

    def test_every_donor_is_in_a_different_state(self, national):
        """The matching is restricted to another state on purpose: a good match
        must not be explainable by the two districts being next door."""
        for d in national["donors"]:
            assert d["donor_state"] != d["receiver_state"], d

    def test_the_summary_counts_the_cross_state_matches(self, national):
        assert national["summary"]["cross_state"] == len(national["donors"])

    def test_profile_distance_is_present_and_non_negative(self, national):
        for d in national["donors"]:
            assert d["profile_distance"] is not None and d["profile_distance"] >= 0, d


class TestScoping:
    @pytest.mark.parametrize("state", ["Maharashtra", "Telangana"])
    def test_a_state_scope_narrows_the_series_count(self, national, state):
        one = forecast_view.outlook(state)
        assert one["summary"]["series"] < national["summary"]["series"]
        assert one["curve"]

    def test_a_state_scope_still_scores_all_four_arms(self):
        d = forecast_view.outlook("Maharashtra")
        for a in d["accuracy"]:
            assert a["wmape"] is not None, a

    def test_a_scope_with_no_history_says_so_rather_than_drawing_nothing(self):
        """An empty chart with no explanation is the failure this project keeps
        having. The flag has to reach the renderer."""
        d = forecast_view.outlook(state="Nowhere")
        assert d["empty"] is True

    def test_the_default_class_follows_the_scope(self):
        """A class that is busiest nationally may not be stocked in one state.
        Carrying the national default into a state scope draws an empty chart."""
        assert forecast_view.default_class("Maharashtra")


class TestThePanelSaysWhenItsOwnForecastIsNotUsable:
    """The dropdown offers 36 classes and the method does not work equally well
    across them. For 18 of them the pooled shape does not beat a flat average
    at all, and 11 score above 40% error — Albendazole worst at 83.5%, because
    it moves on National Deworming Day and a monthly multiplier cannot fit a
    calendar campaign.

    Drawing all 36 with the same confidence would invite a district officer to
    order stock against a number wrong by more than itself. These pin the
    admission in place.
    """

    def test_a_tight_forecast_is_called_usable(self):
        r = forecast_view.outlook(atc_class="N02BE")["summary"]["reliability"]
        assert r["level"] == "ok"
        assert r["helps"] is True

    def test_a_wide_forecast_is_not_dressed_up(self):
        d = forecast_view.outlook(atc_class="P02CA")
        r = d["summary"]["reliability"]
        assert r["level"] == "bad", r
        assert "too wide to order against" in r["text"]
        assert str(d["summary"]["pooled"]) in r["text"]

    def test_a_class_the_exchange_does_not_help_says_so(self):
        """Vitamin A: a flat average beats the pooled shape by 27.1 points. If
        this is ever silently rendered as a win, the 19.4 -> 14.4 headline
        starts standing in for classes it was never measured on."""
        s = forecast_view.outlook(atc_class="A11CA")["summary"]
        assert s["gain"] < 0, s
        assert s["reliability"]["helps"] is False
        assert "does not help" in s["reliability"]["text"]

    def test_the_verdict_never_reads_as_a_negative_removal(self):
        """"removes -27.1 percentage points" is what the hardcoded sentence
        produced."""
        for cls in ("N02BE", "A11CA", "P02CA", "A10BA", "B01AC"):
            text = forecast_view.outlook(
                atc_class=cls)["summary"]["reliability"]["text"]
            assert "removes -" not in text, (cls, text)

    def test_every_class_gets_a_verdict(self, national):
        """A class with no verdict renders a curve with nothing qualifying it,
        which is the state this panel started in."""
        for c in national["classes"]:
            s = forecast_view.outlook(atc_class=c["atc_class"])["summary"]
            r = s["reliability"]
            assert r["text"] and r["level"] in {"ok", "warn", "bad"}, c
            assert str(s["pooled"]) in r["text"], (c, r)

    def test_the_band_follows_the_thresholds(self, national):
        for c in national["classes"]:
            s = forecast_view.outlook(atc_class=c["atc_class"])["summary"]
            p, level = s["pooled"], s["reliability"]["level"]
            if p >= forecast_view.DIRECTIONAL_BELOW:
                assert level == "bad", (c, p, level)
            elif p >= forecast_view.RELIABLE_BELOW:
                assert level in {"warn", "bad"}, (c, p, level)
            elif s["gain"] > 0:
                assert level == "ok", (c, p, level)

    def test_a_class_that_loses_to_a_flat_average_is_never_green(self, national):
        for c in national["classes"]:
            s = forecast_view.outlook(atc_class=c["atc_class"])["summary"]
            if s["gain"] <= 0:
                assert s["reliability"]["level"] != "ok", (c, s["gain"])

    def test_the_driver_is_named_so_a_wide_forecast_is_explainable(self):
        """"83.5% error" on its own reads as a broken model. "Driven by
        Albendazole doses administered" is why, and a district officer can
        check it."""
        d = forecast_view.outlook(atc_class="P02CA")
        assert d["scope"]["driver"], d["scope"]
        assert d["scope"]["driver"] in d["summary"]["reliability"]["text"]

    def test_the_driver_name_is_not_mangled(self):
        """`.lower()` turned Vitamin A into "vitamin a"."""
        d = forecast_view.outlook(atc_class="A11CA")
        assert "Vitamin A" in d["summary"]["reliability"]["text"]

    def test_the_headline_direction_follows_the_arithmetic(self, national):
        """"Forecast error falls from 83.4% to 83.5%" is what the
        unconditional sentence produced for Albendazole."""
        for c in national["classes"]:
            s = forecast_view.outlook(atc_class=c["atc_class"])["summary"]
            if s["gain"] <= 0:
                assert "falls" not in s["headline"], (c, s["headline"])
                assert "does not pay" in s["headline"], (c, s["headline"])
            else:
                assert "falls from" in s["headline"], (c, s["headline"])


class TestTheArmsAreLabelledAsWhatTheyAre:
    """`demo_in` and `demo_out` are in-state and out-of-state, not similar and
    dissimilar. Both take the single closest district on demographic profile
    and differ only in whether it may sit in another state.

    The page called `demo_out` "a deliberately poor twin" and headed its donor
    districts "Who lends the seasonal shape" — so the losing arm's donors were
    presented as the source of the gain, and the one genuinely surprising
    result in the project was rendered as a sanity check. The real finding is
    that the best demographic match in India is a worse donor than no
    seasonality at all, because monthly shape follows monsoon, not demography.
    """

    def test_the_cross_state_arm_is_not_called_a_poor_match(self):
        labels = {k: (lab, note) for k, lab, note in forecast_view.METHODS}
        lab, note = labels["demo_out"]
        blob = f"{lab} {note}".lower()
        for wrong in ("deliberately poor", "least similar", "worst match"):
            assert wrong not in blob, blob
        assert "different state" in blob or "another state" in blob, blob

    def test_the_in_state_arm_says_same_state(self):
        labels = {k: (lab, note) for k, lab, note in forecast_view.METHODS}
        lab, note = labels["demo_in"]
        assert "same state" in f"{lab} {note}".lower()

    def test_the_named_donors_are_the_cross_state_arms(self, national):
        """They come from `district_matches` (rank 1, different state) — the
        demo_out arm. Every one must therefore cross a boundary."""
        for d in national["donors"]:
            assert d["donor_state"] != d["receiver_state"], d

    def test_the_donor_sentence_does_not_claim_it_is_the_method_in_use(
            self, national):
        text = national["summary"]["donor"].lower()
        assert "borrows the seasonal shape of" not in text, text
        assert "pooled" in text, text

    def test_the_cross_state_twin_really_is_demographically_close(self, national):
        """The point only stands if these are genuinely good matches. A bad
        match scoring badly would prove nothing."""
        from app.bq import run_query
        worst_possible = run_query("""
            SELECT ROUND(MAX(profile_distance), 3) AS d
            FROM `daysupply.daysupply.district_matches`
        """)[0]["d"]
        for d in national["donors"]:
            assert d["profile_distance"] < worst_possible, d
