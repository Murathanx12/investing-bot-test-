# The brain scoreboard cannot rank brains: 267,802 rows are two days

**2026-08-26, session 13, unattended.** Read-only analysis of
`state/counterfactual.jsonl` (285 MB, 267,802 rows) and `state/decisions.jsonl`.

## What the scoreboard appears to say

Taking the final mark per decision and grouping by the originating brain:

| brain | action | n | mean RoR | median | win% |
|---|---|---|---|---|---|
| vol_gap | shadow | 27 | **+13.8%** | +0.1% | 56% |
| narrative_dispersion | shadow | 50 | +2.1% | −9.2% | 38% |
| options_attention | shadow | 33 | +0.9% | −9.0% | 27% |
| vol_gap | refused | 1685 | −5.8% | +0.0% | 25% |
| narrative_dispersion | alternative | 184 | −11.8% | −15.4% | 28% |

Read naively this says two things: `vol_gap` is the best brain, and **every road
not taken lost money**, so the engine's refusals were correct.

The second may well be true. The first is an artefact, and so is most of the
precision in both.

## Three defects, in increasing order of severity

### 1. The mean is three positions

`vol_gap / shadow`: the **top 3 of 27** carry **113%** of the summed
return-on-risk. Trimmed of the top and bottom three, the mean falls +13.8% →
+8.6% and the median is **+0.1%**.

It is worse elsewhere. `narrative_dispersion / shadow` top 3 carry **478%** of
the sum, and trimming flips the mean **+2.1% → −3.6%**.
`options_attention / shadow` top 3 carry **1537%**, trimming gives **−7.7%**.

**Two of the three positive brains are negative once three observations are
removed.**

### 2. The observations are not independent

The top contributors are the same names on the same afternoon:

```
META 2026-08-25 15:27, 15:40, 16:04
AVGO 2026-08-25 15:40, 16:03
AAPL 2026-08-25 15:27, 15:41
```

Decision ids are minute-derived — deliberately, so a restart inside one minute
collides at the broker. The side effect is that one view of META, expressed by
one brain across three passes of one afternoon, enters the scoreboard as **three
independent decisions**.

Collapsing to one observation per (brain, action, symbol, **date**), `vol_gap /
shadow` goes from n=27 to **12 blocks**, and every raw n above shrinks by half
or more. `n_effective` counts date blocks — the canon already says so.

### 3. The whole ledger is two days

This is the one that settles it.

```
counterfactual.jsonl   2026-08-25T13:04Z .. 2026-08-26T15:44Z
decisions.jsonl        rows only on 2026-08-25 and 2026-08-26
distinct calendar days in the entire counterfactual ledger:  2
```

Both files' first row chains from `_prev: aegis-alpha-terminal/v1` — **genesis**.
They were not truncated; they begin there. The forward record in this repository
is **two sessions old**.

So `vol_gap` did not outperform. **META went up on 25 August**, and three brains
had shadow exposure to it.

## What follows

- **No brain can be ranked against another yet, and no brain is a "champion" on
  evidence.** The dev/exp1 champion split is a design choice, not a result — and
  it should be described that way in anything a judge reads.
- **"Every refusal was correct" is also two days.** It is the more robust of the
  two readings — it rests on 1,435–1,685 raw refusals rather than on 27 shadows,
  and it survives collapsing to date blocks (−4.2% to −4.6%) — but two days is
  two days.
- **The scoreboard needs a date-block collapse before it is read again.**
  Reporting raw n over minute-derived ids will keep manufacturing significance
  from repeated marks of one position.

## What was NOT concluded

That the brains are bad. Two sessions cannot show that either. The finding is
about the **instrument**: a 285 MB ledger feels like a lot of evidence, and file
size is not sample size.

## The rule worth keeping

> **Count the days before reading the columns.** 267,802 rows, 5,731 decisions,
> 231,000 usable marks — and two calendar days. Every "per brain" number this
> project has quoted from the counterfactual ledger is a statement about 25 and
> 26 August 2026.
