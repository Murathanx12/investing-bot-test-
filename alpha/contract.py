"""The strategy contract a book must state BEFORE it trades, and the exit code reads.

WHY THIS FILE EXISTS
====================
Until tonight every share position in the fleet was closed at -3% or +2.5% with
no minimum holding time, and the "horizon" the exit pass used was `horizon_days`
copied off the forecast -- which for the tracker books was the sessions left in
a competition window, not the sessions the thesis needs. The consequence is
measured, not feared: **60% of the fleet's round trips finished in the same
session they opened** (S39 verification), on books whose sealed thesis is a
21-session revision drift. A book that cannot hold a position for a day cannot
express a 21-session idea, and every number it produces grades the exit rule
rather than the idea.

So a book now states four things before it trades, and `alpha/exits.py` obeys
them:

1. `expected_horizon_sessions` -- how long the thesis is supposed to take.
2. `min_normal_hold_sessions` -- the earliest a NORMAL exit is legal.
3. `hard_falsifiers` -- what would prove the thesis wrong (prose, graded later).
4. `risk_budget_usd` -- the dollars this book is allowed to lose on the name.

Plus `thesis_expiry` (the date after which the idea is stale even if nothing
moved) and `emergency_exit_reasons` (the typed list below).

BEFORE `min_normal_hold_sessions` A CLOSE NEEDS A TYPED REASON
==============================================================
Not "the price wiggled 3%". One of:

    THESIS_INVALIDATED        the thing the position was opened on stopped being true
    DATA_ERROR                the numbers that opened it were wrong
    HARD_RISK_LIMIT           the declared stop / risk budget, at the PROFILE width
    EXECUTION_CORRECTION      we hold something nothing declared, or a leg is missing
    DEADLINE                  a dated liquidation (contest, expiry, mandate end)
    EXPLICIT_EVENT_STRATEGY_EXIT   an event book whose contract says +N sessions IS the thesis

The enum is written to the ledger on every exit so the churn question -- "why
did this book not hold anything?" -- is answered by a `group by` instead of by
reading prose in 900 rows.

WHY THE STOP IS NOT AN EXCEPTION TO THE HOLD, AND STILL MOVES
=============================================================
`HARD_RISK_LIMIT` is always legal: a book that may not stop out is not safer,
it is unbounded. What changes is the WIDTH. `alpha/exits.py` charged a flat 3%
regardless of profile while `alpha/protect.py` placed the venue stop at the
profile width (8% basket, 6% maximum), so the exit pass pre-empted the stop the
book was actually sized against. On 2026-09-03 that flat 3% sat **0.52 sigma**
from the entry on a name whose own two-session sd was 5.75%, fired on a
ten-minute spike, and made the realised loss **2.25x** the mark at that
session's close (`docs/FINDING_2026-09-05_THE_MEGA11_EXEMPTION.md` 3a). A stop
inside the noise is a fee, not a stop -- `alpha/engine/equity.py` says exactly
that in its own comment and then kept 3% for the SAFE profiles.

WHAT THIS FILE DELIBERATELY DOES NOT DO
=======================================
It does not decide anything. It declares, validates and resolves. Selection
lives in the seal, sizing in the engine, closing in `exits.py`. A contract that
could also close a position would be a second exit rule, and the whole point is
that there is one.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

#: A close before `min_normal_hold_sessions` is legal ONLY for one of these.
#: Ordered most-binding first, which is also the order `exits.evaluate` checks.
EMERGENCY_EXIT_REASONS: tuple[str, ...] = (
    "DEADLINE",
    "EXECUTION_CORRECTION",
    "HARD_RISK_LIMIT",
    "DATA_ERROR",
    "THESIS_INVALIDATED",
    "EXPLICIT_EVENT_STRATEGY_EXIT",
)

#: Exits that are NORMAL -- legal only at or after the minimum hold.
NORMAL_EXIT_REASONS: tuple[str, ...] = ("HORIZON_SPENT", "PROFIT_TARGET", "THESIS_EXPIRED")

#: Every reason string the ledger may carry on an exit row.
EXIT_REASONS: tuple[str, ...] = EMERGENCY_EXIT_REASONS + NORMAL_EXIT_REASONS + ("HELD",)

REQUIRED_FIELDS: tuple[str, ...] = (
    "expected_horizon_sessions",
    "min_normal_hold_sessions",
    "thesis_expiry",
    "hard_falsifiers",
    "risk_budget_usd",
    "emergency_exit_reasons",
)


class ContractRefusal(Exception):
    """A book without a usable contract. Raised at SEAL time, never at trade time."""


@dataclass(frozen=True)
class Contract:
    """What a book promises about ONE position, frozen inside the seal's hash."""

    book: str
    expected_horizon_sessions: int
    min_normal_hold_sessions: int
    thesis_expiry: str                       # YYYY-MM-DD, inclusive
    hard_falsifiers: tuple[str, ...]
    risk_budget_usd: float
    emergency_exit_reasons: tuple[str, ...] = EMERGENCY_EXIT_REASONS
    #: None = this book has NO profit target. The tracker books do not: a
    #: +2.5% target on a 21-session revision thesis collects a day of noise and
    #: calls it the idea working.
    profit_target_frac: float | None = None
    #: None = use the book's risk profile width (`equity.stop_fraction`).
    stop_frac: float | None = None
    profile: str | None = None
    #: The 1:8 GUARD (`docs/FINDING_2026-09-05_THE_MEGA11_EXEMPTION.md` 3).
    #: Refuse an order whose claimed move in dollars is below this multiple of
    #: its own stop in dollars. None = MEASURED AND RECORDED, NOT ENFORCED.
    #:
    #: WHY IT IS NOT 3.0 EVERYWHERE, MEASURED RATHER THAN ASSUMED: the ratio is
    #: `|centre| / stop_fraction`, and the tracker books' own sealed numbers are
    #: an `exp_return` of ~1-3% against a 6-8% profile stop -- 0.2:1 to 0.4:1.
    #: A 3:1 floor therefore refuses ONE HUNDRED PERCENT of what those books
    #: select, which would empty the very accounts this build exists to fill.
    #: That is a finding about the books, not a reason to fudge the constant, so
    #: it is recorded on every admission and binds only where a mandate says so.
    #: Binding it on the tracker books is Murat's call, with the census in hand.
    min_edge_over_stop: float | None = None
    source: str = "declared"                 # declared | ledger | role_default

    def as_dict(self) -> dict:
        d = asdict(self)
        d["hard_falsifiers"] = list(self.hard_falsifiers)
        d["emergency_exit_reasons"] = list(self.emergency_exit_reasons)
        return d

    def stop_fraction(self) -> float:
        """The width `exits.py` charges. Profile first, flat default last."""
        if self.stop_frac is not None:
            return float(self.stop_frac)
        from alpha.engine import equity
        return equity.stop_fraction(self.profile)

    def expired(self, today: date) -> bool:
        try:
            return today > date.fromisoformat(self.thesis_expiry)
        except (TypeError, ValueError):
            return False


