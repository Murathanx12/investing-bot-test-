"""Smoke tests for the 26 Aug risk-accounting repair. Run: python tests_smoke_book.py

Three defects, one cause -- risk was a property of the PASS, not of the BOOK:
  * `open_convex_risk` summed long-leg cost basis (premium paid, not risk carried);
  * `EVENT_NODE_CAP` reset every pass;
  * the champion was the largest approved SIZE, not the best expected economics.
"""
import os
import tempfile

from alpha import book, ledger, recovery
from alpha.engine import payoff, sizing

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("\n-- book: true max loss from ledger + positions")
condor_row = {
    "action": "submitted", "decision_id": "20260825T1535:vol_gap:NVDA", "brain": "vol_gap",
    "symbol": "NVDA", "instrument": "iron_condor", "ts_utc": "2026-08-25T15:35:00+00:00",
    "account_role": None, "order": {"qty": "15"}, "max_loss_per_unit": 855.0,
    "entry_cost_per_unit": -259.0,
    "legs": [["NVDA260828P00200000", "sell", 1], ["NVDA260828P00192500", "buy", 1],
             ["NVDA260828C00222500", "sell", 1], ["NVDA260828C00232500", "buy", 1]],
    "outcome": {"event_node": "print:2026-08-26"},
}
straddle_row = {
    "action": "submitted", "decision_id": "20260825T1540:vol_gap:AVGO", "brain": "vol_gap",
    "symbol": "AVGO", "instrument": "long_straddle", "ts_utc": "2026-08-25T15:40:00+00:00",
    "account_role": "dev", "order": {"qty": "6"}, "max_loss_per_unit": 1264.0,
    "entry_cost_per_unit": 1264.0,
    "legs": [["AVGO260828C00360000", "buy", 1], ["AVGO260828P00360000", "buy", 1]],
    "outcome": {},
}
positions = [
    {"asset_class": "us_option", "symbol": "NVDA260828P00200000", "qty": "-15", "cost_basis": "-2700", "avg_entry_price": "1.8"},
    {"asset_class": "us_option", "symbol": "NVDA260828P00192500", "qty": "15", "cost_basis": "1050", "avg_entry_price": "0.7"},
    {"asset_class": "us_option", "symbol": "NVDA260828C00222500", "qty": "-15", "cost_basis": "-3375", "avg_entry_price": "2.25"},
    {"asset_class": "us_option", "symbol": "NVDA260828C00232500", "qty": "15", "cost_basis": "1185", "avg_entry_price": "0.79"},
    {"asset_class": "us_option", "symbol": "AVGO260828C00360000", "qty": "6", "cost_basis": "4110", "avg_entry_price": "6.85"},
    {"asset_class": "us_option", "symbol": "AVGO260828P00360000", "qty": "6", "cost_basis": "3450", "avg_entry_price": "5.75"},
    {"asset_class": "us_equity", "symbol": "SPY", "qty": "10", "cost_basis": "7660"},
]
b = book.reconstruct(positions, equity=100_000, account_role="dev", rows=[condor_row, straddle_row])
# The two OPTION structures match; the SPY shares in the fixture have no ledger
# row and are a residual BY DESIGN -- that is the case the residual charge
# exists for. The old assertion said `not b.residuals` and had been red since
# the SPY line was added, which is worse than no check: a permanent red line
# beside green ones teaches the reader to skim red lines.
check("both option structures matched", len(b.structures) == 2, f"{len(b.structures)} / {len(b.residuals)}")
check("the unmatched SPY shares are a named residual, not a silent gap",
      [r.symbol for r in b.residuals] == ["SPY"] and not b.residuals[0].unbounded,
      str([(r.symbol, r.how) for r in b.residuals]))
check("condor charged at its MAX LOSS, not its long wings",
      abs(b.by_underlying["NVDA"] - 15 * 855.0) < 1e-6, f"{b.by_underlying['NVDA']:,.0f}")
