"""LOCK_THE_JUMP_v1 -- does the 08:30 NFP gap survive until options open at 09:30?

    python -m scripts.lock_the_jump [--json]

The frozen 4 Sep trade buys a SPY straddle the afternoon before. The jobs
report lands at 08:30 ET; equity options do not trade until 09:30. For one
hour the straddle's delta after the gap is a bet nobody chose. SPY itself trades
pre-market, so the delta can be locked with shares at 08:31 -- IF the gap tends
to give back before the open. If the gap tends to EXTEND, locking sells the
move the straddle was bought for.

Measured on every NFP release day since 2024-03 from SPY 1-minute bars
(extended hours):

    jump        08:29 close -> first print after 08:30
    to_open     that print -> 09:30
    to_mark     09:30 -> 10:45  (the trade's flat time)

If corr(jump, to_open) is negative and the |jump| exceeds the |move to 10:45|
on average, the 08:31 hedge preserves value the straddle would otherwise lose
before it can be sold. If not, the extension is the trade and hedging is the
mistake. This is a DIRECTION check on ~28 days, and it says so.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def minute_bars(client, symbol: str, day: str) -> list[dict]:
    page = client._request("GET", "/v2/stocks/bars", base=config.data_url(),
                           params={"symbols": symbol, "timeframe": "1Min", "start": f"{day}T11:00:00Z",
                                   "end": f"{day}T14:50:00Z", "limit": 1000, "feed": config.stock_feed()})
    return (page.get("bars") or {}).get(symbol) or []


def _at(bars: list[dict], hhmm_utc: str, *, before: bool) -> float | None:
    """Last close at or before `hhmm_utc` (before=True), or first close at or after it."""
    if before:
        rows = [b for b in bars if b["t"][11:16] <= hhmm_utc]
        return float(rows[-1]["c"]) if rows else None
    rows = [b for b in bars if b["t"][11:16] >= hhmm_utc]
    return float(rows[0]["c"]) if rows else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    src = json.loads((_state_dir() / "nfp_straddle_backtest.json").read_text(encoding="utf-8"))
    days = sorted({r["release"] for r in src["rows"] if r["symbol"] == "SPY"})
    straddle = {r["release"]: r for r in src["rows"] if r["symbol"] == "SPY"}
    rows = []
    for day in days:
        bars = minute_bars(client, "SPY", day)
        # The free IEX feed is thin before 08:30; when no pre-release bar exists
        # the prior close stands in (the overnight drift is then inside "jump").
        pre_bar = _at(bars, "12:29", before=True)
        pre = pre_bar or straddle[day].get("spot_prev_close")
        jump = _at(bars, "12:31", before=False)
        jump_rows = [b for b in bars if b["t"][11:16] >= "12:31"]
        jump_ts = jump_rows[0]["t"][11:16] if jump_rows else None
        open_ = _at(bars, "13:30", before=False)
        mark = _at(bars, "14:45", before=True)
        if not all((pre, jump, open_, mark)):
            print(f"  {day}: incomplete bars (pre {pre}, jump {jump}, open {open_}, mark {mark})")
            continue
        r = {"release": day, "pre": pre, "pre_source": "premarket_bar" if pre_bar else "prior_close",
             "first_print_after_0830_utc": jump_ts, "jump_px": jump, "open_px": open_, "mark_px": mark,
             "jump": jump / pre - 1.0, "to_open": open_ / jump - 1.0, "to_mark": mark / open_ - 1.0,
             "pre_to_open": open_ / pre - 1.0, "pre_to_mark": mark / pre - 1.0,
             "n_premarket_bars": sum(1 for b in bars if "12:30" <= b["t"][11:16] < "13:30"),
             "straddle_return_1045": straddle[day].get("straddle_return"),
             "implied_move": straddle[day].get("implied_move")}
        r["jump_kept_at_open"] = (r["pre_to_open"] / r["jump"]) if abs(r["jump"]) > 1e-6 else None
        r["reversed_half_by_open"] = (r["jump_kept_at_open"] is not None and r["jump_kept_at_open"] < 0.5)
        rows.append(r)
        print(f"  {day}  jump {r['jump']:+.2%}  ->open {r['to_open']:+.2%}  ->10:45 {r['to_mark']:+.2%}  "
              f"| pre->open {r['pre_to_open']:+.2%}  pre->10:45 {r['pre_to_mark']:+.2%}  kept {r['jump_kept_at_open'] if r['jump_kept_at_open'] is None else round(r['jump_kept_at_open'], 2)}")
    if len(rows) < 5:
        print("too few days with extended-hours bars -- an absence, not a result")
        return 1

    def corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        sa, sb = statistics.pstdev(a), statistics.pstdev(b)
        return (sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)) / (sa * sb) if sa > 0 and sb > 0 else 0.0

    jumps = [r["jump"] for r in rows]; to_open = [r["to_open"] for r in rows]
    abs_jump = [abs(r["jump"]) for r in rows]
    abs_open = [abs(r["pre_to_open"]) for r in rows]
    abs_mark = [abs(r["pre_to_mark"]) for r in rows]
    diff = [a - b for a, b in zip(abs_jump, abs_open)]
    t = statistics.mean(diff) / (statistics.pstdev(diff) / len(diff) ** 0.5) if statistics.pstdev(diff) > 0 else None
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_days": len(rows),
           "n_days_with_premarket_bar": sum(1 for r in rows if r["pre_source"] == "premarket_bar"),
           "first_print_after_0830_median_utc": sorted(r["first_print_after_0830_utc"] for r in rows)[len(rows) // 2],
           "corr_jump_vs_to_open": round(corr(jumps, to_open), 3),
           "mean_abs_jump": round(statistics.mean(abs_jump), 4),
           "mean_abs_pre_to_open": round(statistics.mean(abs_open), 4),
           "mean_abs_pre_to_1045": round(statistics.mean(abs_mark), 4),
           "abs_jump_minus_abs_open_t": round(t, 2) if t is not None else None,
           "share_reversed_half_by_open": round(sum(r["reversed_half_by_open"] for r in rows) / len(rows), 3),
           "share_extended_by_open": round(sum(1 for r in rows if r["jump_kept_at_open"] is not None and r["jump_kept_at_open"] > 1.0) / len(rows), 3),
           "median_premarket_bars_per_day": statistics.median(r["n_premarket_bars"] for r in rows),
           "rows": rows}
    print(f"\nLOCK_THE_JUMP_v1 -- {len(rows)} NFP days, SPY extended-hours minute bars "
          f"({out['n_days_with_premarket_bar']} with a pre-08:30 bar; median first print after 08:30 at "
          f"{out['first_print_after_0830_median_utc']} UTC)\n")
    print(f"  corr(jump, drift to 09:30) {out['corr_jump_vs_to_open']:+.3f}   "
          f"|jump| {out['mean_abs_jump']:.2%} vs |pre->open| {out['mean_abs_pre_to_open']:.2%} vs |pre->10:45| {out['mean_abs_pre_to_1045']:.2%} "
          f"(|jump|-|open| t {out['abs_jump_minus_abs_open_t']})")
    print(f"  gap gave back half or more before the open on {out['share_reversed_half_by_open']:.0%} of days; "
          f"extended beyond the jump on {out['share_extended_by_open']:.0%}")
    print("  reading: negative corr AND |jump| > |pre->open| means the 08:31 hedge preserves value; positive corr means the"
          " extension is the trade and the hedge sells it.")
    if args.json:
        path = _state_dir() / "lock_the_jump.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
