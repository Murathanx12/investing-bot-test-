# FINDING 2026-08-25 (evening) — the surface, the strip, the short side, walk-forward

**Receipt:** `state/event_surface_backtest.json` (`python -m scripts.event_surface_backtest`).
**Data:** the same 117 SEC-dated prints as `FINDING_2026-08-25_STRADDLE_BACKTEST.md`,
112 reconstructed with five front strikes (K, K±w, K±2w) and a back-expiry ATM
straddle, all at expired-contract CLOSES. `w` = one implied move rounded to the
strike grid. Everything below is **walk-forward**: event *t* sees only events
before *t*, for the name's prior AND for the tercile cut-offs.

## 1. EVENT_VARIANCE_STRIP — built, measured, and it did not help

Two expiries solve `σ²T = aT + J` for ambient variance `a` and event jump `J`.

| | median |
|---|---|
| event share of front-expiry variance | **84.8%** |
| market jump sd `√J` | 8.21% |
| raw implied move (straddle/spot) | 7.56% |
| realised \|move\| | 6.21% |

The decomposition is real (the print is ~85% of what the front expiry is
charging for), and the premium is confirmed in the clean quantity. **But as a
predictor of the realised move it is worse than the contaminated one:**

| predictor of realised \|move\| | corr |
|---|---|
| raw front implied move | **0.334** |
| stripped market jump sd | 0.182 |
| our walk-forward prior (RMS of the name's last 8 prints) | 0.287 (n=76) |

Two readings. The chain's raw number already contains information the strip
throws away (the back expiry is noisy at closes, and its own event premium is
not zero). And **our history is a weaker forecaster of the size of a print than
the chain is** — the market's number beats the name's own last eight prints.
`event_move` therefore keeps the raw comparison; the strip stays as a
diagnostic (`alpha/surface.py`) and as the relay's per-name denominator.

## 2. SHORT STRUCTURES — "long straddle loses" did not make any short a winner

Unconditional, return on max loss, n=112 at closes:

| structure | mean | median | hit | t |
|---|---|---|---|---|
| long straddle | −0.5% | −19.6% | 40% | −0.09 |
| long strangle (K±w) | +1.8% | −51.7% | 37% | 0.15 |
| **iron butterfly** (short K straddle, long K±w) | **+5.2%** | +1.4% | 51% | 0.70 |
| iron condor (short K±w, long K±2w) | −1.1% | +13.7% | 63% | −0.30 |
| call debit spread | +12.4% | −43.6% | 40% | 0.84 |
| put debit spread | +1.0% | −39.3% | 43% | 0.11 |

Nothing clears |t| = 1. The condor wins 63% of the time and loses money on
average — its wings are where the tail events land, exactly the trap the review
named. NVDA alone was 8/8 for the condor; the population is not NVDA.

## 3. THE CONDITIONAL RULE, walk-forward — survives weakly, on the SHORT side

Rule: gap = (name's prior mean |move|) − (implied at entry); terciles from
gaps observed before *t*; top → long straddle, bottom → iron butterfly, middle
→ no trade.

| | n | mean | median | hit | t |
|---|---|---|---|---|---|
| naive gap (history − raw implied) | 46 | **+15.0%** | +16.2% | 61% | **1.41** |
| stripped gap (history − market jump sd) | 47 | +6.9% | +4.4% | 53% | 0.72 |

By bucket (naive): bottom tercile — chain prices MORE than history — iron
butterfly **+20.9%, hit 61%** (n=28) while the straddle there loses −8.4% at 32%;
top tercile — history above chain — straddle only +5.9% (n=18). So the
in-sample "+16% / −7%" of the morning became, out of sample, "the short side
of the sort pays, the long side barely does". At 75 events (before the
optional-wing fix) the same policy read t=0.07; at 112 it reads 1.41. **That
swing is the sample size talking, not the rule** — treat it as a candidate
that has not failed, not as an edge.

## 4. SKEW_DIRECTION — nothing

IV(call K+w) − IV(put K−w) at entry vs the signed move: hit **45.3%** (n=106),
strong-tercile 48.6%, corr 0.09. A debit spread in the skew's direction shows a
+40% mean on a −74% median — one print. The surface's asymmetry does not tell
us which way a mega-cap print goes at this horizon. Retired from the current
search; the volatility-spread literature used option order flow we do not have.

## 5. CURVATURE — the RoF 2025 signature reproduces, weakly

70 of 112 surfaces were CONCAVE (wings priced below the body) at entry.

| surface | n | median realised | median implied | long straddle | iron butterfly |
|---|---|---|---|---|---|
| concave | 70 | **6.39%** | 7.52% | −3.6% (hit 39%) | +7.5% |
| convex | 42 | 5.97% | 7.79% | +4.7% (hit 43%) | +1.5% |

Concave surfaces precede slightly larger moves and pay convexity buyers worse —
the paper's direction, at a size that does not decide anything on its own.
`alpha/surface.py` reports `shape` on every live reading so the event card can
say "the market has already bought the tail".

## 6. UNCERTAINTY RELAY — first live reading, NVDA print of 26 Aug

`python -m scripts.uncertainty_relay NVDA --event 2026-08-27 --expiry 2026-08-28`
(`state/relay/NVDA_2026-08-27.json`). Each peer's history of moving on NVDA
print days (last 8) against what its own chain charges to the expiry spanning
the print, stripped against the next expiry:

| name | cond. jump sd (history) | market jump sd | ratio |
|---|---|---|---|
| **ARM** | 6.49% | 3.96% | **1.64** |
| **TSM** | 2.91% | 1.91% | **1.52** |
| SOXX | 3.07% | 2.98% | 1.03 |
| MU | 5.35% | 5.27% | 1.02 |
| AVGO | 3.21% | 3.58% | 0.90 |
| SMH | 3.08% | 3.62% | 0.85 |
| QQQ | 1.39% | 1.63% | 0.85 |
| AMD | 3.62% | 4.78% | 0.76 |
| **NVDA** | 4.75% | 6.77% | **0.70** |

The originator is the most expensive place to own its own print; ARM and TSM
charge less than their measured co-movement. No surface in the set is concave.
This is a ranking of candidates for the structure engine, not an order — and
after §1 it carries the caveat that history under-forecasts size relative to
the chain, so a ratio of 1.5 is not 50% of edge.

## 7. EVENT_CONTRACT_BASIS — the NFP direction channel is dead

`python -m scripts.event_contract_basis --release 2026-09-04`. First-print
headlines from ALFRED vintages (no revision leakage), surprise = print minus
the mean of the prior three first prints, SPY move prior close → 10:45 ET:
corr **0.026** in-sample, **−0.573** walk-forward (n=18) — the sign of "good
news" flips by regime. The Kalshi ladder (crowd expects +50k, 15% mass on each
tail) therefore cannot be turned into a side; the mixture collapses to the
residual sd (1.23%) and says P(|move| > typical 0DTE break-even 0.77%) = 53%.
The trade, if taken, is a WIDTH trade with the crowd's dispersion as its only
input from this channel. The SPY 4 Sep strip reads a 1.5% jump sd, but that
window also spans the NVDA print and the holiday — the comparable number is
the 0DTE straddle at the 3 Sep close.

## What changed in code because of this

- `alpha/surface.py`: geometry (ATM IV, skew, curvature, shape) and the strip,
  from any `ChainSnapshot`; tested against a planted jump (recovers 6.00%).
- `scripts/event_surface_backtest.py`, `scripts/uncertainty_relay.py`,
  `scripts/event_contract_basis.py`; all write receipts.
- `alpha/runner.py`: **EVENT_NODE_CAP = 25%** — positions that cite the same
  `event_date` or `theme` share one budget; the fourth 8% expression of one
  print is refused with the node named. Tested.
- `scripts/agent_loop.py`: `--brains/--shadow/--profile/--universe` so the two
  accounts run champion vs challenger, not two copies.
- `event_move` is unchanged: the strip did not earn its way in.
