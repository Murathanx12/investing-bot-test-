# 2026-08-31 — the two fixes shipped, and the link they were shipped for does not exist

**RESULT IMPROVEMENT: NONE on Monday's orders.** The §0 fixes are done, tested
and pushed. They do not change what any account trades on Monday, because the
books they fix are not connected to the runner. That is the session's finding
and it is worth more than the fixes.

**READ THIS BEFORE RUNNING THE MONDAY CHAIN.**

## 0. The correction

The 31 Aug (f) brief's connection map said:

| link | failsafe | gap |
|---|---|---|
| book → portfolios (hack3/4/6) | worst case derived from code | sector cap missing |
| portfolios → runner | admission, day latch, daily-loss latch | **none known** |

"none known" was wrong. **There is no `portfolios → runner` link.**
`build_portfolio` — the personalities, the rankings, the sector caps, the
liquidity floors, everything fixed tonight — is called by exactly two things:
`scripts/tracker.py --portfolios`, which prints, and its tests. Nothing the
runner can reach calls it.

Three independent checks, which do not share a cause:

1. `grep build_portfolio` → `scripts/tracker.py` and `tests_smoke_tracker.py`.
2. `python -m scripts.reachability` → `ORPHAN alpha.tracker — imported by no
   entry point`. **The audit was already saying this**, buried among 22 other
   orphans. A permanent red block teaches the reader to skim it, which is the
   CLAUDE.md lesson about red lines, arriving as the thing it warned about.
3. Railway env, all six services:

   | service | `AAT_LOOP_BRAINS` | universe |
   |---|---|---|
   | hack1 | `post_event_drift` | SPY QQQ IWM |
   | hack2 | `post_event_drift` | window |
   | hack3 | `theme_basket` | OUST SYM RCAT ONDS (hardcoded) |
   | hack4 | `post_event_drift` | window |
   | hack5 | `theme_basket,post_event_drift` | OUST SYM RCAT ONDS |
   | hack6 | `council_vector,post_event_drift,theme_basket` | window |

   **`murat_rule` — the only brain that reads a sealed book — is enabled on
   none of them.** `--window-universe` is Finnhub's *earnings calendar*
   (`scripts/window_universe.py`, zero tracker references), not the tracker.

So "hack6 was going to hold 13 biotechs on Monday" was never true. hack6 was
going to trade `council_vector,post_event_drift,theme_basket` over the earnings
window, exactly as it did last week. The 13 biotechs were a print.

## 1. What the real path is

    tracker --refresh
      → prediction_book --seal --universe tracker     (claims per name)
      → --publish   → docs/seed/predictions/<day>.json
                      (/app/state is a VOLUME and SHADOWS state/, so the seed
                       dir is the only delivery path — this is documented in
                       alpha/brains/murat_rule.py and it is correct)
      → the `murat_rule` BRAIN reads that file
      → only if `murat_rule` is in AAT_LOOP_BRAINS for that account.

The bridge is built, registered (`alpha/brains/__init__.py`), unquarantined,
and careful: it declines with a reason when there is no book, trades only names
that CLAIM, and rescales the book's 21-session numbers to the loop's horizon
(centre linear in t, sd in √t) rather than reusing them. It is a switch that
has never been flipped.

`tests_smoke_tracker.py::test_the_books_are_analysis_and_the_only_bridge_to_an_order_is_named`
now pins all of this, so the map cannot drift back.

## 2. Railway does not deploy on push

`df31a7f` was committed **2026-08-30 20:58 +08** and pushed. The most recent
deployment is **2026-08-30 12:44 +08** — eight hours *earlier*. It was pushed
and never deployed. `prediction_book --publish` already prints
"git push, **then redeploy**"; that instruction is load-bearing.

So §0's "nothing on Railway changes until we push" understates it: nothing
changes until someone runs `railway redeploy --from-source`.

**I did not redeploy, and I recommend not doing it before the open.** The 13
unshipped commits touch `alpha/{tracker,logic_brain,transpose}.py` and
`scripts/{tracker,prediction_book,era_replay,logic_brain}.py` and **nothing
else** — no running brain, no `agent_loop`, no admission, broker, exits or
ledger. The loops' code path is byte-identical either way, so a redeploy would
restart six live services to change nothing. Do it when there is a reason.

## 3. What was actually shipped (`6895d69`, pushed)

Correct, tested, and inert until the switch above is flipped.

