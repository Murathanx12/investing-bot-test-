"""Run the sanity sentinels over the ledger. See `alpha/sentinels.py`.

    python -m scripts.sentinels                  # every brain, whole ledger
    python -m scripts.sentinels --since 2026-08-27   # after the arithmetic fix
    python -m scripts.sentinels --strict         # exit 1 if any brain is BROKEN

Reads and prints. Places no orders and quarantines nothing by itself -- the
runner asks `sentinels.broken()` at entry time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alpha import sentinels

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


def read(since: str | None) -> list[dict]:
    p = STATE / "decisions.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:                                          # noqa: BLE001
                continue
            if since and (r.get("ts_utc") or "") < since:
                continue
            out.append(r)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None, help="ISO date; only decisions at or after it")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    rows = read(args.since)
    verdicts = sentinels.evaluate(rows)
    scope = f"since {args.since}" if args.since else "whole ledger"
    print(f"SANITY SENTINELS  {scope}  ({len(rows)} decision rows)")
    print(f"  trigger: one-sided on more than {sentinels.ONE_SIDED_MAX:.0%} of at least "
          f"{sentinels.MIN_DECISIONS} comparable decisions\n")
    if not verdicts:
        print("  no decisions carry both a forecast sd and a chain implied move.")
        return 0
    for v in verdicts:
        print("  " + v.line())
        print(f"      {v.detail}")
    bad = [v for v in verdicts if v.state == sentinels.BROKEN]
    print(f"\n  {len(bad)} brain(s) would lose NEW-POSITION authority. "
          "Exits, marking and management are unaffected.")
    return 1 if (bad and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
