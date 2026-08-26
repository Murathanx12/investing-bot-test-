# ROADMAP — 26 Aug 2026: STOP BLEED, FIX OBJECTIVE, FIND POSITIVE OPTION EXPECTANCY

The review's fifteen items, in its order. Status: `[x]` done with receipt · `[~]` partial · `[ ]` not started · `[-]` dropped, with why.
Full findings in `docs/FINDING_2026-08-26_POSITIVE_EXPECTANCY_SEARCH.md`.

- [x] 1. **Live-book risk accounting.** `alpha/book.py` reconstructs structure-level TRUE max loss from ledger + positions; residual shorts charged at full width; unbounded → refuse. Dev 72.7% (sizer believed ~50%), exp1 58.2%. `tests_smoke_book.py`.
- [x] 2. **EVENT_NODE_CAP is book-level.** `node_committed` seeded from `book.by_node`; new `submitted` rows carry `outcome.event_node`. Legacy rows (25 Aug) carry none — the NVDA condors count under NVDA, not under `print:2026-08-26`.
- [x] 3. **Gate / rank / size split.** `alpha/engine/payoff.py`: piecewise terminal payoff integrated over the brain's forecast → EV, EV/max-loss, P(profit), median, ES5, P(max loss), P(+50%), spread. MDM gates, EV/max-loss ranks (within a brain's structures AND across brains on a symbol), risk fraction sizes. Economics on every ledger row (`outcome.economics`).
- [x] 4. **Cash is a champion.** EV ≤ 0 after spread → refused with `CASH:`; `PassResult.cash` counts it.
- [x] 5. **PNL_ATTRIBUTION_v1.** `alpha/attribution.py`, `python -m scripts.pnl_attribution --all --json`. Realised −$6 both books; NVDA condors red on vega with theta for them.
- [x] 6. **POSITION_ARBITER_v1** in **advise** mode (records every 30 min; `AAT_ARBITER=act` to act). Event-aware across brains' forecasts. SWITCH not evaluated (said in the docstring). Leg-level exits found to be able to close one wing of a condor — handled in act mode, logged in advise.
- [x] 7. **Dev in recovery.** Restarted `--profile conservative` with `AAT_RECOVERY=1` (negative brain → no new long premium; two consecutive live losses → shadow). `maximum` refused before kickoff without `AAT_ALLOW_MAXIMUM=1`. Exp1 left as the aggressive challenger (8%/50%); the review's "~30% aggregate" for it is NOT applied — it is already at 58% true and cannot add until exits release, so the change would bind nothing tonight and the envelope stays as declared.
- [x] 8. **EVENT_MISPRICING_v1** — `scripts/event_mispricing.py`. Walk-forward ridge, OOS corr +0.105, tercile spread +26.6% (t 1.78). Univariate implied/rv20 terciles +10 / +7 / −17%. Shadow-brain grade, not a book.
- [x] 9. **POST_EVENT_VOL_CRUSH_v1** — `scripts/post_event_vol_crush.py`. Seller wins 82% of next days (paired t −7.74) and loses the mean (+1.8% long) to the tail. Needs wing bars to price the butterfly; rich tercile is the cut.
- [~] 10. **POST_EVENT_UNDERREACTION_v1** — the plain numeric half is done inside `scripts/post_event_relay.py` (`source_pead_day0`): **+1.13% 3-day excess, hit 64%, t 2.72, n=108**. The LLM semantic half (beat quality, guidance) is NOT built. The first grade of the numeric half on a live print is NVDA tonight → 27 Aug close → 1 Sep.
- [x] 11. **POST_EVENT_RELAY_v1** — peers dead both ways (t −0.6; big moves t −0.84). Pre-event and post-event relay are both retired from current search.
- [x] 12. **BELLWETHER_PREMIUM_v1** — `scripts/bellwether_premium.py`. Spearman −0.57 / +0.60 on 12 names, direction as hypothesised. Explains NVDA; says where not to buy vol.
- [ ] 13. **SURFACE_MOMENT_SHOCK_v1** — needs historical skew/kurtosis series per print; the bar feed prices named contracts only, so it means reconstructing 4-6 strikes per print × 117 prints. Not tonight.
- [ ] 14. **LOCK_THE_JUMP_v1** — needs 08:30–09:30 extended-hours SPY minute bars beside the 0DTE straddle bars `nfp_straddle_backtest` already pulls. Feasible; not tonight.
- [x] 15. **$99 Algo Trader Plus: NO** stands.

## Explicitly NOT done tonight
- No order on any account by hand. No change to exits' leg-level stops (the arbiter advises).
- No brain promoted. EVENT_MISPRICING and source-PEAD are candidates for SHADOW brains; neither is built as a brain yet.
- Railway: still Murat's call.
