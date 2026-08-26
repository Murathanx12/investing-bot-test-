"""PSYCHOHISTORY records: compile before the event, resolve after it.

    python -m scripts.psychohistory record  --evidence state/psychohistory_evidence/NVDA_2026-08-26.json [--expiry 2026-08-28]
    python -m scripts.psychohistory show    [--id PH:...]
    python -m scripts.psychohistory resolve --id PH:NVDA:2026-08-27:xxxxxxxx --day0-move 0.031 \
            [--revenue 92.9 --guide 100.5 --eps 2.12 --pead 0.011 --notes "..."]

`record` reads an evidence file (facts with sources, authored by a human or a
collector -- the compiler never invents facts), adds what the machine can
MEASURE right now (the chain's implied move, the crowd's ladder from the latest
event card, our brains' widths from forecasts.jsonl), sends the bundle to the
compiler, validates the structure, and appends ONE row to
`state/psychohistory.jsonl` with `action: SHADOW_ONLY`. Nothing here can order.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, psychohistory as ph

logger = logging.getLogger(__name__)


def _latest_brains(symbol: str) -> dict:
    from alpha import ledger

    latest = {}
    for r in ledger.read_all("forecasts"):
        if r.get("symbol") == symbol and r.get("brain"):
            b = r["brain"]
            if b not in latest or (r.get("ts_utc") or "") > (latest[b].get("ts_utc") or ""):
                latest[b] = r
    return {b: {"centre": r.get("predicted_move"), "sd": r.get("predicted_sd"), "ts": r.get("ts_utc"),
                "claim": ((r.get("outcome") or {}).get("claim"))} for b, r in latest.items()}


def _crowd(symbol: str) -> list[dict]:
    cards = sorted((Path("state") / "cards").glob(f"{symbol}_*.json"))
    if not cards:
        return []
    d = json.loads(cards[-1].read_text(encoding="utf-8"))
    out = []
    for m in (d.get("what_the_crowd_believes") or {}).get("polymarket") or []:
        if (m.get("liquidity") or 0) < 100:
            continue
        out.append({"question": m.get("question"), "p_yes": (m.get("belief") or {}).get("Yes"),
                    "liquidity": round(m.get("liquidity") or 0)})
    return out


def _chain(symbol: str, expiry: str | None) -> dict:
    if not expiry:
        return {}
    try:
        from alpha.broker.alpaca import AlpacaPaper
        from alpha.data import chain as chain_mod

        client = AlpacaPaper()
        snap = chain_mod.fetch(client, symbol, expiry_from=expiry, expiry_to=expiry)
        return {"spot": snap.spot, "implied_move_to_expiry": snap.implied_move(expiry), "expiry": expiry,
                "median_quote_age_s": round(snap.median_quote_age_seconds, 1), "feed": snap.feed}
    except Exception as exc:                                             # noqa: BLE001
        logger.warning("chain not read: %s", exc)
        return {"chain_error": f"{type(exc).__name__}: {exc}"}


def cmd_record(args) -> int:
    bundle = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    trigger, horizon = bundle["trigger"], bundle["horizon"]
    evidence = list(bundle["evidence"])
    market = dict(bundle.get("market_expectation") or {})
    symbol = trigger["symbol"]
    market.update({k: v for k, v in _chain(symbol, args.expiry or market.get("expiry")).items() if v is not None})
    market["our_brains"] = _latest_brains(symbol)
    crowd = _crowd(symbol)
    if crowd:
        market["crowd_polymarket"] = crowd
    n0 = len(evidence)
    for b, v in market["our_brains"].items():
        if v.get("sd"):
            evidence.append({"kind": "brain", "fact": f"our {b} brain: centre {v['centre']:+.2%}, sd {v['sd']:.2%} ({v.get('claim')})",
                             "source": "state/forecasts.jsonl", "date": (v.get("ts") or "")[:10]})
    for c in crowd[:12]:
        evidence.append({"kind": "crowd", "fact": f"Polymarket: {c['question']} -> {c['p_yes']}", "source": "polymarket", "date": "live"})
    if market.get("implied_move_to_expiry"):
        evidence.append({"kind": "chain", "fact": f"option chain implied move to {market.get('expiry')}: {market['implied_move_to_expiry']:.2%} (spot {market.get('spot')})",
                         "source": "alpaca option chain", "date": datetime.now(timezone.utc).isoformat()[:16]})
    logger.info("evidence: %d authored + %d measured = %d items", n0, len(evidence) - n0, len(evidence))
    if args.dry_run:
        print(ph.build_prompt(trigger, horizon, evidence, market))
        return 0
    compiled, llm = ph.compile_with_deepseek(trigger, horizon, evidence, market)
    rec = ph.make_record(trigger, horizon, evidence, market, compiled, llm)
    path = ph.append(rec)
    print(f"recorded {rec.id} -> {path}  (LLM ${llm['cost_usd']:.4f}, {llm['latency_s']}s)")
    _print(rec.__dict__)
    return 0


def _print(rec: dict) -> None:
    c = rec["compiled"]
    print(f"\n{rec['id']}  asof {rec['asof_utc'][:16]}  action {rec['action']}")
    print(f"  surprise axis : {c['surprise_axis']}")
    print(f"  priced in     : {c['priced_in']:.2f}   templates: {', '.join(c['templates_used']) or '-'}")
    print("  causal chain  :")
    for e in c["causal_chain"][:12]:
        print(f"    {e.get('from')} -[{e.get('edge')} c={e.get('confidence')} lag={e.get('lag_days')}d]-> {e.get('to')}")
    print("  scenarios     :")
    for s in c["scenarios"]:
        pr = s.get("predicts") or {}
        print(f"    {s.get('p'):.2f}  {s.get('name')}: {s.get('description')}")
        print(f"          -> day0 {pr.get('day0_move_bucket')} | revenue {pr.get('revenue_vs_consensus')} | guide {pr.get('guide_vs_consensus')}")
        print(f"          falsifiers: {'; '.join(s.get('falsifiers') or [])[:200]}")
    print("  second order  :")
    for so in c.get("second_order") or []:
        print(f"    {so.get('who')}: {so.get('effect')} ({so.get('direction')}, lag {so.get('lag_days')}d, c={so.get('confidence')})")
    print(f"  model buckets : {rec['model_buckets']}")
    print(f"  market buckets: {rec['market_buckets']}")
    d = rec["disagreement"]
    print(f"  disagreement  : largest {d['largest']} | tail model {d['tail_mass_model']} vs market {d['tail_mass_market']} | TV {d['total_variation']}")
    print(f"  expression    : {c['candidate_expression']}")
    if rec.get("outcome"):
        o = rec["outcome"]
        print(f"  OUTCOME       : day0 {o['day0_move']:+.2%} = {o['realised_bucket']} | Brier model {o['brier_model']} vs market {o['brier_market']} "
              f"-> {'MODEL' if o['model_beat_market'] else 'MARKET'} better | scenario realised: {o.get('scenario_realised')}")


def cmd_show(args) -> int:
    rows = ph.read_all()
    if args.id:
        rows = [r for r in rows if r["id"] == args.id]
    for r in rows:
        _print(r)
    print(f"\n{len(rows)} record(s)")
    return 0


def cmd_resolve(args) -> int:
    rows = [r for r in ph.read_all() if r["id"] == args.id]
    if not rows:
        print(f"no record {args.id}")
        return 1
    rec = rows[0]
    reported = {k: getattr(args, k) for k in ("revenue", "guide", "eps") if getattr(args, k) is not None}
    if "revenue" in reported:
        reported["revenue_usd_bn"] = reported.pop("revenue")
    if "guide" in reported:
        reported["guide_usd_bn"] = reported.pop("guide")
    outcome = ph.resolve(rec, day0_move=args.day0_move, reported=reported, pead_3d=args.pead, notes=args.notes or "")
    rec = dict(rec, outcome=outcome)
    ph.append(ph.Record(**{k: rec[k] for k in ph.Record.__dataclass_fields__}))
    _print(rec)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--evidence", required=True)
    r.add_argument("--expiry", default=None)
    r.add_argument("--dry-run", action="store_true", help="print the prompt, call nothing")
    s = sub.add_parser("show")
    s.add_argument("--id", default=None)
    v = sub.add_parser("resolve")
    v.add_argument("--id", required=True)
    v.add_argument("--day0-move", type=float, required=True, help="signed fraction, first reflecting close vs prior close")
    v.add_argument("--revenue", type=float, default=None, help="reported revenue, $bn")
    v.add_argument("--guide", type=float, default=None, help="next-quarter revenue guide midpoint, $bn")
    v.add_argument("--eps", type=float, default=None)
    v.add_argument("--pead", type=float, default=None, help="3-session excess after day 0, signed fraction")
    v.add_argument("--notes", default="")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    return {"record": cmd_record, "show": cmd_show, "resolve": cmd_resolve}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
