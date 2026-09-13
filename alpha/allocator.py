"""THE ALLOCATOR -- cut losers on RISK, promote winners on RETURN, slowly.

    python -m scripts.allocator --anchor          # once, on deploy day
    python -m scripts.allocator --run             # once a day, after the close
    python -m scripts.allocator --show            # today's record, no writes

THE ASYMMETRY, AND WHY IT IS NOT A STYLE CHOICE
===============================================
A drawdown is observed directly, in dollars, the same day it happens: no
significance test is needed to know a book is down 7.5%. A RETURN EDGE needs
enough independent observations to separate signal from the book's own
volatility, and at this fleet's ~1.5% daily book-level sd, **ten daily marks
cannot distinguish a winning book from a lucky one below roughly 340%
annualised** -- the arithmetic is in `docs/TRIALS/TRIAL-DRAFT-ALLOCATOR-v0.md`
section 2 and it is not close. So:

  * **kill on RISK, mechanically, from day two.** -5% from the book's own peak
    halves its gross; -7.5% floors it at a de-minimis 2% for twenty sessions.
    These are the numbers reported for Millennium (Rubinstein, "Peak Pod",
    2023) and they need almost no data underneath them.
  * **promote on RETURN, slowly, capped, and never in one jump.** A book's
    share moves toward its Thompson posterior, no book exceeds a declared 35%
    of the pool, and **the capital a cut frees is NOT handed to the winners**:
    it becomes `cash_weight` and is printed. There is no symmetric ratchet-up
    in the reported pod-shop rules and this file does not invent one.

A KILLED BOOK IS NEVER SET TO ZERO
==================================
`FLOOR_WEIGHT` is 2%, not 0. Every book keeps marking whatever its weight, which
is what makes the twins in `twins()` EXACT rather than estimated: the
counterfactual "what would equal-weight have earned" is a re-weighting of six
fully observed daily series, so no importance-weighted off-policy estimator is
needed. Setting a book to zero would end its series and destroy that property
permanently.

THE POOL WEIGHT AND THE GROSS BUDGET ARE TWO DIFFERENT OBJECTS
==============================================================
Six Alpaca accounts are six separate venues and **capital cannot move between
them**. So this module computes two things and never confuses them:

  * `allocator_weight` -- a POOL SHARE. It is a paper portfolio over the six
    books and it exists to be graded against the two twins. It is arithmetic,
    not an instruction.
  * `gross_budget_scale` -- what the loop actually reads: the fraction of its
    OWN declared gross a book may put on, `min(1.0, kill_scale x share / equal
    share)`. It can only ever REDUCE. Promotion restores a book toward its own
    100% and never beyond, because leverage is not on the table
    (`tests_smoke_monday` pins gross cap <= 1.0).

WHAT THE LLM HAS TO DO WITH THIS
================================
Nothing. There is no model call, no text, and no import of anything that makes
one, in this module or in `scripts/allocator.py`. Pinned by test.

LICENCE: `PRODUCT_EXPERIMENT`, trial `TRIAL-DRAFT-ALLOCATOR-v0` (UNSIGNED). The
allocator is itself a strategy and is graded like one: if it cannot beat its own
equal-weight twin over 60 trading sessions it is a `FAILED_VARIANT` and the
fleet runs equal-weighted under the kill floor alone. The kill floor is NOT part
of what is being tested and does not wait for that verdict.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRIAL = "TRIAL-DRAFT-ALLOCATOR-v0"
LICENCE = "PRODUCT_EXPERIMENT"

STATE = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "allocator"
SEED_STATE = ROOT / "docs" / "seed" / "allocator"
ANCHOR = "anchor.json"

# --------------------------------------------------------------------------
# THE FROZEN CONTRACT
#
# Every number below is fixed BEFORE the first decision and hashed into every
# daily receipt. Changing one changes `contract_sha256()`, which is how a reader
# three months from now can tell "the rule fired" from "the rule was edited".

#: The six venue accounts. `hack2` is NOT here: Murat reassigned it to lane D on
#: 2026-09-13 12:05 HKT and its loop is down. A role that is not in this tuple
#: is not allocated to, and `budget_for` refuses it by name rather than handing
#: it a default.
ROLES = ("hack1", "hack3", "hack4", "hack5", "hack6")

#: Millennium's reported ladder (Rubinstein, "Peak Pod", Sept 2023, as cited by
#: hedgefundinterview.com and Young & Calculated). Widely reported, NOT
#: officially published -- said here because a number whose provenance is
#: forgotten becomes a number nobody may question.
CUT_HALVE = -0.05
CUT_FLOOR = -0.075

#: "still measured, not funded". Never 0 -- see the module docstring.
FLOOR_WEIGHT = 0.02

#: Trading sessions a floored book stays floored. It is re-examined after, with
#: a fresh contract, never silently re-armed.
COOLDOWN_SESSIONS = 20

#: No book exceeds this share of the pool. Chosen because `alpha/guards.py` and
#: `alpha/book_limits` already treat >30-40% concentration as the thing that
#: needs a name -- not because 35% was fit to any outcome here.
CEILING = 0.35

#: Book-level daily return sd, the working number section 2's arithmetic is
#: built on (`alpha/fleet.py`'s own caveat measured the theme basket at 60-170%
#: annualised). It is the OBSERVATION sd in the posterior update and it is
#: declared rather than estimated from the live curve, because estimating it
#: from ten marks is the same small-sample problem one level down.
DAILY_SD = 0.015

#: Draws for the Thompson step. `np.random.default_rng(seed)`, seeded from the
#: day, so a given day's allocation is reproducible from its own receipt.
N_DRAWS = 4000

#: The trial's own decision horizon (sessions from the anchor).
DECISION_SESSIONS = 60

#: COMPLETE DATE BLOCKS a book needs before its gross budget may move ON RETURN.
#:
#: Below this the drawdown rule is the ONLY thing that moves a budget. The
#: asymmetry section 1 states is about evidence, not about direction: a CUT on
#: return is as unreliable at n=0 as a promotion on return is, and an allocator
#: that cut a book to 12% of its size on day one because three other books had
#: ten sessions of luck would be doing the exact thing this contract exists to
#: prevent. The pool weights are still computed, printed and GRADED against both
#: twins from day one -- the trial's own primary metric needs that from the
#: first session -- they simply do not touch a live book's size yet.
#:
#: Three, because a block mean is an observation and two observations have no
#: dispersion to speak of; at hack3's 21-session block that is a quarter, which
#: is the order the spec's own table says a return signal needs.
MIN_BLOCKS_FOR_BUDGET = 3

#: Each book's prior on its DAILY excess over the fleet's equal-weight return,
#: with the evidence it rests on. Two shapes, and the difference is the point:
#:
#:   * hack3 carries Book F's REPLAY prior -- 419 monthly blocks, t 3.1178 --
#:     because its engine is F as of chunk 13b and its live curve belongs to the
#:     tracker engine that was retired. That prior is TIGHT.
#:   * every other book carries its OWN realised excess over the fleet mean on
#:     the 2026-08-28..2026-09-11 live window, which is TEN SESSIONS and, at
#:     each book's own minimum hold, is FEWER THAN ONE DATE BLOCK. That number
#:     is recorded here and REPORTED on every receipt, and `prior_for` does NOT
#:     use it as a centre -- see the comment there. Canon section 58 counts date
#:     blocks, and zero blocks is zero evidence about a mean.
#:
#: Equities read live 2026-09-13 12:10 HKT; each began at $100,000. Fleet mean
#: over the five allocated books = -9.4336%, so `excess_window` below is
#: (book return - that mean) and `mean` is that divided by the ten sessions.
PRIOR_WINDOW = {
    "first_session": "2026-08-28", "last_session": "2026-09-11", "sessions": 10,
    "benchmark": "the equal-weight mean of the five allocated books (-9.4336%)",
    "spy_same_window": -0.0066,
}

PRIORS: dict[str, dict] = {
    "hack1": {"equity": 93_863.0, "excess_window": +0.03297,
              "source": "own realised curve, 10 sessions"},
    "hack3": {"equity": 83_342.0, "excess_window": None,
              "source": ("Book F's replay at the $10M floor: +0.4328%/month net "
                         "vs its turnover-matched twin, t 3.1178, 419 blocks "
                         "(night_factory_2026-09-13/B_books_efg_replay_run01.json). "
                         "The live curve belongs to the tracker engine this book "
                         "no longer runs and is NOT the prior."),
              "mean": 0.004328 / 21.0,
              "sd": (0.004328 / 3.1178) / 21.0,
              "n_effective_blocks": 419},
    "hack4": {"equity": 92_941.0, "excess_window": +0.02375,
              "source": "own realised curve, 10 sessions"},
    "hack5": {"equity": 95_095.0, "excess_window": +0.04529,
              "source": ("own realised curve, 10 sessions; the premium bound "
                         "(-15%) is unchanged by this allocator")},
    "hack6": {"equity": 87_591.0, "excess_window": -0.02975,
              "source": "own realised curve, 10 sessions"},
}


def contract() -> dict:
    """Every frozen number, as data. Hashed into every daily receipt."""
    return {
        "trial": TRIAL, "licence": LICENCE, "roles": list(ROLES),
        "cut_halve": CUT_HALVE, "cut_floor": CUT_FLOOR,
        "floor_weight": FLOOR_WEIGHT, "cooldown_sessions": COOLDOWN_SESSIONS,
        "ceiling": CEILING, "daily_sd": DAILY_SD, "n_draws": N_DRAWS,
        "decision_sessions": DECISION_SESSIONS,
        "prior_window": PRIOR_WINDOW,
        "priors": {r: {k: v for k, v in p.items()} for r, p in PRIORS.items()},
        "excess_definition": (
            "a book's daily excess is its own return minus the EQUAL-WEIGHT mean "
            "return of the books that are not floored that day. That quantity is "
            "fully observed for every book on every day whatever weight it "
            "carries, which is what makes both twins exact rather than estimated, "
            "and it is the quantity a weight decision is actually about: "
            "over-weight a book if and only if it beats the average book."),
        "block_definition": (
            "n_effective counts DATE BLOCKS, not daily marks (canon section 58). "
            "A block is `contract.HORIZON_REMAP[role]['min_normal_hold_sessions']` "
            "consecutive sessions -- the book's own declared minimum hold, the "
            "shortest period over which two of its positions can be independent. "
            "An incomplete block is not counted."),
        "promotion_never_jumps": (
            "capital freed by a cut becomes `cash_weight` and is NOT "
            "redistributed. No symmetric ratchet-up is reported for any pod "
            "shop and this contract does not invent one."),
    }


def contract_sha256() -> str:
    return hashlib.sha256(json.dumps(
        contract(), sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


class AllocatorUnavailable(RuntimeError):
    """The allocator cannot state a budget, and says which input is missing.

    Raised rather than returning 1.0. "A missing allocator file means the book
    keeps yesterday's budget and says so, never a default of 100%" -- and where
    there is no yesterday either, the honest answer is a refusal that stops a
    deploy, not a silent full-size book.
    """


# --------------------------------------------------------------------------
# the per-book arithmetic


@dataclass
class Prior:
    mean: float
    sd: float
    n_effective_blocks: float
    source: str
    status: str


def block_sessions(role: str) -> int:
    """The book's own declared minimum hold. Derived, never chosen here."""
    from alpha import contract as _c

    k = _c.HORIZON_REMAP.get(role)
    if not k:
        raise AllocatorUnavailable(
            f"role {role!r} has no horizon contract in contract.HORIZON_REMAP "
            f"({sorted(_c.HORIZON_REMAP)}), so its date-block length cannot be "
            f"derived. A guard derives its inputs or it refuses.")
    return max(1, int(k["min_normal_hold_sessions"]))


