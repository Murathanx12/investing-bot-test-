# NEXT SESSION FOR OPUS — 2026-08-31 (g)

**Read first:** `docs/REPORT_2026-08-31_THE_BOOKS_DO_NOT_REACH_THE_RUNNER.md`, then the strategic repo's active `docs/ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`.

Murat's objective has not changed: maximize expected P&L/terminal wealth subject to survival. The last two days produced useful research and a large wiring discovery. Do not spend this session improving an offline print path while calling it a trading portfolio.

## 0. CORRECTION TO THE PREVIOUS DECISION

Do **not** simply enable `murat_rule` and describe hack3/4/6 tracker portfolios as live.

Why: `murat_rule` reads `murat_rule_v1` prediction claims from the sealed prediction book. `alpha.tracker.build_portfolio()` is a different object: it applies each personality's top-k, ranking, sector/liquidity/coverage/downside filters and weights. There is still no exact `build_portfolio -> runner` artery.

The report correctly found that the portfolios do not reach the runner, but "enable murat_rule" is only a prediction-claim experiment, not the portfolio experiment Murat asked for.

## 1. P0 — BUILD THE EXACT SEALED PORTFOLIO -> RUNNER ARTERY

Smallest acceptable implementation:

`tracker day file -> build_portfolio(personality) -> seal exact holdings -> publish seed -> named selector brain -> agent_loop -> admission -> broker`

Build one canonical artifact, e.g. `portfolio-book-1`, containing:

- day / seal timestamp / tracker vintage / tracker age;
- personality and version;
- selected symbol list in exact rank order;
- target weights or max notional per name;
- rank input/value and selection reason per name;
- exclusions histogram;
- sector/driver exposure summary;
- derived gross and worst-case bound;
- content hash;
- source commit/model/rule versions.

The selector MUST read the seal. It may not call `build_portfolio()` again at order time and may not re-rank on fresh data after the seal.

Add three tests that do not share a cause:

1. reachability: a portfolio marked LIVE must be reachable from an entry point through its named brain to admission;
2. identity: dry-run holdings read by the brain equal the sealed holdings/weights exactly;
3. mutation: change the tracker after sealing and prove the live selector remains on the sealed portfolio.

Fix the misleading authority language in `prediction_book`: a forecast artifact has no order/sizing authority **by itself**; a named enabled selector may consume it. Do not leave an artifact saying "nothing may influence an order" while a brain is explicitly using it to influence an order.

## 2. MONDAY PAPER DECISION

Recommended first host after P0 passes: **hack4 only**.

Reason: its desired personality is profit-max and its prior running lane has been comparatively inactive/near-flat. Keeping hack1/hack2 and the other experimental accounts untouched preserves controls.

Before any environment change:

- refresh tracker;
- build/seal today's profit-max portfolio;
- print the exact holdings, weights, rank values, sector/driver exposures and derived worst-case;
- run full suite and fleet checks;
- prove seed path is visible under Railway's mounted `/app/state` setup;
- make the env change on hack4 only;
- redeploy hack4 only;
- verify logs show the named portfolio selector and the same seal hash before any entry.

If this cannot be proved before the open, keep the new portfolio shadow-only today. Do not substitute `murat_rule` silently.

Do NOT touch gross caps, opening-range protection, broker reconciliation, or options premium-risk rules in this step.

## 3. CAPS — MURAT'S QUESTION ANSWERED IN CODE

Add comments/docs/tests that classify constraints so we stop arguing about "caps" as one thing:

- survival/data-integrity boundaries are hard;
- portfolio/personality constraints are experimental knobs;
- confidence is not a speaking gate.

Specific rulings:

- `UPSIDE_IMPLAUSIBLE_AT=4.0` stays: it is a measured stale-target/share-basis data-quality boundary, not a preference against huge upside.
- hack6 `max_downside=0.20` stays only on preservation. Never globalize it.
- sector name caps stay through the competition as a temporary anti-concentration guard. Start the replacement: a **causal-driver exposure report** so later we budget one AI-memory bet as one driver even if it contains twelve sectors/tickers, and allow several names in one sector when their actual drivers differ.
- no 95% confidence requirement to publish a forecast. Uncertainty belongs in confidence/size, not silence.

