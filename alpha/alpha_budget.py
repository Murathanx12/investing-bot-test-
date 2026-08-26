"""RESEARCH_ALPHA_BUDGET -- hypothesis generation is free, PROMOTION is not.

THE PROBLEM THIS EXISTS FOR
===========================
The night researcher is getting more creative, and that is the point. It is also
the failure mode: an agent that can generate five thousand variants will find a
beautiful t-statistic in pure noise, and preregistration alone does not stop it,
because each variant can be preregistered honestly one at a time. What
preregistration controls is *editing a hypothesis after seeing the data*. What
it does not control is *how many hypotheses were seen*.

This session produced the example. `bounce_battery` tested eight liquidity ×
horizon cells; the best reached a two-way clustered t of 1.99, which reads like
a discovery until you compute the expected maximum |t| of eight independent
draws -- 1.78. Adjusted for the eight looks, p = 0.317.

So: generation is unlimited, promotion is rationed.

WHY ONLINE, AND NOT JUST BH-FDR
===============================
CANON §63 already says SCREEN = BH-FDR and EXPORT = Holm, and both are BATCH
procedures: they need the full family of tests in hand. An autonomous researcher
does not have that -- it runs a test tonight and decides tomorrow whether to run
another, and the family is never closed. Batch FDR applied to a growing family
is not a correction, it is a moving target.

ALPHA-INVESTING (Foster & Stine 2008) is the online analogue. The researcher
holds a WEALTH of testable alpha. Each test spends some; a rejection pays a
dividend back; a failure to reject costs slightly more than it spent. When
wealth reaches zero the family is out of budget and further promotion is
refused -- generation continues, promotion does not. Under independence this
controls mFDR.

The economics are what make it behave: a family that keeps producing genuine
discoveries can afford to keep testing indefinitely, and a family that produces
nothing goes broke. That is the incentive the night lab needs, and it is
enforced arithmetically rather than by intention.

WHAT A FAMILY IS
================
A family is a line of inquiry that shares a data source and a question, e.g.
`post_event_drift`, `analyst_targets`, `causal_edges`. Cells inside one
experiment (buckets, horizons, variants) are TESTS in that family, not separate
families -- splitting them to get fresh budget is exactly the manoeuvre this
prevents, so `record_batch` charges for every cell examined, not just the one
that was reported.

THIS IS NOT A GATE ON LOOKING
=============================
Nothing here stops an experiment running, and nothing stops a number being
written down. It gates the word PROMOTED: whether a candidate may graduate
toward a forward book. A refused test is still recorded, with its p-value, in
the ledger -- the negative-results corpus is the asset, and a corpse with a
p-value is worth more than one without.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parent.parent / "state" / "alpha_budget.jsonl"

#: Starting wealth per family. Deliberately small: this is the total mFDR the
#: whole line of inquiry is allowed to spend, not a per-test level.
DEFAULT_WEALTH = 0.10

#: Dividend paid back on a discovery. Must be <= the starting wealth for the
#: guarantee to hold.
DEFAULT_PAYOUT = 0.05

#: A family is EXHAUSTED once it can no longer afford a test at this level.
#:
#: Without this the budget never actually runs out. Spending half the remaining
#: wealth each time decays it geometrically -- after twelve failures it was
#: 0.00002 and still nominally solvent -- so the guard could never fire. A gate
#: that cannot go red is not a gate. And the floor is not arbitrary: a family
#: that can only afford alpha = 0.0005 cannot pass a test in practice, so
#: letting it limp on is a fiction that costs real compute.
MIN_ALPHA = 0.001


def expected_max_abs_t(n: int) -> float:
    """Expected maximum |t| from `n` independent standard normal draws.

    The number that turns "our best cell hit t = 2.0" into a question rather
    than an answer.

    Computed by exact integration, `E[max] = integral_0^inf (1 - F(x)^n) dx`
    with `F(x) = erf(x/sqrt(2))`, NOT by the usual Gumbel approximation. The
    approximation was tried first and it UNDERSTATES this by 0.13 to 0.32 over
    the range that matters (n = 2..200, checked against 200k Monte-Carlo draws)
    -- and understating it is the dangerous direction, because it makes the
    noise bar look lower and a reported t look more remarkable than it is. A
    guard that errs toward "this is a discovery" is not a guard.
    """
    if n < 1:
        return 0.0
    if n == 1:
        return 0.7978845608  # E|N(0,1)| = sqrt(2/pi)
    # Simpson's rule to x = 10; the integrand is < 1e-15 beyond that.
    steps = 4000
    hi = 10.0
    h = hi / steps
    total = 0.0
    for i in range(steps + 1):
        x = i * h
        f = 1.0 - math.erf(x / math.sqrt(2.0)) ** n
        w = 1.0 if i in (0, steps) else (4.0 if i % 2 else 2.0)
        total += w * f
    return total * h / 3.0


def two_sided_p(t: float) -> float:
    """Two-sided normal p-value for a t statistic."""
    return math.erfc(abs(t) / math.sqrt(2.0))


@dataclass
class Verdict:
    family: str
    hypothesis: str
    n_tests_charged: int
    alpha_spent: float
    wealth_before: float
    wealth_after: float
    p_value: float | None
    best_t: float | None
    expected_max_t: float | None
    promoted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def wealth(family: str, *, start: float = DEFAULT_WEALTH) -> float:
    """Current testable alpha for a family."""
    w = start
    for r in _rows():
        if r.get("family") != family:
            continue
        w = r.get("wealth_after", w)
    return w


def history(family: str | None = None) -> list[dict]:
    return [r for r in _rows() if family is None or r.get("family") == family]


def record_batch(family: str, hypothesis: str, *, best_t: float,
                 n_tests: int, note: str = "", start: float = DEFAULT_WEALTH,
                 payout: float = DEFAULT_PAYOUT, dry_run: bool = False) -> Verdict:
    """Charge a family for an experiment and say whether it may be PROMOTED.

    `n_tests` is every cell that was LOOKED AT, not the one that was reported.
    That is the whole mechanism: an experiment that sliced eight buckets and
    reported the best one pays for eight.

    The test is applied to the best cell after a Bonferroni adjustment within
    the experiment (`p_adj = 1 - (1 - p)^n`, which is the exact probability that
    the best of n independent cells is at least this extreme). The online budget
    then handles the fact that this experiment is one of many over time.
    """
    w0 = wealth(family, start=start)
    p_raw = two_sided_p(best_t)
    p_adj = 1.0 - (1.0 - p_raw) ** max(1, n_tests)
    emax = expected_max_abs_t(n_tests)

    if w0 / 2.0 < MIN_ALPHA:
        v = Verdict(family, hypothesis, n_tests, 0.0, w0, w0, p_adj, best_t, emax, False,
                    f"FAMILY OUT OF BUDGET: {family!r} has {w0:.5f} testable alpha left, "
                    f"below the {MIN_ALPHA} it takes to run a test that could pass. "
                    "Generation continues; promotion does not. Retire a dead branch or "
                    "produce a discovery to earn wealth back.")
        _append(v, note, dry_run)
        return v

    # Spend half the remaining wealth on this test -- a standard, conservative
    # investing rule that can never exhaust the budget in one go.
    alpha_i = w0 / 2.0
    if p_adj <= alpha_i:
        w1 = w0 - alpha_i + payout
        v = Verdict(family, hypothesis, n_tests, alpha_i, w0, w1, p_adj, best_t, emax, True,
                    f"PROMOTABLE: best |t| {abs(best_t):.2f} over {n_tests} cells gives "
                    f"p_adj {p_adj:.4f} <= alpha {alpha_i:.4f}. Expected max |t| from "
                    f"{n_tests} noise draws is {emax:.2f}.")
    else:
        w1 = w0 - alpha_i / (1.0 - alpha_i)
        v = Verdict(family, hypothesis, n_tests, alpha_i, w0, w1, p_adj, best_t, emax, False,
                    f"NOT PROMOTABLE: best |t| {abs(best_t):.2f} over {n_tests} cells gives "
                    f"p_adj {p_adj:.4f} > alpha {alpha_i:.4f}. Expected max |t| from "
                    f"{n_tests} noise draws is {emax:.2f}"
                    + (" -- the reported t is BELOW what noise produces at this "
                       "many cells." if abs(best_t) < emax else "."))
    _append(v, note, dry_run)
    return v


def _append(v: Verdict, note: str, dry_run: bool) -> None:
    if dry_run:
        return
    row = {**v.as_dict(), "note": note,
           "ts_utc": datetime.now(timezone.utc).isoformat()}
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def summary() -> dict[str, Any]:
    """Per family: wealth left, tests charged, discoveries."""
    out: dict[str, Any] = {}
    for r in _rows():
        f = r["family"]
        b = out.setdefault(f, {"experiments": 0, "cells_charged": 0,
                               "promoted": 0, "wealth": DEFAULT_WEALTH})
        b["experiments"] += 1
        b["cells_charged"] += int(r.get("n_tests_charged") or 0)
        b["promoted"] += bool(r.get("promoted"))
        b["wealth"] = r.get("wealth_after", b["wealth"])
    for b in out.values():
        b["wealth"] = round(b["wealth"], 5)
        b["exhausted"] = b["wealth"] / 2.0 < MIN_ALPHA
    return out
