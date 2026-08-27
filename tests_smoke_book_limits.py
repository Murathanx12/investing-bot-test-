"""Book limits: implemented, tested, enforced by nothing."""
import sys

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import book_limits as B

EQ = 100_000.0

print("\n-- a clean book breaches nothing")
ok = B.evaluate(equity=EQ, true_max_loss=20_000, free_capital=50_000,
                thesis_weights={"A": 1, "B": 1, "C": 1, "D": 1, "E": 1, "F": 1}, n_risk=3.2)
check("no breaches on a spread, lightly-loaded book", ok == [], B.summary(ok))
check("would_admit agrees", B.would_admit(ok))

print("\n-- the actual dev book on 2026-08-26 must breach")
dev = B.evaluate(equity=97_559, true_max_loss=53_649, free_capital=76_736,
                 thesis_weights={"NVDA": 25270, "AMD": 10785, "QQQ": 8952,
                                 "SPY": 2322, "MSFT": 598, "AAPL": 186, "NIO": 136},
                 n_risk=1.51)
names = {b.limit for b in dev}
check("55% true max loss breaches MAX_BOOK_STRESS", "MAX_BOOK_STRESS" in names, str(names))
check("NVDA at 52% breaches MAX_SINGLE_THESIS", "MAX_SINGLE_THESIS" in names)
check("1.51 bets breaches MIN_EFFECTIVE_N_RISK", "MIN_EFFECTIVE_N_RISK" in names)
check("free capital at 79% does NOT breach", "MIN_FREE_CAPITAL" not in names)
check("dev at 1.51 does NOT get the liquidation clause",
      not any("forced liquidation" in b.detail for b in dev),
      "1.51 is above the 1.43 reference, so that clause must stay silent")

print("\n-- exp1, which is BELOW the reference")
exp1 = B.evaluate(equity=94_824, true_max_loss=56_889, free_capital=56_443,
                  thesis_weights={"SPY": 24168, "QQQ": 12549, "NVDA": 10212,
                                  "IWM": 9727, "AAPL": 185, "NIO": 72},
                  n_risk=1.26)
check("1.26 is flagged against the $20bn reference",
      any("forced liquidation" in b.detail for b in exp1),
      f"{[b.limit for b in exp1]}")

print("\n-- an unmeasurable concentration is a BREACH, not a pass")
unk = B.evaluate(equity=EQ, true_max_loss=10_000, free_capital=80_000, n_risk=None)
check("n_risk=None breaches rather than passing silently",
      any(b.limit == "MIN_EFFECTIVE_N_RISK" for b in unk), B.summary(unk))
check("...and says why", any("could NOT be measured" in b.detail for b in unk))

print("\n-- thresholds carry derivations, and the one without evidence is UNSET")
check("MAX_DAILY_THETA is deliberately None", B.MAX_DAILY_THETA is None,
      "a threshold without a derivation is a guess wearing a policy's clothes")
check("the effective-N floor sits ABOVE every measured failure state",
      B.MIN_EFFECTIVE_N_RISK > max(1.43, 1.51, 1.27),
      f"floor {B.MIN_EFFECTIVE_N_RISK} vs worst observed 1.51")
check("the reference is the measured liquidation value",
      abs(B.REFERENCE_N_RISK_AT_LIQUIDATION - 1.43) < 1e-9)

print("\n-- it is ENFORCED at the admission choke point (was: by nothing)")
import pathlib
src = pathlib.Path(".")
# INVERTED 2026-08-27. This check used to assert that NO execution path imported
# book_limits -- it pinned the module's "written but never called" status. That
# status is now closed, so the same check asserts the opposite: admission must
# enforce them, or the limits are decoration again.
adm = (src / "alpha/admission.py").read_text(encoding="utf-8", errors="replace")
check("admission imports book_limits", "book_limits" in adm)
check("and REFUSES on a binding breach", "BOOK LIMIT" in adm and "book_limits.refusing" in adm)
check("evaluated on the POST-trade book, not the current one", "true_max_loss=post_total" in adm,
      "a limit checked before the order is a limit checked too late")

# THE PROPERTY THAT MADE THIS SAFE TO TURN ON: a pristine account must be able to
# place its first order. Both diversification limits are arithmetic identities on
# a one-position book, so enforcing them from trade #1 deadlocks the account
# forever -- and a gate that cannot go green is a broken gate, not a strict one.
first = B.evaluate(equity=100_000, true_max_loss=2_000, free_capital=98_000,
                   thesis_weights={"NVDA": 2_000}, n_risk=1.0, n_positions=1)
check("a healthy FIRST trade on a pristine $100k account is not refused",
      B.refusing(first) == [], str([b.limit for b in B.refusing(first)]))
check("but the breach is still MEASURED and reported, not hidden",
      len(first) == 2 and all(not b.binding for b in first),
      "a small book with 100% in one name must not read as clean")
check("the warm-up is stated on the breach itself",
      any("not yet binding" in b.line() for b in first))

sixth = B.evaluate(equity=100_000, true_max_loss=10_000, free_capital=90_000,
                   thesis_weights={"NVDA": 10_000}, n_risk=1.0,
                   n_positions=B.DIVERSIFICATION_BINDS_AT)
check("once five positions are held, the sixth is bound by both",
      len(B.refusing(sixth)) == 2, str([b.limit for b in B.refusing(sixth)]))

# UNMEASURED tracks the same schedule. Binding it always refused every fresh
# account for failing to measure something that is arithmetic at one position.
un_small = B.evaluate(equity=100_000, true_max_loss=2_000, free_capital=98_000,
                      thesis_weights={"NVDA": 2_000}, n_risk=None, n_positions=1)
un_big = B.evaluate(equity=100_000, true_max_loss=2_000, free_capital=98_000,
                    thesis_weights={"A": 500, "B": 500, "C": 500, "D": 500, "E": 500},
                    n_risk=None, n_positions=5)
check("an UNMEASURED concentration does not refuse a one-position book",
      not any(b.limit == "MIN_EFFECTIVE_N_RISK" and b.binding for b in un_small))
check("but it DOES refuse once the limit binds",
      any(b.limit == "MIN_EFFECTIVE_N_RISK" and b.binding for b in un_big),
      "there, 'we could not look' really is different from 'it is fine'")

unknown = B.evaluate(equity=100_000, true_max_loss=2_000, free_capital=98_000,
                     thesis_weights={"NVDA": 2_000}, n_risk=1.0, n_positions=None)
check("an UNKNOWN position count binds", len(B.refusing(unknown)) == 2,
      "a caller that cannot say how many positions it holds does not get the warm-up")

dev = B.evaluate(equity=100_000, true_max_loss=72_900, free_capital=27_100,
                 thesis_weights={"NVDA": 38_200, "QQQ": 34_700}, n_risk=1.51, n_positions=8)
check("the 25 Aug dev book (72.9%, n_risk 1.51) is refused on all three",
      len(B.refusing(dev)) == 3, str([b.limit for b in B.refusing(dev)]))
check("...while pre-flight DOES, to display them",
      "book_limits" in (src / "scripts/preflight.py").read_text(encoding="utf-8", errors="replace"))
# Turning these on changes what the account trades. That is an attended decision,
# and this test is what stops it happening by accident.

print("\n-- degenerate equity refuses rather than dividing by it")
z = B.evaluate(equity=0.0, true_max_loss=1000, free_capital=0)
check("zero equity yields a single EQUITY breach",
      len(z) == 1 and z[0].limit == "EQUITY", B.summary(z))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
