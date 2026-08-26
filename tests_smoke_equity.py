"""Smoke checks for the SHARES path (`alpha/engine/equity.py`). No keys, no network.

Run: python tests_smoke_equity.py  (also executed by tests_smoke.py)

The claim under test: a `direction` brain with a ~0.7% centre, integrated at the
CHAIN's width, clears the same gate in SHARES that it fails in every option --
against a post-print width. Against the pre-print width it clears nothing, in
shares either. The instrument changes; the gate does not.
"""
from __future__ import annotations

import math
import os
import tempfile
from datetime import datetime, timezone, timedelta

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


import importlib

from alpha import book, exits, ledger, runner
# Earlier suites replace `runner.evaluate` with fakes and never restore it.
runner = importlib.reload(runner)
from alpha.brains.base import Forecast
from alpha.engine import equity, payoff, sizing

print("\n-- equity.shares: a bounded structure from a stock quote")
s = equity.shares("NVDA", spot=180.0, bid=179.98, ask=180.02, direction="up",
                  implied_move=0.03, horizon_days=2.0, days_to_expiry=2.0)
check("long shares built", s is not None and s.kind == "long_shares")
check("max loss is the declared stop+gap", s is not None and abs(s.max_loss - 180.0 * 0.05) < 1e-9, f"{s.max_loss:.2f}")
check("break-even is one round trip", s is not None and abs(s.breakeven_move - 0.04 / 180.0) < 1e-12)
check("legs carry the equity symbol", s is not None and s.legs == (("NVDA", "buy", 1),))
sh = equity.shares("NVDA", spot=180.0, bid=179.98, ask=180.02, direction="down",
                   implied_move=0.03, horizon_days=2.0, days_to_expiry=2.0, shortable=False)
check("not shortable -> no short structure", sh is None)
sh = equity.shares("NVDA", spot=180.0, bid=179.98, ask=180.02, direction="down",
                   implied_move=0.03, horizon_days=2.0, days_to_expiry=2.0, shortable=True)
check("short shares: credit entry, sell leg", sh is not None and sh.entry_cost < 0 and sh.legs[0][1] == "sell")
w = equity.shares("NVDA", spot=180.0, bid=179.98, ask=180.02, direction="up",
                  implied_move=0.04, horizon_days=1.0, days_to_expiry=4.0)
check("chain width is NEVER scaled down to a shorter horizon (a jump has no sqrt(t))",
      w is not None and abs(w.implied_move - 0.04) < 1e-12, f"{w.implied_move:.4f}")
w2 = equity.shares("NVDA", spot=180.0, bid=179.98, ask=180.02, direction="up",
                   implied_move=0.02, horizon_days=4.0, days_to_expiry=1.0)
check("chain width scaled UP to a longer horizon (sqrt 4)", w2 is not None and abs(w2.implied_move - 0.04) < 1e-12, f"{w2.implied_move:.4f}")
live = equity.shares("NVDA", spot=212.96, bid=212.85, ask=213.07, direction="up",
                     implied_move=0.0510, horizon_days=2.0, days_to_expiry=2.6)
_st0 = sizing.TournamentState(equity=100_000, starting_equity=100_000, fraction_of_window_remaining=0.9)
_live_v = sizing.size(live, 0.0072, live.implied_move * math.sqrt(math.pi / 2), _st0)
check("the 26 Aug live case: pre-print 5.1% width, +0.72% centre -> REFUSED", not _live_v.approved, f"edge {_live_v.mdm_edge:+.1%}")

print("\n-- payoff: linear, one share per unit")
check("long share terminal P&L", abs(payoff.terminal_pnl(s, 180.0, 183.0) - (183.0 - 180.02)) < 1e-9)
check("short share terminal P&L", abs(payoff.terminal_pnl(sh, 180.0, 177.0) - (179.98 - 177.0)) < 1e-9)
check("liquidation at the bid, no x100", abs(payoff.liquidation_value(s, {"NVDA": {"bid": 181.0, "ask": 181.1}}) - 181.0) < 1e-9)
sigma_post = 0.03 * math.sqrt(math.pi / 2)
econ = payoff.economics(s, 180.0, 0.0072, sigma_post, horizon_days=None)
check("EV positive at +0.72% centre against a 3% chain width", econ.ev_usd > 0, f"EV ${econ.ev_usd:.2f}/share")
check("P(max loss) is the stop probability, small", 0.0 < econ.p_max_loss < 0.15, f"{econ.p_max_loss:.3f}")

