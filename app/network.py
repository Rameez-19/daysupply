"""The Network view — who is doing well, who needs help, and who is being
judged unfairly by geography.

## Why this page exists at all

Today v2 grades **one scope**. This ranks and compares **across scopes**, which
is the job nothing else in the product does and the one a federated health
system actually runs on: you do not manage 116 districts by looking at them one
at a time, you manage them by knowing which are falling behind.

The page it replaces was a resource switcher, a stock-health doughnut and a
critical-shortages bar — all three of which Today v2 now does better. Two pages
answering the same question is worse than one, so this one changed job rather
than being kept for the nav slot.

## Four things, in the order the argument runs

1. **A league table.** Districts ranked on the measure that matters for the
   resource being viewed. This is the page's spine — the thing somebody
   screenshots and sends to a state team.
2. **The distribution, not the average.** A national 78.6% could be every
   district at 78%, or half at 100% and half at 55%. Those need completely
   different responses and the mean hides which one you have.
3. **Best against worst, named.** A gap stated as two real places lands harder
   than any distribution: same medicines, same model, tens of points apart.
4. **Structural disadvantage.** Some districts are hard to supply *by
   geography*, and a league table that does not say so blames them for their
   own road network.

## The geography finding, stated honestly

Mean availability falls monotonically as the distance from the supply hub
rises — 83.9% under nine days of lead time, 75.5% at 9-12, 64.7% at 12-15,
56.4% past 15. That is a 27-point spread and it is a real effect.

It is also **not the whole story**: the correlation between district
availability and lead time is **-0.296**, which explains under a tenth of the
variance. So lead time is *a* reason a district is behind, not *the* reason,
and the page says so in those words. Presenting it as the explanation would be
a more comfortable story and a false one — it would hand every badly run
district a ready excuse.

The longest band holds only two districts, which is too few to lean on. The
count travels with every band so a reader can see that for themselves.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# Same floor Today v2 uses. A district with three tracked lines reads 100% or
# 0% on a single bad one, and a league table sorted on that puts noise at both
# ends — which is the one thing a ranking must never do.
MIN_FOR_RATE = 8

# How many rows each end of the table shows.
TOP_N = 10


def _geo(state: str) -> str:
    return "state = @state" if state else "TRUE"


def _params(state: str) -> list:
    return ([bigquery.ScalarQueryParameter("state", "STRING", state)]
            if state else [])


MEDICINE_LABELS = {
    "title": "Which districts are best and worst supplied?",
    "score": "Medicines available",
    "score_short": "Available",
    "secondary": "Life-saving available",
    "secondary_short": "Life-saving",
    "secondary_is_pct": True,
    "failure": "Completely out",
    "failure_short": "Out",
    "failure_is_pct": True,
    "unit": "%",
    "distribution": {
        "title": "Is it the same everywhere, or a few bad places?",
        "note": "Districts grouped by how much of their medicine list is at a "
                "safe level. An average cannot tell you whether a problem is "
                "shared or concentrated.",
    },
    "structure": {
        "title": "How much of the gap is distance?",
        "note": "Districts grouped by how long resupply takes to reach them. "
                "Availability falls steadily as that gets longer — but this "
                "explains under a tenth of the difference between districts, "
                "so distance is one reason a district is behind, not the "
                "reason.",
    },
    "extremes": {
        "title": "The two ends of the same network",
        "note": "Same medicine list, same model, same rules.",
    },
}

BED_LABELS = {
    "title": "Which districts have the most bed pressure?",
    "score": "Beds free",
    "score_short": "Free",
    "secondary": "Centres at capacity",
    "secondary_short": "At capacity",
    "secondary_is_pct": True,
    "failure": "Patients turned away",
    "failure_short": "Turned away",
    # A headcount, not a share — the one failure column that is not a rate.
    "failure_is_pct": False,
    "unit": "%",
    "distribution": {
        "title": "Is the pressure shared or concentrated?",
        "note": "Districts grouped by how much of their bed capacity is free "
                "on average.",
    },
    "structure": {},
    "extremes": {
        "title": "The two ends of the same network",
        "note": "Same bed norm, same measure.",
    },
}

STAFF_LABELS = {
    "title": "Which states are best and worst staffed?",
    "grain_note": "Compared by state, not by district. Vacancy is published by "
                  "Rural Health Statistics at state level, so every district "
                  "in a state carries the same figure — ranking districts on "
                  "it would name places the number says nothing about.",
    "score": "Posts filled",
    "score_short": "Filled",
    "secondary": "Doctors in post",
    "secondary_short": "Doctors",
    "secondary_is_pct": True,
    "failure": "Roles with a gap",
    "failure_short": "Gaps",
    "failure_is_pct": True,
    "unit": "%",
    "distribution": {
        "title": "Is the shortage shared or concentrated?",
        "note": "States grouped by how many of their sanctioned posts are "
                "filled.",
    },
    "structure": {},
    "extremes": {
        "title": "The two ends of the same network",
        "note": "Same sanctioned establishment, same measure.",
    },
}


# Same measure, one zoom level in: roles within a state rather than states.
STAFF_CADRE_LABELS = {
    "title": "Which roles are hardest to fill here?",
    "grain_note": "Compared by role, not by district. Vacancy is published at "
                  "state level, so it is identical in every district of this "
                  "state — but it differs sharply between roles, which is the "
                  "comparison that can actually be acted on.",
    "score": "Posts filled",
    "score_short": "Filled",
    "secondary": "Sanctioned posts",
    "secondary_short": "Posts",
    "secondary_is_pct": False,
    "failure": "Centres with a gap",
    "failure_short": "Gaps",
    "failure_is_pct": True,
    "unit": "%",
    "distribution": {
        "title": "Is the shortage shared or concentrated?",
        "note": "Roles grouped by how many of their sanctioned posts are "
                "filled.",
    },
    "structure": {},
    "extremes": {
        "title": "The two ends of the same establishment",
        "note": "Same state, same sanctioned list — different roles.",
    },
}


def _finish(rows: list, labels: dict, structure: list, state: str) -> dict:
    """Shared tail: order, distribution, extremes, summary."""
    if not rows:
        return {"empty": True, "labels": labels, "rows": [],
                "distribution": [], "structure": [], "extremes": None,
                "summary": {}, "scope": state or "All India"}

    rows = sorted(rows, key=lambda r: (r["score"] is None, r["score"]))
    scores = [r["score"] for r in rows if r["score"] is not None]

    # Buckets are fixed, not quantiles: a quantile always produces a bottom
    # fifth even when every district is healthy, which would invent a crisis.
    bands = [(0, 60, "Under 60%"), (60, 75, "60 to 75%"),
             (75, 90, "75 to 90%"), (90, 101, "90% or better")]
    distribution = [
        {"bucket": name, "sort_order": i + 1,
         "n": sum(1 for s in scores if lo <= s < hi)}
        for i, (lo, hi, name) in enumerate(bands)
    ]

    worst, best = rows[0], rows[-1]
    median = (sorted(scores)[len(scores) // 2] if scores else None)
    # The median as a PLACE, not just a value. Two extremes alone cannot say
    # whether the worst is an outlier or whether the middle of the pack is
    # struggling too, and those need different responses: one district to
    # rescue, or a system to fix.
    typical = rows[len(rows) // 2]

    return {
        "empty": False,
        "labels": labels,
        "scope": state or "All India",
        # Both ends, because a league table that only shows failures teaches
        # nobody what good looks like.
        "rows": rows[:TOP_N] + rows[-TOP_N:] if len(rows) > TOP_N * 2 else rows,
        "worst": rows[:TOP_N],
        "best": list(reversed(rows[-TOP_N:])),
        "distribution": distribution,
        "structure": structure,
        "extremes": {
            "best": best, "worst": worst,
            "typical": typical,
            "above_typical": sum(1 for x in scores
                                 if typical["score"] is not None
                                 and x > typical["score"]),
            "below_typical": sum(1 for x in scores
                                 if typical["score"] is not None
                                 and x < typical["score"]),
            "gap": (round(best["score"] - worst["score"], 1)
                    if best["score"] is not None
                    and worst["score"] is not None else None),
        },
        "summary": {
            "districts": len(rows),
            "median": median,
            "lowest": min(scores) if scores else None,
            "highest": max(scores) if scores else None,
        },
    }


def medicine_comparison(state: str = "", vital_only: bool = False) -> dict:
    where = _geo(state) + (" AND ven_class = 'Vital'" if vital_only else "")
    rows = run_query(f"""
    WITH d AS (
      SELECT district, ANY_VALUE(state) AS state,
             COUNT(*) AS tracked,
             COUNT(DISTINCT facility_id) AS centres,
             ROUND(100 * SAFE_DIVIDE(COUNTIF(NOT needs_reorder), COUNT(*)), 1) AS score,
             ROUND(100 * SAFE_DIVIDE(
               COUNTIF(ven_class = 'Vital' AND NOT needs_reorder),
               NULLIF(COUNTIF(ven_class = 'Vital'), 0)), 1) AS secondary,
             ROUND(100 * SAFE_DIVIDE(COUNTIF(status = 'stocked_out'), COUNT(*)), 1) AS failure,
             ROUND(AVG(lead_time_days), 1) AS lead_days,
             ROUND(AVG(distance_to_hq_km), 0) AS km
      FROM `{D}.reorder_status`
      WHERE {where}
      GROUP BY district
      HAVING tracked >= {MIN_FOR_RATE})
    SELECT * FROM d ORDER BY score
    """, _params(state), cache_key=f"net:med:{state}:{int(vital_only)}", ttl=300)

    structure = run_query(f"""
    WITH d AS (
      SELECT district, COUNT(*) AS tracked,
             100 * SAFE_DIVIDE(COUNTIF(NOT needs_reorder), COUNT(*)) AS score,
             AVG(lead_time_days) AS lead_days,
             AVG(distance_to_hq_km) AS km
      FROM `{D}.reorder_status`
      WHERE {where}
      GROUP BY district
      HAVING tracked >= {MIN_FOR_RATE})
    SELECT band, sort_order, COUNT(*) AS districts,
           ROUND(AVG(score), 1) AS mean_score,
           ROUND(AVG(lead_days), 1) AS mean_lead,
           ROUND(AVG(km), 0) AS mean_km
    FROM (
      SELECT *,
        CASE WHEN lead_days < 9 THEN 'Under 9 days'
             WHEN lead_days < 12 THEN '9 to 12 days'
             WHEN lead_days < 15 THEN '12 to 15 days'
             ELSE '15 days or more' END AS band,
        CASE WHEN lead_days < 9 THEN 1
             WHEN lead_days < 12 THEN 2
             WHEN lead_days < 15 THEN 3 ELSE 4 END AS sort_order
      FROM d)
    GROUP BY band, sort_order ORDER BY sort_order
    """, _params(state), cache_key=f"net:medstruct:{state}:{int(vital_only)}",
        ttl=300)

    out = _finish([dict(r) for r in rows], MEDICINE_LABELS,
                  [dict(r) for r in structure], state)
    out["resource"] = "medicine"
    out["grain"] = "district"
    return out


def bed_comparison(state: str = "") -> dict:
    where = _geo(state)
    rows = run_query(f"""
    SELECT district, ANY_VALUE(state) AS state,
           COUNT(*) AS tracked, COUNT(*) AS centres,
           ROUND(100 * SAFE_DIVIDE(SUM(free_beds), SUM(bed_capacity)), 1) AS score,
           ROUND(100 * SAFE_DIVIDE(COUNTIF(status = 'over_capacity'), COUNT(*)), 1) AS secondary,
           SUM(turned_away) AS failure,
           CAST(NULL AS FLOAT64) AS lead_days,
           CAST(NULL AS FLOAT64) AS km
    FROM `{D}.bed_status`
    WHERE {where}
    GROUP BY district
    ORDER BY score
    """, _params(state), cache_key=f"net:bed:{state}", ttl=300)

    out = _finish([dict(r) for r in rows], BED_LABELS, [], state)
    out["resource"] = "bed"
    out["grain"] = "district"
    return out


def staff_comparison(state: str = "") -> dict:
    """Staffing, compared at the grain the data actually has.

    **No state chosen — compare states.** Vacancy comes from Rural Health
    Statistics 2017, which publishes it at state level. Applied down to
    facilities it is the same number everywhere within a state: all 33
    Rajasthan districts read 59.3%, all 27 Assam districts read 96.3% —
    measured, exactly one distinct value per state. A district league table
    built on that would rank 33 districts as jointly worst and invite a reader
    to blame Jaisalmer for a Rajasthan statistic.

    **A state chosen — compare the roles inside it.** Narrowing a
    state-grain comparison to one state leaves one row ranked against itself:
    best, worst and typical all read "Assam 96.3%", which is not a comparison
    at all. Cadre is the grain that does vary inside a state, and it varies a
    lot — Rajasthan runs from 28.6% of male health assistant posts filled to
    89.4% of doctor posts. It is also the more useful question at that zoom:
    "which roles can we not fill here" is a recruitment decision, where "how
    does Rajasthan compare with Rajasthan" is nothing.

    Attendance is deliberately not used at either grain. It is modelled and the
    model is broken for whole states — all 55 of Delhi's rows read zero staff
    present across 30 reported days.
    """
    if not state:
        rows = run_query(f"""
        SELECT t.state AS district, t.state AS state,
               COUNT(*) AS tracked,
               COUNT(DISTINCT t.facility_id) AS centres,
               ROUND(100 - 100 * AVG(t.vacancy_rate), 1) AS score,
               ROUND(100 - 100 * AVG(IF(t.cadre = 'Doctor (allopathic)',
                                        t.vacancy_rate, NULL)), 1) AS secondary,
               ROUND(100 * SAFE_DIVIDE(COUNTIF(t.days_none_present > 0),
                                       COUNT(*)), 1) AS failure,
               CAST(NULL AS FLOAT64) AS lead_days,
               CAST(NULL AS FLOAT64) AS km
        FROM `{D}.staff_status` t
        GROUP BY t.state
        ORDER BY score
        """, [], cache_key="net:staff:all", ttl=300)
        out = _finish([dict(r) for r in rows], STAFF_LABELS, [], state)
        out["resource"] = "personnel"
        out["grain"] = "state"
        return out

    rows = run_query(f"""
    SELECT t.cadre AS district, CAST(NULL AS STRING) AS state,
           COUNT(*) AS tracked,
           COUNT(DISTINCT t.facility_id) AS centres,
           ROUND(100 - 100 * AVG(t.vacancy_rate), 1) AS score,
           -- A headcount, not a share: how big the role is here, so a 28%
           -- fill rate on 66 posts is not read like one on 4.
           SUM(t.sanctioned_posts) AS secondary,
           ROUND(100 * SAFE_DIVIDE(COUNTIF(t.days_none_present > 0),
                                   COUNT(*)), 1) AS failure,
           CAST(NULL AS FLOAT64) AS lead_days,
           CAST(NULL AS FLOAT64) AS km
    FROM `{D}.staff_status` t
    WHERE t.state = @state
    GROUP BY t.cadre
    ORDER BY score
    """, _params(state), cache_key=f"net:staffcadre:{state}", ttl=300)

    out = _finish([dict(r) for r in rows], STAFF_CADRE_LABELS, [], state)
    out["resource"] = "personnel"
    out["grain"] = "cadre"
    return out


def comparison(resource: str = "medicine", state: str = "",
               vital_only: bool = False) -> dict:
    if resource == "bed":
        return bed_comparison(state)
    if resource == "personnel":
        return staff_comparison(state)
    return medicine_comparison(state, vital_only)
