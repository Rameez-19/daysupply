"""Check that the deployed frontend and backend talk to each other.

Calls every endpoint the web app uses, the way the app calls it, and checks
the status and the shape of the answer. Capture endpoints are called in
preview mode, so nothing is written to the ledger.

    python -m scripts.smoke_test                       # the live service
    python -m scripts.smoke_test http://localhost:8080  # a local run
"""

from __future__ import annotations

import sys
import time

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else
        "https://daysupply-898541549182.asia-south1.run.app").rstrip("/")
CENTRE = "IN-19662"

GET_CHECKS = [
    ("web app", "/", lambda r: "StockPulse" in r.text and 'id="capture-view"' in r.text),
    ("build stamp", "/api/v1/build", lambda r: "build" in r.json()),
    ("health", "/api/v1/healthz", lambda r: r.status_code == 200),
    ("states", "/api/v1/states", lambda r: len(r.json()["states"]) >= 30),
    ("Today geography", "/api/v1/today2/geography", lambda r: r.json()["totals"]["states"] >= 6),
    ("Today scorecard", "/api/v1/today2", lambda r: r.json()["scorecard"]["tracked"] > 0),
    ("Today staff", "/api/v1/today2?resource=personnel", lambda r: len(r.json()["kpis"]) >= 5),
    ("Today beds", "/api/v1/today2?resource=bed", lambda r: len(r.json()["kpis"]) >= 5),
    ("task bar counts", "/api/v1/action-queue?summary=true", lambda r: r.json()["summary"]["total"] > 0),
    ("action queue", "/api/v1/action-queue", lambda r: "escalate" in r.json()),
    ("early warnings", "/api/v1/surge/signals?limit=5", lambda r: "signals" in r.json()),
    ("early-warning count", "/api/v1/surge/signals?count_only=true", lambda r: "early_warning_districts" in r.json()),
    ("scenario options", "/api/v1/surge/scenario/options", lambda r: len(r.json()["combinations"]) > 0),
    ("demand outlook", "/api/v1/outlook", lambda r: r.status_code == 200),
    ("map", "/api/v1/map", lambda r: r.status_code == 200),
    ("model evidence", "/api/v1/model-evidence", lambda r: r.json()["model"]["series"] > 0),
    ("pattern exchange", "/api/v1/exchange/evaluation", lambda r: "pooled_wmape" in r.json()),
    ("review queue", "/api/v1/review-queue", lambda r: "items" in r.json()),
    ("medicine tiles", "/api/v1/items/quick", lambda r: len(r.json()["items"]) >= 30),
    ("capture modes", "/api/v1/capture-modes", lambda r: len(r.json()["modes"]) >= 6),
]


def check(name, method, path, ok, **kw):
    t = time.time()
    try:
        r = requests.request(method, BASE + path, timeout=120, **kw)
        good = r.status_code == 200 and ok(r)
        note = f"HTTP {r.status_code}"
    except Exception as exc:
        good, note = False, str(exc)[:60]
    print(f"{'OK  ' if good else 'FAIL'}  {name:<22} {time.time() - t:5.1f}s  {note}")
    return good


def main() -> None:
    print(f"Checking {BASE}\n")
    results = [check(n, "GET", p, ok) for n, p, ok in GET_CHECKS]
    results.append(check(
        "typed report (preview)", "POST", "/api/v1/chat-note",
        lambda r: any(e.get("item_id") == "PARACETAMOL" for e in r.json().get("events", [])),
        data={"facility_id": CENTRE, "preview": "true",
              "message": "paracetamol ke do sau tablet aaye"}))
    results.append(check(
        "spoken read-back", "POST", "/api/v1/speak",
        lambda r: r.headers.get("content-type", "").startswith("audio/") and len(r.content) > 1000,
        json={"text": "పారాసిటమాల్, 200 మాత్రలు, వచ్చాయి", "lang": "te"}))
    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
