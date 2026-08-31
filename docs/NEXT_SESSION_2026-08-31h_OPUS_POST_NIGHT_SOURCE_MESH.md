# NEXT SESSION FOR OPUS — 2026-08-31 (h) — DO NOT STOP AFTER THE NIGHT JOB

**Murat's new instruction:** the competition result is secondary. Treat the six paper accounts as an experiment farm for AEGIS. He is away and explicitly does **not** want the work to stop when the current tracker/night process finishes. Once the current job exits, continue through the sequence below without waiting for another reply, provided the hard tests pass and all trading remains PAPER only.

Read first:
- this repo's newest artery/session report;
- strategic repo `docs/ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`;
- strategic repo `docs/SOURCE_REGISTRY_2026-08-31_FREE_NEWS_AND_ARCHIVES.md` (commit d55904c).

Do not interrupt the tracker refresh that is already running merely to install crawlers. Finish the current state first.

---

## 0. THE CURRENT JOB IS A BARRIER, NOT THE END OF THE SESSION

When the active `tracker --refresh` / repair process exits:

1. Capture a receipt: start/end, rows expected/written, per-source success/error/empty counts, damaged symbols, source outage intervals and exit code.
2. Confirm the process is actually gone. A process-table entry or an empty log is not proof of a running process (we already paid for this failure).
3. Repair the Finnhub-503 rows with bounded retries. Do not infinite-loop on an outage.
4. If a noncritical analyst field remains unavailable after bounded retries:
   - carry forward the last VALID observed value only when it is <=2 sessions old;
   - preserve the original `observed_at`; add `carried_forward_at`, `stale_sessions`, `source_health`;
   - lower `evidence_density/confidence`; NEVER turn missing data into bearish data;
   - never stamp old information as fresh.
5. If a critical price/tradability/share-basis field is unreadable, refuse that name for live execution but keep it in observation/research.
6. Run full tests + fleet check + tracker freshness/diff.

Then continue. Do not end the session with "refresh finished."

---

# 1. TWO MORE P0 GAPS FOUND AFTER THE ARTERY WAS BUILT

The `tracker_portfolio` brain is real and correctly reads only the sealed portfolio. But two additional reachability questions remain before it may be called an **exact live portfolio**.

## P0.5 — SEALED SYMBOLS MUST REACH `forecast()`

Current `scripts/run_pass.py` builds the universe from fixed `--universe`, `--window-universe` and `--candidates`; it does not add `tracker_portfolio.sealed_holdings()` automatically.

A registered brain can therefore be live and never be ASKED about a sealed holding.

Build a dedicated universe path, preferably `--sealed-portfolio-universe` / fleet universe `tracker_sealed`, whose ONLY source is today's sealed artifact. It must not call `alpha.tracker` or re-rank.

Proofs:
- every sealed holding for an enabled tracker role is in `run_pass`'s final universe;
- every sealed holding reaches `tracker_portfolio.forecast()` in a dry run;
- a symbol not in the seal is declined even if it is in another universe;
- mutate the tracker after sealing: today's universe/holdings do not change;
- missing/stale/pre-artery seal refuses loudly.

A reachability test should fail if:
`LIVE tracker_portfolio -> any sealed holding not reachable from agent_loop/run_pass`.

## P0.6 — SEALED WEIGHTS ARE NOT YET LIVE WEIGHTS

`tracker_portfolio` carries `sealed_notional` in `Forecast.evidence`, but the current runner sizes orders from the arbiter/sizer's `verdict.risk_fraction`. The live order-sizing path does not consume `sealed_notional`.

So the current code proves **exact names**, but not exact portfolio weights.

Fix this explicitly rather than implying the weight is enforced.

For the first tracker experiment, make hack3/hack4/hack6 **shares-only** so the mapping is unambiguous:

`sealed target notional -> maximum shares notional`; admission/sizer may CUT it but may never raise it.

Implement a deterministic ceiling in the runner/admission path for `tracker_portfolio`:
- target notional dollars = `sealed_notional * current_equity`;
- convert to max share quantity using current executable price;
- final quantity = `min(sizer_quantity, sealed_quantity_ceiling, existing gross/driver/admission ceilings)`;
- record `sealed_target`, `sizer_proposal`, `final_quantity`, and which constraint bound.

Do not convert the share notional directly to option premium risk. That is a different expression experiment (§4).

Tests:
- sizer tries to exceed seal -> seal wins;
- sizer chooses less -> smaller size preserved;
- price changes between seal and order -> quantity changes but NOT target notional fraction;
- no sealed target -> no tracker order;
- exact selected names + ceilings are inspectable before deploy.

---