# --------------------------------------------------------------------- defaults

#: The books that trade the sealed tracker portfolio. Their thesis is a
#: multi-week revision/target drift, and 21/10 is the pair Murat approved on
#: 2026-09-05 (`docs/DECISIONS_2026-09-05_PLAIN_LANGUAGE.md` B.2).
TRACKER_BOOKS = ("hack3", "hack4", "hack6")

TRACKER_FALSIFIERS = (
    "the sealed ranking value for this name is no longer in the book's admitted set",
    "the analyst target that ranked it is withdrawn or cut below the entry price",
    "a delisting, halt or split makes the sealed price basis unreadable",
)

#: Event books measure a +1..+3 session drift; their horizon IS the thesis, so a
#: minimum hold of ten sessions would be a different strategy. They exit on
#: EXPLICIT_EVENT_STRATEGY_EXIT, which is typed and therefore countable.
EVENT_FALSIFIERS = (
    "the day-0 move is revised away by a restatement or a corrected print",
    "the drift window (+1..+3 sessions) closes with no continuation",
)


def defaults_for(book: str, *, profile: str | None = None) -> dict:
    """The contract shape a book gets when it does not declare one."""
    b = (book or "").strip().lower()
    if b in TRACKER_BOOKS:
        return {
            "expected_horizon_sessions": 21,
            "min_normal_hold_sessions": 10,
            "hard_falsifiers": TRACKER_FALSIFIERS,
            "profit_target_frac": None,
            # RECORDED, NOT ENFORCED on these books tonight -- see the field.
            "min_edge_over_stop": None,
            "profile": profile,
        }
    return {
        "expected_horizon_sessions": 3,
        "min_normal_hold_sessions": 0,
        "hard_falsifiers": EVENT_FALSIFIERS,
        "profit_target_frac": 0.025,
        # RECORDED here too, and BINDING only on the population the finding
        # actually indicts: a NAKED SHORT, where the stop is the only bound on
        # the loss (`admission.NAKED_SHORT_MIN_EDGE_OVER_STOP`). Measured before
        # this was written: at 3:1 a blanket floor refuses every order these
        # books can generate -- post_event_drift claims ~1% against a 3% stop,
        # 0.3:1 -- so binding it here would disarm the event books silently
        # while looking like a risk control. A book that WANTS the floor sets
        # this field; the census is on every admission either way.
        "min_edge_over_stop": None,
        "profile": profile,
    }


