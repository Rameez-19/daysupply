"""BigQuery access layer with cost guard rails and caching.

Every query in the application goes through `run_query`. It exists to enforce
three rules that are easy to break by accident:

1. **No unbounded scans.** Every query is dry-run first. If it would scan more
   than `MAX_SCAN_BYTES` the query is refused, not run.
2. **No `SELECT *` on `facilities`.** Refused before it reaches BigQuery.
3. **Reference data is cached.** Dropdown contents change when the facility
   master is reloaded, which is roughly never, so they are held in process.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Iterable, Sequence

from google.cloud import bigquery

log = logging.getLogger(__name__)

PROJECT = os.getenv("GCP_PROJECT", "daysupply")
DATASET = os.getenv("BQ_DATASET", "daysupply")
LOCATION = os.getenv("BQ_LOCATION", "asia-south1")

FACILITIES = f"`{PROJECT}.{DATASET}.facilities`"
GEO_SUMMARY = f"`{PROJECT}.{DATASET}.geo_summary`"

# Refuse anything that would scan more than 10 GB. Nothing this application
# does legitimately comes close; crossing it means a query lost its filter.
MAX_SCAN_BYTES = int(os.getenv("BQ_MAX_SCAN_GB", "10")) * 1024 ** 3

# Reference-data cache lifetime, seconds.
CACHE_TTL = int(os.getenv("BQ_CACHE_TTL", "3600"))

_client: bigquery.Client | None = None
_client_lock = threading.Lock()

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()

# `SELECT *` / `SELECT t.*` anywhere in the statement.
_SELECT_STAR = re.compile(r"select\s+(?:[a-z_][a-z0-9_]*\s*\.\s*)?\*", re.I)


class QueryTooExpensive(RuntimeError):
    """Raised when a query would scan more than the configured limit."""


class UnsafeQuery(ValueError):
    """Raised when a query violates a project guard rail."""


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def client() -> bigquery.Client:
    """Process-wide BigQuery client, created on first use."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = bigquery.Client(project=PROJECT, location=LOCATION)
    return _client


def _check_guard_rails(sql: str) -> None:
    if _SELECT_STAR.search(sql) and "facilities" in sql.lower():
        raise UnsafeQuery(
            "SELECT * on facilities is forbidden — project the columns you need"
        )


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del _cache[key]
            return None
        return value


def _cache_put(key: str, value: Any, ttl: int) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, value)


def clear_cache() -> None:
    """Drop cached reference data — call after reloading the facility master."""
    with _cache_lock:
        _cache.clear()


def run_query(
    sql: str,
    params: Sequence[bigquery.ScalarQueryParameter] | None = None,
    *,
    cache_key: str | None = None,
    ttl: int = CACHE_TTL,
    max_scan_bytes: int = MAX_SCAN_BYTES,
) -> list[dict]:
    """Run a parameterised query and return rows as dicts.

    Dry-runs first and refuses to execute anything scanning more than
    `max_scan_bytes`. Results are cached in process when `cache_key` is given.
    """
    _check_guard_rails(sql)

    if cache_key is not None:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    params = list(params or [])
    bq = client()

    # --- Cost check -------------------------------------------------------
    dry = bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=params, dry_run=True, use_query_cache=False
        ),
    )
    scanned = dry.total_bytes_processed or 0
    if scanned > max_scan_bytes:
        raise QueryTooExpensive(
            f"Query would scan {_human_bytes(scanned)}, limit is "
            f"{_human_bytes(max_scan_bytes)}. Refusing to run."
        )
    if scanned > 1024 ** 3:
        log.warning("Query will scan %.2f GB", scanned / 1024 ** 3)

    # --- Execute ----------------------------------------------------------
    job = bq.query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
    )
    rows = [dict(row) for row in job.result()]

    if cache_key is not None:
        _cache_put(cache_key, rows, ttl)
    return rows


def scalar(rows: Iterable[dict], field: str, default: Any = None) -> Any:
    """First value of `field` across `rows`, or `default` if there are none."""
    for row in rows:
        return row.get(field, default)
    return default
