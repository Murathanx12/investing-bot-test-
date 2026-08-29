"""Smoke checks for DRIVER concentration (`alpha/drivers.py` + the admission gate).

Run: python tests_smoke_drivers.py  (also executed by tests_smoke.py)

28 Aug, hack3: twelve names bought in thirteen seconds, ELEVEN stopped between
09:36 and 09:48. Gross was 300%; the gross cap (P0.0) fixes the size. These
pin the OTHER half -- that twelve tickers on three drivers get three drivers'
worth of authority, not twelve names' worth.
"""
from __future__ import annotations

import math

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import admission, book, drivers
from alpha.engine import sizing

EQ = 100_000.0

# Friday's book, by name. The roadmap read it as three drivers -- uranium,
# quantum, fuel-cell/solar -- and that is what the declared taxonomy must say
# without being told the answer.
FRIDAY = ["QUBT", "IONQ", "RGTI", "OKLO", "SMR", "LEU", "BE", "PLUG", "FSLR", "QS", "SLDP", "NVDA"]


def _shares(symbol, spot=100.0, stop=0.08):
    """A long-share structure priced so one unit costs `spot` of notional."""
    return sizing.Structure(symbol, "long_shares", direction="up", entry_cost=spot,
                            max_loss=spot * stop, breakeven_move=0.0002, implied_move=0.03,
                            quote_spread_pct=0.0002, days_to_expiry=2,
                            legs=((symbol, "buy", 1),), quote={"last_trade": spot})


def bk(total=0.0, by=None):
    return book.BookRisk(equity=EQ, structures=[], residuals=[], unbounded=False, max_loss_usd=total,
                         by_underlying=by or {}, by_node={}, premium_paid_usd=0.0)


print("\n-- the DECLARED taxonomy is loaded and non-empty")
m = drivers.declared_map()
check("themes seed parses to a symbol -> theme map", len(m) > 30, f"{len(m)} symbols")
check("at least the seven human-stated themes", len(set(m.values())) >= 7, str(sorted(set(m.values()))))
check("an index instrument is its own NAMED driver, not UNCLASSIFIED",
      drivers.declared_driver("SPY") == drivers.INDEX_DRIVER)
check("a symbol nobody declared falls to the ONE shared bucket",
      drivers.declared_driver("ZZZZ_NOT_A_TICKER") == drivers.UNCLASSIFIED)
check("case and whitespace do not create a second driver",
      drivers.declared_driver(" qubt ") == drivers.declared_driver("QUBT"))
check("the empty symbol is UNCLASSIFIED, not a crash",
      drivers.declared_driver("") == drivers.UNCLASSIFIED)

print("\n-- Friday's twelve names resolve to a handful of drivers, not twelve")
d, note = drivers.resolve(FRIDAY)
groups = {}
for s, g in d.items():
    groups.setdefault(g, []).append(s)
check("twelve tickers -> at most six drivers", len(groups) <= 6, f"{len(groups)}: {sorted(groups)}")
check("the quantum names share one driver",
      len({d["QUBT"], d["IONQ"], d["RGTI"]}) == 1, str([d["QUBT"], d["IONQ"], d["RGTI"]]))
check("the nuclear names share one driver",
      len({d["OKLO"], d["SMR"], d["LEU"]}) == 1, str([d["OKLO"], d["SMR"], d["LEU"]]))
check("quantum and nuclear are NOT the same driver by declaration alone",
      d["QUBT"] != d["OKLO"])
check("with no returns the note says the taxonomy is declared only",
      note.startswith("declared only"), note)

print("\n-- measurement may MERGE two drivers; it may never SPLIT one")
# One shared factor plus a small idiosyncratic wobble: every name moves together.
base = [math.sin(i / 3.0) * 0.03 for i in range(60)]
together = {s: [b + 0.0005 * ((i + hash(s) % 7) % 3 - 1) for i, b in enumerate(base)]
            for s in ("QUBT", "IONQ", "OKLO", "SMR")}
d2, note2 = drivers.resolve(["QUBT", "IONQ", "OKLO", "SMR"], together)
check("two declared drivers that MOVED together collapse into one",
      len(set(d2.values())) == 1, f"{sorted(set(d2.values()))} | {note2}")
check("the note names the merge and its correlation", "merged at rho>=" in note2, note2)

# The opposite: names inside ONE declared driver that did not co-move stay one
# driver. A low correlation is never licence to claim breadth.
apart = {"QUBT": [0.01 * ((i % 5) - 2) for i in range(60)],
         "IONQ": [0.01 * ((i % 7) - 3) for i in range(60)]}
d3, note3 = drivers.resolve(["QUBT", "IONQ"], apart)
check("a LOW correlation inside a declared driver does not split it",
      len(set(d3.values())) == 1, f"{sorted(set(d3.values()))} | {note3}")

