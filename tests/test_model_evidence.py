"""ARIMA_PLUS, and the claim that everything rests on it.

The model is the most load-bearing thing in the system and was the least
visible: no page named it, and the single chart that drew it was deleted along
with the markup it wrote into. Meanwhile every shortage on every page is a
consequence of it —

    ML.FORECAST(demand_forecast)
      -> demand_baseline.avg_daily_demand
        -> reorder_status.reorder_point = demand x lead_time + 1.65 x sigma x sqrt(lead_time)
          -> needs_reorder -> the shortage list, action queue, transfers, map

These pin two things. That the chain is real and joined up at both ends, so
"everything downstream of the model" is arithmetic rather than a slogan. And
that every figure on the panel is read back out of BigQuery rather than typed
into the page, because a hardcoded 2,794 would survive the model being deleted.
"""

import pytest

from app import forecast


@pytest.fixture(scope="module")
def ev():
    return forecast.model_evidence()


class TestTheModelDescribesItself:
    def test_it_is_arima_plus(self, ev):
        assert ev["model"]["name"] == "BigQuery ML ARIMA_PLUS"
        assert ev["model"]["table"].endswith("demand_forecast")

    def test_every_series_is_fitted(self, ev):
        assert ev["model"]["series"] > 0
        assert ev["model"]["series"] == 2794, (
            "the trained series count moved; check the model was retrained "
            "rather than partially built")

    def test_the_orders_were_chosen_per_series_not_stamped(self, ev):
        """A single (p,d,q) across all 2,794 series would mean auto-ARIMA never
        selected anything, and the panel's claim would be empty."""
        assert ev["model"]["distinct_orders"] > 1, ev["model"]
        assert len(ev["orders"]) > 1
        assert sum(o["n"] for o in ev["orders"]) <= ev["model"]["series"]

    def test_seasonality_was_detected_rather_than_configured(self, ev):
        m = ev["model"]
        assert 0 < m["seasonal"] < m["series"], (
            "either none or all series are seasonal, which would mean the "
            "flag is constant rather than detected")
        assert m["seasonal_pct"] == pytest.approx(
            round(100 * m["seasonal"] / m["series"], 1))

    def test_the_horizon_and_interval_come_from_the_module(self, ev):
        assert ev["model"]["horizon"] == forecast.HORIZON
        assert ev["model"]["confidence"] == forecast.CONFIDENCE


class TestTheChainIsRealAtBothEnds:
    def test_every_step_carries_a_figure(self, ev):
        assert len(ev["chain"]) >= 4
        for c in ev["chain"]:
            assert c["figure"] and c["step"] and c["detail"], c

    def test_the_first_step_is_the_model_itself(self, ev):
        first = ev["chain"][0]
        assert "ML.FORECAST" in first["step"]
        assert first["figure"] == f"{ev['model']['series']:,}"

    def test_the_baseline_covers_every_trained_series(self, ev):
        """`demand_baseline` is AVG(ML.FORECAST) grouped by facility and item,
        so a line missing here is a series whose forecast reaches no reorder
        point — it would silently never raise a shortage."""
        from app.bq import run_query
        n = run_query("""
            SELECT COUNT(*) AS n
            FROM `daysupply.daysupply.demand_baseline`
        """)[0]["n"]
        assert n == ev["model"]["series"], (n, ev["model"]["series"])

    def test_the_reorder_point_really_is_built_from_the_forecast(self):
        """The join that makes the whole claim true. If `reorder_status` ever
        stopped reading `demand_baseline`, every page would keep rendering and
        the model would quietly no longer matter."""
        from app.bq import run_query
        d = run_query("""
            SELECT view_definition
            FROM `daysupply.daysupply.INFORMATION_SCHEMA.VIEWS`
            WHERE table_name = 'reorder_status'
        """)[0]["view_definition"]
        assert "demand_baseline" in d
        assert "avg_daily_demand" in d

    def test_the_shortage_count_matches_the_table_it_claims(self, ev):
        from app.bq import run_query
        n = run_query("""
            SELECT COUNTIF(needs_reorder) AS n
            FROM `daysupply.daysupply.reorder_status`
        """)[0]["n"]
        figures = [c["figure"] for c in ev["chain"]]
        assert f"{n:,}" in figures, (n, figures)

    def test_no_figure_is_hardcoded_in_the_page(self):
        """A constant typed into index.html would survive the model being
        deleted, which is the opposite of evidence."""
        from pathlib import Path
        html = (Path(__file__).resolve().parents[1]
                / "web" / "index.html").read_text(encoding="utf-8")
        start = html.index('id="model-chain"')
        end = html.index('id="model-orders"')
        block = html[start:end]
        for figure in ("2,794", "2794", "597", "527", "2,149"):
            assert figure not in block, (
                f"{figure} is written into the markup; it must come from "
                "/api/v1/model-evidence")


