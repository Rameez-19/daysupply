"""Per-facility staffing establishment, derived from state-level statistics.

**State-level source, per-facility output — this is an assumption, exactly like
`population_served`.** Rural Health Statistics publishes sanctioned and
in-position counts per state, not per facility. Sanctioned posts per facility
are that state's total divided by the number of facilities the posts belong to.

**The denominator differs by cadre and getting it wrong overstates staffing.**
`allo-doc-PHCS` and the two `assistant-*-PHCS` files count PHC posts and divide
by PHCs. `nursing-staff-PHCS-CHCS` and `pharmacists-PHCS-CHCS` cover PHCs *and*
CHCs, so they divide by both — dividing those by PHCs alone would overstate
per-PHC nursing and pharmacist strength by roughly 18%.

**Vacancy is real and it is the ceiling on attendance.** A post that is vacant
cannot be attended, so `expected_in_position` is the sanctioned establishment
less that state and cadre's actual vacancy rate. Where a state reports more
staff in post than sanctioned posts — contractual NHM staff over and above
sanctioned strength, which five states do for nursing — the ratio is kept above
1.0 rather than clipped, because that is what the source says.

**Nursing has a second, independent requirement.** One nurse per six beds in
the inpatient department. This is an **Indian Nursing Council regulation**,
which CHC IPHS 2022 quotes at page 60 and tabulates at page 118 — IPHS cites it
rather than originating it, and it should be attributed to the INC.

That gives a *required* nursing strength derived from bed capacity, which is a
different quantity from the *sanctioned* strength derived from staffing
statistics. Both are carried, and the gap between
them is itself a finding.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
STAFFING = f"`{PROJECT}.{DATASET}.staffing`"
FACILITY_STAFFING = f"`{PROJECT}.{DATASET}.facility_staffing`"

# The facility master and the staffing files spell some states differently.
# Written against RHS 2021-22. Its spellings moved from 2017's: "A & N Island"
# became "Andaman & Nicobar Islands", and Dadra & Nagar Haveli and Daman & Diu
# are one UT since 2020, so the facility master's two names both map to the
# merged row. Left unmapped, those 45 centres silently got no establishment.
STATE_ALIASES = {
    "A & N Islands": "Andaman & Nicobar Islands",
    "Andhra Pradesh Old": "Andhra Pradesh",
    "Dadra & Nagar Haveli": "Dadra & Nagar Haveli and Daman & Diu",
    "Daman & Diu": "Dadra & Nagar Haveli and Daman & Diu",
}

BUILD = f"""
CREATE OR REPLACE TABLE {FACILITY_STAFFING}
CLUSTER BY facility_id
AS
WITH aliased AS (
  SELECT
    f.*,
    CASE f.admin_l1
      {' '.join(f"WHEN '{k}' THEN '{v}'" for k, v in STATE_ALIASES.items())}
      ELSE f.admin_l1
    END AS staffing_state
  FROM {FACILITIES} f
  WHERE f.country_code = 'IN' AND f.facility_type IN ('phc', 'chc')
),
-- The denominator each cadre's posts are spread across.
denominators AS (
  SELECT
    staffing_state AS state,
    COUNTIF(facility_type = 'phc')                        AS phc_count,
    COUNTIF(facility_type IN ('phc', 'chc'))              AS phc_chc_count
  FROM aliased
  GROUP BY state
),
per_facility AS (
  SELECT
    s.state,
    s.cadre,
    s.applies_to_facility_types,
    s.sanctioned,
    s.in_position,
    s.vacancy_rate,
    -- PHC-only cadres divide by PHCs; PHC+CHC cadres divide by both.
    IF(ARRAY_LENGTH(s.applies_to_facility_types) = 1,
       d.phc_count, d.phc_chc_count) AS denominator,
    SAFE_DIVIDE(s.sanctioned,
      IF(ARRAY_LENGTH(s.applies_to_facility_types) = 1,
         d.phc_count, d.phc_chc_count)) AS sanctioned_per_facility,
    -- What the source says is actually in post, not what is authorised.
    SAFE_DIVIDE(s.in_position,
      IF(ARRAY_LENGTH(s.applies_to_facility_types) = 1,
         d.phc_count, d.phc_chc_count)) AS in_position_per_facility
  FROM {STAFFING} s
  JOIN denominators d ON d.state = s.state
)
SELECT
  f.facility_id,
  f.name          AS facility_name,
  f.admin_l1      AS state,
  f.admin_l2      AS district,
  f.facility_type,
  f.bed_capacity,
  p.cadre,
  p.denominator   AS facilities_sharing_these_posts,
  ROUND(p.sanctioned_per_facility, 3)  AS sanctioned_per_facility,
  ROUND(p.in_position_per_facility, 3) AS in_position_per_facility,
  p.vacancy_rate,
  -- Establishment rounded to whole posts: a facility cannot hold 2.4 doctors.
  GREATEST(1, CAST(ROUND(p.sanctioned_per_facility) AS INT64))
    AS sanctioned_posts,
  -- Rounding the two ratios independently can invert their order — 1.4
  -- sanctioned rounds to 1 while 1.6 in position rounds to 2 — which would
  -- claim more staff in post than posts exist. Cap at the establishment,
  -- except where the source genuinely reports more staff than sanctioned
  -- posts (contractual NHM staff, which five states report for nursing).
  IF(p.in_position > p.sanctioned,
     GREATEST(0, CAST(ROUND(p.in_position_per_facility) AS INT64)),
     LEAST(
       GREATEST(1, CAST(ROUND(p.sanctioned_per_facility) AS INT64)),
       GREATEST(0, CAST(ROUND(p.in_position_per_facility) AS INT64))))
    AS expected_in_position,
  -- Nursing only: the requirement derived from bed capacity. The 1:6
  -- ratio is an Indian Nursing Council regulation that IPHS cites; it is
  -- not an IPHS-originated norm.
  IF(p.cadre = 'Nursing staff', f.nurses_required, NULL)
    AS nurses_required_by_beds
