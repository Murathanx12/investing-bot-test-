"""Smoke checks for the 2026-08-29 MONDAY-SAFETY patches. No keys, no network.

Run: python tests_smoke_monday.py  (also executed by run_tests.py)

28 Aug, first live session: twelve basket names at 25% notional each = 300%
gross; a 3% stop on 300% gross = -9%. Five 5-DTE OTM calls lost 60% apiece.
Every share entry filled 09:30-09:33 and every stop fired by 09:48 on a 0.1%
index move. The counterfactual marker sent "BBW" to the option-quote endpoint
and four of six loops exited non-zero 17 times in a row. These pin the fixes.
"""
from __future__ import annotations

from datetime import datetime

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import admission, book, runner
from alpha.engine import sizing, equity

EQ = 100_000.0
shares = sizing.Structure("QUBT", "long_shares", direction="up", entry_cost=8.55, max_loss=8.55 * 0.11,
                          breakeven_move=0.002, implied_move=0.12, quote_spread_pct=0.002, days_to_expiry=3,
                          legs=(("QUBT", "buy", 1),), quote={"last_trade": 8.55})


def bk(total=0.0, by=None):
    return book.BookRisk(equity=EQ, structures=[], residuals=[], unbounded=False, max_loss_usd=total,
                         by_underlying=by or {}, by_node={}, premium_paid_usd=0.0)


print("\n-- P0.0 gross notional cap")
n = 2922                                                        # 25% notional, Friday's QUBT fill
add = runner.structure_notional_usd(shares, n)
check("share notional = spot x shares", abs(add - 2922 * 8.55) < 1e-6, f"{add:,.0f}")
a = admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15,
                    gross_cap=1.00, gross_usd=0.0, add_notional_usd=add)
check("first 25% name on an empty book admitted", a.ok, a.reason[:70])
a = admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15,
                    gross_cap=1.00, gross_usd=75_000.0, add_notional_usd=add)
check("fourth 25% name (gross 75% + 25%) admitted at exactly 100%", a.ok, a.reason[:70])
a = admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15,
                    gross_cap=1.00, gross_usd=100_000.0, add_notional_usd=add)
check("fifth 25% name refused with GROSS", (not a.ok) and a.reason.startswith("GROSS"), a.reason[:60])
check("worst case at the 8% basket stop is now <= -8%, not -24%",
      sizing.gross_cap("basket") * equity.stop_fraction("basket") <= 0.08 + 1e-9)
a = admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15,
                    gross_cap=1.00, gross_usd=50_000.0, add_notional_usd=add, committed_notional_usd=30_000.0)
check("notional committed EARLIER IN THE PASS counts (50 + 30 + 25 > 100)", not a.ok and "GROSS" in a.reason)
a = admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15,
                    gross_cap=1.00, gross_usd=None, add_notional_usd=add)
check("unmeasurable gross REFUSES rather than assumes flat", not a.ok and a.reason.startswith("GROSS") and a.metrics.get("gross") == "CANNOT DETERMINE")
check("same order with no gross cap requested behaves as before",
      admission.admit(bk(), shares, n, equity=EQ, aggregate_cap=0.36, per_underlying_cap=0.15).ok)
check("every profile has a gross cap and basket's is 100%",
      all(p in sizing.GROSS_NOTIONAL_CAP for p in sizing.PROFILES) and sizing.gross_cap("basket") == 1.0)
check("unknown profile falls to the default cap", sizing.gross_cap("nonsense") == sizing.DEFAULT_GROSS_NOTIONAL_CAP)


class _Pos:
    def positions(self):
        return [{"symbol": "BE", "asset_class": "us_equity", "market_value": "24451.6"},
                {"symbol": "PLUG260904C00002000", "asset_class": "us_option", "qty": "80",
                 "current_price": "0.19", "market_value": None},
                {"symbol": "NVDA", "asset_class": "us_equity", "market_value": "-5000"}]


class _Broken:
    def positions(self):
        raise RuntimeError("401")


g = runner.gross_notional_usd(_Pos())
check("gross = sum |market_value|, options at x100 when market_value is absent, shorts by absolute",
      abs(g - (24451.6 + 80 * 0.19 * 100 + 5000)) < 1e-6, f"{g:,.2f}")
check("unreadable positions -> None, not 0.0", runner.gross_notional_usd(_Broken()) is None)

print("\n-- P0.2 convex entry rules")
check("convex aggregate premium at risk is 15%", sizing.PROFILES["convex"]["aggregate"] == 0.15)
check("convex needs >= 10 DTE and break-even <= 1x the market's width",
      sizing.CONVEX_MIN_DTE == 10.0 and sizing.CONVEX_MAX_BREAKEVEN_TO_IMPLIED == 1.0)

print("\n-- P0.3 opening range")
check("09:31 ET is inside the opening range", runner.in_opening_range(datetime(2026, 8, 31, 9, 31)))
check("09:44 ET is inside", runner.in_opening_range(datetime(2026, 8, 31, 9, 44)))
check("09:45 ET is outside", not runner.in_opening_range(datetime(2026, 8, 31, 9, 45)))
check("13:00 ET is outside", not runner.in_opening_range(datetime(2026, 8, 31, 13, 0)))
check("refusal classes name the two new refusals",
      "opening_range" in runner.REFUSAL_CLASSES and "convex_rule" in runner.REFUSAL_CLASSES)

print("\n-- P0.1 counterfactual quote routing")
check("BBW is a share leg, an OCC symbol is not",
      equity.is_equity_symbol("BBW") and equity.is_equity_symbol("AG")
      and not equity.is_equity_symbol("NVDA260904C00232500"))
src = open(__file__.replace("tests_smoke_monday.py", "scripts/counterfactual.py"), encoding="utf-8").read()
check("counterfactual routes share legs to stock_quote and option legs to option_quotes",
      "stock_quote(shares)" in src and "option_quotes(options)" in src)
check("a missing quote is reported as MISSING, not silently zero", "missing" in src and "MISSING" in src)

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("all monday-safety checks passed")
