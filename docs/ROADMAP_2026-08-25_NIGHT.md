# ROADMAP — night of 25→26 Aug 2026 (autonomous, Murat asleep, 8 hours)

Standing question for every chunk: *does this change what the agent will do on
26 Aug (NVDA print), 28 Aug (kickoff) or 4 Sep (NFP + deadline)?* If not, it is
not on the list.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done with receipt · `[-]` dropped, with why.

## Chunk 0 — validate session 3 (before building on it)
- [x] 0.1 `tests_smoke.py` ALL PASS; both loops alive; `account_role` stamped on rows from 16:03 UTC.
- [ ] 0.2 Grade the live day at the 20:00 UTC close (loops run counterfactual hourly; read `brain_scoreboard` + fills after).
- [x] 0.3 NVDA 2026-05-21 strip reproduced by hand: σ_f 1.00, σ_b 0.56, a 0.123, √J 6.95%, butterfly +88%.
- [x] 0.4 **Found and fixed two defects by reading the live book**: one-position-per-symbol was per PASS (dev re-bought QQQ x4→x8 and a second NVDA condor; now per BOOK, tested) and two loops wrote one hash chain unlocked (broke at line 1203, six interleaved lines; now an O_EXCL lock, malformed lines counted not rewritten, tested).

## Chunk 1 — RELAY, backtested before trusted
- [x] 1.1 `scripts/relay_backtest.py` → **REFUTED**: 290 relay legs mean −4.2%, hit 34%, t −2.0; the ratio does not sort. `docs/FINDING_2026-08-26_RELAY_REFUTED.md`.
- [x] 1.2 `alpha/brains/relay.py` registered, SHADOW with the reason in its docstring; forecasts land in the originator's event node.
- [x] 1.3 Smoke tests (map, registry, shadow default, node).

## Chunk 2 — ATTENTION_VOL_BASIS (review item 5)
- [x] 2.1 `scripts/attention_vol_basis.py`: 383 spikes vs 1,023 controls, basis +0.069 IV-units, **t 1.62 < 2 → not promoted**. The chain is already ~10% wider on attention days; ΔIV is negative INTO the spike (pageviews lag the chain). `docs/FINDING_2026-08-26_ATTENTION_VOL_BASIS.md`.
- [x] 2.2 Recorded in the handoff; write-up unchanged (its "attention widens" claim stands, its trade does not).

## Chunk 3 — belief velocity data (review item 6), collection only
- [x] 3.1 `scripts/belief_recorder.py`: 350 markets per snapshot (Polymarket ×7 queries, Kalshi payrolls/Fed), hourly from the loop → `state/belief_series.jsonl`.

## Chunk 4 — the judge-facing surface (criterion 4)
- [x] 4.1 `scripts/dashboard.py` → `state/dashboard.html` (accounts, decisions incl. refusals/shadows, scoreboard, card, relay, receipts, crowd).
- [x] 4.2 `docs/WRITEUP.md` refreshed: eight receipts, six negative, two accounts two champions.

## Chunk 5 — operations
- [x] 5.1 Railway: CLI logged in; `Dockerfile` + `railway.toml` written; **NOT deployed** — pushing paper keys to a cloud host and running a second copy beside the laptop loops is Murat's call (one role, one host).
- [x] 5.2 `scripts/nfp_trade.py`: the 4 Sep trade as a frozen contract (policy hash = sha256 of the file), two measurable gates (0DTE implied ≤ 0.85%, Kalshi tail mass ≥ 25%), entry window 3 Sep 15:45–16:00 ET enforced, ordinary engine downstream, `manage.py` flattens at 10:45.
- [ ] 5.3 Handoff + memory at the end; commit per chunk (done so far: a469dc7, a2e447a, +).

## Explicitly NOT tonight
- Any order on the competition account. Any change to `event_move`'s comparison
  (the strip lost). Any brain promoted to execute on dev without a graded reason.
