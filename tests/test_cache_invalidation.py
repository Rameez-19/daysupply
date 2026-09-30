"""A capture must clear every cached answer that depends on the stock position.

The officer pages added after the write-through was built (Today, the Action
queue, the Map, the Network page) cached for five minutes and were not in the
list, so a report saved on a phone did not show on the officer's screen until
the cache ran out.
"""

import pytest

from app import bq


@pytest.fixture(autouse=True)
def isolated_cache():
    """These tests plant fake entries under real keys; never let them leak."""
    with bq._cache_lock:
        saved = dict(bq._cache)
        bq._cache.clear()
    yield
    with bq._cache_lock:
        bq._cache.clear()
        bq._cache.update(saved)

STOCK_KEYS = [
    "v2:Assam:Cachar:IN-19662:0",   # Today, one centre
    "v2::::0",                      # Today, national
    "v2bed:Assam:Cachar:IN-19662",  # Today, beds
    "v2staff:::",                   # Today, staff
    "reported:bed:x:[]",            # centres reporting today
    "triage:Assam:Cachar:IN-19662", # Action queue
    "access:Assam::0",              # access scorecard
    "net:med:Assam:0",              # Network page
    "map:Assam",                    # transfers on the map
    "beds:sum:Assam::", "staff:sum:Assam::",  # bed and staff status
    "alerts:x", "recs:x",           # the original list still applies
]
KEPT_KEYS = [
    "v2:geography",       # the dropdown pre-aggregate; a capture cannot change it
    "register:Assam",     # the facility register on the map
    "surge:current_month",
    "model:evidence",
]


def test_a_capture_clears_every_stock_dependent_page():
    for k in STOCK_KEYS + KEPT_KEYS:
        bq._cache_put(k, ["cached"], 300)
    bq.invalidate_stock_reads()
    stale = [k for k in STOCK_KEYS if bq._cache_get(k) is not None]
    assert not stale, f"still cached after a capture: {stale}"


def test_a_capture_keeps_what_it_cannot_change():
    for k in KEPT_KEYS:
        bq._cache_put(k, ["cached"], 300)
    bq.invalidate_stock_reads()
    dropped = [k for k in KEPT_KEYS if bq._cache_get(k) is None]
    assert not dropped, f"dropped although a capture cannot change it: {dropped}"
