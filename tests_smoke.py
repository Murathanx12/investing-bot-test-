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
# THE CLAMP (audit defect 2). `st_late` is DOWN 12%, and until 26 Aug that
# state sized 1.6-2.0x on the rank argument that a small loss and a large loss
# score the same. True, and also how -2% becomes -20% -- so convexity is now
# bought from flat, never from red. The rank logic is kept where it is safe and
# pinned below: behind but NOT negative still leans in.
check("behind+late+NEGATIVE does not size up (clamped at 1.0)",
      behind.risk_fraction <= edge.risk_fraction,
      f"{edge.risk_fraction:.2%} -> {behind.risk_fraction:.2%}")
st_behind_flat = TournamentState(equity=100_000, starting_equity=100_000,
                                 fraction_of_window_remaining=0.05, field_leader_estimate=0.25)
behind_flat = size(s, 0.06, 0.05, st_behind_flat)
check("behind+late but FLAT still leans into convexity",
      behind_flat.risk_fraction > edge.risk_fraction,
      f"{edge.risk_fraction:.2%} -> {behind_flat.risk_fraction:.2%}")
check("ahead+late sizes DOWN", ahead.risk_fraction < edge.risk_fraction,
      f"{edge.risk_fraction:.2%} -> {ahead.risk_fraction:.2%}")
from alpha.engine.sizing import profile as riskprofile
cap = riskprofile()["aggregate"]
check("aggregate cap binds", not size(s,0.06,0.05,st_early,open_convex_risk=cap).approved, f"cap={cap:.0%}")
from alpha.engine.sizing import PROFILES
check("profiles escalate", PROFILES["maximum"]["per_thesis"] > riskprofile("aggressive")["per_thesis"] > riskprofile("conservative")["per_thesis"])
from alpha.engine.sizing import maximum_allowed
if maximum_allowed():
    # kickoff has passed (28 Aug 11:00 ET): the gate is OPEN by date, and the
    # test says so instead of asserting a pre-kickoff world forever.
    check("maximum profile allowed after kickoff", riskprofile("maximum")["aggregate"] == 0.75)
else:
    try:
        riskprofile("maximum"); check("maximum profile refused before kickoff", False)
    except ValueError as exc:
        check("maximum profile refused before kickoff", "kickoff" in str(exc))
os.environ["AAT_ALLOW_MAXIMUM"] = "1"
check("maximum profile allowed with explicit override", riskprofile("maximum")["aggregate"] == 0.75)
del os.environ["AAT_ALLOW_MAXIMUM"]
check("maximum still bounded", all(p["aggregate"] <= 1.0 for p in __import__("alpha.engine.sizing",fromlist=["x"]).PROFILES.values()))
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
    signal_shape="declared:tail", instrument="long_convexity", thesis="t",
    predicted_move=0.06, predicted_sd=0.05, implied_move=0.05, breakeven_move=0.04,
    mdm_edge=0.12, quote_snapshot={"bid":1.9,"ask":2.1}, action="submitted",
    refusal_reason=None, risk_fraction=0.05, max_loss_usd=5000, order={})
ledger.record(d); ledger.record(d)
ok, msg = ledger.verify_chain(); check("chain verifies", ok, msg)
p = ledger._path()
raw = p.read_text().splitlines(); raw[0] = raw[0].replace('"AVGO"','"TSLA"')
p.write_text("\n".join(raw)+"\n")
ok2, msg2 = ledger.verify_chain(); check("tamper detected", not ok2, msg2[:80])

print("\n-- counterfactual marking (grading the roads not taken)")
from alpha import counterfactual as cf
# REAL OCC SYMBOLS. These legs are option contracts and every assertion below
# is at x100 ("structures.py multiplies by 100 at construction"). Since
# 2026-08-29 the multiplier is applied PER LEG, matching the endpoint each
# leg was quoted from, so the placeholders "L"/"S" would now correctly price
# as SHARES. The fixture was the thing that named them wrongly.
L = "TSLA260918C00400000"
S = "TSLA260918C00410000"
Q = {L: {"bid": 3.0, "ask": 3.4}, S: {"bid": 1.0, "ask": 1.4}}
# A long leg leaves at the BID, a short leg is bought back at the ASK. Marking
# both at the mid would gift half a spread per leg, and gift it hardest to the
# four-leg structures -- which is how a condor beats a call on arithmetic alone.
check("long leg exits at the bid", cf.exit_value_per_unit([(L,"buy",1)], Q) == 300.0)
check("short leg exits at the ask", cf.exit_value_per_unit([(S,"sell",1)], Q) == -140.0)
check("spread exits at both crossed sides",
      cf.exit_value_per_unit([(L,"buy",1),(S,"sell",1)], Q) == 160.0)