# 2. FINISH TODAY'S SEAL AND PUBLISH THE ACTUAL ARTIFACT

Only after §0 + P0.5/P0.6 are green:

1. build/seal 2026-08-31 tracker book;
2. verify content hash;
3. verify every portfolio has non-degenerate ranking, source versions, driver exposure, derived gross and determinable worst-case;
4. run a DRY run through the exact final universe + selector + sizing-ceiling path;
5. compare dry-run proposed names and max notionals against the seal;
6. `--publish` the latest seal — not an older reseal;
7. verify `docs/seed/predictions/2026-08-31...` is the same content hash the dry run consumed;
8. commit + push;
9. deploy from source only after the code commit and seed commit are both present;
10. verify the running service heartbeat names the new build and logs the same book hash before an entry pass.

A stale published seed is a hard failure. We already had 302/1 published while 749/10 existed locally.

---

# 3. THE SIX PAPER ACCOUNTS BECOME AN EXPERIMENT FARM

Murat does not care much about contest placement now. The goal is to learn which decision/portfolio/expression mechanisms work while continuing to collect real fills.

**Update `alpha/fleet.py` FIRST** so the declared code mandate matches Railway. Do not manually change Railway into a state the repo cannot reproduce.

Target experimental roles after §1–2 pass:

### hack1 — CONTROL / ANCHOR
Keep the existing safe anchor/post-event management lane. Do not add tracker intelligence. This is the operational/control equity curve.

### hack2 — MEASURED POST-EVENT DRIFT CONTROL
Keep `post_event_drift` unchanged. It is the clean measured-event comparator.

### hack3 — TRACKER BALANCED, SHARES
Switch to `tracker_portfolio`, sealed hack3 balanced personality, shares-only. This is the broad analyst-dislocation arm with its current experimental past-winner exclusion.

Question: does broad risk-adjusted analyst/dislocation selection beat the old event/theme machinery and controls?

### hack4 — TRACKER PROFIT-MAX, SHARES
Switch to `tracker_portfolio`, sealed hack4 profit-max personality, shares-only. This is the PRIMARY adaptive profit-max tracker arm.

Question: does upside x consensus + catalyst portfolio selection create better P&L/opportunity recall than measured drift and balanced breadth?

### hack5 — SAME FORECASTS, OPTIONS EXPRESSION
Do NOT let hack5 select a different underlying universe if the experiment is shares vs options.

Build a sealed `hack5` expression block whose UNDERLYING NAMES and ranking are identical to hack4's profit-max selection, but whose capital field is **premium-at-risk / max-loss**, not share notional.

Allowed structures remain defined-risk / long premium under the already shipped rules (>=10 DTE, break-even inside market width, option liquidity, premium-risk ceiling). Prefer bull call spread vs long call as two recorded alternatives if the chain permits.

Question: given the SAME bullish names, are options or shares the better expression after spread/theta/IV?

If this exact-name expression block cannot be finished before today's open, leave hack5 on its old convex lane today and label it OLD CONVEX CONTROL. Do not pretend it is the expression A/B.

### hack6 — TRACKER PRESERVATION, SHARES
Switch to `tracker_portfolio`, sealed hack6 preservation personality, shares-only. Keep its experimental coverage/liquidity/downside constraints local to hack6.

Question: how much expected P&L does preservation give up, and how much drawdown/calibration does it buy?

## Hard rule for all six

Keep gross/account breakers, opening-range share guard, broker-state reconciliation, stale-data integrity, defined-risk option rules and append-only receipts. These are survival/data-integrity controls, not alpha opinions.

## Railway change order

After code + seed are pushed:
1. deploy code first where needed;
2. change one service at a time;
3. verify `AAT_ACCOUNT_ROLE`, `AAT_LOOP_BRAINS`, universe args, risk profile, structure kinds, build commit and sealed hash in logs;
4. run one dry/diagnostic pass;
5. then PAPER live;
6. repeat for the next experimental role.

If any account is not changed, report its actual old mandate. Never describe the target architecture as the running fleet.

---

# 4. NIGHT -> DECISION BARRIER FOR EVERY DAY THIS WEEK

Murat explicitly wants the night research to finish and THEN the decisions to be made from that completed state.

Build a small `night_manifest` / `night_complete` receipt instead of relying on process timing.

Required lanes should register:
- tracker refresh;
- price/coverage repair;
- news/source ingest;
- EventCluster build when available;
- catalyst calendar;
- premarket/global digest;
- logic/council enrichment when scheduled;
- prior-day autopsy/discovery autopsy;
- source-health summary.

Each writes `status`, start/end, input/output hashes, row/event counts and errors.

