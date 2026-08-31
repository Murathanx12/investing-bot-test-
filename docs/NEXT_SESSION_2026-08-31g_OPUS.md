# NEXT SESSION FOR OPUS — 2026-08-31 (g)

**Read first:** `docs/REPORT_2026-08-31_THE_BOOKS_DO_NOT_REACH_THE_RUNNER.md`, then the strategic repo's active `docs/ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`.

Murat's objective has not changed: maximize expected P&L/terminal wealth subject to survival. The last two days produced useful research and a large wiring discovery. Do not spend this session improving an offline print path while calling it a trading portfolio.

> **MERGE NOTE (this file has two authors).** The 14:35 +08 version specified the P0 artery. It has since been BUILT and pushed (`26faa7b`), so §1 changes from *build it* to *prove it and finish the four missing fields*. Everything else from that version is preserved; verified facts, gates and commands are added. Where the two disagreed, the measurement wins and is shown.

---

## 0. CORRECTION TO THE PREVIOUS DECISION

Do **not** simply enable `murat_rule` and describe hack3/4/6 tracker portfolios as live.

Why: `murat_rule` reads `murat_rule_v1` prediction claims from the sealed prediction book. `alpha.tracker.build_portfolio()` is a different object: it applies each personality's top-k, ranking, sector/liquidity/coverage/downside filters and weights.

The report correctly found that the portfolios do not reach the runner, but "enable murat_rule" is only a prediction-claim experiment, not the portfolio experiment Murat asked for. **The 31 Aug report recommended exactly that, and it was wrong.** It is recorded here so it is not made twice.

**A third layer, found while checking the second:** the *published* seed book was stale. `docs/seed/predictions/2026-08-30.json` held **302 considered / 1 claim (MU)**; the local reseals held **749 / 10**. `--publish` was never run after the reseal. So enabling `murat_rule` would have traded **one name**, not ten, and not hack4's five.

---

## 1. P0 — THE EXACT SEALED PORTFOLIO → RUNNER ARTERY  ✅ BUILT, NOT ENABLED

Built and pushed in `26faa7b`. The chain now exists end to end:

`tracker day file → build_portfolio(personality) → seal exact holdings → publish seed → named selector brain → agent_loop → admission → broker`

- The seal carries `portfolios[book]` inside `content_sha256`.
- `alpha/brains/tracker_portfolio.py` reads that block and nothing else. It never imports `alpha.tracker`, so it **cannot** re-rank at order time.
- Registered in `alpha/brains/__init__.py` as `tracker_portfolio`, distinct from `murat_rule`. **Enabling one does not enable the other.**
- Verified: the sealed holdings are **identical** to the `--portfolios` print for all three books.

The three tests that do not share a cause are in `tests_smoke_artery.py` and are green:

1. **reachability** — registry + `scripts.reachability` no longer calls the brain an orphan;
2. **identity** — holdings read by the brain equal the sealed holdings and weights exactly, and every other symbol is refused;
3. **mutation** — emptying `tracker.PERSONALITIES` after the seal does not move today's book.

Plus the refusals: unset `AAT_ACCOUNT_ROLE` refuses rather than defaulting into another mandate's names; an unknown role refuses rather than substituting; a pre-artery book refuses loudly instead of reading as an empty portfolio; a **degenerate** sealed ranking refuses to trade at all.

One correctness detail worth keeping: `sd = |downside_5pct| / 1.645`, because `downside_5pct` is a 5% normal quantile. Using it raw would have inflated every name's spread by 64%.

**60 suites, 2551 checks, ALL PASS.**

### 1a. FINISH THE ARTIFACT — 4 of 15 spec fields are missing (measured)

Present: day · seal timestamp · tracker vintage · tracker age · personality · symbols in exact rank order · target weight per name · rank value per name · exclusions histogram · sector exposure summary · content hash.

**Missing — do these first, they are small:**

