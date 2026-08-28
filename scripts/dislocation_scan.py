"""EARNINGS_DISLOCATION_v1 -- where the release and the reaction DISAGREE. Shadow.

    AAT_ACCOUNT_ROLE=staging python -m scripts.dislocation_scan                 # printers reacting today/yesterday
    AAT_ACCOUNT_ROLE=staging python -m scripts.dislocation_scan --symbols S WDAY MRVL ESTC --deep 2

WHAT IT RANKS
=============
For each recent printer the council's LIGHT pass (facts, expectations, the
surprise cube -- no causal/skeptic/synthesis) gives a cube; the feed gives the
day-0 / after-hours reaction. Four quadrants:

    +cube / -reaction   under-reaction, hidden disappointment or a latent KPI
    -cube / +reaction   delayed downside or positioning
    +cube / +reaction   continuation vs already-priced
    -cube / -reaction   continuation vs over-reaction

The cube's net is the signed sum of its guide-vs-prior and guide-vs-consensus
cells (the forward-looking ones), weighted by |relative|, so a raised revenue
guide and a lowered EPS guide net to what they net to rather than to a label.
Names with ZERO comparable cells are listed but not ranked -- a cube that has
nothing to say must not be read as "flat".

This is the ATTENTION_ROUTER's middle tier: cheap over many, and `--deep N`
runs the full council on the N most dislocated. It places nothing and gives no
lane capital; a dislocation is a candidate for a human thesis or for a
historical replay, not a signal.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper
from alpha.council import providers, run

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")
FORWARD_AXES = ("guide_vs_prior_guide", "guide_vs_consensus")


def recent_printers(days_back: int = 1) -> list[str]:
    p = STATE / "window_universe.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    today = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
    keep = []
    for row in d.get("rows") or []:
        try:
            delta = (today - datetime.fromisoformat(str(row.get("reacts_on"))).date()).days
        except ValueError:
            continue
        if 0 <= delta <= days_back and row.get("status") != "BEFORE_KICKOFF":
            keep.append(str(row.get("symbol")).upper())
    return sorted(set(keep))


def cube_net(cube: dict) -> tuple[float, int]:
    net, n = 0.0, 0
    for c in cube.get("cells") or []:
        if c.get("axis") in FORWARD_AXES and c.get("relative") is not None:
            net += float(c["relative"])
            n += 1
    return net, n


def quadrant(net: float, n: int, reaction: float | None) -> str:
    if n == 0:
        return "NO_CELLS"
    if reaction is None:
        return "NO_REACTION_YET"
    cs = "+" if net > 0 else "-" if net < 0 else "0"
    rs = "+" if reaction > 0.01 else "-" if reaction < -0.01 else "0"
    return {("+", "-"): "UNDER_REACTION_OR_LATENT_KPI", ("-", "+"): "DELAYED_DOWNSIDE_OR_POSITIONING",
            ("+", "+"): "CONTINUATION_VS_PRICED", ("-", "-"): "CONTINUATION_VS_OVERREACTION"}.get((cs, rs), f"{cs}/{rs}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=15)
    ap.add_argument("--deep", type=int, default=0, help="run the FULL council on the N most dislocated")
    args = ap.parse_args()
    config.load_env()
    client = AlpacaPaper()
    symbols = [s.upper() for s in (args.symbols or recent_printers())][:args.max]
    if not symbols:
        print("no printers: pass --symbols or build state/window_universe.json")
        return 2
    live = providers.probe()
    print("live:", {k: v.get("state") for k, v in live.items()})
    rows = []
    for s in symbols:
        pk = run.council(client, s, live=live, light=True)
        run.write(pk)
        cube = pk["steps"].get("surprise_cube", {})
        net, n = cube_net(cube)
        ah = (pk["steps"].get("scout") or {}).get("ah_move")
        q = quadrant(net, n, ah)
        score = (abs(net) * (abs(ah) if ah is not None else 0.0)) if n and ah is not None else 0.0
        rows.append({"symbol": s, "cube_net": round(net, 4), "cells": n, "incomparable": cube.get("n_incomparable", 0),
                     "reaction": ah, "quadrant": q, "dislocation": round(score, 6), "verdict": pk.get("verdict"),
                     "refusals": [r["step"] for r in pk.get("refusals", [])]})
    rows.sort(key=lambda r: (-(r["quadrant"] in ("UNDER_REACTION_OR_LATENT_KPI", "DELAYED_DOWNSIDE_OR_POSITIONING")), -r["dislocation"]))
    print(f"\n{'sym':<6}{'cube':>8}{'cells':>6}{'incomp':>7}{'react':>8}  {'quadrant':<34}{'dislocation':>12}  refusals")
    for r in rows:
        print(f"{r['symbol']:<6}{r['cube_net']:>+8.3f}{r['cells']:>6}{r['incomparable']:>7}"
              f"{('n/a' if r['reaction'] is None else f'{r['reaction']:+.1%}'):>8}  {r['quadrant']:<34}{r['dislocation']:>12.5f}  {','.join(r['refusals'])}")
    day = (datetime.now(timezone.utc) - timedelta(hours=4)).date().isoformat()
    out = STATE / "dislocation"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{day}.json").write_text(json.dumps({"date": day, "rows": rows}, indent=1), encoding="utf-8")
    print(f"\nreceipt: {out / (day + '.json')}")
    if args.deep:
        deep = [r["symbol"] for r in rows if r["quadrant"] not in ("NO_CELLS", "NO_REACTION_YET")][:args.deep]
        print(f"\nFULL council on {deep}")
        for s in deep:
            pk = run.council(client, s, live=live)
            run.write(pk)
            syn = pk["steps"].get("synthesis", {})
            sk = pk["steps"].get("skeptic", {})
            print(f"  {s}: direction={syn.get('direction')} magnitude={syn.get('magnitude')} p_priced={sk.get('p_already_priced')} "
                  f"falsifier={str(syn.get('falsifier', ''))[:80]}")
    print("\nShadow only. A dislocation is a candidate for `scripts.thesis`, not a signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
