# ROADMAP — INFORMATION FIRST (logged 2026-08-26, day session 12)

> **Don't ask the market for more patterns until we have extracted more
> information from the world.**

Two review documents arrived on 26 Aug and this file is where they are logged so
they are not lost when the session ends. They are different in kind and must not
be interleaved in execution:

- **Doc A — the continuation brief (Aegis / competition).** Twelve items, most
  of them deadline-bound, several of them expiring TONIGHT at the NVDA print.
- **Doc B — the Optimus architecture review (NVIDIA / NeMo / Hugging Face).**
  A model-independent cognitive-OS design for the *parent* brain. Almost none of
  it is competition work; logging it here is the point, not scheduling it here.

**The competition deadline is 2026-09-04 11:00 ET.** Everything in Doc B except
one item is therefore AFTER it. Saying that plainly is the whole value of this
file — the failure mode is a session that spends the last nine days building a
cognitive operating system and submits a book with no stop at the venue.

---

## 0. The sequencing decision, stated once

| Window | What runs | Why |
|---|---|---|
| **26 Aug, before 16:20 ET** | Doc A items 1-3 (NVDA pre-print freeze) | the event happens once; a state vector written after the print is worthless |
| **26-27 Aug** | Doc A item 4 (condor grade), audit patches 1-3 | patches must be green before the competition account exists at 28 Aug 15:00 UTC |
| **28 Aug - 4 Sep** | Doc A items 5-9 (bounce battery, STALE_TARGET, registry, scout, spend rule) | research that can still change what the book trades |
| **After 4 Sep** | Doc A items 10-12, all of Doc B | the parent brain, the research gym, embodiment |

The one Doc B item that starts now is **item 10** — the `EmbeddingProvider`
prototype in the *Optimus* repo — and it starts now only because it touches
neither `alpha/` nor the loops nor Aegis night, and can be done in dead time.

---

## 1. Doc A — the continuation brief, as tracked work

Status key: `DONE` - `IN PROGRESS` - `QUEUED` - `DEFERRED`

### A1. `NVDA_EARNINGS_STATE_VECTOR_v1` — freeze before the print — **DONE (sealed 11:50 UTC, `a1634ef3...`)**

Not a `beat/miss` scalar. A typed vector of the twelve fields the brief names:
`revenue_surprise` - `datacenter_surprise` - `hyperscale_growth` -
`ACIE_growth` - `gross_margin_surprise` - `Rubin_timing_change` -
`Blackwell_demand` - `HBM_cost_pressure` - `customer_financing_quality` -
`China_optional_revenue` - `custom_silicon_competition` -
`future_capacity_constraint`.

Frozen with only pre-print information: consensus vintage **with its as-of
stamp**, NVIDIA's own Q2 guide, the live option-implied move measured from our
own chain (not quoted from a news article), and the supply-chain evidence set.

**The information ranking is part of the preregistration**, because it is the
falsifiable claim: `Q3 guide > gross margin > Rubin ramp > customer financing >
Data Center growth > China > Q2 headline EPS`. If tomorrow's move is explained
by EPS and not by the guide, that ranking was wrong and we will have said so
first.

**Do not modify `PH:NVDA:2026-08-27:b29d506d`.** It is the old brain's record
and it is the control. The new vector is a supplementary, separately hashed
preregistration so the two can be graded against the same outcome.

### A2. `NVDA_SHOCK_PROPAGATION_v1` — freeze before the print — **DONE (sealed `4d3ad6fa...`), AND AMENDED**

> **AMENDMENT, same day.** The power check says this graph cannot resolve an
> underreaction on ONE event: per-node MDE 5.9%-24.0% against a 5.1% implied
> move. It is a REPEATED-measurement instrument, not a next-day trade
> generator, and must not be presented as one.
> `docs/FINDING_2026-08-26_THE_SHOCK_GRAPH_CANNOT_RESOLVE_ONE_EVENT.md`.

A causal graph frozen with pre-print prices, each edge declaring **sign, lag,
exposure estimate and the observable intermediate outcome** — not a story.

```
NVDA demand ──► HBM ──► advanced packaging ──► optical ──► server ODM
                                                  └──► power ──► cooling ──► grid
memory inflation ──► server BOM ──► customer AI ROI ──► capex affordability
                                                  └──► custom silicon substitution
```

Tomorrow's question is **not** "did NVDA move". It is:
`large fundamental exposure x small price response` — which connected name moved
less than its exposure to the realised state vector implies.

