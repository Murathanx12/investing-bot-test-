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


def now_et() -> datetime:
    return datetime.now(timezone.utc) + ET_OFFSET


def deadline_liquidation_due(deadline_utc: str, *, now: datetime | None = None) -> bool:
    """True once we are inside the final session and past `LIQUIDATE_BY_ET`."""
    deadline = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    current = now or datetime.now(timezone.utc)
    if current.date() < (deadline + ET_OFFSET).date():
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
        if r.get("instrument") not in ("long_shares", "short_shares"):
            continue
        if r.get("account_role") not in (role, None):
            continue
        if best is None or (r.get("ts_utc") or "") > (best.get("ts_utc") or ""):
            best = r
    return best


def _evaluate_shares(position: dict, *, plpc: float, et: datetime,
                     rows: list[dict] | None) -> ExitVerdict:
    from alpha.engine import equity

    symbol = position.get("symbol", "")
    if equity.stop_hit(plpc):
        return ExitVerdict(True, (
            f"shares at {plpc:+.2%} against the declared {-equity.STOP_FRACTION:.0%} stop. "
            "This is the number the book was charged at; past it the position is an "
            "undeclared bet."))
    if equity.target_hit(plpc):
        return ExitVerdict(True, (
            f"shares at {plpc:+.2%} against a +{equity.PROFIT_TARGET:.1%} target -- about twice "
            "the measured three-day drift. Beyond it the tercile split says the move stops "
            "continuing; collected."))
    row = _entry_row_for_shares(symbol, rows)
    if row is None:
        return ExitVerdict(True, (
            "shares with NO ledger row in this account: nothing declared a horizon or a stop "
            "for them. Flattened rather than carried as an unexplained position."))
    horizon = float(((row.get("outcome") or {}).get("horizon_days")) or 1.0)
    elapsed = _sessions_since(row.get("ts_utc") or "", et.date())
    last_session = elapsed >= math.ceil(horizon) - 1
    if elapsed >= math.ceil(horizon) or (last_session and et.time() >= SHARES_HORIZON_EXIT_ET):
        return ExitVerdict(True, (
            f"drift window spent: {elapsed} session(s) since entry against a {horizon:.0f}-session "
            "horizon. The mechanism was measured over +1..+3 and has no opinion after that."))
    return ExitVerdict(False, (
        f"shares {plpc:+.2%}, session {elapsed + 1} of {math.ceil(horizon)} in the drift window, "
        "inside stop and target. Holding."))


def evaluate(position: dict, *, deadline_utc: str, now: datetime | None = None,
             rows: list[dict] | None = None) -> ExitVerdict:
    """Should this position be closed, and why. `rows` is the ledger, read once per pass."""
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
        ), urgency="immediate")

    # 2. Never hold through an expiry.
    expiry = _expiry_of(symbol)
    if expiry is not None:
        days_left = (expiry - et.date()).days
        if days_left < 0:
            return ExitVerdict(True, "contract has expired; flattening the residue.",
                               urgency="immediate")
        if days_left == 0 and et.time() >= CLOSE_BEFORE_EXPIRY_ET:
            return ExitVerdict(True, (
                "expiry session and past "
                f"{CLOSE_BEFORE_EXPIRY_ET.strftime('%H:%M')} ET. ITM contracts auto-exercise "
                "at $0.01, which converts a small premium position into a large stock "
                "position overnight with no decision taken."
            ), urgency="immediate")

    if cost <= 0:
        return ExitVerdict(False, "no cost basis yet; nothing to judge against.")

    # 2b. SHARES: a drift position, not a premium one. Its worst case was
    # DECLARED as a stop plus a gap allowance (`alpha/engine/equity.py`), so the
    # stop here is the number the book was charged at, and the horizon is the
    # measured drift window -- the mechanism is spent after +3 sessions and
    # holding past it is an unpriced bet.
    asset_class = position.get("asset_class") or ""
    if asset_class == "us_equity" or (not asset_class and expiry is None and _looks_like_share(symbol)):
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
    positions = client.positions()
    summary = {"checked": 0, "closed": 0, "held": 0, "errors": 0, "actions": []}
    leg_action, arbiter_close = _arbiter_pass(client, summary)
    rows = None
    if any((p.get("asset_class") or "") == "us_equity" for p in positions):
        rows = ledger.read_all()

    for position in positions:
        summary["checked"] += 1
        verdict = evaluate(position, deadline_utc=deadline_utc, rows=rows)
        symbol = position.get("symbol", "")
        if symbol in arbiter_close and not verdict.close:
            verdict = ExitVerdict(True, "arbiter CLOSE: remaining edge below the close cost (act mode)")
        elif verdict.close and verdict.urgency != "immediate" and leg_action.get(symbol) == "HOLD_EVENT_PENDING":
            logger.info("arbiter overrides leg stop on %s: event pending -- %s", symbol, verdict.reason[:80])
            summary["actions"].append(("override_hold", symbol, verdict.reason))
            verdict = ExitVerdict(False, "arbiter HOLD: event pending; a pre-event mark is not the thesis")
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
            client.close_position(symbol)
            summary["closed"] += 1
            summary["actions"].append(("closed", symbol, verdict.reason))
            logger.info("CLOSED %s -- %s", symbol, verdict.reason)
            _record_exit(decision_id, position, verdict, action="closed")
        except BrokerRefusal as exc:
            summary["errors"] += 1
            summary["actions"].append(("error", symbol, str(exc)))
            logger.warning("close failed %s: %s", symbol, exc)
            _record_exit(decision_id, position, verdict, action="close_failed", error=str(exc))

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
        outcome={"urgency": verdict.urgency},
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
