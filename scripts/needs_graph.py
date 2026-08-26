"""NEEDS_GRAPH_v1 -- which layer of the build-out is closest to supply-constrained?

    python -m scripts.needs_graph

THE QUESTION THIS ENCODES
=========================
Murat's actual reasoning, in his words: *what will the world need, and who
fulfils that need?* Then: which link in that chain is the bottleneck, because
the bottleneck is where the pricing power ends up.

The AI build-out as one bounded chain, demand flowing downward:

    ACCELERATORS -> MEMORY -> FOUNDRY/PACKAGING -> NETWORKING
                 -> SERVERS -> POWER -> COOLING/GRID -> DATACENTRE OPERATORS

WHAT "SUPPLY CONSTRAINED" LOOKS LIKE IN NUMBERS
===============================================
Capacity, backlog and lead times are the direct evidence and we do not have
them. What a constrained supplier leaves in its financials is a **joint**
signature:

    revenue growing        demand is real, not a story
    AND gross margin RISING  it can raise price without losing the order

Either alone means little. Growth with FALLING margin is a supplier taking
volume at someone else's price -- the opposite of a bottleneck, and the trap this
screen exists to avoid. **The conjunction is the signal.**

Torque is carried alongside from `state/research/elasticity.json`, because the
node that is constrained and the company that MOVES on it are different
questions, and the second is the expression.

WHAT THIS IS NOT
================
Not a forecast that a shortage happens, and not a claim about any node's future.
It ranks where pricing power is showing up **now**, in filed numbers, so a
mega-cap event can be pointed at a layer instead of at a ticker. Shadow only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from alpha import config

RES = Path(__file__).resolve().parent.parent / "state" / "research"

#: One bounded chain, demand flowing downward. Membership is a judgement and is
#: written here rather than inferred, so it can be argued with.
GRAPH = [
    ("accelerators",      ["NVDA", "AMD"]),
    ("memory / HBM",      ["MU", "SNDK", "WDC"]),
    ("foundry+packaging", ["TSM", "AMAT", "LRCX", "KLAC", "ENTG"]),
    ("networking/optics", ["ANET", "CRDO", "ALAB", "COHR", "LITE", "AAOI"]),
    ("servers / ODM",     ["SMCI", "DELL"]),
    ("power / thermal",   ["VRT", "MPWR", "POWI", "BE"]),
    ("datacentre ops",    ["APLD", "IREN", "CORZ", "NBIS"]),
]


def metrics(sym: str, key: str) -> dict:
    url = ("https://finnhub.io/api/v1/stock/metric?"
           + urllib.parse.urlencode({"symbol": sym, "metric": "all", "token": key}))
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            return (json.load(r) or {}).get("metric") or {}
    except Exception:                                          # noqa: BLE001
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    config.load_env()
    key = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not key:
        print("REFUSED: AAT_FINNHUB_API_KEY is not set.")
        return 1

    elas = {}
    ep = RES / "elasticity.json"
    if ep.exists():
        elas = {r["symbol"]: r["elasticity"] for r in json.loads(ep.read_text(encoding="utf-8"))["rows"]}

    print("NEEDS_GRAPH_v1 -- where is pricing power showing up in the AI build-out?\n")
    print("  constrained = revenue GROWING *and* gross margin RISING.")
    print("  growth with falling margin is volume at someone else's price.\n")

    nodes = []
    for node, members in GRAPH:
        rows = []
        for s in members:
            m = metrics(s, key)
            time.sleep(0.4)
            g = m.get("revenueGrowthTTMYoy")
            gm_now = m.get("grossMarginTTM")
            gm_5y = m.get("grossMargin5Y")
            if g is None or gm_now is None or gm_5y is None:
                rows.append({"symbol": s, "missing": True})
                continue
            rows.append({"symbol": s, "growth": float(g), "gm": float(gm_now),
                         "gm_5y": float(gm_5y), "gm_delta": float(gm_now) - float(gm_5y),
                         "torque": elas.get(s)})
        good = [r for r in rows if not r.get("missing")]
        if not good:
            nodes.append((node, None, rows))
            continue
        # node score: median growth x median margin expansion, both required
        import statistics as st
        mg = st.median([r["growth"] for r in good])
        md = st.median([r["gm_delta"] for r in good])
        constrained = mg > 0 and md > 0
        nodes.append((node, {"growth": mg, "gm_delta": md, "constrained": constrained,
                             "n": len(good)}, rows))

    scored = [(n, d, r) for n, d, r in nodes if d]
    scored.sort(key=lambda t: -(t[1]["growth"] * max(t[1]["gm_delta"], 0)))

    print(f"{'node':20s} {'n':>2s} {'med growth':>11s} {'med GM vs 5y':>13s}  reads")
    for node, d, rows in scored:
        verdict = ("CONSTRAINED-LIKE: growing AND pricing up" if d["constrained"]
                   else "growing, but NOT pricing up" if d["growth"] > 0
                   else "not growing")
        print(f"{node:20s} {d['n']:>2d} {d['growth']:>+10.1f}% {d['gm_delta']:>+12.1f}pp  {verdict}")
    for node, d, rows in nodes:
        if d is None:
            miss = ",".join(r["symbol"] for r in rows)
            print(f"{node:20s}  -- NO usable metrics ({miss}) -- excluded, not scored")

    top = [t for t in scored if t[1]["constrained"]]
    # IS THE CONDITION RARE? A screen that keeps six of seven nodes is not a
    # screen. The whole AI complex is growing with expanding margins, so the
    # BINARY carries almost no information -- the same failure as conditioning on
    # "analysts are still bullish" when 93% of names qualify. The ORDERING is
    # what survives, and the one node that FAILS is what validates the metric.
    if len(top) > 0.6 * len(scored):
        print(f"\n  *** THE BINARY DOES NOT DISCRIMINATE: {len(top)} of {len(scored)} nodes"
              f" qualify. ***")
        print("  A condition true of almost everything is not a screen. Read the ORDERING,")
        print("  not the label -- and note which node FAILS, because that is the check that")
        print("  the metric measures anything at all.")
        failed = [t for t in scored if not t[1]["constrained"]]
        for node, d, _ in failed:
            print(f"    {node}: {d['growth']:+.1f}% growth on {d['gm_delta']:+.1f}pp margin"
                  " -- growth WITHOUT pricing power, which is what an assembler looks like.")
    if top:
        print(f"\n  CONSTRAINED-LIKE NODES: {', '.join(t[0] for t in top)}")
        print(f"\n  and WHO MOVES on it -- the node is the diagnosis, the company is the trade:")
        for node, d, rows in top[:3]:
            with_t = sorted([r for r in rows if r.get("torque")],
                            key=lambda r: -r["torque"])
            if with_t:
                print(f"    {node:20s} " + "  ".join(
                    f"{r['symbol']} {100*r['torque']:.0f}%" for r in with_t[:4]))
    else:
        print("\n  NO node shows the joint signature right now. That is a reading, not a")
        print("  failure -- 'nothing is constrained today' is an answer.")

    print("\n  LIMITS: capacity, backlog and lead times are the direct evidence and we do")
    print("  not have them; this is their financial shadow. Membership is a judgement,")
    print("  written in the file so it can be argued with. Gross margin moves with MIX as")
    print("  well as with price. Shadow only -- nothing here trades.")

    RES.mkdir(parents=True, exist_ok=True)
    out = RES / "needs_graph.json"
    out.write_text(json.dumps({"nodes": [{"node": n, "summary": d, "members": r}
                                         for n, d, r in nodes]}, indent=1), encoding="utf-8")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
