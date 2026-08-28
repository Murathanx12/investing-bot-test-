# Strategy review before kickoff (2026-08-28, 08:45 ET)

Murat: *"with the papers I see you are trying one strategy only but the best I
bet will be mixing them — review the strategy, review how other winners did,
how the Bloomberg competition is comparable, and what we learned."*

## 1. One strategy per account was deliberate, and it is now half the fleet

Five of the six accounts hold ONE selector each on purpose: an Alpaca account
is one equity curve, and a curve that mixes three selectors cannot say which
of them paid. The parent project spent five months with ten books that all
selected on one signal and called the differences "strategies"
(`arena_composite`, 99.5% of names carrying only 12-1 momentum) — folding a
new mechanism into a composite hides the only thing being tested, whether its
errors are different errors.

Murat's bet is also right, and it is testable: **`hack6` is the BLEND** —
council vector + post-print drift + theme basket in one aggressive book. If
mixing is better, `hack6` ends above `hack2`, `hack3` and a paper council-only
book. If it does not, the ledger says which leg dragged. Both claims get a
number by 4 Sep.

What "mixing" must NOT mean: averaging forecasts. The runner takes one
position per symbol from whichever brain has the strongest priced claim and
records every other brain's view as a counterfactual. Errors stay separable.

## 2. What past winners actually did (measured, not remembered)

- **lablab Alpaca hackathon (prior round, `reference_lablab_judge_rubric`):**
  the winner was **+$19 on a backtest**. Admission of failure scored. Judges
  asked *"why ARM over five correlated names?"* — the concentration question.
  The P&L bar is low; criteria 2–4 (creativity, engineering, presentation)
  decided it.
- **This round's post:** $5,000 pool, 3 winners + 2 social-engagement awards,
  "P&L *and* creativity or engagement". A one-page write-up (AI logic, risk
  gates, Alpaca infra) is a deliverable. The account ID is how P&L is read.
- **GitHub field:** TradingAgents (~100k★, role agents + bull/bear debate),
  ai-hedge-fund (~63k★, investor personas, does not trade), FinRL-X
  (weight-centric RL, Alpaca execution). None price their refusals, none seal
  an account's birth, none replay their own design on real option quotes.
  Every one of them collapses to mega-caps by construction (the universe is a
  list of famous tickers). That is our write-up's first paragraph.

## 3. The Bloomberg Trading Challenge, and what transfers

Bloomberg's challenge is ~six weeks, teams start with a fixed notional, and
the score is **return relative to a benchmark, ranked** — a tournament, not a
utility. Three things about it are measured facts of tournaments generally:

1. **Rank objectives reward variance.** A team behind the leader late should
   take more risk, not less: P(finishing first) rises with variance once you
   are behind, and E[return] is irrelevant to the rank. Our `alpha/tournament.py`
   already encodes this — BASE ranks on the median (five compounding sessions
   follow the median), ATTACK (behind late) ranks on EV. That switch is
   pre-registered, not improvised.
2. **Winners are concentrated and leveraged; so are the bottom of the table.**
   The same behaviour produces both tails. With SIX accounts we can afford the
   tails on four of them and hold two safe — the fleet is a portfolio of
   tournament entries, which one account could never be.
3. **The benchmark decides the trade.** Bloomberg scores vs an index; Alpaca
   scores raw P&L. Raw P&L over five sessions is ~80% market beta plus noise:
   expected from beta alone ≈ +0.5% (SPY drift), one-sigma ≈ ±2.5%. Anything
   we call "alpha" is inside that noise band, which is why the safe accounts
   hold beta and the risky ones hold *variance we chose*.

What does NOT transfer: Bloomberg teams have six weeks of prints and macro;
we have five sessions with THREE relevant earnings events (NVDA reaction,
PANW 2 Sep, AVGO 3 Sep) and NFP on the 4th (a gap, not a trade). The
post-print drift edge fires at most three times; the rest of the window is
beta and the thesis basket.

## 4. What we learned this week that is now IN the fleet

| lesson | where it lives |
|---|---|
| the chain overprices mega-cap prints, but only on two names (NVDA, AVGO); "all UP refused" was too crude | `refuted.py` scoped to its sample |
| long straddles: t −5.7 to −8.7 over 26 years; the −$37k day was long vol with no catalyst, short vol with one | no long-straddle structure in any mandate |
| the 70%-short-put-spread core fails on real quotes | it is not in any mandate |
| all of the return is overnight; enter MOC, never flatten intraday | `hack1` enters MOC; exits every 5 min but never at the open |
| concentration is a negative-return decision (k=5 0.09x → k=100 0.73x) | `basket` profile, 6%/name, 15+ names |
| a brand-new account has `last_equity=0` → every entry refused | `daybreak` derives from genesis; genesis frozen on all six |
| a hand-picked universe is survivorship bias | the theme seed carries the caveat and is graded vs IWM |
| a refusal and a dead loop print alike | `railway logs` per role; the staging key was pulled the hour it died |
| a dislocation between surprise and reaction does NOT pay; continuation does | `dislocation_scan` labels relabelled; `hack4` trades the continuation cell |

## 5. What we expect (written before the first fill)

- `hack1` (SAFE): median +0.3%, P(≥+2%) 27%, P(≤−5%) 1.8%.
- `hack2` (SAFE): cash until a print; +1.08%/event on ~3 events at 8% ⇒ +0.25% ± 0.6%.
- `hack3` (THESIS): basket beta to a sector that just fell 30%; ±14% one-sigma.
  This is the account most likely to be either first or last.
- `hack4` (PREDATOR): continuation cell +0.11% median/3 sessions per name; the
  pair mostly refused by the MDM floor; expect a thin book and small numbers.
- `hack5` (CONVEXITY): long premium at 100% vol; P(profit) 33–51% per
  structure; expect a −40%…+150% sleeve outcome on 40% of equity ⇒ account
  range roughly −15%…+60%. Mean-ranked by design.
- `hack6` (BLEND): between `hack2` and `hack3`; the question is whether the
  council's vector adds a sign the price brains lack.

If, on 4 Sep, the ranking is `hack3`/`hack5` at the top, the lesson is
"variance won a tournament"; if `hack1`/`hack2` are at the top, "beta and one
measured edge beat conviction". Either is a result; both are written here first.