check("premium-paid view is the OLD (smaller) number",
      b.premium_paid_usd < b.max_loss_usd, f"paid {b.premium_paid_usd:,.0f} < true {b.max_loss_usd:,.0f}")
check("fraction is true max loss / equity", abs(b.fraction - (15 * 855 + 6 * 1264) / 100_000) < 1e-9, f"{b.fraction:.4f}")
check("event node exposure read from the book", abs(b.node_fraction("print:2026-08-26") - 15 * 855 / 100_000) < 1e-9)
check("unknown node is zero", b.node_fraction("print:2026-09-04") == 0.0)

# The row belongs to the OTHER account: the legs are not here, so it must not match.
b_other = book.reconstruct(positions[4:], equity=100_000, account_role="exp1", rows=[condor_row, straddle_row])
check("a row is never matched against a book that does not hold it",
      not [s for s in b_other.structures if s.symbol == "NVDA"])
check("stamped row for another role is skipped even if legs coincide",
      not [s for s in b_other.structures if s.symbol == "AVGO"], "AVGO row is stamped dev")
check("unexplained long legs charged at cost basis", abs(b_other.max_loss_usd - (4110 + 3450)) < 1e-6, f"{b_other.max_loss_usd:,.0f}")

# Residual short with a protective long: charged at full width.
resid = [
    {"asset_class": "us_option", "symbol": "NVDA260828C00222500", "qty": "-10", "cost_basis": "-2250", "avg_entry_price": "2.25"},
    {"asset_class": "us_option", "symbol": "NVDA260828C00232500", "qty": "10", "cost_basis": "790", "avg_entry_price": "0.79"},
]
b_res = book.reconstruct(resid, equity=100_000, account_role="dev", rows=[])
check("residual short charged at FULL WIDTH to its protective long",
      abs(b_res.max_loss_usd - 10 * 10 * 100) < 1e-6 and not b_res.unbounded, f"{b_res.max_loss_usd:,.0f}")
# Residual short with NO protective long: unbounded -> fraction 1.0.
b_naked = book.reconstruct(resid[:1], equity=100_000, account_role="dev", rows=[])
check("naked residual short reads as UNBOUNDED", b_naked.unbounded and b_naked.fraction == 1.0)
check("unbounded is said out loud", "UNBOUNDED" in b_naked.summary())

# Role-less rows: larger exact fit explains the book first.
qqq4 = {**straddle_row, "decision_id": "a:vol_gap:QQQ", "symbol": "QQQ", "account_role": None, "order": {"qty": "4"},
        "max_loss_per_unit": 1107.0, "legs": [["QQQ260828C00711000", "buy", 1], ["QQQ260828P00711000", "buy", 1]]}
qqq8 = {**qqq4, "decision_id": "b:options_attention:QQQ", "brain": "options_attention", "order": {"qty": "8"}, "max_loss_per_unit": 1119.0}
qqq_pos = [
    {"asset_class": "us_option", "symbol": "QQQ260828C00711000", "qty": "8", "cost_basis": "4408", "avg_entry_price": "5.51"},
    {"asset_class": "us_option", "symbol": "QQQ260828P00711000", "qty": "8", "cost_basis": "4464", "avg_entry_price": "5.58"},
]
b_q = book.reconstruct(qqq_pos, equity=100_000, account_role="exp1", rows=[qqq4, qqq8])
check("role-less rows: the x8 row explains an 8-lot, the x4 row is left for the other book",
      [s.contracts for s in b_q.structures] == [8] and not b_q.residuals,
      f"{[s.contracts for s in b_q.structures]} residuals={len(b_q.residuals)}")

print("\n-- payoff: the ranker integrates the ACTUAL payoff")
spot = 100.0
strad = sizing.Structure("X", "long_straddle", direction="both", entry_cost=600, max_loss=600,
                         breakeven_move=0.06, implied_move=0.05, quote_spread_pct=0.05, days_to_expiry=3,
                         legs=(("XYZ260828C00100000", "buy", 1), ("XYZ260828P00100000", "buy", 1)))
