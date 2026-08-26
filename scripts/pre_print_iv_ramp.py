"""PRE_PRINT_IV_RAMP_v1 -- own the run-up INTO the print, and be flat for the print itself.

    python -m scripts.pre_print_iv_ramp [--json]

Every straddle test so far holds THROUGH the event and pays the crush. The
other half of the earnings-vol calendar is the ramp: implied volatility in the
expiry that contains the print tends to rise in the sessions before it as
hedgers and speculators arrive. A straddle bought N sessions before the entry
close of the existing backtest and SOLD at that entry close (the close before
the print) owns the ramp and never faces the announcement.

For every reconstructed print and the same ATM strike/expiry the pre-event
test used (so the two are the same contract, one sold to the other):

    entry   close N sessions before the pre-event entry day    (N = 5 and 3)
    exit    the pre-event entry close (the last close before the print)

The straddle's return over that window is the ramp net of theta and of the
underlying's drift, which is exactly the trade's P&L. It is reported beside
the pre-event straddle's own return on the same contract so the two halves of
the cycle can be read as one line.
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

WINDOWS = (5, 3)


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    days_by_sym: dict[str, list[str]] = {}
    rows = []
    for e in events:
        sym = e["symbol"]
        if sym not in days_by_sym:
            days_by_sym[sym] = [b["t"][:10] for b in _daily_bars(client, sym, 800)]
        days = days_by_sym[sym]
        if e["entry_day"] not in days:
            continue
        i = days.index(e["entry_day"])
        if i < max(WINDOWS):
            continue
        exp = e["expiry"].replace("-", "")[2:]
        syms = [f"{sym}{exp}{r}{int(round(e['strike'] * 1000)):08d}" for r in "CP"]
        start = days[i - max(WINDOWS)]
        try:
            bars = option_bars(client, syms, start, e["entry_day"])
        except BrokerRefusal:
            continue
        cd = {b["t"][:10]: float(b["c"]) for b in (bars.get(syms[0]) or [])}
        pd_ = {b["t"][:10]: float(b["c"]) for b in (bars.get(syms[1]) or [])}
        row = {"symbol": sym, "event_day": e["event_day"], "exit_day": e["entry_day"],
               "straddle_exit": e["straddle_entry"], "implied_move": e["implied_move"],
               "pre_event_straddle_return": e["straddle_return"]}
        ok = False
        for n in WINDOWS:
            d = days[i - n]
            if d in cd and d in pd_ and cd[d] + pd_[d] > 0:
                entry = cd[d] + pd_[d]
                row[f"entry_{n}"] = round(entry, 2)
                row[f"ramp_{n}"] = e["straddle_entry"] / entry - 1.0
                row[f"days_{n}"] = n
                ok = True
        if ok:
            rows.append(row)
    if len(rows) < 20:
        print("too few prints with ramp bars -- an absence, not a result")
        return 1

    def t(xs):
        return statistics.mean(xs) / (statistics.pstdev(xs) / math.sqrt(len(xs))) if len(xs) > 2 and statistics.pstdev(xs) > 0 else None

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": len(rows), "windows": WINDOWS, "by_window": {}, "rows": rows}
    print(f"\nPRE_PRINT_IV_RAMP_v1 -- {len(rows)} prints; long the ATM straddle into the last close before the print, flat for the print\n")
    for n in WINDOWS:
        xs = [r[f"ramp_{n}"] for r in rows if f"ramp_{n}" in r]
        if not xs:
            continue
        both = [(r[f"ramp_{n}"], r["pre_event_straddle_return"]) for r in rows if f"ramp_{n}" in r]
        cycle = [(1 + a) * (1 + b) - 1 for a, b in both]
        by_sym = {}
        for s in sorted({r["symbol"] for r in rows}):
            v = [r[f"ramp_{n}"] for r in rows if r["symbol"] == s and f"ramp_{n}" in r]
            if v:
                by_sym[s] = round(statistics.mean(v), 4)
        out["by_window"][str(n)] = {
            "n": len(xs), "mean": round(statistics.mean(xs), 4), "median": round(statistics.median(xs), 4),
            "hit": round(sum(1 for x in xs if x > 0) / len(xs), 3), "t": round(t(xs), 2) if t(xs) else None,
            "worst": round(min(xs), 4), "best": round(max(xs), 4),
            "full_cycle_ramp_then_hold_mean": round(statistics.mean(cycle), 4),
            "corr_ramp_vs_event_return": round(_corr([a for a, _ in both], [b for _, b in both]), 3),
            "by_symbol": by_sym,
        }
        v = out["by_window"][str(n)]
        print(f"  T-{n} -> T-0 close:  n={v['n']} mean {v['mean']:+.1%} median {v['median']:+.1%} hit {v['hit']:.0%} t {v['t']}  "
              f"worst {v['worst']:+.0%} best {v['best']:+.0%} | corr with the event's own straddle return {v['corr_ramp_vs_event_return']:+.2f}")
        print("     by name: " + ", ".join(f"{s} {x:+.0%}" for s, x in by_sym.items()))
    print("  reading: a positive mean with hit > 50% is the ramp paying more than theta; the ramp is a DIFFERENT bet from the print"
          " and a negative corr with the event return means the two halves hedge each other across names.")
    if args.json:
        path = _state_dir() / "pre_print_iv_ramp.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


def _corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa, sb = statistics.pstdev(a), statistics.pstdev(b)
    return (sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)) / (sa * sb) if sa > 0 and sb > 0 else 0.0


if __name__ == "__main__":
    sys.exit(main())
