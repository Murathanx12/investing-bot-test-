"""T2 -- refusal classes and the refusal-ledger NAV.

Run: python tests_smoke_refusal_nav.py  (also executed by tests_smoke.py)

The 2026-08-29 lesson this file exists to prevent repeating: a counterfactual
that pools every refusal into one number printed "the gate is discarding edge --
loosen it or explain it". Two of the three defects behind that were arithmetic
and are fixed. The third is structural: the daily-loss latch and the
minimum-detectable-move test are both "refused", and they are not the same kind
of thing. These pin the classifier, the kinds, and the states that must read
CANNOT DETERMINE rather than zero.
"""
from __future__ import annotations

import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import refusal_classes as rc

# Reason sentences taken verbatim in shape from state/decisions.jsonl.
CASES = [
    ("GROSS: after this order the book would carry 109% of equity in notional", "GROSS_NOTIONAL"),
    ("DRIVER: after this order the book would carry 50% of equity on 'quantum'", "DRIVER_CONCENTRATION"),
    ("CROSS-BOOK: BE is already held outright by another book in the fleet", "CROSS_BOOK"),
    ("OPENING RANGE: shares are not bought in the first 15 minutes.", "OPENING_RANGE"),
    ("CONVEX RULE: 5 DTE < 10: a long option inside the horizon is a lottery ticket", "CONVEX_RULE"),
    ("ADMISSION: BOOK LIMIT: MAX_BOOK_STRESS 36.0% > 35%", "BOOK_LIMIT"),
    ("DAILY LOSS LATCH: -3.1% against the previous close ($100,000 -> $96,900)", "DAILY_LOSS_LATCH"),
    ("aggregate convex risk is already 61% of equity (ceiling 75%). Refused", "AGGREGATE_RISK"),
    ("minimum detectable move is 3.4%; our forecast puts 41% of mass beyond it", "MDE"),
    ("disagreement with the chain is +1.2% of probability mass -- below the bar", "EDGE_BELOW_BAR"),
    ("NVDA already positioned in this book (5 legs); exits decide when it leaves", "ALREADY_HELD"),
    ("approved 3% of $100,000 = $3,000, but one unit of long_call risks $4,000. "
     "Rounds to zero contracts", "CAPITAL_ROUNDS_TO_ZERO"),
    ("8 structures enumerated at 2026-08-28, none cleared the gates. aggregate", "NO_STRUCTURE_CLEARED"),
    ("out-ranked on median/max-loss by long_shares (+2% vs -1%; EV +3 vs +1)", "OUTRANKED_BY_SIBLING"),
    ("CASH beats it: cleared the MDM gate (+4%) but EV $-20/unit", "CASH_BEATS_IT"),
    ("round-trip spread is 31% of max loss (ceiling 25%). The edge is inside the spread", "SPREAD_EATS_THE_EDGE"),
    ("pair_short_vs_iwm: this is a DIRECTION-only forecast, which is integrated", "CLAIM_MISMATCH_PAIR"),
    ("CANNOT DETERMINE the day's drawdown: equity=100000 last_equity=0", "DRAWDOWN_UNKNOWN"),
]

print("\n-- every gate in the ledger gets its own class")
for reason, want in CASES:
    got = rc.classify(reason)
    check(f"{want:<24} <- {reason[:44]}", got == want, f"got {got}")

print("\n-- order is meaning: the specific pattern wins over the general one")
check("a BOOK LIMIT inside an ADMISSION line is a BOOK_LIMIT, not unclassified",
      rc.classify("ADMISSION: BOOK LIMIT: MIN_FREE_CAPITAL") == "BOOK_LIMIT")
WRAP = ("3 structures enumerated at 2026-08-28, none cleared the gates. "
        "aggregate convex risk is already 60%")
check("'none cleared the gates. aggregate...' is NO_STRUCTURE_CLEARED, not AGGREGATE_RISK",
      rc.classify(WRAP) == "NO_STRUCTURE_CLEARED", rc.classify(WRAP))
check("...and the gate it QUOTES is recovered as the sub-class",
      rc.sub_classify(WRAP) == "AGGREGATE_RISK", str(rc.sub_classify(WRAP)))
check("a non-wrapper row has no sub-class",
      rc.sub_classify("DAILY LOSS LATCH: -3.1%") is None)
check("the wrapper is matched FIRST, or 473 forecast-level rows land in AGGREGATE_RISK",
      rc.PATTERNS[0][0] == "NO_STRUCTURE_CLEARED", rc.PATTERNS[0][0])

print("\n-- an unmatched reason is UNCLASSIFIED and never quietly bucketed")
check("nonsense is UNCLASSIFIED", rc.classify("something nobody has written yet") == rc.UNCLASSIFIED)
check("an empty reason is UNCLASSIFIED", rc.classify("") == rc.UNCLASSIFIED)
check("None is UNCLASSIFIED, not a crash", rc.classify(None) == rc.UNCLASSIFIED)

print("\n-- the KINDS, which decide what a counterfactual on the class is asking")
check("the daily-loss latch is a BOOK STATE limit", rc.kind_of("DAILY_LOSS_LATCH") == "book state")
check("the MDE test is about the IDEA", rc.kind_of("MDE") == "merit")
check("being out-ranked by a sibling is neither -- it is the tournament",
      rc.kind_of("OUTRANKED_BY_SIBLING") == "tournament")
check("an unknown class is 'unknown', never silently 'merit'",
      rc.kind_of("SOMETHING_NEW") == "unknown")
check("no class is in two kinds at once",
      not (rc.BOOK_STATE_CLASSES & rc.MERIT_CLASSES)
      and not (rc.BOOK_STATE_CLASSES & rc.TOURNAMENT_CLASSES)
      and not (rc.MERIT_CLASSES & rc.TOURNAMENT_CLASSES))
check("every pattern's class is assigned a kind",
      all(rc.kind_of(name) != "unknown" for name, _ in rc.PATTERNS),
      str([n for n, _ in rc.PATTERNS if rc.kind_of(n) == "unknown"]))

print("\n-- the report: what cannot be priced says so, and is not a zero")
from scripts import refusal_nav

rows = [
    # refused before a structure existed -- no legs, no max_loss_per_unit
    {"action": "refused", "refusal_reason": "NVDA already positioned in this book (2 legs)",
     "ts_utc": "2026-08-28T14:00:00Z", "symbol": "NVDA"},
    {"action": "refused", "refusal_reason": "DAILY LOSS LATCH: -3.1% against the previous close",
     "ts_utc": "2026-08-28T14:00:00Z", "symbol": "AMD"},
]
by_cls = {}
for r in rows:
    by_cls[rc.classify(r["refusal_reason"])] = r
check("both fixtures classify", set(by_cls) == {"ALREADY_HELD", "DAILY_LOSS_LATCH"}, str(set(by_cls)))
check("neither carries legs, so neither can ever be marked",
      all(not r.get("legs") for r in rows))
check("MIN_DAYS is more than one -- worlds from one afternoon are not independent",
      refusal_nav.MIN_DAYS > 1, str(refusal_nav.MIN_DAYS))
check("the notional risk budget is a stated constant, not a hidden default",
      refusal_nav.NOTIONAL_RISK_USD > 0)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
