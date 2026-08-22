"""Block 2 — Local validation tests for facility ingestion.

Run: .venv\\Scripts\\python -m pytest tests/test_ingestion.py -v

These tests validate data parsing and transformation WITHOUT BigQuery.
They use --dry-run mode to avoid cloud calls.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIndiaIngestion:
    """Validate Indian facility data parsing."""

    def test_row_count(self):
        from ingestion.load_india import load_india_facilities
        df = load_india_facilities(dry_run=True)
        assert len(df) == 200_438, f"Expected 200,438 rows, got {len(df)}"

    def test_facility_id_format(self):
        from ingestion.load_india import load_india_facilities
        df = load_india_facilities(dry_run=True)
        assert df["facility_id"].str.startswith("IN-").all(), \
            "All India facility IDs should start with 'IN-'"

    def test_demo_facilities_exist(self):
        from ingestion.load_india import load_india_facilities
        df = load_india_facilities(dry_run=True)
        demo = df[df["is_demo_facility"]]
        assert len(demo) > 0, "No demo facilities flagged"
        print(f"  India demo facilities: {len(demo)}")

    def test_demo_facilities_have_coordinates(self):
        from ingestion.load_india import load_india_facilities
        df = load_india_facilities(dry_run=True)
        demo = df[df["is_demo_facility"]]
        null_coords = demo[demo["latitude"].isna() | demo["longitude"].isna()]
        assert len(null_coords) == 0, \
            f"{len(null_coords)} demo facilities missing coordinates"

    def test_country_code(self):
        from ingestion.load_india import load_india_facilities
        df = load_india_facilities(dry_run=True)
        assert (df["country_code"] == "IN").all()


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
