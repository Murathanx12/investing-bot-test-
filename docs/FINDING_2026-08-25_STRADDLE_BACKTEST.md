# FINDING 2026-08-25 — the chain already knows these names print

**Receipt:** `state/event_straddle_backtest.json` (`python -m scripts.event_straddle_backtest`).
**Data:** Alpaca daily bars for EXPIRED option contracts (free plan), SEC 8-K
Item 2.02 release dates (exact, with session), 12 names, 117 prints, Feb 2024 →
Aug 2026. ATM straddle at the nearest weekly after the print, bought at the
close before the release and sold at the close after, at **closes** (no
spread paid — so every number here flatters the long side).

## Pooled

| | |
|---|---|
| prints | 117 |
| median implied move (straddle / spot) | **7.6%** |
| median realised \|close-to-close\| | **6.3%** |
| straddles that cleared their own break-even | **43%** |
| median straddle return | **−18%** |
| mean straddle return | −0.1% (a few big winners) |
| paired t, realised − implied | **−2.24** |

The chain, on average, prices these prints *higher* than they realise. An
unconditional long straddle into a mega-cap print is a losing trade on our own
data, before spreads. This agrees with the recent literature (BSIC 2011–21
re-test of Gao–Xing–Zhang: +1.2% gross, −9.1% net).

## By name — it is two-sided

| name | n | median implied | median realised | cleared BE | mean ret | median ret | t |
|---|---|---|---|---|---|---|---|
| **NVDA** | 8 | 7.0% | 3.2% | **0 / 8** | **−46%** | −46% | **−4.37** |
| PANW | 6 | 8.0% | 6.5% | 17% | −33% | −34% | −2.50 |
| AAPL | 10 | 5.2% | 2.0% | 20% | −17% | −28% | −3.19 |
| GOOGL | 10 | 6.6% | 3.9% | 40% | −13% | −34% | −1.58 |
| AMZN | 10 | 8.1% | 5.9% | 40% | −13% | −20% | −1.68 |
| MU | 10 | 10.1% | 9.0% | 50% | −3% | +8% | −0.68 |
| AMD | 10 | 8.4% | 7.7% | 40% | +8% | −16% | +0.10 |
| META | 9 | 7.5% | 8.7% | 56% | +5% | +4% | −0.20 |
| MSFT | 10 | 5.2% | 5.2% | 60% | +14% | 0% | +0.46 |
| NIO | 9 | 11.3% | 11.5% | 67% | +14% | −21% | −0.81 |
| TSLA | 17* | 6.6% | 5.2% | 47% | +21% | +7% | +0.34 |
| **AVGO** | 8 | 8.6% | 10.1% | **63%** | **+32%** | +22% | +1.18 |

\* TSLA's 17 rows are real: Tesla files an Item 2.02 8-K for quarterly DELIVERIES as well as earnings, so both are event days.

## The conditional sort (the literature's result, reproduced here)

Rank each print by *(mean realised move over the name's PRIOR prints) − (implied
move at entry)*, n = 81 with ≥3 priors:

| tercile | mean straddle return | hit rate |
|---|---|---|
| history > implied (top) | **+16%** | 56% |
| middle | +4% | — |
| implied > history (bottom) | **−7%** | 30% |

The sign of the gap between a name's own history and its chain predicts which
side of the straddle pays. That is the whole `event_move` thesis, and it is
**two-sided**: when the chain prices more than the history, the condor is the
trade, not the straddle.

## What changed because of this

1. **The NVDA straddle for 26 Aug is withdrawn.** `event_move` had forecast an
   8.7% (then 6.6%) event sd from a 12–14 print history reaching to 2023 and
   proposed a long straddle at 18.5% risk. On the last eight real prints that
   trade lost every time. After the fix (`RECENT_EVENTS = 8`, recent mean
   3.8%, sd 5.7% vs 5.0% implied) the brain REFUSES the NVDA straddle and
   still buys AVGO's (recent mean 10.7% vs 8.6% implied). `vol_gap`'s iron condor on the same chain was the
   historically right side. The brain-vs-brain grade tomorrow is now an
   out-of-sample test of *this* finding.
2. `event_move` weights the **last 8 prints** (`RECENT_EVENTS`); the full history
   is recorded as context. A print distribution is not stationary across a
   regime.
3. Event dates come from **SEC 8-K Item 2.02** (exact, with release time);
   inference is the fallback for 6-K filers only. The inferred list had padded
   NVDA with the 2025-01-27 DeepSeek selloff and AMZN with a non-print day.
4. Per-name history, not a pooled prior: AVGO and TSLA buy convexity; NVDA,
   PANW, AAPL sell it (defined-risk).

## Caveats, stated once

- Closes, not crossed quotes; real straddles pay ~5% relative spread each way.
- n = 6–10 per name; the conditional-sort result is in-sample and unregularised.
- TSLA n = 17 because deliveries releases (early Jan/Apr/Jul/Oct) are also
  Item 2.02 filings; they are genuine scheduled events and are kept.
- Every name's rows and dates are in the receipt. Print the dates before
  trusting the statistic.
