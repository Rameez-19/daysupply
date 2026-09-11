"""Today v2 — the supply chain as a scorecard, not a pile of counts.

## What is different, and why

v1 grew by accretion: every finding that proved interesting got a panel, and
the page ended up answering fifteen questions of unequal importance in no
particular order. This is a deliberate scorecard instead.

Public-health logistics has a settled way of grading a supply chain, and it is
not "how many things are short". It is five questions, in this order:

1. **Availability** — what share of what we track is actually there? This is
   the service level, the number a programme is judged on, and the only one
   here where higher is better. Leading with it changes the reader's frame from
   "how many problems" to "how well is this working".
2. **Failure** — what has already run out? Availability of 90% with the missing
   10% being life-saving is a different situation from 90% with the gap in
   vitamins.
3. **Forward risk** — what runs out next, and when? A count is a snapshot; a
   date is a plan.
4. **Equity** — is this concentrated in a few districts or systemic? The
   national average hides both, and the response differs completely.
5. **Resilience** — could it take a shock? Every other number describes today.

## Rates, not counts

Counts are not comparable across scopes: 597 short means nothing until you know
whether it is out of 600 or 6,000, and a district with more facilities will
always look worse. Every headline here is a rate with the count kept beside it,
so Telangana and Assam can be read on the same scale.

## The four visuals answer four different questions

**When** (time to stock-out), **what** (which medicines, by name, in the most
places), **where** (districts plotted by exposure against ability to cope), and
**how robust** (absorption at 2x, 3x, 5x). Four questions, four forms — nothing
here is the same chart twice with a different filter.

The quadrant is the one that earns its place hardest. Shortage and resilience
are usually read separately, and separately they mislead: a district can be
short and able to cover itself from stock next door, or comfortable today and
unable to survive any surge. Plotted together, the districts that are both
badly short *and* unable to cope separate out visibly — Lakhimpur sits at 91.7%
short with 0% able to absorb a tripling, which no ranked list on the v1 page
puts in front of anyone.

One round trip, as everywhere else: the BigQuery job floor is ~1.3s, so six
panels fetched separately would be six floors stacked.
"""

from __future__ import annotations

import os

from google.cloud import bigquery

from app.bq import run_query

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
D = f"{PROJECT}.{DATASET}"

# The spike a district is asked to absorb from stock it already holds. Same 3x
# used by the executive view and the map, so the three cannot disagree.
ABSORPTION_MULTIPLIER = 3.0

# Below this share of positions holding, a district is "could not cope".
FRAGILE_BELOW = 35.0

# A district with three tracked medicines can read 100% short on one bad line.
# Rates need a floor under the denominator or the chart shows noise as crisis.
MIN_LINES_FOR_RATE = 8

# How many bars a reader can compare without counting them.
TOP_N = 10


def _predicates(state: str, district: str, phc: str, vital_only: bool,
                state_col: str = "state", district_col: str = "district",
                facility_col: str | None = "facility_id",
                ven_col: str = "ven_class") -> str:
    """Build a WHERE body against one table's own column names.

    Takes column names rather than rewriting a finished predicate. The
    `where.replace('state', 'to_state')` shortcut has broken this codebase
    twice by renaming the bound parameter along with the column, so it is not
    available here by construction.

    `facility_col=None` means the table has no facility column and the PHC
    filter cannot apply to it. That is deliberate rather than an oversight:
    `network_absorption` asks whether a DISTRICT's pooled stock could cover a
    surge, so there is no such thing as one facility's absorption. Silently
    dropping the filter would leave a reader thinking they had narrowed a
    number they had not, so the caller reports the mismatch and the page says
    which panels stayed at district level.
    """
    parts = []
    if state:
        parts.append(f"{state_col} = @state")
    if district:
        parts.append(f"{district_col} = @district")
    if phc and facility_col:
        parts.append(f"{facility_col} = @phc")
    if vital_only:
        parts.append(f"{ven_col} = 'Vital'")
    return " AND ".join(parts) if parts else "TRUE"


