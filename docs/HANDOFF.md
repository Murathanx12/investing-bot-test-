# HANDOFF — read this first

## SESSION 10 (26 Aug, ~07:00-10:30 ET, Fable autonomous) — the three reviews' P0-P10

**RESULTS SCOREBOARD.** Best historical net strategy: none survives — the whole-market short lane was CLOSED
by its own adversarial battery (below). Best forward paper: dev / exp1 unchanged (loops alive, PIDs 3896 /
31428, passes run as subprocesses so code changes are live). Independent selectors: still the mega-11
`post_event_drift` and the vol brains. Farm/oracle candidates tested: 1 lane attacked and closed, 1 pair
hypothesis opened, 0 promoted. New actionable finding: **a print detaches the stock from the index for a
week** (losers stay down while it rises, winners rise less) — a PAIR statement, not a short. LLM spend this
session ≈ $0.02 (4 Psychohistory records, 5 triages, 1 void record). **RESULT IMPROVEMENT: NONE in P&L;
one lane that would have bled was stopped before the competition account exists.**

**What the battery said** (`docs/FINDING_2026-08-26_PEAD_ADVERSARIAL.md`, `scripts/pead_adversarial.py`):
the +0.44%/3d "drift" was excess over β·QQQ on a tape where QQQ averaged +0.60% per window; raw +0.03%
(t 0.25); in SIMPLE returns (a short pays −(e^r−1)) the unhedged raw short is **+0.04% / +0.00%**; the pair
(short loser / long IWM) keeps +0.35% / +0.26% (t 2.2 / 2.0 iid, less clustered). Edge starts at a 5% drop
(3.5-5% dead); two-way clustered t 2.15 mid / 3.08 big on the EXCESS; **6 of 11 quarters negative; 2026 raw
negative**; UP prints RISE raw (+0.25%, t 2.5) — "good news fades" is retired. Next-open entry is right
(it misses a −0.11% bounce); drift peaks at 5 sessions; the 3% stop is harmless (+0.17% net either way).
**Code:** `post_event_drift.py` `WIDE_UNHEDGED_SHORT_ENABLED=False` — wide DOWN refused with the numbers
in the text; if ever flipped it can only quote RAW (test-pinned). The mega-11 rule is untouched.

**Selection oracle + book** (`docs/FINDING_2026-08-26_SELECTION_ORACLE.md`): 61 Nov-25 picks vs 2,343
liquidity-matched controls — no rank edge (63s median −14%, beat controls 33%); picks' pre-selection vol 72%
vs 35% (the method was a VOLATILITY screen). Biotechs β_XBI 1.4-2.0 with NEGATIVE residuals (NTLA −79%,
AARD −117% at 252d), residual corr 0.07. Agent 9: book effective N **1.85**, SLDP 50% of variance, net XBI
beta 0.00, actual weights 0.898× vs equal 1.097× vs XBI 1.977×; proposed common-shock admission test.

**Shadow tools built:** `alpha/state_change.py` + `scripts/state_change.py` — ticker-blind loser triage
(HUBS falsification case → PRICE_OVERREACTION from day-0 facts; DKS 0.65; HOV/OSIS/DKNG CANNOT_DETERMINE
without guidance/balance-sheet facts) and STATE_CHANGE_OPTIONALITY with BIO base rates as priors (needs an
EDGAR XBRL runway/dilution collector before it is scored on live names). `scripts/selection_oracle.py`.

**Preregistered / recorded:** 27 Aug AMC prints frozen in `state/event_grade/` (IREN 9.66%, AFRM 9.28%,
S 9.23%, RBRK 11.47% implied to 08-28; ESTC 13.3% to 09-18). Vol agent's prereg: BUY ESTC event variance,
SELL S up-side 22/24 bear call, REFUSE IREN/AFRM/RBRK, all conditional on ≤10% relative spread at the RTH
pass. Psychohistory: `PH:DKS:2026-08-25:e1c64749` (21-session; the earlier DKS record that bucketed the KNOWN
day-0 is VOID), HOV, OSIS, BJ (21-session; resolve with `--day0-move <horizon move>` on 19-24 Sep).

**Agent round** (`docs/agents_2026-08-26/`, six briefs): agent 1 DEPARTURE PRINT (8-K 2.02 + 5.02 C-suite,
n=48, +2.4%, post-hoc) and the log-vs-simple attack; agent 2 FINANCING_SHADOW refuted in-sample (runway <4Q
legs −0.03%; drift lives in cash-generative names) and BROKEN_NARRATIVE (DOWN print after a prior UP print,
+0.92%, week t 2.33, 10/11 quarters — **excess/log numbers; re-run in raw simple before believing**); agent 4
POST_PRINT_CALL_SIDE (post-print bear call spread; straddle paired t −7.7 never sold), DKS 130/140 Sep-18
frozen; agent 9 above; agent 10 ten non-factor strategies, build the ADR overnight residual first, and the
universe attack (max-of-4,634 noise z≈4.1/day); **agent 7 (microstructure, 15-min + full panel)**: the drift
is SESSION drift (intradays +0.28%, overnights +0.07%; the overnight after day 0 goes AGAINST the short in
every bucket), day+1 open→close is the one resolvable segment (t 4.2-4.9) — so the honest clock is short
09:45-10:00 ET, cover MOC, flat overnight (no gap charge); the UP side shows the same raw clock, so the
rival mechanism is attention (Lou-Polk-Skouras), to be settled by a non-print ≤−3.5% mover placebo; and the
attack: on INTRADAY highs (not closes) the 3% stop / 2.5% target closes 77-91% of positions, net −0.26% to
+0.20%/leg — my close-basis "stop is harmless" (§6 of the finding) was a lower bound and is superseded.
Options: none (edge < one bid-ask).

