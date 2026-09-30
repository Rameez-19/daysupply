"""The Network page ranks districts; a district is a state and a name.

Pratapgarh is a district in both Rajasthan and Uttar Pradesh. Grouped by name
alone, the two became one row labelled with whichever state came first.
"""

from app import network
from app.bq import run_query

D = "daysupply.daysupply"


def _count(key: str) -> int:
    return run_query(f"""
        SELECT COUNT(*) AS n FROM (
          SELECT {key} FROM `{D}.reorder_status`
          GROUP BY {key} HAVING COUNT(*) >= {network.MIN_FOR_RATE})
    """)[0]["n"]


def test_every_state_and_district_is_its_own_row():
    assert network.medicine_comparison()["summary"]["districts"] == _count("state, district")


def test_the_data_really_has_a_shared_district_name():
    """Otherwise the test above could not tell the two groupings apart."""
    assert _count("state, district") > _count("district")