def prior_for(role: str) -> Prior:
    p = PRIORS.get(role)
    if p is None:
        raise AllocatorUnavailable(
            f"no declared prior for {role!r}. Every book's posterior is seeded "
            f"from ITS OWN evidence; an undeclared book would start from "
            f"ignorance, which throws away what has already been measured.")
    if p.get("mean") is not None:
        return Prior(float(p["mean"]), float(p["sd"]),
                     float(p["n_effective_blocks"]), p["source"], "MEASURED")
    blocks = PRIOR_WINDOW["sessions"] / block_sessions(role)
    mean = float(p["excess_window"]) / PRIOR_WINDOW["sessions"]
    if blocks < 1.0:
        # ZERO COMPLETE BLOCKS IS ZERO EVIDENCE ABOUT A MEAN, AND THAT APPLIES
        # TO THE CENTRE AS MUCH AS TO THE SPREAD.
        #
        # The spec asked for the live books to be seeded with their own realised
        # curve. Computed, those centres are +0.24% to +0.45% PER DAY -- 60% to
        # 110% annualised excess -- from TEN sessions, which is exactly the
        # regime the spec's own arithmetic says is unreadable (a t=2 read at
        # n=10 needs 0.95%/day). Using them as centres would hand the largest
        # budgets to the three books whose evidence is thinnest, which is the
        # failure this whole document exists to prevent. So the centre is ZERO,
        # the observed number is REPORTED beside it, and canon section 58 is
        # applied where it bites rather than where it is convenient.
        return Prior(
            0.0, DAILY_SD, 0.0, p["source"],
            f"UNINFORMATIVE: {PRIOR_WINDOW['sessions']} sessions is {blocks:.2f} "
            f"of one {block_sessions(role)}-session date block. Observed window "
            f"excess {mean:+.4%}/day is REPORTED and NOT used as the centre -- "
            f"zero complete blocks is zero evidence about a mean.")
    return Prior(mean, DAILY_SD / math.sqrt(blocks), blocks, p["source"], "MEASURED")


