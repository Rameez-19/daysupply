"""Runtime item catalogue, read from BigQuery.

At runtime the catalogue comes from `daysupply.items`, never from the NLEM
spreadsheet. The spreadsheet is an ingestion-time input: `Data/` is excluded
from the container image, so parsing it here would work locally and fail on
Cloud Run — which is exactly how it did fail once.

Loaded lazily and cached, so importing this module does no I/O and a container
that starts without BigQuery reachable still boots.
"""

from __future__ import annotations

import logging
import re
import threading

from app.bq import run_query

log = logging.getLogger(__name__)

PROJECT_TABLE = "items"

_lock = threading.Lock()
_catalog: list[dict] | None = None
_name_index: dict[str, str] | None = None
_names: list[str] | None = None


def _load() -> list[dict]:
    from app.bq import DATASET, PROJECT
    return run_query(
        f"""
        SELECT item_id, display_name, local_name_in, spoken_variants,
               unit, ven_class, atc_code, demand_driver, is_forecast_item,
               units_per_driver_event, driver_rationale
        FROM `{PROJECT}.{DATASET}.{PROJECT_TABLE}`
        ORDER BY display_name
        """,
        cache_key="items:catalog",
    )


def catalog() -> list[dict]:
    """The full National List of Essential Medicines, cached in process."""
    global _catalog
    if _catalog is None:
        with _lock:
            if _catalog is None:
                _catalog = _load()
                log.info("Item catalogue loaded: %d medicines", len(_catalog))
    return _catalog


# Parenthetical glosses in NLEM names — "Glycerin/glycerol (as mentioned in
# IP)" — are stripped before indexing. Left in, they give partial-ratio scorers
# a long tail of common words to match arbitrary speech against.
_GLOSS = re.compile(r"\([^)]*\)|\[[^\]]*\]")

# Strengths are noise for identity: a worker saying "metformin 500" means
# metformin. Which strength was dispensed is carried by the unit and quantity
# fields, not by the item match.
_STRENGTH = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g|gm|iu|lac|%)?\b", re.I
)

# Matching runs in two stages, because real speech comes in two shapes.
#
# Stage 1 compares the whole utterance. A clean extraction — "paracetamol",
# "dolo 650" — scores 90-100 here, and unrelated speech scores in the 50s-70s,
# so 85 sits comfortably in the gap.
#
# Stage 2 exists because the drug name is often *inside* a longer phrase:
# "paracetamol ke do sau tablet", "sugar ki goli metformin". Whole-string
# comparison scores those in the 50s-70s and rejects them, which is wrong — the
# medicine is named, plainly. `token_set_ratio` asks the different question of
# whether a catalogue name appears within the utterance, and it separates the
# two groups sharply: embedded names score 100, while the worst score across a
# corpus of unrelated clinic speech ("haan ji boliye", "doctor sahab nahi
# aaye", "wo neeli wali dawai") is 60. The threshold is set at 90, inside that
# gap and deliberately nearer the top of it.
MATCH_THRESHOLD = 85
CONTAINED_THRESHOLD = 90

# A catalogue entry shorter than this can be "contained" in almost anything,
# so stage 2 ignores them and leaves stage 1 to judge.
MIN_CONTAINED_LENGTH = 4


def _key(text: str) -> str:
    stripped = _STRENGTH.sub(" ", _GLOSS.sub(" ", text or "").lower())
    return re.sub(r"\s+", " ", stripped).strip(" .,-")


def _build_index() -> tuple[list[str], dict[str, str]]:
    global _names, _name_index
    if _names is None or _name_index is None:
        names: list[str] = []
        index: dict[str, str] = {}
        for item in catalog():
            variants = [item["display_name"], item["local_name_in"]]
            variants += list(item.get("spoken_variants") or [])
            for variant in variants:
                key = _key(variant)
                if key and key not in index:
                    names.append(key)
                    index[key] = item["item_id"]
        _names, _name_index = names, index
    return _names, _name_index


def match(local_name: str, threshold: int = MATCH_THRESHOLD) -> str | None:
    """Fuzzy-match a spoken drug name to an item_id.

    Matching happens server-side against the catalogue on purpose. The model is
    never asked to produce a drug code — a hallucinated drug code is the worst
    failure this system could produce.

    `token_sort_ratio` compares the whole string rather than the best-matching
    fragment, so a sentence of unrelated speech cannot score highly against a
    long medicine name just by sharing a few words.
    """
    if not local_name:
        return None
    from thefuzz import fuzz, process

    names, index = _build_index()
    key = _key(local_name)
    if not names or not key:
        return None

    # Stage 1 — the whole utterance is the drug name.
    best = process.extractOne(key, names, scorer=fuzz.token_sort_ratio)
    if best and best[1] >= threshold:
        return index[best[0]]

    # Stage 2 — the drug name sits inside a longer phrase.
    contained = process.extractOne(
        key,
        [n for n in names if len(n) >= MIN_CONTAINED_LENGTH],
        scorer=fuzz.token_set_ratio,
    )
    if contained and contained[1] >= CONTAINED_THRESHOLD:
        return index[contained[0]]
    return None


def reset() -> None:
    """Drop the cached catalogue — used by tests."""
    global _catalog, _names, _name_index
    with _lock:
        _catalog = _names = _name_index = None
