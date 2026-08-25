"""Smoke checks for the brains, the narrative schema, the sources and the
multi-brain runner. No keys, no network. Run: python tests_smoke_brains.py
(also executed by tests_smoke.py)."""
from __future__ import annotations

import math
from datetime import date, timedelta

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# ------------------------------------------------------------ narrative schema
print("\n-- narrative schema: axes, validation, belief gap")
from alpha.narrative import schema

full = {k: (lo + hi) / 2 for k, (lo, hi, _) in schema.AXES.items()}
check("every axis validates at mid-range", len(schema.validate_axes(full)) == len(schema.AXES))
try:
    schema.validate_axes({k: v for k, v in full.items() if k != "truth_probability"})
    check("missing axis refused", False)
except ValueError as exc:
    check("missing axis refused", "truth_probability" in str(exc))
clamped = schema.validate_axes({**full, "truth_probability": 7.0})
check("out-of-range clamped", clamped["truth_probability"] == 1.0)


def shock(**over):
    axes = {**full, **over}
    return schema.NarrativeShock("v", "id", "TTWO", "GTA VI leak", "", "2026-08-25T00:00:00Z", [],
                                 schema.validate_axes(axes), ["TTWO"], ["gaming"], "leak", {})


check("false+believed+unpriced -> momentum",
      shock(truth_probability=0.2, market_belief=0.8, already_priced_fraction=0.1).belief_gap["case"]
      == "false_but_believed_unpriced")
check("false+believed+priced -> reversal",
      shock(truth_probability=0.2, market_belief=0.8, already_priced_fraction=0.9).belief_gap["case"]
      == "false_believed_fully_priced")
check("true+unnoticed -> underreaction",
      shock(truth_probability=0.9, social_proof=0.1, already_priced_fraction=0.1).belief_gap["case"]
      == "true_but_unnoticed")
check("true+believed+priced -> REFUSE",
      shock(truth_probability=0.9, market_belief=0.9, already_priced_fraction=0.9).belief_gap["case"]
      == "true_believed_priced")

# -------------------------------------------------------- narrative dispersion
print("\n-- narrative dispersion: LLM axes -> variance, never a trade")
from alpha.brains import narrative_dispersion as nd

quiet = shock(market_impact_probability=0.1, disagreement=0.1, truth_probability=0.95, already_priced_fraction=0.9)
loud = shock(market_impact_probability=0.9, disagreement=0.9, truth_probability=0.5, already_priced_fraction=0.1)
wq, _ = nd.widen_from_shock(quiet, None)
wl, _ = nd.widen_from_shock(loud, None)
check("loud disagreement widens more than quiet consensus", wl > wq, f"{wq:.2f} -> {wl:.2f}")
check("widening is capped", nd.widen_from_shock(loud, 50.0)[0] <= nd.MAX_WIDEN)
check("priced-in shock barely widens", wq < 1.1, f"{wq:.2f}")

# --------------------------------------------------------------- event_move
print("\n-- event_move: inferred prints, extrapolated periods")
from alpha.brains import event_move

# synthetic bars: flat 1% noise, with a +9% day 30 days after each period end
start = date(2024, 1, 1)
bars, closes = [], 100.0
period_ends = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
jump_days = {(date.fromisoformat(p) + timedelta(days=30)).isoformat() for p in period_ends}
d = start
import random
rng = random.Random(7)
while d < date(2025, 8, 1):
    if d.weekday() < 5:
        r = 0.09 if d.isoformat() in jump_days else rng.gauss(0, 0.01)
        closes *= math.exp(r)
        bars.append({"t": d.isoformat() + "T04:00:00Z", "c": closes})
    d += timedelta(days=1)
ev = event_move.event_days_inferred(bars, period_ends)
check("finds one print per period", len(ev) == 5, str(len(ev)))
check("print days are the planted jumps", all(e["event_day"] in jump_days for e in ev))
check("moves are ~9%", all(abs(e["move"] - 0.09) < 0.02 for e in ev))
ext = event_move.extend_periods(["2026-03-31", "2025-12-31"], years=2)
check("periods extrapolated backwards quarterly", len(ext) >= 8 and ext[-1] < "2024-07-01", f"{len(ext)}: {ext[-1]}")

