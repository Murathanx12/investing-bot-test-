"""One decision pass: perceive, enumerate, gate, size, record, order.

THE LOOP IS DELIBERATELY BORING
==============================
Everything interesting already happened in `shape.py` (which instrument), the
brains (what distribution) and `sizing.py` (is this resolvable, and how big).
The runner's whole job is to do that in a fixed order, write down what it saw,
and not surprise anybody at 3am on a Wednesday.

Two properties it must have, because it runs unattended for a week:

**Restart-safe.** Decision ids are derived from (minute, brain, symbol) and
client order ids from the decision id, so a crash-restart inside the same minute
collides at the broker instead of doubling the position. That is why the id is
derived rather than generated.

**Loud about refusals.** Every candidate is written to the ledger whether it
traded or not. A pass that opens nothing still produces a full record of what it
looked at and why it declined, which is the difference between an agent that was
thinking and an agent that was down.

THE DEADLINE IS A FIRST-CLASS INPUT
===================================
Judging happens at 11:00 ET on 4 September -- ninety minutes after the opening
bell, not at a close. So `must_close_by` is threaded through every entry: a
structure whose expiry or thesis needs time we do not have is refused at
selection, not discovered on the last morning. An agent holding an unclosable
position into a deadline is not aggressive, it is unfinished.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from alpha import config, ledger
from alpha.brains.base import Forecast
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data import chain as chain_mod
from alpha.engine import sizing, structures

logger = logging.getLogger(__name__)

KICKOFF = datetime.fromisoformat(config.COMPETITION["kickoff_utc"].replace("Z", "+00:00"))
DEADLINE = datetime.fromisoformat(config.COMPETITION["deadline_utc"].replace("Z", "+00:00"))

#: Never open a structure whose expiry lands after the judging deadline unless
#: it can be sold before it. In practice: expiry on or before the deadline date,
#: because an option still has time value at 10:45 and can be closed, whereas a
#: thesis that needs next week cannot be scored at all.
MAX_EXPIRY_SLACK_DAYS = 0.0


@dataclass
class PassResult:
    considered: int = 0
    submitted: int = 0
    refused: int = 0
    errors: int = 0
    decisions: list[str] = None

    def __post_init__(self) -> None:
        self.decisions = self.decisions or []


def tournament_state(client: AlpacaPaper, *, starting_equity: float | None = None,
                     field_leader_estimate: float | None = None) -> sizing.TournamentState:
    """Where we stand, read from the venue rather than from our own bookkeeping."""
    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    start = starting_equity if starting_equity is not None else config.COMPETITION[
        "required_starting_equity"]
    now = datetime.now(timezone.utc)
    total = (DEADLINE - KICKOFF).total_seconds()
    remaining = max(0.0, min(1.0, (DEADLINE - now).total_seconds() / total))
    return sizing.TournamentState(
        equity=equity, starting_equity=start,
        fraction_of_window_remaining=remaining,
        field_leader_estimate=field_leader_estimate,
    )


def open_convex_risk(client: AlpacaPaper) -> float:
    """Premium currently at risk, as a fraction of equity.

    Computed from what the BROKER says we hold, not from our own tally of what
    we sent. An order that filled differently, partially, or not at all is
    exactly the case where an internal counter and reality diverge, and the
    aggregate ceiling is the guard that stops the agent over-committing before
    the biggest catalysts of the week.
    """
    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    if equity <= 0:
        return 1.0
    at_risk = 0.0
    for pos in client.positions():
        if (pos.get("asset_class") or "") != "us_option":
            continue
        qty = float(pos.get("qty") or 0.0)
        cost = abs(float(pos.get("cost_basis") or 0.0))
        # A long option's risk is what we paid. A short leg inside a spread is
        # capped by its partner, and `cost_basis` already nets across the pair.
        at_risk += cost if qty > 0 else 0.0
    return at_risk / equity


def evaluate(client: AlpacaPaper, forecast: Forecast, *, state: sizing.TournamentState,
             expiry: str, risk_profile: str | None = None,
             open_risk: float | None = None) -> tuple[sizing.Structure | None, sizing.SizingVerdict, object]:
    """Enumerate every structure at this expiry and return the best approved one.

    "Best" is the largest approved risk fraction, which is the sizer's own
    expression of how far our distribution departs from the chain's. It is NOT
    the highest expected return -- a structure can have a huge payoff and a tiny
    probability edge, and sizing on payoff rather than on edge is how an options
    book quietly becomes a lottery ticket.
    """
    # Strikes are bounded to a band around spot scaled by the forecast's OWN
    # width. A 1000-contract page limit truncates a full SPY chain arbitrarily
    # (by symbol order, so it silently keeps low strikes), and a band keeps the
    # part of the chain any of our structures could actually reach.
    band = max(4.0 * forecast.sd, 0.06)
    spot_hint = forecast.evidence.get("last_close")
    lo = hi = None
    if spot_hint:
        lo, hi = spot_hint * (1 - band), spot_hint * (1 + band)
    snapshot = chain_mod.fetch(
        client, forecast.symbol, expiry_from=expiry, expiry_to=expiry,
        strike_from=lo, strike_to=hi,
    )

    risk = open_risk if open_risk is not None else open_convex_risk(client)
    best: tuple[sizing.Structure, sizing.SizingVerdict] | None = None
    rejected: list[tuple[sizing.Structure, sizing.SizingVerdict]] = []

    for structure in structures.enumerate_all(snapshot, expiry):
        verdict = sizing.size(
            structure, forecast.centre, forecast.sd, state,
            open_convex_risk=risk, conviction=forecast.conviction,
            risk_profile=risk_profile,
        )
        if verdict.approved and (best is None or verdict.risk_fraction > best[1].risk_fraction):
            if best is not None:
                rejected.append(best)
            best = (structure, verdict)
        else:
            rejected.append((structure, verdict))

    if best is None:
        why = sizing.SizingVerdict(
            False, 0.0, 0.0,
            f"{len(rejected)} structures enumerated at {expiry}, none cleared the gates. "
            + (rejected[0][1].reason if rejected else "chain produced nothing tradeable."),
        )
        return None, why, snapshot, rejected
    return best[0], best[1], snapshot, rejected


def build_order(structure: sizing.Structure, contracts: int) -> dict:
    """Alpaca order payload. Single-leg or `mleg`, always a LIMIT.

    Never a market order. Alpaca's paper engine does not model order size
    against displayed NBBO quantity, so a market order in a thin option can fill
    at a price that never existed -- which would flatter the P&L and poison the
    evidence at the same time. A limit at our computed executable price gets a
    fill we can defend or no fill at all, and no fill is a fine outcome.
    """
    if contracts < 1:
        raise ValueError("refusing a zero-contract order")

    # Alpaca prices a multi-leg order at the NET: positive is a debit we pay,
    # negative is a credit we receive. Single-leg orders take an absolute price
    # with the direction carried by `side`.
    net_price = round(structure.entry_cost / structures.MULT, 2)

    if len(structure.legs) == 1:
        symbol, side, _ratio = structure.legs[0]
        return {
            "symbol": symbol, "qty": str(contracts), "side": side,
            "type": "limit", "limit_price": f"{abs(net_price):.2f}",
            "time_in_force": "day",
        }

    return {
        "order_class": "mleg", "qty": str(contracts), "type": "limit",
        "limit_price": f"{net_price:.2f}", "time_in_force": "day",
        "legs": [
            {"symbol": sym, "ratio_qty": str(ratio), "side": side,
             "position_intent": "buy_to_open" if side == "buy" else "sell_to_open"}
            for sym, side, ratio in structure.legs
        ],
    }


def contracts_for(structure: sizing.Structure, risk_fraction: float, equity: float) -> int:
    """How many units the approved risk buys, floored at zero.

    Uses `max_loss`, never `entry_cost`. For a credit structure the cash
    received is small and the exposure is the width of the spread -- sizing on
    the credit would buy roughly seven times too many.
    """
    budget = risk_fraction * equity
    if structure.max_loss <= 0:
        return 0
    return int(budget // structure.max_loss)


def run_pass(client: AlpacaPaper, forecasts: list[Forecast], *, expiry: str,
             risk_profile: str | None = None, dry_run: bool = True,
             field_leader_estimate: float | None = None) -> PassResult:
    """One full decision pass over a list of forecasts."""
    result = PassResult()
    state = tournament_state(client, field_leader_estimate=field_leader_estimate)
    risk = open_convex_risk(client)
    logger.info("pass: equity $%s, %.0f%% of window left, %.1f%% already at risk",
                f"{state.equity:,.0f}", state.fraction_of_window_remaining * 100, risk * 100)

    committed = 0.0
    for forecast in forecasts:
        result.considered += 1
        decision_id = ledger.new_decision_id(forecast.symbol, forecast.brain)
        try:
            structure, verdict, snapshot, alternatives = evaluate(
                client, forecast, state=state, expiry=expiry,
                risk_profile=risk_profile, open_risk=risk + committed,
            )
        except Exception as exc:                                    # noqa: BLE001
            result.errors += 1
            _record(decision_id, forecast, None, None, None, state,
                    action="error", reason=f"{type(exc).__name__}: {exc}")
            logger.warning("%s: %s", forecast.symbol, exc)
            continue

        # The roads not taken, written down at the moment they were not taken.
        # Recorded BEFORE the chosen one so that a crash between the two leaves
        # a ledger that over-states what we declined rather than what we did.
        for i, (alt, alt_verdict) in enumerate(alternatives):
            _record(f"{decision_id}:alt{i}", forecast, alt, alt_verdict, snapshot, state,
                    action="refused" if not alt_verdict.approved else "alternative",
                    reason=alt_verdict.reason)

        if structure is None:
            result.refused += 1
            _record(decision_id, forecast, None, verdict, snapshot, state,
                    action="refused", reason=verdict.reason)
            continue

        # The aggregate ceiling has to bind WITHIN a pass, not just across
        # passes. Sizing every candidate against the risk level at the START of
        # the loop lets six positions each pass a 50% test and total 300% -- the
        # ceiling reads as enforced and is not. `risk` accumulates as we commit.
        n = contracts_for(structure, verdict.risk_fraction, state.equity)
        if n < 1:
            result.refused += 1
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="refused",
                    reason=(f"approved {verdict.risk_fraction:.2%} of ${state.equity:,.0f} "
                            f"= ${verdict.risk_fraction * state.equity:,.0f}, but one unit of "
                            f"{structure.kind} risks ${structure.max_loss:,.0f}. Rounds to zero "
                            "contracts -- refused rather than rounded UP, which is how a risk "
                            "ceiling becomes a suggestion."))
            continue

        order = build_order(structure, n)
        if dry_run:
            result.refused += 1
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="dry_run", reason="dry run: order built and not sent", order=order,
                    contracts=n)
            logger.info("DRY  %s %s x%d  risk %.2f%%  (cumulative %.1f%%)",
                        forecast.symbol, structure.kind, n,
                        verdict.risk_fraction * 100, (risk + committed) * 100)
            committed += (structure.max_loss * n) / state.equity if state.equity else 0.0
            continue

        try:
            placed = client.submit(
                order, decision_id=decision_id,
                quote_snapshot=_quote_snapshot(structure, snapshot),
            )
            result.submitted += 1
            result.decisions.append(decision_id)
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="submitted", reason=verdict.reason, order=order, contracts=n,
                    alpaca_order_id=placed.get("id"))
            committed += (structure.max_loss * n) / state.equity if state.equity else 0.0
            logger.info("SENT %s %s x%d id=%s  (cumulative risk %.1f%%)",
                        forecast.symbol, structure.kind, n, placed.get("id"),
                        (risk + committed) * 100)
        except BrokerRefusal as exc:
            result.errors += 1
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="rejected", reason=str(exc), order=order, contracts=n)
            logger.warning("REJECTED %s: %s", forecast.symbol, exc)

    return result


def _quote_snapshot(structure: sizing.Structure, snapshot) -> dict:
    """The quotes we actually saw, per leg, plus how stale they were."""
    wanted = {sym for sym, _, _ in structure.legs}
    legs = [
        {"symbol": c.symbol, "bid": c.bid, "ask": c.ask, "bid_size": c.bid_size,
         "ask_size": c.ask_size, "quote_ts": c.quote_ts.isoformat(),
         "age_s": round(c.quote_age_seconds, 1),
         "effective_age_s": round(c.effective_age_seconds, 1),
         "adjusted_mid": c.adjusted_mid, "staleness_penalty": c.staleness_penalty,
         "delta": c.delta, "iv": c.implied_vol, "greeks_source": c.greeks_source}
        for c in snapshot.contracts if c.symbol in wanted
    ]
    return {
        "underlying": snapshot.underlying, "spot": snapshot.spot,
        "spot_source": snapshot.spot_source, "spot_ts": snapshot.spot_ts.isoformat(),
        "feed": snapshot.feed, "market_open": snapshot.market_open,
        "median_quote_age_s": round(snapshot.median_quote_age_seconds, 1),
        "legs": legs,
    }


def _record(decision_id: str, forecast: Forecast, structure, verdict, snapshot,
            state: sizing.TournamentState, *, action: str, reason: str,
            order: dict | None = None, contracts: int = 0,
            alpaca_order_id: str | None = None) -> None:
    ledger.record(ledger.Decision(
        decision_id=decision_id,
        ts_utc=datetime.now(timezone.utc).isoformat(),
        symbol=forecast.symbol,
        brain=forecast.brain,
        signal_shape=forecast.signal_shape,
        instrument=structure.kind if structure else "none",
        thesis=forecast.rationale,
        predicted_move=forecast.centre,
        predicted_sd=forecast.sd,
        implied_move=structure.implied_move if structure else None,
        breakeven_move=structure.breakeven_move if structure else None,
        mdm_edge=verdict.mdm_edge if verdict else None,
        quote_snapshot=_quote_snapshot(structure, snapshot) if (structure and snapshot) else {},
        action=action,
        refusal_reason=None if action in ("submitted",) else reason,
        risk_fraction=verdict.risk_fraction if verdict else 0.0,
        max_loss_usd=(structure.max_loss * contracts) if structure else 0.0,
        order=order,
        alpaca_order_id=alpaca_order_id,
        # Unit-scale economics on EVERY row, taken or refused, so the decision
        # can be priced forward later at a risk budget it never actually got.
        entry_cost_per_unit=structure.entry_cost if structure else None,
        max_loss_per_unit=structure.max_loss if structure else None,
        legs=tuple(structure.legs) if structure else (),
        tournament_state={
            "equity": state.equity, "return": state.total_return,
            "phase": state.phase.value,
            "window_remaining": state.fraction_of_window_remaining,
        },
        llm=None,
    ))
