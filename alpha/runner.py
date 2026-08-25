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

SEVERAL BRAINS, ONE POSITION PER SYMBOL, NOTHING AVERAGED
=========================================================
Several brains may forecast the same name. Every brain's enumeration is
recorded in full under its own decision id -- refused and alternative rows
included -- and the one that is EXECUTED is the brain whose approved structure
carries the largest risk fraction (the sizer's own measure of disagreement with
the chain). The others are written as `shadow`: the structure that brain would
have opened, priced at the same crossed quotes, so the counterfactual can grade
brain against brain and not only structure against structure. Nothing is
averaged: the parent project's diagnosed bottleneck was ten books that averaged
everything into one signal. And every forecast is written to `forecasts.jsonl`
BEFORE any structure is priced, so a brain that never wins still leaves a
gradeable centre and spread on every pass.

THE DEADLINE IS A FIRST-CLASS INPUT
===================================
Judging happens at 11:00 ET on 4 September -- ninety minutes after the opening
bell, not at a close. So `must_close_by` is threaded through every entry: a
structure whose expiry or thesis needs time we do not have is refused at
selection, not discovered on the last morning.
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

MAX_EXPIRY_SLACK_DAYS = 0.0


@dataclass
class PassResult:
    considered: int = 0
    submitted: int = 0
    refused: int = 0
    shadow: int = 0
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
    """Premium currently at risk, as a fraction of equity -- from the BROKER's book."""
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
        at_risk += cost if qty > 0 else 0.0
    return at_risk / equity


