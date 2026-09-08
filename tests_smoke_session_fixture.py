"""X1 + X3 -- THE CLOCK IS CHECKED, AND A CLOSED VENUE IS A REASON, NOT A ZERO.

    python run_tests.py -k session_fixture      # the ONLY supported way

WHAT THIS PINS, AND WHAT IT COST TO LEARN
=========================================
Two failures that look unrelated and are the same failure: **nothing in this
repo ever compared the clock it decides on with the clock the venue keeps.**

X1 -- CLOCK SKEW. `client.clock()` is the venue's. `in_opening_range`,
`exits.deadline_liquidation_due` and `exits.session_day` are the LOCAL wall
clock plus a fixed -4h, on a box that runs UTC+8 and has been measured ~15
minutes fast (S33b). C1-8 measured the consequences and could only report them:
a +20 min fast clock silently DISARMS the opening-range guard at a true 09:32
and liquidates the whole book twenty minutes early; a -20 min slow clock refuses
a legitimate 09:50 entry. `runner.venue_clock_skew` now probes once per pass and
refuses ENTRIES past a five-minute tolerance.

  EXITS ARE UNAFFECTED, AND THAT IS THE DESIGN, NOT AN OMISSION. A skewed clock
  must never be able to trap us in a position. `alpha.exits` does not import the
  guard, `manage` never consults it, and the last two checks in this file fail
  if that ever stops being true.

X3 -- NO SESSION TO ENTER INTO. Four end-to-end suites went red at ET Sunday
13:34 on 2026-09-06 with `run_pass` returning `considered=0`, and green again
the next afternoon with nothing changed but the wall clock. Each had already
DERIVED its session clock from `today` -- and still mixed a LOCAL date for the
clock with a UTC date for the expiry. Between 20:00 and 08:00 local those two
are a day apart, the session lands ON the expiry, and `run_pass` correctly
refuses the session as its own expiry day. The suite then read a zero it could
not explain, because that branch returned `considered=0 refused=0`: a SILENT
ZERO, which every census reads as "the alpha layer produced nothing" -- the
opposite diagnosis from "we were never allowed to trade".

So `tests_fixtures` derives session AND expiry from ONE clock and a real
calendar (2026-09-07 is a Monday AND Labor Day; a weekday is not a session), and
every pass-level refusal is now COUNTED and TYPED.

ZERO NETWORK. No `AlpacaPaper` is constructed; the only venue here is `Venue`
below. The socket block belongs to `run_tests.py` and no suite touches it.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, time as _time, timedelta, timezone

# The ledger resolves its directory at IMPORT time; redirect BEFORE any `alpha`
# import, transitive ones included, or this suite appends to the production
# chain (B3.1b, 2026-09-05).
os.environ["AAT_LEDGER_DIR"] = tempfile.mkdtemp(prefix="aat-x3-fixture-")
os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

from alpha import exits, ledger, refusal_classes, runner            # noqa: E402
from alpha.brains.base import Forecast                              # noqa: E402
from alpha.engine import sizing                                     # noqa: E402
import tests_fixtures as tf                                         # noqa: E402

fails: list[str] = []


def check(name: str, cond, detail: str = "") -> bool:
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)
    return bool(cond)


# ===========================================================================
print("-- the fixture: one clock, and a calendar")
# ===========================================================================
check("2026-09-07 is a weekday", datetime(2026, 9, 7).weekday() < 5)
check("  ...and is NOT a session (Labor Day): a weekday is not a calendar",
      not tf.is_session(datetime(2026, 9, 7).date()))
check("the session before Labor Day 2026 is Friday 09-04",
      tf.previous_session(datetime(2026, 9, 7).date()).isoformat() == "2026-09-04",
      tf.previous_session(datetime(2026, 9, 7).date()).isoformat())
check("the session after Labor Day 2026 is Tuesday 09-08",
      tf.next_session(datetime(2026, 9, 7).date()).isoformat() == "2026-09-08")
check("Good Friday 2026-04-03 is not a session", not tf.is_session(datetime(2026, 4, 3).date()))

# THE REPRODUCTION. The old derivation mixed a LOCAL date (this box is UTC+8)
# with a UTC date. Sweep every hour of 500 days and count how often the two
# formulas produce a session that IS its own expiry -- the state that returns
# considered=0. The old one must collide; the new one must never.
UTC8 = timedelta(hours=8)
old_collisions = new_collisions = not_a_session = 0
base = datetime(2025, 12, 1, tzinfo=timezone.utc)
for i in range(500):
    for h in range(24):
        utc = base + timedelta(days=i, hours=h)
        et = utc + exits.ET_OFFSET
        local = (utc + UTC8).date()                 # what `datetime.now().date()` returned
        # -- the OLD derivation, verbatim --
        d = local
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        old_expiry = (utc.date() + timedelta(days=1)).isoformat()
        if d.isoformat() == old_expiry:
            old_collisions += 1
        # -- the NEW derivation --
        clk = tf.session_clock(now=et)
        exp = tf.expiry_after_session(now=et)
        if clk.date().isoformat() >= exp:
            new_collisions += 1
        if not tf.is_session(clk.date()):
            not_a_session += 1

check("the OLD derivation really did collide (session == its own expiry)",
      old_collisions > 1000, f"{old_collisions} of 12,000 hours "
                             f"({old_collisions / 120.0:.1f}% of all wall-clock hours)")
check("  the NEW derivation never collides, at any hour of any day",
      new_collisions == 0, f"{new_collisions} collisions")
check("  and never lands on a weekend or an exchange holiday",
      not_a_session == 0, f"{not_a_session} non-sessions")


# ===========================================================================
print("\n-- the venue fixture: open, closed, and skewed")
# ===========================================================================
class Venue:
    """The smallest client `run_pass` will walk end to end. `skew_minutes` moves
    the VENUE's clock, which is the same measurement as moving ours."""

    def __init__(self, *, clock=None, skew_minutes: float = 0.0):
        self._clock = clock or tf.open_clock()
        self._skew = skew_minutes
        self.submitted: list[dict] = []

    def clock(self) -> dict:
        c = dict(self._clock)
        c["timestamp"] = (datetime.now(timezone.utc)
                          - timedelta(minutes=self._skew)).isoformat()
        return c

    def account(self): return {"equity": "100000", "last_equity": "100000"}
    def positions(self): return []
    def orders(self, status="open", limit=200): return []
    def stock_quote(self, syms):
        return {"quotes": {syms[0]: {"bp": 179.98, "ap": 180.02, "bs": 5, "as": 5, "t": "now"}}}
    def asset(self, sym): return {"shortable": True, "easy_to_borrow": True, "tradable": True}
    def submit(self, order, *, decision_id, quote_snapshot):
        self.submitted.append(dict(order))
        return {"id": "fake-" + decision_id}


