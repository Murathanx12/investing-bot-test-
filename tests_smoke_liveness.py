"""LOOP_LIVENESS_v1: a stopped loop must not read like a quiet market."""
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import liveness

liveness.BEAT_DIR = Path(tempfile.mkdtemp())
NOW = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)


def at(**kw):
    return NOW + timedelta(**kw)


print("\n-- the PID probe, proven against a known-alive AND a known-dead process")
# The whole guard rests on this one primitive, and the obvious implementation is
# wrong here: os.kill(pid, 0) reports a killed-and-reaped process as ALIVE on
# Windows, and Git Bash `kill -0` cannot see native Windows PIDs at all. Both
# fail toward "healthy", which is the direction that certifies a dead loop.
# So it is measured, not assumed. A check that did not run is not a check that
# passed.
proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
time.sleep(1.5)
check("a KNOWN-ALIVE process reads alive", liveness.pid_alive(proc.pid) is True,
      f"pid {proc.pid}")
proc.kill()
proc.wait()
time.sleep(1.0)
check("a KNOWN-DEAD process reads dead", liveness.pid_alive(proc.pid) is False,
      f"pid {proc.pid} (os.kill would say ALIVE here)")
check("a never-existed pid reads dead", liveness.pid_alive(999_999) is False)
check("pid 0 is not 'alive'", liveness.pid_alive(0) is False)

print("\n-- no receipt is UNKNOWN, and UNKNOWN is not health")
st, why = liveness.status("dev", now=NOW)
check("a role with no heartbeat is UNKNOWN", st == liveness.UNKNOWN, why[:60])
check("...and it says CANNOT DETERMINE rather than implying health",
      "CANNOT DETERMINE" in why)
# The scan is injected, never read from the real machine: letting it read the
# actual process table would make this verdict depend on whatever happens to be
# running here, which is the ambient-environment defect that made two other
# tests in this suite pass for the wrong reason.
ok, _ = liveness.report(("dev",), now=NOW, scan=(0, []))
check("no receipt AND no loop processes fails the report", not ok)

print("\n-- a live, cycling loop is HEALTHY")
beat = liveness.Beat(role="dev", pid=__import__("os").getpid(), cycle=7, expiry="2026-09-04",
                     live=True, started_utc=at(seconds=-70).isoformat(),
                     completed_utc=at(seconds=-65).isoformat())
liveness.write(beat)
st, why = liveness.status("dev", now=NOW)
check("cycling recently -> HEALTHY", st == liveness.HEALTHY, why[:70])
check("the receipt names the cycle and the expiry",
      "cycle 7" in why and "2026-09-04" in why, why[:70])

print("\n-- the loop dies: DEAD, and it says the log stopping did not say so")
dead = liveness.Beat(role="exp1", pid=999_999, cycle=12,
                     completed_utc=at(seconds=-90).isoformat(),
                     last_error="URLError: [Errno 11001] getaddrinfo failed")
liveness.write(dead)
st, why = liveness.status("exp1", now=NOW)
check("a gone pid -> DEAD", st == liveness.DEAD, why[:70])
check("...and the last error is carried into the verdict",
      "getaddrinfo" in why, why[-60:])

print("\n-- alive but not cycling: STALE. A live process is not a working loop.")
hung = liveness.Beat(role="hung", pid=__import__("os").getpid(), cycle=3,
                     started_utc=at(seconds=-4000).isoformat(),
                     completed_utc=at(seconds=-3600).isoformat())
liveness.write(hung)
st, why = liveness.status("hung", now=NOW)
check("no completed cycle past the ceiling -> STALE", st == liveness.STALE, why[:70])
# The ceiling must exceed the longest job the loop may legitimately be running,
# or a normal 25-minute entry pass reads as a hang.
check("the ceiling clears run_pass's own 1500s timeout",
      liveness.STALE_AFTER_S > 1500, str(liveness.STALE_AFTER_S))
st_ok, _ = liveness.status("hung", now=NOW, stale_after_s=7200)
check("...and a wider ceiling clears it", st_ok == liveness.HEALTHY)

never = liveness.Beat(role="never", pid=__import__("os").getpid(),
                      started_utc=at(seconds=-30).isoformat())
liveness.write(never)
st, why = liveness.status("never", now=NOW)
check("started but never completed a cycle -> STALE", st == liveness.STALE, why[:60])

print("\n-- backing off after errors: DEGRADED, not silently HEALTHY")
deg = liveness.Beat(role="deg", pid=__import__("os").getpid(), cycle=4,
                    completed_utc=at(seconds=-40).isoformat(),
                    consecutive_errors=3, last_error="BrokerRefusal: transport failure",
                    backoff_until_utc=at(seconds=+60).isoformat())
liveness.write(deg)
st, why = liveness.status("deg", now=NOW)
check("errors + backoff -> DEGRADED", st == liveness.DEGRADED, why[:70])
check("the error count is in the verdict", "3 consecutive error" in why, why[:70])

