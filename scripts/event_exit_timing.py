"""EVENT_EXIT_TIMING_v1 -- sell the pre-print straddle at the OPEN or at the CLOSE?

    python -m scripts.event_exit_timing [--json]

The pre-event backtest (`event_straddle_backtest`) exits the straddle at the
first CLOSE that reflects the print. But the print is overnight: the gap is
realised at the OPEN, and the day-0 session that follows is where implied
collapses and where the day-night option-return asymmetry literature says the
long option BLEEDS (close-to-open option returns positive, open-to-close
negative). If the straddle's value at the open exceeds its value at the close
on average, every pre-event straddle in this project has been exited a
session too late -- and the live loop's exit rules, which mark at whatever
time the pass runs, are leaving the same money on the table.

For every reconstructed print: the same ATM straddle's OPEN and CLOSE on the
event day from the same daily option bars (which carry `o` and `c`), plus the
underlying's open and close.

    r_open      straddle_open / entry - 1        (exit at the day-0 open)
    r_close     straddle_close / entry - 1       (the existing number)
    intraday    straddle_close / straddle_open - 1  (what holding the session cost)

Daily bar opens for options are the first trade of the session, which can be
minutes after 09:30 and wide; this is a direction check on 117 prints, not an
executable fill. It says so.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.brains.vol_gap import _daily_bars
from scripts.event_straddle_backtest import option_bars


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    ubars: dict[str, dict[str, dict]] = {}
    rows = []
    for e in events:
        sym = e["symbol"]
        if sym not in ubars:
            ubars[sym] = {b["t"][:10]: b for b in _daily_bars(client, sym, 800)}
        k = e["strike"]
        exp = e["expiry"].replace("-", "")[2:]
        syms = [f"{sym}{exp}{r}{int(round(k * 1000)):08d}" for r in "CP"]
        try:
            bars = option_bars(client, syms, e["entry_day"], e["event_day"])
        except BrokerRefusal:
            continue
        cd = {b["t"][:10]: b for b in (bars.get(syms[0]) or [])}
        pd_ = {b["t"][:10]: b for b in (bars.get(syms[1]) or [])}
        d0 = e["event_day"]
        if d0 not in cd or d0 not in pd_:
            continue
        entry = e["straddle_entry"]
        s_open = float(cd[d0]["o"]) + float(pd_[d0]["o"])
        s_close = float(cd[d0]["c"]) + float(pd_[d0]["c"])
        s_high = float(cd[d0]["h"]) + float(pd_[d0]["h"])
        ub = ubars[sym].get(d0) or {}
        u_open, u_close = float(ub.get("o") or 0), float(ub.get("c") or 0)
        if entry <= 0 or s_open <= 0:
            continue
        rows.append({
            "symbol": sym, "event_day": d0, "entry": entry, "straddle_open": round(s_open, 2),
            "straddle_close": round(s_close, 2), "straddle_high_sum": round(s_high, 2),
            "r_open": s_open / entry - 1.0, "r_close": s_close / entry - 1.0,
            "intraday": s_close / s_open - 1.0,
            "gap_abs": abs(u_open / e["spot_entry"] - 1.0) if u_open else None,
            "day0_abs": abs(u_close / e["spot_entry"] - 1.0) if u_close else None,
            "intraday_underlying": (u_close / u_open - 1.0) if u_open and u_close else None,
            "implied_move": e["implied_move"],
        })
    if len(rows) < 10:
        print("too few prints with open bars -- an absence, not a result")
        return 1

    def t(xs):
        return statistics.mean(xs) / (statistics.pstdev(xs) / math.sqrt(len(xs))) if len(xs) > 2 and statistics.pstdev(xs) > 0 else None

    ro = [r["r_open"] for r in rows]; rc = [r["r_close"] for r in rows]; intr = [r["intraday"] for r in rows]
    diff = [a - b for a, b in zip(ro, rc)]
    gap_share = [r["gap_abs"] / r["day0_abs"] for r in rows if r["gap_abs"] is not None and r["day0_abs"]]
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": len(rows),
           "exit_at_open": {"mean": round(statistics.mean(ro), 4), "median": round(statistics.median(ro), 4),
                            "hit": round(sum(1 for x in ro if x > 0) / len(ro), 3), "t": round(t(ro), 2) if t(ro) else None},
           "exit_at_close": {"mean": round(statistics.mean(rc), 4), "median": round(statistics.median(rc), 4),
                             "hit": round(sum(1 for x in rc if x > 0) / len(rc), 3), "t": round(t(rc), 2) if t(rc) else None},
           "open_minus_close": {"mean": round(statistics.mean(diff), 4), "t": round(t(diff), 2) if t(diff) else None,
                                "share_open_better": round(sum(1 for d in diff if d > 0) / len(diff), 3)},
           "holding_the_session": {"mean": round(statistics.mean(intr), 4), "median": round(statistics.median(intr), 4),
                                   "t": round(t(intr), 2) if t(intr) else None},
           "median_share_of_day0_move_in_the_gap": round(statistics.median(gap_share), 3) if gap_share else None,
           "by_symbol": {}, "rows": rows}
    for sym in sorted({r["symbol"] for r in rows}):
        rs = [r for r in rows if r["symbol"] == sym]
        out["by_symbol"][sym] = {"n": len(rs), "open": round(statistics.mean(r["r_open"] for r in rs), 4),
                                 "close": round(statistics.mean(r["r_close"] for r in rs), 4)}
    print(f"\nEVENT_EXIT_TIMING_v1 -- {len(rows)} pre-print straddles, exit at day-0 OPEN vs CLOSE\n")
    for k in ("exit_at_open", "exit_at_close"):
        v = out[k]; print(f"  {k:14s} mean {v['mean']:+.1%} median {v['median']:+.1%} hit {v['hit']:.0%} t {v['t']}")
    v = out["open_minus_close"]; print(f"  open - close   mean {v['mean']:+.1%} t {v['t']}  open better on {v['share_open_better']:.0%} of prints")
    v = out["holding_the_session"]; print(f"  holding day 0  mean {v['mean']:+.1%} median {v['median']:+.1%} t {v['t']}  (the straddle's intraday return after the gap)")
    print(f"  median share of the day-0 |move| already in the gap: {out['median_share_of_day0_move_in_the_gap']}")
    print("  by name (open/close): " + ", ".join(f"{s} {v['open']:+.0%}/{v['close']:+.0%}" for s, v in out["by_symbol"].items()))
    if args.json:
        path = _state_dir() / "event_exit_timing.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
