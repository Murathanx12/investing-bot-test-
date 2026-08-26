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
from datetime import datetime, timezone

from alpha import book as book_mod
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


def admit(book: book_mod.BookRisk, structure: sizing.Structure, contracts: int, *,
          equity: float, aggregate_cap: float, committed_usd: float = 0.0,
          own_event: str | None = None, reserved_events: dict[str, float] | None = None,
          greeks: BookGreeks | None = None, new_delta_usd: float | None = None,
          new_theta_usd_per_day: float | None = None, new_daily_sigma: float | None = None,
          per_underlying_cap: float = PER_UNDERLYING_CAP) -> Admission:
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

    return Admission(True, (
        f"admitted: post-trade true max loss {post_total / equity:.1%}, {free_after / equity:.1%} free, "
        f"{sym} at {post_sym / equity:.1%}"), m)
