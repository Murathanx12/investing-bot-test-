"""Competition book limits -- implemented, tested, and called by NOTHING.

STATUS: NOT ENFORCED. No admission path imports this module. It exists so that
turning the limits on is a one-line, attended decision rather than an
implementation project at 15:00 UTC on the day the account opens.

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


@dataclass(frozen=True)
class Breach:
    limit: str
    observed: float
    threshold: float
    detail: str

    def line(self) -> str:
        return f"{self.limit}: {self.detail}"


def evaluate(*, equity: float, true_max_loss: float, free_capital: float,
             thesis_weights: dict[str, float] | None = None,
             n_risk: float | None = None) -> list[Breach]:
    """Every limit this book currently breaches. Empty list = within all of them.

    `n_risk=None` means concentration could NOT be measured. That is reported as
    its own breach rather than passing silently: "we could not look" and "it is
    fine" must never print the same.
    """
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
                                  f"{100*MAX_SINGLE_THESIS:.0f}% cap."))

    if n_risk is None:
        out.append(Breach("MIN_EFFECTIVE_N_RISK", float("nan"), MIN_EFFECTIVE_N_RISK,
                          "concentration could NOT be measured. This is not evidence of "
                          "diversification -- 'we could not look' and 'it is fine' must not "
                          "print the same."))
    elif n_risk < MIN_EFFECTIVE_N_RISK:
        near = (" -- at or below the value a $20bn book carried at forced liquidation"
                if n_risk <= REFERENCE_N_RISK_AT_LIQUIDATION else "")
        out.append(Breach("MIN_EFFECTIVE_N_RISK", n_risk, MIN_EFFECTIVE_N_RISK,
                          f"the book behaves like {n_risk:.2f} independent bet(s) against a "
                          f"{MIN_EFFECTIVE_N_RISK:.1f} floor{near}."))
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
