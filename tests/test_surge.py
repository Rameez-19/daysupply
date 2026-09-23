"""Part 2 — surge detection, the supply consequence, and reach.

The claims this block makes that would matter if they were wrong:

* the detection statistic can actually rank outbreaks (the classical one cannot)
* a surge is not declared on three cases becoming twelve
* a surge changes the supply answer rather than only lighting a lamp
* where reordering physically cannot work, the system says transfer, not order
* scenario mode computes rather than replays
* the population figure counts each person once
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import surge  # noqa: E402
from app.bq import run_query  # noqa: E402

# n = 12 monthly observations. A standardised residual cannot exceed this.
SERIES_MONTHS = 12
CLASSICAL_CEILING = (SERIES_MONTHS - 1) / math.sqrt(SERIES_MONTHS)


class TestSurgeStatistic:
    def test_classical_z_is_pinned_to_its_arithmetic_ceiling(self):
        """The whole reason the modified z is used.

        With twelve observations the largest attainable standardised residual
        is 11/sqrt(12) = 3.175. If the observed maximum sits just under it, the
        statistic is saturated and cannot distinguish a 12x outbreak from a 4x
        bump — which is precisely why it is not the test that fires.
        """
        rows = run_query("""
            SELECT MAX(z_classical) AS max_z, MIN(z_classical) AS min_z
            FROM `daysupply.daysupply.surge_signals`
        """)
        # z_classical is stored rounded to two decimals, so a residual at the
        # ceiling itself (3.1754) is stored as 3.18. Half a unit in the last
        # place is the tolerance that rounding introduces, and no more.
        assert rows[0]["max_z"] <= CLASSICAL_CEILING + 0.005, (
            "a standardised residual above the ceiling means the residual was "
            "not centred on its own mean before dividing")
        assert rows[0]["max_z"] > CLASSICAL_CEILING - 0.05, (
            "the classical statistic should be saturated at its ceiling here")

    def test_modified_z_is_not_bounded_and_can_rank(self):
        """MAD is immune to the outlier, so the statistic stays informative."""
        rows = run_query("""
            SELECT MAX(z_modified) AS max_z,
                   COUNT(DISTINCT ROUND(z_modified)) AS distinct_values
            FROM `daysupply.daysupply.surge_signals` WHERE is_surge
        """)
        assert rows[0]["max_z"] > CLASSICAL_CEILING * 3
        assert rows[0]["distinct_values"] > 20, "the statistic is not ranking"

    def test_the_two_statistics_disagree_about_ordering(self):
        """If they agreed, replacing one with the other would be pointless."""
        rows = run_query("""
            SELECT COUNT(*) AS misordered
            FROM `daysupply.daysupply.surge_signals`
            WHERE is_surge AND z_classical < 3.0
        """)
        assert rows[0]["misordered"] > 0, (
            "no detected surge falls below a 3-sigma classical rule, so the "
            "classical rule would have caught them all")

    def test_mad_of_zero_never_produces_a_surge(self):
        rows = run_query("""
            SELECT COUNTIF(mad_undefined AND is_surge) AS bad
            FROM `daysupply.daysupply.surge_signals`
        """)
        assert rows[0]["bad"] == 0


class TestSurgeIsNotNoise:
    def test_every_surge_clears_all_three_conditions(self):
        rows = run_query("""
            SELECT COUNTIF(NOT (passes_statistic AND passes_ratio
                                AND passes_magnitude)) AS inconsistent
            FROM `daysupply.daysupply.surge_signals` WHERE is_surge
        """)
        assert rows[0]["inconsistent"] == 0

    def test_a_small_district_going_from_three_to_twelve_is_not_a_surge(self):
        """The magnitude floor has to actually exclude something."""
        rows = run_query("""
            SELECT COUNT(*) AS excluded
            FROM `daysupply.daysupply.surge_signals`
            WHERE passes_statistic AND passes_ratio AND NOT passes_magnitude
        """)
        assert rows[0]["excluded"] > 0, (
            "the magnitude floor excluded nothing, so it is not doing any work")

    def test_expectation_is_the_pooled_pattern_not_a_flat_average(self):
        """If expected == baseline, seasonality was never applied."""
        rows = run_query("""
            SELECT COUNTIF(ABS(pooled_multiplier - 1.0) > 0.05) AS seasonal,
                   COUNT(*) AS total
            FROM `daysupply.daysupply.surge_signals`
        """)
        assert rows[0]["seasonal"] > rows[0]["total"] * 0.5

    def test_a_habitually_volatile_district_is_not_flagged_every_month(self):
        """Gadchiroli swings 2.2x, 2.3x and 3.0x against the pooled vector.

        Its malaria season is winter-peaking against a monsoon-shaped pooled
        pattern, so its residuals are large all year and its MAD is large with
        them. A test that called that district surging every month would be
        measuring the wrong thing.
        """
        rows = run_query("""
            SELECT COUNTIF(is_surge) AS surges, COUNT(*) AS months
            FROM `daysupply.daysupply.surge_signals`
            WHERE district_key = 'GADCHIROLI' AND atc_class = 'P01BA'
        """)
        assert rows[0]["months"] == SERIES_MONTHS
        assert rows[0]["surges"] == 0

    def test_the_malaria_worked_example_is_real_and_detected(self):
        """Brihan Mumbai, January: 2,345 confirmed against 988 expected."""
        rows = run_query("""
            SELECT observed, expected, surge_multiplier, z_modified,
                   z_classical, is_surge
            FROM `daysupply.daysupply.surge_signals`
            WHERE district_key = 'BRIHAN MUMBAI' AND atc_class = 'P01BA'
              AND month = 'January'
        """)
        assert rows, "the worked example is missing from the data"
        row = rows[0]
        assert row["is_surge"]
        assert row["observed"] > row["expected"]
        assert row["z_classical"] < 3.0, (
            "the example is only interesting because a 3-sigma rule misses it")


class TestSurgeChangesTheSupplyAnswer:
    def test_the_surge_reorder_point_is_higher_than_the_steady_one(self):
        rows = run_query("""
            SELECT COUNTIF(reorder_point_surge <= reorder_point) AS not_raised,
                   COUNT(*) AS total
            FROM `daysupply.daysupply.surge_supply_impact`
        """)
        assert rows[0]["total"] > 0
        assert rows[0]["not_raised"] == 0

    def test_facilities_become_at_risk_that_were_not_before(self):
        rows = run_query("""
            SELECT COUNTIF(newly_at_risk) AS newly
            FROM `daysupply.daysupply.surge_supply_impact`
        """)
        assert rows[0]["newly"] > 0, (
            "if nothing changes status, the surge is not reaching the plan")

    def test_lead_time_decisive_means_exactly_what_it_says(self):
        """Runs out before an indent can arrive — no other definition."""
        rows = run_query("""
            -- days_to_stockout is stored to one decimal and the decision is
            -- taken on the unrounded value, so 10.96 days against an 11-day
            -- lead time is stored as 11.0 and is correctly decisive. The 0.05
            -- margin is that rounding, and no more.
            SELECT COUNTIF(lead_time_decisive
                           AND days_to_stockout >= lead_time_days + 0.05) AS wrong,
                   COUNTIF(NOT lead_time_decisive
                           AND days_to_stockout < lead_time_days - 0.05) AS missed
            FROM `daysupply.daysupply.surge_supply_impact`
        """)
        assert rows[0]["wrong"] == 0
        assert rows[0]["missed"] == 0

    def test_a_facility_that_cannot_be_resupplied_is_told_to_transfer(self):
        """The UI must never show an order quantity as if it would arrive."""
        rows = run_query("""
            SELECT COUNTIF(lead_time_decisive
                           AND surge_action != 'transfer_only') AS wrong
            FROM `daysupply.daysupply.surge_supply_impact`
        """)
        assert rows[0]["wrong"] == 0

    def test_transfer_only_is_decided_by_lead_time_not_by_band(self):
        """This used to assert a monotone gradient: centres with longer lead
        times are transfer-only more often. Across five states it held weakly
        (43.5% / 47.9% / 80.0%, the last on 5 lines). With Uttar Pradesh
        added it does not: 49.8% at 6-10 days, 45.4% at 11-15. The claim is
        withdrawn in CLAIMS §0 rather than rescued here.

        What does hold, by construction, is that the decision is taken per
        line on days of cover against that line's own lead time, which the
        test above pins. This checks only that every band has lines to
        decide on, so a lead-time build that collapsed to one value fails."""
        rows = run_query("""
            SELECT COUNT(DISTINCT lead_time_days) AS lead_times,
                   COUNTIF(lead_time_decisive) AS decisive,
                   COUNTIF(NOT lead_time_decisive) AS not_decisive
            FROM `daysupply.daysupply.surge_supply_impact`
        """)[0]
        assert rows["lead_times"] > 3, rows
        assert rows["decisive"] > 0 and rows["not_decisive"] > 0, rows


class TestSurgeRedistribution:
    def test_a_donor_is_never_stripped_below_its_own_surge_requirement(self):
        rows = run_query("""
            SELECT COUNTIF(donor_cover_after < 0) AS stranded
            FROM `daysupply.daysupply.surge_recommendations`
        """)
        assert rows[0]["stranded"] == 0

    def test_donor_stock_is_never_promised_twice_within_an_episode(self):
        """The steady-state engine can double-promise; this one must not.

        Grouped by surge month on purpose. The table holds a row for every
        detected surge month and those are *alternative* episodes — a donor's
        spare stock is one current position, so it may be committed once per
        episode but summing across months would promise it twelve times. That
        is why every read of the table is scoped to a single month.
        """
        rows = run_query("""
            SELECT COUNT(*) AS over_allocated FROM (
              SELECT r.from_facility_id, r.supplied_item_id, r.surge_month,
                     SUM(r.quantity) AS promised,
                     ANY_VALUE(s.on_hand) AS donor_on_hand
              FROM `daysupply.daysupply.surge_recommendations` r
              JOIN `daysupply.daysupply.reorder_status` s
                ON s.facility_id = r.from_facility_id
               AND s.item_id = r.supplied_item_id
              GROUP BY r.from_facility_id, r.supplied_item_id, r.surge_month
            ) WHERE promised > donor_on_hand
        """)
        assert rows[0]["over_allocated"] == 0

    def test_reads_of_the_transfer_table_are_scoped_to_one_month(self):
        """A caller that forgets the month must not get a mixed list."""
        default = surge.get_surge_transfers(limit=200)
        months = {row["surge_month"] for row in default}
        assert len(months) <= 1, (
            f"the default read spans {len(months)} surge months, which would "
            "over-promise donors")

    def test_rationing_actually_happens(self):
        """If nothing is ever rationed, the priority order is untested."""
        rows = run_query("""
            SELECT COUNTIF(donor_partially_exhausted) AS rationed
            FROM `daysupply.daysupply.surge_recommendations`
        """)
        assert rows[0]["rationed"] > 0

    def test_vital_is_never_rationed_behind_a_desirable_from_one_donor(self):
        """Vital outranks Desirable for the same donor's finite stock."""
        rows = run_query("""
            SELECT COUNT(*) AS inversions
            FROM `daysupply.daysupply.surge_recommendations` v
            JOIN `daysupply.daysupply.surge_recommendations` d
              ON d.from_facility_id = v.from_facility_id
             AND d.supplied_item_id = v.supplied_item_id
             AND d.surge_month = v.surge_month
            WHERE v.ven_class = 'Vital' AND d.ven_class = 'Desirable'
              AND v.claim_rank > d.claim_rank
        """)
        assert rows[0]["inversions"] == 0

    def test_the_widened_radius_is_recorded_on_every_row(self):
        rows = run_query("""
            SELECT COUNTIF(distance_km > transfer_max_km) AS beyond_limit,
                   MAX(transfer_max_km) AS limit_km
            FROM `daysupply.daysupply.surge_recommendations`
        """)
        assert rows[0]["beyond_limit"] == 0
        assert rows[0]["limit_km"] > 150, "the surge radius did not widen"


