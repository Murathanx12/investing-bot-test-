# Session 28 — the three decisions are live, the brain is running, and the analyst count was the wrong number

For Murat and Fable. Plain language on purpose.
59 suites, **2,516 checks, all pass**. `fleet --check-all` green on all six accounts.
**No cap, stop, notional limit or opening-range rule was touched.**

---

## 0. Scoreboard

| | |
|---|---|
| **Result improvement on P&L** | **None realised yet.** Nothing new has traded. |
| the three decisions from your brief | **all three live**, with tests that stop them being quietly undone |
| the cost question you asked | **answered**, and the capacity answer is more useful than the cost one |
| a bug found in our own data | **the analyst count was the wrong variable** — see §3. Fixed and re-fetched: **508 names appeared in the best bucket, which had been empty.** Biggest thing here. |
| the three books | **all three fill for the first time** — 10/10, 5/5, 15/15, worst cases −6.64 / −3.00 / −2.70% |
| the daily diff | built (`tracker --diff`); needs a second day of data, and says so rather than printing an empty table |
| the logic brain | **running**, $0.004 a night at today's scale, and it produced a finding about itself in §5 |
| your fantasy transposition (T13) | **built, gated and run** — $0.30, 150 windows, 11 months. Prose beats numbers-only; everything else is a ridge, not a plateau. §5b. |
| fleet | $570,801 of $600,000 (−4.87%), unchanged — no new orders |

---

## 1. Your three decisions are live

**Past-winner exclusion: ON for hack3, OFF for hack4 and hack6.** This needed
more than flipping a constant. The exclusion used to live in the tracker's
*status*, which is one label shared by all three books — so with it there, a
past winner became `WATCH` for everybody and hack4 could never see a name hack3
had already rejected. One arm of your experiment would have been invisible.

So clause (f) moved to where the disagreement is: the book. The status now
*reports* `past_winner` and never bars on it; each book declares its own answer,
and a book that declines a name for it counts the decline. A personality that
doesn't state its answer now raises an error rather than inheriting one —
a switch worth 2.9 points a year should not be acquired by forgetting to type it.

**hack3's ranking is now the ratio** (`exp_return / |downside|`) with the
downside also capped at 30% as a hard constraint. The ratio fixes the
subtraction that was sorting on low volatility; the constraint fixes the hole a
ratio opens, which is that +0.4% against −1% outranks +8% against −25%.

**The sealed book now runs on the whole tracker.** Last night: 151 considered,
**1 claim**. Tonight's dry run: **749 considered, 10 claims.** That is the "many
names, not one" you asked for.

And the seal now checks that out loud, as your brief asked. It prints claims per
generator against the bar of ten, and when a generator is under it, it names the
*reason* — because a low count has three causes that need completely different
fixes and the number alone cannot tell them apart: a quiet market, a universe too
small to contain candidates, or a clause that is silently unreadable. The last of
those is a data gap wearing a market's clothes, and it is what happened last week
with the catalyst clause. Tonight it reads `claims ok murat_rule_v1: 10 of 749
considered (bar 10)`.

## 2. The cost question, answered — and a better question underneath it

You asked: does the thin-coverage edge survive what those names actually cost?
Here is the same rule at four cost levels, as paired excess return over the
equal-weighted market with its t-statistic:

| | 10 bps | 25 bps | 50 bps | 100 bps |
|---|---|---|---|---|
| **all candidates** (hack4/hack6 arm) | +6.00% t 2.74 | +5.24% t 2.39 | +3.97% t 1.81 | +1.43% t 0.65 |
| all candidates **minus past winners** (hack3) | +3.88% t 2.16 | +3.03% t 1.68 | +1.61% t 0.89 | −1.23% t −0.68 |
| 1–3 analysts | +5.79% t 2.31 | +5.02% t 2.00 | +3.75% t 1.49 | +1.19% t 0.47 |
| 4–10 analysts | +5.99% t 1.87 | +5.19% t 1.62 | +3.86% t 1.20 | +1.20% t 0.37 |
| 11–25 analysts | +2.35% t 0.51 | +1.11% t 0.24 | −0.95% | −5.06% |
| 26+ analysts | −8.25% | −9.74% | −12.22% | −17.19% t −2.21 |

