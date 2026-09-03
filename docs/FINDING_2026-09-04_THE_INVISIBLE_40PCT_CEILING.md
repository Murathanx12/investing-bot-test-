# FINDING 2026-09-04 (overnight Opus session) — the fleet's deployment ceiling is one word: UNCLASSIFIED

Two night-watch items handed over by the day session (S36 close), both now
root-caused with receipts. Diagnosis only — **nothing is hotfixed pre-judging**
(builder boundaries hold; judging 2026-09-04 11:00 ET).

## 1. hack3 entered none of its ten sealed names — and the reason caps the WHOLE fleet

**Reproduced locally** (dry run, hack3's exact loop args + today's seal
4fdc008f fetched from the authority; log:
`state/nightwatch/hack3_dryrun_20260904.log`):

- `inject_sealed_portfolio` WORKS: `+10 names -> ASPI,DAKT,ELDN,IMRX,INVA,IVA,KDK,LENZ,MOMO,RELX`.
  The peer hypothesis (sealed names never reach the forecast universe) is
  REFUTED — the S29/S30 guard does its job.
- All ten produce forecasts. Three pass admission (`DRY ... IVA/ELDN/IMRX`).
  The other seven die in ONE guard:

      ADMISSION refused <name> long_shares: DRIVER: after this order the book
      would carry 41% of equity in notional on the single driver 'UNCLASSIFIED'
      (cap 40%)

- `refusals by class: risk=7`. considered=10 submitted=0(dry 3) refused=7.

**Root cause chain:** `alpha/drivers.py` declares themes from
`docs/seed/universe/THEMES_2026-08-28.json` (~39 hand-declared theme symbols);
every symbol not in it falls to `UNCLASSIFIED`, and *every UNCLASSIFIED name
shares ONE bucket* — deliberate conservatism ("not knowing whether four names
are independent is not evidence that they are"). That reading was designed for
the theme universe. The sealed tracker books draw from a 3,056-name
whole-market watchlist, so effectively **every tracker name is UNCLASSIFIED,
and every tracker book is capped at `DRIVER_SHARE_OF_GROSS` = 40% of gross
authority — total, across all its names.**

**The live venue numbers confirm it to the decimal** (utilization
2026-09-03): hack3 ACTUAL 33.3% (intent 83%), hack6 35.9% (intent 90%),
hack4 40.2% (intent 50%). Three books, three personalities, one ceiling.
This — not caution, not admission strictness — is the standing answer to
"why is most buying power unused." A taxonomy coverage gap became a
fleet-wide position limit, silently, wearing a risk guard's clothes.

Note what this is NOT: the guard is not wrong to distrust unknown
correlation ([count-bets-not-tickers] cuts both ways). What is wrong is that
a *data-classification gap* binds harder than any declared intent and no
surface said so. `utilization.py` shows ACTUAL vs INTENT vs CEILING — but the
BINDING ceiling (driver cap on one bucket) appears nowhere.

**Fix direction (post-judging fix train, P1 — ahead of everything except the
red-team risk guards):**
(a) give tracker names a real declared taxonomy at seal time — sector/SIC
    from the panel (the finance repo's SIC work tonight makes 9999 an honest
    `Unclassified`; the EDGAR collector now pulls per-CIK SIC) — so the
    driver cap binds per SECTOR, not per absence-of-label;
(b) keep `UNCLASSIFIED` as the conservative fallback for the truly unknown;
(c) `utilization.py` and the daily learning report print which constraint is
    BINDING (driver cap / gross cap / per-name cap / admission), per book —
    a ceiling that cannot be seen teaches the reader that idle = chosen.

## 2. hack6's BUR stop refused every pass (HTTP 422) — the id outlives its order

`alpha/protect.py::stop_client_order_id = sha256(symbol|qty|stop_price)` —
deterministic in the inputs, BY DESIGN, to stop double-placement inside one
pass. But Alpaca requires `client_order_id` uniqueness against the account's
whole order HISTORY: once a BUR stop with the same (symbol, qty, price) triple
has ever reached a terminal state (filled/cancelled — e.g. yesterday's stop
before the re-entry), every re-place of the same triple is 422
"client order id must be unique", forever. `ensure()` sees no live stop and
retries next pass: the refusal loops, and BUR x15 (~$65) rests unprotected.

Trivial dollars, bad class: any re-entered name that lands on the same qty
and stop price re-creates it. Fix direction (post-judging): salt the digest
with the session day (`symbol|qty|price|day`), or catch the 422-unique
refusal and re-place with an attempt salt. Idempotency is unaffected either
way — the docstring itself says it rests on reading the venue's open orders,
not on the id.

## Open question (not asserted, logs scrolled)

hack3 SOLD IVA at 09:33 ET — a name in TODAY's sealed book — before the
10:01 entry pass tried (and driver-cap-failed) to re-admit it. Whether that
exit judged against the right day's book needs the runner's exit-pass log,
which is outside the 500-line Railway buffer. Tomorrow's fill audit should
pull `state/fills` from the volume before this is called a third bug.

## Ops notes from the same night

- `seal-authority` now has a PUBLIC domain
  (https://seal-authority-production.up.railway.app) — created inadvertently
  by `railway domain` while checking for one; kept deliberately after
  verifying the server is `SimpleHTTPRequestHandler` (GET/HEAD only, serves
  only the books dir, POST=501). Books are public in the repo anyway.
  Review after judging; delete if unwanted.
- The authority's 2026-09-03 seal (sha 4fdc008f, verified) is now also at
  `state/predictions/2026-09-03.json` on the laptop — fetched for the
  reproduction; harmless (laptop runs no loops) and it lets local tooling
  (utilization intent, learning report) see the solo seal.
- Benchmark regret receipt: `state/benchmark_regret_20260903.json` (SPY flat
  +0.07% over the window; hack4 -0.22pp the best line, only positive-realized
  book at +$2,027).
