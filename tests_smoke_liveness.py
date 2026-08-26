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

print("\n-- writes are atomic and a bad receipt does not crash the reader")
liveness._path("torn").write_text("{ this is not json", encoding="utf-8")
check("an unreadable receipt reads as absent, not as a crash",
      liveness.read("torn") is None)
st, _ = liveness.status("torn", now=NOW)
check("...and classifies UNKNOWN", st == liveness.UNKNOWN)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
