"""THE ONE SPY CLOSE SOURCE. Every benchmark number in this repo comes through here.

    from alpha import spy
    closes = spy.daily_closes(client, start="2026-08-18")      # {ET date -> close}
    w      = spy.window(closes, genesis_day="2026-08-28", day="2026-09-04")

WHY THIS FILE EXISTS (B3, 2026-09-05)
=====================================
There were at least four independent SPY close readers, each with its own
window convention AND -- worse -- its own FEED:

  * `scripts/daily_learning_report.spy_window`  via `client.stock_bars`, which
    sends `feed=config.stock_feed()`;
  * `scripts/move_decomposition`                via `client.stock_bars_multi`,
    which defaults to `feed="sip"`;
  * `scripts/logic_brain`                       via `stock_bars_multi`;
  * `scripts/blind_tournament`                  via its own paged `/v2/stocks/bars`.

Two reports quoting "SPY" off two different tapes is the shape of the mistake
this repo has paid for repeatedly: two numbers that disagree, both correct
under their own unstated convention, and a reader who cannot tell which. The
consolidated tape is the right answer for a daily close (a daily bar built from
IEX alone is ~2-4% of the market's volume -- see `stock_bars_multi`'s own
docstring), so SIP is fixed here and stated, not inherited from whichever
helper a caller happened to reach for.

THE TWO CONVENTIONS, NAMED
==========================
* **A daily bar's `t` IS its ET session date.** Alpaca stamps daily bars at
  04:00Z, so `t[:10]` is the session, and converting it through a timezone
  would move it a day. This is NOT true of intraday bars or of order
  timestamps, where `alpha.exits.ET_OFFSET` is required -- the difference is
  the reason both rules are written down here.
* **The competition window** is the `state/benchmark_regret_*.json` receipt's
  own: the first daily bar ON OR AFTER the genesis kickoff date, to the report
  day's close. `window()` REFUSES (rather than sliding) when the report day has
  no bar, because a silently-substituted earlier close is a benchmark that
  flatters or punishes by an amount nobody named.

Read-only. Fetches bars and returns numbers; owns no state, writes no file.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: The benchmark. One symbol, one place.
SYMBOL = "SPY"

#: The consolidated tape, fixed. See the module docstring.
FEED = "sip"

#: What `window()` says when it will not answer.
CANNOT = "CANNOT DETERMINE"


def closes_from_bars(bars: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """`{ET session date -> close}` from a list of Alpaca DAILY bars.

    Pure: this is the half every caller can unit-test without a venue. A bar
    with no `c` or no `t` is skipped rather than defaulted -- a missing close
    is not a zero close.
    """
    out: dict[str, float] = {}
    for b in bars or []:
        t = str(b.get("t") or "")[:10]
        c = b.get("c")
        if not t or c is None:
            continue
        try:
            out[t] = float(c)
        except (TypeError, ValueError):
            continue
    return out


def daily_closes(client, *, start: str, end: str | None = None,
                 symbol: str = SYMBOL) -> dict[str, float]:
    """`{ET session date -> close}` for `symbol`, from the SIP tape.

    Uses `stock_bars_multi` on purpose: it is the transport that pins the feed
    and follows `next_page_token`, so a window longer than one page does not
    silently truncate at its far end -- which for a benchmark is the end that
    matters.
    """
    raw = client.stock_bars_multi([symbol], start=start, end=end,
                                  timeframe="1Day", adjustment="all", feed=FEED)
    return closes_from_bars((raw or {}).get(symbol) or [])


def window(closes: Mapping[str, float], *, genesis_day: str, day: str) -> dict:
    """The competition window and the day's own move, or a NAMED refusal.

    `closes` is whatever `daily_closes`/`closes_from_bars` returned. Keys are ET
    session dates; only string comparison is used, which is safe because they
    are ISO.
    """
    seq = sorted(closes.items())
    start = next(((d, c) for d, c in seq if d >= genesis_day), None)
    upto = [(d, c) for d, c in seq if d <= day]
    if not start or not upto:
        return {"status": CANNOT,
                "why": f"no {SYMBOL} bar on/after {genesis_day} or on/before {day}"}
    end_d, end_c = upto[-1]
    if end_d != day:
        return {"status": CANNOT,
                "why": f"no {SYMBOL} bar FOR {day} (latest at/under it is {end_d}) -- "
                       f"was {day} a session?"}
    prev = upto[-2] if len(upto) >= 2 else None
    out = {"status": "ok", "source": f"alpha.spy feed={FEED}",
           "start_date": start[0], "start_close": start[1],
           "end_date": end_d, "end_close": end_c,
           "return_pct": round((end_c / start[1] - 1) * 100, 3)}
    if prev:
        out["prev_date"], out["prev_close"] = prev
        out["day_return_pct"] = round((end_c / prev[1] - 1) * 100, 3)
    return out
