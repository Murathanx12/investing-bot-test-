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

import math
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from alpha import admission
from alpha import book as book_mod
from alpha import config, daybreak, ledger, recovery
from alpha.brains.base import Forecast
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data import chain as chain_mod
from alpha.engine import equity, payoff, sizing, structures
from alpha.engine import equity as equity_mod

logger = logging.getLogger(__name__)

KICKOFF = datetime.fromisoformat(config.COMPETITION["kickoff_utc"].replace("Z", "+00:00"))
DEADLINE = datetime.fromisoformat(config.COMPETITION["deadline_utc"].replace("Z", "+00:00"))

MAX_EXPIRY_SLACK_DAYS = 0.0

#: EVENT CLUSTER RISK. NVDA, AVGO and SMH structures that all exist because of
#: one NVDA print are ONE bet wearing three tickers. Position risk is capped per
#: symbol by the sizer; this caps the sum across every position that cites the
#: same scheduled event (event_move's `event_date`, or a narrative `theme`).
#: 25% of equity per event node -- enough for an aggressive expression through
#: the originator AND a relay leg, not enough to be the whole book.
EVENT_NODE_CAP = 0.25

#: EVENT RESERVE. Premium kept free for a scheduled event so that ordinary
#: passes cannot spend the whole aggregate cap before it arrives. On 25 Aug the
#: dev book reached the 50% ceiling on a Tuesday; the jobs report on 4 Sep is
#: the one event with a positive historical receipt and it would have found an
#: empty budget. Ordinary forecasts see the cap LESS the reserve; a forecast
#: whose own event_date is the reserved date sees the full cap.
EVENT_RESERVE: dict[str, float] = {"2026-09-04": 0.10}


def event_node(forecast: Forecast) -> str | None:
    """The scheduled event this forecast exists because of, or None."""
    ev = forecast.evidence or {}
    if ev.get("event_date"):
        return f"print:{ev['event_date']}"
    if ev.get("theme"):
        return f"theme:{ev['theme']}"
    return None


def _priced_out(reason: str) -> bool:
    """Did the arbiter decline on PRICE/liquidity rather than on the forecast?

    Deliberately conservative: anything not recognisably about the market
    microstructure is attributed to EVIDENCE, so the alpha layer is blamed by
    default and the execution number can only be under-stated. A decomposition
    that flatters the signal is worse than none.
    """
    r = (reason or "").lower()
    return any(k in r for k in (
        "spread", "no quote", "quotes", "illiquid", "liquidity", "no chain",
        "unquotable", "bid", "ask", "wide", "no strike", "no expiry", "stale"))


#: WHY an entry did not happen, and the reason this enumeration exists.
#:
#: `48 forecasts, 48 refused, errors=0` is operationally excellent and says
#: NOTHING about the only question worth asking of it: is the alpha layer barren,
#: or is the risk layer so strict the system cannot trade? Those two states print
#: identically, and they call for opposite work. A count without a decomposition
#: is a reassurance, not a measurement.
#:
#: `dry_run` is deliberately NOT a refusal. It used to increment `refused`, which
#: made a dry pass -- where every order was built successfully and simply not
#: sent -- indistinguishable from a pass where risk blocked all of it. The smoke
#: run on 26 Aug reported "refused=48" for a pass that had in fact BUILT 48
#: orders. That is the failure this whole enumeration exists to stop, and it was
#: sitting inside the counter itself.
REFUSAL_CLASSES = (
    "evidence",           # the forecast did not earn a structure
    "execution",          # no tradeable structure at an acceptable price
    "risk",               # admission, event-node cap, latch, unbounded book
    "already_held",       # a position or a resting order exists for this symbol
    "capital",            # approved size does not buy one unit
    "insufficient_data",  # the inputs to decide were not there
    "cash",               # a structure cleared and CASH still beat it on EV
)


