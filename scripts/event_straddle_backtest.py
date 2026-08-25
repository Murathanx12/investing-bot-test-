"""EVENT_STRADDLE_BACKTEST -- grade `event_move` on REAL option prices, 2024-2026.

    AAT_ACCOUNT_ROLE=dev python -m scripts.event_straddle_backtest --symbols NVDA AVGO ...

The question, asked the way the parent project asks it: before trusting the
prior that "this name moves more than its chain implies on prints", could the
last two years of ACTUAL straddle prices have answered? Alpaca serves daily bars
for EXPIRED contracts, so for every inferred print we can reconstruct the ATM
straddle at the nearest expiry after it, buy it at the close BEFORE the print
and sell it at the close AFTER, at real closes.

What is reported per event: implied move (straddle / spot at entry), realised
|move| (close-to-close across the print), straddle return, and whether the
realised move cleared the straddle's own break-even. Then per name and pooled:
median implied vs realised, hit rate, mean/median return, and the paired
t-stat of (realised - implied). It is a DIRECTION CHECK on our data with
closes rather than crossed quotes -- a real straddle pays the spread on both
sides and this does not -- so a small positive here is not an edge, and a
negative here is a warning the chain already knows about this name.

Every reconstructed contract, price and date is printed. Print the dates before
trusting the statistic.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

from alpha import config
from alpha.brains import event_move
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.sources import finnhub

DEFAULT = ["NVDA", "AVGO", "AMD", "TSLA", "META", "AAPL", "MSFT", "GOOGL", "AMZN", "PANW", "MU", "NIO"]


def next_friday(d: date) -> date:
    return d + timedelta(days=(4 - d.weekday()) % 7 or 7)


def atm_strike(spot: float, increment: float) -> float:
    return round(spot / increment) * increment


def option_bars(client, symbols: list[str], start: str, end: str) -> dict:
    page = client._request("GET", "/v1beta1/options/bars", base=config.data_url(),
                           params={"symbols": ",".join(symbols), "timeframe": "1Day",
                                   "start": start, "end": end, "limit": 1000})
    return (page or {}).get("bars") or {}


def one_event(client, symbol: str, bars_by_day: dict[str, float], days: list[str],
              event_day: str, move: float) -> dict | None:
    i = days.index(event_day)
    if i < 2 or i + 1 >= len(days):
        return None
    # The print lands between close[i-1] and close[i] (amc the day before, or bmo
    # on the day) -- the inferred `event_day` is the first close that reflects it.
    entry_day, exit_day = days[i - 1], days[i]
    spot = bars_by_day[entry_day]
    expiry = next_friday(date.fromisoformat(event_day))
    if expiry == date.fromisoformat(event_day):
        expiry = next_friday(expiry)
    for inc in (2.5, 5.0, 1.0, 10.0):
        k = atm_strike(spot, inc)
        syms = [f"{symbol}{expiry:%y%m%d}{r}{int(round(k * 1000)):08d}" for r in "CP"]
        try:
            bars = option_bars(client, syms, entry_day, exit_day)
        except BrokerRefusal:
            continue
        c_, p_ = bars.get(syms[0]) or [], bars.get(syms[1]) or []
        cd = {b["t"][:10]: b for b in c_}
        pd = {b["t"][:10]: b for b in p_}
        if entry_day in cd and entry_day in pd and exit_day in cd and exit_day in pd:
            entry = cd[entry_day]["c"] + pd[entry_day]["c"]
            exit_ = cd[exit_day]["c"] + pd[exit_day]["c"]
            if entry <= 0:
                continue
            return {
                "symbol": symbol, "event_day": event_day, "entry_day": entry_day, "expiry": expiry.isoformat(),
                "strike": k, "spot_entry": spot, "straddle_entry": round(entry, 2), "straddle_exit": round(exit_, 2),
                "implied_move": round(entry / spot, 4), "realised_abs_move": round(abs(move), 4),
                "signed_move": round(move, 4), "straddle_return": round(exit_ / entry - 1.0, 4),
                "cleared_breakeven": abs(move) > entry / spot,
                "volume_entry": int(cd[entry_day].get("v", 0) + pd[entry_day].get("v", 0)),
            }
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=DEFAULT)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    events: list[dict] = []
    for sym in args.symbols:
        bars = _daily_bars(client, sym, 800)
        bars = [b for b in bars if b["t"][:10] >= "2024-02-01"]
        if len(bars) < 120:
            print(f"{sym}: {len(bars)} bars since 2024-02, skipping")
            continue
        days = [b["t"][:10] for b in bars]
        by_day = {b["t"][:10]: float(b["c"]) for b in bars}
        served = [x["period"] for x in finnhub.earnings_periods(sym, limit=12) if x.get("period")]
        periods = event_move.extend_periods(served, years=3)
        inferred = event_move.event_days_inferred(bars, periods)
        got = 0
        for e in inferred:
            if e["event_day"] < "2024-02-20":
                continue
            row = one_event(client, sym, by_day, days, e["event_day"], e["move"])
            if row:
                events.append(row)
                got += 1
                print(f"  {sym} {row['event_day']} K={row['strike']:<8} straddle {row['straddle_entry']:>7.2f} -> "
                      f"{row['straddle_exit']:>7.2f}  implied {row['implied_move']:6.2%}  realised "
                      f"{row['signed_move']:+7.2%}  ret {row['straddle_return']:+7.1%}")
        print(f"{sym}: {got} of {len(inferred)} inferred prints reconstructed\n")

    if not events:
        print("no events reconstructed -- an absence, not a result")
        return 1

    def summ(rows: list[dict]) -> dict:
        r = [x["straddle_return"] for x in rows]
        d = [x["realised_abs_move"] - x["implied_move"] for x in rows]
        n = len(r)
        t = statistics.mean(d) / (statistics.pstdev(d) / math.sqrt(n)) if n > 2 and statistics.pstdev(d) > 0 else None
        return {"n": n, "median_implied": round(statistics.median(x["implied_move"] for x in rows), 4),
                "median_realised_abs": round(statistics.median(x["realised_abs_move"] for x in rows), 4),
                "hit_rate_cleared_breakeven": round(sum(x["cleared_breakeven"] for x in rows) / n, 3),
                "mean_straddle_return": round(statistics.mean(r), 4), "median_straddle_return": round(statistics.median(r), 4),
                "paired_t_realised_minus_implied": round(t, 2) if t is not None else None}

    out = {"pooled": summ(events), "by_symbol": {}}
    for sym in sorted({e["symbol"] for e in events}):
        out["by_symbol"][sym] = summ([e for e in events if e["symbol"] == sym])
    print(json.dumps(out, indent=1))
    path = config.__file__.rsplit("alpha", 1)[0] + "state/event_straddle_backtest.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(), "events": events, "summary": out}, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
