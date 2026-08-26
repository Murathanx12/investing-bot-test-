"""Night/day boundary: every scripts/night_*.py stays off the execution surface."""
import subprocess, sys

def test_night_guard_static():
    r = subprocess.run([sys.executable, "-m", "scripts.night_guard"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout

if __name__ == "__main__":
    test_night_guard_static(); print("night guard: PASS")