short = {s: v[:5] for s, v in together.items()}
d4, note4 = drivers.resolve(["QUBT", "OKLO"], short)
check("a series shorter than MIN_SESSIONS merges nothing and SAYS so",
      len(set(d4.values())) == 2 and "overlapping sessions" in note4, note4)
check("and it does not claim independence", "not evidence of independence" in note4, note4)

print("\n-- notional by driver, and the cap arithmetic")
by_sym = {"QUBT": 10_000.0, "IONQ": 10_000.0, "OKLO": 10_000.0}
bydrv = drivers.notional_by_driver(by_sym, d)
check("per-symbol notional folds into per-driver notional",
      abs(sum(bydrv.values()) - 30_000.0) < 1e-6 and bydrv[d["QUBT"]] == 20_000.0, str(bydrv))
check("a symbol the pass never saw still counts against its declared driver",
      drivers.notional_by_driver({"RGTI": 5_000.0})[drivers.declared_driver("RGTI")] == 5_000.0)
check("basket gross 100% -> one driver may carry 40% of equity",
      abs(drivers.cap_fraction(sizing.gross_cap("basket")) - 0.40) < 1e-9)
check("conservative gross 60% -> 24%, so the cap moves WITH the profile",
      abs(drivers.cap_fraction(sizing.gross_cap("conservative")) - 0.24) < 1e-9)

print("\n-- the gate: four names on one driver, and the fifth is refused")
cap = drivers.cap_fraction(sizing.gross_cap("basket"))          # 0.40
held: dict[str, float] = {}
admitted = []
for sym in ("QUBT", "IONQ", "RGTI", "ARQQ", "QMCO"):
    drv = drivers.declared_driver("QUBT")                       # force one driver
    a = admission.admit(bk(), _shares(sym), 100, equity=EQ, aggregate_cap=0.36,
                        gross_cap=sizing.gross_cap("basket"), gross_usd=sum(held.values()),
                        add_notional_usd=10_000.0,
                        driver="quantum", driver_cap=cap,
                        driver_gross_usd=held.get("quantum", 0.0),
                        driver_note="declared only")
    if a.ok:
        admitted.append(sym)
        held["quantum"] = held.get("quantum", 0.0) + 10_000.0
    else:
        last = a
check("four names at 10% fill the 40% driver cap", len(admitted) == 4, str(admitted))
check("the fifth is refused, and the refusal names DRIVER", not last.ok and last.reason.startswith("DRIVER"),
      last.reason[:100])
check("the refusal carries the driver and the post-trade fraction",
      last.metrics.get("driver") == "quantum" and last.metrics.get("post_driver_frac") == 0.5,
      str({k: v for k, v in last.metrics.items() if k.startswith("driver") or k.startswith("post_driver")}))
check("the refusal quotes the taxonomy it used", "declared only" in last.reason, last.reason[-60:])
check("worst case on one driver at the 8% basket stop is 3.2%, not 8%",
      abs(cap * 0.08 - 0.032) < 1e-9)

print("\n-- the gate is inert when it has nothing to say")
a = admission.admit(bk(), _shares("QUBT"), 100, equity=EQ, aggregate_cap=0.36,
                    gross_cap=1.0, gross_usd=0.0, add_notional_usd=10_000.0)
check("no driver_cap supplied -> no driver check, no crash", a.ok, a.reason[:60])
check("and the metrics do not claim a driver was checked", "post_driver_frac" not in a.metrics)

a = admission.admit(bk(), _shares("QUBT"), 100, equity=EQ, aggregate_cap=0.36,
                    gross_cap=1.0, gross_usd=0.0, add_notional_usd=10_000.0,
                    driver="quantum", driver_cap=0.40, driver_gross_usd=0.0)
check("an order inside the cap is admitted and the metric is recorded",
      a.ok and a.metrics["post_driver_frac"] == 0.1, str(a.metrics.get("post_driver_frac")))

print("\n-- GROSS refuses before DRIVER: the specific number beats the general one")
a = admission.admit(bk(), _shares("QUBT"), 100, equity=EQ, aggregate_cap=0.36,
                    gross_cap=1.0, gross_usd=99_000.0, add_notional_usd=10_000.0,
                    driver="quantum", driver_cap=0.40, driver_gross_usd=90_000.0)
check("both caps breached -> GROSS is the reason given", not a.ok and a.reason.startswith("GROSS"),
      a.reason[:60])

print("\n-- an unreadable book still refuses on GROSS, never on a driver it invented")
a = admission.admit(bk(), _shares("QUBT"), 100, equity=EQ, aggregate_cap=0.36,
                    gross_cap=1.0, gross_usd=None, add_notional_usd=10_000.0,
                    driver="quantum", driver_cap=0.40, driver_gross_usd=0.0)
check("gross unmeasurable -> refused, and the reason is GROSS",
      not a.ok and "CANNOT DETERMINE" in str(a.metrics.get("gross")), a.reason[:70])

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