- `driver exposure summary` (`alpha/drivers.py` already resolves drivers; sum notional per driver);
- `derived gross` and `worst_case bound` inside the block (`tracker.worst_case`, taking the **binding** constraint);
- `source commit / model / rule versions`.

Also still open from the earlier version: **fix the misleading authority language in `prediction_book`.** A forecast artifact has no order/sizing authority *by itself*; a named enabled selector may consume it. Do not leave an artifact saying "nothing may influence an order" while a brain is explicitly using it to influence an order.

---

## 2. MONDAY PAPER DECISION

Recommended first host: **hack4 only.** Profit-max personality, comparatively inactive lane. Keeping hack1/hack2 and the others untouched preserves controls.

Before any environment change:

- refresh tracker — **freshness must be 0–1 sessions** (the guard refuses ≥3);
- build/seal today's profit-max portfolio;
- print exact holdings, weights, rank values, sector/driver exposures and derived worst-case;
- **inspect what the runner consumes, not the print:**
  ```python
  from alpha.brains import tracker_portfolio as TP
  import os; os.environ["AAT_ACCOUNT_ROLE"] = "hack4"
  h = TP.sealed_holdings(); print(h["content_sha256"], h["n_selected"], sorted(h["holdings"]))
  ```
- confirm `ranking_is_degenerate: false` (the brain refuses it anyway — know before the runner tells you);
- print the worst case **both ways** and take the binding one: `n × notional × stop` **and** `Σ|notional| / equity` (CLAUDE.md session-protocol 4). hack4 is k=5 × 10% = 50% gross, stop 6% → −3.00%. Re-derive from code; do not copy that number;
- run full suite and fleet checks;
- prove the seed path is visible under Railway's mounted `/app/state` setup;
- make the env change on hack4 only; redeploy hack4 only;
- verify logs show the named portfolio selector **and the same seal hash** before any entry.

**A PUSH DOES NOT DEPLOY.** Proven 31 Aug: `df31a7f` was committed 20:58 +08 and the newest deployment was 12:44 +08 — eight hours *earlier*. It was pushed and never deployed. `prediction_book --publish` already prints "git push, **then redeploy**"; that instruction is load-bearing. Use `railway redeploy --from-source`.

**You may not flip `AAT_LOOP_BRAINS` yourself.** It is a mandate change on a live paper account. Prepare everything, print the exact command, hand it over.

If this cannot be proved before the open, keep the new portfolio **shadow-only** today. Do not substitute `murat_rule` silently. An empty book is recoverable; a book you believe is something else is not.

Do NOT touch gross caps, opening-range protection, broker reconciliation, or options premium-risk rules in this step.

**Never report "the tracker portfolio is live" unless `tracker_portfolio` is in that account's `AAT_LOOP_BRAINS`.**

---

## 3. CAPS — MURAT'S QUESTION ANSWERED IN CODE

Classify constraints so "caps" stops being one argument:

- survival/data-integrity boundaries are **hard**;
- portfolio/personality constraints are **experimental knobs**;
- confidence is **not** a speaking gate.

Specific rulings:

- `UPSIDE_IMPLAUSIBLE_AT=4.0` **stays**: a measured stale-target/share-basis data-quality boundary, not a preference against huge upside. The >400% band's median upside is **4,424%** — an arithmetic artefact of a reverse split, not a forecast. Capping it moved a screen from **−5.5%/yr to +3.9%/yr, t 2.16**.
- hack6 `max_downside=0.20` stays **only** on preservation. Never globalize it.
- sector name caps stay through the competition as a temporary anti-concentration guard. Start the replacement: a **causal-driver exposure report**, so one AI-memory bet is one driver even across twelve sectors, and several names in one sector are allowed when their drivers genuinely differ.
- no 95% confidence requirement to publish a forecast. Uncertainty belongs in confidence and size, not silence.

---

## 4. CLOSE THE LEARNING LOOP

After P0, do **fills → tracker/company-state write-back** before another large model experiment.

