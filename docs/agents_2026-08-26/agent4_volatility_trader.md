# AGENT 4 — VOLATILITY TRADER (adversarial round, 2026-08-26)

Written 26 Aug ~13:00 UTC, market closed. Every chain number below was read from the paper account through
`alpha.data.chain.fetch` (feed `indicative`, quotes ~11 h old, `market_open=False`) and every print history from
SEC 8-K Item 2.02 via `event_days_from_sec`. Nothing was placed, nothing outside this file was modified.
I do not care whether DKS or AFRM is a good business. I care whether the chain's distribution and the likely
realised one differ by more than the spread.

**Three facts from this repo's own receipts that the rest of this document is built on:**

| receipt | fact | what a vol desk reads from it |
|---|---|---|
| `state/event_straddle_backtest.json` (117 prints) | pre-print straddle median −18%, 43% clear break-even, paired t −2.24; **two-sided by name** (NVDA 0/8, AVGO +32%); conditional sort history−implied top tercile +16% / bottom −7% | the pre-print surface is fair-to-rich on average and the *sign of history minus implied* is the only pre-print signal that paid |
| `state/post_event_vol_crush.json` (114 prints) | straddle bought at the **day-0 close** (post-print): median −6.9%, **17.5% clear break-even, paired t −7.74**, implied_post/pre = 0.59 | **the post-print surface is the richest thing in the repo** — the day after the print the chain still prices 4.2% and delivers less, at t 7.7. That is three times the t of anything the directional side owns |
| `state/pead_wide.json` (25,856 prints) | DOWN 3.5–8.2%: +0.44%/3d t 4.29; >8.2%: +0.64% t 5.16; UP reverses t −2.0/−3.2 | outside the mega-11 the up-tail after a print is *over*priced twice: by the crush AND by the fade. The down-tail is the only side with realised follow-through |

So: post-print, sell the CALL side. Never buy the post-print surface. That is the strategy, the attack, and most of
the preregistration.

---

## 1. STRATEGY — POST_PRINT_CALL_SIDE_v1 ("sell the side that fades on the surface that crushes")

**Economic mechanism.** Two independent overpricings stack on the same leg. (a) Post-print IV does not finish
crushing at the day-0 open: the day-0-close straddle still loses 82.5% of the time (t −7.74) — dealers keep the
event premium bid for another session because the flow that bought pre-print convexity is closing, not opening.
(b) Direction: outside the mega-11 an UP print reverses (t −3.2 big band) and a DOWN print continues (t +5.2), so
whichever way the print went, the *upside* over the next three sessions is the side realised returns do not visit.
A short call spread on day+1 is short vega (a), short delta in the direction the tape follows (b), and long theta,
with contractual max loss. It is the mirror of what the repo has measured to lose, with the sign the wide PEAD says.

**Exact signal (three conditions, all mandatory).**
1. SEC 8-K 2.02 print with first reflecting close = day 0, |r_0| ≥ 5% (either sign; DOWN preferred, UP allowed
   outside `MEGA_MEASURED` only).
2. Post-print richness: ATM IV of the expiry 10–25 calendar days out, at the day+1 15:30 ET pass, **≥ 1.15 × the
   name's 60-session pre-print realised vol** (EWMA, event days excluded — `event_move` already computes this).
   DKS today: chain IV 0.49–0.53 vs 0.38–0.42 realised → ratio 1.2–1.3, passes.
3. Up-tail overpriced in the chain's own terms: the 25–30-delta call is quoted ≥ the 25–30-delta put on the same
   expiry in IV terms OR the name is outside the mega-11 (where the fade is measured). DKS: 130C IV 0.493 vs 120P
   0.534 — the puts are richer, so on DKS this condition passes only by the second clause.

