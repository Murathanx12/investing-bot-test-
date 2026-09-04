"""Closing positions -- the half of a trading agent that competitions expose.

WHY THIS IS NOT AN AFTERTHOUGHT
==============================
An agent that opens and never closes has a P&L determined entirely by expiry
mechanics, which for short-dated options means most positions go to zero and a
few go to whatever they happened to be worth on the third Friday. That is not a
strategy; it is a lottery with extra steps. It also fails judging criterion 1
while contradicting the "risk gates" section the rules require us to submit.

Five reasons to close, checked in this order, most binding first:

1. **THE DEADLINE.** Judging is at 11:00 ET on 4 September -- ninety minutes
   after the bell, not at a close. A position still open then is scored at
   whatever mark the venue happens to carry, which for a wide option is not a
   price anyone would pay. Everything is flat by `LIQUIDATE_BY_ET`, and this
   rule outranks every other consideration including a winning thesis.

2. **EXPIRY.** In-the-money contracts auto-exercise at $0.01, which on a paper
   account turns a $2,000 option position into a $70,000 stock position
   overnight and blows the risk budget without a single decision being made. We
   never hold through an expiry.

3. **PROFIT TARGET.** Asymmetric on purpose: long premium takes profit LATE
   (the whole reason to own convexity is the tail), short premium takes profit
   EARLY (the last 30% of a credit is the part where the risk/reward inverts --
   you are risking the width to earn pennies).

4. **STOP.** A defined-risk structure cannot gap through its own stop, so the
   stop here is about redeploying capital, not about survival. That is why it is
   generous: a 50% drawdown on a straddle three days from a catalyst is normal
   and cutting it is how you pay for convexity and never collect it.

5. **THESIS INVALIDATION.** The forecast that opened the position no longer
   holds. Rare, and deliberately requires a real reversal rather than a wobble.

AMENDED 2026-09-05: SHARES ARE CLOSED BY THEIR CONTRACT, NOT BY THIS LIST
=========================================================================
The five reasons above are the OPTION rules and they stand. A share position is
now judged against the strategy contract its book sealed (`alpha/contract.py`):
an expected horizon, a minimum normal hold, a thesis expiry, a risk budget and
a typed list of reasons that may close it early. Before the minimum hold, only
one of those typed reasons may close it -- and "the price moved 3%" is not one.

The measurement that forced this: **60% of the fleet's round trips finished in
the same session they opened**, on books whose sealed thesis is a 21-session
revision drift (S39). Every number those books produced graded the exit rule.

Two constants left with it. The flat 3% stop is replaced by the book's PROFILE
width -- the same number `alpha/protect.py` places at the venue, so the exit
pass no longer pre-empts the stop the position was sized against. The +2.5%
profit target is now a per-contract field, and the tracker books declare NONE:
collecting 2.5% of a 21-session thesis is collecting a day of noise.

WHAT IS DELIBERATELY NOT HERE
=============================
A trailing stop. Over a five-session window with 1-4 day options, gamma makes
mark-to-market so noisy that a trailing stop is a random exit generator -- it
would convert the tail we paid for into an average outcome, which is the exact
failure the shape thesis exists to avoid.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from alpha import ledger
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

logger = logging.getLogger(__name__)

#: US/Eastern is UTC-4 during the competition (EDT; the switch is 1 November).
#: Hardcoded rather than pulled from a tz database because the window is eight
#: days long and entirely inside EDT -- and a missing tzdata on a slim container
#: is a silent one-hour error in the one calculation that must not be wrong.
ET_OFFSET = timedelta(hours=-4)

#: Flat by this time on deadline day. 10:45 ET leaves fifteen minutes of margin
#: before the 11:00 judging cut for a fill to actually happen -- an order sent
#: at 10:59 into a wide option spread is a hope, not an exit.
LIQUIDATE_BY_ET = time(10, 45)

#: Never carry an option into its expiry session's close. ITM auto-exercise at
#: $0.01 would silently convert premium risk into stock risk.
CLOSE_BEFORE_EXPIRY_ET = time(15, 30)

#: Long premium: take profit late. We paid for the tail; collecting at +40%
#: means never once being paid for what the convexity was bought to capture.
LONG_PROFIT_TARGET = 1.00        # +100% of debit
LONG_STOP = -0.60                # -60% of debit

#: Short premium: take profit early. The last third of a credit earns pennies
#: against the full width of the spread.
SHORT_PROFIT_TARGET = 0.60       # 60% of max credit captured
SHORT_STOP = -1.50               # loss of 1.5x the credit received


@dataclass(frozen=True)
class ExitVerdict:
    close: bool
    reason: str
    urgency: str = "normal"      # "normal" | "immediate"
    #: The TYPED reason, from `alpha.contract.EXIT_REASONS`. Prose is for a
    #: human reading one row; this is for counting nine hundred of them. A book
    #: that never held anything is diagnosed by `group by exit_reason`, not by
    #: reading nine hundred sentences -- which is how "60% of round trips closed
    #: in the same session" took until S39 to be noticed.
    code: str = "HELD"


def now_et() -> datetime:
    return datetime.now(timezone.utc) + ET_OFFSET


def session_day(now: datetime | None = None) -> str:
    """The TRADING day (ET) an artefact belongs to, as YYYY-MM-DD.

    Anything keyed by day -- council packets, autopsies, the sealed pre-open
    book -- must agree on this or a writer and a reader will disagree for the
    four hours a day when the UTC date is already tomorrow and the ET date is
    not. `alpha/council/run.write` and `council_vector.latest_packet` derived it
    separately and agreed; `tests_smoke_fleet` derived it a third time from the
    raw UTC date and did not, so the suite passed for twenty hours a day and
    failed for four. One definition, next to the offset it depends on.

    (`ET_OFFSET` is a fixed -4h and is therefore EDT. It is wrong by an hour
    from the first Sunday in November; that is a live issue for anything dated
    near midnight ET after that date, and it is recorded rather than fixed here
    because changing the repo's clock convention is not a change to make the
    night before an open.)
    """
    return ((now or datetime.now(timezone.utc)) + ET_OFFSET).date().isoformat()


def deadline_liquidation_due(deadline_utc: str, *, now: datetime | None = None) -> bool:
    """True on the deadline's OWN ET date, past `LIQUIDATE_BY_ET`. Not after it.

    THE PREDICATE IS `==`, NOT `>=`, AND THAT IS THE WHOLE POINT
    ===========================================================
    Until 2026-09-05 this read `current.date() < deadline.date() -> False`, so
    from the deadline date ONWARDS it returned True at 10:45 ET every single
    day, for ever. During the contest that was invisible: the deadline was in
    the future and the loop was killed after it. It became live the moment
    entries were re-armed on a fleet whose `AAT_LOOP_EXPIRY` had passed --
    every book would have been liquidated at 10:45 each morning, and (with the
    entry pass gated on this same predicate, `fd0c75b`) refused every entry for
    the rest of the day. A book that is flattened daily cannot hold anything
    for the ten sessions its contract now promises.

    The cost of `==` is stated rather than hidden: if the loop is DOWN on the
    deadline date, nothing liquidates and positions carry past it. That is
    acceptable here and would not be for a contest -- the fleet's expiry is now
    2027-12-31 (`alpha/fleet.py`), so this branch is a mandate end-date, not a
    judging cut. A real contest re-arms the old behaviour by setting the expiry
    to the contest date, which is exactly one variable.

    Both sides are compared in ET. The old code compared a UTC date against an
    ET date, which is a one-day error for four hours a day.
    """
    deadline = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if (current + ET_OFFSET).date() != (deadline + ET_OFFSET).date():
        return False
    return (current + ET_OFFSET).time() >= LIQUIDATE_BY_ET


def _looks_like_share(symbol: str) -> bool:
    return bool(symbol) and not (len(symbol) >= 15 and symbol[-8:].isdigit())


#: A share position is flat at the end of its LAST measured session, once the
#: closing auction is near enough that the day's drift has been collected.
SHARES_HORIZON_EXIT_ET = time(15, 45)


def _sessions_since(entry_utc: str, today_et) -> int:
    """Completed weekday sessions between the entry date and today (ET), holidays ignored --
    the competition window contains none."""
    from datetime import date

    try:
        t = datetime.fromisoformat(entry_utc.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        d0 = (t + ET_OFFSET).date()
    except (ValueError, AttributeError):
        return 0
    n, d = 0, d0
    while d < today_et:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _entry_row_for_shares(symbol: str, rows: list[dict] | None) -> dict | None:
    """The latest SUBMITTED share row for this symbol in this account."""
    import os

    role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None
    rows = rows if rows is not None else ledger.read_all()
    best = None
    for r in rows:
        if r.get("action") != "submitted" or r.get("symbol") != symbol:
            continue
        if r.get("instrument") not in ("long_shares", "short_shares", "pair_short_vs_iwm"):
            continue
        if r.get("account_role") not in (role, None):
            continue
        if best is None or (r.get("ts_utc") or "") > (best.get("ts_utc") or ""):
            best = r
    return best


def _evaluate_shares(position: dict, *, plpc: float, et: datetime,
                     rows: list[dict] | None) -> ExitVerdict:
    """Close this share position, and under which clause of its own contract.

    THE ORDER IS THE CONTRACT'S ORDER, AND IT IS NOT THE OLD ONE
    ===========================================================
    Until 2026-09-05 this function closed at -3% or +2.5% before it had looked
    at a single thing the book declared, and its "horizon" was the forecast's
    `horizon_days` -- which for the tracker books was *sessions left in the
    competition window*. Both are gone. What survives is the risk limit, at the
    profile width the book was actually sized against, because a book that may
    not stop out is not safer.

    1. `HARD_RISK_LIMIT` -- the stop, always legal, at `contract.stop_fraction()`.
    2. `EXECUTION_CORRECTION` -- we hold something no ledger row declared.
    3. before `min_normal_hold_sessions`: HOLD. This is the whole fix.
    4. `THESIS_EXPIRED` / `HORIZON_SPENT` / `PROFIT_TARGET` -- normal exits.
    """
    from alpha import contract as contract_mod

    symbol = position.get("symbol", "")
    row = _entry_row_for_shares(symbol, rows)
    k = contract_mod.resolve(row, day=et.date().isoformat(),
                             profile=os.environ.get("AAT_RISK_PROFILE") or None)
    stop_frac = k.stop_fraction()
    src = "" if k.source == "ledger" else f" [contract source: {k.source}]"

    # 1. THE STOP. At the PROFILE width -- the number `alpha/protect.py` places
    #    at the venue and the number the position was sized against. The flat 3%
    #    this used to charge pre-empted an 8% venue stop on the basket books and
    #    sat 0.52 sigma out on PANW (FINDING_2026-09-05 3a).
    if plpc <= -stop_frac:
        return ExitVerdict(True, (
            f"HARD_RISK_LIMIT: shares at {plpc:+.2%} against the {stop_frac:.0%} stop declared for "
            f"profile {k.profile or 'default'!r}. This is the width the position was sized at; past "
            f"it the position is an undeclared bet.{src}"), code="HARD_RISK_LIMIT")

    # 2. A position nothing declared. Not a thesis, so no hold protects it.
    if row is None:
        return ExitVerdict(True, (
            "EXECUTION_CORRECTION: shares with NO ledger row in this account -- nothing declared a "
            "horizon, a stop or a contract for them. Flattened rather than carried as an "
            "unexplained position."), code="EXECUTION_CORRECTION")

    elapsed = _sessions_since(row.get("ts_utc") or "", et.date())
    horizon = int(k.expected_horizon_sessions)
    hold = int(k.min_normal_hold_sessions)

    # 3. THE MINIMUM HOLD. Everything below this line is a NORMAL exit and is
    #    illegal before it. The emergency reasons are all above.
    if elapsed < hold:
        return ExitVerdict(False, (
            f"HELD under contract: session {elapsed + 1} of a {horizon}-session thesis, minimum "
            f"normal hold {hold}. {plpc:+.2%} unrealised is inside the {stop_frac:.0%} stop, and a "
            f"price wiggle is not one of {list(k.emergency_exit_reasons)}.{src}"), code="HELD")

    # 4. NORMAL EXITS.
    if k.expired(et.date()):
        return ExitVerdict(True, (
            f"THESIS_EXPIRED: past the declared thesis expiry {k.thesis_expiry} "
            f"({elapsed} session(s) held). The idea is stale whether or not it moved.{src}"),
            code="THESIS_EXPIRED")
    if k.profit_target_frac is not None and plpc >= k.profit_target_frac:
        return ExitVerdict(True, (
            f"PROFIT_TARGET: shares at {plpc:+.2%} against this book's declared "
            f"+{k.profit_target_frac:.1%}, after the {hold}-session minimum hold.{src}"),
            code="PROFIT_TARGET")
    last_session = elapsed >= horizon - 1
    if elapsed >= horizon or (last_session and et.time() >= SHARES_HORIZON_EXIT_ET):
        code = "EXPLICIT_EVENT_STRATEGY_EXIT" if hold == 0 else "HORIZON_SPENT"
        return ExitVerdict(True, (
            f"{code}: {elapsed} session(s) since entry against the contract's {horizon}-session "
            f"horizon. The mechanism has no opinion after that.{src}"), code=code)
    return ExitVerdict(False, (
        f"HELD: shares {plpc:+.2%}, session {elapsed + 1} of {horizon}, past the {hold}-session "
        f"minimum hold, inside the {stop_frac:.0%} stop.{src}"), code="HELD")


PAIR_KIND = "pair_short_vs_iwm"


def live_pairs(rows: list[dict] | None, positions: list[dict]) -> list[dict]:
    """Every submitted PAIR row in this account whose short leg is still held.

    Returns dicts: {row, short, hedge, hedge_shares, short_pos, hedge_pos}. The
    hedge leg is a share position in an ETF the book may also hold for its own
    reasons, so a pair is identified by its SHORT leg and its recorded hedge
    share count, never by "the IWM position"."""
    import os

    role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None
    rows = rows if rows is not None else ledger.read_all()
    by_sym = {p.get("symbol"): p for p in positions}
    out = []
    latest: dict[str, dict] = {}
    for r in rows:
        if r.get("action") != "submitted" or r.get("instrument") != PAIR_KIND:
            continue
        if r.get("account_role") not in (role, None):
            continue
        sym = r.get("symbol")
        if sym not in latest or (r.get("ts_utc") or "") > (latest[sym].get("ts_utc") or ""):
            latest[sym] = r
    for sym, r in latest.items():
        oc = r.get("outcome") or {}
        hedge = str(oc.get("hedge_symbol") or "IWM")
        h = int(oc.get("hedge_shares") or 0)
        sp = by_sym.get(sym)
        hp = by_sym.get(hedge)
        if sp is None and hp is None:
            continue                     # closed on both sides; nothing live
        out.append({"row": r, "short": sym, "hedge": hedge, "hedge_shares": h,
                    "short_pos": sp if (sp and float(sp.get("qty") or 0) < 0) else None,
                    "hedge_pos": hp if (hp and float(hp.get("qty") or 0) > 0) else None})
    return out


def hedge_reserved(pairs: list[dict]) -> dict[str, int]:
    """Hedge shares that belong to a live pair (short leg still held), by symbol.
    These must not carry a protective stop of their own and must not be closed
    as a free-standing position: they leave with their short leg."""
    out: dict[str, int] = {}
    for pr in pairs:
        if pr["short_pos"] is not None and pr["hedge_pos"] is not None:
            out[pr["hedge"]] = out.get(pr["hedge"], 0) + pr["hedge_shares"]
    return out


def pair_plpc(pr: dict) -> float:
    """Joint P&L of the pair as a fraction of the SHORT leg's cost basis.

    The hedge position may be larger than the pair's share of it (the book may
    hold the ETF on its own), so the hedge's P&L is pro-rated to the recorded
    hedge share count."""
    sp, hp = pr["short_pos"], pr["hedge_pos"]
    if sp is None:
        return 0.0
    cost = abs(float(sp.get("cost_basis") or 0.0))
    if cost <= 0:
        return 0.0
    pnl = float(sp.get("unrealized_pl") or 0.0)
    if hp is not None:
        hq = float(hp.get("qty") or 0.0)
        if hq > 0:
            pnl += float(hp.get("unrealized_pl") or 0.0) * min(1.0, pr["hedge_shares"] / hq)
    return pnl / cost


def _evaluate_pair(pr: dict, *, et: datetime) -> ExitVerdict:
    """Stop, target and horizon on the JOINT P&L, under the pair's own contract;
    both legs leave together."""
    from alpha import contract as contract_mod

    plpc = pair_plpc(pr)
    if pr["hedge_pos"] is None:
        return ExitVerdict(True, (
            "EXECUTION_CORRECTION: pair with its HEDGE LEG GONE. An unhedged short is the structure "
            "this brain refuses to hold (simple-return short is worth nothing). Flattening the short "
            "leg."), urgency="immediate", code="EXECUTION_CORRECTION")
    row = pr["row"]
    k = contract_mod.resolve(row, day=et.date().isoformat(),
                             profile=os.environ.get("AAT_RISK_PROFILE") or None)
    stop_frac = k.stop_fraction()
    src = "" if k.source == "ledger" else f" [contract source: {k.source}]"
    if plpc <= -stop_frac:
        return ExitVerdict(True, (
            f"HARD_RISK_LIMIT: pair at {plpc:+.2%} joint against the {stop_frac:.0%} stop declared "
            f"for profile {k.profile or 'default'!r}.{src}"), code="HARD_RISK_LIMIT")
    elapsed = _sessions_since(row.get("ts_utc") or "", et.date())
    horizon = int(k.expected_horizon_sessions)
    hold = int(k.min_normal_hold_sessions)
    if elapsed < hold:
        return ExitVerdict(False, (
            f"HELD under contract: pair {plpc:+.2%} joint, session {elapsed + 1} of {horizon}, "
            f"minimum normal hold {hold}.{src}"), code="HELD")
    if k.profit_target_frac is not None and plpc >= k.profit_target_frac:
        return ExitVerdict(True, (
            f"PROFIT_TARGET: pair at {plpc:+.2%} joint against this book's declared "
            f"+{k.profit_target_frac:.1%}.{src}"), code="PROFIT_TARGET")
    last_session = elapsed >= horizon - 1
    if elapsed >= horizon or (last_session and et.time() >= SHARES_HORIZON_EXIT_ET):
        code = "EXPLICIT_EVENT_STRATEGY_EXIT" if hold == 0 else "HORIZON_SPENT"
        return ExitVerdict(True, (
            f"{code}: {elapsed} session(s) since entry against the contract's {horizon}-session "
            f"horizon. The pair was measured over that window and has no opinion after it.{src}"),
            code=code)
    return ExitVerdict(False, (
        f"HELD: pair {plpc:+.2%} joint, session {elapsed + 1} of {horizon}, inside the "
        f"{stop_frac:.0%} stop. Holding both legs.{src}"), code="HELD")


def close_pair_hedge(client, pr: dict, reason: str, summary: dict, *, dry_run: bool,
                     urgency: str = "normal") -> bool:
    """Close the pair's hedge shares BY COUNT (never the whole ETF position).
    Returns True if a close was sent. Records the exit either way."""
    if pr.get("hedge_pos") is None or int(pr.get("hedge_shares") or 0) < 1:
        return False
    hq = int(min(pr["hedge_shares"], float(pr["hedge_pos"].get("qty") or 0)))
    if hq < 1:
        return False
    why = f"{reason}; closing {hq} {pr['hedge']}"
    d_id = ledger.new_decision_id(pr["hedge"], "exit")
    verdict = ExitVerdict(True, why, urgency)
    if dry_run:
        summary["actions"].append(("dry_run", pr["hedge"], why))
        _record_exit(d_id, pr["hedge_pos"], verdict, action="dry_run")
        return False
    try:
        client.close_position(pr["hedge"], qty=hq)
        summary["closed"] += 1
        summary["actions"].append(("closed", pr["hedge"], why))
        logger.info("CLOSED %s x%d -- %s", pr["hedge"], hq, why)
        _record_exit(d_id, pr["hedge_pos"], verdict, action="closed")
        return True
    except BrokerRefusal as exc:
        summary["errors"] += 1
        summary["actions"].append(("error", pr["hedge"], str(exc)))
        logger.error("PAIR hedge close failed %s: %s -- a free-standing long remains", pr["hedge"], exc)
        _record_exit(d_id, pr["hedge_pos"], verdict, action="close_failed", error=str(exc))
        return False


def evaluate(position: dict, *, deadline_utc: str, now: datetime | None = None,
             rows: list[dict] | None = None, pair: dict | None = None) -> ExitVerdict:
    """Should this position be closed, and why. `rows` is the ledger, read once per pass.

    `pair` (from `live_pairs`) means this position is the SHORT leg of a pair
    and is judged on the joint P&L; the hedge leg is never judged alone."""
    current = now or datetime.now(timezone.utc)
    et = current + ET_OFFSET

    symbol = position.get("symbol", "")
    qty = float(position.get("qty") or 0.0)
    cost = abs(float(position.get("cost_basis") or 0.0))
    plpc = float(position.get("unrealized_plpc") or 0.0)

    # 1. The deadline outranks everything, including a winning thesis.
    if deadline_liquidation_due(deadline_utc, now=current):
        return ExitVerdict(True, (
            f"deadline liquidation: past {LIQUIDATE_BY_ET.strftime('%H:%M')} ET on judging "
            "day. A position open at the cut is scored at whatever mark the venue carries, "
            "which for a wide option is not a price anyone would pay."
        ), urgency="immediate", code="DEADLINE")

    # 2. Never hold through an expiry.
    expiry = _expiry_of(symbol)
    if expiry is not None:
        days_left = (expiry - et.date()).days
        if days_left < 0:
            return ExitVerdict(True, "DEADLINE: the option contract has expired; flattening the "
                               "residue.", urgency="immediate", code="DEADLINE")
        if days_left == 0 and et.time() >= CLOSE_BEFORE_EXPIRY_ET:
            return ExitVerdict(True, (
                "expiry session and past "
                f"{CLOSE_BEFORE_EXPIRY_ET.strftime('%H:%M')} ET. ITM contracts auto-exercise "
                "at $0.01, which converts a small premium position into a large stock "
                "position overnight with no decision taken."
            ), urgency="immediate", code="DEADLINE")

    if cost <= 0:
        return ExitVerdict(False, "no cost basis yet; nothing to judge against.")

    # 2b. SHARES: a drift position, not a premium one. Its worst case was
    # DECLARED as a stop plus a gap allowance (`alpha/engine/equity.py`), so the
    # stop here is the number the book was charged at, and the horizon is the
    # measured drift window -- the mechanism is spent after +3 sessions and
    # holding past it is an unpriced bet.
    asset_class = position.get("asset_class") or ""
    if asset_class == "us_equity" or (not asset_class and expiry is None and _looks_like_share(symbol)):
        if pair is not None:
            return _evaluate_pair(pair, et=et)
        return _evaluate_shares(position, plpc=plpc, et=et, rows=rows)

    # 3/4. Targets and stops, asymmetric by whether we are long or short premium.
    long_premium = qty > 0
    if long_premium:
        if plpc >= LONG_PROFIT_TARGET:
            return ExitVerdict(True, (
                f"long premium at {plpc:+.0%} against a +{LONG_PROFIT_TARGET:.0%} target. "
                "Taking the tail we paid for."
            ))
        if plpc <= LONG_STOP:
            return ExitVerdict(True, (
                f"long premium at {plpc:+.0%} against a {LONG_STOP:.0%} stop. The loss is "
                "bounded either way; closing releases the risk budget for a catalyst that "
                "has not happened yet."
            ))
    else:
        if plpc >= SHORT_PROFIT_TARGET:
            return ExitVerdict(True, (
                f"short premium at {plpc:+.0%} of max credit against a "
                f"+{SHORT_PROFIT_TARGET:.0%} target. The remaining credit earns pennies "
                "against the full width of the spread."
            ))
        if plpc <= SHORT_STOP:
            return ExitVerdict(True, (
                f"short premium at {plpc:+.0%}; the trade has moved {abs(SHORT_STOP):.1f}x "
                "the credit against us. Closing inside the defined maximum rather than "
                "waiting to find out whether the wing holds."
            ))

    return ExitVerdict(False, (
        f"{plpc:+.0%} unrealised, "
        + (f"{days_left}d to expiry, " if expiry is not None else "")
        + "inside targets. Holding."
    ))


def _arbiter_pass(client: AlpacaPaper, summary: dict) -> tuple[dict[str, str], set[str]]:
    """Run the position arbiter. Returns (leg -> structure action, legs to close now).

    In `advise` mode (default) it records verdicts and changes nothing. In
    `act` mode an arbiter CLOSE closes every leg of the structure, and a HOLD on
    a structure whose event is still pending overrides a leg-level stop -- the
    leg rules cannot see that a short call at -38% is one wing of a condor
    whose other wing is +37%.
    """
    import os

    from alpha import arbiter

    m = arbiter.mode()
    summary["arbiter_mode"] = m
    if m == "off":
        return {}, set()
    try:
        role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None
        verdicts = arbiter.judge_book(client, account_role=role, record=_arbiter_record_due(role))
    except Exception as exc:                                             # noqa: BLE001
        logger.warning("arbiter failed (%s: %s); exit rules stand alone this pass", type(exc).__name__, exc)
        summary["arbiter_error"] = f"{type(exc).__name__}: {exc}"
        return {}, set()
    summary["arbiter"] = [(v.symbol, v.kind, v.action, round(v.remaining_edge_usd)) for v in verdicts]
    if m != "act":
        return {}, set()
    from alpha import book as book_mod

    acct = client.account()
    bk = book_mod.reconstruct(client.positions(), equity=float(acct.get("equity") or 0.0),
                              account_role=role)
    by_id = {s.decision_id: s for s in bk.structures}
    leg_action: dict[str, str] = {}
    to_close: set[str] = set()
    for v in verdicts:
        st = by_id.get(v.decision_id)
        if st is None:
            continue
        for sym, _side, _ratio in st.legs:
            if v.action == "CLOSE":
                to_close.add(sym)
            elif v.action == "HOLD" and v.event_pending:
                leg_action[sym] = "HOLD_EVENT_PENDING"
    return leg_action, to_close


#: Verdicts are judged every exit pass and WRITTEN at most this often per account,
#: so the ledger carries a graded series rather than a row per structure per
#: five minutes. Overridable for tests.
ARBITER_RECORD_EVERY_S = 1800.0


def _arbiter_record_due(role: str | None) -> bool:
    import os
    import time
    from pathlib import Path

    marker = Path(ledger.LEDGER_DIR) / f"arbiter_last_{role or 'default'}.txt"
    now = time.time()
    try:
        last = float(marker.read_text().strip())
    except (OSError, ValueError):
        last = 0.0
    if now - last < ARBITER_RECORD_EVERY_S:
        return False
    try:
        marker.write_text(f"{now:.0f}")
    except OSError:
        pass
    return True


def manage(client: AlpacaPaper, *, deadline_utc: str, dry_run: bool = True) -> dict:
    """Evaluate every open position and close the ones that earned it."""
    from alpha import protect

    positions = client.positions()
    summary = {"checked": 0, "closed": 0, "held": 0, "errors": 0, "actions": []}

    # VENUE-SIDE STOPS FIRST. Until this ran, the only thing standing behind a
    # share position was this function's own cadence -- which is 5 minutes at
    # best and nothing at all between 16:00 and the next session. A broker error
    # here must not abort the exit pass: an unplaced stop is the status quo ante,
    # a skipped `evaluate` loop is a position nobody is watching at all.
    rows = None
    pairs: list[dict] = []
    if any((p.get("asset_class") or "") == "us_equity" for p in positions):
        rows = ledger.read_all()
        pairs = live_pairs(rows, positions)
    reserved = hedge_reserved(pairs)
    pair_by_short = {pr["short"]: pr for pr in pairs if pr["short_pos"] is not None}
    try:
        summary["protect"] = protect.ensure(client, positions, dry_run=dry_run, exclude_qty=reserved)
        if summary["protect"]["placed"] or summary["protect"]["orphans"]:
            logger.info("protective stops: %s", summary["protect"])
    except BrokerRefusal as exc:
        summary["errors"] += 1
        summary["actions"].append(("protect_error", "", str(exc)))
        logger.warning("protective stop pass failed: %s", exc)

    leg_action, arbiter_close = _arbiter_pass(client, summary)

    # ORPHAN HEDGES: a pair whose short leg is gone (stopped at the venue, or
    # closed by hand) leaves its hedge shares as a free-standing long the book
    # never chose. They leave now, by the recorded share count, never the
    # whole ETF position.
    for pr in pairs:
        if pr["short_pos"] is None:
            close_pair_hedge(client, pr, f"orphan hedge: the short leg of the {pr['short']} pair is gone",
                             summary, dry_run=dry_run)

    for position in positions:
        summary["checked"] += 1
        symbol = position.get("symbol", "")
        if symbol in reserved and float(position.get("qty") or 0) <= reserved[symbol] + 1e-9:
            # Entirely a hedge leg (or legs): judged with its short, never alone.
            summary["held"] += 1
            logger.debug("hold %s: hedge leg of a live pair (%d reserved)", symbol, reserved[symbol])
            continue
        pr = pair_by_short.get(symbol)
        verdict = evaluate(position, deadline_utc=deadline_utc, rows=rows, pair=pr)
        if symbol in arbiter_close and not verdict.close:
            verdict = ExitVerdict(True, (
                "THESIS_INVALIDATED: arbiter CLOSE -- the remaining edge is below the cost of "
                "closing (act mode). A typed reason, so it may pre-empt a contract's minimum "
                "hold; a price wiggle may not."), code="THESIS_INVALIDATED")
        elif verdict.close and verdict.urgency != "immediate" and leg_action.get(symbol) == "HOLD_EVENT_PENDING":
            logger.info("arbiter overrides leg stop on %s: event pending -- %s", symbol, verdict.reason[:80])
            summary["actions"].append(("override_hold", symbol, verdict.reason))
            verdict = ExitVerdict(False, "arbiter HOLD: event pending; a pre-event mark is not the thesis",
                                  code="HELD")
        if not verdict.close:
            summary["held"] += 1
            logger.debug("hold %s: %s", symbol, verdict.reason)
            continue

        decision_id = ledger.new_decision_id(symbol, "exit")
        if dry_run:
            summary["actions"].append(("dry_run", symbol, verdict.reason))
            logger.info("DRY CLOSE %s -- %s", symbol, verdict.reason)
            _record_exit(decision_id, position, verdict, action="dry_run")
            continue

        try:
            # CANCEL THE STOP BEFORE CLOSING. `close_position` is a market
            # DELETE; a sell-stop that outlives the long it protected has
            # nothing left to sell, and the next trigger OPENS A SHORT in an
            # account whose book model reads the symbol as flat. If the cancel
            # fails we do NOT close -- carrying the position one more cycle is
            # recoverable, an unbounded accidental short is not.
            protect.cancel_for(client, symbol)
        except BrokerRefusal as exc:
            summary["errors"] += 1
            summary["actions"].append(("stop_cancel_failed", symbol, str(exc)))
            logger.error("NOT closing %s: its protective stop would outlive it (%s)", symbol, exc)
            _record_exit(decision_id, position, verdict, action="close_failed",
                         error=f"protective stop cancel failed, close withheld: {exc}")
            continue

        try:
            client.close_position(symbol)
            summary["closed"] += 1
            summary["actions"].append(("closed", symbol, verdict.reason))
            logger.info("CLOSED %s -- %s", symbol, verdict.reason)
            _record_exit(decision_id, position, verdict, action="closed")
        except BrokerRefusal as exc:
            summary["errors"] += 1
            summary["actions"].append(("error", symbol, str(exc)))
            logger.warning("close failed %s: %s", symbol, exc)
            # A ONE-SIDED GUARD LEAVES THE POSITION NAKED (2026-09-05).
            #
            # The cancel above reasons carefully about *cancel fails => do not
            # close*. Nothing said what to do when the CLOSE fails after the
            # cancel succeeded, so the position carried on with no protective
            # stop until the next pass placed one -- on 2026-09-04 that was a
            # 76-minute unbounded short on hack2, and it contained the spike
            # that would have filled the cancelled stop. It paid that once,
            # which is exactly why it would never otherwise be found.
            #
            # Re-placing is best-effort and never masks the close failure: the
            # error stands, the row still says `close_failed`, and the outcome
            # of the re-place is recorded beside it.
            replaced = "not attempted"
            try:
                res = protect.ensure(client, [position], dry_run=False, exclude_qty=reserved)
                replaced = f"re-placed ({res.get('placed')} order(s))"
                summary["actions"].append(("stop_replaced", symbol, replaced))
                logger.info("re-placed the protective stop on %s after the close failed", symbol)
            except (BrokerRefusal, Exception) as exc2:                   # noqa: BLE001
                replaced = f"RE-PLACE FAILED: {type(exc2).__name__}: {exc2}"
                summary["actions"].append(("stop_replace_failed", symbol, replaced))
                logger.error("%s is UNPROTECTED: close failed and the stop could not be "
                             "re-placed (%s)", symbol, exc2)
            _record_exit(decision_id, position, verdict, action="close_failed",
                         error=f"{exc}; protective stop {replaced}")
            continue
        if pr is not None:
            # BOTH LEGS LEAVE. The short is gone; its hedge follows by the
            # recorded count, so an ETF the book also holds on its own is untouched.
            close_pair_hedge(client, pr, f"hedge leg of the {symbol} pair: {verdict.reason}",
                             summary, dry_run=False, urgency=verdict.urgency)

    return summary


def _record_exit(decision_id: str, position: dict, verdict: ExitVerdict, *,
                 action: str, error: str | None = None) -> None:
    ledger.record(ledger.Decision(
        decision_id=decision_id,
        ts_utc=datetime.now(timezone.utc).isoformat(),
        symbol=position.get("symbol", ""),
        brain="exit",
        signal_shape=None,
        instrument="close",
        thesis=verdict.reason,
        predicted_move=None, predicted_sd=None, implied_move=None,
        breakeven_move=None, mdm_edge=None,
        quote_snapshot={
            "qty": position.get("qty"),
            "cost_basis": position.get("cost_basis"),
            "market_value": position.get("market_value"),
            "unrealized_pl": position.get("unrealized_pl"),
            "unrealized_plpc": position.get("unrealized_plpc"),
            "current_price": position.get("current_price"),
        },
        action=action,
        refusal_reason=error,
        risk_fraction=0.0,
        max_loss_usd=0.0,
        order=None,
        outcome={"urgency": verdict.urgency, "exit_reason": verdict.code},
    ))


def _expiry_of(occ_symbol: str):
    """Expiry date from an OCC symbol, or None for an equity/crypto position."""
    from datetime import date

    if len(occ_symbol) < 15 or not occ_symbol[-8:].isdigit():
        return None
    try:
        yy, mm, dd = occ_symbol[-15:-13], occ_symbol[-13:-11], occ_symbol[-11:-9]
        return date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None