**Neither branch of your decision rule fires cleanly, so here is the honest
version.** The thin bucket survives 25 bps comfortably (+5.02%, t 2.00). At
50 bps it is still positive (+3.75%) but no longer distinguishable from noise
(t 1.49). It does not die at 25, and it does not clearly survive 50.

And a correction to how I put it last night: 1–3 and 4–10 are **not
distinguishable from each other** (5.02 vs 5.19 at 25 bps). The real shape is
that **26+ analysts is what to avoid** — that bucket is the one carrying the
monotone decline. "Prefer thin" and "avoid crowded" sound like the same rule and
only the second one is supported.

### The capacity table, which I think matters more

Basis points answer "what does the spread take". They do not answer "could this
position have been opened at all", and a thin-coverage edge that lives in
unbuyable names is not an edge. So I split the same basket by how much the name
actually traded, at 25 bps:

| median daily dollar volume | name-months | excess vs market | t |
|---|---|---|---|
| under $100k/day | 6,776 | +2.08% | 0.51 |
| **$100k – $1m** | 19,295 | **+6.98%** | **2.22** |
| **$1m – $10m** | 29,315 | **+5.79%** | **1.93** |
| $10m – $100m | 16,536 | −1.98% | −0.69 |
| over $100m | 2,690 | −0.12% | −0.02 |

There is a **liquidity band**, and we are mostly outside it. The edge is in
names trading $100k to $10m a day; it is absent above $10m and weak in the
untradeable tail below $100k. Our books are $99k each at 8.3% a name, so a
$500k/day stock is about 1.6% of one day's volume — comfortably inside our size.

**Of tonight's 749 candidates, 219 (29%) sit in that band and 530 (71%) sit
above it**, where the eleven-year test measured no edge. Not one is below $1m a
day, because the universe snapshot is itself a liquidity screen.

That is a one-line change to the personalities and I have **not** made it — you
have already taken three switch decisions this week and this is a fourth. It is
in §7 with the exact line.

## 3. The bug: we were measuring the wrong analyst count

This is the part I would read first.

The whole thin-coverage question is bucketed on "how many analysts cover this
name". Our live tracker gets that number from Finnhub's recommendation panel.
The eleven-year test gets it from IBES `numrec`, the count of brokers with a
current recommendation. **They are not the same quantity.**

I noticed because the live tracker had **zero names with 1–3 analysts** — the
best bucket in the whole study — and its minimum was five. That is not a
universe without thin names; it holds four-analyst biotechs. It is a variable
that cannot express them.

Checked against a second live source (yfinance's `numberOfAnalystOpinions`,
which is the field that means what IBES means), on a 56-name stratified sample:

- **Finnhub's count runs a median 1.80× the other source.**
- 14 of the 56 names have fewer than 4 analysts on the honest count. **Zero** do
  on Finnhub's.
- SLDP: Finnhub **8**, yfinance **2**. KULR: Finnhub **7**, yfinance **1**.

KULR is on tonight's candidate list at +210% upside. That upside is **one
analyst's** target. We were reading it as seven.

**What it cost, exactly.** hack6 is the preservation book and its rule requires
4–10 analysts. On Finnhub's inflated scale that rule was *admitting* one- and
two-analyst names — the precise opposite of what it was written to do. A
preservation mandate was quietly selecting the least-covered names in the
universe.

**Fixed three ways.** The count now comes from yfinance, in the same call that
already fetches the price target, so it costs no extra time. Every row records
which scale its count is on. And any book rule that names a coverage bucket now
**refuses** a row on the uncalibrated scale rather than reading it — a guard
derives its input or it refuses. You can see the refusal working in tonight's
output: hack6 declined 745 of 749 names with "coverage on an uncalibrated scale".

### It landed, and it moved the whole universe

The re-fetch finished: 2,950 names re-read, nothing empty, nothing errored,
about 78 minutes. This is not a handful of corrected rows.

| analysts covering | Finnhub panel | the honest count |
|---|---|---|
| **1–3** | **0** | **508** |
| 4–10 | 657 | 1,243 |
| 11–25 | 1,765 | 1,058 |
| 26+ | 595 | 149 |

Five hundred and eight names appeared in the bucket the eleven years say is
best — a bucket the tracker previously could not express at all. **142 of
today's 749 candidates are in it.**

