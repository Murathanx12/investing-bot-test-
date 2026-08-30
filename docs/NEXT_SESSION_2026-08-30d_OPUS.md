# NEXT SESSION FOR OPUS — 2026-08-30 (d) — THE TRACKER: A WHOLE-MARKET WATCHLIST THAT LEARNS

Fable, Sun 30 Aug ~19:00 SGT (07:00 ET). Supersedes §2 of `NEXT_SESSION_2026-08-30b_OPUS.md`
for what the book selects FROM; keeps everything else. Plain language on purpose.

## 0. Session 26 validated — and the one decision

`30180dd` + `31138c3` are correct: 56 suites / 2,432 checks, `fleet --check-all`
green, the two-clock catalyst fix is right (a forward date asks "did we know
the date", not "had it happened"), T12 closed negative on a real answer, hack2
is between earnings waves (42 of 47 chances land 2–4 Sep). The MOC deferral
was the right call the night before a session.

**Murat's verdict on the output: not acceptable — one name, a past winner.**
MU is up ~700% in a year and the rule still fired because "down 23% from the
60-day high" says nothing about the 12-month path, and because the 151-name
universe is mostly mega-caps with dozens of analysts. He is right, and the
50.8% base rate is a property of that universe too.

**Push decision (Fable's recommendation to Murat): PUSH.** The commit is the
numbers-for-every-name change plus the calendar fix. MU alone is ≤ 8.3%
notional × 8% stop = −0.66% of hack3 worst case; the −8% bound only binds at
12 names. The tracker below widens the list for Tuesday's seal.

## 1. What Murat asked for (his words, cleaned)

> Have a big list of stocks we keep track of. The list adapts: we add potential
> winners and drop losers, like a firm's strong-buy / hold / sell. Then we have a
> list of potential candidates, and on the paper accounts we test how we make
> portfolios from it — balanced, profit-maximising. That is how the project gets
> better every day: it accumulates its OWN data instead of relying on other
> sources, and later we train the NN on it. Pull every strong-buy from analysts —
> even names with ONE review, not just mega-caps with dozens — see which have the
> most % upside and what the consensus is, add our own findings to the list, and
> build multiple portfolios from there.

This is the right architecture and it is also a fix for the survivorship bias
we keep paying for: a list that is rebuilt from the whole market every day,
with its history kept, is a point-in-time screen that we own.

## 2. Data — measured today, all free

| source | gives | cost / limits | probe |
|---|---|---|---|
| Finnhub `/stock/recommendation` | strongBuy/buy/hold/sell counts, monthly, ANY covered name | free, 60/min → ~5,000 names in ~85 min | SLDP 8 analysts, KYTX 12, MU 56 |
| yfinance `Ticker.analyst_price_targets` | current, mean, high, low target | free, unofficial, ~2/s with backoff | SLDP mean 6.875 vs 2.33 = 2.95× |
| Finnhub `/stock/price-target` | consensus target | **403 — paid. Do not use.** | |
| Alpaca `/v2/assets` | the tradable universe (active, US equity, not OTC) | free | ~10k symbols |
| WRDS IBES (Aegis repo, `scripts/actor_corpus_ibes.py`) | consensus targets + recs, whole US market, **point-in-time 2013-2024** | already licensed | the backtest source — never the live one |

Rate-limit rule from memory: a 429 reads as absence. Retry, and report
**coverage by symbol count**, not just rows.

## 3. Build: `alpha/tracker.py` + `scripts/tracker.py` (do this first, ≤ 5 h)

### 3a. Universe = every active US common stock on Alpaca with ≥ 1 analyst

Nightly (`--refresh`): assets → Finnhub rec counts → yfinance targets → last
close, 60-day high, 12-month return, sector (yfinance `info.sector`, cached),
market cap bucket → next dated catalyst from the corpus calendar. One row per
symbol per day, **append-only** `state/tracker/YYYY-MM-DD.parquet` + a
`latest.json`. Every row carries `observed_at`. This file IS the dataset Murat
wants to accumulate; nothing ever rewrites a past day.

### 3b. Our rating, computed, per name, every day

```
upside          = mean_target / close − 1
consensus       = (5·strongBuy + 4·buy + 3·hold + 2·sell + 1·strongSell) / n_analysts
coverage_bucket = 1–3 / 4–10 / 11–25 / 26+
drawdown_60d    = close / high_60d − 1
ret_12m         = 12-month return
past_winner     = ret_12m in the top decile of its sector  (Murat's objection, as a number)
days_to_catalyst
p_up, exp_return, downside, confidence   <- from the book's generators once they run on the tracker
```

Status, by rule, frozen in code:

```
STRONG_BUY  upside ≥ 0.50 and consensus ≥ 4.1 and not past_winner and catalyst ≤ 21 sessions
BUY         upside ≥ 0.30 and consensus ≥ 4.0 and not past_winner
HOLD        already on the list and still upside ≥ 0.15
SELL        upside < 0.10, or consensus < 3.5, or a stop hit on any book
DROP        off the list after 5 sessions at SELL, or delisted / < $1 / OTC
```

A name enters the **candidate list** at BUY or better, leaves at DROP. The
transitions are logged (`state/tracker/transitions.jsonl`) — that log is the
"add potential winners, drop losers" history and the future NN label source.

### 3c. Per-sector view

`scripts/tracker --sectors`: for each sector, top 10 by `upside` among
BUY/STRONG_BUY, with coverage bucket and consensus beside them. This is the
"track of good stocks per sector and expected outcome" — a table, refreshed
daily, kept.

### 3d. The book selects FROM the tracker, not from the 151

`prediction_book` gains `--universe tracker`: `murat_rule_v1` runs on every
BUY/STRONG_BUY name. Clause (f) added: `not past_winner`. Clause (g):
`coverage_bucket ≤ 11–25` preferred — report the claims split by coverage
bucket so we can see whether thin-coverage names behave differently (that is
Murat's hypothesis, stated as a question).

## 4. Portfolios = the paper books (PRODUCT_EXPERIMENT each, own selector)

| book | personality | construction from the candidate list |
|---|---|---|
| hack3 THESIS | **balanced** | top 10 by `exp_return − |downside|`, equal weight, ≤ 8.3% notional each, one sector ≤ 30% |
| hack4 PREDATOR | **profit-max** | top 5 by `upside × consensus`, ≤ 10% each, catalyst inside 21 sessions required |
| hack6 BLEND | **preservation** | top 15 by confidence, ≤ 6% each, coverage bucket ≥ 4–10 only |
| hack1/hack2/hack5 | unchanged | anchor / drift / convex keep their mandates |

Worst case printed per book before deploy: `n × notional% × 8%` — hack3 −8.0%,
hack4 −4.0%, hack6 −7.2%. All inside −9%. Gross cap unchanged.

Each book's fills, stops and exits write back to the tracker row
(`held_by`, `entry`, `exit`, `pnl`) — that is the loop that makes the dataset
ours.

## 5. Backtest the watchlist rule where it is NOT in-sample (Aegis repo)

The 50.8% was measured on the 152 names the book ranks. Run the SAME status
rules on IBES + CRSP, 2013–2024, whole market, monthly, in the farm
(`portfolio_farm`, costs on): terminal wealth of the STRONG_BUY / BUY basket vs
the market, split by **coverage bucket** and by **past_winner**. This answers
Murat's two hypotheses directly — "thin coverage has more upside" and "don't
buy the past winner" — with 11 years instead of 11 months. Report by decade.
If thin-coverage STRONG_BUY beats the market net of costs, the tracker's
weighting changes; if not, it stays equal-weight and the row says so.

## 6. Order of work

1. §3a–3b tracker refresh, run tonight (85 min for Finnhub; yfinance overnight).
2. §3d book on the tracker → Tuesday's seal has many names, not one.
3. §4 hack3 balanced basket wired (worst case printed) → deploy after
   `fleet --check-all`.
4. §5 farm backtest (Aegis repo) — can run in parallel with 1–3.
5. §3c sector table in the premarket digest.
6. Then back to `NEXT_SESSION_2026-08-30b_OPUS.md` §3–§5 (T13 fantasy
   transposition, funnel) — the tracker rows are what the decider will rank.

Handoff opens with the scoreboard: fleet equity, tracker size (symbols with
≥ 1 analyst), candidate list size, claims per generator, worst case per book.
