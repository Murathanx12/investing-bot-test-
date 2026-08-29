# SESSION 2026-08-29 (evening, Opus) — THE MONDAY-SAFETY REMAINDER, AND A LEARNING LOOP THAT WAS LYING

**Repos touched:** `aegis-alpha-terminal` (all code), `aegis-finance` (roadmap status).
**State:** committed, pushed, deployed to all six Railway loops, verified.
**Suite:** 43 → **48 suites, 1,946 checks, all green.**

---

## 0. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** No trade was placed and no strategy was promoted.
Monday's *downside* is smaller and one input to every future decision stopped
being wrong. Both are worth something; neither is a return.

| | before | after |
|---|---|---|
| basket worst case, one driver | −8% (10 names × 10% × 8%) | **−3.2%** (40% driver cap × 8%) |
| Murat's rule, condition (a) resolvable | **0 / 20** | **14 / 20** — and it discriminates (6 pass, 8 fail) |
| counterfactual `best_available` | `pair BBW **+$62,687,334**` | `long_put NVDA **+$5,892.86**` |
| counterfactual `refusal_verdict` | *"the gate is discarding edge — **loosen it**"* | *"not enough of both to compare yet"* |
| a stop resting on the wrong side / size | kept as "covered" | cancelled and re-placed |
| deploys verifiable from outside | never | `AAT_BUILD_COMMIT` reads back |

---

## 1. THE RED SUITE WAS A WALL CLOCK

Three suites (`tests_smoke`, `_equity`, `_pair`) were failing when this session
opened, and the previous handoff's "43 suites / 1,673 checks, all green" was
true when it was written. Nothing had changed but the time.

`in_opening_range()` read the wall clock with no injection seam and is called
from inside `_execute`. It was **09:34 ET**. The guard fired — on a Saturday —
and refused every share entry in the fixtures. At 09:45 the suites would have
gone green again on their own.

Fourth instance of the calendar-moment class CLAUDE.md names, and the first in a
**production guard** rather than a fixture, so no fixture edit could have fixed
it. The guard now takes a clock the way `exits.deadline_liquidation_due(now=...)`
already did, weekends are not a session, and the fixtures derive their session
time from `today`.

---

## 2. P0.4 — CONCENTRATION BY DRIVER (`alpha/drivers.py`)

The gross cap (P0.0) bounds **how much**. Nothing bounded **how many different
things can go wrong**, and a 100% gross book that is 100% one driver still loses
the whole stop width at once — which is what 28 Aug was: twelve names bought in
thirteen seconds, eleven stopped between 09:36 and 09:48.

**Declared is the floor; measurement may only MERGE.** Murat's seven themes (70
symbols) name the driver. Realised correlation may collapse two declared drivers
into one; it may **never split one**, because a quiet sixty days would then
manufacture breadth that does not exist. Measurement can only make the book look
*more* concentrated — the direction that cannot flatter it.

An undeclared symbol shares **one** bucket. Not knowing whether four names are
independent is not evidence that they are.

Cap = 40% of the profile's **own** gross authority, so it moves with the profile
instead of being a second constant to keep in sync.

**It earned its keep on the first live pass:**

```
drivers this pass: 3 name(s) -> 1 driver(s)
  (declared + merged at rho>=0.60: nuclear+solar_grid_alt_energy rho +0.69)
```

The declared taxonomy said SMR is nuclear and BE/PLUG are solar-grid — two
buckets. The market says **one**. That is Friday's failure caught by measurement
rather than by opinion.

One batched bars call per pass, never in the per-order path.

---

## 3. P0.5 — ORDER / STOP RECONCILIATION (`alpha/protect.py`)

`ensure()` asked `covered >= want_qty` over the **sum** of resting stops. That
inequality is true in three states the module exists to prevent, and it called
all three "kept". All three were live; all three now fail first in
`tests_smoke_stop_reconcile.py`:

| | what rested | what it does when it fires |
|---|---|---|
| **SIDE FLIP** | a sell-stop under a position that is now SHORT | sells shares nobody holds — the short doubles |
| **SHRINK** | a ×120 stop over a position reduced to 40 | sells 120 where 40 exist — an 80-share phantom short |
| **STACKED** | two ×60 stops on 120 shares | either is right; both firing sells 240 |

The test is now exact and singular: **one** resting stop, right side, right
quantity. Anything else is cancelled and re-placed.

A stale stop **price** is reported and left standing, not cancelled: correcting
it opens a window with no protection at all and the re-place can be refused by
the venue. That is a deliberate asymmetry and it is written down at the site.

---

## 4. P0.2 REMAINDER — CROSS-BOOK OVERLAP (`alpha/crossbook.py`)

`python -m scripts.fleet --overlap`, against the six live accounts:

