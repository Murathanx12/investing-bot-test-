"""Smoke tests for PNL_ATTRIBUTION_v1 and POSITION_ARBITER_v1. Run: python tests_smoke_arbiter.py"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from alpha import arbiter, attribution, book, exits, ledger
from alpha.data.chain import _bs_price

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("\n-- implied vol inversion")
iv = attribution.implied_vol(_bs_price(100, 100, 0.01, 0.55, "C"), 100, 100, 0.01, "C")
check("round-trips BS", iv is not None and abs(iv - 0.55) < 1e-4, str(iv))
check("below intrinsic -> None", attribution.implied_vol(0.5, 100, 90, 0.01, "C") is None)
check("zero price -> None", attribution.implied_vol(0.0, 100, 100, 0.01, "P") is None)

print("\n-- attribution: the identity holds and vega carries the IV move")
now = datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc)
t_entry = "2026-08-25T15:40:00+00:00"
row = {
    "ts_utc": t_entry, "decision_id": "20260825T1540:vol_gap:NVDA", "brain": "vol_gap",
    "quote_snapshot": {"spot": 212.0, "legs": [
        {"symbol": "NVDA260828C00222500", "bid": 2.20, "ask": 2.30, "adjusted_mid": 2.25, "iv": 0.80},
        {"symbol": "NVDA260828C00232500", "bid": 0.76, "ask": 0.80, "adjusted_mid": 0.78, "iv": 0.82},
    ]},
    "breakeven_move": 0.05, "implied_move": 0.06,
}
st = book.OpenStructure("20260825T1540:vol_gap:NVDA", "vol_gap", "NVDA", "bear_call_spread", 10, 760.0, -146.0,
                        [("NVDA260828C00222500", "sell", 1), ("NVDA260828C00232500", "buy", 1)],
                        "print:2026-08-26", t_entry, "dev", row)
# IV rose 10 points into the print, spot unchanged: the short call is marked up, the long wing less so.
positions = {
    "NVDA260828C00222500": {"avg_entry_price": "2.25", "current_price": "3.00", "qty": "-10"},
    "NVDA260828C00232500": {"avg_entry_price": "0.79", "current_price": "1.10", "qty": "10"},
}

# The manage() section below reads the REAL clock (the test pins that on
# purpose), so ITS contracts must expire in the future: on 2026-08-29 the
# literal 260828 legs were flattened as expired before the override ran.
_exp = datetime.now(timezone.utc).date() + timedelta(days=14)
while _exp.weekday() != 4:
    _exp += timedelta(days=1)
EXP = _exp.strftime("%y%m%d")
st_live = book.OpenStructure("20260825T1540:vol_gap:NVDA", "vol_gap", "NVDA", "bear_call_spread", 10, 760.0, -146.0,
                             [(f"NVDA{EXP}C00222500", "sell", 1), (f"NVDA{EXP}C00232500", "buy", 1)],
                             "print:2026-08-26", t_entry, "dev", row)
att = attribution.attribute_structure(st, positions, 212.0, now=now)
check("actual is the venue mark move", abs(att.actual_usd - (-10 * (3.00 - 2.25) * 100 + 10 * (1.10 - 0.79) * 100)) < 1e-6, f"{att.actual_usd:,.0f}")
total = att.delta_usd + att.gamma_usd + att.vega_usd + att.theta_usd + att.spread_usd + att.residual_usd
check("delta+gamma+vega+theta+spread+residual == actual", abs(total - att.actual_usd) < 1e-6)
check("spot unchanged -> delta and gamma are zero", abs(att.delta_usd) < 1e-9 and abs(att.gamma_usd) < 1e-9)
check("a short-vol structure marked up by IV is a VEGA loss", att.vega_usd < 0, f"{att.vega_usd:,.0f}")
check("theta is in the short structure's favour", att.theta_usd > 0, f"{att.theta_usd:,.0f}")
check("net delta is negative on a bear call spread", att.net_delta_shares < 0, f"{att.net_delta_shares:,.0f}")
check("spread paid at entry is a cost", att.spread_usd < 0)
bare = book.OpenStructure("x", "vol_gap", "NVDA", "bear_call_spread", 10, 760.0, -146.0, st.legs, None, t_entry, "dev",
                          {"ts_utc": t_entry, "quote_snapshot": {}})
att_bare = attribution.attribute_structure(bare, positions, 212.0, now=now)
check("no entry snapshot -> actual lands in residual and the leg says so",
      abs(att_bare.residual_usd - att_bare.actual_usd) < 1e-9 and all(l.note for l in att_bare.legs))

print("\n-- arbiter verdicts")
fc = {"symbol": "NVDA", "brain": "vol_gap", "predicted_move": 0.0, "predicted_sd": 0.03,
      "ts_utc": "2026-08-25T19:00:00+00:00", "outcome": {"horizon_days": 3.0, "evidence": {}}}
v = arbiter.judge(st, positions, 212.0, forecast=fc, now=now)
check("event node pending -> HOLD whatever the mark", v.action == "HOLD" and v.event_pending, v.reason[:80])
after = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
v2 = arbiter.judge(st, positions, 212.0, forecast=fc, now=after)
check("after the event the mark is judged", not v2.event_pending)
check("a quiet forecast keeps the short spread: HOLD with positive remaining edge",
      v2.action == "HOLD" and v2.remaining_edge_usd > 0, f"{v2.action} {v2.remaining_edge_usd:+,.0f}")
wild = {**fc, "predicted_move": 0.12, "predicted_sd": 0.02}
v3 = arbiter.judge(st, positions, 212.0, forecast=wild, now=after)
check("a forecast through the short strike says CLOSE", v3.action == "CLOSE" and v3.remaining_edge_usd < 0,
      f"{v3.action} {v3.remaining_edge_usd:+,.0f}")
v4 = arbiter.judge(st, positions, 212.0, forecast=None, now=after)
check("no forecast -> HOLD and says it cannot judge", v4.action == "HOLD" and "cannot judge" in v4.reason)
no_node = book.OpenStructure("y", "vol_gap", "NVDA", "iron_condor", 10, 760.0, -146.0, st.legs, None, t_entry, "dev", row)
others = [{"symbol": "NVDA", "brain": "event_move", "ts_utc": "2026-08-25T19:00:00+00:00",
           "outcome": {"evidence": {"event_date": "2026-08-26"}}}]
v5 = arbiter.judge(no_node, positions, 212.0, forecast=fc, now=now, all_forecasts=others)
check("another brain's event_date makes the event pending for a node-less structure", v5.event_pending)
v6 = arbiter.judge(no_node, positions, 212.0, forecast=fc, now=now,
                   all_forecasts=[{**others[0], "outcome": {"evidence": {"event_date": "2026-09-10"}}}])
check("an event after expiry is not pending for this structure", not v6.event_pending)
straddle = book.OpenStructure("z", "vol_gap", "META", "long_straddle", 4, 1620.0, 1620.0,
                              [("META260828C00565000", "buy", 1), ("META260828P00565000", "buy", 1)], None, t_entry, "dev",
                              {"ts_utc": t_entry, "quote_snapshot": {"spot": 565.0, "legs": []}, "breakeven_move": 0.03, "implied_move": 0.03})
pos_s = {"META260828C00565000": {"current_price": "10.5"}, "META260828P00565000": {"current_price": "5.25"}}
fc_s = {**fc, "symbol": "META", "predicted_sd": 0.045}
v7 = arbiter.judge(straddle, pos_s, 580.0, forecast=fc_s, now=after, net_delta_shares=250.0)
check("a two-sided structure with a big delta is a HEDGE advisory", v7.action == "HEDGE", v7.action)
check("mode defaults to advise", arbiter.mode() == "advise")
os.environ["AAT_ARBITER"] = "nonsense"; check("unknown mode falls back to advise", arbiter.mode() == "advise")
os.environ["AAT_ARBITER"] = "off"; check("off is off", arbiter.mode() == "off")

print("\n-- exits.manage: advise records, act overrides")
tmp = tempfile.mkdtemp(); ledger.LEDGER_DIR = __import__("pathlib").Path(tmp)
closed = []


class FakeClient:
    cancelled: list = []
    stops: list = []
    def account(self): return {"equity": "100000", "last_equity": "100000"}
    def orders(self, status="open", limit=200): return []
    def cancel_order(self, order_id): self.cancelled.append(order_id)
    def submit_protective_stop(self, order): self.stops.append(order); return {"id": "stop-1"}
    def positions(self):
        return [{"asset_class": "us_option", "symbol": f"NVDA{EXP}C00222500", "qty": "-10", "cost_basis": "-2250",
                 "avg_entry_price": "2.25", "current_price": "6.00", "unrealized_pl": "-3750", "unrealized_plpc": "-1.67"},
                {"asset_class": "us_option", "symbol": f"NVDA{EXP}C00232500", "qty": "10", "cost_basis": "790",
                 "avg_entry_price": "0.79", "current_price": "3.50", "unrealized_pl": "2710", "unrealized_plpc": "3.43"}]
    def close_position(self, symbol, **k): closed.append(symbol); return {}
    def latest_trade(self, symbols): return {"trades": {s: {"p": 212.0} for s in symbols}}


ledger.record(ledger.Decision(
    decision_id=st.decision_id, ts_utc=t_entry, symbol="NVDA", brain="vol_gap", signal_shape=None,
    instrument="bear_call_spread", thesis="t", predicted_move=0.0, predicted_sd=0.03, implied_move=0.06,
    breakeven_move=0.05, mdm_edge=0.1, quote_snapshot=row["quote_snapshot"], action="submitted", refusal_reason=None,
    risk_fraction=0.05, max_loss_usd=7600.0, order={"qty": "10"}, entry_cost_per_unit=-146.0, max_loss_per_unit=760.0,
    # THE EVENT DATE MUST BE RELATIVE, because this block deliberately runs
    # `exits.manage` against the REAL clock (see `exits.datetime = datetime`
    # below). A hard-coded "print:2026-08-26" made "is the event pending?" a
    # question about the wall calendar: it passed all day on 26 Aug and began
    # FAILING the moment NVDA actually reported, with no code change.
    #
    # Third instance of this class in one session -- after a test that depended
    # on AAT_ACCOUNT_ROLE being unset, and one that depended on it being set.
    # A fixture that encodes a moment in time is an ambient-state test wearing
    # a logic test's name.
    legs=tuple(st_live.legs), account_role="dev",
    outcome={"event_node": f"print:{(datetime.now(timezone.utc) + timedelta(days=1)).date()}"}))
ledger.record(ledger.Decision(
    decision_id="f:vol_gap:NVDA:forecast", ts_utc="2026-08-25T19:00:00+00:00", symbol="NVDA", brain="vol_gap",
    signal_shape=None, instrument="forecast", thesis="", predicted_move=0.0, predicted_sd=0.03, implied_move=None,
    breakeven_move=None, mdm_edge=None, quote_snapshot={}, action="forecast", refusal_reason=None, risk_fraction=0.0,
    max_loss_usd=0.0, order=None, outcome={"horizon_days": 3.0, "evidence": {}}), name="forecasts")
os.environ["AAT_ACCOUNT_ROLE"] = "dev"
os.environ["AAT_ARBITER"] = "advise"
exits.ARBITER_RECORD_EVERY_S = 0.0
exits.datetime = datetime  # ensure the module clock is the real one
s = exits.manage(FakeClient(), deadline_utc="2026-09-04T15:00:00Z", dry_run=False)
rows = ledger.read_all()
arb = [r for r in rows if r["brain"] == "arbiter"]
check("advise: the arbiter wrote a verdict row", arb and arb[-1]["action"] == "arbiter_hold", arb[-1]["action"] if arb else "none")
check("advise: the leg stop still fired on the short leg (-167% of credit)", f"NVDA{EXP}C00222500" in closed, str(closed))
closed.clear()
os.environ["AAT_ARBITER"] = "act"
s = exits.manage(FakeClient(), deadline_utc="2026-09-04T15:00:00Z", dry_run=False)
check("act: event pending -> the leg stop is overridden, nothing closed", not closed and any(a[0] == "override_hold" for a in s["actions"]), str(closed))
os.environ["AAT_ARBITER"] = "advise"
del os.environ["AAT_ACCOUNT_ROLE"]

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("ALL PASS")