def scorecard(state: str = "", district: str = "", phc: str = "",
              vital_only: bool = False) -> dict:
    """Everything Today v2 needs, in a single round trip."""
    # Tables that carry a facility column take the PHC filter.
    rs = _predicates(state, district, phc, vital_only)
    ssi = _predicates(state, district, phc, vital_only)
    rec = _predicates(state, district, phc, vital_only,
                      state_col="to_state", district_col="to_district",
                      facility_col="to_facility_id")
    # `network_absorption` has no facility column, by design — see _predicates.
    na = _predicates(state, district, phc, vital_only, facility_col=None)

    params = []
    if state:
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))
    if phc:
        params.append(bigquery.ScalarQueryParameter("phc", "STRING", phc))

    rows = run_query(f"""
    SELECT
      -- 1-5. The scorecard itself. Everything is a rate with its count beside
      -- it, so scopes of different sizes can be compared honestly.
      (SELECT AS STRUCT
         COUNT(*) AS tracked,
         COUNTIF(NOT needs_reorder) AS available,
         COUNTIF(needs_reorder) AS short,
         COUNTIF(status = 'stocked_out') AS stocked_out,
         COUNTIF(ven_class = 'Vital') AS vital_tracked,
         COUNTIF(ven_class = 'Vital' AND NOT needs_reorder) AS vital_available,
         COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short,
         -- Forward risk: already gone, or gone inside a week.
         COUNTIF(on_hand <= 0 OR days_of_cover <= 7) AS at_risk_week,
         COUNT(DISTINCT facility_id) AS facilities,
         COUNT(DISTINCT district) AS districts,
         COUNT(DISTINCT IF(needs_reorder, district, NULL)) AS districts_short,
         COUNT(DISTINCT state) AS states,
         SUM(on_hand) AS units_on_hand
       FROM `{D}.reorder_status` WHERE {rs}) AS scorecard,

      -- WHEN. Ordered, mutually exclusive. Medicines with no usage history are
      -- excluded rather than dropped into the healthiest bucket, which would
      -- flatter the picture.
      ARRAY(SELECT AS STRUCT bucket, sort_order, n
            FROM (
              SELECT
                CASE WHEN on_hand <= 0 THEN 'Already out'
                     WHEN days_of_cover <= 7 THEN 'Within a week'
                     WHEN days_of_cover <= 14 THEN '1 to 2 weeks'
                     WHEN days_of_cover <= 30 THEN '2 to 4 weeks'
                     ELSE 'More than a month' END AS bucket,
                CASE WHEN on_hand <= 0 THEN 1
                     WHEN days_of_cover <= 7 THEN 2
                     WHEN days_of_cover <= 14 THEN 3
                     WHEN days_of_cover <= 30 THEN 4
                     ELSE 5 END AS sort_order,
                COUNT(*) AS n
              FROM `{D}.reorder_status`
              WHERE {rs} AND (days_of_cover IS NOT NULL OR on_hand <= 0)
              GROUP BY bucket, sort_order
              ORDER BY sort_order)) AS timeline,

      -- WHAT. By medicine name, because "Vitamin A is short in 49 health
      -- centres" is a sentence somebody can act on and an ATC code is not.
      ARRAY(SELECT AS STRUCT item_name, ven_class, centres, districts
            FROM (
              SELECT item_name, ANY_VALUE(ven_class) AS ven_class,
                     COUNT(DISTINCT facility_id) AS centres,
                     COUNT(DISTINCT district) AS districts
              FROM `{D}.reorder_status`
              WHERE {rs} AND needs_reorder
              GROUP BY item_name
              ORDER BY centres DESC, districts DESC
              LIMIT {TOP_N})) AS worst_medicines,

      -- WHERE. Exposure against ability to cope. Read separately these two
      -- mislead; together they separate the districts that are both badly
      -- short and unable to help themselves.
      ARRAY(SELECT AS STRUCT district, state, pct_short, pct_cope, tracked,
                             vital_short
            FROM (
              SELECT s.district, s.state, s.tracked, s.vital_short,
                     ROUND(100 * SAFE_DIVIDE(s.short, s.tracked), 1) AS pct_short,
                     ROUND(100 * SAFE_DIVIDE(c.holds, c.positions), 1) AS pct_cope
              FROM (
                SELECT district, ANY_VALUE(state) AS state,
                       COUNT(*) AS tracked, COUNTIF(needs_reorder) AS short,
                       COUNTIF(ven_class = 'Vital' AND needs_reorder) AS vital_short
                FROM `{D}.reorder_status` WHERE {rs}
                GROUP BY district
                HAVING tracked >= {MIN_LINES_FOR_RATE}) s
              JOIN (
                SELECT district, COUNTIF(absorbs) AS holds, COUNT(*) AS positions
                FROM `{D}.network_absorption`
                WHERE multiplier = {ABSORPTION_MULTIPLIER} AND {na}
                GROUP BY district) c
              USING (district))) AS districts_plot,

      -- HOW ROBUST.
      ARRAY(SELECT AS STRUCT multiplier, holds, total,
                             ROUND(100 * SAFE_DIVIDE(holds, total), 1) AS pct
            FROM (
              SELECT multiplier, COUNTIF(absorbs) AS holds, COUNT(*) AS total
              FROM `{D}.network_absorption` WHERE {na}
              GROUP BY multiplier ORDER BY multiplier)) AS absorption,

      -- What a purchase order cannot save.
      (SELECT COUNTIF(lead_time_decisive)
       FROM `{D}.surge_supply_impact` WHERE {ssi}) AS transfer_only,

      -- Queued decisions, for the scope line.
      (SELECT AS STRUCT COUNT(*) AS recommended, SUM(quantity) AS units,
              COUNTIF(ven_class = 'Vital') AS vital
       FROM `{D}.recommendations` WHERE {rec}) AS queue
    """, params,
        cache_key=f"v2:{state}:{district}:{phc}:{int(vital_only)}", ttl=300)

    if not rows:
        return {"error": "no data"}

    r = dict(rows[0])
    r["scope"] = {
        "state": state or "All India",
        "district": district,
        "phc": phc,
        "vital_only": vital_only,
        # Panels the PHC filter could not narrow, so the page can say so
        # instead of showing a district figure under a facility heading.
        "district_level_panels": (
            ["Could the network take a shock?", "Which districts need help first?"]
            if phc else []),
    }
    r["grades"] = _grades(r)
    r["resource"] = "medicine"
    # Nothing tracked at all is a real answer, not an error. Kept out of
    # `grades` because it is not a grade, and everything in there is iterated
    # as one.
    r["empty"] = (sc.get("tracked") or 0) == 0 if (sc := r.get("scorecard")) else True
    r["labels"] = MEDICINE_LABELS
    # The same `kpis` list beds and staff return, so the front end renders any
    # resource through one path instead of a branch per resource.
    g = r["grades"]
    sc = r.get("scorecard") or {}
    r["kpis"] = [
        _kpi(g["availability"]["pct"], "%", "Medicines available",
             f"{g['availability']['count'] or 0:,} of "
             f"{g['availability']['of'] or 0:,} at a safe level",
             g["availability"]["tone"], g["availability"]["says"]),
        _kpi(g["vital_availability"]["pct"], "%", "Life-saving available",
             f"{g['vital_availability']['count'] or 0:,} of "
             f"{g['vital_availability']['of'] or 0:,}",
             g["vital_availability"]["tone"], g["vital_availability"]["says"]),
        _kpi(g["stocked_out"]["pct"], "%", "Completely out",
             f"{g['stocked_out']['count'] or 0:,} with nothing on the shelf",
             g["stocked_out"]["tone"], g["stocked_out"]["says"]),
        _kpi(g["at_risk_week"]["pct"], "%", "Gone within a week",
             f"{g['at_risk_week']['count'] or 0:,} at the current rate of use",
             g["at_risk_week"]["tone"], g["at_risk_week"]["says"]),
        _kpi(g["spread"]["pct"], "%", "Districts affected",
             f"{g['spread']['count'] or 0:,} of {g['spread']['of'] or 0:,} "
             f"district{'' if (g['spread']['of'] or 0) == 1 else 's'}",
             g["spread"]["tone"], g["spread"]["says"]),
    ]
    # Same generic keys the other two resources use.
    r["summary"] = {"primary": sc.get("tracked") or 0,
                    "noun": "medicines",
                    "centres": sc.get("facilities") or 0,
                    "districts": sc.get("districts") or 0}
    r["distribution"] = r.get("timeline") or []
    r["ranking"] = [
        {"name": m["item_name"], "value": m["centres"],
         "sub": f"{m['districts']} district"
                f"{'' if m['districts'] == 1 else 's'}",
         "flag": m["ven_class"] == "Vital"}
        for m in (r.get("worst_medicines") or [])
    ]
    r["quadrant"] = [
        {"name": d["district"], "sub": d["state"], "x": d["pct_short"],
         "y": d["pct_cope"], "tracked": d["tracked"],
         "critical": d["pct_short"] >= 40 and d["pct_cope"] < FRAGILE_BELOW}
        for d in (r.get("districts_plot") or [])
    ]
    return r


