# TRIAL-DRAFT-ALLOCATOR-v0 — the fleet allocator as a strategy, graded like one

**STATUS: UNSIGNED DRAFT.** Written 2026-09-13, before the first weight. It is
not in any experiment registry and has not incremented a cumulative trial
count: registration is the attended step, and a draft that registered itself
would make the attended step decorative.

**Licence:** `PRODUCT_EXPERIMENT`. It moves PAPER gross budgets on six paper
accounts. It accrues no real capital and places no orders of its own.

**Code:** `alpha/allocator.py` (pure), `scripts/allocator.py` (the daily run).
**Contract hash at registration:** `alpha.allocator.contract_sha256()`, stamped
into every daily receipt and into `state/allocator/anchor.json`. Every frozen
number below is in `contract()`; changing one changes the hash, which is how a
reader tells "the rule fired" from "the rule was edited".

**Spec:** `../aegis-finance/docs/research_notes/2026-09-13/spec_allocator_kill_promote.md`.
Where this draft departs from that spec, section 6 says so and why.

---

## 1. The hypothesis

> A Thompson-sampling allocator over the five allocated paper books, with a
> mechanical drawdown kill floor (−5% halves the book's gross, −7.5% floors it
> at 2% with a 20-session cooldown) and posteriors seeded from each book's own
> historical prior, produces higher risk-adjusted terminal wealth over 60
> trading sessions than (a) an equal-weight twin over the same surviving books
> and (b) a constrained random-Dirichlet twin, at the same `n_effective` and
> under the same kill floor and concentration ceiling.

`hack2` is not in the trial: Murat reassigned it to lane D on 2026-09-13 12:05
HKT and its loop is down. Five books, named in `allocator.ROLES`.

## 2. The arithmetic that shapes the whole design

