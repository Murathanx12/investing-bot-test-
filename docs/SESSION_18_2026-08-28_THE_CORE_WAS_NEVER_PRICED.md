# Session 18 — the core was never priced, and the book could not have been placed

*2026-08-28, overnight. Continues session 17.*

## RESULTS SCOREBOARD

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE in P&L.** No capital was deployed and no order was placed. |
| best historical net strategy vs the market | still **beta**. Long shares is the only structure positive on all three index underlyings with a positive t (SPY t **+3.58**) |
| best forward paper strategy | none. Both books remain management-only |
| independent selector count | unchanged |
| **allocations refuted** | **one, worth 70% of the book's risk** |
| **unplaceable order types caught** | **one, in the book's own core** |
| new actionable finding | selling index put spreads at this horizon loses to holding on all three underlyings |
| external execution drag | not re-measured this session |
| LLM spend | none — every number here is arithmetic over stored data |

A session that ships a lot of engineering and moves no P&L says so first. This
one did not raise the account by a dollar. What it did was stop a 70%-of-risk
allocation from being funded on evidence that could not support it, and stop an
order type that the venue rejects from being discovered at 15:50 ET on a
competition day.

## What was asked, and what the answer turned out to be

The review asked one question above the others:

> Backtest the exact SPY/QQQ/IWM short-put-spread family using **historical
> option prices**, not simulated stock returns. If the core does not survive,
> kill or condition it before kickoff.

It does not survive.

`optionm.opprcd`, 1996-2025, **11,859,415 real bid/offer rows**, ~3,000
non-overlapping five-session blocks, execution crossed against us on all four
crossings:

| short put spread | SPY | QQQ | IWM |
|---|---|---|---|
| median / hit | +2.94% / 68.8% | +2.21% / 58.8% | +1.76% / 57.7% |
| **mean / t** | +0.67% / +2.16 | **−1.27% / −3.54** | **−0.65% / −1.94** |
| **terminal wealth** | 2.79x | **0.05x** | **0.21x** |
| buy & hold, same window | **5.39x** | **5.14x** | **2.50x** |

**Fails on two of three, beats holding on none.** QQQ has a positive median, a
58.8% hit rate, and turns a dollar into five cents — the same variance drag that
killed the momentum candidate in session 17, in a different instrument.

Full detail: `FINDING_2026-08-28_THE_CORE_WAS_NEVER_PRICED.md`.

## The other three things

**The book was unplaceable.** Step 5 said "enter MARKET-ON-CLOSE" for a core of
multileg options; Alpaca accepts `tif=day` for options and nothing else. And the
15:50 ET CLS cutoff means a signal read off the 16:00 close can never trade that
close — lookahead in the execution layer.
`FINDING_2026-08-28_THE_BOOK_COULD_NOT_HAVE_BEEN_PLACED.md`.

**Long premium is annihilated.** The long straddle: t **−5.66 to −8.72**, 0.00x
terminal wealth on all three underlyings, negative median in every era. The
August book's single largest loss was a long straddle (−$22,017).

**NFP is not a trade.** 379 releases since 1999: the whole effect is the **gap**
(62% hit), the intraday segment is *negative* on release days, and the
release-day move is only **1.13x** an ordinary day. Hold into it and add nothing.
`FINDING_2026-08-28_NFP_IS_NOT_A_TRADE.md`.

## What replaced the book

`COMPETITION_BOOK_v1` is withdrawn rather than patched. v2 has **no fixed core**.

- `alpha/timing.py` — venue order semantics. Refuses an MOC whose signal froze
  late, and one whose freeze time is merely *unknown*.
- `alpha/spreads.py` — real chain, crossed against us. `matching_spread` selects
  the **replayed geometry**: ranking by credit/width picks a near-ATM coin flip
  (live SPY chose 763P/762P at 43% of width) and the measured distribution would
  not describe that trade.
- `alpha/nodes.py` — SPY+QQQ+IWM score **1.54 effective nodes**, not three
  positions. Beta loadings measured from returns; structural ones declared.
- `alpha/tournament.py` — contest P(target) and real-money log wealth kept apart,
  and **the mode selects the objective**.
- `scripts/execution_probe.py` — every order shape the book can emit, validated
  offline. **Not yet exercised live**, which is the one item on this page that is
  documented rather than demonstrated.

Aegis gains `backend/services/copy_lab/sentinel.py`: a refusing lane and a dead
lane no longer write the same file.

## Six bugs found in my own work, five of them by tests

Listed because the ratio matters more than the count: almost none of these were
found by reading.

1. **The delta filter deleted the losing tail.** Filtering the pull on
   `abs(delta)` dropped the *exit* quotes of trades that went wrong — 117 of 409
   SPY blocks, exactly the losers. Now filtered on moneyness.
2. **The benchmark spanned a different window** than the strategy (26y vs 20y).
3. **A threshold objective has no gradient** — the greedy auction allocated
   nothing in precisely the ATTACK case it exists for.
4. **The bid ladder doubled** and could never offer the exact remaining budget.
5. **The per-name cap was defeated by decomposition** — SPY under three
   structure names, 6% each.
6. **Node caps were enforced without betas and reported with them.**

And one mistake in the sentinel that is the sentinel's own lesson in miniature:
it first reported the twelve deliberately-dormant lanes as FAIL, which is twelve
permanent red lines beside two real ones.

## Verified state

- terminal repo: **1390 checks, all pass**; commit `59e76c5`, pushed.
- Aegis repo: fast suite green; `optionm_etf_quotes` added (11.86M rows).
- **No capital deployed. No order placed. Both books remain management-only.**

## Still open

- **Registration closes 11:00 ET today**, and the judged account needs **options
  level 3** or the spread structures cannot be placed at all.
- The execution probe has **not** been run live. Nothing here proves an mleg
  payload is accepted as written by this account.
- The auction simulates opportunities **independently**, which understates the
  left tail. Shared exposure is handled by node caps, not inside the simulation.
- The book still shows **1.12 effective bets** and refuses itself on
  concentration. Three index instruments cannot be diversified by holding all
  three; that needs a genuinely different alpha source, which is the research
  programme's problem and not this week's.