**Next:** (1) after tonight's close `scripts.daily_autopsy` runs itself; 27 Aug close → `event_grade NVDA
--post --resolve PH:NVDA:2026-08-27:b29d506d`, then IREN/AFRM/S/RBRK post-grades on the 28th; (2) build the
PAIR structure (short stock / long IWM) and re-grade the wide legs in simple returns per quarter before any
lane; (3) re-run agent 2's BROKEN_NARRATIVE and agent 1's DEPARTURE PRINT in raw simple returns with the
battery; (4) Friday evening restart both loops with `--expiry 2026-09-04`; (5) kickoff 28 Aug 15:00 UTC —
competition keys, preflight, no test order.

**Updated 2026-08-26 ~02:30 ET, session 8 (Fable, autonomous; market closed throughout).**
Competition derivative of the Aegis-Finance research project (`AEGIS_SOURCE_COMMIT=44c8352`).
Previous handoff text is in git history (`2561449`); this one supersedes it.

## SESSION 9 (26 Aug 02:30-05:30 ET, market closed) — the second review: "stop looking under the streetlamp"

**RESULT IMPROVEMENT: no P&L (market closed). Two facts that change the book: (1) BOTH PAPER LOOPS WERE DEAD —
the "two python processes" were the Optimus MCP server; the last dev entry pass was 03:30 UTC. Restarted
detached (`Start-Process`), PIDs in `state/loop_*_s9.log`. Silence had been read as health. (2) The engine now
searches the WHOLE market: HIGH_DISPERSION_US_v1 = 4,634 names, candidates every 6 h, autopsy after every close.**
Commits `038791d → c95e619`, pushed; 273 smoke checks green.

| built | what it does | first reading |
|---|---|---|
| `alpha/universe.py` | every active US common equity, price ≥ $2, median $3M/day on **SIP** (IEX volume is 2-4% of consolidated — the first build with IEX bars dropped 9 of Murat's 12 holdings), ETF-like flagged, $-volume buckets, market cap read per candidate | 4,634 members; 11/12 control holdings inside (AARD < $3M/day) |
| `scripts/candidates.py` | market-wide earnings calendar → SEC-confirmed → `post_event_drift` → ranked ticker-blind; `UNIVERSE_COLLAPSE` audit; control holdings | 152 printers / 74 in universe / **3 candidates: BJ, OSIS, HOV** — 0 from the old fifteen |
| `scripts/daily_autopsy.py` | best/worst movers, measured why (print / headlines / industry cluster), compiled why (template, knowable-before, precursor), graded against the candidate lane; templates tallied over days | 25 Aug: winners = a biotech cluster (7/15), losers = prints (DKS −31%) + retail cluster; **20/30 movers had no visible precursor; the lane held none** |
| `scripts/pead_wide.py` | source PEAD across the universe by size bucket + 10/21-session HOLD horizons | RUNNING (bars phase, ~1 h); result → `state/pead_wide.json` |
| equity semantics | `max_loss` for shares = **stress-loss charge** (stop 3% + measured p95 overnight gap, raised to the implied move when an event is inside the horizon); theoretical loss recorded; shorts UNBOUNDED on the row | NVDA into the print: 3% + 5.1% |
| Psychohistory v0.1 | evidence ids + origin roots + independence; checkpoints with due dates; edge ids persisted (`state/causal_graph.jsonl`); edge SHAPE | schema `PSYCHOHISTORY_v0.1` |
| `docs/FINDING_2026-08-26_MURATS_LIST_GRADED.md` | Murat's Nov-2025 list graded to today | watchlist +47% (XBI +56%, SPY +15%); **analyst upside Spearman 0.017**; the red-coded (target < price) names +154% (MU, MRNA); portfolio median −15% from construction |

**THE WIDE PEAD RESULT (`docs/FINDING_2026-08-26_PEAD_WIDE.md`, 2,532 names / 25,856 prints):** the two-sided
+1.13% drift is a property of the eleven mega-caps (reproduced +1.09%, t 2.72); across the market it is
5 bp. What exists instead is an ASYMMETRY — **bad news drifts, good news fades**: after a 3.5-8.2% day-0 DROP
the name keeps falling (+0.44%/3d in that direction, hit 54%, t 4.29, weekly-block t 2.30; small caps
+0.73%, t 4.08; positive in 2024/25/26; >8.2% drops +0.64%, t 5.16), after a RISE it reverses (−0.22%, t −1.99;
>8.2% −0.44%, t −3.23). `post_event_drift` now REFUSES an UP print outside the eleven and SHORTS a DOWN one
(wide numbers scaled to the sessions left; big band not discounted). Borrow (`shortable+ETB`) is the constraint.
**So the first whole-market lane is a SHORT-the-losers lane**, and 28 Aug candidates will be shorts.

**Loops:** dev `--profile conservative` + `AAT_RECOVERY=1`, exp1 challenger set; both take `--candidates`
and run `scripts.candidates` every 6 h and `scripts.daily_autopsy` after the close. **`--expiry 2026-08-28`
expires Friday — restart with `--expiry 2026-09-04` on Friday evening (and on the competition account at kickoff).**

**For the morning, added to session 8's list:** (6) read `state/pead_wide.json` — if the mid band holds t > 2
in small/mid buckets the candidate lane is measured, not borrowed; (7) `python -m scripts.daily_autopsy`
after tonight's close (the loop does it; check `state/autopsy/2026-08-26.json`); (8) `scripts.candidates`
output on 28 Aug morning is what the competition account's first pass will see.

## SESSION 8 (26 Aug 00:00-02:30 ET, market closed) — Murat's review executed in its order

**RESULT IMPROVEMENT: no P&L (market closed; both books unchanged: dev $96,160 / exp1 $97,779,
realised −$6 each). What changed: the one positive-t mechanism has an instrument that does not
eat it; the book can no longer immobilise itself; and the first Psychohistory record exists
BEFORE tonight's print.** Commits `8378503 → f06f7d7`, 241 smoke checks green (`python tests_smoke.py`).

| built | what it is | receipt |
|---|---|---|
| **SHARES as a structure** (`alpha/engine/equity.py`) | `long_shares`/`short_shares` enumerated BESIDE the options for any `direction` brain; same MDM gate, same EV/max-loss ranker, same sizer. Worst case is DECLARED: 3% stop + 2% gap allowance = 5% of spot per share, charged in the book; notional capped at 25%/name; shorts only if the venue says shortable+ETB. `book.py`, `exits.py` (stop / +2.5% target / horizon spent at 15:45 ET on the last session / orphan flattened), `attribution.py`, `arbiter.py` (skips shares) all read equity legs. | `tests_smoke_equity.py` (51). **Live probe on the real NVDA chain:** +0.72% centre vs the PRE-print 5.10% width → shares refused at **+4.5pp** (floor 5pp), exactly the doctrine's number. The first cut had scaled the width by √(horizon/dte) and let shares clear at 4.5%→5.1pp — **a jump has no √t; the width is never scaled DOWN** (commit 2). |
| **PROSPECTIVE admission** (`alpha/admission.py`) | Before any order: the POST-trade book must keep **10% of equity free** under the aggregate ceiling for a better signal tomorrow (unless the order IS the reserved event's expression), ≤15%/name (or the profile's single-thesis max), **theta burn ≤0.75%/day**, **2σ delta stress ≤10%** (delta-only, labelled). Theta/stress say `CANNOT DETERMINE` when greeks cannot be derived — never a silent pass. Refusals are ledger rows `ADMISSION: …` with the post-trade metrics. | `tests_smoke_admission.py` (27). The 25 Aug dev book replayed one order at a time: the second NVDA condor refused on CONCENTRATION, the book never passes 40%. Live dry pass on dev: greeks derived from attribution; all 5 forecasts refused (72.7% book). |
| **PSYCHOHISTORY v0** (`alpha/psychohistory.py`, `scripts/psychohistory.py`, `docs/ROADMAP_2026-08-26_CAUSAL_WORLD_MODEL.md`) | The causal compiler upstream of verification. Evidence bundle (authored facts with sources + measured: chain implied, Polymarket ladder, our brains) → DeepSeek → causal chain (confidence, lag), 3-5 scenarios each committing to a **day-0 bucket on the PEAD terciles** with **falsifiers (refused without)**, priced-in, second-order winners/losers, templates used. Folded onto five buckets and set against the CHAIN's own bucket distribution; Brier + log score for both on resolve. `SHADOW_ONLY`, no trading authority. | `tests_smoke_psychohistory.py` (24). **First record `PH:NVDA:2026-08-27:b29d506d`** ($0.0034): priced-in 0.80; surprise axis = GM ≥74% under HBM cost inflation + the guide; model tail mass **12% vs chain 20%**, mild up-skew (34/29). `python -m scripts.psychohistory show`. |
| **Component grader** (`scripts/event_grade.py`) | Width (each brain vs chain vs realised), crush (28 Aug implied/IV before→after), direction, P&L by greek per structure per account with the **share from the CLAIMED mechanism** (condor = vega+theta; straddle = gamma+vega) and the unclaimed delta, and the Psychohistory resolve. | `--pre` frozen at 05:07 UTC: chain implied **5.10%, ATM IV 0.95** (0.81 on 25 Aug → the pre-print lift the condors are red on: vega −851/−736/−720 against theta +549/+502/+443). |

**Crypto: no "round" exists.** Sat/Sun are days when crypto is the only open market; it is 25% of the
calendar and 0% of the criteria. Skipped on evidence, and the write-up says so. $99 Algo Trader Plus: still NO.

**For the morning (in order):**
1. `python -m scripts.pnl_attribution --all` (unchanged rule). The admission controller is LIVE on both
   loops' next entry pass (`run_pass` is spawned per pass, no restart needed); expect `ADMISSION:` rows
   only once exits free capital.
2. **After the 27 Aug close** (day-0): `python -m scripts.event_grade NVDA --expiry 2026-08-28 --post --resolve PH:NVDA:2026-08-27:b29d506d`
   — the condors graded by mechanism, the first Psychohistory Brier line. If bars are not final pass `--day0-move`.
3. **28 Aug, first pass after kickoff:** `post_event_drift` may fire on NVDA (day+1, needs |day-0| ≥ 3.5%).
   The chain's 28 Aug width will have collapsed; if the +0.72% centre now clears 5pp, the champion will be
   **shares**, not an option — the whole point of commit 1. If it does not clear, the record says so and cash wins.
4. Dashboard does not yet read `state/psychohistory.jsonl`, `state/event_grade/`, or `ADMISSION:` rows.
5. Not done from the review: the adversarial falsifier pass, Trade Pulse (customs by HS code), edge shapes — §5 of the roadmap.

## SESSION 7 (25 Aug ~22:00-00:30 ET, market closed) — `docs/FINDING_2026-08-26_SWEEP_OF_THE_WILD.md`

**RESULT IMPROVEMENT: no P&L. Six repos cloned and read, six papers, four new mechanisms tested on our 117 prints:**

| mechanism | verdict |
|---|---|
| PRE_PRINT_IV_RAMP_v1 — the retail "buy the run-up, sell before the print" | **REFUTED**: T-5→T-0 mean −19.5%, hit 11%, **t −12.9**; every name negative. The largest t of the week, negative. |
| PRE_PRINT_OPTION_FLOW_v1 — unsigned call−put volume before the print | dead (hit 44%); the signed version (Johnson-So) needs the tape |
| EVENT_EXIT_TIMING_v1 — sell the pre-print straddle at the day-0 OPEN | **rule**: 89% of the day-0 move is in the gap; holding the session costs −4.5% (open beats close on 62%) |
| EVENT_CALENDAR_v1 — short front straddle through the print, long the back | direction: +5.5% of debit mean, t 0.77; steep term structure +14.3% vs flat −8.9%; **NVDA +35%/6** — the one structure positive on NVDA |

The wild: `IgorGanapolsky/trading` ran 69 SPY condors to **23% win rate, −$57/trade, 0 of 39 cells survive Bonferroni** and
wrote the same "no resumption without a written hypothesis change" rule we call recovery mode. The LLM frameworks
(TradingAgents, ai-hedge-fund) never touch options. Competitor pitches name no mechanism.

**For the morning, added:** (5) a long-premium event structure exits at the first pass after the day-0 open, not the close —
the arbiter logs it today, acts only under `AAT_ARBITER=act`; (6) NVDA calendar (short 28 Aug ATM straddle / long Sep
monthly, same strike) is a SHADOW candidate for the print — not placed.

## SESSION 6 (26 Aug, ~01:00-04:00 ET, market closed) — `docs/FINDING_2026-08-26_DIRECTION_CANNOT_BE_SPENT_ON_A_CONDOR.md`

**RESULT IMPROVEMENT: no P&L (market closed throughout; both books still above every ceiling, nothing sized).**
What changed: the one mechanism with a positive t is decomposed, dated, cost-tested and BUILT AS A BRAIN — and
building it found a defect in the core gate that had nothing to do with it.

**The headline held.** Source PEAD (+1.13%, hit 64%, t 2.72, n=108) was taken apart three ways and survived all
three: **not one name** (leave-one-out t never below 2.37; the only negative name is GOOGL and dropping it RAISES
the headline to 2.86), **not clustering** (one observation per calendar week — 62 blocks, the honest n — t 2.23),
**not long drift** (the DOWN side is the stronger half: hit 72%, t 2.37, against the up side's 54% and 1.65). It
lives in the mid |day-0 move| tercile (3.5-8.2%: **t 3.45, hit 81%**) and **it dies of costs, not of doubt** —
1% of spot round-trip leaves mean +0.13%, t 0.32. The whole edge is about 1% of spot.

**And it survives arriving LATE, which is the only reason the competition can trade it.** The account is created
28 Aug; NVDA's first reflecting close is 27 Aug. The drift is flat across +1/+2/+3 (+0.41/+0.31/+0.41%) and the
overnight gap is worth **+0.05% (t 0.42)**, so a day+1 OPEN entry keeps **+1.08% of the +1.13% at t 2.82**; a
full session late still keeps +0.72% at t 2.17.

```
NEW  alpha/brains/post_event_drift.py   fires on an SEC-dated print 1-2 sessions old; refuses while the day-0 bar
                                        is still forming; quotes the LATER arrival's number when it cannot tell how
                                        late it is; refuses |move|<3.5%, halves conviction above 8.2%
