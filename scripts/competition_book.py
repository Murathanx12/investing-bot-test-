"""COMPETITION_BOOK_v2 -- an auction over MEASURED distributions. Places nothing.

    python -m scripts.competition_book --evidence state/evidence/core_replay.json
    python -m scripts.competition_book --equity 100000 --target-pct 8 --sessions 5

WHAT v1 GOT WRONG, AND WHY A REWRITE RATHER THAN A PATCH
========================================================
v1 was internally consistent, respected every limit it declared, and **could not
have been placed**. Four defects, each fixed by a module rather than by an
edit here:

1. IT PRINTED AN IMPOSSIBLE ORDER. "5. TIMING enter MARKET-ON-CLOSE" for a core
   made of multileg options. Alpaca accepts `time_in_force=day` for options and
   nothing else; `cls` is rejected outright. The correct instruction is split by
   instrument -- `alpha/timing.py`.

2. IT INVENTED ITS OWN PRICES. `credit = width * 0.30` and strikes at 95%/90%
   of spot. The credit is the thing under test, so assuming it assumes the
   answer -- `alpha/spreads.py` reads the real chain, and refuses when the chain
   cannot support a structure.

3. IT CALLED ONE BET THREE. `CORE = [SPY, QQQ, IWM]` was described as "three
   diversified positions". They are one MARKET_BETA node plus one
   SHORT_VARIANCE node -- `alpha/nodes.py`.

4. IT RANKED ON THE MEDIAN, AND FIXED 70/30 BY FIAT. A +0.4% median book is an
   excellent real-money book and a guaranteed mid-table finish. The contest
   objective is P(final >= target) under a hard floor, and beta earns its share
   by winning increments rather than by being written into a constant --
   `alpha/tournament.py`.

THE EVIDENCE FILE IS MANDATORY
==============================
Every distribution comes from `scripts/optionmetrics_core_replay` (Aegis repo),
which replays the exact structures over thirty years of real OptionMetrics bid
and offer. Without that receipt this script REFUSES rather than falling back to
an assumption. That is the whole lesson of v1: the fallback was the bug.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, time, timedelta
from pathlib import Path

import numpy as np

from alpha import config, lab, nodes, playbook, timing, tournament
from scripts.today_book import effective_bets
from scripts.wealth_lab import UNIVERSE

EARNINGS_IN_WINDOW = {
    "MRVL": "2026-08-28", "WDAY": "2026-08-28", "ADSK": "2026-08-28",
    "AFRM": "2026-08-28", "ULTA": "2026-08-28", "GAP": "2026-08-28",
    "NIO": "2026-09-01", "MDT": "2026-09-01",
    "PANW": "2026-09-02", "MDB": "2026-09-02", "DLTR": "2026-09-02",
    "AVGO": "2026-09-03", "HPE": "2026-09-03", "LULU": "2026-09-03",
    "SNOW": "2026-09-03", "NTAP": "2026-09-03", "CIEN": "2026-09-03",
    "DELL": "2026-09-04", "ZS": "2026-09-04", "DOCU": "2026-09-04",
    "PATH": "2026-09-04", "GWRE": "2026-09-04",
}

CORE_SYMBOLS = ["SPY", "QQQ", "IWM"]


def trend_ok(panel: lab.Panel, i: int, symbol: str = "SPY",
             window: int = 200) -> bool:
    """Cash when the market is below its own 200-session average.

    Adding this to the CRSP sweep lifted nearly every cell and took the best
    configuration from 2.58x to 5.03x. It is the cheapest risk control we own
    and the book that lost $37,337 never consulted it.
    """
    if symbol not in panel.symbols or i < window:
        return True
    j = panel.symbols.index(symbol)
    ma = float(np.nanmean(panel.close[i - window:i + 1, j]))
    return bool(np.isfinite(ma) and panel.close[i, j] >= ma)


def load_evidence(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"REFUSING: no measured evidence at {path}.\n"
            "  Run, in the Aegis repo:\n"
            "    python -m scripts.optionmetrics_core_replay --json "
            f"{path.name}\n"
            "  v1 of this book invented `credit = 30% of width` instead. A "
            "structure priced from an assumption cannot be evidence about that "
            "assumption, and the whole 70% core rested on it.")
    return json.loads(path.read_text(encoding="utf-8"))


def opportunities_from(ev: dict, *, recent_only: bool, equity: float
                       ) -> list[tournament.Opportunity]:
    """One Opportunity per (symbol, structure) with a measured sample array.

    The per-candidate ceiling comes from `playbook.name_budget`, which
    reconciles the per-name cap against the book cap and returns whichever
    binds. An earlier version of this function wrote
    `MAX_LOSS_PER_NAME * 100_000` -- the right rule against a HARDCODED equity,
    so the cap was correct only for a $100k account and silently wrong for
    every other one. Caught by `tests_smoke_playbook`, which asserts this
    script consults `name_budget` rather than re-deriving the arithmetic.
    """
    key = "samples_recent" if recent_only else "samples"
    out: list[tournament.Opportunity] = []
    rows = [(sym, struct, arr)
            for sym, block in ev.items()
            for struct, arr in (block.get(key) or {}).items()
            if len(arr) >= 20]
    per_name = playbook.name_budget(equity, max(1, len({s for s, _, _ in rows})))
    for sym, struct, arr in rows:
        tags = (nodes.SMALL_CAP,) if sym == "IWM" else ()
        out.append(tournament.Opportunity(
            name=f"{sym}:{struct}", samples=np.asarray(arr, dtype=float),
            symbol=sym, structure=struct, node_tags=tags,
            increment_usd=1_000.0, max_usd=per_name,
            group=sym, group_max_usd=per_name,
            note=f"{len(arr)} measured non-overlapping blocks"))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--evidence", default="state/evidence/core_replay.json")
    p.add_argument("--target-pct", type=float, default=8.0,
                   help="terminal equity target as a %% gain; the contest "
                        "objective is P(reaching it), not the median")
    p.add_argument("--floor-pct", type=float, default=15.0,
                   help="hard maximum drawdown; breaching it is a VETO")
    p.add_argument("--sessions", type=int, default=5)
    p.add_argument("--recent-only", action="store_true",
                   help="use only 2021+ blocks -- fewer samples, current regime")
    p.add_argument("--k", type=int, default=playbook.MIN_BREADTH_K)
    args = p.parse_args()
    config.load_env()

    ev = load_evidence(Path(args.evidence))
    equity = args.equity
    target = equity * (1 + args.target_pct / 100.0)
    floor = equity * (1 - args.floor_pct / 100.0)

    panel = lab.build_panel(UNIVERSE,
                            start=(date.today() - timedelta(days=1100)).isoformat())
    i = panel.n_dates - 1
    spot = panel.close[i]

    print(f"COMPETITION BOOK v2   decision close {panel.dates[i]}   "
          f"equity ${equity:,.0f}")
    print(f"objective: P(final >= ${target:,.0f}) subject to a hard floor at "
          f"${floor:,.0f}")
    print("=" * 96)

    # ---- 0. regime gate ----------------------------------------------------
    up = trend_ok(panel, i)
    print(f"\n0. REGIME   SPY {'ABOVE' if up else 'BELOW'} its 200-session average"
          f" -> {'deploy' if up else 'CASH'}")
    if not up:
        print("   The 32-year sweep improved in nearly every cell with this "
              "filter. Cash is a position and it is this one. NOTHING TO SEND.")
        return 0

    # ---- 1. mode -----------------------------------------------------------
    mode, why = tournament.mode_for(equity, target=target, start_equity=equity,
                                    sessions_left=args.sessions)
    print(f"\n1. MODE     {mode}\n   {why}")

    # ---- 2. the auction ----------------------------------------------------
    opps = opportunities_from(ev, recent_only=args.recent_only, equity=equity)
    if not opps:
        print("\nREFUSING: the evidence file carries no usable sample arrays.")
        return 1

    budget = equity * playbook.MAX_LOSS_FRACTION
    print(f"\n2. AUCTION  ${budget:,.0f} of DEFINED LOSS, allocated one "
          f"increment at a time by marginal P(target)")
    print(f"   {len(opps)} opportunities, each a measured non-overlapping sample:")
    for o in opps:
        s = o.samples
        print(f"     {o.name:<26} n={s.size:>4}  median {np.median(s):>+7.2%}"
              f"  mean {np.mean(s):>+7.2%}  p05 {np.percentile(s, 5):>+7.2%}")

    betas: dict[str, float | None] = {}
    if "SPY" in panel.symbols:
        js = panel.symbols.index("SPY")
        mkt = panel.close[1:, js] / panel.close[:-1, js] - 1.0
        for sym in {o.symbol for o in opps}:
            if sym in panel.symbols:
                j = panel.symbols.index(sym)
                betas[sym] = nodes.realised_beta(
                    panel.close[1:, j] / panel.close[:-1, j] - 1.0, mkt)

    # THE MODE CHOOSES THE OBJECTIVE. In BASE the book maximises expected log
    # wealth, which is what a real account wants and what refuses a negative-
    # median structure however fat its right tail. Only ATTACK -- behind, and
    # out of sessions -- switches to P(target), where convexity is worth buying
    # precisely because reliability that cannot reach the target is worthless.
    objective = "target" if mode == "ATTACK" else "growth"
    print(f"   -> objective = {objective}")
    alloc = tournament.auction(opps, equity=equity, target=target, floor=floor,
                               budget=budget, n_paths=6000, betas=betas,
                               objective=objective)
    print()
    for line in alloc.log:
        print(f"   {line}")

    if not alloc.by_name:
        print("\n   THE AUCTION BOUGHT NOTHING. Every candidate either failed to "
              "raise P(target) or breached a cap. Cash is the book, and that is "
              "a measurement rather than a silence.")
        return 0

    # ---- 3. risk nodes -----------------------------------------------------
    index = {o.name: o for o in opps}
    positions = [nodes.Position(symbol=index[n].symbol, structure=index[n].structure,
                                max_loss_usd=v, tags=index[n].node_tags)
                 for n, v in alloc.by_name.items()]
    att = nodes.attribute(positions, equity=equity, betas=betas)
    print(f"\n3. RISK NODES")
    print(nodes.report(att, equity))
    for b in att.breaches:
        print(f"   BREACH: {b}")

    # The node allocator counts CAUSES. `playbook.check_book` counts correlated
    # TICKERS. They are different questions and the second one does not become
    # unnecessary because the first exists: a book can hold six names inside one
    # node cap and still be 1.3 effective bets, which is how dev lost 21.8% in a
    # session. Both run.
    held = sorted({p_.symbol for p_ in positions})
    idx = [panel.symbols.index(s) for s in held if s in panel.symbols]
    n_eff = effective_bets(panel, idx, i) if len(idx) >= 2 else float("nan")
    print(f"   {len(held)} distinct underlyings, {n_eff:.2f} effective bets "
          f"(tickers), {nodes.effective_node_count(att):.2f} effective nodes")
    for r in playbook.check_book(n_eff, len(held)):
        print(f"   REFUSAL: {r}")
    for s in held:
        if s in EARNINGS_IN_WINDOW:
            print(f"   DROP {s}: reports {EARNINGS_IN_WINDOW[s]}, inside the "
                  f"holding window. The measured distribution does not contain "
                  f"that print.")

    # ---- 4. the decision table --------------------------------------------
    print(f"\n4. BOOK")
    print(f"   {'candidate':<26}{'node':<16}{'max loss':>10}{'median':>9}"
          f"{'p10':>9}{'p90':>9}{'timing':>22}")
    print("   " + "-" * 99)
    total = 0.0
    for name, usd in sorted(alloc.by_name.items(), key=lambda kv: -kv[1]):
        o = index[name]
        s = o.samples
        instr = "option" if "spread" in o.structure or "call" in o.structure \
            or "straddle" in o.structure else "equity"
        try:
            t = timing.entry_timing(instr, signal_frozen_et=time(15, 40))
            tif = f"{t.order_type}/{t.time_in_force}"
        except timing.TimingRefusal:
            tif = "REFUSED"
        node = (nodes.SHORT_VARIANCE if nodes.is_short_premium(o.structure)
                else nodes.LONG_VARIANCE if nodes.is_long_premium(o.structure)
                else nodes.MARKET_BETA)
        total += usd
        print(f"   {name:<26}{node:<16}{usd:>10,.0f}"
              f"{np.median(s):>+9.2%}{np.percentile(s, 10):>+9.2%}"
              f"{np.percentile(s, 90):>+9.2%}{tif:>22}")
    print(f"   {'TOTAL':<26}{'':<16}{total:>10,.0f}  "
          f"= {total / equity:.1%} of equity")

    final = tournament.simulate(alloc.by_name, index, equity, n_paths=20000)
    print(f"\n   simulated final equity: median ${np.median(final):,.0f}   "
          f"p10 ${np.percentile(final, 10):,.0f}   "
          f"p90 ${np.percentile(final, 90):,.0f}")
    print(f"   P(>= target) {tournament.p_target(final, target):.1%}   "
          f"P(< floor) {tournament.p_floor_breach(final, floor):.2%}")
    print("   NOTE: opportunities are drawn INDEPENDENTLY, which understates the "
          "left tail.\n   Shared exposure is handled by the node caps above, not "
          "inside this simulation.")

    # ---- 5. timing, split by instrument ------------------------------------
    print(f"\n5. TIMING   (v1 said 'MARKET-ON-CLOSE' for an OPTION core; the "
          f"venue rejects that)")
    eq_t = timing.entry_timing("equity", signal_frozen_et=time(15, 40))
    op_t = timing.entry_timing("option", signal_frozen_et=time(15, 40))
    print(f"   equities: {eq_t.order_type}/{eq_t.time_in_force} -- {eq_t.note}")
    print(f"   options : {op_t.order_type}/{op_t.time_in_force} worked "
          f"{op_t.window_et[0]}-{op_t.window_et[1]} ET")
    print(f"   the signal must be FROZEN by {timing.SIGNAL_FREEZE_ET} ET; the "
          f"venue rejects CLS after {timing.CLS_CUTOFF_ET}.")
    print(f"   A signal read off the 16:00 close cannot trade that close.")

    # ---- 6. entry cap ------------------------------------------------------
    print(f"\n6. ENTRY    at most {playbook.MAX_ENTRIES_PER_SESSION} names per "
          f"session. 100% of the $37,337 loss entered on ONE day.")

    print("\nNOTHING WAS SENT. These are orders for a human to approve, and the "
          "option legs\nstill require a LIVE chain through alpha/spreads.py "
          "before any price is real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