**Point-in-time data available here.** Alpaca option chains (`chain_mod.fetch`, live greeks/IV filled by BS when
the feed omits them); expired option daily bars (`scripts.event_straddle_backtest.option_bars`) — that is what makes
the backtest possible on this account without paying for history; SEC 8-K dates (`alpha.sources.sec`); SIP daily
bars for realised vol and gaps. All four are already wired.

**Entry.** Day+1, 15:30–15:45 ET pass (the drift is flat across +1/+2/+3 and the crush receipt is measured at the
day-0 close, so day+1 close sells after the first crush but before the second). Structure: SELL the ~30-delta call,
BUY the ~15-delta call, same expiry, first expiry ≥ 10 calendar days after entry (DKS: 130/140 on 2026-09-18).
Order as one multi-leg limit at mid − 0.25 × the combined half-spread; refuse if unfilled by 15:50.

**Exit.** Whichever first: (i) 50% of the credit captured; (ii) day+3 close **only if** the mark is ≥ 0.9 × credit
(i.e. the trade is dead money — exit and stop paying the exit spread on a winner); otherwise hold; (iii) spot
through the short strike at any close → close at the next pass (this is the directional stop, 4.5% above spot on
DKS); (iv) 3 sessions before expiry, unconditionally (pin/assignment). Never held through a second scheduled print.

**Sizing.** Max loss = width − credit, charged to the book as such (it IS contractual). Per-thesis fraction from
`sizing.PROFILES` unchanged; additional cap **credit received ≥ 15% of width** (DKS 130/140 at mids: 2.11 on 10 =
21%, passes; at quoted bid/ask 1.97 = 19.7%, passes). Aggregate: counts against the same event node as any other
expression of the print (`runner.event_node`), so a drift short and this spread on the same name share one cap.

**Transaction-cost model.** Each leg crossed at half the quoted spread on entry and again on exit; DKS 130C
half-spread 0.095, 140C 0.045 → 0.14/spread entry, 0.14 exit = **0.28 on a 1.97 credit (14% round trip)**. Theta:
+0.025/day net at entry (+0.134 short, −0.108 long) — the structure PAYS to be held, which is the point of the
brief's "no theta bleed". Vega: −0.029/pt net; each IV point of further crush is +0.03. Slippage on the short-strike
stop: one half-spread of the ITM call at that time, modelled as 2× the entry half-spread. Commissions $0.

**Falsifier (pre-declared).** On the backtest below with ≥ 200 legs: mean return on max loss ≤ 0 net of the cost
model, OR the weekly-block t < 1.5. Either kills v1 as an implementation (`FAILED_VARIANT`), not the mechanism.

**Placebo.** The identical spread sold on the same names on the day+1 of a NON-print day matched on |1-day move| ≥
5% (a 5% ordinary-day move, no 8-K). If the placebo earns as much, the edge is "sell calls after any big move" —
still tradeable, but not an earnings mechanism and the crush leg of the story is false.

**Matched control.** The mirror structure — a bull PUT spread (sell 30-delta put, buy 15-delta put) on the same
day+1, same expiry. Three outcomes and each has a reading: call side > put side → direction (the fade) is real;
both positive and equal → it is pure crush, and shares + short put (§2) dominate this structure; put side > call
side → the mechanism is the opposite of the claim and v1 is `MECHANISM_REJECTED` for the up-side.

**Expected failure mode.** The dead-cat bounce. In the 46 prints I pulled today for five names, three DOWN prints
reversed by more than the spread's width inside three sessions: AFRM 2025-05-09 −15.8% → **+21.9%**; RBRK
2026-02-05 −7.1% → **+15.7%**; S 2025-03-13 −5.7% → +6.2%. The wide-PEAD mean of +0.64% hides a fat up-tail on
single names; the spread's max loss is 4× its credit (DKS 8.03 vs 1.97), so a 20% hit rate on those blows
through the mean. That is why the width is capped and the short-strike stop exists, and why this is sized as a
candidate.

**Stock expression.** Short shares, no 3% stop (see §2 — the stop is the defect), sized to one 3-session implied
sigma. Cheaper by 100 bp per unit delta and worse by the crush it cannot sell.