NEW  scripts/source_pead_decompose.py   by name / leave-one-out / week+day blocks / day-0 sign / tercile / cost
NEW  scripts/source_pead_horizon.py     per-day drift + what each arrival keeps (the late-arrival table above)
NEW  tests_smoke_pead.py                38 checks on a SYNTHETIC planted print -- no live name has printed in the
                                        last two sessions, so the brain declines on all 15 today and that proves nothing
```

**THE DEFECT.** Probed through the real engine on a live NVDA chain, a **+0.72% forecast and a −0.72% forecast were
handed THE SAME IRON CONDOR** (EV $54 and $48 per unit — the sign of a 108-print mechanism moved the answer by $6
and changed nothing else). Cause: a brain's `sd` enters the gate as a claim that the chain has the WIDTH wrong, and
a directional brain makes that claim by accident — implied sits above trailing realised, so every long option looks
overpriced, every short-premium structure looks free, and the biggest such "disagreement" is always the structure
that cannot see a sign. `shape.py`'s own thesis failing in the mirror: not buying a tail that is not there, but
selling one it has no view on.

**Fix:** `Forecast.claim` — `direction` | `dispersion` | `distribution`, defaulting to `distribution` so every
existing brain is byte-identical. A `direction` brain is integrated at the **chain's** width (`runner.effective_sd`:
the structure's ATM implied move under the same `sigma = implied*sqrt(pi/2)` conversion the MDM gate already uses).
No quoted width **REFUSES** rather than falling back. A `dispersion` brain that tilts is refused at construction.
The arbiter now judges a position at the width it was gated at; every ledger row records its `claim`.
Now: UP → long_call / bull_call_spread / bull_put_spread; DOWN → the mirror; **the condor is gone from both sides.**

**It still refuses, and that is the honest answer.** On the 28 Aug chain the directional disagreement is 3-5pp
against a 5pp floor, and where it clears (AMD `bull_call_spread` +5.1%) **cash beats it at −$6/unit** — the same
number §1's cost table gives by another route. **But that expiry contains tonight's NVDA print**, so implied is
inflated by the event and our shift looks small against it. When the brain actually fires — 28 Aug against a
POST-print expiry, where implied has collapsed — the same centre is a larger fraction of the chain's width.
**Whether it clears then is the measurement, and it has not been made.**

**One judgement call to review:** `post_event_drift` is in `DEFAULT_BRAINS` and deliberately **NOT** in
`DEFAULT_SHADOW`. The reason that list exists is that brains which WIDEN sigma win the gate by construction; this
brain does the opposite — it cannot inflate its own edge, and after the fix it cannot claim the chain's width
either. It reaches dev on the next entry pass (the loop spawns `run_pass` as a subprocess, so code changes go live
without a restart). Exp1 runs an explicit `--brains` list and does NOT have it. Override with `--shadow` if you
disagree.

**For the morning:** (1) `python -m scripts.pnl_attribution --all` before any P&L number, unchanged; (2) NVDA
prints tonight amc → day 0 is **27 Aug** → the brain can speak **28 Aug** → the window closes **1 Sep**, inside the
competition; (3) the first thing to check on 28 Aug is whether the post-print chain lets a 0.72% centre clear the
5pp floor — if it does not, the mechanism is real and the INSTRUMENT is wrong, and the next question is whether the
underlying itself (shares, not options) is the honest expression of a 1%-of-spot edge.

## SESSION 5 (26 Aug, ~21:00–01:00 ET, autonomous) — `docs/ROADMAP_2026-08-26_STOP_BLEED.md` · `docs/FINDING_2026-08-26_POSITIVE_EXPECTANCY_SEARCH.md`

**The objective is not to recover yesterday's loss. The objective is to refuse every negative-EV dollar from today forward.**

**RESULT IMPROVEMENT: no P&L was made (market closed all session). The book's stated risk is now its real risk,
the engine can choose cash, and ONE mechanism has a positive t for the first time.** Realised P&L is **−$6 on each
account** (fees); everything else is unrealised: dev −$3,834, exp1 −$2,215, unchanged since the close.

```
TRUE max loss (new)              dev $69,878 = 72.7% of equity   (the sizer believed ~50%; the old function summed
                                 exp1 $56,913 = 58.2%             long-leg cost basis and could not see a short leg)
