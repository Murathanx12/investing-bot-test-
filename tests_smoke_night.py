"""Night/day boundary: every scripts/night_*.py stays off the execution surface."""
import subprocess
import sys

fails: list[str] = []


def check(name: str, cond: bool, why: str = "") -> None:
    # The shared `  ok   <name>` convention, not a bare "PASS" line. run_tests.py
    # counts assertions by that convention, and this file used to print its own
    # wording -- so the runner scored it 0 checks and reported it as a suite that
    # asserted nothing. It was asserting; it was invisible, which is worse.
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("night guard")
r = subprocess.run([sys.executable, "-m", "scripts.night_guard"],
                   capture_output=True, text=True, timeout=300)
check("no scripts/night_*.py touches the execution surface", r.returncode == 0,
      (r.stdout + r.stderr).strip()[-400:])

print("\n1 check")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
