# ROADMAP — P0 PROFIT RECOVERY / DECISION BRAIN (2026-08-27)

Supersedes the ordering in `ROADMAP_2026-08-26_STOP_BLEED.md`. Everything there
still stands; this decides what comes first.

## THE DOCTRINE, IN ONE LINE

```
WORLD -> CATALYST -> STATE DISTRIBUTION -> MARKET EXPECTATION -> DISAGREEMENT
      -> DIRECT EXPRESSION -> PROXY CHALLENGERS -> INSTRUMENT -> SIZING
      -> EXECUTION -> REGRET/OUTCOME -> CALIBRATION
```

**The system spends most of its intelligence before `DISAGREEMENT` and almost
none between `DISAGREEMENT` and `POSITION`.** That is the diagnosis, and it is
not an opinion — it is what 26 Aug measured. NVIDIA guided Q3 to $108.0bn against
$104.2bn, China-free; the stock rose ~6.8% against a ~5.4% implied move; the
sealed vector had ranked that guide #1 and flagged memory as the constrained node
hours before the filing confirmed a $160bn memory commitment. The books held
index straddles and a peer straddle on AMD.

The research was right. The capital did not know.

## RESULTS SCOREBOARD (27 Aug, 11:45 ET, read from the venue)

| | |
|---|---|
| best historical net strategy | none |
| best forward paper | dev −13.7% · exp1 −4.1% (both PRE_UNITS_FIX legacy books, manage-only) |
| independent selectors | unchanged |
| candidates tested / promoted | 0 / 0 |
| new actionable finding | the refusal guard would have blocked the one trade the research was right about |
| external execution drag | unmeasured this session |
| LLM spend | $0.00 |
| **RESULT IMPROVEMENT** | **NONE.** No strategy tested, no P&L moved. What moved is what the machine is *allowed* to do. |

The dev drawdown is **legacy damage, not a fresh post-fix result**: every losing
position was opened 25 Aug under the broken width/time arithmetic and nothing new
has been opened since. The corrected engine remains **prospectively unproven**.
That is a reason to test it, not a reason to feel better.

---

## DONE THIS SESSION

| item | what it now does |
|---|---|
| **evidence scoping** (`alpha/refuted.py`) | a refusal covers only the sample it was measured on. `LONG_VOL` is refusable; `long_call`/`long_put` are not, because neither the 0-for-8 nor the 290 relay legs contains a directional leg. `MEASURED_OWN_PRINT` holds one symbol. `UNMEASURED` records what nobody tested, so absence stays visible |
| **COMPETITION_ACCOUNT_GENESIS_v1** (`alpha/genesis.py`) | the judged account gets a birth certificate or nothing trades. Denylist keyed on the venue's `account_number`. Wired into `preflight` **and** `run_pass` |
| **CLAIM_EXPRESSION_MATRIX_v1** (`alpha/claims.py`) | a `direction` claim cannot see a sign-blind payoff at all — structural, before pricing, alongside the existing arithmetic fix |
| **HUMAN_THESIS_ARM_v1** (`alpha/human.py`) | a typed, falsifiable, prospective wire from a human view into the tournament. No broker import, no order verb |
| **PASSIVE_BETA_v2** (`alpha/benchmark.py`) | five states derived from the venue. `EXPIRED_UNFILLED` ≠ `UNSEEDED`. SUBMITTED may no longer read as SEEDED |
| **role→account truth** (`scripts/accounts.py`) | the mapping comes from the venue, not from a dashboard nickname |

1045 checks, venue blocked, all pass.

**Two review claims were wrong and are corrected here.** (1) There *is* an Alpaca
CLI and MCP implementation — `alpha/tooling.py`, all eight probe lines PASS, MCP
runs with the `trading` toolset withheld. (2) `AAT_TEST_MODE` is already
zero-egress: `getaddrinfo` is blocked alongside `connect`, so DNS does not leave
the machine. And `PA32Q5IW7TAS` is the **dev** role; "hackathon" is a UI nickname,
not a role.

---

## OVERNIGHT UPDATE (27 Aug, ~14:00 ET) — three P0 items closed, and the ordering changed

