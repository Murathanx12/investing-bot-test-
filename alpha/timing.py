"""WHEN and HOW an order may be sent -- split by INSTRUMENT, because Alpaca is.

THE BUG THIS MODULE EXISTS TO KILL
==================================
`scripts/competition_book` printed, as step 5 of the book:

    5. TIMING  enter MARKET-ON-CLOSE, not at the next open.

That instruction came from a real finding (`FINDING_..._ALL_OF_IT_HAPPENS_
OVERNIGHT.md`: the overnight segment compounded +17.31%/yr over CRSP 1993-2024
while intraday returned -7.26%). The finding is sound. The ORDER is not
placeable, and the book's own 70% core is the part that cannot place it:

  * Alpaca supports `time_in_force` of **`day` ONLY** for options, single-leg
    and multileg alike. `cls` and `opg` are rejected with
    "order_time_in_force provided not supported for options trading".
  * `cls`/`loc` exist for EQUITIES, but "CLS orders submitted after 3:50pm but
    before 7:00pm ET will be rejected."

So the book carried an instruction that would have been discovered at 15:50 ET
on a competition day, against the judged account, with no rehearsed fallback.

AND A SECOND, QUIETER PROBLEM
-----------------------------
The 3:50 cutoff means **the signal cannot be computed from the 16:00 close it
intends to trade.** An MOC order must be in the book ten minutes before the
price it fills at exists. Any design that reads today's close and sends today's
MOC is using information that did not exist when the order had to be submitted
-- the same lookahead the replay is careful to avoid, reintroduced by the
execution layer. `freeze_deadline_et` is that rule as code.

WHAT REPLACES THE ONE-LINE INSTRUCTION
--------------------------------------
    shares  -> MOC/LOC, but only if the signal was frozen before the cutoff
    options -> late-RTH MARKETABLE LIMIT, tif=day
    never   -> same-close information the order could not have seen
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

# --- venue facts, each with its source in the docstring above ---------------
OPTION_TIF = ("day",)
"""The COMPLETE set of time-in-force values Alpaca accepts for options."""

EQUITY_TIF = ("day", "gtc", "opg", "cls", "ioc", "fok")

CLS_CUTOFF_ET = time(15, 50)
"""CLS/LOC submitted after this and before 19:00 ET are REJECTED."""

OPG_CUTOFF_ET = time(9, 28)

SIGNAL_FREEZE_ET = time(15, 45)
"""A signal feeding an MOC order must be complete by here -- five minutes of
slack before the venue's own cutoff. Chosen, not measured: the point is that it
is STRICTLY BEFORE `CLS_CUTOFF_ET`, so the order can still be sent if the
computation runs long."""

OPTION_ENTRY_WINDOW_ET = (time(15, 30), time(15, 55))
"""When to work an option order if the intent is close-like exposure. Options
have no closing auction available to us, so 'as near the close as is safely
fillable' is the best available approximation of an MOC."""


class TimingRefusal(RuntimeError):
    pass


@dataclass(frozen=True)
class OrderTiming:
    instrument: str
    order_type: str
    time_in_force: str
    window_et: tuple[time, time] | None
    note: str


