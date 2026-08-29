"""P0.5 -- ORDER / STOP RECONCILIATION. Does the resting stop still describe
the position underneath it?

Run: python tests_smoke_stop_reconcile.py  (also executed by tests_smoke.py)

`alpha/protect.py` states the rule in its own docstring: *"sizing to the
order's qty rather than the fill's would over-sell a partial fill, and an
over-sold long is a short."* `ensure()` enforced that in ONE direction. It
compared `covered >= want_qty` and kept the resting stop when the inequality
held -- which is true not only when the stop matches, but also when the stop is
too BIG, when there are two of them, and when it is on the wrong SIDE entirely.
Each of those is the same accident the module exists to prevent:

  A. SIDE FLIP    -- a sell-stop resting under a position that is now SHORT.
                     It sells shares nobody holds: the short doubles.
  B. SHRINK       -- a x120 stop over a position reduced to 40. It sells 120
                     where 40 exist: an 80-share short in an account whose book
                     model says the name is flat.
  C. STACKED      -- two x60 stops on 60 shares. Either one is correct; BOTH
                     firing sells 120.
  D. RESTART      -- the loop restarts with no memory. `ensure()` must reach
                     the same book state from the venue alone, and reaching it
                     must not place a second stop.

The 28 Aug book stopped eleven names in twelve minutes. Every one of those
exits was a fill against a resting stop, and any of A-C would have turned an
exit into an entry on the wrong side.
"""
import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import protect
from alpha.broker.alpaca import BrokerRefusal

LONG = {"asset_class": "us_equity", "symbol": "NVDA", "qty": "120",
        "avg_entry_price": "180.00", "cost_basis": "21600"}


class FakeClient:
    def __init__(self, positions=None, orders=None, reject=False):
        self._p = list(positions or [])
        self._o = list(orders or [])
        self.placed = []
        self.cancelled = []
        self.reject = reject

    def account(self):
        return {"equity": "100000", "last_equity": "100000"}

    def positions(self):
        return list(self._p)

    def orders(self, status="open", limit=200):
        return list(self._o)

    def submit_protective_stop(self, order):
        if self.reject:
            raise BrokerRefusal("HTTP 422: stop price must be below the last trade")
        self.placed.append(order)
        oid = f"srv-{len(self.placed)}"
        self._o.append({**order, "id": oid, "status": "new"})
        return {"id": oid}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        self._o = [o for o in self._o if o.get("id") != order_id]

    def close_position(self, symbol, **kw):
        return {}


def resting(c, symbol="NVDA"):
    return [o for o in c.orders() if o.get("symbol") == symbol and protect.is_ours(o)]


print("\n-- A. SIDE FLIP: a sell-stop must never rest under a short position")
c = FakeClient([LONG])
protect.ensure(c)
check("the long is stopped with a SELL", resting(c)[0]["side"] == "sell")
# The position flips: the long was closed and a short opened in the same name
# (an over-sold exit, a reversal thesis, a manual trade -- the cause does not
# matter, the venue is the truth).
c._p = [{"asset_class": "us_equity", "symbol": "NVDA", "qty": "-120",
         "avg_entry_price": "175.00", "cost_basis": "-21000"}]
protect.ensure(c)
live = resting(c)
check("after the flip there is exactly ONE resting stop", len(live) == 1,
      str([(o["side"], o["qty"]) for o in live]))
check("and it is a BUY stop ABOVE the short's entry -- not the stale sell",
      live and live[0]["side"] == "buy" and float(live[0]["stop_price"]) > 175.0,
      str([(o["side"], o["stop_price"]) for o in live]))
check("the stale sell-stop was cancelled, not left resting", len(c.cancelled) == 1,
      str(c.cancelled))

print("\n-- B. SHRINK: a stop may never cover more shares than exist")
c = FakeClient([LONG])
protect.ensure(c)
c._p = [{**LONG, "qty": "40"}]                     # partial exit at the venue
protect.ensure(c)
live = resting(c)
covered = sum(int(float(o["qty"])) for o in live)
check("the resting stop is resized DOWN to the position", covered == 40,
      f"covered {covered} vs position 40")
check("exactly one stop rests after the resize", len(live) == 1, str(len(live)))
check("no phantom short: covered never exceeds the position", covered <= 40)

print("\n-- C. STACKED: two stops that each look sufficient are not sufficient")
# Two live stops, 60 each, against 120 shares. Summing them says 'covered'; the
# venue says 'two orders that will both fire'.
stacked = [
    {"id": "a", "symbol": "NVDA", "side": "sell", "qty": "60", "status": "new",
     "client_order_id": protect.STOP_PREFIX + "aaa"},
    {"id": "b", "symbol": "NVDA", "side": "sell", "qty": "60", "status": "new",
     "client_order_id": protect.STOP_PREFIX + "bbb"},
]
c = FakeClient([LONG], orders=list(stacked))
protect.ensure(c)
live = resting(c)
check("two stacked stops collapse to ONE", len(live) == 1,
      str([(o["id"], o["qty"]) for o in live]))
check("the survivor covers the whole position exactly",
      live and int(float(live[0]["qty"])) == 120, str(live[:1]))
check("both stale orders were cancelled", len(c.cancelled) == 2, str(c.cancelled))

print("\n-- D. RESTART: the venue is the only memory, and it is enough")
c = FakeClient([LONG])
protect.ensure(c)
placed_before, orders_snapshot = len(c.placed), list(c.orders())
# A fresh process: no local state at all, the same venue.
c2 = FakeClient([LONG], orders=orders_snapshot)
s = protect.ensure(c2)
check("a restart places nothing new", not c2.placed, str(c2.placed))
check("a restart cancels nothing", not c2.cancelled, str(c2.cancelled))
check("and it reports the stop as KEPT, so the pass is not silent",
      any("NVDA" in k for k in s["kept"]), str(s["kept"]))

print("\n-- the orphan sweep still runs first, and a human's order is untouched")
c = FakeClient([], orders=[
    {"id": "mine", "symbol": "NVDA", "side": "sell", "qty": "120", "status": "new",
     "client_order_id": protect.STOP_PREFIX + "ccc"},
    {"id": "theirs", "symbol": "NVDA", "side": "sell", "qty": "10", "status": "new",
     "client_order_id": "a-human-put-this-here"},
])
s = protect.ensure(c)
check("our orphan is cancelled", c.cancelled == ["mine"], str(c.cancelled))
check("an order we did not place is never touched",
      any(o.get("id") == "theirs" for o in c.orders()))

print("\n-- a refusal is still recorded rather than retried")
c = FakeClient([LONG], reject=True)
s = protect.ensure(c)
check("the venue's refusal lands in `refused` with its text",
      s["refused"] and "NVDA" in s["refused"][0], str(s["refused"]))
check("and nothing was placed", not c.placed)

print("\n-- dry_run changes nothing at the venue")
c = FakeClient([LONG], orders=list(stacked))
s = protect.ensure(c, dry_run=True)
check("dry_run cancels nothing", not c.cancelled, str(c.cancelled))
check("dry_run places nothing", not c.placed, str(c.placed))
check("but it still SAYS what it would have done", bool(s["placed"] or s["resized"]),
      str({k: v for k, v in s.items() if v}))

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
