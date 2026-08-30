"""T2 -- REFUSAL-LEDGER NAV. What would the book be worth if every refused
decision had been taken, BY REFUSAL CLASS?

    python -m scripts.refusal_nav                 # the table
    python -m scripts.refusal_nav --json          # the receipt
    python -m scripts.refusal_nav --min-marked 30 # raise the bar for a verdict

WHY BY CLASS, AND WHY THAT IS THE WHOLE POINT
=============================================
`scripts/counterfactual` already prices every road not taken and reports one
number for the gate as a whole. One number cannot be acted on: "the gate cost
us money" does not say WHICH gate, and the gates do very different jobs. The
daily-loss latch and the minimum-detectable-move test are both "refused", and
turning one off is a risk decision while turning the other off is a research
decision.

TWO KINDS OF REFUSAL, NEVER POOLED
==================================
`alpha/refusal_classes.py` splits them:

* **merit** -- MDE, edge-below-bar, refuted route, claim mismatch. The
  counterfactual asks *"was this idea any good?"*, which is the question a
  research programme wants answered.
* **book state** -- aggregate risk, gross, driver, the daily-loss latch,
  already-held. The counterfactual asks *"should the book have had room?"*,
  which is a question about SIZING, not about the idea. A positive number here
  is not evidence that the limit is wrong; it is evidence that the book was
  full, which is what a limit does.

Pooling the two produces "the gate is discarding edge -- loosen it", which is
the sentence this project printed on 2026-08-29 off $62m of arithmetic that did
not exist. That number is fixed; the pooling that made it sound actionable is
what this file refuses to repeat.

WHAT CANNOT BE MARKED IS NAMED, NOT DROPPED
===========================================
Measured 2026-08-30 over 7,599 refused rows: `ALREADY_HELD` (903) and
`DAILY_LOSS_LATCH` (538) carry NO legs at all -- they are refused before a
structure exists -- so they can never be marked, and a table that silently
omitted them would imply the latch cost nothing. Every class prints its
markable fraction, and a class with nothing markable prints CANNOT DETERMINE.

NO VERDICT ON A THIN CELL
=========================
A class is scored only above `--min-marked` (default 30) marked worlds spanning
at least `MIN_DAYS` distinct decision days; below that the row reads
`too thin`. Overlapping worlds from one afternoon are not thirty observations.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, counterfactual, ledger, refusal_classes
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.engine import equity as equity_mod

#: The risk budget every refused world is scaled to. A refusal has no size of
#: its own, so comparing them at all requires a stated notional -- the same
#: convention `scripts/counterfactual` uses, and stated rather than buried.
NOTIONAL_RISK_USD = 5_000.0
#: Distinct decision DAYS a class needs before its mean means anything. Worlds
#: from one afternoon share a market; thirty of them are not thirty draws.
MIN_DAYS = 3


def load_rows() -> tuple[list[dict], int]:
    rows, bad = [], 0
    for line in (Path(ledger.LEDGER_DIR) / "decisions.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    return rows, bad


def fetch_quotes(rows: list[dict]) -> tuple[dict, list[str]]:
    legs = {str(l[0]) for r in rows for l in (r.get("legs") or []) if l}
    quotes: dict[str, dict] = {}
    notes: list[str] = []
    if not legs:
        return quotes, ["no legs recorded on any row"]
    client = AlpacaPaper()
    shares = sorted(x for x in legs if equity_mod.is_equity_symbol(x))
    options = sorted(x for x in legs if not equity_mod.is_equity_symbol(x))
    # Share legs to the STOCK endpoint and option legs to the OPTION endpoint --
    # the split that four loops lacked until 2026-08-29, when they exited
    # non-zero seventeen times in a row and marked nothing.
    for label, syms, call in (("options", options, lambda s: client.option_quotes(s)),
                              ("shares", shares, lambda s: (client.stock_quote(s) or {}).get("quotes") or {})):
        if not syms:
            continue
        try:
            raw = call(syms)
            quotes.update({sym: {"bid": q.get("bp"), "ask": q.get("ap")} for sym, q in raw.items()})
        except BrokerRefusal as exc:
            notes.append(f"{label}: {exc}")
    missing = sorted(legs - set(quotes))
    notes.append(f"quoted {len(quotes)} of {len(legs)} legs; {len(missing)} missing")
    return quotes, notes


def build(*, min_marked: int) -> dict:
    rows, bad_lines = load_rows()
    refused = [r for r in rows if r.get("action") == "refused"]
    taken = [r for r in rows if r.get("action") == "submitted"]
    quotes, qnotes = fetch_quotes(refused + taken)

    by_class: dict[str, list] = defaultdict(list)
    unmarkable: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    days: dict[str, set] = defaultdict(set)
    no_legs: dict[str, int] = defaultdict(int)

    # A forecast-level refusal NAMES the gate that stopped its best structure.
    # Reported beside the table rather than folded into that gate's own total:
    # matching the tail first put 473 of these into AGGREGATE_RISK and inflated
    # the largest bucket with rows of a different kind.
    sub_counts: dict[str, int] = defaultdict(int)
    for r in refused:
        if refusal_classes.classify(r.get("refusal_reason")) == "NO_STRUCTURE_CLEARED":
            sub_counts[str(refusal_classes.sub_classify(r.get("refusal_reason")))] += 1

    for r in refused:
        cls = refusal_classes.classify(r.get("refusal_reason"))
        if not r.get("legs") or not (r.get("max_loss_per_unit") or 0):
            no_legs[cls] += 1
            continue
        m = counterfactual.mark(r, quotes, risk_budget_usd=NOTIONAL_RISK_USD)
        if m.mark_source == "chain":
            by_class[cls].append(m)
            days[cls].add(str(r.get("ts_utc") or "")[:10])
        else:
            why = str((m.detail or {}).get("why", "unmarkable")).split(":")[0]
            unmarkable[cls][why] += 1

    taken_marks = [counterfactual.mark(r, quotes, risk_budget_usd=NOTIONAL_RISK_USD)
                   for r in taken if r.get("legs") and (r.get("max_loss_per_unit") or 0)]
    taken_chain = [m for m in taken_marks if m.mark_source == "chain"]

    out_classes = []
    for cls in sorted(set(by_class) | set(no_legs) | set(unmarkable)):
        marks = by_class.get(cls, [])
        n_days = len(days.get(cls, ()))
        row = {
            "class": cls,
            "kind": refusal_classes.kind_of(cls),
            "n_refused": (len(marks) + no_legs.get(cls, 0)
                          + sum(unmarkable.get(cls, {}).values())),
            "n_marked": len(marks),
            "n_no_legs": no_legs.get(cls, 0),
            "n_unmarkable": dict(unmarkable.get(cls, {})),
            "n_decision_days": n_days,
        }
        if not marks:
            row["verdict"] = "CANNOT DETERMINE"
            row["why"] = ("refused before a structure existed, so there is no world to price"
                          if no_legs.get(cls) else "every world was unmarkable")
        elif len(marks) < min_marked or n_days < MIN_DAYS:
            row["nav_usd"] = round(sum(m.pnl_usd for m in marks), 2)
            row["verdict"] = "too thin"
            row["why"] = (f"{len(marks)} marked world(s) over {n_days} decision day(s); "
                          f"needs {min_marked} over {MIN_DAYS}")
        else:
            ror = [m.return_on_risk for m in marks]
            row["nav_usd"] = round(sum(m.pnl_usd for m in marks), 2)
            row["mean_return_on_risk"] = round(st.mean(ror), 4)
            row["median_return_on_risk"] = round(st.median(ror), 4)
            row["share_positive"] = round(sum(1 for m in marks if m.pnl_usd > 0) / len(marks), 3)
            row["verdict"] = "scored"
        out_classes.append(row)

    out_classes.sort(key=lambda r: (-(r.get("n_marked") or 0), r["class"]))
    return {
        "computed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "risk_budget_usd": NOTIONAL_RISK_USD,
        "min_marked": min_marked, "min_decision_days": MIN_DAYS,
        "ledger_rows": len(rows), "unparseable_lines": bad_lines,
        "n_refused": len(refused), "n_taken": len(taken),
        "quote_notes": qnotes,
        "taken_book": {
            "n_marked": len(taken_chain),
            "nav_usd": round(sum(m.pnl_usd for m in taken_chain), 2) if taken_chain else None,
            "mean_return_on_risk": round(st.mean([m.return_on_risk for m in taken_chain]), 4)
            if taken_chain else None,
            "note": ("the NULL: what the book actually did, priced the same way at the same "
                     "risk budget. A refusal class only 'cost' something relative to this."),
        },
        "classes": out_classes,
        "forecast_level_stopped_by": dict(sorted(sub_counts.items(), key=lambda kv: -kv[1])),
        "reading": [
            "MERIT classes answer 'was the idea good'. BOOK STATE classes answer 'should the "
            "book have had room' -- a positive number there says the book was full, which is "
            "what a limit is for, and is NOT an argument to raise the limit.",
            "CANNOT DETERMINE is not zero. ALREADY_HELD and DAILY_LOSS_LATCH are refused "
            "before a structure exists and can never be priced by this method.",
            "Every world is marked at one instant. Refusals from different weeks are compared "
            "at today's quotes, so this is a snapshot of standing P&L, not a return series.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-marked", type=int, default=30)
    args = ap.parse_args(argv)
    config.load_env()
    rep = build(min_marked=args.min_marked)

    if args.json:
        print(json.dumps(rep, indent=1))
        return 0

    print(f"\nREFUSAL-LEDGER NAV -- {rep['n_refused']} refused, {rep['n_taken']} taken, "
          f"at ${rep['risk_budget_usd']:,.0f} of risk per world")
    for n in rep["quote_notes"]:
        print(f"  {n}")
    if rep["unparseable_lines"]:
        print(f"  {rep['unparseable_lines']} unparseable ledger line(s) -- NOT skipped silently")
    tb = rep["taken_book"]
    if tb["nav_usd"] is not None:
        print(f"\n  THE NULL (what the book actually did): {tb['n_marked']} marked, "
              f"NAV ${tb['nav_usd']:,.0f}, mean {tb['mean_return_on_risk']:+.1%} of risk")
    else:
        # ASK "BETTER THAN WHAT?". Without the taken book priced the same way,
        # a negative NAV on a refusal class says the refused ideas would have
        # lost money -- it does NOT say refusing beat trading, because nothing
        # was measured to beat. Loud, because the table above reads like a
        # verdict and this is the sentence that makes it one or not.
        print(f"\n  THE NULL IS EMPTY: none of the {rep['n_taken']} taken decisions could be "
              "marked (their legs have expired; today's quotes cannot price a contract that "
              "no longer trades).")
        print("  So every row below says what the REFUSED ideas would be worth now, and NOT "
              "whether refusing beat trading. That comparison needs the null.")

    print(f"\n  {'class':<24}{'kind':<11}{'refused':>8}{'marked':>7}{'days':>5}"
          f"{'NAV $':>12}{'mean/risk':>11}  verdict")
    for c in rep["classes"]:
        nav = f"{c['nav_usd']:>12,.0f}" if c.get("nav_usd") is not None else f"{'-':>12}"
        mean = f"{c['mean_return_on_risk']:>+10.1%}" if c.get("mean_return_on_risk") is not None else f"{'-':>11}"
        print(f"  {c['class']:<24}{c['kind']:<11}{c['n_refused']:>8}{c['n_marked']:>7}"
              f"{c['n_decision_days']:>5}{nav}{mean}  {c['verdict']}")
        if c["verdict"] == "CANNOT DETERMINE":
            print(f"      {c['why']}")
    if rep["forecast_level_stopped_by"]:
        print("")
        print("  NO_STRUCTURE_CLEARED is a FORECAST-level refusal. What stopped its "
              "best structure:")
        for k, v in rep["forecast_level_stopped_by"].items():
            print(f"      {v:>5}  {k}")
        print("      (counted HERE, not inside those gates' own totals -- they are refusals of "
              "a different kind)")
    print()
    for line in rep["reading"]:
        print(f"  * {line}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