print("\n-- PRE-BEAT: loops that predate the heartbeat are not a false alarm")
# A loop started before the heartbeat existed cannot emit one until it restarts.
# Calling that UNKNOWN-and-red would print a red line every render that no
# action available today can clear -- the defect this project has now paid for
# three times (the ledger chain warning, monday_gate_check, and this).
ok_pre, pre = liveness.report(("a", "b"), now=NOW, scan=(2, ["-m scripts.agent_loop --live",
                                                            "-m scripts.agent_loop --live"]))
check("no receipts + enough loop processes -> PRE-BEAT, and it passes", ok_pre,
      str([l[:18] for l in pre]))
check("...and it is never called HEALTHY",
      all(liveness.HEALTHY not in l for l in pre if l.startswith(("a ", "b "))))
check("...and it says role attribution is what is missing",
      any("account role" in l for l in pre))
ok_none, _ = liveness.report(("a", "b"), now=NOW, scan=(0, []))
check("ZERO loop processes is decisive whatever the receipts say", not ok_none)
ok_unread, unread = liveness.report(("a",), now=NOW, scan=None)
check("an unreadable process table fails rather than assuming", not ok_unread)

print("\n-- an EXPECTED role that has no receipt is still reported")
ok, lines = liveness.report(("dev", "exp1", "ghost"), now=NOW, scan=(2, ["agent_loop", "agent_loop"]))
check("a role we expected but never saw is named", any(l.startswith("ghost") for l in lines),
      str([l[:22] for l in lines]))
check("the report fails when any role is unhealthy", not ok)

print("\n-- the independent check: count the processes, do not trust the receipt alone")
scanned = liveness.scan_processes()
check("the process table is readable", scanned is not None)
if scanned is not None:
    n, cmds = scanned
    check("scanning finds the running agent_loops (or honestly reports none)",
          isinstance(n, int) and n == len(cmds), f"{n} found")
check("a receipt-only report still runs the scan",
      any(l.startswith("scan") for l in lines), str([l[:8] for l in lines]))

print("\n-- defect 4: the entry pass must not be allowed to starve exits")
import importlib
al = importlib.import_module("scripts.agent_loop")
# The old ceiling was 1500s -- a safety net someone typed, which I quoted in a
# handoff as though it described behaviour. Ten measured entry passes: median
# 368s, p90 and max 439s. The ceiling was 3.4x the worst pass ever seen, and it
# bought that headroom with a 25-minute worst-case exit delay.
check("the entry-pass ceiling is bounded by what was MEASURED, not by a safety net",
      al.TIMEOUTS_S["scripts.run_pass"] <= 900, str(al.TIMEOUTS_S["scripts.run_pass"]))
check("...and still clears the worst pass ever observed (439s) with margin",
      al.TIMEOUTS_S["scripts.run_pass"] >= 550, str(al.TIMEOUTS_S["scripts.run_pass"]))
check("exits are never given a LONGER ceiling than entries",
      al.TIMEOUTS_S["scripts.manage"] <= al.TIMEOUTS_S["scripts.run_pass"])
src = open(al.__file__, encoding="utf-8").read()
check("an exit pass runs IMMEDIATELY after an entry pass, not on the next tick",
      "EXITS IMMEDIATELY AFTER" in src and 'last["exit"] = time.time()' in src)
check("...and it re-reads the clock rather than trusting the stale cycle-start time",
      "_market_open(client)" in src)
check("an unreadable clock skips the extra exit rather than assuming open",
      "return False" in src.split("def _market_open")[1].split("\ndef ")[0])

print("\n-- writes are atomic and a bad receipt does not crash the reader")
liveness._path("torn").write_text("{ this is not json", encoding="utf-8")
check("an unreadable receipt reads as absent, not as a crash",
      liveness.read("torn") is None)
st, _ = liveness.status("torn", now=NOW)
check("...and classifies UNKNOWN", st == liveness.UNKNOWN)

print("\n-- a REFUSING sub-step must not read like a quiet market either")
# The loop can cycle perfectly while the step that places orders exits 2 on every
# pass: a bad --expiry, an unverified genesis, a missing window universe. `_run`
# returns an exit code and every caller discards it, so from the loop's point of
# view nothing is wrong and the heartbeat said HEALTHY throughout. That is the
# same shape as the dead loops on 26 Aug, one layer down.
import os                                                            # noqa: E402

_pid = os.getpid()
liveness.write(liveness.Beat(role="refusing", pid=_pid, cycle=40,
                             completed_utc=at(seconds=-30).isoformat(),
                             started_utc=at(seconds=-60).isoformat(),
                             live=True, failing_steps={"scripts.run_pass": 6}))
_st, _why = liveness.status("refusing", now=NOW)
check("a loop whose entry pass keeps failing is DEGRADED, not HEALTHY",
      _st == liveness.DEGRADED, f"{_st}: {_why[:130]}")
