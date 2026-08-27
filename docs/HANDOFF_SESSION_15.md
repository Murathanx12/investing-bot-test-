# SESSION 15 — 2026-08-27 — the gates that could not go green

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | **unchanged** |
| best forward paper strategy | `market` (SPY buy-and-hold) seeded and filling; dev/exp1 manage-only |
| independent selector count | **unchanged** |
| farm candidates tested / promoted | **0 / 0** this session |
| new actionable finding | the effective book ceiling moved 40% → 35%; the reserved-event exemption is dead code at `aggregate_cap ≥ 45%` |
| external execution drag | not measured this session |
| LLM spend | ~$0 (one failed DeepSeek call in a dry pass) |

> **RESULT IMPROVEMENT: NONE.** Every change below is a guardrail or an
> infrastructure fix. No strategy was tested, no candidate promoted, and no P&L
> moved. What changed is the set of accidents that can destroy the record.

---

## 1 — The suite could reach the live venue. Now it cannot.

A `--manage-only` test stubbed `loop._run` but not `loop.subprocess.call`, so a
CHILD process ran `belief_vs_chain` against the venue and appended **338 rows**
to `state/belief_series.jsonl`. Once the judged account exists, that class of
accident writes into a judged record.

There was nowhere for a guard to live — **no conftest, no pytest.ini, no
pyproject**; every suite is a standalone script. So:

- the switch is `AAT_TEST_MODE`, set by **`run_tests.py`**, and it is an ENV VAR
  because a monkeypatch in a parent cannot reach a child and an env var is
  inherited by one;
- the block is at the **socket**, installed at import of `alpha/config.py`,
  which every script already imports — so it needs no per-file discipline, which
  is the property the original bug was missing.

A first cut refused inside `credentials()` and broke two suites that plant FAKE
keys precisely so they can exercise role logic offline. **A fake key cannot reach
a venue; a socket can.**

**Zero egress**: `connect` *and* `getaddrinfo` are refused, so no DNS query for
the venue leaves either. The first version blocked `connect` only, on the
argument that a lookup is not an order — true, and still wrong while the switch
is described as "no network in tests".

> **Run the suite with `python run_tests.py` and nothing else.** Running a
> `tests_smoke_*.py` file directly leaves the venue reachable.
> `--allow-venue` opts out deliberately and prints a banner.

Two things the runner found on its first run:

- the real check count is **917, not the 306 quoted in recent handoffs** — 306
  was `tests_smoke.py` alone standing in for the suite;
- a suite scoring 0 was printing its own wording, not asserting nothing. The
  runner now reports *"no `ok` lines"* rather than diagnosing something it cannot
  distinguish.

## 2 — Intent before POST, and reconciliation that reports rather than repairs

The seeding bug was not a missing argument. It was that **the order goes out
before anything local describes it**, and recovery needs the `decision_id` to
derive the `client_order_id` — which only existed in the row that was never
written. `runner` now writes an `intent` row before `client.submit` and the
`submitted` row after, which breaks that circularity.

Safe mid-flight because every ledger consumer filters on explicit action values
(`book`, `exits`, `recovery`, `fills`, `counterfactual`, `fill_audit`) — pinned
by test rather than assumed.

`scripts/reconcile` **reports and does not repair**: appending to a hash chain on
a program's own guess is the tampering the chain exists to expose.

**Two defects in the reconciler, both found by running it:**

1. the intent scan cannot see the 4,178 dev and 3,179 exp1 rows written before
   the protocol — the rows most likely to hold an old orphan. `--from-venue`
   asks the broker for every order instead and needs no local artefact;
2. its first run reported **16 orders as having no record. Every one was in the
   ledger with the correct `alpaca_order_id`.** The known-set was built from
   role-filtered rows, and those rows carry `account_role: None`, so the filter
   dropped precisely the rows that answered the question.

**Verified after the correction: 0 lost rows on market, dev and exp1.**

## 3 — The book-wide limits are enforced, and why they never were

