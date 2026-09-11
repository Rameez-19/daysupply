"""Part 1 — three resource types on one pipeline, medicines unchanged.

The binding constraint on this block was that nothing may weaken the medicine
vertical. These tests pin that first, then check that beds and personnel behave
according to what they actually are: bed capacity is a published standard, not
an estimate; a vacant post cannot be attended; beds do not transfer.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import capture_pipeline  # noqa: E402
from app.bq import run_query  # noqa: E402

# IPHS 2022 Volume III, PHC, pages 46-47.
ESSENTIAL_BEDS = 2
DESIRABLE_BEDS = 4
IPHS_TOTAL_BEDS = ESSENTIAL_BEDS + DESIRABLE_BEDS


class TestMedicinePathUnchanged:
    """The compatibility view must be indistinguishable from the old table."""

    def test_stock_events_view_shows_only_medicines(self):
        rows = run_query("""
            SELECT COUNT(*) AS total FROM `daysupply.daysupply.stock_events`
        """)
        typed = run_query("""
            SELECT COUNT(*) AS medicine
            FROM `daysupply.daysupply.resource_events`
            WHERE resource_type = 'medicine'
        """)
        assert rows[0]["total"] == typed[0]["medicine"]

    def test_view_excludes_beds_and_personnel(self):
        """A downstream query against the old name must not see new rows."""
        other = run_query("""
            SELECT COUNT(*) AS n
            FROM `daysupply.daysupply.resource_events`
            WHERE resource_type != 'medicine'
        """)
        assert other[0]["n"] > 0, "beds and personnel were never loaded"
        rows = run_query("""
            SELECT COUNT(*) AS n FROM `daysupply.daysupply.stock_events`
            WHERE item_id LIKE 'BED-%' OR item_id LIKE 'STAFF-%'
        """)
        assert rows[0]["n"] == 0

    def test_partitioning_and_clustering_survived(self):
        rows = run_query("""
            SELECT ddl FROM `daysupply.daysupply.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = 'resource_events'
        """)
        ddl = rows[0]["ddl"]
        assert "PARTITION BY DATE(event_ts)" in ddl
        assert "CLUSTER BY" in ddl and "facility_id" in ddl


class TestBedCapacity:
    """Capacity is the government's own norm, not an estimate."""

    def test_every_phc_has_the_iphs_capacity(self):
        rows = run_query("""
            SELECT COUNT(*) AS phcs,
                   COUNTIF(bed_capacity IS NULL) AS missing,
                   COUNTIF(bed_capacity != @total) AS off_norm
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND facility_type = 'phc'
        """, [__import__("google.cloud.bigquery", fromlist=["x"])
              .ScalarQueryParameter("total", "INT64", IPHS_TOTAL_BEDS)])
        assert rows[0]["missing"] == 0
        assert rows[0]["off_norm"] == 0

    def test_urban_phcs_get_day_care_beds(self):
        """IPHS gives urban PHCs day-care beds; they take no overnight stay."""
        rows = run_query("""
            SELECT COUNTIF(location_type = 'urban' AND NOT beds_are_day_care)
                     AS urban_marked_inpatient,
                   COUNTIF(location_type = 'rural' AND beds_are_day_care)
                     AS rural_marked_day_care
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND facility_type = 'phc'
        """)
        assert rows[0]["urban_marked_inpatient"] == 0
        assert rows[0]["rural_marked_day_care"] == 0

    def test_24x7_status_is_an_explicit_unknown(self):
        """Nothing in the data says which PHCs run 24x7, so nothing may claim to."""
        rows = run_query("""
            SELECT COUNTIF(is_24x7 IS NOT NULL) AS claimed
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND facility_type = 'phc'
        """)
        assert rows[0]["claimed"] == 0

    def test_occupancy_never_exceeds_capacity(self):
        rows = run_query("""
            SELECT COUNTIF(quantity > capacity) AS impossible
            FROM `daysupply.daysupply.resource_events`
            WHERE resource_type = 'bed' AND event_type = 'occupancy'
        """)
        assert rows[0]["impossible"] == 0

    def test_beds_produce_referrals_not_transfers(self):
        """A bed cannot be moved. Pressure must yield a route, not a transfer."""
        rows = run_query("""
            SELECT COUNT(*) AS routes,
                   COUNTIF(from_facility_id = to_facility_id) AS self_referral
            FROM `daysupply.daysupply.bed_referrals`
        """)
        assert rows[0]["routes"] > 0
        assert rows[0]["self_referral"] == 0


class TestPersonnel:
    def test_generated_attendance_is_frozen_history_that_feeds_nothing(self):
        """This used to assert generated attendance never exceeded filled
        posts. That invariant belonged to the generator, which no longer runs.

        After the RHS 2021-22 refresh, 28,397 of those old rows exceed the new
        in-position figures — generated against 2017's establishment, compared
        against 2022's. That is precisely why nothing may read them. What is
        pinned now: no product table carries a column built from them, and no
        new generated personnel row has appeared since the ledger was seeded.
        Real personnel reports from the capture pipeline are not affected —
        they carry a source other than 'seed'.
        """
        r = run_query("""
            SELECT MAX(DATE(event_ts)) AS last_day, COUNT(*) AS n
            FROM `daysupply.daysupply.resource_events`
            WHERE resource_type = 'personnel' AND source = 'seed'
        """)[0]
        assert r["n"] == 0 or str(r["last_day"]) <= "2026-08-29", r
        cols = {c["column_name"] for c in run_query("""
            SELECT column_name
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = 'staff_status'
        """)}
        assert not cols & {"mean_present", "attendance_vs_sanctioned",
                           "days_none_present", "status"}, cols

    def test_over_establishment_is_always_explained_by_the_source(self):
        """Rounding two ratios independently can invert their order.

        1.4 sanctioned rounds to 1 while 1.6 in position rounds to 2, which
        would claim staff that no post exists for. Every facility carrying more
        staff than posts must trace to a state the source reports that way.
        """
        rows = run_query("""
            SELECT COUNT(*) AS unexplained
            FROM `daysupply.daysupply.facility_staffing` fs
            JOIN `daysupply.daysupply.staffing` s
              ON s.cadre = fs.cadre
             -- 2021-22 publishes Nursing and Pharmacist once per facility
             -- type, so a cadre+state join alone matches two source rows and
             -- a PHC over its PHC establishment could be "explained" by the
             -- CHC row, or not, depending on which row the join kept.
             AND fs.facility_type IN UNNEST(s.applies_to_facility_types)
             AND s.state = CASE fs.state
                   WHEN 'A & N Islands' THEN 'Andaman & Nicobar Islands'
                   WHEN 'Andhra Pradesh Old' THEN 'Andhra Pradesh'
                   WHEN 'Dadra & Nagar Haveli'
                     THEN 'Dadra & Nagar Haveli and Daman & Diu'
                   WHEN 'Daman & Diu'
                     THEN 'Dadra & Nagar Haveli and Daman & Diu'
                   ELSE fs.state END
            WHERE fs.expected_in_position > fs.sanctioned_posts
              AND s.in_position <= s.sanctioned
        """)
        assert rows[0]["unexplained"] == 0

    def test_vacancy_rates_are_real_and_vary(self):
        """Flat vacancy would mean the source was not actually used."""
        rows = run_query("""
            SELECT COUNT(DISTINCT ROUND(vacancy_rate, 3)) AS distinct_rates,
                   MIN(vacancy_rate) AS lo, MAX(vacancy_rate) AS hi
            FROM `daysupply.daysupply.staffing`
            WHERE vacancy_rate IS NOT NULL
        """)
        assert rows[0]["distinct_rates"] > 20
        assert rows[0]["hi"] > rows[0]["lo"]

    def test_a_vacant_post_cannot_be_attended(self):
        """Attendance is bounded by posts actually filled, not sanctioned."""
        rows = run_query("""
            SELECT COUNTIF(expected_in_position > sanctioned_posts
                           AND vacancy_rate > 0) AS impossible
            FROM `daysupply.daysupply.facility_staffing`
        """)
        assert rows[0]["impossible"] == 0

    def test_nursing_carries_the_bed_derived_requirement(self):
        """The Indian Nursing Council 1:6 ratio links the two resource
        types. IPHS cites it; the INC originates it."""
        rows = run_query("""
            SELECT COUNTIF(nurses_required_by_beds IS NULL) AS missing,
                   COUNT(*) AS nursing_rows
            FROM `daysupply.daysupply.facility_staffing`
            WHERE cadre = 'Nursing staff'
        """)
        assert rows[0]["nursing_rows"] > 0
        assert rows[0]["missing"] == 0

    def test_reallocation_is_answered_by_structure_not_simulation(self):
        """This asserted the reallocation table never stranded a donor. The
        table is gone: every move in it differenced two generated attendance
        figures. What replaced it is the structural answer — how many cadres
        are sanctioned at most one post per centre — which is real."""
        from app import resources
        c = resources.staff_reallocation()["constraint"]
        assert resources.staff_reallocation()["reallocations"] == []
        assert 0 < c["single_post_cadres"] <= c["cadres"], c
        assert "recruitment" in c["why"], c["why"]


class TestOnePipeline:
    """Beds and staff go through the same extraction path as medicines."""

    @pytest.mark.parametrize("spoken,resource_type,expected", [
        ("bed", "bed", "BED-INPATIENT"),
        ("twelve beds occupied", "bed", "BED-INPATIENT"),
        ("palang", "bed", "BED-INPATIENT"),
        ("day care bed", "bed", "BED-DAYCARE"),
        ("doctor", "personnel", "STAFF-DOCTOR"),
        ("two ANMs present today", "personnel", "STAFF-NURSE"),
        ("compounder", "personnel", "STAFF-PHARMACIST"),
        ("female health assistant", "personnel", "STAFF-HA-FEMALE"),
        ("paracetamol", "medicine", "PARACETAMOL"),
    ])
    def test_resource_matching(self, spoken, resource_type, expected):
        assert capture_pipeline.match_resource(spoken, resource_type) == expected

    @pytest.mark.parametrize("resource_type", ["bed", "personnel"])
    def test_unknown_resource_goes_to_review(self, resource_type):
        result = capture_pipeline.route(
            [{"local_name": "wo cheez", "confidence": 0.9, "quantity": 3}],
            "IN-155740", "voice", resource_type=resource_type)
        assert not result["events"]
        assert len(result["review_queue"]) == 1

    @pytest.mark.parametrize("resource_type", ["medicine", "bed", "personnel"])
    def test_record_shape_is_identical_across_resources(self, resource_type):
        name = {"medicine": "paracetamol", "bed": "bed",
                "personnel": "nurse"}[resource_type]
        result = capture_pipeline.route(
            [{"local_name": name, "confidence": 0.95, "quantity": 3}],
            "IN-155740", "voice", resource_type=resource_type)
        assert len(result["events"]) == 1
        event = result["events"][0]
        for field in ("event_id", "resource_type", "facility_id", "item_id",
                      "quantity", "confidence", "source", "event_ts"):
            assert field in event
        assert event["resource_type"] == resource_type

    def test_confidence_gate_applies_to_every_resource(self):
        for resource_type, name in [("bed", "bed"), ("personnel", "nurse")]:
            result = capture_pipeline.route(
                [{"local_name": name, "confidence": 0.4, "quantity": 3}],
                "IN-155740", "voice", resource_type=resource_type)
            assert not result["events"], resource_type
            assert len(result["review_queue"]) == 1

    def test_unknown_resource_type_is_rejected(self):
        with pytest.raises(ValueError):
            capture_pipeline.route(
                [{"local_name": "bed", "confidence": 0.9, "quantity": 1}],
                "IN-155740", "voice", resource_type="ambulance")
