# FINDING — The wide-PEAD result under attack: it is a PAIR, it starts at 5%, and 2026 is negative

`python -m scripts.pead_adversarial` · receipts `state/pead_adversarial.json` (v2 legs, 25,855 legs with opens,
horizons 1..21, IWM/XBI/SPY) and `state/pead_adversarial_v1.json` · legs re-pulled by `scripts/pead_wide.py`
(now writes `overnight_gap_signed`, `from_open1_signed`, `day0_gap`, `day0_intraday`, `signed_1..21`, `price0`,
`raw_{iwm,xbi,spy,qqq}_3`, `raw_3`).

The claim under attack (`docs/FINDING_2026-08-26_PEAD_WIDE.md`): outside the mega-11, a 3.5-8.2% day-0 DROP drifts
a further +0.44%/3d (t 4.29) and an UP print reverses (−0.22%, t −1.99). The review asked forty questions. The
ones that changed the answer are below; the rest are in the receipt.

## 1. The benchmark WAS the result (checks 21-24)

Mid-band DOWN, 3 sessions, drift in the day-0 direction (= the return to a SHORT):

| benchmark | mean | t |
|---|---|---|
| **none (raw)** | **+0.03%** | **+0.25** |
| minus IWM | +0.29% | +2.83 |
| minus SPY | +0.43% | +4.15 |
| minus beta·QQQ (the finding) | +0.44% | +4.29 |
| minus QQQ (beta 1) | +0.58% | +5.49 |

The average QQQ move over the legs' 3-session windows is **+0.60%** (a 2024-26 bull tape, prints clustered in
its up-weeks). A loser that simply stops moving "drifts" +0.44% against that. So the mechanism is not "bad news
keeps falling"; it is **"the loser does not join the index's rise for three sessions."** That is a real,
tradeable statement — for a PAIR (short loser / long index). For an unhedged short it is worth the raw line.

The UP side inverts the same way: raw, a ≥5% winner keeps RISING (+0.25%, t +2.49); it only trails QQQ
(−0.37%, t −3.85) and is flat against IWM (−0.14%, t −1.46). **"Good news fades" was false in raw terms.** The
refusal stands — there is no excess to sell and no raw edge worth buying — but the reason on the row is now
"no edge", not "reversal".

## 2. Where the edge starts (checks 1-2, 40)

DOWN side, 1% bins of |day-0|, 3-session excess vs β·QQQ:

| |day-0| | 0-1 | 1-2 | 2-3 | 3-4 | 4-5 | **5-6** | **6-7** | **7-8** | 8-9 | 9-10 | 10-13 | 13-19 | >19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mean | +0.09 | +0.29 | −0.03 | +0.07 | +0.27 | **+0.72** | **+0.61** | **+0.60** | +0.28 | +0.07 | +0.3 | +0.8 | **+1.08** |
| t | 0.8 | 2.4 | −0.3 | 0.5 | 1.4 | **3.0** | **2.3** | **2.4** | 0.8 | 0.2 | ~1 | ~1.8 | **3.8** |

The 3.5-5% zone is dead (raw short −0.05%, t −0.3). Spearman(|day-0|, drift) = +0.048 — a weak monotone rise
with a step at 5%. The preregistered 3.5% edge was the mega-11's tercile boundary, not this population's.

## 3. Honest standard errors (checks 3-4, 8)

Mid-band DOWN excess: iid t 4.29 → by issuer 4.22 → by week 2.16 → **by quarter 1.75** → **two-way issuer×week
2.15**. Big band: 5.16 → 3.08 two-way, 3.19 by quarter. UP mid band: −1.99 → −1.18.

Leave-one-quarter-out: **6 of 11 quarters have a NEGATIVE mean** (2024Q1, Q2, Q4, 2025Q2, Q3, 2026Q1, Q3); the
total is carried by 2024Q3 (+1.39%), 2025Q1 (+1.30%), 2025Q4 (+0.79%) and 2026Q2 (+1.90%). That is the
signature of a regime effect riding on the benchmark, not of a per-print mechanism. By year, the RAW ≥5% short:
2024 +0.58% (t 3.2), 2025 +0.09% (t 0.6), **2026 −0.14% (t −0.8)**.

Issuer concentration is not the problem: top-50 issuers hold 7.2% of the mid-band DOWN sample, max 8 prints per
name, leave-one-issuer-out t ranges 4.14-4.74.

## 4. Timing (checks 29-35) — the implementation captures MORE than the close-to-close number

| segment, mid-band DOWN | mean | t |
|---|---|---|
| close₀ → open₁ (what a next-open entry MISSES) | **−0.11%** | −3.5 |
| open₁ → close₃ (what it EARNS), excess vs β·QQQ | **+0.56%** | +5.35 |
| same, small bucket | +0.84% | +4.67 |

The overnight after day 0 goes the WRONG way for the short (a small bounce), so entering at the next open — which
is what `alpha/runner.py` + `equity.py` do — is the right timestamp, not a compromise. Day 0 itself splits evenly
between the gap (−2.73%) and the session (−2.80%).

## 5. Horizon (checks 38-40)

Cumulative excess in the day-0 direction, sessions 1 → 21:

| cell | 1 | 3 | 5 | 10 | 15 | 21 |
|---|---|---|---|---|---|---|
| mid DOWN | +0.17 (2.5) | +0.44 (4.3) | **+0.54 (4.4)** | +0.38 (2.4) | +0.28 (1.5) | +0.29 (1.3) |
| big DOWN | +0.27 (3.2) | +0.64 (5.2) | +0.60 (4.0) | +0.47 (2.2) | +0.56 (2.2) | +0.55 (1.9) |
| small-bucket mid DOWN | +0.20 (1.8) | +0.73 (4.1) | +0.80 (3.7) | +0.80 (2.8) | +0.95 (2.8) | **+1.15 (2.8)** |
| mid UP | −0.14 | −0.22 | −0.34 | **−0.68 (−4.1)** | −0.38 | −0.74 (−3.2) |
| big UP | −0.11 | −0.44 | −0.69 (−4.3) | −0.69 | −0.49 | −0.69 (−2.5) |

The DOWN drift peaks at 5 sessions and decays; holding to 21 keeps nothing the 5-session exit did not have,
except in the small bucket. The UP trail-behind-the-index is a LONGER phenomenon (10-21 sessions). Both are
excess numbers and inherit §1's caveat.

## 6. Costs and the stop (check 25; the vol desk's attack)

Round trip on the mid-band excess: 10 bp t 3.3, **30 bp t 1.4, 50 bp gone**; small bucket survives 30 bp
(t 2.4). Borrow is per name and not in these numbers.

The vol agent's attack was that the lane's 3% stop (`equity.STOP_FRACTION`) was never in the measurement and,
with post-print session-1 σ of 4.9%, would fire on most legs. Measured on the ≥5% DOWN legs (close basis, a
LOWER bound on hits): stop 3% hit on **38%** of legs, 5% on 24%, 8% on 12% — and the net raw short return is
**+0.171% / +0.180% / +0.188%** against +0.167% with no stop. The stop clips both tails about equally; the traded
object is worth what the measurement said. No change to `equity.py`.

## 6b. Log versus simple — the attack that closed the unhedged lane (agent 1)

The legs are LOG returns; a short is paid in SIMPLE returns, −(e^r − 1). A −113% log leg costs a real short
−211%. Recomputed on the ≥5% DOWN legs, raw, short from the next open, 3 sessions:

| band | raw short, log | **raw short, simple** | pair (long IWM), simple |
|---|---|---|---|
| 5-8.2% | +0.27% (t 1.87) | **+0.04% (t 0.22)** | +0.35% (t 2.22) |
| >8.2% | +0.32% (t 2.51) | **+0.00% (t 0.03)** | +0.26% (t 1.96) |

The unhedged short of a wide-universe loser is worth nothing. The pair keeps a third of a percent at t ~2 iid,
which after §3's clustering is a hypothesis, not a lane. Agent 1's other numbers (30 bp cost leaves +0.06%;
non-ETB legs carry the drift, ETB legs +0.36%) point the same way.

## 7. What changed in code (P0: a confirmed forecast-semantics defect, not a new idea)

**Final state:** `WIDE_UNHEDGED_SHORT_ENABLED = False` — outside the mega-11 the brain REFUSES the DOWN side
too, with the simple-return numbers in the refusal text and the pair numbers (`WIDE_HEDGED_IWM_SIMPLE`) on
record. The whole-market lane is therefore CLOSED as an unhedged short and OPEN as a pair to build. The
paragraphs below describe the intermediate state the switch guards (pinned by test so that flipping it can
only ever quote the raw number).

`alpha/brains/post_event_drift.py`: the wide rule quoted an EXCESS-over-QQQ centre into a structure that is an
UNHEDGED short, and the MDM gate sizes an absolute move. The brain now quotes the **RAW short-from-next-open**
numbers (`WIDE_DOWN`: 5-8.2% +0.27%/3d sd 6.7%; >8.2% +0.32% sd 7.8%), refuses drops under **5%**
(`WIDE_MIN_ABS_MOVE`), cuts wide conviction to 0.6, and carries `hedged_vs_iwm` (+0.56%, t 3.95 / +0.55%, t 4.49)
and `raw_2026_3d` (−0.14%) on every row so the pair expression can be built without re-measuring. The UP refusal
says "no edge", not "reverses". Smoke: 9 wide checks, suite green.

## 8. Verdict

- As an unhedged short, DOWN ≥5% is a **+0.2-0.3%/3d tilt (t 1.9-2.5) that was negative in 2026**. The gate
  will mostly refuse it at conviction 0.6, and that is the correct output.
- As a **pair (short loser / long IWM)** it is +0.55%/3d, t 4-4.5 iid, ~2.2-3.1 two-way clustered, best in the
  small bucket and best from the next open, 5-session exit. That is the expression worth building
  (`docs/ROADMAP_2026-08-26_CAUSAL_WORLD_MODEL.md` §5b) — and it must be re-graded quarterly, because six of
  eleven quarters said no.
- "Bad news drifts, good news fades" is retired as a sentence. The measured sentence is: **after a large print
  the stock detaches from the index for a week — losers stay down while it rises, winners rise less than it
  does.** That is an information-processing statement, and it is the one Psychohistory should model.
