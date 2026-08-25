"""Smoke tests that need no keys and no network. Run: python tests_smoke.py"""
from alpha.engine.shape import (Shape, Instrument, classify, construction_for,
                                SHAPE_PRIOR)
from alpha.engine.sizing import (Structure, TournamentState, size,
                                 implied_probability_beyond)
from alpha import ledger, config
import os, tempfile, math

fails = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond: fails.append(name)

print("\n-- shape classification")
tail  = [8,9,9,10,10,11,11,12,13,19]          # flat then a jump
step  = [4,5,6,7,9,14,14.3,14.5,14.8,14.6]     # cliff then plateau
inv   = [19,17,15,13,12,11,10,9,8,7]
check("TAIL curve -> TAIL", classify(tail, 30) is Shape.TAIL, classify(tail,30).value)
check("STEP curve -> STEP", classify(step, 90) is Shape.STEP, classify(step,90).value)
check("inverted -> INVERTED", classify(inv, 50) is Shape.INVERTED)
grad  = [5,6,7,8,9,10,11,12,13,14]              # a straight ramp, no jump
check("linear ramp -> GRADIENT (not TAIL)", classify(grad, 40) is Shape.GRADIENT, classify(grad,40).value)
check("few names -> DEGENERATE", classify(tail, 3.6) is Shape.DEGENERATE)

print("\n-- construction verdicts (the thesis)")
for sig, want_instr in [("mom_12_1", Instrument.LONG_CONVEXITY),
                        ("rev_dispersion", Instrument.LONG_CONVEXITY),
                        ("profit_roe", Instrument.WIDE_EQUITY),
                        ("value_bm", Instrument.REFUSE),
                        ("size_large", Instrument.REFUSE),
                        ("liquid", Instrument.REFUSE)]:
    v = construction_for(sig)
    check(f"{sig:15s} -> {v.instrument.value:16s} n={v.breadth}", v.instrument is want_instr)
check("unknown signal refused", construction_for("made_up").instrument is Instrument.REFUSE)

print("\n-- MDM sizing")
st_early = TournamentState(equity=100_000, starting_equity=100_000, fraction_of_window_remaining=0.9)
st_late  = TournamentState(equity=88_000,  starting_equity=100_000, fraction_of_window_remaining=0.05,
                           field_leader_estimate=0.25)
st_ahead = TournamentState(equity=130_000, starting_equity=100_000, fraction_of_window_remaining=0.10)

# a structure that breaks even at a 4% move while the chain implies 5%
s = Structure("AVGO250905C00300000","debit_spread",entry_cost=2.0,max_loss=2.0,
              breakeven_move=0.04, implied_move=0.05, quote_spread_pct=0.05, days_to_expiry=3)
agree = size(s, predicted_move=0.005, predicted_sd=0.03, state=st_early)
check("agreeing with the chain is refused", not agree.approved, agree.reason[:70])

edge  = size(s, predicted_move=0.06, predicted_sd=0.05, state=st_early)
check("real disagreement approved", edge.approved, f"risk={edge.risk_fraction:.2%} edge={edge.mdm_edge:+.1%}")

wide = Structure("X","long_call",entry_cost=2.0,max_loss=2.0,breakeven_move=0.04,
                 implied_move=0.05, quote_spread_pct=0.40, days_to_expiry=3)
check("wide spread refused", not size(wide, 0.06, 0.05, st_early).approved)

behind = size(s, 0.06, 0.05, st_late)
ahead  = size(s, 0.06, 0.05, st_ahead)
check("behind+late sizes UP", behind.risk_fraction > edge.risk_fraction,
      f"{edge.risk_fraction:.2%} -> {behind.risk_fraction:.2%}")
check("ahead+late sizes DOWN", ahead.risk_fraction < edge.risk_fraction,
      f"{edge.risk_fraction:.2%} -> {ahead.risk_fraction:.2%}")
check("aggregate cap binds", not size(s,0.06,0.05,st_early,open_convex_risk=0.35).approved)
try:
    Structure("X","naked_put",entry_cost=1.0,max_loss=0.0,breakeven_move=0.01,
              implied_move=0.05,quote_spread_pct=0.05,days_to_expiry=1)
    check("unbounded structure refused", False)
except ValueError:
    check("unbounded structure refused", True)

print("\n-- ledger chain")
tmp = tempfile.mkdtemp(); os.environ["AAT_LEDGER_DIR"] = tmp
import importlib; importlib.reload(ledger)
d = ledger.Decision(decision_id=ledger.new_decision_id("AVGO","dispersion"),
    ts_utc="2026-09-02T20:00:00Z", symbol="AVGO", brain="dispersion",
    signal_shape="tail", instrument="long_convexity", thesis="t",
    predicted_move=0.06, predicted_sd=0.05, implied_move=0.05, breakeven_move=0.04,
    mdm_edge=0.12, quote_snapshot={"bid":1.9,"ask":2.1}, action="submitted",
    refusal_reason=None, risk_fraction=0.05, max_loss_usd=5000, order={})
ledger.record(d); ledger.record(d)
ok, msg = ledger.verify_chain(); check("chain verifies", ok, msg)
p = ledger._path()
raw = p.read_text().splitlines(); raw[0] = raw[0].replace('"AVGO"','"TSLA"')
p.write_text("\n".join(raw)+"\n")
ok2, msg2 = ledger.verify_chain(); check("tamper detected", not ok2, msg2[:80])

print("\n-- credential refusals")
for v in ["AAT_ACCOUNT_ROLE","AAT_DEV_KEY_ID","AAT_DEV_SECRET_KEY"]: os.environ.pop(v, None)
try: config.role(); check("unset role refuses", False)
except config.CredentialRefusal: check("unset role refuses", True)
os.environ["AAT_TRADING_BASE"]="https://api.alpaca.markets"
try: config.base_url(); check("LIVE host refused", False)
except config.EndpointRefusal: check("LIVE host refused", True)
os.environ.pop("AAT_TRADING_BASE")
os.environ["ALPACA_API_KEY_ID"]="live-key-from-parent"
try:
    config.credentials("dev"); check("does not inherit parent keys", False)
except config.CredentialRefusal as e:
    check("does not inherit parent keys", "deliberately NOT used" in str(e))

print(f"\n{'ALL PASS' if not fails else str(len(fails))+' FAILED: '+', '.join(fails)}\n")
raise SystemExit(1 if fails else 0)