def evaluate(client: AlpacaPaper, forecast: Forecast, *, state: sizing.TournamentState,
             expiry: str, risk_profile: str | None = None,
             open_risk: float | None = None):
    """Enumerate every structure at this expiry and return the best approved one.

    "Best" is the largest approved risk fraction -- the sizer's own expression of
    how far our distribution departs from the chain's. NOT the highest expected
    return: sizing on payoff rather than on edge is how an options book quietly
    becomes a lottery ticket.
    """
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
    best = None
    rejected = []
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
    """Alpaca order payload. Single-leg or `mleg`, always a LIMIT, never market."""
    if contracts < 1:
        raise ValueError("refusing a zero-contract order")
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
    """How many units the approved risk buys, floored at zero. Uses max_loss, never entry_cost."""
    budget = risk_fraction * equity
    if structure.max_loss <= 0:
        return 0
    return int(budget // structure.max_loss)


def record_forecasts(forecasts: list[Forecast], *, note: str = "") -> int:
    """Every brain's forecast, written BEFORE any structure is priced.

    The shadow record: a brain that never wins the enumeration still leaves a
    centre and a spread on every symbol every pass, so its calibration can be
    graded against realised moves whether or not it ever traded. Without this,
    "three independent brains" is a claim about code, not about forecasts.
    """
    n = 0
    for f in forecasts:
        ledger.record(ledger.Decision(
            decision_id=f"{ledger.new_decision_id(f.symbol, f.brain)}:forecast",
            ts_utc=datetime.now(timezone.utc).isoformat(), symbol=f.symbol, brain=f.brain,
            signal_shape=f.signal_shape, instrument="forecast", thesis=f.rationale,
            predicted_move=f.centre, predicted_sd=f.sd, implied_move=None, breakeven_move=None,
            mdm_edge=None, quote_snapshot={}, action="forecast", refusal_reason=None,
            risk_fraction=0.0, max_loss_usd=0.0, order=None,
            outcome={"horizon_days": f.horizon_days, "conviction": f.conviction,
                     "evidence": _compact(f.evidence), "note": note},
        ), name="forecasts")
        n += 1
    return n


def _compact(evidence: dict) -> dict:
    out = {}
    for k, v in evidence.items():
        if k in ("shocks", "event_days"):
            out[k] = f"<{len(v)} items>" if isinstance(v, list) else str(v)[:200]
        else:
            out[k] = v
    return out


def run_pass(client: AlpacaPaper, forecasts: list[Forecast], *, expiry: str,
             risk_profile: str | None = None, dry_run: bool = True,
             field_leader_estimate: float | None = None,
             shadow_brains: tuple[str, ...] = ()) -> PassResult:
    """One full decision pass over forecasts from one or several brains.

    `shadow_brains` never execute regardless of ranking -- a brain earns its
    first live order by beating the others in shadow first.
    """
    result = PassResult()
    state = tournament_state(client, field_leader_estimate=field_leader_estimate)
    risk = open_convex_risk(client)
    logger.info("pass: equity $%s, %.0f%% of window left, %.1f%% already at risk",
                f"{state.equity:,.0f}", state.fraction_of_window_remaining * 100, risk * 100)
    record_forecasts(forecasts, note=f"pass expiry={expiry} dry_run={dry_run}")

    by_symbol: dict[str, list[Forecast]] = {}
    for f in forecasts:
        by_symbol.setdefault(f.symbol, []).append(f)

    committed = 0.0
    for symbol, group in by_symbol.items():
        evaluated = []
        for forecast in group:
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
                logger.warning("%s/%s: %s", forecast.symbol, forecast.brain, exc)
                continue
            # Roads not taken, written BEFORE the chosen one: a crash between the
            # two leaves a ledger that over-states what we declined, never what we did.
            for i, (alt, alt_verdict) in enumerate(alternatives):
                _record(f"{decision_id}:alt{i}", forecast, alt, alt_verdict, snapshot, state,
                        action="refused" if not alt_verdict.approved else "alternative",
                        reason=alt_verdict.reason)
            if structure is None:
                result.refused += 1
                _record(decision_id, forecast, None, verdict, snapshot, state,
                        action="refused", reason=verdict.reason)
                continue
            evaluated.append((decision_id, forecast, structure, verdict, snapshot))

        if not evaluated:
            continue
        executable = [e for e in evaluated if e[1].brain not in shadow_brains]
        champion = max(executable, key=lambda e: e[3].risk_fraction) if executable else None
        for e in evaluated:
            if e is champion:
                continue
            d_id, forecast, structure, verdict, snapshot = e
            why = ("shadow-only brain" if forecast.brain in shadow_brains else
                   f"out-ranked by {champion[1].brain} at {champion[3].risk_fraction:.2%} "
                   f"vs {verdict.risk_fraction:.2%} on the same symbol")
            result.shadow += 1
            _record(d_id, forecast, structure, verdict, snapshot, state, action="shadow",
                    reason=why)
        if champion is None:
            continue
        committed = _execute(client, result, *champion, state, committed, dry_run=dry_run)
    return result


def _execute(client, result: PassResult, decision_id: str, forecast: Forecast,
             structure: sizing.Structure, verdict: sizing.SizingVerdict, snapshot,
             state: sizing.TournamentState, committed: float, *, dry_run: bool) -> float:
    """Size, build and (unless dry) send the champion. Returns updated `committed`.

    The aggregate ceiling binds WITHIN a pass: `committed` accumulates so six
    candidates cannot each pass a 50% test and total 300%.
    """
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
        return committed

    order = build_order(structure, n)
    add = (structure.max_loss * n) / state.equity if state.equity else 0.0
    if dry_run:
        result.refused += 1
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="dry_run", reason="dry run: order built and not sent", order=order,
                contracts=n)
        logger.info("DRY  %s %s %s x%d  risk %.2f%%", forecast.brain, forecast.symbol,
                    structure.kind, n, verdict.risk_fraction * 100)
        return committed + add

    try:
        placed = client.submit(order, decision_id=decision_id,
                               quote_snapshot=_quote_snapshot(structure, snapshot))
        result.submitted += 1
        result.decisions.append(decision_id)
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="submitted", reason=verdict.reason, order=order, contracts=n,
                alpaca_order_id=placed.get("id"))
        logger.info("SENT %s %s %s x%d id=%s", forecast.brain, forecast.symbol,
                    structure.kind, n, placed.get("id"))
        return committed + add
    except BrokerRefusal as exc:
        result.errors += 1
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="rejected", reason=str(exc), order=order, contracts=n)
        logger.warning("REJECTED %s: %s", forecast.symbol, exc)
        return committed


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
        "parity_gap": snapshot.parity_gap(_expiry_of_legs(structure)),
        "legs": legs,
    }


def _expiry_of_legs(structure: sizing.Structure) -> str:
    from alpha.data.chain import _decode_occ

    return _decode_occ(structure.legs[0][0])[2] if structure.legs else ""


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
        entry_cost_per_unit=structure.entry_cost if structure else None,
        max_loss_per_unit=structure.max_loss if structure else None,
        legs=tuple(structure.legs) if structure else (),
        tournament_state={
            "equity": state.equity, "return": state.total_return,
            "phase": state.phase.value,
            "window_remaining": state.fraction_of_window_remaining,
        },
        llm=(forecast.evidence.get("shocks") or [{}])[0].get("llm") if forecast.evidence.get("shocks") else None,
    ))
