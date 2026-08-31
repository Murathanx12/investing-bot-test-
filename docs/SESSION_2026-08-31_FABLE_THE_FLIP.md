# SESSION 2026-08-31 (Fable, 03:26–10:0x ET) — THE FLIP

**RESULT IMPROVEMENT: THREE SEALED TRACKER BOOKS WENT LIVE.** hack4 (profit-max
k=5×10%) flipped at the open; hack3 (balanced k=10×8.3%) and hack6 (diversified
k=15×6%) flipped an hour later on Murat's follow-up instruction ("make sure all
the other paper accounts are also wired and not empty … up to the engine").
First time in the programme's history that ANY tracker portfolio is
order-reachable — now all three personalities are, from one seal, as a live
breadth A/B on the ridge T13 found (k=5 beat k=10 in prose arms).

## 1. What became order-reachable that was not before

The exact sealed hack4 portfolio. Chain, every link verified today:

`tracker (3,059 names) → build_portfolio(profit_max) → seal (portfolios[hack4]
inside content_sha256) → --publish → docs/seed/predictions/2026-08-31.json →
git push → fleet --deploy hack4 --up → tracker_portfolio brain →
inject_sealed_portfolio → run_pass → admission`

Dry pass (no --live): `sealed portfolio hack4 (2026-08-31, sha e6f967a62863):
+5 names -> ABAT,ALMU,LAES,NB,RZLV` · forecasts=5 · declined=109 (every
non-sealed symbol, each with the reason) · errors=0.

## 2. Exact seal / account / holdings

- **Account:** hack4 (PA3R9XHMCVDA, $99.2k equity), `AAT_LOOP_BRAINS=tracker_portfolio`,
  `AAT_STRUCTURE_KINDS=long_shares`, shadow=`post_event_drift` (the old mandate,
  recorded not lost), build `424c971+dirty`.
- **Seal:** sha `e6f967a62863131c`, sealed 12:03:50 UTC from the repaired
  2026-08-31 tracker. Published hash re-verified equal to the local artifact.
- **Holdings:** RZLV, NB, LAES, ABAT, ALMU — 10% each, gross 50%.
- **Worst case, BOTH ways:** stop-based **−3.00%** (5 × 10% × 6%, name_count
  binding under the 150% `maximum` cap) and all-five-gap-to-modelled-5%-downside
  **≈ −18.4% (~−$18.2k)** — the five names carry −30% to −42% modelled
  downsides. profit_max has NO `max_downside`, so it selects high-downside
  names BY CONSTRUCTION; this is now a stated property in the mandate caveat,
  not an artifact. (Credit: the parallel Opus session flagged the second number.)
- **Authorization:** `docs/DECISION_2026-08-31_HACK4_TRACKER_APPROVED.md` — all
  nine activation conditions verified before the env change; approval was
  Murat's, given at ~19:00 +08.

## 3. P&L impact expected today vs research-only

Three tracker books attempt share entries from the first pass ≥09:31 ET, each
with its sealed notional as a reduce-only ceiling, stops/gross/opening-range
untouched:

| role | book | sealed gross | stop-case | all-gap case |
|---|---|---|---|---|
| hack4 | profit-max k=5 ×10% (RZLV NB LAES ABAT ALMU) | 50% | −3.00% | ≈−18.3% |
| hack3 | balanced k=10 ×8.3% (ORCL RZLT LOVE LAES RKLB OFIX MCHP CDZI LYTS WD) | 83% | −6.64% | ≈−23.3% |
| hack6 | diversified k=15 ×6% (RARE MAZE NKTR INVA NAMS BUR MLYS PAM HDB CRC OMCL BBAR GRAB CALX TGS) | 90% | −2.70% | ≈−13.0% |

Note the inversion: hack3's gap case is WORSE than hack4's — breadth was bought
with gross (83% vs 50%), a property of the balanced personality, stated in its
mandate caveat. hack3's old thesis brains and hack6's council blend run as
SHADOW comparators (their adjudicated rules intact there). hack1/hack2/hack5
unchanged: hack1 is loop-wired (its 08-28 NVDA drift round-trip was
loop-placed) with the anchor core attended-by-design; hack2's drift is
signal-starved until the window universe refreshes post-Finnhub-outage and this
week's printers (NIO/MDT 09-01, PANW/MDB 09-02) arrive; hack5 holds its two
convexity positions.

## 3a. The first live entry pass (09:31 ET) — verified, and a refusal is a finding