def entry_timing(instrument: str, *, signal_frozen_et: time | None,
                 want_close_exposure: bool = True) -> OrderTiming:
    """The placeable order for this instrument, or a refusal saying why not.

    `instrument` is "equity" or "option". `signal_frozen_et` is when the inputs
    to the decision stopped changing -- None means "not established", which is
    itself a refusal for anything auction-routed, because an unknown freeze time
    cannot be shown to precede the cutoff.
    """
    if instrument == "option":
        if want_close_exposure:
            return OrderTiming(
                instrument="option", order_type="limit", time_in_force="day",
                window_et=OPTION_ENTRY_WINDOW_ET,
                note=("options accept tif=day ONLY -- no cls, no opg. Close-like "
                      "exposure is approximated by a MARKETABLE LIMIT worked in "
                      f"{OPTION_ENTRY_WINDOW_ET[0]}-{OPTION_ENTRY_WINDOW_ET[1]} ET. "
                      "There is no closing auction for us here and pretending "
                      "otherwise is what produced an unplaceable book."))
        return OrderTiming("option", "limit", "day", None,
                           "options are tif=day; use a limit, never a market "
                           "order, on a spread whose quote can be 10% wide")

    if instrument != "equity":
        raise TimingRefusal(f"unknown instrument {instrument!r}")

    if not want_close_exposure:
        return OrderTiming("equity", "market", "day", None, "ordinary RTH entry")

    if signal_frozen_et is None:
        raise TimingRefusal(
            "MOC requested but the signal freeze time is not established. The "
            f"venue rejects CLS after {CLS_CUTOFF_ET} ET, so an order whose "
            "inputs may still be moving cannot be shown to be legal -- and a "
            "signal read off the 16:00 close could not have been in the book "
            "by 15:50 anyway. That is lookahead wearing an execution costume.")

    if signal_frozen_et > SIGNAL_FREEZE_ET:
        raise TimingRefusal(
            f"signal froze at {signal_frozen_et} ET, after the {SIGNAL_FREEZE_ET} "
            f"deadline (venue cutoff {CLS_CUTOFF_ET}). Use yesterday's close for "
            "today's MOC, or accept a next-open fill. Do NOT send it late.")

    return OrderTiming(
        instrument="equity", order_type="market", time_in_force="cls",
        window_et=(time(9, 30), CLS_CUTOFF_ET),
        note=("MOC is legal here: the signal froze before the cutoff. This is "
              "the only leg of the book that can capture the overnight segment "
              "the 32-year decomposition found (+17.31%/yr vs -7.26% intraday)."))


def marketable_limit(bid: float, ask: float, side: str,
                     aggression: float = 0.5) -> float:
    """A limit price that should fill, without paying the whole spread.

    `aggression` 0.0 rests at mid, 1.0 crosses fully to the far touch. The
    default gives up half the half-spread, which is what a resting order at the
    touch of a two-sided market usually costs anyway.

    Rounded to the cent, because an option limit that is not a valid tick is a
    rejection, and a rejection at 15:52 ET is a missed entry.
    """
    if not (bid > 0 and ask > 0 and ask >= bid):
        raise TimingRefusal(f"unusable quote bid={bid} ask={ask}; a structure "
                            "priced off a crossed or empty quote is not priced")
    mid = (bid + ask) / 2.0
    a = min(1.0, max(0.0, aggression))
    if side == "buy":                      # paying a debit: go UP toward the ask
        return round(mid + a * (ask - mid), 2)
    if side == "sell":                     # taking a credit: come DOWN to the bid
        return round(mid - a * (mid - bid), 2)
    raise TimingRefusal(f"side must be buy or sell, got {side!r}")


def validate_payload(payload: dict) -> list[str]:
    """Refusals for an order dict BEFORE it reaches the venue.

    This is the cheap half of the execution probe: everything that can be known
    without a broker round trip is known here, so a live rehearsal only has to
    test what genuinely needs the venue.
    """
    out: list[str] = []
    tif = str(payload.get("time_in_force") or "")
    is_opt = bool(payload.get("legs")) or _looks_like_occ(payload.get("symbol"))

    if is_opt and tif not in OPTION_TIF:
        out.append(f"time_in_force={tif!r} is not accepted for options; Alpaca "
                   f"permits {OPTION_TIF} only. This is the exact rejection the "
                   "book's 'enter MARKET-ON-CLOSE' instruction would have hit.")
    if not is_opt and tif and tif not in EQUITY_TIF:
        out.append(f"time_in_force={tif!r} is not a recognised equity TIF")
    if payload.get("legs") and payload.get("type") == "market":
        out.append("a multileg option order should be a LIMIT: a market order "
                   "on a spread whose quote is 10% wide is an unbounded fill")
    if payload.get("legs") and payload.get("type") == "limit" \
            and payload.get("limit_price") in (None, ""):
        out.append("limit order without a limit_price is rejected as "
                   "'limit price is required for limit orders'")
    return out


def _looks_like_occ(symbol) -> bool:
    s = str(symbol or "")
    return len(s) >= 15 and s[-8:].isdigit()
