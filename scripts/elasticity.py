"""STATE_CHANGE_ELASTICITY -- rank by torque, not by market cap.

    python -m scripts.elasticity --shock 1000        # a $1bn revenue shock
    python -m scripts.elasticity --shock 1000 --universe panel

THE INTUITION THIS MAKES PRECISE
================================
Murat's version: a smaller firm has more room to move on the same news. The
literal form of that -- "small caps move more" -- is false as stated, and this
project has an option chain implying **5.10% in one session for a ~$5T company**
to prove it. Size does not bound the move.

The defensible form is about **convexity to a state transition**. If an AI
build-out puts $1bn of incremental annual revenue into a supplier:

    a $400M-revenue components maker    -> revenue MORE THAN DOUBLES
    NVIDIA                              -> a rounding error

Same shock, same direction, same thesis. Utterly different repricing. That
difference is a measurable property of the company, not a feeling about its size.

THE ARITHMETIC, AND ITS ONE ASSUMPTION
======================================
For a shock of `S` dollars in annual revenue, holding the revenue multiple
constant:

    delta EV  ~  S * (EV / Revenue)
    elasticity = delta EV / EV  =  S / Revenue

So **elasticity to a revenue shock is simply the shock over current revenue.**
Clean, and it rests on one assumption worth stating loudly: **that the multiple
survives the shock.** It often does not — a company that doubles revenue on a
low-margin contract can re-rate *down*. So this ranks CANDIDATES by torque; it
does not forecast a price.

WHAT THIS IS NOT
================
Not a signal, not a recommendation, and not an estimate of whether the shock
happens. It answers exactly one question: **if this thing happens, who moves?**
Which is the question `ANCHOR_TO_TORQUE_v1` needs answered before it can rank
expressions for a mega-cap event.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from alpha import config

OUT = Path(__file__).resolve().parent.parent / "state" / "research"
PANEL = OUT / "analyst_panel"

#: The AI build-out chain, from the contagion graph. These are the names a
#: mega-cap AI print is INFORMATION about.
CHAIN = ["TSM", "MU", "AMD", "AVGO", "ANET", "VRT", "MPWR", "CRDO", "ALAB",
         "COHR", "LITE", "AAOI", "SMCI", "DELL", "ORCL", "APLD", "IREN", "CORZ",
         "NVDA", "SNDK", "BE", "NBIS", "STM", "WDC", "SLAB", "POWI", "ENTG"]


def metric(symbol: str, key: str) -> dict:
    url = ("https://finnhub.io/api/v1/stock/metric?"
           + urllib.parse.urlencode({"symbol": symbol, "metric": "all", "token": key}))
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:                                     # noqa: BLE001
        return {"_error": type(e).__name__}


def profile(symbol: str, key: str) -> dict:
    url = ("https://finnhub.io/api/v1/stock/profile2?"
           + urllib.parse.urlencode({"symbol": symbol, "token": key}))
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return json.load(r)
    except Exception:                                          # noqa: BLE001
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--shock", type=float, default=1000.0,
                   help="incremental ANNUAL revenue shock, in $ millions")
    p.add_argument("--universe", default="chain", choices=["chain", "panel"])
    args = p.parse_args()
    config.load_env()
    key = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not key:
        print("REFUSED: AAT_FINNHUB_API_KEY is not set.")
        return 1

    if args.universe == "panel":
        files = sorted(PANEL.glob("*.jsonl"))
        if not files:
            print("no panel capture to read")
            return 1
        rows = [json.loads(l) for l in files[-1].open(encoding="utf-8") if l.strip()]
        syms = [r["symbol"] for r in rows][:250]
    else:
        syms = CHAIN

    print(f"STATE_CHANGE_ELASTICITY   shock = ${args.shock:,.0f}M of annual revenue")
    print(f"{len(syms)} names\n")
    out, foreign = [], []
    for i, s in enumerate(syms, 1):
        m = metric(s, key)
        time.sleep(0.4)
        met = (m or {}).get("metric") or {}
        # revenuePerShareTTM * shares outstanding -> TTM revenue, in $M
        rps = met.get("revenuePerShareTTM")
        prof = profile(s, key)
        time.sleep(0.4)
        shares = prof.get("shareOutstanding")            # millions
        cap = prof.get("marketCapitalization")           # $M
        rev = (float(rps) * float(shares)) if (rps and shares) else None
        if not rev or rev <= 0:
            print(f"  {s:6s} revenue UNAVAILABLE -- excluded, not guessed")
            continue
        # CURRENCY. Finnhub reports a foreign issuer in its HOME currency. TSM
        # comes back with revenue 4,469,418 and cap 62,237,686 -- Taiwan dollars,
        # ~31x the USD figure. Elasticity divides a USD shock by that revenue, so
        # it lands ~31x too small and TSM reads as having essentially NO torque.
        # (P/S survives the error, because it divides TWD by TWD -- which is why
        # the row looked plausible enough to ship.)
        #
        # Excluded and NAMED rather than converted: an FX rate is one more daily
        # input to get wrong, and a silently mis-scaled row at the bottom of a
        # ranking is exactly the number that gets quoted later as "no torque".
        ccy = (prof.get("currency") or "USD").upper()
        if ccy != "USD":
            foreign.append((s, ccy))
            print(f"  {s:6s} reports in {ccy} -- EXCLUDED (a USD shock over {ccy} "
                  f"revenue is off by the FX rate)")
            continue
        out.append({"symbol": s, "revenue_ttm_musd": rev, "market_cap_musd": cap,
                    "ps": (cap / rev) if cap else None,
                    "elasticity": args.shock / rev,
                    "industry": prof.get("finnhubIndustry")})
        if i % 10 == 0:
            print(f"  ...{i}/{len(syms)}", flush=True)

    out.sort(key=lambda r: -r["elasticity"])
    print(f"\n{'symbol':7s} {'revenue $M':>11s} {'cap $M':>11s} {'P/S':>6s} "
          f"{'elasticity':>11s}  industry")
    for r in out:
        print(f"{r['symbol']:7s} {r['revenue_ttm_musd']:>11,.0f} "
              f"{(r['market_cap_musd'] or 0):>11,.0f} {(r['ps'] or 0):>6.1f} "
              f"{100*r['elasticity']:>10.1f}%  {str(r['industry'])[:28]}")

    if out:
        top, bot = out[0], out[-1]
        print(f"\n  {top['symbol']} moves {top['elasticity']/bot['elasticity']:,.0f}x more than "
              f"{bot['symbol']} on the SAME ${args.shock:,.0f}M of revenue.")
        print(f"  Ranking these by market cap would put {bot['symbol']} first.")
    if foreign:
        print("\n  EXCLUDED, non-USD reporters: "
              + ", ".join(f"{sym} ({c})" for sym, c in foreign)
              + ".\n  Their torque is NOT zero -- it is UNMEASURED here. A silently dropped row"
                "\n  at the bottom of a ranking is exactly what gets quoted later as 'no torque'.")
    print("\n  ASSUMPTION, stated loudly: this holds the revenue multiple CONSTANT.")
    print("  A company that doubles revenue on a low-margin contract can re-rate DOWN.")
    print("  This ranks CANDIDATES by torque; it does not forecast a price, and it says")
    print("  nothing about whether the shock happens.")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "elasticity.json"
    path.write_text(json.dumps({
        "computed_utc": datetime.now(timezone.utc).isoformat(),
        "shock_musd": args.shock, "universe": args.universe,
        "assumption": "revenue multiple held constant; ranks candidates, does not price them",
        "rows": out,
        "excluded_non_usd": [{"symbol": a, "currency": b} for a, b in foreign]},
        indent=1), encoding="utf-8")
    print(f"\n  -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