The morning seal reads ONE finalized night manifest.

Rules:
- it does not seal against a file still being mutated;
- a failed OPTIONAL source does not freeze AEGIS forever — use the last valid observation with explicit staleness/evidence penalty;
- a missing CRITICAL execution input refuses the affected name, not the whole world;
- no partial successful run overwrites a better complete artifact with an empty one;
- if the night exceeds the pre-open deadline, freeze the latest complete snapshot and say which lanes are stale rather than racing the open with half-written data.

This is a data-integrity boundary, not a 95%-confidence trading gate.

---

# 5. FREE NEWS / ARCHIVE MESH — RAVENPACK IS CLOSED, USE THE WEB WE HAVE

The complete source registry is now in the strategic repo:
`docs/SOURCE_REGISTRY_2026-08-31_FREE_NEWS_AND_ARCHIVES.md`.

Do not spend the session searching randomly again. Start these probes in this order after the paper chain is stable.

## 5.1 SC454k — FIRST HISTORICAL TEXT PROBE

~454k Nasdaq small-cap news/press releases paired with WRDS market data.

Why first: our central live defect is famous-company news bias. A small-cap corpus tests the exact opposite universe.

Task:
- download metadata + a bounded shard;
- inspect date range, timestamp completeness, symbol/corporate-action mapping, publisher mix and reuse terms;
- convert 1–2 months to `raw_observation -> EventCluster`;
- run the T13/T20 encoder on it;
- compare duplicate rate, evidence density and opportunity recall with the current Benzinga-heavy corpus.

## 5.2 FNSPID — SECOND

Authors report ~15.7M news records / 4,775 companies / 1999–2023 plus prices.

Do a bounded shard first. Audit PIT and license provenance; the public repo and HF license metadata have conflicting language. Fine as an internal research probe; do not assume unrestricted commercial training rights.

Use it to expand fantasy-era/context experiments beyond 11 recent months.

## 5.3 COMMON CRAWL CC-NEWS — FIRST TRUE WORLD ARCHIVE

Adopt:
- `fhamborg/news-please` for article extraction;
- `commoncrawl/cdx_toolkit` for CC + Internet Archive targeted URL/date discovery;
- `commoncrawl/cc-downloader` when a FILTERED path set is ready.

Proof first:
- one historical month;
- a selected list of financial, technology, trade, biotech and Asia/local domains;
- stream WARC, do not download the whole crawl;
- normalize URL/date/language;
- deterministic exact/near-duplicate compression before LLM.

Measure **canonical events**, not downloaded articles.

## 5.4 ARCHIVEBOX — START OUR OWN MEMORY NOW

Every high-value URL AEGIS actually uses should be eligible for forward archival when rights/robots permit.

Goal: in Aug 2027 we should be able to replay what AEGIS knew in Aug 2026 from our own receipts, not ask a vendor to recreate it.

Keep archival storage separate from latency-sensitive trading services.

## 5.5 MEDIA CLOUD

Probe its 200M+ Online News Archive and Wayback-backed source collections. Use it as an index/discovery layer even if full text is not always returned.

## 5.6 EDGAR + GDELT ARE CORE LIVE SENSORS

EDGAR cures under-covered-company silence. GDELT cures US/English/famous-company tunnel vision.

Build both into `EventCluster v0` before another expensive per-ticker LLM digest.

---

# 6. OFFICIAL NON-NEWS SOURCES — THESE ARE OFTEN BETTER THAN ARTICLES

Prioritize adapters/receipts for:

- SEC/EDGAR: 8-K/exhibits, 10-Q/K, 6-K/20-F, Form 4, 13D/G, tender/M&A, offerings;
- FDA/openFDA + ClinicalTrials.gov;
- Federal Register / GovInfo policy/regulation;
- USAspending contracts/grants;
- FRED + ALFRED real-time vintages;
- Census international trade from 2010;
- World Bank country/macro state.

A Reuters article about a government contract is secondary evidence if USAspending/agency data has the actual award.

---

# 7. ASIA-FIRST LANE

Build stubs + one real receipt each:

- HKEX official RSS/regulatory announcements;
- Korea OpenDART;
- Japan EDINET v2;
- China: AKShare/FinNLP adapter references plus CNINFO/exchange/MIIT/NDRC/MOFCOM/customs/issuer primary pages;
- GDELT/local-language cross-check.

Every EventCluster gets `information_region`, `language`, `first_seen_utc`, and whether the event was observable before the US open.

This feeds T21: Asia/local information vs US-only baseline.

---

# 8. SOCIAL: COLLECT ATTENTION, NOT 'TRUTH'

