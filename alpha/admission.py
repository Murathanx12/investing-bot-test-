"""PROSPECTIVE admission control -- what the book looks like AFTER this order.

WHY THE SIZER IS NOT ENOUGH
===========================
On 25 Aug both paper books ended the day at a TRUE max loss of 72.7% and 58.2%
of equity, every position inside its own per-thesis cap and the aggregate cap
tested one order at a time. Each admission was individually legal and the book
they added up to was one nobody would have approved in a single decision: it
could not add a position for the one event with a positive receipt (4 Sep), it
bled ~3% of equity a day in theta on a quiet tape, and it carried an unhedged
delta the brains had never claimed. The sizer answers "how much may THIS
thesis risk"; nothing answered "what can the book still DO tomorrow".

This module asks the second question, once per candidate order, on the
post-trade book, and REFUSES the order if the answer is "less than it must":

  1. POST-TRADE TRUE MAX LOSS  -- book + everything this pass already committed
     + this order -- must leave `MIN_FREE_FRACTION` of equity under the profile's
     aggregate ceiling for a better signal tomorrow. The order that spends the
     last of the budget is the one refused, whatever its edge, unless the order
     IS the reserved event's own expression.
  2. CONCENTRATION -- post-trade max loss on one underlying <= `PER_UNDERLYING_CAP`.
  3. THETA BURN -- post-trade book theta per calendar day >= -`THETA_BURN_CAP`
     of equity. Long premium is allowed; a book that pays 0.75% of equity a day
     to wait is not.
  4. DELTA STRESS -- post-trade, the sum over underlyings of |delta $| x two
     daily sigmas <= `STRESS_CAP` of equity. Delta-only, correlated-worst-case,
     and labelled as such: gamma and vega are NOT in it, so this is a floor on
     the stress, never the stress.

Checks 3 and 4 need greeks, which need a spot and a quote per leg. When they
cannot be derived (a fake client, a feed outage) the verdict SAYS SO in its
metrics -- `theta: CANNOT DETERMINE` -- and does not pretend to have passed.
The max-loss and concentration checks need only the book and always run.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from alpha import book as book_mod
from alpha import book_limits, concentration
from alpha.engine import sizing

logger = logging.getLogger(__name__)

#: Equity that must remain FREE under the aggregate ceiling after the order.
MIN_FREE_FRACTION = 0.10
#: Post-trade true max loss on one underlying, fraction of equity.
PER_UNDERLYING_CAP = 0.15
#: Post-trade book theta per calendar day, fraction of equity (a negative number
#: is a cost; the cap is on the cost).
THETA_BURN_CAP = 0.0075
#: Post-trade two-sigma one-day adverse delta move, fraction of equity.
STRESS_CAP = 0.10
MULT = 100.0


@dataclass
class BookGreeks:
    """Per-underlying delta ($ per 1.0 move = shares-equivalent x spot) and theta ($/day)."""
    delta_usd: dict[str, float] = field(default_factory=dict)
    theta_usd_per_day: float = 0.0
    daily_sigma: dict[str, float] = field(default_factory=dict)
    derived: bool = False
    note: str = ""


@dataclass(frozen=True)
class Admission:
    ok: bool
    reason: str
    metrics: dict


def book_greeks(client, *, account_role: str | None = None) -> BookGreeks:
    """Delta and theta of the OPEN book, derived from the same attribution the
    P&L report uses. Returns `derived=False` with a note when it cannot."""
    try:
        from alpha import attribution

        report = attribution.attribute_book(client, account_role=account_role)
    except Exception as exc:                                             # noqa: BLE001
        return BookGreeks(note=f"CANNOT DETERMINE: attribution failed ({type(exc).__name__}: {exc})")
    out = BookGreeks(derived=True)
    structs = report.get("_structs") or []
    for att in structs:
        spot = att.spot_now or 0.0
        if spot <= 0:
            out.note = "some structures have no spot; their delta is not in the stress"
            continue
        out.delta_usd[att.symbol] = out.delta_usd.get(att.symbol, 0.0) + att.net_delta_shares * spot
        out.theta_usd_per_day += getattr(att, "net_theta_usd_per_day", 0.0)
    # Daily sigma per underlying from the entry rows: implied move over the life / sqrt(dte at entry).
    try:
        bk = book_mod.reconstruct(client.positions(), equity=float(report.get("equity") or 0.0),
                                  account_role=account_role)
        for s in bk.structures:
            row = s.row or {}
            im = float(row.get("implied_move") or 0.0)
            if im <= 0 or not s.legs:
                continue
            dte = _dte_at(row.get("ts_utc"), s.legs[0][0]) or 1.0
            sig = im / math.sqrt(max(1.0, dte))
            out.daily_sigma[s.symbol] = max(out.daily_sigma.get(s.symbol, 0.0), sig)
    except Exception as exc:                                             # noqa: BLE001
        out.note = f"daily sigma not derived ({type(exc).__name__})"
    return out


def _dte_at(ts_utc: str | None, leg: str) -> float | None:
    if book_mod.is_share(leg) or not ts_utc:
        return None
    try:
        _, _, _, expiry = book_mod.decode_occ(leg)
        t = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        exp = datetime.fromisoformat(expiry + "T20:00:00+00:00")
        return max(0.5, (exp - t).total_seconds() / 86400.0)
    except ValueError:
        return None


def structure_greeks(structure: sizing.Structure, contracts: int, snapshot) -> tuple[float | None, float | None]:
    """(delta $, theta $/day) of `contracts` units of the candidate, from the chain's own greeks."""
    if not structure.legs:
        return None, None
    if book_mod.is_share(structure.legs[0][0]):
        spot = float(getattr(snapshot, "spot", 0.0) or 0.0)
        sign = 1.0 if structure.legs[0][1] == "buy" else -1.0
        return sign * contracts * spot, 0.0
    by_sym = {c.symbol: c for c in (getattr(snapshot, "contracts", None) or [])}
    spot = float(getattr(snapshot, "spot", 0.0) or 0.0)
    delta = theta = 0.0
    for sym, side, ratio in structure.legs:
        c = by_sym.get(sym)
        if c is None or c.delta is None:
            return None, None
        sign = 1.0 if side == "buy" else -1.0
        delta += sign * ratio * contracts * float(c.delta) * MULT * spot
        th = c.theta
        if th is None:
            return delta, None
        theta += sign * ratio * contracts * float(th) * MULT
    return delta, theta


