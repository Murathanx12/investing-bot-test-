# AEGIS Alpha Terminal — how this wins

## The one sentence

> Every other agent in this hackathon decides **which way** a stock is going.
> This one decides **what shape** the edge has — because a signal whose payoff
> lives in the tail *is* an option, and a signal whose payoff is a broad plateau
> is a stock book. We measured which is which over 32 years of CRSP, and the
> agent picks the instrument to match.

That is the differentiator, and it is not a slogan we can be caught not having:
`alpha/engine/shape.py` is the mapping, the decile curves behind it are real
measurements from the parent research project, and the agent visibly refuses to
buy a call on a signal whose measured tail is empty.

## The competitive read

Four judged criteria, **P&L first and highlighted** (see the rules snapshot).
~2,236 registered participants; realistically a few hundred submissions.

Three public entrants at snapshot time tell us where the field sits:

| Team | Concept | What it means for us |
|---|---|---|
| `midas-gate` | Sells defined-risk SPY credit spreads, gold/GLD/UUP as a regime filter | The serious competitor. Short-premium on SPY is the *right* trade most weeks and it is explainable. It is also **capped**: credit spreads can win small, not large. In a 5-session P&L race it very likely finishes mid-pack-positive. |
| `Dawn Of The Trading Agents` | Bull-agent / bear-agent / risk-agent debate | The commodity architecture. Expect a dozen of these. The parent project already measured that specialist personas are mostly correlated forecasters wearing different hats — **do not build this.** |
| `AlpacaSentry` | Event-triggered LLM reasoning + MCP news + rationale dashboard | Closest to us on *presentation*. Their differentiator is the trigger; ours has to be what happens after the trigger. |

**The commodity project this week is: LLM reads news → says bullish → buys a
call.** Our originality has to be something that cannot be produced by a good
prompt, or it isn't originality.

## What "risky" should actually mean here

Murat's instruction is to go risky, and that is the right instinct — a +1.2%
account with a beautiful Sharpe loses to a +30% account. But there are two very
different things called risky and only one of them has positive expected value
under *this* scoring:

**Convexity without a floor** — naked shorts, undefined structures, size that
can gap through a stop overnight. The modal outcome is a blown account, which
fails criterion 1 *and* directly contradicts the "risk gates" section we are
required to submit. It also destroys the evidence we want to bring home.

**Maximum convexity within defined risk** — every structure states a bounded
worst case at entry, and the aggression goes into *how many independent convex
shots we take* and *how large each premium is*, not into removing the floor.
The ceiling here is `MAX_AGGREGATE_CONVEX_RISK = 35%` of equity in premium at
risk simultaneously. That is a genuinely aggressive book by any normal standard
— a long-only manager would call it reckless — and it cannot produce a zero.

**We build the second one.** The realistic target is **+8% to +25% over five
sessions**, which should land in the top decile of the P&L field while remaining
an account a judge can read. Chasing +100% requires the first kind, and in a
four-criterion contest the expected value of that trade is negative.

One honest caveat, stated once: if the field's leader is at +60% on Thursday
afternoon, the rank-optimal policy really does become "swing for it," and
`sizing.py` implements exactly that escalation (`behind and late -> 2.0x`). The
difference is that it escalates *within* defined risk, so the downside branch is
a bad week rather than a zero.

## Architecture

```
    GLOBAL WORLD                       ALPACA MARKET DATA
 news · filings · macro · Asia/Europe   quotes · bars · OPRA chain
             │                                    │
             └──────────────┬─────────────────────┘
                            ▼
                    WORLD SENSOR  (LLM: extract, classify, dedupe)
                            │
       ┌────────────┬───────┴────────┬──────────────┐
       ▼            ▼                ▼              ▼
   EVENT       TAIL MOMENTUM    DISPERSION     GLOBAL RELAY
  RESPONSE      (mom_12_1)    (rev_dispersion)  (ADR/ETF)     + CRYPTO 24/7
       │            │                │              │
       └────────────┴────────┬───────┴──────────────┘
                             ▼
                   ┌──── SHAPE ENGINE ────┐          ← the differentiator
                   │ tail  → convexity    │
                   │ step  → wide equity  │
                   │ inv/degen → REFUSE   │
                   └──────────┬───────────┘
                              ▼
                   FORECAST DISTRIBUTION  (centre + uncertainty)
                              │
                              ▼
            OPTION CHAIN  →  IMPLIED DISTRIBUTION
                              │
                              ▼
              MINIMUM DETECTABLE MOVE  (from real bid/ask)   ← the second one
              P_model(beyond MDM) − P_implied(beyond MDM)
                              │
                              ▼
                  TOURNAMENT SIZER (rank objective, defined risk)
                              │
                              ▼
                ALPACA  (alpaca-py loop · CLI audit · MCP demo)
                              │
                              ▼
              HASH-CHAINED DECISION LEDGER  →  ALPHA TERMINAL UI
                    (including every REFUSED candidate)
```

