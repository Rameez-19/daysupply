"""The register layer: every PHC and CHC, not just the ones that report.

The map drew 116 district nodes and, on the access layer, the 200 centres that
report stock. That is the demonstration set. Showing only it invites a reader
to think 200 centres *are* the network, when the register behind them holds
nearly thirty-five thousand.

Two things have to hold. The points must be placeable — the first version of
this query filtered only for NULL coordinates and would have drawn centres in
China, in Egypt and in the Arctic Ocean. And the counts must be the register's
own, so "national scale" is a number a reader can check rather than a word.
"""

import pytest

from app import mapview
from app.bq import run_query

# Mainland plus islands, generously drawn. Every real Indian facility sits
# inside this; the junk coordinates did not.
LAT_RANGE = (6.0, 37.6)
LON_RANGE = (68.0, 97.5)


@pytest.fixture(scope="module")
def register():
    return mapview.facility_register()


class TestEveryPointCanBePlaced:
    def test_no_point_falls_outside_india(self, register):
        """173 of the 35,108 centres carrying coordinates carry impossible
        ones — a longitude of 75,070,600,009, a latitude equal to its own
        longitude. Filtering only for NULL drew all of them."""
        for lat, lon, _t, _r in register["points"]:
            assert LAT_RANGE[0] <= lat <= LAT_RANGE[1], (lat, lon)
            assert LON_RANGE[0] <= lon <= LON_RANGE[1], (lat, lon)

    def test_it_uses_the_registers_own_validity_flag(self, register):
        """Not a bounding box invented here. `has_valid_coords` is what the
        district centroids already use, and measured against the box it agrees
        exactly — nothing it admits falls outside, nothing it rejects falls
        inside. Two rules that disagreed would be a trap for whoever changed
        one of them."""
        n = run_query("""
            SELECT COUNTIF(has_valid_coords) AS valid,
                   COUNTIF(has_valid_coords AND NOT (
                     latitude BETWEEN 6 AND 37.6
                     AND longitude BETWEEN 68 AND 97.5)) AS admitted_outside,
                   COUNTIF(NOT has_valid_coords
                     AND latitude BETWEEN 6 AND 37.6
                     AND longitude BETWEEN 68 AND 97.5) AS rejected_inside
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN'
              AND facility_type IN ('phc', 'chc')
              AND latitude IS NOT NULL AND longitude IS NOT NULL
        """)[0]
        assert n["admitted_outside"] == 0 and n["rejected_inside"] == 0
        assert len(register["points"]) == n["valid"]

    def test_the_unplaceable_are_counted_not_hidden(self, register):
        """A centre held back by bad coordinates is still a centre."""
        assert register["counts"]["unplaceable"] > 0
        assert str(register["counts"]["unplaceable"]) in \
            register["summary"]["headline"]


class TestTheCountsAreTheRegisters:
    def test_the_totals_match_the_facility_table(self, register):
        n = run_query("""
            SELECT COUNTIF(facility_type = 'phc') AS phc,
                   COUNTIF(facility_type = 'chc') AS chc
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN'
              AND facility_type IN ('phc', 'chc') AND has_valid_coords
        """)[0]
        c = register["counts"]
        assert (c["phc"], c["chc"]) == (n["phc"], n["chc"])
        assert c["total"] == c["phc"] + c["chc"] == len(register["points"])

    def test_the_reporting_centres_are_the_forecast_set(self, register):
        """The centres that report stock are the same set every other view
        counts; a different number here would mean two definitions of
        'reporting'. Counted from the flag rather than pinned: it was a literal
        200 until Uttar Pradesh took the set to 275."""
        from app.bq import run_query
        n = run_query("SELECT COUNTIF(is_forecast_facility) AS n FROM `daysupply.daysupply.facilities`")[0]["n"]
        assert register["counts"]["reporting"] == n
        assert sum(1 for p in register["points"] if p[3] == 1) == n

    def test_the_register_dwarfs_the_reporting_set(self, register):
        """The point of the layer. If these ever converged, the layer would be
        making a claim about coverage that is no longer true."""
        c = register["counts"]
        assert c["total"] > 30000
        assert c["reporting"] / c["total"] < 0.05
        assert f"{c['total']:,}" in register["summary"]["headline"]


class TestThePayloadStaysSmallEnoughToDraw:
    def test_points_are_positional_not_objects(self, register):
        """35,000 rows of {"lat": .., "lon": ..} is mostly field names."""
        for p in register["points"][:50]:
            assert isinstance(p, list) and len(p) == 4
            assert p[2] in (0, 1) and p[3] in (0, 1)

    def test_coordinates_are_rounded_for_the_wire(self, register):
        """Three decimals is about 110 m. A dot on a national map cannot be
        placed more precisely than it can be seen."""
        for lat, lon, _t, _r in register["points"][:200]:
            assert round(lat, mapview.REGISTER_PRECISION) == lat
            assert round(lon, mapview.REGISTER_PRECISION) == lon

    def test_the_whole_payload_is_under_a_megabyte(self, register):
        import json
        raw = json.dumps(register, separators=(",", ":"))
        assert len(raw) < 1_000_000, f"{len(raw)/1e6:.2f} MB"


class TestScoping:
    def test_a_state_returns_only_its_own_centres(self):
        one = mapview.facility_register("Assam")
        n = run_query("""
            SELECT COUNT(*) AS n FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND facility_type IN ('phc', 'chc')
              AND has_valid_coords AND admin_l1 = 'Assam'
        """)[0]["n"]
        assert one["counts"]["total"] == n == len(one["points"])
        assert one["scope"] == "Assam"

    def test_a_state_is_smaller_than_the_nation(self, register):
        one = mapview.facility_register("Assam")
        assert one["counts"]["total"] < register["counts"]["total"]
        assert one["counts"]["reporting"] < register["counts"]["reporting"]

    def test_an_unknown_state_says_so_rather_than_drawing_nothing(self):
        d = mapview.facility_register("Nowhere")
        assert d["points"] == []
        assert d["summary"]["headline"]