hack4's 09:31 pass, from the container logs: `sealed portfolio hack4
(2026-08-31, sha e6f967a62863): +5 names` → `brains=1 forecasts=5 declined=108
| considered=5 submitted=0 refused=5 errors=0 | ledger: chain intact`. All
five refused by the **opening-range guard** (no share entries 09:30–09:45 ET —
the 28 Aug lesson: every open-print entry stopped out by 09:48 on a 0.1% index
move), each with the reason on the ledger row. hack3's pass ran identically
(+10 names, non-sealed declined by name); its exit engine sold the legacy BE
theme position. First real entries land at the ≥09:45 passes (~10:01 ET).
Condition 9 of the decision doc is satisfied: the running services consume the
exact seal, and what they did with it is recorded, not inferred from
"deployment SUCCESS".

## 4. Tests / suite / fleet

62 suites, **2,726 checks, ALL PASS** (three times today: after seal §1a fields,
after the mandate, after the runner fix). Fleet check hack4: LEGACY (fine —
not the judged account), trading not blocked. Pytest-collect vs runner count
compared for the artery suite: 11 == 11.

## 5. Source coverage added and cost

- **WRDS RavenPack: NOT ENTITLED** — trial/sample = ONE day (2020-09-30,
  409,198 equity events). Receipt: aegis-finance
  `docs/SOURCE_RECEIPT_2026-08-31_WRDS_RAVENPACK.md`. $0 spent; the hour bought
  a closed question, an EventCluster schema reference, and the volume
  calibration (~150m events/yr ⇒ clustering is load-bearing).
- Opus (parallel session): `tr_ibes.ptgdetu` — 4.66M analyst-level price
  targets 2013–2026 already entitled; kills the retail-API purchase case.

## 6. New EventCluster / CompanyState fields

None built this session (deliberate — the artery outranked them). Seal gained:
`driver_exposure`, `derived_gross`, `worst_case` (binding named, refuses
visibly), `source_versions`, `data_gaps` (absent-vs-refused, from tonight).

## 7. Experiments run

None registered. The day's measurement was operational: the Finnhub
recommendation endpoint 503'd in waves for ~4 hours (their outage, confirmed by
direct probe). Repair: strip rows with `rec_status!='ok'` → re-run `--refresh`
(fetches only missing symbols) → repeat; 7 cycles converged 1,200 → 75 damaged.
The 75 stay in the day file with the failure on the row — observed-but-
unreadable is a recorded refusal, not an absence.

## 8. Missed opportunities and why

Not evaluated today (T15 opportunity recall remains queued). The WBUY case is
Opus's: the digest ranked it first and nothing that places ever read the file —
closed by their proof 7.

## 9. What remains disconnected

- hack1 anchor core: attended-by-design (`competition_book` places nothing);
  the command exists, the human runs it after 15:45 ET or delegates explicitly.
- hack5 exact-name options expression block: not built — hack5 stays OLD
  CONVEX CONTROL, labeled as such.
- Fills → outcome write-back (brief §4): the artery's downstream half, still
  the next bottleneck after today's fills land.
- EventCluster/EDGAR/GDELT: queued behind the write-back.

## 10. The next single bottleneck

**Fills → tracker/company-state write-back** (append-only, keyed by
(day, symbol, book), refusals recorded). Today produces the first live fills a
tracker book has ever generated; if they are not written back, the learning
loop stays open and the day teaches nothing.

## Bugs found and fixed today

1. Seal built from a vol-less tracker day: `--refresh` does not derive
   `realised_vol_20d`; without `--backfill-prices` every downside is unreadable
   and hack3/hack6 seal EMPTY while hack4 fills. Seal order is now: refresh →
   backfill-prices → seal. (First empty seal kept beside the reseal, as designed.)
2. `alpha/runner.py`: chain-less names (ABAT, ALMU) crashed the SHARE builder
   on `None.implied_move` — a sealed 5-name book silently shrank to 3. Guarded;
   gap charge falls back to measured overnight gaps (`424c971`).
3. Seal §1a fields + honest authority text (`8fbafe4`): the artifact no longer
   claims "nothing may influence an order" while a selector brain consumes it.

## Standing notes

- Ledger hash chain: **still broken since 25 Aug** (6 declared historical
  epochs; `state/ledger_epochs.json`). Logged, not repaired.
- `universe.load()` now defaults to `scope="execute"` (Opus, 6ad7232) — a
  verified no-op today; stops being one after any `build(scope="observe")`.
- Two sessions drove one repo today; the SendMessage handshake before touching
  Railway is the pattern to keep.