Per live/shadow prediction/holding: seal id and portfolio id · entry/exit/fill prices and timestamps · realized/unrealized P&L · slippage/refusal/partial-fill reason · 1/5/20/63/126/252-session outcome checkpoints · whether the thesis/falsifier fired · whether a better candidate replaced it or should have.

**Two things a naive implementation gets wrong:**
- **Append-only**, keyed by (day, symbol, book). Never mutate a past row — the history *is* the training table.
- **Record the refusals.** A name that was sealed and did NOT fill is the most informative row we can write, and it is the one that gets dropped. `admission` already has the reason; carry it through.

This is the training set Murat means by "our own data." A neural net trained before this loop exists learns vendor history, not AEGIS's decisions.

---

## 5. SPLIT OBSERVATION UNIVERSE FROM EXECUTION UNIVERSE

The 11-year test's best liquidity band is below the current tracker floor, and the tracker **cannot even observe it**: `universe.MIN_DOLLAR_VOLUME = 3_000_000`, and the measured minimum across all 3,059 rows is **$3.0m/day**. Zero names below it.

Do NOT lower the live execution floor globally. Instead:

- `OBSERVATION_UNIVERSE`: broad enough to include low-liquidity listed names for discovery, research and spread measurement;
- `EXECUTION_UNIVERSE`: current declared liquidity requirements for actual orders.

Record `spread_bps`, median dollar volume, quote availability and expected participation for the thin-name observational lane. Then "the edge exists, but is it executable?" gets answered with data instead of by deleting the names before they are measured.

> This **retires the "measurement lane"** proposed in brief (f) §1, which would have logged `spread_bps` for $100k–$1m names. There are none. Widen observation first, then measure, then decide.

---

## 6. NEWS: STOP THINKING PER-TICKER FIRST

The next information build is a world-first scanner, not 3,000 independent per-symbol digests.

Build `EventCluster` v0 with a cheap clustering/dedupe pass. A canonical event must separate syndicated copies from independent confirmation.

Minimum fields:

`event_id, event_type, first_seen_at, effective_at, known_by, entities/roles, source_count, independent_source_count, source_quality, novelty_company, novelty_theme, dissemination_speed, surprise_vs_expectation, direction, magnitude, demand_delta, supply_delta, capacity_constraint, contract_or_policy_dollars, revenue_exposure_estimate, causal_driver, causal_hop, causal_uncertainty, already_priced_proxy, evidence_density, verified`

`verified` distinguishes *claimed* from *independently confirmed*: on 31 Aug an AI-generated video circulated with an unevidenced attack claim. A claim and a confirmed event must not enter at one weight.

The expensive LLM sees event clusters, not 1,000 copies of one story. Normalize attention/coverage against each name's **own history** and its sector/size/coverage peers. Raw news volume must never rank NVDA above a biotech just because reporters write about NVDA — Benzinga files 1,566 items on NVDA and 3 on a small biotech (**390:1**), and the logic brain can currently speak on **16 of 749** candidates.

**The rule that makes thin names investable:**

> **evidence density ≠ expected upside.** A biotech with 4 credible observations: expected +70%, confidence 0.43. NVDA with thousands: +14%, confidence 0.81. The biotech may rank higher and still take less capital. Missing evidence lowers **certainty**, never **opportunity**.

**Proof for this chunk:** feed 200 near-identical NVDA items + 3 biotech items; assert one NVDA cluster with high corroboration and a biotech cluster with high expected return and low confidence. If the biotech vanishes, the clustering is a fame filter.

---

## 7. DATA ACQUISITION TASKS

In order:

1. **Check WRDS entitlement for RavenPack** *before* buying another archive. WRDS lists RavenPack Full/Web/Dow Jones, **2000 → Jul 2026**. If entitled, this is the historical-news lane for T13 and event research. **Unverified for our account — a negative answer is worth the hour.**
2. **EDGAR** bulk + submissions/exhibit ingestion for all listed companies ($0). Under-covered names file even when Benzinga ignores them. This is the fix for a brain that can speak on 16 of 749.
3. **GDELT** multilingual event/GKG ingestion for world/Asia lead signals; the **Global Numeric Graph** extracts numeric expressions with context (~152 languages, 2020→). Treat as a broad sensor, not a clean corporate newswire.
4. **Common Crawl** only for historical open-web backfill where licensed archives are absent.
5. Do **not** automate around WSJ/paywall rights. Licensed archive or user-provided lawful text only.
6. X full archive is optional/paid; price it before crawling. **Reddit raw content is not assumed trainable under current API terms** — derived permitted features only; do not build the NN corpus from stored Reddit text. This is a hard line, not a preference.

Write a **source receipt** per sensor: history start, update lag, coverage, license/use class, expected cost, rate limits, and which `EventCluster` fields it can supply.

**Asia-first still stands** (VISION file): the Asian session closes before the US opens. Same-day Asian coverage is the highest-value daily slice we do not have.

---

## 8. NVIDIA — IMPLEMENT THE PARTS THAT FIT AEGIS

Do not install a giant local model on the 8 GB laptop. Hosted inference; the local GPU must not become the bottleneck.

**QSD pattern.** Signal Agent proposes a structured hypothesis over `CompanyState`/`EventCluster` fields → Code Agent converts it to a versioned executable feature/strategy → Evaluation Agent runs AEGIS's PIT backtester/nulls/costs and returns a verdict → **every viewed cell is charged to the persistent experiment-family budget.** An agent that may test 50,000 formulas until one looks excellent has discovered nothing. Keep lineage per candidate (borrowed from the Futarchists entry's strategy genomes).

Operators should be *our* features, not OHLCV: `analyst_revision_velocity, event_novelty, demand_delta, social_attention_z, causal_hop, coverage, abnormal_reaction, drawdown, contract_value/revenue`.

**NeMo Agent Toolkit / AI-Q** for orchestration of broad research/web retrieval, provenance and tracing. Retrieval does not write a trading fact directly; it produces source-backed observations that deterministic code stores and clusters.

**NeMo Data Designer / Curator** to extend T13 with a balanced **synthetic rare-event exam bank**: approvals/rejections, sanctions, war, supply shortage/glut, funding withdrawal, fraud, contract win/loss, regulatory reversal, capacity bottleneck, technology substitution. Generate variations, semantic-dedupe globally, and test whether the decider's probabilities move **monotonically when only one causal fact changes** — same fictional company and financials, raw-material availability −40% vs +40%. If expected return barely moves, the reasoning is not causal.

---

## 9. NEXT BACKTESTS — DO NOT RUN ONE GLOBAL "DOES NEWS WORK?" TEST

After P0/§4, run these as independent manifests:

- **A. `T14_THEME_FIRST_REPLAY`** — world/industry information → needs/bottlenecks → anonymized company exposure table → top-k. No ticker supplied first.
- **B. `T15_OPPORTUNITY_RECALL`** — for each historical month, of the subsequent top 20/50 tradable winners, how many were generated BEFORE the move? Categorize every miss: sensor, entity map, generator, rank, portfolio, expression.
- **C. `T16_MATCHED_LOSERS`** — every winner vs same sector/size/liquidity/coverage names with similar bullish context that did not win.
- **D. `T17_REVISION_VELOCITY`** — 30/60/90-day target/EPS/recommendation changes vs static upside on IBES. *(Cheapest of these; computable today.)*
- **E. `T18_COVERAGE_INITIATION`** — 0 → first analyst event vs matched controls.
- **F. `T19_SURPRISE_REACTION`** — surprise + abnormal day-0 price/volume reaction, controlling for 5d and 12m momentum.
- **G. `T20_COMPRESSION`** — raw copies vs canonical clusters vs numeric-only vs causal summary.
- **H. `T21_ASIA_LEAD`** — information available before the US open vs US-only.
- **I. `T22_EVIDENCE_DENSITY`** — sparse evidence should worsen confidence/calibration but must NOT automatically erase expected-return rank.
- **J. `T23_PORTFOLIO_EXPRESSION`** — same forecasts: equal-weight breadth, top-k, expected-return weighted, risk-budgeted/fractional Kelly, causal-driver constrained, cash. *(Breadth already beat concentration: k=5 → 0.09x terminal, k=100 → 0.73x. "Maximum profit" does not mean "top five".)*
- **K. `T24_HOLD_REUNDERWRITE`** — buy-and-hold until thesis break vs take-profit vs trailing vs replacement-edge.
- **L. `T25_MODEL_DISAGREEMENT`** — independent provider disagreement as a predictor of forecast error/return dispersion.