try:
    cf.exit_value_per_unit([("MISSING","buy",1)], Q); check("missing quote refuses", False)
except cf.Unmarkable: check("missing quote refuses", True)

def _w(ident, kind, action, cost, loss, legs, reason=None):
    return {"decision_id": ident, "symbol": "TSLA", "instrument": kind, "action": action,
            "refusal_reason": reason, "entry_cost_per_unit": cost,
            "max_loss_per_unit": loss, "legs": legs}

# Per-unit economics are in DOLLARS per contract (structures.py multiplies by
# 100 at construction), which is the same scale `exit_value_per_unit` returns.
# Mixing premium-per-share with dollars-per-contract is a silent 100x.
# Same $1,000 of risk, two structures with different per-unit risk: the cheaper
# one buys more units. Equal RISK, not equal size -- otherwise the comparison is
# between two different bets rather than between two shapes.
taken = cf.mark(_w("d1","long_call","submitted",200.0,200.0,[(L,"buy",1)]),
                Q, risk_budget_usd=1000)          # 5 units, exit 300 -> +500
alt   = cf.mark(_w("d1:alt0","debit_spread","refused",100.0,100.0,
                   [(L,"buy",1),(S,"sell",1)], "edge below 5pp"),
                Q, risk_budget_usd=1000)          # 10 units, exit 160 -> +600
check("equal risk, not equal size", taken.units == 5.0 and alt.units == 10.0)
check("marked from the chain", taken.mark_source == "chain")
check("pnl is exit minus entry", taken.pnl_usd == 500.0 and alt.pnl_usd == 600.0)
null = cf.mark(cf.null_world("d1","TSLA"), Q, risk_budget_usd=1000)
check("the null pays exactly zero", null.pnl_usd == 0.0 and null.mark_source == "null")
gone = cf.mark(_w("d1:alt1","straddle","refused",100.0,100.0,[("GONE","buy",1)]), Q,
               risk_budget_usd=1000)
check("unpriceable world is unmarkable, not zero", gone.mark_source == "unmarkable")

rep = cf.report([taken, alt, null, gone])
check("unmarkable excluded from the comparison",
      rep["worlds_marked"] == 3 and rep["unmarkable"] == 1)
check("best available identified", rep["best_available"]["kind"] == "debit_spread")
check("false refusal counted", rep["false_refusals"] == 1)
check("opportunity capture is taken over best", rep["opportunity_capture"] == 0.8333)
check("negative refusal edge is reported as such",
      rep["refusal_edge_on_risk"] < 0 and "discarding edge" in rep["refusal_verdict"])

# Every world under water: a capture ratio against a non-positive denominator
# reads well and means nothing, so it is refused and the null is named instead.
loser = cf.mark(_w("d2","long_call","submitted",400.0,400.0,[(L,"buy",1)]),
                Q, risk_budget_usd=1000)          # 2.5 units, exit 300 -> -250
sunk  = cf.mark(_w("d2:alt0","debit_spread","refused",400.0,400.0,
                   [(L,"buy",1),(S,"sell",1)], "spread too wide"),
                Q, risk_budget_usd=1000)          # 2.5 units, exit 160 -> -600
rep2 = cf.report([loser, sunk, cf.mark(cf.null_world("d2","TSLA"), Q, risk_budget_usd=1000)])
check("no capture ratio against a loss", rep2["opportunity_capture"] is None)
check("says abstaining won", "abstaining won" in rep2.get("capture_note",""))
check("saved losses counted", rep2["saved_losses"] == 1)
check("positive refusal edge is reported as such",
      rep2["refusal_edge_on_risk"] > 0 and "selecting" in rep2["refusal_verdict"])
check("empty report is an absence, not a zero",
      cf.report([gone])["status"] == "nothing markable")
# A same-instant mark returns exactly minus the spread. A report full of those
# is a spread measurement, and must say so rather than read as vindicated caution.
check("fresh all-negative report carries the spread caveat",
      "bid-ask round trip" in rep2.get("caveat", ""))