class TestNetworkAbsorption:
    def test_absorption_falls_as_the_spike_grows(self):
        rows = run_query("""
            SELECT multiplier,
                   SAFE_DIVIDE(COUNTIF(absorbs), COUNT(*)) AS share
            FROM `daysupply.daysupply.network_absorption`
            GROUP BY multiplier ORDER BY multiplier
        """)
        shares = [r["share"] for r in rows]
        assert len(shares) >= 3
        assert shares == sorted(shares, reverse=True), (
            "a bigger spike must never be easier to absorb")

    def test_absorbs_agrees_with_its_own_arithmetic(self):
        rows = run_query("""
            SELECT COUNTIF(absorbs != (absorption_days >= slowest_lead_time))
                     AS disagreements
            FROM `daysupply.daysupply.network_absorption`
            WHERE absorption_days IS NOT NULL
        """)
        assert rows[0]["disagreements"] == 0

    def test_a_district_that_absorbs_is_never_short(self):
        rows = run_query("""
            SELECT COUNTIF(absorbs AND units_short > 0) AS contradictions
            FROM `daysupply.daysupply.network_absorption`
        """)
        assert rows[0]["contradictions"] == 0


class TestScenarioMode:
    """Scenario mode must compute, not replay."""

    def test_an_arbitrary_multiplier_is_accepted(self):
        """A precomputed 2x/3x/5x lookup could not answer 2.7x."""
        result = surge.run_scenario("Brihan Mumbai", "P01BA", 2.7)
        assert result["multiplier"] == 2.7
        assert result["computed_live"] is True
        assert result["facility_count"] > 0

    def test_a_bigger_spike_never_improves_the_outcome(self):
        low = surge.run_scenario("Brihan Mumbai", "P01BA", 1.5)
        high = surge.run_scenario("Brihan Mumbai", "P01BA", 5.0)
        assert high["facilities_failing"] >= low["facilities_failing"]
        assert high["absorption_days"] <= low["absorption_days"]
        assert high["units_short"] >= low["units_short"]

    def test_stockout_day_scales_with_the_multiplier(self):
        """Doubling demand must halve the time to stockout.

        Compared with an absolute tolerance, not a relative one: the figures
        are rounded to a tenth of a day for display, and on a facility with
        under a day of cover that rounding is most of the value.
        """
        one = surge.run_scenario("Brihan Mumbai", "P01BA", 1.0)
        two = surge.run_scenario("Brihan Mumbai", "P01BA", 2.0)
        assert one["first_stockout_days"] == pytest.approx(
            two["first_stockout_days"] * 2, abs=0.2)

    @pytest.mark.parametrize("district,atc,multiplier", [
        ("", "P01BA", 3.0),
        ("Brihan Mumbai", "", 3.0),
        ("Brihan Mumbai", "P01BA", 0.5),
        ("Brihan Mumbai", "P01BA", 999.0),
        ("Nowhere At All", "P01BA", 3.0),
    ])
    def test_unanswerable_scenarios_are_refused(self, district, atc,
                                                multiplier):
        with pytest.raises(surge.ScenarioError):
            surge.run_scenario(district, atc, multiplier)

    def test_the_verdict_matches_the_arithmetic(self):
        for m in (1.0, 2.0, 3.0, 5.0):
            r = surge.run_scenario("Brihan Mumbai", "P01BA", m)
            expected = r["absorption_days"] >= r["slowest_lead_time"]
            assert r["district_holds"] == expected, m