print("\n-- the gate: same test, shares vs options, post- vs pre-print width")
state = sizing.TournamentState(equity=100_000, starting_equity=100_000, fraction_of_window_remaining=0.9)
post = sizing.size(s, 0.0072, sigma_post, state)
check("post-print width: shares clear the 5pp floor", post.approved, f"edge {post.mdm_edge:+.1%}")
sigma_pre = 0.054 * math.sqrt(math.pi / 2)
pre = sizing.size(s, 0.0072, sigma_pre, state)
check("pre-print width: shares are refused too (the honest measurement)", not pre.approved, f"edge {pre.mdm_edge:+.1%}")
# The option at the same width and centre: a 30-delta call breaking even at +4%.
call = sizing.Structure("NVDA260828C00185000", "long_call", direction="up", entry_cost=250.0, max_loss=250.0,
                        breakeven_move=0.04, implied_move=0.03, quote_spread_pct=0.08, days_to_expiry=2, legs=(("NVDA260828C00185000", "buy", 1),))
c = sizing.size(call, 0.0072, sigma_post, state)
check("the call at the same width does NOT clear", not c.approved, f"edge {c.mdm_edge:+.1%}")


class FakeChain:
    def __init__(self, spot=180.0, implied=0.03):
        self.underlying = "NVDA"; self.spot = spot; self.spot_source = "test"
        self.spot_ts = datetime.now(timezone.utc); self.feed = "test"; self.market_open = True
        self.median_quote_age_seconds = 0.0; self.contracts = []; self._implied = implied

    def implied_move(self, expiry): return self._implied
    def parity_gap(self, expiry): return None


class FakeClient:
    def __init__(self, positions=(), shortable=True, bid=179.98, ask=180.02):
        self._p = list(positions); self._short = shortable; self._q = (bid, ask)

    def account(self): return {"equity": "100000"}
    def positions(self): return self._p
    def clock(self): return {"is_open": True}
    def stock_quote(self, syms): return {"quotes": {syms[0]: {"bp": self._q[0], "ap": self._q[1], "bs": 5, "as": 5, "t": "now"}}}
    def asset(self, sym): return {"shortable": self._short, "easy_to_borrow": self._short, "tradable": True}
    def submit(self, order, *, decision_id, quote_snapshot): return {"id": "fake-" + decision_id}


print("\n-- runner.evaluate: shares enumerated beside the options for a direction brain")
runner.chain_mod.fetch = lambda *a, **k: FakeChain(implied=0.03)
runner.structures.enumerate_all = lambda snapshot, expiry: [call]
f_up = Forecast("post_event_drift", "NVDA", 2.0, 0.0072, 0.03, 1.0, "drift", "gradient",
                {"last_close": 180.0, "event_date": "2026-08-27"}, claim="direction")
st, v, snap, rej = runner.evaluate(FakeClient(), f_up, state=state, expiry="2026-08-28", open_risk=0.0)
check("champion is long_shares", st is not None and st.kind == "long_shares", getattr(st, "kind", v.reason[:80]))
check("verdict integrated at the chain's width", v.economics and v.economics.get("sd_source") == "chain_implied_move")
check("the call is in the rejected list", any(x.kind == "long_call" for x, _ in rej))
f_dn = Forecast("post_event_drift", "NVDA", 2.0, -0.0072, 0.03, 1.0, "drift", "gradient",
                {"last_close": 180.0, "event_date": "2026-08-27"}, claim="direction")
