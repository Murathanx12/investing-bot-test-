# docs/INDEX.md — what to read, in what order (2026-09-02)

This repo has 90 docs and a 1,700+ line `HANDOFF.md`. A new session must NOT
read them all. Read TIER 0 (below, five lines), then the CURRENT session block
of `HANDOFF.md`, then jump into the MAP by the question you actually have.

Sibling repo `../aegis-finance` holds the strategy, canon and research; its
`docs/INDEX.md` is the strategic authority. This index is about EXECUTION.

## TIER 0 — WHAT THIS REPO IS, AND THE FOUR THINGS THAT DO NOT MOVE

1. **This is the EXECUTION brain**, not the strategy. Six Alpaca **paper**
   accounts (`hack1` anchor · `hack2` drift · `hack3` thesis · `hack4` predator
   · `hack5` convexity · `hack6` blend), declared as data in `alpha/fleet.py`,
   each running as Railway service `aat-loop-<role>` in project
   `loving-elegance` with volume `/app/state`. The laptop does not have to be on.
2. **A day is a SEALED BOOK.** `state/predictions/<day>.json` carries the exact
   holdings per book inside `content_sha256`; the runner expresses that book and
   may only CUT it, never raise it. Mandate expiry `AAT_LOOP_EXPIRY=2026-09-04`
   — books liquidate **10:45 ET**, judging **11:00 ET on 2026-09-04**.
3. **Books fail CLOSED.** No sealed book for the day ⇒ `tracker_portfolio`
   selects nothing and the account trades nothing. An empty book with 800
   refusal reasons is a *valid decision*, not a bug.
4. **No LLM authority over capital.** LLMs generate theses, score narratives and
   write autopsies; no LLM sits on an order path. Every LLM call passes
   `alpha/spend.py justify()` with a decision verb.
5. **Two operational absolutes.** The ledger hash chain (`state/decisions.jsonl`)
   has been **BROKEN since 25 Aug** — it is logged and reported every run and is
   **never silently repaired**; repairing a tamper-evident chain IS the
   tampering (`docs/FINDING_LEDGER_CHAIN_BREAK_2026-08-25.md`). And the house
   deploy is `python -m scripts.fleet --check-all` then
   `python -m scripts.fleet --deploy <role> --up` (stamps `BUILD_COMMIT`) —
   **not** `railway redeploy`, and Railway does **not** deploy on push.

Also standing: tests run ONLY via `python run_tests.py` (it sets
`AAT_TEST_MODE=1`, which blocks the socket in every child process).

## TIER 1 — THE CURRENT SESSION QUEUE (do not duplicate it; go read it)

**`docs/HANDOFF.md`, the top block — `## SESSION 33 CLOSE (2026-09-01)`.**
It opens the file, and its `### WHAT IS LEFT` list is the live queue (seal the
day under BAND_PRIOR v2 · verify the 10:01 ET Railway pass · grade
`state/decision_outcomes` · arena v2 minds · holder provenance · the Wednesday
09-04 judging plan). Everything below that block in `HANDOFF.md` is a diary in
reverse-chronological order: it records what was true when written, and a fact
taken from it must be re-verified against code, a receipt, or TIER 0.

`docs/NEXT_SESSION_*.md` are per-session briefs from the same lineage; the
newest is `NEXT_SESSION_2026-08-31i_FABLE_WBUY_ROOT_CAUSE_AND_ADAPTIVE_DECISIONS.md`.
They are inputs to a session, never authority.

Strategic authority is one repo over: `../aegis-finance/docs/INDEX.md` TIER 0 +
its single TIER 1 roadmap.

## THE MAP — grouped by the question you arrived with

### "How does a day get sealed?"
The artery, in order:
- `scripts/tracker.py` — nightly refresh of the ~3,000-name watchlist; writes
  `state/tracker/<day>.jsonl` + `latest.json`. Run with `--backfill-prices`
  **before** sealing or the vol-dependent books seal empty.
- `scripts/seal_authority.py` — the attended wrapper that runs the watcher, the
  refresh and the seal in the one order that works.