class TestPopulationReach:
    def test_each_person_is_counted_once(self):
        """Catchments nest. Summing every facility type triple-counts.

        A correct once-only tiling lands near, and below, the Census 2011 rural
        population. Well above it means catchments are being double-counted.
        """
        rows = run_query("""
            SELECT population, census_2011_rural_india
            FROM `daysupply.daysupply.population_reach`
            WHERE tier = 'national_directory'
        """)
        ratio = rows[0]["population"] / rows[0]["census_2011_rural_india"]
        assert 0.80 <= ratio <= 1.05, (
            f"PHC catchments sum to {ratio:.2f}x the rural population")

    def test_the_naive_figure_would_have_been_wrong_by_about_threefold(self):
        """Recorded so the discarded number stays on the record."""
        rows = run_query("""
            SELECT SUM(population_served) AS naive
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND population_served IS NOT NULL
        """)
        national = run_query("""
            SELECT population FROM `daysupply.daysupply.population_reach`
            WHERE tier = 'national_directory'
        """)[0]["population"]
        assert rows[0]["naive"] > national * 3

    def test_tiers_nest(self):
        rows = run_query("""
            SELECT tier, phcs, population
            FROM `daysupply.daysupply.population_reach` ORDER BY tier_order
        """)
        assert [r["tier"] for r in rows] == [
            "operating", "demand_data_footprint", "national_directory"]
        for a, b in zip(rows, rows[1:]):
            assert b["phcs"] > a["phcs"]
            assert b["population"] > a["population"]

    def test_no_urban_phc_contributes_to_reach(self):
        """The Rural Health Statistics average is a rural figure."""
        rows = run_query("""
            SELECT COUNT(*) AS counted_phcs
            FROM `daysupply.daysupply.facilities`
            WHERE country_code = 'IN' AND facility_type = 'phc'
              AND location_type = 'rural' AND population_served IS NOT NULL
        """)
        national = run_query("""
            SELECT phcs FROM `daysupply.daysupply.population_reach`
            WHERE tier = 'national_directory'
        """)[0]["phcs"]
        assert national == rows[0]["counted_phcs"]