That is the opposite of ticker-first investing, and it is the only part of
tonight that could still produce a trade, because **the competition account does
not exist for tonight's print** (kickoff 28 Aug 15:00 UTC). NVDA tonight is a
CALIBRATION EVENT. The 28 Aug opportunity, if any, is the second-order laggard.

### A3. Parse the packet before reading the reaction — **BUILT; runs tonight**

Fill the state vector from the release itself **before** revealing the
after-hours print. Price contaminates interpretation; the ordering is the guard.
Mechanically: the grader refuses to display the move until the vector file has a
`sealed_at` newer than the release timestamp.

### A4. Grade the condors as planned — **QUEUED (after 27 Aug close)**

`event_grade NVDA --post --resolve PH:NVDA:2026-08-27:b29d506d`, then
IREN/AFRM/S/RBRK on the 28th. Expected move vs realised, vol crush, direction,
gamma/vega/theta, spreads, **and whether the P&L came from the mechanism we
claimed** — a condor that made money because direction went our way did not
validate a variance view.

### A5. `NON_PRINT_BOUNCE_v1` through the full battery — **QUEUED**

Session 11's new candidate: a non-print >=5% loser bounces +0.37%/3d, +2.1%/21d
over 46k events, where a print loser does not (diff t 5.0).

It gets the **exact** battery that killed wide PEAD, no shortcuts:
raw simple returns - realistic next-open execution - intraday path (not close
basis — agent 7 showed the close basis was a lower bound) - slippage -
sector/size controls - year and quarter stability - microcap exclusion -
liquidity buckets. **No execution is built until it survives.** The bar cache is
already on disk (`state/night_shadow/bars_daily.json.gz`, 3,068 names).

### A6. `STALE_TARGET_v1` — with target AGE as the centre — **QUEUED**

Session 11's provenance v2 found the document rule inside Murat's list: high
analyst upside x deep drawdown returned +5% to +51% excess at 63d, while high
vol *without* upside lost 26-55%. n=52 on one date — a shape, not a result.

The brief's correction is the useful part: the interesting variable is **not**
analyst upside, it is `target_gap x target_age x revision_direction x drawdown x
catalyst`. A stale target that simply has not been cut yet is the opposite of
fresh conviction and looks identical in any snapshot. Requires **point-in-time
IBES target vintages** — a snapshot of today's targets cannot answer this and
must not be used to pretend it did.

### A7. `DATA_SOURCE_REGISTRY_v0` — **DONE v0 (`alpha/sources/registry.py`)**

Every source carries: `source` - `source_type` - `metric` - `entity` -
`frequency` - `publication_lag` - `observed_at` - `effective_period` -
`revision_policy` - `point_in_time_available` - `license` - `cost` -
`reliability` - `independence_group` - `parser` - `failure_rate`.

Two rules that are the reason the registry exists at all:

1. **`independence_group` is load-bearing.** Reuters restating a company press
   release is NOT a second confirmation. Both carry the issuer's group.
2. **Raw observations are append-only.** Never overwrite yesterday's number with
   today's revision — that is precisely how point-in-time backtesting dies, and
   it dies silently.

Seeded with only what the NVDA event and Trade Pulse need. Not the internet.

### A8. `QUESTION_DRIVEN_DATA_SCOUT_v0` — shadow only — **QUEUED**

Input is a falsifiable question ("Is AI infrastructure demand accelerating?"),
not a ticker. Output is candidate datasets ranked by expected information gain
per dollar. No trading authority, ever.

This is the mechanised form of what the brief did by hand: TSMC monthly revenue,
Foxconn monthly server mix, hyperscaler capex and backlog, HBM contract terms,
custom-silicon awards, and ODM production schedules are all answers to
"is demand accelerating" that do not come from a price series.

### A9. Spend rule: `WHY_THIS_CALL_CAN_CHANGE_A_DECISION` — **DONE (`alpha/spend.py`)**

A paid LLM call must carry a short field naming the decision it can change. If
the field cannot be filled, the call is refused. Night lab already ran a whole
session at $0.00; this makes that the default rather than an achievement.

### A10. Optimus `EmbeddingProvider` prototype — **STARTS NOW, separate repo**

See section 2. Restrictions: behind the existing retriever, no replacement of
canonical Markdown, no production-memory migration, no Aegis execution coupling,
benchmarked against the existing retrieval probes before promotion.

### A11. `AEGIS_RESEARCH_GYM_v1` — design only — **DEFERRED to after 4 Sep**