def book_n_risk(book: book_mod.BookRisk, client, *, days: int = 60) -> float | None:
    """Effective N by RISK for the CURRENT book, or None if it cannot be measured.

    One batched bars call, meant to be made ONCE PER CYCLE by the runner and
    threaded into every `admit()` in that pass -- not once per order. A network
    round trip inside the per-order admission path would bolt a new failure mode
    onto the one path that must not fail.

    Returns None on any failure, and None is the SAFE direction: `book_limits`
    treats an unmeasured concentration as a binding breach once the book is large
    enough for the limit to bind at all.
    """
    import math

    try:
        weights = concentration.weights_from_book(book)
        if len(weights) < 2:
            return None            # n_risk is definitionally 1.0; nothing to measure
        start = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        bars = client.stock_bars_multi(sorted(weights), start=start, timeframe="1Day")
        returns: dict[str, list[float]] = {}
        for sym, rows in bars.items():
            closes = [float(r["c"]) for r in rows if r.get("c")]
            if len(closes) > 5:
                returns[sym] = [math.log(closes[i] / closes[i - 1])
                                for i in range(1, len(closes))]
        c = concentration.measure(weights, returns)
        return c.n_risk if c else None
    except Exception as exc:  # noqa: BLE001 -- an unmeasured value is a state, not a crash
        logger.warning("book n_risk could not be measured (%s); admission will treat "
                       "concentration as UNMEASURED, which refuses once the book is large "
                       "enough for the limit to bind", exc)
        return None