I also ran the price backfill, which is what lets the rule produce an expected
return and a downside at all. With both in, **all three books fill for the first
time**: hack3 10 of 10 (it was holding zero — every name that wasn't a past
winner had no downside number), hack4 5 of 5, hack6 15 of 15.

Worst cases came out exactly where they should: **−6.64% / −3.00% / −2.70%**.

### And that immediately exposed the next one

With hack6 finally able to select, look at what it selected: thirteen biotechs
out of fifteen. hack6 sorts on `confidence`, and the rule publishes the *same*
confidence for every name it doesn't claim — so all 607 eligible names scored
0.9170 and "the top 15 by confidence" was **the first 15 in dictionary order**.

It is the same shape as hack3's subtraction sorting on volatility: a ranking
that isn't ranking, invisible unless something counts the distinct values. So
now something does — the report says `only 2 distinct confidence values across
607 names — ties are deciding this book`, and if they ever all tie it says the
book is holding an arbitrary slice of its pool.

I have **not** changed which column hack6 ranks on. That is a selection
decision and it is yours; it is item 2 in §7.

## 4. The daily diff

`python -m scripts.tracker --diff` prints yesterday → today: who entered the
candidate list, who left, the biggest upside moves, and the sector counts that
changed. It writes a JSON file for the premarket digest to read.

One design point worth stating. A name that **vanished from the file** and a
name that **was downgraded** look identical in a status count and mean opposite
things — the first is a data gap, the second is a decision. So universe churn is
reported separately from grade changes, and a name is only ever counted in one
of them. Today it refuses to print at all, because there is only one day on disk
and an empty table would read as "nothing changed".

## 5. The logic brain — and the thing it taught me in the first hour

For each candidate the brain reads the row's numbers plus that company's
genuinely new dated facts from the last few sessions, and moves the rule's
probability up or down. It cannot add a name, remove one, or invent a
probability. A non-zero move **requires naming which supplied fact caused it**,
by id, checked against what was actually supplied — in code, not in the prompt.
It also may never shrink a name's downside, because that is the number position
size is built on.

**It only speaks about 16 of 749 candidates**, and that is the finding, not the
16. Our news corpus is a 152-name panel; Benzinga files 1,566 items on NVDA and
three on a small biotech. So "which names have facts" is very nearly "which
names are famous" — the same asymmetry that made the old book pick MU. **The
logic brain is a mega-cap-only instrument today**, and that is a statement about
our news coverage, not about the brain. It refuses to spend on the other 733,
because a name with no fact comes back on the rule's own number by construction.

### The cap was the answer

First run: I told the model in the prompt it could move the probability by at
most ±0.10. **Eleven of thirteen adjustments came back at exactly 0.100.** It
was returning the boundary — a sign wearing a magnitude's clothes.

I removed the number from the prompt and left the cap enforced in code. Same 16
names, same facts, same model:

| | adjustments | mean size | at the cap |
|---|---|---|---|
| cap named in the prompt | 13 of 16 | 0.075 | 11 |
| cap enforced in code only | 4 of 16 | **0.024** | **0** |

A bound the model can see is an anchor. A bound only the code applies is a
bound. This is now pinned by a test, because it would be an easy thing to
"helpfully" put back.

Cost: **$0.004** for tonight's run, against your ~$0.50/day allowance.

## 5b. T13 is built, and the rewriter is not the signal

Your fantasy transposition is running. `alpha/transpose.py` + `scripts/era_replay.py`.

**What it does.** It takes one company-month of real news, rewrites it into a
made-up world — a made-up year, a made-up industry, made-up companies — and asks
a *different* model family to forecast the next 21 sessions from the rewrite. If
it can still pick winners, it is reading the situation rather than remembering
the company. Here is a real one, Agilent's August guidance update:

> `[2051-08-27]` Fenwick Works (orbital cooling) Narrows FY2051 Adj EPS Guidance
> from $5.54-$5.61 to $5.56-$5.59 vs $5.58 Est; Raises FY2051 Sales Guidance from
> $6.730B-$6.810B to $6.910B-$6.930B vs $6.787B Est

Every one of the twelve numbers survived; the company, the industry and the year
did not. That is the whole idea in one line.

