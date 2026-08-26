# AGENT 7 — EVENT MICROSTRUCTURE: where in the clock does the post-print drift live?

Receipts: `state/agents_2026-08-26/microstructure_sample.json` (15-minute bars, 60 legs, last 3 months),
`state/agents_2026-08-26/microstructure_daily_wide.json` (daily open/close split, 1,608 DOWN legs, 500 symbols, 2.5y),
`state/agents_2026-08-26/microstructure_fullpanel_timing.json` (the re-run's `overnight_gap_signed` / `from_open1_signed`
fields on all 25,856 legs — it landed at 15:28 and was used), `state/agents_2026-08-26/microstructure_stop_sim.json`.
Sign convention everywhere below: **positive = the SHORT earned** (signed in the day-0 direction for a DOWN print),
beta·QQQ excess unless marked RAW. Clock is ET (EDT, UTC−4). Nothing outside `docs/agents_2026-08-26/` and
`state/agents_2026-08-26/` was modified.

## 0. The headline before the tables

1. **The drift is SESSION drift, not a second overnight gap.** Across 1,608 DOWN≥3.5% legs the three intraday
   segments sum to +0.28% and the three overnights to +0.07%. In the mid band it is +0.54% intraday vs +0.19% overnight.
2. **The overnight after day 0 goes AGAINST the short in every bucket** — mid band −0.11% (t −3.5, n=3,690), big band
   −0.14% (t −3.7), mid-cap bucket −0.18% (t −3.6). The day+1 OPEN is a bounce. Entering at the open instead of the
   day-0 close *improves* the trade: from-open +0.56% (t 5.35, weekly t 2.71) vs close-to-close +0.44%.
3. **The bounce is in the gap, not in the first 30 minutes of trading.** On 15-minute bars the first-30 segment of
   day 1 is −0.08% (median −0.44%, hit 45%, n=60) — flat. A 10:00 entry vs a 9:30 entry gains +0.08% on n=60, which
   is noise, but it halves the impact cost: the 9:30 bar's median 15-minute range in small caps is 1.97% against
   0.93% at 10:00 and 0.35% at midday.
4. **The UP side shows the same clock with the opposite sign of the print.** UP mid band: overnight +0.12% in the
   print's direction (t +4.4), then −0.35% from the open (t −3.1). Read RAW, both sides say the same thing: **after a
   large print the next overnight is positive and the next session is negative, whatever the sign of the print**
   (DOWN: raw overnight +0.11%, raw session −0.56%; UP: raw overnight +0.12%, raw session −0.35%). That is the
   Lou–Polk–Skouras "tug of war" pattern (overnight positive / intraday negative in retail-attention names), and it is
   a rival mechanism to PEAD that the placebo in §2 must kill before the lane is called "drift".
5. **The current implementation captures 95–103% of the close-to-close window in gross terms — and then hands it
   back through the 3% stop / 2.5% target.** Numbers in §3.

## 1. MEASUREMENT

### 1a. 15-minute decomposition — 60 legs, 60 symbols, day-0 drop ≥5%, 2026-05-26..08-20, 30 small + 30 mid

Selection: `r0 ≤ −5%`, `day0 ≥ 2026-05-26`, `dv_bucket ∈ {small, mid}`, 30 symbols per bucket (seed 20260826), every
qualifying leg of those symbols; SIP 15Min bars (141,892 bars) plus daily bars; QQQ on the same bars for the excess.
Price at HH:MM = close of the last regular-hours 15-minute bar that started before HH:MM.