class TestMedicineVerticalUnharmed:
    """Part 2 must not weaken what already worked."""

    def test_the_steady_state_plan_covers_every_forecast_series(self):
        rows = run_query("""
            SELECT (SELECT COUNT(*) FROM `daysupply.daysupply.reorder_status`)
                     AS reorder_rows,
                   (SELECT COUNT(*) FROM `daysupply.daysupply.demand_baseline`)
                     AS series
        """)
        assert rows[0]["reorder_rows"] == rows[0]["series"] > 0

    def test_steady_state_recommendations_remain_sane(self):
        """Structural assertions, not frozen magic numbers.

        This used to pin `recs == 525` and `units == 64211`. Those were the
        right check while `reorder_status` was a precomputed table, because
        nothing but a rebuild could move them. It is now a view over live
        stock, so **every capture legitimately changes both figures** — the
        first real capture moved them to 527 and 64,218. A test asserting the
        old constants would fail on correct behaviour and teach people to
        edit the number until it passes.

        What must stay true is the shape of the plan, so that is what is
        checked. The current figures live in `docs/CLAIMS.md`, which is
        re-verified against the live dataset rather than hardcoded here.
        """
        rows = run_query("""
            SELECT COUNT(*) AS recs,
                   SUM(quantity) AS units,
                   COUNTIF(quantity <= 0) AS non_positive,
                   COUNTIF(from_facility_id = to_facility_id) AS self_transfer,
                   COUNTIF(receiver_cover_after < receiver_cover_before)
                     AS receiver_worse_off,
                   COUNTIF(donor_cover_after < 0) AS donor_stranded
            FROM `daysupply.daysupply.recommendations`
        """)
        row = rows[0]
        assert row["recs"] > 400, "the plan has collapsed"
        assert row["units"] > 50_000
        assert row["non_positive"] == 0
        assert row["self_transfer"] == 0
        assert row["receiver_worse_off"] == 0
        assert row["donor_stranded"] == 0

    def test_surge_tables_are_separate_from_steady_state_ones(self):
        """A surge recommendation must never leak into the normal queue."""
        rows = run_query("""
            SELECT COUNT(*) AS leaked
            FROM `daysupply.daysupply.recommendations` r
            JOIN `daysupply.daysupply.surge_recommendations` s
              ON s.recommendation_id = r.recommendation_id
        """)
        assert rows[0]["leaked"] == 0