def reporting_geography() -> dict:
    """The states, districts and health centres that actually report.

    **This is the fix for the filters "not working".** The dropdowns were fed
    from the facility register — 200,438 facilities across 668 districts —
    while only **200 facilities in 116 districts** report stock. Picking a
    health centre therefore had roughly a **one in a thousand** chance of
    landing on one with data, and every other choice emptied the page. The
    filter was working perfectly; it was being offered choices that could not
    work.

    Offering only what reports is also the honest presentation of the demo
    footprint, and stops the product implying facility-level coverage of all
    200,438 that it does not have.

    Small enough to send whole — 200 rows — so the cascade needs no further
    round trips and changing a state repopulates its districts instantly.
    """
    rows = run_query(f"""
        SELECT state, district, facility_id, ANY_VALUE(facility_name) AS name,
               COUNT(*) AS lines
        FROM `{D}.reorder_status`
        GROUP BY state, district, facility_id
        ORDER BY state, district, name
    """, cache_key="v2:geography", ttl=3600)

    states: dict = {}
    for r in rows:
        st = states.setdefault(r["state"],
                               {"state": r["state"], "lines": 0, "districts": {}})
        di = st["districts"].setdefault(
            r["district"],
            {"district": r["district"], "lines": 0, "facilities": []})
        di["facilities"].append({"facility_id": r["facility_id"],
                                 "name": r["name"], "lines": r["lines"]})
        di["lines"] += r["lines"]
        st["lines"] += r["lines"]

    return {
        "states": [
            {**st, "districts": sorted(st["districts"].values(),
                                       key=lambda d: d["district"])}
            for st in sorted(states.values(), key=lambda x: x["state"])
        ],
        "totals": {
            "states": len(states),
            "districts": sum(len(st["districts"]) for st in states.values()),
            "facilities": len(rows),
        },
    }


