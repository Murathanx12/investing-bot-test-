# NON_PRINT_BOUNCE_v1 — refuted. The bounce is beta plus convexity, and 35 rows were corporate actions

**2026-08-26, day session 12.** `python -m scripts.bounce_battery` ·
`state/bounce_battery.json` · 46,361 DOWN non-print events over 2,434 names,
2024-02 to 2026-08.

## The candidate

Session 11's placebo found that a ≥5% one-day loser with no earnings print
within ±5 sessions **bounces** (+0.37% raw/3d, +2.14% raw/21d), where a print
loser does not (diff t 5.0). The print stops the bounce. That mechanism result
stands. The question was whether the bounce is a trade.

**It is not.** It is the market plus a variance harvest, and a small part of it
was a data artefact.

## STEP 0 — the instrument, before the result

Two contaminations in the night bar cache, both inflating the bounce, both found
by looking at the tail before believing the mean:

1. **Alpaca's `adjustment=all` does not adjust a Chapter 11 share exchange.**
   WOLF closes at 1.21 on 2025-09-26 and opens at 18.00 the next session. That
   is not a +1,388% return, it is new shares after reorganisation. AKTS shows
   +6.35 in 3-day log terms (+57,293% simple) across a delisting.
2. **A gap in a symbol's bar list was treated as consecutive sessions.** The
   placebo walks each symbol's own bars, so `days[i0+1:i0+1+h]` takes the next
   *h available* bars regardless of calendar distance. AKTS has no bar at all
   after 2024-12-17; its "3-day" window jumps the delisting and lands on a
   post-reorganisation price.

**35 rows of 46,361 — 0.075% — carried 81.4% of the summed simple return.**

| | contaminated | guarded |
|---|---|---|
| long, 3d, simple | **+4.11%** | **+0.79%** |
| long, 3d, net of 30bp | +3.81% | +0.49% |
| micro cell as a short, 3d | **−12.69%** | **−0.52%** |

An entire "shorting microcaps is crushed by convexity" story evaporated with 35
rows. It was a real effect in the contaminated data and an artefact in the
clean data, and had the battery reported the first number it would have been a
confident, mechanistic, completely wrong finding.

This is the parent project's own lesson recurring in a new place: *the panel
marked share counts at raw prices, so every split was booked as a return.*
**Distrust the number before you distrust the result.**

## STEP 1–2 — the bounce is the tape

Signed so a positive number reads as a bounce; `t2w` is the two-way
issuer × month clustered t.

| horizon | raw | t2w | **excess over β·QQQ** | t2w |
|---|---|---|---|---|
| 1 | +0.12% | 1.52 | −0.04% | −0.40 |
| 3 | +0.31% | 1.60 | **−0.07%** | −0.30 |
| 5 | +0.52% | 1.83 | −0.09% | −0.42 |
| 21 | +2.08% | 1.41 | **−0.36%** | −0.23 |

The raw bounce is real and it is **entirely beta**. Net of the market the loser
does not bounce at all — at 21 days it *underperforms* by 0.36%. This is the
wide-PEAD trap running in reverse: there the benchmark-relative number looked
like an edge and the raw number was nothing; here the raw number looks like an
edge and the benchmark-relative number is nothing. Same lesson, opposite sign.

## STEP 3 — where the raw number actually comes from

| horizon | log mean | simple mean | **convexity** | net of 30bp |
|---|---|---|---|---|
| 3 | +0.31% | +0.79% | **+0.48%** | +0.49% |
| 21 | +2.08% | +8.91% | **+6.83%** | +8.61% |

An equal-weighted book does earn the simple mean, so +0.49%/3d net is arithmetic
fact. But **more than half of it is convexity** — `E[e^r] > e^{E[r]}`, a
variance harvest available from *any* equal-weighted basket of high-variance
names. It is not a bounce, it has nothing to do with the absence of a print, and
it comes with the variance that produced it.

The log excess over β·QQQ is −0.07%. So: the strategy delivers beta plus a
volatility harvest, at far more idiosyncratic risk than buying the index.

## STEP 4 — per-quarter stability, the step PEAD failed

Excess positive in **6 of 11 quarters at 3d, 3 of 11 at 21d**. Quarterly excess
ranges −4.59% to +4.94% at 21 days. The pooled mean is a coin flip with a sign.

## STEP 5 — liquidity buckets

| bucket | n | names | exc 3d | t2w | exc 21d | t2w |
|---|---|---|---|---|---|---|
| micro | 12,229 | 464 | −0.38% | −0.92 | −2.23% | −0.17 |
| small | 15,734 | 800 | +0.02% | 0.33 | +0.20% | 0.32 |
| mid | 12,600 | 815 | −0.09% | −0.26 | +0.10% | 0.32 |
| large | 4,814 | 312 | +0.38% | 0.61 | **+0.86%** | **1.99** |

**One cell of eight reaches t2w ≈ 2.0** — large caps at 21 days. That is exactly
what a multiple-comparison budget exists to price: eight cells tested, best t
2.0, and the expected maximum |t| from eight independent draws is ≈ 1.9. It is
recorded as a candidate, **not** as a finding, and it is the first entry for the
`RESEARCH_ALPHA_BUDGET`.

## Verdict

**`NON_PRINT_BOUNCE_v1`: FAILED_VARIANT.** Not `MECHANISM_REJECTED` — the
print-suppresses-bounce asymmetry is intact and remains a real information
result for Psychohistory. What is refuted is the bounce as a tradeable long:
it is beta plus convexity, unstable across quarters, and absent in excess terms.

No execution is built. Total cost: **$0.00** — every number came from bars
already on disk.

## What must be fixed upstream

1. **`scripts/night_bars.py` needs a corporate-action screen.** `adjustment=all`
   is not sufficient for reorganisations and some microcap reverse splits. Until
   it exists, every bar-cache result is subject to the same 0.075% tail.
2. **`scripts/night_attention_placebo.py` must not treat a bar gap as
   consecutive sessions.** The guard now lives in `bounce_battery`; it belongs
   in the row writer so every consumer inherits it.
3. **Session 11's other bar-cache results deserve a re-read against this
   guard** — the pair regrade and the timezone lead were computed from the same
   cache. Their headline numbers were near zero, so contamination is unlikely to
   have created them, but "unlikely" is not "checked".

## The rule worth keeping

> **A tail check is not optional diligence, it is step zero.** Print the top
> twenty contributors to any mean before believing the mean. Here twenty rows
> out of 46,361 were 81% of it.
