# Competition account admission — a proposal, with every number traced

**2026-08-26, session 13, unattended. STATUS: PROPOSAL. Nothing here is
enforced.** Turning any of it on changes what the account trades and is an
attended decision. What follows is the argument and the evidence, so that
decision takes minutes rather than a session.

Pre-flight tool: `python -m scripts.preflight [--require-clean]`.

## The problem, stated as a fact rather than a worry

The rehearsal book reached **72.9% of equity in true max loss** — and today
still sits at **55.0%** — while every individual structure was defined-risk and
**every admission check passed.** Nothing was violated. The checks never asked
the question.

Alongside it, measured today:

| observation | value | where |
|---|---|---|
| refusals that are "we already own it" | **32 of 48** | `run_pass` decomposition |
| effective N by RISK, dev | **1.51** | `scripts.concentration` |
| effective N by RISK, exp1 | **1.27** | `scripts.concentration` |
| largest single thesis, dev | **NVDA at 52.4% of book max loss** | `scripts.preflight` |
| Situational Awareness at liquidation | **1.43** | `docs/FINDING_2026-08-26_EFFECTIVE_N_BY_RISK.md` |

**exp1 is more concentrated than the $20bn fund that was forced to liquidate in
July.** Not by assets — by the only measure that predicts a bad week.

## Proposed controls, each with its derivation

### `MAX_BOOK_STRESS` — true max loss ≤ **35%** of equity

*Derivation.* Situational Awareness's unlevered Q2 book lost **23.3%** over 41
sessions with a 42.2% peak drawdown, and **survived**. A cap at 35% means a full
simultaneous realisation of every structure leaves the account solvent and
recoverable, at roughly the worst outcome that portfolio actually produced
without leverage. The rehearsal book's 72.9% would have needed a 3.4x recovery.

*Measured against the honest number.* `true max loss`, never the premium-paid
view — today those read 55.0% and 34.1% on the same book, and only one of them
is what the account can lose.

### `MAX_SINGLE_THESIS` — ≤ **20%** of book max loss on one underlying

*Derivation.* dev currently carries **52.4% on NVDA**, on the night NVDA
reports. There is no version of "diversified" that survives one name being more
than half the downside. 20% means five roughly equal theses would be the floor
of compliance, which is already generous given the next control.

### `MIN_EFFECTIVE_N_RISK` — ≥ **2.0**

*Derivation.* This is the control the others are proxies for. Every observed
failure or near-failure state sits below 2.0: Situational Awareness 1.43 at
forced liquidation, exp1 1.27, dev 1.51. **2.0 is the smallest round value
strictly above every failure state we have measured.** It is not a
theoretically motivated number and should not be described as one — it is a
floor drawn above the observed wreckage, and it should move once we have
examples of books that survived a bad week.

*Why weight-based caps are not enough.* dev's weight-based effective N is 2.77
while its risk-based N is 1.51. A position-count or capital-weight rule passes a
book that behaves like one bet; **only the correlation-adjusted count catches
it.**

### `MIN_FREE_CAPITAL` — ≥ **25%** of equity

*Derivation.* Two uses. It is the capacity to act on an opportunity that appears
after the book is built — the saturation finding says 32 of 48 refusals were
"already held", so the account is routinely unable to take a new idea. And it is
the buffer that makes a forced exit a choice rather than a liquidation, which is
the mechanism, not the thesis, that destroyed the reference portfolio.

### `MAX_EVENT_CLUSTER` — keep the existing `EVENT_NODE_CAP`

Already enforced in `runner.py` and already refusing. No change proposed; it is
listed so the set is complete.

### `MAX_DAILY_THETA` — **UNSET, and deliberately so**

I can compute the book's theta but I have **no evidence for a threshold**. A
number invented tonight would look exactly like the four above and carry none of
their derivation. Left unset with the reason recorded, rather than filled in to
make the table look finished.

> **A threshold without a derivation is a guess wearing a policy's clothes.**

## What the pre-flight prints before the first order

```
equity · cash · buying power · positions · open orders
TRUE max loss (and the premium-paid view beside it, so the gap is visible)
book unbounded · structures · residual legs
effective N by RISK + verdict + largest single thesis
daily loss latch state
loop liveness
```

`--require-clean` exits non-zero if the account holds any position or any
**open order** — a resting order is exposure that no position line shows, and it
was an in-flight order that produced the double-entry defect on 25 Aug.

## The one recommendation I would make regardless of the thresholds

**The competition account starts empty.** Not because the rehearsal book is bad
— it is defined-risk and bounded — but because a book assembled under the old
admission rules has not proved itself under the new ones, and there is no way to
tell from the outside which of its 9 structures would have been admitted.

## What this is NOT

- **Not enforced.** No refusal in this repo consults any of it.
- **Not a claim that these numbers are right.** Three of five are drawn above
  observed failures rather than derived from theory, and they should tighten or
  loosen as evidence arrives.
- **Not a substitute for the licences.** This is `PRODUCT_EXPERIMENT` risk
  hygiene, not a `CAPITAL_CANDIDATE` promotion.

## Open question I could not answer tonight

Whether `MIN_EFFECTIVE_N_RISK` should be measured **at admission** (would this
order push the book below the floor?) or **continuously** (has correlation
drifted the book below it?). The second is strictly better and strictly harder:
correlations move, so a book admitted at 2.1 can be at 1.6 a month later with no
trade having occurred. The reference portfolio's effective N fell from 12.5 to
5.7 in one quarter, **and roughly half of that was the hedge coming off rather
than new buying** — a change no per-order check would have seen.
