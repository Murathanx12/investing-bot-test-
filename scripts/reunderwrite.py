"""CONTINUOUS_REUNDERWRITING -- would I open this position today, at this price?

    python -m scripts.reunderwrite

THE QUESTION THIS ASKS
======================
Entry gets almost all of this engine's attention. Money is also made by not
continuing to hold something that was right once. The daily question is not
"is this up or down", it is:

    If I held CASH instead of this position today, would I buy it at this price?

A position that no longer answers yes is being held by inertia, and inertia has
a cost: it is the `already_held` refusal. Two thirds of this engine's refusals
(32 of 48, measured 2026-08-26) are "we already own it" -- so every stale
position is not merely dead weight, it is **actively blocking the next idea.**

WHAT MAKES A THESIS STALE
=========================
Not P&L. A winner and a loser can both be finished. What ends a thesis:

  EVENT PASSED      the catalyst the structure was opened for has happened.
                    A long straddle bought for a print is, the morning after,
                    a decaying volatility position nobody chose.
  EXPIRY NEAR       remaining time is short relative to the thesis horizon.
  CAPITAL DEAD      the remaining max loss ties up capital while the remaining
                    upside no longer justifies it.

The first is the sharpest and the cheapest to check, because every row carries
its own `event_node` -- and an event node with a date in the past is an
objective fact, not a judgement.

WHAT THIS DOES NOT DO
=====================
It closes nothing and sizes nothing. It reports, and `exits.manage` remains the
only thing that acts. Reading is safe; deciding to exit on a stale thesis rather
than on a stop is a change to exit policy, and that is attended work.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from alpha import book as book_mod, config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def event_date_of(node: str | None) -> date | None:
    """`print:2026-08-27` -> the date. None when the node carries no date."""
    if not node:
        return None
    m = _DATE.search(str(node))
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def expiry_of(symbol: str) -> date | None:
    """OCC: AAPL260828C00200000 -> 2026-08-28."""
    m = re.match(r"^[A-Z]+(\d{2})(\d{2})(\d{2})[CP]\d{8}$", symbol or "")
    if not m:
        return None
    try:
        return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def earnings_dates(symbols: list[str], today: date) -> dict[str, date]:
    """Next/most recent earnings date per symbol, from Finnhub's calendar.

    Returns {} rather than guessing when the key or the call is unavailable --
    and the caller SAYS so, because "no event exposure found" and "could not
    look" print identically otherwise.
    """
    key = os.getenv("AAT_FINNHUB_API_KEY", "").strip()
    if not key or not symbols:
        return {}
    lo = (today - timedelta(days=21)).isoformat()
    hi = (today + timedelta(days=45)).isoformat()
    url = ("https://finnhub.io/api/v1/calendar/earnings?"
           + urllib.parse.urlencode({"from": lo, "to": hi, "token": key}))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
    except Exception:                                          # noqa: BLE001
        return {}
    want = set(symbols)
    out: dict[str, date] = {}
    for row in (data.get("earningsCalendar") or []):
        sym = row.get("symbol")
        if sym not in want or not row.get("date"):
            continue
        try:
            d = date.fromisoformat(row["date"])
        except ValueError:
            continue
        # keep the one closest to today, so a name with two rows in the window
        # is scored against the event that actually bounds the position
        if sym not in out or abs((d - today).days) < abs((out[sym] - today).days):
            out[sym] = d
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--asof", default=None, help="YYYY-MM-DD (default: today, UTC)")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    today = date.fromisoformat(args.asof) if args.asof else datetime.now(timezone.utc).date()

    b = book_mod.read(client)
    structures = list(getattr(b, "structures", []))
    if not structures:
        print("no matched structures -- nothing to re-underwrite.")
        return 0

    try:
        positions = {p["symbol"]: p for p in client.positions()}
    except BrokerRefusal as exc:
        print(f"REFUSED: {exc}")
        return 1

    equity = float(client.account().get("equity") or 0.0)
    syms = sorted({getattr(s, "symbol", "") for s in structures if getattr(s, "symbol", "")})
    earnings = earnings_dates(syms, today)
    if earnings:
        print("  earnings calendar: " + ", ".join(f"{k} {v}" for k, v in sorted(earnings.items())))
    else:
        print("  earnings calendar UNAVAILABLE -- untagged event exposure cannot be checked, "
              "which is not the same as there being none.")
    stale, live, exposed = [], [], []
    print(f"RE-UNDERWRITING  {len(structures)} structures, asof {today}\n")
    print(f"{'brain':20s} {'symbol':7s} {'kind':14s} {'risk $':>9s} {'mark $':>9s} "
          f"{'event':>12s} {'exp':>11s}  verdict")

    for s in structures:
        risk = float(getattr(s, "max_loss_per_unit", 0) or 0) * int(getattr(s, "contracts", 0) or 0)
        mark = 0.0
        for leg in getattr(s, "legs", []) or []:
            pos = positions.get(leg[0])
            if pos:
                mark += float(pos.get("market_value") or 0.0)
        ev = event_date_of(getattr(s, "event_node", None))
        exps = [e for e in (expiry_of(l[0]) for l in (getattr(s, "legs", []) or [])) if e]
        exp = min(exps) if exps else None
        dte = (exp - today).days if exp else None

        # EVENT EXPOSURE IS A FACT ABOUT THE UNDERLYING, NOT A TAG.
        # `vol_gap` opens volatility structures and assigns no event node, so
        # every row in this book reads `event: -` -- while two NVDA iron condors
        # sit short-vol into an earnings print. A structure whose underlying
        # reports before it expires is an event structure whoever opened it, and
        # scoring it off the tag alone made that invisible.
        # STALE and EVENT-EXPOSED are OPPOSITE conditions and must not share a
        # bucket. Stale means the thesis is finished and the capital is idle.
        # Event-exposed means the thesis is about to be decided and the capital
        # is at its most live. Calling the second "stale" would have reported
        # two NVDA condors sitting into tonight's print as dead weight.
        cal = earnings.get(getattr(s, "symbol", ""))
        stale_why, live_why = [], []
        if ev is not None and ev < today:
            stale_why.append(f"EVENT PASSED ({ev})")
        if cal and cal < today and (exp is None or today <= exp):
            stale_why.append(f"EVENT PASSED (untagged, reported {cal})")
        if dte is not None and dte <= 1:
            stale_why.append(f"EXPIRY IN {dte}d")
        if cal and today <= cal and (exp is None or cal <= exp):
            live_why.append(f"EVENT EXPOSED: reports {cal}, before expiry, UNTAGGED")
        verdict = "; ".join(stale_why + live_why) or "thesis live"
        if stale_why:
            stale.append((s, risk, verdict))
        else:
            live.append((s, risk, verdict))
            if live_why:
                exposed.append((s, risk, verdict))
        print(f"{str(getattr(s,'brain','')):20s} {str(getattr(s,'symbol','')):7s} "
              f"{str(getattr(s,'kind','')):14s} {risk:>9,.0f} {mark:>9,.0f} "
              f"{str(ev or '-'):>12s} {str(exp or '-'):>11s}  {verdict}")

    stale_risk = sum(r for _, r, _ in stale)
    live_risk = sum(r for _, r, _ in live)
    total = stale_risk + live_risk
    print(f"\n  thesis live   {len(live):>2d} structures  ${live_risk:>9,.0f} "
          f"({100*live_risk/total if total else 0:.1f}% of book risk)")
    print(f"  STALE         {len(stale):>2d} structures  ${stale_risk:>9,.0f} "
          f"({100*stale_risk/total if total else 0:.1f}% of book risk)")
    if equity:
        print(f"  stale capital as a share of equity: {100*stale_risk/equity:.1f}%")

    if exposed:
        exposed_risk = sum(r for _, r, _ in exposed)
        print(f"  EVENT EXPOSED {len(exposed):>2d} structures  ${exposed_risk:>9,.0f} "
              f"({100*exposed_risk/total if total else 0:.1f}% of book risk"
              + (f", {100*exposed_risk/equity:.1f}% of equity)" if equity else ")"))
        print("\n  Event-exposed is NOT stale -- the thesis is about to be decided, not finished.")
        print("  It is flagged because none of these carry an event node, so EVENT_NODE_CAP never")
        print("  saw them: the cap counts what brains TAG, and vol_gap tags nothing. Concentration")
        print("  into one scheduled event is exactly what that cap exists to prevent, and it was")
        print("  invisible to it.")
    if stale:
        print("\n  Every stale structure is capital that cannot take the next idea. Two thirds")
        print("  of this engine's refusals are already 'we already own it', so a position held")
        print("  past its thesis is not neutral -- it is the binding constraint.")
    elif not exposed:
        print("\n  No structure is past its event or its expiry. Nothing is held by inertia.")
    print("\n  (Reporting only. `exits.manage` remains the only thing that closes anything.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