def blocks_of(excess: list[float], n: int) -> list[float]:
    """Complete, non-overlapping block means. An incomplete tail is dropped."""
    out = []
    for i in range(0, len(excess) - n + 1, n):
        chunk = excess[i:i + n]
        out.append(sum(chunk) / len(chunk))
    return out


def posterior(prior: Prior, block_means: list[float], n_sessions_per_block: int,
              *, daily_sd: float = DAILY_SD) -> dict:
    """Normal-Normal update of the mean daily excess on complete date blocks."""
    sigma_block = daily_sd / math.sqrt(max(1, n_sessions_per_block))
    n = len(block_means)
    if n == 0:
        return {"mean": prior.mean, "sd": prior.sd, "n_effective_date_blocks": 0,
                "status": "PRIOR ONLY -- no complete date block has closed yet",
                "prior_status": prior.status, "prior_source": prior.source}
    prec = 1.0 / (prior.sd ** 2) + n / (sigma_block ** 2)
    mean = (prior.mean / (prior.sd ** 2) + sum(block_means) / (sigma_block ** 2)) / prec
    return {"mean": mean, "sd": math.sqrt(1.0 / prec), "n_effective_date_blocks": n,
            "status": "UPDATED", "prior_status": prior.status,
            "prior_source": prior.source}


