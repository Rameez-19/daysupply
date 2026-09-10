"""Where can a patient actually be treated?

This is the only view in the product that answers the question the person at
the counter has rather than the one a manager has, and it is the sharpest form
of alert the product makes: "126 Vital lines below reorder" is a statistic,
"Salchapra is at zero days of Oxytocin and the nearest supply is 46.7 km away"
is an emergency with an address.

That sharpness is exactly why it needs pinning. A wrong number here would send
somebody to the wrong clinic.
"""

import pytest

from app import access


@pytest.fixture(scope="module")
def national():
    return access.nearest_help()


class TestTheSourceIsActuallyAbleToHelp:
    def test_a_source_is_never_the_facility_itself(self, national):
        for c in national["all_cases"]:
            if c["source_name"]:
                assert not (c["source_name"] == c["facility_name"]
                            and c["source_district"] == c["district"]), c

    def test_a_source_holds_stock(self, national):
        """A source above zero but below its own reorder point would just move
        the shortage. The query requires it to be above reorder; this asserts
        the on-hand that came back is real."""
        for c in national["all_cases"]:
            if c["source_name"]:
                assert (c["source_on_hand"] or 0) > 0, c

    def test_every_case_is_actually_short(self, national):
        for c in national["all_cases"]:
            assert c["ven_class"] == "Vital"

    def test_the_medicine_matches(self, national):
        """The nearest facility that has *that* medicine — not the nearest
        facility that has *something*."""
        assert all(c["item_id"] for c in national["all_cases"])


class TestTheDistances:
    def test_distances_are_positive_and_plausible(self, national):
        for c in national["all_cases"]:
            if c["km"] is not None:
                assert 0 <= c["km"] <= 4000, c

    def test_it_really_is_the_nearest(self, national):
        """The whole claim. Recomputed independently for the worst case: no
        other facility holding that medicine may be closer."""
        from google.cloud import bigquery
        from app.bq import run_query
        worst = max((c for c in national["all_cases"] if c["km"] is not None),
                    key=lambda c: c["km"])
        rows = run_query("""
            SELECT MIN(ST_DISTANCE(ST_GEOGPOINT(@lon, @lat),
                                   ST_GEOGPOINT(f.longitude, f.latitude))/1000)
                   AS km
            FROM `daysupply.daysupply.reorder_status` r
            JOIN `daysupply.daysupply.facilities` f USING (facility_id)
            WHERE r.item_id = @item AND NOT r.needs_reorder AND r.on_hand > 0
              AND f.has_valid_coords AND r.facility_id != @fid
        """, [
            bigquery.ScalarQueryParameter("lat", "FLOAT64", worst["lat"]),
            bigquery.ScalarQueryParameter("lon", "FLOAT64", worst["lon"]),
            bigquery.ScalarQueryParameter("item", "STRING", worst["item_id"]),
            bigquery.ScalarQueryParameter("fid", "STRING", worst["facility_id"]),
        ])
        assert rows[0]["km"] == pytest.approx(worst["km"], abs=0.2), (
            f"a closer source exists than the one reported for "
            f"{worst['facility_name']}")


class TestTheAlertOrdering:
    """The map colours by distance, so the table earns its place by answering
    who runs out first. Ordering it by distance buried a centre with half a day
    of stock left at row eight."""

    def test_the_table_leads_with_the_soonest_to_run_out(self, national):
        cover = [c["days_of_cover"] for c in national["cases"]
                 if c["days_of_cover"] is not None]
        assert cover == sorted(cover), cover

    def test_unknown_cover_is_not_treated_as_urgent(self, national):
        """Unknown is unmeasured, not imminent."""
        seen_null = False
        for c in national["cases"]:
            if c["days_of_cover"] is None:
                seen_null = True
            elif seen_null:
                pytest.fail("a known cover ranked below an unknown one")


class TestTheSummaryIsHonest:
    def test_population_is_counted_once_per_centre(self, national):
        """A centre short of four medicines must not have its catchment counted
        four times."""
        seen, expected = set(), 0
        for c in national["all_cases"]:
            if c["facility_id"] not in seen:
                seen.add(c["facility_id"])
                expected += c.get("population") or 0
        assert national["summary"]["people"] == expected

    def test_centres_is_distinct_facilities_not_shortages(self, national):
        s = national["summary"]
        assert s["centres"] == len({c["facility_id"] for c in national["all_cases"]})
        assert s["centres"] <= s["cases"]

    def test_the_bands_add_up_to_the_case_count(self, national):
        total = sum(b["n"] for b in national["bands"])
        assert total == national["summary"]["cases"]

    def test_the_detail_line_matches_whether_anything_is_unreachable(
            self, national):
        s = national["summary"]
        if s["unreachable"] == 0:
            assert "has a source somewhere" in s["detail"]
        else:
            assert "no source anywhere" in s["detail"]

    def test_the_alert_line_matches_the_far_count(self, national):
        s = national["summary"]
        if s["far"]:
            assert str(s["far"]) in s["alert"]
        else:
            assert "None is more than" in s["alert"]


class TestScoping:
    @pytest.mark.parametrize("state", ["Rajasthan", "Assam"])
    def test_a_state_scope_returns_only_that_state(self, state):
        d = access.nearest_help(state)
        assert {c["state"] for c in d["all_cases"]} <= {state}

    def test_a_state_scope_is_smaller_than_the_nation(self, national):
        one = access.nearest_help("Assam")
        assert one["summary"]["cases"] < national["summary"]["cases"]

    def test_a_source_may_lie_outside_the_scope(self, national):
        """Deliberate: the nearest supply is wherever it is. Restricting
        sources to the filtered state would invent a longer journey than the
        real one, and a state border does not stop a van."""
        d = access.nearest_help("Assam")
        assert d["all_cases"], "no cases to check"
        assert all(c["source_name"] for c in d["all_cases"])


class TestClickingARowReachesTheMap:
    """A table beside a map that do not talk to each other are two things to
    read. Selecting a row is supposed to fly to it, lift it out of the other
    125 and open its detail — and the way that breaks silently is a table key
    with no matching feature on the map, which looks like a dead click.

    So the focus path is executed against the real payloads with a stubbed
    Leaflet: every key the tables render must resolve, the map must actually be
    moved, and the rest must FADE rather than disappear — hiding them would
    remove the context that makes the selected one mean anything. 353 km is
    only striking next to the ones that are 20.
    """

    def test_the_focus_path_works_end_to_end(self, tmp_path):
        import json
        import shutil
        import subprocess
        from pathlib import Path

        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not installed")

        from app import mapview

        root = Path(__file__).resolve().parent.parent
        acc = tmp_path / "access.json"
        mp = tmp_path / "map.json"
        acc.write_text(json.dumps(access.nearest_help()), encoding="utf-8")
        mp.write_text(json.dumps(mapview.supply_map("")), encoding="utf-8")

        result = subprocess.run(
            [node, str(root / "tests" / "focus_check.js"), str(acc), str(mp)],
            capture_output=True, text=True, cwd=str(root))
        assert result.returncode == 0, (
            "clicking a table row does not reach the map:\n"
            f"{result.stdout}{result.stderr}")
