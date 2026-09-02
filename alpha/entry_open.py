"""ENTRY TIMING: the same sealed book, expressed at a different moment.

WHY THIS EXISTS (2026-09-02, session 35)
========================================
The three tracker books (`hack3`, `hack4`, `hack6`) trade the SAME artifact --
`state/predictions/<day>.json`, the exact holdings inside `content_sha256` --
and they differ in BREADTH (k=10 / k=5 / k=15). They do not differ in WHEN the
weight is put on: all three enter at the 10:01 ET pass, thirty-one minutes after
the bell, at whatever the tape has already done.

That is an untested constant, and it is the cheapest remaining experiment in the
book: the sealed names are identical, the weights are identical, the only thing
that varies is the entry expression. So:

    hack3   CONTROL      the 10:01 ET pass, unchanged, bit for bit
    hack4   CHALLENGER   the whole sealed weight as `opg` market-on-open
    hack6   CHALLENGER   half at `opg`, half at the ordinary 10:01 pass

THE GATE IS AN ENVIRONMENT VARIABLE, AND UNSET MEANS TODAY
==========================================================
`AAT_ENTRY_STYLE` is unset by default and every predicate in this module
returns the "do nothing new" answer when it is. The runners differ by
variables, never by image -- the same convention `AAT_LOOP_BRAINS` already
follows -- so hack3 keeps running the identical code path it ran yesterday and
its control arm stays a control arm.

An UNKNOWN value is a REFUSAL, not a fallback to the control. A typo in a
Railway variable that silently produced the control would make the tournament's
own arms unreadable, which is the one failure a tournament cannot survive.

WHAT THE OPENING AUCTION ACTUALLY IS
====================================
Alpaca accepts `time_in_force="opg"` with `type="market"` for the primary
listing exchange's opening auction, and REJECTS the order if it arrives after
09:28 ET. So the pre-open pass has a hard deadline that is not the bell, and
this module's window stops well short of it (`PRE_OPEN_WINDOW_MIN_MIN`) rather
than racing it: an order that arrives at 09:29 is rejected, and a book that
believed it had entered is worse than a book that knows it did not.

FAIL-CLOSED IN BOTH DIRECTIONS
==============================
The marker file is claimed BEFORE the orders are built, not after they are sent.
A crash mid-pass therefore costs the day's auction entry and the ordinary 10:01
pass buys the book instead -- the challenger degrades into the control, which is
the harmless direction. The other ordering (claim after sending) would let a
restart re-submit, and the only thing standing between that and a doubled
position is the venue's duplicate-client-id rejection. That rejection is the
BACKSTOP (`opg_decision_id` is derived from day+symbol+"opg", so a replay
collides), never the plan.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENV_VAR = "AAT_ENTRY_STYLE"

#: style -> the fraction of each sealed weight submitted into the OPENING AUCTION.
#: The remainder (if any) is left for the ordinary 10:01 ET pass to complete.
STYLES: dict[str, float] = {
    "open_auction": 1.0,
    "staggered": 0.5,
}

#: The pre-open pass may start this many minutes before the open, at the earliest.
PRE_OPEN_WINDOW_MAX_MIN = 45.0

#: ...and this many at the LATEST. Not zero, and not the venue's own 09:28
#: cutoff either: a pass that builds ~15 share structures makes tens of network
#: calls, so starting at 09:29 guarantees a rejected order and a book that
#: thinks it entered. Ten minutes leaves eight minutes of runway before the
#: cutoff. A container that comes up at 09:22 simply gets no auction entry that
#: day and enters at 10:01 like the control -- the harmless failure.
PRE_OPEN_WINDOW_MIN_MIN = 10.0

#: Below this fraction of the sealed weight, the 10:01 top-up for a STAGGERED
#: book is not worth a second commission and a second stop reconciliation.
MIN_TOPUP_FRACTION_OF_SEALED = 0.10


class EntryStyleRefusal(RuntimeError):
    """The declared entry style cannot be honoured, and says why."""


# --------------------------------------------------------------------- the gate

def entry_style(env: dict[str, str] | None = None) -> str | None:
    """The declared style, or None when the variable is unset (= today's behaviour).

    Raises on an unknown value. `env` is injectable so a test never has to
    mutate the process environment to prove the default.
    """
    raw = ((env if env is not None else os.environ).get(ENV_VAR) or "").strip().lower()
    if not raw:
        return None
    if raw not in STYLES:
        raise EntryStyleRefusal(
            f"{ENV_VAR}={raw!r} is not a declared entry style (have {sorted(STYLES)}). "
            "Refusing rather than falling back to the control: an arm that silently "
            "becomes the control makes the tournament unreadable.")
    return raw


def auction_fraction(style: str | None) -> float:
    """How much of each sealed weight goes into the opening auction. 0.0 when unset."""
    return 0.0 if style is None else STYLES[style]


def leaves_remainder(style: str | None) -> bool:
    """True when this style deliberately leaves weight for the 10:01 pass."""
    return style is not None and auction_fraction(style) < 1.0 - 1e-9


# ------------------------------------------------------------------ the window

def should_run(*, style: str | None, is_open: bool, mins_to_open: float,
               day: str, role: str | None,
               ledger_dir: str | Path | None = None) -> tuple[bool, str]:
    """Should the pre-open auction pass fire right now? Returns (yes, why).

    Every clause is supplied rather than read from a clock or an environment,
    because a guard whose value cannot be supplied is a guard that cannot be
    tested -- the lesson `runner.in_opening_range` paid for on a Saturday.
    """
    if style is None:
        return False, f"{ENV_VAR} unset: no pre-open pass (this is the control arm)"
    if is_open:
        return False, "the market is already open; the ordinary entry pass owns this"
    if not (PRE_OPEN_WINDOW_MIN_MIN <= float(mins_to_open) <= PRE_OPEN_WINDOW_MAX_MIN):
        return False, (f"{float(mins_to_open):.1f} min to the open is outside the pre-open "
                       f"window [{PRE_OPEN_WINDOW_MIN_MIN:.0f}, {PRE_OPEN_WINDOW_MAX_MIN:.0f}] "
                       f"-- the venue rejects `opg` after 09:28 ET")
    if not role:
        return False, "AAT_ACCOUNT_ROLE is unset; there is no book to express"
    marker = marker_path(day, role, ledger_dir=ledger_dir)
    if marker.exists():
        return False, f"already ran today: {marker}"
    return True, (f"{style}: {float(mins_to_open):.1f} min to the open, "
                  f"{auction_fraction(style):.0%} of each sealed weight into the auction")


# ------------------------------------------------------------------ the marker

def state_dir(ledger_dir: str | Path | None = None) -> Path:
    root = Path(ledger_dir or os.getenv("AAT_LEDGER_DIR") or "state")
    return root / "entry_timing"


def marker_path(day: str, role: str, *, ledger_dir: str | Path | None = None) -> Path:
    return state_dir(ledger_dir) / f"{day}_{role}.marker"


def receipt_path(day: str, role: str, *, ledger_dir: str | Path | None = None) -> Path:
    return state_dir(ledger_dir) / f"{day}_{role}.json"


def claim_today(day: str, role: str, *, style: str,
                ledger_dir: str | Path | None = None) -> bool:
    """Claim the day for this role. False when someone already had it.

    `O_EXCL`, not "check then write": two loop cycles a second apart, or a
    redeploy overlapping the old container, are exactly the race this exists to
    lose safely.
    """
    p = marker_path(day, role, ledger_dir=ledger_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"day": day, "role": role, "entry_style": style,
                          "claimed_utc": _now_iso(), "pid": os.getpid()})
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    return True


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- deterministic ids

def opg_decision_id(day: str, symbol: str) -> str:
    """The decision id for an opening-auction entry: (day, symbol, "opg").

    Deliberately NOT `ledger.new_decision_id`, whose minute component makes a
    restart four minutes later a DIFFERENT decision and therefore a second
    order. Here the decision is "this day's sealed weight in this name at the
    auction", which happens once however many times the container restarts.
    `broker.alpaca.client_order_id` hashes this into the venue-side id, and the
    venue rejects the duplicate.
    """
    return f"{day}:opg:{str(symbol).upper()}"


def opg_client_order_id(day: str, symbol: str) -> str:
    """The id the venue will see. Exposed so a receipt can be reconciled by hand."""
    from alpha.broker.alpaca import client_order_id
    return client_order_id(opg_decision_id(day, symbol))


# ------------------------------------------------------------- the sealed book

def verified_book(day: str) -> dict:
    """Today's sealed book, re-hashed. Raises when it is absent or edited.

    The hash algorithm is NOT re-implemented here: it is imported from the
    delivery path that already installs the book, so the two cannot drift into
    disagreeing about what "verified" means.
    """
    from alpha.brains import tracker_portfolio as _tp
    from scripts.prediction_book_sync import _canonical_sha

    payload = _tp._book_for(day)
    if payload is None:
        raise EntryStyleRefusal(
            f"no sealed book for {day}; the opening auction expresses a sealed book or "
            "nothing at all. Declining rather than re-deriving one before the bell.")
    if str(payload.get("day")) != str(day):
        raise EntryStyleRefusal(
            f"the sealed file found for {day} declares day={payload.get('day')!r}; "
            "refusing to trade yesterday's book at today's open.")
    _canonical_sha(payload)                     # raises ValueError on a mismatch
    return payload


# --------------------------------------------------- expressing a partial weight

def scaled_forecasts(forecasts: list, fraction: float) -> list:
    """Each sealed forecast with its `sealed_notional` cut to `fraction` of itself.

    This is the ONLY mechanism by which a staggered book puts on half a
    position, and it works because `sealing` already made the weight the single
    number every downstream layer reads: `sizing.size(sealed_notional=...)`
    sizes from it and `tracker_portfolio.clamp_to_sealed` caps at it. Cutting it
    here cuts both, coherently, and can only ever REDUCE.
    """
    if fraction >= 1.0 - 1e-9:
        return list(forecasts)
    if not (0.0 < fraction < 1.0):
        raise EntryStyleRefusal(f"auction fraction {fraction} is not in (0, 1]")
    out = []
    for f in forecasts:
        ev = dict(f.evidence or {})
        sealed = ev.get("sealed_notional")
        if sealed is None:
            out.append(f)
            continue
        ev["sealed_notional"] = float(sealed) * fraction
        ev["sealed_notional_full"] = float(sealed)
        ev["entry_style_fraction"] = fraction
        out.append(replace(f, evidence=ev))
    return out


def topup_headroom(forecasts: list, positions: list[dict[str, Any]],
                   equity: float) -> dict[str, float]:
    """{symbol: remaining sealed weight} for a STAGGERED book at the 10:01 pass.

    A book that put half its weight on at the auction is HELD in every one of
    those names, and `run_pass`'s one-position-per-symbol rule would refuse the
    second half forever -- turning "staggered" into "half-sized auction", which
    is a different experiment wearing the right label.

    So the remainder is admitted, and it is admitted as a HEADROOM, never as a
    fresh full weight: `sealed - what the venue says is already on`. The
    position is measured at the venue, not from our own bookkeeping, and a name
    whose headroom is below `MIN_TOPUP_FRACTION_OF_SEALED` of its sealed weight
    is left alone. Once the top-up fills, the headroom is ~0 and the name is
    refused again by this same arithmetic -- so this cannot become the 30-minute
    re-buy loop the original guard was written to stop.
    """
    if not equity or equity <= 0:
        return {}
    held_usd: dict[str, float] = {}
    for pos in positions or []:
        if (pos.get("asset_class") or "us_equity") != "us_equity":
            continue
        sym = str(pos.get("symbol") or "").upper()
        if not sym:
            continue
        mv = pos.get("market_value")
        if mv is None:
            qty = float(pos.get("qty") or 0.0)
            px = float(pos.get("current_price") or pos.get("avg_entry_price") or 0.0)
            mv = qty * px
        held_usd[sym] = held_usd.get(sym, 0.0) + abs(float(mv))
    out: dict[str, float] = {}
    for f in forecasts:
        sealed = (f.evidence or {}).get("sealed_notional")
        if sealed is None:
            continue
        sym = str(f.symbol).upper()
        full = float((f.evidence or {}).get("sealed_notional_full") or sealed)
        room = full - held_usd.get(sym, 0.0) / float(equity)
        if room >= MIN_TOPUP_FRACTION_OF_SEALED * full and room > 0:
            out[sym] = room
    return out


def with_sealed_notional(forecast, weight: float):
    """A copy of `forecast` whose sealed weight is `weight`. Used for the top-up."""
    ev = dict(forecast.evidence or {})
    ev["sealed_notional"] = float(weight)
    ev["entry_style_topup"] = True
    return replace(forecast, evidence=ev)