| item | status |
|---|---|
| **P0.1 `PNL_FORENSICS_v1`** | **DONE.** −$23,306 realised is **94.5% one structure**. NVDA cost $284; SPY+QQQ are 63%; slippage 3.2%. `scripts/pnl_forensics`, reconciles with the venue |
| **P0.2 `BELIEF_TO_POSITION_AUDIT_v1`** | **DONE.** `scripts/belief_to_position`. **0 of 6 proxies beat the source**; AMD −1.24% and MU −2.65% went the wrong way |
| **P0.6 `EXECUTION_REACHABILITY`** | **DONE.** `scripts/reachability`, in the suite. Found `shape.py` with zero importers and `must_close_by` as a docstring sentence |
| P0.3 `ALPHA_REGRET_LEDGER` | partial — `counterfactual.jsonl` marks alternatives; the **mandatory challenger set** is not enforced |
| P0.4 `DIRECT_FIRST` / `PROXY_PENALTY` / `CAUSAL_DISTANCE` | **evidence gathered, and it argues for LESS machinery, not more** — see below |
| **P0.5 `SANITY_SENTINELS`** | **DONE.** `alpha/sentinels.py`, wired into `run_pass`. **Four of five brains are BROKEN**, not one: relay 99.0%, narrative_dispersion 96.1%, options_attention 95.4%, vol_gap 93.1%; `event_move` (never executed) is the only balanced one. **Post-fix it says CANNOT_DETERMINE on 32–35 decisions — the arithmetic fix is NOT yet verified** |

### THE EVIDENCE CHANGED P0.4

The reviews asked for causal-distance scoring, proxy penalties and torque
estimation — a substantial modelling layer to decide *which* beneficiary to
trade. The one event where the causal chain was independently confirmed by the
primary document says something simpler and harsher:

**Buy the source.** NVDA +9.61%; every proxy lost to it; the two the graph most
strongly implied (AMD, MU) were **negative**. MU fell 2.65% on the day NVIDIA
disclosed $160bn of memory commitments — the exact prediction `NEEDS_GRAPH` had
made hours earlier from filed fundamentals.

A causal arrow that exists is not an edge with a sign you can spend. So P0.4
collapses from *"score causal distance and pick the best beneficiary"* to
**"the source is the default and a proxy must beat it on measured net payoff"** —
which is already how `runner.evaluate` enumerates, with shares competing beside
options. **One rule, not a scoring system.** The scoring system can come back
when a proxy has actually won something.

### AND A NEW P0.7, FROM THE SAME EVENT

**`INSTRUMENT_MATCHES_CLAIM` is worth more than any of the causal work.** On the
26 Aug print the call paid **+219%** and the straddle **+60.7%** — same name,
same entry, same event. Two thirds of the return was given away by owning the
absolute move when the view was about the sign. `alpha/claims.py` now refuses
that pairing structurally, and it is the highest-value guard added this session
because it is the one with a measured price tag.

---

## P0 — OPEN, IN ORDER

### P0.1 `PNL_FORENSICS_v1` — account for every dollar, in dollars
Decompose the two losing books by brain, underlying, structure, direction,
theta, vega/IV change, delta/gamma, spread, entry/exit timing, concentration,
**software/unit defect**, and market beta. A waterfall, not a narrative.

Dedupe by `alpaca_order_id` first — summing `pnl_usd_if_closed_now` over
`fills.jsonl` gives −$302,818 and is nonsense, because the auditor re-marks 22
orders hundreds of times.

*Blocked by nothing. This is the next thing to build.*

### P0.2 `BELIEF_TO_POSITION_AUDIT_v1` — reconstruct 26–27 Aug NVDA
What Murat believed, what the sealed vector believed, what the chain implied,
what was actually held, and **at which stage the information died**: prediction,
proxy selection, instrument selection, sizing, timing, or gating. Counterfactually
mark NVDA shares, an NVDA debit spread, an NVDA call, SMH, QQQ, AMD, MU and cash
from the same timestamp at executable costs.

*Needs the 27 Aug close. Runs tonight.*

### P0.3 `ALPHA_REGRET_LEDGER_v1` — make the road not taken measurable
`state/counterfactual.jsonl` already marks alternatives (561MB, 555,964 lines).
What it lacks is the **mandatory challenger set**: for every selected trade, the
direct underlying's shares, the market baseline, cash, the best causal
beneficiary, and the human arm — graded at T+1/T+3/expiry.

