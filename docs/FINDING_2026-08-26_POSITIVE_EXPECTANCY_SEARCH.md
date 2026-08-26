# FINDING 2026-08-26 — the positive-expectancy search, and what the book was actually carrying

**Licence:** `PRODUCT_EXPERIMENT` throughout. Nothing here is a claim; every number is a receipt in `state/`.
**Sample:** the 117 reconstructed prints of `state/event_straddle_backtest.json` (12 names, 2024-02 → 2026-08, real expired-option daily bars, SEC 8-K dates) unless stated.

## 0. RESULTS SCOREBOARD

| item | outcome | receipt |
|---|---|---|
| **True risk of the dev book** | **72.7% of equity** ($69,878), not the 50% the sizer believed — the risk function summed long-leg cost basis and credited two NVDA condors with ~$5k of a ~$25k worst case. exp1: 58.2%. | `alpha/book.py`, `python -m scripts.pnl_attribution --all` |
| Event-node cap | was per PASS (reset every 30 min); now seeded from the book | `alpha/runner.py`, `tests_smoke_book.py` |
| Structure selection | was "largest approved risk fraction"; now MDM **gates**, `EV / max_loss` under the brain's own forecast **ranks**, risk fraction **sizes**; a structure with EV ≤ 0 after spread is refused with `CASH:` in its reason | `alpha/engine/payoff.py` |
| P&L attribution | dev −$3,219 attributed = delta −943, gamma +522, **vega −1,286, theta −1,947**, spread −1,114, residual +1,550. The NVDA condors are red on vega into the print with theta running for them; TSLA's 10-lot call is −$916 of plain delta. | `state/pnl_attribution.json` |
| Position arbiter | HOLD / CLOSE / HEDGE from remaining edge, event-aware; **advise mode** (records, does not act) | `alpha/arbiter.py` |
| Recovery mode | dev restarted `conservative` (3%/20%) with `AAT_RECOVERY=1`: vol_gap marks −6.0% on 12 live decisions → no new long premium from it; `maximum` profile refused before kickoff | `alpha/recovery.py` |
| EVENT_MISPRICING_v1 | walk-forward OOS corr +0.105, tercile spread +26.6% (**t 1.78**); univariate implied/rv20 terciles +10% / +7% / **−17%** | `state/event_mispricing.json` |
| BELLWETHER_PREMIUM_v1 | Spearman(systemic share, straddle return) **−0.57**, (share, implied/realised) **+0.60**, n=12 names | `state/bellwether_premium.json` |
| POST_EVENT_VOL_CRUSH_v1 | next-day move clears the post-print straddle **18%** of the time (paired t **−7.74**), median −6.9%, **mean +1.8%** — the tail pays the buyer on average, the seller wins 4 in 5 | `state/post_event_vol_crush.json` |
| POST_EVENT_RELAY_v1 | **peers: dead** (392 legs, t −0.6; big source moves t −0.84). **Source PEAD: alive** — 3-day excess in the direction of the day-0 move +1.13%, hit 64%, **t 2.72**, n=108 | `state/post_event_relay.json` |

**RESULT IMPROVEMENT: no P&L was made. One mechanism has a positive t for the first time (source continuation after a print); the book's stated risk is now the book's real risk; and the engine can say "cash" and mean it.**

## 1. The book was not what the sizer thought it was

`open_convex_risk()` summed the cost basis of long option legs. For a straddle that is the max loss. For a credit spread or an iron condor it is the price of the *wing*, and the short leg — the thing that loses — was invisible. `alpha/book.py` now matches every `submitted` ledger row (legs, per-unit max loss, contracts) against the venue's open legs, charges what the ledger cannot explain conservatively (a residual short at full width to its protective long; a residual short with no protective long makes the book UNBOUNDED and refuses every entry), and totals exposure per underlying and per event node.

| account | premium-paid view (old) | true max loss (new) | ceiling the sizer believed |
|---|---|---|---|
| dev | $49,382 (51%) | **$69,878 (72.7%)** | 50% |
| exp1 | $49,742 (51%) | **$56,913 (58.2%)** | 50% |

