"""ONE derivation of "a session clock and a venue that is open", for the suites.

    from tests_fixtures import session_clock, expiry_after_session, open_clock

WHY THIS FILE EXISTS (X3, 2026-09-07)
=====================================
Four end-to-end suites -- `tests_smoke`, `tests_smoke_equity`, `tests_smoke_pair`,
`tests_smoke_entry_timing` -- went red on 2026-09-06/07 with `run_pass` returning
`considered=0`, and green again the next morning with nothing changed but the
wall clock. Each of them had already done the obvious right thing and DERIVED its
mid-session clock from `today` instead of writing a literal date (CLAUDE.md rule
5, paid for by three literal option expiries). They still broke, and the reason
is the trap this repo is named after twice over:

    NOW_ET   = datetime.now().date()              <- LOCAL, and this box is UTC+8
    EXPIRY   = datetime.now(timezone.utc).date() + 1 day

Between 20:00 and 08:00 local, the LOCAL date is already tomorrow while the UTC
date is not. So `NOW_ET.date()` and `EXPIRY` land on the SAME day, `run_pass`
correctly refuses the whole session as its own expiry day (red-team R1: an entry
on the expiry session is churn into the judged window by construction), and the
suite reads a zero it cannot explain. It was ET Sunday 13:34 = local Monday 01:34
when the night lab hit it, and by Monday 18:00 local the two clocks agreed again
and the same code passed.

TWO RULES, AND BOTH OF THEM ARE THE POINT
  1. ONE CLOCK. Everything here is derived from `alpha.exits.now_et()`, which is
     UTC + the repo's single ET offset. Never `datetime.now()`, never a bare
     `date.today()`, never a UTC date compared against a local one.
  2. THE FIXTURE OWNS THE CALENDAR. A weekday is not a session: 2026-09-07 is a
     Monday AND Labor Day, and the venue is shut. `session_clock()` steps back to
     a real session; `expiry_after_session()` steps FORWARD past every weekend and
     holiday, so the expiry can never collide with the session the clock is on.

The holiday table is deliberately small and explicit rather than a dependency: it
covers the window these suites actually run in. A date outside it degrades to
"weekday = session", which is what the suites assumed before this file existed --
so an out-of-range year is never WORSE than the status quo, and `HOLIDAYS_COVER`
says out loud where the table stops.
"""
from __future__ import annotations

from datetime import date, datetime, time as _time, timedelta, timezone

from alpha import exits as _exits

__all__ = ["US_MARKET_HOLIDAYS", "HOLIDAYS_COVER", "is_session", "previous_session",
           "next_session", "session_clock", "expiry_after_session", "open_clock",
           "closed_clock"]

#: NYSE/Nasdaq full closures. Half-days (the 13:00 ET closes) are NOT here: a
#: half day IS a session and every gate in this repo behaves normally on one.
US_MARKET_HOLIDAYS: frozenset[date] = frozenset({
    # 2025
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
})

#: The years the table above is complete for. Outside it, `is_session` falls back
#: to "a weekday is a session" -- stated here rather than discovered by a suite
#: that goes red in 2028 for a reason nobody can see.
HOLIDAYS_COVER: tuple[int, int] = (2025, 2027)


def is_session(d: date) -> bool:
    """Is `d` a regular US equity session? Weekends and full closures are not."""
    return d.weekday() < 5 and d not in US_MARKET_HOLIDAYS


def previous_session(d: date, *, include_today: bool = True) -> date:
    """The latest session on or before `d` (or strictly before it)."""
    cur = d if include_today else d - timedelta(days=1)
    for _ in range(40):
        if is_session(cur):
            return cur
        cur -= timedelta(days=1)
    raise ValueError(f"no session found within 40 days before {d}")


def next_session(d: date, *, include_today: bool = False) -> date:
    """The earliest session on or after `d` (or strictly after it)."""
    cur = d if include_today else d + timedelta(days=1)
    for _ in range(40):
        if is_session(cur):
            return cur
        cur += timedelta(days=1)
    raise ValueError(f"no session found within 40 days after {d}")


def _today_et(now: datetime | None = None) -> date:
    """TODAY in ET, from the one clock. Not `datetime.now().date()`."""
    return (now or _exits.now_et()).date()


def session_clock(hour: int = 10, minute: int = 30, *, now: datetime | None = None) -> datetime:
    """A naive ET datetime on a REAL session at `hour:minute`.

    Naive on purpose: `run_pass(now_et=...)`, `in_opening_range` and
    `deadline_liquidation_due` all take a naive ET clock, and handing them an
    aware one compares an offset-naive to an offset-aware datetime."""
    return datetime.combine(previous_session(_today_et(now)), _time(hour, minute))


def expiry_after_session(now: datetime | None = None, *, sessions: int = 1) -> str:
    """An expiry (YYYY-MM-DD) strictly AFTER the day `session_clock` sits on.

    This is the half that was wrong. It is derived from the same session date as
    the clock -- not from a second, different clock -- so `run_pass`'s expiry-day
    gate can never fire on a fixture, at any hour of any day, in any timezone."""
    d = previous_session(_today_et(now))
    for _ in range(max(1, sessions)):
        d = next_session(d)
    return d.isoformat()


def event_date_pending(now: datetime | None = None) -> str:
    """An `event_date` that `run_pass` will actually treat as PENDING.

    Deliberately NOT `session_clock().date()`, and the difference is a real
    seam rather than a fixture convenience: `run_pass` builds its `printing`
    set with `d >= datetime.now(timezone.utc).date()` -- a UTC date -- while
    every other date in the pass is ET. The two differ for the four hours a day
    when UTC is already tomorrow, and they differ by three days whenever the
    latest SESSION is not today (a weekend, or Labor Day 2026-09-07). So the
    fixture's event has to clear whichever of the two is later, or "an event is
    pending" silently becomes false and the charge under test is never applied.

    (The seam itself is reported, not fixed here: changing which clock the
    entry pass reads pendingness off is a change to the live entry gate of six
    services, and this file is a test fixture.)"""
    ts = now or datetime.now(timezone.utc)
    return max(previous_session(_today_et(ts)), ts.date()).isoformat()


def open_clock(*, now: datetime | None = None) -> dict:
    """A `GET /v2/clock` payload for a venue that IS open, on a real session.

    `runner.venue_session_closed` and `runner.venue_clock_skew` both read this,
    so a fixture client that grows a `clock()` returning this is a venue that is
    open and a local clock with zero skew -- which is the state every end-to-end
    entry suite means to be testing, and which none of them could state before."""
    ts = now or datetime.now(timezone.utc)
    d = previous_session(_today_et(ts))
    return {
        "timestamp": ts.isoformat(),
        "is_open": True,
        "next_open": datetime.combine(next_session(d), _time(13, 30)).isoformat() + "+00:00",
        "next_close": datetime.combine(d, _time(20, 0)).isoformat() + "+00:00",
    }


def closed_clock(*, now: datetime | None = None) -> dict:
    """A `GET /v2/clock` payload for a day with NO session at all.

    The other half of X3: a closed venue must produce a TYPED REFUSAL with a
    reason, never `considered=0`. `next_open` is on a later ET date, which is
    what separates "shut for good today" from "shut, and opening in an hour"
    (the pre-open auction pass, which must keep working)."""
    ts = now or datetime.now(timezone.utc)
    d = _today_et(ts)
    return {
        "timestamp": ts.isoformat(),
        "is_open": False,
        "next_open": datetime.combine(next_session(d), _time(13, 30)).isoformat() + "+00:00",
        "next_close": datetime.combine(next_session(d), _time(20, 0)).isoformat() + "+00:00",
    }
