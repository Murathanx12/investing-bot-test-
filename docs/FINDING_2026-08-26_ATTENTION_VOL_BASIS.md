# FINDING 2026-08-26 (night) — attention widens the next day, and the chain has mostly already paid for it

**Receipt:** `state/attention_vol_basis.json` (`python -m scripts.attention_vol_basis`).
**Data:** 12 names, Aug 2024 → Aug 2026, Wikipedia daily pageviews; a SPIKE is z > 2 against the
trailing 30 days. On each spike day t (and every fifth non-spike day as control) the ATM
straddle-implied vol at the close of t and t−1 from expired weekly bars with ≥ 3 sessions left;
the next day's |return| standardised by that IV. 383 spikes, 1,023 controls.

`attention_backtest` (25 Aug) had shown the raw effect: next-day |r| 262 bp after a spike vs
195 bp otherwise, +27%. The review's objection was exact — that is only an edge if the chain
did not widen too. The promotion rule was written into the script before it ran: **attention
brains execute only if the basis (spike − control, in units of IV) clears t > 2.**

| | spikes | controls |
|---|---|---|
| n | 383 | 1,023 |
| next-day \|r\| (bp) | 253.5 | 200.4 |
| ATM IV at the close of day t | **49.9%** | 45.5% |
| ΔIV into day t | −0.06 pp | +1.45 pp |
| \|r\| / daily IV, mean | **0.782** | 0.713 |
| \|r\| / daily IV, median | 0.565 | 0.547 |
| share of days with \|r\| > 1 IV | 28.2% | 24.7% |

**basis = +0.069 IV-units, t = 1.62.** Below the pre-declared bar.

Two readings. First, the chain is already ~10% wider on attention days (49.9 vs 45.5), which
absorbs most of the +27% raw widening; what is left is a ~10% relative excess with a t of 1.6
on 383 events — the same sign as the literature, at a size the free feed's spreads (median 5%)
would eat. Second, ΔIV into the spike day is *negative* on spike days and positive on
controls: the option market widened BEFORE the pageview count did — pageviews lag a day, the
chain does not. Attention measured from Wikipedia is a confirmation, not a precursor.

## What this changes

- `options_attention` and `narrative_dispersion` **stay shadow on dev**; they execute on exp1
  only, where the challenger book exists to produce fill-and-mark evidence. The rule that
  promotes them is now a number in a receipt, not a judgment.
- The widening the brains assume (σ up, no sign) is real; the trade it implies is not, at this
  data latency. A same-day attention source (HN/Mastodon velocity intraday) is the only version
  worth re-testing, and only if it can be shown to lead the chain rather than follow it.
- Review item 5 is closed as **measured and not promoted**.
