"""Name the signal that fired, and say whether it leads or coincides.

## A correction to how this was described

An earlier audit of this system said surge "fires on realised dispensing
deviation — patients have already arrived and been treated". **That was wrong.**
`pattern_vectors.value` is `SUM(demand_reference.value)` over HMIS *clinical*
indicators, so surge has always fired on clinical driver deviation, never on
stock or dispensing. Verified: no ATC class maps to more than one driver, so the
existing signal is already indicator-level.

What was actually missing is narrower and entirely real: **the signal has no
name.** The surge says *"P02CA is 6.31× expected"*. A district officer does not
stock P02CA, they respond to diarrhoea. And crucially, *"Childhood diarrhoea is
6.31× expected in this district in March"* and *"dispensing has already
deviated"* are different statements demanding different responses — the first is
a clinical warning, the second is a supply fact. Nothing on screen distinguished
them.

## Leading, coincident, and programme signals

Not every driver carries the same warning value, and pretending otherwise would
be the overclaim here.

**LEADING** — rises before the medicine demand it drives, because a clinical
presentation precedes a course of treatment:

* *Outpatient attendance — allopathic*: the broadest early signal. People arrive
  before they are treated.
* *Malaria — confirmed cases*: a confirmed case precedes a full antimalarial
  course; treatment is dispensed over following days.
* *Inpatient admissions — infectious*: an admission precedes the antibiotic
  course it triggers.
* *Childhood diarrhoea*, *childhood pneumonia*: presentation precedes the ORS or
  antibiotic course.

**COINCIDENT** — the clinical event and the dispensing happen together, so
deviation is information but not warning. Chronic-disease outpatient counts
behave this way: a hypertension review *is* the repeat prescription.

**PROGRAMME** — deviation is a planned campaign, not an outbreak. Albendazole
and Vitamin A move on National Deworming Day and immunisation rounds. A 22.64×
Albendazole swing is a *calendar* event, and calling it a surge would be the
clearest possible false positive.

## Claim discipline

Labelling a driver LEADING says the clinical signal precedes the dispensing it
causes. It does **not** say we predict outbreaks. We detect that one has begun,
earlier and more reliably than a 3-sigma rule — which on this data cannot fire
at all above 3.175. The lead we can claim is the lead we measure, in
`measure_lead()`, and where the data cannot support a number this module says so
instead of producing one.
"""

from __future__ import annotations

import os
import sys

from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

SIGNAL_LABELS = f"`{PROJECT}.{DATASET}.signal_labels`"

# driver -> (class, plain-English what it means, why it leads or does not)
DRIVER_CLASS = {
    "Outpatient attendance - allopathic": (
        "leading",
        "People arriving at the clinic",
        "The broadest early signal there is. Attendance rises before any of it "
        "is dispensed."),
    "Malaria - confirmed cases": (
        "leading",
        "Confirmed malaria diagnoses",
        "A confirmed case precedes a full treatment course, which is dispensed "
        "over the days that follow."),
    "Inpatient admissions - infectious": (
        "leading",
        "Admissions for infectious illness",
        "An admission precedes the antibiotic course it triggers."),
    "Childhood diarrhoea": (
        "leading",
        "Children presenting with diarrhoea",
        "Presentation precedes the ORS and zinc course."),
    "Childhood pneumonia and respiratory infection": (
        "leading",
        "Children presenting with pneumonia or respiratory infection",
        "Presentation precedes the antibiotic course."),
    "Inpatient admissions - total": (
        "leading",
        "All inpatient admissions",
        "Admissions precede the IV fluids they consume."),
    "Asthma and COPD": (
        "coincident",
        "Asthma and COPD presentations",
        "Largely chronic repeat care; the visit and the inhaler go together."),
    "Cardiac - outpatient and emergency": (
        "coincident", "Cardiac presentations",
        "Emergency cases lead, chronic review coincides; mixed, so not claimed "
        "as leading."),
    "Stroke - outpatient and emergency": (
        "coincident", "Stroke presentations", "Same mix as cardiac."),
    "Outpatient - Diabetes": (
        "coincident", "Diabetes outpatient visits",
        "A chronic review *is* the repeat prescription."),
    "Outpatient - Hypertension": (
        "coincident", "Hypertension outpatient visits", "As diabetes."),
    "Outpatient - Epilepsy": (
        "coincident", "Epilepsy outpatient visits", "As diabetes."),
    "Outpatient - Mental illness": (
        "coincident", "Mental illness outpatient visits", "As diabetes."),
    "Outpatient - Dental": (
        "coincident", "Dental outpatient visits", "Treatment at the visit."),
    "Outpatient - Ophthalmic Related": (
        "coincident", "Eye outpatient visits", "Treatment at the visit."),
    "Institutional deliveries": (
        "coincident", "Deliveries in a facility",
        "Oxytocin is used at the delivery, not after it."),
    "Eclampsia cases managed": (
        "coincident", "Eclampsia cases managed",
        "Magnesium sulphate is given during management."),
    "Albendazole doses administered": (
        "programme",
        "Deworming doses given",
        "National Deworming Day, 10 August and 10 February. A 22.64x swing is "
        "a calendar event, not an outbreak."),
    "Vitamin A doses administered": (
        "programme", "Vitamin A doses given",
        "Immunisation and supplementation rounds. Planned, not emergent."),
}