@dataclass
class PassResult:
    considered: int = 0
    submitted: int = 0
    refused: int = 0
    shadow: int = 0
    errors: int = 0
    cash: int = 0
    """Symbols where a structure cleared the gate and CASH still beat it on EV."""
    dry_run: int = 0
    """Orders BUILT and deliberately not sent. Not a refusal -- see REFUSAL_CLASSES."""
    by_reason: dict[str, int] = None
    decisions: list[str] = None

    def __post_init__(self) -> None:
        self.decisions = self.decisions or []
        self.by_reason = self.by_reason or {}

    def refuse(self, why: str) -> None:
        """Count one refusal AND its class. Never increment `refused` directly."""
        if why not in REFUSAL_CLASSES:
            raise ValueError(f"unknown refusal class {why!r}; add it to REFUSAL_CLASSES "
                             "rather than passing a free string -- an unclassified "
                             "refusal is the thing this exists to prevent")
        self.refused += 1
        self.by_reason[why] = self.by_reason.get(why, 0) + 1

    def decomposition(self) -> str:
        """The one-line summary that says which half of the system to work on."""
        if not self.by_reason:
            return "none"
        return " ".join(f"{k}={v}" for k, v in sorted(
            self.by_reason.items(), key=lambda kv: -kv[1]))


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


def held_underlyings(client: AlpacaPaper) -> dict[str, int]:
    """Underlyings with an open OPTION or SHARE position in this account -> leg count."""
    out: dict[str, int] = {}
    for pos in client.positions():
        cls = pos.get("asset_class") or ""
        sym = pos.get("symbol") or ""
        if cls == "us_option" and len(sym) > 15:
            out[sym[:-15]] = out.get(sym[:-15], 0) + 1
        elif cls == "us_equity" and sym:
            out[sym] = out.get(sym, 0) + 1
    return out


def open_order_underlyings(client: AlpacaPaper) -> dict[str, int]:
    """Underlyings with a RESTING, UNFILLED order -> order count.

    `held_underlyings` reads POSITIONS, and an entry limit that has not filled is
    not a position. The one-position-per-symbol guard was therefore blind to it:
    the 10:00 pass rests `buy 120 NVDA limit 212.96 DAY`, the price ticks up, and
    at 10:30 the brain re-forecasts, gets a new decision id (the id only collides
    within the same MINUTE) and rests a SECOND order. A dip fills both -- 240
    shares against a 25% notional cap, two ledger rows, and an admission
    controller that was never asked about the second one. The same mechanism
    fires on any restart more than a minute after a submit.

    Protective stops are excluded: `alpha.protect` places those as a consequence
    of a position that already exists, so counting them here would refuse every
    re-entry into a name we already stopped out of.
    """
    from alpha import protect
    from alpha.broker.alpaca import _is_option

    out: dict[str, int] = {}
    for order in client.orders(status="open"):
        if protect.is_ours(order):
            continue
        legs = order.get("legs") or []
        symbols = [str(leg.get("symbol") or "") for leg in legs] if legs else [
            str(order.get("symbol") or "")]
        for sym in symbols:
            if not sym:
                continue
            root = sym[:-15] if _is_option(sym) and len(sym) > 15 else sym
            out[root] = out.get(root, 0) + 1
    return out


def open_convex_risk(client: AlpacaPaper) -> float:
    """TRUE maximum loss of the open book, as a fraction of equity.

    Until 26 Aug this summed the cost basis of LONG legs -- premium paid, not
    risk carried -- and credited two NVDA condors with ~$5k of a ~$25k worst
    case. It is now `alpha.book.read`: structures matched against the ledger at
    their stated max loss, residual shorts charged at full width, an unbounded
    short read as 100% (every entry refused).
    """
    return book_mod.read(client).fraction


class ChainWidthUnavailable(RuntimeError):
    """A `direction` brain asked for the market's width and the chain had none."""


