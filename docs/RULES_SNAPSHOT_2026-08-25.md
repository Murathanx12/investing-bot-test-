# Rules snapshot — Alpaca AI Trading Agents Hackathon

**Pulled 2026-08-25 from the live event page**, not from memory and not from a
summary. Source: `https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon`
(the page is a Next.js app and returns 403 to plain fetchers; the text below was
extracted from the RSC payload, saved verbatim in the session scratchpad).

**Re-pull this file at kickoff on 28 Aug.** Everything below is a fact about a
web page on one day.

---

## Window — and it is shorter than it looks

| | UTC | ET |
|---|---|---|
| Kickoff | **2026-08-28 15:00** | Fri 28 Aug, 11:00 |
| Submission deadline | **2026-09-04 15:00** | Fri 4 Sep, **11:00** |

Machine-readable `startDate` / `endDate` from the page's own JSON-LD.

**The deadline is 11:00 ET, ninety minutes after the opening bell — not the
close.** Everything downstream follows from this:

| Session | Equity trading available |
|---|---|
| Fri 28 Aug | 11:00–16:00 ET — **partial**, 5h |
| Sat 29 / Sun 30 Aug | **crypto only** (24/7 on Alpaca) |
| Mon 31 Aug | full |
| Tue 1 Sep | full |
| Wed 2 Sep | full |
| Thu 3 Sep | full — **the last complete session** |
| Fri 4 Sep | 09:30–11:00 ET — 1.5h, then judged |

Total: **32.5 hours = exactly 5.0 equity sessions**, plus two crypto-only days.
Labor Day is Mon 7 Sep, *after* the window, so there is no market holiday inside it.

Two consequences that should shape the code, not just the plan:

1. **Every position must be closable by ~10:45 ET on 4 Sep.** A thesis that
   needs Friday's close to work cannot be expressed. The agent needs a hard
   liquidation deadline as a first-class parameter, not an afterthought.
2. **Two of the eight calendar days have no equity market at all.** Crypto is
   the only instrument that can move the account on 29–30 Aug. That is not a
   gimmick — it is 25% of the calendar.

## Judging criteria — verbatim, in the page's own order

The first card is styled `--primary` on the page. That is the site telling us
which one it weighs most.

1. **P&L Performance** — *"The trading performance of the submitted agent in the
   Alpaca paper trading environment. Judges will consider the project's P&L and
   how effectively the strategy performs through its trading activity."*
2. **Technology Implementation** — *"How effectively the project uses Alpaca's
   Trading API, MCP server, CLI, and other required technologies to build an
   autonomous trading agent."*
3. **Creativity & Originality** — *"The originality of the concept, trading
   strategy, agent behavior, and overall approach."*
4. **Presentation & Execution** — *"How clearly and effectively the project
   communicates its idea, demonstrates the agent in action, and presents the
   reasoning behind its trading strategy and results."*

> **Correction to the briefing that started this pivot.** It said the criteria
> were "Application of Technology, Presentation, Business Value and
> Originality" and that P&L was *not* described as deciding the result. That is
> lablab's generic four-criterion template; this event replaced it. **P&L is
> criterion one and it is the highlighted card.** Everything about how much risk
> to take rests on this, so it was worth reading the page rather than the summary.

## Prizes — both numbers in circulation are correct

| | |
|---|---|
| 1st | **$2,500** |
| 2nd | **$1,500** |
| 3rd | **$1,000** |
| Social engagement | **2 winning teams × $500** + 1-month Algo Trader Plus **per member** |
| **Total** | **$6,000** |

$5,000 is the main track; $6,000 is the pool including the social prize. The
"discrepancy" was two people quoting different subtotals.

## The social track is a second, separately winnable prize

> *"Share your progress publicly on social media — **X and LinkedIn** — while you
> build. Share your process, your reasoning, and your setbacks. Tag both
> lablab.ai and Alpaca in your posts. You can submit up to **5 social media post
> links** with your final project submission."*

Judged on *"both the quality of the content and the engagement it generates."*

Two teams win it. It is a **separate $500 + subscription**, it does not compete
with the main track, and it costs a few hours of writing against work we are
doing anyway. Start on day one — engagement accrues over the week and cannot be
back-filled on 3 Sep.

## Account requirements

- **Development:** *"Use any paper account you like during development."*
- **Judged submission:** *"create a brand-new Alpaca paper trading account
  dedicated to this hackathon. Projects run on an existing or reused account
  will not be eligible for judging."*
- **Starting balance must be set to $100,000.**
- **One-page write-up** covering *"your AI logic, risk gates, and Alpaca
  infrastructure implementation."*

Note what the third deliverable implies: **risk gates are a scored artefact.**
An account that blows up is not only a bad P&L — it contradicts the document we
are required to submit alongside it.

## Core requirements

- Autonomous AI trading agent on Alpaca's Trading API
- **Must** use Alpaca's MCP server **or** its CLI
- **All strategies must incorporate options trading**
- Teams: 1–6 people
- *"Submissions must be original and MIT-compliant."*
- Scale: the event page shows **2,236 registered participants**

## Market data — and what the free plan can actually do

From `alpaca.markets/data`:

| | Free | **Algo Trader Plus — $99/mo** |
|---|---|---|
| Options | **"Yes, indicative"** | **"Yes, real-time"** (OPRA) |
| Stocks via API | 15-minute delay | real-time |
| API rate limit | 200/min | unlimited |
| Websocket symbols | **30** | unlimited |

**MEASURED 2026-08-25 on `PA32Q5IW7TAS`, and the first draft of this section
was wrong.** It said the indicative feed made the minimum-detectable-move
computation "fiction". It does not. The free feed returned 1000 SPY contracts,
**100% with both a bid and an ask**, 46% with greeks, median relative spread
5.3%. The feed is not missing — it is **late**, by about fifteen minutes.

`alpha/data/chain.py` handles that explicitly: stale quotes are carried forward
with delta and gamma against a real-time underlying, a staleness penalty widens
the assumed execution price in proportion to the carry, missing greeks are
computed from Black-Scholes, and anything past ~25 minutes of *market-time*
staleness is refused rather than adjusted.

What it costs is real and is stated in the module: **the agent cannot trade
reactions.** It positions ahead of scheduled catalysts instead. Buy the $99 if
measured fill slippage exceeds ~15% of expected edge, or if we commit to the
Friday jobs-report trade. See `docs/HANDOFF.md` for the decision rule.

## Options on a paper account

- Multi-leg (Level 3) is **auto-approved on paper** — up to four legs; spreads,
  straddles, strangles, condors. No application; that is for live only.
- Order types: `market`, `limit`, `stop`, `stop_limit` (stop is single-leg only).
- `time_in_force` must be `day` or `gtc`; **`extended_hours` must be false** —
  options cannot be routed outside RTH. Enforced in `alpha/broker/alpaca.py`.
- ITM contracts auto-exercise at $0.01. Assignment is REST-poll only, no
  websocket event.

## Paper-fill realism — the line we do not cross

Alpaca documents that paper trading does **not** model market impact, latency
slippage, queue position, or order size against displayed NBBO quantity. A large
order in a thin option can therefore fill at a price nobody could have got.

We do not use this. Every order records the bid, ask and size seen at decision
time (enforced: `AlpacaPaper.submit()` refuses an order without a quote
snapshot). A P&L built on a simulator artefact fails criterion 1 the moment a
judge looks at the contracts, and it is worthless as evidence to bring home.