def drawdown(curve: list[dict], *, since: str | None = None) -> dict:
    """Peak-to-now on the book's own equity, measured from `since` onward.

    `since` is the LATER of the anchor and the last weight change, exactly as
    the contract states: a book whose weight was already cut restarts its peak
    at the cut, or a halved book could never leave the floor however it
    recovered.
    """
    pts = [r for r in curve if since is None or str(r["day"]) >= str(since)]
    if not pts:
        return {"peak": None, "current": None, "drawdown": None,
                "status": "CANNOT DETERMINE -- no mark since " + str(since)}
    eq = [float(r["equity"]) for r in pts]
    peak = max(eq)
    cur = eq[-1]
    return {"peak": peak, "current": cur,
            "drawdown": (cur / peak - 1.0) if peak > 0 else None,
            "n_marks": len(eq), "peak_measured_since": since, "status": "OK"}


def kill_step(dd: float | None, *, state: str, cooldown_left: int) -> dict:
    """One book's kill state for today. Cuts are one-way until the cooldown clears."""
    if cooldown_left > 0:
        return {"state": "FLOOR", "scale": FLOOR_WEIGHT,
                "cooldown_left": cooldown_left - 1,
                "fired": None,
                "why": f"COOLDOWN: {cooldown_left - 1} session(s) left at the floor"}
    if dd is None:
        # A guard that cannot measure its input says so; it does not assume the
        # book is fine and it does not kill it either.
        return {"state": state, "scale": _scale_of(state), "cooldown_left": 0,
                "fired": None,
                "why": "CANNOT DETERMINE -- no drawdown could be measured; "
                       "yesterday's state is carried and said out loud"}
    if dd <= CUT_FLOOR:
        return {"state": "FLOOR", "scale": FLOOR_WEIGHT,
                "cooldown_left": COOLDOWN_SESSIONS,
                "fired": (f"drawdown {dd:.2%} at or beyond {CUT_FLOOR:.1%}: gross "
                          f"floored at {FLOOR_WEIGHT:.0%} for {COOLDOWN_SESSIONS} "
                          f"sessions; the book keeps marking"),
                "why": "FLOOR"}
    if dd <= CUT_HALVE:
        if state in ("HALVED", "FLOOR"):
            return {"state": state, "scale": _scale_of(state), "cooldown_left": 0,
                    "fired": None, "why": f"already {state} at drawdown {dd:.2%}"}
        return {"state": "HALVED", "scale": 0.5, "cooldown_left": 0,
                "fired": (f"drawdown {dd:.2%} at or beyond {CUT_HALVE:.1%}: gross "
                          f"halved 1.00 -> 0.50"),
                "why": "HALVED"}
    if state == "HALVED":
        # RECOVERY IS NOT AUTOMATIC AND IT IS NOT PERMANENT EXILE EITHER. The
        # peak restarts at the cut (see `drawdown(since=)`), so a halved book
        # that makes a new post-cut high has, by construction, recovered on its
        # OWN measure -- and only then does it come back, one step, to full.
        return {"state": "ACTIVE", "scale": 1.0, "cooldown_left": 0,
                "fired": (f"recovered to a new post-cut high (drawdown {dd:.2%} "
                          f"from the peak measured since the cut): gross restored "
                          f"0.50 -> 1.00"),
                "why": "RESTORED"}
    return {"state": "ACTIVE", "scale": 1.0, "cooldown_left": 0, "fired": None,
            "why": f"drawdown {dd:.2%} inside the {CUT_HALVE:.1%} line"}


def _scale_of(state: str) -> float:
    return {"ACTIVE": 1.0, "HALVED": 0.5, "FLOOR": FLOOR_WEIGHT}.get(state, 1.0)


# --------------------------------------------------------------------------
# the weights