condor = sizing.Structure("X", "iron_condor", direction="inside", entry_cost=-200, max_loss=800,
                          breakeven_move=0.08, implied_move=0.05, quote_spread_pct=0.05, days_to_expiry=3,
                          legs=(("XYZ260828P00090000", "sell", 1), ("XYZ260828P00080000", "buy", 1),
                                ("XYZ260828C00110000", "sell", 1), ("XYZ260828C00120000", "buy", 1)))
check("straddle pays |move| - debit", abs(payoff.terminal_pnl(strad, spot, 110) - 400) < 1e-9)
check("condor keeps the credit inside the wings", abs(payoff.terminal_pnl(condor, spot, 105) - 200) < 1e-9)
check("condor loses width - credit beyond a wing", abs(payoff.terminal_pnl(condor, spot, 125) + 800) < 1e-9)
quiet = payoff.economics(strad, spot, 0.0, 0.03)
big = payoff.economics(strad, spot, 0.08, 0.04)
check("a quiet forecast makes the straddle NEGATIVE EV", quiet.ev_usd < 0, f"{quiet.ev_usd:,.0f}")
check("a big-move forecast makes it positive", big.ev_usd > 0, f"{big.ev_usd:,.0f}")
c_quiet = payoff.economics(condor, spot, 0.0, 0.03)
check("the same quiet forecast makes the condor POSITIVE EV", c_quiet.ev_usd > 0, f"{c_quiet.ev_usd:,.0f}")
check("EV/max-loss ranks condor over straddle when quiet", c_quiet.ev_over_max_loss > quiet.ev_over_max_loss)
check("P(profit) in [0,1] and ES5 <= median", 0 <= big.p_profit <= 1 and big.es_5_usd <= big.median_usd)
check("spread is charged once", abs(big.spread_cost_usd - 0.05 * 600) < 1e-9)
check("economics serialise", isinstance(big.as_dict()["ev_over_max_loss"], float))
scaled = payoff.economics(strad, spot, 0.0, 0.03, horizon_days=1.0)
check("a shorter horizon than the life is widened, never narrowed", scaled.ev_usd > quiet.ev_usd)
no_legs = sizing.Structure("X", "long_call", direction="up", entry_cost=100, max_loss=100,
                           breakeven_move=0.02, implied_move=0.05, quote_spread_pct=0.05, days_to_expiry=3)
try:
    payoff.economics(no_legs, spot, 0.0, 0.03); check("a structure without legs is refused", False)
except ValueError:
    check("a structure without legs is refused", True)
check("liquidation value uses the bid for longs, the ask for shorts",
      abs(payoff.liquidation_value(condor, {"XYZ260828P00090000": {"bid": 1.0, "ask": 1.2},
                                            "XYZ260828P00080000": {"bid": 0.3, "ask": 0.4},
                                            "XYZ260828C00110000": {"bid": 1.0, "ask": 1.2},
                                            "XYZ260828C00120000": {"bid": 0.3, "ask": 0.4}})
          - (-120 + 30 - 120 + 30)) < 1e-9)
check("a missing quote returns None, never zero", payoff.liquidation_value(condor, {}) is None)

print("\n-- evaluate: gate, then ranker, then sizer")
from alpha import runner
from alpha.brains.base import Forecast
from alpha.data import chain as chain_mod


class FakeChain:
    def __init__(self, spot=100.0):
        from datetime import datetime, timezone
        self.underlying = "XYZ"; self.spot = spot; self.spot_source = "test"
        self.spot_ts = datetime.now(timezone.utc); self.feed = "test"; self.market_open = True
        self.median_quote_age_seconds = 0.0; self.contracts = []

    def parity_gap(self, expiry): return None