attribution, dev  -3,219 attrib  delta -943  gamma +522  VEGA -1,286  THETA -1,947  spread -1,114  residual +1,550
attribution, exp1 -2,215         delta +172  gamma  +60  VEGA -1,017  THETA -2,796  spread   -614  residual +1,980
NVDA condors (dev -981, exp1 -437)  red on VEGA into the print, THETA running FOR them -> held through the print by design
TSLA 10-lot call (dev -1,160)       -916 of plain delta; nothing to attribute it to but the forecast
arbiter (advise)                 21 HOLD, 1 CLOSE (dev SPY straddle, edge -38 vs cost 9), 1 HEDGE (dev META, +91 delta)
dev loop                         RESTARTED 21:01 ET: --profile conservative, AAT_RECOVERY=1 (vol_gap marks -6.0% on 12
                                 live decisions -> no new long premium from it); exp1 loop untouched (aggressive challenger)
entries tomorrow                 NONE will size on either book until exits release capital: both are above every ceiling
first grade that matters         NVDA prints 26 Aug amc -> python -m scripts.counterfactual after Thursday's open, by account_role
```

**Code (4c7cf3f, 26f1bdb, +):** `alpha/book.py` (true structure-level max loss from ledger+positions; residual shorts at full
width; unbounded → refuse), `alpha/engine/payoff.py` (EV / max-loss ranker: MDM gates, EV ranks, risk fraction sizes; EV ≤ 0
after spread → `CASH:` refusal), `alpha/recovery.py`, `alpha/attribution.py` + `scripts/pnl_attribution.py`,
`alpha/arbiter.py` (HOLD/CLOSE/HEDGE from remaining edge, event-aware across brains, records every 30 min, **advise mode**;
`AAT_ARBITER=act` to let it close whole structures and override leg stops while an event is pending), `maximum` profile
refused before kickoff. Event-node cap now seeded from the book. 68 new smoke checks (`tests_smoke_book.py`,
`tests_smoke_arbiter.py`), every suite green.

**Research (all `PRODUCT_EXPERIMENT`, receipts in `state/`):**

| mechanism | verdict | number |
|---|---|---|
| EVENT_MISPRICING_v1 (walk-forward ridge on 117 prints) | direction, not significance | OOS corr +0.105, tercile spread +26.6% (t 1.78); implied/rv20 terciles **+10 / +7 / −17%** |
| BELLWETHER_PREMIUM_v1 | direction as hypothesised, n=12 names | Spearman(systemic share, straddle) **−0.57**; (share, implied/realised) **+0.60** |
| POST_EVENT_VOL_CRUSH_v1 (114 next-day straddles) | seller wins 82% of days, loses the mean to the tail | hit 18%, paired t −7.74, median −6.9%, **mean +1.8%**; wings decide it |
| LOCK_THE_JUMP_v1 (28 NFP days) | **refuted** — the gap EXTENDS; do not hedge the straddle at 08:31 | corr +0.42; \|move\| 0.39 → 0.45 → 0.72% (t −3.6) |
| POST_EVENT_RELAY_v1 — peers | **dead both ways** (retired with the pre-event relay) | 392 legs, t −0.6; big moves t −0.84 |
| POST_EVENT_RELAY_v1 — **source PEAD** | **first positive t on record** | 3-day excess in day-0 direction **+1.13%, hit 64%, t 2.72, n=108** |

**Not done:** SURFACE_MOMENT_SHOCK (needs 4-6 strikes × 117 prints of bars), the LLM half of POST_EVENT_UNDERREACTION, the dashboard rebuild (it does
not read the new receipts yet), Railway (still yours).

**For the morning:** (1) `python -m scripts.pnl_attribution --all` before reading any P&L; (2) NVDA grades after the
print — condors first, then `scripts.counterfactual` by role; (3) if the source-PEAD shape holds on NVDA's day-0 move
(27 Aug close), that is the first shadow trade to write as a brain, filtered "not a bellwether"; (4) decide whether the
arbiter earns `act` from its recorded verdicts.

## NIGHT SESSION 4 (25→26 Aug, autonomous) — `docs/ROADMAP_2026-08-25_NIGHT.md` has the chunk status

**RESULT IMPROVEMENT: one more idea killed before it cost money, two live-book defects
fixed, the 4 Sep trade frozen. P&L: NEGATIVE on the day** — dev $96,160 (−$3,834
unrealised, 22 legs), exp1 $97,779 (−$2,215, 15 legs); a quiet Tuesday bled every long
straddle and the NVDA condors sit on pre-print IV lift. At equal risk across all marked
worlds, no brain was positive (vol_gap −3.7% of risk, attention −6.8% at 16% hit); the
refusal gate carried +0.8%. The NVDA print on 26 Aug is the first grade that matters. The RELAY is refuted on 290 real relay legs (mean −4.2%,
hit 34%, t −2.0; the ratio does not sort — `docs/FINDING_2026-08-26_RELAY_REFUTED.md`), so the
afternoon's ARM/TSM ranking stays shadow. Reading the live book found that one-position-per-
symbol was per PASS (dev re-bought QQQ x4→x8, a second NVDA condor) and that two loops on one
unlocked hash chain broke it at line 1203 — both fixed and tested, corrupt lines counted not
rewritten. Dev then hit the 50% cap on a Tuesday → `EVENT_RESERVE` keeps 10% for 4 Sep.
Built: `scripts/nfp_trade.py` (frozen contract, two gates, entry window enforced),
`scripts/dashboard.py` → `state/dashboard.html` (published privately at
https://claude.ai/code/artifact/36440187-1bf4-4230-b116-b1c3782a65e9 — rebuild + republish to refresh), `scripts/belief_recorder.py` (hourly crowd
series), `scripts/attention_vol_basis.py` → **basis +0.07 IV-units, t 1.62 on 383 spikes: the chain is
already 10% wider on attention days, attention brains stay shadow on dev**
(`docs/FINDING_2026-08-26_ATTENTION_VOL_BASIS.md`), `Dockerfile` +
`railway.toml` (prepared, **not deployed** — your call: keys to a cloud host, one role per host).

## SESSION 3 IN ONE PARAGRAPH (read `docs/FINDING_2026-08-25_SURFACE_AND_STRIP.md`)

The review's priority list was executed in order and most of it came back
NEGATIVE, which is the point. Walk-forward on 112 real prints: **stripping the
event variance did not beat the naive comparison** (raw implied predicts
realised size at corr 0.33; the stripped jump 0.18; our own history 0.29 — the
chain knows more than the name's last eight prints); **no short structure is a
free lunch** (iron butterfly +5%, t 0.7; the condor wins 63% and loses money);
the morning's conditional sort **survives weakly and on the SHORT side** (n=46,
+15%, hit 61%, t 1.41 — bottom-tercile butterfly +21%); **skew predicts nothing**
(45%); concave surfaces reproduce the RoF 2025 direction weakly. The
**UNCERTAINTY RELAY** produced its first ranking for tomorrow's NVDA print: NVDA
itself is the most expensive place to own it (ratio 0.70), ARM 1.64 and TSM 1.52
the cheapest. The **NFP event-contract basis is built and its direction channel
is dead** (surprise→SPY corr 0.03, −0.57 walk-forward); Kalshi can inform width,
never side. In code: `alpha/surface.py` (geometry + strip, tested on a planted
jump), `EVENT_NODE_CAP` 25% per scheduled event in the runner (tested), the loop
takes `--brains/--shadow` so **dev runs the champion and exp1 the challenger —
both loops are LIVE on paper as of 15:30 UTC** (`state/loop_dev.log`,
`state/loop_exp1.log`), and one full unattended cycle was proven before that.
NFP is now "our strongest observed long-vol macro candidate", not "the one tail".

---

## COMPETITION SCOREBOARD

```
competition account equity      NOT YET CREATED (create at kickoff 28 Aug 15:00 UTC)
dev account                     PA32Q5IW7TAS  $100,000  options level 3
experiment account exp1         PA3AOJPJTSBW  $100,000  options level 3
competition return              n/a
best live strategy              none proven -- ONE rehearsal fill (TSLA 350 straddle x3), see FILL
best shadow strategy            NOT YET GRADED -- shadow ledger started today, first marks land after
                                the NVDA print (26 Aug amc)