class TestTheSeriesChartIsRealModelOutput:
    def test_a_trained_series_can_be_drawn(self):
        s = forecast.pick_series("Telangana")
        assert s, "no trained series in the default scope"
        d = forecast.get_forecast_series(s["facility_id"], s["item_id"],
                                         horizon=14)
        assert d["source"] == "BigQuery ML ARIMA_PLUS"
        assert len(d["labels"]) == len(d["forecast"]) == len(d["upper"])

    def test_the_interval_brackets_the_forecast(self):
        """An upper bound below the forecast would render as an inverted band
        and would mean the columns had been swapped."""
        s = forecast.pick_series("Telangana")
        d = forecast.get_forecast_series(s["facility_id"], s["item_id"],
                                         horizon=14)
        pairs = [(lo, f, hi) for lo, f, hi
                 in zip(d["lower"], d["forecast"], d["upper"])
                 if lo is not None and f is not None and hi is not None]
        assert pairs
        for lo, f, hi in pairs:
            assert lo <= f <= hi, (lo, f, hi)

    def test_history_and_forecast_do_not_overlap(self):
        """They share an x-axis; a day carrying both would draw two points for
        one date and make the join look like a spike."""
        s = forecast.pick_series("Telangana")
        d = forecast.get_forecast_series(s["facility_id"], s["item_id"],
                                         horizon=14)
        both = [i for i, (h, f) in enumerate(zip(d["historical"], d["forecast"]))
                if h is not None and f is not None]
        # Exactly one: the last observed point is duplicated on purpose so the
        # two lines join instead of showing a gap.
        assert len(both) == 1, both

    def test_a_scope_with_no_trained_series_raises_rather_than_returning_zeros(
            self):
        with pytest.raises(forecast.ForecastUnavailable):
            forecast.get_forecast_series("NOT_A_FACILITY", "NOT_AN_ITEM")


class TestTheEvidencePageDoesNotLeakItsOwnPayload:
    """The panel carrying the project's central claim — 19.4% -> 14.4% — was
    rendering `JSON.stringify(d).slice(0, 400)` into a paragraph.

    `/api/v1/exchange/evaluation` returns flat keys (`flat_wmape`,
    `pooled_wmape`, ...) and never an `arms` array, so the renderer's
    `arms.length ? table : debug-dump` always took the debug branch. Nobody
    noticed because the blob contains the right numbers.

    It also broke the page: a JSON string has no spaces, so it cannot wrap, and
    it forced the whole Evidence view 319px wider than the viewport — cutting
    every other panel off at the right edge.
    """

    def test_the_payload_is_flat_keys_not_an_arms_array(self):
        """The mismatch itself. The renderer asked for `d.arms`; the API has
        never sent one. If it ever starts to, the page should be revisited
        rather than silently falling back to a debug dump again."""
        from app import exchange
        d = exchange.evaluation_summary()
        assert "arms" not in d and "evaluation" not in d, sorted(d)
        for key in ("flat_wmape", "pooled_wmape", "demo_in_wmape",
                    "demo_out_wmape", "predictions", "districts"):
            assert key in d, (key, sorted(d))

    def test_the_four_arms_all_carry_a_number(self):
        """An arm arriving as None renders as "null% error", which this
        project has already shipped once."""
        from app import exchange
        d = exchange.evaluation_summary()
        for key in ("flat_wmape", "pooled_wmape", "demo_in_wmape",
                    "demo_out_wmape"):
            assert isinstance(d[key], (int, float)), (key, d[key])

    def test_the_panel_verdict_is_arithmetic_on_the_payload(self):
        from app import exchange
        d = exchange.evaluation_summary()
        assert d["improvement_points"] == pytest.approx(
            round(d["flat_wmape"] - d["pooled_wmape"], 1))
        assert d["best_arm"] == "pooled"

    def test_the_renderer_reads_the_keys_the_api_actually_sends(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1]
              / "web" / "app.js").read_text(encoding="utf-8")
        for key in ("flat_wmape", "pooled_wmape", "demo_in_wmape",
                    "demo_out_wmape"):
            assert key in js, f"{key} is never read by the page"

    @staticmethod
    def _code_only(js: str) -> str:
        """Comments are not code.

        The first version of this test failed on the comment above the fix,
        which quotes the construct it forbids — the same way the SELECT * guard
        once fired on a SQL comment containing the phrase. Whole-line comments
        are stripped rather than everything after `//`, so a `https://` inside
        a string cannot silently truncate a line of real code.
        """
        import re
        js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
        return "\n".join(ln for ln in js.splitlines()
                         if not ln.lstrip().startswith("//"))

    def test_no_panel_stringifies_its_payload_into_the_page(self):
        """The specific construct that shipped. A JSON dump is a debug tool and
        it cannot wrap, so it takes the layout with it."""
        from pathlib import Path
        import re
        js = self._code_only((Path(__file__).resolve().parents[1]
                              / "web" / "app.js").read_text(encoding="utf-8"))
        assert "JSON.stringify(d).slice" not in js
        # innerHTML = ... JSON.stringify(...) — in any panel, not just this one.
        for m in re.finditer(r"innerHTML\s*=\s*[^;]{0,400}", js):
            assert "JSON.stringify" not in m.group(0), m.group(0)[:160]

    def test_the_arms_are_labelled_in_state_and_out_of_state(self):
        """Same correction as Plan ahead: demo_out is the closest twin in
        ANOTHER state, not a poor match."""
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1]
              / "web" / "app.js").read_text(encoding="utf-8")
        js = self._code_only(js)
        block = js[js.index("EXCHANGE_ARMS"):js.index("async function loadExchangeEval")]
        assert "same state" in block
        assert "another state" in block
        assert "deliberately poor" not in block