Historical false discoveries and negative results become **episodes**. An agent
is given the information available before each failed experiment and scored on:
corpse rediscovery - noticing the known confound - requesting the correct
placebo - using simple rather than log returns - separating factor exposure from
alpha - recognising insufficient power - **knowing when to abstain**.

Build the evaluation environment first. Fine-tune nothing. Aegis already has the
corpus most autonomous-research setups lack — `NEGATIVE_RESULTS`, the postmortem
registry, and roughly five months of receipts.

### A12. `NIGHT_CONFLICT_GUARD` stays sacred — **DONE, keep it that way**

`scripts/night_guard.py` + `tests_smoke_night.py`. Night writes research
artefacts and shadow state only. No runner/admission/broker/book mutation, no
loop restart, no shared execution-state writes. Day promotes.

---

## 1b. The execution patches that outrank all of the above

From `docs/night/2026-08-26_EXECUTION_AUDIT.md`. These are not research; they are
the difference between a judged book and a bled one, and **they must be green
before the competition account exists at 28 Aug 15:00 UTC**.

1. **DONE** (`alpha/protect.py`). ~~No stop at the venue.~~ Positions were naked
   from 16:00 to the first `manage` pass. Post-fill GTC `stop` sized to `filled_qty`, id from
   `decision_id + ":stop"`, recorded on the row. The "3% stop" the book was
   charged for was never a stop — it was a charge.
2. **DONE** (`alpha/daybreak.py`). ~~No daily-loss latch, and the tournament
   multiplier sizes UP on losses~~
   (1.6-2.0x when behind). Read `account.last_equity`, refuse entries at -3%,
   clamp the multiplier to <=1.0 when `ret < 0`.
3. **DONE** (`runner.open_order_underlyings`). ~~Unfilled entry orders are
   invisible to the one-position-per-symbol guard.~~
   Merge `client.orders(status="open")` into `held`.

4-7 (exit sampling starved by the entry pass; partial short-shares read as
UNBOUNDED and halts the book; `--role` vs `AAT_ACCOUNT_ROLE` silent
disagreement; expired/partial orders never terminal in the ledger) are queued
behind them.

---

## 2. Doc B — Optimus as a model-independent cognitive OS

**The thesis, and it is right:** Optimus should be the persistent executive
brain; an LLM is one replaceable cognitive faculty beside retrieval, vision,
speech, and Aegis. That is already the repo's architecture — `core.llm` puts
model calls behind a `Completer` seam, Markdown is canonical, SQLite is derived,
and `core/router.py` is still deliberately a placeholder. Nothing here proposes
redesigning Optimus around NVIDIA; it proposes NVIDIA models as interchangeable
faculties inside it.

```
                          CLOUD FRONTIER LLM  (hard reasoning only)
                                   ▲ escalation
Sensors / Voice ──► Perception ──► OPTIMUS EXECUTIVE BRAIN
                                   ├ identity / dispositions
                                   ├ episodic - project - semantic memory
                                   ├ world state - causal graph
                                   ├ planner
                                   ├ model router
                                   └ tool / skill router
                    ┌──────────────┼──────────────┐
                  AEGIS      CODE/RESEARCH      ROBOT
              (measurement)   (agents)     (Cosmos/GR00T/ROS)
                    └──────────────┴──────────────┘
                                   ▼
                         result ──► memory distillation
```

### 2a. Build order (post-competition, in this order)

1. **`EmbeddingProvider` + Nemotron-3-Embed-1B as a *derived* index.** Hybrid,
   never a replacement: lexical/domain retrieval union semantic retrieval ->
   domain and tier filtering -> optional rerank -> provenance verification ->
   abstention threshold -> context package. **A dense vector must never become a
   fact.** `query.py` already says the relevance floor must be recalibrated
   whenever the scoring regime changes — adding embeddings IS a scoring-regime
   change, so the recalibration is mandatory, not optional.
2. **`OpenAICompatibleCompleter`** so vLLM / SGLang / llama.cpp / NIM plug into
   the same seam as Anthropic. No new dependency in `core/`.
3. **Router: deterministic first.** Obvious calculation -> Python; explicit
   memory request -> memory; explicit Aegis question -> Aegis; robot command ->
   planner; code task -> coding env. Only genuinely ambiguous requests reach a
   classifier, and the classifier is a small local model (Nemotron 3 Nano 4B Q4),
   not a frontier call. **Routing has no side effects** — it decides who thinks;
   it does not write memory, trade, or move anything.