```
FLEET CROSS-BOOK OVERLAP -- 6 book(s) read
3 distinct name(s) held; 1 held by more than one book
  BE  2 book(s): hack3=shares, hack5=option  <-- ONE BET, TWO INSTRUMENTS
```

**Friday's failure is still open on the books.** hack3 holds BE in shares and
hack5 holds BE calls.

**What it honestly delivers, which is not everything.** An Alpaca account is
reachable only with its own key pair, and `scripts/fleet.py` deploys one role's
keys per Railway service **on purpose** — a bug in the convexity loop must not
reach the anchor book's account. That is the right blast-radius choice and this
does not ask to change it. So:

- **locally / attended:** the check is real and refuses.
- **on Railway:** peers are UNREADABLE and the decision row carries
  `cross_book: CANNOT DETERMINE`, naming every peer it could not see.

`CANNOT DETERMINE` does **not** refuse. Refusing every convex entry forever on a
check the deployment structurally cannot perform would retire the account rather
than protect it — the `monday_gate_check` lesson. The state is loud instead, and
`--overlap` is where the number lives.

Read-only **by construction**: `PeerBook` exposes `positions()` and `role`, is
`__slots__`-ed so an ordering method cannot be attached later, and the tests
assert it cannot submit, cancel or close. `config.peer_credentials` is a
separate door from `credentials()`, whose role-disagreement refusal is exactly
right for the order path and must not be widened.

---

## 5. MURAT'S RULE: (a) AND (b) ARE MEASURED NOW

The handoff recorded both as structurally unknown *"because no target-price
source is wired"*, so 14 of 20 names scored 3/5 or 4/5 and the rule was really
out of three. That was true of the **vendor endpoint** and of neither condition.

**(b) was never blocked.** A 1–5 consensus rating is a weighted mean of analyst
recommendation *counts*, and `stock/recommendation` is free, already fetched at
05:30, and already written to `state/research/analyst_panel/<date>.jsonl` with a
`captured_utc` stamp. MU: 18/33/4/1/0 over 56 analysts = **4.21**, passes.

**(a) was blocked at the vendor and open in the corpus.** The 12-month backfill
carries **2,368 rows** quoting a price target in Benzinga's regular form, and
**1,574 of 1,575** title matches carry exactly one symbol, so the join is
unambiguous. It reaches the thin names a consensus misses: SRRK 70 rows, OLMA
55, ABSI 55, BHVN 79, NTLA 117. Better than a consensus figure: firm, figure,
rating word, and the timestamp it became **knowable**, so the panel replays
point-in-time instead of being one number whose vintage nobody recorded.

### Live, against real prices (2026-08-29)

| | ratio | (a) | | | ratio | (a) |
|---|---:|---|---|---|---:|---|
| OLMA | 4.48 | pass | | AMD | 1.34 | fail |
| SOC | 2.89 | pass | | DKNG | 1.33 | fail |
| QUBT | 2.70 | pass | | BHVN | 1.23 | fail |
| ABSI | 1.61 | pass | | SRRK | 1.06 | fail |
| MU | 1.61 | pass | | PRCH | 1.03 | fail |
| NTLA | 1.59 | pass | | HUBS | 0.84 | fail |
| MRVL | 1.39 | fail | | TSM | 1.38 | fail |

**This changes Monday's shortlist.** Of the three names the previous handoff put
forward — MU, BHVN, SRRK — only **MU passes** its own rule's upside condition.
BHVN (1.23) and SRRK (1.06) **fail**.

### A broken gate, found and removed

The first cut scored the headline-word fallback against Murat's 4.1 bar and
returned `fail` for twelve names. Calibrated on the five names carrying **both**
sources:

| | Finnhub | headline | firms |
|---|---:|---:|---:|
| NVDA | 4.26 | 4.06 | 16 |
| TSM | 4.26 | 3.88 | 8 |
| MU | 4.21 | 3.95 | 19 |
| MRVL | 4.12 | 3.78 | 18 |
| AMD | 4.10 | 3.96 | 23 |

**5 of 5 clear 4.10 on the counts; 0 of 5 clear it on the words.** Systematic
offset −0.27; r = +0.47 on n=5, which is not a calibration of anything. The
cause is discretisation — Benzinga prints the firm's own word (Buy / Overweight
/ Outperform, all 4.0) and says "Strong Buy" in 7 of 1,558 headlines. A bar
calibrated for one scale applied to another **cannot go green**, which is a
broken gate and not a strict one.

The words now vote only at or below 3.0 (hold or worse fails on any scale).
Between, the number is reported and the verdict is `unknown`. **Revisit at n≥30
overlap** — the panel captures ~60 names a day, so this becomes a real
calibration in weeks.

