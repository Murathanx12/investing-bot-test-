"""The counterfactual's UNITS, and the two guards that let them through.

Run: python tests_smoke_counterfactual_units.py  (also executed by tests_smoke.py)

Found in production 2026-08-29, on hack1's own log:

    refused  pair_short_vs_iwm BBW  +61,003,981  (+1220079.6% of risk)
    refused  pair_short_vs_iwm BBW  +62,687,334  (+1253746.7% of risk)
    refusal_edge_on_risk    -744.9337
    refusal_verdict         the gate is discarding edge -- loosen it or explain it

$62 million on a $99,250 book, and the verdict computed from it is an
instruction to LOOSEN the risk gates. Three defects, each independent:

1. `exit_value_per_unit` ended `return total * MULT` -- the OPTIONS contract
   multiplier applied to every leg, shares included. The BBW pair is two share
   legs; IWM_bid - BBW_ask = 296.30, and x100 makes 29,630 per unit against an
   entry recorded at multiplier 1. Two sides of one subtraction, scales 100
   apart. Same defect as 02a3047 (`fills.mark_now`), one layer down: P0.1 fixed
   which ENDPOINT a share leg is quoted from and never touched the multiplier
   applied to the answer.

2. `mark()` had a FLOOR and no CEILING. A mark below -1.05x max loss is
   unmarkable (added after a refused bear-call spread showed -292% of risk);
   +1,226,583% of risk went straight into the verdict. A guard built on one side
   of a symmetric error catches half of it.

3. A PAIR IS NOT ITS RECORDED LEGS. `alpha/book.py:249` already says the row's
   (1, 1) ratios do not describe the hedge -- and on a REFUSED row there is no
   `hedge_shares` either, while `entry_cost_per_unit` is the SHORT LEG ALONE
   (BURL records -289.745 against a ~290 share price, IWM nowhere in it).
   Pricing an exit off both legs against an entry off one yields the short's
   whole notional as profit.
"""
from __future__ import annotations

import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import counterfactual as cf

# The real row, from state/decisions.jsonl.
BBW_PAIR = {
    "decision_id": "d1", "symbol": "BBW", "instrument": "pair_short_vs_iwm",
    "action": "refused", "ts_utc": "2026-08-28T14:00:00+00:00",
    "max_loss_per_unit": 2.3616736965436482,
    "entry_cost_per_unit": -28.405790000000003,
    "legs": [["BBW", "sell", 1], ["IWM", "buy", 1]],
}
# A pair that was actually BUILT records the hedge it bought.
BBW_BUILT = dict(BBW_PAIR, contracts=100, outcome={"hedge_shares": 8})
SHARE_QUOTES = {"BBW": {"bid": 23.90, "ask": 24.10}, "IWM": {"bid": 320.40, "ask": 320.60}}

print("\n-- 1. a SHARE leg is worth its price, not a hundred times its price")
exit_pu = cf.exit_value_per_unit(BBW_PAIR["legs"], SHARE_QUOTES)
check("two share legs mark at multiplier 1",
      abs(exit_pu - (320.40 - 24.10)) < 1e-9, f"{exit_pu:.2f}, expected {320.40 - 24.10:.2f}")
check("...and NOT at the options multiplier",
      abs(exit_pu - (320.40 - 24.10) * 100) > 1.0, f"{exit_pu:.2f}")
check("an OPTION leg still carries the x100 it really has",
      abs(cf.exit_value_per_unit([["NVDA260918C00200000", "buy", 1]],
                                 {"NVDA260918C00200000": {"bid": 5.00, "ask": 5.20}}) - 500.0) < 1e-9)
mixed_q = {"NVDA260918C00200000": {"bid": 5.00, "ask": 5.20}, "NVDA": {"bid": 180.00, "ask": 180.10}}
check("a MIXED structure gets each leg's own multiplier: call x100 minus shares x1",
      abs(cf.exit_value_per_unit([["NVDA260918C00200000", "buy", 1], ["NVDA", "sell", 1]],
                                 mixed_q) - (500.0 - 180.10)) < 1e-9)
check("leg_multiplier says so directly",
      cf.leg_multiplier("NVDA") == 1.0 and cf.leg_multiplier("NVDA260918C00200000") == 100.0)

print("\n-- 3. the production row is REFUSED outright, not priced at $62 million")
m = cf.mark(BBW_PAIR, SHARE_QUOTES, risk_budget_usd=5_000.0)
check("a refused pair carries no hedge quantity, so it is UNMARKABLE",
      m.mark_source == "unmarkable", f"{m.mark_source} {m.pnl_usd:+,.0f}")
check("...and contributes exactly zero", m.pnl_usd == 0.0, f"{m.pnl_usd:+,.0f}")
check("the reason names the incoherence rather than failing vaguely",
      str((m.detail or {}).get("why", "")).startswith("pair_incoherent"),
      str((m.detail or {}).get("why"))[:60])
