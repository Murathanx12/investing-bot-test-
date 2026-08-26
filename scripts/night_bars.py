"""NIGHT LAB bar cache -- pull the universe's daily bars ONCE, reuse for every night experiment.

    python -m scripts.night_bars [--years 2.9]

Writes `state/night_shadow/bars_daily.json.gz` ({symbol: [bar, ...]}) plus a
manifest. Night experiments read this file and never touch the broker. The bar
pull is the only network call the night lab makes to Alpaca, and it is
read-only market data on the DEV keys (never the competition account).
"""
from __future__ import annotations

import argparse, gzip, json, logging, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper

NIGHT = Path("state") / "night_shadow"
BARS = NIGHT / "bars_daily.json.gz"
BENCH = ("QQQ", "IWM", "XBI", "SPY", "SMH", "SOXX", "EWT", "EWY", "EWJ")


def load() -> dict[str, list[dict]]:
    if not BARS.exists():
        raise FileNotFoundError(f"{BARS} missing -- run python -m scripts.night_bars")
    with gzip.open(BARS, "rt", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=float, default=2.9)
    p.add_argument("--extra", default="", help="comma list of extra symbols")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    NIGHT.mkdir(parents=True, exist_ok=True)
    members = universe.load()
    syms = sorted({m.symbol for m in members if not m.etf_like} | set(BENCH) | {s for s in args.extra.split(",") if s})
    start = (datetime.now(timezone.utc) - timedelta(days=int(args.years * 365) + 250)).strftime("%Y-%m-%d")
    t0 = time.time()
    bars = AlpacaPaper().stock_bars_multi(syms, start=start)
    with gzip.open(BARS, "wt", encoding="utf-8") as f:
        json.dump(bars, f)
    (NIGHT / "bars_manifest.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(), "start": start, "symbols": len(bars),
        "bars": sum(len(v) for v in bars.values()), "seconds": round(time.time() - t0), "feed": "sip",
        "adjustment": "all"}, indent=1), encoding="utf-8")
    print(f"cached {len(bars)} symbols, {sum(len(v) for v in bars.values())} bars in {time.time()-t0:.0f}s -> {BARS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
