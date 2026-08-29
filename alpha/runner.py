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
bell, not at a close. Two halves, and until 2026-08-27 only one of them existed:

* EXIT -- real from the start. `alpha/exits.py` liquidates at 10:45 ET on judging
  day and that verdict outranks a winning thesis.
* ENTRY -- this docstring used to claim `must_close_by` was "threaded through
  every entry". It was not an identifier anywhere in the repo; it appeared in
  that sentence and nowhere else, next to a `MAX_EXPIRY_SLACK_DAYS` that nothing
  read. `check_expiry_against_deadline` is the guard the sentence described,
  and `scripts/run_pass` calls it before a single chain is fetched.
"""

from __future__ import annotations

import math
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from alpha import admission
from alpha import book as book_mod
from alpha import claims, concentration, config, crossbook, daybreak, drivers, ledger, recovery, refuted
from alpha.brains.base import Forecast
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data import chain as chain_mod
from alpha.engine import equity, payoff, sizing, structures
from alpha.engine import equity as equity_mod

logger = logging.getLogger(__name__)

KICKOFF = datetime.fromisoformat(config.COMPETITION["kickoff_utc"].replace("Z", "+00:00"))
DEADLINE = datetime.fromisoformat(config.COMPETITION["deadline_utc"].replace("Z", "+00:00"))

#: How far past the judging deadline an expiry may sit. 0.0 = it may not.
#:
#: This constant existed from the beginning and was USED NOWHERE, while the
#: module docstring above claimed `must_close_by` was "threaded through every
#: entry". `must_close_by` is not an identifier in this repo -- it appears in
#: that sentence and nowhere else. Found by `python -m scripts.reachability` on
#: 2026-08-27, the same audit that found `shape.py` had no importer.
#:
#: The EXIT side was always real: `alpha/exits.py` liquidates at 10:45 ET on
#: judging day and that verdict outranks a winning thesis. So the failure mode
#: was never a stuck position -- it was paying a full option bid-ask on the last
#: morning to close something the judge would never see resolve, chosen by an
#: `--expiry` flag nothing checked.
MAX_EXPIRY_SLACK_DAYS = 0.0


class ExpiryPastDeadline(ValueError):
    """The chosen expiry outlives the judged window."""


def check_expiry_against_deadline(expiry: str, *, slack_days: float = MAX_EXPIRY_SLACK_DAYS,
                                  deadline: datetime | None = None) -> None:
    """Refuse an expiry the contest will not live to see.

    An option expiring BEFORE the deadline is ordinary and fine. One expiring
    after it must be SOLD at 10:45 ET on the final morning, into whatever spread
    exists then, having been bought for a thesis that never completed.
    """
    dl = deadline or DEADLINE
    try:
        exp = datetime.fromisoformat(expiry).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ExpiryPastDeadline(f"expiry {expiry!r} is not a date (YYYY-MM-DD).") from exc
    latest = dl + timedelta(days=slack_days)
    if exp.date() > latest.date():
        raise ExpiryPastDeadline(
            f"expiry {expiry} is after the judging deadline {dl.date()} "
            f"(slack {slack_days:g}d). A structure that outlives the judged window has to be "
            f"SOLD at {LIQUIDATE_BY_ET_TEXT} ET on the final morning, into whatever spread "
            "exists then, for a thesis that never got to complete. Choose an expiry inside "
            "the window, or pass --allow-expiry-past-deadline and say why in the handoff.")


#: Printed in the refusal above. Kept as text so this module does not import
#: `exits` (which imports the broker) merely to format a message.
LIQUIDATE_BY_ET_TEXT = "10:45"

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
    "stopped_today",      # a protective stop closed this symbol earlier in the session
    "opening_range",      # shares are not bought in the first 15 minutes (28 Aug: stops at 09:36)
    "convex_rule",        # long premium refused on DTE / break-even vs the market's own width
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


def gross_notional_by_symbol(client: AlpacaPaper) -> dict[str, float] | None:
    """|market_value| per UNDERLYING across every open position, or None.

    Options are folded onto their underlying: a call on QUBT and QUBT shares
    are the same driver and the same name, and splitting them would let a book
    carry a full name twice under one cap.
    """
    try:
        out: dict[str, float] = {}
        for pos in client.positions():
            mv = pos.get("market_value")
            if mv is None:
                qty = float(pos.get("qty") or 0.0)
                px = float(pos.get("current_price") or pos.get("avg_entry_price") or 0.0)
                mult = 100.0 if (pos.get("asset_class") == "us_option") else 1.0
                mv = qty * px * mult
            sym = concentration.underlying_of(str(pos.get("symbol") or "").upper())
            if sym:
                out[sym] = out.get(sym, 0.0) + abs(float(mv))
        return out
    except Exception as exc:                                            # noqa: BLE001
        logger.warning("gross notional unreadable (%s); admission will refuse on GROSS", exc)
        return None


def gross_notional_usd(client: AlpacaPaper) -> float | None:
    """Σ|market_value| across every open position, or None when it cannot be read.

    The number the gross cap binds on. None is a STATE the admission controller
    refuses against; it is never coerced to zero, because an unreadable book is
    not a flat book (2026-08-29)."""
    by_sym = gross_notional_by_symbol(client)
    return None if by_sym is None else sum(by_sym.values())


def in_opening_range(now_et=None) -> bool:
    """True inside the first 15 minutes of the regular session (09:30-09:45 ET).

    28 Aug: every share entry filled 09:30-09:33 and every 3% stop fired by
    09:48 while the index moved 0.1%. The opening print is the most expensive
    fill of the day and its range is wider than any stop we run.

    `now_et` IS THE POINT, not a convenience. The first cut of this guard read
    the wall clock with no seam and was called from inside `_execute`, so
    between 09:30 and 09:45 ET -- on ANY day, including a Saturday -- three
    suites went red and went green again at 09:45 with nothing changed but the
    time. A guard whose value cannot be supplied is a guard that cannot be
    tested, and this project has now paid for that class four times (three
    literal option expiries, then this). Every caller may pass a clock; the
    same shape as `exits.deadline_liquidation_due(now=...)`.

    Weekends are NOT a session. Saturday 09:34 ET is not the opening range of
    anything, and treating it as one is how the guard reached the test suite."""
    from alpha import exits as _exits
    t_et = now_et or _exits.now_et()
    if t_et.weekday() >= 5:
        return False
    t = t_et.time()
    return (t.hour == 9 and 30 <= t.minute < 45)


def _driver_args(gross: dict | None, symbol: str, risk_profile: str | None) -> dict:
    """The driver kwargs for `admission.admit`, or {} when drivers are unknown.

    `by_driver` is None exactly when the book's notional could not be read --
    and in that state the GROSS check already refuses the order with a named
    reason, so returning {} here does not open a hole: it avoids stacking a
    second, vaguer refusal on top of the specific one.
    """
    if not isinstance(gross, dict) or not isinstance(gross.get("by_driver"), dict):
        return {}
    d = (gross.get("driver_of") or {}).get(symbol.upper()) or drivers.declared_driver(symbol)
    return {
        "driver": d,
        "driver_cap": drivers.cap_fraction(sizing.gross_cap(risk_profile)),
        "driver_gross_usd": float(gross["by_driver"].get(d, 0.0)),
        "driver_note": str(gross.get("driver_note") or ""),
    }


def structure_notional_usd(structure: sizing.Structure, n: int) -> float:
    """Dollar notional this order adds to gross.

    `entry_cost` is PER UNIT in dollars for every kind -- one share for share
    kinds, one contract (already x100) for option structures -- so notional is
    |entry_cost| x n in both cases. Shares prefer the last trade when the quote
    carries one, which is what the venue's market_value will be marked at."""
    if structure.kind in equity_mod.KINDS:
        spot = float((structure.quote or {}).get("last_trade") or abs(structure.entry_cost))
        return abs(spot) * n
    return abs(float(structure.entry_cost or 0.0)) * n


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
    # A WIDTH CLAIM STATED AS A MULTIPLE OF THE CHAIN, resolved here.
    #
    # `alpha/human.py` lets a person say the chain is 25% too wide or too narrow.
    # That is a claim ABOUT the chain, so it can only be evaluated against the
    # chain -- and against THIS structure's chain, not one number picked at
    # forecast time. Its first implementation multiplied the raw implied move by
    # the tilt, which (a) skipped the sqrt(pi/2) that turns E|move| into a sigma,
    # making a "25% wider" claim numerically equal to the chain's own sigma, and
    # (b) was then rescaled AGAIN by horizon_days. A thesis saying the chain
    # OVERPRICES the move came out buying a straddle.
    mult = (forecast.evidence or {}).get("width_multiplier")
    if mult:
        implied = getattr(structure, "implied_move", 0.0) or 0.0
        if implied <= 0:
            raise ChainWidthUnavailable(
                f"{structure.kind}: this forecast claims the CHAIN's width is wrong by a factor "
                f"of {mult:g}, and the chain quotes no implied move for this expiry. There is "
                "nothing to be wrong about. Refused rather than substituting a realised-vol "
                "estimate -- that substitution is what made every long option look cheap.")
        return implied * math.sqrt(math.pi / 2.0) * float(mult), f"chain_implied_move x{mult:g}"

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
    objective, _objective_why = rank_objective(state)
    band = max(4.0 * forecast.sd, 0.06)
    spot_hint = forecast.evidence.get("last_close")
    lo = hi = None
    if spot_hint:
        lo, hi = spot_hint * (1 - band), spot_hint * (1 + band)
    # A PAIR is equity-only. A wide-universe printer (LUCK, P, DY, HQY on 28 Aug)
    # often has no listed options at the contest expiry, and a chain refusal
    # there was killing the whole evaluation of a structure that never needed a
    # chain. So the chain is fetched, and for a pair forecast its absence is a
    # note on the row rather than an error: the option candidates are simply
    # empty and the pair is built from stock quotes.
    wants_pair = (forecast.claim == "direction" and forecast.centre != 0.0
                  and (forecast.evidence or {}).get("expression") == equity.PAIR_KIND)
    try:
        snapshot = chain_mod.fetch(
            client, forecast.symbol, expiry_from=expiry, expiry_to=expiry,
            strike_from=lo, strike_to=hi,
        )
    except chain_mod.ChainRefusal:
        # Shares need no chain either. A DIRECTION forecast on a name with no
        # listed contracts at the contest expiry (FLNC, NTLA on 28 Aug) was
        # dying here before its share structure was ever built; the option
        # candidates are simply empty and the row says why.
        if not wants_pair and forecast.claim != "direction":
            raise
        snapshot = None
        logger.info("%s: no chain at %s; %s forecast proceeds on stock quotes only", forecast.symbol, expiry,
                    "pair" if wants_pair else "direction")

    risk = open_risk if open_risk is not None else open_convex_risk(client)
    best = None
    rejected = []
    cash_beat = 0
    candidates = list(structures.enumerate_all(snapshot, expiry)) if snapshot is not None else []
    # SHARES beside the options, for a brain that knows WHICH WAY. The same
    # gate, the same ranker; the instrument with no premium to pay wins only
    # when the shift alone clears one bid-ask (`alpha/engine/equity.py`).
    if forecast.claim == "direction" and forecast.centre != 0.0:
        # A forecast whose evidence says `expression: pair_short_vs_iwm` was
        # measured as a RELATIVE move (short loser / long IWM); the unhedged
        # short of it is worth nothing in simple returns, so `short_shares` is
        # NOT enumerated for it -- only the pair is.
        try:
            share = (pair_structure(client, forecast, snapshot, expiry) if wants_pair
                     else share_structure(client, forecast, snapshot, expiry))
        except Exception as exc:                                          # noqa: BLE001
            share = None
            logger.warning("%s: %s structure not built: %s", forecast.symbol,
                           "pair" if wants_pair else "share", exc)
        if share is not None:
            candidates.append(share)
    # A mandate may restrict the KINDS it will hold (`alpha/fleet.py`, e.g. the
    # options-only account). Empty = every kind. A kind filtered here is a
    # declared choice of the account, not a refusal, so it is not logged as one.
    allowed = {k.strip() for k in os.getenv("AAT_STRUCTURE_KINDS", "").split(",") if k.strip()}
    if allowed:
        candidates = [c for c in candidates if getattr(c, "kind", None) in allowed]
    # -- CLAIM_EXPRESSION_MATRIX (alpha/claims.py) ---------------------------
    # Structural, and BEFORE anything is priced. `effective_sd` already makes a
    # condor score badly for a directional brain; this makes it inadmissible
    # regardless of how it scores. The two halves normally agree, and when they
    # stop agreeing the rejected list says so instead of the book finding out.
    inexpressible = [s for s in candidates if not claims.admissible(forecast.claim, s.kind)]
    for s in inexpressible:
        rejected.append((s, sizing.SizingVerdict(
            False, 0.0, 0.0, f"CLAIM {forecast.claim}: {claims.why_not(forecast.claim, s.kind)}")))
    candidates = [s for s in candidates if claims.admissible(forecast.claim, s.kind)]

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
                structure, _spot_for(snapshot, structure), forecast.centre, sd_used,
                # A sd that CAME FROM THE CHAIN is already stated over the
                # structure's own life. Rescaling it by a declared horizon
                # inflates it by sqrt(horizon/life) -- a 2-day view on a 1-day
                # option becomes sqrt(2) wider, which turned a "the chain is too
                # expensive" thesis into a long straddle. Keyed off where the sd
                # came from, not off the claim word, so every chain-derived path
                # gets it.
                horizon_days=None if sd_note.startswith("chain") else forecast.horizon_days)
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
        mine = _rank_value(structure, verdict.economics, objective)
        if best is None or mine > _rank_value(best[0], best[1].economics, objective):
            if best is not None:
                rejected.append((best[0], replace(
                    best[1], approved=False, risk_fraction=0.0,
                    reason=f"out-ranked on {objective}/max-loss by {structure.kind} "
                           f"({mine:+.0%} vs "
                           f"{_rank_value(best[0], best[1].economics, objective):+.0%}; "
                           f"EV {econ.ev_over_max_loss:+.0%} vs "
                           f"{best[1].economics['ev_over_max_loss']:+.0%}). {best[1].reason}")))
            best = (structure, verdict)
        else:
            rejected.append((structure, replace(
                verdict, approved=False, risk_fraction=0.0,
                reason=f"out-ranked on {objective}/max-loss by {best[0].kind} "
                       f"({_rank_value(best[0], best[1].economics, objective):+.0%} vs {mine:+.0%}; "
                       f"EV {best[1].economics['ev_over_max_loss']:+.0%} vs "
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
    # No chain (FLNC, NTLA at the contest expiry, 28 Aug): spot comes from the
    # stock's own last trade, exactly as `pair_structure` does. Shares never
    # needed a chain; only the spot was being read off one.
    spot = snapshot.spot if snapshot is not None else 0.0
    if spot <= 0:
        try:
            snap = client._request("GET", f"/v2/stocks/{symbol}/snapshot", base=config.data_url(),
                                   params={"feed": config.stock_feed()}) or {}
            spot = float(((snap.get("latestTrade") or {}).get("p")) or 0.0)
        except BrokerRefusal:
            spot = 0.0
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


def _stock_quote_or_synthetic(client: AlpacaPaper, symbol: str, spot: float):
    """(bid, ask, raw, synthetic) with the same one-sided/off-trade repair as shares."""
    raw = (client.stock_quote([symbol]).get("quotes") or {}).get(symbol) or {}
    bid, ask = float(raw.get("bp") or 0.0), float(raw.get("ap") or 0.0)
    synthetic = None
    usable = (bid > 0 and ask > 0 and ask >= bid and spot > 0
              and abs(bid / spot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE
              and abs(ask / spot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE)
    if not usable:
        if spot <= 0:
            return 0.0, 0.0, raw, None
        synthetic = {"bid": bid, "ask": ask, "why": "one-sided or off-trade quote replaced by last trade +/- half-spread"}
        bid, ask = spot * (1.0 - SYNTHETIC_HALF_SPREAD), spot * (1.0 + SYNTHETIC_HALF_SPREAD)
    return bid, ask, raw, synthetic


def pair_structure(client: AlpacaPaper, forecast: Forecast, snapshot, expiry: str):
    """Short one share of the loser against dollar-neutral IWM (`equity.pair_short_vs_hedge`)."""
    symbol = forecast.symbol
    hedge = equity.DEFAULT_HEDGE
    spot = snapshot.spot if snapshot is not None else 0.0
    if spot <= 0:
        try:
            snap = client._request("GET", f"/v2/stocks/{symbol}/snapshot", base=config.data_url(),
                                   params={"feed": config.stock_feed()}) or {}
            spot = float(((snap.get("latestTrade") or {}).get("p")) or 0.0)
        except BrokerRefusal:
            spot = 0.0
    bid, ask, raw, synthetic = _stock_quote_or_synthetic(client, symbol, spot)
    if bid <= 0:
        logger.info("%s: no spot and no two-sided stock quote; pair not built", symbol)
        return None
    asset = client.asset(symbol)
    shortable = bool(asset.get("shortable")) and bool(asset.get("easy_to_borrow"))
    hraw = (client.stock_quote([hedge]).get("quotes") or {}).get(hedge) or {}
    hbid, hask = float(hraw.get("bp") or 0.0), float(hraw.get("ap") or 0.0)
    hspot = 0.5 * (hbid + hask) if hbid > 0 and hask >= hbid else 0.0
    if hspot <= 0:
        try:
            snap = client._request("GET", f"/v2/stocks/{hedge}/snapshot", base=config.data_url(),
                                   params={"feed": config.stock_feed()}) or {}
            hspot = float(((snap.get("latestTrade") or {}).get("p")) or 0.0)
        except BrokerRefusal:
            hspot = 0.0
    hsyn = None
    if hspot > 0 and not (hbid > 0 and hask >= hbid
                          and abs(hbid / hspot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE
                          and abs(hask / hspot - 1.0) <= SYNTHETIC_QUOTE_TOLERANCE):
        hsyn = {"bid": hbid, "ask": hask, "why": "hedge quote one-sided or off-trade; last trade +/- half-spread"}
        hbid, hask = hspot * (1.0 - SYNTHETIC_HALF_SPREAD), hspot * (1.0 + SYNTHETIC_HALF_SPREAD)
    dte = 1.0
    try:
        dte = max(0.5, (datetime.fromisoformat(expiry + "T20:00:00+00:00")
                        - datetime.now(timezone.utc)).total_seconds() / 86400.0)
    except ValueError:
        pass
    ev = forecast.evidence or {}
    today = datetime.now(timezone.utc).date().isoformat()
    event_pending = bool(ev.get("event_date")) and str(ev.get("event_date")) >= today
    bars = hbars = None
    try:
        from alpha.brains.vol_gap import _daily_bars

        bars = _daily_bars(client, symbol, equity.GAP_LOOKBACK + 20)
        hbars = _daily_bars(client, hedge, equity.GAP_LOOKBACK + 20)
    except Exception as exc:                                              # noqa: BLE001
        logger.info("%s: bars for the pair gap allowance not read (%s); floor applies", symbol, exc)
    implied = (snapshot.implied_move(expiry) or 0.0) if snapshot is not None else 0.0
    return equity.pair_short_vs_hedge(
        symbol, spot=spot, bid=bid, ask=ask, hedge_symbol=hedge, hedge_spot=hspot,
        hedge_bid=hbid, hedge_ask=hask, bars=bars, hedge_bars=hbars,
        implied_move=implied, event_pending=event_pending,
        horizon_days=forecast.horizon_days, days_to_expiry=dte, shortable=shortable,
        quote={"symbol": symbol, "bid": bid, "ask": ask, "bid_size": raw.get("bs"),
               "ask_size": raw.get("as"), "quote_ts": raw.get("t"), "feed": config.stock_feed(),
               "shortable": shortable, "last_trade": spot, "synthetic": synthetic,
               "hedge_synthetic": hsyn, "hedge_quote_ts": hraw.get("t")},
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
    if structure.kind == equity.PAIR_KIND:
        return build_pair_orders(structure, contracts)
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


def build_pair_orders(structure: sizing.Structure, units: int) -> list[dict]:
    """TWO equity limit-day orders: short leg at the bid, hedge leg at the ask.

    Alpaca has no multi-leg EQUITY order, so a pair is two orders under ONE
    decision id (leg suffixes on the client_order_id keep the replay collision).
    The hedge share count is rounded once here, on the whole position."""
    q = structure.quote or {}
    ratio = float(q.get("hedge_ratio") or 0.0)
    hedge = str(q.get("hedge_symbol") or equity.DEFAULT_HEDGE)
    h = equity.hedge_shares(units, ratio)
    if h < 1:
        raise ValueError("pair: hedge share count rounds to zero")
    short_sym = structure.legs[0][0]
    return [
        {"symbol": short_sym, "qty": str(units), "side": "sell", "type": "limit",
         "limit_price": f"{abs(structure.entry_cost):.2f}", "time_in_force": "day"},
        {"symbol": hedge, "qty": str(h), "side": "buy", "type": "limit",
         "limit_price": f"{float(q.get('hedge_ask') or 0.0):.2f}", "time_in_force": "day"},
    ]


def pair_order_record(orders: list[dict]) -> dict:
    """The ledger's `order` field for a pair: ONE dict (every reader does `.get`),
    carrying both payloads and the hedge share count."""
    return {"pair": True, "qty": orders[0]["qty"], "symbol": orders[0]["symbol"],
            "side": orders[0]["side"], "hedge_symbol": orders[1]["symbol"],
            "hedge_qty": orders[1]["qty"], "legs_orders": orders}


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
             shadow_brains: tuple[str, ...] = (),
             now_et=None) -> PassResult:
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
    # WHICH NAMES HAVE A PRINT AHEAD, pooled across every brain in this pass.
    # Pooled deliberately: on 25 Aug `vol_gap` opened NVDA condors carrying no
    # event in its own evidence while `event_move` knew the print was on the
    # 26th. The book does not care which brain knew -- the same reasoning the
    # arbiter already uses in `_event_pending`.
    _today = datetime.now(timezone.utc).date().isoformat()
    printing: set[str] = set()
    for f in forecasts:
        d = (f.evidence or {}).get("event_date")
        if d and str(d) >= _today:
            printing.add(f.symbol.upper())
    role = os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower() or None
    greeks = admission.book_greeks(client, account_role=role)
    if not greeks.derived:
        logger.warning("book greeks not derived: %s -- theta/stress admission checks will say so", greeks.note)
    # ONCE PER CYCLE, not once per order: one batched bars call feeds the
    # book-wide concentration limit for every admission in this pass. Putting a
    # network round trip inside the per-order path would bolt a new failure mode
    # onto the one path that must not fail.
    book_n_risk = admission.book_n_risk(book, client) if book is not None else None
    logger.info("book effective N by RISK: %s",
                f"{book_n_risk:.2f}" if book_n_risk is not None
                else "UNMEASURED (binds once the book holds "
                     f"{admission.book_limits.DIVERSIFICATION_BINDS_AT}+ positions)")
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
    # Gross notional is measured ONCE per pass and accumulated as orders go out.
    gross_by_sym = gross_notional_by_symbol(client)
    gross = {"usd": None if gross_by_sym is None else sum(gross_by_sym.values()),
             "committed": 0.0}
    # DRIVER taxonomy for this pass (P0.4). One batched bars call, made HERE and
    # never inside the per-order path -- the same discipline `book_n_risk` keeps,
    # for the same reason: the order path must not grow a network failure mode.
    _driver_syms = sorted(set(by_symbol) | set(gross_by_sym or {}))
    _returns: dict[str, list[float]] = {}
    if len(_driver_syms) > 1:
        try:
            _start = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
            _returns = drivers.returns_from_bars(
                client.stock_bars_multi(_driver_syms, start=_start, timeframe="1Day"))
        except Exception as exc:                                        # noqa: BLE001
            logger.warning("driver correlations unmeasured (%s); the DECLARED taxonomy alone "
                           "decides drivers this pass, and it can only UNDER-count them", exc)
    _driver_of, _driver_note = drivers.resolve(_driver_syms, _returns)
    gross["driver_of"] = _driver_of
    gross["driver_note"] = _driver_note
    gross["by_driver"] = (None if gross_by_sym is None
                          else drivers.notional_by_driver(gross_by_sym, _driver_of))
    logger.info("drivers this pass: %d name(s) -> %d driver(s) (%s)",
                len(_driver_syms), len(set(_driver_of.values())), _driver_note)
    # CROSS-BOOK (P0.2 remainder). Only the convex book asks, because only it is
    # forbidden from expressing a thesis another book already holds outright.
    # ONCE per pass: these are network reads of other accounts.
    cross: dict = {"held": set(), "notes": [], "status": "not applicable (not a convex book)"}
    if (risk_profile or "").strip().lower() == "convex":
        _h, _n = crossbook.held_by_peers(os.getenv("AAT_ACCOUNT_ROLE", "").strip().lower())
        cross = {"held": _h, "notes": _n, "status": crossbook.status(_h, _n)}
        logger.info("cross-book: %s", cross["status"])
    in_flight = open_order_underlyings(client)
    for sym, n in in_flight.items():
        held[sym] = held.get(sym, 0) + n
    today = datetime.now(timezone.utc).date().isoformat()
    reserve_for = {d: v for d, v in EVENT_RESERVE.items() if d >= today}
    reserve_total = sum(reserve_for.values())
    from alpha import protect as _protect
    try:
        stopped = _protect.stopped_today(client)
    except Exception as exc:                                            # noqa: BLE001
        stopped = set()
        logger.warning("stopped_today unreadable (%s); re-entry guard is OFF this pass", exc)
    for symbol, group in by_symbol.items():
        if symbol in stopped and symbol not in held:
            # A stop that fired is the book's most recent OPINION on this name;
            # re-buying it thirty minutes later at the same rule is churn with
            # a fee. 28 Aug: nine names stopped within eleven minutes, and the
            # next pass would have re-bought all nine. Tomorrow is a new day.
            for forecast in group:
                result.considered += 1
                result.refuse("stopped_today")
                _record(ledger.new_decision_id(forecast.symbol, forecast.brain), forecast, None, None, None, state,
                        action="refused", reason=f"{symbol}: a protective stop closed this name earlier today; "
                                                 "no same-session re-entry -- tomorrow is a new decision")
            continue
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
        objective, objective_why = rank_objective(state)
        champion = (max(executable, key=lambda e: _rank_value(e[2], e[3].economics, objective))
                    if executable else None)
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
        # THE RANKER OPTIMISES THE MEAN, AND THE CONTEST IS FIVE SESSIONS LONG.
        #
        # `_ev_ratio` reads `ev_over_max_loss` -- the arithmetic mean. Measured
        # on a live NVDA chain on 2026-08-27 with a +0.72% directional forecast,
        # that picks a `long_call` at +38% EV with **P(profit) 33% and a median
        # of -$137**, over `long_shares` at +12% EV with P(profit) 56% and a
        # median of +$1. Both numbers are right; they answer different questions.
        # Over a long series the mean is the one that matters. Over a handful of
        # sequential compounding decisions, terminal wealth follows the median.
        #
        # This does NOT change the choice -- see
        # docs/FINDING_2026-08-27_THE_RANKER_OPTIMISES_THE_MEAN.md. Editing the
        # objective function of a system hours before it is judged is how a
        # seventh instrument defect gets made. It makes the trade-off VISIBLE at
        # the moment it is taken, because `P(profit) 33%` is already computed,
        # already on the ledger row, and was being read by nobody.
        _ce = champion[3].economics or {}
        _p_win = _ce.get("p_profit")
        logger.info("RANKED ON %s -- %s", objective.upper(), objective_why)
        if objective == "mean" and _p_win is not None and _p_win < 0.5:
            _better = [(e[2].kind, (e[3].economics or {}).get("p_profit"))
                       for e in evaluated
                       if e is not champion and (e[3].economics or {}).get("p_profit", 0) >= 0.5]
            logger.warning(
                "MEAN-RANKED %s %s: chosen on EV %+.0f%% with P(profit) %.0f%% and median "
                "%s%s", champion[1].symbol, champion[2].kind, 100 * _ev_ratio(champion[3]),
                100 * _p_win,
                _fmt_usd(_ce.get("median_usd")),
                (f"; a majority-win alternative existed: "
                 f"{', '.join(f'{k} P(profit) {100*p:.0f}%' for k, p in _better)}")
                if _better else "; no majority-win alternative was available")
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
                             reserved=reserve_for, n_risk=book_n_risk, printing=printing,
                             gross=gross, now_et=now_et, cross=cross)
        if node is not None:
            node_committed[node] = node_committed.get(node, 0.0) + (committed - before)
    return result


def _execute(client, result: PassResult, decision_id: str, forecast: Forecast,
             structure: sizing.Structure, verdict: sizing.SizingVerdict, snapshot,
             state: sizing.TournamentState, committed: float, *, dry_run: bool,
             book=None, greeks=None, risk_profile: str | None = None,
             reserved: dict[str, float] | None = None,
             n_risk: float | None = None,
             printing: set | None = None,
             gross: dict | None = None,
             now_et=None, cross: dict | None = None) -> float:
    """Size, build and (unless dry) send the champion. Returns updated `committed`.

    The aggregate ceiling binds WITHIN a pass: `committed` accumulates so six
    candidates cannot each pass a 50% test and total 300%. Then the PROSPECTIVE
    admission controller looks at the whole post-trade book (`alpha/admission.py`).
    """
    # -- REFUTED ROUTES (alpha/refuted.py) -----------------------------------
    # Checked FIRST, before sizing: a route we have already measured as negative
    # should not be priced, sized or admitted, only declined. On 25 Aug this book
    # opened a long AMD straddle into NVDA's print (-$4,125) and long NVDA
    # premium into NVDA's own print -- both routes this project had killed in
    # writing, with 290 legs and an 0-for-8 respectively. The findings existed;
    # the code did not know them.
    _printing = {s.upper() for s in (printing or set())}
    _refusal = refuted.check(
        symbol=forecast.symbol, kind=structure.kind,
        event_ahead_on_symbol=forecast.symbol.upper() in _printing,
        originators_printing=refuted.peers_printing(forecast.symbol, _printing),
        # The index-straddle sample is a WEEKLY straddle held to expiry. Without
        # this the rule refuses a 0DTE structure too, and the 0DTE SPY straddle
        # into NFP is the best-evidenced trade in the contest window.
        days_to_expiry=getattr(structure, "days_to_expiry", None))
    if _refusal is not None:
        result.refuse("evidence")
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="refused", reason=_refusal.line(), contracts=0)
        logger.info("REFUTED %s %s: %s", forecast.symbol, structure.kind, _refusal.route)
        return committed

    n = contracts_for(structure, verdict.risk_fraction, state.equity)
    profile_key = (risk_profile or "").strip().lower()
    # -- OPENING RANGE (2026-08-29): no share entry 09:30-09:45 ET ------------
    if structure.kind in equity_mod.KINDS and in_opening_range(now_et):
        result.refuse("opening_range")
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="refused", contracts=n,
                reason=("OPENING RANGE: shares are not bought in the first 15 minutes. On 28 Aug "
                        "every entry filled 09:30-09:33 and every 3% stop fired by 09:48 on a "
                        "0.1% index move. The next pass is after 09:45."))
        return committed
    # -- CONVEX RULES (2026-08-29): long premium needs time and a fair break-even
    if profile_key == "convex" and structure.kind not in equity_mod.KINDS:
        dte = float(structure.days_to_expiry or 0.0)
        be = abs(float(structure.breakeven_move or 0.0))
        width = abs(float(structure.implied_move or 0.0))
        why = None
        if dte < sizing.CONVEX_MIN_DTE:
            why = (f"{dte:.0f} DTE < {sizing.CONVEX_MIN_DTE:.0f}: a long option inside the horizon "
                   "is a lottery ticket on the print (28 Aug: five 5-DTE calls, -60% each).")
        elif width > 0 and be > sizing.CONVEX_MAX_BREAKEVEN_TO_IMPLIED * width:
            why = (f"break-even {be:.1%} exceeds the market's own expected move {width:.1%}: "
                   "priced to lose on the median path.")
        if why:
            result.refuse("convex_rule")
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="refused", contracts=n, reason="CONVEX RULE: " + why)
            return committed
        # ONE BET, ONE INSTRUMENT: the convex book may not buy premium on a name
        # another fleet book already holds outright (28 Aug: the basket book's
        # twelve theme names and the convex book's five calls on the same names
        # were reported as independent selectors and lost together).
        _cross = cross or {}
        _line = crossbook.overlap_refusal(forecast.symbol, _cross.get("held") or set(),
                                          _cross.get("notes") or [])
        if _line:
            result.refuse("cross_book")
            _record(decision_id, forecast, structure, verdict, snapshot, state,
                    action="refused", contracts=n, reason=_line)
            logger.info("CROSS-BOOK refused %s: held by a peer book", forecast.symbol)
            return committed
        verdict = replace(verdict, economics={**(verdict.economics or {}),
                                              "cross_book": _cross.get("status", "not checked")})
    add_notional = structure_notional_usd(structure, n) if n >= 1 else 0.0
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
            new_theta_usd_per_day=t_new, new_daily_sigma=sig_new, n_risk=n_risk,
            gross_cap=sizing.gross_cap(risk_profile),
            gross_usd=(gross or {}).get("usd"),
            add_notional_usd=add_notional,
            committed_notional_usd=float((gross or {}).get("committed") or 0.0),
            **_driver_args(gross, forecast.symbol, risk_profile))
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

    built = build_order(structure, n)
    pair_orders = built if isinstance(built, list) else None
    order = pair_order_record(built) if pair_orders else built
    add = (structure.max_loss * n) / state.equity if state.equity else 0.0
    if gross is not None:
        gross["committed"] = float(gross.get("committed") or 0.0) + add_notional
        _by_driver = gross.get("by_driver")
        if isinstance(_by_driver, dict):
            _d = (gross.get("driver_of") or {}).get(forecast.symbol.upper())                 or drivers.declared_driver(forecast.symbol)
            _by_driver[_d] = _by_driver.get(_d, 0.0) + add_notional
    if dry_run:
        result.dry_run += 1
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="dry_run", reason="dry run: order built and not sent", order=order,
                contracts=n)
        logger.info("DRY  %s %s %s x%d  risk %.2f%%", forecast.brain, forecast.symbol,
                    structure.kind, n, verdict.risk_fraction * 100)
        return committed + add

    # INTENT BEFORE POST. The order below is written to the ledger twice: once as
    # an `intent` before it is sent, once as `submitted` after the broker accepts
    # it. The two rows are not redundant -- the gap between them is where an order
    # can exist at the venue with nothing local describing it.
    #
    # That is not hypothetical. On 2026-08-27 `seed_market` POSTed successfully
    # and then raised inside ledger.record, leaving a real 126-share SPY position
    # with no row. Recovery needed the decision_id to find the order by its
    # client_order_id -- and the decision_id only existed in the row that was
    # never written. Persisting intent first breaks that circularity: after any
    # crash, every order that COULD exist has a local row naming the
    # client_order_id to reconcile against (`python -m scripts.reconcile`).
    #
    # Safe to add mid-flight: every consumer of the ledger filters on explicit
    # action values ("submitted", or a named tuple), so an `intent` row is
    # invisible to the book, exits, recovery, counterfactual and fill_audit.
    _record(decision_id, forecast, structure, verdict, snapshot, state,
            action="intent", reason="intent persisted before POST", order=order,
            contracts=n)
    if pair_orders:
        return _submit_pair(client, pair_orders, order, decision_id, forecast, structure, verdict,
                            snapshot, state, result, n, committed, add)
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


