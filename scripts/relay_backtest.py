"""RELAY_BACKTEST -- did owning an originator's print in its PEERS pay, on real closes?

    AAT_ACCOUNT_ROLE=dev python -m scripts.relay_backtest --originators NVDA AVGO AMD MU

`scripts.uncertainty_relay` ranks peers by (conditional history / market jump sd)
for ONE upcoming print. Before that ranking sizes anything, the same idea has to
be graded on the past: for every SEC-dated print of each originator, buy each
peer's ATM straddle at the close before and sell at the close after (the same
`one_event` reconstruction as the single-name backtest), and ask

    1. unconditionally: which peers' straddles paid on originator print days?
    2. walk-forward: does the RATIO (peer's prior RMS move on originator prints
       / peer's implied at entry) sort the peer straddle returns?
    3. against the originator's own straddle on the same event: is the relay
       leg a better expression than the source?

A peer that prints itself within two sessions of the originator is skipped for
that event -- otherwise the "relay" is just the peer's own print. Closes, not
crossed quotes; every row is in the receipt.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone

from alpha import config
from alpha.brains import event_move
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources.http import SourceRefusal
from scripts.event_straddle_backtest import one_event

PEERS = ["NVDA", "AMD", "AVGO", "MU", "ARM", "TSM", "SMH", "SOXX", "QQQ"]
RECENT = 8


def _stats(v: list[float]) -> dict:
    v = [z for z in v if z is not None]
    if not v:
        return {"n": 0}
    m, sd = statistics.mean(v), statistics.pstdev(v)
    return {"n": len(v), "mean": round(m, 3), "median": round(statistics.median(v), 3),
            "hit": round(sum(1 for z in v if z > 0) / len(v), 2),
            "t": round(m / (sd / math.sqrt(len(v))), 2) if sd and len(v) > 2 else None}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--originators", nargs="*", default=["NVDA", "AVGO", "AMD", "MU"])
    p.add_argument("--peers", nargs="*", default=PEERS)
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    bars: dict[str, list[dict]] = {}
    own_prints: dict[str, set[str]] = {}
    for sym in set(args.originators) | set(args.peers):
        bars[sym] = [b for b in _daily_bars(client, sym, 800) if b["t"][:10] >= "2024-02-01"]
        try:
            own_prints[sym] = {e["event_day"] for e in event_move.event_days_from_sec(bars[sym], sym)}
        except SourceRefusal:
            own_prints[sym] = set()
        print(f"{sym}: {len(bars[sym])} bars, {len(own_prints[sym])} own prints")

    rows = []
    for orig in args.originators:
        events = sorted(own_prints[orig])
        for ev_day in events:
            if ev_day < "2024-02-20":
                continue
            for peer in args.peers:
                days = [b["t"][:10] for b in bars[peer]]
                if ev_day not in days:
                    continue
                i = days.index(ev_day)
                near = set(days[max(i - 2, 0):i + 3])
                if peer != orig and (own_prints[peer] & near):
                    continue                       # the peer's own print would masquerade as relay
                by_day = {b["t"][:10]: float(b["c"]) for b in bars[peer]}
                move = math.log(by_day[ev_day] / by_day[days[i - 1]])
                row = one_event(client, peer, by_day, days, ev_day, move, "relay")
                if row:
                    row.update({"originator": orig, "peer": peer, "is_originator": peer == orig})
                    rows.append(row)
                    print(f"  {orig} {ev_day} via {peer:5} implied {row['implied_move']:6.2%} realised "
                          f"{row['signed_move']:+6.2%} straddle {row['straddle_return']:+.1%}")

    if not rows:
        print("nothing reconstructed")
        return 1

    # walk-forward: peer's prior RMS move on this originator's prints vs implied
    rows.sort(key=lambda r: r["event_day"])
    hist: dict[tuple[str, str], list[float]] = {}
    pool: list[float] = []
    for r in rows:
        key = (r["originator"], r["peer"])
        prior = hist.get(key, [])[-RECENT:]
        if len(prior) >= 3:
            rms = math.sqrt(sum(m * m for m in prior) / len(prior))
            r["relay_ratio_wf"] = round(rms / (r["implied_move"] / 0.8), 3)
            if len(pool) >= 9:
                s = sorted(pool)
                lo, hi = s[len(s) // 3], s[2 * len(s) // 3]
                r["bucket"] = "top" if r["relay_ratio_wf"] > hi else "bottom" if r["relay_ratio_wf"] < lo else "middle"
            pool.append(r["relay_ratio_wf"])
        hist.setdefault(key, []).append(r["signed_move"])

    summary = {"n_rows": len(rows), "by_originator_peer": {}, "peer_vs_originator_same_event": {},
               "walkforward_ratio_buckets": {}}
    for orig in args.originators:
        for peer in args.peers:
            rs = [r for r in rows if r["originator"] == orig and r["peer"] == peer]
            if len(rs) >= 3:
                summary["by_originator_peer"][f"{orig}->{peer}"] = {
                    **_stats([r["straddle_return"] for r in rs]),
                    "median_implied": round(statistics.median(r["implied_move"] for r in rs), 4),
                    "median_realised": round(statistics.median(r["realised_abs_move"] for r in rs), 4)}
    # paired: peer straddle minus originator straddle on the same event
    by_event = {}
    for r in rows:
        by_event.setdefault((r["originator"], r["event_day"]), {})[r["peer"]] = r["straddle_return"]
    for peer in args.peers:
        diffs = [d[peer] - d[o] for (o, _), d in by_event.items() if peer in d and o in d and peer != o]
        if len(diffs) >= 3:
            summary["peer_vs_originator_same_event"][peer] = _stats(diffs)
    for b in ("top", "middle", "bottom"):
        rs = [r for r in rows if r.get("bucket") == b and not r["is_originator"]]
        if rs:
            summary["walkforward_ratio_buckets"][b] = _stats([r["straddle_return"] for r in rs])
    summary["all_relay_legs"] = _stats([r["straddle_return"] for r in rows if not r["is_originator"]])
    summary["all_originator_legs"] = _stats([r["straddle_return"] for r in rows if r["is_originator"]])
    print(json.dumps(summary, indent=1))
    path = config.__file__.rsplit("alpha", 1)[0] + "state/relay_backtest.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(), "rows": rows, "summary": summary}, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