def _grades(r: dict) -> dict:
    """Turn each headline into a rate plus a plain verdict.

    A percentage with no verdict is a number a specialist can grade and nobody
    else can: the page has to say whether 78.6% is good, or it has not
    communicated anything. Thresholds are stated here once so the wording and
    the colour cannot drift apart.
    """
    s = r.get("scorecard") or {}
    tracked = s.get("tracked") or 0
    vital_tracked = s.get("vital_tracked") or 0
    districts = s.get("districts") or 0

    def rate(num, den):
        return round(100 * num / den, 1) if den else None

    availability = rate(s.get("available") or 0, tracked)
    vital_availability = rate(s.get("vital_available") or 0, vital_tracked)
    out_rate = rate(s.get("stocked_out") or 0, tracked)
    week_rate = rate(s.get("at_risk_week") or 0, tracked)
    spread = rate(s.get("districts_short") or 0, districts)
    absorb3 = next((a["pct"] for a in (r.get("absorption") or [])
                    if a["multiplier"] == ABSORPTION_MULTIPLIER), None)

    def band(value, good, fair, higher_is_better=True):
        """`good`/`fair` are the two cut points, read in the natural direction."""
        if value is None:
            return "unknown"
        if higher_is_better:
            return "ok" if value >= good else "warn" if value >= fair else "bad"
        return "ok" if value <= good else "warn" if value <= fair else "bad"

    return {
        "availability": {
            "pct": availability, "count": s.get("available"), "of": tracked,
            "tone": band(availability, 90, 75),
            "says": _say_availability(availability)},
        "vital_availability": {
            "pct": vital_availability, "count": s.get("vital_available"),
            "of": vital_tracked, "tone": band(vital_availability, 95, 85),
            # A scope with no life-saving lines is not "protecting them well",
            # it simply has none. The old sentence passed judgement on an
            # empty set, and the tile rendered "null%" above it.
            "says": ("No life-saving medicines are tracked here."
                     if vital_availability is None else
                     "Life-saving medicines should be the last thing to run "
                     "short, not the same as everything else."
                     if availability is not None
                     and vital_availability <= availability
                     else "Life-saving medicines are being protected ahead of "
                          "the rest, which is what should happen.")},
        "stocked_out": {
            "pct": out_rate, "count": s.get("stocked_out"), "of": tracked,
            "tone": band(out_rate, 1, 5, higher_is_better=False),
            "says": "Nothing on the shelf at all today."},
        "at_risk_week": {
            "pct": week_rate, "count": s.get("at_risk_week"), "of": tracked,
            "tone": band(week_rate, 5, 15, higher_is_better=False),
            "says": "Gone within seven days at the current rate of use."},
        # Meaningless below two districts: one district short of one district
        # is 100%, and "almost every district is affected" is then a sentence
        # about a sample of one. Showing it anyway is how a filtered view ends
        # up making a confident claim that is not about anything.
        "spread": ({
            "pct": spread, "count": s.get("districts_short"), "of": districts,
            "tone": band(spread, 25, 60, higher_is_better=False),
            "says": _say_spread(spread)}
            if districts > 1 else {
            "pct": None, "count": s.get("districts_short"), "of": districts,
            "tone": "unknown",
            "says": "Not meaningful for a single district — widen the area to "
                    "compare districts against each other."}),
        "resilience": {
            "pct": absorb3, "tone": band(absorb3, 70, FRAGILE_BELOW),
            "says": _say_resilience(absorb3)},
    }


MEDICINE_LABELS = {
    "distribution": {
        "title": "When will it run out?",
        "note": "Every medicine we track, grouped by how many days of supply "
                "is left at the current rate of use.",
    },
    "ranking": {
        "title": "Which medicines are short in the most places?",
        "note": "Counted by how many health centres are short of each one. "
                "Red is life-saving.",
        "unit": "health centres short",
    },
    "quadrant": {
        "title": "Which districts need help first?",
        "note": "Every district placed by how much is running low (across) "
                "against how much it could cope with if demand tripled (up). "
                "The bottom right is the worst place to be: badly short, and "
                "unable to help itself.",
        "x": "Share of medicines running low",
        "y": "Could cope if demand tripled",
        "critical": "Needs help first",
        "other": "Other districts",
    },
    "provenance": "Stock counts come from the ledger. Expected demand comes "
                  "from the trained model.",
}


def _say_availability(pct: float | None) -> str:
    if pct is None:
        return "Nothing is being tracked here yet."
    if pct >= 90:
        return "Healthy. Most medicines are where they should be."
    if pct >= 75:
        return "Under strain. One medicine in four or five is running low."
    return "Poor. A large share of the medicine list is running low."


def _say_spread(pct: float | None) -> str:
    if pct is None:
        return "No districts in view."
    if pct <= 25:
        return "Concentrated in a few districts, so it can be fixed locally."
    if pct <= 60:
        return "Spread across many districts, not just a few bad ones."
    return "Systemic. Almost every district is affected, so this is not a "\
           "local problem to delegate."


def _say_resilience(pct: float | None) -> str:
    if pct is None:
        return "Not enough data to work this out."
    if pct >= 70:
        return "Most district stocks could cope if demand tripled."
    if pct >= FRAGILE_BELOW:
        return "Many district stocks could not cope if demand tripled."
    return "Low. Most district stocks could not cope if demand tripled."


