"""C3 -- SILENT-FRAGILITY SWEEP over everything touched since 2026-09-04.

    python -m scripts.labor_c3_fragility_sweep            # write both receipts
    python -m scripts.labor_c3_fragility_sweep --print    # and print the table

THE HOUSE FAILURE MODE
======================
Not wrong arithmetic -- tests catch that. **Code that runs green and does
nothing**: a broad `except` that returns a plausible EMPTY value, a rate over a
zero denominator, a `.get(k, 0)` where absence and a real zero mean different
things, a gate whose inputs can be missing so it can only ever pass. Every one
of those produces a number a reader cannot distinguish from a measurement.

The canonical instance in this project is `spent_usd()` reading a MISSING file
as $0.00 and re-authorising $30 that had already been spent. This sweep found
that same shape rebuilt in the successor module one release later, and in the
provenance checker written to catch exactly this class.

WHAT THIS FILE IS
=================
The sweep itself was a read of every Python file both repos touched since
2026-09-04 (the `silent-fragility-audit` discipline: find candidates
mechanically, then READ the surrounding code and judge each one). This module
carries the RESULT -- the ranked findings, with file, line, what plausible-but-
wrong output each can produce, who consumes it, the proposed refusal, and
whether a fix is safe -- so that the list is a queryable artefact rather than a
paragraph in a handoff that nobody greps.

It also re-verifies, at run time, the two findings that were FIXED, so this file
cannot quietly become a description of a repo that has moved on.

Receipts:
    aegis-alpha-terminal/state/labor_day_lab_2026-09-07/C3_fragility_sweep.json
    aegis-finance/backend/data/optimus/labor_day_lab_2026-09-07/C3_fragility_sweep.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = Path(__file__).resolve().parent.parent
FINANCE = TERMINAL.parent / "aegis-finance"

#: The scope, as the mandate defined it: every module touched since 2026-09-04.
SCOPE_CMD = "git log --since=2026-09-04 --name-only --pretty=format:"

F = "FIXED"
R = "REPORTED"

#: Ranked most dangerous first. `rank` is the sweep's ordering; `state` is what
#: this session did about it. A finding is REPORTED rather than FIXED when the
#: repair changes what a LIVE loop refuses -- that is attended work, and a lab
#: session that quietly re-tunes a risk gate has done the thing this whole
#: programme exists to prevent.
FINDINGS: list[dict] = [
    {
        "rank": 1, "state": F, "repo": "finance",
        "file": "backend/services/llm_telemetry.py", "lines": "1071-1075",
        "what": "`spend()` returned a populated dict of ZEROS for a ledger it never read.",
        "detail": (
            "`read_calls()` returns [] when the path cannot be resolved, when the file "
            "does not exist, and when every line is torn. `spend()` then returned "
            "{'n_calls': 0, 'total_cost_usd': 0.0, ...} -- truthy. Its own docstring "
            "says \"Returns {} on failure, never a zero: research_budget reads an empty "
            "dict as 'spend is UNKNOWN' and refuses\", and there was no such branch."),
        "consumer": ("backend/services/research_budget.py:121 -> check():137 tests "
                     "`if not s:`; a truthy dict of zeros skips it and calls_left becomes "
                     "MAX_CALLS, usd_left becomes MAX_USD -- the whole ceiling is "
                     "re-authorised at the moment the accounting is broken."),
        "refusal": ("return {} when the resolved path is None or does not exist, tested "
                    "on the FILE and before any filtering -- a `since`/`purpose` filter "
                    "that matches nothing is a REAL zero and must stay one."),
        "safety": "SAFE (both consumers already document and handle {})",
        "test": "backend/tests/test_labor_lane_c.py::test_spend_refuses_when_the_ledger_file_does_not_exist",
        "lineage": "[[a docs move disarmed a budget gate]], rebuilt in the successor module",
    },
    {
        "rank": 2, "state": R, "repo": "terminal",
        "file": "alpha/admission.py", "lines": "112-113, 369-385",
        "what": "the DELTA-STRESS risk gate reports $0 and cannot fire when the sigma "
                "derivation throws.",
        "detail": (
            "`book_greeks` sets derived=True as soon as `attribute_book` succeeds. If the "
            "second block (positions / reconstruct / OCC decode) raises, daily_sigma is {} "
            "but derived is still True. Every underlying lands in `missing`, stress stays "
            "0.0, and `stress_2sigma_delta_usd: 0.00` is stamped as a measurement. "
            "`if stress > STRESS_CAP * equity` can never be true."),
        "consumer": "alpha/runner.py:1055 -> :1470 (the live entry path); runner checks "
                    "only greeks.derived, which is True.",
        "refusal": "set derived=False in the sigma except, and emit "
                   "stress = 'CANNOT DETERMINE' whenever `missing` is non-empty.",
        "safety": ("RISKY IN EFFECT: it will start REFUSING entries that pass today. That "
                   "is the point, and it is exactly why it is not a lab commit -- six live "
                   "services re-arm on Tuesday and a new refusal on their entry path is "
                   "Murat's call, not a Sunday's."),
    },
    {
        "rank": 3, "state": F, "repo": "finance",
        "file": "backend/services/receipt_provenance.py", "lines": "150-164, 469-472",
        "what": "a file the loader could NOT find counted as a file it opened.",
        "detail": (
            "`InputTracker.opened()` records a nonexistent path as "
            "{'path': ..., 'error': 'MISSING'} and appends it to the order -- correctly. "
            "`check_receipt` built `opened` by filtering on `path` alone, so those entries "
            "satisfied both EMPTY_INPUTS and UNOPENED_PATH_STAMPED. A job whose every "
            "input was absent produced a receipt that passed the provenance sweep CLEAN."),
        "consumer": "every receipt sweep in the finance repo; this is the module written "
                    "to catch the W4b 'stamped a path it never opened' defect.",
        "refusal": "exclude error-bearing entries from `opened` and emit a hard "
                   "INPUTS_MISSING_ON_DISK finding naming them.",
        "safety": "SAFE (may correctly turn some existing receipts red)",
        "test": "backend/tests/test_labor_lane_c.py::test_a_MISSING_input_does_not_count_as_an_opened_one",
    },
    {
        "rank": 4, "state": R, "repo": "finance",
        "file": "learner/allocator.py", "lines": "349-365, 651-668",
        "what": "a sleeve whose uncertainty inputs are ALL unreadable scores as ZERO "
                "uncertainty -- so failing to read the evidence FLATTERS the sleeve.",
        "detail": ("`_uncertainty_total` returns value: 0.0 with basis: 'derived' even when "
                   "`missing` is every sub-component. `utility_of` rejects only None, so "
                   "U = E - l1|CVaR| - l2*Costs - l3*0 and the sleeve is scored risk-free "
                   "relative to peers, taking a larger margin-proportional share."),
        "consumer": "build_decision_artifact -> write_decision_artifact (the SHADOW "
                    "allocation artifact -- no capital moves on it today).",
        "refusal": "return {'value': None, 'basis': 'REFUSED', 'missing': [...]} when "
                   "nothing was summed, so utility_of returns None and the row gets "
                   "GATE:UNPRICEABLE. The None path already exists and is handled.",
        "safety": "SAFE, but the allocator is another lane's file this weekend -- handed "
                  "over rather than edited underneath a peer.",
    },
    {
        "rank": 5, "state": R, "repo": "terminal",
        "file": "scripts/daily_learning_report.py", "lines": "640-641, 396-435",
        "what": "a MISSING decisions ledger reads as 'the book held'.",
        "detail": ("An absent or AAT_LEDGER_DIR-shadowed state/decisions.jsonl yields rows=[] "
                   "-> holding_discipline([], day) -> status 'ok' with the sentence \"no exits "
                   "today -- with entries armed, that is a book holding.\" Because status is "
                   "'ok', refusal_census.take() skips it, so it appears in neither the "
                   "PLUMBING nor the NO_DATA_YET count."),
        "consumer": "section (c2) of the daily learning report -- the metric the entire S39 "
                    "churn finding rests on, reported green from an empty set.",
        "refusal": "pass a ledger_exists flag and return _cannot(..., CAUSE_PLUMBING).",
        "safety": "SAFE, but daily_learning_report.py was rewritten on 2026-09-05 and is "
                  "live in the nightly loop; reported so the repair is made with its "
                  "author's context.",
    },
    {
        "rank": 6, "state": R, "repo": "terminal",
        "file": "scripts/discovery_autopsy.py", "lines": "225-233, 305",
        "what": "a news-endpoint outage EMPTIES the discovery-failure research queue and "
                "the receipt records the emptiness as a finding.",
        "detail": ("`pre_move_evidence` catches every exception into news = [] and returns "
                   "news_before_open: 0. The queue is built as `[m for m in rows if "
                   "m['where'] == 'NOT_GENERATED' and m['news_before_open'] > 0]`, so a 403 "
                   "or 429 produces research_queue: [] -- 'nothing was knowable beforehand', "
                   "which is the exact claim the Micron test exists to test."),
        "consumer": "state/autopsy/discovery_<day>.json -> the research queue.",
        "refusal": "news_before_open = None on the except path (as `has_options` already "
                   "does), exclude None rows from `missed`, count news_unreadable.",
        "safety": "SAFE. Deferred with rank 7 to keep this session's edits inside the "
                  "files it demonstrated a fault in.",
        "lineage": "[[a rate limit reads as absence]]",
    },
    {
        "rank": 7, "state": R, "repo": "terminal",
        "file": "scripts/discovery_autopsy.py", "lines": "203-206, 324",
        "what": "the receipt names FIVE observation sources that were never read.",
        "detail": ("`inputs['observed_sources'] = sorted(lists)` sorts the dict's KEYS, which "
                   "are the five hard-coded names, populated or not. Separately, "
                   "`fleet.theme_symbols()` raising FileNotFoundError is swallowed by a bare "
                   "`except: pass`, so every seeded name then types NOT_OBSERVED -- whose "
                   "documented repair is 'COVERAGE: a wider universe' -- and `observed` has "
                   "no readability check at all in the refusal guard at :334."),
        "consumer": "the opportunity-recall ledger, i.e. what the research programme is "
                    "pointed at next.",
        "refusal": "sorted(k for k, v in lists.items() if v), plus a per-source "
                   "{name: ok|MISSING|UNREADABLE} block and `observed` in the unreadable list.",
        "safety": "SAFE",
    },
    {
        "rank": 8, "state": R, "repo": "terminal",
        "file": "run_tests.py", "lines": "66-68, 137",
        "what": "the production-ledger tripwire cannot see a DELETED ledger, cannot see an "
                "in-place rewrite of equal length, and cannot tell a TEST from another "
                "PROCESS.",
        "detail": ("`grew` iterates `after`, so a ledger present before and absent after never "
                   "appears. Sizes, not hashes, so an equal-length rewrite is invisible. And "
                   "measured live this session: the tripwire fired on state/llm_spend.jsonl "
                   "during a clean 78-suite run -- every row added in the window had caller "
                   "'labor_b2.fantasy_exam', a CONCURRENT PEER LANE. It reported "
                   "'A test wrote into a production ledger'. No test did."),
        "consumer": "every `python run_tests.py` verdict; a tripwire that cries wolf on a "
                    "concurrent process trains the reader to skim its banner.",
        "refusal": "iterate set(before) | set(after); fingerprint by SHA-256; and attribute "
                   "the delta (the added rows carry a `caller`) before blaming a suite.",
        "safety": "SAFE, but run_tests.py was edited on 2026-09-05 and may be in a peer's "
                  "hands this weekend. Reported.",
    },
    {
        "rank": 9, "state": R, "repo": "terminal",
        "file": "run_tests.py", "lines": "113-124, 147",
        "what": "a suite that asserts NOTHING is printed `ok` and the run ends ALL PASS.",
        "detail": ("Zero `ok` lines appends the file to `unknown`, contributes 0 to the total, "
                   "and never touches `failed`. The comment concedes it cannot tell 'asserts "
                   "nothing' from 'prints its own wording' and resolves the ambiguity toward "
                   "green -- the `__main__`-guard failure at runner scope."),
        "refusal": "an explicit allowlist of suites known to use other wording; any other "
                   "zero-check suite is a FAIL.",
        "safety": "SAFE",
    },
    {
        "rank": 10, "state": R, "repo": "finance",
        "file": "scripts/night_lab.py / scripts/weekend_lab.py", "lines": "108-116 / 320-327",
        "what": "`run_job` re-reads a STALE receipt when the child dies before writing one.",
        "detail": ("The receipt path is never cleared before launching and `_receipt_path(job, "
                   "run)` collides on any re-run at the same (job, run, variant). An "
                   "OOM-killed child leaves the PREVIOUS run's payload, which is re-stamped "
                   "with the new elapsed_s -- and `payload.setdefault('verdict', 'FAILED')` "
                   "will not overwrite the old verdict, so the old headline is appended to "
                   "the leaderboard and can win update_best."),
        "refusal": "out_path.unlink(missing_ok=True) before subprocess.run; assignment, not "
                   "setdefault, for the failure verdict.",
        "safety": "SAFE, but both runners are lane A/B files this weekend.",
    },
    {
        "rank": 11, "state": R, "repo": "terminal",
        "file": "scripts/utilization.py", "lines": "135-145",
        "what": "a CORRUPT seal silently falls through to the stale SEED book, or reads as "
                "'nothing was sealed'.",
        "detail": ("An unreadable state/predictions/<day>.json `continue`s to the next base, "
                   "which is docs/seed/predictions -- the directory S29 already caught serving "
                   "a stale book (302/1 vs local 749/10). Absent that, it returns None and "
                   "daily_learning_report prints 'there is NO sealed book for <day> ... "
                   "nothing was sealed that day, for any role', with a fix: telling the "
                   "operator to re-seal a file that exists and is corrupt."),
        "refusal": "a third state -- return the unreadable paths and their errors -- so the "
                   "caller says CORRUPT rather than ABSENT and never substitutes the seed.",
        "safety": "SAFE",
    },
    {
        "rank": 12, "state": R, "repo": "terminal",
        "file": "scripts/window_universe.py", "lines": "118, 126, 245-261, 287",
        "what": "'checked, nothing dropped' and 'never checked' write the same receipt; and "
                "an empty earnings calendar is indistinguishable from a filtered one.",
        "detail": ("The tradability check's failure is disclosed only by a print(); the JSON "
                   "writes dropped_not_tradable: [] either way. `finnhub.earnings_calendar` "
                   "returns `(data or {}).get('earningsCalendar') or []`, so a 200 with an "
                   "error body, a null field or a throttle is an empty list, and `plan()` "
                   "records no raw row count. Given the documented Finnhub 503 storm this is "
                   "live. Secondarily, a MISSING revenueEstimate is dropped exactly as if it "
                   "were below the floor."),
        "refusal": "stamp tradability_checked, n_calendar_rows, n_dropped_no_revenue_estimate "
                   "and n_dropped_below_floor; refuse the write on zero calendar rows over a "
                   "multi-week span.",
        "safety": "SAFE",
    },
    {
        "rank": 13, "state": R, "repo": "finance",
        "file": "scripts/weekend_lab.py", "lines": "250-260, 284-285, 305-307",
        "what": "the memory guard's own diagnostic is wrong in the direction that hides the "
                "cause it was written for.",
        "detail": ("`_other_lab_jobs` returns [] on any exception, so a SKIPPED_LOW_MEMORY "
                   "receipt stamps other_lab_job_pids: [] and '0 other lab job(s) running' -- "
                   "the evidence for the OOM post-mortem. And `_free_gb()` returning None "
                   "skips the guard entirely, leaving NO trace in the receipt, despite the "
                   "docstring naming 'a guard that silently passes' as what it replaces."),
        "refusal": "return None (not []) on failure and stamp 'CANNOT DETERMINE'; stamp "
                   "memory_guard: 'UNMEASURED' on every receipt written when _free_gb is None.",
        "safety": "SAFE, lane A/B file this weekend.",
    },
    {
        "rank": 14, "state": R, "repo": "finance",
        "file": "scripts/companyworld_extract.py", "lines": "801-816, 929, 951",
        "what": "rates manufactured from an empty denominator, and six failure modes "
                "collapsed into one None.",
        "detail": ("`cost / max(len(ok), 1) * 100` prints a per-100-filings projection from "
                   "ZERO successes; `n_qv / max(n_edges, 1)` reports quote_verified_rate 0.0 "
                   "for zero edges, indistinguishable from '1,000 edges, none verified'. "
                   "`provider_balance()` returns None for a missing key, an import failure, an "
                   "HTTP error, an unexpected shape and a genuine null alike -- and per "
                   "[[the DeepSeek balance is the truth]] that is the number that adjudicates "
                   "our own telemetry. `alpha/recall.summarise` gets this right in the other "
                   "repo: 'a rate over ZERO movers is None, not 1.0 and not 0.0'."),
        "refusal": "None on a zero denominator; return (value, reason) from provider_balance "
                   "and stamp the reason.",
        "safety": "SAFE",
    },
    {
        "rank": 15, "state": R, "repo": "finance",
        "file": "scripts/weekend_lab_jobs.py", "lines": "517-529, 735-742",
        "what": "a partially-failed walk-forward produces a full-looking, RANKABLE cell.",
        "detail": ("The per-fold error key omits the year, so 20 failed folds of 22 leave ONE "
                   "error entry, each overwriting the last, and the surviving 2 folds are "
                   "concatenated into a cell that is evaluated, ranked, and can win the "
                   "report's `best`. Nothing records folds_attempted vs folds_used, and the "
                   "`if len(tr) < 5000: continue` skip leaves no record at all -- if every "
                   "fold is skipped the cell vanishes from `cells` and a reader cannot tell "
                   "it was tried."),
        "refusal": "key errors per year; count folds_used/folds_attempted into every cell; "
                   "refuse a cell below a declared minimum fold coverage.",
        "safety": "SAFE, lane A file this weekend.",
    },
    {
        "rank": 16, "state": R, "repo": "finance",
        "file": "learner/features_price.py", "lines": "100-105, 189",
        "what": "the receipt stamps the REQUESTED window while silently skipping absent years.",
        "detail": ("Only ALL years missing refuses. Eleven of twenty-seven present produces a "
                   "receipt whose `window` reads '1998-2024'. first_date/last_date betray it "
                   "to a careful reader, but the stamped provenance line is the argument -- "
                   "the W4b defect, and invisible to check_receipt because no PATH is stamped."),
        "refusal": "stamp years_found / years_missing; refuse above a declared missing share.",
        "safety": "SAFE",
    },
    {
        "rank": 17, "state": R, "repo": "terminal",
        "file": "alpha/spend.py", "lines": "134-135, 154-155",
        "what": "`except OSError: pass` on the spend-ledger append -- the call happened, the "
                "row did not -- and `summary()` reads an absent file as calls: 0.",
        "detail": "The same shape as rank 1, in the other repo's spend ledger.",
        "refusal": "count the dropped appends in a process-local sentinel and surface it on "
                   "summary(); return {} (not zeros) for an absent ledger.",
        "safety": "SAFE",
    },
    {
        "rank": 18, "state": R, "repo": "terminal",
        "file": "scripts/utilization.py", "lines": "76-80",
        "what": "`float(acct.get('long_market_value') or 0.0)` -- a venue response omitting "
                "the field reports gross_frac 0%, i.e. 'this book holds nothing'.",
        "detail": "That number is the input to the INVISIBLE 40% CEILING diagnosis (S37). A "
                  "field the venue omitted and a book that is genuinely flat must not print "
                  "the same.",
        "refusal": "None when the key is absent; 'CANNOT DETERMINE' downstream.",
        "safety": "SAFE",
    },
    {
        "rank": 19, "state": R, "repo": "finance",
        "file": "learner/models.py + scripts/weekend_lab.py + scripts/daily_learning_report.py",
        "lines": "437-438 / 176-180 / 566-570, 645-648, 673-676",
        "what": "a cluster of smaller instances of the same shape.",
        "detail": ("feature importance `return {}` on failure reads as 'the model used no "
                   "features'; a corrupt best_so_far.json is reset to {} so the next entry "
                   "becomes BEST SO FAR at any DSR; bad JSONL lines `continue` with no "
                   "skipped-row count, so a wholly corrupt tracker/<day>.jsonl yields an empty "
                   "set (not None) and prints '0 on the watchlist, N dropouts'."),
        "refusal": "None or a typed refusal in each case, with the skipped count surfaced.",
        "safety": "SAFE",
    },
]


def _git(repo: Path, args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                              text=True, timeout=60).stdout.strip()
    except Exception as exc:                                            # noqa: BLE001
        return f"<git unavailable: {exc}>"


def _scope(repo: Path) -> list[str]:
    out = _git(repo, ["log", "--since=2026-09-04", "--name-only", "--pretty=format:"])
    return sorted({l for l in out.splitlines() if l.strip().endswith(".py")})


def verify_the_two_fixes() -> dict:
    """Re-check the FIXED findings against the code as it stands now.

    A list of findings that is not re-derived is a description of a repo that
    may have moved on. Both fixes live in the finance repo, so this runs there
    if it can and says CANNOT DETERMINE if it cannot -- never a silent pass.
    """
    out: dict[str, str] = {}
    if not FINANCE.exists():
        return {"status": "CANNOT DETERMINE: the finance repo is not beside this one"}
    sys.path.insert(0, str(FINANCE))
    try:
        from backend.services import llm_telemetry, receipt_provenance
    except Exception as exc:                                            # noqa: BLE001
        return {"status": f"CANNOT DETERMINE: import failed ({type(exc).__name__}: {exc})"}
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        out["rank1_absent_ledger_is_unknown"] = (
            "PASS" if llm_telemetry.spend(path=d / "absent.jsonl") == {} else "FAIL")
        (d / "empty.jsonl").write_text("", encoding="utf-8")
        got = llm_telemetry.spend(path=d / "empty.jsonl")
        out["rank1_present_empty_ledger_is_a_real_zero"] = (
            "PASS" if got and got.get("n_calls") == 0 else "FAIL")
        t = receipt_provenance.InputTracker()
        t.opened(d / "never_written.parquet")
        findings = receipt_provenance.check_receipt(
            {"_provenance": {"sys_argv": ["probe"], "resolved_config": {},
                             "_inputs_opened": t.entries()}}, require_inputs=True)
        out["rank3_missing_input_is_not_an_opened_one"] = (
            "PASS" if any("MISSING" in f for f in findings) else "FAIL")
    return out


def build() -> dict:
    fixed = [f for f in FINDINGS if f["state"] == F]
    reported = [f for f in FINDINGS if f["state"] == R]
    return {
        "item": "C3", "lane": "C", "lab": "labor_day_lab_2026-09-07",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv,
        "config": {
            "discipline": ".claude/skills/silent-fragility-audit",
            "scope_command": SCOPE_CMD,
            "method": ("mechanical candidate sweep (except / return [] / return {} / "
                       "`or 0` / .get(k, default) / bare continue) followed by a READ of "
                       "the surrounding code and of the CALLER, so that a broad except "
                       "that re-raises or records a typed refusal is not reported"),
            "network": "none",
            "llm_calls": 0,
        },
        "inputs_opened": {
            "terminal": {"repo": str(TERMINAL), "commit": _git(TERMINAL, ["rev-parse", "HEAD"]),
                         "python_files_in_scope": _scope(TERMINAL)},
            "finance": {"repo": str(FINANCE), "commit": _git(FINANCE, ["rev-parse", "HEAD"]),
                        "python_files_in_scope": _scope(FINANCE)},
        },
        "counts": {"findings": len(FINDINGS), "fixed": len(fixed), "reported": len(reported),
                   "by_repo": {"terminal": sum(1 for f in FINDINGS if f["repo"] == "terminal"),
                               "finance": sum(1 for f in FINDINGS if f["repo"] == "finance")}},
        "fixes_reverified_now": verify_the_two_fixes(),
        "why_most_are_reported_not_fixed": (
            "Three reasons, in order of how often they applied. (1) The repair changes what "
            "a LIVE loop refuses -- rank 2 would start declining entries on six services "
            "that re-arm on Tuesday, which is Murat's call with the census in hand and not "
            "a Sunday's. (2) The file belongs to a concurrent lane this weekend "
            "(night_lab, weekend_lab, weekend_lab_jobs, allocator, run_tests) and editing "
            "underneath a peer is how two correct changes become one broken file. (3) The "
            "mandate's own rule: a production module is edited only to fix a fault "
            "DEMONSTRATED FIRST with a failing test, and a demonstration costs more than a "
            "sentence -- so the two with the clearest blast radius were done properly and "
            "the rest are handed over with their line numbers, their consumers and their "
            "proposed refusals."),
        "findings": FINDINGS,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--print", action="store_true", help="print the ranked table too")
    a = p.parse_args()
    payload = build()

    for base, name in ((TERMINAL / "state" / "labor_day_lab_2026-09-07",
                        "C3_fragility_sweep.json"),
                       (FINANCE / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07",
                        "C3_fragility_sweep.json")):
        if not base.parent.exists():
            print(f"skipped {base}: parent does not exist")
            continue
        base.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"receipt: {base / name}")

    if a.print:
        print(f"\n{'#':>2}  {'state':<8} {'repo':<9} file:lines")
        for f in payload["findings"]:
            print(f"{f['rank']:>2}  {f['state']:<8} {f['repo']:<9} {f['file']}:{f['lines']}")
            print(f"      {f['what']}")
    print(f"\n{payload['counts']['findings']} findings, "
          f"{payload['counts']['fixed']} fixed, {payload['counts']['reported']} reported")
    print(f"fixes re-verified now: {payload['fixes_reverified_now']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
