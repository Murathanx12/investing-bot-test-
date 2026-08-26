# Audit defect 4 — the exit pass IS starved, and it cannot cost more than slippage

**2026-08-26, day session 13.** Closing the last execution defect flagged as
possibly competition-blocking. **It is real, it is now smaller, and it was
mis-sized in my own handoff.**

## What was claimed

> **Defect 4 (exit sampling starved by the entry pass): CAN still affect the
> competition account.** It remains live for OPTION structures, which have no
> venue stop and are closed only when `exits.manage` runs — every 5 minutes at
> best, and the entry pass may hold the loop for up to 1500s. **Not closed.**

Literally true. Materially overstated, in both terms.

## Correction 1 — "up to 1500s" was a configured ceiling, not a measurement

`TIMEOUTS_S["scripts.run_pass"] = 1500` was a safety net someone picked, and I
quoted it as though it described behaviour. Measured over 10 completed entry
passes in `state/loop_exp1.log`:

| | seconds |
|---|---|
| median | **368** |
| p90 | **439** |
| max | **439** |

The ceiling was **3.4x the worst pass ever observed**, and it bought that
headroom by permitting a 25-minute exit delay that has never actually happened.

**Quote the measurement or don't quote the number.**

## Correction 2 — "no venue stop" is true and does not imply exposure

The book, read live:

```
unbounded: False
structures: 5 long_straddle · 2 iron_condor · 2 long_call
```

**Seven of nine structures are LONG-ONLY.** A long option's maximum loss is the
premium paid; it cannot lose more no matter how late the exit runs, and that
premium was charged against equity at entry. The two iron condors are
defined-risk by construction — the long wings cap the short legs — and
`book.unbounded` already refuses every entry in the account if any short leg
lacks its protective long.

So a delayed `manage` pass cannot produce a loss larger than one already
budgeted. What it can do is exit a `LONG_STOP` (-60% of debit) or `SHORT_STOP`
(-1.5x credit) later and worse.

`exits.py` had already written the argument down at line 29, and I did not read
it before writing the handoff:

> *A defined-risk structure cannot gap through its own stop, so the stop here is
> about redeploying capital, not about survival.*

**Defect 4 is a slippage and capital-recycling defect. It is not a ruin
defect.**

## What was changed

1. **`run_pass` timeout 1500s -> 600s**, which is ~37% above the worst pass ever
   observed. Worst-case exit delay falls from ~26 minutes to ~11. A pass that
   exceeds 600s is not slow, it is stuck, and the next cycle re-reads the venue
   anyway.
2. **An exit pass now runs immediately after every entry pass**, instead of
   waiting out the 60s sleep. By the time a ~6-minute entry pass returns, the
   five-minute exit cadence is already overdue; making it wait another minute
   delays a stop for reasons that have nothing to do with the position.

Together the typical exit lateness drops from about `368 + 60` seconds to
approximately zero, and the tail from 1560s to 660s.

## What was REFUSED, and why

**Venue-side stops on option structures.** The review proposed them; they are
wrong here in two different ways:

- **For multi-leg structures they are dangerous.** A stop on one leg of an iron
  condor that fills alone leaves the remaining legs as a *different structure
  with a different worst case* — potentially a naked short option. That converts
  a bounded book into an unbounded one in pursuit of protecting a bounded book.
  `protect.py` already refuses anything but single-leg SHARE rows for exactly
  this reason.
- **For long-only structures they are unnecessary.** Max loss is the debit,
  already paid and already charged.

The structure-level liquidation the review describes — aggregate stress, cancel
conflicting orders, ordered close, verify residuals, repair — is the right shape
*if* an unbounded structure could ever exist. `book.unbounded` is the cheaper
guard that stops one existing at all, and it is already enforced at entry.

## What this depends on

Both changes assume the loop is running. That assumption is no longer free:
`LOOP_LIVENESS_v1` (`alpha/liveness.py`, `python -m scripts.liveness`) landed in
the same session precisely because a software-side stop is only as alive as the
loop holding it. A dead loop has an infinite exit delay, and until today nothing
would have said so.

## Verdict

**Defect 4: CLOSED as a competition-blocking item. Downgraded to a measured
slippage cost.** It was never able to breach the max loss the book had already
charged. The two fixes are proportionate to the measured exposure rather than to
the alarming version of it.

## The rule worth keeping

> **A configured ceiling is not a measurement of behaviour.** I reported "up to
> 1500s" as the exposure when the observed worst case was 439s, and sized the
> defect from a constant someone typed rather than from ten runs sitting in a
> log file. The same reflex as *quote the cost rate or don't quote the count*.