Start forward collection cheaply:

- Bluesky AT Protocol firehose: public/no-auth forward attention stream;
- Hacker News official API: useful for AI/software/security/developer narratives;
- StockNet historical Twitter dataset: small 2014–2016 benchmark.

Derived features:
`mention_z, velocity, unique_authors, link_domain_diversity, disagreement, narrative_entropy, dissemination_speed`.

Do not use unofficial X/Stocktwits scrapers as a foundational dependency. X full archive is paid. Stocktwits new app registration is paused and scraping is prohibited. Reddit raw content is not a blanket training dataset under current terms.

---

# 9. EVENTCLUSTER v0 — BUILD THIS BEFORE MORE LLM SPEND

One economic event should survive 1,000 syndicated copies as ONE row with corroboration fields.

Minimum:
`event_id, event_type, first_seen_at, effective_at, known_by, entities_roles, source_count, independent_source_count, source_quality, novelty_company, novelty_theme, dissemination_speed, surprise_vs_expectation, direction, magnitude, demand_delta, supply_delta, capacity_constraint, contract_or_policy_dollars, revenue_exposure_estimate, causal_driver, causal_hop, causal_uncertainty, already_priced_proxy, evidence_density, information_region, language`.

Dedup layers:
1. normalized URL/content hash;
2. near-duplicate title/body similarity constrained by entity/time;
3. semantic event cluster.

Do deterministic reduction BEFORE sending anything to an LLM.

---

# 10. COMPANYSTATE + LEARNING LOOP

Close fills/outcomes -> CompanyState before building the NN.

Every decision vintage should eventually preserve:
- source/EventCluster IDs;
- analyst target/upside/count/revision velocity/disagreement;
- price/volume/momentum/drawdown/liquidity;
- causal drivers/exposures;
- 1/5/21/63/126/252-session p_up/exp_return/downside/confidence;
- selected portfolio/weight/expression;
- actual fills/slippage/refusals;
- later outcomes and thesis/falsifier status.

This is the dataset AEGIS owns.

---

# 11. RESEARCH JOBS AFTER THE OPERATIONAL CHAIN IS GREEN

Do not wait for all sources to exist. Start with whichever historical source passed the bounded probe.

Priority:
1. T14 Theme-First Replay;
2. T15 Opportunity Recall;
3. T16 Matched Losers;
4. T17 Analyst Revision Velocity;
5. T18 Coverage Initiation;
6. T19 Surprise x Initial Reaction;
7. T20 Raw News vs EventCluster vs Numeric vs Causal Summary;
8. T21 Asia-before-US lead;
9. T22 Evidence Density vs expected-return rank/calibration;
10. T23 Portfolio Expression;
11. T24 Hold/Re-underwrite/Replacement Edge;
12. T25 Independent-model disagreement.

Use NVIDIA's QSD Signal -> Code -> Evaluation pattern as the experiment factory, with AEGIS fields/backtester/nulls rather than NVIDIA's demo universe. Use NeMo Agent Toolkit for provenance/orchestration; use Data Designer/Curator pattern for balanced fantasy rare-event exams.

---

# 12. DO NOT STOP BECAUSE ONE SOURCE FAILS

Source failover philosophy:

- one source down -> mark it down and use other independent sensors;
- one ticker lacks news -> keep candidate with lower evidence density;
- one API 503 -> bounded retry, carry valid stale values, do not fabricate freshness;
- one crawler/parser breaks -> raw URL stays queued for another extractor;
- one LLM provider fails -> deterministic features remain and another model may classify later;
- all evidence is thin -> publish uncertainty, not "company is bad".

But do not convert a data failure into a tradeable fact.

---

# 13. REQUIRED SESSION EXIT — ONLY AFTER THE CHAIN ABOVE

Report plainly:

1. Did the original tracker/night process finish? final counts/errors?
2. Which damaged rows were repaired/carried/refused?
3. Today's exact seal hash and publication hash.
4. Did every sealed holding reach `forecast()`?
5. Are sealed notional ceilings actually enforced in quantity sizing?
6. Exact running mandate of hack1–hack6 after Railway changes, not target plan.
7. Build/deploy hash per changed account.
8. Paper account equity/P&L/open positions after setup.
9. Which source probes completed and their usable date/row/full-text/PIT/license results?
10. EventCluster/CompanyState progress.
11. Experiments started/finished and positives/nulls.
12. What remains disconnected.
13. Single next bottleneck.

The success criterion is not contest rank. It is that every day AEGIS sees more of the world, converts it into a reproducible state, makes explicit portfolio decisions, receives real paper execution feedback, and owns a larger training/evaluation history than the day before.