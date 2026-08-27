"""INDEX_PREMIUM -- is short-dated index premium rich or cheap, held to expiry?

THE QUESTION THIS EXISTS TO SETTLE
==================================
On 27 Aug the live chain code was found to understate the market's own quoted
width by 15% and to price a 1-session option at sqrt(3) of its real life
(docs/FINDING_2026-08-27_THE_CHAIN_WAS_NEVER_CHEAP.md). Both books had bought
five index straddles on the strength of that arithmetic and were down 5-7%.

Fixing the arithmetic says the chain is NOT cheap. It does not say the chain is
RICH -- and "so now sell premium" would be the same mistake with the sign
flipped. This measures it instead, on our own bars, with costs.

WHAT IT MEASURES
================
Every week, buy the ATM straddle on the nearest Friday expiry at the close four
sessions before it, and HOLD TO EXPIRY, settling at intrinsic against the
settlement close. No exit quote is needed and none is invented: intrinsic at
expiry is exactly what a held position collects, for buyer and seller alike.

    implied move   = straddle premium / spot        (an identity at the money --
                                                     no 0.85, no multiplier)
    realised move  = |close_expiry / close_entry - 1|
    buyer's P&L    = intrinsic - premium - entry haircut
    seller's P&L   = premium - intrinsic - entry haircut

The seller is the buyer's mirror MINUS the same haircut, not plus it. Both sides
cross the spread once, and the spread is a cost to whoever pays it.

WHAT IT REFUSES TO CONCLUDE
===========================
A mean. Short premium's whole risk lives in the tail, so the mean of a
short-straddle series is the least informative number in it -- 35 rows of 46,361
carried 81% of a result in this project once already. So this prints the worst
weeks and the loss quantiles BEFORE the average, and reports UNRESOLVED when the
mean sits inside the sample's own MDE. An unresolvable positive mean is not a
strategy.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from datetime import date, timedelta
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

#: Index ETFs first -- they are what both books actually bought, and their chains
#: are the tightest, so a result here is not a liquidity artefact.
DEFAULT = ["SPY", "QQQ", "IWM"]

#: Measured round-trip haircut on this account's real fills, deduped to unique
#: orders and marked within 90 minutes: 2.6% of premium. ONE side of it is
#: charged to each of buyer and seller, because each crosses once.
HAIRCUT_PER_SIDE = 0.013

STRIKE_INCREMENTS = (1.0, 5.0, 2.5, 10.0)

#: Sessions before expiry at which the straddle is bought. Fixed once, by
#: convention (a Monday close in a normal week), and NOT tuned -- an entry day
#: chosen after seeing the answer is a fitted parameter wearing a convention's
#: clothes.
ENTRY_SESSIONS_BEFORE = 4


def _fridays(days: list[str]) -> list[date]:
    d = date.fromisoformat(days[0])
    d += timedelta(days=(4 - d.weekday()) % 7)
    last = date.fromisoformat(days[-1])
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def _option_bars(client, symbols: list[str], start: str, end: str) -> dict:
    page = client._request("GET", "/v1beta1/options/bars", base=config.data_url(),
                           params={"symbols": ",".join(symbols), "timeframe": "1Day",
                                   "start": start, "end": end, "limit": 1000})
    return (page or {}).get("bars") or {}


def one_week(client, symbol: str, by_day: dict, days: list[str],
             entry_day: str, expiry: date) -> dict | None:
    """One held-to-expiry straddle. None when the chain cannot be reconstructed."""
    exp_s = expiry.isoformat()
    if exp_s not in by_day:      # expiry must be a session we hold a real close for
        return None
    spot = by_day[entry_day]
    settle = by_day[exp_s]
    for inc in STRIKE_INCREMENTS:
        k = round(spot / inc) * inc
        syms = [symbol + expiry.strftime("%y%m%d") + r + "%08d" % round(k * 1000) for r in "CP"]
        try:
            bars = _option_bars(client, syms, entry_day, exp_s)
        except BrokerRefusal:
            continue
        cd = {b["t"][:10]: b for b in (bars.get(syms[0]) or [])}
        pd = {b["t"][:10]: b for b in (bars.get(syms[1]) or [])}
        if entry_day not in cd or entry_day not in pd:
            continue
        premium = cd[entry_day]["c"] + pd[entry_day]["c"]
        if premium <= 0:
            continue
        intrinsic = max(0.0, settle - k) + max(0.0, k - settle)
        haircut = premium * HAIRCUT_PER_SIDE
        return {
            "symbol": symbol, "entry_day": entry_day, "expiry": exp_s,
            "sessions": sum(1 for d in days if entry_day < d <= exp_s),
            "strike": k, "spot_entry": round(spot, 2), "spot_settle": round(settle, 2),
            "premium": round(premium, 2), "intrinsic": round(intrinsic, 2),
            "implied_move": round(premium / spot, 5),
            "realised_move": round(abs(settle / spot - 1.0), 5),
            "buyer_pnl_pct": round((intrinsic - premium - haircut) / premium, 4),
            "seller_pnl_pct": round((premium - intrinsic - haircut) / premium, 4),
            "volume_entry": int(cd[entry_day].get("v", 0) + pd[entry_day].get("v", 0)),
        }
    return None


def _summ(rows: list[dict], key: str) -> dict:
    r = [x[key] for x in rows]
    n = len(r)
    mean = st.mean(r)
    sd = st.stdev(r) if n > 1 else 0.0
    srt = sorted(r)
    # 80% power, two-sided 5%: the smallest per-week return this sample resolves.
    mde = 2.8 * sd / math.sqrt(n) if n > 1 and sd > 0 else float("inf")
    return {"n": n, "mean": round(mean, 4), "median": round(st.median(r), 4),
            "sd": round(sd, 4),
            "t": round(mean / (sd / math.sqrt(n)), 2) if n > 1 and sd > 0 else 0.0,
            "mde_per_week": round(mde, 4) if mde != float("inf") else None,
            "hit_rate": round(sum(1 for x in r if x > 0) / n, 3),
            "worst": round(srt[0], 4),
            "p05": round(srt[max(0, int(0.05 * n) - 1)], 4),
            "p25": round(srt[max(0, int(0.25 * n) - 1)], 4),
            "best": round(srt[-1], 4),
            "resolvable": bool(abs(mean) > mde)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=DEFAULT)
    p.add_argument("--since", default="2024-02-01")
    p.add_argument("--out", default="state/index_premium_backtest.json")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    rows: list[dict] = []
    for sym in args.symbols:
        page = client._request("GET", "/v2/stocks/" + sym + "/bars", base=config.data_url(),
                               params={"timeframe": "1Day", "start": args.since,
                                       "adjustment": "all", "limit": 10000,
                                       "feed": config.stock_feed()})
        bars = (page or {}).get("bars") or []
        if len(bars) < 60:
            print(sym + ": " + str(len(bars)) + " bars since " + args.since + " -- skipping")
            continue
        days = [b["t"][:10] for b in bars]
        by_day = {b["t"][:10]: float(b["c"]) for b in bars}
        got = 0
        for fri in _fridays(days):
            before = [d for d in days if d < fri.isoformat()]
            if len(before) < ENTRY_SESSIONS_BEFORE:
                continue
            row = one_week(client, sym, by_day, days, before[-ENTRY_SESSIONS_BEFORE], fri)
            if row:
                rows.append(row)
                got += 1
        print(f"{sym}: {got} weekly straddles reconstructed  ({days[0]} -> {days[-1]})")

    if not rows:
        print("nothing reconstructed -- an absence, not a result")
        return 1

    out = {
        "haircut_per_side": HAIRCUT_PER_SIDE,
        "entry_sessions_before_expiry": ENTRY_SESSIONS_BEFORE,
        "n_weeks": len(rows),
        "first": min(r["entry_day"] for r in rows),
        "last": max(r["entry_day"] for r in rows),
        "pooled": {"buyer": _summ(rows, "buyer_pnl_pct"), "seller": _summ(rows, "seller_pnl_pct")},
        "by_symbol": {s: {"buyer": _summ([r for r in rows if r["symbol"] == s], "buyer_pnl_pct"),
                          "seller": _summ([r for r in rows if r["symbol"] == s], "seller_pnl_pct")}
                      for s in sorted({r["symbol"] for r in rows})},
        "rows": rows,
    }

    worst5 = sorted(rows, key=lambda r: r["seller_pnl_pct"])[:5]
    print("\nTHE TAIL FIRST -- the five worst weeks for the SELLER:")
    for r in worst5:
        print(f"  {r['symbol']} {r['entry_day']} -> {r['expiry']}  implied {r['implied_move']:.2%}  "
              f"realised {r['realised_move']:.2%}  seller {r['seller_pnl_pct']:+.1%}")

    b, s = out["pooled"]["buyer"], out["pooled"]["seller"]
    print(f"\n{'':10} {'n':>4} {'mean':>8} {'median':>8} {'hit':>6} {'t':>6} "
          f"{'MDE/wk':>8} {'worst':>8} {'p05':>8}")
    print("-" * 76)
    for label, d in (("BUYER", b), ("SELLER", s)):
        mde = f"{d['mde_per_week']:.1%}" if d["mde_per_week"] is not None else "  n/a"
        print(f"{label:10} {d['n']:>4} {d['mean']:>7.1%} {d['median']:>7.1%} {d['hit_rate']:>5.0%} "
              f"{d['t']:>6.2f} {mde:>8} {d['worst']:>7.1%} {d['p05']:>7.1%}")
    print("-" * 76)
    for sym, d in out["by_symbol"].items():
        rich = sum(1 for r in rows if r["symbol"] == sym and r["implied_move"] > r["realised_move"])
        print(f"{sym:10} {d['seller']['n']:>4} seller mean {d['seller']['mean']:>7.1%}  "
              f"t {d['seller']['t']:>5.2f}  worst {d['seller']['worst']:>7.1%}  "
              f"implied>realised {rich}/{d['seller']['n']}")

    if not s["resolvable"]:
        verdict = (f"UNRESOLVED: the seller's mean {s['mean']:+.1%}/week sits inside this sample's "
                   f"own MDE of {s['mde_per_week']:.1%}. {len(rows)} weeks cannot settle it.")
    elif s["mean"] > 0:
        verdict = (f"SELLER POSITIVE and resolvable: {s['mean']:+.1%}/week, t {s['t']:.2f}, "
                   f"worst week {s['worst']:+.1%}, 5th percentile {s['p05']:+.1%}. "
                   f"DEFINED RISK ONLY -- an undefined short straddle is not licensed by a mean.")
    else:
        verdict = (f"BUYER POSITIVE: {b['mean']:+.1%}/week after costs, t {b['t']:.2f}. "
                   f"The chain is genuinely cheap on this sample.")
    out["verdict"] = verdict
    print("\nVERDICT: " + verdict)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("receipt: " + args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