def sessions_ahead(start: date, n: int) -> date:
    """`n` weekday sessions after `start` (holidays ignored: the error is one
    session on a horizon of twenty-one, and a holiday calendar that is wrong is
    worse than one that is absent and said so)."""
    d, left = start, max(0, int(n))
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def for_book(book: str, *, day: str, risk_budget_usd: float,
             profile: str | None = None, **overrides) -> Contract:
    """The contract a book seals for `day`. `risk_budget_usd` is the dollars the
    book may lose on this name -- notional x stop width, computed by the caller
    that knows the equity, never guessed here."""
    d = defaults_for(book, profile=profile)
    d.update({k: v for k, v in overrides.items() if v is not None})
    start = date.fromisoformat(day)
    return Contract(
        book=book,
        expected_horizon_sessions=int(d["expected_horizon_sessions"]),
        min_normal_hold_sessions=int(d["min_normal_hold_sessions"]),
        thesis_expiry=str(d.get("thesis_expiry")
                          or sessions_ahead(start, int(d["expected_horizon_sessions"]))),
        hard_falsifiers=tuple(d["hard_falsifiers"]),
        risk_budget_usd=round(float(risk_budget_usd), 2),
        emergency_exit_reasons=EMERGENCY_EXIT_REASONS,
        profit_target_frac=d.get("profit_target_frac"),
        stop_frac=d.get("stop_frac"),
        profile=d.get("profile"),
        min_edge_over_stop=d.get("min_edge_over_stop"),
        source="declared",
    )


# ------------------------------------------------------------------ validation


def validate(payload: dict | None, *, where: str = "contract") -> list[str]:
    """Everything wrong with this contract, as prose. Empty list = usable.

    Returns rather than raises so a seal can report ALL of a book's problems in
    one pass instead of one per re-run."""
    if not isinstance(payload, dict) or not payload:
        return [f"{where}: absent. A book without a strategy contract may not be sealed "
                f"(fields: {', '.join(REQUIRED_FIELDS)})."]
    bad: list[str] = []
    for f in REQUIRED_FIELDS:
        if payload.get(f) is None:
            bad.append(f"{where}: `{f}` is missing.")
    if bad:
        return bad
    try:
        horizon = int(payload["expected_horizon_sessions"])
        hold = int(payload["min_normal_hold_sessions"])
    except (TypeError, ValueError):
        return [f"{where}: horizon/min-hold are not integers "
                f"({payload.get('expected_horizon_sessions')!r}/"
                f"{payload.get('min_normal_hold_sessions')!r})."]
    if horizon < 1:
        bad.append(f"{where}: `expected_horizon_sessions` = {horizon}; a thesis needs at least one session.")
    if hold < 0:
        bad.append(f"{where}: `min_normal_hold_sessions` = {hold}; negative is not a hold.")
    if hold > horizon:
        bad.append(f"{where}: minimum hold {hold} exceeds the horizon {horizon} -- "
                   "the book could never exit normally.")
    try:
        date.fromisoformat(str(payload["thesis_expiry"]))
    except ValueError:
        bad.append(f"{where}: `thesis_expiry` {payload['thesis_expiry']!r} is not a YYYY-MM-DD date.")
    if not list(payload.get("hard_falsifiers") or []):
        bad.append(f"{where}: `hard_falsifiers` is empty. A thesis nothing could refute is not a thesis.")
    try:
        if float(payload["risk_budget_usd"]) <= 0:
            bad.append(f"{where}: `risk_budget_usd` = {payload['risk_budget_usd']}; a zero risk budget "
                       "means the position may lose nothing, which no position can promise.")
    except (TypeError, ValueError):
        bad.append(f"{where}: `risk_budget_usd` {payload.get('risk_budget_usd')!r} is not a number.")
    unknown = [r for r in (payload.get("emergency_exit_reasons") or []) if r not in EMERGENCY_EXIT_REASONS]
    if unknown:
        bad.append(f"{where}: emergency reasons {unknown} are not in the enum {list(EMERGENCY_EXIT_REASONS)}.")
    if not list(payload.get("emergency_exit_reasons") or []):
        bad.append(f"{where}: `emergency_exit_reasons` is empty; a book that may never close early "
                   "cannot honour its own stop.")
    return bad


