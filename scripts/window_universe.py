"""WINDOW_UNIVERSE_v1 -- the names that will actually have an event inside the contest.

    python -m scripts.window_universe                 # plan the competition window
    python -m scripts.window_universe --json          # write state/window_universe.json
    python -m scripts.window_universe --check-chains  # also verify each name is optionable

WHY THIS EXISTS
===============
On 2026-08-27, with `vol_gap` quarantined and the two sigma-inflating brains on
shadow, a dry pass over the default universe produced **zero forecasts**. Every
line was `NotApplicable`:

    post_event_drift  META   20 sessions since the print on 2026-07-30
    event_move        NVDA   no scheduled print inside 2 days

The universe is a hardcoded list of fifteen mega-caps
(`scripts/run_pass.UNIVERSE`), and mega-caps report in the *last week of July*.
By late August they are all 19-25 sessions past their prints and the measured
drift window is +1..+3. So the agent was pointed at the one slice of the market
guaranteed to have no events during the contest.

A book that refuses everything scores zero, and **P&L is judging criterion #1**.
That is not a risk-management success; it is the same failure as a book that
loses money, arriving more quietly.

WHAT THE CALENDAR ACTUALLY SAYS
===============================
The window is not empty. It is BACK-LOADED, which changes the plan rather than
cancelling it:

    27 Aug amc   MRVL WDAY ADSK ULTA AFRM   -> drift lands 28, 31 Aug, 1 Sep
    28 Aug       nothing tradeable          -> DAY ONE OF THE CONTEST HAS NO PRINT
    31 Aug       SAIC ASO AEO               -> thin
    1  Sep       NIO MDT DLTR PANW MDB      -> drift 2-4 Sep
    2  Sep amc   AVGO HPE LULU NTAP SNOW    -> drift 3-4 Sep
    3  Sep       DELL CIEN ZS DOCU          -> drift 4 Sep only

Two consequences the hardcoded universe cannot express:

1. **MRVL prints tonight, so its drift window opens on day one.** It is not in
   the universe.
2. **AVGO on 2 Sep is the marquee event**, and it IS in the universe -- but the
   deadline is 11:00 ET on 4 Sep, so its +1..+3 drift has only two sessions to
   run and the third never arrives. A thesis whose horizon outruns the deadline
   is refused at selection here rather than discovered on the last morning.

THE DEADLINE IS A FILTER, NOT A FOOTNOTE
========================================
Every row reports `sessions_before_deadline`. A print AFTER the last tradeable
moment is listed and marked `TOO_LATE` rather than dropped, because "there were
no events" and "there were events we could not reach" are different sentences
and they call for different work.

Nothing here trades, sizes or orders. It reads a calendar and prints a plan.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.sources import finnhub

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")

#: The measured post-event drift window, in sessions after the print.
#: `alpha/brains/post_event_drift.py` -- +1..+3, spent after 3.
DRIFT_SESSIONS = (1, 3)

#: Revenue estimate floor, in dollars. A crude size proxy and named as one: it
#: is a filter for LIQUIDITY OF THE OPTION CHAIN, which is what actually decides
#: whether a thesis can be expressed, and revenue is a poor stand-in for it.
#: `--check-chains` replaces the proxy with the real thing.
MIN_REVENUE_ESTIMATE = 250_000_000

#: US market holidays inside any plausible window. Labor Day is 7 Sep 2026,
#: AFTER the contest, so the window has none -- stated rather than assumed.
HOLIDAYS: frozenset[date] = frozenset()


def sessions_between(a: date, b: date) -> int:
    """Trading sessions strictly after `a`, up to and including `b`."""
    if b <= a:
        return 0
    n, cur = 0, a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur not in HOLIDAYS:
            n += 1
    return n


def effective_print_date(day: date, hour: str) -> date:
    """The session the market first REACTS in.

    `amc` prints after the close, so the reaction is the NEXT session, and a
    drift window counted from the calendar date would be one session early on
    roughly half the calendar. `bmo` reacts the same day. A blank hour is
    treated as `amc`, the conservative direction: it delays the window rather
    than opening it before the information is public.
    """
    h = (hour or "").strip().lower()
    if h == "bmo":
        return day
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5 or nxt in HOLIDAYS:
        nxt += timedelta(days=1)
    return nxt


def plan(*, kickoff: date, deadline: date, lookback_days: int = 5) -> list[dict]:
    start = (kickoff - timedelta(days=lookback_days)).isoformat()
    end = (deadline + timedelta(days=2)).isoformat()
    rows = finnhub.earnings_calendar(start=start, end=end)

    out = []
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or "." in sym:                 # class shares quote badly and rarely
            continue
        rev = r.get("revenueEstimate")
        if not rev or float(rev) < MIN_REVENUE_ESTIMATE:
            continue
        try:
            day = date.fromisoformat(r["date"])
        except Exception:                                                  # noqa: BLE001
            continue
        react = effective_print_date(day, r.get("hour"))
        lo = react + timedelta(days=DRIFT_SESSIONS[0] - 1)
        # First and last session the drift is tradeable, skipping weekends.
        def _shift(d: date, n: int) -> date:
            cur, left = d, n
            while left > 0:
                cur += timedelta(days=1)
                if cur.weekday() < 5 and cur not in HOLIDAYS:
                    left -= 1
            return cur
        window_open = react
        window_close = _shift(react, DRIFT_SESSIONS[1] - DRIFT_SESSIONS[0])

        usable = max(0, min(sessions_between(react, deadline) + 1,
                            DRIFT_SESSIONS[1] - DRIFT_SESSIONS[0] + 1))
        if window_open > deadline:
            status = "TOO_LATE"
        elif window_close < kickoff:
            status = "BEFORE_KICKOFF"
        elif usable < (DRIFT_SESSIONS[1] - DRIFT_SESSIONS[0] + 1):
            status = "TRUNCATED_BY_DEADLINE"
        else:
            status = "FULL_WINDOW"
        out.append({
            "symbol": sym,
            "print_date": day.isoformat(),
            "hour": r.get("hour") or "unknown(treated amc)",
            "reacts_on": react.isoformat(),
            "drift_open": window_open.isoformat(),
            "drift_close": window_close.isoformat(),
            "usable_sessions": usable,
            "status": status,
            "revenue_estimate": float(rev),
            "eps_estimate": r.get("epsEstimate"),
        })
    out.sort(key=lambda x: (x["reacts_on"], -x["revenue_estimate"]))
    return out


def check_chain(symbol: str, expiry_hint: str) -> tuple[bool, str]:
    """Is there a quotable option chain? The only liquidity test that matters."""
    from alpha.broker.alpaca import AlpacaPaper
    from alpha.data import chain as chain_mod
    try:
        client = AlpacaPaper()
        snap = chain_mod.fetch(client, symbol, expiry_from=expiry_hint, expiry_to=expiry_hint)
        n = len(getattr(snap, "contracts", []) or [])
        return (n > 0), f"{n} contracts at {expiry_hint}"
    except Exception as exc:                                               # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:70]}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--check-chains", action="store_true",
                   help="verify each candidate has a quotable chain (slow, hits the venue)")
    p.add_argument("--expiry", default=None, help="expiry to test chains against")
    args = p.parse_args()
    config.load_env()

    kickoff = datetime.fromisoformat(
        config.COMPETITION["kickoff_utc"].replace("Z", "+00:00")).date()
    deadline = datetime.fromisoformat(
        config.COMPETITION["deadline_utc"].replace("Z", "+00:00")).date()

    rows = plan(kickoff=kickoff, deadline=deadline)
    print(f"WINDOW UNIVERSE  kickoff {kickoff}  deadline {deadline} "
          f"(11:00 ET, ninety minutes after the bell)")
    print(f"  drift window {DRIFT_SESSIONS[0]}..{DRIFT_SESSIONS[1]} sessions; "
          f"revenue-estimate floor ${MIN_REVENUE_ESTIMATE/1e6:,.0f}M as a LIQUIDITY PROXY")

    tradeable = [r for r in rows if r["status"] in ("FULL_WINDOW", "TRUNCATED_BY_DEADLINE")]
    print(f"\n  {len(rows)} sized prints in range, {len(tradeable)} with a drift window "
          "reaching inside the contest\n")
    print(f"  {'sym':<7}{'print':<12}{'hr':<5}{'reacts':<12}{'usable':>7}  status")
    for r in rows:
        mark = "  " if r["status"] in ("FULL_WINDOW", "TRUNCATED_BY_DEADLINE") else "x "
        print(f"  {mark}{r['symbol']:<5}{r['print_date']:<12}{r['hour'][:4]:<5}"
              f"{r['reacts_on']:<12}{r['usable_sessions']:>5}    {r['status']}")

    by_day: dict[str, list[str]] = {}
    for r in tradeable:
        by_day.setdefault(r["reacts_on"], []).append(r["symbol"])
    print("\n  UNIVERSE BY SESSION -- what to point `--universe` at each morning")
    for d in sorted(by_day):
        print(f"    {d}   {' '.join(by_day[d])}")
    if not by_day:
        print("    NOTHING. The contest window contains no sized print whose drift "
              "reaches it.")

    syms = sorted({r["symbol"] for r in tradeable})

    # THE VENUE DECIDES WHAT IS TRADEABLE, not the earnings calendar (2026-08-30).
    # `tradeable` above means "has a sized print whose drift reaches the window".
    # It never asked whether the name is still a listed equity, and on 2026-08-30
    # four of 98 were not: GES and GMS are `inactive, tradable=False` at Alpaca
    # (taken private / acquired), and SNBR and TPIC return HTTP 404 -- they are
    # not assets at all. Their SEC tickers are SNBRQ and TPICQ, and the Q is the
    # bankruptcy suffix; TPIC's newest filing is a 15-12G, which IS
    # deregistration. Nothing could ever have filled, so this cost no money.
    # What it cost was a universe count that did not mean what it said, and
    # quote calls spent enumerating structures on shells.
    #
    # ONE call, not one per name. A failure to reach the venue leaves the list
    # UNFILTERED and says so: refusing a whole universe because an asset lookup
    # timed out would turn a cosmetic check into an outage.
    dropped: list[str] = []
    try:
        from alpha import config as _cfg
        from alpha.broker.alpaca import AlpacaPaper

        _cfg.load_env()
        active = {str(a.get("symbol") or "").upper()
                  for a in (AlpacaPaper()._request(
                      "GET", "/v2/assets",
                      params={"status": "active", "asset_class": "us_equity"}) or [])
                  if a.get("tradable")}
        if active:
            dropped = [s for s in syms if s not in active]
            syms = [s for s in syms if s in active]
            for day, names in list(by_day.items()):
                by_day[day] = [n for n in names if n not in set(dropped)]
    except Exception as exc:                                            # noqa: BLE001
        print(f"\n  TRADABILITY UNCHECKED ({type(exc).__name__}: {str(exc)[:70]}). "
              "The list below is the calendar's answer, not the venue's.")

    print(f"\n  ALL {len(syms)}: {' '.join(syms)}")
    if dropped:
        print(f"  DROPPED {len(dropped)} not tradable at the venue: {' '.join(dropped)}")
        print("    (delisted, acquired or in bankruptcy -- a name the calendar knows and the "
              "venue does not is a fact about the company, not a feed gap)")

    if args.check_chains and syms:
        exp = args.expiry or (deadline.isoformat())
        print(f"\n  CHAIN CHECK at {exp} -- a name with no quotable chain cannot be "
              "expressed, whatever its thesis")
        for s in syms:
            ok, why = check_chain(s, exp)
            print(f"    {'ok ' if ok else 'NO '} {s:<6} {why}")

    if args.json:
        dest = STATE / "window_universe.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(
            {"kickoff": kickoff.isoformat(), "deadline": deadline.isoformat(),
             "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "drift_sessions": list(DRIFT_SESSIONS),
             "min_revenue_estimate": MIN_REVENUE_ESTIMATE,
             "by_session": by_day, "universe": syms, "rows": rows,
             # Named, not silently absent: a reader comparing this count against
             # the calendar's must be able to see where the difference went.
             "dropped_not_tradable": dropped}, indent=2) + "\n")
        print(f"\n  receipt: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