# A row written after 2026-08-29 carries the pair's own shape: the ratio and
# what the hedge cost at entry, so entry and exit describe the SAME structure.
BBW_RECORDED = dict(BBW_PAIR, outcome={"hedge_ratio": 0.0747, "hedge_entry_ask": 320.60,
                                       "hedge_leg": "IWM"})
m_rec = cf.mark(BBW_RECORDED, SHARE_QUOTES, risk_budget_usd=5_000.0)
check("with hedge_ratio + hedge_entry_ask the pair IS marked",
      m_rec.mark_source == "chain", f"{m_rec.mark_source} {m_rec.pnl_usd:+,.0f}")
# The entry per unit is now the short's credit PLUS what the hedge cost, so
# entry and exit describe the same two-legged thing. -28.4058 + 0.0747*320.60
# = -4.457 per unit, against an exit of -24.10 + 0.0747*320.40 = -0.166.
check("the entry now includes the hedge, so both sides describe the same structure",
      abs(m_rec.entry_cost_usd / m_rec.units - (-28.405790000000003 + 0.0747 * 320.60)) < 1e-6,
      f"{m_rec.entry_cost_usd / m_rec.units:.4f}")
check("and the mark is bounded -- well inside the ceiling, not a fortune",
      abs(m_rec.return_on_risk) < cf.IMPLAUSIBLE_GAIN_ON_RISK, f"{m_rec.return_on_risk:+.2%}")

m_ok = cf.mark(BBW_BUILT, SHARE_QUOTES, risk_budget_usd=5_000.0)
check("an older row with hedge_shares/contracts still falls back to that ratio",
      m_ok.mark_source == "chain", f"{m_ok.mark_source} {m_ok.pnl_usd:+,.0f}")

print("\n-- 2. the CEILING: an impossible gain is unmarkable, as an impossible loss already was")
crazy_q = {"BBW": {"bid": 23.90, "ask": 24.10}, "IWM": {"bid": 99_999.0, "ask": 100_000.0}}
m2 = cf.mark(BBW_BUILT, crazy_q, risk_budget_usd=5_000.0)
check("a gain that is a huge multiple of the structure's own max loss is UNMARKABLE",
      m2.mark_source == "unmarkable", f"{m2.mark_source} {m2.pnl_usd:+,.0f}")
check("...and contributes ZERO rather than a fortune", m2.pnl_usd == 0.0, str(m2.pnl_usd))
check("the raw number is KEPT so the error is visible and countable",
      "raw_pnl_per_unit" in (m2.detail or {}) and "gain_on_risk" in (m2.detail or {}),
      str(sorted((m2.detail or {}))))
check("and the reason names which side it failed on",
      str((m2.detail or {}).get("why", "")).startswith("implausible_gain"),
      str((m2.detail or {}).get("why"))[:60])

loss_q = {"BBW": {"bid": 9_999.0, "ask": 10_000.0}, "IWM": {"bid": 320.40, "ask": 320.60}}
m3 = cf.mark(BBW_BUILT, loss_q, risk_budget_usd=5_000.0)
check("the pre-existing FLOOR still catches an impossible loss",
      m3.mark_source == "unmarkable" and m3.pnl_usd == 0.0, f"{m3.mark_source} {m3.pnl_usd:+,.0f}")

print("\n-- an ordinary SHARE world is still marked, and still moves")
LONG_SHARES = {"decision_id": "d2", "symbol": "NVDA", "instrument": "long_shares",
               "action": "refused", "ts_utc": "2026-08-28T14:00:00+00:00",
               "max_loss_per_unit": 10.80, "entry_cost_per_unit": 180.02,
               "legs": [["NVDA", "buy", 1]]}
m4 = cf.mark(LONG_SHARES, {"NVDA": {"bid": 183.00, "ask": 183.10}}, risk_budget_usd=5_000.0)
check("a real move is marked from the chain", m4.mark_source == "chain", m4.mark_source)
check("a long share position rising is a GAIN, at multiplier 1",
      m4.pnl_usd > 0 and abs(m4.pnl_usd - (183.00 - 180.02) * (5000 / 10.80)) < 1e-6,
      f"{m4.pnl_usd:+,.2f}")

print("\n-- the report counts what it threw away rather than dropping it in silence")
rep = cf.report([m, m2, m3, m4])
check("unmarkable worlds are counted", rep.get("unmarkable") == 3, str(rep.get("unmarkable")))
check("an implausible gain is counted SEPARATELY from a missing quote",
      rep.get("implausible") == 1, str(rep.get("implausible")))
check("and an incoherent pair is its own count, being its own kind of problem",
      rep.get("pair_incoherent") == 1, str(rep.get("pair_incoherent")))
check("the best-available world is the real one, not the fantasy",
      rep["best_available"]["pnl_usd"] == round(m4.pnl_usd, 2), str(rep["best_available"]))

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