def require(payload: dict | None, *, where: str = "contract") -> None:
    bad = validate(payload, where=where)
    if bad:
        raise ContractRefusal(" ".join(bad))


def from_payload(payload: dict, *, book: str | None = None, source: str = "declared") -> Contract:
    """A `Contract` from a sealed/ledger dict. Assumes `validate` already passed."""
    return Contract(
        book=str(payload.get("book") or book or ""),
        expected_horizon_sessions=int(payload["expected_horizon_sessions"]),
        min_normal_hold_sessions=int(payload["min_normal_hold_sessions"]),
        thesis_expiry=str(payload["thesis_expiry"]),
        hard_falsifiers=tuple(payload.get("hard_falsifiers") or ()),
        risk_budget_usd=float(payload["risk_budget_usd"]),
        emergency_exit_reasons=tuple(payload.get("emergency_exit_reasons") or EMERGENCY_EXIT_REASONS),
        profit_target_frac=(None if payload.get("profit_target_frac") is None
                            else float(payload["profit_target_frac"])),
        stop_frac=(None if payload.get("stop_frac") is None else float(payload["stop_frac"])),
        profile=payload.get("profile"),
        min_edge_over_stop=(None if payload.get("min_edge_over_stop") is None
                            else float(payload["min_edge_over_stop"])),
        source=source,
    )


# -------------------------------------------------------------------- resolving


def role() -> str | None:
    r = (os.getenv("AAT_ACCOUNT_ROLE") or "").strip().lower()
    return r or None


def resolve(entry_row: dict | None, *, book: str | None = None,
            day: str | None = None, profile: str | None = None) -> Contract:
    """The contract governing a LIVE position, and where it came from.

    Order, and the reason for it:

    1. **The entry ledger row** (`outcome.contract`). This is the contract as it
       was at the decision, which is the only version that can grade the
       decision. A contract re-read from today's seal would let a re-seal
       silently re-write the terms of a position already on.
    2. **The role default** (`defaults_for`), stamped `source="role_default"`.
       Used for positions opened before contracts existed. It is a FALLBACK, not
       a silence: `exits.py` prints the source in the verdict, so a book still
       running on defaults says so on every pass.

    There is deliberately no third source. Refusing to exit a position whose
    contract cannot be read would convert a bookkeeping gap into an unbounded
    hold, and `HARD_RISK_LIMIT` has to keep working on exactly those positions.
    """
    b = (book or role() or "").strip().lower()
    payload = ((entry_row or {}).get("outcome") or {}).get("contract")
    if isinstance(payload, dict) and not validate(payload):
        return from_payload(payload, book=b or payload.get("book"), source="ledger")
    d = defaults_for(b, profile=profile)
    today = (day or datetime.now().date().isoformat())
    # A ROW THAT RECORDED ITS OWN HORIZON KEEPS IT. `outcome.horizon_days` is
    # what the forecast declared when the position opened, and for a position
    # opened before contracts existed that is a better answer than a role
    # default -- the role default is about the BOOK, this was about the TRADE.
    # The minimum hold is capped by it, because a hold longer than the horizon
    # is a position that can never exit normally.
    horizon = int(d["expected_horizon_sessions"])
    hold = int(d["min_normal_hold_sessions"])
    recorded = ((entry_row or {}).get("outcome") or {}).get("horizon_days")
    src = "role_default"
    try:
        if recorded is not None and float(recorded) >= 1:
            horizon = int(math.ceil(float(recorded)))
            hold = min(hold, horizon)
            src = "ledger_horizon_days"
    except (TypeError, ValueError):
        pass
    return Contract(
        book=b,
        expected_horizon_sessions=horizon,
        min_normal_hold_sessions=hold,
        thesis_expiry=str(sessions_ahead(date.fromisoformat(today), horizon)),
        hard_falsifiers=tuple(d["hard_falsifiers"]),
        #: Unknown, and said so rather than invented: the fallback path has no
        #: equity snapshot. `exits.py` never divides by it.
        risk_budget_usd=0.0,
        emergency_exit_reasons=EMERGENCY_EXIT_REASONS,
        profit_target_frac=d.get("profit_target_frac"),
        stop_frac=d.get("stop_frac"),
        profile=d.get("profile") or profile,
        min_edge_over_stop=d.get("min_edge_over_stop"),
        source=src,
    )