st_d, v_d, _, _ = runner.evaluate(FakeClient(), f_dn, state=state, expiry="2026-08-28", open_risk=0.0)
check("DOWN centre -> short_shares (the sign is spent)", st_d is not None and st_d.kind == "short_shares", getattr(st_d, "kind", v_d.reason[:80]))
st_ns, v_ns, _, _ = runner.evaluate(FakeClient(shortable=False), f_dn, state=state, expiry="2026-08-28", open_risk=0.0)
check("DOWN centre, not shortable -> nothing clears", st_ns is None, v_ns.reason[:80])
runner.chain_mod.fetch = lambda *a, **k: FakeChain(implied=0.054)
st_p, v_p, _, _ = runner.evaluate(FakeClient(), f_up, state=state, expiry="2026-08-28", open_risk=0.0)
check("pre-print chain width -> shares refused as well", st_p is None, v_p.reason[:90])
dist_f = Forecast("vol_gap", "NVDA", 2.0, 0.0, 0.03, 1.0, "quiet", "step", {"last_close": 180.0})
runner.chain_mod.fetch = lambda *a, **k: FakeChain(implied=0.03)
_, _, _, rej_dist = runner.evaluate(FakeClient(), dist_f, state=state, expiry="2026-08-28", open_risk=0.0)
check("a dispersion/distribution brain never sees a share structure", not any(x.kind in equity.KINDS for x, _ in rej_dist))

