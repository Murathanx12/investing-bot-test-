# HANDOFF — read this first

**Written 2026-08-25.** This repo is a seven-day competition derivative of the
Aegis-Finance research project. Source provenance: `aegis-finance@44c8352`.

---

## COMPETITION SCOREBOARD

Every handoff from here opens with this block, filled in, before any engineering
count. Engineering that moves none of these lines says so in its first
paragraph.

```
competition account equity      NOT YET CREATED (create at kickoff, 28 Aug 15:00 UTC)
competition return              n/a
realized / unrealized P&L       n/a
best live strategy              none — nothing has traded
best shadow strategy            none — shadow arena not built
active independent brains       0 of 5 planned
options trades / win-loss       0 / 0-0
max drawdown                    n/a
unused buying power             n/a
LLM calls / spend               0 / $0
execution failures              0
service uptime                  not deployed
submission readiness            infrastructure only
COMPETITION RESULT IMPROVEMENT  NONE — this session laid foundations and traded nothing
```

---

## What this session established, and what it corrected

**Read `docs/RULES_SNAPSHOT_2026-08-25.md` before anything else.** It was pulled
from the live event page, and it corrects the briefing that started this pivot in
two ways that change the plan:

1. **P&L Performance is judging criterion #1** and is the visually highlighted
   card on the page. The briefing said P&L was *not* described as deciding the
   result and quoted lablab's generic four-criterion template. That template was
   replaced for this event. Risk appetite follows from this, so it mattered.
2. **The deadline is 4 Sep at 11:00 ET — ninety minutes after the open, not the
   close.** The window is **exactly 5.0 equity sessions** plus two crypto-only
   weekend days. The August jobs report (4 Sep, 08:30 ET) is the last catalyst
   and it is a 90-minute trade. Every position must be closable by ~10:45 ET.

Also newly established: a **separate social-engagement prize** (2 teams × $500 +
Algo Trader Plus per member, up to 5 post links submitted, judged on quality
*and* engagement). It does not compete with the main track and engagement cannot
be back-filled — **start posting on day one.**

## Answering the question that was asked

> *"I will create a new paper account — do I have to do it when the competition
> starts or now?"*

**Two accounts, and the timing differs.**

- **Development account: create it NOW.** The rules say explicitly *"Use any
  paper account you like during development."* Every rehearsal, every test
  order, every mistake goes here. Set `AAT_ACCOUNT_ROLE=dev`.
- **Competition account: create it at kickoff, 28 Aug 15:00 UTC**, and not
  before. The rule is *"create a brand-new Alpaca paper trading account
  dedicated to this hackathon; projects run on an existing or reused account
  will not be eligible."* There is **no upside** to creating it early and a real
  downside: an account with a creation date and any activity before the window
  invites exactly the argument the rule is written to make. Set its starting
  balance to exactly **$100,000**, generate fresh keys, put them in
  `AAT_COMPETITION_KEY_ID` / `AAT_COMPETITION_SECRET_KEY`, and **never place a
  test order on it.** Run `python -m scripts.preflight` against it once,
  immediately — it checks paper status, the $100k, and freshness (zero orders,
  zero positions), and freshness is the one property that cannot be repaired
  afterwards, because resetting the account is itself a reuse.

## What exists in this repo

| File | What it is |
|---|---|
| `alpha/config.py` | Credentials, endpoints, three refusals |
| `alpha/broker/alpaca.py` | The only path to Alpaca: paper-only, idempotent, quote-recording |
| `alpha/engine/shape.py` | **Differentiator 1** — decile shape → instrument |
| `alpha/engine/sizing.py` | **Differentiator 2** — minimum detectable move + rank-objective sizing |
| `alpha/ledger.py` | Hash-chained append-only decision record, including refusals |
| `scripts/preflight.py` | Proves the account is the one we think it is |
| `tests_smoke.py` | 21 checks, no keys, no network. `python tests_smoke.py` |
| `docs/RULES_SNAPSHOT_2026-08-25.md` | The rules, verbatim, with the corrections |
| `docs/STRATEGY.md` | The thesis, the competitive read, the catalyst calendar |
| `docs/COMPETITOR_WATCH.md` | Who is building what |

All 21 smoke checks pass. Nothing has touched a broker.

### Three safety refusals you must not "fix"

