"""POST_EVENT_VOL_CRUSH_v1 -- after the print, is the STILL-RICH straddle a sale?

    python -m scripts.post_event_vol_crush [--json]

The pre-event short-vol tests were weak (iron butterfly +5%, t 0.7). This is
a different timing: the event is resolved, the uncertainty it carried is gone,
and the literature says straddles bought IMMEDIATELY AFTER earnings are
substantially more negative than usual. So for every reconstructed print:

    entry   the first close that reflects the print (the pre-event trade's exit)
    strike  ATM at that close, same next-Friday expiry the pre-event trade used
    exit    the next session's close

and the P&L of a LONG straddle over that day is what the seller of a
defined-risk butterfly/condor would capture, sign flipped, up to the wings.

Reported: mean/median post-event straddle return, hit rate of the next-day
|move| against the straddle's break-even, a paired t, and the conditional cut
the paper suggests -- by prior 20-day realised vol tercile, and by how rich
the post-print straddle still is against that realised vol.

Every number is from real expired-option daily bars off the same feed the
pre-event backtest used, so the two are directly comparable.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from alpha import config
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from scripts.event_straddle_backtest import atm_strike, next_friday, option_bars


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _rv20(cl: list[float], i: int) -> float | None:
    if i < 21:
        return None
    return statistics.pstdev([math.log(cl[j] / cl[j - 1]) for j in range(i - 19, i + 1)])


def post_event(client, e: dict, days: list[str], cl: list[float]) -> dict | None:
    i = days.index(e["event_day"]) if e["event_day"] in days else -1
    if i < 21 or i + 1 >= len(days):
        return None
    entry_day, exit_day = days[i], days[i + 1]
    spot = cl[i]
    expiry = date.fromisoformat(e["expiry"])
    if expiry <= date.fromisoformat(exit_day):
        expiry = next_friday(date.fromisoformat(exit_day))
    for inc in (2.5, 5.0, 1.0, 10.0):
        k = atm_strike(spot, inc)
        syms = [f"{e['symbol']}{expiry:%y%m%d}{r}{int(round(k * 1000)):08d}" for r in "CP"]
        try:
            bars = option_bars(client, syms, entry_day, exit_day)
        except BrokerRefusal:
            continue
        cd = {b["t"][:10]: b for b in (bars.get(syms[0]) or [])}
        pd = {b["t"][:10]: b for b in (bars.get(syms[1]) or [])}
        if entry_day in cd and entry_day in pd and exit_day in cd and exit_day in pd:
            entry = cd[entry_day]["c"] + pd[entry_day]["c"]
            exit_ = cd[exit_day]["c"] + pd[exit_day]["c"]
            if entry <= 0:
                continue
            move = cl[i + 1] / spot - 1.0
            rv = _rv20(cl, i - 1)          # realised vol BEFORE the print
            return {
                "symbol": e["symbol"], "event_day": e["event_day"], "post_entry_day": entry_day,
                "post_exit_day": exit_day, "expiry": expiry.isoformat(), "strike": k, "spot": spot,
                "straddle_post_entry": round(entry, 2), "straddle_post_exit": round(exit_, 2),
                "implied_post": round(entry / spot, 4), "implied_pre": e["implied_move"],
                "next_day_abs_move": round(abs(move), 4), "next_day_move": round(move, 4),
                "post_straddle_return": round(exit_ / entry - 1.0, 4),
                "cleared_breakeven": abs(move) > entry / spot,
                "rv20_pre": rv, "post_implied_over_rv": (entry / spot) / rv if rv else None,
                "pre_event_straddle_return": e["straddle_return"],
            }
    return None


def summ(rows: list[dict]) -> dict:
    r = [x["post_straddle_return"] for x in rows]
    d = [x["next_day_abs_move"] - x["implied_post"] for x in rows]
    n = len(r)
    t = statistics.mean(d) / (statistics.pstdev(d) / math.sqrt(n)) if n > 2 and statistics.pstdev(d) > 0 else None
    return {"n": n, "mean_post_straddle_return": round(statistics.mean(r), 4) if n else None,
            "median_post_straddle_return": round(statistics.median(r), 4) if n else None,
            "hit_rate_cleared_breakeven": round(sum(x["cleared_breakeven"] for x in rows) / n, 3) if n else None,
            "median_implied_post": round(statistics.median(x["implied_post"] for x in rows), 4) if n else None,
            "median_implied_post_over_pre": round(statistics.median(x["implied_post"] / x["implied_pre"] for x in rows), 3) if n else None,
            "paired_t_realised_minus_implied": round(t, 2) if t is not None else None,
            "short_side_mean_capped_at_1x": round(statistics.mean(-min(x, 1.0) for x in r), 4) if n else None}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    rows = []
    cache = {}
    for e in events:
        sym = e["symbol"]
        if sym not in cache:
            bars = _daily_bars(client, sym, 800)
            cache[sym] = ([b["t"][:10] for b in bars], [float(b["c"]) for b in bars])
        days, cl = cache[sym]
        r = post_event(client, e, days, cl)
        if r:
            rows.append(r)
            print(f"  {sym:5s} {r['event_day']} post straddle {r['straddle_post_entry']:7.2f} -> {r['straddle_post_exit']:7.2f} "
                  f"implied {r['implied_post']:6.2%} (pre {r['implied_pre']:6.2%}) next-day {r['next_day_move']:+6.2%} "
                  f"ret {r['post_straddle_return']:+7.1%}")
    if not rows:
        print("no post-event straddles reconstructed -- an absence, not a result")
        return 1
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "pooled": summ(rows), "by_symbol": {},
           "by_rv20_tercile": {}, "by_post_richness_tercile": {}, "rows": rows}
    for sym in sorted({r["symbol"] for r in rows}):
        out["by_symbol"][sym] = summ([r for r in rows if r["symbol"] == sym])
    with_rv = sorted([r for r in rows if r["rv20_pre"]], key=lambda r: r["rv20_pre"])
    n = len(with_rv)
    for k, name in enumerate(("low", "mid", "high")):
        out["by_rv20_tercile"][name] = summ(with_rv[k * n // 3:(k + 1) * n // 3])
    with_rich = sorted([r for r in rows if r["post_implied_over_rv"]], key=lambda r: r["post_implied_over_rv"])
    n = len(with_rich)
    for k, name in enumerate(("cheap", "mid", "rich")):
        out["by_post_richness_tercile"][name] = summ(with_rich[k * n // 3:(k + 1) * n // 3])
    print(f"\nPOST_EVENT_VOL_CRUSH_v1 -- {len(rows)} post-print straddles (day after the print, real bars)\n")
    pl = out["pooled"]
    print(f"  pooled: mean {pl['mean_post_straddle_return']:+.1%} median {pl['median_post_straddle_return']:+.1%} "
          f"hit {pl['hit_rate_cleared_breakeven']:.0%} paired t {pl['paired_t_realised_minus_implied']} | "
          f"post implied {pl['median_implied_post']:.2%} = {pl['median_implied_post_over_pre']:.2f}x pre | "
          f"short side (capped 1x) {pl['short_side_mean_capped_at_1x']:+.1%}")
    for label, d in (("by prior rv20", out["by_rv20_tercile"]), ("by post richness", out["by_post_richness_tercile"])):
        print(f"  {label}: " + " | ".join(f"{k}: n={v['n']} mean {v['mean_post_straddle_return']:+.1%} hit {v['hit_rate_cleared_breakeven']:.0%}"
                                          for k, v in d.items() if v["n"]))
    print("  by name: " + ", ".join(f"{k} {v['mean_post_straddle_return']:+.0%}/{v['n']}" for k, v in out["by_symbol"].items()))
    print(f"  pre-event straddle mean on the same prints for comparison: "
          f"{statistics.mean(r['pre_event_straddle_return'] for r in rows):+.1%}")
    if args.json:
        path = _state_dir() / "post_event_vol_crush.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
