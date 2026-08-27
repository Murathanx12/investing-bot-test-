"""Record or list a human thesis. See `alpha/human.py`.

    python -m scripts.thesis --list
    python -m scripts.thesis --symbol NVDA --direction up --expected-move 0.06 \
        --catalyst "Q2 FY27 print" --catalyst-at 2026-08-26T20:20Z --horizon 3 \
        --conviction 0.9 --reason "..." --falsifier "..."

Writes one line to `state/human_theses.jsonl`. Sends nothing, sizes nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from alpha import human


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--author", default="murat")
    p.add_argument("--symbol")
    p.add_argument("--direction", choices=human.DIRECTIONS, default="none")
    p.add_argument("--magnitude", choices=human.MAGNITUDES, default="unknown",
                   help="the chain's implied move is WIDER/NARROWER than the outcome will be")
    p.add_argument("--expected-move", type=float, default=None,
                   help="signed fraction of spot over the horizon, e.g. 0.06")
    p.add_argument("--catalyst")
    p.add_argument("--catalyst-at", help="ISO timestamp; must be AFTER now")
    p.add_argument("--horizon", type=float, default=3.0)
    p.add_argument("--conviction", type=float, default=1.0)
    p.add_argument("--reason", default="")
    p.add_argument("--falsifier", default="")
    args = p.parse_args()

    if args.list:
        rows = human.load_all()
        if not rows:
            print(f"no theses in {human.path()}")
            return 0
        now = datetime.now(timezone.utc)
        for t in rows:
            state = "OPEN " if t in human.open_theses(now) else "CLOSED"
            move = f"{t.expected_move:+.2%}" if t.expected_move is not None else "  --  "
            print(f"{state} {t.thesis_id()}  {t.symbol:<6} {t.direction:<5} {move} "
                  f"width={t.magnitude:<8} claim={t.claim:<12} conv {t.conviction:.2f}")
            print(f"       catalyst {t.catalyst_at_utc}  {t.catalyst}")
            print(f"       stated   {t.stated_at_utc}")
            print(f"       falsifier: {t.falsifier}")
        return 0

    missing = [n for n in ("symbol", "catalyst", "catalyst_at") if not getattr(args, n.replace("-", "_"))]
    if missing:
        print(f"missing required: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        t = human.Thesis(
            author=args.author, symbol=args.symbol.upper(), direction=args.direction,
            magnitude=args.magnitude, catalyst=args.catalyst, catalyst_at_utc=args.catalyst_at,
            horizon_days=args.horizon, reason=args.reason, falsifier=args.falsifier,
            expected_move=args.expected_move, conviction=args.conviction,
        )
    except human.ThesisRefusal as exc:
        print(f"THESIS REFUSED\n  {exc}", file=sys.stderr)
        return 1

    tid = human.record(t)
    print(f"recorded {tid}  {t.symbol} {t.direction} claim={t.claim}")
    print(f"  admissible structures: see alpha/claims.ADMISSIBLE[{t.claim!r}]")
    print(f"  written to {human.path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
