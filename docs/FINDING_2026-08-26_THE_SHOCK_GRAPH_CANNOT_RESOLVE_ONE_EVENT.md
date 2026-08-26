# The shock graph is underpowered on one event — measured BEFORE the event

**2026-08-26, day session 12, ~08:00 ET — four hours before NVDA reports.**
Artefacts: `state/event_state/NVDA_2026-08-27_{vector,shock}.json`
(sealed `a1634ef3ce52b31a4acb40e904514a20` / `4d3ad6fae2ff50a66e62f5f4d0ad30fa`).
Reproduce: `python -m scripts.nvda_preprint --power`.

## The result in one paragraph

The continuation brief asked for a causal graph around tonight's NVDA print, to
be read tomorrow for `large fundamental exposure x small price response`. The
graph is built, frozen and sealed — 24 nodes, each with a declared sign, lag and
observable, plus a measured NVDA-beta and a frozen pre-print price. **Then the
power check said the reading it was built for cannot be done on one event.**
Every node's one-event minimum detectable underreaction lands between **5.9% and
24.0%**, against an option-implied NVDA move of **5.1%** measured from our own
chain. The best single node is TSM at 5.9%. There is no plausible move tonight
that produces a residual any node could resolve.

This is the standing rule applied on time for once: *ask whether the sample
could have answered, before asking what it said.* The difference is that the
project has usually asked it afterwards.

## Why grouping does not fix it, and what does

The obvious repair is to stop reading nodes individually and read each EDGE as a
portfolio. It barely works, and the reason is the interesting part:

| edge | n | MDE, NVDA only | MDE, + SMH control | events for 2% |
|---|---|---|---|---|
| `future_capacity_constraint` | 8 | 7.5% | **3.8%** | 3.6 |
| `customer_financing_quality` | 3 | 4.9% | 4.9% | 6.1 |
| `custom_silicon_competition` | 3 | 7.3% | **5.0%** | 6.1 |
| `HBM_cost_pressure` | 2 | 12.4% | **5.9%** | 8.6 |
| `datacenter_surprise` | 5 | 13.2% | 10.1% | 25.6 |
| `Blackwell_demand` | 3 | 11.3% | 10.2% | 25.9 |

**The five optical/datacentre names carry a HIGHER group residual sd (4.72%)
than several of them do individually.** Averaging them diversified nothing,
because the residual is not idiosyncratic noise — it is a SECTOR FACTOR, and
adding more names from the same sector concentrates it rather than cancelling
it. That is a fact about the construction, not about the signal, and it is the
same shape as the parent project's finding that ten names out of five hundred is
what makes tracking error 34%.

So the control belongs **in the regression, not in the sample size**. Regressing
on NVDA *and* SMH halves the MDE on the edges whose mechanism is broad —
capacity 7.5% → 3.8%, memory 12.4% → 5.9%, custom silicon 7.3% → 5.0% — and
barely moves optical or server-ODM, which carry their own factor that a
semiconductor proxy does not span. Those two edges need their own control
(an optical or hardware basket) before they can be read at all.

## What the betas said, which was worth the exercise on its own

| already priced as an NVDA name (β ≥ 1.0) | barely priced (β < 0.5) |
|---|---|
| AAOI 1.65, SMCI 1.59, COHR 1.26, MU 1.14, LITE 1.09, MRVL 1.03 | META 0.44, PWR 0.35, AMZN 0.31, GOOGL 0.26, MSFT 0.23 |

Every R² is low — 0.05 to 0.46, TSM highest. **Even for the names the market
plainly trades as NVDA derivatives, NVDA explains at most 46% and typically
~20% of their daily variance.** A residual computed against that beta is
four-fifths noise, and the "underreaction" ranking the brief asked for would
have been a rank with no resolution behind it, exactly like every farm signals
leaderboard before `portfolio_farm_signal_power` was written.

Note the cell that was hypothesised and did NOT appear: **no node has high
declared economic exposure AND a beta below 0.5.** The pitch for this graph was
that the market has not yet repriced the second-order names; on this sample it
has. The names we declared `high` exposure are the names already carrying β ≥ 1,
and the low-beta names are the hyperscalers we ourselves declared `low`.

## The measurement that was quoted and should not have been

The evidence bundle carried `reported_implied_move_28aug: 0.0558` sourced to
25 Aug previews. Measured from our own 28 Aug chain: **0.051**. Not a large gap,
and not the point — the point is that we could not have known what the quoted
number was computed from, and now the number in the artefact is one we made.
The reported figure is retained as a cross-check and labelled as such.

## What this changes tonight

1. **No trade from this instrument.** That was already the plan — the
   competition account does not exist until 28 Aug 15:00 UTC and NVDA was
   designated a calibration event — but it is now a measured statement rather
   than a stance.
2. **The vector still gets resolved tonight, in order.** `StateVector.resolve()`
   fills the thirteen fields from the release, and `reaction()` REFUSES to
   return the price move until every field is filled or explicitly marked
   `UNAVAILABLE`. A move you have already seen cannot be un-seen while reading
   the facts that caused it.
3. **The information hierarchy is the live claim.** We committed, before the
   print, that `q3_guide_surprise` carries more information than
   `revenue_surprise` — the Q2 headline is ranked LAST of thirteen on the
   grounds that the quarter is nine weeks old and largely pre-announced by the
   supply chain. If tomorrow's move is explained by the headline and not by the
   guide, that ranking was wrong and the record said so first.
4. **The graph accrues.** It is an instrument for repeated shocks, not for one.
   The capacity edge needs ~4 comparable events at a 2% target; the optical edge
   needs a better control before it needs more events.

## What it changes for the roadmap

`docs/ROADMAP_2026-08-26_INFORMATION_FIRST.md` A2 is amended: the shock graph is
**not** a next-day trade generator and must not be presented as one. It is a
repeated-measurement instrument, and its first job is to accumulate events.

And a rule that generalises past this graph, which is the part worth keeping:

> **Before averaging a group to beat noise, check whether the noise is shared.**
> A portfolio of one sector's names does not diversify that sector's factor —
> it concentrates it. Diversification is a property of the RESIDUALS, and it is
> measured, never assumed from n.

## Caveats, stated rather than buried

- 120 sessions, one lookback, one control (SMH). A different window or control
  moves these numbers; the ORDERING across edges is the durable part.
- 2.8σ is the usual 80%-power two-sided constant. Nothing here is a t-statistic
  on a result — there is no result yet, which is the finding.
- `events_for_target` assumes independence across events. NVDA prints are
  quarterly and the supply chain's composition drifts, so treat 3.6 events as a
  floor rather than a schedule.
- Betas are OLS on daily closes with no lead/lag term. A supplier that reacts at
  a one-session lag has some of its NVDA exposure sitting in the residual, which
  inflates its MDE. That is conservative in the direction that matters.
