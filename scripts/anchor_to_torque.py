"""ANCHOR_TO_TORQUE_v1 -- the mega-cap is the sensor; rank the expressions.

    python -m scripts.anchor_to_torque --event 2026-08-27

THE INVARIANT THIS IMPLEMENTS
=============================
> The mega-cap is a SENSOR, not the trade. NVIDIA tells us what world we are in;
> it is rarely the best instrument for monetising that world.

After a mega-cap print the reflex question is "buy it?". The better question has
four parts, and this ranks them from receipts that already exist:

  EXPOSURE     does this name actually load on the anchor?
               -> `state/research/contagion_baseline.json`, betas fitted BEFORE
                  the event
  TORQUE       does the same shock matter more here?
               -> `state/research/elasticity.json`, shock / revenue
  COVERAGE     is anyone watching?
               -> the PIT analyst panel; fewer analysts, slower repricing
  RESIDUAL     did it move already?
               -> actual return minus what its pre-fitted betas predicted

A name that is exposed, high-torque, under-covered and **has not yet moved** is
the expression the anchor is pointing at. A name that is exposed and has already
moved its full beta is the anchor with extra steps.

WHAT THIS IS NOT
================
**Shadow only.** It ranks candidates and trades nothing. One event cannot
resolve a per-node effect -- MDE runs 3.9% to 20.8% against a ~5% move -- so a
single night's ranking is recorded to ACCUMULATE across prints, never read as a
result. That limit is printed with the output every run so it cannot be quietly
dropped when the table looks compelling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

RES = Path(__file__).resolve().parent.parent / "state" / "research"


def _load(name: str):
    p = RES / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event", required=True, help="session to rank against, YYYY-MM-DD")
    p.add_argument("--anchor", default="NVDA")
    args = p.parse_args()
    config.load_env()

    base = _load("contagion_baseline.json")
    elas = _load("elasticity.json")
    if not base:
        print("REFUSED: no contagion baseline. Fit it BEFORE the event -- betas fitted "
              "after the reaction make the residual a story with an equation.")
        return 1
    if not elas:
        print("REFUSED: no elasticity receipt. Run `python -m scripts.elasticity` first.")
        return 1
    torque = {r["symbol"]: r for r in elas["rows"]}
    excluded = {r["symbol"] for r in elas.get("excluded_non_usd", [])}

    panels = sorted((RES / "analyst_panel").glob("*.jsonl"))
    coverage = {}
    if panels:
        for line in panels[-1].open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                coverage[r["symbol"]] = r.get("coverage")

    client = AlpacaPaper()
    # SMH is a REGRESSOR, not a node -- contagion deliberately keeps it out of the
    # beta table (regressing it on itself gives a degenerate zero MDE). It is
    # still needed to compute the EXPECTED return, so it must be fetched even
    # though it never appears as a candidate. Forgetting that made mv("SMH")
    # return None and silently dropped every single row.
    syms = sorted(set(base["betas"]) | {args.anchor, "SMH"})
    try:
        bars = client.stock_bars_multi(syms, start="2026-08-01", timeframe="1Day")
    except BrokerRefusal as exc:
        print(f"REFUSED: {exc}")
        return 1
    closes = {s: {b["t"][:10]: float(b["c"]) for b in rows if b.get("c")}
              for s, rows in bars.items()}
    dates = sorted({d for s in closes for d in closes[s]})
    if args.event not in dates:
        print(f"REFUSED: no bar for {args.event}. Latest available: {dates[-1] if dates else 'none'}.")
        print("  The session has not printed; there is nothing to rank against yet.")
        return 1
    i = dates.index(args.event)
    prev = dates[i - 1]

    def mv(s):
        a, b = closes.get(s, {}).get(prev), closes.get(s, {}).get(args.event)
        return (b / a - 1) if (a and b) else None

    anchor_move, smh_move = mv(args.anchor), mv("SMH")
    if anchor_move is None:
        print(f"REFUSED: no move for {args.anchor}.")
        return 1
    print(f"ANCHOR_TO_TORQUE  {args.anchor} {anchor_move:+.2%}  ({prev} -> {args.event})")
    print("  SHADOW ONLY. One event cannot resolve a per-node effect.\n")

    rows = []
    for s, b in base["betas"].items():
        if s in ("SPY", "QQQ", "IWM"):
            continue
        act = mv(s)
        if act is None or smh_move is None:
            continue
        exp = b["beta_nvda"] * anchor_move + b["beta_smh"] * smh_move
        t = torque.get(s)
        rows.append({
            "symbol": s, "beta_nvda": b["beta_nvda"], "actual": act,
            "expected": exp, "residual": act - exp, "mde": b["mde_1event"],
            "elasticity": (t or {}).get("elasticity"),
            "coverage": coverage.get(s),
        })

    # A candidate must LOAD on the anchor at all, or its torque is irrelevant.
    ranked = [r for r in rows if r["beta_nvda"] > 0.05 and r["elasticity"]]
    ranked.sort(key=lambda r: -(r["elasticity"] * r["beta_nvda"]))

    print(f"{'sym':6s} {'beta':>6s} {'torque':>8s} {'cov':>4s} {'actual':>8s} "
          f"{'expected':>9s} {'residual':>9s} {'MDE':>7s} {'r/MDE':>6s}")
    for r in ranked:
        cov = f"{r['coverage']}" if r["coverage"] is not None else "-"
        ratio = r["residual"] / r["mde"] if r["mde"] else 0.0
        print(f"{r['symbol']:6s} {r['beta_nvda']:>6.2f} {100*r['elasticity']:>7.0f}% "
              f"{cov:>4s} {r['actual']:>+8.2%} {r['expected']:>+9.2%} "
              f"{r['residual']:>+9.2%} {r['mde']:>6.1%} {ratio:>+6.2f}")

    resolved = [r for r in ranked if abs(r["residual"]) >= r["mde"]]
    if not resolved:
        # This is the expected outcome, and saying so matters: a verdict column
        # where every row reads the same carries no information, and would look
        # like agreement rather than like an instrument that cannot separate.
        print(f"\n  NOT ONE of {len(ranked)} names cleared its own one-event MDE. That is the")
        print("  power limit doing its job, not a signal that nothing happened -- residual")
        print("  and MDE are the same order of magnitude here. Read the `r/MDE` column for")
        print("  ORDERING across prints; do not read any single row as a verdict.")
    else:
        print(f"\n  {len(resolved)} name(s) cleared their own MDE: "
              + ", ".join(f"{r['symbol']} {r['residual']:+.1%}" for r in resolved))
        print("  Still one event. Recorded to accumulate.")

    if excluded:
        print(f"\n  no torque measured for: {', '.join(sorted(excluded))} "
              f"(non-USD reporter). NOT zero -- unmeasured.")
    print("\n  Ranked by exposure x torque. The residual column says whether the market")
    print("  has already done the work; a name that is exposed, high-torque and still")
    print("  inside its own MDE is what the anchor is pointing at.")
    if ranked:
        print("\n  THE LIMIT, printed every run: per-node MDE here runs "
              f"{100*min(r['mde'] for r in ranked):.1f}%-"
              f"{100*max(r['mde'] for r in ranked):.1f}% against a ~5% anchor move.")
        print("  A single night's ranking ACCUMULATES across prints. It does not conclude.")
    else:
        print("\n  NO candidate loaded on the anchor with measurable torque. That is a")
        print("  REFUSAL to rank, not a statement about the market -- check the baseline")
        print("  and the elasticity receipt before reading anything into an empty table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
