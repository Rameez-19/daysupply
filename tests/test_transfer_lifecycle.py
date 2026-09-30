"""Transfer fulfilment — the difference between computed and executed.

`POST /api/v1/recommendations/{id}/approve` used to return
`{"status": "approved"}`, write nothing, and claim in its docstring to trigger
stock updates. The UI faded the card and called no endpoint at all. That was the
last simulated surface in the product, and it sat under the "automated
cross-district resource redistribution" clause.

These tests pin the properties that make "automated" mean executed.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import transfers  # noqa: E402
from app.bq import run_query  # noqa: E402


class TestLifecycleOrder:
    """A transfer moves forward, one step at a time, or not at all."""

    def test_the_lifecycle_is_ordered(self):
        assert transfers.LIFECYCLE == (
            "recommended", "approved", "dispatched", "received")

    def test_each_state_has_exactly_one_successor(self):
        for state in transfers.LIFECYCLE[:-1]:
            assert transfers.NEXT_STATE[state] in transfers.LIFECYCLE
        assert transfers.NEXT_STATE["received"] is None, (
            "a received transfer is complete and must not advance further")

    def test_an_unknown_state_is_refused(self):
        with pytest.raises(transfers.TransferError):
            transfers.advance("whatever", "cancelled")

    def test_an_unknown_recommendation_is_refused_with_a_useful_reason(self):
        with pytest.raises(transfers.TransferError) as caught:
            transfers.advance("not-a-real-id", "approved")
        # Plan rebuilds regenerate ids, which is the likeliest cause.
        assert "rebuilt" in str(caught.value)

    def test_there_is_no_reverse_transition(self):
        """No path back. Retraction is a compensating movement, never an undo."""
        reachable = set(transfers.NEXT_STATE.values()) - {None}
        for state, nxt in transfers.NEXT_STATE.items():
            if nxt is None:
                continue
            assert transfers.LIFECYCLE.index(nxt) == \
                transfers.LIFECYCLE.index(state) + 1
        assert "recommended" not in reachable, (
            "nothing may return to the recommended state")


class TestLedgerEventsAreReal:
    def test_a_dispatch_event_is_shaped_for_the_ledger(self):
        event = transfers._ledger_event(
            "evt-1", "IN-1", "PARACETAMOL", "dispatched", 100, "note")
        for field in ("event_id", "resource_type", "facility_id", "item_id",
                      "event_type", "quantity", "event_ts", "source"):
            assert field in event
        assert event["source"] == "transfer"
        assert event["resource_type"] == "medicine"
        assert event["quantity"] == 100

    def test_dispatch_is_not_recorded_as_dispensed(self):
        """Nobody handed it to a patient. Conflating the two would overstate
        consumption and hide the transfer entirely."""
        event = transfers._ledger_event(
            "evt-1", "IN-1", "PARACETAMOL", "dispatched", 100, "note")
        assert event["event_type"] == "dispatched"
        assert event["event_type"] != "dispensed"


class TestTimestampsSurviveTheRoundTrip:
    """Found live: approve succeeded and dispatch 500'd.

    BigQuery returns timestamps as `datetime`; `insert_rows_json` serialises
    with plain `json.dumps`, which cannot encode one. The first step has no
    prior state to read back, so it never hit the problem — only carrying an
    earlier `approved_at` into the next write did. A whole-lifecycle test is
    the only kind that catches this.
    """

    def test_a_datetime_is_normalised_to_a_string(self):
        from datetime import datetime, timezone
        value = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        assert isinstance(transfers._iso(value), str)

    def test_a_string_passes_through_unchanged(self):
        assert transfers._iso("2026-09-02T12:00:00+00:00") == \
            "2026-09-02T12:00:00+00:00"

    def test_none_stays_none(self):
        assert transfers._iso(None) is None

    def test_every_timestamp_column_is_normalised(self):
        """If a column is added and left off this list, it breaks on step two."""
        schema_fields = {f.name for f in __import__(
            "ingestion.build_transfer_fulfilment", fromlist=["SCHEMA"]).SCHEMA
            if f.field_type == "TIMESTAMP"}
        assert schema_fields == set(transfers.TIMESTAMP_FIELDS), (
            f"timestamp columns {schema_fields} do not match the normalised "
            f"set {set(transfers.TIMESTAMP_FIELDS)}")


class TestAMovementHappensAtMostOnce:
    """Found live, and it cost 18 units of real stock.

    A 9-unit transfer produced **three** `dispatched` events and took 27 units
    off the donor. Two earlier attempts wrote the ledger event and then crashed
    in `_save_state`, leaving orphan movements that nothing could see, because
    the event id was a random UUID and the retry generated a different one.

    There is no cross-table transaction between the ledger and the fulfilment
    table. Rather than pretend the two writes are atomic, the movement is made
    repeatable without duplication — which is the property that actually
    protects the stock position.
    """

    def test_the_movement_id_is_derived_not_random(self):
        a = transfers.movement_event_id("rec-1", "dispatched")
        b = transfers.movement_event_id("rec-1", "dispatched")
        assert a == b, "a retry must produce the same id, or it duplicates"

    def test_each_step_has_its_own_id(self):
        assert transfers.movement_event_id("rec-1", "dispatched") != \
            transfers.movement_event_id("rec-1", "received")

    def test_each_transfer_has_its_own_id(self):
        assert transfers.movement_event_id("rec-1", "dispatched") != \
            transfers.movement_event_id("rec-2", "dispatched")

    def test_no_transfer_has_duplicate_movements_in_the_ledger(self):
        """The invariant the bug violated. One movement per transfer per step."""
        rows = run_query("""
            SELECT COUNT(*) AS duplicated FROM (
              SELECT event_id, COUNT(*) AS n
              FROM `daysupply.daysupply.resource_events`
              WHERE source = 'transfer'
              GROUP BY event_id HAVING n > 1
            )
        """)
        assert rows[0]["duplicated"] == 0

    def test_transfer_movements_match_recorded_fulfilment(self):
        """Every transfer movement must be one a fulfilment row accounts for.

        An orphan — a movement in the ledger that no fulfilment row references
        — means stock moved and nothing recorded why.

        A movement may also be **reversed by a compensating correction**, which
        is how the two orphans this bug created were dealt with: they were in
        the streaming buffer and so immune to DELETE, and per HANDOVER §9e we
        do not pretend rows can vanish. A `correction`-sourced receipt of the
        same quantity nets each one out, and the audit trail keeps both.
        """
        rows = run_query("""
            SELECT COUNTIF(f.recommendation_id IS NULL AND c.event_id IS NULL)
                     AS unexplained
            FROM (
              SELECT event_id FROM `daysupply.daysupply.resource_events`
              WHERE source = 'transfer'
            ) e
            LEFT JOIN (
              SELECT dispatch_event_id AS event_id, recommendation_id
              FROM `daysupply.daysupply.transfer_fulfilment`
              WHERE dispatch_event_id IS NOT NULL
              UNION ALL
              SELECT receipt_event_id, recommendation_id
              FROM `daysupply.daysupply.transfer_fulfilment`
              WHERE receipt_event_id IS NOT NULL
            ) f USING (event_id)
            LEFT JOIN (
              SELECT REPLACE(event_id, 'correction:', '') AS event_id
              FROM `daysupply.daysupply.resource_events`
              WHERE source = 'correction'
            ) c USING (event_id)
        """)
        assert rows[0]["unexplained"] == 0, (
            "a transfer movement exists that no fulfilment row explains and no "
            "correction reverses")


class TestStockLeavesTheDonor:
    def test_dispatched_is_netted_out_of_on_hand(self):
        """Otherwise a donor appears to hold units that are on a vehicle."""
        from ingestion import build_current_stock
        assert "dispatched" in build_current_stock.CONSUMING_EVENT_TYPES
        assert "dispensed" in build_current_stock.CONSUMING_EVENT_TYPES
        assert "expired" in build_current_stock.CONSUMING_EVENT_TYPES

    def test_the_ledger_still_reconciles_with_the_batch_view(self):
        """The balance formula changed; the invariant must survive it.

        The consuming list is read from `CONSUMING_EVENT_TYPES` rather than
        written out here. It was hardcoded once and drifted: Block G started
        recording `lost` events, `current_stock` netted them out, this query
        did not, and the invariant failed on a single 50-unit loss. The test
        was wrong, not the view. Deriving the list makes that impossible.
        """
        from ingestion.build_current_stock import CONSUMING_EVENT_TYPES
        consuming = ", ".join(f"'{e}'" for e in CONSUMING_EVENT_TYPES)
        rows = run_query(f"""
            WITH ledger AS (
              SELECT facility_id, item_id,
                     SUM(IF(event_type = 'received', quantity, 0))
                       - SUM(IF(event_type IN ({consuming}), quantity, 0))
                       AS balance
              FROM `daysupply.daysupply.stock_events`
              GROUP BY facility_id, item_id
            ),
            batched AS (
              SELECT facility_id, item_id, SUM(remaining_qty) AS batched
              FROM `daysupply.daysupply.current_stock`
              GROUP BY facility_id, item_id
            )
            SELECT COUNTIF(IFNULL(b.batched, 0) != l.balance
                           AND l.balance >= 0) AS mismatches,
                   COUNTIF(l.balance < 0) AS below_zero
            FROM ledger l LEFT JOIN batched b USING (facility_id, item_id)
        """)
        assert rows[0]["mismatches"] == 0
        # Two phone reports on 2026-09-29/30 gave out stock at centres with
        # none on record, before the overdraw guard existed; the ledger keeps
        # them (nothing is retracted). The guard now holds such reports for
        # review, so this number must never grow.
        assert rows[0]["below_zero"] <= 2, rows[0]


class TestFulfilmentStateSurvivesPlanRebuilds:
    def test_fulfilment_is_a_separate_table(self):
        """`recommendations` is CREATE OR REPLACE'd; state written into it
        would be destroyed on the next rebuild."""
        rows = run_query("""
            SELECT table_type
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = 'transfer_fulfilment'
        """)
        assert rows[0]["table_type"] == "BASE TABLE"

    def test_it_does_not_collide_with_the_existing_status_column(self):
        """`recommendations.status` is the receiver's *stock* status.

        Reusing that name for fulfilment would silently overload a column that
        already means something else.
        """
        cols = run_query("""
            SELECT column_name
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = 'transfer_fulfilment'
        """)
        names = {c["column_name"] for c in cols}
        assert "fulfilment_status" in names
        assert "status" not in names

    def test_no_transfer_is_ever_recorded_as_received_without_dispatch(self):
        """Stock cannot arrive somewhere it never left."""
        rows = run_query("""
            SELECT COUNTIF(fulfilment_status = 'received'
                           AND dispatched_at IS NULL) AS impossible
            FROM `daysupply.daysupply.transfer_fulfilment`
        """)
        assert rows[0]["impossible"] == 0
