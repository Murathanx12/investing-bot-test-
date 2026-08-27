# NFP_FINAL_BOSS: the last event of the contest is not worth a special trade

*2026-08-28. `scripts/nfp_reaction_history` (Aegis repo). 379 Employment
Situation releases from FRED release 50; SPY 321, QQQ 318, IWM 305 release days
against ~6,300 control days each, 1999-2025.*

## Why it was asked now, and frozen now

The August Employment Situation is released **08:30 ET on 4 September 2026** and
the competition deadline is **11:00 ET the same morning**. It is the last
information event of the contest and the only one whose timing is known to the
minute. A decision about it made at 08:29 is not a decision, so this is settled
days early.

`scripts/nfp_straddle_backtest` already grades a 0DTE straddle, but only over
2024-2026 — **28 releases**, because Alpaca's option history starts there. At 28
events a 57% hit rate and pure noise are the same picture. The *underlying* we
have back to 1999 from the OptionMetrics pull, so the reaction is measured over
**~320 releases per symbol** instead.

## What release day actually does

| SPY | NFP mean | control mean | diff | t | NFP \|move\| | control \|move\| | NFP hit |
|---|---|---|---|---|---|---|---|
| **gap** (prev close → open) | +0.094% | +0.023% | +0.071% | **+1.67** | 0.558% | 0.439% | **62.0%** |
| intraday (open → close) | **−0.013%** | +0.007% | −0.020% | −0.34 | 0.717% | 0.666% | 52.6% |
| full day | +0.081% | +0.030% | +0.051% | +0.71 | 0.916% | 0.812% | 57.3% |

Three things, and all three point away from a special trade.

**1. The whole effect is in the GAP, and the session gives some of it back.**
The gap contains the 08:30 release (the open is 09:30) and hits **62% of the
time**; the intraday segment on release days is *negative*. This is the overnight
decomposition again — `FINDING_2026-08-28_ALL_OF_IT_HAPPENS_OVERNIGHT.md` — in
the one place we had a specific reason to expect an intraday move.

**A position already held into the release captures that gap for free.** There is
nothing to buy.

**2. The release-day move is barely larger than an ordinary day's.**

| | SPY | QQQ | IWM |
|---|---|---|---|
| \|full-day move\| vs an ordinary day | **1.13x** | **1.13x** | **1.09x** |
| t on the difference | +2.11 | +1.92 | +1.65 |

A long-premium NFP trade is paying an event premium for a **13% excess move**,
and on QQQ and IWM that excess is not resolvable at all. Combined with the
straddle result from real option prices — t between **−5.66 and −8.72**, 0.00x
terminal wealth on all three underlyings over 26 years — buying premium into this
print is the worst-supported trade available.

**3. The directional edge is one regime.**

| full day, mean | ≤2007 | 2008-2012 | 2013-2019 | 2020-2025 |
|---|---|---|---|---|
| SPY | +0.076% | −0.071% | **+0.255%** (t +2.50) | +0.006% |
| QQQ | +0.137% | −0.185% | +0.250% (t +1.88) | −0.112% |
| IWM | −0.143% | −0.118% | **+0.303%** (t +2.61) | +0.081% |

Everything positive lives in 2013-2019. The most recent era is flat to negative
on two of three. Same shape as every other candidate this project has examined.

## The frozen decision

> **No NFP trade.** Hold whatever the book already holds into the release, take
> the gap for free, and do not add, hedge or straddle around it.

Kill conditions for that decision, decided in advance:

- if the book is **already at or above target** on 3 Sep, reduce risk into the
  print — the gap is worth +0.09% and the tail is worth more than that;
- if the book is **materially behind** on 3 Sep, the ATTACK case applies, but the
  instrument is *not* an NFP straddle. Its measured median is −8% and its t is
  −5.66. Convexity should be bought where the evidence supports it, not where the
  calendar is loudest.

## The limit of this study, stated plainly

Daily bars support prev-close→open, open→close and prev-close→close. They **do
not** support open→10:00 or open→10:45, which is the window the contest actually
trades. A daily-bar study can say whether release day carries an unusual return
or an unusual range; it cannot say when within the session it arrived. The
2024-2026 minute-bar work remains the only evidence about intraday timing and
this document does not overrule it — it bounds the *size* of what that timing
could be worth.