def apply_ceiling(raw: dict, *, ceiling: float = CEILING) -> tuple[dict, set]:
    """Water-fill `raw` (which sums to 1 over its keys) under a per-book cap."""
    w = dict(raw)
    bound: set = set()
    for _ in range(len(w) + 1):
        over = [k for k, v in w.items() if v > ceiling + 1e-12]
        if not over:
            break
        bound |= set(over)
        spill = sum(w[k] - ceiling for k in over)
        for k in over:
            w[k] = ceiling
        free = [k for k in w if k not in bound]
        tot = sum(w[k] for k in free)
        if not free or tot <= 0:
            break
        for k in free:
            w[k] += spill * w[k] / tot
    return w, bound


def thompson(posteriors: dict, *, seed: int, n_draws: int = N_DRAWS) -> dict:
    """Thompson weights on a SHARPE-SHAPED reward, plus P(best) for the receipt.

    WHY NOT P(BEST), WHICH IS THE TEXTBOOK FORM. P(best) rewards VARIANCE: a
    book with no evidence at all (posterior N(0, 1.5%/day)) wins the argmax
    about as often as it loses, while a book with a genuinely measured but
    modest edge -- Book F's replay prior is +0.0206%/day with sd 0.0066% -- wins
    it almost never. Measured on this fleet's own day-one posteriors, P(best)
    gave the ONLY book with 419 blocks of evidence a 2.4% share and the four
    books with zero blocks 24% each. An allocator that systematically funds the
    least-measured book is worse than no allocator.

    So the sampled quantity is `max(sample, 0) / posterior_sd` -- the reward the
    spec's own literature note prefers ("risk-adjusted (Sharpe-shaped) reward
    rather than raw return ... closer to what a thin-sample bandit can actually
    resolve"). It is still Thompson: one draw per book per iteration from that
    book's own posterior, averaged. It reduces to a book's own t-statistic where
    the posterior IS the replay prior, and it penalises uncertainty instead of
    paying for it.

    `p_best` is computed anyway and printed on the receipt, because the textbook
    quantity is what a later reader will ask for -- but it decides nothing, and
    the receipt says which of the two did.
    """
    import numpy as np

    keys = sorted(posteriors)
    if not keys:
        return {"weights": {}, "p_best": {}}
    rng = np.random.default_rng(int(seed))
    draws = np.column_stack([
        rng.normal(posteriors[k]["mean"], max(posteriors[k]["sd"], 1e-12), n_draws)
        for k in keys])
    sds = np.array([max(posteriors[k]["sd"], 1e-12) for k in keys])
    score = np.clip(draws, 0.0, None) / sds
    mean_score = score.mean(axis=0)
    total = float(mean_score.sum())
    if total <= 0:
        w = {k: 1.0 / len(keys) for k in keys}
    else:
        w = {k: float(mean_score[i]) / total for i, k in enumerate(keys)}
    wins = np.bincount(draws.argmax(axis=1), minlength=len(keys))
    return {"weights": w,
            "p_best": {k: float(wins[i]) / float(n_draws) for i, k in enumerate(keys)},
            "reward": "max(sampled mean, 0) / posterior sd  (Sharpe-shaped)"}


def twins(survivors: list[str], *, seed: int) -> dict:
    """The two comparators, built WITH the allocator and on the same clock.

    Twin 1 -- equal weight over the surviving books (DeMiguel, Garlappi & Uppal
    2009: naive 1/N frequently beats optimised weights out of sample because
    estimation error costs more than the optimisation gains, which is exactly
    the exposure a thin-data bandit has here).

    Twin 2 -- a constrained random draw (Dirichlet(1)). If the allocator cannot
    beat a properly constrained random allocation, its apparent skill is the
    CONSTRAINTS doing the work, not the learning -- so the twin gets the same
    ceiling and the same kill scales, applied by the caller.
    """
    import numpy as np

    if not survivors:
        return {"equal_weight": {}, "random_dirichlet": {}}
    ew = {r: 1.0 / len(survivors) for r in survivors}
    rng = np.random.default_rng(int(seed) ^ 0xD1C4)
    d = rng.dirichlet(np.ones(len(survivors)))
    return {"equal_weight": ew,
            "random_dirichlet": {r: float(d[i]) for i, r in enumerate(sorted(survivors))}}


def _weights_from_base(base: dict, kill: dict) -> tuple[dict, dict, float]:
    """base (sums to 1 over survivors) -> capped -> x kill scale; floors forced."""
    capped, bound = apply_ceiling(base)
    w, binding = {}, {}
    for r, k in kill.items():
        if k["state"] == "FLOOR":
            w[r] = FLOOR_WEIGHT
            binding[r] = "kill:FLOOR"
            continue
        w[r] = capped.get(r, 0.0) * k["scale"]
        binding[r] = ("kill:HALVED" if k["state"] == "HALVED"
                      else ("ceiling" if r in bound else "none"))
    cash = max(0.0, 1.0 - sum(w.values()))
    return w, binding, cash