1. **This repo never reads `ALPACA_API_KEY_ID`.** Those variables exist on the
   dev machine and are attached to a **live** account — a smoke test in the
   parent project once called `sync()` against them and placed **twelve real
   sell orders**. `config.credentials()` refuses and names the variable it is
   protecting you from. Everything here is `AAT_*`.
2. **The live host is not reachable.** `api.alpaca.markets` is absent from the
   allowlist and there is no flag that adds it.
3. **`AAT_ACCOUNT_ROLE` has no default.** An unset variable selecting the judged
   account is the one mistake with no undo.

## Next session — 26 August. Build the loop.

Priority order. Items 1–3 are the session; 4–6 if it goes well.

1. **Buy Algo Trader Plus ($99/mo) and prove the OPRA feed.** On the free plan
   the options feed is *indicative*, which makes the minimum-detectable-move
   calculation — the core of the sizer — fiction. `scripts/preflight.py` already
   reports which feed is live. This is the highest-value $99 of the week.
2. **`alpha/data/chain.py`** — chain snapshot → liquidity filter (spread as a
   fraction of max loss, open interest, quote age) → the handful of tradeable
   contracts. Everything downstream consumes this, and the liquidity filter is
   what keeps us on the honest side of the paper-fill line.
3. **`alpha/engine/structures.py`** — enumerate long call, debit spread, long
   straddle/strangle, defined-risk credit spread and iron condor from a real
   chain, each returning a `sizing.Structure` with `max_loss` and
   `breakeven_move` computed at the **ask**, never the mid. Then the first real
   end-to-end run against the dev account: chain → structure → MDM → size →
   ledger → order → fill.
4. **Catalyst radar** over the calendar in `STRATEGY.md`, with primary-source
   re-verification of every date.
5. **MCP + CLI.** Both are competition requirements and each has a natural role:
   the **CLI** as a deterministic JSON execution/audit path, **MCP** as the
   natural-language "why did you make this trade?" surface for the demo. Do not
   route the live tick loop through MCP — use `alpaca-py` for that.
6. **First social post.** Build-in-public, tagging lablab.ai and Alpaca. The
   shape-vs-instrument idea is the post; it is genuinely interesting and it is
   ours.

### Do NOT do these

- **Do not build a bull-agent / bear-agent / risk-agent debate.** A competitor
  already is, the field will be full of them, and the parent project measured
  that specialist personas are mostly correlated forecasters in costume.
- **Do not fold new mechanisms into one composite score.** The parent project's
  diagnosed bottleneck is exactly this: ten books that all select on one signal
  because everything was averaged into a composite whose coverage histogram was
  `{"1": 206, "6": 1}`. A new mechanism arrives as its own brain with its own
  shadow book. And a composite must always be checked against its own best
  component — `rev_dispersion` alone lifts +7.6 where the composite containing
  it lifts +2.3.
- **Do not exploit the paper simulator.** Alpaca documents that it models
  neither market impact nor order size against displayed NBBO quantity. Large
  orders in thin options would produce a fake number that fails criterion 1 the
  moment a judge reads the contracts, and it would poison the corpus we want to
  bring home.
- **Do not continue the ordinary Aegis roadmap.** No WRDS pulls, no MDE work, no
  new guardrails. That project's `main` stays where it is.

## The two ideas the whole submission rests on

If a future session keeps only two things from this repo, keep these.

**Shape decides the instrument.** A TAIL signal *is* an option — buy convexity,
narrow. A STEP signal is a stock book — buy breadth, wide; there is no tail to
pay a premium for. `mom_12_1` and `rev_dispersion` are tails; `profit_roe` is a
plateau and the agent **refuses** to buy calls on it. That refusal is the
strongest thing we can put in front of a judge, because it is a decision no
prompt-based agent would ever make.

**Ask whether the trade can resolve before asking whether it wins.** A structure
bought at the ask and sold at the bid breaks even at a specific underlying move
— the minimum detectable move. Unless our forecast puts materially more
probability beyond it than the chain does, we agree with the market and would be
paying to say so. It is the parent project's `MDE = z·te/√T` discipline
transplanted into a place where the market quotes the denominator for us.

## Provenance and licence

`AEGIS_SOURCE_COMMIT=44c8352`. This repo carries **no** secrets, no WRDS/CRSP or
IBES data, no OptionMetrics, and no generated ledgers from the parent project.
The shape priors are *summary statistics* of measurements made there, quoted as
numbers in source, which is not redistribution of licensed data. Submissions
must be MIT-compliant, and the repo is MIT.