4. **Model registry with MEASURED capability/cost/latency**, not hard-coded
   names. Twenty real Optimus bugs and twenty real Aegis bugs as the benchmark:
   completion - tests passed - regressions - tokens - wall clock - cost - tool
   calls - invalid assumptions - human corrections. Then routing is empirical
   rather than an opinion.
5. **MCP as the boundary.** NeMo Agent Toolkit (or anything else) wraps Optimus
   as an MCP client; Optimus never becomes a NeMo application. NVIDIA can change
   its agent stack, LangGraph can vanish, the frontier model can change — the
   memory stays ours. Note the packaging has already moved (`nvidia-nat` / `nat`
   CLI, and newer work to `nemo-agents-spec-v1`); take the architecture from the
   2025 tutorials, never the `aiq` scaffolding verbatim.
6. **Nemotron Parse 2.0 as a document ingest adapter.** PDF/slide/chart/scan ->
   structured Markdown + tables + coordinates -> claims + provenance +
   embeddings. Ranked ahead of any additional agent persona: expanding what the
   brain can accurately READ compounds harder than another voice in the room.
   Feeds Aegis directly (investor decks, annual reports, scanned tables).
7. **Correction/failure log -> evaluation corpus.**
8. **Aegis autonomous-research worker, extremely restricted permissions.**
9. **`optimus-embodied`** — voice, world-state schema, ROS bridge, simulation,
   then GR00T/Cosmos. Not before.

### 2b. Model shortlist (roles, not enthusiasm)

| Function | Model | Note |
|---|---|---|
| semantic memory | Nemotron-3-Embed-1B | ~2.3 GB, 34 languages; **first download** |
| document ingest | Nemotron Parse 2.0 | <1B; layout/tables/charts/reading order |
| cheap local router | Nemotron 3 Nano 4B (Q4 GGUF) | llama.cpp; always-on |
| tool execution / subagents | Nemotron 3.5 Lightning 30B-A3B | ~3B active/token |
| autonomous coding | Qwen3-Coder-30B-A3B | 3.3B active, 256K ctx |
| rerank | llama-nemotron-rerank-1b-v2 | **only once the corpus justifies it** |
| speech in | Parakeet TDT 0.6B v3 | 714 MB Q8 GGUF |
| speech (later) | NemotronLabs VoiceChat 11B | full duplex; ~44 GB checkpoint |
| world model | Cosmos 3 Edge 4B | robot only |
| robot policy | GR00T N1.7 3B | robot only |

**Deliberately NOT on the list:** any "finance LLM" asked what goes up tomorrow.
That buys everyone else's model plus everyone else's information. The local
models exist to eliminate expensive cognitive labour — scan 10,000 headlines,
retrieve 200 filings, structure them into events, run 30 cheap experiments — so
that only the hard 1-5% reaches a frontier model.

### 2c. Model admission process (non-negotiable)

`LICENSE_CHECK -> REVISION_PIN -> SAFETENSORS_ONLY -> NO_REMOTE_CODE unless
audited -> isolated container -> benchmark -> capability registration`

Never `trust_remote_code=True` on an unaudited repo; prefer `safetensors`; pin a
reviewed revision. A model that beats the shortlist on 40 real tasks gets the
job regardless of who published it. **The benchmark decides, not the brand.**

### 2d. Where this rejoins Aegis

The LLM result Aegis has already demonstrated is narrow and real: direct stock
selection showed nothing, multiple specialist personas showed nothing, but
**identifying economic relationships absent from a correlation matrix** was a
clean positive architecture result. So the division of labour is:

- the **LLM creates possibility space** (candidate causal edges),
- **Optimus maintains belief state and memory** (the causal hypothesis graph),
- **Aegis measures and falsifies** (is it priced, is it measurable, what leads
  what, what horizon, what falsifies it, is there variation, what magnitude,
  does a placebo kill it, did we already test it),
- **reality supplies reward.**

`NVDA_SHOCK_PROPAGATION_v1` (A2) is the first instance of exactly this loop, and
it runs tonight.

---

## 3. What this roadmap refuses

- **No NVIDIA/NeMo work before 4 Sep** beyond the one embedding prototype.
- **No robotics anything** until Optimus is a cognitive OS worth embodying.
- **No fine-tuning** before an evaluation environment exists to fine-tune against.
- **No vector database replacing the existing retriever.** Semantic retrieval
  goes UNDERNEATH it; the domain scoping, tombstones, provenance and abstention
  that were expensive to build stay in charge.
