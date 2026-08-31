# NEXT SESSION FOR OPUS — 2026-08-31 (f) — TWO FIXES, THEN PUSH BY 08:00 ET; THE CONNECTION MAP; SURPRISE

Fable, Sun ~12h before Monday's open. Session 28 validated (12 commits checked,
reseals confirm 749/10, tracker summary confirms the coverage repair:
yfinance source on 2,958 of 3,059 names, 508 in the 1–3 bucket). Plain language.

## 0. THE CLOCK ITEM — nothing on Railway changes until we push

The loops still run the last pushed image. If nothing is pushed tonight,
Monday runs the OLD code and the tracker books hold nothing. But pushing NOW
deploys hack6 choosing 13 biotechs by dictionary order. So the order is fixed
and it has a deadline:

1. **hack6 ranking fix** (decision taken, §1) — one line + test.
2. **Liquidity floor** (decision taken, §1) — one line per book + test.
3. **Data-staleness guard** (§2, small) — the seal and the portfolio builder
   refuse tracker data older than 2 sessions, printing its age. Tonight's gap:
   the lock has a staleness rule, the DATA does not.
4. `python run_tests.py` → `fleet --check-all` → **push by 08:00 ET Monday**
   (20:00 SGT). If any of 1–3 is not green by 07:00 ET, push `df31a7f`'s
   state instead (books empty but safe) and say so — a book that holds nothing
   is recoverable; a book that holds dictionary order is a story.

## 1. The three decisions (taken — Murat asked for decisions, these are Fable's, he can override)

**Liquidity: floor $1m/day median dollar volume on all three books; hack6
floor $5m/day; prefer <$10m as a tie-break, do not hard-exclude above.**
Why not the backtest's $100k–$1m sweet spot: at our sizes ($6–8k/name) a
$100k/day name is 6–8% of the day's volume and its spread is often 1–3% —
more than the band's monthly edge. The backtest paid 10–50bps; those names
don't fill at 10–50bps. The $100k–$1m bucket becomes a MEASUREMENT lane
instead: log the quoted spread of those names daily in the tracker
(`spread_bps` column) so after the contest we know what they actually cost.
That is the honest version of "the edge is there" — it is there net of a cost
we have not measured, so measure it before buying it.

**hack6 (preservation) ranks on `upside / |downside|`, coverage 4–25,
liquidity ≥ $5m/day, and a sector cap: ≤ 3 of 15 names per sector.** The
sector cap is what actually kills the 13-biotech failure; any ranking column
without it re-creates the problem in whichever sector is cheapest that day.
Add the same cap to hack3 (≤ 3 of 10) and hack4 (≤ 2 of 5) — the count-bets
lesson: 20 of 21 names falling together was one bet wearing 20 tickers.

**Push: yes — after 1–3, by the deadline in §0.**

## 2. THE CONNECTION MAP — Murat asked "is everything connected, safe, with fallbacks"

The chain as of tonight, with each link's failsafe. Print this table in the
handoff every session; a link without a failsafe is work.

| link | what flows | failsafe today | gap |
|---|---|---|---|
| nightly refresh → tracker | 3,059 rows | resumable, lock, append-only | **yfinance is unofficial** — if it breaks, refresh dies. Fallback: carry yesterday's row forward with `stale=1`, refuse after 2 sessions (§0.3) |
| tracker → sealed book | 749 candidates | seal is hashed, `--verify` | **no age check** → §0.3 |
| book → portfolios (hack3/4/6) | ranked names | worst case derived from code | sector cap missing → §1 |
| portfolios → runner | orders | admission (GROSS, notional, opening range), day latch, daily-loss latch | none known |
| runner → Alpaca | fills | URLError→refusal conversion, supervisor wrap | ledger hash chain **still broken since 25 Aug** — do not repair silently; log it in every report until we decide |
| fills → tracker | held_by/pnl written back | — | **not yet wired** (brief d §4 last line) — do it this session; without it the "accumulating our own data" loop is open |
| logic brain → tracker rows | p_up adjustments | can only adjust ±, must cite a fact, code-capped | speaks on 16/749 (corpus is famous-names-only) — see §4 problem 2 |

## 3. WHAT'S LEFT ON THE ROADMAP (after §0–2)

Done this weekend: guards, tracker, IBES verdicts, T12 (no), T13 v1, logic
brain v1, book claims. Left, in order:

1. **#8 SURPRISE encoding** (Opus's own recommendation — endorsed, do first
   after the push): day-0 abnormal return and abnormal volume vs the name's
   own 60-day sigma, on the CRSP panel, **controlled against plain 5-day and
   12-month momentum** — if surprise adds nothing over momentum, say so and
   stop. If it adds: it becomes a tracker column and the brain's second fact.
2. **Fills → tracker write-back** (§2 last gap).
3. **#5 second decider family on T1/T13** (gpt-5-mini as decider, DeepSeek
   rewrites — swap roles) — only the calibration claim needs it.
4. T11 bias-state panel (still the novel-paper candidate).

## 4. PROBLEMS AND LIMITS — plain, for Murat to invent around

1. **Time is the scarce thing, not compute.** T13 has 11 monthly observations;
   the contest has 4 sessions left. No amount of parallel work manufactures
   independent months. Anything scored on 21 days cannot resolve before
   judging — the books are graded at their 5-day checkpoints only.
2. **The news we have is famous-names news.** Benzinga: 1,566 NVDA stories,
   3 on a small biotech. The logic brain can only speak on 16 of 749
   candidates. Workarounds to choose from: EDGAR 8-K text (every listed
   company files, $0), IR/PR feeds per candidate ($0, slow to build), or a
   paid small-cap feed. The tracker doesn't need news; the BRAIN does.
3. **The model ranks better than it prices.** T13 calibration is negative in
   all four arms — keep the ordering, throw the probability away, or make the
   probability come from the base rate and let the LLM only reorder.
4. **Free market data is a day behind.** Bars stop at the last closed session
   and options OI is missing. A 09:15 seal prices on Friday's close. Fine for
   21-day claims, blinding for intraday ones — so we make none.
5. **The thin-name edge is real but unbuyable at unknown cost.** §1's answer:
   measure the spread daily, decide after the contest.
6. **Two results rest on one model family each** (T13 verdicts, calibration).
   Cheap to fix (§3.3), not urgent.

## 5. NOVEL METHODS (Murat asked; each is one testable sentence + its null)

- **Coverage initiation:** the day a name goes 0→1 analyst is a dated,
  whole-market event nobody's counting; test on IBES 2013–24 (first target in
  the file per name), null = matched names of the same size/sector without an
  initiation that month.
- **Revision velocity:** rank on the CHANGE in consensus target over 30 days,
  not its level — a rising 30% upside and a decaying 80% upside are different
  animals; the tracker's append-only history makes this computable from day 3
  of its own data (and IBES gives the 11-year version now).
- **The disagreement spread:** yfinance gives high/low targets free; a wide
  target range on a thin-coverage name = one analyst who knows something vs
  one who doesn't. Test whether (high−low)/price conditions the upside edge.
- **Brain-vs-rule ledger:** every night the brain's reordering of the rule's
  list is logged; after 10 sessions we have OUR OWN dataset answering "does
  the LLM add ordering skill on top of the rule" — no vendor can sell us that.

## 6. Do not

Touch gross/stops/opening range · repair the ledger chain silently · pool
eras/horizons · push with hack6 unfixed (see §0's fallback instead) · read a
verdict off a job that is still writing.
