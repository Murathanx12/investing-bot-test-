# AGENT 1 — SMALL-CAP PREDATOR — 2026-08-26

Scope: US equities $150M–$5B. The universe carries NO market cap (`market_cap_usd` is null on all 4,634
members; `cap_bucket` has never run), so "small cap" below means the `small` DOLLAR-VOLUME bucket
($10M–$50M/day) with `mid` ($50M–$300M) reported beside it — stated as a proxy, not pretended to be a cap screen.
Every number here was computed read-only from `state/pead_wide_legs_v1.jsonl` (25,856 legs), the
`state/sec_cache/` 8-K item codes (102,418 releases), `state/pead_wide.json`, `state/pead_adversarial_v1.json`,
and 233 8-K bodies fetched live from EDGAR. Scripts ran in the session scratchpad; nothing in the repo was modified.

**One convention change runs through everything: the legs file records LOG excess returns, and a short's P&L
is SIMPLE.** `short_simple = -(exp(fwd_excess) - 1)`. Every "shortSIMPLE" figure below is that.

---

## 1. STRATEGY — DEPARTURE PRINT (short the small-cap earnings 8-K that also carries Item 5.02)

**Economic mechanism.** Item 5.02 exists because the SEC forces disclosure of an officer/director departure
within four business days. Bundling it into the earnings 8-K (Item 2.02) is the "bury it in the print" pattern.
Day 0 prices the EPS/guide; the governance information — a CEO/CFO/COO/President leaving on a big print —
is processed over the following sessions, because a $10–50M/day name has few analysts and the print already
saturated attention. It is a compound-event underreaction, and it is DIRECTION-BLIND: an UP print with a
departure fades too. That is the difference from the champion (PEAD refuses UP; this lane shorts UP).

**Exact signal (PIT).** For a name in the universe:
```
release  = latest SEC 8-K with "2.02" AND "5.02" in items, acceptanceDateTime -> session (bmo/amc)  [alpha/sources/sec.py]
day0     = first close reflecting the release (bmo: same session; amc: next)                       [event_days_from_sec]
r0       = ln(close_day0 / close_day0-1)                                                            [Alpaca SIP daily bars]
fire     = |r0| > 0.082  AND  "5.07" not in items  AND  dv_bucket == small  AND  shortable & easy_to_borrow
class    = DEPART_CSUITE if the Item 5.02 body (EDGAR primary doc, item title stripped) matches
           (resign|retire|step down|terminat|separation|departure of|will cease) AND (CEO|CFO|COO|President|chief ...)
           within the first 600 chars; else NO_TRADE                                               [one GET, free]
```
**Entry.** Short at the day+1 OPEN (the champion's measured entry; the legs' forward window is sessions +1..+3
from the day-0 close). If the classifier cannot fetch or parse the body: NO TRADE, never "assume departure".

**Exit.** Close at the day+3 close (the measured window). No target, no trailing — the 10/21-session horizons
in `state/pead_wide.json` say drift after a print does NOT persist (mid band: −0.15% at 10 sessions, −0.22%
at 21), so holding longer is an unmeasured bet.

**Sizing.** Declared stop 8% + measured p95 overnight gap (the `alpha/engine/equity.py` stress-loss charge).
Risk 1% of equity per leg on that charge (~$1,000 on $100k ⇒ ~$8–10k notional per name); max 3 legs open;
cap per name 10% of equity; cap on names sharing an event week 25%. Never above 20% of the name's median
daily dollar volume per fill.

