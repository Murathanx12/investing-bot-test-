# SESSION FINDINGS — 2026-08-31 (Opus) — validation pass + the band inversion

Murat asked this session to re-read everything it did, **validate it with fresh
checks rather than by agreeing with its own summary**, continue on the roadmap,
and leave findings for the main Fable session. This is that document.

---

## RESULTS SCOREBOARD (first, per canon)

- **Best new actionable finding:** the +400% band inversion (§3) — a measured,
  conditional result that reverses the pending softening decision and localises
  Murat's "lost great winners" to a specific, addressable region.
- **Structural cuts closed:** 2 (discovery→book `012a35c`; observe/execute
  split `6ad7232`), both with executed proofs, both pushed.
- **Forward paper:** hack4 flip to `tracker_portfolio` in progress by Fable
  (their session, per `32178bd`); this session touched neither Railway nor the
  seal path. Both gap-case and stop-case worst numbers now in the mandate.
- **Demonstrated edge moved:** not yet — nothing new traded this session.
- **LLM spend this session:** $0 external (all analysis on local/WRDS data).

## 1. Validation of this session's own claims — all fresh checks

| claim | fresh check | verdict |
|---|---|---|
| Suite green on merged tree | `run_tests.py` re-run after Fable's merge | **62 suites, 2,726 checks, ALL PASS** |
| `--news-universe` in no loop invocation (off by default) | grep of `agent_loop.py` | TRUE — flag appears nowhere |
| Proof 7 executes (not greps) | counted at runtime | 12/12 checks execute |
| `universe.load()` change is a no-op today | observe=4,634, execute=4,634, dropped=0 | TRUE — and stops being one after the first `build(scope="observe")` |
| hack4 gap-case −18.4% | recomputed from published seal `e6f967a...` (5 × 10% × mean 36.7% modelled 5% downside) | TRUE; Fable adopted both numbers into `fleet.py` (`c3dfc71`) |
| `ptgdetu` entitlement + scale | live WRDS query | 4,658,468 targets, 1,348 brokers, 33,043 analysts, `amaskcd` present |
| Six paper accounts | live API | hack1/2/6 flat, hack3 BE −$601, hack4 NVDA −$11, hack5 two calls −$1,680 |

One correction to a prior expectation, not a claim: my feedback (`cf2b09d` §3)
rated the >400% retraction branch likely. §3 below measured it. **It was wrong.**

## 2. What this session shipped (pointers, not restatement)

- `012a35c` — **proof 7**: news discovery reaches the placing universe.
  `inject_news_universe`, digest's own rank order, refuses on missing/stale.
  Verified on the real 08-31 file: WBUY arrives at rank 0.
- `6ad7232` — **observe ≠ execute**: `MIN_OBSERVE_DOLLAR_VOLUME` ($20k) vs
  `MIN_EXECUTE_DOLLAR_VOLUME` ($3m, unchanged); `execution_authority()` returns
  a tier + dollar cap (WBUY → OBSERVE_ONLY, $250; unknown → authorises nothing).
- `cf2b09d` — **feedback to Fable**: analyst provenance already owned
  (`ptgdetu`), purchase recommendations (no Koyfin / no InvestingPro-as-API /
  no WSJ-as-infrastructure / Quiver only as post-build benchmark), three
  timestamps rule, verdicts-vs-decisions.
- Aegis-Finance `cb3b13a` — the band experiment (§3).

## 3. THE BAND INVERSION — the finding Fable must read before its queue item 5

Full doc: `Aegis-Finance:docs/FINDING_2026-08-31_THE_BELIEVABLE_EXTREME_TARGET_IS_THE_TOXIC_ONE.md`
Receipt: `backend/data/optimus/tracker_backtest/upside_band_decontamination.json`

The brief (`2237e7c` §"400%") proposed softening the >400% hard reject into
`HIGH_UPSIDE_ANOMALY — REVIEW`, on the theory the −26.47%/yr was mostly
stale/share-basis garbage hiding legitimate 5× opportunities. **Measured: the
opposite.** 2013–2024, 434k name-months, every cell graded band-in-cell vs
all-names-in-cell, +200–400% as control band:

- **CLEAN rows (≥$2, not crashed, no split, ≥2 analysts): −41.40%/yr, t −8.94**
  — worse than the raw band. DIRTY rows: −17.03%. The garbage was *diluting*
  the damage.
- Marginal toxicity monotone in believability: −4.3pp under $1 → −47.7pp at $5+.
- **The winners Murat is right about live one band down**: +200–400% in
  cheap/crashed/thin names = +28.06%/yr t 2.55 (under-$1 cell +77.76% t 1.91)
  — already *admitted* by the 4.0 bar; it is the **execution floor** that
  excludes them, which is exactly what the observe/execute split addresses.
- The bar is well-placed: the same CLEAN cut is **+9.95% below the bar,
  −41.40% above it**.

**Queue change this implies for Fable:**
1. Brief item "replace >400% hard reject with anomaly diagnosis" → **do not
   soften for CLEAN rows.** The bar stays, now as a measured prior, not a hunch.
2. Add one data-integrity rule instead: `split_prior_year` ⇒ upside
   **UNREADABLE** in every band (only cell negative on both sides of the bar).
3. For sub-$2 / one-voice rows (WBUY-shaped): the band prior is
   **UNINFORMATIVE (t 0.39) — the engine must say "no opinion from this
   evidence", never "historically bad."** WBUY's binding constraints are target
   provenance and execution authority, not this prior.
4. The `HIGH_UPSIDE_ANOMALY` shadow book, if still wanted, should be built on
   the **+200–400% dirty cells** (where the fat tail actually is), not on 400%+.

## 4. Coordination state with the Fable session (as of writing)

- Fable sealed 08-31 (reseal sha `e6f967a62863131c`), three books fill, identity
  proven, published `df78c40`; adopted all three of my review points
  (`c3dfc71` mandate caveat with both worst cases; `b54e350` data_gaps
  provenance for tomorrow's seals).
- Fable is executing the hack4 redeploy + env flip per `32178bd`. **This
  session held `build(scope="observe")` at Fable's request** until they confirm
  the flip — it is the next unblocked action afterwards, and everything in the
  WBUY exam (CompanyState row, grading at 1/5/21/63d) is behind it.
- The 75 `rec_status=error` rows remain in the day file as observed-but-
  unreadable, blocked from candidacy — absent-vs-refused becomes distinguishable
  inside the artifact from tomorrow's seal.

## 5. Open queue, in order

1. **After Fable's flip confirmation:** `universe.build(scope="observe")`
   against the venue; then WBUY CompanyState row + multi-horizon grading.
2. **Per-broker / per-analyst skill from `ptgdetu`** — the decisive control is
   now PRE-REGISTERED and corpse-checked (PASS vs 352 prior experiments):
   `Aegis module:TRIALS/PREREG_ANALYST_SKILL_1.md` (`8be8857`). Deciding
   number: paired monthly ΔIC, NW(3) t ≥ 2.0, estimation 2013-2018 frozen,
   evaluation 2019-2024, split-crossing targets excluded from BOTH arms. No
   skill number has been computed — run the trial as written, no parameter
   moves.
3. Form 4 insider ingestion (fast clock) before politicians (slow clock);
   three timestamps (`transaction/filing/first_seen`) mandatory on both.
4. DecisionCard — `execution_authority` already supplies its capital-authority
   field; the band finding supplies its prior-vs-no-opinion semantics.
5. The 200–400% dirty-cell shadow experiment (replaces the 400%+ anomaly book).

## 6. Session lessons already persisted to memory

- `feedback_test_reachability_not_stage_correctness` — two cuts in one day,
  invisible to 2,687 green checks; pipelines need end-to-end reachability
  tests; execute the call site, never grep it.
- The band inversion joins `feedback_run_the_control_you_would_not_have_chosen`
  — second time today an instinct survived while its assumed direction flipped
  (13F was the first).
