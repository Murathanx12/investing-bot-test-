"""The artery: the exact sealed tracker portfolio, and nothing else.

WHY THIS EXISTS
===============
Until 2026-08-31 the tracker's personalities -- hack3's top 10, hack4's top 5,
hack6's top 15, their rankings, sector caps, coverage bands, liquidity floors
and downside limits -- reached NOTHING. `build_portfolio` was called by
`scripts/tracker.py --portfolios`, which prints, and by its tests.
`scripts.reachability` had been saying so for weeks (`ORPHAN alpha.tracker`),
buried among 22 other orphans.

The obvious repair was "enable `murat_rule`". That is the WRONG repair and it
would have been believed: `murat_rule` reads per-name CLAIMS from the sealed
book (`rule_predictions`), and the seal never called `build_portfolio` at all.
Turning it on would have traded the claimers -- one name, MU, on the published
book -- while the handoff said "hack4 is live". Executing a different strategy
while believing it is the new one teaches false lessons, which is worse than
trading nothing.

So the seal now carries `portfolios[book]["holdings"]`: symbol and weight,
decided before the open and frozen inside `content_sha256`. This brain reads
that block and refuses everything else.

THE THREE PROPERTIES THIS FILE HAS TO HAVE
==========================================
1. **The runner can reach it.** It is registered in `alpha/brains/__init__.py`.
   Reachability is not "the module imports"; it is "an entry point can call it".
2. **It sees exactly what was sealed.** No re-ranking, no recomputation, no
   reading of `alpha.tracker` at decision time. If it could re-derive, it could
   drift from the artifact that was inspected -- and then the hash guarantees
   nothing. This module deliberately does NOT import `alpha.tracker`.
3. **A tracker refresh after the seal cannot change today's book.** Guaranteed
   by 2: the only input is the sealed file.

WHICH BOOK THIS ACCOUNT TRADES
==============================
`AAT_ACCOUNT_ROLE` (hack3 / hack4 / hack6), the same variable the fleet already
sets per Railway service. An account whose role has no portfolio in the seal
declines every symbol WITH A REASON rather than falling back to another book --
a fallback here would silently run hack3's names on hack6's mandate.

SEALING IS NOT ENABLING. Every seal from today carries this block. It trades
only where `AAT_LOOP_BRAINS` contains `tracker_portfolio`, which is an attended
decision on a live paper account and is made by a human, not by this file.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from alpha import exits as _exits
from alpha.brains.base import Forecast

ROOT = Path(__file__).resolve().parent.parent.parent

#: Same two locations, same order, and for the same reason as `murat_rule`: on
#: Railway `AAT_LEDGER_DIR=/app/state` is a mounted VOLUME and SHADOWS whatever
#: the image ships at that path, so a book committed under `state/` is invisible
#: to the loop. `docs/seed/` is not shadowed and is the delivery path.
BOOKS = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "predictions"
SEED_BOOKS = ROOT / "docs" / "seed" / "predictions"

BRAIN = "tracker_portfolio"

#: The horizon the sealed numbers were computed for. A loop on a shorter horizon
#: gets them SCALED, never reused: `centre` is a drift (linear in t), `sd` is a
#: diffusion (linear in sqrt t). Reusing a 21-session centre at 5 sessions would
#: overstate the claim by more than four times.
BOOK_HORIZON_SESSIONS = 21
SESSIONS_PER_CALENDAR_DAY = 5.0 / 7.0


class PortfolioDeclined(Exception):
    """This brain has nothing to say about this symbol, and says why."""


def _book_for(day: str) -> dict | None:
    """The NEWEST sealed book for `day`, ledger dir first, then the seed dir.

    A reseal writes a new file beside the original rather than replacing it, so
    `<day>.json` alone can be a superseded book. Sorting puts `resealed_HHMMSS`
    after the plain name and the last one wins -- the same rule `murat_rule`
    uses, deliberately duplicated rather than shared, because a change to one
    brain's book-selection must not silently change the other's.
    """
    for base in (BOOKS, SEED_BOOKS):
        cands = sorted(base.glob(f"{day}.json")) + sorted(base.glob(f"{day}.resealed_*.json"))
        if not cands:
            continue
        try:
            return json.loads(cands[-1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def role() -> str | None:
    """Which book this account trades. None when the fleet has not said."""
    r = (os.getenv("AAT_ACCOUNT_ROLE") or "").strip().lower()
    return r or None


def sealed_holdings(day: str | None = None, *, book: str | None = None) -> dict:
    """{symbol: holding} for this account's book, plus the provenance.

    Exposed separately from `forecast` so the pre-open check can print exactly
    what will trade and compare it against the hash, without going through a
    broker client. "I inspected the artifact the runner consumes" has to be a
    command anyone can run, or it is not a proof.
    """
    day = day or _exits.session_day()
    b = book or role()
    payload = _book_for(day)
    if payload is None:
        raise PortfolioDeclined(
            f"no sealed book for {day}: this brain trades only what was sealed before "
            f"the open (`python -m scripts.prediction_book --seal --universe tracker` "
            f"then `--publish`). Declining rather than re-deriving.")
    if b is None:
        raise PortfolioDeclined(
            "AAT_ACCOUNT_ROLE is unset, so there is no way to know WHICH book this "
            "account trades. Refusing rather than defaulting -- a default here runs "
            "one mandate's names on another mandate's account.")
    ports = payload.get("portfolios") or {}
    if not ports:
        raise PortfolioDeclined(
            f"the sealed book for {day} carries no `portfolios` block (schema "
            f"{payload.get('schema')!r}). It was sealed before the artery existed; "
            f"re-seal and re-publish before enabling this brain.")
    port = ports.get(b)
    if port is None:
        raise PortfolioDeclined(
            f"the sealed book for {day} has no portfolio for role {b!r} "
            f"(it has {sorted(ports)}). Refusing rather than substituting another book.")
    if port.get("ranking_is_degenerate"):
        raise PortfolioDeclined(
            f"{b}'s sealed ranking is DEGENERATE -- all eligible names share one "
            f"`{port.get('ranking')}` value, so these holdings are an arbitrary slice "
            f"of the pool in dict order, not the best {port.get('k_target')}. "
            f"Refusing to trade a sort that did not sort.")
    return {
        "book": b,
        "day": day,
        "content_sha256": payload.get("content_sha256"),
        "sealed_at_utc": payload.get("sealed_at_utc"),
        "ranking": port.get("ranking"),
        "n_selected": port.get("n_selected"),
        "k_target": port.get("k_target"),
        "constraints": port.get("constraints"),
        "holdings": {h["symbol"]: h for h in (port.get("holdings") or [])},
    }


def forecast(client, symbol: str, horizon_days: float, *, day: str | None = None) -> Forecast:
    sym = str(symbol).upper()
    sealed = sealed_holdings(day)
    h = sealed["holdings"].get(sym)
    if h is None:
        raise PortfolioDeclined(
            f"{sym} is not in {sealed['book']}'s sealed portfolio for {sealed['day']} "
            f"({sealed['n_selected']} names: {', '.join(sorted(sealed['holdings'])) or 'none'}). "
            f"This brain does not re-rank at decision time -- if the name is not in the "
            f"sealed book it does not trade today, however good it looks now.")

    exp_r, dn = h.get("exp_return"), h.get("downside_5pct")
    if exp_r is None or dn is None:
        raise PortfolioDeclined(
            f"{sym} is in the sealed book but carries no numbers "
            f"(exp_return={exp_r}, downside_5pct={dn}) -- refusing rather than inventing them.")

    sessions = max(1.0, float(horizon_days) * SESSIONS_PER_CALENDAR_DAY)
    t = min(1.0, sessions / BOOK_HORIZON_SESSIONS)
    centre = float(exp_r) * t
    # `downside_5pct` is the 5% normal quantile, so |dn| / 1.645 recovers the sd
    # it was computed from. Using |dn| directly as the spread would inflate it by
    # 64% and hand every name a wider distribution than the book claimed.
    sd = (abs(float(dn)) / 1.645) * math.sqrt(t)
    if sd <= 0:
        raise PortfolioDeclined(
            f"{sym} has a non-positive spread ({sd}); a point forecast with no stated "
            f"uncertainty would size itself to the ceiling")

    return Forecast(
        brain=BRAIN, symbol=sym, horizon_days=float(horizon_days),
        centre=centre, sd=sd,
        conviction=max(0.05, min(1.0, float(h.get("confidence") or 0.05))),
        # DIRECTION only. The book ranks names; it does not claim to know how
        # wide each outcome is, and claiming the width is how a bullish reading
        # gets handed an iron condor.
        claim="direction",
        signal_shape=None,
        rationale=(f"{sealed['book']} sealed portfolio ({sealed['ranking']}): "
                   f"{sym} at {h.get('notional'):.1%} of equity, rank {h.get('rank_value')}, "
                   f"sector {h.get('sector')}; {sealed['n_selected']}/{sealed['k_target']} "
                   f"names sealed at {sealed['sealed_at_utc']}"),
        evidence={
            "book": sealed["book"],
            "sealed_day": sealed["day"],
            "book_sha256": sealed["content_sha256"],
            "ranking": sealed["ranking"],
            "constraints": sealed["constraints"],
            # THE WEIGHT THE BOOK CHOSE. The runner's admission layer may cut it
            # (gross cap, notional cap, opening range) and must never raise it.
            "sealed_notional": h.get("notional"),
            "rank_value": h.get("rank_value"),
            "sector": h.get("sector"),
            "exp_return_21d": exp_r,
            "downside_5pct_21d": dn,
            "confidence": h.get("confidence"),
            "numbers_source": h.get("numbers_source"),
            "horizon_scaling": f"centre x {t:.3f} (linear), sd x sqrt({t:.3f}) (diffusion)",
            "sd_from_downside": "sd = |downside_5pct| / 1.645, the normal 5% quantile",
            "licence": "PRODUCT_EXPERIMENT",
            "no_reranking": ("this brain reads the sealed file only and never imports "
                             "alpha.tracker; a refresh after the seal cannot change today"),
        },
    )


# --------------------------------------------------------------------------
# ENFORCING THE SEALED WEIGHT (2026-08-31)
# --------------------------------------------------------------------------
#
# The seal proved WHICH NAMES trade. It did not, until now, constrain HOW MUCH.
# `sealed_notional` was written into the forecast's evidence and read by
# nothing -- `grep sealed_notional` returned exactly one hit, the line that
# writes it -- while the runner sized from `sizing.PROFILES[risk_profile]`.
# hack4's profile is `maximum`, whose `per_thesis` is 0.15, against a sealed
# 0.10: the runner could put HALF AGAIN the weight the book chose into a name
# and every receipt would still say the book was followed.
#
# So the book's weight becomes a CEILING. The sizer and admission may cut it --
# gross cap, opening range, daily-loss latch all still bind and all still only
# reduce -- but nothing may exceed it.

#: Structures whose notional means what the book meant by it. A 10% stock
#: weight and 10% of equity spent on calls are not the same risk, and treating
#: them alike is how a "10% position" becomes a total loss. Options get their
#: own premium-risk semantics; they do not get the equity weight.
SHARE_KINDS = frozenset({"long_shares", "short_shares"})


class SealedWeightRefusal(Exception):
    """This structure cannot express a sealed equity weight honestly."""


def clamp_to_sealed(risk_fraction: float, forecast_evidence: dict,
                    structure_kind: str) -> tuple[float, str]:
    """Cut `risk_fraction` to the sealed weight. Never raises it.

    Returns `(fraction, note)`. Raises `SealedWeightRefusal` for a non-share
    structure, because there is no honest conversion from "6% of equity in the
    stock" to a premium budget, and inventing one silently changes the mandate.
    """
    sealed = forecast_evidence.get("sealed_notional")
    if sealed is None:
        # Not a sealed-portfolio forecast: this clamp has no opinion.
        return risk_fraction, ""
    if structure_kind not in SHARE_KINDS:
        raise SealedWeightRefusal(
            f"{structure_kind} cannot express a sealed equity weight of "
            f"{sealed:.1%}. The tracker books are SHARES-ONLY so the sealed "
            f"notional keeps one meaning; express the same forecast as options "
            f"on a book with premium-risk semantics instead.")
    sealed = float(sealed)
    if risk_fraction <= sealed + 1e-12:
        return risk_fraction, (f"within the sealed {sealed:.1%}")
    return sealed, (f"CUT from {risk_fraction:.1%} to the sealed {sealed:.1%} "
                    f"-- the book's weight is a ceiling, not a suggestion")
