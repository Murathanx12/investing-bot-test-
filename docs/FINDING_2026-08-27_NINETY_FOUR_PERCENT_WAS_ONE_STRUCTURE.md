# FINDING — 94.5% of the realised loss is one structure, and it is not the one anyone was arguing about

`python -m scripts.pnl_forensics --all --json` · receipt `state/pnl_forensics.json`
· read from the venue 2026-08-27, ~12:40 ET.

## THE NUMBER

Both losing books, realised only — closed contracts, net cash, reconciled
against the positions the venue actually holds.

| | realised |
|---|---|
| dev (`PA32Q5IW7TAS`) | **−$14,335** |
| exp1 (`PA3AOJPJTSBW`) | **−$8,971** |
| **combined** | **−$23,306** |

| structure | realised | share of loss |
|---|---|---|
| **`long_straddle`** | **−$22,017** | **94.5%** |
| `long_call` | −$1,005 | 4.3% |
| `iron_condor` | −$284 | 1.2% |

**Everything that is not a long straddle, combined, cost $1,289.**

Slippage against the quotes the engine decided on, deduped by order id:
**−$757, or 3.2% of the loss.** Execution is not the story. Every dollar was
opened on **2026-08-25**, in one session.

## FOUR THINGS THIS OVERTURNS

**1. NVDA was not the problem. It cost $284.**

| underlying | realised |
|---|---|
| SPY | **−$7,849** |
| QQQ | **−$6,862** |
| AVGO | −$4,692 |
| TSLA | −$4,675 |
| AMD | −$3,075 |
| NVDA | **−$284** |
| IWM / NIO | −$53 / −$48 |
| AAPL | +$406 |
| MSFT | +$782 |
| META | **+$3,044** |

**SPY and QQQ alone are 63% of the realised loss.** The reviews spent their
length on NVDA-vs-AMD proxy selection and causal distance — a real architectural
question, and worth ~13% of the damage. The book died on **broad index
volatility**, where there is no proxy question at all, no causal graph, and no
stock selection: it simply bought the index's absolute move and the index did
not move enough.

**2. The NVDA condors did not lose $5,629.** That figure is an unrealised mark
from 25 Aug that has since largely recovered; realised, iron condors across both
books are **−$284**. Short premium into a print has not been shown to lose here.
It was already correct not to refuse it in `alpha/refuted.py`; this is the
receipt.

**3. "Every option structure lost" is false, and so is "QQQ +56% / SPY +23% were
the winners."** Both describe unrealised marks on open positions. In realised
dollars long calls are **−$1,005**. The honest sentence is narrower and more
useful: *the structure that pays on the ABSOLUTE move lost; the structures that
pay on the SIGNED move and on the move being SMALL did not.*

**4. It is not a brain problem in the way the quarantine implies.** All three
brains lost, in proportion to how much straddle they bought:

| brain | realised |
|---|---|
| `vol_gap` | −$14,335 |
| `narrative_dispersion` | −$5,772 |
| `options_attention` | −$3,199 |

`vol_gap` is the one measured ACCURATE against no-lookahead truth (0.97x) while
the other two run 1.16–1.17x, and it lost the most. Its sigma was right. What
was wrong was the same three unit errors everywhere, and what it bought with
them was straddles.

## SO WHAT THE MECHANISM ACTUALLY WAS

Three compounding unit errors made the chain look cheap on 96.4% of 6,070
decisions. A brain told "the chain underprices the absolute move" has exactly one
way to express that, and it is a straddle. So a measurement error in **one
scalar** — implied move — routed essentially the whole book into **one structure**,
and that structure is the only one whose payoff depends on the quantity that was
mismeasured.

That is why the loss is 94.5% concentrated. It was never a portfolio of
different bets that happened to go wrong together. It was one bet, priced with
one broken ruler, wearing ten tickers.

And it is the concentration failure `alpha/concentration.py` was built to catch:
effective N by risk read 1.49 on dev. The names were diverse. The **claim** was
not.

## WHAT THIS SAYS ABOUT THE COMPETITION BOOK

- **Fixing the ruler is necessary and is done** (`tests_smoke_chain_width.py`).
  It is not sufficient, because nothing yet stops a corrected ruler from routing
  the whole book into one structure again.
- **The guard that matters is structural diversity of the CLAIM**, not of the
  ticker. `alpha/claims.py` and the `effective N by risk` limit are the two
  places that can enforce it. Today only the second one binds.
- **A long straddle is now refusable only where measured** (NVDA's own print,
  peer straddles into an originator's print). The SPY and QQQ straddles that
  cost $14,711 would still be admissible: no print, no peer relation, no sample.
  **That gap is named here rather than closed by analogy** — closing it needs a
  measurement of index straddles held into no event, which
  `scripts/index_premium_backtest` already has the machinery for (381 weekly ATM
  straddles, seller +17.2%/wk pooled, and a regime warning: 2026 is −0.8%).
- **The one open question worth measuring before Friday**: over the competition
  window, is the index straddle a loser because of theta specifically? The open
  exp1 book decomposes to **delta +$3,106, gamma +$1,054, vega +$1,168, theta
  −$5,048, spread −$163**. Direction, convexity and volatility were all *right*
  and together earned +$5,327 against −$5,048 of rent. A book that is right three
  ways and still loses is paying too much for time, and that is an argument for
  **shorter-dated or spread-financed** expressions, not for abandoning options.

## METHOD, AND THE BUG IN THE FIRST VERSION

There is no "realised P&L" field. This sums cash: buy `−qty × price × 100`, sell
`+qty × price × 100`; a contract back to zero net quantity is closed and its net
cash IS its realised P&L.

**The first run of this script was wrong and printed a confident waterfall
anyway.** Ten of the 29 dev orders are `order_class: mleg` — a multi-leg parent
with `symbol: ""` carrying the real contracts in `legs`. Summing parents
collapsed every spread and straddle into one phantom contract with an empty
ticker and net quantity −71, and reported realised as **−$1,161**. A third of the
book, and the third holding the losses, was simply absent.

What caught it was a reconciliation the script now performs and prints on every
run: **net quantity from the order history must equal the position the venue
holds.** It did not, by 8 contracts. The corrected reconstruction reconciles
exactly and lands on −$14,335 against `pnl_attribution`'s independently derived
−$14,330.

Distrust the instrument before the result — the sixth time on this project, and
the first where the instrument was written the same hour.

Also pinned: summing `pnl_usd_if_closed_now` over `state/fills.jsonl` gives
**−$302,818**. It is 1,070 rows re-marking 29 orders. Dedupe by
`alpaca_order_id` first; that number is an artefact of the file and has been
quoted in a handoff.