def effective_sd(forecast: Forecast, structure: sizing.Structure) -> tuple[float, str]:
    """The spread this forecast is allowed to be integrated at, and where it came from.

    A brain that declares `claim="direction"` knows which WAY, not how FAR. Its
    own sd is a realised-volatility estimate, and handing that to the gate makes
    an accidental second claim -- that the chain has the width wrong -- which is
    the larger of the two claims and the one it has no evidence for. Since
    implied is above trailing realised most of the time, that accident is
    systematic in one direction: every long option looks overpriced, every
    short-premium structure looks free, and the EV ranker hands a directional
    brain an IRON CONDOR. Measured on a live NVDA chain, the same condor won
    whether the print was up or down; the sign of the forecast moved its EV by
    $6 on $54 and changed nothing else.

    So a `direction` brain is integrated at the CHAIN's width -- the structure's
    own ATM implied move, converted with sigma = E|Z| * sqrt(pi/2) exactly as
    `sizing.implied_probability_beyond` does, so the gate compares like with
    like. What survives is a pure statement about the SHIFT: this structure pays
    only if the centre moves enough mass across its breakeven to cover its quote.

    A chain that cannot state its own width REFUSES rather than falling back to
    the brain's sd -- a fallback here would silently restore the bug on exactly
    the illiquid names where it does the most damage.
    """
    if forecast.claim != "direction":
        return forecast.sd, "brain"
    implied = getattr(structure, "implied_move", 0.0) or 0.0
    if implied <= 0:
        raise ChainWidthUnavailable(
            f"{structure.kind}: this is a DIRECTION-only forecast, which is integrated at the "
            "chain's own width, and the chain quotes no implied move for this expiry. Refused "
            "rather than falling back to the brain's sd, which would turn a view about which "
            "way into a view about how far.")
    return implied * math.sqrt(math.pi / 2.0), "chain_implied_move"


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
    cash_beat = 0
    candidates = list(structures.enumerate_all(snapshot, expiry))
    # SHARES beside the options, for a brain that knows WHICH WAY. The same
    # gate, the same ranker; the instrument with no premium to pay wins only
    # when the shift alone clears one bid-ask (`alpha/engine/equity.py`).
    if forecast.claim == "direction" and forecast.centre != 0.0:
        try:
            share = share_structure(client, forecast, snapshot, expiry)
        except Exception as exc:                                          # noqa: BLE001
            share = None
            logger.warning("%s: share structure not built: %s", forecast.symbol, exc)
        if share is not None:
            candidates.append(share)
    for structure in candidates:
        try:
            sd_used, sd_note = effective_sd(forecast, structure)
        except ChainWidthUnavailable as exc:
            rejected.append((structure, sizing.SizingVerdict(False, 0.0, 0.0, str(exc))))
            continue
        verdict = sizing.size(
            structure, forecast.centre, sd_used, state,
            open_convex_risk=risk, conviction=forecast.conviction,
            risk_profile=risk_profile,
        )
        if not verdict.approved:
            rejected.append((structure, verdict))
            continue
        # THE GATE passed. Now THE RANKER: integrate the actual payoff over our
        # own forecast. A structure that cannot beat cash after the spread is
        # refused here, whatever its probability edge looked like.
        try:
            # A `direction` brain's sd is already the chain's own width, stated
            # over the structure's LIFE, so it must not be re-scaled by horizon.
            econ = payoff.economics(
                structure, snapshot.spot, forecast.centre, sd_used,
                horizon_days=None if forecast.claim == "direction" else forecast.horizon_days)
        except ValueError as exc:
            rejected.append((structure, sizing.SizingVerdict(
                False, 0.0, verdict.mdm_edge, f"payoff could not be integrated: {exc}")))
            continue
        verdict = replace(verdict, economics={**econ.as_dict(), "sd_used": round(sd_used, 5),
                                              "sd_source": sd_note},
                          reason=f"{verdict.reason} {econ.summary()}.")
        if econ.ev_usd <= 0.0:
            cash_beat += 1
            rejected.append((structure, replace(
                verdict, approved=False, risk_fraction=0.0,
                reason=(f"CASH beats it: cleared the MDM gate ({verdict.mdm_edge:+.1%}) but "
                        f"{econ.summary()} -- expected P&L is not positive after the spread. "
                        "Cash is a structure with EV exactly zero and it wins this comparison."))))
            continue
        if best is None or econ.ev_over_max_loss > best[1].economics["ev_over_max_loss"]:
            if best is not None:
                rejected.append((best[0], replace(
                    best[1], approved=False, risk_fraction=0.0,
                    reason=f"out-ranked on EV/max-loss by {structure.kind} "
                           f"({econ.ev_over_max_loss:+.0%} vs "
                           f"{best[1].economics['ev_over_max_loss']:+.0%}). {best[1].reason}")))
            best = (structure, verdict)
        else:
            rejected.append((structure, replace(
                verdict, approved=False, risk_fraction=0.0,
                reason=f"out-ranked on EV/max-loss by {best[0].kind} "
                       f"({best[1].economics['ev_over_max_loss']:+.0%} vs "
                       f"{econ.ev_over_max_loss:+.0%}). {verdict.reason}")))

    if best is None:
        with_econ = sum(1 for _, v in rejected if v.economics is not None)
        lead = "CASH: " if cash_beat and cash_beat == with_econ else ""
        why = sizing.SizingVerdict(
            False, 0.0, 0.0,
            f"{lead}{len(rejected)} structures enumerated at {expiry}, none cleared the gates"
            + (f" ({cash_beat} cleared MDM and lost to cash on EV)" if cash_beat else "") + ". "
            + (rejected[0][1].reason if rejected else "chain produced nothing tradeable."),
        )
        return None, why, snapshot, rejected
    return best[0], best[1], snapshot, rejected