def _fmt_usd(v) -> str:
    """`$-137` or `?`. A named helper because the inline form needed a nested
    same-quote f-string, which is Python 3.12+ only (PEP 701) and would be a
    SyntaxError on 3.11 -- a portability trap in the one file the agent cannot
    fail to import."""
    return "?" if v is None else f"${v:,.0f}"


def _submit_pair(client, orders: list[dict], record_order: dict, decision_id: str, forecast, structure,
                 verdict, snapshot, state, result, n: int, committed: float, add: float) -> float:
    """Send the two legs. If the SECOND is refused, the first is undone at once.

    A pair with one leg is an unhedged short -- the exact thing the brain
    refuses to hold. So leg-2 refusal is not "half a position": the leg-1
    order is cancelled and any filled shares are bought back at market, and the
    row says `pair_leg_failed_flattened` so the counterfactual can see it.
    """
    snap = _quote_snapshot(structure, snapshot)
    try:
        first = client.submit(orders[0], decision_id=decision_id + ":leg1", quote_snapshot=snap)
    except BrokerRefusal as exc:
        result.errors += 1
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="rejected", reason=f"pair leg 1 refused: {exc}", order=record_order, contracts=n)
        logger.warning("REJECTED pair leg 1 %s: %s", forecast.symbol, exc)
        return committed
    try:
        second = client.submit(orders[1], decision_id=decision_id + ":leg2", quote_snapshot=snap)
    except BrokerRefusal as exc:
        result.errors += 1
        undo = _flatten_leg(client, orders[0], first.get("id"), decision_id)
        _record(decision_id, forecast, structure, verdict, snapshot, state,
                action="pair_leg_failed_flattened",
                reason=f"pair leg 2 ({orders[1]['symbol']}) refused: {exc}; leg 1 undone: {undo}",
                order=record_order, contracts=n, alpaca_order_id=first.get("id"))
        logger.error("PAIR leg 2 refused on %s (%s); leg 1 flattened: %s", forecast.symbol, exc, undo)
        return committed
    result.submitted += 1
    result.decisions.append(decision_id)
    _record(decision_id, forecast, structure, verdict, snapshot, state,
            action="submitted", reason=verdict.reason,
            order={**record_order, "hedge_order_id": second.get("id")}, contracts=n,
            alpaca_order_id=first.get("id"))
    logger.info("SENT %s %s pair x%d (+%s %s) ids=%s/%s", forecast.brain, forecast.symbol, n,
                orders[1]["qty"], orders[1]["symbol"], first.get("id"), second.get("id"))
    return committed + add