A sophisticated expression must beat the simplest expression of the same claim
after costs before complexity gets credit (`SIMPLEST_EXPRESSION_CHALLENGE`).
Shares are already enumerated beside options for a `direction` claim
(`runner.share_structure`); this makes the comparison a *record* rather than a
side effect.

### P0.4 `DIRECT_FIRST_v1` + `PROXY_PENALTY_v1` + `CAUSAL_DISTANCE_v1`
A causal edge is not a licence. `NVDA beats → AMD up` is two separate edges with
opposite signs: a positive `AI_DEMAND_BETA` and a potentially negative
`NVDA_COMPETITIVE_RESIDUAL`. On 26 Aug AMD rose ~1.8% against NVDA's ~6.8% — even
where the sign was right, **the torque was completely different**.

Every additional causal hop must earn its uncertainty with more expected torque,
and the information-producing security's own shares are a **mandatory control**,
not a candidate.

### P0.5 `SANITY_SENTINELS_v1` — generalise the 96.4%
A component automatically loses **new-position authority** (never manage/exit
authority) when: a mature liquid market is classified one-sidedly cheap or
expensive at absurd frequency; a brain's forecast/implied ratio drifts past
calibration; a book loses heavily in a regime it claims positive exposure to; or
a policy has no reachable execution caller.

`vol_gap` is already quarantined by hand. This makes the quarantine a rule.

**Quarantine should become capability-scoped, not binary**: `may_forecast_direction`
/ `may_forecast_magnitude` / `may_select_expression` / `may_size` / `may_execute`.
One broken capability should not kill the useful parts of a module.

### P0.6 `EXECUTION_REACHABILITY_AUDIT` — `/graphify`
Find every object whose name implies `gate`, `limit`, `risk`, `kill`, `refuse`,
`contract`, `invariant`, `policy`, `quarantine`, `refuted` — and **prove a call
path to the real runner**. `book_limits.py` described itself as "implemented,
tested, and called by NOTHING" for days. That class of failure must be
machine-detectable, not review-detectable.

Then invert it: **every execution refusal must point to an evidence record**
(`EVIDENCE_TO_GUARD_REGISTRY_v1`), with `finding_id`, scope, claim type,
instrument, universe, sample, net result, status, reopening condition, guard and
guard test. The rewrite of `refuted.py` is the shape; the registry is the rule.

---

## P1 — AFTER THE JUDGED ACCOUNT IS LIVE AND GREEN

`EVENT_DOMINANCE_v1` (one dated catalyst may rationally dominate the opportunity
set when *independent* evidence classes converge — five LLMs repeating one Reuters
article is one source, not five) · `CONVEX_CONVICTION_SIZING_v1` (sizing that
actually separates an ordinary idea from an exceptional one, on **calibrated**
confidence, never an LLM's self-report) · `THESIS_VECTOR_v1` (direction /
magnitude / volatility / skew / horizon as separate fields, fused at the
expression layer rather than averaged — "up, and the chain overprices the move"
is coherent and points at shares or a capped spread) · `EVENT_SCENARIO_MARKET_v1`
· `HUMAN_CONVERGENCE_v1` (engine analyses and freezes *before* the human view is
revealed) · `MURAT_POLICY_DISTILLATION_v1` (the mirror portfolio is the only
profitable arm on record — study the archetype, do not clone the trades).

**Concentration is not a pathology.** Bad concentration is many positions that
secretly depend on one factor — that is what `effective N by risk` measures, and
dev ran at N 1.49. Good concentration is one unusually strong, well-timed,
differentiated thesis getting more capital because nothing else in the opportunity
set is close. The engine currently cannot tell those apart, and P1 is where it
learns to.

## P2 — RESEARCH GYM, and no router before it

Four providers are live and deliberately **not** a router. Benchmark them on
**our own corpses** — option expected-move units, calendar/session mismatch,
simple vs log returns, corporate actions, PIT leakage, the one-sided 96%-cheap
failure, a dead process read as a quiet market, role-filtered reconciliation, a
test child escaping to the network, POST before local intent, famous-event
leakage — not on MMLU. Choose by research error rate, structured validity,
latency and cost. Routing comes after the Gym says who wins which job.

**No LLM gets trading authority during the competition because an integration
works.** Shadow first, measured promotion later.