**The ranking and the probability are different tests.** T13 says ordering can carry information while calibration is bad. Preserve the ordering; calibrate probabilities in code from historical bins rather than trusting the LLM's literal 0.73.

> **Citations caveat.** The review that produced several of these ideas cited 2025-26 papers (Management Science on LLM earnings language; JFE on ChatGPT headline scores; a textual-novelty paper; an SSRN analyst-narrative study). **None is verified by us.** Treat them as leads. Do not cite them in any AEGIS claim until someone opens the paper.

---

## 10. PAPER ACCOUNT EXPERIMENT DESIGN

Target architecture **after** the exact portfolio bridge is enabled; do not merely rename current loops:

hack1 old anchor/control · hack2 post-event drift · hack3 broad analyst-dislocation/breadth · hack4 profit-max tracker/world-model portfolio · hack5 options expression of shared underlying forecasts · hack6 preservation/causal-driver-balanced.

This week, use the accounts for hypotheses that can resolve quickly: reachability, execution, entry timing, stop/re-entry behaviour, opportunity recall, rank ordering and expression. **Do not pretend four trading days can validate a 126-session forecast.** Convert one account at a time or the comparison is destroyed.

---

## 11. COMPETITOR LESSON

Current public Alpaca entries are mostly narrow: SPY/mega-cap technical scans, defined-risk option spreads, LLM critic + deterministic risk, or simple sentiment. Their engineering lesson is **exact order/risk reachability and visible audit trails**. Their weakness relative to AEGIS is discovery breadth and persistent causal learning.

Steal: atomic defined-risk option expression, explicit proposal review, live API telemetry, a visible decision→order→fill chain, replayable journals, per-strategy lineage. Do not copy their fixed small universes.

> Our differentiation: **they decide better on a tiny known universe; AEGIS discovers opportunities the tiny universe never contained** — true only if discovery reaches an order, which is why §1 came first.

---

## 12. SESSION EXIT REQUIRED

Report in plain language:

1. what became order-reachable that was not before;
2. exact seal hash / account / holdings if anything was enabled;
3. P&L impact expected TODAY vs research-only impact;
4. tests/suite/fleet state;
5. source coverage added and cost;
6. new `EventCluster` / `CompanyState` fields;
7. experiments run, with positives, negatives **and dormant cells**;
8. missed opportunities and why AEGIS missed them;
9. what remains disconnected;
10. the next single bottleneck.

If the session shipped engineering and moved none of the scoreboard, the first paragraph says **RESULT IMPROVEMENT: NONE.**

---

## 13. DO NOT

Report a book as live without naming the account whose `AAT_LOOP_BRAINS` contains `tracker_portfolio` · enable more than one book · flip a Railway env var yourself · assume a push deploys · touch gross/stops/opening range · repair the ledger hash chain silently (broken since 25 Aug — log it every report) · cite the §9 papers before opening them · train on Reddit text · pool eras or horizons · read a verdict off a job still writing · **add a test below a `__main__` guard** (on 31 Aug five checks sat below one, `run_tests.py` counted 49 while pytest counted 54, and it printed ALL PASS over five checks that never ran — a check that did not run is not a check that passed).
