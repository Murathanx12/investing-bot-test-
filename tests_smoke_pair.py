"""PAIR_SHORT_VS_IWM -- the hedged expression of a wide-universe DOWN print.
Run: python run_tests.py -k pair   (the runner sets the venue guard)

Why a pair (post_event_drift, 2,532 names): the unhedged short of a 5%+ loser
is worth +0.04% / +0.00% per 3 sessions in SIMPLE returns; short loser / long
IWM keeps +0.35% / +0.26% (t 2.2 / 2.0). The edge is relative, so the structure
must be. Everything below is the contract that lets that structure exist
without leaving a one-legged short anywhere.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

from alpha import book, exits, ledger, protect, runner
from alpha.brains.base import Forecast
from alpha.broker.alpaca import BrokerRefusal, client_order_id
from alpha.engine import equity, sizing

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


_TODAY = datetime.now(timezone.utc).date()
EXPIRY = (_TODAY + timedelta(days=1)).isoformat()
EVENT_DATE = (_TODAY - timedelta(days=1)).isoformat()

# ------------------------------------------------------------------ builder
# A DERIVED weekday mid-session clock, never a literal date. `run_pass` refuses
# share entries inside the opening range (09:30-09:45 ET); before this was
# injectable these suites went red for fifteen minutes every day and green again
# at 09:45 with nothing changed but the wall clock. Derive from `today` so the
# fixture cannot rot -- the rule CLAUDE.md states after three literal expiries.
def _mid_session_et():
    from datetime import datetime, time as _time, timedelta
    d = datetime.now().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime.combine(d, _time(10, 30))


NOW_ET = _mid_session_et()


print("\n-- equity.pair_short_vs_hedge: dollar-neutral, charged on the spread")
bars = [{"o": 100.0, "c": 100.0}] * 5          # no gaps -> floor 2%
st = equity.pair_short_vs_hedge("LOSER", spot=20.0, bid=19.98, ask=20.02,
                                hedge_symbol="IWM", hedge_spot=300.0, hedge_bid=299.9, hedge_ask=300.1,
                                bars=bars, hedge_bars=bars, implied_move=0.0, event_pending=False,
                                horizon_days=3.0, days_to_expiry=3.0, shortable=True)
check("built with the pair kind and two legs", st is not None and st.kind == "pair_short_vs_iwm"
      and st.legs == (("LOSER", "sell", 1), ("IWM", "buy", 1)), str(getattr(st, "legs", None)))
check("hedge ratio = spot / hedge_spot (dollar neutral)", abs(st.quote["hedge_ratio"] - 20.0 / 300.0) < 1e-6)
check("charge = short (stop 3% + gap 2%) + hedge gap 2% = 7% of spot", abs(st.max_loss - 20.0 * 0.07) < 1e-9, f"{st.max_loss:.3f}")
check("the charge is named a STRESS charge on the SPREAD, unbounded declared",
      "SPREAD" in st.quote["risk_semantics"]["max_loss_is"] and "UNBOUNDED" in st.quote["risk_semantics"]["theoretical_max_loss"])
check("direction down, credit entry at the bid", st.direction == "down" and st.entry_cost == -19.98)
check("kind is in equity.KINDS and admissible for a direction claim",
      st.kind in equity.KINDS and __import__("alpha.claims", fromlist=["x"]).admissible("direction", st.kind))
check("not shortable -> not built", equity.pair_short_vs_hedge("L", spot=20, bid=19.9, ask=20.1, hedge_spot=300,
      hedge_bid=299.9, hedge_ask=300.1, bars=None, hedge_bars=None, implied_move=0.0, event_pending=False,
      horizon_days=3, days_to_expiry=3, shortable=False) is None)
check("hedge shares rounded once on the whole position", equity.hedge_shares(150, 20.0 / 300.0) == 10
      and equity.hedge_shares(1, 20.0 / 300.0) == 1)

# ------------------------------------------------------------- orders
print("\n-- runner.build_order: two equity limit orders, hedge sized on the position")
orders = runner.build_order(st, 150)
check("returns a LIST of two orders", isinstance(orders, list) and len(orders) == 2)
check("leg 1 sells the loser at the bid, DAY limit", orders[0] == {"symbol": "LOSER", "qty": "150", "side": "sell",
      "type": "limit", "limit_price": "19.98", "time_in_force": "day"}, str(orders[0]))
check("leg 2 buys 10 IWM at the ask, DAY limit", orders[1] == {"symbol": "IWM", "qty": "10", "side": "buy",
      "type": "limit", "limit_price": "300.10", "time_in_force": "day"}, str(orders[1]))
rec = runner.pair_order_record(orders)
check("ledger order record is ONE dict with qty and hedge_qty", rec["qty"] == "150" and rec["hedge_qty"] == "10" and rec["pair"])
check("shares/options build_order still returns a dict", isinstance(runner.build_order(sizing.Structure(
    "X", "long_shares", direction="up", entry_cost=180.02, max_loss=10.8, breakeven_move=0.0, implied_move=0.03,
    quote_spread_pct=0.0, days_to_expiry=2, legs=(("X", "buy", 1),)), 5), dict))
check("client ids: same decision, leg suffixes, distinct",
      client_order_id("d:leg1") != client_order_id("d:leg2") and client_order_id("d:leg1") == client_order_id("d:leg1"))


# ------------------------------------------------------------- end to end
class FakeChain:
    def __init__(self, spot=20.0, implied=0.03):
        self.underlying = "LOSER"; self.spot = spot; self.spot_source = "test"
        self.spot_ts = datetime.now(timezone.utc); self.feed = "test"; self.market_open = True
        self.median_quote_age_seconds = 0.0; self.contracts = []; self._implied = implied

    def implied_move(self, expiry): return self._implied
    def parity_gap(self, expiry): return None


class FakeClient:
    def __init__(self, positions=(), fail_leg2=False):
        self._p = list(positions); self.fail_leg2 = fail_leg2
        self.submitted = []; self.cancelled = []; self.closed = []
        self._q = {"LOSER": (19.98, 20.02), "IWM": (299.9, 300.1)}

    def account(self): return {"equity": "100000", "last_equity": "100000"}
    def positions(self):
        # In the leg-2-failure scenario the short leg FILLS after leg 1 is sent
        # (the venue holds it) -- so the position exists only once a submit did.
        if self.fail_leg2 and self.submitted:
            return list(self._p) + [{"asset_class": "us_equity", "symbol": "LOSER", "qty": "-40", "cost_basis": "-799"}]
        return list(self._p)
    def orders(self, status="open", limit=200): return []
    def clock(self): return {"is_open": True}
    def stock_quote(self, syms):
        return {"quotes": {s: {"bp": self._q[s][0], "ap": self._q[s][1], "bs": 5, "as": 5, "t": "now"} for s in syms if s in self._q}}
    def stock_bars(self, symbol, **kw): return {"bars": {symbol: []}}
    def asset(self, sym): return {"shortable": True, "easy_to_borrow": True, "tradable": True}
    def submit(self, order, *, decision_id, quote_snapshot):
        self.submitted.append((decision_id, order))
        if self.fail_leg2 and len(self.submitted) == 2:
            raise BrokerRefusal("HTTP 403 insufficient buying power")
        return {"id": "fake-" + decision_id}
    def cancel_order(self, oid): self.cancelled.append(oid)
    def close_position(self, symbol, *, percentage=None, qty=None):
        self.closed.append((symbol, qty)); return {}
    def _request(self, *a, **k): return {}


print("\n-- run_pass: a pair forecast enumerates the PAIR and never short_shares")
state = sizing.TournamentState(equity=100_000, starting_equity=100_000, fraction_of_window_remaining=0.9)
runner.chain_mod.fetch = lambda *a, **k: FakeChain()
runner.structures.enumerate_all = lambda snapshot, expiry: []
f_pair = Forecast("post_event_drift", "LOSER", 2.0, -0.0023, 0.045, 0.6, "wide drop", "declared:gradient",
                  {"last_close": 20.0, "event_date": EVENT_DATE, "expression": "pair_short_vs_iwm",
                   "hedged_vs_iwm": {"centre_3d": 0.00346, "t": 2.22}}, claim="direction")
st_p, v_p, snap, rej = runner.evaluate(FakeClient(), f_pair, state=state, expiry=EXPIRY, open_risk=0.0)
kinds_seen = {x.kind for x, _ in rej} | ({st_p.kind} if st_p else set())
check("the pair is enumerated", "pair_short_vs_iwm" in kinds_seen, str(kinds_seen))
check("short_shares is NOT enumerated for a pair forecast", "short_shares" not in kinds_seen, str(kinds_seen))
f_plain = Forecast("post_event_drift", "LOSER", 2.0, -0.0072, 0.03, 1.0, "mega drop", "declared:gradient",
                   {"last_close": 20.0, "event_date": EVENT_DATE}, claim="direction")
st_s, _, _, rej_s = runner.evaluate(FakeClient(), f_plain, state=state, expiry=EXPIRY, open_risk=0.0)
kinds_s = {x.kind for x, _ in rej_s} | ({st_s.kind} if st_s else set())
check("a plain DOWN forecast still enumerates short_shares, not the pair",
      "short_shares" in kinds_s and "pair_short_vs_iwm" not in kinds_s, str(kinds_s))

tmp = tempfile.mkdtemp(); ledger.LEDGER_DIR = __import__("pathlib").Path(tmp)
book.read = lambda client, **k: book.reconstruct(client.positions(), equity=100_000, account_role=None, rows=[])
runner.book_mod = book
# A wide hedged pair at -0.23% over 2 sessions is a small tilt; whether the
# sizer approves it is its business. Force a generous approval so the ORDER
# PATH is what this test exercises.
_real_size = runner.sizing.size
def _approve(structure, centre, sd, st_, **kw):
    v = _real_size(structure, centre, sd, st_, **kw)
    from dataclasses import replace
    return replace(v, approved=True, risk_fraction=0.02, reason="forced approval (order-path test)")
runner.sizing.size = _approve
try:
    cl = FakeClient()
    res = runner.run_pass(cl, [f_pair], expiry=EXPIRY, dry_run=False, now_et=NOW_ET)
    rows = ledger.read_all()
    sub = [r for r in rows if r["action"] == "submitted"]
    check("one pair submitted as two venue orders", res.submitted == 1 and len(cl.submitted) == 2, f"{res} / {len(cl.submitted)}")
    if len(cl.submitted) == 2:
        (d1, o1), (d2, o2) = cl.submitted
        check("both legs share the decision id with leg suffixes",
              d1.endswith(":leg1") and d2.endswith(":leg2") and d1[:-5] == d2[:-5], f"{d1} / {d2}")
        check("leg 1 is the short, leg 2 the IWM hedge", o1["side"] == "sell" and o1["symbol"] == "LOSER"
              and o2["side"] == "buy" and o2["symbol"] == "IWM")
        n_short = int(o1["qty"]); n_hedge = int(o2["qty"])
        check("hedge shares = round(units * ratio)", n_hedge == equity.hedge_shares(n_short, 20.0 / 300.0), f"{n_short} / {n_hedge}")
    check("the ledger row is ONE row, instrument pair, order dict with hedge_qty",
          len(sub) == 1 and sub[0]["instrument"] == "pair_short_vs_iwm" and sub[0]["order"].get("pair")
          and int(sub[0]["outcome"]["hedge_shares"]) == int(sub[0]["order"]["hedge_qty"]), str(sub[0]["order"] if sub else None)[:120])
    check("the row lands in the print's event node", sub and sub[0]["outcome"]["event_node"] == f"print:{EVENT_DATE}")

    # ---- leg 2 refused -> leg 1 undone
    print("\n-- leg 2 refused at the venue: leg 1 is cancelled and bought back")
    ledger.LEDGER_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
    cl2 = FakeClient(fail_leg2=True)
    res2 = runner.run_pass(cl2, [f_pair], expiry=EXPIRY, dry_run=False, now_et=NOW_ET)
    rows2 = ledger.read_all()
    flat = [r for r in rows2 if r["action"] == "pair_leg_failed_flattened"]
    check("nothing counted as submitted; one error", res2.submitted == 0 and res2.errors == 1, str(res2))
    check("leg 1 order cancelled", cl2.cancelled and cl2.cancelled[0].endswith(":leg1"), str(cl2.cancelled))
    check("filled short shares bought back BY COUNT", cl2.closed == [("LOSER", 40)], str(cl2.closed))
    check("the row says pair_leg_failed_flattened and why",
          len(flat) == 1 and "leg 2 (IWM) refused" in (flat[0].get("refusal_reason") or "") and "bought back 40" in flat[0]["refusal_reason"],
          (flat[0].get("refusal_reason") or "")[:120] if flat else "no row")
finally:
    runner.sizing.size = _real_size

# ------------------------------------------------------------- the book
print("\n-- book.reconstruct: a pair from a short share position and its hedge")
qty_s = int(sub[0]["order"]["qty"]) if sub else 100
qty_h = int(sub[0]["order"]["hedge_qty"]) if sub else 7
pos = [{"asset_class": "us_equity", "symbol": "LOSER", "qty": str(-qty_s), "cost_basis": str(-qty_s * 19.98),
        "avg_entry_price": "19.98", "unrealized_pl": "0", "unrealized_plpc": "0"},
       {"asset_class": "us_equity", "symbol": "IWM", "qty": str(qty_h + 3), "cost_basis": str((qty_h + 3) * 300.1),
        "avg_entry_price": "300.1", "unrealized_pl": "0", "unrealized_plpc": "0"}]
role = sub[0].get("account_role") if sub else None
b = book.reconstruct(pos, equity=100_000, account_role=role, rows=rows)
check("the pair row matches the short leg", len(b.structures) == 1 and b.structures[0].kind == "pair_short_vs_iwm", b.summary()[:120])
check("the book is NOT unbounded (the short is explained by the pair)", not b.unbounded)
check("the 3 extra IWM shares are an ordinary long residual, not the pair's",
      [(r.symbol, r.qty) for r in b.residuals] == [("IWM", 3.0)], str([(r.symbol, r.qty) for r in b.residuals]))
mlpu = float(sub[0]["max_loss_per_unit"]) if sub else 0.0
check("charged at the row's stress charge x short units", abs(b.max_loss_usd - (qty_s * mlpu + 3 * 300.1 * equity.MAX_LOSS_FRACTION)) < 1e-6,
      f"{b.max_loss_usd:.2f}")
b_partial = book.reconstruct([{**pos[0], "qty": str(-(qty_s // 2))}, pos[1]], equity=100_000, account_role=role, rows=rows)
check("a partial short fill still matches the pair (DAY limits fill partially)",
      len(b_partial.structures) == 1 and b_partial.structures[0].contracts == qty_s // 2 and not b_partial.unbounded)
b_orphan = book.reconstruct([pos[1]], equity=100_000, account_role=role, rows=rows)
check("hedge with no short -> long share residual, bounded", not b_orphan.structures and not b_orphan.unbounded)

# ------------------------------------------------------------- exits
print("\n-- exits: joint P&L, both legs leave, hedge never judged alone")
dl = "2026-09-04T15:00:00Z"
now = datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc)
if sub:
    sub[0]["ts_utc"] = "2026-08-28T15:05:00+00:00"
pairs = exits.live_pairs(rows, pos)
check("live_pairs finds the pair by its SHORT leg", len(pairs) == 1 and pairs[0]["short"] == "LOSER" and pairs[0]["hedge_shares"] == qty_h)
check("hedge_reserved reserves exactly the pair's IWM shares", exits.hedge_reserved(pairs) == {"IWM": qty_h})
pr = pairs[0]
check("inside everything -> hold both", not exits.evaluate(pos[0], deadline_utc=dl, now=now, rows=rows, pair=pr).close)
pr_loss = {**pr, "short_pos": {**pos[0], "unrealized_pl": str(-0.04 * qty_s * 19.98)},
           "hedge_pos": {**pos[1], "unrealized_pl": "0"}}
v = exits.evaluate(pos[0], deadline_utc=dl, now=now, rows=rows, pair=pr_loss)
check("joint -4% -> stop, close", v.close and "joint" in v.reason, v.reason[:80])
pr_hedged = {**pr, "short_pos": {**pos[0], "unrealized_pl": str(-0.04 * qty_s * 19.98)},
             "hedge_pos": {**pos[1], "unrealized_pl": str(0.04 * qty_s * 19.98 * (qty_h + 3) / qty_h)}}
check("the hedge's gain (pro-rated to the pair's share count) offsets the short's loss -> hold",
      not exits.evaluate(pos[0], deadline_utc=dl, now=now, rows=rows, pair=pr_hedged).close)
pr_no_hedge = {**pr, "hedge_pos": None}
v2 = exits.evaluate(pos[0], deadline_utc=dl, now=now, rows=rows, pair=pr_no_hedge)
check("short leg with its hedge gone -> immediate close", v2.close and v2.urgency == "immediate")
cl3 = FakeClient(positions=pos)
summ = {"closed": 0, "errors": 0, "actions": []}
sent = exits.close_pair_hedge(cl3, pr, "test", summ, dry_run=False)
check("close_pair_hedge closes the hedge BY COUNT, leaving the book's own IWM", sent and cl3.closed == [("IWM", qty_h)], str(cl3.closed))
orphan = [p for p in exits.live_pairs(rows, [pos[1]])]
check("a pair whose short is gone is reported with short_pos None (orphan hedge)",
      len(orphan) == 1 and orphan[0]["short_pos"] is None and orphan[0]["hedge_pos"] is not None)
check("entry row lookup sees the pair instrument for the short symbol",
      exits._entry_row_for_shares("LOSER", rows) is not None)

print("\n-- protect.ensure: no stop on the hedge shares, a stop on the rest")
class StopClient(FakeClient):
    def __init__(self, positions): super().__init__(positions); self.stops = []
    def submit_protective_stop(self, order): self.stops.append(order); return {"id": "stop-" + order["symbol"]}
sc = StopClient(pos)
summ_p = protect.ensure(sc, pos, dry_run=False, exclude_qty={"IWM": qty_h})
stop_syms = {(o["symbol"], int(o["qty"])) for o in sc.stops}
check("short leg gets its buy-stop", ("LOSER", qty_s) in stop_syms, str(stop_syms))
check("IWM stop covers only the 3 non-hedge shares", ("IWM", 3) in stop_syms, str(stop_syms))
sc2 = StopClient([pos[0], {**pos[1], "qty": str(qty_h)}])
protect.ensure(sc2, sc2.positions(), dry_run=False, exclude_qty={"IWM": qty_h})
check("an IWM position that is ENTIRELY hedge gets no stop", not any(o["symbol"] == "IWM" for o in sc2.stops), str([o["symbol"] for o in sc2.stops]))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
else:
    print("ALL PASS")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