Book-level daily return sd on this fleet is on the order of 1.5%
(`alpha/fleet.py`'s own caveat measured the theme basket at 60-170% annualised).
A two-sample t on `n` daily marks needs a mean daily excess of
`t × 1.5% / sqrt(n)`:

| n (sessions) | sd of the mean | daily excess for t = 2 | annualised |
|---|---|---|---|
| 5 | 0.67% | 1.34%/day | ~630%/yr |
| **10** | **0.474%** | **0.95%/day** | **~340%/yr** |
| 20 | 0.335% | 0.67%/day | ~230%/yr |
| 60 | 0.194% | 0.39%/day | ~130%/yr |
| 252 | 0.095% | 0.19%/day | ~55%/yr |

**A return-based bandit cannot honestly promote or kill on two to six weeks of
paper P&L.** That is not a reason to skip the RL; it is the reason the RL leans
on a signal that resolves fast (drawdown) while the return signal accumulates —
which is also, independently, what every reported pod-shop rule does.

## 3. The frozen rules

| rule | value | why this number |
|---|---|---|
| halve | drawdown ≤ **−5%** from the book's own peak | Millennium, as reported by Rubinstein's *Peak Pod* (Sept 2023) and cited by hedgefundinterview.com and Young & Calculated. Widely reported, **not** officially published. |
| floor | drawdown ≤ **−7.5%** → gross **2%**, cooldown **20 sessions** | same source for the −7.5% wind-down. 2%, never 0: a killed book keeps marking, which is what makes both twins exact rather than estimated. |
| ceiling | **35%** of the pool | `alpha/guards.py` and `alpha/book_limits` already treat >30-40% concentration as the thing that needs a name. Not fitted to any outcome here. |
| freed capital | **not redistributed** — it becomes `cash_weight` | **NOT FOUND:** a published numeric ratchet-up schedule for any platform. Every source that describes cuts is silent on the mirror image, and this contract does not invent one. |
| observation sd | **1.5%/day**, declared | estimating it from ten marks is the same small-sample problem one level down. |
| peak window | restarts at every state change | otherwise a halved book can never recover however well it does. |
| budget gate | a book's gross moves on RETURN only at **≥ 3 complete date blocks** | section 6, departure 2. |

**A date block is the book's own declared `min_normal_hold_sessions`**
(`contract.HORIZON_REMAP`): hack1 5, hack3 21, hack4 42, hack5 2, hack6 21.
`n_effective` counts complete blocks, never daily marks — canon §58, and the
reason is that five daily P&L numbers from one position held for a week are one
observation, not five.

## 4. The primary metric and the decision rule, stated before the first weight

**Primary:** cumulative excess of the allocator's realised weighted return over
**Twin 1 (equal weight)**, over **60 trading sessions from the anchor**, in
dollars and in percent of starting fleet equity.

**Secondary:** the same against **Twin 2 (random Dirichlet, same ceiling and
same kill scales)**.

**Decision rule.** The allocator is a **`FAILED_VARIANT`** if, after 60 trading
sessions, its cumulative excess over Twin 1 is **≤ 0**, or is positive with a
paired **t < 2.0** on the daily-excess series (block-corrected at the fleet's
own cadence). **The one number that ends it: cumulative excess over the
equal-weight twin ≤ $0.** A learned weighting that cannot beat naive 1/N over
its own surviving set after two months is paying more in estimation error than
the learning is worth (DeMiguel, Garlappi & Uppal, *RFS* 2009), and the fleet
should run equal-weighted under the kill floor alone.

**Earliest decision date:** 60 trading sessions after the anchor. Not before —
section 2 says anything earlier is reading noise.

**A null owes two tests.** If Twin 1 says FAILED_VARIANT, the second test is
against Twin 2: losing to equal weight but **beating** random says the learning
has signal and the prior shape is wrong; losing to **both** says the five series
do not carry enough signal at this `n` for any allocation scheme, and the fix is
time, not a better allocator.

**What does NOT wait for that verdict:** the kill floor. It is not part of what
is being tested and it binds from day one.

## 5. The twins, built with the allocator and not after it

- **Twin 1 — equal weight** over the books that are not floored, carrying the
  same kill scales and the same ceiling.
- **Twin 2 — random Dirichlet(1)**, seeded from the day, under the same
  constraints — so the comparison isolates the LEARNING, not the constraint set.

Both are computed **exactly**, not estimated: every book marks daily whatever
weight it carries, so "what would equal weight have earned" is a re-weighting of
five fully observed series. No importance-weighted or doubly-robust estimator is
needed, and that property is the reason a killed book is floored at 2% instead
of zeroed. It would be destroyed permanently the first time a book stopped
marking.

## 6. Departures from the spec, and why

1. **The pool weight and the gross budget are two different objects.** The spec
   speaks of moving capital between books. Six Alpaca accounts are six separate
   venues and **capital cannot move between them**. So `allocator_weight` is a
   paper pool share that exists to be graded against the twins, and
   `gross_budget_scale` — `min(1.0, kill_scale × share / equal share)` — is what
   a loop reads. It can only REDUCE. Promotion restores a book toward its own
   100% and never beyond, because leverage is not on the table.

2. **A book's gross does not move on RETURN until it has 3 complete date
   blocks.** The spec's asymmetry is stated as fast-cut / slow-promote, but the
   evidence argument is about DIRECTION-FREE reliability: a cut on return at
   n = 0 is exactly as unreliable as a promotion on return at n = 0. Measured on
   this fleet's own day-one posteriors, an ungated version cut hack3 — the only
   book with 419 blocks of evidence behind it — to **12% of its size** because
   three other books had ten sessions of luck. The pool weights are still
   computed, printed and graded from session one; they simply do not touch a
   live book's size until the return evidence exists.

3. **The Thompson reward is Sharpe-shaped, not P(best).** P(best) rewards
   VARIANCE. On day one it gave the book with a measured t of 3.12 a 2.4% share
   and the four books with zero complete blocks 24% each. The sampled quantity
   is `max(sample, 0) / posterior_sd`, which is the risk-adjusted reward the
   spec's own literature note prefers (IEEE 9894518) and which reduces to a
   book's own t-statistic where the posterior is its replay prior. `p_best` is
   computed and printed anyway, because it is the quantity a later reader will
   ask for — and the receipt says plainly that it decides nothing.

4. **A prior resting on fewer than one complete date block is centred at ZERO,
   not at its observed window return.** The spec asked for the live books to be
   seeded with their own realised curves. Computed, those centres are +0.24% to
   +0.45% **per day** from ten sessions — 60% to 110% annualised excess, which
   is the regime section 2 says is unreadable. The observed number is recorded
   in `PRIORS` and printed on every receipt as
   `observed_window_excess_daily`; it is not used as a centre. hack1 and hack5,
   whose declared minimum holds are 5 and 2 sessions, DO clear one block over
   that window and keep their measured centres with the sd their block count
   earns.

5. **hack3's prior is Book F's replay, not hack3's live curve.** Its engine
   became Book F on 2026-09-13 (chunk 13b); the live curve belongs to the
   tracker engine it no longer runs. Prior: +0.4328%/month net vs its
   turnover-matched twin, t 3.1178, 419 blocks, $10M floor.

6. **The regime-conditioned posterior (spec §2c) is NOT built.** Four regime
   cells quarter an already-thin sample, and section 2's table is already the
   binding constraint at one cell. It is a v1 candidate and its absence is
   declared rather than silently skipped.

## 7. What this can and cannot be used for

It may move paper gross budgets. It may not be described as evidence that
allocation adds value until section 4's clock has run and the paired test has
been read. **The LLM has no path into any of it** — no model call, no text, and
no import that makes one, in `alpha/allocator.py` or `scripts/allocator.py`.
Pinned by `tests_smoke_allocator.py`.

## 8. Worst case, printed before the first weight

Anchor 2026-09-11, equities read live 2026-09-13 12:10 HKT, every budget at
1.00 because no book has a complete date block yet:

| role | equity | scale | stop | worst case |
|---|---|---|---|---|
| hack1 | $93,863 | 1.00 | 10% | −$9,386 |
| hack3 | $83,342 | 1.00 | 12% | −$10,001 |
| hack4 | $92,941 | 1.00 | 12% | −$11,153 |
| hack5 | $95,095 | 1.00 | 9% (premium bound 15% → 6 × 3% × 50%) | −$8,559 |
| hack6 | $87,591 | 1.00 | 10% | −$8,759 |
| **fleet** | **$452,832** | | | **−$47,858 = −10.57%** |

That is the fleet's worst case WITHOUT the allocator as well: on day one the
allocator changes no budget. Every number is recomputed by
`scripts/allocator.py --run`, which prints it before it writes, from
`alpha.contract.worst_case` — never from this table.
