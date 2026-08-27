"""COMPETITION_BOOK_v1 -- every limit is the negative of a measured failure.

A limit that cannot bind is decoration. Each check here makes one of them bind
on the exact input that broke the book on 2026-08-25.
"""
from __future__ import annotations

from pathlib import Path

from alpha import playbook

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("competition playbook")

# --- the two caps must be RECONCILED ---------------------------------------
# 6% per name across 6 names is 36%, and the book cap is 30%. The first version
# applied only the per-name cap and produced a 34.1% book that its own check
# then refused -- a limit that can breach another limit is not a limit.
eq = 100_000.0
check("with few names the PER-NAME cap binds",
      abs(playbook.name_budget(eq, 2) - eq * playbook.MAX_LOSS_PER_NAME) < 1e-9,
      f"{playbook.name_budget(eq, 2)}")
check("with many names the BOOK cap binds instead",
      playbook.name_budget(eq, 10) < eq * playbook.MAX_LOSS_PER_NAME)
check("  and the book total can never exceed the book cap",
      all(playbook.name_budget(eq, n) * n <= eq * playbook.MAX_LOSS_FRACTION + 1e-6
          for n in range(1, 40)),
      "this is the property the first version violated at n=6")
check("an empty book budgets nothing rather than dividing by zero",
      playbook.name_budget(eq, 0) == 0.0)

# --- sizing is from DEFINED LOSS -------------------------------------------
def refuses(f) -> bool:
    try:
        f()
    except playbook.PlaybookRefusal:
        return True
    except Exception:                                                # noqa: BLE001
        return False
    return False


check("sizing off a structure with no defined loss is REFUSED",
      refuses(lambda: playbook.size_leg(eq, 0.0)),
      "a spread's risk is (width - credit) x 100 and is known at entry; sizing "
      "off notional is how an implicit-leverage bug bought with locked capital")
check("  (a negative defined loss is refused too, not silently flipped)",
      refuses(lambda: playbook.size_leg(eq, -5.0)))
n = playbook.size_leg(eq, 700.0, n_names=6)
check("contracts fit inside the binding budget",
      n * 700.0 <= playbook.name_budget(eq, 6) + 1e-6, f"{n} x 700")

# --- a catalyst inside the window changes the distribution ------------------
check("a name with a catalyst in the window is REFUSED, not repriced",
      playbook.structure_for(0.9, has_catalyst=True) == "refuse_catalyst",
      "repricing a measured distribution from nothing is what the NVDA condor did")
check("low conviction buys the structure that survived the NULL",
      playbook.structure_for(0.5, False) == "short_put_spread")
check("high conviction is required before paying for convexity",
      playbook.structure_for(0.75, False) == "call_debit_spread",
      "long premium levers a drift; it does not create one")
check("  and the threshold is declared, not implicit",
      playbook.structure_for(0.69, False) == "short_put_spread")

# --- concentration ----------------------------------------------------------
c = playbook.check_book(1.51, 10)
check("dev's ACTUAL 1.51 effective bets would have been refused", c and "CONCENTRATION" in c[0],
      "ten tickers at 1.32 effective bets is one semiconductor bet")
check("  and the refusal says widening beats adding correlated names",
      "do not add correlated names" in c[0])
check("2.65 effective bets passes", playbook.check_book(2.65, 6) == [])
check("an EMPTY book is a refusal, not a clean pass",
      any("EMPTY BOOK" in x for x in playbook.check_book(float("nan"), 0)),
      "on 2026-08-27 the universe produced zero forecasts and no test saw it -- "
      "refusing correctly and having nothing to refuse print identically")

# --- limits are wired into the script --------------------------------------
src = Path("scripts/competition_book.py").read_text(encoding="utf-8")
for tok, why in (("EARNINGS_IN_WINDOW", "the catalyst exclusion must actually run"),
                 ("check_book", "the concentration floor must actually run"),
                 ("name_budget", "the reconciled cap must be the one used"),
                 ("MAX_ENTRIES_PER_SESSION", "one entry date is one bet")):
    check(f"competition_book consults {tok}", tok in src, why)
check("the script places NOTHING", "submit(" not in src and "NOTHING WAS SENT" in src,
      "a corrected engine with no prospective evidence does not get the keys")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