**Transaction-cost model.** Round trip 30 bp (small-bucket spreads; the adversarial receipt's own number);
borrow: ETB names 0.5–3%/yr ⇒ 1–3 bp for 3 sessions; hard-to-borrow ⇒ refused. Gap risk is charged, not
priced: the stress charge is the max loss the sizer sees; the theoretical short loss is unbounded and the row
says so.

**Backtest numbers (this repo's legs, 2024-02 → 2026-08, all `5.02`-bundled prints without `5.07`, |day0| > 8.2%):**

| slice | n | shortSIMPLE | median | hit | t iid | t week-cluster | t issuer-cluster |
|---|---|---|---|---|---|---|---|
| all buckets, both directions | 270 | **+1.15%** | +1.31% | 0.578 | 2.53 | 2.54 (89 wk) | 2.55 (225 issuers) |
| `small` dv bucket | 94 | **+2.23%** | +2.53% | 0.596 | 2.54 | 2.73 (51) | 2.48 (78) |
| `mid` dv bucket | 92 | +0.11% | +0.71% | 0.565 | 0.16 | 0.17 | 0.17 |
| DOWN day-0 | 167 | +1.03% | +1.47% | 0.575 | 1.88 | 1.70 | 1.96 |
| UP day-0 | 103 | +1.34% | +1.18% | 0.583 | 1.70 | 1.72 | 1.68 |
| 2024 / 2025 / 2026 | 84/102/84 | −0.69% / +2.18% / +1.73% | | 0.49/0.61/0.63 | −0.89 / 2.62 / 2.59 | | |
| EDGAR body = C-suite DEPARTURE, `small` | **48** | **+2.42%** | +3.17% | **0.67** | 2.44 | — | — |
| EDGAR body = non-C-suite departure, `small` | 15 | +0.16% | −0.68% | 0.40 | 0.09 | — | — |
| EDGAR body = APPOINTMENT only, all buckets | 49 | +0.32% | −1.33% | 0.45 | 0.22 | — | — |

Stratified placebo (5.02 label re-drawn 1,000× inside the same band × bucket × sign cells):
observed +1.15% vs placebo +0.21% (sd 0.49%), **z 1.93, p 0.027**; small+mid subset z 1.69, p 0.043.
The mid band (3.5–8.2%) with 5.02 is dead (n 206, −0.00%). The mechanism lives on big prints only.

**Honest reading.** t ≈ 2.5 on 94 legs after several post-hoc cuts, 2024 negative, and a regex classifier
(FFIV and DECK were mis-tagged); a 36-leg random draw of the same set averaged −0.73%. This is a
`PRODUCT_EXPERIMENT` with a coherent mechanism split (C-suite +2.42% vs non-C-suite +0.16% is the shape the
story predicts), not a claim.

**Falsifier.** Prospective: after 40 paper legs, mean shortSIMPLE net of 30 bp < +0.5% OR hit < 0.52 ⇒
`FAILED_VARIANT`. Retrospective, cheaper and first: re-run the classifier on all 760 `5.02` legs — if
C-suite-departure legs do not beat appointment-only legs by ≥ 1.0% at |day0| > 8.2%, the mechanism is
"any extra item" noise and the lane is not built.

**Placebo.** (a) the stratified re-labelling above, re-run per release; (b) `5.07` (annual-meeting votes)
and `1.01` (material agreement) as extra items: −0.41% (n 71) and +0.37% (n 311) — neither carries it.

**Matched control.** Same |day0| band, same dv bucket, same sign, same week, no 5.02, shorted both sides:
n 4,699 small+mid, shortSIMPLE **+0.20%** (t 1.81, week-t 1.10). The departure premium over its matched
control is ~+1.0% (all buckets) / ~+2.0% (`small`).

**Expected failure mode.** A squeeze: the worst five legs are −20.3%, −19.6%, −18.1%, −16.7%, −15.4%
(AEVA +17% is the best). Trimmed-5% mean is +1.09%, so the mean is not made by the tails, but one 20% gap
on a 10% position is a −2% day for the book. Second mode: "departure" is a planned retirement with a named
successor, which the regex does not always separate.

**Stock expression.** Short shares, ETB only (262 of 270 legs are ETB today; the 8 non-ETB legs carry +0.18%).

**Option expression.** None. The edge is 1–2% of spot over three sessions; small-cap puts give that back in
half-spread, and the claim is a GRADIENT (`shape.py`: size, not convexity). If a chain exists with < 5% wide
markets, a put debit spread is the only structure worth enumerating, and the engine already refuses wide ones.

**Backtest script.** `scripts/departure_print.py` — joins `state/sec_cache` items to `pead_wide_legs_v1.jsonl`,
fetches every `5.02` primary doc once (cached under `state/sec_cache/docs/`), classifies, and writes
`state/departure_print_v1.json`: per-leg class, shortSIMPLE, band, bucket, the table above with iid /
week / issuer / two-way t, the 1,000-draw placebo, the matched control, and 10/21-session horizons once
`pead_wide` carries them for the big band. Receipt fields `n_classifier_failed` and `n_not_etb` are mandatory.

**Prospective shadow record** (written BEFORE the first order, `state/shadow/departure_print/<sym>_<day0>.json`):
symbol, release accession, acceptanceDateTime, session, items, day0, r0, dv bucket, ETB flag, classifier
class + the 600-char body it read, planned entry (day+1 open), planned exit (day+3 close), stress charge,
notional, policy hash of this document. The resolved row is appended, never rewritten.

**What fires tomorrow.** In the last ten days the cache holds two bundled prints — FN (08-17, `large`,
−21.5%, window spent) and BJ (08-21, `mid`, no big move). **Zero qualifying legs.** The lane opens at zero.

---

## 2. ATTACK — the wide DOWN-PEAD short lane is measured in a unit a short cannot earn

**The finding is in LOG returns. A short is paid in SIMPLE returns, and the difference is most of the edge.**
The legs record `fwd_excess` as a 3-session log return; `signed` flips its sign. For a short position the
realised P&L is `-(exp(fwd) - 1)`, which is strictly below `-fwd`, and the gap grows with the variance of the
leg — i.e. exactly on the squeezes. Recomputing every DOWN leg:

| slice | n | log signed (as reported) | t | **shortSIMPLE** | t |
|---|---|---|---|---|---|
| DOWN ≥ 3.5% (the lane) | 7,481 | +0.54% | 6.70 | **+0.29%** | 3.30 |
| DOWN ≥ 5% (where the response curve starts) | 5,923 | +0.64% | 6.75 | **+0.36%** | 3.56 |
| ≥ 5%, `small` | 1,942 | +0.74% | 4.69 | +0.50% | 3.09 |
| ≥ 5%, `mid` | 1,925 | +0.42% | 3.09 | **+0.24%** | 1.79 |
| ≥ 5%, `micro` | 1,226 | +1.02% | 3.59 | +0.48% | 1.41 |
| ≥ 5%, `large` | 698 | +0.29% | 1.33 | +0.12% | 0.56 |

Nearly half the headline is Jensen's inequality. The median is unchanged (+0.59% both ways) — the loss is
entirely the tail: the worst leg is `fwd_excess = +1.135` log, which the file books as a −113% short and a
real short pays as **−211%**. Now apply the adversarial receipt's own cost line: 30 bp round trip takes
+0.36% to **+0.06%** on the ≥ 5% lane and +0.24% to **−0.06%** in the `mid` bucket. Only `small` survives
(+0.50% → +0.20%), at t ≈ 1.2 net.

Three more numbers on the same file:

1. **Seasonality is not "6 of 11 quarters negative"; it is monthly regimes.** DOWN ≥ 5% by month: 2025-04
   **−0.98% (t −2.56)**, 2025-12 −2.30%, 2026-01 −1.28% (t −2.06), 2026-07 **−1.25% (t −2.85)**, against
   2024-08 +2.08% (t 5.52) and 2026-05 +2.20% (t 5.62). Three months (2024-08, 2025-02, 2026-05) supply
   the majority of the summed excess. A five-session competition window is one draw from that distribution.
2. **The 3-day drift is not a drift.** `state/pead_wide.json` `hold_horizons_mid_band`: signed excess
   **−0.15% at 10 sessions (t −1.34) and −0.22% at 21 (t −1.37)**; `micro` −0.65% at 10 (t −2.13). Whatever
   is earned by session +3 is given back by session +10. That is a liquidity-rebound pattern, not
   information diffusion, and it means the exit must be mechanical at +3 — one late fill flips the sign.
3. **Survivorship and borrow.** All 2,511 leg symbols are members of TODAY'S universe; any name that
   delisted between 2024-02 and 2026-08 is absent, so the tail a short is paid for (collapses) and the
   tail it is killed by (takeovers at a premium after a bad print) are both unmeasured. The `not ETB
   today` DOWN ≥ 5% legs carry **+1.22%** against ETB's +0.36% — the best legs are in names the venue
   will not lend.

Verdict on the lane: real in log space, marginal in dollar space, and its only tradeable bucket (`small`)
nets ~+0.2% per 3-session leg before a stress charge that the same bucket's gaps make the largest.

---

## 3. VERDICT

With $100k paper tomorrow I would trade **nothing** in this scope: the DEPARTURE PRINT lane has zero
qualifying legs (FN is `large` and spent, BJ did not move), and the champion's DOWN-PEAD short, in the unit a
short is actually paid in, is +0.06% net per leg outside the `small` bucket. I would spend the session
writing `scripts/departure_print.py`, running the classifier over all 760 bundled legs, and writing the
lane's frozen contract, so that the first C-suite-departure print in a `small` name after 2026-08-27 opens a
shadow row and, if the adversarial receipt survives, one $8–10k short at the day+1 open with a mechanical
day+3 exit. I would refuse: any short in the `mid`/`large` buckets on this evidence, any hold past session
+3, any leg the classifier could not read, any non-ETB name, and any option expression of a 1–2% gradient.
