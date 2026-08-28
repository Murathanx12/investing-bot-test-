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
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from alpha import guards

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


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
                                               str(r.get("ts_utc", ""))[:10])

    per_guard = defaultdict(lambda: {"n": 0, "saved": 0.0, "cost": 0.0, "wins": 0, "sample": ""})
    per_class = defaultdict(lambda: {"n": 0, "saved": 0.0, "cost": 0.0})
    for reason, pnl, sym, inst, day in last.values():
        g = guards.classify(reason)
        key = g.key if g else "UNCLASSIFIED: " + reason[:48]
        cls = g.cls if g else "UNCLASSIFIED"
        a = per_guard[key]
        a["n"] += 1
        if pnl < 0:
            a["saved"] += -pnl
        else:
            a["cost"] += pnl
            a["wins"] += 1
        a["sample"] = a["sample"] or f"{sym} {inst} {day}"
        c = per_class[cls]
        c["n"] += 1
        c["saved"] += -pnl if pnl < 0 else 0.0
        c["cost"] += pnl if pnl > 0 else 0.0

    print(f"{n_rows:,} ledger rows; {len(last):,} distinct refused decisions priced (last mark each)\n")
    print(f"{'class':<13}{'n':>8}{'saved $':>12}{'cost $':>12}{'net $':>12}")
    for cls in ("HARD", "EMPIRICAL", "TOURNAMENT", "RETEST_DUE", "UNCLASSIFIED"):
        c = per_class.get(cls)
        if c:
            print(f"{cls:<13}{c['n']:>8,}{c['saved']:>12,.0f}{c['cost']:>12,.0f}{c['saved'] - c['cost']:>12,.0f}")
    print(f"\n{'guard':<44}{'class':<12}{'n':>7}{'win%':>6}{'saved $':>11}{'cost $':>11}{'net $':>11}  sample")
    rows = sorted(per_guard.items(), key=lambda kv: -(kv[1]["n"]))
    for key, a in rows[:args.top]:
        g = guards.classify(key) if not key.startswith("UNCLASSIFIED") else None
        cls = next((x.cls for x in guards.GUARDS if x.key == key), "UNCLASSIFIED")
        win = (a["wins"] / a["n"]) if a["n"] else 0.0
        print(f"{key[:43]:<44}{cls:<12}{a['n']:>7,}{win:>6.0%}{a['saved']:>11,.0f}{a['cost']:>11,.0f}{a['saved'] - a['cost']:>11,.0f}  {a['sample']}")
    print("\nA positive net is a guard that paid for itself in the parallel world. An EMPIRICAL guard "
          "with a large negative net and a high win% is due its `reopens_when`; a HARD guard's net is not a verdict.")
    print("Unclassified reasons are rules nobody owns -- add them to alpha/guards.GUARDS.")
    out = STATE / "refusal_regret.json"
    out.write_text(json.dumps({"rows": n_rows, "decisions": len(last), "by_class": per_class,
                               "by_guard": {k: v for k, v in rows}}, indent=1, default=float), encoding="utf-8")
    print(f"receipt: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