`book_limits.py` opened with *"implemented, tested, and called by NOTHING."*
That was not neglect. **Wired naively it deadlocks a fresh account:** a pristine
$100,000 book taking a healthy 2%-risk first trade breaches `MAX_SINGLE_THESIS`
(one position is 100% of book max loss) and `MIN_EFFECTIVE_N_RISK` (one position
is 1.00 independent bets). Both are **arithmetic identities on a small book, not
risk statements** — and a gate that cannot go green is a broken gate.

So the two diversification limits bind from `DIVERSIFICATION_BINDS_AT = 5`
positions — not invented here: `SOURCE_PEAD_MID_v1` already declares
`min_effective_n_by_risk_before_6th`. Below it they are **measured and reported
but do not refuse**; a four-position book with 90% in one name must not read as
clean. An UNKNOWN position count gets no warm-up.

Placed **last** in `admit()`, not first: the specific reason should beat the
general one, and running first bypassed the reserved-event exemption.

`n_risk` is measured **once per cycle** in the runner (one batched bars call),
never inside the per-order path.

**Two policy facts this surfaced, both now pinned by test:**

- admission allowed the book to reach **40%** of equity (50% aggregate cap − 10%
  free) while `MAX_BOOK_STRESS` caps it at **35%**. Those numbers contradicted
  each other; 35% is the one with a derivation. **The effective ceiling moved to
  35%.**
- the reserved-event exemption needs post-trade max loss in
  `((cap − 0.10), 0.35)`, which is **EMPTY at `aggregate_cap ≥ 45%`** — dead code
  reading as a live policy.

Replaying the 25 Aug dev book order by order: **stopped at 5 orders / 32.5%**
instead of reaching the 72.9% it actually reached.

> **NOT LIVE-VERIFIED.** A dry pass timed out in the chain fetches before
> reaching admission, so this wiring is covered by the suite and not yet by a
> live pass. Exercise it before the judged account is writable.

## 4 — State of the competition gate

- **The `competition` credential does not exist.** `AAT_COMPETITION_KEY_ID` is
  unset, so the judged account has not been created. That is correct — the rules
  require a brand-new $100k account — but it is the last external gate.
- **`alpha/tooling.py` already implements the MCP/CLI requirement**, and with the
  right idea: the MCP server can be started with the `trading` toolset withheld,
  so an LLM connected to it *has no order-placing verb*. That is worth a screen
  of the demo.
- **The expression engine already exists** (`structures.py`, `sizing.py`,
  `payoff.py`, `shape.py`, `equity.py`). Do not rebuild it. Prove the chain
  end-to-end instead.
- Both repos are **public**: `Murathanx12/Aegis-Finance` and
  `Murathanx12/investing-bot-test-`. `docs/HANDOFF.md` lives in the latter and
  404s in the former, by design — now documented in `CLAUDE.md`.

## 5 — Tooling installed

`graphify` (`graphifyy` 0.9.50) installed as a user skill; optimus's
`aegis_skills()` now reads three roots and sees all 9 skills.

**`pip install agent-reach` installed the WRONG PACKAGE** — PyPI's `agent-reach`
is `jgalea/agent-reach` 0.1.0, not `Panniantong/Agent-Reach` 1.5.0. Uninstalled.
Check `project_urls` on the PyPI JSON API before installing anything derived from
a GitHub link.

## 6 — The next discriminating test

1. **Grade the 27-Aug session** — `contagion`, `anchor_to_torque`, condors vs the
   pre-outcome receipt. Still outstanding.
2. **Exercise admission live** so §3 stops being suite-only.
3. **Re-pull the rules at kickoff** as `RULES_SNAPSHOT_2026-08-28` and fail
   preflight if a requirement changed.
4. **Price real option wings** off expired bars — the one measurement between
   `FAILED_VARIANT` and a defined-risk premium arm.

## 7 — Blockers

| blocker | who clears it |
|---|---|
| `competition` account does not exist | Murat, at kickoff |
| NVIDIA key exposed twice in transcript | Murat — rotate |
| Railway plan tier unreadable from CLI | Murat — dashboard |
| `state/counterfactual.jsonl` 561 MB, ~10k marks/hour | unowned |
| ledger hash chain break at line 1203 (25 Aug) | declared epoch; do NOT repair silently |