def _flatten_leg(client, order: dict, order_id: str | None, decision_id: str) -> str:
    """Cancel the resting leg, then buy back whatever of it filled."""
    notes = []
    if order_id:
        try:
            client.cancel_order(order_id)
            notes.append("cancelled")
        except BrokerRefusal as exc:
            notes.append(f"cancel failed: {exc}")
    sym = order["symbol"]
    try:
        held = [p for p in client.positions() if p.get("symbol") == sym and float(p.get("qty") or 0) < 0]
    except BrokerRefusal as exc:
        return "; ".join(notes + [f"positions unreadable: {exc}"])
    if held:
        try:
            client.close_position(sym, qty=int(abs(float(held[0].get("qty") or 0))))
            notes.append(f"bought back {abs(float(held[0].get('qty') or 0)):.0f} {sym}")
        except BrokerRefusal as exc:
            notes.append(f"BUY-BACK FAILED, unhedged short remains: {exc}")
    else:
        notes.append("nothing filled")
    return "; ".join(notes)


def _ev_ratio(verdict: sizing.SizingVerdict) -> float:
    return float((verdict.economics or {}).get("ev_over_max_loss") or 0.0)


#: Sessions in the contest window. Used only to turn the window fraction into
#: the `sessions_left` that `tournament.mode_for` reasons in.
CONTEST_SESSIONS = 5


