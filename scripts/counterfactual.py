"""Mark every road not taken, and publish the score whichever way it goes.

    python -m scripts.counterfactual                 # report only
    python -m scripts.counterfactual --record        # also append to the chain
    python -m scripts.counterfactual --json

Reads the decision ledger, gathers each decision's family -- the structure we
took, the seven we enumerated and did not, and the null that costs nothing --
prices all of them forward off the CURRENT chain at the SAME risk budget, and
prints what that says about the gate.

The number to distrust is `opportunity_capture` on a day when nothing was
marked: an empty report is an absence, not a 100%. Every line reports how many
worlds it could not price and why.
"""

from __future__ import annotations

import json
import sys

from alpha import config, counterfactual, ledger
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

#: The risk budget every world is scaled to when the real decision committed
#: nothing (a refusal has no position size of its own). Comparing refusals at a
#: notional budget is the only way to compare them at all -- and it is stated
#: here rather than buried, because it is an assumption, not a measurement.
NOTIONAL_RISK_USD = 5_000.0


def main() -> int:
    config.load_env()
    rows = ledger.read_all()
    if not rows:
        print("\n  no decisions recorded yet -- nothing to counterfactual.\n")
        return 0

    families = counterfactual.base_ids(rows)
    print(f"\nCounterfactual marking -- {len(families)} decision families "
          f"in {len(rows)} ledger rows\n")

    # One quote call for every leg in every world, taken and untaken alike.
    legs: set[str] = set()
    for row in rows:
        for leg in (row.get("legs") or []):
            if leg and isinstance(leg, (list, tuple)):
                legs.add(str(leg[0]))
    quotes: dict[str, dict] = {}
    if legs:
        try:
            client = AlpacaPaper()
            raw = client.option_quotes(sorted(legs))
            quotes = {sym: {"bid": q.get("bp"), "ask": q.get("ap")}
                      for sym, q in raw.items()}
            print(f"  quoted {len(quotes)} of {len(legs)} distinct legs")
        except BrokerRefusal as exc:
            print(f"  [FAIL] could not fetch quotes: {exc}")
            return 2
    else:
        print("  no legs recorded on any row -- older rows predate leg capture")

    marks: list[counterfactual.Mark] = []
    for base in families:
        worlds = counterfactual.worlds_for(rows, base)
        budget = max((float(w.get("max_loss_usd") or 0.0) for w in worlds),
                     default=0.0) or NOTIONAL_RISK_USD
        for world in worlds:
            marks.append(counterfactual.mark(world, quotes, risk_budget_usd=budget))

    summary = counterfactual.report(marks)
    if "--json" in sys.argv:
        print(json.dumps(summary, indent=2))
    else:
        print()
        for key, value in summary.items():
            print(f"  {key:26s} {value}")
        print()
        losers = sorted((m for m in marks if m.mark_source == "chain"),
                        key=lambda m: m.pnl_usd)
        for m in losers[:3] + losers[-3:]:
            print(f"    {m.action:11s} {m.kind:15s} {m.symbol:22s} "
                  f"{m.pnl_usd:+10,.0f}  ({m.return_on_risk:+.1%} of risk)")
        print()

    if "--record" in sys.argv:
        n = counterfactual.record_marks(marks)
        ok, msg = ledger.verify_chain("counterfactual")
        print(f"  recorded {n} marks; chain {'verifies' if ok else 'BROKEN: ' + msg}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
