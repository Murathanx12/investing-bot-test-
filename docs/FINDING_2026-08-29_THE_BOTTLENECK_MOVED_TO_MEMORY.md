# FINDING 2026-08-29 — THE ENGINE FOUND THE BOTTLENECK AND COULD NOT BUY IT

**Status:** measured, sourced, SHADOW. No position, no backtest, no claim of alpha.
**Prompted by:** Murat — *"why did AMD increase 200% while Nvidia did not, even
though they are competitors in the same market."*

---

## 0. THE PREMISE WAS RIGHT AND THE QUESTION WAS STILL WRONG

Measured from Alpaca daily bars, split/dividend adjusted, 2025-08-25 → 2026-08-28:

| | total | over SPY | over sector (SMH) |
|---|---:|---:|---:|
| **MU** | **+702.7%** | +681.6pp | **+613.9pp** |
| MRVL | +197.5% | +176.4pp | +108.7pp |
| **AMD** | +185.0% | +163.9pp | +96.2pp |
| SMH | +88.8% | +67.7pp | — |
| **NVDA** | **+21.2%** | +0.1pp | **−67.6pp** |
| SPY | +21.1% | — | — |

**AMD was the third-best of the names we digested.** MU beat it by 3.8×.
And NVDA did not merely lag AMD — it returned *exactly the market* while
underperforming its own sector by 67.6 points.

**The number was verified before it was interpreted.** MU adjusted +702.7% vs
raw +701.4%, largest single day +19.4% — not the 2×/4× shape a split leaves.
This repo has booked a reverse split as a +36.34% "excess" before
(`CLAUDE.md`, split adjustment), so an 8× move gets checked, not quoted.

---

## 1. WHY EACH ONE MOVED

**NVDA — a datable negative shock, not gravity.** China data-center revenue to
effectively zero under export controls; a **$4.5B H20 inventory charge**;
**$2.5B** of revenue unshippable; gross margin **61.0% vs 71.3% ex-charge**;
JPMorgan/Bernstein put the cumulative headwind at **$5.5–16B**. Revenue still
grew enormously. The stock returned market anyway.

**AMD — a datable positive shock from a base that priced none of it.** The
**OpenAI 6GW MI450** agreement; Q1 2026 revenue **$10.25B, +38% y/y** against
$9.89B consensus, **+19% on the print**; Microsoft shipping **CUDA→ROCm**
converters, which attacked the switching cost that was AMD's actual moat
problem; Alibaba's **$675M** order.

**MU — the constraint itself.** Q2 FY2026 revenue **+196% y/y to $23.9B**,
operating income **$16.5B (69% operating margin)**, HBM **sold out through 2026**
on multi-year contracts, DRAM ASP **+mid-60% sequentially**, NAND **+high-70%**.
A commodity DRAM vendor became a pricing-power member of a three-firm oligopoly.

---

## 2. MURAT'S THREE HYPOTHESES, GRADED

**(a) "NVDA got stuck because it is so big."** Conclusion partly right,
mechanism wrong — and the mechanism is the part that generalises. Our own
invariant already rejects size as a bound (*"size does not bound the move"*; our
own chain implied 5.10% in one session on a ~$5T name). NVDA did not stall from
gravity, it took a specific event.

**(b) "The CEOs are cousins."** Lisa Su and Jensen Huang are distantly related,
and it is irrelevant to a 164-point gap: unfalsifiable, and it predicts nothing
forward. **The instinct underneath it is right and has a checkable form** — the
industry is a network, not a set of duelists. The edges that moved money were
*customer↔supplier*: OpenAI↔AMD, Microsoft↔AMD, Alibaba↔AMD. That is a graph an
engine can build; CEO kinship is not.

**(c) "Not competitors — two companies in the same market."** **The sharpest of
the three, and the data supports it.** Zero-sum rivals would show AMD's gain as
NVDA's loss. Instead the whole sector re-rated +88.8% and the biggest winner was
a **supplier to both**. The correct causal object is the AI-capex supply chain,
not the AMD-vs-NVDA duel.

---

## 3. THE MECHANISM, STATED SO IT TRANSFERS

**A stock return is SURPRISE against EXPECTATION, never the level of
fundamentals.** NVDA's fundamentals were extraordinary and paid SPY, because
"AI leader" was already the price. MU's fundamentals surprised, because
"commodity memory" was the price. The distance between those two beliefs was the
whole trade.

This is `AEGIS_STRATEGIC_INVARIANTS` earned rather than asserted: **the mega-cap
is a SENSOR, not the trade.** NVDA told us which world we were in. MU was how
that world got monetised.

The corollary is the screening rule: never ask *"who is best positioned in AI?"*
(answer: NVDA, and it paid the index). Ask **"where is the expectation furthest
below what the CONSTRAINT implies?"** Over this window the binding constraint
moved from compute to memory.

---

## 4. THE PART THAT INDICTS US

**`NEEDS_GRAPH` had already flagged MEMORY as the constrained node**, hours
before NVDA's 26 Aug print disclosed **+$160bn of commitments "primarily related
to the procurement of memory"** (`MEMORY.md`, NVDA print receipt).

So the system identified the bottleneck correctly, in advance, in writing —
**and had no path from "memory is the constraint" to "buy the memory maker."**

That is not a forecasting failure. It is a missing *edge* between a theme and an
instrument, and it is exactly the gap the whole-market discovery layer is meant
to close:

```
AI capex ↑ → GPU demand ↑ → HBM per GPU ↑ → HBM sold out
          → memory pricing power → WHO SELLS HBM?  (three firms)
```

Every link in that chain was public before the move.

---

## 5. WHAT THIS DOES NOT ESTABLISH

- **Nothing here is a backtest.** It is one window, chosen after the outcome was
  known, on names selected because they had already risen. That is the
  textbook shape of a retrospective story, and rule 2 of `CLAUDE.md` applies:
  *explaining a winner afterwards is trivial; finding precursors observable
  beforehand is the research problem.*
- **No matched losers were examined.** Other memory and semi names carried the
  same "AI demand" coverage. Until the losers are studied as hard as the
  winners (rule 4), the causal claim is unsupported.
- The horizon question is unresolved: this is a 12-month effect. Nothing here
  says it was tradeable at 5 or 20 days.

The value of this note is the **mechanism and the missing edge**, not the
returns.

---

## 6. SOURCES

Prices: Alpaca daily bars, `adjustment=all` and `raw`, IEX feed, verified
against split shape. Fundamentals and commentary:

- NVIDIA Q1 FY2026 results — nvidianews.nvidia.com
- NVIDIA 10-Q FY2026 — sec.gov
- "Why Is NVIDIA Stock Falling? China, AI Demand & Valuation" — indmoney.com
- "AMD Stock Analysis 2026: How AMD Quietly Outperformed Nvidia" — heygotrade.com
- "Nvidia vs. AMD: The Better AI Chip Stock for 2026" — fool.com
- "Micron's Sold-Out HBM Supply Makes the Bull Case Hard to Dismiss" — investing.com
- "Micron Stock Up 120% YTD: What the HBM Memory Leader Plans for 2026" — io-fund.com
- "Is Micron the Next Nvidia? Why the 2026 Memory Crunch..." — tradingkey.com