Same defect, second form: `EVENT_NODE_CAP` (25% per scheduled event) lived in a dict that was born and died with each pass. It now starts from what the book holds on that node. Third form: the champion structure was the one the sizer approved the largest fraction for, which conflates the gate with the ranker.

**The rule that comes out of it: risk is a property of the BOOK. Any number computed inside a pass and compared with a ceiling is a per-pass number wearing a book-level name.** Both live books are above every profile's aggregate ceiling, so no new entries will size until exits release capital — which is correct.

## 2. Why the positions are red (attribution, 25 Aug close)

```
dev   actual -3,219 = delta -943  gamma +522  vega -1,286  theta -1,947  spread -1,114  residual +1,550
exp1  actual -2,215 = delta +172  gamma  +60  vega -1,017  theta -2,796  spread   -614  residual +1,980
```

Long premium bled theta on a quiet day and paid ~$1.1k / $0.6k of spread to get in. The NVDA condors (dev −$439/−$542, exp1 −$437) are **vega losses with theta in their favour** — IV rose into the print and the mark moved against a short-vol position, which is the position, not the outcome. They are graded after the print, not before. The residual is positive on every long straddle: BS theta at entry IV overstates the decay a 3-day option actually showed, and the marks are mid, not bid.

Realised P&L on both accounts: **−$6** (fees). Everything else is unrealised.

## 3. The arbiter, and why it starts in advise

`alpha/arbiter.py` asks per structure: `E[value at expiry | latest forecast from the brain that opened it] − liquidation value now`. HOLD if positive after the close cost or if the event is still ahead; CLOSE if the venue pays more now than the forecast says expiry is worth; HEDGE (advisory) if a two-sided structure carries a one-sigma delta swing over 35% of its max loss.

First run on the live books: 21 HOLD, 1 CLOSE (dev's SPY straddle, edge −$38 vs close cost $9), 1 HEDGE (dev's META straddle, +91 share-equivalent delta). **The circularity is the reason it advises rather than acts:** the brain that was wrong to enter will be wrong to hold, and every live brain is currently negative. It records a verdict series every 30 minutes; promotion to `act` needs those verdicts graded against what closing would have paid.

One defect it made visible: `exits.py` judges LEGS, and a condor's short call at −38% beside its long wing at +37% is one structure. The leg-level short stop (−150% of credit) can close one wing of a condor. In `act` mode the arbiter closes structures whole and overrides a leg stop while the event is pending; in `advise` mode the leg rules stand and the conflict is logged.

## 4. The four backtests

### EVENT_MISPRICING_v1 — predict the option's error, not the stock's move
Target = the straddle's own return. Nine features knowable at the entry close (implied move, trailing 20d realised vol, their ratio, the name's prior residuals and prior straddle returns, prior-print bellwether share, 5-day drift, option volume). Ridge, standardised, λ=3, walk-forward from print 41.

- OOS corr **+0.105** (name-prior baseline +0.055), sign hit 62% vs 58%.
- Truth by predicted tercile: −12.3% / −1.0% / **+14.3%**; top−bottom +26.6%, **t 1.78**.
- "Buy when predicted > 0": n=36, mean +8.4%; the 41 avoided averaged −6.4%.
- Predicting realised−implied directly: nothing (corr −0.006). The straddle's return is the better target because it already carries the price.
- The univariate is the finding: **straddle return by implied/rv20 tercile (cheap→rich) is +10.1% / +6.7% / −17.1%.** The chain's richness against the name's own recent realised vol sorts the outcome. This is `vol_gap`'s comparison applied at print time, and it is what `event_move` should compare against instead of the last eight prints alone.

Not a claim. Seventy-seven out-of-sample prints, one λ, no multiplicity control — a `PRODUCT_EXPERIMENT` that earns a shadow brain, not a book.