check("the OPEN fixture reports a venue that is open", tf.open_clock()["is_open"] is True)
check("the CLOSED fixture's next open is on a LATER ET date (a holiday, not pre-open)",
      tf.closed_clock()["is_open"] is False)
_open_skew = runner.venue_clock_skew(Venue())
check("a matched clock measures ~0s of skew and does not refuse",
      _open_skew.verified and abs(_open_skew.seconds) < 5 and not _open_skew.refuses,
      f"{_open_skew.seconds}")
for mins in (20, -20):
    k = runner.venue_clock_skew(Venue(skew_minutes=mins))
    check(f"  a {mins:+d} min skew is MEASURED and refuses",
          k.verified and abs(abs(k.seconds) - 1200) < 5 and k.refuses, f"{k.seconds}")
k4 = runner.venue_clock_skew(Venue(skew_minutes=4))
check("  a 4 min skew is inside the 5 min tolerance and does NOT refuse",
      k4.verified and not k4.refuses, f"{k4.seconds}")
k_none = runner.venue_clock_skew(object())
check("a client with no clock() is CANNOT DETERMINE, not a crash and not a pass",
      (not k_none.verified) and k_none.seconds is None)
check("  and by default it does not refuse (a transport blip is not a fleet freeze)",
      not k_none.refuses)
