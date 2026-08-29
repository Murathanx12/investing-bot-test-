# CLAUDE.md — aegis-alpha-terminal (the EXECUTION brain)

This repo runs the six hackathon paper books. It is not the strategy: the
strategic brain, the canon and the research live in `../aegis-finance`
(`docs/AEGIS_STRATEGIC_INVARIANTS.md`, `docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`,
`docs/INDEX.md`). Read those first, then `docs/HANDOFF.md` here. The memory is
the Optimus MCP (`session_briefing()`, `brain_query`) — run it before grepping.

## The fleet (2026-08-28 → 4 Sep 11:00 ET)

`alpha/fleet.py`: hack1 ANCHOR · hack2 DRIFT · hack3 THESIS (basket) · hack4
PREDATOR · hack5 CONVEXITY · hack6 BLEND. Each runs as Railway service
`aat-loop-<role>` (project `loving-elegance`), volume `/app/state`. Deploy with
`python -m scripts.fleet --check-all` (fails closed) then
`python -m scripts.fleet --deploy all --up`. `railway logs --service aat-loop-<role>`
is the heartbeat. Machine clock is UTC+8; the venue clock is `/v2/clock`.

## Non-negotiables

- **Tests only via `python run_tests.py`** (sets `AAT_TEST_MODE=1`, which blocks
  the socket in every child). Bare `python tests_smoke_x.py` needs the env var
  set by hand. Suite: 43 suites / 1,670 checks, all green at 2026-08-29.
- `.env` is never committed. New keys → `scripts.genesis --freeze` per role
  BEFORE the first order, or the day-1 latch refuses every entry.
- Every LLM call passes `alpha/spend.py justify()` with a decision verb.
  Provider probe order: deepseek → featherless → nvidia_kimi → hf_glm; blank
  `AAT_DEEPSEEK_API_KEY` for a process to route it to Featherless.
- **Risk arithmetic before risk edits**: `per_thesis`/`aggregate` are RISK
  fractions; shares = risk/(stop+gap) capped at 25% notional per name;
  `sizing.GROSS_NOTIONAL_CAP` bounds Σ|notional| (basket 100%). Print
  `n × notional% × stop%` for the largest admissible book before changing any of
  them. 28 Aug: 300% gross × 3% stop = −9%.
- Shares are not bought 09:30–09:45 ET (`runner.in_opening_range`); the convex
  book needs ≥10 DTE and a break-even inside the market's own width.
- A refused decision is a finding; a loop that exits non-zero N times in a row
  is printed as such (`scripts.counterfactual` did, 17×, and marked nothing).
- Test fixtures derive dates from today; a literal expiry is a calendar bomb.

## Where things are

`alpha/runner.py` (entry pass, admission wiring) · `alpha/admission.py` (post-trade
caps incl. GROSS) · `alpha/engine/{sizing,equity}.py` (profiles, stops) ·
`alpha/protect.py` (stops at the venue) · `alpha/exits.py` (manage) ·
`alpha/sources/corpus.py` + `scripts/{news_backfill,catalyst_horizon,corpus_digest}.py`
(PIT observation corpus, 2025-06 → 2027-02) · `scripts/premarket_digest.py`,
`scripts/discovery_autopsy.py` (the two autopsy questions) · `state/` is the
runtime (ledger, receipts, corpus — `state/corpus/` is gitignored, regenerable).