@dataclass
class Day:
    day: str
    licence: str = LICENCE
    trial: str = TRIAL
    contract_hash: str = ""
    per_book: dict = field(default_factory=dict)
    rule_fired: list = field(default_factory=list)
    kill_log: list = field(default_factory=list)
    promotion_log: list = field(default_factory=list)
    worst_case_usd_fleet: float | None = None
    worst_case_pct_equity_fleet: float | None = None
    allocator_vs_equal_weight_twin_cum_excess: float | None = None
    allocator_vs_random_twin_cum_excess: float | None = None
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def allocate(day: str, *, curves: dict, anchor: dict, yesterday: dict | None = None,
             seed: int | None = None) -> dict:
    """One day's allocation. Pure over its inputs; writes nothing.

    `curves`   {role: [{"day":..., "equity":...}, ...]} ascending by day
    `anchor`   the anchor record (deploy-time equity per role)
    `yesterday` the previous day's record, for the kill state and the cooldown
    """
    from alpha import contract as _c

    seed = int(seed if seed is not None else int(str(day).replace("-", "")))
    prev = ((yesterday or {}).get("per_book") or {})
    anchor_books = (anchor or {}).get("books") or {}

    kill, dds, states = {}, {}, {}
    for r in ROLES:
        a = anchor_books.get(r) or {}
        since = prev.get(r, {}).get("peak_measured_since") or a.get("anchor_day")
        dd = drawdown(curves.get(r) or [], since=since)
        dds[r] = dd
        step = kill_step(dd.get("drawdown"),
                         state=prev.get(r, {}).get("kill_state_base", "ACTIVE"),
                         cooldown_left=int(prev.get(r, {}).get("cooldown_left", 0)))
        kill[r] = step
        # A state CHANGE restarts the peak window: today's mark becomes the new
        # reference. Without this a cut book can never recover on its own terms.
        states[r] = (day if step["fired"] else since)

    # the daily excess series, per book, against the equal-weight mean of the
    # books that are not floored -- computed on every day, for every book,
    # whatever weight it actually carried. That is what makes the twins exact.
    rets = _returns(curves)
    survivors = [r for r in ROLES if kill[r]["state"] != "FLOOR"]
    excess = _excess(rets, survivors)

    posts = {}
    for r in survivors:
        n = block_sessions(r)
        posts[r] = posterior(prior_for(r), blocks_of(excess.get(r, []), n), n)

    draw = thompson(posts, seed=seed) if posts else {"weights": {}, "p_best": {}}
    base = draw["weights"]
    tw = twins(survivors, seed=seed)

    w, binding, cash = _weights_from_base(base, kill)
    ew_w, _, ew_cash = _weights_from_base(tw["equal_weight"], kill)
    rd_w, _, rd_cash = _weights_from_base(tw["random_dirichlet"], kill)

    ew_share = (1.0 / len(survivors)) if survivors else 0.0
    rec = Day(day=str(day), contract_hash=contract_sha256())
    worst_usd, equity_total = 0.0, 0.0
    for r in ROLES:
        a = anchor_books.get(r) or {}
        curve = curves.get(r) or []
        eq = float(curve[-1]["equity"]) if curve else a.get("anchor_equity")
        wc = _c.worst_case(r) or {}
        capped_share = (w[r] / kill[r]["scale"]) if kill[r]["scale"] else 0.0
        blocks = posts.get(r, {}).get("n_effective_date_blocks", 0)
        return_gate = int(blocks) >= MIN_BLOCKS_FOR_BUDGET
        if kill[r]["state"] == "FLOOR":
            scale, scale_why = FLOOR_WEIGHT, "kill:FLOOR"
        elif not return_gate:
            # THE DRAWDOWN RULE IS THE ONLY LEVER UNTIL THE RETURN EVIDENCE
            # EXISTS. See MIN_BLOCKS_FOR_BUDGET.
            scale, scale_why = kill[r]["scale"], (
                f"kill rule only: {int(blocks)} complete date block(s) < "
                f"{MIN_BLOCKS_FOR_BUDGET}, so the return signal may not move this "
                f"book's size yet (the pool weight is still graded)")
        elif ew_share > 0:
            scale = min(1.0, kill[r]["scale"] * (capped_share / ew_share))
            scale_why = (f"kill {kill[r]['scale']:.2f} x share {capped_share:.3f} / "
                         f"equal share {ew_share:.3f}, capped at 1.00 (no leverage)")
        else:
            scale, scale_why = kill[r]["scale"], "no survivors to share with"
        wc_usd = (float(wc.get("worst_case_frac") or 0.0) * scale * float(eq or 0.0))
        worst_usd += wc_usd
        equity_total += float(eq or 0.0)
        rec.per_book[r] = {
            "anchor_equity": a.get("anchor_equity"),
            "anchor_day": a.get("anchor_day"),
            "peak_equity_since": dds[r].get("peak"),
            "peak_measured_since": states[r],
            "current_equity": eq,
            "drawdown_from_peak_pct": dds[r].get("drawdown"),
            "drawdown_status": dds[r].get("status"),
            "kill_state": ("COOLDOWN_UNTIL:+%d sessions" % kill[r]["cooldown_left"]
                           if kill[r]["cooldown_left"] else kill[r]["state"]),
            "kill_state_base": kill[r]["state"],
            "cooldown_left": kill[r]["cooldown_left"],
            "kill_why": kill[r]["why"],
            "posterior_mean_daily_excess_vs_twin": posts.get(r, {}).get("mean"),
            "posterior_sd": posts.get(r, {}).get("sd"),
            "posterior_status": posts.get(r, {}).get(
                "status", "NOT SAMPLED -- floored books are excluded from the draw"),
            "prior_status": posts.get(r, {}).get("prior_status"),
            "prior_source": posts.get(r, {}).get("prior_source"),
            "n_effective_date_blocks": posts.get(r, {}).get("n_effective_date_blocks", 0),
            "date_block_sessions": block_sessions(r),
            "thompson_weight_raw": base.get(r),
            "thompson_p_best_REPORTED_NOT_USED": draw.get("p_best", {}).get(r),
            "thompson_reward": draw.get("reward"),
            "observed_window_excess_daily": (
                (PRIORS[r]["excess_window"] / PRIOR_WINDOW["sessions"])
                if PRIORS.get(r, {}).get("excess_window") is not None else None),
            "gross_budget_scale_why": scale_why,
            "allocator_weight": w[r],
            "equal_weight_twin_weight": ew_w[r],
            "random_twin_weight": rd_w[r],
            "gross_budget_scale": round(scale, 6),
            "declared_worst_case_frac": wc.get("worst_case_frac"),
            "worst_case_usd": round(wc_usd, 2),
            "binding_constraint": binding[r],
        }
        if kill[r]["fired"]:
            rec.rule_fired.append(f"{r}: {kill[r]['fired']}")
            rec.kill_log.append({
                "role": r, "drawdown_pct": dds[r].get("drawdown"),
                "action": kill[r]["state"], "date": str(day)})
        prev_w = prev.get(r, {}).get("allocator_weight")
        if prev_w is not None and abs(prev_w - w[r]) > 1e-6:
            rec.promotion_log.append({
                "role": r, "from_weight": prev_w, "to_weight": w[r],
                "reason": binding[r],
                "n_effective_at_decision": posts.get(r, {}).get(
                    "n_effective_date_blocks", 0)})

    rec.worst_case_usd_fleet = round(worst_usd, 2)
    rec.worst_case_pct_equity_fleet = (round(worst_usd / equity_total, 6)
                                       if equity_total else None)
    rec.notes = [
        f"cash_weight {cash:.4f} (allocator), {ew_cash:.4f} (EW twin), "
        f"{rd_cash:.4f} (random twin) -- capital a cut frees is NOT redistributed",
        f"survivors {len(survivors)} of {len(ROLES)}; equal share {ew_share:.4f}",
        "the LLM has no path into this file",
    ]
    cum = _cumulative(day, rec, curves, yesterday)
    rec.allocator_vs_equal_weight_twin_cum_excess = cum["vs_equal_weight"]
    rec.allocator_vs_random_twin_cum_excess = cum["vs_random"]
    out = rec.as_dict()
    out["cumulative"] = cum
    out["verdict_clock"] = _verdict_clock(cum)
    return out


