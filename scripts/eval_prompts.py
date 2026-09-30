"""Score the stock-extraction prompt against the edge cases in evals/.

Each case goes through the same path as a typed report on the Report page:
Gemini extraction with the live system instruction, then the server-side
catalogue matcher and confidence gate. Nothing is written anywhere.

    python -m scripts.eval_prompts                 # the configured model chain
    python -m scripts.eval_prompts --model gemini-3.8-flash@global

Prints one line per case and the pass rate. A case passes only when what
would be written, and what would be held for the pharmacist, both match.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import capture, capture_pipeline  # noqa: E402

CASES = ROOT / "evals" / "extraction_cases.json"


def run_case(case: dict) -> tuple[bool, str, float]:
    t0 = time.time()
    try:
        raw = capture.process_text(case["text"])
        extractions = capture_pipeline.parse_model_json(raw)
    except Exception as exc:
        return False, f"error: {str(exc)[:80]}", time.time() - t0
    routed = capture_pipeline.route(extractions, "EVAL", "chat", raw_transcript=case["text"])
    accept = case.get("accept_event", {})
    got = sorted((e["item_id"], e["event_type"], e["quantity"]) for e in routed["events"])
    want = sorted(tuple(x) for x in case.get("expect", []))

    def norm(rows):
        out = []
        for item, ev, q in rows:
            if item in accept and ev in accept[item]:
                ev = accept[item][0]
            out.append((item, ev, q))
        return sorted(out)

    held = sorted({r["item_id"] for r in routed["review_queue"] if r.get("item_id")})
    want_held = sorted(case.get("held", []))
    ok = norm(got) == norm(want) and held == want_held
    detail = f"wrote {got}" + (f" held {held}" if held else "")
    return ok, detail, time.time() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="pin one model, e.g. gemini-3.8-flash@global")
    args = ap.parse_args()
    if args.model:
        capture.MODEL, _, loc = args.model.partition("@")
        if loc:
            capture.LOCATION = loc
        capture.FALLBACK_MODELS = []
        capture.MAX_ATTEMPTS = 2
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    passed, total_time = 0, 0.0
    for case in cases:
        ok, detail, secs = run_case(case)
        passed += ok
        total_time += secs
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<18} {secs:5.1f}s  "
              f"{capture.model_used():<22} {detail}")
    print(f"\n{passed}/{len(cases)} passed ({100 * passed / len(cases):.0f}%), "
          f"mean {total_time / len(cases):.1f}s per report")


if __name__ == "__main__":
    main()
