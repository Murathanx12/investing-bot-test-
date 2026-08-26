"""Daily candidate report over the WHOLE universe -- with its own bias audit.

    python -m scripts.candidates [--sessions 3] [--enrich 40]

Who printed in the last N sessions (Finnhub's market-wide earnings calendar,
one call), confirmed against SEC 8-K Item 2.02 where the filer is covered, and
run through the `post_event_drift` brain -- the one mechanism with a positive
t -- over HIGH_DISPERSION_US_v1 instead of fifteen mega-caps. Every candidate
carries its dollar-volume bucket, market cap and industry (Finnhub profile,
candidates only), whether it was in the OLD universe, and whether it is one of
the CONTROL holdings.

The report ends with `UNIVERSE_COLLAPSE` instrumentation: if the candidates
are mostly the old fifteen or mostly mega, the report says so in capitals,
however well they scored. Fame adds no score here; nothing in this file reads
a ticker's name before ranking it.

Output: `state/candidates/<date>.json` and a table.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config, universe
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources import finnhub
from alpha.sources.http import SourceRefusal

logger = logging.getLogger(__name__)
OUT = Path("state") / "candidates"


def recent_printers(sessions: int) -> dict[str, dict]:
    """Symbols on the market-wide earnings calendar in the last `sessions` weekdays."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=sessions + (2 if sessions >= 3 else 1) + 1)
    rows = finnhub.earnings_calendar(start=start.isoformat(), end=today.isoformat())
    out = {}
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        if sym:
            out[sym] = {"date": r.get("date"), "hour": r.get("hour"), "eps_actual": r.get("epsActual"),
                        "eps_estimate": r.get("epsEstimate"), "revenue_actual": r.get("revenueActual"),
                        "revenue_estimate": r.get("revenueEstimate")}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", type=int, default=3)
    p.add_argument("--enrich", type=int, default=40, help="Finnhub profile calls for the top candidates")
    p.add_argument("--horizon", type=float, default=3.0)
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    config.load_env()
    client = AlpacaPaper()
    members = universe.load()
    by_sym = {m.symbol: m for m in members}
    if not members:
        print("no universe on disk; build it first")
        return 1
    printers = recent_printers(args.sessions)
    in_universe = sorted(s for s in printers if s in by_sym and not by_sym[s].etf_like)
    print(f"{len(printers)} names on the calendar in the last {args.sessions} sessions; {len(in_universe)} inside {universe.NAME}")

    from alpha.brains import post_event_drift as ped

    spoke, declined = [], []
    for sym in in_universe:
        try:
            f = ped.forecast(client, sym, args.horizon)
            spoke.append((sym, f))
        except Exception as exc:                                         # noqa: BLE001
            declined.append({"symbol": sym, "why": f"{type(exc).__name__}: {str(exc)[:140]}"})
    # Rank by the brain's own centre/sd (a ticker-blind number), conviction as a tie-break.
    spoke.sort(key=lambda sf: -(abs(sf[1].centre) / sf[1].sd * sf[1].conviction))
    cand_members = [by_sym[s] for s, _ in spoke]
    n_enriched = universe.enrich(cand_members, max_calls=args.enrich)

    rows = []
    for sym, f in spoke:
        m = by_sym[sym]
        ev = f.evidence
        rows.append({"symbol": sym, "centre": round(f.centre, 5), "sd": round(f.sd, 5), "conviction": f.conviction,
                     "score": round(abs(f.centre) / f.sd * f.conviction, 4), "direction": "UP" if f.centre > 0 else "DOWN",
                     "r_day0": round(ev.get("r_day0", 0.0), 4), "band": ev.get("abs_move_band"), "elapsed": ev.get("elapsed_sessions"),
                     "event_day": ev.get("event_day"), "dv_bucket": m.dv_bucket, "median_dollar_volume": m.median_dollar_volume,
                     "market_cap_usd": m.market_cap_usd, "cap_bucket": universe.cap_bucket(m.market_cap_usd),
                     "industry": m.industry, "shortable_etb": m.shortable and m.easy_to_borrow,
                     "old_universe": sym in universe.OLD_UNIVERSE, "control_holding": sym in universe.CONTROL_HOLDINGS,
                     "calendar": printers.get(sym)})
    audit = universe.collapse_audit([r["symbol"] for r in rows], members)
    control_seen = {s: ("candidate" if s in {r["symbol"] for r in rows} else
                        "printed_declined" if s in {d["symbol"] for d in declined} else
                        "in_universe_no_print" if s in by_sym else "NOT IN UNIVERSE")
                    for s in universe.CONTROL_HOLDINGS}
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "universe": universe.NAME,
              "universe_n": len(members), "printers_on_calendar": len(printers), "printers_in_universe": len(in_universe),
              "candidates": rows, "declined": declined, "enriched": n_enriched, "collapse_audit": audit,
              "control_holdings": control_seen,
              "policy": "index membership, fame and a liquid chain add NO score; liquidity decides execution only"}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{datetime.now(timezone.utc).date().isoformat()}.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    print(f"\nCANDIDATES ({len(rows)}) -- post_event_drift over {universe.NAME}; {len(declined)} printers declined")
    print(f"  {'sym':6s} {'dir':4s} {'score':>6s} {'centre':>7s} {'sd':>6s} {'day0':>7s} {'band':10s} {'dv':6s} {'cap':>8s} {'bucket':6s} industry")
    for r in rows[:40]:
        cap = f"{r['market_cap_usd'] / 1e9:.1f}B" if r["market_cap_usd"] else "?"
        flag = " OLD" if r["old_universe"] else (" CONTROL" if r["control_holding"] else "")
        print(f"  {r['symbol']:6s} {r['direction']:4s} {r['score']:6.3f} {r['centre']:+7.2%} {r['sd']:6.2%} {r['r_day0']:+7.2%} "
              f"{(r['band'] or '')[:10]:10s} {r['dv_bucket']:6s} {cap:>8s} {(r['cap_bucket'] or '-'):6s} {(r['industry'] or '')[:22]}{flag}")
    why = {}
    for d in declined:
        parts = d["why"].split(":")
        k = (parts[2] if len(parts) > 2 else parts[-1]).strip()[:48]
        why[k] = why.get(k, 0) + 1
    print("  declined, by reason:", dict(sorted(why.items(), key=lambda kv: -kv[1])[:6]))
    print(f"\n  UNIVERSE AUDIT: {audit['verdict']}  old-universe share {audit['share_old_universe']:.0%}, mega share {audit['share_mega']:.0%}, "
          f"by bucket {audit['by_dv_bucket']}")
    print(f"  control holdings: {control_seen}")
    print(f"  receipt -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