def _returns(curves: dict) -> dict:
    """{role: {day: simple return}} from consecutive marks."""
    out: dict[str, dict] = {}
    for r, c in (curves or {}).items():
        d = {}
        for i in range(1, len(c)):
            a, b = float(c[i - 1]["equity"]), float(c[i]["equity"])
            if a > 0:
                d[str(c[i]["day"])] = b / a - 1.0
        out[r] = d
    return out


def _excess(rets: dict, survivors: list[str]) -> dict:
    days = sorted({d for r in survivors for d in rets.get(r, {})})
    out = {r: [] for r in survivors}
    for day in days:
        vals = {r: rets[r][day] for r in survivors if day in rets.get(r, {})}
        if len(vals) < 2:
            continue
        mean = sum(vals.values()) / len(vals)
        for r, v in vals.items():
            out[r].append(v - mean)
    return out


def _cumulative(day: str, rec: Day, curves: dict, yesterday: dict | None) -> dict:
    """Yesterday's weights x today's book returns, accumulated. Exact, not estimated."""
    prior = (yesterday or {}).get("cumulative") or {}
    base = {"alloc": float(prior.get("alloc", 0.0)),
            "ew": float(prior.get("ew", 0.0)),
            "rd": float(prior.get("rd", 0.0)),
            "sessions": int(prior.get("sessions", 0))}
    rets = _returns(curves)
    today = {r: rets.get(r, {}).get(str(day)) for r in ROLES}
    prev = ((yesterday or {}).get("per_book") or {})
    if yesterday and any(v is not None for v in today.values()):
        for key, field_ in (("alloc", "allocator_weight"),
                            ("ew", "equal_weight_twin_weight"),
                            ("rd", "random_twin_weight")):
            base[key] += sum(float(prev.get(r, {}).get(field_) or 0.0) * (today[r] or 0.0)
                             for r in ROLES)
        base["sessions"] += 1
    return {**base,
            "vs_equal_weight": base["alloc"] - base["ew"],
            "vs_random": base["alloc"] - base["rd"],
            "how": ("yesterday's weights applied to today's realised book returns; "
                    "every book marks daily whatever weight it carries, so both "
                    "twins are computed EXACTLY and no off-policy estimator is used")}


