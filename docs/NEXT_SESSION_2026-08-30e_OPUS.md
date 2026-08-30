# NEXT SESSION FOR OPUS — 2026-08-30 (e) — DECISIONS TAKEN, MONDAY CHAIN, THEN T13

Fable, Sun 30 Aug ~22:00 SGT (10:00 ET). Session 27 validated. Plain language.

## 0. Session 27 — validated

- `62d9bb8` + `e9edfe5` (terminal), `09ba798` (Aegis): 57 suites / 2,466 pass,
  fleet green. Tracker refresh **finished: 3,059 names** in `state/tracker/2026-08-30.jsonl`.
- IBES receipt (`backend/data/optimus/tracker_backtest/ibes_status_rules_2013_2024.json`)
  carries `cost_bps_per_side=10`, `ibes_lag_days`, the tracker's sha, the cap
  sensitivity and per-era rows. The 4× cap is a data-cleaning rule (stale
  targets after reverse splits), not a fitted threshold — plateau 1.5×–10×.
- The "requiring news is a mega-cap filter" diagnosis is correct and is the
  real cause of the MU-only book.
- One weakness to fix in §2: 10 bps/side is optimistic for 1–3-analyst names.

## 1. Murat's three decisions (taken by Fable on his instruction "make decisions, be ready before Monday")

| switch | decision | why |
|---|---|---|
| `EXCLUDE_PAST_WINNERS` | **OFF on hack4, ON on hack3** | data says off (+2.9pp/yr, t 3.00); Murat's rule says on. Run both so Friday tells us which — the ON/OFF split is the experiment. hack6 follows hack4. |
| hack3 ranking | **ratio: `exp_return / |downside_5pct|`**, downside also as a hard constraint (≤ 30%) | the subtraction was sorting on low vol and re-importing mega-caps |
| push | **PUSH all three commits** | worst cases −6.64 / −3.00 / −2.70, inside the bound; the book must have many names on Monday |

Murat's question, answered for the record (he asked "why are we capping —
boundaries will limit the project"): there are two kinds of caps and they are
not the same thing. **Data caps** (the 4× upside cap) remove broken numbers,
not opportunities — without it the screen LOSES 5.5%/yr; with it +3.9%. **Money
caps** (gross 100%, stop, opening range) bound how much a wrong opinion can
cost — they are why Friday was −9% and not −24%. Neither cap decides WHAT to
buy; the decider (rule today, LLM council in §4) decides that on the spot,
every day, inside them. **Idea caps are hypotheses**, and two were tested and
one flipped tonight — that is the process working, not the process limiting.

## 2. Before Monday's seal (≤ 3 h)

1. Apply §1 (three one-line changes) with tests; worst case re-derived from code.
2. **Thin-name cost sensitivity** (Aegis): re-run the capped BUY basket by
   coverage bucket at 25 and 50 bps/side. If the 1–3 bucket survives 50 bps,
   Murat's thin-coverage finding is real net of what those names actually cost;
   if it dies at 25, say so and weight hack3 toward 4–10.
3. Monday chain, in order, Murat runs locally after the open data is in:
   `tracker --backfill-prices` → `--show` → `--sectors` →
   `prediction_book --seal --universe tracker` → `--verify` → `--publish` →
   `tracker --portfolios` → commit `docs/seed` → push.
   The seal must show **claims per generator ≥ 10** or print why.
4. hack3 entries: existing limit-order builder (MOC stays deferred), never
   09:30–09:45, MOC wiring is a Tuesday-evening task with its own test.

## 3. New daily surface: the tracker diff (≤ 2 h)

`scripts/tracker --diff` prints yesterday→today: names entering BUY/STRONG_BUY,
names dropping, biggest upside changes, sector counts. Goes into the premarket
digest as a table. This is the "we update the list when needed and keep track"
Murat described; a list nobody reads is not tracked.

## 4. The logic brain ON the tracker — bounded, on the spot (after §2–3)

Murat: "we should make decisions on the spot using the logic brain." Build it
where it is safe to be wrong: for each STRONG_BUY/BUY name (≤ 200/day), the
council (DeepSeek, `spend.justify`) reads the tracker row + last 5 sessions of
that name's new-fact items (T12's relevance labels, `subject && new_fact`) and
returns `{p_up_21d, exp_return, downside_5pct, confidence, reason}`. No
direction from prose alone — the LLM adjusts the rule's base rate up or down
and must name the fact it used. Those numbers go on the tracker row and the
books rank on them. The rule-only number stays beside it, so the grade at
5/21 sessions says whether the brain added anything over the rule — that is
the test Murat wants and it costs ~$0.50/day.

## 5. Then T13 (fantasy transposition) — unchanged from brief (b) §9

Tracker rows are the decider's universe. Rewriter PIT, frozen entity map,
numbers preserved, parity check, calibration table.

## 6. Do not

Touch gross cap, stops, opening range. Pool eras. Read a verdict off a partial
refresh. Deploy without `fleet --check-all`.
