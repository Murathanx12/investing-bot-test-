"""The RESUMABLE news pull: cursor, log, pid file, per-month receipts.

The pull that died at 2026-09-07 03:18 had none of the four, so 112 months of
Alpaca work could neither be resumed nor even measured. Every check here is
one of those four artefacts, plus the two refusals that stop the failure from
recurring quietly (a relative window; a silent fallback to the 156-name fleet).

The venue is blocked for every suite by the runner's own env guard; this file
does not name that variable, because `tests_smoke_test_isolation.py` checks
that no other suite mentions it at all. Nothing here fetches.
"""
import json
import os
import sys
import tempfile
from datetime import date, timezone       # noqa: F401  (imported for parity with the module)
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


# A scratch state dir, set BEFORE the modules that read it at import time.
_scratch = tempfile.mkdtemp(prefix="aat-news-pull-")
os.environ["AAT_STATE_DIR"] = _scratch
sys.path.insert(0, str(Path(__file__).parent))

from scripts import pull_journal                                        # noqa: E402
from scripts import tradable_universe as tu                             # noqa: E402
import scripts.news_backfill as nb                                      # noqa: E402

ROOT = Path(_scratch) / "pulls"

print("\n-- error_class: an HTTP status is counted as itself, a transport failure as one")
check("429 is bucketed by status", pull_journal.error_class("GET /x -> HTTP 429: slow down") == "429")
check("403 is bucketed by status", pull_journal.error_class("GET /x -> HTTP 403: nope") == "403")
check("a transport failure is its own bucket",
      pull_journal.error_class("GET /x -> transport failure: getaddrinfo failed") == "transport")
check("anything else is 'other', never dropped",
      pull_journal.error_class("item without timestamp dropped") == "other")
t = pull_journal.tally({}, ["HTTP 429", "HTTP 429", "HTTP 500", "transport failure: x"])
check("tally counts by bucket", t == {"429": 2, "500": 1, "transport": 1}, str(t))

print("\n-- pid liveness never SIGNALS the process it probes")
check("this process is alive", pull_journal.pid_alive(os.getpid()))
check("pid 0 is not alive", not pull_journal.pid_alive(0))
# 999999 is above the Windows and Linux default pid ceilings in practice; if it
# ever IS alive the check says so rather than asserting a coincidence.
check("an implausible pid is not alive", not pull_journal.pid_alive(999_999))

print("\n-- run_id is derived from the JOB, so a resume is 'run the same command again'")
a = pull_journal.run_id_for("news", start="2025-01-01", end="2026-09-08", universe="fleet")
b = pull_journal.run_id_for("news", start="2025-01-01", end="2026-09-08", universe="fleet")
c = pull_journal.run_id_for("news", start="2015-01-01", end="2026-09-08", universe="fleet")
d = pull_journal.run_id_for("news", start="2025-01-01", end="2026-09-08", universe="tradable")
check("the same job gets the same id", a == b, a)
check("a different WINDOW is a different job", a != c)
check("a different UNIVERSE is a different job", a != d)
check("the id is filesystem-safe", all(ch.isalnum() or ch in "_.-" for ch in a), a)

print("\n-- the four artefacts exist the moment a run opens")
jr = pull_journal.PullJournal("t_open", root=ROOT, meta={"start": "2025-01-01", "end": "2025-03-01"})
jr.open(["python", "-m", "scripts.news_backfill"])
check("cursor file written at open", jr.cursor_path.exists())
check("log file written at open", jr.log_path.exists() and jr.log_path.stat().st_size > 0)
check("pid file names THIS process",
      json.loads(jr.pid_path.read_text())["pid"] == os.getpid())
check("pid file records the argv, so a survivor can be identified",
      json.loads(jr.pid_path.read_text())["argv"][:2] == ["python", "-m"])
check("months dir exists before the first month finishes", jr.months_dir.is_dir())

print("\n-- a month is DONE only when its receipt is on disk; a kill costs one unit")
jr.complete_month("alpaca", "2025-01", {"symbols_requested": 100, "items_fetched": 7,
                                        "rows_stored_new": 7, "rows_duplicate": 0,
                                        "http_errors": {"429": 1}, "seen": {"AAPL": 7}})
check("the month receipt is a file", (jr.months_dir / "2025-01.alpaca.json").exists())
check("the cursor now says that month is done", jr.is_done("alpaca", "2025-01"))
check("a month never started is not done", not jr.is_done("alpaca", "2025-02"))
check("the OTHER leg is tracked separately", not jr.is_done("finnhub", "2025-01"))
jr.checkpoint("alpaca", "2025-02", 17)
check("an intra-month checkpoint is readable", jr.resume_index("alpaca", "2025-02") == 17)
check("a checkpoint in one month does not leak into another",
      jr.resume_index("alpaca", "2025-03") == 0)