def _verdict_clock(cum: dict) -> dict:
    n = int(cum.get("sessions", 0))
    left = max(0, DECISION_SESSIONS - n)
    if left > 0:
        return {"status": "TOO EARLY", "sessions_elapsed": n,
                "sessions_to_decision": left,
                "clause": (f"the allocator is a FAILED_VARIANT if, after "
                           f"{DECISION_SESSIONS} sessions, its cumulative excess "
                           f"over the equal-weight twin is <= 0. Reading it "
                           f"earlier is reading noise ({TRIAL} section 2).")}
    ok = cum["vs_equal_weight"] > 0
    return {"status": "READ" if ok else "FAILED_VARIANT",
            "sessions_elapsed": n, "sessions_to_decision": 0,
            "cum_excess_vs_equal_weight": cum["vs_equal_weight"],
            "cum_excess_vs_random": cum["vs_random"],
            "second_test_owed": (
                "a null owes two tests: losing to equal-weight but BEATING random "
                "says the learning has signal and the prior is wrong; losing to "
                "both says the six series do not carry enough signal at this n for "
                "any allocation scheme, and the fix is time, not a better allocator")}


# --------------------------------------------------------------------------
# what the loop reads


def state_dir() -> Path:
    return STATE


def latest_record(*, day: str | None = None) -> tuple[dict | None, Path | None]:
    """The newest daily record at or before `day`, from the volume then the seed."""
    best: tuple[str, Path] | None = None
    for base in (STATE, SEED_STATE):
        if not base.is_dir():
            continue
        for p in base.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"):
            if day is not None and p.stem > str(day):
                continue
            if best is None or p.stem > best[0]:
                best = (p.stem, p)
    if best is None:
        return None, None
    try:
        return json.loads(best[1].read_text(encoding="utf-8")), best[1]
    except (OSError, ValueError):
        return None, best[1]


def budget_for(role: str, *, day: str | None = None) -> dict:
    """This book's gross budget scale, and WHERE it came from.

    Never returns a silent 1.0. Three outcomes and each is named on the row:

      * `FRESH`  -- a record for `day` exists;
      * `STALE`  -- the newest record is older; the book KEEPS that budget and
                    the row says how old it is. A stale allocator must not
                    silently re-arm a book that was cut;
      * refusal  -- there is no allocator state at all, which means the anchor
                    step has not run. That stops a deploy, which is the point.
    """
    from alpha import exits as _exits

    r = (role or "").strip().lower()
    if r not in ROLES:
        raise AllocatorUnavailable(
            f"{r!r} is not an allocated role ({list(ROLES)}). hack2 was "
            f"reassigned to lane D on 2026-09-13 and is deliberately absent. "
            f"Refusing rather than handing an unknown role a default budget.")
    day = day or _exits.session_day()
    rec, path = latest_record(day=day)
    if rec is None:
        raise AllocatorUnavailable(
            f"no allocator record under {STATE} or {SEED_STATE}. Run "
            f"`python -m scripts.allocator --anchor` and then `--run` before "
            f"deploying: a book whose budget nobody has stated must not deploy "
            f"at 100% by default.")
    row = (rec.get("per_book") or {}).get(r)
    if row is None or row.get("gross_budget_scale") is None:
        raise AllocatorUnavailable(
            f"the allocator record {path.name if path else '?'} carries no gross "
            f"budget for {r!r} (it has {sorted(rec.get('per_book') or {})})")
    fresh = rec.get("day") == str(day)
    return {
        "role": r,
        "scale": float(row["gross_budget_scale"]),
        "kill_state": row.get("kill_state"),
        "binding_constraint": row.get("binding_constraint"),
        "record_day": rec.get("day"),
        "asked_for_day": str(day),
        "freshness": "FRESH" if fresh else "STALE",
        "note": ("today's record" if fresh else
                 f"STALE: the newest allocator record is {rec.get('day')}, not "
                 f"{day}. This book KEEPS that budget and says so; a stale "
                 f"allocator never re-arms a book back to full size."),
        "contract_hash": rec.get("contract_hash"),
        "source": str(path) if path else None,
    }