- **No source ranked by how convenient it is.** Primary sources first: filings
  and IR -> government/exchange/customs -> audited industry data -> wire services
  -> other media -> social. And a restatement is never a confirmation.

---

## 4. Review of 2026-08-26 (second pass) — assessed, and what was adopted

The review is **largely valid**. Its five-finding summary matches the receipts,
its ranking of the project's best results is better than the one this repo had
been using, and its central diagnosis is correct and uncomfortable:

> Aegis is much better at proving that something should not be traded than at
> continuously producing a portfolio of high-expected-return trades.

Adopted immediately (this session):

- **A5 run.** `NON_PRINT_BOUNCE_v1` went through the battery and is
  **FAILED_VARIANT** — the bounce is beta plus convexity, and 35 corporate-action
  rows out of 46,361 carried 81% of the simple return.
  `docs/FINDING_2026-08-26_NON_PRINT_BOUNCE_IS_BETA_AND_CONVEXITY.md`.
- **`RESEARCH_ALPHA_BUDGET` built** (`alpha/alpha_budget.py`), motivated by a
  live example from that battery rather than in the abstract.
- **Audit defects 5 and 6 closed**; 4 and 7 assessed below.

### 4a. The one correction the review asked for

It asked for the exact distinction between the *stock reaction magnitude* and
the *minimum detectable residual edge*, and it was right that the handoff
compressed this. **There is no contradiction, but the handoff's phrasing was
wrong and is withdrawn.**

- The **implied move (5.1%)** is the expected size of NVDA's OWN move.
- The **MDE (3.8% on the capacity edge)** is the smallest *abnormal* return —
  the part of a node's move NOT explained by its loading on NVDA and SMH — that
  one event can resolve at 80% power.

These are different quantities and comparing them, as the handoff did, is a
category error. The correct comparison is MDE against the *plausible size of an
underreaction*. Concretely, the capacity group's mean NVDA-beta is 0.734, so on
a +5% NVDA move its expected move is +3.67%; clearing a 3.8% MDE requires the
group to land at **≤ −0.13% or ≥ +7.47%**.

So the precise verdict, replacing "nothing is resolvable":

> **Only a near-total non-response is resolvable on one event.** An ordinary
> partial underreaction of 1–2% — the interesting case — is not. The instrument
> needs ~4 comparable events on the capacity edge and more elsewhere.

### 4b. Where the review is right and it changes the plan

1. **Causal edges accumulate across events.** NVDA is observation #1, not a
   verdict. Reuse edge ids across AMD, AVGO, hyperscaler capex, Foxconn monthly,
   TSMC sales and supplier results. This is the correct reading of the power
   result and it is now the design, not a consolation.
2. **The two projects must converge.** The strongest evidence (momentum tail,
   revision dispersion tail, profitability step, over decades and broad
   universes) is disconnected from a paper system trading short-dated options on
   SPY/QQQ/NVDA/TSLA. That is a real structural mismatch and naming it is worth
   more than another strategy.
3. **Marginal Alpha Contribution over standalone Sharpe.** A sleeve earns capital
   by improving the portfolio *given what every other sleeve already knows*. This
   is the direct answer to the diagnosed bottleneck — ten books selecting on one
   signal — and it is the right principle to take from Numerai.
4. **LLM large-cap bias is an architecture problem, not a prompting problem.**
   We have our own evidence, which is stronger than any citation: every arena
   book is a mega-cap, and the first whole-market scan returned BJ/OSIS/HOV —
   none of the old fifteen. Ticker-blind reasoning already exists in
   `alpha/state_change.py`; the missing half is **coverage normalisation**, and
   the review is right that blinding alone does not fix it. Evidence *quantity*
   must never become conviction.
5. **The audit-first methodology may be the most defensible contribution.**
   Recording how much apparent alpha dies at each audit layer is nearly free
   now, because the layers already exist and each kill is already written down.

### 4c. Where I would push back

- **The 24-idea table is too many, and the review says so itself before listing
  them.** They are logged in §5 below, unscheduled. Roughly half need data we do
  not have (patents, procurement, grid queues, job postings) and are
  post-competition by necessity, not by preference.
- **The citations were not verified.** Several point to venues I cannot check
  from here, and the underlying claims are well-supported by our own receipts
  anyway. Nothing in this roadmap depends on them.
