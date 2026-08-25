"""One dashboard-readable EVENT CARD for one symbol: the artefact a judge asked for.

    AAT_ACCOUNT_ROLE=dev python -m scripts.event_card NVDA --expiry 2026-08-28

Prints (and writes to state/cards/<SYMBOL>_<date>.json) a single record with:

    what happened            latest news items, with sources and timestamps
    what the LLM read        NARRATIVE_SHOCK axes: truth, belief, attention,
                             disagreement, impact, already-priced -> belief-gap case
    what the crowd believes  Polymarket / Kalshi prices where a market exists
    attention                Wikipedia velocity, HN counts, option volume ratio
    every brain's forecast   centre + sd + conviction, and the brains that declined
    the chain's expectation  implied move, ATM straddle, parity gap
    what was chosen          from the decision ledger for this symbol today
    the alternatives         every refused / shadow structure with its reason
    the result so far        counterfactual marks, if any

Everything here is READ from ledgers and sources; nothing is decided here. A
card assembled after the fact from numbers written before the fact is the
difference between reasoning and "plausible narrative after the fact".
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import brains, config, ledger
from alpha.broker.alpaca import AlpacaPaper
from alpha.data import chain as chain_mod
from alpha.sources import attention, belief
from alpha.sources.http import SourceRefusal


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as exc:                                        # noqa: BLE001
        return {"unavailable": f"{type(exc).__name__}: {str(exc)[:160]}"}


def build(client, symbol: str, *, expiry: str, horizon: float, pm_query: str | None) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    forecasts, declined = brains.forecast_all(client, [symbol], horizon,
                                              brains=list(brains.BRAINS), expiries=[expiry])
    snap = _safe(chain_mod.fetch, client, symbol, expiry_from=expiry, expiry_to=expiry)
    chain_view = snap if isinstance(snap, dict) else {
        "spot": snap.spot, "spot_source": snap.spot_source, "feed": snap.feed,
        "implied_move": snap.implied_move(expiry), "parity_gap": snap.parity_gap(expiry),
        "median_quote_age_s": snap.median_quote_age_seconds, "contracts": len(snap.contracts),
        "liquid_contracts": len(snap.liquid()),
    }
    rows = [r for r in ledger.read_all() if r.get("symbol") == symbol and r.get("ts_utc", "")[:10] == today]
    chosen = [r for r in rows if r["action"] in ("submitted", "dry_run")]
    alternatives = [r for r in rows if r["action"] in ("refused", "alternative", "shadow")]
    cf = [r for r in ledger.read_all("counterfactual") if r.get("symbol") == symbol]

    narrative = next((f for f in forecasts if f.brain == "narrative_dispersion"), None)
    shock = (narrative.evidence.get("shocks") or [None])[0] if narrative else None

    return {
        "symbol": symbol, "as_of_utc": datetime.now(timezone.utc).isoformat(), "expiry": expiry,
        "what_happened": (shock or {}).get("sources") or _safe(
            lambda: [{"source": n.get("source"), "created_at": n.get("created_at"), "headline": n.get("headline")}
                     for n in attention.alpaca_news(client, [symbol], limit=8)]),
        "what_the_llm_read": {
            "headline": (shock or {}).get("headline"), "summary": (shock or {}).get("summary"),
            "event_type": (shock or {}).get("event_type"), "axes": (shock or {}).get("axes"),
            "belief_gap": (shock or {}).get("belief_gap"), "llm": (shock or {}).get("llm"),
        } if shock else {"unavailable": "narrative brain declined"},
        "what_the_crowd_believes": {
            "polymarket": _safe(belief.polymarket_search, pm_query or symbol),
            "vix_term_structure": _safe(belief.vix_term_structure),
            "cboe_put_call": _safe(belief.put_call_ratios),
        },
        "attention": {
            "wikipedia": _safe(attention.wiki_attention, symbol),
            "hacker_news": _safe(attention.hn_mentions, pm_query or symbol),
            "option_volume": next((f.evidence for f in forecasts if f.brain == "options_attention"), None),
        },
        "forecasts": [{"brain": f.brain, "centre": f.centre, "sd": f.sd, "conviction": f.conviction,
                       "rationale": f.rationale} for f in forecasts],
        "declined": declined,
        "chain_expectation": chain_view,
        "chosen": [{k: r.get(k) for k in ("decision_id", "brain", "instrument", "action", "risk_fraction",
                                          "max_loss_usd", "mdm_edge", "implied_move", "breakeven_move")}
                   for r in chosen],
        "alternatives": [{k: r.get(k) for k in ("brain", "instrument", "action", "mdm_edge", "refusal_reason")}
                         for r in alternatives],
        "result_so_far": [{k: r.get(k) for k in ("decision_id", "instrument", "outcome", "ts_utc")} for r in cf[-12:]],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--expiry", required=True)
    p.add_argument("--horizon", type=float, default=3.0)
    p.add_argument("--role", default=None)
    p.add_argument("--query", default=None, help="prediction-market / HN search phrase")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper(role=args.role)
    card = build(client, args.symbol.upper(), expiry=args.expiry, horizon=args.horizon, pm_query=args.query)
    out_dir = ledger.LEDGER_DIR / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.symbol.upper()}_{card['as_of_utc'][:10]}.json"
    path.write_text(json.dumps(card, indent=1, default=str), encoding="utf-8")
    print(json.dumps(card, indent=1, default=str))
    print(f"\nwritten: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
