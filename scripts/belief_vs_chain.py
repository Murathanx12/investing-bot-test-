"""BELIEF vs CHAIN -- two prices for the same event, compared as numbers.

    AAT_ACCOUNT_ROLE=dev python -m scripts.belief_vs_chain NVDA --expiry 2026-08-28

The idea, stated the way Murat framed it: don't ask "is the news bullish?",
ask "what does the crowd BELIEVE, and what has the market already CHARGED?".
Both are now readable as prices without an LLM in the loop:

    crowd belief   Polymarket "Will NVDA close above $K on <date>?"  -> P_crowd
    chain belief   the option chain's risk-neutral P(S_T > K)         -> P_chain

P_chain is read off the chain the plain way: N(d2) with the ATM implied vol at
the option expiry, time-scaled to the market's resolution date when the two do
not coincide (a daily Polymarket market against a Friday weekly). That is a
lognormal approximation, stated as one; a vertical-spread digital would be
more exact and is a follow-up.

What the disagreement means: if P_crowd >> P_chain the crowd is more bullish
than the options market is charging for -- a candidate for a defined-risk
long-delta structure (or, if we think the crowd is wrong, the reverse). Either
way it is recorded BEFORE resolution and graded after, so the question "does
Polymarket lead options, or lag them?" gets an answer from data rather than a
prior. Nobody in the field is comparing these two, as far as the field research
could find.

Risk-neutral vs real-world: P_chain is risk-neutral; over a few days the drift
term is negligible next to the disagreement sizes we care about (10-20pp).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper
from alpha.data import chain as chain_mod
from alpha.sources import belief

_ABOVE = re.compile(r"close above \$?([0-9][0-9,]*\.?[0-9]*) on (\w+ \d+)", re.I)


def p_chain_above(spot: float, k: float, iv: float, t_years: float, r: float = 0.045) -> float:
    if t_years <= 0 or iv <= 0:
        return 1.0 if spot > k else 0.0
    d2 = (math.log(spot / k) + (r - 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
    return 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))


def _resolution_date(text: str, year: int) -> date | None:
    m = _ABOVE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(2)} {year}", "%B %d %Y").date()
    except ValueError:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--expiry", required=True)
    p.add_argument("--query", default=None)
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    sym = args.symbol.upper()

    snap = chain_mod.fetch(client, sym, expiry_from=args.expiry, expiry_to=args.expiry)
    call, put = snap.atm(args.expiry, "C"), snap.atm(args.expiry, "P")
    ivs = [c.implied_vol for c in (call, put) if c and c.implied_vol]
    if not ivs:
        print("no ATM implied vol on the chain; cannot price the chain's belief")
        return 1
    iv = sum(ivs) / len(ivs)
    now = datetime.now(timezone.utc)
    rows = []
    for m in belief.polymarket_search(args.query or sym, limit=40):
        q = m["question"] or ""
        km = _ABOVE.search(q)
        if not km or sym not in q.upper() and (args.query or sym).lower() not in q.lower():
            continue
        k = float(km.group(1).replace(",", ""))
        res = _resolution_date(q, now.year)
        if res is None:
            continue
        # Resolution at that day's close, 16:00 ET = 20:00 UTC.
        t_years = max((datetime(res.year, res.month, res.day, 20, tzinfo=timezone.utc) - now).total_seconds(), 0) / (365.25 * 86400)
        p_crowd = float(m["belief"].get("Yes", 0.0))
        p_ch = p_chain_above(snap.spot, k, iv, t_years)
        rows.append({"question": q, "K": k, "resolves": res.isoformat(), "p_crowd": p_crowd,
                     "p_chain": round(p_ch, 4), "gap_crowd_minus_chain": round(p_crowd - p_ch, 4),
                     "volume_24h": m["volume_24h"], "iv_used": round(iv, 4), "spot": snap.spot,
                     "chain_expiry": args.expiry, "t_years": round(t_years, 5)})
    rows.sort(key=lambda r: (r["resolves"], r["K"]))
    out = {"generated_utc": now.isoformat(), "symbol": sym, "spot": snap.spot, "atm_iv": round(iv, 4),
           "quote_age_s": round(snap.median_quote_age_seconds, 1), "rows": rows,
           "note": "P_chain is lognormal N(d2) at ATM IV time-scaled to the market's resolution; a vertical digital is the exact follow-up"}
    print(json.dumps(out, indent=1))
    d = config.__file__.rsplit("alpha", 1)[0] + "state/belief_vs_chain"
    import os
    os.makedirs(d, exist_ok=True)
    with open(f"{d}/{sym}_{now:%Y%m%dT%H%M}.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
