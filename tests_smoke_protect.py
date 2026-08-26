"""The three day patches from the night execution audit, pinned.

Each check here corresponds to a confirmed defect in
`docs/night/2026-08-26_EXECUTION_AUDIT.md`, and each one is a behaviour that
looked fine in every existing test because the FAKE ACCOUNT was an incomplete
model of the venue: it had no `last_equity` and it never answered `/v2/orders`.
An absent order and an absent field are invisible in exactly the same way.

  1. protective stops exist AT THE VENUE and are cancelled before the close
  2. the daily-loss latch, and the sizer that used to lean into a drawdown
  3. a resting, unfilled order counts as held
"""
import os
import sys

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import daybreak, protect
from alpha.broker.alpaca import BrokerRefusal

LONG = {"asset_class": "us_equity", "symbol": "NVDA", "qty": "120",
        "avg_entry_price": "180.00", "cost_basis": "21600"}
SHORT = {"asset_class": "us_equity", "symbol": "HOV", "qty": "-50",
         "avg_entry_price": "10.00", "cost_basis": "-500"}
OPT = {"asset_class": "us_option", "symbol": "NVDA260828C00222500", "qty": "-10",
       "avg_entry_price": "2.25", "cost_basis": "-2250"}


class FakeClient:
    def __init__(self, positions=None, orders=None, reject=False):
        self._p = positions or []
        self._o = orders or []
        self.placed = []
        self.cancelled = []
        self.closed = []
        self.reject = reject

    def account(self):
        return {"equity": "100000", "last_equity": "100000"}

    def positions(self):
        return self._p

    def orders(self, status="open", limit=200):
        return list(self._o)

    def submit_protective_stop(self, order):
        if self.reject:
            raise BrokerRefusal("POST /v2/orders -> HTTP 422: stop price must be below the last trade")
        self.placed.append(order)
        oid = f"srv-{len(self.placed)}"
        self._o.append({**order, "id": oid, "status": "new"})
        return {"id": oid}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        self._o = [o for o in self._o if o.get("id") != order_id]

    def close_position(self, symbol, **kw):
        self.closed.append(symbol)
        return {}

    def latest_trade(self, symbols):
        return {"trades": {s: {"p": 180.0} for s in symbols}}


print("\n-- 1. protective stops at the venue")

c = FakeClient([LONG, SHORT, OPT])
s = protect.ensure(c)
by_symbol = {o["symbol"]: o for o in c.placed}
check("a long gets a SELL stop 3% under its entry", "NVDA" in by_symbol
      and by_symbol["NVDA"]["side"] == "sell" and by_symbol["NVDA"]["stop_price"] == "174.60",
      str(by_symbol.get("NVDA")))
check("a short gets a BUY stop 3% above its entry", "HOV" in by_symbol
      and by_symbol["HOV"]["side"] == "buy" and by_symbol["HOV"]["stop_price"] == "10.30",
      str(by_symbol.get("HOV")))
check("stops are GTC -- the hole was 16:00 to the next session's first pass",
      all(o["time_in_force"] == "gtc" for o in c.placed))
check("qty comes from the POSITION, not from an order", by_symbol["NVDA"]["qty"] == "120")
check("an OPTION leg gets no stop (exits closes structures, not legs)",
      "NVDA260828C00222500" not in by_symbol, str(list(by_symbol)))

before = len(c.placed)
protect.ensure(c)
check("ensure() is idempotent -- a second pass places nothing",
      len(c.placed) == before, f"{before} -> {len(c.placed)}")

# A partial fill that later completed: the resting stop covers less than the
# position, so it is cancelled and re-placed at the full size, never stacked.
c2 = FakeClient([{**LONG, "qty": "60"}])
protect.ensure(c2)
c2._p = [LONG]
s2 = protect.ensure(c2)
check("a grown position resizes its stop instead of stacking a second one",
      len(c2.cancelled) == 1 and len(c2.placed) == 2 and c2.placed[-1]["qty"] == "120",
      f"cancelled={c2.cancelled} qty={c2.placed[-1]['qty']}")

c3 = FakeClient([LONG], reject=True)
s3 = protect.ensure(c3)
check("a venue refusal is RECORDED, not retried into a loop",
      s3["refused"] and not s3["placed"], str(s3["refused"])[:60])

print("\n-- 2. the orphan sweep: a stop that outlives its position OPENS a short")

