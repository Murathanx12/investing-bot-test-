"""CLAIM_EXPRESSION_MATRIX_v1 -- which structures a claim is allowed to buy.

WHAT A FORECAST IS ACTUALLY CLAIMING
====================================
`Forecast.claim` says which part of the distribution a brain has evidence for:

    direction     which WAY. No opinion on the width.
    dispersion    how WIDE. No opinion on the sign.
    distribution  both, and it must be able to defend both.

An instrument is not a preference; it is a bet on a specific moment. A call pays
on the SIGNED move. A straddle pays on the ABSOLUTE move. An iron condor pays on
the absolute move being SMALL -- and it cannot see the sign at all, which is the
whole point of it.

So a brain that knows only the direction, buying a condor, has spent evidence it
has on a payoff that cannot express it. That is not a bad trade. It is a
CATEGORY error, and it happened here: measured on a real NVDA chain on
2026-08-26, the same condor won the EV ranking at centre +0.72% AND at -0.72%,
its EV moving $6 on $54. Flip the forecast's sign and the answer did not change,
which means the answer never depended on the forecast.

WHY THE ECONOMIC FIX IS NOT ENOUGH ON ITS OWN
=============================================
`runner.effective_sd` already integrates a `direction` brain at the CHAIN's
width instead of its own, which removes the accidental second claim that made
short-premium structures look free. That is the right fix and it stays.

But it is a fix that works by ARITHMETIC: it makes the condor score badly. A
future chain, a wider spread, a different regime, or one more unit bug can make
it score well again, and nothing would notice, because nothing anywhere says the
condor was inadmissible on principle. Three of the six defects this project has
paid for were arithmetic pointing the wrong way while every structural check
passed.

This module is the structural half. It is not a ranking and it does not look at
prices: it deletes from the candidate list the structures whose payoff cannot
express the claim, before anything is sized or priced. If both halves agree, the
result is unchanged and this costs nothing. If they disagree, we find out.

WHAT IT DELIBERATELY DOES NOT DO
================================
It does not force a claim toward its "natural" instrument -- `direction` keeps
shares, calls, puts and both debit and credit vertical spreads, and choosing
among those stays an economic question about how much of the move you are paying
for. It only removes what the claim cannot say anything about.

And it never widens: a claim may not buy a structure outside its row because the
EV looked good. That is the direction the loss came from.
"""

from __future__ import annotations

#: Sign-dependent payoffs. A directional claim can express itself in any of
#: these; which one is an economic question (how much of the move am I paying
#: for, and does the shift clear the quote).
DIRECTIONAL = frozenset({
    "long_shares", "short_shares",
    "long_call", "long_put",
    "bull_call_spread", "bear_put_spread",     # debit verticals
    "bull_put_spread", "bear_call_spread",     # credit verticals
})

#: Long the absolute move. Pays when the outcome is WIDER than the chain charges.
LONG_ABSOLUTE = frozenset({"long_straddle", "long_strangle"})

#: Short the absolute move. Pays when the outcome is NARROWER. Sign-blind by
#: construction -- it is the same trade whether the print is up or down.
SHORT_ABSOLUTE = frozenset({"iron_condor", "iron_butterfly", "short_straddle", "short_strangle"})

#: claim -> the structures whose payoff can express it.
#:
#: `dispersion` gets both absolute rows because a width claim has a sign of its
#: own: "wider than quoted" buys the long row, "narrower than quoted" sells it.
#: The magnitude of `sd` against the chain's implied is what picks between them,
#: and that comparison is exactly what the sizer already does.
ADMISSIBLE: dict[str, frozenset[str]] = {
    "direction": DIRECTIONAL,
    "dispersion": LONG_ABSOLUTE | SHORT_ABSOLUTE,
    "distribution": DIRECTIONAL | LONG_ABSOLUTE | SHORT_ABSOLUTE,
}


def admissible(claim: str, kind: str) -> bool:
    """Can a forecast making `claim` express itself through `kind`?

    An UNKNOWN kind is admissible. A new structure must not be silently dropped
    by a matrix that has not heard of it -- that is a filter, and a filter on
    the thing you just built is invisible. `unclassified` names them instead.
    """
    row = ADMISSIBLE.get(claim)
    if row is None:
        return True
    return kind in row or kind not in KNOWN


#: Every kind this matrix has an opinion about.
KNOWN = DIRECTIONAL | LONG_ABSOLUTE | SHORT_ABSOLUTE


def unclassified(kinds) -> list[str]:
    """Structure kinds no row covers. A non-empty list is a bug in this file."""
    return sorted({k for k in kinds if k not in KNOWN})


def why_not(claim: str, kind: str) -> str:
    """The refusal text, naming the moment the payoff depends on."""
    if kind in SHORT_ABSOLUTE and claim == "direction":
        return (f"{kind} is sign-blind: it pays on the absolute move being SMALL and is the "
                f"same trade whether the move is up or down. This forecast claims DIRECTION "
                "only, so it has no evidence this structure can express. Measured on NVDA "
                "2026-08-26 the identical condor won the ranking at centre +0.72% and -0.72%.")
    if kind in LONG_ABSOLUTE and claim == "direction":
        return (f"{kind} pays on the ABSOLUTE move exceeding what the chain charges for both "
                "sides. This forecast claims DIRECTION only and makes no claim about width, "
                "so buying both sides spends evidence it does not have.")
    if kind in DIRECTIONAL and claim == "dispersion":
        return (f"{kind} pays on the SIGNED move. This forecast claims width only and its "
                "centre is pinned at zero, so it cannot say which side to take.")
    return f"{kind} cannot express a {claim!r} claim."