**The gate passed, and it is the result that matters most so far.** Before
paying for the grid, the same windows are rewritten twice by two *different*
model families and we check whether the forecast moves more between two rewrites
of one window than it does between different windows. If it did, we would be
measuring the rewriter and every number after it would be worthless.

| | |
|---|---|
| p_up moved between two rewrites of the same window | **0.0045** |
| p_up moved across different windows | **0.0372** |
| ratio | **0.12** — well under the 1.0 that would stop the run |

So the model is responding to the situation, not to how it was phrased.

**Four arms, and the one that could end the exercise cheaply.** Alongside `real`
(names and year intact), `real_anon` and `fantasy`, there is a `numbers_only`
arm: the magnitudes and event types with every sentence deleted. If that scores
like the fantasy arm, the prose was carrying nothing and we have our answer
without a council. `real − fantasy` is how much was memory. Two nulls run
beside them: the same picks against somebody else's outcome, and the
equal-weighted era basket.

**"I don't know" is gone**, as you asked. The decider returns p_up, expected
return, downside and confidence for every name, every time; uncertainty is p_up
near 0.5 at low confidence. On the first 29 windows it used the range: p_up
0.35 to 0.62, confidence 0.10 to 0.70. Then the *choosing* is code, and wealth
and calibration are graded separately, because a model can rank well and be
badly calibrated or the reverse, and one number would hide whichever is smaller.

**Two bugs in my own checker, both found by running it.** The rule that a
rewrite must preserve every number was throwing away good rewrites: it read the
day-numbers out of my own date headers, so `[2025-10-27] → [2051-11-17]` looked
like three numbers deleted and three invented. Worse, the drop was concentrated
in the windows with the most dated items — the ones carrying the most
information. The fix then broke differently: "Mar" matched inside "Margin", so
"Margin 31%" was stripped as a date and a real number vanished. Both are pinned
by tests now.

### It ran. Here is what it says, and what it does not.

1,001 windows over 152 names and 11 monthly rebalances (2025-06 → 2026-07),
graded on the **150 windows every arm has** — the arms lose different windows
when a rewrite fails, and comparing baskets of different companies would be a
difference of portfolios before it was anything about memory. Total cost: **$0.30.**

At a top-5 basket under the balanced ranking:

| arm | terminal wealth | t | vs its own shuffled null |
|---|---|---|---|
| the market basket (every name, equal weight) | 1.149 | 0.97 | — |
| **real** (names and year intact) | 1.670 | 2.33 | beats it |
| **real_anon** | 1.756 | 2.07 | beats it |
| **fantasy** | 1.567 | 2.12 | beats it |
| **numbers_only** (prose deleted) | 0.924 | −0.16 | **loses to it** |

Read alone, that is a result: the model beats the market on a story it has never
seen, and fails when you take the story away. **I do not think you should read
it alone.** Here is the same thing at four basket sizes:

| balanced | k=3 | k=5 | k=10 | k=25 |
|---|---|---|---|---|
| real | 1.667 | 1.670 | **1.076** | 1.237 |
| real_anon | 2.329 | 1.756 | **1.198** | 1.237 |
| fantasy | 1.371 | 1.567 | **1.097** | 1.237 |
| numbers_only | 1.087 | 0.924 | 1.027 | 1.237 |

Everything collapses at ten names. And under the *other* ranking rule — the
aggressive one, `p_up × expected return` — the arm that should be **worst**,
the one that sees no prose at all, is the **best** at k=3 (1.925, t 2.25).
That is noise winning, and it is what a narrow ridge looks like from the side.

I held the upside cap in the eleven-year study to a **plateau** — it had to work
from 1.5× to 10× or I would not have believed it. The same standard has to apply
here, or the standard was about the conclusion rather than about evidence. So:

- **What survives every basket size:** prose beats numbers-only under the
  balanced ranking. That contrast is stable and it is the one thing I would
  carry forward.
- **What does not survive:** the size of the outperformance, and the
  `real ≈ fantasy` reading. The gap between them is inside the noise of the
  sweep, so I cannot yet tell you whether the model is remembering or reading.
- **And the number that bounds all of it:** this is **11 monthly observations**,
  not 150. Names inside one month share that month's market. Eleven is not
  enough for any of this, and the grade prints that line every time.

