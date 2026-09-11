"""Demand ahead, at the scope the reader chose — and how good that forecast is.

## What this replaces

The Plan ahead page opened with a forecast chart for **one facility-item out of
2,794** — Ferrous Salt and Folic acid at Jahanuma PHC. On a page a state
official opens, the panel carrying the whole "forecast demand" requirement was
a single clinic's single medicine, and the horizon buttons changed the range of
a series nobody had chosen.

Meanwhile `pattern_exchange_eval` — 31,322 rows over 3,978 district-and-class
series across 116 districts — sat on no page at all, holding both of the things
that panel was supposed to show.

## The trade this makes, stated plainly

`demand_baseline` is scalar: one average per facility-item, no curve in it. So
an aggregated forecast has to come from the monthly evaluation table, whose
grain is **district x ATC class x month** rather than facility x item x day.

That is coarser resolution in exchange for far broader relevance, and it is a
real trade rather than a free win. A district officer asking "what is coming
for antimalarials here" is answered; "what is coming for Ferrous Salt at
Jahanuma on Thursday" is not.

## Why the accuracy panel matters more than the curve

Any forecast can be drawn. The question a reader should ask is whether to
believe it, and the evaluation table answers that in a way almost nothing else
does — by scoring four methods against the same actuals:

| Arm | wMAPE |
|---|---|
| Closest demographic twin, **different state** | **71.2%** |
| Flat, no seasonality | 19.4% |
| Closest demographic twin, **same state** | 16.4% |
| **Every district's shape, pooled** | **14.4%** |

Districts exchange seasonal **shape**, not data — a twelve-number monthly
multiplier per medicine class — and that takes error from 19.4% to 14.4%.

The ordering is the finding, and it is not the obvious one. `demo_out` is not a
bad match: it is the *closest demographic twin in all of India*, only required
to sit in a different state. Amravati's is Ranga Reddy in Telangana, 0.323 away
on profile — and borrowing its seasonal shape is nearly four times worse than
using no seasonality at all. Confine the same matching to one state and the
error falls from 71.2% to 16.4%.

Two districts can be demographically interchangeable and still have nothing to
say to each other about *when* demand arrives, because what drives the monthly
shape is monsoon and season, and those follow geography. That is why the arm
that wins is the pooled one: it takes the shape every district contributes to
rather than betting on a single lookalike.

An earlier version of this page labelled `demo_out` "a deliberately poor twin"
and put its donor districts under the heading "Who lends the seasonal shape",
which inverted the result — presenting the losing arm's donors as the source
of the gain.

wMAPE is computed as `SUM(|error|) / SUM(actual)` — weighted by volume, not the
mean of per-row ratios, which would let a tiny series with a large relative
error dominate a big one that was nearly right.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# Month arrives as a name, so the order has to be supplied — and it is the
# Indian financial year, April first, exactly as `build_pattern_exchange.py`
# defines it. Ordering these on the calendar year splits the evaluation window
# in half and draws a chart with a hole in the middle of it, which is a
# rendering artefact rather than anything in the data.
MONTH_ORDER = ("April", "May", "June", "July", "August", "September",
               "October", "November", "December", "January", "February",
               "March")

# April to June is the history each district is allowed to see. Everything
# after it is held out and predicted, which is why those three months are
# absent from the evaluation and why their absence is the design rather than a
# gap. Saying "8 months, not twelve" without saying why would read as missing
# data.
OBSERVED_MONTHS = ("April", "May", "June")

# Forecast error a district officer can act on. These are wMAPE bands, not
# significance tests, and they are deliberately blunt.
#
# They exist because the class dropdown offers 36 choices and the method does
# not work equally well across them. The pooled shape beats a flat average for
# Paracetamol by 6.1 points; for 18 of the 36 classes it does not beat a flat
# average at all, and 11 classes score above 40% error. Albendazole is the
# clearest case at 83.5%: it moves on National Deworming Day, and a monthly
# seasonal multiplier cannot fit a calendar campaign.
#
# A page that drew all 36 curves with the same confidence would be inviting a
# reader to order stock against a number that is wrong by more than itself. The
# panel says which band it is in instead.
RELIABLE_BELOW = 20.0      # tight enough to size an order against
DIRECTIONAL_BELOW = 40.0   # tells you the direction, not the quantity

# `demo_in` and `demo_out` are in-state and out-of-state, NOT similar and
# dissimilar. Both take the single closest district on demographic profile;
# they differ only in whether that district may sit in another state. Labelling
# `demo_out` "a deliberately poor twin" inverted the result — it is the best
# demographic match in all of India, and it is the worst forecast here.
METHODS = [
    ("pooled", "Every district's shape, pooled",
     "The average monthly shape across all 116 districts, rescaled to this "
     "district's own level. This is what the product uses."),
    ("demo_in", "Closest twin in the same state",
     "The most demographically similar district inside the same state."),
    ("flat", "No seasonality at all",
     "A flat monthly average from the district's own three observed months — "
     "what you get without exchanging anything."),
    ("demo_out", "Closest twin in another state",
     "The most demographically similar district in India, required to sit in "
     "a different state. The best match demography can find, and the worst "
     "forecast on this page."),
]

# `pattern_exchange_eval.actual` is the HMIS **demand driver** — outpatient
# attendance, confirmed malaria cases, institutional deliveries — not units of
# medicine. Classes that share a driver therefore hold byte-identical series:
# Paracetamol and Ibuprofen are both driven by allopathic OPD attendance, and
# all 928 rows of N02BE match M01AE exactly. Nine such groups cover 26 of the
# 36 classes, so a dropdown listing classes offered 36 entries that drew 19
# distinct curves, and a y-axis of 33.8 million "tablets" that was really a
# count of clinic visits.
#
# `items.units_per_driver_event` is the documented conversion: 1.2 paracetamol
# tablets per OPD visit, 0.35 ibuprofen, 28 antimalarial tablets per confirmed
# case (18 chloroquine + 10 primaquine — a vivax case gets both, which is why
# this sums across the items in a class rather than averaging them).
#
# Applying it does two things: the curve lands in the unit named on the axis,
# and the duplicate classes separate. It leaves every accuracy figure exactly
# where it was — wMAPE is SUM(|error|)/SUM(actual), so a constant multiplier
# cancels top and bottom. 19.4% to 14.4% is the same number before and after.
CLASS_UNITS = f"""
  SELECT SUBSTR(atc_code, 1, 5) AS atc_class,
         SUM(units_per_driver_event) AS units_per_event,
         ANY_VALUE(unit) AS unit,
         ANY_VALUE(demand_driver) AS driver,
         STRING_AGG(DISTINCT display_name, ', ' ORDER BY display_name) AS medicines
  FROM `{D}.items`
  WHERE atc_code IS NOT NULL AND demand_driver IS NOT NULL
    AND units_per_driver_event IS NOT NULL
  GROUP BY atc_class