# ── Beds and staff ───────────────────────────────────────────────────
#
# The page showed "not graded yet" for these, which was honest and useless.
# They are graded the same way medicines are, because the questions a health
# official asks about beds are the same questions in a different unit.
#
# All three resources return the same shape — a `kpis` list plus `distribution`,
# `ranking` and `quadrant` — so one front-end path renders any of them and the
# titles travel with the data instead of living in a branch per resource.


def _kpi(value, unit, label, sub, tone, says) -> dict:
    return {"value": value, "unit": unit, "label": label, "sub": sub,
            "tone": tone, "says": says}


def _band(value, good, fair, higher_is_better=True) -> str:
    if value is None:
        return "unknown"
    if higher_is_better:
        return "ok" if value >= good else "warn" if value >= fair else "bad"
    return "ok" if value <= good else "warn" if value <= fair else "bad"


def _rate(num, den):
    return round(100 * num / den, 1) if den else None


def _geo_where(state: str, district: str, phc: str) -> str:
    """Geography predicate for the bed and staff tables.

    Both carry state, district and facility_id, so all three filters apply —
    unlike `network_absorption`, which has no facility column at all.
    """
    parts = []
    if state:
        parts.append("state = @state")
    if district:
        parts.append("district = @district")
    if phc:
        parts.append("facility_id = @phc")
    return " AND ".join(parts) if parts else "TRUE"


def _geo_params(state: str, district: str, phc: str) -> list:
    params = []
    if state:
        params.append(bigquery.ScalarQueryParameter("state", "STRING", state))
    if district:
        params.append(
            bigquery.ScalarQueryParameter("district", "STRING", district))
    if phc:
        params.append(bigquery.ScalarQueryParameter("phc", "STRING", phc))
    return params


BED_LABELS = {
    "distribution": {
        "title": "How full are the health centres?",
        "note": "Every centre placed by how much of its bed capacity is in use.",
    },
    "ranking": {
        "title": "Where are patients being turned away?",
        "note": "The centres turning away the most people in the last 30 days "
                "of reporting. Red "
                "is a centre that is over capacity.",
        "unit": "patients turned away",
    },
    "quadrant": {
        "title": "Which districts are under most pressure?",
        "note": "Districts placed by how full their beds are (across) against "
                "how much spare capacity is left (up). The bottom right is "
                "full, with nothing held in reserve.",
        "x": "Average occupancy",
        "y": "Spare capacity left",
        "critical": "Under pressure",
        "other": "Other districts",
    },
    "provenance": "Bed numbers are the IPHS 2022 government norm, which is "
                  "real. How full they are is modelled from real HMIS "
                  "admission volumes.",
}

STAFF_LABELS = {
    "distribution": {
        "title": "How badly staffed are the roles?",
        "note": "Every role at every centre, placed by how many of its "
                "sanctioned posts are unfilled.",
    },
    "ranking": {
        "title": "Which roles are hardest to fill?",
        "note": "Average share of sanctioned posts unfilled, by role. Red is "
                "30% or worse.",
        "unit": "% of posts unfilled",
    },
    # Was "which districts are worst staffed?", plotted against attendance.
    # Both axes were wrong. Vacancy in `staff_status` takes exactly 23 distinct
    # values — one per state and cadre, from RHS 2017 (20 under 2021-22) — repeated across 928
    # rows and 116 districts, so a district scatter drew 116 points from 23
    # numbers and invited the reader to compare districts that carry an
    # identical figure. Attendance was generated outright.
    #
    # Plotted at the grain the data actually has, it answers a recruitment
    # question instead: which cadre, in which state, is both badly vacant and
    # large enough for that to matter.
    "quadrant": {
        "title": "Which roles need recruiting into first?",
        "note": "One point per cadre per state, placed by the share of "
                "sanctioned posts unfilled (across) against how many posts "
                "there are (up). Top right is a large establishment with a "
                "lot of it empty. Points left of zero are cadres RHS records "
                "as over establishment - more staff in position than "
                "sanctioned - which is a real finding, not a negative gap.",
        "x": "% of posts unfilled",
        "y": "Sanctioned posts",
        # The y-axis is a count now, not a share. Without this the renderer's
        # default drew "450%" on an axis of sanctioned posts.
        "x_unit": "%",
        "y_unit": "",
        "critical": "30% or worse",
        "other": "Other roles",
        "flagged": "roles at 30% vacant or worse",
        "empty": "No role in scope carries an RHS 2021-22 vacancy figure.",
    },
    "provenance": "Vacancy and sanctioned strength are from Rural Health "
                  "Statistics 2021-22 at state-and-cadre grain, which is the "
                  "grain this panel reports. Nothing here is per-facility.",
}


