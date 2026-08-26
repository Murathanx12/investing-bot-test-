"""Smoke checks for PSYCHOHISTORY v0 (`alpha/psychohistory.py`). No keys, no network.

Run: python tests_smoke_psychohistory.py  (also executed by tests_smoke.py)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import psychohistory as ph
from alpha.sources.http import SourceRefusal

print("\n-- buckets are the PEAD terciles")
check("+3.1% is the flat bucket", ph.bucket_of(0.031) == "-3.5..+3.5%")
check("+5% is the mid band", ph.bucket_of(0.05) == "+3.5..+8.2%")
check("-9% is the far down tail", ph.bucket_of(-0.09) == "<-8.2%")
mk = ph.market_buckets(0.0558)
check("market buckets sum to 1", abs(sum(mk.values()) - 1.0) < 1e-3, str(mk))
check("market is symmetric", abs(mk["<-8.2%"] - mk[">+8.2%"]) < 1e-6 and abs(mk["-8.2..-3.5%"] - mk["+3.5..+8.2%"]) < 1e-6)
check("5.58% implied puts ~38% inside +/-3.5%", 0.30 < mk["-3.5..+3.5%"] < 0.45, f"{mk['-3.5..+3.5%']:.3f}")

print("\n-- scenario tree -> model buckets, validation")
scen = [
    {"name": "beat and raise, priced", "p": 0.5, "description": "x", "falsifiers": ["a"],
     "predicts": {"day0_move_bucket": "-3.5..+3.5%", "revenue_vs_consensus": "above", "guide_vs_consensus": "inline"}},
    {"name": "guide disappoints", "p": 0.3, "description": "y", "falsifiers": ["b"],
     "predicts": {"day0_move_bucket": "-8.2..-3.5%", "revenue_vs_consensus": "inline", "guide_vs_consensus": "below"}},
    {"name": "blowout", "p": 0.2, "description": "z", "falsifiers": ["c"],
     "predicts": {"day0_move_buckets": {"+3.5..+8.2%": 0.7, ">+8.2%": 0.3}, "revenue_vs_consensus": "above", "guide_vs_consensus": "above"}},
]
raw = {"causal_chain": [{"from": "a", "to": "b", "edge": "SUPPLIES", "confidence": 0.8, "lag_days": 0}],
       "scenarios": scen, "priced_in": 0.7, "surprise_axis": "guide", "templates_used": ["capex_echo", "made_up"],
       "candidate_expression": "none", "what_would_change_my_mind": ["q"]}
c = ph.validate_compiled(raw)
check("unknown template dropped, known kept", c["templates_used"] == ["capex_echo"])
mb = ph.model_buckets(c["scenarios"])
check("weighted spread folds correctly", abs(mb["+3.5..+8.2%"] - 0.14) < 1e-6 and abs(mb[">+8.2%"] - 0.06) < 1e-6, str(mb))
check("model buckets sum to 1", abs(sum(mb.values()) - 1.0) < 1e-3)
bad = dict(raw, scenarios=[dict(scen[0], p=0.5), dict(scen[1], p=0.2)])
try:
    ph.validate_compiled(bad); check("probabilities not summing to 1 are refused", False)
except SourceRefusal as exc:
    check("probabilities not summing to 1 are refused", "sum to" in str(exc))
bad = dict(raw, scenarios=[dict(scen[0], falsifiers=[]), scen[1], scen[2]])
try:
    ph.validate_compiled(bad); check("a scenario without a falsifier is refused", False)
except SourceRefusal as exc:
    check("a scenario without a falsifier is refused", "falsifier" in str(exc))
bad = dict(raw, scenarios=[dict(scen[0], predicts={"day0_move_bucket": "+5%"}), scen[1], scen[2]])
try:
    ph.validate_compiled(bad); check("an unknown bucket is refused", False)
except SourceRefusal as exc:
    check("an unknown bucket is refused", "bucket" in str(exc))

print("\n-- record, disagreement, resolve")
trigger = {"symbol": "NVDA", "event": "print", "event_date": "2026-08-27", "type": "scheduled_print"}
rec = ph.make_record(trigger, {"sessions": 3}, [{"kind": "measured", "fact": "f", "source": "s", "date": "d"}],
                     {"implied_move_to_expiry": 0.0558}, c, {"model": "fake", "cost_usd": 0.0}, asof="2026-08-26T05:00:00+00:00")
check("record is shadow-only", rec.action == "SHADOW_ONLY")
check("id is deterministic on (symbol, event, asof)", rec.id == ph.new_id("NVDA", "2026-08-27", "2026-08-26T05:00:00+00:00"))
d = rec.disagreement
check("disagreement names the largest bucket gap", d["largest"]["bucket"] in ph.BUCKETS and abs(d["total_variation"]) <= 1.0)
check("model has less tail mass than the market here", d["tail_mass_model"] < d["tail_mass_market"], f"{d['tail_mass_model']} vs {d['tail_mass_market']}")
store = Path(tempfile.mkdtemp()) / "ph.jsonl"
ph.append(rec, store)
rows = ph.read_all(store)
check("append + read round-trips", len(rows) == 1 and rows[0]["id"] == rec.id)
out = ph.resolve(rows[0], day0_move=-0.05, reported={"revenue_usd_bn": 93.0}, pead_3d=-0.012)
check("realised bucket from the move", out["realised_bucket"] == "-8.2..-3.5%")
check("Brier for both, and a verdict", out["brier_model"] < out["brier_market"] and out["model_beat_market"], f"{out['brier_model']} vs {out['brier_market']}")
check("scenario realised is the one that predicted the bucket", out["scenario_realised"] == "guide disappoints")
check("revenue vs consensus needs the consensus", out["revenue_vs_consensus_realised"] is None)
rec2 = ph.make_record(trigger, {}, [], {"implied_move_to_expiry": 0.0558, "consensus_revenue_usd_bn": 92.05}, c, {}, asof="2026-08-26T05:00:00+00:00")
out2 = ph.resolve(rec2.__dict__ | {"model_buckets": rec2.model_buckets, "market_buckets": rec2.market_buckets}, day0_move=0.01, reported={"revenue_usd_bn": 93.5})
check("revenue +1.6% vs consensus = above", out2["revenue_vs_consensus_realised"] == "above")
check("a flat print: the model that put 0.5 on the flat bucket beats the market's 0.38", out2["brier_model"] < out2["brier_market"], f"{out2['brier_model']} vs {out2['brier_market']}")
check("per-template calibration rows exist", "capex_echo" in out2["per_template"])

if __name__ == "__main__":
    print(f"\n{len(fails)} failures" + (": " + ", ".join(fails) if fails else ""))
    raise SystemExit(1 if fails else 0)