## 4. CLOSE THE LEARNING LOOP

After the P0 bridge, do **fills -> tracker/company-state write-back** before another large model experiment.

For each live/shadow prediction/holding keep:

- seal id and prediction/portfolio id;
- entry/exit/fill prices and timestamps;
- realized/unrealized P&L;
- slippage/refusal/partial-fill reason;
- 1/5/20/63/126/252-session outcome checkpoints when available;
- whether the original thesis/falsifier fired;
- whether a better candidate replaced it or should have.

This is the training set Murat means by "our own data." A neural net trained before this loop exists learns vendor history, not AEGIS's decisions.

## 5. SPLIT OBSERVATION UNIVERSE FROM EXECUTION UNIVERSE

The 11-year test's best liquidity band is below the current tracker floor, and the current tracker cannot even observe it.

Do NOT lower the live execution floor globally.

Instead create:

- `OBSERVATION_UNIVERSE`: broad enough to include low-liquidity listed names for discovery/research and spread measurement;
- `EXECUTION_UNIVERSE`: current/declared liquidity requirements for actual orders.

Record `spread_bps`, median dollar volume, quote availability and expected participation for the observational thin-name lane. Then the project can answer "the edge exists, but is it executable?" with data rather than deleting the names before they are measured.

## 6. NEWS: STOP THINKING PER-TICKER FIRST

The next information build is a world-first scanner, not 3,000 independent expensive per-symbol digests.

Build `EventCluster` v0 and a cheap clustering/dedupe pass over the corpus. A canonical event must separate syndicated copies from independent confirmation.

Minimum fields:

`event_id, event_type, first_seen_at, effective_at, known_by, entities/roles, source_count, independent_source_count, source_quality, novelty_company, novelty_theme, dissemination_speed, surprise_vs_expectation, direction, magnitude, demand_delta, supply_delta, capacity_constraint, contract_or_policy_dollars, revenue_exposure_estimate, causal_driver, causal_hop, causal_uncertainty, already_priced_proxy, evidence_density`.

The expensive LLM sees event clusters, not 1,000 copies of one story.

Normalize attention/coverage against each name's own history and sector/size/coverage peers. Raw news volume must never rank NVDA above a biotech just because reporters write about NVDA.

## 7. DATA ACQUISITION TASKS

In order:

1. **Check WRDS entitlement for RavenPack** before buying another archive. WRDS lists RavenPack Full/Web/Dow Jones history from 2000 through 2026. If entitled, this is the historical-news lane for T13 and event research.
2. Add/verify EDGAR bulk + submissions/exhibit ingestion for all listed companies. Under-covered names get filings even when Benzinga ignores them.
3. GDELT global multilingual/event/GKG ingestion for world/Asia lead signals. Treat it as a broad sensor, not a clean corporate newswire.
4. Common Crawl only for historical open-web backfill where primary/licensed archives are absent.
5. Do not automate around WSJ/paywall rights. Licensed archive or user-provided lawful text only.
6. X full archive is optional/paid; price it before crawling. Reddit raw content is not assumed trainable under current API terms.

Write a source receipt: history start, update lag, coverage, license/use class, expected cost, rate limits and which EventCluster fields it can supply.

## 8. NVIDIA — IMPLEMENT THE PARTS THAT FIT AEGIS

Do not install a giant local model on the 8 GB laptop.

### QSD pattern

Take NVIDIA's Quantitative Signal Discovery Agent structure and point it at AEGIS data:

- Signal Agent proposes a structured hypothesis over `CompanyState/EventCluster` fields;
- Code Agent converts it to an executable, versioned feature/strategy;
- Evaluation Agent runs AEGIS's PIT backtester/nulls/costs and returns a verdict;
- every viewed cell is charged to the persistent experiment-family budget.

Run hosted NIM/API where appropriate. We want the workflow, not NVIDIA's demo S&P universe.

### NeMo Agent Toolkit / AI-Q

Use for orchestration of broad research/web retrieval, provenance and tracing. Retrieval does not get to write a trading fact directly; it produces source-backed observations that deterministic code stores and clusters.

### NeMo Data Designer / Curator pattern

