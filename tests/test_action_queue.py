"""The action queue must account for every shortage exactly once.

The page used to open with all 597 shortages above a queue of 527 transfers.
525 of those rows already appeared in the queue below with an Approve button,
so the first list was 88% a restatement of the second — which is why it read as
a log with nothing to do. What the duplication hid was the 39 that no routine
action fixes.

The failure mode of a triage is a row falling through the gap between two
panels and being seen by nobody, so the arithmetic is pinned first and hardest.
"""

import pytest

from app import action_queue


@pytest.fixture(scope="module")
def triaged():
    return action_queue.triage()


class TestEveryShortageIsInExactlyOneGroup:
    def test_the_three_groups_sum_to_the_total(self, triaged):
        s = triaged["summary"]
        assert s["transfer"] + s["order"] + s["escalate"] == s["total"], s

    def test_no_shortage_appears_in_two_groups(self, triaged):
        key = lambda r: (r["facility_id"], r["item_id"])
        groups = [
            {key(r) for r in triaged["escalate"]},
            {key(r) for r in triaged["order"]},
            {key(r) for r in triaged["transfer"]},
        ]
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                assert not (groups[a] & groups[b]), (
                    f"rows in two groups at once: {groups[a] & groups[b]}")

    def test_no_shortage_is_missing_from_all_three(self, triaged):
        key = lambda r: (r["facility_id"], r["item_id"])
        placed = ({key(r) for r in triaged["escalate"]}
                  | {key(r) for r in triaged["order"]}
                  | {key(r) for r in triaged["transfer"]})
        everything = {key(r) for r in triaged["all_shortages"]}
        missing = everything - placed
        assert not missing, (
            f"{len(missing)} shortages are in no panel and would be seen by "
            f"nobody: {sorted(missing)[:5]}")

    def test_the_total_matches_the_shortage_count(self, triaged):
        from app.bq import run_query
        n = run_query("""
            SELECT COUNT(*) AS n FROM `daysupply.daysupply.reorder_status`
            WHERE needs_reorder
        """)[0]["n"]
        assert triaged["summary"]["total"] == n


class TestTheGroupsMeanWhatTheySay:
    def test_escalation_has_no_transfer_and_cannot_be_ordered_in_time(
            self, triaged):
        for r in triaged["escalate"]:
            assert not r["has_transfer"], r
            assert r["days_of_cover"] is not None
            assert r["days_of_cover"] < r["lead_time_days"], r

    def test_the_order_group_has_no_transfer_but_arrives_in_time(self, triaged):
        for r in triaged["order"]:
            assert not r["has_transfer"], r
            if r["days_of_cover"] is not None:
                assert r["days_of_cover"] >= r["lead_time_days"], r

    def test_the_transfer_group_all_have_one(self, triaged):
        for r in triaged["transfer"]:
            assert r["has_transfer"], r

    def test_the_transfer_group_matches_the_recommendations_table(
            self, triaged):
        """The claim behind the whole split: these rows really are the ones the
        queue below already covers."""
        from app.bq import run_query
        rows = run_query("""
            SELECT DISTINCT to_facility_id AS f, requested_item_id AS i
            FROM `daysupply.daysupply.recommendations`
        """)
        covered = {(r["f"], r["i"]) for r in rows}
        for r in triaged["transfer"]:
            assert (r["facility_id"], r["item_id"]) in covered, r

    def test_unknown_cover_is_never_called_an_emergency(self, triaged):
        """An unmeasured line is unmeasured. Putting a guess at the top of the
        one panel that most needs to be trusted would be the worst place in the
        product to do it."""
        for r in triaged["escalate"]:
            assert r["days_of_cover"] is not None, r


class TestTheEscalationPanelIsWorthLeadingWith:
    def test_it_is_ordered_by_days_left(self, triaged):
        cover = [r["days_of_cover"] for r in triaged["escalate"]]
        assert cover == sorted(cover), cover

    def test_it_is_small_enough_to_act_on(self, triaged):
        """If this ever approached the full shortage count the split would have
        stopped meaning anything."""
        s = triaged["summary"]
        assert s["escalate"] < s["total"] / 2

    def test_the_summary_counts_match_the_rows(self, triaged):
        s = triaged["summary"]
        assert s["escalate"] == len(triaged["escalate"])
        assert s["order"] == len(triaged["order"])
        assert s["transfer"] == len(triaged["transfer"])
        assert s["escalate_vital"] == sum(
            1 for r in triaged["escalate"] if r["ven_class"] == "Vital")
        assert s["escalate_out_now"] == sum(
            1 for r in triaged["escalate"] if (r["on_hand"] or 0) <= 0)

    def test_the_shortfall_is_never_negative(self, triaged):
        for r in triaged["all_shortages"]:
            assert (r["shortfall"] or 0) >= 0, r


class TestScoping:
    @pytest.mark.parametrize("state", ["Assam", "Maharashtra"])
    def test_a_state_scope_returns_only_that_state(self, state):
        d = action_queue.triage(state)
        assert {r["state"] for r in d["all_shortages"]} <= {state}

    def test_a_state_scope_still_adds_up(self):
        s = action_queue.triage("Assam")["summary"]
        assert s["transfer"] + s["order"] + s["escalate"] == s["total"]

    def test_a_state_scope_is_smaller_than_the_nation(self, triaged):
        one = action_queue.triage("Assam")
        assert one["summary"]["total"] < triaged["summary"]["total"]
