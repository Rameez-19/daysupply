"""The personnel vertical reports only what was measured.

`ingestion/generate_bed_personnel.py` produces `mean_present` from a fixed-seed
random attendance propensity, lower on Sundays. Three things were built on it
and shown as findings:

* Today v2: "Actually on duty 53.2%" and "Roles with a day nobody came".
* Today v1's national summary: "in 875 cases a role had a day with nobody on
  duty at all".
* `/api/v1/personnel/reallocation`: proposed staff moves, which were
  differences between two generated numbers, selected by `status` thresholds
  on the same generated column.

It was also wrong on its own terms. No facility-cadre is fully vacant, yet 278
with posts filled reported nobody present across all 30 days, and
`days_none_present > 0` covered 875 of 928 rows — 94% of everything, which
cannot separate a struggling centre from a healthy one.

What is real is narrower than the old page implied: `vacancy_rate` takes **23
distinct values** across all 928 rows, one per state and cadre from Rural
Health Statistics 2017. It does not vary by district or by facility, so no
per-district personnel comparison means anything.
"""

import pytest

from app import executive, resources, today_v2
from app.bq import run_query


GENERATED = ("mean_present", "attendance_vs_sanctioned", "days_none_present",
             "days_reported")


def _leaves(obj, path=""):
    """Every scalar in a nested payload, with the path that reached it."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, obj


class TestTheGeneratedColumnsStillLookLikeThis:
    """If the generator is ever fixed or replaced, these fail and the panels
    above can be reconsidered. Until then they are the reason for the removal.
    """

    def test_presence_is_zero_where_posts_are_filled(self):
        r = run_query("""
            SELECT COUNTIF(vacancy_rate >= 0.999) AS fully_vacant,
                   COUNTIF(mean_present = 0 AND vacancy_rate < 0.999)
                     AS zero_but_staffed
            FROM `daysupply.daysupply.staff_status`
        """)[0]
        assert r["fully_vacant"] == 0
        assert r["zero_but_staffed"] > 200, (
            "if this has dropped, re-check whether presence became real")

    def test_the_nobody_came_flag_covers_almost_everything(self):
        r = run_query("""
            SELECT COUNTIF(days_none_present > 0) AS with_gap, COUNT(*) AS n
            FROM `daysupply.daysupply.staff_status`
        """)[0]
        assert r["with_gap"] / r["n"] > 0.9, (
            "a flag on 94% of rows distinguishes nothing")

    def test_vacancy_exists_only_at_state_and_cadre_grain(self):
        """The reason no personnel figure may be reported per district."""
        r = run_query("""
            SELECT COUNT(DISTINCT FORMAT('%s|%s|%t', state, cadre, vacancy_rate))
                     AS distinct_values,
                   COUNT(DISTINCT FORMAT('%s|%s', state, cadre)) AS pairs,
                   COUNT(DISTINCT district) AS districts
            FROM `daysupply.daysupply.staff_status`
        """)[0]
        assert r["distinct_values"] == r["pairs"], (
            "vacancy varies by something other than state and cadre")
        assert r["districts"] > r["pairs"], (
            "more districts than distinct figures, so a district ranking "
            "would repeat the same numbers as though they were observations")


class TestNoGeneratedFigureReachesAReader:
    def test_the_personnel_scorecard_is_clean(self):
        for path, value in _leaves(today_v2.staff_scorecard()):
            low = path.lower()
            assert not any(g in low for g in GENERATED), (path, value)
            if isinstance(value, str):
                assert "on duty" not in value.lower(), (path, value)
                assert "nobody came" not in value.lower(), (path, value)

    def test_the_national_summary_is_clean(self):
        text = executive.national_picture()["headline"]["personnel"]
        for phrase in ("nobody on duty", "day with nobody", "on duty at all"):
            assert phrase not in text.lower(), text
        assert "sanctioned posts are unfilled" in text, text

    @pytest.mark.parametrize("fn", [
        lambda: resources.staff_summary(),
        lambda: resources.staff_facilities(limit=5),
        lambda: resources.staff_reallocation(),
    ])
    def test_the_personnel_endpoints_are_clean(self, fn):
        for path, value in _leaves(fn()):
            assert not any(g in path.lower() for g in GENERATED), (path, value)

    def test_reallocation_proposes_no_moves_built_on_generated_presence(self):
        d = resources.staff_reallocation()
        assert d["reallocations"] == []
        assert d["constraint"]["why"]


class TestWhatReplacedItIsReal:
    def test_every_scorecard_kpi_has_a_value(self):
        """Removing three KPIs and leaving holes would be its own failure."""
        kpis = today_v2.staff_scorecard()["kpis"]
        assert len(kpis) >= 4
        for k in kpis:
            assert k.get("value") is not None, k
            assert k.get("label"), k

    def test_the_worst_role_matches_the_ranking(self):
        d = today_v2.staff_scorecard()
        worst_kpi = next(k for k in d["kpis"]
                         if "Hardest" in k["label"] or "hardest" in k["label"])
        top = d["ranking"][0]
        assert worst_kpi["label"].endswith(top["name"]) or \
            worst_kpi["value"] >= top["value"], (worst_kpi, top)

    def test_vacancy_is_weighted_by_establishment(self):
        """A plain average gave Delhi's 11 posts the same say as
        Maharashtra's several hundred."""
        d = resources.staff_summary()
        expected = run_query("""
            SELECT ROUND(100 * SAFE_DIVIDE(
                     SUM(vacancy_rate * sanctioned_posts),
                     SUM(IF(vacancy_rate IS NULL, 0, sanctioned_posts))), 1) AS v
            FROM `daysupply.daysupply.staff_status`
        """)[0]["v"]
        assert d["vacancy_pct"] == pytest.approx(expected)

    def test_posts_filled_is_never_over_a_hundred_percent(self):
        """47 cadres are over establishment — negative vacancy, which is a
        real RHS outcome. "103% of posts filled" reads as a bug."""
        filled = next(k for k in today_v2.staff_scorecard()["kpis"]
                      if k["label"] == "Posts filled")
        assert 0 <= filled["value"] <= 100, filled

    def test_the_quadrant_plots_roles_not_districts(self):
        """116 district points drawn from 23 numbers invited the reader to
        compare districts carrying an identical figure."""
        d = today_v2.staff_scorecard()
        pts = d["quadrant"]
        assert pts, "the panel would render empty"
        districts = {r["district"] for r in run_query("""
            SELECT DISTINCT district FROM `daysupply.daysupply.staff_status`
        """)}
        assert not ({p["name"] for p in pts} & districts), (
            "district names are back on the staffing scatter")
        assert len(pts) <= 40, len(pts)

    def test_the_quadrant_axes_are_labelled_for_what_is_plotted(self):
        lab = today_v2.STAFF_LABELS["quadrant"]
        assert "on duty" not in lab["y"].lower(), lab
        assert "post" in lab["y"].lower(), lab

    def test_the_provenance_states_the_grain(self):
        p = today_v2.STAFF_LABELS["provenance"].lower()
        assert "state" in p and "cadre" in p, p
        assert "attendance" not in p, p

    def test_a_non_percentage_axis_declares_its_unit(self):
        """The scatter hardcoded `%` on both axes, which was true only while it
        plotted vacancy against attendance. Staffing plots the size of the
        establishment up the y-axis now, and 450 sanctioned posts rendered as
        "450%"."""
        lab = today_v2.STAFF_LABELS["quadrant"]
        assert lab["y_unit"] == "", lab
        assert lab["x_unit"] == "%", lab

    @pytest.mark.parametrize("fn,pct_y", [(today_v2.bed_scorecard, True),
                                          (today_v2.staff_scorecard, False)])
    def test_the_axis_unit_matches_what_the_axis_holds(self, fn, pct_y):
        d = fn()
        lab = d["labels"]["quadrant"]
        unit = lab.get("y_unit", "%")
        ys = [p["y"] for p in d["quadrant"] if p.get("y") is not None]
        assert ys
        if pct_y:
            assert unit == "%"
            assert max(ys) <= 100, max(ys)
        else:
            assert unit == "", unit
            assert max(ys) > 100, (
                "if every value now fits under 100 this test no longer "
                "distinguishes a count from a percentage")

    def test_the_renderer_defaults_to_percent_when_no_unit_is_given(self):
        """Beds and medicines send no unit and must keep their % axes."""
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1]
              / "web" / "today2.js").read_text(encoding="utf-8")
        assert "lab.y_unit === undefined ? '%'" in js
        assert "lab.x_unit === undefined ? '%'" in js
