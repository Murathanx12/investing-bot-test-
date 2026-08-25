"""NFP_TRADE -- the 4 September jobs-report trade, as a frozen contract with two gates.

    AAT_ACCOUNT_ROLE=dev python -m scripts.nfp_trade                 # dry: gates + structure, no order
    AAT_ACCOUNT_ROLE=dev python -m scripts.nfp_trade --live          # Thu 3 Sep after 15:45 ET only

What the evidence licenses (docs/FINDING_2026-08-25_STRADDLE_BACKTEST.md, addendum;
state/event_contract_basis/SPY_2026-09-04.json):

    28 releases, SPY 0DTE ATM straddle, prior close -> 10:45 ET:
    mean +16.8%, median +6.8%, hit 57%, 9 of the last 12 positive.
    A TAIL payoff: a few large release days carry it. Bounded by construction.
    The direction channel (headline surprise -> SPY) is DEAD (corr 0.03); the
    crowd's ladder informs WIDTH only.

So this is a WIDTH trade with a centre of zero, taken only when two things the
agent can measure at the close on 3 Sep both hold:

    GATE 1  the 0DTE straddle costs no more than the historical median implied
            move (0.77%) x 1.10  -- we do not pay up for a tail;
    GATE 2  the crowd is wide: the Kalshi payrolls ladder puts >= 25% of its
            mass in the two outer buckets  -- the crowd itself expects a tail.

The forecast handed to the ordinary engine is centre 0, sd = the standard
deviation of the 28 historical moves to 10:45 (1.23%), horizon 1 session; the
engine enumerates structures and sizes as it does for every other brain, so
the trade is not a special case anywhere downstream. `manage.py` liquidates
at 10:45 ET on judging day, which is exactly the window measured.

The policy hash below is the sha256 of THIS FILE. It is written into the
forecast's evidence; changing the rule changes the hash on the ledger row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha import config, runner
from alpha.brains.base import Forecast
from alpha.broker.alpaca import AlpacaPaper
from alpha.data import chain as chain_mod
from alpha.sources.belief import kalshi_markets
from scripts.event_contract_basis import ladder_to_buckets

RELEASE = "2026-09-04"
SYMBOL = "SPY"
MAX_IMPLIED = 0.0077 * 1.10
MIN_TAIL_MASS = 0.25
ET = ZoneInfo("America/New_York")


def policy_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def history() -> dict:
    root = config.__file__.rsplit("alpha", 1)[0]
    rows = [r for r in json.load(open(root + "state/nfp_straddle_backtest.json", encoding="utf-8"))["rows"]
            if r["symbol"] == SYMBOL and r.get("move_to_1045") is not None]
    moves = [r["move_to_1045"] for r in rows]
    return {"n": len(rows), "sd_move_1045": statistics.pstdev(moves), "median_implied": statistics.median(r["implied_move"] for r in rows),
            "mean_straddle_return": statistics.mean(r["straddle_return"] for r in rows),
            "hit": sum(1 for r in rows if r["straddle_return"] > 0) / len(rows)}


def gates(client) -> tuple[dict, bool]:
    snap = chain_mod.fetch(client, SYMBOL, expiry_from=RELEASE, expiry_to=RELEASE)
    implied = snap.implied_move(RELEASE)
    markets = [m for m in kalshi_markets("KXPAYROLLS", limit=100) if (m.get("close_time") or "").startswith(RELEASE)]
    buckets = ladder_to_buckets(markets) if markets else []
    tail_mass = (buckets[0]["p"] + buckets[-1]["p"]) if len(buckets) >= 2 else None
    g1 = implied is not None and implied <= MAX_IMPLIED
    g2 = tail_mass is not None and tail_mass >= MIN_TAIL_MASS
    return ({"implied_0dte": implied, "gate1_cheap_enough": g1, "max_implied": MAX_IMPLIED,
             "kalshi_tail_mass": tail_mass, "gate2_crowd_wide": g2, "min_tail_mass": MIN_TAIL_MASS,
             "n_kalshi_markets": len(markets), "spot": snap.spot, "quote_age_s": snap.median_quote_age_seconds},
            g1 and g2)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--force-window", action="store_true", help="ignore the 3 Sep 15:45-16:00 ET entry window (dry runs only)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    client = AlpacaPaper()
    h = history()
    g, ok = gates(client)
    now_et = datetime.now(timezone.utc).astimezone(ET)
    in_window = now_et.strftime("%Y-%m-%d") == "2026-09-03" and "15:45" <= now_et.strftime("%H:%M") <= "16:00"
    print(json.dumps({"history": h, "gates": g, "licensed": ok, "in_entry_window": in_window,
                      "now_et": now_et.isoformat(), "policy_hash": policy_hash()}, indent=1))
    if args.live and not in_window:
        print("REFUSED: --live outside the 3 Sep 15:45-16:00 ET entry window. The contract is the window.")
        return 2
    if not ok:
        print("REFUSED by gates; recorded as a refusal below.")
    forecast = Forecast(
        brain="nfp_event", symbol=SYMBOL, horizon_days=1.0, centre=0.0, sd=h["sd_move_1045"],
        conviction=1.0 if ok else 0.3,
        rationale=(f"Employment Situation {RELEASE} 08:30 ET. 28 releases: SPY moved sd {h['sd_move_1045']:.2%} to 10:45; "
                   f"0DTE straddle mean {h['mean_straddle_return']:+.0%}, hit {h['hit']:.0%}. Gates: implied "
                   f"{(g['implied_0dte'] or 0):.2%} <= {MAX_IMPLIED:.2%} [{g['gate1_cheap_enough']}], crowd tail mass "
                   f"{g['kalshi_tail_mass']} >= {MIN_TAIL_MASS} [{g['gate2_crowd_wide']}]. Width only; centre 0."),
        signal_shape="tail",
        evidence={"event_date": RELEASE, "policy_hash": policy_hash(), "gates": g, "history": h, "last_close": g["spot"]},
    )
    shadow = () if ok else ("nfp_event",)
    res = runner.run_pass(client, [forecast], expiry=RELEASE, dry_run=not args.live or not ok, shadow_brains=shadow)
    print(f"considered={res.considered} submitted={res.submitted} refused={res.refused} shadow={res.shadow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
