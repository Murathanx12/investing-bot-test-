"""NFP-DAY STRADDLE BACKTEST -- the 4 September trade, graded on 2024-2026.

    AAT_ACCOUNT_ROLE=dev python -m scripts.nfp_straddle_backtest --symbols SPY QQQ

The competition deadline is 11:00 ET on 4 Sep and the August jobs report lands
at 08:30 ET that morning. Our window is the 09:30 open to a 10:45 flatten. So
the question is precise: buy the 0DTE ATM straddle at the prior close, sell it
at 10:45 ET on release day -- what did that return on every Employment
Situation release since March 2024?

Rhoads (Nasdaq, 2025) reports 1-day index straddles UNDERpriced the move on 10
of the last 12 NFP days; Wright (NBER 28306) finds the employment-day variance
premium small and unstable. This script measures it on Alpaca's own bars:
release dates from FRED (release_id 50, exact, including the shutdown-displaced
ones), expired 0DTE contracts' minute bars for the 10:45 mark.

Closes and minute-bar closes, not crossed quotes; a real exit at 10:45 pays the
0DTE spread. The number is a direction check, not an edge.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.sources.http import get_json

#: Not an Employment Situation print: the preliminary benchmark revision.
EXCLUDE = {"2024-08-21"}
MARK_UTC = "14:45"   # 10:45 ET during EDT


def nfp_dates(start: str = "2024-03-01") -> list[str]:
    key = os.getenv("AAT_FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit("AAT_FRED_API_KEY not set")
    d, _ = get_json("https://api.stlouisfed.org/fred/release/dates",
                    {"release_id": 50, "realtime_start": "2024-01-01",
                     "include_release_dates_with_no_data": "true", "api_key": key, "file_type": "json"})
    today = datetime.now(timezone.utc).date().isoformat()
    return [r["date"] for r in d["release_dates"] if start <= r["date"] < today and r["date"] not in EXCLUDE]


def straddle_on(client, symbol: str, day: str) -> dict | None:
    bars = client.stock_bars(symbol, start=(date.fromisoformat(day) - timedelta(days=6)).isoformat(),
                             timeframe="1Day", adjustment="raw")["bars"].get(symbol) or []
    prev = [b for b in bars if b["t"][:10] < day]
    on = [b for b in bars if b["t"][:10] == day]
    if not prev or not on:
        return None
    spot_prev = float(prev[-1]["c"])
    k = round(spot_prev)
    d = date.fromisoformat(day)
    syms = [f"{symbol}{d:%y%m%d}{r}{int(k * 1000):08d}" for r in "CP"]
    try:
        daily = client._request("GET", "/v1beta1/options/bars", base=config.data_url(),
                                params={"symbols": ",".join(syms), "timeframe": "1Day",
                                        "start": prev[-1]["t"][:10], "end": day, "limit": 10})
        mins = client._request("GET", "/v1beta1/options/bars", base=config.data_url(),
                               params={"symbols": ",".join(syms), "timeframe": "1Min",
                                       "start": f"{day}T13:30:00Z", "end": f"{day}T15:00:00Z", "limit": 2000})
    except BrokerRefusal:
        return None
    db, mb = daily.get("bars") or {}, mins.get("bars") or {}
    entry = 0.0
    for s in syms:
        rows = [b for b in (db.get(s) or []) if b["t"][:10] == prev[-1]["t"][:10]]
        if not rows:
            return None
        entry += float(rows[0]["c"])
    exit_ = 0.0
    for s in syms:
        rows = [b for b in (mb.get(s) or []) if b["t"][11:16] <= MARK_UTC]
        if not rows:
            return None
        exit_ += float(rows[-1]["c"])
    # Underlying at the mark, from the option-implied intrinsic is unreliable;
    # use the minute stock bar instead.
    sb = client._request("GET", "/v2/stocks/bars", base=config.data_url(),
                         params={"symbols": symbol, "timeframe": "1Min", "start": f"{day}T13:30:00Z",
                                 "end": f"{day}T14:46:00Z", "limit": 200, "feed": config.stock_feed()})
    srows = [b for b in ((sb.get("bars") or {}).get(symbol) or []) if b["t"][11:16] <= MARK_UTC]
    spot_mark = float(srows[-1]["c"]) if srows else None
    return {"symbol": symbol, "release": day, "strike": k, "spot_prev_close": spot_prev,
            "spot_1045": spot_mark, "move_to_1045": (spot_mark / spot_prev - 1.0) if spot_mark else None,
            "implied_move": round(entry / spot_prev, 4), "straddle_entry": round(entry, 2),
            "straddle_1045": round(exit_, 2), "straddle_return": round(exit_ / entry - 1.0, 4) if entry else None}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=["SPY", "QQQ"])
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    days = nfp_dates()
    print(f"{len(days)} Employment Situation releases since 2024-03 (FRED release 50)")
    rows = []
    for sym in args.symbols:
        for day in days:
            r = straddle_on(client, sym, day)
            if r is None:
                print(f"  {sym} {day}: no 0DTE data")
                continue
            rows.append(r)
            print(f"  {sym} {day} K={r['strike']} implied {r['implied_move']:.2%} move@10:45 "
                  f"{(r['move_to_1045'] or 0):+.2%} straddle {r['straddle_entry']:.2f} -> {r['straddle_1045']:.2f} "
                  f"ret {r['straddle_return']:+.1%}")
    if not rows:
        print("nothing reconstructed")
        return 1
    out = {}
    for sym in args.symbols:
        rs = [r for r in rows if r["symbol"] == sym and r["straddle_return"] is not None]
        if not rs:
            continue
        rets = [r["straddle_return"] for r in rs]
        out[sym] = {"n": len(rs), "mean_return": round(statistics.mean(rets), 4),
                    "median_return": round(statistics.median(rets), 4),
                    "hit_rate": round(sum(1 for x in rets if x > 0) / len(rets), 3),
                    "worst": round(min(rets), 4), "best": round(max(rets), 4),
                    "median_implied": round(statistics.median(r["implied_move"] for r in rs), 4),
                    "median_abs_move_1045": round(statistics.median(abs(r["move_to_1045"] or 0) for r in rs), 4)}
    print(json.dumps(out, indent=1))
    path = config.__file__.rsplit("alpha", 1)[0] + "state/nfp_straddle_backtest.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(), "rows": rows, "summary": out}, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