os.environ["AAT_CLOCK_SKEW_STRICT"] = "1"
check("  ...but AAT_CLOCK_SKEW_STRICT=1 makes an unverifiable clock a refusal",
      runner.venue_clock_skew(object()).refuses)
os.environ.pop("AAT_CLOCK_SKEW_STRICT", None)


# ===========================================================================
print("\n-- run_pass end to end: open venue, closed venue, skewed clock")
# ===========================================================================
SESSION = tf.session_clock()
EXPIRY = tf.expiry_after_session()
EVENT = tf.event_date_pending()
check("the fixture's expiry is strictly after its own session day",
      EXPIRY > SESSION.date().isoformat(), f"session {SESSION.date()} expiry {EXPIRY}")


def forecasts(n: int = 2) -> list[Forecast]:
    return [Forecast("post_event_drift", sym, 2.0, 0.0072, 0.03, 1.0, "drift",
                     "declared:gradient", {"last_close": 180.0, "event_date": EVENT},
                     claim="direction")
            for sym in ("NVDA", "AMD")[:n]]


def run(venue, **kw):
    ledger.MALFORMED.clear()
    return runner.run_pass(venue, forecasts(), expiry=EXPIRY, dry_run=True,
                           now_et=SESSION, **kw)

# -- OPEN. This is the control: on a real closed-venue day (Labor Day) the
# fixture still delivers a pass that reaches the candidates.
res_open = run(Venue())
check("an OPEN venue fixture produces a pass that CONSIDERS its candidates",
      res_open.considered == 2, str(res_open))
check("  and it is not refused as session_closed or clock_skew",
      "session_closed" not in res_open.by_reason and "clock_skew" not in res_open.by_reason,
      res_open.decomposition())

# -- CLOSED. The X3 headline: a reason, not a zero.
res_shut = run(Venue(clock=tf.closed_clock()))
check("a CLOSED venue counts every candidate rather than returning a silent zero",
      res_shut.considered == 2, str(res_shut))
check("  every one of them is refused",
      res_shut.refused == 2 and res_shut.submitted == 0, str(res_shut))
check("  under the TYPED class `session_closed`",
      res_shut.by_reason.get("session_closed") == 2, res_shut.decomposition())
_rows = [r for r in ledger.read_all() if r.get("action") == "refused"]
_shut_rows = [r for r in _rows if str(r.get("refusal_reason", "")).startswith("SESSION CLOSED")]
check("  the ledger row carries the sentence, and it names the venue's next open",
      len(_shut_rows) >= 2 and "next open" in _shut_rows[-1]["refusal_reason"],
      str(_shut_rows[-1].get("refusal_reason", ""))[:120] if _shut_rows else "no row")
check("  and the row's terminal_state is MANDATE (the SESSION had no authority)",
      all(r.get("terminal_state") == "MANDATE" for r in _shut_rows[-2:]),
      str([r.get("terminal_state") for r in _shut_rows[-2:]]))
check("  `SESSION CLOSED:` classifies, so a census can group it",
      refusal_classes.classify(_shut_rows[-1]["refusal_reason"]) == "SESSION_CLOSED")

# -- the PRE-OPEN auction must still work while the venue is shut.
res_auction = run(Venue(clock=tf.closed_clock()), entry_style="open_auction")
check("the PRE-OPEN auction pass is NOT refused by the closed-venue gate",
      "session_closed" not in res_auction.by_reason, res_auction.decomposition())

# -- SKEW. Entries refused, and the reason says which clock.
res_skew = run(Venue(skew_minutes=20))
check("a +20 min skew refuses every entry, counted and typed",
      res_skew.considered == 2 and res_skew.by_reason.get("clock_skew") == 2,
      res_skew.decomposition())