c4 = FakeClient([LONG])
protect.ensure(c4)
c4._p = []                      # position gone: manual close, liquidation, whatever
s4 = protect.ensure(c4)
check("a stop with no position is cancelled", s4["orphans"] and not c4._o,
      str(s4["orphans"]))

c5 = FakeClient([LONG], orders=[{"symbol": "NVDA", "id": "human-1",
                                 "client_order_id": "my-own-order", "status": "new"}])
protect.ensure(c5)
c5._p = []
s5 = protect.ensure(c5)
check("an order we did NOT place is never cancelled",
      "human-1" not in c5.cancelled, str(c5.cancelled))

print("\n-- 3. cancel BEFORE close, and refuse to close if the cancel fails")

from alpha import exits

c6 = FakeClient([LONG])
protect.ensure(c6)
n = protect.cancel_for(c6, "NVDA")
check("cancel_for cancels our stop on that symbol", n == 1 and len(c6.cancelled) == 1)


class StubbornClient(FakeClient):
    def cancel_order(self, order_id):
        raise BrokerRefusal("POST -> HTTP 500: venue unavailable")


c7 = StubbornClient([{**LONG, "unrealized_plpc": "-0.05"}])
protect.ensure(c7)
summary = exits.manage(c7, deadline_utc="2026-09-04T15:00:00Z", dry_run=False)
check("a position whose stop cannot be cancelled is NOT closed",
      not c7.closed and any(a[0] == "stop_cancel_failed" for a in summary["actions"]),
      f"closed={c7.closed}")

c8 = FakeClient([{**LONG, "unrealized_plpc": "-0.05"}])
protect.ensure(c8)
summary8 = exits.manage(c8, deadline_utc="2026-09-04T15:00:00Z", dry_run=False)
check("the ordinary path cancels the stop and THEN closes",
      c8.closed == ["NVDA"] and len(c8.cancelled) == 1,
      f"closed={c8.closed} cancelled={c8.cancelled}")

print("\n-- 4. the daily-loss latch")

check("flat day -> not latched", not daybreak.read(FakeClient()).latched)


class DownClient(FakeClient):
    def __init__(self, equity):
        super().__init__()
        self._eq = equity

    def account(self):
        return {"equity": str(self._eq), "last_equity": "100000"}


check("-2.9% -> not latched", not daybreak.read(DownClient(97_100)).latched,
      f"{daybreak.read(DownClient(97_100)).drawdown:+.2%}")
d = daybreak.read(DownClient(96_900))
check("-3.1% -> LATCHED", d.latched, f"{d.drawdown:+.2%}")
check("the latch says the number, not just 'refused'", "DAILY LOSS LATCH" in d.reason
      and "96,900" in d.reason, d.reason[:70])


class BlindClient(FakeClient):
    def account(self):
        return {"equity": "100000"}          # no last_equity


blind = daybreak.read(BlindClient())
check("a drawdown that CANNOT BE DETERMINED latches (fail-closed)",
      blind.latched and not blind.derived and "CANNOT DETERMINE" in blind.reason,
      blind.reason[:60])


class DeadClient(FakeClient):
    def account(self):
        raise BrokerRefusal("GET /v2/account -> HTTP 403")


check("an unreadable account latches rather than trading blind",
      daybreak.read(DeadClient()).latched)

print("\n-- 5. a resting, unfilled order counts as held")

from alpha import runner

c9 = FakeClient([], orders=[{"symbol": "NVDA", "id": "o1", "client_order_id": "aat-abc",
                             "status": "new"}])
flight = runner.open_order_underlyings(c9)
check("an unfilled entry limit makes its symbol held", flight.get("NVDA") == 1, str(flight))

c10 = FakeClient([LONG])
protect.ensure(c10)
check("our own protective stop does NOT block a re-entry",
      runner.open_order_underlyings(c10) == {}, str(runner.open_order_underlyings(c10)))

c11 = FakeClient([], orders=[{"id": "m1", "client_order_id": "aat-x", "status": "new",
                              "legs": [{"symbol": "NVDA260828C00222500"},
                                       {"symbol": "NVDA260828C00232500"}]}])
check("a multileg order's OCC legs resolve to the underlying",
      runner.open_order_underlyings(c11).get("NVDA") == 2,
      str(runner.open_order_underlyings(c11)))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