FROM aliased f
JOIN per_facility p
  ON p.state = f.staffing_state
 AND f.facility_type IN UNNEST(p.applies_to_facility_types)
WHERE f.is_forecast_facility
"""

VERIFY = f"""
SELECT
  cadre,
  COUNT(*)                                    AS rows_out,
  COUNT(DISTINCT facility_id)                 AS facilities,
  ROUND(AVG(sanctioned_per_facility), 2)      AS avg_sanctioned,
  ROUND(AVG(vacancy_rate) * 100, 1)           AS avg_vacancy_pct,
  SUM(sanctioned_posts)                       AS total_posts,
  SUM(expected_in_position)                   AS total_in_post
FROM {FACILITY_STAFFING}
GROUP BY cadre ORDER BY cadre
"""


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)

    print("Building facility_staffing ...")
    client.query(BUILD).result()

    print(f"\n  {'cadre':28s} {'facs':>5} {'avg sanc':>9} {'vac%':>6} "
          f"{'posts':>6} {'in post':>8}")
    total_facilities = 0
    for r in client.query(VERIFY).result():
        total_facilities = max(total_facilities, r.facilities)
        print(f"  {r.cadre:28s} {r.facilities:>5} {r.avg_sanctioned:>9} "
              f"{r.avg_vacancy_pct:>6} {r.total_posts:>6} {r.total_in_post:>8}")

    if total_facilities == 0:
        raise SystemExit("facility_staffing is empty")

    # The two requirements for nursing are computed from different sources and
    # do not have to agree. Where they disagree, that is a real finding.
    gap = next(iter(client.query(f"""
        SELECT
          COUNT(*) AS facilities,
          ROUND(AVG(sanctioned_posts), 2)          AS avg_sanctioned,
          ROUND(AVG(nurses_required_by_beds), 2)   AS avg_required_by_beds,
          COUNTIF(sanctioned_posts < nurses_required_by_beds) AS under_norm
        FROM {FACILITY_STAFFING}
        WHERE cadre = 'Nursing staff' AND nurses_required_by_beds IS NOT NULL
    """).result()))
    print(f"\n  Nursing, two independent requirements:")
    print(f"    sanctioned establishment (RHS 2021-22):  "
          f"{gap.avg_sanctioned} per facility")
    print(f"    required by beds (INC 1:6, cited by IPHS): "
          f"{gap.avg_required_by_beds} per facility")
    print(f"    facilities sanctioned below the bed-based norm: "
          f"{gap.under_norm} of {gap.facilities}")

    print("\nOK — establishment derived. State-level source, per-facility "
          "output: an assumption, recorded as one.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
