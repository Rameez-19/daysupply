"""What the avoided waste is worth in rupees, at real published ceiling prices.

A ministry reviewer does not think in units. "26,612 units of expiry waste
avoided" is abstract; "₹X per PHC per year" is a budget line. This module does
that conversion using **NPPA ceiling prices under DPCO** — published, statutory,
and the correct basis, because a ceiling price is what a government purchaser
may lawfully be charged.

## It refused to publish a headline until 2026-09-13

Two things were wrong with the price data, and either alone would have
disqualified a headline in a project whose entire differentiator is
traceability:

1. **Coverage was 26.9%.** Prices covered only 8,851 of the 32,893 expired
   units. The single largest waste item — Ferrous Salt + Folic acid, **34.5%**
   of all expiry on its own — had no price at all. Grossing up from a quarter
   of the units would have been an extrapolation dressed as a measurement.

2. **The source was secondary.** Six rows transcribed from a summary of the
   DPCO schedule rather than from NPPA itself. `source_tier` is recorded per
   row so that was visible rather than assumed.

Both are fixed. `ingestion/extract_nppa_prices.py` reads the **NPPA Compendium
of Prices 2022** — ceiling prices notified under S.O. 1499(E) of 30.03.2022 —
and prices **35 of the 39** tracked items from it at `source_tier: primary`.
Coverage is **97.9%** (32,192 of 32,893 expired units), above the floor, so the
figure is computed rather than withheld.

**Four items stay unpriced on purpose**, together 701 units — 2.1% of expiry.
Sodium chloride is notified per 1000 ml glass bottle, Chlorhexidine and Timolol
per millilitre, Artesunate + Sulphadoxine-Pyrimethamine per co-blistered
course; stock here is counted in vials, bottles and tablets. Converting any of
them needs a pack size this project does not hold, and inventing one to raise
coverage would put a fabricated number inside a rupee claim. They count as
uncovered instead.

`COVERAGE_FLOOR` still gates the headline and still would if the price list
regressed. This is the same pattern as `substitution_constraint()` and staff
reallocation: the feature works, states its own limit, and does not invent past
it.

## What the figure will and will not mean

**It is computed on generated consumption.** The expiry it prices comes from the
generated ledger, anchored to real HMIS demand. The *prices* are real and the
*method* is real; the units they multiply are modelled. Any figure this produces
must be said as "on a modelled year of dispensing at this facility set", never
as observed savings.

It also **understates**, twice over: ceiling prices exclude GST, and a ceiling is
a maximum permitted price rather than a typical procurement price.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

PRICES_CSV = Path("Data/India/nppa_ceiling_prices.csv")
WASTE_VALUE = f"`{PROJECT}.{DATASET}.waste_value`"

# Below this share of priced expiry units, no headline figure is published.
COVERAGE_FLOOR = float(os.getenv("WASTE_VALUE_COVERAGE_FLOOR", "0.80"))
# Forecast PHCs, over which the per-facility figure is expressed.
FORECAST_PHCS = 200


def load_prices() -> pd.DataFrame:
    if not PRICES_CSV.exists():
        raise SystemExit(f"price file not found: {PRICES_CSV}")
    df = pd.read_csv(PRICES_CSV)
    primary = (df["source_tier"] == "primary").sum()
    print(f"  price rows: {len(df)} ({primary} primary, "
          f"{len(df) - primary} secondary)")
    return df


def run() -> None:
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    prices = load_prices()

    expired = client.query(f"""
        SELECT i.display_name AS item, i.unit, SUM(e.quantity) AS units
        FROM `{PROJECT}.{DATASET}.resource_events` e
        JOIN `{PROJECT}.{DATASET}.items` i ON i.item_id = e.item_id
        WHERE e.event_type = 'expired'
        GROUP BY item, unit
    """).to_dataframe()

    # Match on the leading word of the NLEM display name. Deliberately
    # conservative: an unmatched item contributes nothing rather than being
    # priced by something that merely looks similar.
    def price_for(name: str):
        for _, row in prices.iterrows():
            if str(name).lower().startswith(str(row["item_match"]).lower()):
                return row["ceiling_price_inr"], row["source_tier"]
        return None, None

    expired[["price", "tier"]] = expired["item"].apply(
        lambda n: pd.Series(price_for(n)))

    total_units = int(expired["units"].sum())
    priced = expired.dropna(subset=["price"]).copy()
    priced["value_inr"] = priced["units"] * priced["price"]
    priced_units = int(priced["units"].sum())
    coverage = priced_units / total_units if total_units else 0.0

    print(f"\n  expired units, all items:   {total_units:,}")
    print(f"  expired units with a price: {priced_units:,}")
    print(f"  coverage:                   {coverage:.1%} "
          f"(floor for a headline: {COVERAGE_FLOOR:.0%})")

    print("\n  Priced:")
    for _, r in priced.sort_values("value_inr", ascending=False).iterrows():
        print(f"    {r['item'][:30]:32s} {int(r['units']):>7,} {r['unit']:8s}"
              f" x Rs {r['price']:>6} = Rs {r['value_inr']:>10,.2f}  "
              f"[{r['tier']}]")

    unpriced = expired[expired["price"].isna()].sort_values(
        "units", ascending=False)
    print(f"\n  Unpriced ({len(unpriced)} items, "
          f"{int(unpriced['units'].sum()):,} units) — biggest first:")
    for _, r in unpriced.head(5).iterrows():
        print(f"    {r['item'][:30]:32s} {int(r['units']):>7,} units  "
              f"{100 * r['units'] / total_units:4.1f}% of all expiry")

    partial_value = float(priced["value_inr"].sum())
    print(f"\n  Value of priced expiry:     Rs {partial_value:,.2f}")

    if coverage < COVERAGE_FLOOR:
        print(f"\n  NO HEADLINE FIGURE PUBLISHED.")
        print(f"  Coverage {coverage:.1%} is below the {COVERAGE_FLOOR:.0%} "
              "floor.")
        print("  Grossing up from here would be an extrapolation presented as "
              "a measurement.")
        print("\n  To publish: add primary-source NPPA gazette prices to "
              f"{PRICES_CSV},")
        print("  starting with Ferrous Salt + Folic acid — a third of all "
              "expiry on its own.")
        return

    # Only reached once coverage is real.
    waste_avoided_share = next(iter(client.query(
        f"SELECT waste_avoided_share FROM `{PROJECT}.{DATASET}.impact_metrics`"
    ).result())).waste_avoided_share
    avoided_value = partial_value / coverage * waste_avoided_share
    print(f"\n  Value of waste AVOIDED by FEFO: Rs {avoided_value:,.0f}")
    print(f"  Per PHC per year:               Rs "
          f"{avoided_value / FORECAST_PHCS:,.0f}")
    print("\n  Computed on generated consumption, at real published ceiling "
          "prices. Understates twice: ceiling prices exclude GST, and a "
          "ceiling is a maximum rather than a typical procurement price.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