runner.chain_mod.fetch = lambda *a, **k: FakeChain()
runner.structures.enumerate_all = lambda snapshot, expiry: [strad, condor]
state = sizing.TournamentState(equity=100_000, starting_equity=100_000, fraction_of_window_remaining=0.9)
quiet_f = Forecast("vol_gap", "XYZ", 3, 0.0, 0.02, 1.0, "quiet", "step", {"last_close": 100})
loud_f = Forecast("event_move", "XYZ", 3, 0.0, 0.10, 1.0, "print", "tail", {"last_close": 100, "event_date": "2026-08-26"})
s_q, v_q, _, rej_q = runner.evaluate(None, quiet_f, state=state, expiry="2026-08-28", open_risk=0.0)
check("quiet forecast -> the condor is the champion", s_q is not None and s_q.kind == "iron_condor", getattr(s_q, "kind", None))
check("verdict carries the economics", v_q.economics is not None and v_q.economics["ev_usd"] > 0)
s_l, v_l, _, rej_l = runner.evaluate(None, loud_f, state=state, expiry="2026-08-28", open_risk=0.0)
check("loud forecast -> the straddle is the champion", s_l is not None and s_l.kind == "long_straddle", getattr(s_l, "kind", None))
# A structure that clears MDM but cannot beat cash: forecast sd just above implied, straddle EV negative after spread.
mid_f = Forecast("vol_gap", "XYZ", 3, 0.0, 0.08, 1.0, "meh", "tail", {"last_close": 100})
wide_strad = sizing.Structure("X", "long_straddle", direction="both", entry_cost=600, max_loss=600,
                              breakeven_move=0.06, implied_move=0.05, quote_spread_pct=0.20, days_to_expiry=3,
                              legs=strad.legs)
runner.structures.enumerate_all = lambda snapshot, expiry: [wide_strad]
s_m, v_m, _, rej_m = runner.evaluate(None, mid_f, state=state, expiry="2026-08-28", open_risk=0.0)
check("clears the gate, loses to cash -> refused and says CASH", s_m is None and v_m.reason.startswith("CASH:"), v_m.reason[:90])
check("the losing structure's own row names cash", any("CASH beats it" in v.reason for _, v in rej_m))

print("\n-- run_pass: node cap and recovery gate are BOOK-level")
tmp = tempfile.mkdtemp(); ledger.LEDGER_DIR = __import__("pathlib").Path(tmp)


class FakeClient:
    def __init__(self, positions): self._p = positions
    def account(self): return {"equity": "100000", "last_equity": "100000"}
    def positions(self): return self._p
    def orders(self, status="open", limit=200): return []
    def clock(self): return {"is_open": True}
    def submit(self, order, *, decision_id, quote_snapshot): return {"id": "fake-" + decision_id}


runner.structures.enumerate_all = lambda snapshot, expiry: [strad, condor]
# A book already carrying 24% of equity on the NVDA print node, in ANOTHER symbol.
node_row = {**condor_row, "symbol": "AVGO", "account_role": None, "order": {"qty": "28"},
            "legs": [["AVGO260828P00300000", "sell", 1], ["AVGO260828P00290000", "buy", 1]],
            "max_loss_per_unit": 857.0, "decision_id": "z:relay:AVGO"}
node_pos = [
    {"asset_class": "us_option", "symbol": "AVGO260828P00300000", "qty": "-28", "cost_basis": "-2800", "avg_entry_price": "1.0"},
    {"asset_class": "us_option", "symbol": "AVGO260828P00290000", "qty": "28", "cost_basis": "560", "avg_entry_price": "0.2"},
]
real_read = book.read
book.read = lambda client, **k: book.reconstruct(client.positions(), equity=100_000, account_role=None, rows=[node_row])
runner.book_mod = book
res = runner.run_pass(FakeClient(node_pos), [loud_f], expiry="2026-08-28", dry_run=False)
rows = ledger.read_all()
refusals = [r for r in rows if r["action"] == "refused" and r["symbol"] == "XYZ" and "node" in (r["refusal_reason"] or "")]
check("node cap counts what the BOOK already holds on that event", res.submitted == 0 and refusals,
      (refusals[0]["refusal_reason"][:100] if refusals else "no node refusal"))
check("the refusal names the book", refusals and "across the BOOK" in refusals[0]["refusal_reason"])

