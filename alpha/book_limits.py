"""Competition book limits -- ENFORCED at the admission choke point.

STATUS: LIVE since 2026-08-27. `alpha.admission.admit()` calls `evaluate()` on
the POST-trade book and refuses on any BINDING breach, so these bind from trade
number one on any account -- including the judged one, before it exists.

They were written weeks earlier and called by nothing. The reason was not
neglect, and it is worth recording because it is the whole design of this file:
wired naively they DEADLOCK a fresh account. A pristine $100,000 book taking a
healthy 2%-risk first trade breaches MAX_SINGLE_THESIS (one position is 100% of
book max loss) and MIN_EFFECTIVE_N_RISK (one position is 1.00 independent bets).
Both are arithmetic identities on a small book, not risk statements. See
DIVERSIFICATION_BINDS_AT.

WHY THESE SIX
=============
The rehearsal book reached **72.9% of equity in true max loss** while every
structure was defined-risk and every admission check passed. Nothing was
violated. The existing checks are per-ORDER and per-UNDERLYING; none of them
ever asked a question about the book as a whole.

Each threshold below carries its derivation, and the one without evidence is
left UNSET rather than filled in to make the set look complete.

    MAX_BOOK_STRESS        35%   Situational Awareness's unlevered Q2 book lost
                                 23.3% over 41 sessions and SURVIVED. A cap here
                                 means a full simultaneous realisation leaves the
                                 account solvent, at about the worst that
                                 portfolio actually produced without leverage.
    MAX_SINGLE_THESIS      20%   dev carried 52.4% of max loss on NVDA on the
                                 night NVDA reported. No definition of
                                 "diversified" survives one name being more than
                                 half the downside.
    MIN_EFFECTIVE_N_RISK   2.0   Every failure state measured sits below it:
                                 SA 1.43 at forced liquidation, exp1 1.27,
                                 dev 1.51. This is a floor drawn ABOVE the
                                 observed wreckage, not a theoretical result, and
                                 it should move once books that survived a bad
                                 week are measured too.
    MIN_FREE_CAPITAL       25%   32 of 48 refusals are already "we already own
                                 it". Free capital is both the capacity to take
                                 the next idea and the buffer that makes an exit
                                 a choice rather than a liquidation.
    MAX_EVENT_CLUSTER       --   already enforced as EVENT_NODE_CAP; listed so
                                 the set is complete. But note it counts what
                                 brains TAG, and no brain tags.
    MAX_DAILY_THETA       UNSET  I can compute the book's theta and have NO
                                 evidence for a threshold. A number invented here
                                 would look exactly like the four above and carry
                                 none of their derivation.

**A threshold without a derivation is a guess wearing a policy's clothes.**

WHAT A VERDICT IS
=================
`evaluate()` returns a list of `Breach`, never a bool. A caller decides whether
a breach refuses, warns, or resizes -- that policy belongs at the call site,
attended, not buried here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_BOOK_STRESS = 0.35
MAX_SINGLE_THESIS = 0.20
MIN_EFFECTIVE_N_RISK = 2.0
MIN_FREE_CAPITAL = 0.25
MAX_DAILY_THETA = None          # deliberately unset; see the module docstring

#: The value a real $20bn book carried at the moment leverage plus a correlated
#: drawdown forced its liquidation. Kept beside the floor so the floor can be
#: argued about against evidence rather than taste.
REFERENCE_N_RISK_AT_LIQUIDATION = 1.43


#: The position count at which the two DIVERSIFICATION limits start to bind.
#:
#: Below it they are arithmetic identities, not risk statements: a one-position
#: book carries 100% of its max loss in one thesis and behaves like exactly 1.00
#: independent bet, no matter how small or how sensible that position is. A
#: pristine $100,000 account taking a healthy 2% first trade breaches BOTH. Wired
#: without this, the judged account could never place its first order -- and a
#: gate that cannot go green is a broken gate, not a strict one.
#:
#: 5 is not invented here: `SOURCE_PEAD_MID_v1` already declares
#: `min_effective_n_by_risk_before_6th: 2.0` -- the floor is a condition on
#: adding a SIXTH position, so it starts binding once five are held.
#:
#: They are still MEASURED and REPORTED below it. A four-position book with 90%
#: of its risk in one name must not read as clean.
DIVERSIFICATION_BINDS_AT = 5


@dataclass(frozen=True)
class Breach:
    limit: str
    observed: float
    threshold: float
    detail: str
    #: False = measured and exceeded, but not yet enforceable. Never means "fine".
    binding: bool = True

    def line(self) -> str:
        flag = "" if self.binding else "  [measured, not yet binding]"
        return f"{self.limit}: {self.detail}{flag}"


def refusing(breaches: list["Breach"]) -> list["Breach"]:
    """Only the breaches that must stop an order. Reporting is the caller's job."""
    return [b for b in breaches if b.binding]