check("  and the message names the step and the count",
      "scripts.run_pass" in _why and "x6" in _why, _why[:160])
check("  and says the loop is fine while the WORK is not happening",
      "work is not happening" in _why, _why[:160])

liveness.write(liveness.Beat(role="working", pid=_pid, cycle=40,
                             completed_utc=at(seconds=-30).isoformat(),
                             started_utc=at(seconds=-60).isoformat(),
                             live=True, failing_steps={}))
_st2, _ = liveness.status("working", now=NOW)
check("a loop with no failing steps is still HEALTHY", _st2 == liveness.HEALTHY, _st2)

_b = liveness.read("refusing")
check("failing_steps survives the write/read round trip",
      _b is not None and _b.failing_steps == {"scripts.run_pass": 6},
      str(getattr(_b, "failing_steps", None)))

_src = Path("scripts/agent_loop.py").read_text(encoding="utf-8")
check("_run counts consecutive non-zero exits", "_consecutive_failures" in _src)
check("  and shouts after a threshold rather than on the first blip",
      "NOISY_AFTER" in _src and "HAS EXITED NON-ZERO" in _src,
      "one failure is usually a transient venue refusal")
check("  and resets on recovery", "recovered after" in _src)
check("the loop publishes them on the heartbeat",
      "beat.failing_steps = failing_steps()" in _src)

# --- NO STEP MAY BYPASS THE FAILURE COUNTER --------------------------------
# Three steps called subprocess.call directly, so their exit codes reached
# nobody: not the counter, not the heartbeat, not the log. One of them --
# belief_vs_chain_grade -- had been crashing on EVERY cycle since its first
# success, because it writes GRADES.json into the directory it globs and then
# reads its own output back as an input. It failed silently for as long as it
# had existed.
import ast as _ast                                                   # noqa: E402

_loop_src = Path("scripts/agent_loop.py").read_text(encoding="utf-8")
_tree = _ast.parse(_loop_src)
# `_run` itself must call subprocess -- it is the wrapper. Everything ELSE must
# go through it, so the scan excludes _run's own body.
_run_body = next((n for n in _tree.body
                  if isinstance(n, _ast.FunctionDef) and n.name == "_run"), None)
_run_lines = set(range(_run_body.lineno, (_run_body.end_lineno or _run_body.lineno) + 1))     if _run_body else set()
_direct = []
for _n in _ast.walk(_tree):
    if not isinstance(_n, _ast.Call):
        continue
    _f = _n.func
    if isinstance(_f, _ast.Attribute) and _f.attr == "call"             and isinstance(_f.value, _ast.Name) and _f.value.id == "subprocess"             and getattr(_n, "lineno", 0) not in _run_lines:
        _direct.append(getattr(_n, "lineno", "?"))
check("only _run may call subprocess; no step bypasses it", not _direct,
      f"lines {_direct} -- their exit codes reach no counter and no heartbeat")
check("  and _run really is the one wrapper", _run_body is not None)
check("every step goes through _run", _loop_src.count("_run(") >= 8)

_g = Path("scripts/belief_vs_chain_grade.py").read_text(encoding="utf-8")
check("the grader excludes its own output from its inputs",
      "OUTPUT_NAME" in _g and "not f.endswith(OUTPUT_NAME)" in _g,
      "it writes GRADES.json into the directory it globs")
check("  and says so where the next reader will hit it",
      "dead since its first success" in _g)
check("a malformed reading is SKIPPED with a reason, not fatal",
      "SKIP" in _g and "must not cost the other" in _g,
      "one bad file was costing the other 97")

# --- retire(): a DELIBERATE single cycle must not leave a DEAD receipt -----
# `agent_loop --once` on pead wrote a heartbeat and exited correctly, and the
# next report said "pead DEAD -- the loop is gone", a false alarm produced by a
# healthy act and printed beside two real HEALTHY lines.
liveness.write(liveness.Beat(role="oneshot", pid=_pid, cycle=1,
                             completed_utc=at(seconds=-10).isoformat()))
check("a receipt exists before retiring", liveness.read("oneshot") is not None)
check("retire() removes it and says it did", liveness.retire("oneshot") is True)
check("  and it is gone", liveness.read("oneshot") is None)
check("  and retiring again is idempotent, not an error",
      liveness.retire("oneshot") is False)
check("--once retires its own receipt",
      "liveness.retire(role)" in _loop_src,
      "a single deliberate cycle is a diagnostic, not a loop")
_i_once, _i_ret = _loop_src.find("if args.once:"), _loop_src.find("liveness.retire(role)")
check("  and it does so BEFORE returning", -1 < _i_once < _i_ret,
      f"{_i_once} vs {_i_ret}")
check("  and retire() refuses to be used for a crash",
      "NOT for a crash" in Path("alpha/liveness.py").read_text(encoding="utf-8"),
      "a missing receipt and a stale one mean different things")

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
