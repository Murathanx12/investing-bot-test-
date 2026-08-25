# Social post 1 — draft for Murat (X + LinkedIn), day one

Tag: @lablabai @AlpacaHQ · post from the personal account · attach the NVDA
event card screenshot (`state/cards/NVDA_2026-08-25.json` rendered) or the
two-column condor-vs-straddle table.

---

**X (≤280 chars):**

Building an options agent for the @AlpacaHQ × @lablabai hackathon. Day 1 result
I didn't expect: two of my brains looked at the same NVDA chain before tomorrow's
print and chose OPPOSITE trades — realised-vol says iron condor, event-history
says straddle. Both written down before the print. Loser gets graded publicly.

---

**LinkedIn (longer):**

Day 1 of the Alpaca AI Trading Agents Hackathon, and the first thing my agent
produced was a disagreement with itself.

The engine runs several independent "brains", each reading a different data
source: one compares realised volatility to what the option chain implies; one
compares the chain to the company's OWN history of earnings-day moves (NVDA has
moved a median 7.5% on its last twelve prints; the chain prices 5.4% to Friday);
one reads news through an LLM and asks not "is this bullish?" but "is it TRUE,
is it BELIEVED, and has price already moved?"; one measures unsigned option
volume as attention.

Before NVIDIA's print tomorrow, brain one chose to SELL the move (iron condor).
Brain two chose to BUY it (straddle). Same chain, same minute. Nothing is
averaged — each brain's choice is written to a hash-chained ledger with the
quotes it saw, and after the print every road not taken is priced at equal risk.
Whichever brain loses, that gets published too.

Three things I learned today measuring free data sources instead of assuming
them: Polymarket and Kalshi answer without a login (the crowd prices NVDA's Q2
gross margin at 74–76% with 93%); Reddit and StockTwits do not; and the free
option feed's closing quotes disagreed with the underlying by 1.3% on put-call
parity. The agent records that gap on every decision now.

Setbacks so far: zero P&L evidence — one fill, one day old. More tomorrow.

#AlpacaHackathon #options #tradingagents