print("\n-- sizing to shares: notional cap, order payload")
n = runner.contracts_for(st, 0.08, 100_000.0)
check("share count capped at 25% notional", n == int(25_000 // 180.0), str(n))
n_small = runner.contracts_for(st, 0.005, 100_000.0)
check("small risk -> fewer shares than the cap", n_small == int(500 // 9.0), str(n_small))
o = runner.build_order(st, n)
check("equity order: limit at the ask, day, buy", o == {"symbol": "NVDA", "qty": str(n), "side": "buy", "type": "limit",
                                                         "limit_price": "180.02", "time_in_force": "day"}, str(o))
o_s = runner.build_order(st_d, 10)
check("short order: sell at the bid", o_s["side"] == "sell" and o_s["limit_price"] == "179.98", str(o_s))
qs = runner._quote_snapshot(st, snap)
check("quote snapshot carries the stock quote", qs["legs"] and qs["legs"][0]["symbol"] == "NVDA" and qs["parity_gap"] is None)
check("held_underlyings counts a share position", runner.held_underlyings(FakeClient([{"asset_class": "us_equity", "symbol": "NVDA", "qty": "10"}])) == {"NVDA": 1})
# The free feed's one-sided after-hours quote (measured: NVDA bid 200.45 / ask 0 vs trade 212.96).
st_syn, v_syn, snap_syn, _ = runner.evaluate(FakeClient(bid=200.45, ask=0.0), f_up, state=state, expiry="2026-08-28", open_risk=0.0)
check("one-sided quote -> synthetic quote around the last trade, labelled",
      st_syn is not None and st_syn.kind == "long_shares" and st_syn.quote["synthetic"] is not None
      and abs(st_syn.entry_cost - 180.0 * 1.0005) < 1e-9, str(getattr(st_syn, "quote", v_syn.reason[:60])))
st_far, _, _, _ = runner.evaluate(FakeClient(bid=185.0, ask=185.1), f_up, state=state, expiry="2026-08-28", open_risk=0.0)
check("two-sided but 2.8% off the trade -> also synthetic", st_far is not None and st_far.quote["synthetic"] is not None)

print("\n-- run_pass end to end (dry), and the book that results")
tmp = tempfile.mkdtemp(); ledger.LEDGER_DIR = __import__("pathlib").Path(tmp)
real_read = book.read
book.read = lambda client, **k: book.reconstruct(client.positions(), equity=100_000, account_role=None, rows=[])
runner.book_mod = book
res = runner.run_pass(FakeClient(), [f_up], expiry="2026-08-28", dry_run=False)
rows = ledger.read_all()
sub = [r for r in rows if r["action"] == "submitted"]
check("one share order submitted", res.submitted == 1 and len(sub) == 1 and sub[0]["instrument"] == "long_shares", str(res))
check("row carries claim and node", sub[0]["outcome"]["claim"] == "direction" and sub[0]["outcome"]["event_node"] == "print:2026-08-27")
qty = int(sub[0]["order"]["qty"])
pos = [{"asset_class": "us_equity", "symbol": "NVDA", "qty": str(qty), "cost_basis": str(qty * 180.02),
        "avg_entry_price": "180.02", "current_price": "181.0", "unrealized_plpc": "0.0054"}]
b = book.reconstruct(pos, equity=100_000, account_role=None, rows=rows)
check("book matches the share row", len(b.structures) == 1 and b.structures[0].kind == "long_shares", b.summary()[:100])
check("book charges shares at the declared stop+gap", abs(b.max_loss_usd - qty * 9.0) < 1e-6, f"{b.max_loss_usd:.0f} vs {qty * 9.0:.0f}")
check("node exposure carries the share risk", abs(b.by_node.get("print:2026-08-27", 0) - qty * 9.0) < 1e-6)
check("premium-paid view excludes shares", b.premium_paid_usd == 0.0)
res2 = runner.run_pass(FakeClient(pos), [f_up], expiry="2026-08-28", dry_run=False)
check("already positioned -> the next pass refuses", res2.submitted == 0 and res2.refused == 1)
b_orphan = book.reconstruct([{**pos[0], "qty": "-5"}], equity=100_000, account_role=None, rows=[])
check("unexplained SHORT shares -> book unbounded", b_orphan.unbounded)
b_long = book.reconstruct(pos, equity=100_000, account_role=None, rows=[])
check("unexplained LONG shares charged at 5%, bounded", not b_long.unbounded and abs(b_long.max_loss_usd - qty * 180.02 * 0.05) < 1e-6)

print("\n-- attribution: a share leg is all delta and does not crash")
from alpha import attribution
att = attribution.attribute_structure(b.structures[0], {"NVDA": pos[0]}, 181.0)
check("actual = qty * (mark - entry)", abs(att.actual_usd - qty * (181.0 - 180.02)) < 1e-6, f"{att.actual_usd:.2f}")
check("delta + spread = actual", abs(att.delta_usd + att.spread_usd - att.actual_usd) < 1e-6)
check("net delta in shares", abs(att.net_delta_shares - qty) < 1e-9)

print("\n-- exits: stop, target, horizon, orphan")
dl = "2026-09-04T15:00:00Z"
now = datetime(2026, 8, 28, 16, 0, tzinfo=timezone.utc)      # 12:00 ET, entry day
row_ts = sub[0]["ts_utc"]
sub[0]["ts_utc"] = "2026-08-28T15:05:00+00:00"
base = {"asset_class": "us_equity", "symbol": "NVDA", "qty": str(qty), "cost_basis": "1000", "unrealized_plpc": "0.0"}
check("inside everything -> hold", not exits.evaluate(base, deadline_utc=dl, now=now, rows=rows).close)
check("stop -3% -> close", exits.evaluate({**base, "unrealized_plpc": "-0.031"}, deadline_utc=dl, now=now, rows=rows).close)
check("target +2.5% -> close", exits.evaluate({**base, "unrealized_plpc": "0.026"}, deadline_utc=dl, now=now, rows=rows).close)
last_day_late = datetime(2026, 8, 31, 19, 50, tzinfo=timezone.utc)   # Mon 15:50 ET, session 2 of 2
v_h = exits.evaluate(base, deadline_utc=dl, now=last_day_late, rows=rows)
check("last session past 15:45 ET -> horizon spent, close", v_h.close and "drift window spent" in v_h.reason, v_h.reason[:80])
last_day_early = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)   # Mon 10:00 ET
check("last session, morning -> still holding", not exits.evaluate(base, deadline_utc=dl, now=last_day_early, rows=rows).close)
check("orphan shares with no row -> flattened", exits.evaluate(base, deadline_utc=dl, now=now, rows=[]).close)
check("deadline still outranks everything", exits.evaluate(base, deadline_utc=dl, now=datetime(2026, 9, 4, 14, 50, tzinfo=timezone.utc), rows=rows).urgency == "immediate")
sub[0]["ts_utc"] = row_ts
book.read = real_read

if __name__ == "__main__":
    print(f"\n{len(fails)} failures" + (": " + ", ".join(fails) if fails else ""))
    raise SystemExit(1 if fails else 0)