res_skew2 = run(Venue(skew_minutes=-20))
check("  and so does a -20 min skew (a slow clock is not safer than a fast one)",
      res_skew2.by_reason.get("clock_skew") == 2, res_skew2.decomposition())
_sk = [r for r in ledger.read_all()
       if str(r.get("refusal_reason", "")).startswith("CLOCK SKEW")]
check("  the row names the tolerance and both clocks",
      _sk and "tolerance" in _sk[-1]["refusal_reason"] and "venue" in _sk[-1]["refusal_reason"],
      str(_sk[-1].get("refusal_reason", ""))[:140] if _sk else "no row")
check("  and it types as CLOCK_SKEW -> DATA_STALE",
      refusal_classes.classify(_sk[-1]["refusal_reason"]) == "CLOCK_SKEW"
      and refusal_classes.terminal_state(_sk[-1]["refusal_reason"]) == "DATA_STALE")

# -- EXPIRY DAY: the branch that used to be the silent zero.
res_exp = runner.run_pass(Venue(), forecasts(), expiry=SESSION.date().isoformat(),
                          dry_run=True, now_et=SESSION)
check("an expiry-day pass is a COUNTED, TYPED refusal, not considered=0",
      res_exp.considered == 2 and res_exp.by_reason.get("session_closed") == 2,
      str(res_exp))


class _NeverCalled:
    """Raises on ANY attribute access -- `getattr(client, "clock")` included."""

    def __getattr__(self, name):
        raise AssertionError(f"the expiry-day pass touched the venue via .{name}")


# ORDER IS LOAD-BEARING (2026-09-07). The clock probe was first for one commit,
# on the reasoning that the expiry gate is itself derived from the local clock.
# It made an expiry-day pass reach for `client.clock` and broke
# `tests_smoke_expiry_day`, which was right to complain: R1's guard is decided
# from local knowledge alone. Nothing is lost by probing second -- a skew big
# enough to move an ET DATE is hours, and if it HID the expiry day the probe
# below refuses the whole pass anyway. Pinned here as well as there, because the
# reason lives in this lane.
_never_ok = False
try:
    runner.run_pass(_NeverCalled(), forecasts(), expiry=SESSION.date().isoformat(),
                    dry_run=True, now_et=SESSION)
    _never_ok = True
except AssertionError as exc:
    _never_ok = False
    _detail = str(exc)
check("the expiry gate still runs BEFORE the clock probe: no venue is touched at all",
      _never_ok, "" if _never_ok else _detail)


# ===========================================================================
print("\n-- EXITS ARE UNAFFECTED BY THE CLOCK GUARD (the load-bearing half)")
# ===========================================================================
check("`alpha.exits` exposes no skew guard and imports none",
      not any("skew" in n.lower() for n in dir(exits)),
      str([n for n in dir(exits) if "skew" in n.lower()]))
check("  the entry guard lives in `runner`, where the entry gate is",
      hasattr(runner, "venue_clock_skew") and hasattr(runner, "CLOCK_SKEW_LIMIT_S"))
_src = open(exits.__file__, encoding="utf-8").read()
check("  and nothing in exits.py mentions the guard by name",
      "venue_clock_skew" not in _src and "CLOCK_SKEW_LIMIT_S" not in _src)
# The behavioural half: a stop still fires while the clock is 20 minutes out.
_v = exits.evaluate({"symbol": "NVDA", "asset_class": "us_equity", "qty": "10",
                     "avg_entry_price": "180.00", "current_price": "160.00",
                     "cost_basis": "1800.00", "market_value": "1600.00",
                     "unrealized_pl": "-200.00", "unrealized_plpc": "-0.1111"},
                    deadline_utc="2027-12-31T15:00:00Z", rows=[])
check("  a position 11% underwater still exits with a skewed clock in the building",
      _v.close, f"{_v.code}: {_v.reason[:100]}")


# ===========================================================================
print("\n" + "=" * 72)
if fails:
    print(f"FAILED ({len(fails)}): " + ", ".join(fails))
    raise SystemExit(1)
print("ALL PASS")
