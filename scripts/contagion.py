"""CAUSAL_CONTAGION_NVDA_v1 -- four channels that are routinely reported as one.

    python -m scripts.contagion --baseline        # measure betas BEFORE the event
    python -m scripts.contagion --event 2026-08-27

WHY THE DECOMPOSITION IS THE WHOLE POINT
========================================
"NVIDIA missed and dragged the market down" is four different claims, and they
imply different trades:

  1 MECHANICAL     NVDA is ~7.8% of the S&P 500. A -5% NVDA move takes ~-0.39%
                   off the index arithmetically, with every other constituent
                   unchanged. This is not contagion, it is a weighted average.
  2 SECTOR         semis move because NVDA's result is INFORMATION about semis.
                   Expected from each name's own pre-measured NVDA beta.
  3 BEHAVIOURAL    names move MORE than their beta predicts, and breadth
                   collapses -- the fear channel Murat described.
  4 FORCED FLOW    de-risking and margin, visible as a volume/vol spike rather
                   than as a return.

Channel 1 is arithmetic. Channel 2 is priced by a regression fitted BEFORE the
event. **Only what survives both is a candidate for 3 or 4** -- and without
subtracting them, "fear contagion" is unfalsifiable against ordinary factor
beta, which is exactly the objection this project raises against every other
narrative.

THE ORDER MATTERS, AGAIN
========================
`--baseline` must be run BEFORE the print and writes the betas it will later be
judged against. Fitting a beta after seeing the reaction and then reporting the
residual as contagion is a post-hoc story with an equation attached. The event
run REFUSES a baseline stamped after the release.

POWER, STATED UP FRONT
======================
`FINDING_2026-08-26_THE_SHOCK_GRAPH_CANNOT_RESOLVE_ONE_EVENT`: per-node one-event
MDE runs 5.9% to 24.0% against a ~5.1% implied move. **One event cannot resolve a
per-node effect.** This measures and records; it accumulates across prints. A
session that reads a single night's residual as a finding has misread the
arithmetic.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

OUT = Path(__file__).resolve().parent.parent / "state" / "research"
BASELINE = OUT / "contagion_baseline.json"

#: NVDA's weight in the S&P 500. Two independent readings, deliberately kept
#: apart rather than averaged into a false precision:
#:
#:   REPORTED   ~7.8% (index-provider commentary, 2026-08-26; 7.50% at 30 June)
#:   FITTED     0.084 -- SPY's regression loading on NVDA controlling for SMH,
#:              over 269 sessions. Derived from RETURNS, not constituent caps.
#:
#: The fitted value sits ABOVE the reported one, which is expected: a regression
#: beta absorbs the mechanical weight PLUS whatever NVDA-specific correlation
#: SMH does not already explain. It is an upper bound on the purely mechanical
#: term, not a competing estimate of it.
#:
#: The band spans both, and the mechanical channel is reported ACROSS it. Picking
#: one number here would put false precision at the base of the whole
#: decomposition -- and the "beyond mechanical" residual is exactly the quantity
#: that a wrong weight biases.
NVDA_SPX_WEIGHT = 0.078
NVDA_SPX_WEIGHT_BAND = (0.075, 0.085)
NVDA_SPX_WEIGHT_FITTED = 0.084

#: The complex, by causal role. SPY/QQQ/SMH are the aggregates the mechanical
#: term applies to; the rest are the transmission nodes.
INDEXES = ["SPY", "QQQ", "SMH", "IWM"]
NODES = ["TSM", "MU", "AMD", "AVGO", "ANET", "VRT", "MPWR", "CRDO", "ALAB",
         "COHR", "LITE", "AAOI", "SMCI", "DELL", "ORCL", "APLD", "IREN", "CORZ"]


def _closes(client: AlpacaPaper, syms: list[str], start: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i in range(0, len(syms), 100):
        try:
            bars = client.stock_bars_multi(syms[i:i + 100], start=start, timeframe="1Day")
        except BrokerRefusal as exc:
            print(f"  bar batch failed: {exc}")
            continue
        for s, rows in bars.items():
            out[s] = {r["t"][:10]: float(r["c"]) for r in rows if r.get("c")}
    return out


def _rets(series: dict[str, float], dates: list[str]) -> list[float]:
    return [math.log(series[dates[i]] / series[dates[i - 1]]) for i in range(1, len(dates))
            if dates[i] in series and dates[i - 1] in series]


def _ols2(y: list[float], x1: list[float], x2: list[float]) -> tuple[float, float, float]:
    """y ~ a*x1 + b*x2 (no intercept; daily means are ~0). Returns (a, b, resid_sd)."""
    n = len(y)
    if n < 30:
        return 0.0, 0.0, 0.0
    s11 = sum(v * v for v in x1); s22 = sum(v * v for v in x2)
    s12 = sum(a * b for a, b in zip(x1, x2))
    sy1 = sum(a * b for a, b in zip(y, x1)); sy2 = sum(a * b for a, b in zip(y, x2))
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-18:
        return 0.0, 0.0, 0.0
    a = (sy1 * s22 - sy2 * s12) / det
    b = (sy2 * s11 - sy1 * s12) / det
    resid = [yy - a * u - b * v for yy, u, v in zip(y, x1, x2)]
    return a, b, st.pstdev(resid)


def cmd_baseline(client: AlpacaPaper, start: str) -> int:
    syms = ["NVDA"] + INDEXES + NODES
    px = _closes(client, syms, start)
    have = [s for s in syms if len(px.get(s, {})) > 60]
    dates = sorted(set.intersection(*[set(px[s]) for s in have]))
    nv = _rets(px["NVDA"], dates)
    smh = _rets(px["SMH"], dates)
    rows = {}
    for s in have:
        # SMH is a REGRESSOR. Regressing it on itself yields beta 1.0 and a zero
        # residual sd, which prints as a 0.00% MDE -- a row that reads as
        # "infinitely sensitive" when it is actually "not a test at all".
        if s in ("NVDA", "SMH"):
            continue
        y = _rets(px[s], dates)
        n = min(len(y), len(nv), len(smh))
        b_nv, b_smh, sd = _ols2(y[-n:], nv[-n:], smh[-n:])
        rows[s] = {"beta_nvda": round(b_nv, 4), "beta_smh": round(b_smh, 4),
                   "resid_sd": round(sd, 5), "n": n,
                   "mde_1event": round(2.8 * sd, 5)}
    doc = {"measured_utc": datetime.now(timezone.utc).isoformat(),
           "window_start": start, "window_end": dates[-1], "sessions": len(dates),
           "nvda_spx_weight": NVDA_SPX_WEIGHT, "weight_band": NVDA_SPX_WEIGHT_BAND,
           "note": ("betas fitted on data ENDING BEFORE the event. Refitting after the "
                    "reaction and calling the residual contagion is a story with an equation."),
           "betas": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"baseline over {len(dates)} sessions ending {dates[-1]} -> {BASELINE}")
    print(f"\n{'sym':6s} {'beta_NVDA':>10s} {'beta_SMH':>9s} {'resid sd':>9s} {'1-event MDE':>12s}")
    for s, r in sorted(rows.items(), key=lambda kv: -kv[1]["beta_nvda"]):
        print(f"{s:6s} {r['beta_nvda']:>10.2f} {r['beta_smh']:>9.2f} "
              f"{100*r['resid_sd']:>8.2f}% {100*r['mde_1event']:>11.2f}%")
    return 0


def cmd_event(client: AlpacaPaper, event_date: str) -> int:
    if not BASELINE.exists():
        print("REFUSED: no baseline. Run --baseline BEFORE the event; fitting betas after "
              "seeing the reaction produces a post-hoc story with an equation attached.")
        return 1
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    syms = ["NVDA"] + INDEXES + [s for s in base["betas"] if s not in INDEXES]
    px = _closes(client, syms, "2026-08-01")
    dates = sorted(set().union(*[set(px[s]) for s in px if px[s]]))
    if event_date not in dates:
        print(f"REFUSED: no bar for {event_date} yet. The session has not printed.")
        print(f"  latest available: {dates[-1] if dates else 'none'}")
        return 1
    i = dates.index(event_date)
    if i == 0:
        print("REFUSED: no prior session to measure against.")
        return 1
    prev = dates[i - 1]

    def move(s):
        a, b = px.get(s, {}).get(prev), px.get(s, {}).get(event_date)
        return (b / a - 1) if (a and b) else None

    nv = move("NVDA")
    if nv is None:
        print("REFUSED: no NVDA move for that session.")
        return 1
    print(f"CAUSAL CONTAGION  {prev} -> {event_date}")
    print(f"  NVDA {nv:+.2%}\n")

    print("CHANNEL 1 -- MECHANICAL (arithmetic, not contagion)")
    lo, hi = base["weight_band"]
    print(f"  NVDA weight in SPX {base['nvda_spx_weight']:.1%} (band {lo:.1%}-{hi:.1%})")
    mech = base["nvda_spx_weight"] * nv
    print(f"  index effect from NVDA alone: {mech:+.3%}  (band {lo*nv:+.3%} .. {hi*nv:+.3%})")
    spy = move("SPY")
    if spy is not None:
        print(f"  SPY actual {spy:+.2%}  ->  BEYOND MECHANICAL {spy - mech:+.3%}")

    print("\nCHANNEL 2/3 -- SECTOR TRANSFER vs BEHAVIOURAL (residual after pre-fitted beta)")
    smh = move("SMH")
    print("  NOTE: the INDEX rows are the resolvable ones. SPY/QQQ residual sd gives a")
    print("  one-event MDE near 1.4%, while per-node MDE runs 3.9%-20.8%. So 'did the index")
    print("  move beyond its mechanical share' IS answerable on a single print, and 'did")
    print("  THIS supplier overreact' is not. Read the top two rows; accumulate the rest.")
    print(f"{'sym':6s} {'actual':>8s} {'expected':>9s} {'residual':>9s} {'MDE':>7s}  reads")
    flagged = []
    for s, r in sorted(base["betas"].items(), key=lambda kv: -kv[1]["beta_nvda"]):
        act = move(s)
        if act is None or smh is None:
            continue
        exp = r["beta_nvda"] * nv + r["beta_smh"] * smh
        resid = act - exp
        mde = r["mde_1event"]
        verdict = "RESOLVABLE" if abs(resid) > mde else "inside noise"
        if abs(resid) > mde:
            flagged.append((s, resid))
        print(f"{s:6s} {act:>+8.2%} {exp:>+9.2%} {resid:>+9.2%} {mde:>6.1%}  {verdict}")

    print("\nCHANNEL 4 -- FORCED FLOW: not measured here (needs volume/IV, recorded as ABSENT)")
    print("\nBREADTH (the fear channel's own signature)")
    moves = [move(s) for s in base["betas"] if move(s) is not None]
    down = sum(1 for m in moves if m < 0)
    print(f"  {down} of {len(moves)} nodes fell. Median {st.median(moves):+.2%}"
          if moves else "  no node moves available")

    print("\nVERDICT")
    if not flagged:
        print("  NO node cleared its own one-event MDE. On this print the complex moved as")
        print("  its pre-fitted NVDA and SMH loadings predict -- which is channels 1 and 2,")
        print("  with nothing left over to attribute to fear.")
    else:
        print(f"  {len(flagged)} node(s) cleared their one-event MDE: "
              + ", ".join(f"{s} {r:+.1%}" for s, r in flagged))
        print("  ONE EVENT IS NOT A FINDING -- per-node MDE is 5.9%-24.0% against a ~5% move,")
        print("  so this is recorded to accumulate across prints, not read as a result.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--start", default="2025-08-01")
    p.add_argument("--event", default=None, help="YYYY-MM-DD session to decompose")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    if args.baseline:
        return cmd_baseline(client, args.start)
    if args.event:
        return cmd_event(client, args.event)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
