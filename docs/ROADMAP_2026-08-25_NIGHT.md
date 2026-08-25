# ROADMAP — night of 25→26 Aug 2026 (autonomous, Murat asleep, 8 hours)

Standing question for every chunk: *does this change what the agent will do on
26 Aug (NVDA print), 28 Aug (kickoff) or 4 Sep (NFP + deadline)?* If not, it is
not on the list.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done with receipt · `[-]` dropped, with why.

## Chunk 0 — validate session 3 (before building on it)
- [ ] 0.1 Re-run `tests_smoke.py`; confirm both loops alive and stamping `account_role`.
- [ ] 0.2 Grade the live day at the 20:00 UTC close: fills on both accounts, counterfactual marks, `belief_vs_chain_grade`.
- [ ] 0.3 Sanity-check the strip on one hand-computed event (NVDA 2026-05-21) — numbers in the receipt must reproduce by hand.

## Chunk 1 — RELAY, backtested before trusted
- [ ] 1.1 `scripts/relay_backtest.py`: on every originator print (NVDA, AVGO, AMD, MU), the PEERS' ATM straddles at expired closes. Did owning the print in ARM/TSM/SMH pay better than in the originator? Walk-forward ratio → tercile sort.
- [ ] 1.2 `alpha/brains/relay.py`: peer forecasts (centre 0, sd = conditional jump sd) inside the originator's event node; SHADOW by default; registered in `BRAINS`.
- [ ] 1.3 Smoke tests for both.

## Chunk 2 — ATTENTION_VOL_BASIS (review item 5)
- [ ] 2.1 `scripts/attention_vol_basis.py`: on Wikipedia z>2 days, ΔIV (ATM straddle-implied, expired bars) vs next-day |r|/IV. Promotion rule for `options_attention`/`narrative_dispersion` becomes a NUMBER.
- [ ] 2.2 Write the rule into `DEFAULT_SHADOW` logic docs (not code) — shadow until basis > 0 on ≥ 100 name-days.

## Chunk 3 — belief velocity data (review item 6), collection only
- [ ] 3.1 `scripts/belief_recorder.py` + loop hook: hourly snapshot of a watchlist of Polymarket/Kalshi markets (tariff, Fed Sep cut, payrolls ladder, NVDA >K) with volume. No brain until there is a series to grade.

## Chunk 4 — the judge-facing surface (criterion 4)
- [ ] 4.1 `scripts/dashboard.py` → `state/dashboard.html`: scoreboard, per-account positions, brain scoreboard, event card with surface `shape`, relay rank, refused/shadow screen. Self-contained HTML.
- [ ] 4.2 Write-up refresh with tonight's negatives.

## Chunk 5 — operations
- [ ] 5.1 Railway feasibility for `agent_loop` (CLI auth present? env injection?). If not deployable tonight, document the exact blocker.
- [ ] 5.2 Handoff + memory at the end; commit per chunk.

## Explicitly NOT tonight
- Any order on the competition account. Any change to `event_move`'s comparison
  (the strip lost). Any brain promoted to execute on dev without a graded reason.
