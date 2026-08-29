"""Block A — cost guard rails on the BigQuery access layer.

These are the rules that stop an accidental full-table scan reaching BigQuery.
They run entirely offline: the guard rails are checked before any client is
created, so nothing here bills.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bq import (  # noqa: E402
    UnsafeQuery,
    _check_guard_rails,
    _human_bytes,
    clear_cache,
    _cache_get,
    _cache_put,
)


class TestSelectStarGuard:
    """`SELECT *` on the 200,438-row facility table is forbidden."""

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM `daysupply.daysupply.facilities`",
        "select   *  from daysupply.facilities",
        "SELECT f.* FROM `daysupply.daysupply.facilities` f",
        "SELECT\n  *\nFROM facilities",
    ])
    def test_rejects_select_star_on_facilities(self, sql):
        with pytest.raises(UnsafeQuery):
            _check_guard_rails(sql)

    @pytest.mark.parametrize("sql", [
        "SELECT facility_id, name FROM `daysupply.daysupply.facilities`",
        "SELECT COUNT(*) FROM `daysupply.daysupply.facilities`",
        "SELECT COUNTIF(is_demo_facility) FROM facilities",
    ])
    def test_allows_projected_columns(self, sql):
        _check_guard_rails(sql)  # must not raise

    def test_count_star_is_not_select_star(self):
        """COUNT(*) is an aggregate, not a projection — it must be allowed."""
        _check_guard_rails(
            "SELECT admin_l1, COUNT(*) AS n FROM facilities GROUP BY 1"
        )


class TestCache:
    def test_put_and_get(self):
        clear_cache()
        _cache_put("k", [{"a": 1}], ttl=60)
        assert _cache_get("k") == [{"a": 1}]

    def test_expired_entry_is_dropped(self):
        clear_cache()
        _cache_put("k", [{"a": 1}], ttl=-1)
        assert _cache_get("k") is None

    def test_missing_key(self):
        clear_cache()
        assert _cache_get("nope") is None

    def test_clear(self):
        _cache_put("k", [1], ttl=60)
        clear_cache()
        assert _cache_get("k") is None


class TestHumanBytes:
    def test_formats_scales(self):
        assert _human_bytes(512) == "512 B"
        assert "KB" in _human_bytes(2048)
        assert "MB" in _human_bytes(5 * 1024 ** 2)
        assert "GB" in _human_bytes(10 * 1024 ** 3)
