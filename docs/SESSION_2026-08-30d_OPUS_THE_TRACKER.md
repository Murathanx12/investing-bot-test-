# Session 27 — the tracker is built, and eleven years of data changed two of its rules

For Murat and Fable. Plain language on purpose.
`62d9bb8` in `aegis-alpha-terminal`, `09ba798` in `aegis-finance`. **Committed, not pushed.**
57 suites, **2,466 checks, all pass**. `fleet --check-all` green on all six accounts.

---

## 0. Scoreboard

| | |
|---|---|
| **Result improvement on P&L** | **None realised yet.** Nothing new has traded. What changed is that the screen now has eleven years of evidence behind it instead of eleven date blocks. |
| the watchlist | built and running — `alpha/tracker.py` + `scripts/tracker.py` |
| tonight's refresh | **in progress**, ~560 of 3,059 names at the time of writing, ~6.7s per name → finishes overnight. Resumable; nothing is lost if it stops. |
| out-of-sample test | **434,295 name-months, 2013–2024, whole US market** |
| the screen, capped | **+3.88%/yr over the market, paired t 2.16**, wealth 4.107 vs 2.863 |
| the screen, uncapped | −5.48%/yr, paired t −2.10 — i.e. the cap is the whole result |
| your thin-coverage idea | **CONFIRMED**, monotone: 1–3 analysts 12.83% CAGR → 26+ analysts −8.84% |
| your "don't buy the past winner" idea | **REFUTED**: it costs ~2.9pp/yr. Left switched ON — it is your call, not mine. |
| fleet | $570,801 of $600,000 (−4.87%), unchanged — no new orders were placed |

---

## 1. You were right about the cause, and the fix was bigger than the rule

MU got picked because the book could only look at names that had **news**. That
sounds neutral and is not: Benzinga files 1,566 stories on NVDA and three or
four on AARD. Requiring news is a mega-cap filter wearing a data requirement's
clothes, and it is how a 151-name panel of mostly mega-caps produced one
mega-cap.

So the tracker does not need news at all. Every input your rule actually reads
— the analyst target, the consensus rating, the drawdown, the next dated
catalyst — is available for a four-analyst biotech as readily as for Apple.

**What it does, every night:** every active US common stock on our venue with at
least one analyst → target, rating, price, 60-day high, 12-month return, sector,
next catalyst → one row per name per day, appended, **never overwritten**. Then
`STRONG_BUY / BUY / HOLD / SELL / DROP`, and every status change is logged with
the numbers that caused it. That log is the dataset you asked us to own, and it
is the label source if we ever train a network on this.

`WATCH` is a sixth label I added. A name we have never held, which today clears
no bar, has nothing to sell and nothing to drop — calling that SELL would fill
the log with three thousand exits a morning that never happened.

## 2. The number that matters, and it is not the one I expected

I tested the same rules on **IBES + CRSP, 2013–2024** — licensed, point-in-time,
the whole US market, 434,295 name-months. This is the instrument the terminal
repo does not have: our own tracker is one day old, so it cannot tell us its own
hit rate. Eleven years can.

**The first answer was that the screen loses badly: −5.48%/yr against the
market, t −2.10.** Then I sorted the names by how much upside they had:

| upside band | name-months | excess vs market | t |
|---|---|---|---|
| +30% to +50% | 47,357 | **+3.59%/yr** | 2.02 |
| +50% to +100% | 39,534 | **+5.98%/yr** | 2.22 |
| +100% to +200% | 20,301 | **+11.68%/yr** | 2.41 |
| +200% to +400% | 10,270 | **+17.19%/yr** | 2.45 |
| **+400% and above** | 54,232 | **−26.47%/yr** | **−4.71** |

The screen is monotone and strongly positive, and then it falls off a cliff.
The last band has a **median upside of 4,424%** — which is not a forecast
anybody made. It is a stale analyst target read against a price on a different
share basis: a company does a 1-for-10 reverse split, the old target sits in the
file at a tenth of the new price, and the ratio becomes arithmetic rather than
opinion.

Our rule said `upside ≥ 30%` with no upper bound, so it was buying all of it.

**Capping it turns the screen around completely:**

| | terminal wealth | CAGR | excess vs market | paired t |
|---|---|---|---|---|
| the market (equal weighted) | 2.863 | +9.23% | — | — |
| BUY basket, uncapped | 1.270 | +2.03% | −5.48%/yr | −2.10 |
| **BUY basket, capped at 4×** | **4.107** | **+12.59%** | **+3.88%/yr** | **+2.16** |

I want to be careful about how much credit to take for that, so two checks:

- **The threshold was not fitted.** `4.00` was already in the file as a warning
  flag before this data existed. And it is a **plateau, not a knife edge** —
  every cap between 1.5× and 10× gives +2.9% to +4.2%/yr at t 1.8–2.3. Only
  removing the cap entirely collapses it.
- **It holds in every era**, never pooled: +4.66% / +2.81% / +4.11% per year
  across 2013–16, 2017–20, 2021–24.

## 3. Your two intuitions: one confirmed, one refuted

**Thin coverage — you were right.** Once the stale targets are out:

