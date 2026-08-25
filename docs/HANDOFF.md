# HANDOFF — read this first

**Updated 2026-08-25 evening, sandbox session 3 (Fable).** Competition derivative
of the Aegis-Finance research project (`AEGIS_SOURCE_COMMIT=44c8352`).
Previous handoff text is in git history (`2561449`); this one supersedes it.

## NIGHT SESSION 4 (25→26 Aug, autonomous) — `docs/ROADMAP_2026-08-25_NIGHT.md` has the chunk status

**RESULT IMPROVEMENT: one more idea killed before it cost money, two live-book defects
fixed, the 4 Sep trade frozen.** The RELAY is refuted on 290 real relay legs (mean −4.2%,
hit 34%, t −2.0; the ratio does not sort — `docs/FINDING_2026-08-26_RELAY_REFUTED.md`), so the
afternoon's ARM/TSM ranking stays shadow. Reading the live book found that one-position-per-
symbol was per PASS (dev re-bought QQQ x4→x8, a second NVDA condor) and that two loops on one
unlocked hash chain broke it at line 1203 — both fixed and tested, corrupt lines counted not
rewritten. Dev then hit the 50% cap on a Tuesday → `EVENT_RESERVE` keeps 10% for 4 Sep.
Built: `scripts/nfp_trade.py` (frozen contract, two gates, entry window enforced),
`scripts/dashboard.py` → `state/dashboard.html`, `scripts/belief_recorder.py` (hourly crowd
series), `scripts/attention_vol_basis.py` (result below when it lands), `Dockerfile` +
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