def evaluate(*, equity: float, true_max_loss: float, free_capital: float,
             thesis_weights: dict[str, float] | None = None,
             n_risk: float | None = None,
             n_positions: int | None = None) -> list[Breach]:
    """Every limit this book currently breaches. Empty list = within all of them.

    `n_risk=None` means concentration could NOT be measured. That is reported as
    its own breach rather than passing silently: "we could not look" and "it is
    fine" must never print the same.

    `n_positions` decides whether the two DIVERSIFICATION limits BIND -- see
    DIVERSIFICATION_BINDS_AT. Passing None means the count is unknown, and an
    unknown count binds: a caller that cannot say how many positions it holds
    does not get the benefit of the warm-up.
    """
    # `< N` and not `<= N`: at exactly DIVERSIFICATION_BINDS_AT held positions the
    # next order is the (N+1)th, which is the one the PEAD contract's
    # "before_6th" wording constrains.
    diversification_binds = n_positions is None or n_positions >= DIVERSIFICATION_BINDS_AT
    _warmup = (f" Held {n_positions} position(s), below the {DIVERSIFICATION_BINDS_AT} at which "
               "this limit binds: with fewer, it is an arithmetic identity rather than a risk "
               "statement, so it is MEASURED and reported but does not refuse.")
    out: list[Breach] = []
    if equity <= 0:
        return [Breach("EQUITY", equity, 0.0,
                       "equity is not positive; no limit is meaningful against it")]

    stress = true_max_loss / equity
    if stress > MAX_BOOK_STRESS:
        out.append(Breach("MAX_BOOK_STRESS", stress, MAX_BOOK_STRESS,
                          f"true max loss is {100*stress:.1f}% of equity against a "
                          f"{100*MAX_BOOK_STRESS:.0f}% cap. The rehearsal book reached 72.9% "
                          f"with every individual check passing."))

    free = free_capital / equity
    if free < MIN_FREE_CAPITAL:
        out.append(Breach("MIN_FREE_CAPITAL", free, MIN_FREE_CAPITAL,
                          f"free capital is {100*free:.1f}% of equity against a "
                          f"{100*MIN_FREE_CAPITAL:.0f}% floor. A book with no room refuses new "
                          f"ideas on 'already held' rather than on their merits."))

    if thesis_weights:
        total = sum(abs(v) for v in thesis_weights.values())
        if total > 0:
            sym, w = max(thesis_weights.items(), key=lambda kv: abs(kv[1]))
            share = abs(w) / total
            if share > MAX_SINGLE_THESIS:
                out.append(Breach("MAX_SINGLE_THESIS", share, MAX_SINGLE_THESIS,
                                  f"{sym} carries {100*share:.1f}% of book max loss against a "
                                  f"{100*MAX_SINGLE_THESIS:.0f}% cap."
                                  + ("" if diversification_binds else _warmup),
                                  binding=diversification_binds))

    if n_risk is None:
        # An UNMEASURED concentration binds on the same schedule as a measured
        # one, and for the same reason. A first draft made it bind ALWAYS,
        # reasoning that "we could not look" must never pass -- but on a
        # one-position book n_risk is DEFINITIONALLY 1.00 and needs no
        # measurement, so that rule refused every fresh account for failing to
        # measure something arithmetic. Once the book is large enough for the
        # limit to bind, an unmeasured value refuses: there, not looking really is
        # different from being fine.
        out.append(Breach("MIN_EFFECTIVE_N_RISK", float("nan"), MIN_EFFECTIVE_N_RISK,
                          "concentration could NOT be measured. This is not evidence of "
                          "diversification -- 'we could not look' and 'it is fine' must not "
                          "print the same." + ("" if diversification_binds else _warmup),
                          binding=diversification_binds))
    elif n_risk < MIN_EFFECTIVE_N_RISK:
        near = (" -- at or below the value a $20bn book carried at forced liquidation"
                if n_risk <= REFERENCE_N_RISK_AT_LIQUIDATION else "")
        out.append(Breach("MIN_EFFECTIVE_N_RISK", n_risk, MIN_EFFECTIVE_N_RISK,
                          f"the book behaves like {n_risk:.2f} independent bet(s) against a "
                          f"{MIN_EFFECTIVE_N_RISK:.1f} floor{near}."
                          + ("" if diversification_binds else _warmup),
                          binding=diversification_binds))
    return out


def summary(breaches: list[Breach]) -> str:
    if not breaches:
        return "within every declared book limit"
    return f"{len(breaches)} limit(s) breached: " + "; ".join(b.line() for b in breaches)


def would_admit(breaches: list[Breach]) -> bool:
    """Convenience for a caller that wants a bool. Deliberately NOT used here:
    whether a breach refuses, warns or resizes is a policy decision that belongs
    at an attended call site."""
    return not breaches