def bed_scorecard(state: str = "", district: str = "", phc: str = "") -> dict:
    """Bed availability, graded.

    Capacity is the IPHS 2022 government norm and is real. How full those beds
    are is modelled from real HMIS admission volumes, which the page states
    rather than buries — occupancy is the number a reader would otherwise
    assume had been counted.
    """
    where = _geo_where(state, district, phc)
    params = _geo_params(state, district, phc)

    rows = run_query(f"""
    SELECT
      (SELECT AS STRUCT
         COUNT(*) AS centres,
         SUM(bed_capacity) AS beds,
         SUM(free_beds) AS free_beds,
         SUM(turned_away) AS turned_away,
         ROUND(AVG(occupancy_rate), 4) AS mean_occupancy,
         COUNTIF(status = 'over_capacity') AS over_capacity,
         COUNTIF(turned_away > 0) AS turning_away,
         COUNT(DISTINCT district) AS districts,
         COUNT(DISTINCT IF(turned_away > 0, district, NULL)) AS districts_affected
       FROM `{D}.bed_status` WHERE {where}) AS s,

      ARRAY(SELECT AS STRUCT bucket, sort_order, n FROM (
        SELECT CASE WHEN occupancy_rate >= 1 THEN 'Over capacity'
                    WHEN occupancy_rate >= 0.85 THEN '85% or more full'
                    WHEN occupancy_rate >= 0.5 THEN 'Half to 85% full'
                    WHEN occupancy_rate > 0 THEN 'Under half full'
                    ELSE 'Empty' END AS bucket,
               CASE WHEN occupancy_rate >= 1 THEN 1
                    WHEN occupancy_rate >= 0.85 THEN 2
                    WHEN occupancy_rate >= 0.5 THEN 3
                    WHEN occupancy_rate > 0 THEN 4 ELSE 5 END AS sort_order,
               COUNT(*) AS n
        FROM `{D}.bed_status` WHERE {where}
        GROUP BY bucket, sort_order ORDER BY sort_order)) AS distribution,

      ARRAY(SELECT AS STRUCT name, value, sub, flag FROM (
        SELECT facility_name AS name, turned_away AS value,
               CONCAT(district, ' - ', CAST(bed_capacity AS STRING), ' beds') AS sub,
               status = 'over_capacity' AS flag
        FROM `{D}.bed_status` WHERE {where} AND turned_away > 0
        ORDER BY turned_away DESC LIMIT {TOP_N})) AS ranking,

      ARRAY(SELECT AS STRUCT name, sub, x, y, tracked, critical FROM (
        SELECT district AS name, ANY_VALUE(state) AS sub,
               ROUND(100 * AVG(occupancy_rate), 1) AS x,
               ROUND(100 * SAFE_DIVIDE(SUM(free_beds), SUM(bed_capacity)), 1) AS y,
               COUNT(*) AS tracked,
               SUM(turned_away) > 0 AND AVG(occupancy_rate) >= 0.5 AS critical
        FROM `{D}.bed_status` WHERE {where}
        GROUP BY district)) AS quadrant
    """, params, cache_key=f"v2bed:{state}:{district}:{phc}", ttl=300)

    if not rows:
        return {"resource": "bed", "empty": True, "kpis": [],
                "labels": BED_LABELS}

    r = dict(rows[0])
    s = dict(r["s"])
    centres = s.get("centres") or 0
    if not centres:
        return {"resource": "bed", "empty": True, "scorecard": s, "kpis": [],
                "labels": BED_LABELS}

    occ = 100 * (s.get("mean_occupancy") or 0)
    free = round(100 - occ, 1)
    over = _rate(s.get("over_capacity") or 0, centres)
    turning = _rate(s.get("turning_away") or 0, centres)
    districts = s.get("districts") or 0
    spread = (_rate(s.get("districts_affected") or 0, districts)
              if districts > 1 else None)

    return {
        "resource": "bed",
        "empty": False,
        "scorecard": s,
        "labels": BED_LABELS,
        "summary": {"primary": s.get("beds") or 0, "noun": "beds",
                    "centres": centres, "districts": districts},
        "kpis": [
            _kpi(free, "%", "Beds free on average",
                 f"{s.get('beds') or 0:,} beds across {centres:,} centres",
                 _band(free, 40, 15),
                 "Spare capacity is what absorbs a bad week. Too little and a "
                 "surge turns patients away."),
            _kpi(over, "%", "Centres over capacity",
                 f"{s.get('over_capacity') or 0:,} of {centres:,} centres",
                 _band(over, 5, 20, higher_is_better=False),
                 "More patients than beds, so somebody is being sent "
                 "elsewhere."),
            _kpi(s.get("turned_away") or 0, "", "Patients turned away",
                 f"In the last 30 days of reporting, at "
                 f"{s.get('turning_away') or 0:,} centres",
                 "bad" if (s.get("turned_away") or 0) > 0 else "ok",
                 "Every one of these is a person who arrived and could not be "
                 "admitted."),
            _kpi(turning, "%", "Centres turning people away",
                 f"{s.get('turning_away') or 0:,} of {centres:,}",
                 _band(turning, 5, 20, higher_is_better=False),
                 "Whether this is a few overwhelmed centres or a general "
                 "shortage of beds."),
            _kpi(spread, "%", "Districts affected",
                 f"{s.get('districts_affected') or 0:,} of {districts:,} districts",
                 _band(spread, 25, 60, higher_is_better=False),
                 _say_spread(spread) if spread is not None
                 else "Not meaningful for a single district - widen the area "
                      "to compare districts against each other."),
        ],
        "distribution": [dict(x) for x in (r.get("distribution") or [])],
        "ranking": [dict(x) for x in (r.get("ranking") or [])],
        "quadrant": [dict(x) for x in (r.get("quadrant") or [])],
    }


