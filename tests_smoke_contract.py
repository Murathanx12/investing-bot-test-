"""The strategy contract, and the exit rule that now obeys it (B2, 2026-09-05).

Every check here corresponds to a measured defect, not to a design preference:

  1. 60% of the fleet's round trips finished in the SESSION THEY OPENED, on
     books whose sealed thesis is a 21-session drift (S39). A minimum hold that
     only a typed reason may pre-empt is the fix; these tests pin it.
  2. `exits.py` charged a flat 3% stop while `protect.py` placed the venue stop
     at the PROFILE width -- so the exit pass pre-empted the stop the position
     was sized against, and on PANW that barrier sat 0.52 sigma out
     (FINDING_2026-09-05 3a).
  3. `deadline_liquidation_due` returned True at 10:45 ET EVERY DAY once the
     deadline date had passed. With entries re-armed that is a book flattened
     each morning for ever.
  4. The re-entry guard read the venue's filled STOPS and was blind to a
     position `exits.manage` closed itself -- three of the four exit routes.
  5. `Mandate.tier` was read nowhere: a SAFE book opened five unhedged shorts.
  6. Nothing compared the claimed move in dollars with the stop in dollars,
     though the book held both numbers (0.13-0.18:1 on all five).
  7. A close that FAILED after its protective stop was cancelled left the
     position naked for 76 minutes.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")
# The venue guard is set by `run_tests.py` and ONLY by it, and is asserted by
# `tests_smoke_test_isolation` down to the string: a suite that sets its own
# guard is a suite that can be run without one. Run this file through the runner.

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import admission, contract, exits, fleet, ledger, protect
from alpha.broker.alpaca import BrokerRefusal

# ---------------------------------------------------------------- 1. the shape

print("\n-- the contract: what a book must state before it trades")
k = contract.for_book("hack4", day="2026-09-08", risk_budget_usd=1500.0, profile="maximum")
check("a tracker book declares 21 sessions and a 10-session minimum hold",
      (k.expected_horizon_sessions, k.min_normal_hold_sessions) == (21, 10),
      f"{k.expected_horizon_sessions}/{k.min_normal_hold_sessions}")
check("a tracker book declares NO profit target -- 2.5% of a 21-session thesis is noise",
      k.profit_target_frac is None, str(k.profit_target_frac))
check("the stop width is the PROFILE's, not a flat 3%", abs(k.stop_fraction() - 0.06) < 1e-9,
      f"{k.stop_fraction():.3f}")
check("the expiry is derived from the horizon in SESSIONS (weekends skipped)",
      k.thesis_expiry == "2026-10-07", k.thesis_expiry)
check("a complete contract validates", contract.validate(k.as_dict()) == [],
      str(contract.validate(k.as_dict())))

ev = contract.for_book("hack2", day="2026-09-08", risk_budget_usd=500.0, profile="aggressive")
check("an event book declares its own +1..+3 horizon and no minimum hold",
      (ev.expected_horizon_sessions, ev.min_normal_hold_sessions) == (3, 0))
check("every emergency reason is in the enum",
      set(k.emergency_exit_reasons) == set(contract.EMERGENCY_EXIT_REASONS))

print("\n-- validation REFUSES, and says everything that is wrong at once")
check("an absent contract is refused", len(contract.validate(None)) == 1)
bad = dict(k.as_dict()); bad.pop("risk_budget_usd")
check("a missing field is named", any("risk_budget_usd" in b for b in contract.validate(bad)))
bad2 = dict(k.as_dict()); bad2["min_normal_hold_sessions"] = 30
check("a hold longer than the horizon is refused -- it could never exit normally",
      any("exceeds the horizon" in b for b in contract.validate(bad2)))
bad3 = dict(k.as_dict()); bad3["hard_falsifiers"] = []
check("a thesis nothing could refute is refused", any("falsifier" in b for b in contract.validate(bad3)))
bad4 = dict(k.as_dict()); bad4["risk_budget_usd"] = 0
check("a zero risk budget is refused", any("risk_budget_usd" in b for b in contract.validate(bad4)))
bad5 = dict(k.as_dict()); bad5["emergency_exit_reasons"] = ["BECAUSE_I_SAID_SO"]
check("an unknown emergency reason is refused", any("not in the enum" in b for b in contract.validate(bad5)))

# ------------------------------------------------------- 2. the exit rule obeys

print("\n-- exits: before the minimum hold, only a typed reason closes")
ENTRY = "2026-09-08T14:00:00+00:00"          # Tue 10:00 ET
SEALED = contract.for_book("hack4", day="2026-09-08", risk_budget_usd=1500.0,
                           profile="maximum").as_dict()
ROW = {"action": "submitted", "symbol": "RZLV", "instrument": "long_shares",
       "account_role": None, "ts_utc": ENTRY,
       "outcome": {"horizon_days": 21.0, "contract": SEALED}}
POS = {"asset_class": "us_equity", "symbol": "RZLV", "qty": "100",
       "cost_basis": "10000", "unrealized_plpc": "0.0"}
DL = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat().replace("+00:00", "Z")


def ev_at(days: int, plpc: float, hour_utc: int = 16):
    when = datetime(2026, 9, 8, hour_utc, 0, tzinfo=timezone.utc) + timedelta(days=days)
    return exits.evaluate({**POS, "unrealized_plpc": str(plpc)},
                          deadline_utc=DL, now=when, rows=[ROW])


v = ev_at(0, -0.029)
check("session 1, -2.9%: HELD. This is the churn that emptied the books",
      not v.close and v.code == "HELD", f"{v.code}: {v.reason[:70]}")
v = ev_at(1, 0.030)
check("session 2, +3.0%: HELD -- a tracker book has no profit target",
      not v.close and v.code == "HELD", f"{v.code}: {v.reason[:70]}")
v = ev_at(1, -0.070)
check("-7.0% is inside the 6% profile stop? no -- past it, so HARD_RISK_LIMIT",
      v.close and v.code == "HARD_RISK_LIMIT", f"{v.code}: {v.reason[:70]}")
v = ev_at(1, -0.040)
check("-4.0% HOLDS at the 6% profile width, where the old flat 3% would have sold",
      not v.close, f"{v.code}: {v.reason[:70]}")
v = ev_at(29, 0.01)                                  # 21 sessions later, on the expiry date
check("at the horizon: HORIZON_SPENT", v.close and v.code == "HORIZON_SPENT",
      f"{v.code}: {v.reason[:70]}")
v = ev_at(31, 0.01)                                  # two days past the declared expiry
check("past the thesis expiry: THESIS_EXPIRED, whether or not it moved",
      v.close and v.code == "THESIS_EXPIRED", f"{v.code}: {v.reason[:70]}")
v = exits.evaluate(POS, deadline_utc=DL,
                   now=datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc), rows=[])
check("shares with NO ledger row: EXECUTION_CORRECTION, flattened",
      v.close and v.code == "EXECUTION_CORRECTION", f"{v.code}: {v.reason[:70]}")

print("\n-- the contract travels with the POSITION, not with today's seal")
c_led = contract.resolve(ROW, day="2026-09-09")
check("a row's own contract is read back (source: ledger)", c_led.source == "ledger",
      c_led.source)
c_leg = contract.resolve({"outcome": {"horizon_days": 2.0}}, book="dev", day="2026-09-09")
check("a legacy row keeps the horizon it recorded",
      c_leg.expected_horizon_sessions == 2 and c_leg.source == "ledger_horizon_days",
      f"{c_leg.expected_horizon_sessions} {c_leg.source}")
c_def = contract.resolve(None, book="hack3", day="2026-09-09")
check("no row at all -> the role default, stamped as such",
      (c_def.expected_horizon_sessions, c_def.source) == (21, "role_default"), c_def.source)

# ------------------------------------------------------------- 3. the deadline

print("\n-- the deadline fires ON its date, not every day after it")
DEADLINE = "2026-09-04T15:00:00Z"                    # 11:00 ET


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


check("deadline day, 10:44 ET -> not yet",
      not exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 4, 14, 44)))
check("deadline day, 10:46 ET -> liquidate",
      exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 4, 14, 46)))
check("THE DAY AFTER at 10:46 ET -> NOT due. The old code said True here, for ever",
      not exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 5, 14, 46)))
check("a week later -> still not due",
      not exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 11, 18, 0)))
check("the day BEFORE -> not due",
      not exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 3, 18, 0)))
check("both sides compared in ET: 00:30 UTC on 09-05 is 20:30 ET on 09-04 -- still due",
      exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 5, 0, 30)))
check("05:00 UTC on 09-05 is 01:00 ET on 09-05 -- a different day, not due",
      not exits.deadline_liquidation_due(DEADLINE, now=at(2026, 9, 5, 5, 0)))

print("\n-- the mandate end is a variable, and it defaults to the contest deadline")
from alpha import config
check("no env -> the competition deadline (nothing changes for old callers)",
      config.deadline_utc() == config.COMPETITION["deadline_utc"])
os.environ["AAT_MANDATE_END_UTC"] = "2027-12-31T15:00:00Z"
check("AAT_MANDATE_END_UTC moves it", config.deadline_utc() == "2027-12-31T15:00:00Z")
del os.environ["AAT_MANDATE_END_UTC"]
check("the fleet ships the mandate end to every service",
      fleet.COMMON_ENV["AAT_MANDATE_END_UTC"].startswith("2027-"))
check("a share-only book's expiry is the mandate end, not an option date",
      fleet.expiry_for(fleet.FLEET["hack4"]) == fleet.COMMON_ENV["AAT_LOOP_EXPIRY"])
opt_exp = fleet.expiry_for(fleet.FLEET["hack5"], today=datetime(2026, 9, 8).date())
check("an options book gets a DERIVED third-Friday expiry at least a fortnight out",
      opt_exp == "2026-10-16", opt_exp)

# --------------------------------------------------------- 4. the re-entry guard

print("\n-- the re-entry guard sees every exit, not only venue stops")
from alpha import runner

TODAY = exits.session_day()
YEST = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
ROWS = [
    {"brain": "exit", "action": "closed", "symbol": "AAA", "account_role": "dev",
     "ts_utc": datetime.now(timezone.utc).isoformat()},
    {"brain": "exit", "action": "closed", "symbol": "BBB", "account_role": "dev", "ts_utc": YEST},
    {"brain": "exit", "action": "closed", "symbol": "CCC", "account_role": "hack9", "ts_utc":
     datetime.now(timezone.utc).isoformat()},
    {"brain": "exit", "action": "close_failed", "symbol": "DDD", "account_role": "dev",
     "ts_utc": datetime.now(timezone.utc).isoformat()},
    {"brain": "exit", "action": "closed", "symbol": "EEE", "account_role": "dev", "ts_utc": None},
]
seen = runner.exits_closed_today(rows_today=ROWS, role="dev")
check("a name this book closed TODAY blocks re-entry", "AAA" in seen, str(sorted(seen)))
check("yesterday's exit does not -- tomorrow is a new decision", "BBB" not in seen)
check("another account's exit does not", "CCC" not in seen)
check("a FAILED close is not an exit", "DDD" not in seen)
check("an undated row is skipped, never assumed to be today", "EEE" not in seen, str(sorted(seen)))

# ------------------------------------------------------ 5/6. mandate and edge

print("\n-- the mandate binds on SIDE, and the edge is compared with the stop")
check("no fleet book may open a naked short by default",
      not any(fleet.may_short(r) for r in fleet.FLEET))
check("an unknown role may not short either", not fleet.may_short("whatever"))

from alpha import book as book_mod
from alpha.engine import sizing


class _S:                                   # the two fields `admit` reads
    def __init__(self, kind="long_shares", max_loss=500.0, symbol="PANW"):
        self.kind, self.max_loss, self.symbol = kind, max_loss, symbol
        self.legs = ((symbol, "sell" if "short" in kind else "buy", 1),)


bk = book_mod.reconstruct([], equity=100_000.0, account_role=None, rows=[])
common = dict(equity=100_000.0, aggregate_cap=0.5, gross_cap=None)
a = admission.admit(bk, _S("short_shares"), 1, is_naked_short=True, may_short=False, **common)
check("a book that has not declared allow_short cannot open one",
      not a.ok and "MANDATE" in a.reason, a.reason[:60])
a = admission.admit(bk, _S("short_shares"), 1, is_naked_short=True, may_short=True,
                    expected_edge_usd=114.0, stop_loss_usd=474.0, **common)
check("PANW's own numbers: $114 of claimed move against a $474 stop -> REFUSED",
      not a.ok and "EDGE vs STOP" in a.reason and a.metrics["edge_over_stop"] == 0.241,
      f"{a.metrics.get('edge_over_stop')} {a.reason[:60]}")
a = admission.admit(bk, _S("short_shares"), 1, is_naked_short=True, may_short=True,
                    expected_edge_usd=1500.0, stop_loss_usd=474.0, **common)
check("a naked short at 3.16:1 clears the floor", a.ok, a.reason[:60])
a = admission.admit(bk, _S("short_shares"), 1, is_naked_short=True, may_short=True, **common)
check("a naked short whose edge cannot be measured is REFUSED, not waved through",
      not a.ok and a.metrics["edge_over_stop"] == "CANNOT DETERMINE", a.reason[:60])
a = admission.admit(bk, _S("long_shares"), 1, expected_edge_usd=114.0, stop_loss_usd=474.0,
                    **common)
check("a LONG at the same 0.24:1 is admitted and the ratio is RECORDED",
      a.ok and a.metrics["edge_over_stop"] == 0.241, f"{a.ok} {a.metrics.get('edge_over_stop')}")
check("recording it is the census: a 3:1 blanket floor would refuse every book here",
      contract.defaults_for("hack4")["min_edge_over_stop"] is None)

# --------------------------------------------- 7. a failed close is not naked

print("\n-- a close that fails re-places the stop it just cancelled")


class RefusingClient:
    """Cancels fine, refuses the close -- the 2026-09-04 hack2 sequence."""

    def __init__(self):
        self.placed, self.cancelled = [], []

    def account(self):
        return {"equity": "100000", "last_equity": "100000"}

    def positions(self):
        return [{"asset_class": "us_equity", "symbol": "PANW", "qty": "-48",
                 "avg_entry_price": "328.90", "cost_basis": "-15787",
                 "unrealized_plpc": "-0.09"}]

    def orders(self, status="open", limit=200):
        return []

    def submit_protective_stop(self, order):
        self.placed.append(order)
        return {"id": f"srv-{len(self.placed)}"}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)

    def close_position(self, symbol, **kw):
        raise BrokerRefusal("DELETE /v2/positions/PANW -> HTTP 403: position is not closeable")

    def latest_trade(self, symbols):
        return {"trades": {s: {"p": 328.9} for s in symbols}}


rc = RefusingClient()
summary = exits.manage(rc, deadline_utc=DL, dry_run=False)
kinds = [a[0] for a in summary["actions"]]
check("the close failure is still an error and still recorded", summary["errors"] >= 1, str(kinds))
check("the protective stop is re-placed rather than left cancelled",
      "stop_replaced" in kinds or len(rc.placed) >= 1, f"{kinds} placed={len(rc.placed)}")

# ------------------------------------------------------------ 8. the seal gate

print("\n-- a book without a contract may not be sealed")
from scripts import prediction_book as pb

good_port = {"holdings": [{"symbol": "AAA", **{f: contract.for_book(
    "hack4", day="2026-09-08", risk_budget_usd=100.0).as_dict()[f]
    for f in contract.REQUIRED_FIELDS}}],
    "contract": contract.for_book("hack4", day="2026-09-08", risk_budget_usd=100.0).as_dict()}
check("a complete book passes", pb.check_contracts({"portfolios": {"hack4": good_port}}) == [])
no_contract = {"holdings": good_port["holdings"]}
check("no contract block -> refused",
      any("contract" in b for b in pb.check_contracts({"portfolios": {"hack4": no_contract}})))
unstamped = {"contract": good_port["contract"], "holdings": [{"symbol": "BBB"}]}
check("an unstamped holding -> refused and named",
      any("BBB" in b for b in pb.check_contracts({"portfolios": {"hack4": unstamped}})))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("0 failures")