def rank_objective(state: sizing.TournamentState) -> tuple[str, str]:
    """Which number ranks structures: "median" (terminal wealth) or "mean" (EV).

    Decided 2026-08-28. The 27 Aug finding (docs/FINDING_2026-08-27_THE_RANKER_
    OPTIMISES_THE_MEAN.md) left this open: on a live NVDA chain the EV ranker
    picked a long_call at +38% EV / P(profit) 33% / median -$137 over
    long_shares at +12% / 56% / +$1. Both are right; they answer different
    questions, and the contest is FIVE compounding sessions, where terminal
    wealth follows the median. Every refutation this week came from substituting
    terminal wealth for the mean, so the default follows the same substitution.

    The mean is still the right objective in exactly one state, and it is the
    one `tournament.mode_for` already pre-registers: ATTACK -- behind late with
    a target that a positive-median book cannot reach, where only dispersion can
    change rank. So the ranker follows the MODE rather than a constant.

    `AAT_RANK_OBJECTIVE=mean|median` overrides, and says so in the reason.
    """
    forced = os.getenv("AAT_RANK_OBJECTIVE", "").strip().lower()
    if forced in ("mean", "median"):
        return forced, f"AAT_RANK_OBJECTIVE={forced} (override)"
    from alpha import tournament

    try:
        target_pct = float(os.getenv("AAT_TARGET_PCT", "2") or 2.0)
    except ValueError:
        target_pct = 2.0
    sessions_left = max(0, int(math.ceil(state.fraction_of_window_remaining * CONTEST_SESSIONS)))
    mode, why = tournament.mode_for(state.equity, target=state.starting_equity * (1 + target_pct / 100.0),
                                    start_equity=state.starting_equity, sessions_left=sessions_left)
    if mode == "ATTACK":
        return "mean", f"ATTACK: {why}"
    return "median", f"{mode}: {why}"


