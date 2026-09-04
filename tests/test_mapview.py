"""The map is only worth showing if every point on it is real.

A map is the most persuasive surface in the product and therefore the most
dangerous. A district drawn at a plausible-looking coordinate that was actually
defaulted, or an arc drawn between two places no recommendation connects, would
be indistinguishable from the truth at a glance. These tests pin the things a
reader cannot check by looking.

The flow layer in particular shipped empty once: the query filtered
`recommendations.status = 'recommended'`, but that column holds the *receiver's*
stock condition — 'critical', 'reorder', 'stocked_out' — not a lifecycle state.
The filter matched zero rows of 527 and the whole redistribution layer silently
vanished, while the district layer looked perfect. `test_flows_are_not_empty`
exists so that cannot happen quietly again.
"""

import pytest

from app import mapview


@pytest.fixture(scope="module")
def national():
    return mapview.supply_map("")


class TestEveryDistrictIsRealAndPlaced:
    def test_districts_are_returned(self, national):
        assert national["districts"], "no districts on the map at all"

    def test_every_district_has_coordinates(self, national):
        """A node without coordinates cannot be drawn, and a node drawn at a
        default coordinate is worse than one not drawn."""
        missing = [d["district"] for d in national["districts"]
                   if d.get("lat") is None or d.get("lon") is None]
        assert not missing, f"districts with no coordinate: {missing[:10]}"

    def test_coordinates_are_inside_india(self, national):
        """Catches a lat/lon swap, which produces a map that looks fine until
        you notice everything is in the ocean off Somalia."""
        for d in national["districts"]:
            assert 6.0 <= d["lat"] <= 37.5, f"{d['district']} lat {d['lat']}"
            assert 68.0 <= d["lon"] <= 97.5, f"{d['district']} lon {d['lon']}"

    def test_no_district_is_duplicated(self, national):
        keys = [(d["state"], d["district"]) for d in national["districts"]]
        assert len(keys) == len(set(keys)), "a district is plotted twice"

    def test_counts_are_internally_consistent(self, national):
        """Vital-short and stocked-out are subsets of the tracked lines."""
        for d in national["districts"]:
            assert d["short"] <= d["tracked"]
            assert d["vital_short"] <= d["tracked"]
            assert d["stocked_out"] <= d["tracked"]


class TestTheFlowLayer:
    def test_flows_are_not_empty(self, national):
        """The layer that vanished. 362 of 527 recommendations cross a district
        boundary, so an empty flow list means the query is wrong, not that the
        network is calm."""
        assert national["flows"], (
            "no redistribution arcs — check the recommendations filter; "
            "`status` is the receiver's stock condition, not a lifecycle state")

    def test_no_arc_starts_and_ends_in_the_same_district(self, national):
        """Intra-district moves are real but have nothing to draw: the arc
        would be a dot on top of the node."""
        same = [f for f in national["flows"]
                if f["from_district"] == f["to_district"]
                and f["from_state"] == f["to_state"]]
        assert not same, f"{len(same)} arcs begin and end in one district"

    def test_every_arc_has_both_endpoints_placed(self, national):
        for f in national["flows"]:
            for k in ("from_lat", "from_lon", "to_lat", "to_lon"):
                assert f.get(k) is not None, f"arc missing {k}: {f}"

    def test_arcs_carry_units_and_a_distance(self, national):
        for f in national["flows"]:
            assert (f["units"] or 0) > 0, "an arc moving nothing"
            assert (f["km"] or 0) >= 0

    def test_severity_is_one_of_the_three_ranks(self, national):
        assert {f["severity"] for f in national["flows"]} <= {1, 2, 3}


class TestScoping:
    """A scoped request must narrow, and must not error.

    Scoping is where this codebase has broken twice, both times because a
    finished predicate was string-replaced and the bound parameter was renamed
    along with the column.
    """

    @pytest.mark.parametrize("state", ["Telangana", "Assam", "Maharashtra"])
    def test_a_state_scope_returns_only_that_state(self, state):
        d = mapview.supply_map(state)
        assert d["districts"], f"{state} returned no districts"
        assert {x["state"] for x in d["districts"]} == {state}

    def test_a_state_scope_is_smaller_than_the_nation(self, national):
        one = mapview.supply_map("Telangana")
        assert len(one["districts"]) < len(national["districts"])


class TestTheSummaryMatchesTheData:
    """The headline sits above the map and will be read instead of it."""

    def test_counts_match_the_arrays(self, national):
        s = national["summary"]
        assert s["districts"] == len(national["districts"])
        assert s["flows"] == len(national["flows"])

    def test_units_in_flight_matches_the_arcs(self, national):
        s = national["summary"]
        assert s["units_in_flight"] == sum(f["units"] for f in national["flows"])

    def test_fragile_count_uses_the_same_threshold_as_the_executive_view(
            self, national):
        """35% is the break used by the absorption bars. If the map quietly
        used its own, the two views would disagree about the same district."""
        expected = sum(1 for d in national["districts"]
                       if d.get("pct_hold") is not None and d["pct_hold"] < 35)
        assert national["summary"]["fragile_districts"] == expected

    def test_absorption_multiplier_agrees_with_the_rest_of_the_project(self):
        assert mapview.ABSORPTION_MULTIPLIER == 3.0