def share_structure(client: AlpacaPaper, forecast: Forecast, snapshot, expiry: str):
    """One share of the underlying as a bounded structure, priced at the live stock quote."""
    symbol = forecast.symbol
    raw = (client.stock_quote([symbol]).get("quotes") or {}).get(symbol) or {}
    bid, ask = float(raw.get("bp") or 0.0), float(raw.get("ap") or 0.0)
    synthetic = None
    spot = snapshot.spot
    # The free IEX quote is routinely ONE-SIDED or stale: measured 26 Aug 00:15 ET,
    # NVDA bid 200.45 / ask 0 against a last trade of 212.96. A quote that is
    # missing a side, or whose sides sit more than SYNTHETIC_QUOTE_TOLERANCE from
    # the last trade, is replaced by the trade +/- a declared half-spread and
    # LABELLED as such in the snapshot, so the fill audit can tell the two apart.
    usable = (bid > 0 and ask > 0 and ask >= bid and spot > 0
              and abs(bid / spot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE
              and abs(ask / spot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE)
    if not usable:
        if spot <= 0:
            logger.info("%s: no spot and no two-sided stock quote; shares not built", symbol)
            return None
        synthetic = {"bid": bid, "ask": ask, "why": "one-sided or off-trade quote replaced by last trade +/- half-spread"}
        bid, ask = spot * (1.0 - SYNTHETIC_HALF_SPREAD), spot * (1.0 + SYNTHETIC_HALF_SPREAD)
        logger.info("%s: stock quote unusable (bid %s ask %s vs trade %.2f); using synthetic %.2f/%.2f",
                    symbol, synthetic["bid"], synthetic["ask"], spot, bid, ask)
    direction = "up" if forecast.centre > 0 else "down"
    shortable = True
    if direction == "down":
        asset = client.asset(symbol)
        shortable = bool(asset.get("shortable")) and bool(asset.get("easy_to_borrow"))
    dte = 1.0
    try:
        dte = max(0.5, (datetime.fromisoformat(expiry + "T20:00:00+00:00")
                        - datetime.now(timezone.utc)).total_seconds() / 86400.0)
    except ValueError:
        pass
    # The stress-loss charge is MEASURED from the name's own overnight gaps, and
    # raised to the chain's implied move when a scheduled event sits inside the
    # position's horizon (a print IS the gap).
    ev = forecast.evidence or {}
    today = datetime.now(timezone.utc).date().isoformat()
    event_pending = bool(ev.get("event_date")) and str(ev.get("event_date")) >= today
    bars = None
    try:
        from alpha.brains.vol_gap import _daily_bars

        bars = _daily_bars(client, symbol, equity.GAP_LOOKBACK + 20)
    except Exception as exc:                                              # noqa: BLE001
        logger.info("%s: bars for the gap allowance not read (%s); floor applies", symbol, exc)
    implied = snapshot.implied_move(expiry) or 0.0
    charge, charge_note = equity.stress_charge(bars, implied_move=implied, event_pending=event_pending)
    return equity.shares(
        symbol, spot=snapshot.spot, bid=bid, ask=ask, direction=direction,
        implied_move=implied, charge_fraction=charge, charge_note=charge_note,
        horizon_days=forecast.horizon_days, days_to_expiry=dte, shortable=shortable,
        quote={"symbol": symbol, "bid": bid, "ask": ask, "bid_size": raw.get("bs"),
               "ask_size": raw.get("as"), "quote_ts": raw.get("t"), "feed": config.stock_feed(),
               "shortable": shortable, "last_trade": spot, "synthetic": synthetic},
    )


#: A stock quote whose side is further than this from the last trade is not a quote.
SYNTHETIC_QUOTE_TOLERANCE = 0.005
#: Half-spread assumed when the quote is replaced by the last trade (5 bp a side;
#: NVDA's real spread is ~1 bp, so this over-charges rather than under-charges).
SYNTHETIC_HALF_SPREAD = 0.0005


def build_order(structure: sizing.Structure, contracts: int) -> dict:
    """Alpaca order payload. Single-leg or `mleg`, always a LIMIT, never market."""
    if contracts < 1:
        raise ValueError("refusing a zero-contract order")
    if structure.kind in equity.KINDS:
        symbol, side, _ratio = structure.legs[0]
        return {
            "symbol": symbol, "qty": str(contracts), "side": side,
            "type": "limit", "limit_price": f"{abs(structure.entry_cost):.2f}",
            "time_in_force": "day",
        }
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
    n = int(budget // structure.max_loss)
    if structure.kind in equity_mod.KINDS:
        # A 5%-of-spot declared worst case would let a 7% risk budget buy 140% of
        # the account. Shares are additionally capped by NOTIONAL.
        spot = float((structure.quote or {}).get("last_trade") or abs(structure.entry_cost))
        n = min(n, equity_mod.units_cap(spot, equity))
    return n


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
                     "claim": f.claim, "evidence": _compact(f.evidence), "note": note},
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
    book = book_mod.read(client)
    risk = book.fraction
    logger.info("pass: equity $%s, %.0f%% of window left, %.1f%% TRUE max loss already at risk "
                "(premium-paid view %.1f%%)", f"{state.equity:,.0f}",
                state.fraction_of_window_remaining * 100, risk * 100,
                (book.premium_paid_usd / state.equity * 100) if state.equity else 0.0)
    record_forecasts(forecasts, note=f"pass expiry={expiry} dry_run={dry_run}")
    role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None
    greeks = admission.book_greeks(client, account_role=role)
    if not greeks.derived:
        logger.warning("book greeks not derived: %s -- theta/stress admission checks will say so", greeks.note)
    scores = recovery.live_scores(account_role=role) if recovery.active() else {}
    if recovery.active():
        logger.info("%s", recovery.summary(scores))
    day = daybreak.read(client)
    if day.latched:
        for forecast in forecasts:
            result.considered += 1
            result.refuse("risk")
            _record(ledger.new_decision_id(forecast.symbol, forecast.brain), forecast, None, None,
                    None, state, action="refused", reason=day.reason)
        logger.error("%s", day.reason)
        return result
    logger.info("%s", day.reason)

    if book.unbounded:
        for forecast in forecasts:
            result.considered += 1
            result.refuse("risk")
            _record(ledger.new_decision_id(forecast.symbol, forecast.brain), forecast, None, None,
                    None, state, action="refused",
                    reason="BOOK UNBOUNDED: a short option leg has no protective long in this "
                           "account. No entry is sized against a worst case that cannot be "
                           "stated. " + book.summary())
        logger.error("book unbounded; every entry refused: %s", book.summary())
        return result

    by_symbol: dict[str, list[Forecast]] = {}
    for f in forecasts:
        by_symbol.setdefault(f.symbol, []).append(f)

    committed = 0.0
    # Event exposure starts from what the BOOK already carries, not from zero.
    node_committed: dict[str, float] = (
        {node: usd / state.equity for node, usd in book.by_node.items()} if state.equity else {})
    held = held_underlyings(client)
    in_flight = open_order_underlyings(client)
    for sym, n in in_flight.items():
        held[sym] = held.get(sym, 0) + n
    today = datetime.now(timezone.utc).date().isoformat()
    reserve_for = {d: v for d, v in EVENT_RESERVE.items() if d >= today}
    reserve_total = sum(reserve_for.values())
    for symbol, group in by_symbol.items():
        if symbol in held:
            # ONE POSITION PER SYMBOL is a property of the BOOK, not of a pass.
            # Without this the loop re-buys the same straddle every thirty
            # minutes until the aggregate cap binds -- which it did on 25 Aug
            # (QQQ straddle x4 became x8, a second NVDA condor at new strikes).
            for forecast in group:
                result.considered += 1
                result.refuse("already_held")
                pending = in_flight.get(symbol, 0)
                why = (f"{symbol} has {pending} order(s) IN FLIGHT at the venue and unfilled; "
                       "a resting entry is not a position and used to be invisible here, "
                       "which is how one symbol got two orders thirty minutes apart"
                       ) if pending else (
                    f"{symbol} already positioned in this book ({held[symbol]} legs); "
                    "exits decide when it is free again, not entries")
                _record(ledger.new_decision_id(forecast.symbol, forecast.brain), forecast, None, None, None, state,
                        action="refused", reason=why)
            continue
        evaluated = []
        for forecast in group:
            result.considered += 1
            decision_id = ledger.new_decision_id(forecast.symbol, forecast.brain)
            try:
                own_event = (forecast.evidence or {}).get("event_date")
                reserve = reserve_total - reserve_for.get(own_event, 0.0)
                structure, verdict, snapshot, alternatives = evaluate(
                    client, forecast, state=state, expiry=expiry,
                    risk_profile=risk_profile, open_risk=risk + committed + reserve,
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
                if verdict.reason.startswith("CASH:"):
                    result.cash += 1
                    result.refuse("cash")
                else:
                    # The arbiter declined. Whether that was the EVIDENCE (the
                    # forecast never earned a structure) or EXECUTION (nothing
                    # was quotable at an acceptable price) is the split that
                    # decides where the next session's work goes.
                    result.refuse("execution" if _priced_out(verdict.reason) else "evidence")
                _record(decision_id, forecast, None, verdict, snapshot, state,
                        action="refused", reason=verdict.reason)
                continue
            evaluated.append((decision_id, forecast, structure, verdict, snapshot))

        if not evaluated:
            continue
        demoted: dict[str, str] = {}
        for e in evaluated:
            why_not = recovery.refusal(e[1].brain, e[2].kind, scores)
            if why_not:
                demoted[e[0]] = why_not
        executable = [e for e in evaluated
                      if e[1].brain not in shadow_brains and e[0] not in demoted]
        # Across brains on one symbol the champion is the best EXPECTED ECONOMICS,
        # not the largest approved size -- size is the sizer's answer, not the ranker's.
        champion = max(executable, key=lambda e: _ev_ratio(e[3])) if executable else None
        for e in evaluated:
            if e is champion:
                continue
            d_id, forecast, structure, verdict, snapshot = e
            why = (demoted[d_id] if d_id in demoted else
                   "shadow-only brain" if forecast.brain in shadow_brains else
                   f"out-ranked by {champion[1].brain} at {_ev_ratio(champion[3]):+.0%} EV/max-loss "
                   f"vs {_ev_ratio(verdict):+.0%} on the same symbol")
            result.shadow += 1
            _record(d_id, forecast, structure, verdict, snapshot, state, action="shadow",
                    reason=why)
        if champion is None:
            continue
        node = event_node(champion[1])
        if node is not None:
            already = node_committed.get(node, 0.0)
            if already + champion[3].risk_fraction > EVENT_NODE_CAP:
                result.refuse("risk")
                _record(champion[0], champion[1], champion[2], champion[3], champion[4], state,
                        action="refused",
                        reason=(f"event node {node} already carries {already:.1%} of equity across "
                                f"the BOOK and this pass; adding {champion[3].risk_fraction:.1%} "
                                f"would exceed the {EVENT_NODE_CAP:.0%} node cap. Correlated "
                                "expressions of one event are one bet."))
                continue
        before = committed
        committed = _execute(client, result, *champion, state, committed, dry_run=dry_run,
                             book=book, greeks=greeks, risk_profile=risk_profile,
                             reserved=reserve_for)
        if node is not None:
            node_committed[node] = node_committed.get(node, 0.0) + (committed - before)
    return result


def _execute(client, result: PassResult, decision_id: str, forecast: Forecast,
             structure: sizing.Structure, verdict: sizing.SizingVerdict, snapshot,
             state: sizing.TournamentState, committed: float, *, dry_run: bool,
             book=None, greeks=None, risk_profile: str | None = None,
             reserved: dict[str, float] | None = None) -> float:
    """Size, build and (unless dry) send the champion. Returns updated `committed`.

    The aggregate ceiling binds WITHIN a pass: `committed` accumulates so six
    candidates cannot each pass a 50% test and total 300%. Then the PROSPECTIVE
    admission controller looks at the whole post-trade book (`alpha/admission.py`).
    """
    n = contracts_for(structure, verdict.risk_fraction, state.equity)
    if n >= 1 and book is not None:
        d_new, t_new = admission.structure_greeks(structure, n, snapshot)
        sig_new = (structure.implied_move / math.sqrt(max(1.0, structure.days_to_expiry))
                   if structure.implied_move else None)
        env = sizing.profile(risk_profile)
        adm = admission.admit(
            book, structure, n, equity=state.equity,
            aggregate_cap=env["aggregate"],
            per_underlying_cap=max(admission.PER_UNDERLYING_CAP, env["per_thesis"] * env["edge_scale_cap"]),
            committed_usd=committed * state.equity, own_event=event_node(forecast),
            reserved_events=reserved, greeks=greeks, new_delta_usd=d_new,
            new_theta_usd_per_day=t_new, new_daily_sigma=sig_new)
        verdict = replace(verdict, economics={**(verdict.economics or {}), "admission": adm.metrics})
        if not adm.ok:
            result.refuse("risk")
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="refused", reason=f"ADMISSION: {adm.reason}", contracts=n)
            logger.info("ADMISSION refused %s %s x%d: %s", forecast.symbol, structure.kind, n, adm.reason[:100])
            return committed
    if n < 1:
        result.refuse("capital")
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
        result.dry_run += 1
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


def _ev_ratio(verdict: sizing.SizingVerdict) -> float:
    return float((verdict.economics or {}).get("ev_over_max_loss") or 0.0)


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
    if structure.kind in equity_mod.KINDS and structure.quote:
        legs.append(dict(structure.quote))
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

    if not structure.legs or equity_mod.is_equity_symbol(structure.legs[0][0]):
        return ""
    return _decode_occ(structure.legs[0][0])[2]


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
        account_role=os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None,
        tournament_state={
            "equity": state.equity, "return": state.total_return,
            "phase": state.phase.value,
            "window_remaining": state.fraction_of_window_remaining,
        },
        llm=(forecast.evidence.get("shocks") or [{}])[0].get("llm") if forecast.evidence.get("shocks") else None,
        outcome={
            "event_node": event_node(forecast),
            "economics": verdict.economics if verdict else None,
            "horizon_days": forecast.horizon_days,
            # So a later reader -- the arbiter, the counterfactual -- can tell
            # WHICH width this row was gated at without re-deriving it.
            "claim": forecast.claim,
        },
    ))
