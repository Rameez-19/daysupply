"""What the avoided waste is worth in rupees — and why no figure is published yet.

A ministry reviewer does not think in units. "26,612 units of expiry waste
avoided" is abstract; "₹X per PHC per year" is a budget line. This module does
that conversion using **NPPA ceiling prices under DPCO** — published, statutory,
and the correct basis, because a ceiling price is what a government purchaser
may lawfully be charged.

## It currently refuses to publish a headline, on purpose

Two things are wrong with the price data available right now, and either alone
would be enough to disqualify a headline number in a project whose entire
differentiator is traceability:

1. **Coverage is 26.9%.** Prices are held for items covering only 8,851 of the
   32,893 expired units. The single largest waste item — Ferrous Salt + Folic
   acid, **34.5%** of all expiry on its own — has no price at all. Grossing up
   from a quarter of the units to a total would be an extrapolation dressed as
   a measurement.

2. **The source is secondary.** The figures were transcribed from a summary of
   the DPCO schedule, not from the Gazette of India notification itself. That
   is fine for arithmetic and not fine for a submission claim. `source_tier` is
   recorded per row so this is visible rather than assumed.

So `COVERAGE_FLOOR` gates the headline. Below it the module computes everything,
reports the partial figure clearly labelled as partial, and declines to publish
a national number. This is the same pattern as `substitution_constraint()` and
staff reallocation: the feature works, states its own limit, and does not invent
past it.

**To publish a real figure**, drop the NPPA gazette PDF for the DPCO ceiling
price schedule into `Data/India/`, extend `nppa_ceiling_prices.csv` with
`source_tier=primary` rows covering the forecast items — Ferrous Salt + Folic
acid first, it is a third of the waste on its own — and re-run. Nothing else
needs to change.

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
              "floor, and the prices held are from a secondary source.")
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