Wired: `reconcile_numeric` overwrites (a) and (b) on the digest with the
measured values and keeps the model's own answer as a **correction**, the same
discipline `reconcile` uses for catalysts. The disagreement rate is the
calibration signal.

---

## 6. THE LEARNING LOOP WAS TELLING US TO LOOSEN THE RISK GATES

Found by reading hack1's production log after the deploy:

```
refused  pair_short_vs_iwm BBW  +62,687,334  (+1253746.7% of risk)
refusal_edge_on_risk    -744.9337
refusal_verdict         the gate is discarding edge -- loosen it or explain it
```

$62 million on a $99,250 book, and the conclusion drawn from it is an
instruction to **widen risk**. "The ledger IS the dataset", so this is not a
cosmetic bug — it is the training signal. Three independent defects:

1. **UNITS.** `exit_value_per_unit` ended `return total * MULT`, applying the
   options contract multiplier to every leg including shares. The BBW pair is
   two share legs: `IWM_bid − BBW_ask = 296.30`, ×100 = 29,630 per unit against
   an entry recorded at multiplier 1 — two sides of one subtraction on scales a
   hundred apart. **Same defect as 02a3047**, one layer down: P0.1 fixed which
   *endpoint* a share leg is quoted from and never touched the *multiplier*
   applied to the answer. The fix written for this exact failure did not reach
   it. The multiplier now matches the endpoint, per leg, by construction.

2. **NO CEILING.** `mark()` refused a mark below −1.05× max loss — added after a
   refused bear-call spread showed −292% of risk — and had no upper guard, so
   +1,226,583% sailed into the verdict. **A guard built on one side of a
   symmetric error catches half of it.** Gains above 20× the structure's own max
   loss are UNMARKABLE now, with the raw figure kept and counted.

3. **A PAIR IS NOT ITS RECORDED LEGS.** `book.py:249` already knew the (1,1)
   ratios do not describe the hedge. On a refused row there is no `hedge_shares`
   either, `entry_cost_per_unit` is the **short leg alone** by design, and the
   quote is not persisted at all — so the exit priced two legs against an entry
   for one and returned the short's whole notional as profit. The runner now
   records `hedge_ratio` and `hedge_entry_ask` on every pair row whether or not
   an order was built; a row carrying neither is UNMARKABLE and says so.

Verified live after the fix, on the real ledger: `best_available` is
`long_put NVDA +$5,892.86`, `implausible 0`, `pair_incoherent 37`, and the
verdict is *"not enough of both to compare yet"* — an honest abstention.

---

## 7. DEPLOYS ARE VERIFIABLE FROM OUTSIDE NOW

`agent_loop._commit()` shells out to `git rev-parse` and is documented as the
answer to "which code is running", because *"a heartbeat that cannot say that
explains an outage as a mystery rather than as a deploy."*

`railway up` **tars the working directory**. It does not pull from git, `.git`
is gitignored, so that call has always raised and always returned `None`. Every
deploy since kickoff has been unverifiable from outside — this session restarted
six loops and then had no way to confirm what was in them (no SSH keys either).

The deploy is the only process that knows, so it states it: `fleet.deploy` sets
`AAT_BUILD_COMMIT` alongside every other variable and `_commit()` prefers it. A
dirty tree is stamped `<sha>+dirty` — shipping uncommitted code is allowed and
calling it the commit is not. Read back after deploy: `6edff20+dirty`, matching
local HEAD.

---

## 8. OPEN, IN PRIORITY ORDER

1. **BE is held twice right now** (hack3 shares, hack5 calls). The refusal
   prevents *new* overlap; it does not unwind existing. Murat's call.
2. **Cross-book on Railway is CANNOT DETERMINE by design.** If it should be a
   real refusal there, the fleet needs a published-holdings channel that is not
   another account's keys. Do not solve it by sharing key pairs.
3. **The 37 `pair_incoherent` worlds are historical** — those rows never carried
   the fields. Rows written from 42d5b4c forward do.
4. **Recalibrate the headline rating scale at n ≥ 30** dual-source names.
5. **(a) is still unknown for 6 of 20** — SLDP, KYTX, AARD, SLNO, BEAM, AMSC —
   because no broker note in 90 days names a figure. That is coverage, not code.
6. **`--overlap` is a measurement, not a gate.** It refuses nothing.

## 9. WHAT NOT TO DO

- Do not read `implausible` or `pair_incoherent` as plumbing. They are counts of
  faults in **our** arithmetic, and a rising count is a regression.
- Do not let a correlation *split* a declared driver. Merging is safe in one
  direction only.
- Do not score the headline rating words against the 4.1 bar. Measured: 0 of 5.
- Do not widen `IMPLAUSIBLE_GAIN_ON_RISK` to make a world markable. If a real
  20× appears, the raw number is on the mark — read it, do not raise the bar.