check("a report with a winner carries no caveat", "caveat" not in rep)
check("families group by prefix",
      len(cf.worlds_for([_w("d1","long_call","submitted",2,2,[]),
                         _w("d1:alt0","straddle","refused",1,1,[]),
                         _w("zz","x","refused",1,1,[])], "d1")) == 3)

print("\n-- official tooling (the LLM has no order verb)")
from alpha import tooling
os.environ["AAT_DEV_KEY_ID"] = "PKFAKEFAKEFAKEFAKE"
os.environ["AAT_DEV_SECRET_KEY"] = "fake-secret-never-used"
os.environ["ALPACA_API_KEY_ID"] = "live-key-from-parent"       # the hazard
os.environ["AAT_SMOKE_CANARY"] = "should-not-reach-the-child"
check("`trading` withheld from LLM toolsets", "trading" not in tooling.LLM_SAFE_TOOLSETS)
# This block is about the CHILD ENVIRONMENT, not about role resolution, so it
# declares the role instead of inheriting it. Run with AAT_ACCOUNT_ROLE=exp1 in
# the ambient environment, asking for "dev" here is a real ROLE DISAGREEMENT and
# `config.credentials` refuses it -- correctly: orders would go to one account
# and its ledger rows would be written under the other's name. The guard's own
# advice is "set both, or neither", so this sets both.
os.environ["AAT_ACCOUNT_ROLE"] = "dev"
env = tooling.official_env("dev", toolsets=tooling.LLM_SAFE_TOOLSETS)
check("child env drops parent live keys",
      not any(n in env for n in config._FORBIDDEN_INHERITED))
check("child env is built, not inherited", "AAT_SMOKE_CANARY" not in env)
check("child env forces paper",
      env["ALPACA_PAPER_TRADE"] == "true" and env["ALPACA_LIVE_TRADE"] == "false")
check("ALPACA_TOOLSETS is set from the allowlist",
      env["ALPACA_TOOLSETS"] == ",".join(tooling.LLM_SAFE_TOOLSETS))
try:
    tooling._assert_clean({"ALPACA_LIVE_TRADE": "true", "ALPACA_PAPER_TRADE": "true"})
    check("live-routed env refused", False)
except tooling.ToolingRefusal:
    check("live-routed env refused", True)
try:
    tooling._assert_clean({"ALPACA_API_KEY_ID": "x", "ALPACA_LIVE_TRADE": "false",
                           "ALPACA_PAPER_TRADE": "true"})
    check("forbidden name in child env refused", False)
except tooling.ToolingRefusal:
    check("forbidden name in child env refused", True)
spec = tooling.redacted_mcp_spec("dev")
check("spec leaks no secret",
      "fake-secret-never-used" not in repr(spec) and "PKFAKEFAKEFAKEFAKE" not in repr(spec))
check("spec declares the model cannot trade", spec["model_can_place_an_order"] is False)
check("spec names what was withheld", "trading" in spec["withheld_toolsets"])
for v in ["AAT_DEV_KEY_ID","AAT_DEV_SECRET_KEY","ALPACA_API_KEY_ID","AAT_SMOKE_CANARY"]:
    os.environ.pop(v, None)

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

import tests_smoke_brains
fails += tests_smoke_brains.fails
import tests_smoke_pead
fails += tests_smoke_pead.fails
import tests_smoke_equity
fails += tests_smoke_equity.fails
import tests_smoke_rule_cells
fails += tests_smoke_rule_cells.fails
import tests_smoke_refusal_nav
fails += tests_smoke_refusal_nav.fails
import tests_smoke_counterfactual_units
fails += tests_smoke_counterfactual_units.fails
import tests_smoke_crossbook
fails += tests_smoke_crossbook.fails
import tests_smoke_analyst_targets
fails += tests_smoke_analyst_targets.fails
import tests_smoke_stop_reconcile
fails += tests_smoke_stop_reconcile.fails
import tests_smoke_drivers
fails += tests_smoke_drivers.fails
import tests_smoke_admission
fails += tests_smoke_admission.fails
import tests_smoke_psychohistory
fails += tests_smoke_psychohistory.fails
import tests_smoke_universe
fails += tests_smoke_universe.fails
import tests_smoke_chain_width
fails += tests_smoke_chain_width.fails
import tests_smoke_manage_only
fails += tests_smoke_manage_only.fails
print(f"\n{'ALL PASS' if not fails else str(len(fails))+' FAILED: '+', '.join(fails)}\n")
raise SystemExit(1 if fails else 0)
