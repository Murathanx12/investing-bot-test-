"""Smoke checks for PROSPECTIVE admission control (`alpha/admission.py`). No keys, no network.

Run: python tests_smoke_admission.py  (also executed by tests_smoke.py)

The 25 Aug book: every order legal on its own, the sum at 72.7% true max loss,
~3%/day of theta, and no room for the one event with a receipt. These pin that
the controller refuses the order that would have produced that book.
"""
from __future__ import annotations

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import admission, book
from alpha.engine import sizing

EQ = 100_000.0
strad = sizing.Structure("NVDA260828C00212500", "long_straddle", direction="both", entry_cost=1200.0, max_loss=1200.0,
                         breakeven_move=0.057, implied_move=0.051, quote_spread_pct=0.05, days_to_expiry=2.6,
                         legs=(("NVDA260828C00212500", "buy", 1), ("NVDA260828P00212500", "buy", 1)))
shares = sizing.Structure("NVDA", "long_shares", direction="up", entry_cost=213.0, max_loss=10.65,
                          breakeven_move=0.0002, implied_move=0.051, quote_spread_pct=0.0002, days_to_expiry=2,
                          legs=(("NVDA", "buy", 1),))


def bk(total=0.0, by=None, by_node=None):
    return book.BookRisk(equity=EQ, structures=[], residuals=[], unbounded=False, max_loss_usd=total,
                         by_underlying=by or {}, by_node=by_node or {}, premium_paid_usd=0.0)


