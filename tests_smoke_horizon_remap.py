"""THE HORIZON REMAP: every book holds, every book's worst case is printed.

Murat, 2026-09-07: "make sure the paper accounts now are full with orders lets
use money and hold stocks for more than one day dont buy and sold."

WHAT THIS SUITE IS DEFENDING
============================
Two separate failures, both of which have already happened here:

  1. A BOOK THAT CANNOT HOLD ITS OWN THESIS. `min_normal_hold_sessions` has been
     honoured since 2026-09-05 and the accounts still emptied, because
     HARD_RISK_LIMIT is checked ABOVE the hold and the stop widths were profile
     constants unrelated to the names being bought. Measured on the 2026-09-07
     seal (docs/RECEIPT_2026-09-07_STOP_WIDTH_VS_HOLD.json): hack6's 3% stop was
     0.98 daily sd of its own holdings, and 56.3% of entries were stopped out
     before session 10 of a 21-session thesis.

  2. PROSE THAT DISAGREES WITH CONFIGURATION. On 2026-08-28 a comment said the
     worst case was -9% while the configuration made it -24%. So nothing here
     trusts a written number: every assertion RECOMPUTES from the modules, and
     the seal-derived sizing outranks the declared sizing wherever both exist.
"""
import json
import sys
from pathlib import Path

from alpha import contract, fleet

CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


print("\n-- every book in the fleet can hold for more than one session")
for role in fleet.FLEET:
    k = contract.defaults_for(role, profile=fleet.FLEET[role].profile)
    check(f"{role}: minimum hold is at least 2 sessions",
          int(k["min_normal_hold_sessions"]) >= 2,
          f"hold={k['min_normal_hold_sessions']}")
    check(f"{role}: the horizon is at least the hold -- it can exit normally",
          int(k["expected_horizon_sessions"]) >= int(k["min_normal_hold_sessions"]),
          f"{k['expected_horizon_sessions']}/{k['min_normal_hold_sessions']}")

print("\n-- no book still charges the flat 3% that emptied the accounts")
for role in fleet.FLEET:
    k = contract.for_book(role, day="2026-09-08", risk_budget_usd=100.0,
                          profile=fleet.FLEET[role].profile)
    check(f"{role}: declared stop {k.stop_fraction():.0%} is wider than the flat 3%",
          k.stop_fraction() > 0.03, f"{k.stop_fraction():.3f}")

print("\n-- a forecast may not undercut a book's declared floor")
short = contract.for_book("hack2", day="2026-09-08", risk_budget_usd=100.0,
                          profile="aggressive", expected_horizon_sessions=1)
check("a 1-session forecast is lifted to the 2-session floor, and validates",
      (short.expected_horizon_sessions, short.min_normal_hold_sessions) == (2, 2)
      and contract.validate(short.as_dict()) == [],
      f"{short.expected_horizon_sessions}/{short.min_normal_hold_sessions}")

print("\n-- the worst case is COMPUTED, and no book is levered (CLAUDE.md rule 4)")
for role in contract.BOOK_SIZING:
    w = contract.worst_case(role)
    check(f"{role}: gross {w['gross_over_equity']:.0%} of its own equity, no leverage",
          w["gross_over_equity"] <= 1.0, str(w))
    check(f"{role}: worst case {w['worst_case_frac']:.2%} = n x notional x stop",
          abs(w["worst_case_frac"] - w["n"] * w["notional_each"] * w["stop_frac"]) < 1e-9,
          str(w))
    # A DECLARED CEILING, so a future widening cannot pass unnoticed. 35% is
    # hack1's benchmark arm, whose "stop" is a market crash and not a rule.
    check(f"{role}: worst case is inside the fleet's 35% ceiling",
          w["worst_case_frac"] <= 0.35, f"{w['worst_case_frac']:.2%}")

print("\n-- long premium reports its TRUE bound, not just its stop charge")
w5 = contract.worst_case("hack5")
check("hack5 reports an absolute bound as well as a stop charge",
      "absolute_bound_frac" in w5 and w5["absolute_bound_frac"] > w5["worst_case_frac"],
      str(w5))

print("\n-- the SEAL outranks the declared sizing, and says which it used")
FAKE = {"portfolios": {"hack6": {"max_notional_each": 0.06,
                                 "holdings": [{"symbol": f"S{i}"} for i in range(15)]}}}
w_declared = contract.worst_case("hack6")
w_seal = contract.worst_case("hack6", seal=FAKE)
check("without a seal the source is 'declared'", w_declared["sizing_source"] == "declared")
check("with a seal the source is 'seal'", w_seal["sizing_source"] == "seal")
check("and the seal's sizing is the one reported",
      abs(w_seal["notional_each"] - 0.06) < 1e-9 and w_seal["n"] == 15, str(w_seal))
check("an EMPTY seal falls back to declared rather than reporting a zero book",
      contract.worst_case("hack6", seal={"portfolios": {"hack6": {"holdings": []}}})
      ["sizing_source"] == "declared")

print("\n-- the receipt behind the widening exists and carries its caveats")
r = Path(r"C:\Users\mrthn\aegis-finance\docs\RECEIPT_2026-09-07_STOP_WIDTH_VS_HOLD.json")
check("the stop-width receipt is on disk", r.exists(), str(r))
if r.exists():
    d = json.loads(r.read_text(encoding="utf-8"))
    check("it states that P(stop before hold) is a LOWER bound (closes only)",
          any("LOWER bound" in c for c in d["caveats"]))
    check("it refuses to claim an edge", any("no edge is claimed" in c for c in d["caveats"]))

print(f"\n{CHECKS} checks, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print(f"  FAILED: {f}")
    sys.exit(1)
