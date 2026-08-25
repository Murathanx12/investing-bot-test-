"""BELIEF_RECORDER -- a time series of what the crowd believes, so velocity can be graded later.

    python -m scripts.belief_recorder            # one snapshot, appended to state/belief_series.jsonl

BELIEF_SHOCK (review item 6) needs d(probability)/dt, not a level. Nothing in
this repo stores the level over time yet: `belief_vs_chain` records one reading
per hour for three equity thresholds and nothing about tariffs, the Fed or the
payrolls ladder. This records a watchlist every time the loop calls it:

    polymarket   open markets matching each query, with price and 24h volume
    kalshi       the payrolls ladder and the September Fed decision series

One JSON line per market per snapshot. No brain reads this yet -- a brain built
before its series exists would be tuned to a guess. The grade, when the series
is long enough, is whether large |dp/dt| with small equity reaction precedes
equity movement (under-reaction) or reversal (over-reaction).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from alpha import config
from alpha.sources.belief import kalshi_markets, polymarket_search
from alpha.sources.http import SourceRefusal

POLYMARKET_QUERIES = ["tariff", "Fed rate", "Nvidia", "recession", "China", "Iran", "Tesla"]
KALSHI_SERIES = ["KXPAYROLLS", "KXFEDDECISION", "KXFED"]


def snapshot() -> list[dict]:
    ts = datetime.now(timezone.utc).isoformat()
    out = []
    for q in POLYMARKET_QUERIES:
        try:
            for m in polymarket_search(q, limit=15):
                belief = m.get("belief") or {}
                out.append({"ts_utc": ts, "source": "polymarket", "query": q, "id": m.get("slug"),
                            "title": m.get("question"), "p_yes": belief.get("Yes"), "belief": belief,
                            "liquidity": m.get("liquidity"), "volume_24h": m.get("volume_24h"), "end": m.get("end_date")})
        except (SourceRefusal, Exception) as exc:                       # noqa: BLE001
            out.append({"ts_utc": ts, "source": "polymarket", "query": q, "refusal": str(exc)[:120]})
    for s in KALSHI_SERIES:
        try:
            for m in kalshi_markets(s, limit=60):
                out.append({"ts_utc": ts, "source": "kalshi", "series": s, "id": m.get("ticker"), "title": m.get("title"),
                            "p_yes": m.get("last"), "yes_bid": m.get("yes_bid"), "yes_ask": m.get("yes_ask"),
                            "volume": m.get("volume"), "end": m.get("close_time")})
        except (SourceRefusal, Exception) as exc:                       # noqa: BLE001
            out.append({"ts_utc": ts, "source": "kalshi", "series": s, "refusal": str(exc)[:120]})
    return out


def main() -> int:
    config.load_env()
    rows = snapshot()
    path = config.__file__.rsplit("alpha", 1)[0] + "state/belief_series.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    ok = sum(1 for r in rows if "refusal" not in r)
    print(f"belief snapshot: {ok} markets recorded, {len(rows) - ok} refusals -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