| session | segment | n | mean (ex) | median | hit | t | raw mean |
|---|---|---|---|---|---|---|---|
| +1 | overnight (close0→open1) | 60 | −0.08% | −0.01% | 50% | −0.41 | −0.44% |
| +1 | first 30 min (open→10:00) | 60 | −0.08% | −0.44% | 45% | −0.23 | +0.01% |
| +1 | 10:00–11:00 | 60 | +0.06% | +0.03% | 52% | +0.26 | +0.09% |
| +1 | 11:00–15:30 | 60 | −0.23% | −0.06% | 50% | −0.63 | −0.27% |
| +1 | last 30 min | 60 | +0.02% | +0.23% | 57% | +0.14 | +0.07% |
| +2 | overnight | 60 | +0.19% | −0.24% | 43% | +0.74 | +0.04% |
| +2 | first 30 min | 60 | **+0.55%** | +0.52% | 65% | **+1.98** | +0.50% |
| +2 | 10:00–11:00 | 60 | +0.22% | +0.27% | 55% | +0.98 | +0.23% |
| +2 | 11:00–15:30 | 60 | −0.13% | −0.10% | 48% | −0.45 | −0.07% |
| +2 | last 30 min | 60 | +0.01% | +0.04% | 53% | +0.09 | +0.03% |
| +3 | overnight | 60 | +0.11% | +0.07% | 55% | +0.56 | +0.01% |
| +3 | first 30 min | 60 | −0.28% | −0.31% | 45% | −1.52 | −0.20% |
| +3 | 10:00–11:00 | 60 | −0.20% | −0.27% | 47% | −0.90 | −0.14% |
| +3 | 11:00–15:30 | 60 | +0.06% | −0.01% | 48% | +0.25 | +0.09% |
| +3 | last 30 min | 60 | −0.03% | −0.12% | 43% | −0.27 | +0.02% |
| pooled ×3 | overnight | 180 | +0.07% | −0.06% | 49% | +0.57 | |
| pooled ×3 | first 30 | 180 | +0.06% | +0.07% | 52% | +0.38 | |
| pooled ×3 | 10–11 | 180 | +0.03% | +0.03% | 51% | +0.19 | |
| pooled ×3 | 11–15:30 | 180 | −0.10% | −0.03% | 49% | −0.57 | |
| pooled ×3 | last 30 | 180 | −0.00% | +0.03% | 51% | −0.00 | |

Anchored windows on the same 60 legs: close0→close3 +0.18% (t 0.19) · open1→close3 +0.26% · 10:00₁→close3 +0.34% ·
10:00₁→15:45₃ +0.38% · **10:00₁→15:45₂ (what the code actually does, see §3) +0.64% (t 0.97)** · close1→10:00₂
+0.74% (t 2.17, hit 67%) · 15:30₁→10:00₂ +0.76% (t 2.05). Small: close0→close3 +1.36%; mid: −1.01% (t −0.86, n=30 each).
Conditional: the 33 legs whose first 30 minutes of day 1 went against the short then returned −1.11% from 10:00 to
close3; the 27 that did not returned +2.11% (t 1.77) — first-30 direction is a *momentum* filter, not a fade to buy.

**Power statement, so the table is read correctly.** The 3-session excess has sd ≈ 7.2% on these names, so at n=60 the
MDE at 80% power is 2.8·7.2%/√60 ≈ **2.6%** — six times the effect being decomposed. No cell of this table resolves a
+0.44% drift, and the one |t|≈2 cell (day+2 first 30 min, +0.55%) is one of fifteen cells and is what chance produces.
The 15-minute sample **can** say what the clock looks like and that nothing at 9:30–10:00 on day 1 is worth waiting for
or fading; it cannot rank the segments. The daily split below can, and it was pulled for that reason.

### 1b. Daily open/close split — 1,608 DOWN≥3.5% legs, 500 random small/mid/large symbols, 2024-02..2026-08

| segment | all DOWN≥3.5% (n=1,608) | t | mid band (n=817) | t (weeks) | big band (n=791) | t | small DOWN≥5% (n=547) | t |
|---|---|---|---|---|---|---|---|---|
| gap 0→1 (overnight) | −0.05% | −1.13 | +0.03% | 0.5 (−0.4) | −0.13% | −1.91 | +0.06% | 0.81 |
| intraday 1 | **+0.19%** | **+1.95** | **+0.29%** | 2.44 (1.1) | +0.08% | 0.56 | +0.27% | 1.48 |
| gap 1→2 | +0.06% | 1.82 | +0.10% | 1.96 (1.95) | +0.03% | 0.61 | +0.13% | **2.03** |
| intraday 2 | +0.02% | 0.22 | +0.14% | 1.59 | −0.11% | −0.84 | +0.05% | 0.33 |
| gap 2→3 | +0.05% | 1.45 | +0.06% | 1.10 | +0.05% | 0.94 | +0.06% | 1.08 |
| intraday 3 | +0.07% | 0.99 | +0.11% | 1.32 | +0.03% | 0.24 | +0.12% | 0.88 |
| Σ overnights | +0.07% | 0.99 | +0.19% | 1.98 | −0.05% | −0.52 | +0.25% | 2.19 |
| Σ intradays | **+0.28%** | 1.91 | **+0.54%** | 2.96 | +0.00% | 0.02 | +0.45% | 1.60 |
| close0→close3 | +0.35% | 2.27 | +0.73% | 3.67 (2.34) | −0.05% | −0.22 | +0.69% | 2.37 |
| open1→close3 | +0.40% | 2.65 | +0.70% | 3.59 (2.43) | +0.08% | 0.35 | +0.64% | 2.18 |
| open1→close2 (current code) | +0.27% | 2.16 | +0.52% | 3.37 (1.71) | +0.01% | 0.03 | +0.45% | 1.81 |