def staff_scorecard(state: str = "", district: str = "",
                    phc: str = "") -> dict:
    """Staffing, graded — at the grain the data actually has.

    Three of the five KPIs here used to be built on `attendance_vs_sanctioned`
    and `days_none_present`, which `ingestion/generate_bed_personnel.py`
    produces from a fixed-seed random propensity. "Actually on duty 53.2%" was
    a random number, and it was also wrong on its own terms: 278 facility-cadres
    with posts filled reported nobody present across all 30 days, and
    `days_none_present > 0` covered 875 of 928 rows — 94% of everything, which
    cannot distinguish anything from anything.

    What survives is real and narrower than the old page implied. Vacancy takes
    one distinct value per state and cadre — 23 across 928 rows under Rural
    Health Statistics 2017, 20 across 800 under 2021-22 — so it does not vary by district or by
    facility at all. Sanctioned posts are the IPHS norm. Nurses against the bed
    norm is the Indian Nursing Council ratio applied to real bed capacity.

    Everything below therefore reports state-and-cadre, and says so. Under
    2021-22 no centre-role here is over establishment, and 20 (Telangana's
    health assistants, 0 sanctioned against 1,156 required) have no rate; both
    are handled rather than averaged into silence.
    """
    where = _geo_where(state, district, phc)
    params = _geo_params(state, district, phc)

    rows = run_query(f"""
    SELECT
      (SELECT AS STRUCT
         COUNT(*) AS facility_cadres,
         COUNT(DISTINCT facility_id) AS centres,
         SUM(sanctioned_posts) AS posts,
         COUNT(DISTINCT CONCAT(state, '|', cadre)) AS roles,
         -- Weighted by establishment size, so a 40%-vacant cadre of three
         -- posts does not outvote a 12%-vacant cadre of three hundred.
         ROUND(SAFE_DIVIDE(SUM(vacancy_rate * sanctioned_posts),
                           SUM(IF(vacancy_rate IS NULL, 0,
                                  sanctioned_posts))), 4) AS mean_vacancy,
         COUNTIF(vacancy_rate IS NULL) AS no_rhs_figure,
         SUM(nurses_short_of_bed_norm) AS nurses_short,
         COUNT(DISTINCT district) AS districts,
         COUNT(DISTINCT state) AS states
       FROM `{D}.staff_status` WHERE {where}) AS s,

      -- Counted over state-and-cadre pairs, not over the 800 rows those 20
      -- numbers are repeated across.
      (SELECT AS STRUCT
         COUNTIF(v >= 0.3) AS roles_badly_short,
         COUNT(*) AS roles_scored,
         ARRAY_AGG(STRUCT(cadre, state, ROUND(100 * v, 1) AS pct)
                   ORDER BY v DESC LIMIT 1)[SAFE_OFFSET(0)] AS worst
       FROM (SELECT cadre, state, ANY_VALUE(vacancy_rate) AS v
             FROM `{D}.staff_status`
             WHERE {where} AND vacancy_rate IS NOT NULL
             GROUP BY state, cadre)) AS roleagg,

      ARRAY(SELECT AS STRUCT bucket, sort_order, n FROM (
        SELECT CASE WHEN vacancy_rate >= 0.5 THEN 'Half the posts empty'
                    WHEN vacancy_rate >= 0.3 THEN '30% to 50% empty'
                    WHEN vacancy_rate >= 0.1 THEN '10% to 30% empty'
                    WHEN vacancy_rate > 0 THEN 'Under 10% empty'
                    ELSE 'Fully staffed' END AS bucket,
               CASE WHEN vacancy_rate >= 0.5 THEN 1
                    WHEN vacancy_rate >= 0.3 THEN 2
                    WHEN vacancy_rate >= 0.1 THEN 3
                    WHEN vacancy_rate > 0 THEN 4 ELSE 5 END AS sort_order,
               COUNT(*) AS n
        FROM `{D}.staff_status` WHERE {where}
        GROUP BY bucket, sort_order ORDER BY sort_order)) AS distribution,

      -- By role, not by centre. "Male health assistants are 38% vacant" is a
      -- recruitment decision; no per-facility list adds up to that sentence.
      ARRAY(SELECT AS STRUCT name, value, sub, flag FROM (
        SELECT cadre AS name,
               -- Weighted, like the headline. A plain AVG here gave each
               -- state's figure equal say regardless of how many posts it
               -- covers, so Delhi's 11 posts counted as much as
               -- Maharashtra's several hundred.
               ROUND(100 * SAFE_DIVIDE(
                       SUM(vacancy_rate * sanctioned_posts),
                       SUM(IF(vacancy_rate IS NULL, 0, sanctioned_posts))),
                     1) AS value,
               CONCAT(CAST(SUM(sanctioned_posts) AS STRING),
                      ' sanctioned posts') AS sub,
               SAFE_DIVIDE(SUM(vacancy_rate * sanctioned_posts),
                           SUM(IF(vacancy_rate IS NULL, 0,
                                  sanctioned_posts))) >= 0.3 AS flag
        FROM `{D}.staff_status` WHERE {where}
        GROUP BY cadre ORDER BY value DESC LIMIT {TOP_N})) AS ranking,

      -- One point per state and cadre. A district scatter drew 116 points
      -- from 23 numbers, so districts sharing an identical figure appeared as
      -- distinct observations to compare.
      ARRAY(SELECT AS STRUCT name, sub, x, y, tracked, critical FROM (
        SELECT cadre AS name, state AS sub,
               ROUND(100 * ANY_VALUE(vacancy_rate), 1) AS x,
               SUM(sanctioned_posts) AS y,
               COUNT(DISTINCT facility_id) AS tracked,
               ANY_VALUE(vacancy_rate) >= 0.3 AS critical
        FROM `{D}.staff_status`
        WHERE {where} AND vacancy_rate IS NOT NULL
        GROUP BY state, cadre)) AS quadrant
    """, params, cache_key=f"v2staff:{state}:{district}:{phc}", ttl=300)

    if not rows:
        return {"resource": "personnel", "empty": True, "kpis": [],
                "labels": STAFF_LABELS}

    r = dict(rows[0])
    s = dict(r["s"])
    cadres = s.get("facility_cadres") or 0
    if not cadres:
        return {"resource": "personnel", "empty": True, "scorecard": s,
                "kpis": [], "labels": STAFF_LABELS}

    ra = dict(r["roleagg"]) if r.get("roleagg") else {}
    worst = dict(ra["worst"]) if ra.get("worst") else {}
    roles_scored = ra.get("roles_scored") or 0

    # Over establishment — more in position than sanctioned — is 0 here under
    # 2021-22 (47 under 2017) but reported elsewhere in the source,
    # which is a real RHS outcome and not an error. Capped for display, because
    # "103% of posts filled" invites the reader to think a post is missing.
    filled = min(100.0, round(100 - 100 * (s.get("mean_vacancy") or 0), 1))
    badly_short = _rate(ra.get("roles_badly_short") or 0, roles_scored)         if roles_scored else None
    districts = s.get("districts") or 0

    return {
        "resource": "personnel",
        "empty": False,
        "scorecard": s,
        "labels": STAFF_LABELS,
        "summary": {"primary": s.get("posts") or 0,
                    "noun": "sanctioned posts",
                    "centres": s.get("centres") or 0,
                    "districts": districts},
        "kpis": [
            _kpi(filled, "%", "Posts filled",
                 f"{roles_scored:,} state-and-cadre roles, weighted by "
                 "establishment size",
                 _band(filled, 90, 75),
                 "Rural Health Statistics 2021-22, weighted by sanctioned posts "
                 "so a small badly-vacant cadre does not outvote a large "
                 "one."),
            # The single worst state-and-role, not the nationally hardest
            # role. Today v1 and the ranking chart beside this tile rank roles
            # nationally (health assistants, under 2021-22). Labelled "Hardest
            # to fill", this tile read as contradicting both once Rajasthan's
            # pharmacists became the worst single pair.
            _kpi(worst.get("pct"), "%",
                 f"Worst state and role: {worst.get('cadre') or 'n/a'}"
                 if worst else "Worst state and role",
                 f"{worst.get('state') or ''} — the most vacant single role "
                 "in any state in scope"
                 if worst else "No vacancy figure in scope",
                 _band(worst.get("pct"), 15, 30, higher_is_better=False),
                 "Recruitment happens by cadre and by state, which is also the "
                 "only grain this figure exists at."),
            _kpi(badly_short, "%", "Roles 30% vacant or worse",
                 f"{ra.get('roles_badly_short') or 0:,} of {roles_scored:,} "
                 "state-and-cadre pairs",
                 _band(badly_short, 20, 40, higher_is_better=False),
                 "Counted over the roles themselves. Counting the 800 rows "
                 "they repeat across would report the same 20 figures as "
                 "though they were 800 observations."),
            _kpi(s.get("nurses_short") or 0, "", "Nurses below the bed norm",
                 "Against the Indian Nursing Council ratio IPHS cites",
                 "bad" if (s.get("nurses_short") or 0) > 0 else "ok",
                 "Nursing need is set by how many beds a centre has, not by "
                 "its sanctioned list. Nurses in position are the RHS state rate "
                 "applied to this centre's posts — an estimate, not a "
                 "headcount."),
            _kpi(s.get("posts") or 0, "", "Sanctioned posts",
                 f"across {s.get('centres') or 0:,} centres in "
                 f"{districts:,} districts",
                 "ok",
                 "The establishment these vacancy rates are shares of. "
                 + (f"{s.get('no_rhs_figure') or 0:,} centre-roles have no vacancy "
                    "rate and are excluded above: the source sanctions none "
                    "of those posts (Telangana sanctions 0 health assistants "
                    "at PHCs against 1,156 required)."
                    if (s.get("no_rhs_figure") or 0) else
                    "Every centre-role in scope carries an RHS 2021-22 figure.")),
        ],
        "distribution": [dict(x) for x in (r.get("distribution") or [])],
        "ranking": [dict(x) for x in (r.get("ranking") or [])],
        "quadrant": [dict(x) for x in (r.get("quadrant") or [])],
    }
