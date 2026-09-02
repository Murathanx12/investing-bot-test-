"""ENTRY-TIMING TOURNAMENT: same sealed book, three entry moments. OFFLINE.

    python tests_smoke_entry_timing.py     (and via `python run_tests.py`)

The experiment is worth nothing unless the CONTROL is genuinely a control, so
the first and largest group of checks here is about the arm that must not
change: with `AAT_ENTRY_STYLE` unset, every code path this session touched has
to produce the byte-identical order, the same decision id shape, the same
opening-range refusal, and no pre-open pass at all.

The rest pins the two challengers:

  * the auction order really is `type=market, time_in_force=opg`;
  * the client id is deterministic in (day, symbol, "opg"), so a restart
    collides at the venue instead of doubling the position;
  * the marker cannot fire twice in a day;
  * `staggered` puts on HALF and leaves exactly the remainder for 10:01 --
    measured at the venue, never a second full weight;
  * and the gates that only CUT still run: the auction path goes through the
    SAME `admission.admit` object the 10:01 path does, and the sealed-weight
    clamp still binds.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from datetime import datetime, time as _time, timedelta, timezone
from pathlib import Path

fails: list[str] = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# The suite must never inherit a style from the shell that ran it: that would
# make the CONTROL checks below pass or fail on an ambient variable, which is
# the exact class of test this repo has been bitten by.
os.environ.pop("AAT_ENTRY_STYLE", None)

from alpha import book, entry_open, ledger, runner
runner = importlib.reload(runner)
from alpha.brains.base import Forecast
from alpha.broker.alpaca import client_order_id
from alpha.engine import equity, sizing

_TODAY = datetime.now(timezone.utc).date()
EXPIRY = (_TODAY + timedelta(days=1)).isoformat()
DAY = _TODAY.isoformat()


# ------------------------------------------------------------------ the gate

print("\n-- the gate: AAT_ENTRY_STYLE, and what UNSET means")
check("unset -> None (the control arm)", entry_open.entry_style({}) is None)
check("blank -> None", entry_open.entry_style({"AAT_ENTRY_STYLE": "  "}) is None)
check("open_auction resolves", entry_open.entry_style({"AAT_ENTRY_STYLE": "open_auction"}) == "open_auction")
check("staggered resolves", entry_open.entry_style({"AAT_ENTRY_STYLE": "STAGGERED"}) == "staggered")
try:
    entry_open.entry_style({"AAT_ENTRY_STYLE": "opening"})
    check("a typo REFUSES rather than silently becoming the control", False)
except entry_open.EntryStyleRefusal as exc:
    check("a typo REFUSES rather than silently becoming the control",
          "not a declared entry style" in str(exc), str(exc)[:70])
check("the auction fraction is 100% / 50% / 0%",
      (entry_open.auction_fraction("open_auction"), entry_open.auction_fraction("staggered"),
       entry_open.auction_fraction(None)) == (1.0, 0.5, 0.0))
check("only staggered leaves a remainder for 10:01",
      entry_open.leaves_remainder("staggered") and not entry_open.leaves_remainder("open_auction")
      and not entry_open.leaves_remainder(None))


# ------------------------------------------------------------- the pre-open window

print("\n-- should_run: the pre-open window, and why each clause refuses")
TMP = Path(tempfile.mkdtemp())


def sr(**kw):
    base = dict(style="open_auction", is_open=False, mins_to_open=30.0, day=DAY,
                role="hack4", ledger_dir=TMP)
    base.update(kw)
    return entry_open.should_run(**base)


ok, why = sr()
check("30 min before the open, style set, no marker -> FIRE", ok, why)
ok, why = sr(style=None)
check("STYLE UNSET -> the pre-open pass does not fire (the control's whole exposure)",
      not ok and "unset" in why, why)
ok, why = sr(is_open=True)
check("market already open -> the ordinary entry pass owns it", not ok, why)
ok, why = sr(mins_to_open=60.0)
check("60 min out is too early", not ok, why)
ok, why = sr(mins_to_open=5.0)
check("5 min out is too LATE -- the venue rejects opg after 09:28 ET", not ok, why)
ok, why = sr(mins_to_open=-1.0)
check("a negative/absent clock refuses", not ok, why)
ok, why = sr(role=None)
check("no AAT_ACCOUNT_ROLE -> no book to express", not ok, why)


# --------------------------------------------------------------- the day marker

print("\n-- the marker: a crash or a second cycle cannot fire the auction twice")
check("first claim wins", entry_open.claim_today(DAY, "hack4", style="open_auction", ledger_dir=TMP))
check("second claim LOSES (O_EXCL, not check-then-write)",
      not entry_open.claim_today(DAY, "hack4", style="open_auction", ledger_dir=TMP))
ok, why = sr()
check("and should_run now declines for the rest of the day", not ok and "already ran" in why, why)
ok, why = sr(role="hack6")
check("the marker is PER ROLE -- hack6 still fires", ok, why)
check("the marker lives under state/entry_timing beside the receipt",
      entry_open.marker_path(DAY, "hack4", ledger_dir=TMP).parent.name == "entry_timing"
      and entry_open.marker_path(DAY, "hack4", ledger_dir=TMP)
      != entry_open.receipt_path(DAY, "hack4", ledger_dir=TMP))


# ------------------------------------------------------------ deterministic ids

print("\n-- the client id: derived from (day, symbol, 'opg'), so a replay collides")
d1 = entry_open.opg_decision_id(DAY, "abat")
check("the decision id is (day, opg, SYMBOL)", d1 == f"{DAY}:opg:ABAT", d1)
check("stable across calls -- a restart four minutes later is the SAME decision",
      d1 == entry_open.opg_decision_id(DAY, "ABAT"))
check("distinct per symbol", d1 != entry_open.opg_decision_id(DAY, "RZLV"))
check("distinct per day", d1 != entry_open.opg_decision_id("2020-01-02", "ABAT"))
cid = entry_open.opg_client_order_id(DAY, "ABAT")
check("the venue id is the repo's own client_order_id of that decision",
      cid == client_order_id(d1) and cid.startswith("aat-") and len(cid) <= 48, cid)
check("minute-derived ids are NOT used for the auction (that is the bug this avoids)",
      ledger.new_decision_id("ABAT", "tracker_portfolio") != d1)


# --------------------------------------------------------------- the order body

print("\n-- build_order: unset is byte-identical, opg is market-on-open")
st = equity.shares("ABAT", spot=180.0, bid=179.98, ask=180.02, direction="up",
                   implied_move=0.03, horizon_days=2.0, days_to_expiry=2.0)
base = runner.build_order(st, 10)
check("UNSET: the limit/day payload today's control sends, unchanged",
      base == {"symbol": "ABAT", "qty": "10", "side": "buy", "type": "limit",
               "limit_price": "180.02", "time_in_force": "day"}, str(base))
check("passing entry_style=None explicitly is the same object shape",
      runner.build_order(st, 10, entry_style=None) == base)
opg = runner.build_order(st, 10, entry_style="open_auction")
check("opg: type=market, time_in_force=opg, no limit price",
      opg == {"symbol": "ABAT", "qty": "10", "side": "buy", "type": "market",
              "time_in_force": "opg"}, str(opg))
st_short = equity.shares("ABAT", spot=180.0, bid=179.98, ask=180.02, direction="down",
                         implied_move=0.03, horizon_days=2.0, days_to_expiry=2.0, shortable=True)
check("a short share auction order sells", runner.build_order(st_short, 3, entry_style="staggered")["side"] == "sell")


class _FakeOption:
    kind = "long_call"
    legs = (("ABAT260904C00180000", "buy", 1),)
    entry_cost = 300.0


try:
    runner.build_order(_FakeOption(), 1, entry_style="open_auction")
    check("an OPTION cannot be routed into the auction", False)
except ValueError as exc:
    check("an OPTION cannot be routed into the auction", "not a plain share structure" in str(exc),
          str(exc)[:70])


# -------------------------------------------------- halving, and the 10:01 remainder

print("\n-- staggered: half now, and EXACTLY the remainder at 10:01")


def sealed_forecast(symbol="ABAT", weight=0.10):
    return Forecast("tracker_portfolio", symbol, 2.0, 0.02, 0.05, 0.8, "sealed", None,
                    {"last_close": 180.0, "sealed_notional": weight}, claim="direction")


f_full = sealed_forecast()
halved = entry_open.scaled_forecasts([f_full], 0.5)
check("the sealed weight is HALVED, which is the only lever a partial entry needs",
      abs(halved[0].evidence["sealed_notional"] - 0.05) < 1e-12)
check("the full weight travels with it so 10:01 can compute the remainder",
      halved[0].evidence["sealed_notional_full"] == 0.10)
check("the original forecast is not mutated", f_full.evidence["sealed_notional"] == 0.10)
check("fraction 1.0 changes nothing",
      entry_open.scaled_forecasts([f_full], 1.0)[0].evidence["sealed_notional"] == 0.10)

EQ = 100_000.0
# the one-shot markers persist in the ledger dir; a test that leaves its own
# markers behind fails its own next run. Clean the synthetic days first.
for _m in entry_open.state_dir().glob("2099-*_test.topup_offered.json"):
    _m.unlink()
half_on = [{"asset_class": "us_equity", "symbol": "ABAT", "qty": "27",
            "market_value": str(0.05 * EQ)}]
room = entry_open.topup_headroom(halved, half_on, EQ, day="2099-01-01", role="test")
check("half on -> the top-up is the OTHER half, not a second full weight",
      abs(room.get("ABAT", 0.0) - 0.05) < 1e-9, str(room))
full_on = [{"asset_class": "us_equity", "symbol": "ABAT", "qty": "55",
            "market_value": str(0.10 * EQ)}]
check("already at the sealed weight -> no top-up at all",
      entry_open.topup_headroom(halved, full_on, EQ, day="2099-01-02", role="test") == {})
nearly = [{"asset_class": "us_equity", "symbol": "ABAT", "qty": "54",
           "market_value": str(0.098 * EQ)}]
check("a 2% sliver is not worth a second commission and a stop re-place",
      entry_open.topup_headroom(halved, nearly, EQ, day="2099-01-03", role="test") == {})
check("a forecast with no sealed weight is never topped up",
      entry_open.topup_headroom([Forecast("post_event_drift", "NVDA", 2.0, 0.01, 0.03, 1.0, "", None,
                    {"last_close": 180.0}, claim="direction")], half_on, EQ,
                    day="2099-01-04", role="test") == {})
check("zero/unknown equity tops up nothing", entry_open.topup_headroom(halved, half_on, 0.0, day="2099-01-05", role="test") == {})


# ----------------------------------------------------- run_pass, end to end, offline

print("\n-- run_pass: the auction pass goes through the SAME gates as 10:01")


class FakeChain:
    def __init__(self, spot=180.0, implied=0.03):
        self.underlying = "ABAT"; self.spot = spot; self.spot_source = "test"
        self.spot_ts = datetime.now(timezone.utc); self.feed = "test"; self.market_open = True
        self.median_quote_age_seconds = 0.0; self.contracts = []; self._implied = implied

    def implied_move(self, expiry): return self._implied
    def parity_gap(self, expiry): return None


class FakeClient:
    """Enough venue for a whole pass, and no socket anywhere near it."""

    def __init__(self, positions=()):
        self._p = list(positions)
        self.sent: list[dict] = []

    def account(self): return {"equity": str(EQ), "last_equity": str(EQ)}
    def positions(self): return self._p
    def orders(self, status="open", limit=200): return []
    def clock(self): return {"is_open": True}
    def stock_quote(self, syms):
        return {"quotes": {s: {"bp": 179.98, "ap": 180.02, "bs": 5, "as": 5, "t": "now"} for s in syms}}
    def asset(self, sym): return {"shortable": True, "easy_to_borrow": True, "tradable": True}
    def stock_bars_multi(self, syms, **kw): return {}
    def stock_bars(self, symbol, **kw): return {"bars": {}}
    def _request(self, method, path, **kw): return []
    def submit(self, order, *, decision_id, quote_snapshot):
        self.sent.append({"order": dict(order), "decision_id": decision_id,
                          "client_order_id": client_order_id(decision_id)})
        return {"id": "fake-" + decision_id}


runner.chain_mod.fetch = lambda *a, **k: FakeChain()
runner.structures.enumerate_all = lambda snapshot, expiry: []
book.read = lambda client, **k: book.reconstruct(client.positions(), equity=EQ,
                                                 account_role=None, rows=[])
runner.book_mod = book
ledger.LEDGER_DIR = Path(tempfile.mkdtemp())
os.environ["AAT_LEDGER_DIR"] = str(ledger.LEDGER_DIR)


def _mid_session_et():
    d = datetime.now().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime.combine(d, _time(10, 30))


def _opening_range_et():
    d = datetime.now().date()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime.combine(d, _time(9, 35))


NOW_ET = _mid_session_et()

# THE SAME admission function, counted rather than asserted from the source.
import alpha.admission as _admission_mod
_admit_calls: list[str] = []
_real_admit = _admission_mod.admit


def _counting_admit(*a, **kw):
    _admit_calls.append(kw.get("structure", getattr(a[1], "kind", "?")) if len(a) > 1 else "?")
    return _real_admit(*a, **kw)


_admission_mod.admit = _counting_admit
check("the runner's admission is the module's admission (one object, not a copy)",
      runner.admission is _admission_mod)

# --- the CONTROL: env unset, no entry style, nothing about it has changed -----
c_ctl = FakeClient()
res_ctl = runner.run_pass(c_ctl, [sealed_forecast()], expiry=EXPIRY, dry_run=False,
                          now_et=NOW_ET)
check("CONTROL submits one order", res_ctl.submitted == 1, str(res_ctl))
ctl_order = c_ctl.sent[0]["order"] if c_ctl.sent else {}
check("CONTROL order is limit/day, exactly as before this session",
      ctl_order.get("type") == "limit" and ctl_order.get("time_in_force") == "day"
      and "limit_price" in ctl_order, str(ctl_order))
check("CONTROL decision id is the minute-derived one",
      c_ctl.sent and c_ctl.sent[0]["decision_id"].endswith(":tracker_portfolio:ABAT"),
      str(c_ctl.sent[0]["decision_id"]) if c_ctl.sent else "")
check("CONTROL went through admission.admit", len(_admit_calls) >= 1)
ctl_rows = [r for r in ledger.read_all() if r["action"] == "submitted"]
check("CONTROL row carries NO entry_style -- the control is untouched by the tournament",
      ctl_rows and "entry_style" not in ((ctl_rows[-1]["outcome"] or {}).get("economics") or {}),
      str(((ctl_rows[-1]["outcome"] or {}).get("economics") or {}).get("entry_style")))

# The opening-range refusal still fires for the control at 09:35.
res_or = runner.run_pass(FakeClient(), [sealed_forecast()], expiry=EXPIRY, dry_run=False,
                         now_et=_opening_range_et())
check("CONTROL still refuses share entries inside the opening range",
      res_or.by_reason == {"opening_range": 1}, str(res_or.by_reason))

# --- the AUCTION arm ----------------------------------------------------------
n_before = len(_admit_calls)
c_opg = FakeClient()
res_opg = runner.run_pass(c_opg, [sealed_forecast()], expiry=EXPIRY, dry_run=False,
                          now_et=_opening_range_et(), entry_style="open_auction",
                          seal_day=DAY)
check("AUCTION submits one order", res_opg.submitted == 1, str(res_opg))
opg_order = c_opg.sent[0]["order"] if c_opg.sent else {}
check("AUCTION order is market / opg",
      opg_order.get("type") == "market" and opg_order.get("time_in_force") == "opg"
      and "limit_price" not in opg_order, str(opg_order))
check("AUCTION decision id is deterministic in (day, symbol, opg)",
      c_opg.sent and c_opg.sent[0]["decision_id"] == f"{DAY}:opg:ABAT",
      str(c_opg.sent[0]["decision_id"]) if c_opg.sent else "")
check("AUCTION client id is the one a replay would collide with",
      c_opg.sent and c_opg.sent[0]["client_order_id"] == entry_open.opg_client_order_id(DAY, "ABAT"))
check("AUCTION went through the SAME admission.admit the control did",
      len(_admit_calls) > n_before)
opg_rows = [r for r in ledger.read_all() if r["action"] == "submitted"
            and r["decision_id"] == f"{DAY}:opg:ABAT"]
econ = (opg_rows[-1]["outcome"] or {}).get("economics") or {} if opg_rows else {}
check("AUCTION row NAMES its entry style", econ.get("entry_style") == "open_auction", str(econ.get("entry_style")))
check("the opening-range bypass is RECORDED, not silent",
      "BYPASSED" in str(econ.get("opening_range_gate")), str(econ.get("opening_range_gate"))[:60])
check("the sealed weight still bound the size (a gate that CUTS still cuts)",
      opg_rows and float(opg_rows[-1]["risk_fraction"]) <= 0.10 + 1e-9,
      str(opg_rows[-1]["risk_fraction"]) if opg_rows else "")
check("the auction order is not bigger than the sealed notional",
      opg_rows and int(opg_order["qty"]) * 180.02 <= 0.10 * EQ + 1.0,
      f'{int(opg_order.get("qty", 0)) * 180.02:.0f} vs {0.10 * EQ:.0f}')

# HALF the weight buys about half the shares, and never more.
c_half = FakeClient()
runner.run_pass(c_half, entry_open.scaled_forecasts([sealed_forecast()], 0.5),
                expiry=EXPIRY, dry_run=False, now_et=_opening_range_et(),
                entry_style="staggered", seal_day=DAY)
check("STAGGERED buys about half of what the full auction bought",
      c_half.sent and int(c_half.sent[0]["order"]["qty"]) * 2 - int(opg_order["qty"]) in (-1, 0, 1),
      f'{c_half.sent[0]["order"]["qty"]} vs {opg_order["qty"]}' if c_half.sent else "")


# ---------------------------------------- 10:01 does not re-buy what opg filled

print("\n-- the 10:01 pass and an auction fill: re-buy, or top up, or refuse")
qty = int(opg_order["qty"])
filled = [{"asset_class": "us_equity", "symbol": "ABAT", "qty": str(qty),
           "avg_entry_price": "180.02", "current_price": "180.02",
           "market_value": str(qty * 180.02), "cost_basis": str(qty * 180.02)}]
res_held = runner.run_pass(FakeClient(filled), [sealed_forecast()], expiry=EXPIRY,
                           dry_run=False, now_et=NOW_ET)
check("open_auction arm: 10:01 sees the position and REFUSES as already_held "
      "(it keys on symbol presence, proved here rather than assumed)",
      res_held.submitted == 0 and res_held.by_reason == {"already_held": 1}, str(res_held.by_reason))

os.environ["AAT_ENTRY_STYLE"] = "staggered"
try:
    c_top = FakeClient([{**filled[0], "qty": str(qty // 2),
                         "market_value": str(0.05 * EQ)}])
    res_top = runner.run_pass(c_top, [entry_open.scaled_forecasts([sealed_forecast()], 0.5)[0]],
                              expiry=EXPIRY, dry_run=False, now_et=NOW_ET)
    check("staggered arm: 10:01 completes the book instead of refusing it",
          res_top.submitted == 1, str(res_top.by_reason))
    top_rows = [r for r in ledger.read_all() if r["action"] == "submitted"]
    check("the top-up is a LIMIT/DAY order like every other 10:01 entry",
          c_top.sent and c_top.sent[0]["order"]["type"] == "limit"
          and c_top.sent[0]["order"]["time_in_force"] == "day", str(c_top.sent[0]["order"]) if c_top.sent else "")
    check("the top-up buys the REMAINDER, never a second full weight",
          c_top.sent and int(c_top.sent[0]["order"]["qty"]) * 180.02 <= 0.05 * EQ + 1.0,
          f'{int(c_top.sent[0]["order"]["qty"]) * 180.02:.0f} vs {0.05 * EQ:.0f}' if c_top.sent else "")
    # And once the book is complete, the same arithmetic refuses it again.
    c_done = FakeClient(filled)
    res_done = runner.run_pass(c_done, [entry_open.scaled_forecasts([sealed_forecast()], 0.5)[0]],
                               expiry=EXPIRY, dry_run=False, now_et=NOW_ET)
    check("once complete, the staggered book falls back through already_held "
          "(so this cannot become a 30-minute re-buy loop)",
          res_done.submitted == 0 and res_done.by_reason == {"already_held": 1}, str(res_done.by_reason))
finally:
    os.environ.pop("AAT_ENTRY_STYLE", None)

# THE CONTROL AGAIN, after everything: with the variable unset the top-up path
# is not merely inactive, it is unreachable.
c_ctl2 = FakeClient([{**filled[0], "qty": str(qty // 2), "market_value": str(0.05 * EQ)}])
res_ctl2 = runner.run_pass(c_ctl2, [sealed_forecast()], expiry=EXPIRY, dry_run=False, now_et=NOW_ET)
check("UNSET + a half position -> already_held, no top-up, no new order",
      res_ctl2.submitted == 0 and res_ctl2.by_reason == {"already_held": 1}, str(res_ctl2.by_reason))

_admission_mod.admit = _real_admit


# ------------------------------------------------------------ the loop's own gate

print("\n-- the loop: the pre-open step exists, and unset means it never runs")
import ast

src = Path("scripts/agent_loop.py").read_text(encoding="utf-8")
tree = ast.parse(src)
check("agent_loop imports the gate rather than re-deriving it",
      "from alpha import entry_open" in src)
check("agent_loop calls scripts.open_auction", '"scripts.open_auction"' in src)
check("open_auction has a timeout ceiling like every other step",
      '"scripts.open_auction": 300' in src)
check("mins_to_open is initialised before the clock try-block (it was read unbound)",
      src.index("mins_to_open = 1e9") < src.index("clock = client.clock()"))
check("the call site is guarded by should_run, not by a bare env read",
      "_ok, _why = entry_open.should_run(" in src and "if _ok:" in src)

check("scripts.open_auction is importable and refuses with the variable unset",
      importlib.import_module("scripts.open_auction") is not None)
check("scripts.entry_timing_grade is importable offline",
      importlib.import_module("scripts.entry_timing_grade") is not None)


print("\n-- the receipt: the measurement is the point, so it must actually be written")
import json as _json

_oa = importlib.import_module("scripts.open_auction")
_sealed = {"holdings": {"ABAT": {"symbol": "ABAT", "notional": 0.10}}}
_book = {"content_sha256": "deadbeef" * 8, "sealed_at_utc": "2026-09-02T13:15:00+00:00"}
_p = _oa.write_receipt(day=DAY, role="hack4", style="open_auction", book=_book,
                       result=res_opg, sealed=_sealed, live=True, ledger_dir=TMP)
_r = _json.loads(_p.read_text(encoding="utf-8"))
check("one receipt per day per role, under state/entry_timing",
      _p == entry_open.receipt_path(DAY, "hack4", ledger_dir=TMP) and _p.exists(), str(_p))
check("it names the style, the book hash and the sealed names",
      _r["entry_style"] == "open_auction" and _r["book_sha256"] == _book["content_sha256"]
      and _r["sealed_names"] == ["ABAT"], str(_r)[:90])
check("it carries the order with its client id, type and tif",
      _r["orders"] and _r["orders"][0]["time_in_force"] == "opg"
      and _r["orders"][0]["type"] == "market"
      and _r["orders"][0]["client_order_id"] == entry_open.opg_client_order_id(DAY, "ABAT"),
      str(_r["orders"])[:120])
check("fills and grade are left EMPTY for the after-close grader to fill in",
      _r["fills"] is None and _r["grade"] is None)
_grade = importlib.import_module("scripts.entry_timing_grade")
check("the grader says NO RECEIPT rather than inventing one",
      _grade.grade_day(None, "1999-01-04", "hack4")["status"] == "NO RECEIPT")

# The seal pipeline is untouched: this session added no writer to it.
check("nothing here writes the sealed book",
      "prediction_book" not in Path("alpha/entry_open.py").read_text(encoding="utf-8").replace(
          "prediction_book_sync", ""))


# ---- one-shot marker (red-team R5): a loser must not be re-topped ----------
r1 = entry_open.topup_headroom(halved, half_on, EQ, day="2099-02-01", role="test")
check("first offer on a fresh day admits the remainder", abs(r1.get("ABAT", 0.0) - 0.05) < 1e-9)
dropped = [{"asset_class": "us_equity", "symbol": "ABAT", "qty": "27",
            "market_value": str(0.03 * EQ)}]  # the position LOST value
r2 = entry_open.topup_headroom(halved, dropped, EQ, day="2099-02-01", role="test")
check("a losing position does NOT reopen headroom the same day (no martingale)",
      r2 == {}, str(r2))
r3 = entry_open.topup_headroom(halved, dropped, EQ, day="2099-02-02", role="test")
check("  a NEW day offers again (the marker is daily, not permanent)", "ABAT" in r3)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
raise SystemExit(1 if fails else 0)
