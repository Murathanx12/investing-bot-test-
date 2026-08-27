# FINDING — the engine works end to end, and its ranker optimises the wrong moment

Measured 2026-08-27 ~12:35 ET by evaluating a synthetic `post_event_drift`
forecast — the brain's own measured late-arrival number, centre **+0.72%**,
`claim="direction"` — against **live chains** at the 2026-08-28 expiry.

## THE GOOD NEWS FIRST: THE CHAIN IS WIRED AND THE NEW GUARDS BIND

| name | chosen | EV/max-loss | P(profit) | median | P(max loss) |
|---|---|---|---|---|---|
| NVDA | `long_call` | **+38%** | **33%** | **−$137** | **60%** |
| CRM | `bull_call_spread` | +16% | 29% | −$104 | 68% |
| DG | `long_shares` | +11% | **56%** | **+$1** | **8%** |
| SNPS | `long_shares` | +9% | 54% | +$3 | 12% |

Four things this confirms that were previously only asserted:

1. **`alpha/claims.py` binds in production.** On NVDA, both `long_straddle` and
   `iron_condor` were refused before pricing — *"iron_condor is sign-blind: it
   pays on the absolute move being SMALL and is the same trade whether the move
   is up or down."* This is the guard that would have stopped a directional
   brain being handed a condor, and it is now doing it against a real chain.
2. **Shares genuinely compete.** `long_shares` won twice and was recorded as a
   ranked alternative the other two times. DIRECT_FIRST is not a proposal.
3. **Options win on their merits, not by fiat.** NVDA and CRM chose option
   structures because the edge paid for the spread; DG and SNPS did not. The
   rules' "must incorporate options" requirement is satisfiable without forcing
   an instrument.
4. **CASH beats a bad option.** On SNPS the `long_call` cleared the MDM gate at
   +7.0% edge and was still refused: *"EV −$726/unit = −10% of max loss."*

## THE PROBLEM: +38% EV, 33% HIT RATE, NEGATIVE MEDIAN

The champion is chosen by `runner._ev_ratio`, which reads `ev_over_max_loss` —
the **arithmetic mean** payoff. On NVDA that picks the `long_call`:

    long_call     EV +38%   P(profit) 33%   median -$137   P(max loss) 60%
    long_shares   EV +12%   P(profit) 56%   median   +$1   P(max loss)  8%

The call has three times the expected value and loses **six times out of ten**.

Over a long series, ranking on the mean is right. **The contest is five
sessions.** Terminal wealth over a handful of sequential, compounding decisions
is governed by the median path, not by the mean — that is the whole Kelly
argument, and this repo already has Kelly in `sizing.py`. It just isn't in the
*ranker*.

This is the same error that produced the −$23,306, wearing different clothes.
That book bought the lottery-shaped payoff because a broken implied-move made
its mean look good. Here the arithmetic is correct and the *objective* selects
the lottery anyway.

**It is written down and NOT changed.** Kickoff is under a day away, the
champion ranker is on the path every order takes, and a same-day change to the
objective function of a system about to be judged is exactly the kind of edit
that produces a seventh instrument defect. The lever is being handed over, not
pulled.

## THE ARGUMENT ON THE OTHER SIDE, STATED FAIRLY

Two reasons the mean may be the right objective *here*, and they are not weak:

- **A contest pays for rank, not for survival.** If the field's podium needs a
  large return, a 33%-hit, high-payoff structure is the rational way to buy a
  chance at it. `TournamentState.field_leader_estimate` exists for exactly this
  and is `None` for most of the week.
- **The recorded rubric says the P&L bar is LOW** — a previous lablab winner
  scored on a **backtest** showing +$19, and criteria 2–4 decided the result.
  If the bar is low, the variance is not buying anything, and the median path
  is what a judge will see on the equity curve.

Those two point in opposite directions and the tiebreak is a preference about
what the account should look like on 4 September, which is Murat's call and not
the engine's.

## THE THREE OPTIONS, WITH WHAT EACH COSTS

1. **Leave it.** Ranker keeps the mean. Expect an option-heavy book with a
   choppy equity curve and real upside. No code change, no new risk.
2. **Rank on median, tie-break on EV.** One line in `runner._ev_ratio`.
   Produces a shares-and-spreads book with a smooth curve and a lower ceiling.
   Would likely have chosen `long_shares` on NVDA above.
3. **Cap the share of risk budget that may sit in structures with P(profit) <
   0.5.** Keeps the tail exposure and bounds it. More code, more to go wrong
   before kickoff, and the least tested of the three.

`P(profit)`, `median` and `P(max loss)` are already computed and already on
every ledger row — `payoff.economics` returns them and `verdict.economics`
carries them. Whichever is chosen, nothing new needs measuring; the numbers are
sitting there and only the *selection* reads past them.

## THE OTHER THING THIS RUN PROVED

`post_event_drift` has **zero decision rows in the entire ledger.** It has never
executed, never been ranked, never produced a live forecast. Everything above is
the first time the brain the contest is shaped around has been put through the
engine at all — and it was put through by hand, with a synthetic forecast,
because the real one refuses today for a correct reason (day-0 close still
forming).

A brain with a measured edge, a claim type, a shape, a docstring about surviving
late arrival — and no track record whatsoever in the machine that will trade it.
That is worth knowing before 11:00 ET rather than at 11:05.