- **`ANALYST_STALENESS_v2` should stay v1-shaped until the data exists.** The
  interaction `target_gap × target_age × revision_direction × drawdown ×
  catalyst` is five-way on n=52 from one date. That is not an underpowered
  test, it is an unfittable one. Get point-in-time IBES target vintages first;
  until then the honest version is two-way at most, and every extra interaction
  is a cell the alpha budget will charge for.

### 4d. Audit defects 4 and 7 — the explicit statement the review asked for

- **Defect 4 (exit sampling starved by the entry pass): CAN still affect the
  competition account.** Patch 1 removed it for SHARE positions, which now carry
  a venue-side GTC stop. It remains live for OPTION structures, which have no
  venue stop and are closed only when `exits.manage` runs — every 5 minutes at
  best, and the entry pass may hold the loop for up to 1500s. **Not closed.**
- **Defect 7 (orders never terminal in the ledger): CANNOT affect competition
  execution.** It corrupts grading and recovery scoring — `recovery.live_scores`
  can demote a brain on a trade that never opened — but no order, size or exit
  depends on it. Deferred with that stated.

---

## 5. The idea backlog — LOGGED, NOT SCHEDULED

Twenty-four hypotheses arrived with the second review. They are recorded here so
none is lost, and **deliberately not prioritised as a block**: the review's own
first instruction was "I would not add 30 more items equally."

Triaged by the only thing that decides what can run before 4 Sep — **do we have
the data today?**

### Runnable now (bars, SEC cache, chain, Finnhub already on disk)

| id | hypothesis | note |
|---|---|---|
| `SURPRISE_TO_ATTENTION_RATIO_v1` | high economic surprise / low attention beats raw surprise | the anti-mainstream signal in its cheapest form; the placebo rows already carry attention proxies |
| `LATENT_EVENT_CLUSTER_v1` | seemingly different tickers are one causal trade | directly improves the node cap, which today keys on a declared theme string |
| `PRICE_WITHOUT_CAUSE_v1` | an unexplained move triggers a reverse causal search | `daily_autopsy` already found 20/30 movers had no visible precursor — that IS this dataset |
| `EDGE_DECAY_v1` | deterioration is detectable before statistical death | needs only the forward paper record we already keep |
| `FAME_BIAS_v1` | the recommendation changes when the ticker is revealed | ticker-blind triage exists in `alpha/state_change.py`; this is the A/B on top |
| `ANALYST_STALENESS_v2` | target gap works only at certain target age | **v1-shaped until PIT vintages exist** — see §4c |

### Needs one new collector (feasible, probably post-competition)

`COVERAGE_GAP_v1` · `EVIDENCE_DENSITY_NEUTRAL_v1` · `GUIDANCE_LANGUAGE_DELTA_v1`
· `FOOTNOTE_DRIFT_v1` · `FORM4_CLUSTER_v1` · `ATM_SHADOW_v1` ·
`CUSTOMER_SUPPLIER_CLOCK_v1` · `MANAGEMENT_TRUTH_SCORE_v1` ·
`ALPHA_CROWDING_v1` · `EXPECTATION_DISAGREEMENT_v1`

### Needs data we do not have at all (post-competition, by necessity)

`PROCUREMENT_PULSE_v1` · `GRID_QUEUE_v1` · `JOB_FUNCTION_DELTA_v1` ·
`PATENT_TO_PRODUCTION_v1` · `PHYSICAL_TO_PRICE_LAG_v1` · `CAUSE_WITHOUT_PRICE_v1`

### Architecture, not hypotheses

`MARGINAL_ALPHA_CONTRIBUTION_v1` (the strategy-market allocator) ·
`RESEARCHER_DIVERSITY_v1` · `UNKNOWN_TICKER_CHALLENGE_v1`

**Every one of these is a family under `RESEARCH_ALPHA_BUDGET`.** That is the
point of building it before the backlog rather than after: twenty-four lines of
inquiry run without a budget will manufacture beautiful nonsense, and the
manufacturing is invisible because each individual test is honest.

## 6. The strategic reframe, which is the review's best contribution

> **Search where ordinary LLMs have the least information and the market has the
> weakest information-processing machinery.**
>
> `high economic importance × low information coverage × measurable causal
> evidence × large disagreement with market expectations × executable asymmetry`

Not the most discussed company, not the highest analyst coverage, not the
cleanest option chain, not the ticker the model remembers best.

Unlike "look for risky small caps" — which is what our Nov-2025 list turned out
to be, a 72%-vol screen with no rank edge — this is testable, and every term in
it is something we can already measure.