- `scripts/prediction_book.py` — `--seal` builds `state/predictions/<day>.json`
  (`murat_rule_v1` + BAND_PRIOR), exact per-book holdings inside
  `content_sha256`; `--publish` pushes it to the website surface.
- `scripts/prediction_book_sync.py` — pulls/pushes the published book so a
  container that slept through a day can be repaired.
- `docs/seed/predictions/` — the seeded book history. **Never mutated.**
  `docs/seed/universe/` holds the theme seed (`THEMES_2026-08-28.json`).
- `state/predictions/seals.jsonl` — one line per seal: day, sha, claims,
  considered. This is the quickest "did today seal?" check.

### "How do orders happen?"
- `scripts/agent_loop.py` — the loop each Railway service runs (entry pass,
  manage pass, expiry).
- `alpha/runner.py` — the entry pass itself: brains → claims → admission →
  sizing → orders. `alpha/admission.py` holds the post-trade caps (incl. GROSS).
- `alpha/brains/` — the selectors. `tracker_portfolio.py` reads ONLY the sealed
  book's `portfolios[book]`; `murat_rule.py` trades per-name claims;
  `post_event_drift.py`, `theme_basket.py`, `council_vector.py`,
  `event_move.py`, `relay.py`, `vol_gap.py`, `options_attention.py`,
  `narrative_dispersion.py` are the others. `base.py` is the contract.
- `alpha/engine/sizing.py` (profiles, per-name and gross caps) ·
  `alpha/engine/equity.py` (share structures) · `alpha/engine/shape.py`
  (decile shape → instrument) · `alpha/engine/structures.py`,
  `payoff.py` (option structures).
- `alpha/broker/alpaca.py` — the ONLY venue client. Paper host enforced.
- `alpha/protect.py` (stops resting at the venue) · `alpha/exits.py` (manage) ·
  `alpha/genesis.py` + `scripts/genesis.py` (`--freeze` per role BEFORE the
  first order, or the day-1 latch refuses every entry).

### "How do I check everything?"
- `python -m scripts.fleet_health` — the estate in one command: per-role equity,
  positions, orders, loop liveness.
- `python -m scripts.fleet --plan` / `--check-all` / `--deploy <role> --up` —
  mandates, venue preflight, the house deploy.
- `python -m scripts.flatten` — the attended command to take a book to zero.
- `python run_tests.py` — the ONLY correct way to run the suite (63 suites /
  ~2,769 checks at 2026-09-01).
- `python -m scripts.preflight` (pre-open checks) · `scripts/liveness.py` ·
  `scripts/reconcile.py` (venue orders vs ledger rows) ·
  `scripts/utilization.py` (what fraction of the mandate the book actually used)
  · `scripts/dashboard.py` → `state/dashboard.html`.
- `railway logs --service aat-loop-<role>` is the heartbeat. A laptop PID is not.
- The venue clock is `/v2/clock`. The machine clock is UTC+8 and runs fast.

### "What watches the market?"
- `scripts/ownership_watch.py` — EDGAR 13D/13G attention watcher; a material
  holder event forces observation. Runs inside `seal_authority`.
- `alpha/sources/` — every inbound feed: `finnhub.py` (quotes, targets,
  ratings), `sec.py` + `edgar_ownership.py` (filings, ownership),
  `corpus.py` (the PIT observation corpus), `attention.py`, `belief.py`,
  `features.py`, `registry.py` (what is enrolled), `http.py` (the one transport).
- `scripts/candidates.py` — the day's candidate set → `state/candidates/<day>.json`.
- `scripts/window_universe.py`, `scripts/theme_screen.py`,
  `scripts/seed_market.py` — universe construction and the liquidity floor.
- `scripts/news_backfill.py`, `scripts/corpus_digest.py`,
  `scripts/catalyst_horizon.py` — the corpus and the forward calendar (two
  clocks, two bounds).
- `scripts/premarket_digest.py` — the pre-open read.
- `alpha/company_state.py` + `scripts/company_state_append.py` — text → numeric
  CompanyState.

### "What grades us?"
- `scripts/decision_writeback.py` — closes the loop: every decision (including
  every REFUSAL) gets its outcome written back to `state/decision_outcomes/`.