active independent brains       4 of 4 planned: vol_gap · event_move · options_attention · narrative_dispersion
                                (2 executable, 2 shadow-only until they beat the others on the counterfactual)
independent DATA sources        price/chain (Alpaca) · fiscal calendar (Finnhub) · option tape (Alpaca bars)
                                · news + LLM (Benzinga/DeepSeek) · attention (Wikipedia/HN/Mastodon)
                                · belief (Polymarket/Kalshi) · positioning (CBOE)
options trades / win-loss       1 filled (TSLA straddle x3 @13.35, slippage 0) / 0-0 (open, -$105 @ +17m)
max drawdown                    n/a
LLM calls / spend               ~6 / ~$0.004   ($0.0007 per NARRATIVE_SHOCK extraction, 2.4s)
execution failures              0
service uptime                  not deployed; `scripts/agent_loop.py` PROVEN for one full cycle
                                (--once) and running LIVE on both paper accounts since 15:30 UTC
                                25 Aug from this laptop (nohup; dies with the laptop -- Railway
                                is still the gap). dev = champion set, exp1 = challenger set.
MCP / CLI requirement           the rule is MCP **OR** CLI. We ship BOTH because the MCP side is a
                                risk gate (44 tools exposed, no order verb). Neither is mandatory alone.
counterfactual worlds marked    136 (session 1) + today's dry-run families; brain scoreboard added
submission readiness            engine + 4 brains + exits + MCP/CLI + counterfactual + event card;
                                no dashboard, no write-up, no social post