| analysts covering | terminal wealth | CAGR | t |
|---|---|---|---|
| **1–3** | **4.213** | **+12.83%** | 2.15 |
| 4–10 | 3.819 | +11.90% | 1.87 |
| 11–25 | 2.837 | +9.14% | 1.54 |
| 26+ | 0.356 | −8.84% | −0.01 |

Monotone, in your direction. Worth knowing: **before** the cap, this looked
refuted — the 1–3 bucket was the *worst*. The bad data was concentrated in
exactly the thin names, so the measurement error was hiding your effect and
making you look wrong.

**Past winners — the data disagrees with you.** I ran both arms with the same
cap so the exclusion is the only difference:

| | terminal wealth | excess vs market | t | names/month |
|---|---|---|---|---|
| BUY, excluding past winners | 4.107 | +3.88%/yr | 2.16 | 416 |
| BUY, **not** excluding them | 5.587 | +6.74%/yr | 3.00 | 530 |
| **past winners only** | **18.174** | **+18.60%/yr** | **3.31** | 56 |

Excluding past winners costs about 2.9 points a year, and the names it throws
away are the strongest basket in the whole study. That is twelve-month momentum,
the most replicated effect in the cross-section. It does **not** contradict our
own earlier finding that winner-chasing is an anti-signal — that was measured
over five days; this is a twelve-month formation held one month.

**I left the exclusion ON.** You asked for it by name, and overriding you on
your own rule based on my own analysis is not my call. It is now a single
constant (`EXCLUDE_PAST_WINNERS`), one line to flip, with the whole table
written beside it. If you do flip it, flip it on **one** book, not all of them —
that is how we find out whether it was the rule or the market.

## 4. Concentration is costing us, again

The basket above holds ~416 names. Our books hold 5 to 15. So I tested that:

| holdings | excess vs market | t | months it beat the market |
|---|---|---|---|
| top 5 | +17.01%/yr | 0.95 | **46.2%** |
| top 10 | +4.34%/yr | 0.37 | 44.8% |
| top 25 | +6.28%/yr | 0.78 | 50.3% |
| top 100 | +6.89%/yr | 1.39 | 52.4% |
| all (~416) | +3.88%/yr | **2.16** | **57.3%** |

The 5-name book has the biggest headline number and **beats the market in fewer
than half of all months**. That is a handful of huge winners, not an edge you
can rely on. Reliability rises monotonically with breadth. This is the third
time this project has measured that.

## 5. One thing I built exactly as specified and think is wrong

hack3's "balanced" ranking is `exp_return − |downside_5pct|`. In practice
`exp_return` is about 0.0025 and `downside` is about 0.25 — a hundred times
larger. So the subtraction is dominated ~20:1 by the downside term and the
"risk-adjusted" book is really **sorting on low volatility alone**. You can see
it in the output: TSM, AVGO, NVDA on top. It quietly re-imports the mega-cap
bias the tracker was built to remove.

I implemented it as written rather than redesigning your spec mid-session. The
fix is to rank on a **ratio** (`exp_return / |downside|`) or to rank on
`exp_return` with the downside as a *constraint*. One line, your call.

## 6. Worst case, derived from the code

Read from `fleet.FLEET`, `engine.sizing.gross_cap` and
`engine.equity.stop_fraction` — nothing typed by hand, because a number retyped
beside the code that enforces it goes stale silently.

```
hack3  basket      10 x 8.3% =  83% of a 100% cap  x 8% stop  =  -6.64%
hack4  maximum      5 x 10%  =  50% of a 150% cap  x 6% stop  =  -3.00%
hack6  aggressive  15 x 6%   =  90% of a 100% cap  x 3% stop  =  -2.70%
```

All inside −9%. **No cap, stop, notional limit or opening-range rule was
touched.** hack4 runs the `maximum` profile whose cap is 1.50×, not 1.00× — a
worst case that assumed "basket" for all three would have understated it by
half and still printed confidently.

## 7. Monday

The overnight refresh needs to finish first. Then:

```
python -m scripts.tracker --backfill-prices     # re-derives price columns; refuses if the refresh is still writing
python -m scripts.tracker --show                # the candidate list
python -m scripts.tracker --sectors             # top 10 per sector
python -m scripts.prediction_book --seal --universe tracker
python -m scripts.prediction_book --verify
python -m scripts.prediction_book --publish
python -m scripts.tracker --portfolios          # the three books, worst case each
git add docs/seed && git commit && git push
```

`--publish` matters for the same reason it did last week: Railway mounts a
volume over `/app/state`, which **hides** anything the repo has there.

**One caveat on the sealed book, stated rather than buried.** Its `p_up` still
comes from the 152-name panel — the tracker is one day old and cannot produce a
forward rate yet. So the *ranking* is sound but the *level* of `p_up` is an
extrapolation. That is written into the book payload, and §2 above is the
honest version of the same question answered on eleven years.

---

## What I would do next

1. **Let the refresh finish, then seal on the tracker.** Tuesday's book should
   have many names, not one.
2. **Decide the two switches** — `EXCLUDE_PAST_WINNERS`, and the hack3 ranking.
   Both are one line and both are yours.
3. **Then the fantasy transposition harness** (T13), which is untouched. The
   tracker rows are what its decider will rank, so it was the right thing to
   build second.