### 1c. The full panel, from the re-run that landed during this session (25,856 legs; `overnight_gap_signed`, `from_open1_signed`, `signed_1..3`)

| DOWN slice | n | overnight after day 0 | t | from open1 to close3 | t (weeks) | day1 open→close | t | +day2 | +day3 | open1→close2 (current) |
|---|---|---|---|---|---|---|---|---|---|---|
| mid band, all | 3,690 | **−0.11%** | **−3.51** | **+0.56%** | **+5.35 (2.71)** | +0.28% | 4.20 | +0.14% (t 2.5) | +0.14% (t 2.7) | **+0.42%** (t 4.84) |
| big band, all | 3,790 | −0.14% | −3.69 | +0.78% | +6.30 (0.38) | +0.40% | 4.93 | +0.25% (3.8) | +0.12% (1.8) | +0.66% (6.32) |
| mid band, small | 1,200 | −0.11% | −2.16 | +0.84% | +4.67 (1.30) | +0.31% | 2.80 | +0.27% (2.7) | **+0.26% (2.9)** | +0.58% (3.86) |
| mid band, mid | 1,254 | −0.18% | −3.62 | +0.42% | +2.59 (3.16) | **+0.41%** | **4.72** | −0.03% | +0.03% | +0.38% (3.02) |
| big band, small | 1,275 | −0.05% | −0.82 | +0.69% | +3.38 (0.07) | +0.24% | 1.74 | +0.31% (2.6) | +0.14% | +0.55% (3.04) |
| mid band, micro | 656 | −0.14% | −1.91 | +0.44% | +1.38 | +0.14% | 0.63 | +0.21% | +0.09% | +0.35% (1.29) |
| UP mid band (control) | 3,746 | +0.12% | +4.44 | −0.35% | −3.08 (−1.1) | −0.27% | −4.55 | −0.18% | +0.10% | −0.45% (−4.43) |

Where the drift lives, then: **day+1 open→close is the single largest and most reliable piece** (+0.28% to +0.41%,
t 4.2–4.9 on 1,250–3,800 legs); day 2 and day 3 add +0.14% each in the mid band and are only material in small caps;
the overnight after day 0 is a cost, not a source; the later overnights are +0.03–0.13% and pay only in small caps.
Big band's weekly-block t collapses to 0.38 (prints cluster in earnings weeks) while the mid band's holds at 2.71 —
the mid band is the one with a resolution behind it.

## 2. STRATEGY — "day+1 session short, flat overnight"

- **Mechanism.** After a ≥3.5% down close on a print, the day+1 session (open→close) falls a further +0.28–0.41%
  beta-adjusted; the overnight before it rises. Whether that is information diffusion (PEAD) or retail attention
  buying the open and selling into the day (tug-of-war) is *unresolved and the placebo below decides it*; the trade is
  the same either way — but the universe is not (see placebo).
- **Signal.** SEC 8-K Item 2.02 date (`alpha/sources/sec.py`), first reflecting close `r0 ≤ −3.5%` (mid band
  3.5–8.2% preferred: weekly t 2.71; big band only with the weekly-t caveat), `dv_bucket ∈ {small, mid}`,
  `shortable and easy_to_borrow` at the venue, non-mega (mega keeps the two-sided rule).
