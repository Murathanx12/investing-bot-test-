"""REFUSAL_REGRET_v1 -- what did each guard SAVE or COST, in dollars, by class.

    python -m scripts.refusal_regret                # whole counterfactual ledger
    python -m scripts.refusal_regret --since 2026-08-25 --role staging

WHY
===
A guard that repeatedly saves money has EARNED its authority; a guard that
repeatedly blocks winners is a cost wearing a rule's clothes, and six months of
those is how an engine's only legal action becomes cash. The counterfactual
ledger already marks every refused candidate in a parallel world at a fixed
risk ($5,000): this groups those marks by the guard that refused, using
`alpha.guards.GUARDS` (HARD / EMPIRICAL / TOURNAMENT / RETEST_DUE), and keeps
the LAST mark per decision so an hourly re-mark is not counted twenty times.

READ IT LIKE THIS
=================
    saved   = -sum(pnl of refused worlds that LOST)   -- money the guard kept
    cost    =  sum(pnl of refused worlds that WON)    -- money the guard declined
    net     = saved - cost                            -- positive: the guard pays

A HARD guard's net is not a verdict on the guard (it is not allowed to be
wrong on evidence). An EMPIRICAL guard's net IS -- and its `reopens_when` says
what evidence would relax it. UNCLASSIFIED reasons are rules nobody owns.

GRADED AND UNGRADED ARE REPORTED SEPARATELY (2026-09-02, retro E3)
==================================================================
45.4% of counterfactual decisions carry `pnl_usd = 0.0` because they are
`unmarkable` (no quotable chain) or `null` (the hold-cash world) -- and they
used to count toward `n` and `win%` exactly like a priced world. `daily_latch`
therefore reported **312 wins out of 312 on $0.00 saved and $0.00 cost**: a
100% win rate that measured nothing, printed beside real numbers, in the same
column. So every row now carries `graded`, every count is split, `win%` is over
graded rows ONLY, and a guard with no graded rows prints `--` rather than a
percentage it cannot have earned. An ungraded row is not a win and it is not a
zero: it is a row we have not measured, and the table has to say which.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from alpha import guards

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


def is_graded(row: dict) -> bool:
    """Was this counterfactual world actually PRICED? (E3, retro §3c.)

    Two sources, in order, because the field is newer than the ledger:

      1. `outcome.graded` -- written since 2026-09-02 by `record_marks`.
      2. `quote_snapshot.mark_source == "chain"` -- derivable on every older row,
         which is why the old numbers were wrong rather than unknowable.

    Anything else is UNGRADED. `unmarkable` (no quotable chain) and `null` (the
    hold-cash world) both carry `pnl_usd = 0.0`, they were 45.4% of the ledger,
    and pooling them into `n` and `win%` is what made `daily_latch` report 312
    wins out of 312 on $0.00 saved and $0.00 cost. A row we could not price is
    not a row the guard won.
    """
    out = row.get("outcome") or {}
    if isinstance(out.get("graded"), bool):
        return out["graded"]
    return (row.get("quote_snapshot") or {}).get("mark_source") == "chain"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="ISO date; rows before it are ignored")
    ap.add_argument("--role", default=None)
    ap.add_argument("--path", default=str(STATE / "counterfactual.jsonl"))
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"no counterfactual ledger at {p}")
        return 2
    last: dict[str, tuple] = {}
    n_rows = 0
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_rows += 1
            if r.get("action") != "refused":
                continue
            if args.since and str(r.get("ts_utc", ""))[:10] < args.since:
                continue
            if args.role and str(r.get("account_role")) != args.role:
                continue
            out = r.get("outcome") or {}
            pnl = out.get("pnl_usd")
            if pnl is None:
                continue
            reason = str(r.get("refusal_reason") or "")
            if reason.startswith("the null"):
                continue                       # abstaining pays exactly zero, by construction
            last[str(r.get("decision_id"))] = (reason, float(pnl), r.get("symbol"), r.get("instrument"),
                                               str(r.get("ts_utc", ""))[:10], is_graded(r),
                                               str(r.get("terminal_state") or ""))

    per_guard = defaultdict(lambda: {"n": 0, "graded": 0, "ungraded": 0, "saved": 0.0,
                                     "cost": 0.0, "wins": 0, "sample": ""})
    per_class = defaultdict(lambda: {"n": 0, "graded": 0, "ungraded": 0, "saved": 0.0, "cost": 0.0})
    per_state = defaultdict(lambda: {"n": 0, "graded": 0, "ungraded": 0, "saved": 0.0,
                                     "cost": 0.0, "wins": 0})
    for reason, pnl, sym, inst, day, graded, state in last.values():
        g = guards.classify(reason)
        key = g.key if g else "UNCLASSIFIED: " + reason[:48]
        cls = g.cls if g else "UNCLASSIFIED"
        a = per_guard[key]
        c = per_class[cls]
        s = per_state[state or "<unstamped>"]
        for bucket in (a, c, s):
            bucket["n"] += 1
            bucket["graded" if graded else "ungraded"] += 1
        # AN UNGRADED WORLD CONTRIBUTES NOTHING BUT ITS COUNT. `unmarkable` and
        # hold-cash worlds carry pnl_usd = 0.0, which is an ABSENCE wearing a
        # number: pooled into `wins` it produced `daily_latch 312/312 on $0.00`,
        # a 100% win rate over rows nobody priced (retro 2026-09-02 §3c).
        if graded:
            if pnl < 0:
                a["saved"] += -pnl
                c["saved"] += -pnl
                s["saved"] += -pnl
            elif pnl > 0:
                a["cost"] += pnl
                c["cost"] += pnl
                s["cost"] += pnl
                a["wins"] += 1
                s["wins"] += 1
        a["sample"] = a["sample"] or f"{sym} {inst} {day}"

    n_graded = sum(1 for v in last.values() if v[5])
    n_ungraded = len(last) - n_graded
    print(f"{n_rows:,} ledger rows; {len(last):,} distinct refused decisions "
          f"(last mark each) -- {n_graded:,} GRADED, {n_ungraded:,} UNGRADED "
          f"({(n_ungraded / len(last)) if last else 0:.1%} of the ledger carries "
          f"pnl_usd = 0.0 because nothing priced it)\n")
    print(f"{'class':<13}{'n':>8}{'graded':>8}{'ungrd':>7}{'saved $':>12}{'cost $':>12}{'net $':>12}")
    for cls in ("HARD", "EMPIRICAL", "TOURNAMENT", "RETEST_DUE", "UNCLASSIFIED"):
        c = per_class.get(cls)
        if c:
            print(f"{cls:<13}{c['n']:>8,}{c['graded']:>8,}{c['ungraded']:>7,}"
                  f"{c['saved']:>12,.0f}{c['cost']:>12,.0f}{c['saved'] - c['cost']:>12,.0f}")
    print(f"\n{'guard':<40}{'class':<12}{'n':>7}{'grd':>6}{'ungrd':>6}{'win%':>6}"
          f"{'saved $':>11}{'cost $':>11}{'net $':>11}  sample")
    rows = sorted(per_guard.items(), key=lambda kv: -(kv[1]["n"]))
    for key, a in rows[:args.top]:
        cls = next((x.cls for x in guards.GUARDS if x.key == key), "UNCLASSIFIED")
        # WIN% IS OVER GRADED ROWS ONLY. A guard with zero graded rows prints
        # `--`, not 0% and not 100%: "we have not measured this" is its own
        # answer and must not be readable as either extreme.
        win = f"{a['wins'] / a['graded']:.0%}" if a["graded"] else "--"
        print(f"{key[:39]:<40}{cls:<12}{a['n']:>7,}{a['graded']:>6,}{a['ungraded']:>6,}{win:>6}"
              f"{a['saved']:>11,.0f}{a['cost']:>11,.0f}{a['saved'] - a['cost']:>11,.0f}  {a['sample']}")

    # E3's other half: the same money, grouped by the TYPED state the gate
    # stamped at write time rather than by the sentence it wrote. Rows sealed
    # before `terminal_state` existed group under `<unstamped>` -- visibly, so
    # the coverage of the new field is readable off this table.
    if per_state:
        print(f"\n{'terminal_state':<20}{'n':>7}{'grd':>6}{'ungrd':>6}{'win%':>6}"
              f"{'saved $':>11}{'cost $':>11}{'net $':>11}")
        for st, v in sorted(per_state.items(), key=lambda kv: -kv[1]["n"]):
            win = f"{v['wins'] / v['graded']:.0%}" if v["graded"] else "--"
            print(f"{st:<20}{v['n']:>7,}{v['graded']:>6,}{v['ungraded']:>6,}{win:>6}"
                  f"{v['saved']:>11,.0f}{v['cost']:>11,.0f}{v['saved'] - v['cost']:>11,.0f}")

    print("\nA positive net is a guard that paid for itself in the parallel world. An EMPIRICAL guard "
          "with a large negative net and a high win% is due its `reopens_when`; a HARD guard's net is not a verdict.")
    print("win% and every dollar column are over GRADED rows only; an ungraded row is counted and "
          "priced at nothing, because pnl_usd = 0.0 on an unmarkable world is an absence, not a draw.")
    print("Unclassified reasons are rules nobody owns -- add them to alpha/guards.GUARDS.")
    out = STATE / "refusal_regret.json"
    out.write_text(json.dumps({"rows": n_rows, "decisions": len(last),
                               "graded": n_graded, "ungraded": n_ungraded,
                               "by_class": per_class, "by_terminal_state": per_state,
                               "by_guard": {k: v for k, v in rows}}, indent=1, default=float),
                   encoding="utf-8")
    print(f"receipt: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