**One thing is clean, though, and it is the split the harness was built to
find.** Calibration is negative in all four arms (Brier skill −0.001 to −0.011):
worse than always predicting the base rate. The model **orders better than it
prices**. If we ever use it, use the ranking and throw the probability away.

## 6. A near-miss worth recording

Two commands rewrite the tracker day file — the price backfill and the new
coverage re-fetch. Each reads the whole file, changes a column, writes it back.
Run together, the second one's copy was read before the first one wrote, so one
of them silently reverts the other. Nothing errors; a column just comes back
empty and reads as "the source had no data".

The existing guard compared **line counts**, and neither command changes the
line count — so it would have passed straight through the collision it was
written to stop. I started both by accident tonight, caught it before either
wrote, and replaced the guard with a real lock that names who holds it and for
how long.

### And the two hours I lost to a process that was never running

A second one, in the same family, worth writing down because the checks I made
were the wrong checks. I launched the 3,000-name coverage repair in the
background and then, for two hours, confirmed it was fine twice:

- the process table showed it running — **it did**, as a shell that had already failed
- its log was empty — **which I read as "it writes at the end"**

Both readings were wrong, and they were wrong for the *same* reason, which is
why they agreed with each other. The job had exited immediately with code 127.
Its own exit line said so, one line above the empty log I was looking at.

The measurement that settled it in thirty seconds was CPU time: six seconds
after two hours, for a job that should burn minutes parsing three thousand
responses. Now the job prints `50/2950 0.64/s ~73 min left` every twenty-five
names, flushed, so "started" and "not started" can never look alike again.

The repair is genuinely running now and finishes tonight.

## 7. What is yours to decide

1. **The liquidity band.** Add `min_dollar_volume` / `max_dollar_volume` to the
   personalities so the books buy in the $100k–$10m range where the eleven years
   measured an edge, instead of the $10m+ range where they measured none. It
   would cut tonight's pool from 749 to 219. One line per book, and it is a
   selection change, not a risk cap.
2. **hack6's coverage rule, once the re-fetch lands.** On the honest scale
   "4–10 analysts" means something different from what it has been doing.
   Preservation probably wants *more* coverage, not less — the 26+ bucket is
   the one that loses money, but 11–25 is roughly flat and much easier to exit.
3. **What hack6 ranks on.** It sorts on `confidence`, which the rule publishes
   as a constant for every non-claiming name — so its fifteen holdings are an
   arbitrary slice, currently thirteen biotechs. Any column with real variation
   would do (upside, the risk ratio, coverage); the point is that the current
   one has none. One line, and the diagnostic now shouts about it either way.
4. Whether to **push**. I have not. Everything is committed, tests green
   (59 suites / 2,517 checks), fleet green at $570,800.88. Pushing deploys.

## 8. Monday

Tonight's dry run has already been through all of it once on the 30 Aug data,
so the only step that has not been exercised end to end is `--diff`, which needs
the second day to exist.

```
python -m scripts.tracker --refresh              # a fresh day; carries the honest analyst count
python -m scripts.tracker --backfill-prices      # adds realised_vol_20d; the book needs it
python -m scripts.tracker --diff                 # who entered, who left  (works from tomorrow)
python -m scripts.tracker --show
python -m scripts.tracker --sectors
python -m scripts.prediction_book --seal --universe tracker
python -m scripts.logic_brain --run              # ~$0.01
python -m scripts.prediction_book --verify
python -m scripts.prediction_book --publish
python -m scripts.tracker --portfolios           # three books, worst case each
git add docs/seed && git commit && git push
```

`--backfill-prices` must come before the seal. Without `realised_vol_20d` the
rule cannot produce `exp_return` or `downside_5pct` at all — tonight's dry-run
book had them on **zero** of 749 rows, which is why hack3 selected nothing.
That is not a new bug; it is the reason that step is first in the chain.

## 9. Worst case, derived from the code

```
hack3  basket      10 x 8.3% =  83% of a 100% cap  x 8% stop  =  -6.64%
hack4  maximum      5 x 10%  =  50% of a 150% cap  x 6% stop  =  -3.00%
hack6  aggressive  15 x 6%   =  90% of a 100% cap  x 3% stop  =  -2.70%
```

All inside −9%, and unchanged from last session because nothing in the risk
path was touched.