### BELLWETHER_PREMIUM_v1 — is NVDA dear because NVDA moves the index?
Per name: systemic share = mean |QQQ move on its prints| / mean |own move|. Across 12 names: Spearman(share, mean straddle return) = **−0.57**, Spearman(share, median implied/realised) = **+0.60**. Direction as hypothesised; QQQ beta on the name's move does nothing (+0.03). NVDA is 4th most systemic (share 0.25, straddle −45.8%); AAPL is 1st (0.46, −16.8%); AVGO/MU/NIO carry the least index and the best straddles. Ex post, prints on which QQQ moved >2× its median paid +6.4% on the straddle; prints on which it did not, −6.5%. Twelve points is a sketch. It is consistent with "the systematic names' straddles are insurance, priced as insurance", and with where not to buy long vol.

### POST_EVENT_VOL_CRUSH_v1 — is the still-rich straddle a sale the day after?
114 post-print ATM straddles, entered at the first close reflecting the print, exited at the next close. Post-print implied is **0.59×** the pre-print level. The next-day move clears the break-even **18%** of the time (paired t **−7.74** on realised − implied): the seller wins four prints in five. But the mean long return is **+1.8%** (median −6.9%): the fifth print is the fat tail — NIO, AVGO, TSLA, AMD have +10 to +23% post-event means. An uncapped seller loses ~1.1%/print on average. **This is a high-hit, low-mean sale whose economics are decided by the wings**, which the daily bars for the ATM legs cannot price. The rich-post tercile (implied_post/rv20 highest) is 10% hit / −2.9% mean: the seller's best cut. Next step if pursued: reconstruct butterfly wings from bars for the rich tercile. Not tonight.

### POST_EVENT_RELAY_v1 — after the source reports, does a peer lag?
392 peer legs (NVDA→AMD/AVGO/MU/TSM/SMH/ARM/MRVL etc.), betas fitted on the 120 sessions before each print, forward = 3-day excess over QQQ beta. Peer residual on day 0 vs forward: corr −0.06, hit 48%, t −0.6; on source moves >5%: t −0.84. **The peer relay is dead in both directions** — no underreaction to buy, no overreaction to fade. The pre-event relay is refuted; the post-event relay is now refuted too.

**The source itself continues.** 108 source legs: 3-day excess in the direction of the day-0 move **+1.13%, hit 64%, t 2.72**, corr +0.197. That is PEAD on the printing name, the plain version of `POST_EVENT_UNDERREACTION_v1` before any LLM reads the release. By source: META t 1.69, AMD 1.12, AMZN 1.02; NVDA −1.22 and AVGO −1.71 go the *other* way — the two names whose prints move the index most (§BELLWETHER) do not drift, which is one story or is noise on eight prints each.

**The trade it licenses (shadow first):** at the first close after a print, a 3-to-5-day directional debit spread on the SOURCE in the direction of its day-0 move, sized on a +1.1% expected excess — thin against a 0.35-delta spread's cost, so the shape to test is the cheapest directional expression the chain offers, and the filter to test first is "not a bellwether".

## 5. What changes on the book tomorrow

- Both loops run the new engine on their next pass (each pass is a fresh subprocess). Dev is `conservative` + recovery; exp1 unchanged as challenger. Both are above every ceiling, so entries wait on exits.
- The NVDA condors are held through the print by design; the arbiter records HOLD-with-event-pending on them.
- The first grade that matters is still `python -m scripts.counterfactual` after Thursday's open, split by `account_role`.

## 6. Rules carried forward

1. **Risk is a property of the book.** A per-pass accumulator compared to a book-level ceiling is a bug with a comment.
2. **Gate, then rank, then size.** A probability edge beyond a break-even is admission; expected dollars per dollar of max loss is the ranking; risk fraction is the size. Cash is a structure with EV 0 and it is allowed to win.
3. **Attribute before you close.** A short-vol position red on vega with theta in its favour and its event still ahead is not a losing trade yet.
4. **The objective is not to recover yesterday's loss. The objective is to refuse every negative-EV dollar from today forward.**
