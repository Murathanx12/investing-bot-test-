"""UNCERTAINTY RELAY (RELATIVE_EVENT_VOL_v1) -- where is the NVDA print CHEAPEST to own?

    AAT_ACCOUNT_ROLE=dev python -m scripts.uncertainty_relay NVDA --event 2026-08-26 \
        --peers AMD AVGO MU SMH SOXX TSM ARM --expiry 2026-08-28

Not "are NVDA options cheap?" but "where has the market priced the SAME
information least carefully?". Guttormsen (2026) finds an earnings print
moves the implied vols of industry peers, and the effect persists. So:

  1. HISTORY: on every one of the originator's SEC-dated prints, measure each
     peer's close-to-close move across the same session. That is the EMPIRICAL
     edge weight -- no LLM causal graph, a measured co-movement.
  2. TODAY: read each peer's chain at the expiry spanning the print; strip the
     event variance against the next expiry where possible; compare the peer's
     conditional history (jump sd on originator print days) to what its chain
     charges.
  3. RANK by (our conditional jump sd) / (market jump sd). Above 1: the relay is
     underpriced there; the expression belongs in the peer, not the originator.

Every number is written to state/relay/<originator>_<event>.json. A ratio is a
candidate, never an order: the structure engine still has to clear the spread.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone

from alpha import config, surface
from alpha.brains import event_move
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper
from alpha.data import chain as chain_mod

RECENT = 8


def peer_moves(bars: list[dict], event_days: list[str]) -> list[dict]:
    idx = {b["t"][:10]: i for i, b in enumerate(bars)}
    closes = [float(b["c"]) for b in bars]
    out = []
    for d in event_days:
        i = idx.get(d)
        if i is None or i == 0:
            continue
        out.append({"event_day": d, "move": round(math.log(closes[i] / closes[i - 1]), 5)})
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("originator")
    p.add_argument("--event", required=True, help="first close that reflects the print, YYYY-MM-DD")
    p.add_argument("--peers", nargs="*", default=["AMD", "AVGO", "MU", "SMH", "SOXX", "TSM", "ARM", "QQQ"])
    p.add_argument("--expiry", required=True, help="first expiry after the print")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()

    orig_bars = _daily_bars(client, args.originator, 800)
    events = event_move.event_days_from_sec(orig_bars, args.originator)
    days = [e["event_day"] for e in events][-RECENT:]
    print(f"{args.originator}: {len(events)} SEC prints, using last {len(days)}: {days}")
    back_expiry = (datetime.fromisoformat(args.expiry) + timedelta(days=7)).strftime("%Y-%m-%d")

    rows = []
    for sym in [args.originator] + args.peers:
        bars = _daily_bars(client, sym, 800)
        mv = peer_moves(bars, days)
        if len(mv) < 4:
            print(f"  {sym}: only {len(mv)} matched sessions, skipped")
            continue
        jump_sd = math.sqrt(sum(m["move"] ** 2 for m in mv) / len(mv))
        mean_abs = statistics.mean(abs(m["move"]) for m in mv)
        row = {"symbol": sym, "n": len(mv), "cond_jump_sd": round(jump_sd, 4), "cond_mean_abs": round(mean_abs, 4),
               "moves": mv}
        try:
            snap = chain_mod.fetch(client, sym, expiry_from=args.expiry, expiry_to=back_expiry)
            reading = surface.read(snap, event_before=args.expiry)
            row["surface"] = {k: v for k, v in reading.items() if k != "expiries"}
            row["front"] = reading["expiries"][0] if reading["expiries"] else None
            strip = reading.get("strip")
            mkt = strip["market_jump_sd"] if strip else None
            if mkt is None and row["front"]:
                # no back expiry: fall back to the raw implied move as a sd (0.8 * sd ~ E|x|)
                mkt = row["front"]["implied_move"] / 0.8
                row["market_source"] = "raw_front_implied"
            else:
                row["market_source"] = "variance_strip"
            row["market_jump_sd"] = round(mkt, 4) if mkt else None
            row["relay_ratio"] = round(jump_sd / mkt, 3) if mkt else None
        except Exception as exc:                                    # noqa: BLE001
            row["chain_refusal"] = f"{type(exc).__name__}: {str(exc)[:140]}"
        rows.append(row)
        print(f"  {sym:5} n={row['n']} cond_jump_sd {jump_sd:6.2%} market {row.get('market_jump_sd') or float('nan'):6.2%} "
              f"({row.get('market_source', '-')}) ratio {row.get('relay_ratio') or float('nan'):5.2f} "
              f"shape {((row.get('front') or {}).get('shape')) or '-'}")

    ranked = sorted([r for r in rows if r.get("relay_ratio")], key=lambda r: -r["relay_ratio"])
    print("\nRELAY RANK (history / market, >1 = the print is cheaper to own here):")
    for r in ranked:
        print(f"  {r['symbol']:5} {r['relay_ratio']:.2f}")
    root = config.__file__.rsplit("alpha", 1)[0] + "state/relay"
    import os
    os.makedirs(root, exist_ok=True)
    path = f"{root}/{args.originator}_{args.event}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(), "originator": args.originator,
                   "event": args.event, "expiry": args.expiry, "print_days_used": days, "rows": rows,
                   "rank": [r["symbol"] for r in ranked]}, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