check("totals accumulate on the cursor",
      jr.cursor["totals"]["stored"] == 7 and jr.cursor["totals"]["http_errors"] == {"429": 1},
      json.dumps(jr.cursor["totals"]))
jr.close("partial")
check("the pid file SURVIVES a non-clean close -- it is the evidence of a kill",
      jr.pid_path.exists())

print("\n-- reopening the same run RESUMES; it does not restart from zero")
jr2 = pull_journal.PullJournal("t_open", root=ROOT, meta={"start": "2025-01-01", "end": "2025-03-01"})
check("the finished month is still finished after a reopen", jr2.is_done("alpaca", "2025-01"))
check("the partial index survives a reopen", jr2.resume_index("alpaca", "2025-02") == 17)
check("the resume counter increments", jr2.cursor["resumed"] >= 1, str(jr2.cursor["resumed"]))
jr2.open(["python"])
check("a stale pid file is reported, not silently overwritten",
      "stale pid file" in jr2.log_path.read_text(encoding="utf-8"))
jr2.close("complete")
check("a CLEAN close removes the pid file", not jr2.pid_path.exists())

print("\n-- a cursor opened for another window REFUSES rather than mixing two jobs")
try:
    pull_journal.PullJournal("t_open", root=ROOT, meta={"start": "2015-01-01", "end": "2025-03-01"})
    check("a mismatched window is refused", False)
except pull_journal.JournalRefusal as exc:
    check("a mismatched window is refused", True, str(exc)[:70])

print("\n-- a live owner is refused; the refusal names the PID and forbids image-name kills")
jr3 = pull_journal.PullJournal("t_lock", root=ROOT, meta={"start": "2025-01-01", "end": "2025-02-01"})
jr3.open(["python"])
jr3.pid_path.write_text(json.dumps({"pid": os.getpid(), "started_at": "now", "argv": []}),
                        encoding="utf-8")
jr4 = pull_journal.PullJournal("t_lock", root=ROOT, meta={"start": "2025-01-01", "end": "2025-02-01"})
# The lock is against ANOTHER live pid, so the branch needs a real live process
# that is not us. A sleeping child is spawned, its pid is WRITTEN DOWN, and it
# is terminated by that pid -- never by image name, which is the rule this repo
# learned on 2026-09-06 when a kill-by-image ended three other agents' work.
import subprocess                                                      # noqa: E402
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
try:
    check("the spawned child is alive (the lock has something to lock against)",
          pull_journal.pid_alive(child.pid), f"pid {child.pid}")
    jr4.pid_path.write_text(json.dumps({"pid": child.pid, "started_at": "now", "argv": []}),
                            encoding="utf-8")
    try:
        jr4.open(["python"])
        check("a live owner is refused", False)
    except pull_journal.JournalRefusal as exc:
        check("a live owner is refused", True, str(exc)[:60])
        check("the refusal names the pid", str(child.pid) in str(exc))
        check("the refusal forbids killing by image name", "never by image name" in str(exc))
finally:
    child.terminate()                      # by the pid we wrote down, and only that
    child.wait(timeout=10)
check("a DEAD owner does not lock the run out", not pull_journal.pid_alive(child.pid))
jr4.open(["python"])
jr4.close("complete")

print("\n-- find_runs answers 'what is running' from the FILESYSTEM, not a scrollback")
runs = {r["run_id"]: r for r in pull_journal.find_runs(ROOT)}
check("both runs are listed", {"t_open", "t_lock"} <= set(runs))
check("a cleanly closed run says complete", runs["t_open"]["status"] == "complete",
      runs["t_open"]["status"])

print("\n-- the RELATIVE window is refused: --months named a different job every day")
rc = nb.main(["--months", "12", "--universe", "fleet"])
check("--months is refused with an exit code", rc == 2, str(rc))
rc = nb.main(["--universe", "fleet"])
check("a pull with no --start/--end is refused", rc == 2, str(rc))
rc = nb.main(["--start", "2026-03-01", "--end", "2026-01-01", "--universe", "fleet"])
check("an end before the start is refused", rc == 2, str(rc))
rc = nb.main(["--start", "not-a-date", "--end", "2026-01-01"])
check("an unparseable date is refused", rc == 2, str(rc))

print("\n-- --universe tradable REFUSES when the export is absent (no silent 156-name fallback)")
tu.OUT.parent.mkdir(parents=True, exist_ok=True)
if tu.OUT.exists():
    tu.OUT.unlink()
try:
    tu.load()
    check("an absent export refuses", False)