def admit(book: book_mod.BookRisk, structure: sizing.Structure, contracts: int, *,
          equity: float, aggregate_cap: float, committed_usd: float = 0.0,
          own_event: str | None = None, reserved_events: dict[str, float] | None = None,
          greeks: BookGreeks | None = None, new_delta_usd: float | None = None,
          new_theta_usd_per_day: float | None = None, new_daily_sigma: float | None = None,
          per_underlying_cap: float = PER_UNDERLYING_CAP,
          n_risk: float | None = None,
          gross_cap: float | None = None, gross_usd: float | None = None,
          add_notional_usd: float = 0.0, committed_notional_usd: float = 0.0) -> Admission:
    """Admit or refuse `contracts` units of `structure` on the POST-trade book.

    `per_underlying_cap` defaults to 15% and the runner raises it to the
    profile's own single-thesis maximum (per_thesis x edge_scale_cap) where that
    is larger, so the concentration rule binds on the SECOND order in a name --
    the 25 Aug failure -- and not on a first order the profile already permits."""
    if equity <= 0:
        return Admission(False, "no equity to admit against", {})
    add = structure.max_loss * contracts
    first_leg = structure.legs[0][0] if structure.legs else structure.symbol
    sym = structure.symbol if book_mod.is_share(first_leg) else book_mod.decode_occ(first_leg)[0]
    post_total = book.max_loss_usd + committed_usd + add
    post_sym = book.by_underlying.get(sym, 0.0) + add
    free_after = aggregate_cap * equity - post_total
    reserved = reserved_events or {}
    is_reserved_expression = bool(own_event) and any(own_event.endswith(d) for d in reserved)
    m = {
        "post_true_max_loss_frac": round(post_total / equity, 4),
        "free_after_frac": round(free_after / equity, 4),
        "post_underlying_frac": round(post_sym / equity, 4),
        "underlying": sym, "add_usd": round(add, 2),
        "min_free_frac": MIN_FREE_FRACTION, "per_underlying_cap": per_underlying_cap,
        "reserved_expression": is_reserved_expression,
    }
    # -- GROSS NOTIONAL (2026-08-29) -------------------------------------------
    # The risk caps above sum WORST CASES; nothing here bounded the sum of
    # NOTIONAL, so a 3% stop on 300% gross cost -9% on 28 Aug. A book whose
    # gross cannot be measured is refused, not assumed flat.
    if gross_cap is not None:
        if gross_usd is None:
            m["gross"] = "CANNOT DETERMINE"
            return Admission(False, (
                f"GROSS: the book's notional could not be measured, so the {gross_cap:.0%} "
                "gross cap cannot be checked. Refused rather than assumed flat."), m)
        post_gross = gross_usd + committed_notional_usd + max(0.0, add_notional_usd)
        m["post_gross_frac"] = round(post_gross / equity, 4)
        m["gross_cap"] = gross_cap
        if post_gross > gross_cap * equity + 1e-9:
            return Admission(False, (
                f"GROSS: after this order the book would carry {post_gross / equity:.0%} of equity "
                f"in notional (cap {gross_cap:.0%}). Twelve names at 25% each is 300% gross, and a "
                "3% stop on 300% gross is -9% -- the 28 Aug number."), m)
    if post_sym > per_underlying_cap * equity + 1e-9:
        return Admission(False, (
            f"CONCENTRATION: {sym} would carry {post_sym / equity:.1%} of equity in true max loss "
            f"after this order (cap {per_underlying_cap:.0%}). One name is not a book."), m)
    if free_after < MIN_FREE_FRACTION * equity - 1e-9 and not is_reserved_expression:
        return Admission(False, (
            f"TOMORROW'S OPTIONALITY: after this order the book would sit at {post_total / equity:.1%} "
            f"true max loss, leaving {max(0.0, free_after) / equity:.1%} of equity under the "
            f"{aggregate_cap:.0%} ceiling -- below the {MIN_FREE_FRACTION:.0%} that must stay free for a "
            "better signal tomorrow. The order that spends the last of the budget is the one refused."), m)

    # -- theta burn -----------------------------------------------------------
    if greeks is not None and greeks.derived and new_theta_usd_per_day is not None:
        post_theta = greeks.theta_usd_per_day + new_theta_usd_per_day
        m["post_theta_usd_per_day"] = round(post_theta, 2)
        m["theta_cap_usd_per_day"] = round(-THETA_BURN_CAP * equity, 2)
        if post_theta < -THETA_BURN_CAP * equity:
            return Admission(False, (
                f"THETA BURN: the book would pay ${-post_theta:,.0f}/day to wait "
                f"({-post_theta / equity:.2%} of equity; cap {THETA_BURN_CAP:.2%}/day). On 25 Aug a "
                "quiet Tuesday cost ~3%/day this way. A thesis that needs a move must not also need "
                "the move to be soon."), m)
    else:
        m["theta"] = "CANNOT DETERMINE" + (f": {greeks.note}" if greeks is not None and greeks.note else
                                           "" if greeks is not None else ": no book greeks")

    # -- delta stress ---------------------------------------------------------
    if greeks is not None and greeks.derived and new_delta_usd is not None:
        deltas = dict(greeks.delta_usd)
        deltas[sym] = deltas.get(sym, 0.0) + new_delta_usd
        sigmas = dict(greeks.daily_sigma)
        if new_daily_sigma:
            sigmas[sym] = max(sigmas.get(sym, 0.0), new_daily_sigma)
        stress = 0.0
        missing = []
        for u, d in deltas.items():
            sg = sigmas.get(u)
            if not sg:
                missing.append(u)
                continue
            stress += abs(d) * 2.0 * sg
        m["stress_2sigma_delta_usd"] = round(stress, 2)
        m["stress_cap_usd"] = round(STRESS_CAP * equity, 2)
        m["stress_note"] = "delta-only, every underlying against us; gamma/vega NOT included" + (
            f"; no sigma for {missing}" if missing else "")
        if stress > STRESS_CAP * equity:
            return Admission(False, (
                f"DELTA STRESS: a two-sigma day against every underlying would cost ${stress:,.0f} "
                f"({stress / equity:.1%} of equity; cap {STRESS_CAP:.0%}) after this order -- and that is "
                "delta only. The book is carrying a directional bet the brains did not make."), m)
    else:
        m["stress"] = "CANNOT DETERMINE"

    # -- BOOK-WIDE BACKSTOP (alpha/book_limits.py) ---------------------------
    # Every check above is per-ORDER or per-UNDERLYING. None of them asks a
    # question about the book AS A WHOLE, which is how the rehearsal book reached
    # 72.9% of equity in true max loss with every individual check passing and
    # nothing violated. These limits were written weeks ago and called by nothing.
    #
    # LAST, not first. A first cut ran them at the top of admit() and it was
    # wrong twice: the specific reason (CONCENTRATION, TOMORROW'S OPTIONALITY)
    # should beat the general one in the refusal message, and running first
    # bypassed the reserved-event exemption below -- so a reserved event's own
    # expression, which is deliberately allowed to spend the reserve, was refused
    # by a limit that knows nothing about reserves.
    #
    # Evaluated on the POST-trade book, so the order that WOULD cause the breach
    # is the one refused rather than the one after it.
    post_weights = {**book.by_underlying, sym: post_sym}
    breaches = book_limits.evaluate(
        equity=equity, true_max_loss=post_total,
        # free EQUITY, not room under the policy ceiling. `free_after` is the
        # latter and answers a different question; conflating them would make one
        # limit shadow the other.
        free_capital=equity - post_total,
        thesis_weights=post_weights, n_risk=n_risk, n_positions=len(post_weights))
    m["book_limits"] = [b.line() for b in breaches]
    refusing = [b for b in book_limits.refusing(breaches)
                # Same carve-out the free-capital check above already makes: the
                # reserved event's OWN expression may spend the reserve.
                if not (is_reserved_expression and b.limit == "MIN_FREE_CAPITAL")]
    if refusing:
        return Admission(False, "BOOK LIMIT: " + " | ".join(b.line() for b in refusing), m)

    return Admission(True, (
        f"admitted: post-trade true max loss {post_total / equity:.1%}, {free_after / equity:.1%} free, "
        f"{sym} at {post_sym / equity:.1%}"), m)