def _rank_value(structure, econ: dict | None, objective: str) -> float:
    """The scalar a structure is ranked on, per unit of max loss."""
    econ = econ or {}
    ev = float(econ.get("ev_over_max_loss") or 0.0)
    if objective == "mean":
        return ev
    max_loss = float(getattr(structure, "max_loss", 0.0) or 0.0)
    median = float(econ.get("median_usd") or 0.0)
    # EV as a tie-break in the last place so two zero-median structures still order.
    return (median / max_loss if max_loss > 0 else 0.0) + 1e-6 * ev


def _spot_for(snapshot, structure: sizing.Structure) -> float:
    """The underlying spot: the chain's when there is a chain, else the share
    structure's own quote (a pair on a name with no listed options)."""
    if snapshot is not None and snapshot.spot > 0:
        return float(snapshot.spot)
    q = structure.quote or {}
    for k in ("spot", "mid"):
        if q.get(k):
            return float(q[k])
    b, a = float(q.get("bid") or 0.0), float(q.get("ask") or 0.0)
    return 0.5 * (b + a) if b > 0 and a > 0 else float(structure.entry_cost or 0.0)


def _quote_snapshot(structure: sizing.Structure, snapshot) -> dict:
    """The quotes we actually saw, per leg, plus how stale they were."""
    wanted = {sym for sym, _, _ in structure.legs}
    if snapshot is None:
        # No chain: a pair on a name with no listed options. The stock quotes
        # ARE the record; say so rather than fabricating chain fields.
        return {"underlying": structure.symbol, "spot": _spot_for(None, structure),
                "spot_source": "stock_quote", "spot_ts": datetime.now(timezone.utc).isoformat(),
                "feed": config.stock_feed(), "market_open": None, "median_quote_age_s": None,
                "parity_gap": None, "no_chain": True,
                "legs": [dict(structure.quote)] if structure.quote else []}
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
        # An `intent` row is not a refusal; putting its reason in refusal_reason
        # would make every pre-POST row read as a decline in the dashboard's
        # refusal census.
        refusal_reason=None if action in ("submitted", "intent") else reason,
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
            # The pair's hedge leg is sized on the whole position, not per unit;
            # the book matcher and the exit pass read it from here.
            **({"hedge_symbol": order.get("hedge_symbol"), "hedge_shares": int(order.get("hedge_qty") or 0)}
               if isinstance(order, dict) and order.get("pair") else {}),
        },
    ))
