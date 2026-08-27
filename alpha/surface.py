"""OPTION_SURFACE_GEOMETRY_v1 -- what the surface says the market BELIEVES.

Geometry 1 (alpha/engine/shape.py) reads the SIGNAL's shape and picks the
instrument. This is Geometry 2: read the OPTION SURFACE's shape and recover the
distribution the market has already paid for. The two together let the agent
say the sentence no directional bot can:

    our history says TAIL; the surface is already bimodal and concave;
    the event is real and the market has bought the tail -> REFUSE convexity.

Measured from one ChainSnapshot, per expiry:

    atm_iv               straddle-implied vol at the nearest strike
    iv_call_up/put_down  IV one implied move above / below spot
    skew                 iv_call_up - iv_put_down          (>0: calls bid)
    curvature            mean(wings) - atm                (<0: CONCAVE, wings cheap
                                                          relative to the body, the
                                                          RoF 2025 event-risk signature)
    term                 front vs back ATM IV

and across two expiries the EVENT VARIANCE STRIP:

    sigma_f^2 T_f = a T_f + J,  sigma_b^2 T_b = a T_b + J
    -> a (ambient annual variance), J (event jump variance), sqrt(J) = market jump sd

Every number comes from mids the chain actually quoted; nothing is smoothed.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from alpha.data.chain import ChainSnapshot, Contract, _bs_price

R = 0.045


def _invert(price: float, f) -> float | None:
    lo, hi = 1e-4, 6.0
    if price <= 0 or f(hi) < price or f(lo) > price:
        return None
    for _ in range(80):
        m = (lo + hi) / 2.0
        if f(m) < price:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2.0


def _mid(c: Contract) -> float:
    return c.adjusted_mid if c.adjusted_mid is not None else c.mid


def _nearest(snap: ChainSnapshot, expiry: str, right: str, target: float) -> Contract | None:
    pool = [c for c in snap.contracts if c.expiry == expiry and c.right == right and c.bid > 0]
    return min(pool, key=lambda c: abs(c.strike - target)) if pool else None


def _years(expiry: str, asof: date) -> float:
    return max((date.fromisoformat(expiry) - asof).days, 1) / 365.0


def geometry(snap: ChainSnapshot, expiry: str, *, asof: date | None = None) -> dict[str, Any] | None:
    """Skew, curvature and ATM IV for one expiry, at one implied move from spot."""
    asof = asof or snap.fetched_at.date()
    s, t = snap.spot, _years(expiry, asof)
    call, put = snap.atm(expiry, "C"), snap.atm(expiry, "P")
    if not call or not put:
        return None
    k = call.strike
    straddle = _mid(call) + _mid(put)
    atm_iv = _invert(straddle, lambda v: _bs_price(s, k, t, v, "C", R) + _bs_price(s, k, t, v, "P", R))
    if not atm_iv:
        return None
    w = max(atm_iv * math.sqrt(t) * s, 0.5)          # one implied sd, in dollars
    cu, pd = _nearest(snap, expiry, "C", k + w), _nearest(snap, expiry, "P", k - w)
    cu2, pd2 = _nearest(snap, expiry, "C", k + 2 * w), _nearest(snap, expiry, "P", k - 2 * w)
    out: dict[str, Any] = {"expiry": expiry, "days": round(t * 365), "atm_strike": k, "atm_iv": round(atm_iv, 4),
                           "implied_move": round(straddle / s, 4), "wing_dollars": round(w, 2)}
    if cu and pd and cu.strike != k and pd.strike != k:
        ivc = _invert(_mid(cu), lambda v: _bs_price(s, cu.strike, t, v, "C", R))
        ivp = _invert(_mid(pd), lambda v: _bs_price(s, pd.strike, t, v, "P", R))
        if ivc and ivp:
            out.update({"iv_call_up": round(ivc, 4), "iv_put_down": round(ivp, 4),
                        "skew": round(ivc - ivp, 4), "curvature": round((ivc + ivp) / 2 - atm_iv, 4),
                        "wing_strikes": [pd.strike, cu.strike]})
    if cu2 and pd2 and cu2.strike != (cu.strike if cu else None):
        ivc2 = _invert(_mid(cu2), lambda v: _bs_price(s, cu2.strike, t, v, "C", R))
        ivp2 = _invert(_mid(pd2), lambda v: _bs_price(s, pd2.strike, t, v, "P", R))
        if ivc2 and ivp2:
            out["curvature_2sd"] = round((ivc2 + ivp2) / 2 - atm_iv, 4)
    if "curvature" in out:
        out["shape"] = "concave" if out["curvature"] < -0.01 else "convex" if out["curvature"] > 0.01 else "flat"
    return out


def variance_strip(snap: ChainSnapshot, front: str, back: str, *, asof: date | None = None) -> dict[str, Any] | None:
    """Ambient variance and the event jump priced between `front` and `back`.

    Valid only when BOTH expiries span the same scheduled event (the print sits
    before the front expiry). If the event lies between them the sign flips and
    the strip is meaningless -- the caller must know where the event is.
    """
    asof = asof or snap.fetched_at.date()
    gf, gb = geometry(snap, front, asof=asof), geometry(snap, back, asof=asof)
    if not gf or not gb:
        return None
    tf, tb = _years(front, asof), _years(back, asof)
    if tb <= tf:
        return None
    vf, vb = gf["atm_iv"] ** 2 * tf, gb["atm_iv"] ** 2 * tb
    a = max((vb - vf) / (tb - tf), 0.0)
    j = max(vf - a * tf, 0.0)
    return {"front": front, "back": back, "iv_front": gf["atm_iv"], "iv_back": gb["atm_iv"],
            "ambient_annual_var": round(a, 5), "ambient_daily_sd": round(math.sqrt(a / 252), 5) if a else 0.0,
            "market_jump_sd": round(math.sqrt(j), 5), "event_share_of_front_var": round(j / vf, 3) if vf else None,
            "front_geometry": gf, "back_geometry": gb}


def read(snap: ChainSnapshot, *, event_before: str | None = None) -> dict[str, Any]:
    """The whole surface reading for a snapshot: every expiry's geometry, the
    term structure, and -- when an event date is supplied -- the strip across the
    first two expiries after it."""
    exps = snap.expiries()
    geos = [g for g in (geometry(snap, e) for e in exps) if g]
    out: dict[str, Any] = {"underlying": snap.underlying, "spot": snap.spot, "expiries": geos}
    if len(geos) >= 2:
        out["term_front_minus_back"] = round(geos[0]["atm_iv"] - geos[1]["atm_iv"], 4)
    if event_before:
        after = [e for e in exps if e >= event_before]
        if len(after) >= 2:
            out["strip"] = variance_strip(snap, after[0], after[1])
    return out