# Recovery: a brain whose live marks are negative may not open new long premium.
os.environ["AAT_RECOVERY"] = "1"
real_live_scores = recovery.live_scores
recovery.live_scores = lambda **k: {"event_move": recovery.BrainScore("event_move", n=4, mean_return_on_risk=-0.05, last=[-0.02, 0.01])}
book.read = lambda client, **k: book.reconstruct([], equity=100_000, account_role=None, rows=[])
res = runner.run_pass(FakeClient([]), [loud_f], expiry="2026-08-28", dry_run=False)
rows = ledger.read_all()
sh = [r for r in rows if r["action"] == "shadow" and r["brain"] == "event_move"]
check("negative brain in recovery: long premium goes to shadow, not to the venue",
      res.submitted == 0 and sh and "RECOVERY" in sh[-1]["refusal_reason"], sh[-1]["refusal_reason"][:90] if sh else "none")
recovery.live_scores = lambda **k: {"vol_gap": recovery.BrainScore("vol_gap", n=2, mean_return_on_risk=-0.05, last=[-0.02, -0.01])}
res = runner.run_pass(FakeClient([]), [quiet_f], expiry="2026-08-28", dry_run=False)
rows = ledger.read_all()
sh = [r for r in rows if r["action"] == "shadow" and r["brain"] == "vol_gap"]
check("two consecutive live losses demote the brain even for short premium",
      res.submitted == 0 and sh and "demoted" in sh[-1]["refusal_reason"])
recovery.live_scores = lambda **k: {"vol_gap": recovery.BrainScore("vol_gap", n=1, mean_return_on_risk=-0.05, last=[-0.02])}
res = runner.run_pass(FakeClient([]), [quiet_f], expiry="2026-08-28", dry_run=False)
check("one loss on one mark is not evidence; the trade goes", res.submitted == 1, str(res.submitted))
del os.environ["AAT_RECOVERY"]
check("recovery inactive -> no refusal", recovery.refusal("vol_gap", "long_call", {"vol_gap": recovery.BrainScore("vol_gap", 9, -0.5, [-1, -1])}) is None)
book.read = real_read
recovery.live_scores = real_live_scores

print("\n-- recovery scores from counterfactual rows")
cf = [
    {"action": "submitted", "decision_id": "20260825T1540:vol_gap:AVGO:cf", "ts_utc": "2026-08-25T15:40:00", "_written_utc": "2026-08-25T20:00:00",
     "outcome": {"return_on_risk": -0.03, "pnl_usd": -216}, "quote_snapshot": {"mark_source": "chain"}},
    {"action": "submitted", "decision_id": "20260825T1540:vol_gap:AVGO:cf", "ts_utc": "2026-08-25T15:40:00", "_written_utc": "2026-08-26T00:04:00",
     "outcome": {"return_on_risk": +0.02, "pnl_usd": 150}, "quote_snapshot": {"mark_source": "chain"}},
    {"action": "submitted", "decision_id": "20260825T1107:vol_gap:TSLA:cf", "ts_utc": "2026-08-25T11:07:00", "_written_utc": "2026-08-26T00:04:00",
     "outcome": {"return_on_risk": 0.0, "pnl_usd": 0}, "quote_snapshot": {"mark_source": "unmarkable"}},
    {"action": "refused", "decision_id": "20260825T1540:vol_gap:AVGO:alt0:cf", "ts_utc": "2026-08-25T15:40:00", "_written_utc": "2026-08-26T00:04:00",
     "outcome": {"return_on_risk": -0.5, "pnl_usd": -5000}, "quote_snapshot": {"mark_source": "chain"}},
]
sc = recovery.live_scores(cf_rows=cf)
check("latest mark per decision wins", sc["vol_gap"].n == 1 and abs(sc["vol_gap"].mean_return_on_risk - 0.02) < 1e-9, str(sc))
check("unmarkable and refused worlds do not score a brain", "TSLA" not in str(sc) and sc["vol_gap"].pnl_usd == 150)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("ALL PASS")
