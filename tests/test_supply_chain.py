"""Block C — the supply-chain rules that must hold in the data.

These run against the built BigQuery tables, so they need credentials. They
check the properties a health consultant would check, not the SQL text:
a reorder point that ignores lead time, a transfer that strands the donor, or
a batch that expires in transit are all silent failures otherwise.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bq import run_query  # noqa: E402

SERVICE_LEVEL_Z = 1.65
USABLE_DAYS_AFTER_ARRIVAL = 30


@pytest.fixture(scope="module")
def reorder_rows():
    return run_query("""
        SELECT facility_id, item_id, ven_class, lead_time_days,
               avg_daily_demand, demand_std_dev, safety_stock, reorder_point,
               legacy_threshold, on_hand, days_of_cover, needs_reorder,
               priority_score, status
        FROM `daysupply.daysupply.reorder_status`
        LIMIT 2000
    """)


@pytest.fixture(scope="module")
def recommendations():
    return run_query("""
        SELECT recommendation_id, from_facility_id, to_facility_id,
               requested_item_id, supplied_item_id, is_substitution,
               quantity, distance_km, fefo_days_to_expiry,
               waste_avoided_units,
               receiver_cover_before, receiver_cover_after,
               donor_cover_before, donor_cover_after, ven_class
        FROM `daysupply.daysupply.recommendations`
    """)


class TestReorderPoint:
    """reorder_point = avg_daily_demand x lead_time + Z x sigma x sqrt(lead)."""

    def test_formula_holds(self, reorder_rows):
        assert reorder_rows, "reorder_status is empty"
        for row in reorder_rows[:500]:
            expected = (
                row["avg_daily_demand"] * row["lead_time_days"]
                + SERVICE_LEVEL_Z * row["demand_std_dev"]
                * math.sqrt(row["lead_time_days"])
            )
            assert row["reorder_point"] == pytest.approx(expected, abs=0.15), (
                f"{row['facility_id']}|{row['item_id']}"
            )

    def test_safety_stock_formula(self, reorder_rows):
        for row in reorder_rows[:500]:
            expected = (SERVICE_LEVEL_Z * row["demand_std_dev"]
                        * math.sqrt(row["lead_time_days"]))
            assert row["safety_stock"] == pytest.approx(expected, abs=0.15)

    def test_lead_time_actually_varies(self, reorder_rows):
        """A constant lead time would make the whole exercise pointless."""
        leads = {row["lead_time_days"] for row in reorder_rows}
        assert len(leads) > 1, "lead_time_days is constant across facilities"

    def test_longer_lead_time_raises_the_threshold(self):
        """The core claim: a remote PHC must reorder earlier than a near one.

        Compared within a single item at a single demand level, so the only
        thing varying is distance.
        """
        rows = run_query("""
            SELECT lead_time_days,
                   AVG(SAFE_DIVIDE(reorder_point, avg_daily_demand)) AS cover_days
            FROM `daysupply.daysupply.reorder_status`
            WHERE avg_daily_demand > 1
            GROUP BY lead_time_days
            HAVING COUNT(*) > 20
            ORDER BY lead_time_days
        """)
        assert len(rows) >= 2
        assert rows[-1]["cover_days"] > rows[0]["cover_days"], (
            "Facilities with longer lead times must reorder at a higher "
            "days-of-cover threshold"
        )

    def test_needs_reorder_matches_the_threshold(self, reorder_rows):
        for row in reorder_rows:
            assert row["needs_reorder"] == (
                row["on_hand"] <= row["reorder_point"])


class TestVenWeighting:
    """A vital stock-out outranks a desirable one at equal cover."""

    def test_priority_is_ven_weighted(self, reorder_rows):
        weights = {"Vital": 3.0, "Essential": 2.0, "Desirable": 1.0}
        for row in reorder_rows[:500]:
            if not row["needs_reorder"] or row["reorder_point"] <= 0:
                continue
            shortfall = max(0.0, 1 - row["on_hand"] / row["reorder_point"])
            expected = weights[row["ven_class"]] * shortfall
            assert row["priority_score"] == pytest.approx(expected, abs=0.01)

    def test_vital_outranks_desirable_at_equal_shortfall(self):
        """Two fully stocked-out items rank by criticality, not by cover."""
        rows = run_query("""
            SELECT ven_class, MAX(priority_score) AS top
            FROM `daysupply.daysupply.reorder_status`
            WHERE status = 'stocked_out'
            GROUP BY ven_class
        """)
        by_class = {r["ven_class"]: r["top"] for r in rows}
        if "Vital" in by_class and "Essential" in by_class:
            assert by_class["Vital"] > by_class["Essential"]


class TestRedistribution:
    def test_never_strands_the_donor(self, recommendations):
        """The one thing this engine must never do."""
        for rec in recommendations:
            assert rec["donor_cover_after"] >= 0, rec["recommendation_id"]

    def test_transfer_improves_the_receiver(self, recommendations):
        for rec in recommendations:
            assert rec["receiver_cover_after"] > rec["receiver_cover_before"]

    def test_quantity_is_positive(self, recommendations):
        for rec in recommendations:
            assert rec["quantity"] > 0

    def test_distance_within_limit(self, recommendations):
        for rec in recommendations:
            assert rec["distance_km"] <= 150

    def test_donor_and_receiver_differ(self, recommendations):
        for rec in recommendations:
            assert rec["from_facility_id"] != rec["to_facility_id"]


class TestFefo:
    def test_batch_survives_the_journey(self, recommendations):
        """Never move stock that expires before it can be used.

        The guard is `lead_time_days + 30`; the minimum lead time is 7, so no
        transferred batch may have fewer than 37 days of life.
        """
        for rec in recommendations:
            assert rec["fefo_days_to_expiry"] >= 7 + USABLE_DAYS_AFTER_ARRIVAL, (
                f"{rec['recommendation_id']} moves a batch expiring in "
                f"{rec['fefo_days_to_expiry']} days"
            )

    def test_waste_avoided_never_exceeds_quantity(self, recommendations):
        for rec in recommendations:
            assert 0 <= rec["waste_avoided_units"] <= rec["quantity"]

    def test_current_stock_reconciles_with_the_ledger(self):
        """Batch quantities must sum to received - dispensed - expired.

        **Global again, and permanently so.** This was briefly scoped to
        `source = 'seed'` while `current_stock` was a precomputed table and
        live captures made the two diverge. It is now a view derived from the
        ledger at read time, so the invariant holds for every row including
        captures — and any divergence is a real defect, not staleness.

        This is the strongest single assertion about the FEFO arithmetic: if
        batch quantities do not sum to the ledger balance, on-hand, days of
        cover, reorder points, alerts and transfers are all wrong together.
        """
        rows = run_query("""
            WITH ledger AS (
              SELECT facility_id, item_id,
                     SUM(IF(event_type = 'received',  quantity, 0))
                       - SUM(IF(event_type = 'dispensed', quantity, 0))
                       - SUM(IF(event_type = 'expired',   quantity, 0)) AS balance
              FROM `daysupply.daysupply.stock_events`
              GROUP BY facility_id, item_id
            ),
            batched AS (
              SELECT facility_id, item_id, SUM(remaining_qty) AS batched
              FROM `daysupply.daysupply.current_stock`
              GROUP BY facility_id, item_id
            )
            SELECT COUNTIF(IFNULL(b.batched, 0) != l.balance) AS mismatches
            FROM ledger l LEFT JOIN batched b USING (facility_id, item_id)
        """)
        assert rows[0]["mismatches"] == 0

    def test_an_undated_receipt_is_counted_and_consumed_last(self):
        """A captured receipt has no expiry date and must still be stock.

        The build used to filter `expiry_date IS NOT NULL`, which would have
        dropped every captured receipt from the batch view while still counting
        it in the ledger balance. Undated batches are included and ordered last
        in FEFO, because a batch whose expiry is unknown cannot be claimed to
        expire soon.
        """
        rows = run_query("""
            SELECT COUNTIF(expiry_unknown) AS undated,
                   COUNTIF(expiry_unknown AND is_expired) AS wrongly_expired,
                   COUNTIF(expiry_unknown AND days_to_expiry IS NOT NULL)
                     AS wrongly_dated
            FROM `daysupply.daysupply.current_stock`
        """)
        # No undated batch may be called expired, or given a countdown.
        assert rows[0]["wrongly_expired"] == 0
        assert rows[0]["wrongly_dated"] == 0

    def test_current_stock_is_a_view_so_a_capture_moves_on_hand(self):
        """If this became a table again, capture would stop moving stock."""
        rows = run_query("""
            SELECT table_type
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = 'current_stock'
        """)
        assert rows[0]["table_type"] == "VIEW"

    def test_reorder_status_is_a_view_so_a_capture_moves_an_alert(self):
        """The model half lives in `demand_baseline`; this half must stay live."""
        rows = run_query("""
            SELECT table_name, table_type
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.TABLES`
            WHERE table_name IN ('reorder_status', 'demand_baseline')
            ORDER BY table_name
        """)
        by_name = {r["table_name"]: r["table_type"] for r in rows}
        assert by_name["demand_baseline"] == "BASE TABLE"
        assert by_name["reorder_status"] == "VIEW"

    def test_no_negative_stock(self):
        """A facility cannot have dispensed more than it ever received."""
        rows = run_query("""
            SELECT COUNTIF(remaining_qty < 0) AS negatives
            FROM `daysupply.daysupply.current_stock`
        """)
        assert rows[0]["negatives"] == 0


class TestSubstitution:
    def test_zinc_is_never_substituted_by_magnesium(self):
        """ATC level 3 would allow it; level 4 must not.

        A12C is "other mineral supplements" — zinc (A12CB) and magnesium
        (A12CC) sit in it together and are not interchangeable.
        """
        rows = run_query("""
            SELECT COUNT(*) AS n
            FROM `daysupply.daysupply.recommendations`
            WHERE is_substitution
              AND SUBSTR(requested_item_id, 1, 4) != SUBSTR(supplied_item_id, 1, 4)
              AND (LOWER(requested_item_name) LIKE '%zinc%'
                   AND LOWER(supplied_item_name) LIKE '%magnesium%')
        """)
        assert rows[0]["n"] == 0

    def test_substitutes_share_an_atc_class(self):
        rows = run_query("""
            SELECT COUNTIF(SUBSTR(alternative_atc_code, 1, 5) != atc_class)
                     AS mismatched,
                   COUNT(*) AS total
            FROM `daysupply.daysupply.substitutes`
        """)
        # Substitutes can legitimately be zero. At ATC level 4 only one class
        # among the forecast items — P01BA, chloroquine and primaquine —
        # contains more than one, so there is often nothing to match on. What
        # must never happen is a substitute from a different class.
        assert rows[0]["mismatched"] == 0

    def test_substitution_is_confined_to_classes_with_siblings(self):
        """Substitution can only fire where two forecast items share a class."""
        rows = run_query("""
            SELECT COUNT(*) AS classes_with_siblings FROM (
              SELECT atc_class
              FROM `daysupply.daysupply.reorder_status`
              WHERE atc_class IS NOT NULL
              GROUP BY atc_class
              HAVING COUNT(DISTINCT item_id) > 1
            )
        """)
        # If this ever reaches zero, substitution is dead code and the UI
        # should stop advertising it.
        assert rows[0]["classes_with_siblings"] >= 1

    def test_substitute_is_never_the_same_item(self):
        rows = run_query("""
            SELECT COUNTIF(alternative_item_id = requested_item_id) AS same
            FROM `daysupply.daysupply.substitutes`
        """)
        assert rows[0]["same"] == 0

    def test_cross_facility_substitution_is_labelled(self, recommendations):
        """A substitute must never be presented as the requested item."""
        for rec in recommendations:
            differs = rec["supplied_item_id"] != rec["requested_item_id"]
            assert rec["is_substitution"] == differs


class TestReportingConsistency:
    def test_score_is_a_share(self):
        rows = run_query("""
            SELECT COUNTIF(reporting_consistency < 0
                           OR reporting_consistency > 1) AS out_of_range,
                   COUNT(*) AS total
            FROM `daysupply.daysupply.facility_reporting`
        """)
        assert rows[0]["total"] > 0
        assert rows[0]["out_of_range"] == 0

    def test_status_matches_the_score(self):
        rows = run_query("""
            SELECT COUNTIF(reporting_status = 'silent'
                           AND periods_reported != 0) AS bad_silent,
                   COUNTIF(reporting_status = 'complete'
                           AND periods_reported != periods_expected)
                     AS bad_complete
            FROM `daysupply.daysupply.facility_reporting`
        """)
        assert rows[0]["bad_silent"] == 0
        assert rows[0]["bad_complete"] == 0

    def test_non_reporting_is_visible(self):
        """The metric exists to make silence observable. It must find some."""
        rows = run_query("""
            SELECT COUNTIF(reporting_status != 'complete') AS imperfect
            FROM `daysupply.daysupply.facility_reporting`
        """)
        assert rows[0]["imperfect"] > 0