except tu.UniverseRefusal as exc:
    check("an absent export refuses", True)
    check("the refusal names the command that builds it",
          "scripts.tradable_universe" in str(exc), str(exc)[:80])
tu.OUT.write_text(json.dumps({"universe": []}), encoding="utf-8")
try:
    tu.load()
    check("an EMPTY export refuses too", False)
except tu.UniverseRefusal:
    check("an EMPTY export refuses too", True)
tu.OUT.write_text(json.dumps({"universe": ["zzza", "ZZZB"]}), encoding="utf-8")
import argparse                                                        # noqa: E402
ns = argparse.Namespace(symbols=None, murat=False, universe="tradable")
u = nb._universe(ns)
check("the tradable universe is upper-cased", {"ZZZA", "ZZZB"} <= set(u))
check("MURAT_NAMES ride along as the acceptance names", set(nb.MURAT_NAMES) <= set(u))
check("the tradable universe is deduped and sorted", u == sorted(set(u)))

print("\n-- coverage_by_year is computed from RECEIPTS, so it survives the process")
receipts = [{"month": "2025-01", "items_fetched": 10, "seen": {"A": 3, "B": 7}},
            {"month": "2025-02", "items_fetched": 5, "seen": {"A": 5}},
            {"month": "2026-01", "items_fetched": 1, "seen": {"C": 1}}]
cov = nb.coverage_by_year(receipts, ["2025-01", "2025-02", "2025-03", "2026-01"])
check("a year reports months requested vs months with a receipt",
      cov["2025"]["months_requested"] == 3 and cov["2025"]["months_with_receipt"] == 2,
      json.dumps(cov["2025"]))
check("the month fraction is the E3 gate's numerator/denominator",
      abs(cov["2025"]["month_fraction"] - 2 / 3) < 1e-3,
      str(cov["2025"]["month_fraction"]))
check("distinct symbols are unioned across months", cov["2025"]["distinct_symbols"] == 2)
check("a year with every month present reads 1.0", cov["2026"]["month_fraction"] == 1.0)

print("\n-- the month receipt carries what the gate needs, including errors BY STATUS")
r = nb._month_receipt(symbols=10, units=1, items=4, new=4, dup=0,
                      seen={"A": 2, "B": 2}, refusals=["x -> HTTP 429: y"],
                      first="2025-01-02T00:00:00Z", last="2025-01-30T00:00:00Z",
                      pages=3, elapsed=1.5, resumed_at=0)
for k in ("items_fetched", "rows_stored_new", "rows_duplicate", "distinct_symbols",
          "first_observed_at", "last_observed_at", "http_errors", "coverage_fraction"):
    check(f"receipt carries {k}", k in r)
check("http errors are bucketed by status on the receipt", r["http_errors"] == {"429": 1})
check("coverage_fraction is symbols_with_any / symbols_requested", r["coverage_fraction"] == 0.2)


print("")
print("-- a month can be DONE and NOT FULL: the 17-hour DNS outage of 2026-09-07")
jr5 = pull_journal.PullJournal("t_degraded", root=ROOT, meta={"start": "2025-01-01", "end": "2025-04-01"})
jr5.open(["python"])
jr5.complete_month("alpaca", "2025-01", {"items_fetched": 100, "n_refusals": 0,
                                         "http_errors": {}, "seen": {"A": 100}})
jr5.complete_month("alpaca", "2025-02", {"items_fetched": 9, "n_refusals": 124,
                                         "http_errors": {"transport": 124}, "seen": {"A": 9}})
deg = jr5.degraded_months("alpaca")
check("a month with refusals is flagged degraded", deg == [("2025-02", 124)], str(deg))
check("a clean month is NOT flagged", "2025-01" not in [m for m, _ in deg])
check("both months are still marked done until someone acts",
      jr5.is_done("alpaca", "2025-01") and jr5.is_done("alpaca", "2025-02"))
jr5.reopen_month("alpaca", "2025-02")
check("reopening un-marks the month so it is pulled again",
      not jr5.is_done("alpaca", "2025-02"))
check("the clean month is untouched by the reopen", jr5.is_done("alpaca", "2025-01"))
check("the superseded receipt is KEPT, not overwritten",
      (jr5.months_dir / "2025-02.alpaca.superseded-0.json").exists())
check("a superseded receipt is not counted twice",
      [r["month"] for r in jr5.month_receipts("alpaca")] == ["2025-01"],
      str([r["month"] for r in jr5.month_receipts("alpaca")]))
jr5.close("complete")

print("\n-- the batch size is 20, which is what makes a whole-market pull affordable")
check("ALPACA_BATCH is 20", nb.ALPACA_BATCH == 20)
check("THIN floor is still 3", nb.THIN_ITEMS == 3)

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