- `scripts/daily_autopsy.py` — what the book did and why, per day.
- `scripts/discovery_autopsy.py` — the harder question: what we should have
  found and did not.
- `scripts/move_decomposition.py` — splits each held name's move into
  market / sector / company legs → `state/decomposition/<day>.json`.
- `scripts/scenario_lab.py` — **NOT ON DISK as of 2026-09-02**; expected
  shortly. Do not cite it as existing until it does.
- Also grading: `scripts/counterfactual.py` (what the refused book would have
  done), `scripts/pnl_attribution.py`, `scripts/pnl_forensics.py`,
  `scripts/fill_audit.py`, `scripts/refusal_regret.py` + `refusal_nav.py`
  (a refusal has a price), `scripts/event_grade.py`,
  `scripts/blind_tournament.py`, `scripts/era_replay.py`.

### "Where are the receipts?"
`state/` is the runtime. Everything below is written by code, not by hand.
- `state/decisions.jsonl` — **the ledger** (hash chain, broken since 25 Aug).
- `state/fills.jsonl` · `state/protective_stops.jsonl` · `state/forecasts.jsonl`
  — orders, resting stops, claims made.
- `state/predictions/` — sealed books per day + `seals.jsonl`.
- `state/tracker/` — nightly watchlist rows, `latest.json`, `transitions.jsonl`.
- `state/decision_outcomes/` — graded decisions (EMPTY as of 2026-09-02; queue
  item 3 fills it).
- `state/decomposition/` — market/sector/company splits per day.
- `state/autopsy/` — daily autopsies · `state/premarket/` — pre-open digests.
- `state/candidates/` · `state/universe/` — what was considered, and the
  universe snapshot it came from.
- `state/company_state/` · `state/expectations/` · `state/evidence/` ·
  `state/causal_graph.jsonl` — the world model's own state.
- `state/corpus/` — the PIT observation corpus (**gitignored, regenerable**) ·
  `state/sec_cache/` — ~3,000 cached filings.
- `state/council/`, `state/logic_brain/`, `state/tournament/`,
  `state/era_replay/`, `state/night_shadow/`, `state/lab/`,
  `state/research/` — LLM council packets, blind tournaments, replays, night
  lab and research outputs.
- `state/genesis_hack<N>.json` — the frozen day-1 equity latch per role.
- `state/llm_spend.jsonl` + `state/alpha_budget.jsonl` — spend, per decision verb.
- `state/liveness/` · `state/loop_*.log` — loop heartbeats and stdout.

### "What did we already learn (and must not re-derive)?"
- `docs/FLEET_2026-08-28.md` — the six mandates in one table, with the one
  question each account exists to answer.
- `docs/DECISION_2026-08-31_HACK4_TRACKER_APPROVED.md` — the conditions-based
  authorisation that put a sealed book on a live paper account.
- `docs/REPORT_2026-08-31_THE_BOOKS_DO_NOT_REACH_THE_RUNNER.md` — verify a link
  at its FAR end; the obvious repair was also wrong.
- `docs/FINDING_LEDGER_CHAIN_BREAK_2026-08-25.md` — why the chain stays broken.
- `docs/FINDING_*.md` (41 files) — one measured result each, by date.
- `docs/ROADMAP_*.md`, `docs/RUNBOOK_*.md`, `docs/RULES_SNAPSHOT_*.md` —
  superseded plans and frozen rule snapshots; receipts, not authority.
- `docs/CORPUS_2026-08-29_MEMORY_AND_DIARY.md` — the 30.9k-row corpus study.
- `docs/night/`, `docs/agents_2026-08-26/` — the autonomous night lab and the
  ten adversarial agent personas.
- `docs/COMPETITOR_WATCH.md` — the field.

## Rules for this index
- **Verify a path before you write it here.** A wrong path in an index costs
  more than a missing one.
- `HANDOFF.md` is a diary; the truth is code, receipts, and TIER 0.
- A commit hash quoted in a doc belongs to the repo that doc lives in. Commits
  move between `aegis-finance` and this repo only by hand.
- A new mandate, a new brain or a new state directory adds a MAP line here in
  the same session it lands, or the next session cannot find it.
