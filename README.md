# AEGIS Alpha Terminal

**An autonomous options trading agent for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) (28 Aug – 4 Sep 2026).**

> Every other trading agent decides **which way** a stock is going.
> This one decides **what shape** the edge has — because a signal whose payoff
> lives in the tail *is* an option, and a signal whose payoff is a broad plateau
> is a stock book. We measured which is which over 32 years of market history,
> and the agent picks the instrument to match.

**What this repo is, in three lines.** It is the EXECUTION brain of the AEGIS
programme: six Alpaca **paper** accounts, each a declared mandate in
`alpha/fleet.py`, running unattended as Railway services `aat-loop-<role>`.
Each trading day is a **sealed book** (`state/predictions/<day>.json`) that the
runner may cut but never raise; no sealed book means no trade. The strategy,
canon and research live one repo over, in `../aegis-finance`.

**AI agents: read [`docs/INDEX.md`](docs/INDEX.md) first** — TIER 0 is what this
repo is plus the four non-negotiables, TIER 1 points at the live session queue,
and the MAP answers "how does a day get sealed / how do orders happen / how do I
check everything / what watches the market / what grades us / where are the
receipts" with a verified file path on every line.

**Session-start protocol:** `session_briefing()` + `aegis_verified_state()`
(Optimus MCP) → `docs/INDEX.md` TIER 0 → the top block of
[`docs/HANDOFF.md`](docs/HANDOFF.md) (its SKIM LAYER, then `WHAT IS LEFT`) →
`brain_query` before proposing anything, because the idea may already have a
corpse with receipts. Tests run ONLY via `python run_tests.py`.

---

## The idea in one picture

A signal's *quantile curve* — mean forward return by decile of its score — has a
shape, and the shape is structurally a financial instrument:

```
  TAIL                              STEP
  ····························▇     ·······▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇
  flat, then the top decile jumps   a cliff, then a PLATEAU

  the payoff IS an option           the payoff is a stock book
  → BUY CONVEXITY, narrow           → BUY BREADTH, wide
                                       there is no tail to pay for;
                                       a top-k slice sits on the
                                       flattest part of the curve
```

Buying a call on a STEP signal is paying for a tail the data says is not there.
Holding a hundred names on a TAIL signal dilutes the only decile that pays.
Both are ordinary mistakes, both look like "using options", and both are
measurable in advance.

So the agent refuses to buy convexity on `profit_roe` — a signal with the
*strongest* statistical evidence in the whole research programme — because its
top four deciles were measured to be a flat plateau. **That refusal is the
project.** It is a decision no prompt-based agent would ever make.

## Two mechanisms

**1. Shape-aware construction** — `alpha/engine/shape.py`

Reads a decile curve as geometry before reading it as a ranking, and maps the
shape to an instrument. Distinguishes a real discontinuity from the end of a
ramp by measuring the top decile's lift against the curve's *own* typical step;
without that test every monotone signal looks like a tail.

**2. The minimum detectable move** — `alpha/engine/sizing.py`

A structure bought at the real **ask** and closed at the real **bid** does not
break even at zero — it breaks even at a specific underlying move. Call it the
minimum detectable move. The position is only interesting if our forecast puts
materially more probability beyond it than the option chain's own implied
distribution does:

```
    edge = P_model(|move| > MDM) − P_implied(|move| > MDM)
```

If that is small, the trade is a coin flip with a fee — however confident the
thesis sounds. The agent will refuse a trade **for agreeing with the market**.

This is the research programme's `MDE = z·te/√T` discipline transplanted into a
place where the market quotes the denominator for us. It came from discovering
that, on a 32-year replay, *zero of thirteen signals produced an effect the
window could resolve* — every leaderboard printed before that check was a
ranking with no resolution behind it.

## Risk gates

Every structure states a **bounded worst case at entry**; one that cannot is not
representable in the type system, which is how naked short options are excluded.
On top of that:

| Gate | Rule |
|---|---|
| Spread | round-trip spread > 25% of max loss → refused |
| Resolution | probability edge over the chain < 5pp → refused |
| Concentration | per-name cap set by the account's sizing PROFILE (`alpha/engine/sizing.py`): conservative 3% · aggressive 8% · basket 6% · convex 5% · maximum 15%; scaled by the size of the edge |
| Aggregate | per-profile envelope: 20% / 50% / 80% / 40% / 75% of equity at risk simultaneously. The SAFE accounts (hack1, hack2) run the two smallest; the RISKY fleet (hack3-6) runs the rest by declared mandate (`alpha/fleet.py`) |
| Structure | no undefined-risk position, ever |
| Deadline | every position closable by 10:45 ET on 4 Sep |

The objective is **rank, not Sharpe**. Over five sessions judged against a field,
the difference between +2% and +4% is nearly worthless and the difference
between +15% and +30% is the prize — so the sizer escalates convexity when it is
behind late, and protects when it is ahead late. It escalates *within* defined
risk, so the downside branch is a bad week rather than a zero.

## Safety

This repo can only reach Alpaca's **paper** environment. Three independent
refusals, each with a specific incident behind it:

1. **It never reads `ALPACA_API_KEY_ID`.** That variable exists on the developer
   machine attached to a live account; a smoke test in the parent project once
   placed twelve real sell orders through it. Every credential here is `AAT_*`,
   and the refusal message names the variable it is protecting you from.
2. **The live host is not in the allowlist**, and no flag adds it.
3. **The account role is declared, never defaulted** — an unset variable
   selecting the judged account is the one mistake with no undo.

Orders are **idempotent** (`client_order_id` derived from the decision, so a
crash-restart collides instead of doubling) and every order **records the bid,
ask and size seen at decision time**. Alpaca's paper environment does not model
market impact or order size against displayed NBBO quantity; we do not use that,
and the quote snapshots are how anyone can check.

## The ledger

Append-only, hash-chained JSONL — every candidate considered, **including the
ones that were refused**, with the reason and the quote that justified it.

A log containing only executed orders can answer "how did we do?" and nothing
else. A rejected candidate that later moved 12% is the most valuable row in the
file, and it only exists if the refusal was written down when it was made.

```bash
python tests_smoke.py          # 21 checks, no keys, no network
python -m scripts.preflight    # prove the account is paper, funded, and fresh
```

## Documents

| | |
|---|---|
| [`docs/RULES_SNAPSHOT_2026-08-25.md`](docs/RULES_SNAPSHOT_2026-08-25.md) | The competition rules, pulled from the live page |
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | Thesis, competitive read, catalyst calendar |
| [`docs/COMPETITOR_WATCH.md`](docs/COMPETITOR_WATCH.md) | Who is building what |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Current state and next steps |

## Provenance

Derived from the AEGIS Finance research programme (`AEGIS_SOURCE_COMMIT=44c8352`)
— a self-improving investment intelligence system built around point-in-time
discipline, matched controls, and power analysis. The decile shapes this agent
relies on are summary statistics measured there over a 32-year replay of a
frozen daily history, across three independent data sources: prices, accounting
fundamentals, and analyst estimates.

No licensed data, no secrets and no research ledgers are carried into this repo.

MIT licensed.