"""


def _where(state: str, district: str, atc_class: str) -> str:
    parts = []
    if state:
        parts.append("state = @state")
    if district:
        # `district_key` is upper-cased here and mixed-case in the stock
        # tables, so the same district name reaches this table in two forms.
        parts.append("UPPER(district_key) = UPPER(@district)")
    if atc_class:
        parts.append("atc_class = @atc_class")
    return " AND ".join(parts) if parts else "TRUE"


def _params(state: str, district: str, atc_class: str) -> list:
    p = []
    if state:
        p.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        p.append(bigquery.ScalarQueryParameter("district", "STRING", district))
    if atc_class:
        p.append(
            bigquery.ScalarQueryParameter("atc_class", "STRING", atc_class))
    return p


def default_class(state: str = "", district: str = "") -> str:
    """The busiest medicine class in scope.

    A class must be chosen before a curve can be drawn: units are per class —
    tablets, vials, capsules, units — so summing across classes produces a
    number in no unit at all. The first version did exactly that and reported
    70 million of nothing.
    """
    # Ranked on medicine units, which is what the reader sees on the axis —
    # and, unlike driver events, cannot tie between two classes that share a
    # driver. Paracetamol and Ibuprofen drew the same 260,662,659 before the
    # conversion, so which one "was busiest" came down to whichever row
    # BigQuery happened to return first.
    rows = run_query(f"""
        SELECT p.atc_class
        FROM `{D}.pattern_exchange_eval` p
        JOIN ({CLASS_UNITS}) u USING (atc_class)
        WHERE {_where(state, district, "")}
        GROUP BY p.atc_class
        ORDER BY SUM(p.actual * u.units_per_event) DESC, p.atc_class
        LIMIT 1
    """, _params(state, district, ""),
        cache_key=f"outlook:default2:{state}:{district}", ttl=600)
    return rows[0]["atc_class"] if rows else ""


def outlook(state: str = "", district: str = "", atc_class: str = "") -> dict:
    """The demand curve for a scope, the accuracy behind it, and the donor."""
    # Never aggregate the curve across classes — see default_class.
    if not atc_class:
        atc_class = default_class(state, district)
    if not atc_class:
        # No class means no unit, and the query below binds @atc_class. Saying
        # so is the honest answer; drawing an unlabelled curve is not.
        return {"empty": True, "curve": [], "accuracy": [], "donors": [],
                "classes": [], "scope": {"state": state or "All India",
                                         "district": district, "atc_class": ""},
                "summary": {}}
    where = _where(state, district, atc_class)
    params = _params(state, district, atc_class)
    order = ", ".join(f"'{m}'" for m in MONTH_ORDER)

    rows = run_query(f"""
    SELECT
      -- The curve: actual against the forecast the product actually uses, and
      -- the flat line it beats, so the gain is visible rather than asserted.
      -- Every quantity is multiplied into the medicine's own unit before it
      -- leaves the query, so the axis label and the numbers under it agree.
      ARRAY(SELECT AS STRUCT month, sort_order, actual, pooled, flat
            FROM (
              SELECT month,
                     ARRAY_LENGTH(SPLIT(
                       SUBSTR('{",".join(MONTH_ORDER)}', 1,
                              STRPOS('{",".join(MONTH_ORDER)}', month) - 1),
                       ',')) AS sort_order,
                     ROUND(SUM(p.actual * u.units_per_event)) AS actual,
                     ROUND(SUM(p.pooled_forecast * u.units_per_event)) AS pooled,
                     ROUND(SUM(p.flat_forecast * u.units_per_event)) AS flat
              FROM `{D}.pattern_exchange_eval` p
              JOIN ({CLASS_UNITS}) u USING (atc_class)
              WHERE {where}
              GROUP BY month
              ORDER BY sort_order)) AS curve,

      -- The unit the curve is in, and the medicines it covers.
      (SELECT AS STRUCT unit, medicines, driver,
              ROUND(units_per_event, 2) AS units_per_event
       FROM ({CLASS_UNITS}) WHERE atc_class = @atc_class) AS meta,

      -- Four methods scored against the same actuals. Weighted by volume:
      -- the mean of per-row ratios would let a tiny series with a large
      -- relative error outvote a big one that was nearly right.
      (SELECT AS STRUCT
         ROUND(100 * SAFE_DIVIDE(SUM(flat_abs_error), SUM(actual)), 1) AS flat,
         ROUND(100 * SAFE_DIVIDE(SUM(demo_in_abs_error), SUM(actual)), 1) AS demo_in,
         ROUND(100 * SAFE_DIVIDE(SUM(demo_out_abs_error), SUM(actual)), 1) AS demo_out,
         ROUND(100 * SAFE_DIVIDE(SUM(pooled_abs_error), SUM(actual)), 1) AS pooled,
         COUNT(*) AS observations,
         COUNT(DISTINCT CONCAT(district_key, '|', atc_class)) AS series,
         COUNT(DISTINCT district_key) AS districts,
         SUM(actual) AS total_actual
       FROM `{D}.pattern_exchange_eval` WHERE {where}) AS accuracy,

      -- Who lent the shape. Named, because "shared predictive modelling
      -- across states" is a claim until a reader can see which two places.
      ARRAY(SELECT AS STRUCT donor_district, donor_state, receiver, receiver_state,
                             profile_distance, months
            FROM (
              SELECT donor_district, donor_state,
                     district_key AS receiver, state AS receiver_state,
                     ROUND(ANY_VALUE(profile_distance), 3) AS profile_distance,
                     COUNT(*) AS months
              FROM `{D}.pattern_exchange_eval`
              WHERE {where} AND donor_district IS NOT NULL
              GROUP BY donor_district, donor_state, receiver, receiver_state
              ORDER BY months DESC
              LIMIT 6)) AS donors,

      -- What can be selected at this scope, named by the medicines in the
      -- class. "M01AE" is a code; "Ibuprofen, Diclofenac" is the thing a
      -- district officer recognises.
      -- Named by the medicines and ordered on units, so the list the reader
      -- picks from is ordered the same way the default is chosen.
      ARRAY(SELECT AS STRUCT atc_class, medicines, unit, months, volume
            FROM (
              SELECT p.atc_class,
                     ANY_VALUE(u.medicines) AS medicines,
                     ANY_VALUE(u.unit) AS unit,
                     COUNT(*) AS months,
                     ROUND(SUM(p.actual * u.units_per_event)) AS volume
              FROM `{D}.pattern_exchange_eval` p
              JOIN ({CLASS_UNITS}) u USING (atc_class)
              WHERE {_where(state, district, "")}
              GROUP BY p.atc_class
              ORDER BY volume DESC, p.atc_class
              LIMIT 40)) AS classes
    """, params, cache_key=f"outlook:{state}:{district}:{atc_class}", ttl=600)

    if not rows:
        return {"empty": True}

    r = dict(rows[0])
    acc = dict(r["accuracy"]) if r.get("accuracy") else {}
    curve = [dict(x) for x in (r.get("curve") or [])]
    donors = [dict(x) for x in (r.get("donors") or [])]
    meta = dict(r["meta"]) if r.get("meta") else {}

    return {
        "empty": not curve,
        "curve": curve,
        "accuracy": _accuracy(acc),
        "donors": donors,
        "classes": [dict(x) for x in (r.get("classes") or [])],
        "scope": {"state": state or "All India", "district": district,
                  "atc_class": atc_class,
                  "unit": meta.get("unit") or "",
                  "medicines": meta.get("medicines") or "",
                  "driver": meta.get("driver") or "",
                  "units_per_event": meta.get("units_per_event")},
        "summary": _summary(acc, curve, donors, meta),
    }


def _reliability(pooled, gain, meta: dict) -> dict:
    """How far this particular curve can be trusted, said on the panel.

    Two separate questions, and the page used to answer neither. Whether
    exchanging a seasonal shape helped at all here — it does not for half the
    classes — and whether the resulting forecast is tight enough to order
    against, which is a different thing from being better than the alternative.
    A method can win its comparison and still be unusable.
    """
    if pooled is None:
        return {"level": "warn", "helps": None,
                "text": "This scope has no scored months, so there is no "
                        "error figure to stand behind the curve."}

    # Drivers are HMIS indicator names — "Vitamin A doses administered",
    # "Outpatient attendance - allopathic". Lower-casing them turns Vitamin A
    # into "vitamin a", so they are printed as the source writes them.
    driver = meta.get("driver") or ""

    if pooled >= DIRECTIONAL_BELOW:
        band = (f"At {pooled}% error this curve is too wide to order against. "
                + (f"Demand for it is driven by {driver}, which does not "
                   "repeat closely enough month to month for the exchange to "
                   "pin it down. " if driver else
                   "The monthly shape does not repeat closely enough for the "
                   "exchange to pin it down. ")
                + "Read it as a pattern, and size the order from the reorder "
                  "point instead.")
        level = "bad"
    elif pooled >= RELIABLE_BELOW:
        band = (f"At {pooled}% error this curve gives the direction and the "
                "shape reliably, but not the quantity. Use it to decide when "
                "to move stock, not how much.")
        level = "warn"
    else:
        band = (f"At {pooled}% error this curve is tight enough to size an "
                "order against.")
        level = "ok"

    if gain is None:
        helps = ""
    elif gain > 0:
        helps = (f" Exchanging a seasonal shape removes {gain} percentage "
                 "points of that error against a flat average.")
    else:
        # Reported rather than hidden: if the exchange does not help for a
        # class, the page has to say so, or the 19.4 -> 14.4 headline starts
        # standing in for classes it was never measured on.
        helps = (f" Exchanging a seasonal shape does not help for this class — "
                 f"a flat average scores {abs(gain)} points better. The gain "
                 "is real where the demand driver has a repeating monthly "
                 "shape, and absent where it does not.")
        level = "bad" if level == "ok" else level

    return {"level": level, "helps": gain is not None and gain > 0,
            "text": band + helps}


def _plural(unit: str) -> str:
    """"42,967,606 tablet" reads as a typo. Every unit in `items` is a plain
    English noun — tablet, vial, capsule, bottle, unit — so an "s" is enough
    and there is no irregular case to special-case."""
    return f"{unit}s" if unit and not unit.endswith("s") else unit


def _accuracy(acc: dict) -> list:
    return [
        {"key": key, "label": label, "note": note, "wmape": acc.get(key)}
        for key, label, note in METHODS
    ]


def _summary(acc: dict, curve: list, donors: list,
             meta: dict | None = None) -> dict:
    meta = meta or {}
    flat = acc.get("flat")
    pooled = acc.get("pooled")
    gain = (round(flat - pooled, 1)
            if flat is not None and pooled is not None else None)

    peak = max(curve, key=lambda c: c["actual"] or 0) if curve else None
    trough = min(curve, key=lambda c: c["actual"] or 0) if curve else None
    swing = (round((peak["actual"] or 0) / trough["actual"], 1)
             if peak and trough and (trough["actual"] or 0) > 0 else None)
    # The evaluation window is eight months, July to February — not a year.
    # A chart with four months missing looks like a rendering fault unless the
    # page says so, and "across the year" would be a claim about months that
    # were never scored.
    months = len(curve)

    donor = donors[0] if donors else None
    cross_state = sum(1 for d in donors
                      if d.get("donor_state") != d.get("receiver_state"))

    unit = meta.get("unit") or ""
    return {
        "reliability": _reliability(pooled, gain, meta),
        "unit": unit,
        # Named on the panel so the multiplier is inspectable rather than
        # buried: "1.2 tablets per outpatient visit" is a claim a district
        # pharmacist can argue with, which is the point of showing it.
        "units_per_event": meta.get("units_per_event"),
        "series": acc.get("series"),
        "districts": acc.get("districts"),
        "observations": acc.get("observations"),
        "flat": flat,
        "pooled": pooled,
        "gain": gain,
        # `series` counts district x class pairs, and the class is always
        # pinned by the time this runs — so at this scope it is a count of
        # districts. Calling it "district-and-class series" here would inflate
        # what the reader is being told was measured.
        # "falls from 83.4% to 83.5% — -0.1 percentage points" is what the
        # unconditional sentence produced for Albendazole. The direction has to
        # follow the arithmetic, because for 18 of the 36 classes it is the
        # other one.
        "headline": (
            "Not enough history at this scope." if gain is None else
            f"Forecast error falls from {flat}% to {pooled}% when districts "
            f"exchange seasonal shape — {gain} percentage points, measured "
            f"across {acc.get('districts') or 0:,} districts."
            if gain > 0 else
            f"Exchanging a seasonal shape does not pay for this class: "
            f"{pooled}% error against {flat}% for a flat average, measured "
            f"across {acc.get('districts') or 0:,} districts."),
        "months": months,
        "window": (f"{curve[0]['month']} to {curve[-1]['month']}"
                   if curve else ""),
        "observed": ", ".join(OBSERVED_MONTHS),
        "seasonality": (
            f"Demand peaks in {peak['month']} at "
            f"{peak['actual']:,.0f} {_plural(unit) or 'units'} and bottoms in "
            f"{trough['month']} — a {swing}x swing across the {months} months "
            "scored. A flat average is wrong in both directions."
            if swing and peak and trough else ""),
        "coverage_note": (
            f"Scored on {months} held-out months. Each district is allowed to "
            f"see only {', '.join(OBSERVED_MONTHS)} — three months, which is "
            "not enough to show a district its own seasonality — and every "
            "month after that is predicted and then compared with what the "
            "district actually reported."
            if months else ""),
        # The named district is the *cross-state* demographic twin — the
        # `demo_out` arm, which scores worst. Phrasing it as "borrows the shape
        # of" described the losing arm as though it were the method in use.
        "donor": (
            f"{donor['receiver'].title()}'s closest demographic twin in India "
            f"is {donor['donor_district']}, {donor['donor_state']} — "
            f"{donor['profile_distance']} away on profile. Borrowing its "
            "seasonal shape is the worst-scoring arm here; the shape the "
            "product uses is pooled across every district instead."
            if donor else ""),
        "cross_state": cross_state,
    }