Extend T13 with a balanced **synthetic rare-event exam bank**: approvals/rejections, sanctions, war, supply shortage/glut, bank funding withdrawal, fraud, contract win/loss, regulatory reversal, capacity bottleneck, technology substitution. Generate variations, globally semantic-dedupe them, and test whether the decider's probabilities move monotonically when only one causal fact changes.

## 9. NEXT BACKTESTS — DO NOT RUN ONE GLOBAL "DOES NEWS WORK?" TEST

After P0/P4, run these as independent manifests:

A. `T14_THEME_FIRST_REPLAY`: world/industry information -> identify needs/bottlenecks -> anonymized company exposure table -> top-k. No ticker is supplied first.

B. `T15_OPPORTUNITY_RECALL`: for each historical month, of the subsequent top 20/50 tradable winners, how many were generated BEFORE the move? Categorize every miss: sensor, entity map, generator, rank, portfolio, expression.

C. `T16_MATCHED_LOSERS`: every winner vs same sector/size/liquidity/coverage names that saw similar bullish context but did not win.

D. `T17_REVISION_VELOCITY`: 30/60/90-day target/EPS recommendation changes vs static target upside on IBES.

E. `T18_COVERAGE_INITIATION`: 0 -> first analyst event vs matched controls.

F. `T19_SURPRISE_REACTION`: surprise + abnormal day-0 price/volume reaction, controlling for 5d and 12m momentum.

G. `T20_COMPRESSION`: raw news copies vs canonical event clusters vs numeric-only vs causal summary.

H. `T21_ASIA_LEAD`: Asia/China/Korea/Japan information available before US open vs US-only information.

I. `T22_EVIDENCE_DENSITY`: test Murat's hypothesis explicitly: sparse evidence should worsen confidence/calibration, but should not automatically erase expected-return rank.

J. `T23_PORTFOLIO_EXPRESSION`: same forecasts, different construction — equal-weight breadth, top-k, expected-return weighted, risk-budgeted/fractional-Kelly, causal-driver constrained, cash.

K. `T24_HOLD_REUNDERWRITE`: buy-and-hold until thesis break vs take-profit vs trailing vs replacement-edge.

L. `T25_MODEL_DISAGREEMENT`: independent provider disagreement as predictor of forecast error/return dispersion.

The LLM ranking and probability are different tests. T13 says ranking can contain information while calibration is bad. Preserve ordering, then calibrate probabilities with code from historical bins rather than trusting the LLM's literal 0.73.

## 10. PAPER ACCOUNT EXPERIMENT DESIGN

Target architecture after exact portfolio bridge exists; do not merely rename current loops:

- hack1 old anchor/control;
- hack2 post-event drift;
- hack3 broad analyst-dislocation/breadth;
- hack4 profit-max tracker/world-model portfolio;
- hack5 options expression of shared underlying forecasts;
- hack6 preservation/causal-driver-balanced.

During this week, use the accounts to test hypotheses that can resolve quickly: reachability, execution, entry timing, stop/re-entry behavior, opportunity recall, rank ordering and expression. Do not pretend four trading days can validate a 126-session forecast.

## 11. COMPETITOR LESSON

The current public Alpaca entries are mostly narrow: SPY/mega-cap technical scans, defined-risk option spreads, LLM critic + deterministic risk, or simple sentiment. Their strong engineering lesson is exact order/risk reachability and visible audit trails. Their weakness relative to AEGIS is discovery breadth and persistent causal learning.

Steal the useful parts: atomic defined-risk option expression, explicit proposal review, live API telemetry, visible decision->order->fill chain, and replayable journals. Do not copy their fixed small universes.

## 12. SESSION EXIT REQUIRED

Report in plain language:

1. what became order-reachable that was not before;
2. exact seal hash/account/holdings if anything was enabled;
3. P&L impact expected TODAY vs research-only impact;
4. tests/suite/fleet state;
5. source coverage added and cost;
6. new EventCluster/CompanyState fields;
7. experiments run with positives, negatives and dormant cells;
8. missed opportunities and why AEGIS missed them;
9. what remains disconnected;
10. the next single bottleneck.

Do not report a printed portfolio as a live portfolio. Do not report a news count as independent evidence. Do not report a model probability as calibrated because the model supplied two decimals.