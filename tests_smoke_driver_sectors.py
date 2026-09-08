"""THE DRIVER CAP MUST BIND ON RISK, NOT ON A DATA GAP.

WHAT HAPPENED (2026-09-08)
==========================
`drivers.declared_map()` reads a HUMAN-STATED theme seed written on 2026-08-28
holding 70 symbols -- uranium, quantum, fuel-cell, solar. The tracker books have
since moved to a screened universe of ~774 names that shares almost nothing with
it. On the 2026-09-08 seal, 10 of hack3's 10 names and 14 of hack6's 15 came
back `UNCLASSIFIED`.

Every UNCLASSIFIED name shares ONE bucket. That is deliberate and it is the
right default -- not knowing whether four names are independent is not evidence
that they are. But the consequence, measured on a real dry pass, was:

    ADMISSION refused TNXP long_shares x572: DRIVER: after this order the book
    would carry 41% of equity in notional on the single driver 'UNCLASSIFIED'

...on six of ten names. The book could put on FOUR names out of a sealed ten,
for ever, on every tracker book. The cap was binding on a missing input rather
than on concentration -- and the sealed book had the answer all along, because
`prediction_book` writes a `sector` on every holding and already enforces
`max_names_per_sector = 3` and `max_sector_share = 0.30` at selection time.

So the sealed sector is a THIRD DECLARED SOURCE, ordered after the human theme
seed and before UNCLASSIFIED. It obeys this module's own rule -- "declared is
the floor, and measurement may only MERGE" -- because a correlation may still
collapse two sectors into one driver, and nothing here ever SPLITS one.

WHAT THIS SUITE DEFENDS
=======================
1. the ordering of the sources, most specific first;
2. that a missing seal is a STATE and not a crash (fall through to UNCLASSIFIED);
3. that the fix actually un-blocks a real sealed book, using today's seal;
4. that UNCLASSIFIED still means one shared bucket for names nothing names --
   the conservative default must survive, or this became a loosening.
"""
import json
import sys
from pathlib import Path

from alpha import drivers

CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


print("\n-- the source ORDER, most specific first")
check("a broad index instrument is its own named driver, never a sector",
      drivers.declared_driver("SPY") == drivers.INDEX_DRIVER,
      drivers.declared_driver("SPY"))
_themed = next(iter(drivers.declared_map().items()), None)
if _themed:
    sym, theme = _themed
    check(f"the human theme seed still wins for a name it names ({sym})",
          drivers.declared_driver(sym) == theme, drivers.declared_driver(sym))
check("a name NOTHING names is still UNCLASSIFIED -- the conservative default survives",
      drivers.declared_driver("ZZZZ_NOT_A_REAL_TICKER", day="1970-01-01") == drivers.UNCLASSIFIED,
      drivers.declared_driver("ZZZZ_NOT_A_REAL_TICKER", day="1970-01-01"))
check("an empty symbol is UNCLASSIFIED and does not raise",
      drivers.declared_driver("") == drivers.UNCLASSIFIED)

print("\n-- a missing sealed book is a STATE, not a crash")
drivers.sealed_sector_map.cache_clear()
check("an absent seal returns an empty map rather than raising",
      drivers.sealed_sector_map("1970-01-01") == {})
check("and every symbol then falls through to UNCLASSIFIED",
      drivers.declared_driver("ANIP", day="1970-01-01") == drivers.UNCLASSIFIED)

print("\n-- the fix un-blocks a REAL sealed book (this is the whole point)")
# `run_tests.py` redirects AAT_LEDGER_DIR to a per-run temp directory so no suite
# can append to the production ledger, and `sealed_sector_map` reads from exactly
# that root. So the seal is STAGED into the temp ledger rather than read around
# the redirection: this exercises the real production path and still cannot touch
# `state/`. Reading around the guard would have tested a path production never
# takes, which is worse than not testing it.
import os as _os
import shutil as _shutil

_REPO_SEAL = Path(__file__).resolve().parent / "state" / "predictions" / "2026-09-08.json"
_root = _os.getenv("AAT_LEDGER_DIR")
SEAL = _REPO_SEAL
if _root and _REPO_SEAL.exists():
    _dst = Path(_root) / "predictions"
    _dst.mkdir(parents=True, exist_ok=True)
    _shutil.copy2(_REPO_SEAL, _dst / "2026-09-08.json")
    SEAL = _dst / "2026-09-08.json"
drivers.sealed_sector_map.cache_clear()
if not SEAL.exists():
    print("  SKIP: no 2026-09-08 seal on this machine -- CANNOT DETERMINE, not a pass")
else:
    blob = json.loads(SEAL.read_text(encoding="utf-8"))
    for book, expected_n in (("hack3", 10), ("hack6", 15)):
        holds = (blob["portfolios"][book].get("holdings") or [])
        check(f"{book}: the seal still holds {expected_n} names", len(holds) == expected_n,
              str(len(holds)))
        got = [drivers.declared_driver(h["symbol"], day="2026-09-08") for h in holds]
        unc = sum(1 for g in got if g == drivers.UNCLASSIFIED)
        check(f"{book}: NO name is left UNCLASSIFIED", unc == 0, f"{unc} unclassified")
        biggest = max(got.count(g) for g in set(got))
        # The cap is 40% of the profile's gross authority. With per-name notional
        # at 8.3% (hack3) and 6% (hack6), four-plus names in ONE driver is what
        # tripped it. Three is the seal's own `max_names_per_sector`.
        check(f"{book}: the largest driver holds {biggest} of {len(holds)} names, "
              f"within the seal's own max_names_per_sector of 3",
              biggest <= 3, f"{biggest}")

print("\n-- a sector driver says WHICH source named it")
check("sector drivers carry the SECTOR_PREFIX so a refusal can name its source",
      drivers.SECTOR_PREFIX == "sector:")
if SEAL.exists():
    d = drivers.declared_driver("ANIP", day="2026-09-08")
    check("a sealed name resolves to a prefixed sector driver",
          d.startswith(drivers.SECTOR_PREFIX), d)

print(f"\n{CHECKS} checks, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print(f"  FAILED: {f}")
    sys.exit(1)