print("\n-- max loss and free headroom, post-trade")
a = admission.admit(bk(0.0), strad, 5, equity=EQ, aggregate_cap=0.50)
check("empty book, 6% order -> admitted", a.ok, a.reason[:80])
check("metrics say what was checked and what could not be", a.metrics["post_true_max_loss_frac"] == 0.06 and a.metrics["theta"].startswith("CANNOT DETERMINE"))
a = admission.admit(bk(36_000.0, {"AVGO": 36_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50)
check("36% held + 6% -> 42%, only 8% free -> REFUSED for tomorrow's optionality", not a.ok and "OPTIONALITY" in a.reason, a.reason[:90])
a = admission.admit(bk(30_000.0, {"AVGO": 30_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50)
# POLICY CHANGE 2026-08-27: this used to be ADMITTED. The book-wide backstop
# (alpha/book_limits.MAX_BOOK_STRESS = 35%) now binds before the aggregate cap
# does. Those two numbers contradicted each other -- 50% aggregate minus 10% free
# let the book reach 40% -- and the 35% cap is the one with a derivation behind
# it (a real unlevered book lost 23.3% over 41 sessions and survived).
check("30% held + 6% -> 36% stress -> REFUSED by the book-wide cap, not the aggregate one",
      not a.ok and "MAX_BOOK_STRESS" in a.reason, a.reason[:90])
a = admission.admit(bk(30_000.0, {"AVGO": 30_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50, committed_usd=8_000.0)
check("what THIS pass already committed counts", not a.ok, a.reason[:60])
# The reserve exemption is about FREE CAPITAL, never about total stress: a stress
# cap that may be exceeded for a favourite trade is not a stress cap. So it is
# exercised at an aggregate_cap where the exempt region actually exists.
a = admission.admit(bk(26_000.0, {"AVGO": 26_000.0}), strad, 5, equity=EQ, aggregate_cap=0.40,
                    own_event="print:2026-09-04", reserved_events={"2026-09-04": 0.10})
check("the reserved event's OWN expression may spend the reserve",
      a.ok and a.metrics["reserved_expression"], a.reason[:80])
a = admission.admit(bk(36_000.0, {"AVGO": 36_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50,
                    own_event="print:2026-09-04", reserved_events={"2026-09-04": 0.10})
check("but it does NOT exempt the stress cap", not a.ok and "MAX_BOOK_STRESS" in a.reason, a.reason[:90])
# AND THE FINDING THAT FALLS OUT OF IT: the exemption needs free_after < 10% of
# equity while stress stays under 35%, i.e. post-trade max loss in
# ((cap-0.10), 0.35). At cap >= 45% that interval is EMPTY, so the whole reserve
# feature is unreachable there -- dead code that reads as a live policy.
check("the reserve exemption is unreachable at aggregate_cap >= 45%",
      (0.50 - 0.10) >= 0.35 and (0.40 - 0.10) < 0.35,
      "if this flips, re-check which profiles can actually reserve an event")

print("\n-- concentration")
a = admission.admit(bk(10_000.0, {"NVDA": 10_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50)
check("NVDA at 10% + 6% -> 16% on one name -> REFUSED", not a.ok and "CONCENTRATION" in a.reason, a.reason[:80])
a = admission.admit(bk(10_000.0, {"NVDA": 10_000.0}), shares, 200, equity=EQ, aggregate_cap=0.50)
check("shares count on the same underlying (10% + 2.1% ok)", a.ok and a.metrics["underlying"] == "NVDA", a.reason[:80])

print("\n-- theta burn and delta stress need greeks, and say so when they have none")
g = admission.BookGreeks(delta_usd={"TSLA": 250_000.0}, theta_usd_per_day=-500.0, daily_sigma={"TSLA": 0.03}, derived=True)
a = admission.admit(bk(20_000.0, {"TSLA": 12_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50, greeks=g,
                    new_delta_usd=0.0, new_theta_usd_per_day=-300.0, new_daily_sigma=0.02)
check("theta -800/day on 100k (0.8%) -> REFUSED", not a.ok and "THETA" in a.reason, a.reason[:70])
a = admission.admit(bk(20_000.0, {"TSLA": 12_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50, greeks=g,
                    new_delta_usd=0.0, new_theta_usd_per_day=-100.0, new_daily_sigma=0.02)
check("theta -600/day (0.6%) -> admitted, stress 15k -> wait", not a.ok and "STRESS" in a.reason, a.reason[:70])
g2 = admission.BookGreeks(delta_usd={"TSLA": 50_000.0}, theta_usd_per_day=-200.0, daily_sigma={"TSLA": 0.03}, derived=True)
a = admission.admit(bk(20_000.0, {"TSLA": 12_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50, greeks=g2,
                    new_delta_usd=20_000.0, new_theta_usd_per_day=-100.0, new_daily_sigma=0.02)
check("stress 3k + 0.8k = 3.8% -> admitted", a.ok, a.reason[:70])
check("stress metric labelled delta-only", "gamma/vega NOT included" in a.metrics["stress_note"])
a = admission.admit(bk(20_000.0, {"TSLA": 12_000.0}), strad, 5, equity=EQ, aggregate_cap=0.50, greeks=g2,
                    new_delta_usd=None, new_theta_usd_per_day=None)
check("no greeks for the candidate -> theta and stress CANNOT DETERMINE, not passed", a.ok and a.metrics["stress"] == "CANNOT DETERMINE"
      and a.metrics["theta"].startswith("CANNOT DETERMINE"))
check("undetermined greeks are flagged, not hidden", admission.BookGreeks(note="x").derived is False)

print("\n-- the 25 Aug dev book, replayed one order at a time")
# Reconstructed from pnl_attribution: 12 structures, max losses in $; the controller sees them arrive.
orders = [("QQQ", 4524), ("NVDA", 12445), ("AVGO", 7584), ("AMD", 10785), ("TSLA", 3560), ("AAPL", 186),
          ("SPY", 2322), ("META", 6480), ("MSFT", 598), ("NIO", 136), ("NVDA", 12825), ("QQQ", 4428)]
total, by, admitted, refused = 0.0, {}, [], []
for sym, ml in orders:
    s = sizing.Structure(f"{sym}260828C00100000", "x", entry_cost=ml, max_loss=ml, breakeven_move=0.05,
                         implied_move=0.05, quote_spread_pct=0.05, days_to_expiry=2, legs=((f"{sym}260828C00100000", "buy", 1),))
    a = admission.admit(bk(total, by), s, 1, equity=EQ, aggregate_cap=0.50)
    if a.ok:
        admitted.append(sym); total += ml; by[sym] = by.get(sym, 0.0) + ml
    else:
        refused.append((sym, a.reason.split(":")[0]))
check("the second NVDA condor is refused on concentration", ("NVDA", "CONCENTRATION") in refused, str(refused))
check("the book never passes 40% (50% cap - 10% free)", total / EQ <= 0.40 + 1e-9, f"{total / EQ:.1%} after {len(admitted)} orders")
# Was ">= 7" under the old 40% ceiling. The book-wide cap stops this book at 5
# orders / 32.5% instead of letting it reach the 72.9% it actually reached on the
# day -- which is the entire point of the limits, so the number moving DOWN here
# is the result, not a regression.
check("the book still trades, but the 25 Aug book is stopped much earlier",
      4 <= len(admitted) <= 6, f"{len(admitted)} admitted, {len(refused)} refused")
check("and it never approaches the 72.9% it actually reached", total / EQ <= 0.35 + 1e-9,
      f"{total / EQ:.1%}")

print("\n-- runner integration: an admission refusal is a ledger row, not an exception")
import importlib, tempfile
from alpha import ledger, runner
runner = importlib.reload(runner)
from alpha.brains.base import Forecast
from datetime import datetime, timezone


class FakeChain:
    def __init__(self):
        self.underlying = "NVDA"; self.spot = 213.0; self.spot_source = "test"; self.spot_ts = datetime.now(timezone.utc)
        self.feed = "test"; self.market_open = True; self.median_quote_age_seconds = 0.0; self.contracts = []

    def implied_move(self, expiry): return 0.10
    def parity_gap(self, expiry): return None


class FakeClient:
    def account(self): return {"equity": "100000", "last_equity": "100000"}
    def positions(self): return []
    def orders(self, status="open", limit=200): return []
    def submit(self, order, *, decision_id, quote_snapshot): return {"id": "fake-" + decision_id}


ledger.LEDGER_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
runner.EVENT_RESERVE = {}      # the 4 Sep reserve would make the SIZER refuse first; this pins ADMISSION
runner.chain_mod.fetch = lambda *a, **k: FakeChain()
runner.structures.enumerate_all = lambda snapshot, expiry: [strad]
full = bk(45_000.0, {"AVGO": 45_000.0})
runner.book_mod.read = lambda client, **k: full
runner.admission.book_greeks = lambda client, **k: admission.BookGreeks(note="fake client")
# The print is BEHIND us on purpose (2026-08-20, not ahead). This fixture is an
# NVDA long straddle into NVDA's own print -- which is exactly the route
# alpha/refuted.py now blocks, and it would be declined before admission is ever
# reached. These checks are about ADMISSION arithmetic, so the event is moved
# behind us; the refuted route gets its own coverage immediately below and in
# tests_smoke_refuted.py.
loud = Forecast("event_move", "NVDA", 3, 0.0, 0.20, 1.0, "print", "tail", {"last_close": 213.0, "event_date": "2026-08-20"})
res = runner.run_pass(FakeClient(), [loud], expiry="2026-08-28", dry_run=False)
rows = ledger.read_all()
adm_rows = [r for r in rows if r["action"] == "refused" and (r["refusal_reason"] or "").startswith("ADMISSION")]
check("45% held, straddle sized -> ADMISSION refusal row, nothing sent", res.submitted == 0 and adm_rows,
      adm_rows[-1]["refusal_reason"][:90] if adm_rows else str(res))
check("the row carries the post-trade metrics", adm_rows and adm_rows[-1]["outcome"]["economics"]["admission"]["free_after_frac"] < 0.10)
runner.book_mod.read = lambda client, **k: bk(0.0)
res = runner.run_pass(FakeClient(), [loud], expiry="2026-08-28", dry_run=False)
check("empty book -> the same order goes (19.2% on one name is inside the aggressive profile's own 20%)",
      res.submitted == 1, str(res) + " " + (ledger.read_all()[-1].get("refusal_reason") or "")[:80])
runner.book_mod.read = lambda client, **k: bk(2_000.0, {"NVDA": 2_000.0})
res = runner.run_pass(FakeClient(), [loud], expiry="2026-08-28", dry_run=False)
last = ledger.read_all()[-1]
check("a SECOND order in the same name that would exceed 20% is refused on CONCENTRATION",
      res.submitted == 0 and "CONCENTRATION" in (last.get("refusal_reason") or ""), (last.get("refusal_reason") or "")[:80])

if __name__ == "__main__":
    print(f"\n{len(fails)} failures" + (": " + ", ".join(fails) if fails else ""))
    raise SystemExit(1 if fails else 0)