- **Entry timestamp.** **09:45–10:00 ET on day+1** (21:45–22:00 HK): after the opening 15-minute bar has printed,
  before the 10:00 range halves again. The open bounce is in the gap, so nothing is lost by not being first; impact is
  half the 9:30 bar. Marketable limit at the bid, `time_in_force: day`, cancel if unfilled by 10:15 (a fill after 10:15
  has lost the segment's first hour and is a different trade).
- **Exit timestamp.** **15:55 ET on day+1**, cover with a limit at the ask (or MOC — the 15:45 bar carries 13.5% of the
  day's small-cap volume and the 15:45→close segment is +0.04%, so the closing auction is the cheaper exit, not 15:45).
  Never hold overnight on day+1→+2 in the mid/large buckets (gap 1→2 +0.03–0.10%, borrow and gap risk for nothing).
  Small-cap variant only: re-enter 09:45 day+2 and 09:45 day+3 as *separate* day trades (+0.27%, +0.26%, t 2.7/2.9).
- **Sizing.** Flat overnight means the stress charge is the stop only: `STOP_FRACTION` 3% with **no gap allowance**
  (`equity.stress_charge` currently adds a p95 |overnight gap| that is 5–8% in these names post-print, so the same risk
  budget buys ~2–3× the notional for an intraday-only position). Cap 10% of equity per name, 25% per day across names,
  8 names max; a 3% stop is still 10× the expected edge, so the stop is a disaster guard, not a manager.
- **Cost model.** Small-cap spread at 09:45 ≈ 15–30 bp round trip (proxy: 15-min range 0.93% at 10:00 vs 0.35%
  midday — the receipt has the full time-of-day curve; quotes were not pulled). Impact at 10% of a 15-minute bar's
  volume: ~5 bp. Borrow: easy-to-borrow ≈ 0.3–1%/yr ⇒ <0.5 bp/day; a name that just fell 10% is often hard-to-borrow at
  20–100%/yr ⇒ 5–30 bp/day — **borrow is the cost that can eat the edge**, and an intraday short pays it once. Net
  expectation: +0.28–0.41% gross − 20–35 bp = **+0.05 to +0.20% per trade**, i.e. positive but a third of the gross.
- **Falsifier.** On the forward paper record, mean day+1 open→close excess < +0.10% over the first 60 fills, or the
  weekly-block t of the same on 2024-02..2026-08 mid band falling below 2.0 when the calendar is re-cut by EPS-surprise
  sign instead of price reaction.
- **Placebo (decides the mechanism).** Same names, same size, **non-print days** with a close-to-close move ≤ −3.5%
  (no 8-K 2.02 within ±3 sessions). If the day+1 session is also −0.3% and the overnight also +0.1%, the effect is the
  attention tug-of-war and the lane should trade *every* large down mover, not prints; if the placebo is flat, it is
  PEAD and the print filter is load-bearing. Second placebo: shuffle day-0 dates within name (already the adversarial
  script's calendar-shift null).
- **Matched control.** The UP side at the same |r0|, same bucket, same week: already measured, day+1 session −0.27%
  (t −4.6) for the print's direction ⇒ RAW the session is negative on both sides. A control that returns the same sign
  as the treatment is a warning that the treatment is not the print's sign.
- **Failure mode.** (i) Halt/news at 10:00 in a name that fell 10% yesterday (secondary offering, guidance cut) —
  unbounded on a short; the 3% stop is gapped through inside the session. (ii) Borrow recall or "not shortable" flag
  flipping between the 15:30 scan and the 09:45 entry. (iii) Earnings-week clustering: 8 names on one Thursday is one
  bet on that week's tape (weekly t 2.71 vs raw 5.35 says a third of the t is clustering).
- **Stock expression.** Short shares, marketable limit at bid 09:45–10:00, cover limit at ask / MOC 15:55, no overnight.
- **Option expression.** None. +0.3% gross on a name with a 5% daily range is under one bid-ask of any listed put; a
  0-DTE put on a small cap does not exist. `FINDING_2026-08-26_PEAD_WIDE.md` §3 already said this and the clock does
  not change it.
- **Backtest plan.** Re-run `scripts/pead_wide.py` with `intra1 = open1→close1` as the primary metric (the fields now
  exist: `signed_1 − overnight_gap_signed`) on all 25,856 legs; grade by BH-FDR over the 8 slices; then the placebo
  above on the same bars (needs no new pull: non-print −3.5% days are in the same daily bars). Then a 15-minute pass on
  the mid band only (≈3,700 legs × 4 sessions ≈ 400 symbols × 2.5y of 15Min bars, ~40 min at today's rate) to fix the
  entry at 09:45 vs 10:00 with n that resolves 0.1%.
- **Prospective shadow record.** From the next session: for every name the drift brain forecasts, write a row
  `{symbol, day0, r0, band, bucket, open1, px_0945, px_1000, close1, open2, px_0945_2, close2, borrow_flag, spread_at_0945}`
  to `state/shadow/day1_session_short.jsonl` before any fill; grade at each close; the falsifier above reads this file.

## 3. ATTACK on the current implementation (`alpha/runner.py`, `alpha/engine/equity.py`, `alpha/exits.py`, `alpha/brains/post_event_drift.py`)

What the code actually does, read from the code rather than from the brief:

1. `post_event_drift.forecast` refuses while `elapsed == 0` (day 0 still forming), so the first possible entry is the
   first 30-minute entry pass of day+1 — a fill somewhere in **09:30–10:30 ET** at the bid, DAY limit.
2. `ARRIVAL[1]` returns `sessions_left = 2.0` ⇒ `horizon_days = 2`; `exits._evaluate_shares` counts the entry day as
   session 1 and closes at `SHARES_HORIZON_EXIT_ET = 15:45` on **day+2**, not day+3. The brief's "exit at 15:45 on the
   horizon day" is day+2. **Day+3 is never held** — +0.14% (t 2.7) in the mid band, +0.26% (t 2.9) in small caps.
3. `STOP_FRACTION = 0.03` and `PROFIT_TARGET = 0.025` are checked every 5 minutes on `unrealized_plpc`.

Gross capture of the window it holds (full panel, §1c): **+0.42% of the +0.44%/3d in the mid band (95%), +0.66% of
+0.64% in the big band (103%), +0.58% of +0.73% in small caps (79%)** — because skipping the adverse overnight after day 0
(−0.11%) roughly pays for the day+3 it never holds (+0.14%). Against the *better* benchmark, open1→close3 (+0.56%), it
captures 75%. So the entry/exit clock is not where the money is lost.

The rules are. On the 500-symbol daily sample, entering at open1 and applying the 3% stop / 2.5% target on names whose
**day+1 high breaches +3% above the open in 28% (mid band) to 43% (small) of legs**:

| slice | raw open1→close2, no rules | with stop/target, stop-first when both touch | target-first | rule-closed legs |
|---|---|---|---|---|
| all DOWN≥3.5% (n=1,608) | +0.05% (t 0.4) | **−0.26% (t −4.1)** | +0.20% (t 3.1) | 84% |
| mid band (n=817) | +0.32% (t 2.0) | **−0.22% (t −2.6)** | +0.08% (t 1.0) | 77% |
| big band (n=791) | −0.23% | −0.31% (t −3.3) | +0.31% (t 3.4) | 91% |
| small (n=694) | +0.14% | **−0.41% (t −4.1)** | +0.26% (t 2.6) | 91% |

Daily bars cannot order a same-day stop and target, so the truth sits between the two columns — but **77–91% of
positions are closed by a rule rather than at the horizon**, the stop is wider than the target on a name with a 5–8%
daily range, and the expected drift is 0.4%. The stop/target pair is a random exit generator with a negative skew
(`exits.py` line 40 says exactly this about trailing stops and then applies a fixed one). **Answer to "how much does the
implementation capture": gross, ~95% of the measured +0.44% (mid band) and ~100% of +0.64% (big band); net of its own
stop/target, somewhere between −0.26% and +0.20% per leg, with the stop-first bound the more likely one for a short in
a name that just gapped down** (post-print ranges are front-loaded and the bounce comes first). Add borrow and a
15–30 bp spread on a two-session hold and the realistic capture is **≤ 0 to +0.15% of the +0.44%**, i.e. under a third.

Three concrete defects, in order of money:
- **The 2.5% target is capping the winners at the wrong scale.** It was set at "twice the 3-day drift" for the eleven
  mega-caps; in small caps the 3-day sd is 6–8% and a target at 2.5% converts the right tail into a coin.
- **The stress charge assumes an overnight that the trade does not need.** `stress_charge = stop + p95 |gap|` sizes the
  book for a hold across the one segment (gap 0→1) that is negative and the ones (1→2, 2→3) that are worth ≤0.13%.
- **The exit clock is 15:45 into the thinnest 15 minutes before the auction**, when the closing cross carries 13.5% of
  the day's volume in these names; MOC at 15:55 is both cheaper and +0.04% better.

## 4. VERDICT

The post-print down-drift outside the mega-caps is a **session** phenomenon: the day+1 open→close is the one segment
that carries a resolvable number (+0.28% to +0.41%, t 4.2–4.9, 1,250–3,800 legs), the overnight after day 0 is a
bounce against the short (−0.11%, t −3.5), and every later overnight is worth ≤0.13% while costing borrow and a p95 gap
charge; the 15-minute sample (n=60, MDE 2.6%) shows no dead-cat bounce to wait out inside the first 30 minutes — the
bounce is in the gap — so **09:45–10:00 ET entry, 15:55 MOC exit, flat overnight** is the exact timestamp pair, and it
lets the sizer drop the gap allowance and buy 2–3× the notional per unit of declared risk. The current code has the
right window in gross terms (95–103% of the close-to-close drift) and then destroys it with a 3% stop / 2.5% target
pair that closes 77–91% of positions on names whose day+1 range breaches the stop 28–43% of the time; its realistic
net capture is under a third of the measured +0.44%. The unresolved and dangerous part is that the UP side shows the
same RAW clock (overnight positive, session negative), which is the retail attention tug-of-war rather than PEAD; the
non-print placebo in §2 is the next measurement, and if it fires the lane's universe is every large down mover and its
name is wrong.