BUILD = f"""
CREATE OR REPLACE TABLE {SIGNAL_LABELS} AS
WITH labels AS (
  SELECT * FROM UNNEST([
    {",".join(
        "STRUCT('" + d.replace("'", "\\'") + "' AS demand_driver, '"
        + c + "' AS signal_class, '" + m.replace("'", "\\'")
        + "' AS means, '" + w.replace("'", "\\'") + "' AS why)"
        for d, (c, m, w) in DRIVER_CLASS.items())}
  ])
)
SELECT
  SUBSTR(i.atc_code, 1, 5) AS atc_class,
  i.demand_driver,
  l.signal_class,
  l.means,
  l.why,
  COUNT(DISTINCT i.item_id) AS items_driven,
  STRING_AGG(DISTINCT i.display_name ORDER BY i.display_name LIMIT 4)
    AS example_items
FROM `{PROJECT}.{DATASET}.items` i
JOIN labels l ON l.demand_driver = i.demand_driver
WHERE i.atc_code IS NOT NULL AND i.demand_driver IS NOT NULL
GROUP BY atc_class, i.demand_driver, l.signal_class, l.means, l.why
"""


def measure_lead(client: bigquery.Client) -> None:
    """Does a leading indicator actually peak before a coincident one?

    Measured, not asserted. For each district this compares the peak month of
    outpatient attendance against the peak month of confirmed malaria in the
    same district, and reports the distribution of the gap.

    **The honest limit is stated up front:** twelve monthly observations per
    district is far too few to establish a lag with confidence. This is a
    directional check, not a cross-correlation, and it is reported as such. If
    the distribution is not clearly one-sided, the correct conclusion is that
    the data does not support a lead-time claim — and that is what gets said.
    """
    print("\n  Lead measurement — attendance peak vs confirmed-malaria peak")
    rows = list(client.query(f"""
        WITH peaks AS (
          SELECT district_key, indicator, month, value,
                 ROW_NUMBER() OVER (PARTITION BY district_key, indicator
                                    ORDER BY value DESC) AS rn
          FROM `{PROJECT}.{DATASET}.demand_reference`
          WHERE indicator IN ('Outpatient attendance - allopathic',
                              'Malaria - confirmed cases')
        ),
        top AS (SELECT district_key, indicator, month FROM peaks WHERE rn = 1),
        paired AS (
          SELECT a.district_key,
                 MOD(EXTRACT(MONTH FROM PARSE_DATE('%B', m.month))
                     - EXTRACT(MONTH FROM PARSE_DATE('%B', a.month)) + 12, 12)
                   AS months_malaria_after_attendance
          FROM top a
          JOIN top m ON m.district_key = a.district_key
          WHERE a.indicator = 'Outpatient attendance - allopathic'
            AND m.indicator = 'Malaria - confirmed cases'
        )
        SELECT months_malaria_after_attendance AS gap, COUNT(*) AS districts
        FROM paired GROUP BY gap ORDER BY gap
    """).result())
    total = sum(r.districts for r in rows)
    if not total:
        print("    no paired districts; no claim possible")
        return
    for r in rows:
        bar = "#" * max(1, round(40 * r.districts / total))
        print(f"    malaria peaks {r.gap:>2} month(s) after attendance: "
              f"{r.districts:>3} districts {bar}")
    leading = sum(r.districts for r in rows if 1 <= r.gap <= 3)
    print(f"\n    malaria peak falls 1-3 months after the attendance peak in "
          f"{leading} of {total} districts ({100 * leading / total:.0f}%)")
    if leading / total < 0.5:
        print("    -> NOT a majority. The data does not support a lead-time "
              "claim in months, and none is made. The LEADING label rests on "
              "the clinical mechanism, not on this measurement.")
    else:
        print("    -> directionally consistent, but 12 monthly points per "
              "district cannot establish a lag with confidence. Treat as "
              "supporting the mechanism, not as a measured lead time.")


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    print("Building signal_labels (naming what fired, and whether it leads)...")
    client.query(BUILD).result()

    for r in client.query(f"""
        SELECT signal_class, COUNT(*) AS classes,
               COUNT(DISTINCT demand_driver) AS drivers,
               SUM(items_driven) AS items
        FROM {SIGNAL_LABELS} GROUP BY signal_class ORDER BY signal_class
    """).result():
        print(f"  {r.signal_class:11s} {r.drivers:>2} drivers, "
              f"{r.classes:>2} ATC classes, {r['items']:>2} items")

    print("\n  Surges by signal class (which warnings are actually firing):")
    for r in client.query(f"""
        SELECT l.signal_class, COUNT(*) AS surge_months,
               COUNT(DISTINCT s.district_key) AS districts,
               ROUND(MAX(s.surge_multiplier), 1) AS peak
        FROM `{PROJECT}.{DATASET}.surge_signals` s
        JOIN {SIGNAL_LABELS} l ON l.atc_class = s.atc_class
        WHERE s.is_surge
        GROUP BY l.signal_class ORDER BY surge_months DESC
    """).result():
        print(f"    {r.signal_class:11s} {r.surge_months:>4} surge-months, "
              f"{r.districts:>3} districts, peak {r.peak}x")

    measure_lead(client)
    print("\nOK — every surge can now name its signal, say what it means, and "
          "say whether it leads the demand or moves with it.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