### The two mechanisms that are ours

**1. Shape-aware construction** (`alpha/engine/shape.py`). A decile curve is
read as *geometry* before it is read as a ranking. The classifier distinguishes
a genuine discontinuity from the end of a ramp by measuring the top decile's
lift against the curve's own typical step — without that test every monotone
signal looks like a tail and the agent buys convexity on all of them. It was a
real bug in the first draft and the smoke test now pins it.

**2. The minimum detectable move** (`alpha/engine/sizing.py`). The parent
project's habit is to ask *could this sample have answered?* before *what did it
say?* — a habit that came from discovering that zero of thirteen signals on a
32-year window produced an effect that window could resolve. The options version
is cleaner because the market quotes the denominator: a structure entered at the
ask and exited at the bid breaks even at a specific underlying move, and unless
our forecast puts materially more mass beyond that move than the chain does, the
trade is a coin flip with a fee. Two gates fall out of it, and both fire in the
smoke test: *agreeing with the chain is refused*, and *a 40%-wide option spread
is refused however good the thesis*.

### Why options are structural here rather than a checkbox

The requirement says every strategy must incorporate options. Most teams will
satisfy it by buying a call after an LLM says bullish. Ours satisfies it because
**two of our three strongest signals were measured to be TAIL-shaped**, and a
tail-shaped payoff is definitionally an option: small premium, large payoff,
usually worthless. `rev_dispersion` — analyst disagreement — is the sharpest
case, because high disagreement is literally a forecast of realised dispersion,
which is what a straddle is long. Meanwhile `profit_roe` is a measured *plateau*
and the agent refuses to buy convexity on it. That refusal is the demo.

## The catalyst calendar is the plan

Five sessions is too few to wait for a signal. The window's events are known, so
the agent front-runs its own attention rather than scanning blindly.

**Re-verify every one of these before acting — they are sourced from the
briefing, not from a primary filing.**

| When (ET) | Event | Why it matters here |
|---|---|---|
| Tue 1 Sep, pre-open | **NIO** Q2 | The global-relay demo: a China EV print with US-listed consequences across NIO/LI/XPEV/TSLA/LIT. |
| Tue 1 Sep, 10:00 | **JOLTS** (July) | SPY/QQQ index event. |
| Tue 1 Sep, post-close | **PANW** FQ4 | Single-name vol, tradeable Wednesday. |
| Wed 2 Sep, post-close | **AVGO** FQ3 | **The biggest single-name event in the window** — and Thursday is a full session to monetise it. |
| Thu 3 Sep, 08:30 | Productivity & Costs (revised) | Minor. |
| Thu 3 Sep, pre-open | **CIEN** FQ3 | Optical/AI-infra read-through. |
| **Fri 4 Sep, 08:30** | **Employment Situation (August)** | **2.5 hours before the deadline.** Lands pre-market; only 90 minutes of trading to monetise, and it must be closed by ~10:45. |

Two tactical notes the calendar forces:

- **Thursday 3 Sep is the last full session.** It is the natural day for the
  largest convex position of the week (AVGO's reaction) and the natural day to
  start reducing anything that needs time.
- **The jobs report is the final act and it is a 90-minute trade.** Options
  bought Thursday will already carry that event's vol. The rank-optimal size for
  it depends entirely on where the account stands Thursday night, which is
  precisely what `TournamentState` exists to encode.

## Weekend crypto is 25% of the calendar

29–30 Aug have no equity market. Crypto trades 24/7 on Alpaca and is the only
way the account moves. This is not a side quest — it is two of eight days, and
it makes the agent visibly *autonomous and always-on* for the demo, which is
criterion 2 and criterion 4.

## The Shadow Arena

Do not create dozens of Alpaca accounts. Run N virtual $100k books internally
off the **same frozen live decision state** — event-only, tail-momentum-only,
dispersion-only, relay-only, crypto-only, aggressive-convergence, and a
do-nothing control. The judged account trades whichever sleeve the evidence has
actually promoted; the rest generate counterfactuals in real time.

**No sleeve is promoted today.** The counterfactual ledger spans two calendar
days, which cannot rank one brain against another — so until a sleeve earns it,
the judged account trades an *assigned* set and the write-up says so.

This reuses the parent project's `portfolio_farm` idea directly, and it gives
the dashboard something almost nobody will have: **what the agent did *not* do,
priced.** It is also the mechanism that makes the whole week worth importing
back into the research project afterwards.

## What comes home on 4 September

The tournament risk policy does **not** come back. What comes back is the corpus:
every decision, every *refused* candidate with its reason, the quote that
justified it, the forecast distribution, the chain snapshot, the fill, the
outcome, and the shadow books' counterfactuals — hash-chained and PIT-honest.

The parent project has never had a live forward record of itself actually trying
to make money. After five months in which the demonstrated edge stayed at 0%,
five days of that is worth more than another power calculation.