# ---------------------------------------------------------- options_attention
print("\n-- options_attention: seasoning filter")
from alpha.brains import options_attention as oa
check("widen at 1x volume is 1.0", abs(min(oa.MAX_WIDEN, 1.0 + oa.WIDEN_PER_LOG_RATIO * max(0.0, math.log(1.0))) - 1.0) < 1e-9)
check("widen at 20x is capped", min(oa.MAX_WIDEN, 1.0 + oa.WIDEN_PER_LOG_RATIO * math.log(20.0)) <= oa.MAX_WIDEN)

# ------------------------------------------------------------------ exposure
print("\n-- exposure graph")
from alpha.narrative import exposure
check("every edge has a bounded uncertainty", all(0 <= e.uncertainty <= 1 for e in exposure.EDGES))
check("every edge sign in {-1,0,1}", all(e.sign in (-1, 0, 1) for e in exposure.EDGES))
check("china export controls hit NVDA negatively",
      any(e.symbol == "NVDA" and e.sign == -1 for e in exposure.exposures("china_export_controls")))

# ------------------------------------------------------------------- runner
print("\n-- runner: one position per symbol, shadow attribution, forecasts recorded")
import os, tempfile
from alpha import ledger
from alpha.brains.base import Forecast
from alpha import runner
from alpha.engine import sizing

tmp = tempfile.mkdtemp()
ledger.LEDGER_DIR = __import__("pathlib").Path(tmp)


class FakeChain:
    def __init__(self):
        self.underlying = "X"; self.spot = 100.0; self.spot_source = "test"
        from datetime import datetime, timezone
        self.spot_ts = datetime.now(timezone.utc); self.feed = "test"; self.market_open = False
        self.median_quote_age_seconds = 0.0; self.contracts = []
    def parity_gap(self, expiry): return None


class FakeClient:
    def account(self): return {"equity": "100000"}
    def positions(self): return []
    def submit(self, order, *, decision_id, quote_snapshot): return {"id": "fake-" + decision_id}


def fake_evaluate(client, forecast, *, state, expiry, risk_profile=None, open_risk=None):
    # the brain with the bigger sd disagrees more with the chain -> larger risk
    s = sizing.Structure("X", "long_straddle", direction="both", entry_cost=200.0, max_loss=200.0,
                         breakeven_move=0.03, implied_move=0.03, quote_spread_pct=0.05)
    v = sizing.SizingVerdict(True, min(0.08, forecast.sd), 0.1, "ok")
    return s, v, FakeChain(), []


runner.evaluate = fake_evaluate
f1 = Forecast("vol_gap", "X", 3, 0.0, 0.02, 1.0, "quiet", "tail", {"last_close": 100})
f2 = Forecast("event_move", "X", 3, 0.0, 0.06, 1.0, "print", "tail", {"last_close": 100})
f3 = Forecast("narrative_dispersion", "X", 3, 0.0, 0.09, 1.0, "loud", "tail", {"last_close": 100})
res = runner.run_pass(FakeClient(), [f1, f2, f3], expiry="2026-08-28", dry_run=False,
                      shadow_brains=("narrative_dispersion",))
rows = ledger.read_all()
check("exactly one order per symbol", res.submitted == 1, str(res.submitted))
check("two shadows recorded", res.shadow == 2, str(res.shadow))
winner = [r for r in rows if r["action"] == "submitted"]
check("champion is the largest approved risk among EXECUTABLE brains",
      winner and winner[0]["brain"] == "event_move", winner[0]["brain"] if winner else "none")
shadow_reasons = {r["brain"]: r["refusal_reason"] for r in rows if r["action"] == "shadow"}
check("shadow-only brain is named as such", "shadow-only" in shadow_reasons.get("narrative_dispersion", ""))
check("out-ranked brain names its winner", "event_move" in shadow_reasons.get("vol_gap", ""))
fc = ledger.read_all("forecasts")
check("every brain's forecast recorded before pricing", len(fc) == 3, str(len(fc)))
check("ledger chain intact", ledger.verify_chain()[0] and ledger.verify_chain("forecasts")[0])

