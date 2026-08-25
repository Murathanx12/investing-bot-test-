"""ATTENTION -> NEXT-DAY RETURN, on our universe, 2024-08 .. now. A receipt.

    AAT_ACCOUNT_ROLE=dev python -m scripts.attention_backtest

Cookson, Lu, Mullins, Niessner (JFE 2024) find social ATTENTION predicts
NEGATIVE next-day returns while sentiment predicts positive ones. We cannot read
Twitter, but Wikipedia pageviews are a free attention count with history, so
the question this script answers is the cheap one we can ask before trusting
the attention brains: on the names we trade, does a pageview spike (z > 2
against the trailing 30 days) change the NEXT day's return, its sign or its
size?

First run 2026-08-25 (12 names, 5,844 name-days):
    all          mean +12.7 bp  t 3.19   mean|r| 207 bp
    z > 2 (410)  mean  -7.9 bp  t -0.40  mean|r| 262 bp     <- +27% wider
    z > 3 (212)  mean -15.7 bp  t -0.56  mean|r| 270 bp
    z < 0        mean +14.8 bp  t 3.16   mean|r| 195 bp
Attention WIDENS the next day and weakly tilts it negative. That is the shape
the attention brains assume (sigma up, no sign), now with a number behind it.
Same-source caveat: pageviews are a daily aggregate that lags a day, so this
is attention as of the prior day's total.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources.attention import WIKI, WIKI_ARTICLE
from alpha.sources.http import get_json

DEFAULT = ["TSLA", "NVDA", "AVGO", "AMD", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "NIO", "PANW", "MU"]


def stat(rows: list[tuple]) -> dict:
    r = [x[3] for x in rows]
    n = len(r)
    if n < 5:
        return {"n": n}
    m, s = statistics.mean(r), statistics.pstdev(r)
    return {"n": n, "mean_bp": round(m * 1e4, 1), "t": round(m / (s / math.sqrt(n)), 2) if s else None,
            "mean_abs_bp": round(statistics.mean(abs(x) for x in r) * 1e4, 1),
            "hit_rate_up": round(sum(1 for x in r if x > 0) / n, 3)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=DEFAULT)
    p.add_argument("--start", default="20240801")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    end = datetime.now(timezone.utc).strftime("%Y%m%d")
    rows = []
    for sym in args.symbols:
        art = WIKI_ARTICLE.get(sym)
        if not art:
            print(f"{sym}: no article mapped, skipped")
            continue
        data, _ = get_json(f"{WIKI}/{art}/daily/{args.start}/{end}")
        views = {it["timestamp"][:8]: int(it["views"]) for it in data.get("items", [])}
        bars = client.stock_bars(sym, start=f"{args.start[:4]}-{args.start[4:6]}-{args.start[6:]}",
                                 timeframe="1Day", adjustment="all")["bars"][sym]
        closes = [(b["t"][:10].replace("-", ""), b["c"]) for b in bars]
        days = [d for d, _ in closes]
        for i in range(30, len(closes) - 1):
            d = days[i]
            if d not in views:
                continue
            base = [views[x] for x in days[i - 30:i] if x in views]
            if len(base) < 20:
                continue
            sd = statistics.pstdev(base) or 1.0
            z = (views[d] - statistics.mean(base)) / sd
            rows.append((sym, d, z, math.log(closes[i + 1][1] / closes[i][1])))
    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "symbols": args.symbols,
        "all": stat(rows), "z_gt_2": stat([x for x in rows if x[2] > 2]),
        "z_gt_3": stat([x for x in rows if x[2] > 3]), "z_lt_0": stat([x for x in rows if x[2] < 0]),
        "note": "next-day log return after a Wikipedia pageview z-score vs trailing 30d; pageviews lag ~1 day",
    }
    print(json.dumps(out, indent=1))
    path = config.__file__.rsplit("alpha", 1)[0] + "state/attention_backtest.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
