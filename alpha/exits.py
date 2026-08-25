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


def evaluate(position: dict, *, deadline_utc: str, now: datetime | None = None) -> ExitVerdict:
    """Should this position be closed, and why."""
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


def manage(client: AlpacaPaper, *, deadline_utc: str, dry_run: bool = True) -> dict:
    """Evaluate every open position and close the ones that earned it."""
    positions = client.positions()
    summary = {"checked": 0, "closed": 0, "held": 0, "errors": 0, "actions": []}

    for position in positions:
        summary["checked"] += 1
        verdict = evaluate(position, deadline_utc=deadline_utc)
        symbol = position.get("symbol", "")
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
