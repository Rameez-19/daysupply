"""Local validation tests for facility ingestion.

Run: .venv\\Scripts\\python -m pytest tests/test_ingestion.py -v

These tests validate data parsing and transformation WITHOUT BigQuery. The
facility master is parsed once and shared, because it is a 20 MB CSV.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXPECTED_ROWS = 200_438
EXPECTED_STATES = 37
EXPECTED_DISTRICTS = 668
DEMO_STATES = {"Telangana", "Maharashtra", "Rajasthan", "Delhi", "Assam"}


@pytest.fixture(scope="module")
def india():
    """Parse the facility master once for the whole module."""
    from ingestion.load_facilities import build_facilities
    df, source_rows = build_facilities()
    return df, source_rows


class TestIndiaIngestion:
    """Validate Indian facility data parsing — Block A."""

    def test_row_count_matches_source(self, india):
        df, source_rows = india
        assert source_rows == EXPECTED_ROWS, \
            f"Source file has {source_rows}, expected {EXPECTED_ROWS}"
        assert len(df) == source_rows, \
            f"Transform changed row count: {source_rows} -> {len(df)}"

    def test_national_coverage(self, india):
        """Every state and district must survive the load — no sampling."""
        df, _ = india
        assert df["admin_l1"].nunique() == EXPECTED_STATES
        assert df["admin_l2"].nunique() == EXPECTED_DISTRICTS

    def test_facility_id_format_and_uniqueness(self, india):
        df, _ = india
        assert df["facility_id"].str.startswith("IN-").all()
        assert df["facility_id"].is_unique, "Duplicate facility IDs found"

    def test_country_code(self, india):
        df, _ = india
        assert (df["country_code"] == "IN").all()

    def test_demo_rule_is_phc_in_five_states(self, india):
        """is_demo_facility must be exactly PHCs in the five demo states."""
        df, _ = india
        demo = df[df["is_demo_facility"]]
        assert len(demo) > 0, "No demo facilities flagged"
        assert set(demo["admin_l1"].unique()) <= DEMO_STATES
        assert (demo["facility_type"] == "phc").all()

        # And nothing matching the rule was missed.
        expected = df[
            df["admin_l1"].isin(DEMO_STATES) & (df["facility_type"] == "phc")
        ]
        assert len(demo) == len(expected)

    def test_demo_facilities_have_coordinates(self, india):
        df, _ = india
        demo = df[df["is_demo_facility"]]
        missing = demo[demo["latitude"].isna() | demo["longitude"].isna()]
        assert len(missing) == 0, \
            f"{len(missing)} demo facilities missing coordinates"

    def test_population_scales_with_facility_type(self, india):
        """A PHC must carry a larger catchment than a sub-centre in the same state."""
        df, _ = india
        tg = df[df["admin_l1"] == "Telangana"]
        phc = tg[tg["facility_type"] == "phc"]["population_served"].dropna()
        sub = tg[tg["facility_type"] == "sub_cen"]["population_served"].dropna()
        assert len(phc) and len(sub)
        assert phc.iloc[0] > sub.iloc[0]

    def test_population_gaps_are_only_delhi(self, india):
        """The only missing population values come from Delhi's 'NA' CHC average."""
        df, _ = india
        missing = df[df["population_served"].isna()]
        assert set(missing["admin_l1"].unique()) <= {"Delhi"}


class TestBrazilIngestion:
    """Validate Brazilian facility data parsing."""

    def test_row_count(self):
        from ingestion.load_brazil import load_brazil_facilities
        df = load_brazil_facilities(dry_run=True)
        assert len(df) >= 50_000, f"Expected 50k+ rows, got {len(df)}"

    def test_facility_id_format(self):
        from ingestion.load_brazil import load_brazil_facilities
        df = load_brazil_facilities(dry_run=True)
        assert df["facility_id"].str.startswith("BR-").all(), \
            "All Brazil facility IDs should start with 'BR-'"

    def test_demo_facilities_exist(self):
        from ingestion.load_brazil import load_brazil_facilities
        df = load_brazil_facilities(dry_run=True)
        demo = df[df["is_demo_facility"]]
        assert len(demo) > 0, "No demo facilities flagged"
        print(f"  Brazil demo facilities: {len(demo)}")

    def test_join_preserved_rows(self):
        """The coord join must not drop or duplicate rows."""
        from ingestion.load_brazil import load_brazil_facilities
        df = load_brazil_facilities(dry_run=True)
        # Row count is asserted inside the loader, but double-check uniqueness
        assert df["facility_id"].is_unique, "Duplicate facility IDs found"

    def test_country_code(self):
        from ingestion.load_brazil import load_brazil_facilities
        df = load_brazil_facilities(dry_run=True)
        assert (df["country_code"] == "BR").all()