COMPETITION RESULT IMPROVEMENT  A LOSING TRADE WAS WITHDRAWN BEFORE IT WAS PLACED. The NVDA
                                straddle event_move planned at 18.5% risk lost on 0 of 8 real
                                prints (docs/FINDING_2026-08-25_STRADDLE_BACKTEST.md). Four
                                brains live, one fill measured at zero slippage, feed is seconds
                                late. Still zero P&L evidence; the evidence is now about what NOT
                                to do, which is worth more this week.
```

## THE AFTERNOON'S FINDINGS (25 Aug) — read before touching event_move

1. **Real straddle backtest, 117 prints, 2024–26** (`scripts/event_straddle_backtest.py`,
   expired option bars + SEC 8-K Item 2.02 dates): the chain OVERprices mega-cap
   prints — median straddle **−18%**, 43% clear break-even, paired t −2.24.
   **NVDA 0/8, median −46%.** AVGO the opposite (+32% mean, 5/8). The conditional
   sort (name's own prior history − implied) is two-sided: top tercile +16%,
   bottom −7%. `event_move` now weights the last 8 prints and **refuses NVDA**.
2. **Exact print dates from SEC** (`alpha/sources/sec.py`, no auth): the inferred
   dates had padded NVDA with the DeepSeek selloff. Inference is now the 6-K
   fallback only.
3. **Attention widens** (`scripts/attention_backtest.py`, receipt in
   `state/attention_backtest.json`): Wikipedia z>2 → next-day |r| 262bp vs 195bp,
   direction −8bp vs +15bp. The attention brains' shape (sigma up, no sign) has a number.
4. **Exposure graph graded** on the 24 Aug tariff: F/GM/STLA right, the uncertain
   TSLA edge wrong → sign zeroed. Uncertain edges carry no sign.
5. **Belief vs chain** (`scripts/belief_vs_chain.py`): NVDA >$215 today, crowd 40%
   vs chain 23%. Recorded hourly by the loop, graded by `belief_vs_chain_grade`.
6. **Research sweep** (`docs/SOURCES.md` addendum below): unconditional
   pre-earnings straddles are dead net (−9.1%, BSIC); **NFP-day index straddles
   were underpriced 10/12 recently** — the 4 Sep 08:30→10:45 window is the one
   trade to spend variance on; `scripts/nfp_straddle_backtest.py` grades it on
   2024–26 0DTE minute bars: **SPY mean +16.8%, median +6.8%, 57% hit, 9 of the
   last 12 positive; QQQ mean +17.1%, median −2.6%.** A tail payoff — buy narrow,
   bounded premium, flat by 10:45 (addendum in the FINDING doc).
   Kalshi is calibrated with favourite-longshot bias. NVDA→AVGO IV spillover
   (Guttormsen 2026) is being watched: `state/iv_spillover_watch.jsonl` has the
   pre-print baseline. Crypto weekend sleeve: skipped on evidence.

**The $99: NO.** Slippage 0.00 on the one fill; quote age 3–4 s all session.
Buy it only if a reaction trade is ever wanted at the 08:30 print itself.

### THE FILL (the measurement that decides the $99)

`state/fills.jsonl`, `state/fill_audit_open.log`, `state/parity_probe_open.json`.

| | |
|---|---|
| decision quote (Mon 19:59 ET, indicative, 15h old, market closed) | call ask 6.25 + put ask 7.10 = **13.35** |
| order | TSLA 350 straddle ×3, limit 13.35, `mleg`, day |
| fill | **09:30:02 ET Tue, 13.35** — call 6.85 + put 6.50 (TSLA opened +0.8%, the venue re-split the legs at the limit) |
| package slippage | **0.00 / unit, $0, 0% of expected edge** (n = 1, a limit fill AT the limit) |
| mark +17 min | exit at bid 13.00 → **−$105 on $4,005** (−2.6% ≈ the round-trip spread) |

**And the feed is not fifteen minutes late.** Measured at 09:33 ET with the
market open: NVDA chain **median quote age 3.4 s**, TSLA **3.7 s**; put-call
parity gap **+0.07% / −0.02%**. The −1.34% gap in the NVDA card was the stale
after-hours snapshot, not the live feed. A 30-minute quote-age sampler runs in
`state/quote_age_probe.json`; if it holds at seconds, `chain.py`'s "reactions
cannot be traded" caveat and the staleness penalty are over-cautious and the
`$99` question is closed at "no" on measured evidence rather than on hope.

---

## What changed today, and what each thing is for

### 1. Three new brains — independent by DATA SOURCE, not by formula

| Brain | Reads | Says | Status |
|---|---|---|---|
| `vol_gap` | daily bars | EWMA realised vs implied; damped drift | executable |
| **`event_move`** | SEC 8-K Item 2.02 dates (+ Finnhub/inference fallback) + bars | this name's OWN last-8-print history vs the chain. Recent mean: NVDA **3.8%**, AVGO **10.7%**, PANW **5.0%** close-to-close. Centre 0. Two-sided: narrower than the chain → the sizer picks short premium. | executable |
| **`options_attention`** | Alpaca option daily bars | unsigned volume on SEASONED contracts vs trailing median; NVDA **3.49x** into the print. Widens sigma, never tilts. | shadow-only |
| **`narrative_dispersion`** | Alpaca/Benzinga news → DeepSeek → `NARRATIVE_SHOCK_v1` axes + Wikipedia attention | truth · belief · impact · already-priced → **belief-gap case**; disagreement + truth-uncertainty widen sigma. LLM emits axes, never a trade. | shadow-only |

Event dates come from **SEC 8-K Item 2.02** filings (exact, with release time).
The morning version inferred them from price and padded NVDA's list with the
2025-01-27 DeepSeek selloff — caught because the dates are printed on every
forecast. Inference remains only for 6-K filers (NIO).

**Why two brains are shadow-only:** the sizer rewards disagreement with the
chain, and on long premium a WIDER sigma is a bigger disagreement. A brain that
widens by construction wins the enumeration by construction. Attention and
narrative earn execution by beating the others on `brain_scoreboard` in
`python -m scripts.counterfactual`, not by being loudest. Set `--shadow ''` to
override once they have.

### 2. The demo that fell out of it — NVDA into tomorrow's print

`state/cards/NVDA_2026-08-25.json` (`python -m scripts.event_card NVDA --expiry 2026-08-28 --query nvidia`):

- **`vol_gap`** (realised 3.8% < implied 5.1%) chose an **IRON CONDOR** this morning.
- **`event_move`** (morning version: event prior 11.3% > implied 5.4%) chose a **LONG STRADDLE** at 18.5% risk — **WITHDRAWN in the afternoon** once the real-option backtest showed NVDA straddles 0/8 on recent prints; the corrected brain (recent mean 3.8%, sd 5.7% vs 5.0% implied) now REFUSES it.
- **Polymarket** prices Q2 gross margin 74–76% at 93% and Data Center >$80B at 94% — the crowd sees a low-surprise print.
- **Attention**: Wikipedia pageviews velocity 1.49 (z 1.55), HN 26 stories/33 comments in 48h, option volume 3.49x.
- **Parity gap −1.34%** on the 212.5 straddle at the stale close: the IEX print and the indicative quotes disagreed by $2.8 — the open tells which was stale.

Same chain, opposite instruments, both written before the print — and then one
of them was withdrawn on evidence before the print, which is a better story
than either winning. The shadow ledger still grades both.

### 3. Sources — measured today (`docs/SOURCES.md`)

Works without auth: Alpaca news/option bars/option trades, Finnhub free,
**Polymarket**, **Kalshi**, **CBOE** put/call + VIX term structure, Wikipedia
pageviews, HN Algolia, Mastodon, SEC submissions, DeepSeek. Refused: Reddit,
StockTwits, GDELT, LunarCrush (paywall), Finnhub social, Bluesky search and SEC
full-text (403 from HK — retest from a US host).

Two consequences: **public belief is now a PRICE** (prediction markets) rather
than an LLM guess, recorded beside the LLM's `market_belief` so their
disagreement is a finding; and **social sentiment proper is closed from here**,
so the narrative brain reads news and lets the LLM estimate dispersion — an
admitted substitute for the Twitter/StockTwits corpus the literature used.

### 4. Runner: several brains, one position per symbol, nothing averaged

`alpha/runner.py`: every brain's enumeration recorded under its own decision
id; the champion is the largest approved risk among EXECUTABLE brains; losers
written as `action=shadow` naming the winner; every forecast written to
`state/forecasts.jsonl` BEFORE any structure is priced. `counterfactual.report`
now carries `brain_scoreboard` (n, pnl, mean return on risk, hit rate) over
taken + dry-run + shadow worlds at equal risk.

### 5. Fill audit, parity gap, event card, loop

- `python -m scripts.fill_audit --record` — decision ask vs fill vs mark at the bid, slippage as a fraction of expected edge (n=1 stated as n=1).
- `ChainSnapshot.parity_gap(expiry)` on every ledger row. Diagnostic only; a guard comes after a measured failure, not before.
- `python -m scripts.event_card SYMBOL --expiry …` — the dashboard-readable record a judge asked for.
- `python -m scripts.agent_loop --expiry … [--live]` — exits/5m, entries/30m, counterfactual/60m, fill audit/15m, clock from the venue. **Unproven overnight.**

---

## Step by step — what Murat does, in order

1. **Now — nothing on accounts.** Rotate the leaked LIVE keys (`AK32UD5…`, account 349598088) at app.alpaca.markets if not already done.
2. **Wed 26 Aug:** the NVDA straddle is WITHDRAWN (event_move refuses it). What is live
   instead, from the first champion/challenger pass at 15:30 UTC 25 Aug: **dev** holds
   TSLA 350 straddle x3 + QQQ straddle (vol_gap, 5.3%); **exp1** holds SPY straddle
   (narrative_dispersion, 12.1%), QQQ straddle (options_attention, 9.7%), IWM straddle
   (narrative_dispersion, 10.0%). Same instrument on QQQ at twice the size on exp1 —
   that is the comparison. Read `python -m scripts.uncertainty_relay NVDA --event
   2026-08-27 --expiry 2026-08-28` before the print: ARM/TSM are where the print is cheap.
3. **Thu 27 Aug:** `python -m scripts.counterfactual` → `brain_scoreboard`, split by
   `account_role` (stamped on every decision row from this commit on). Re-run the
   relay after the print for the IV-spillover grade (`state/iv_spillover_watch.jsonl`).
4. **28 Aug, kickoff (15:00 UTC = 23:00 HK):** re-pull rules; create the brand-new $100k account; `AAT_COMPETITION_KEY_ID/SECRET`; `AAT_ACCOUNT_ROLE=competition python -m scripts.preflight`; **never a test order on it**.
5. **First social post** the same day — separate $500 prize, engagement cannot be back-filled.

## Next, in priority order (session 3 re-cut)

1. **Grade the NVDA print** — brain-vs-brain AND account-vs-account, from `brain_scoreboard`
   and `state/fills.jsonl`. Also the relay: did ARM/TSM move more per dollar of implied
   than NVDA?
2. **Railway deploy** of `agent_loop` — both loops run from this laptop under nohup and die
   with it. This moved up: the loops are now the evidence engine.
3. **ATTENTION_VOL_BASIS** (review item 5) — not built. `attention_backtest` stores only
   summaries; it needs the ATM straddle close on each z>2 day (expired bars) to measure
   Δimplied against Δrealised. Until then attention/narrative execute only on exp1.
4. **RELAY as a brain**: `uncertainty_relay` is a script; to be sized it must emit a
   `Forecast` on the peer (centre 0, sd = conditional jump sd) inside the originator's
   event node so `EVENT_NODE_CAP` binds across NVDA + ARM + TSM.
5. **NFP 4 Sep** — `event_contract_basis` before the 3 Sep close; take the 0DTE straddle at
   the prior close only if the crowd's ladder is wide (two 15% tails today) AND the 0DTE
   implied is at or below the 0.77% median; flat by 10:45. Width only; no side.
6. **Dashboard** from event cards + surface `shape`; **write-up** leading with the negatives
   (this session produced four).
7. **Belief-velocity / rumour half-life** (review items 6–7): unbuilt; shadow-only if built.
8. Crypto sleeve, Bluesky/EFTS re-probe from the deploy host — unchanged, low.

## Do NOT

- Do not let `options_attention` or `narrative_dispersion` execute before they lead `brain_scoreboard` on marks older than a session.
- Do not average brains. Do not build a bull/bear debate. Do not use market orders. Do not exploit paper-fill mechanics.
- Do not read the free feed's closing quotes as live: the parity gap says the options and the underlying can disagree by 1.3% at the close.
- Do not continue the ordinary Aegis roadmap this week.
