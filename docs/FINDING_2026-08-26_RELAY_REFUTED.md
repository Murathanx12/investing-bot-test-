# FINDING 2026-08-26 (night) — the relay is priced: peers' chains already know the originator prints

**Receipt:** `state/relay_backtest.json` (`python -m scripts.relay_backtest`).
**Data:** every SEC-dated print of NVDA, AVGO, AMD, MU (Feb 2024 → Aug 2026); for each,
the ATM straddle of each of nine peers (NVDA AMD AVGO MU ARM TSM SMH SOXX QQQ) bought
at the close before and sold at the close after, expired-contract closes. A peer
printing within two sessions of the originator is skipped for that event. 326 rows,
290 relay legs, 36 originator legs.

## The number that matters

| | n | mean (of premium) | median | hit | t |
|---|---|---|---|---|---|
| **relay legs** (peer straddle on originator print day) | 290 | **−4.2%** | −12.8% | **34%** | **−2.0** |
| originator's own straddle, same events | 36 | −1.7% | −14.5% | 36% | −0.2 |

The walk-forward ratio that `scripts/uncertainty_relay.py` prints — the peer's prior RMS
move on the originator's prints over its implied at entry — **does not sort the outcome**:

| ratio tercile (cut-offs from earlier events only) | n | mean | hit |
|---|---|---|---|
| top (history > chain) | 52 | −7.9% | 37% |
| middle | 76 | −6.5% | 30% |
| bottom | 57 | −8.6% | 21% |

All three lose; the top tercile is not better than the bottom. A ratio above one is not
edge — the peers' chains have already widened for the originator's date, and by more than
the peers then move.

## By originator (peer straddle, mean of premium)

| originator | NVDA | AMD | AVGO | MU | ARM | TSM | SMH | QQQ |
|---|---|---|---|---|---|---|---|---|
| **NVDA prints** | −46% (0/8) | −12% | −20% | −8% | **+1%** (3/9) | −16% | −18% | −11% |
| AVGO prints | −2% | 0% | **+32%** (own) | −3% | +2% | +1% | −2% | −3% |
| AMD prints | +13% | +8% (own) | +21% | +18% | −5% | +7% | +1% | +6% |
| MU prints | **−26% (0/9)** | −19% | −13% | −3% (own) | **−20% (1/10)** | −2% | −8% | −3% |

Read the NVDA row against this afternoon's live ranking (ARM 1.64, TSM 1.52, SOXX 1.03):
**on NVDA's last nine prints, ARM straddles cleared 3 of 9 and TSM 2 of 10.** The ranking
selected precisely the legs that lose least often, not ones that win. MU's prints are the
extreme: NVDA and ARM straddles into a MU print lose 19 of 19.

The one positive cell is AMD → peers (AVGO +21%, MU +18%, NVDA +13%, n≈9–10, t ≈ 1.0–1.4):
the chains of AMD's peers under-widen for AMD's date. Small, unverified, and the only
place a relay long has any support.

## What this changes

1. **`alpha/brains/relay.py` stays SHADOW** and its docstring now says why. A relay leg is
   not promoted by a ratio; it would need the AMD-type cell to reproduce forward.
2. **`scripts/uncertainty_relay.py` is a diagnostic, not a candidate list.** Its ratio is
   recorded so the live reading can be graded tomorrow, and the grade is expected to
   agree with this table.
3. The short side of the relay — selling peer premium into an originator's print — is
   the same "the chain over-prices scheduled events" fact as `FINDING_2026-08-25_SURFACE_AND_STRIP.md` §2,
   where iron butterflies were the least-bad structure (+5%, t 0.7). It is not a new
   mechanism and is not being built as one.
4. **Review item 3 ("RELATIVE_EVENT_VOL — probably the most creative practical idea")
   is DEPRIORITIZED as a long-vol expression on this evidence**, not rejected as a
   measurement: the empirical edge weights are real and stay in `RELAY_MAP`; what fails
   is the claim that the peer chain prices them carelessly.