1. **hack6's ranking.** `confidence` is `(clauses readable / 4) × min(1, date
   blocks / N)` — a property of how much of the ROW could be read, not of the
   name. All 607 eligible names scored 0.9170, the sort was a no-op, and
   Python's stable sort returned insertion order: 12 biotechs, 3 others. Now
   `upside / |downside_5pct|` — reward per unit of the name's own bad case.
   Not `risk_adjusted_ratio`, which divides `exp_return` and so carries *our*
   p_up; hack6 is the book that ranks on the street's number.
2. **Sector caps on all three**, derived as `names × max_notional` and pinned
   to that derivation by test: hack3 3-of-10, hack4 2-of-5, hack6 3-of-15.
   hack6 goes from 3 sectors to 9.
3. **Liquidity floors** — and the honest half: `universe.MIN_DOLLAR_VOLUME`
   already screens the tracker at **$3m/day**, so hack3's and hack4's $1m
   floors exclude **zero** names. Only hack6's $5m floor binds (580 → 514).
4. **A coverage ceiling** to match the floor (hack6 is a 4–25 book; a floor
   with no ceiling lets 26+ mega-caps back in). 27 names dropped.
5. **`max_downside = 0.20` on hack6 — not asked for.** Fix 1 created the need:
   a ratio ranking actively selects for high upside, and high upside is high
   vol, so the first build put FRMI −52.5%, NB −41.6%, RZLV −38.0% into the
   *preservation* book — more per-name downside than *balanced* permits,
   against a 3% stop those names gap straight through. Chosen off a sweep, not
   asserted: fills 15/15 at every cap from 0.35 to 0.15, starves below 0.12, so
   0.20 is mid-plateau with 8.8× headroom. Revert is one field.
6. **The seal and the portfolio builder refuse tracker data older than 2
   SESSIONS** and print its age. The lock had a staleness rule; the data did
   not. `latest_day()` returns the newest file however old, so two dead
   refreshes would have sealed Monday's book on Friday's closes silently.
   Sessions, not calendar days — a calendar rule refuses every Monday and gets
   switched off within a week. The age is in the receipt.

Worst case unchanged on all three books: −6.64% / −3.00% / −2.70%. Every change
removes names or leaves the count flat; none adds gross.
59 suites, **2519 checks, ALL PASS**. Fleet: six accounts reachable, none blocked.

## 4. The measurement lane that was planned, and why it was not built

Brief §1 proposed logging `spread_bps` daily for the $100k–$1m/day band, to
price the thin-coverage edge before buying it. **The tracker contains no such
names.** Minimum median dollar volume across all 3,059 rows is **$3.0m/day**,
by construction. The lane would have had nothing to measure — a collector that
feeds nobody, which this repo fails suites over.

The honest statement of the 11-year result is therefore stronger than the
brief's: the $100k–$1m band that carried the biggest edge is **entirely outside
the universe we screen**. Not "we chose not to buy it" — we cannot currently
see it. Widening `universe.MIN_DOLLAR_VOLUME` is a real decision with a real
cost, and it is a decision, not an oversight.

## 5. The one decision for Murat — before 09:15 ET

**Enable `murat_rule` on an account for Monday, or leave the books as analysis?**

- *Leave it off* — Monday looks exactly like last week. Nothing tonight
  reaches an order. Zero new risk, zero new evidence.
- *Turn it on for one account* — add `murat_rule` to that service's
  `AAT_LOOP_BRAINS`, run the Monday chain through `--publish`, commit
  `docs/seed`, push, **then `railway redeploy --from-source`**. The book claimed
  **10 of 749** on 30 Aug, so it is a small, bounded book, and the brain holds
  cash when nothing claims. This is the only way the sealed book earns a
  forward record before the contest ends.

It is a mandate decision on live paper accounts, so it is yours, not mine. If
you want it on, hack4 or hack6 is the natural host — both already run the
window universe rather than a hardcoded four-name basket.

## 6. Then, in order

1. **#8 SURPRISE encoding** — day-0 abnormal return and volume vs the name's own
   60-day sigma on the CRSP panel, controlled against plain 5-day and 12-month
   momentum. If it adds nothing over momentum, say so and stop.
2. **Fills → tracker write-back** — still open, still the thing that closes the
   "accumulate our own data" loop.
3. Second decider family on T13 (only the calibration claim needs it).

## 7. Do not

Touch gross / stops / opening range · repair the ledger hash chain silently
(still broken since 25 Aug, log it every report) · pool eras or horizons · read
a verdict off a job still writing · **and do not describe the books as trading
until `murat_rule` is in an account's brain list.**