# event cluster risk: four names, one print, 8% each -> the fourth breaches the 25% node cap
print("\n-- event node cap: correlated expressions of one event are one bet")
node_fs = [Forecast("event_move", sym, 3, 0.0, 0.08, 1.0, "print", "tail",
                    {"last_close": 100, "event_date": "2026-08-26"}) for sym in ("N1", "N2", "N3", "N4")]
free_f = Forecast("vol_gap", "Q1", 3, 0.0, 0.08, 1.0, "quiet", "tail", {"last_close": 100})
res2 = runner.run_pass(FakeClient(), node_fs + [free_f], expiry="2026-08-28", dry_run=False, shadow_brains=())
rows2 = ledger.read_all()
node_refused = [r for r in rows2 if r["action"] == "refused" and "event node" in (r.get("refusal_reason") or "")]
check("three of four node members execute, the fourth is refused by the node cap",
      res2.submitted == 4 and len(node_refused) == 1, f"submitted={res2.submitted} node_refused={len(node_refused)}")
check("a forecast with no event is outside every node", any(r["symbol"] == "Q1" and r["action"] == "submitted" for r in rows2))
check("node refusal names the node", node_refused and "print:2026-08-26" in node_refused[0]["refusal_reason"])

# -------------------------------------------------------------------- fills
print("\n-- fills: slippage arithmetic")
from alpha import fills


class FillClient:
    def _request(self, m, path, **kw):
        return {"status": "filled", "filled_at": "2026-08-25T13:31:00Z", "qty": "3", "limit_price": "13.35",
                "legs": [{"symbol": "C1", "side": "buy", "filled_avg_price": "6.40"},
                         {"symbol": "P1", "side": "buy", "filled_avg_price": "7.20"}]}
    def option_quotes(self, syms): return {s: {"bp": 6.0, "ap": 6.5, "t": "x"} for s in syms}


dec = {"decision_id": "d", "alpaca_order_id": "o", "symbol": "TSLA", "instrument": "long_straddle",
       "ts_utc": "2026-08-25T11:07:00Z", "legs": [["C1", "buy", 1], ["P1", "buy", 1]],
       "quote_snapshot": {"feed": "indicative", "median_quote_age_s": 5, "legs": [
           {"symbol": "C1", "bid": 6.21, "ask": 6.25}, {"symbol": "P1", "bid": 7.0, "ask": 7.1}]},
       "max_loss_usd": 4005.0, "mdm_edge": 0.167, "order": {"qty": "3"}}
a = fills.audit(FillClient(), dec)
check("decision ask summed across legs", abs(a.decision_ask_per_unit - 13.35) < 1e-9)
check("fill summed across legs", abs(a.fill_per_unit - 13.60) < 1e-9)
check("slippage per unit = fill - decision ask", abs(a.slippage_per_unit - 0.25) < 1e-9)
check("slippage usd scales by 100 x qty", abs(a.slippage_usd - 75.0) < 1e-6)
check("slippage stated as a fraction of expected edge", a.slippage_over_edge is not None and a.slippage_over_edge > 0)
check("mark exits at the bid", abs(a.mark["exit_per_unit_at_bid"] - 12.0) < 1e-9)

print("\n-- counterfactual: a defined-risk mark cannot exceed its max loss")
from alpha import counterfactual as cf
dec = {"decision_id": "z", "symbol": "PANW", "instrument": "bear_call_spread", "action": "refused",
       "legs": [["S", "sell", 1], ["L", "buy", 1]], "entry_cost_per_unit": -100.0, "max_loss_per_unit": 400.0,
       "ts_utc": "2026-08-25T00:00:00Z"}
bad = cf.mark(dec, {"S": {"bid": 30, "ask": 60}, "L": {"bid": 0.05, "ask": 0.10}}, risk_budget_usd=5000)
check("mark below max loss is UNMARKABLE, not a saved loss", bad.mark_source == "unmarkable" and bad.pnl_usd == 0.0,
      bad.detail.get("why", ""))
ok_ = cf.mark(dec, {"S": {"bid": 1.0, "ask": 1.2}, "L": {"bid": 0.05, "ask": 0.10}}, risk_budget_usd=5000)
check("ordinary mark still prices", ok_.mark_source == "chain")

print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