**Option expression.** The bear call spread above. Second choice, on names where the 15-delta call is quoted >
50% relative spread (S, RBRK overnight today): sell shares + sell the 15-delta PUT (covered put) — it monetises the
same rich surface with one option leg instead of two, and the leg it sells is the more liquid one.

**Backtest plan on this repo's data.** New script `scripts/post_print_call_side.py`, copying the scaffolding of
`scripts/post_event_vol_crush.py` (which already reconstructs the day-0 ATM straddle from expired bars):
- universe: the 12 straddle-backtest names (117 prints) first — expired bars are known to exist — then the 2,532
  SEC-covered names from `state/pead_wide_legs.jsonl` filtered to |r_0| ≥ 5% (~7,400 legs; sample 400 by dollar
  volume bucket because expired-bar pulls are ~1 h per 500 names);
- legs: day+1 close, short call at strike = spot × (1 + 0.5 × implied move), long call at spot × (1 + implied
  move), expiry = first weekly ≥ 10 days (`next_friday` + 7); marks from expired daily bars; cost model as above
  with relative spread assumed 6% per leg where no quote survives (the median liquid-leg number in today's DKS chain);
- outputs (the receipt, `state/post_print_call_side.json`): mean/median return on max loss, hit, t raw and by
  week block, by day-0 sign, by band (5–8.2 / >8.2), by size bucket, the placebo, the mirror control, and the
  DATES of the ten worst legs printed in full;
- run: `python -m scripts.post_print_call_side --years 2.5`, before any live sizing.

**Prospective shadow record (opens tonight).** DKS, printed bmo 2026-08-25, r_0 = −36.8% log (−31% simple),
gap −20.7%, day+1 = 26 Aug (today; entry is the 15:30 pass, which this document precedes). Frozen for grading:
spot 124.34, 09-18 implied move 8.87%, 130C 3.94/4.13 (δ 0.39, IV 0.493), 140C 1.88/1.97 (δ 0.21, IV 0.534),
credit 1.97 quoted / 2.11 mid, max loss 8.03, theta +0.025/d, vega −0.029. **Prediction: DKS closes 2026-09-18
below 130 (chain says 61%; I say ≥ 75% — the up-side of a −31% retailer with IV 1.25× realised is the overpriced
side).** Grade: P&L per spread at the exit rule, and whether the mirror 120/110 put spread did better.

---

## 2. ATTACK — "short shares after a ≥5% earnings drop", from the vol desk

The lane as coded (`alpha/engine/equity.py`): short shares, **stop 3%**, target +2.5%, horizon spent at 15:45 on
the last session, stress-loss charge = 3% + p95 |overnight gap| (floored 2%). On DKS today the charge is
**5.89%** (`stress_charge` → "stop 3% + gap 2.89%"). DKS is shortable + ETB. Edge claimed: +0.64%/3 sessions
(big band, t 5.16), measured on close-to-close returns **with no stop**.

### 2a. The stop is the defect, and it is not a small one

The lane's backtest object is a 3-session close-to-close return. The lane's *trade* is a path-dependent one, and
nobody has measured it. DKS's post-print chain says daily σ = 0.53/√252 = **3.34%/day**, 3-day σ 5.78%. By the
reflection principle (drift ignored, which flatters the stop):

| stop | P(hit inside 3 sessions) | P(hit on day 1 alone) |
|---|---|---|
| **3% (as coded)** | **60%** | 37% |
| 5% | 39% | 13% |
| 8% | 17% | 2% |

A 3% stop inside a 3.3%/day name is hit on **six legs in ten**, and every hit forfeits the drift that was the reason
for the trade and pays the stop's slippage. What the backtest measured (+0.64%, t 5.16) is not what the engine
trades; the traded object is `+0.64% × P(survive) − 3% × P(hit) − slippage`, which with these numbers is
`0.26% − 1.8% < 0`. **The lane loses money on DKS as coded, before borrow, on its own edge.** The stop was
calibrated to mega-caps (NVDA 2.2%/day); the wide lane's best bucket is small caps, where the stop is worst.
Fix: stop = max(3%, 1.0 × 1-day chain σ × √(sessions left)) → on DKS ≈ 5.8%, hit rate ~30%, or no stop and
size to the stress charge (which is what the charge is for). Either way the traded object must be re-measured with
the stop *inside* the backtest before the lane is trusted with the +5.16.

### 2b. 30/50-delta put spread vs the shares — numbers, DKS 09-18, mid quotes, BS greeks at chain IV

Bear put spread 120/110 (δ −0.36 / −0.15): debit 3.30 at bid/ask (3.175 mid), net δ **−0.216**, net θ
**−0.054/day**, net vega +0.046. Per unit of share-equivalent delta (divide by 0.216):

| item, 3-session hold | shares (100) | put spread (4.6 spreads = 100 δ) |
|---|---|---|
| expected drift captured (+0.64% × 124.34) | +$80 | +$80 |
| round-trip crossing | ~$4 (4 bp; quoted bid 118.47 after hours is an artefact, RTH DKS is 1–2 c) | **−$116** (0.25 × 4.6 × 100; = 0.93% of spot per unit delta) |
| theta, 3 days | 0 (borrow ~ETB, <$1) | **−$75** (0.054 × 3 × 4.6 × 100) |
| vega if IV crushes 5 more points | 0 | **−$106** (net long vega on the spread) |
| net, expected | **≈ +$76** | **≈ −$217** |
| worst case charged | $733 stress charge (5.89%), theoretical unbounded | $1,518 (debit), contractual |

The put spread is not a better expression; it is three losing legs stacked on a 0.64% edge — spread (0.93% of spot
per unit delta), theta (0.6%), vega (0.85%). The brief's own instinct was right ("prefer structures that do not
bleed theta") and a debit vertical is exactly the theta-bleeding one. It is also **long the post-print surface that
`post_event_vol_crush` says loses at t −7.74**. Reject.

### 2c. Short-stock + OTM-call collar

Short 100 DKS + long 135C at 2.83 ask (δ 0.29, θ −0.124): cost 2.28% of spot for a cap at +8.6%. Over 3 sessions
theta alone is 0.37 = **0.30% of spot, half the edge**; crossing 0.05 more. What it buys: protection above +8.6%,
which the chain prices at ~7% probability over 3 sessions, and which the 5.89% stress charge already does not cover
— so it is the *right* insurance for the *wrong* price. Funding it by selling the 110P (1.18 bid) brings the net
cost to 1.65 = 1.3% of spot, still twice the edge, and adds long delta. Reject as a standing overlay; keep it only
as an event overlay when a second catalyst sits inside the horizon (the engine already raises the gap charge to the
implied move then — the collar is what that charge should buy).

### 2d. What the vol desk would actually change (ranked)

1. **Replace the 3% stop with a width-scaled one and re-run `pead_wide` with the stop inside the leg.** This is
   the only change that can move the lane from unmeasured to measured. Until then the t 5.16 belongs to a different
   trade than the one on the book.
2. **Covered put: short shares + SELL the ~15-delta put** (DKS 110P, 1.18 bid = 0.95% of spot, θ +0.076/d, vega
   0.072). Over the 3-session hold: theta +0.23, crush of 5 IV points +0.36, buyback spread −0.09, minus the long
   delta it adds (0.146 × 0.64% × 124 = −0.12): **≈ +0.38/share = +0.30% of spot on top of the drift**, i.e. the
   edge rises from 0.64% to ~0.9% and the trade is now *short the overpriced surface* instead of ignoring it. The
   cost is a profit cap at −11.5% (110), which a 3-session drift trade never reaches, and the up-side exposure is
   unchanged (the shares' problem, not the put's). Borrow/margin: a cash-secured put on the paper account.
3. **If the name's options are quoted wider than 10% on the 15-delta leg (S, RBRK overnight today), shares alone**
   — an option leg that costs more than the crush it sells is worse than none.
4. Bear call spread (§1) as the *defined-risk* version for names where borrow fails (858 of 4,634 are not ETB).

Net verdict on the lane: the shares are the right instrument and the stop is the wrong one; the vol desk's
contribution is an extra ~30 bp from selling the surface, and a red flag on the stop worth more than that.

---

## 3. PREREGISTRATION — 27 Aug AMC prints (+ ESTC), against the frozen `state/event_grade/*_pre.json`

Decomposition method: chain σ = implied × √(π/2); ordinary variance = EWMA daily sd (event days excluded) × the
ordinary sessions inside the expiry; event-only σ = √(chain² − ordinary²); compare its E|move| = σ√(2/π) with the
name's last-8 SEC-dated prints. **Execution condition on every BUY/SELL: the legs must quote ≤ 10% relative spread
at the 15:30–15:45 ET pass on 27 Aug; overnight the 08-28 chains quote 15–40% (AFRM ATM straddle bid 7.61 / ask
9.41 on mid 8.51 — a 21% round trip) and at those quotes every line below becomes REFUSE.** Grade each on the
day-0 (28 Aug) close.

| name | frozen implied (expiry) | ordinary σ inside | **event-only E\|move\|** | last-8 prints: mean / median / cleared implied | history − implied | call |
|---|---|---|---|---|---|---|
| **IREN** | 9.66% (08-28) | 6.5%/day → 6.5% | **8.1%** | 10.3% / 8.9% / 50% (n=6, and the 2026-07-20 "bmo +18%" row is suspect — print the date) | +0.8pp on a 130%-realised name | **REFUSE convexity, both sides.** The chain is barely charging for the print: 9.7% for two sessions of a name that moves 6.5% on an ordinary day. There is no rich side to sell and the cheap side is inside one half-spread. Post-print: DOWN ≥5% → shares short (wide rule); UP → refuse (fade). |
| **AFRM** | 9.28% (08-28) | 3.2% | **8.9%** | 12.3% / 10.6% / 62% — but the LAST FOUR are 10.1 / 11.1 / **4.1 / 5.2** (mean 7.6%) | +3.4pp on 8, −1.7pp on 4 | **REFUSE the straddle.** The conditional sort's top tercile says buy and the recent regime says the print distribution has halved; a 3.4pp margin sits inside the 21% round trip. Prediction anyway, for the grade: \|day-0\| < 9.28% (P 0.6). Post-print: DOWN ≥5% → short shares + sell 15-delta put (§2d.2); UP → refuse. |
| **S** | 9.23% (08-28) | 3.3% | **8.8%** | 8.7% / 7.7% / 38%; **8 of 10 prints DOWN**, the two ups +6.8% and +5.4%, max up ever +6.8% | −0.1pp symmetric, but the UP tail is empty in history and priced at δ 0.29 for +8.3% | **SELL the up-side only: bear call spread 22/24 (08-28), mids 0.455/0.245 → credit ≈ 0.21 on width 2.0.** Execute only if credit ≥ 0.20 (10% of width) at RTH quotes; else refuse and record. Prediction: S closes 28 Aug **< 22.00** (chain 71%, I say 88% — 2/10 up prints, none past 21.7). **Do not sell puts**: five of ten prints fell ≥ 12%. Post-print DOWN → shares short, no put sale (the puts are the fairly-priced side here). |
| **RBRK** | 11.47% (08-28) | 3.9% | **11.0%** | 12.1% / 12.7% / 50%; bimodal — ups **+18.4, +24.4, +20.2**, downs −9, −20, −7 | +1.1pp; but the chain's skew is put-side (ATM IV put 2.40 vs call 2.16) while history's fat tail is the UP side (3 of 10 > +18%) | **REFUSE convexity** (fair on width, 20–55% spreads on the 100–110 calls). **SHADOW-ONLY skew record, not sized:** 30-delta risk reversal (long 105C mid 1.88 / short 85P mid 2.73, net credit 0.85) — the chain charges more for the tail that history says is smaller. Grade: sign and size of the day-0 move vs ±11.5%; a reversal "wins" if day-0 > +5% or between −8% and +5%. Post-print: DOWN → shares short + sell 15-delta put; UP → refuse. |
| **ESTC** | 13.30% (**09-18, only expiry**) | 3.41%/day × 15 sessions = **13.2%** | **8.1%** | **14.8% / 13.8% / 62%** (−13, +11, −31, +14, +14, −13, −3, −16, −17, +12) | **+6.7pp — the largest gap on the board, and in the BUY direction** | **BUY convexity, narrow, and sell it at the day-0 open.** The 09-18 straddle (mid 12.59, 15.6% of spot) is 62% ordinary variance the trade does not want, which is why the long is exited at the first pass after the 28 Aug open (`event_exit_timing`: 89% of the move is in the gap; holding the session cost −4.5%). Risk = premium, capped at the per-thesis fraction; refuse if the ATM legs quote > 10% spread (overnight: 80C 5.73/7.46 = 26%, 80P 5.14/6.85 = 28% — REFUSE at these). Prediction: \|day-0\| > 9.5% (P 0.65) and the straddle marks above entry at the open (P 0.55). Falsifier for the *method*, not just the leg: if \|move\| < 8.1% the event-only decomposition is worth nothing on monthlies-only names. |
| NVDA (26 Aug amc, on the book) | 5.10% (08-28) | — | — | last-8 3.8% / 3.2% / **0 of 8** | −1.3pp, and 0/8 | **SELL convexity — the condors already on dev/exp1 are the right side.** Prediction: \|day-0\| < 5.1% (P 0.7). The Psychohistory record (tail 12% vs chain 20%) agrees. |

Summary of the calls: **1 BUY (ESTC), 1 SELL up-side (S), 1 SELL (NVDA, standing), 3 REFUSE (IREN, AFRM, RBRK)
plus one shadow skew record (RBRK).** Five of six are refusals or partial — that is what "the chain is fair on
average and two-sided by name" looks like when it is applied honestly, and it is the opposite of a desk that finds
a trade in every chain.

---

## 4. VERDICT

The directional side of this project has one measured mechanism worth ~0.5–1% of spot over three sessions and
wants to pay 1–2.5% of spot per unit delta to express it in options; the vol side has a measurement three times as
strong (post-print straddle paired t −7.74, 17.5% clear break-even) that nobody has sold. The trade that reconciles
them is **sell the post-print up-side** — a bear call spread on day+1, or shares plus a short 15-delta put where the
chain is too wide for two legs — short delta the way the wide PEAD points, short vega the way the crush receipt
points, theta-positive, contractually bounded, and backtestable tonight on the expired bars this account already
serves. The attack on the shares lane is not that shares are wrong (they are the cheapest delta on the board) but
that **a 3% stop inside a 3.3%/day name is hit 60% of the time and the +5.16 was measured without it** — the lane
is trading an object nobody has backtested. For 27 Aug: buy ESTC's event variance and sell it at the open, sell S's
empty up-tail, keep the NVDA condors, refuse IREN/AFRM/RBRK, and refuse everything if the RTH spreads look like the
overnight ones.

---
*File: `docs/agents_2026-08-26/agent4_volatility_trader.md`. Read-only inputs: `state/event_grade/*_pre.json`,
`state/event_straddle_backtest.json`, `state/post_event_vol_crush.json`, `state/event_calendar.json`,
`state/pead_wide.json`, live chains DKS/S/RBRK/AFRM/ESTC via `chain_mod.fetch` at ~13:00 UTC 26 Aug.*
