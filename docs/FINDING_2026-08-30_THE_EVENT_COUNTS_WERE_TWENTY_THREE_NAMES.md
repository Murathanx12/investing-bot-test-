# FINDING 2026-08-30 — "EVENT COUNTS CARRY INFORMATION" WAS TWENTY-THREE NAMES

**Status:** supersedes the second half of
`FINDING_2026-08-29_BLINDED_NEWS_HAS_NO_DIRECTION_EVENT_COUNTS_DO.md`.
The first half (blinded narrative carries no direction) **stands** and is
untouched. The second half — that the dated event COUNTS do carry it — **does
not survive a universe nobody curated.**

Receipts: `state/corpus/features/ic_2026-08-29.json` (23 symbols),
`ic_2026-08-30_wide152.json` (152 symbols),
`ic_narrow23_from_wide_build.json` (the reproduction check).

---

## 1. THE NUMBER

Rank IC against the **21-session SPY-relative** return, entry at the next open,
block bootstrap, 95% CI, **11 date blocks in both runs**:

| feature | 23 symbols | 152 symbols | 95% CI (wide) |
|---|---:|---:|---|
| `ev_insider_20d` | **+0.148** | **+0.023** | [−0.004, +0.046] |
| `ev_earnings_20d` | **+0.155** | +0.008 | [−0.030, +0.043] |
| `ev_macro_20d` | +0.118 | +0.040 | [−0.011, +0.085] |
| `ev_contract_20d` | +0.103 | +0.005 | [−0.031, +0.041] |
| `ev_analyst_rating_20d` | +0.098 | +0.020 | [−0.032, +0.072] |
| `n_target_notes_90d` | +0.070 | +0.023 | [−0.039, +0.093] |
| `n_target_firms_90d` | +0.063 | +0.023 | [−0.042, +0.097] |

**Zero of 29 features have a 95% CI excluding zero on the wide panel.**
On the narrow panel, seven did.

## 2. IT IS THE UNIVERSE, NOT THE HARNESS

The obvious objection is that something else changed — the panel was rebuilt,
the bars were refetched, the code moved. So the **same 23 symbols** were
re-run through the **wide build's own files**:

| feature | original 23 | reproduced from the wide build |
|---|---:|---:|
| `ev_insider_20d` | +0.148 | **+0.139** |
| `ev_earnings_20d` | +0.155 | **+0.145** |
| `ev_analyst_rating_20d` | +0.098 | **+0.086** |
| `ev_contract_20d` | +0.103 | **+0.092** |
| `ev_macro_20d` | +0.118 | **+0.115** |

It reproduces. The harness is the same, the period is the same, the method is
the same. **The 5–6× shrinkage is the universe.**

## 3. WHY THE 23 WERE NOT A CROSS-SECTION

They were Murat's twenty names plus SPY/QQQ/IWM — a list assembled because
those names were **interesting**, in a window during which several of them ran
hard (MU +702.7%, MRVL +197.5%, AMD +185.0% over 2025-08 → 2026-08). Any
feature correlated with "this name had a lot going on" scores well in that
sample, and every event count is correlated with that.

This is `feedback-a-hand-picked-universe-is-survivorship-bias` at full strength,
and its rule decides the matter: **when a curated list and a broad screen
disagree, the screen is right.**

## 4. WHAT IT IS *NOT*

- **Not** evidence that events are irrelevant. It is evidence that a *count of
  event headlines in a 20-day window, ranked cross-sectionally*, does not
  predict the next 21 sessions on a broad universe. A different encoding — the
  event's own surprise, its direction, its size — is untested.
- **Not** a coverage artefact. Coverage was the first suspect, because
  Benzinga files 1,566 items on NVDA and 3–4 on AARD. It is ruled out:
  `coverage_baseline_90d` alone has a per-day cross-sectional IC of **+0.0004**,
  and normalising each count by the name's own 90-day baseline moves the ICs by
  less than 0.005 (insider +0.049 → +0.046 raw → normalised). The counts are
  not a coverage proxy; they are just weak.
- **Not** a reason to stop collecting. The corpus is the input to every other
  test, and the sensors are what make a wide panel possible at all.

## 5. WHAT CHANGED BECAUSE OF IT

- **The sealed pre-open book claims nothing.** `scripts/prediction_book.py`
  derives `CLAIMING` from the CIs rather than asserting it, so the book still
  ranks and still seals — it is T7's control and it accrues vintages — and it
  asserts no direction until a signal clears zero on a universe nobody chose.
  Tonight's seal: **151 considered, 0 claims.**
- **The panel is now built over the corpus universe** (`corpus_features
  --universe corpus`, 152 symbols / 37,601 symbol-days, up from 23 / 5,678).
  T3 could not even be *asked* on 23 names: the only declared drivers with
  three members were `murat_book`, `UNCLASSIFIED` and `index_beta`.

## 6. THE ADJACENT RESULTS FROM THE SAME PANEL

**T6 — Murat's rule cells** (`scripts/rule_cells.py`). Condition (b),
rating ≥ 4.1, is **UNAVAILABLE**: non-null on 135 of 37,601 symbol-days,
because `analyst_panel` records forward from 2026-08-26. So the tested rule is
(a) target/price ≥ 1.5 × (e) drawdown ≤ −20%, SPY-relative, 11 blocks:

| cell | 21d mean | 21d median | terminal wealth | MDE |
|---|---:|---:|---:|---:|
| a AND e | +4.47% | +0.51% | **1.49×** | 23.29% |
| a only | +2.70% | +1.01% | 1.10× | 21.73% |
| e only | −0.73% | −3.14% | **0.92×** | 17.76% |
| neither | +0.65% | −1.09% | 1.08× | 15.26% |

Every cell is **below its own MDE** — not detectable at this power. The
suggestive ordering is that the conjunction beats both singles on terminal
wealth, and that **"already down" on its own LOSES money (0.92×)**, which
agrees with the CRSP knife-basket adjudication already on file (−0.31%/5d,
t −2.35). At 63 days there are 3 blocks and nothing can be read at all.

**T3 — sector lead vs laggard.** 269 events across six real drivers, shock =
`attention_z ≥ 1.0` on ≥3 names in one driver on one day:

| arm | mean | median | terminal wealth | MDE |
|---|---:|---:|---:|---:|
| laggard | +6.74% | **−4.09%** | 1.43× | 34.06% |
| leader | +3.92% | −3.62% | 1.28× | 30.41% |
| the middle | +6.56% | **+0.71%** | **1.50×** | 25.87% |

All below MDE. The laggard beats the leader on both mean and wealth, **and
loses to the middle of the driver on all three measures** — and on the median
it is the worst of the three. There is no support here for "buy the driver's
laggard"; if anything the readable pattern is that both extremes underperform
the middle, which is what you would expect if the extremes are where the
idiosyncratic news is.

## 7. WHAT WOULD CHANGE THE VERDICT

1. **A different encoding of the event**, not its count: surprise vs
   expectation, signed direction, magnitude. Section 4 says why this is open.
2. **More blocks.** Eleven is the binding constraint on every cell above, and
   it is a calendar fact — twelve months of history is eleven independent
   21-session windows. Only time fixes it.
3. **Condition (b)**, once `analyst_panel` has vintages. At ~60 names a day the
   panel reaches a testable history in weeks, and T6 becomes the three-condition
   test it was written to be.
