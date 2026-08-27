"""The suite cannot reach the network -- proven in a CHILD process, not just here.

The 2026-08-27 leak was not a test that called the venue. It was a test that
stubbed the function it expected to call the venue, and then spawned a child
that called it anyway. A check confined to this process would have passed while
the bug was live, so the subprocess case is the only one that settles it.

Check 3 is a regression test on MY OWN first fix, not on the original bug: that
fix refused inside `credentials()` and broke two suites which plant FAKE keys so
they can exercise role logic offline. A fake key cannot reach a venue. The block
belongs at the socket, and this pins that it stayed there.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from alpha import config

fails: list[str] = []
ROOT = Path(__file__).parent


def check(name: str, cond: bool, why: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("test isolation")
under_runner = config.test_mode()
print(f"  ({'under run_tests.py' if under_runner else 'run directly -- installing the block'})")
os.environ[config.TEST_MODE_ENV] = "1"
config._install_network_block()

# --- 1. an outbound connection is refused -----------------------------------
try:
    socket.create_connection(("data.alpaca.markets", 443), timeout=5)
    check("outbound connection refused", False, "it CONNECTED")
except config.NetworkRefusal as e:
    # the message names an IP, not the host: create_connection resolves the
    # name FIRST and hands connect() an address tuple. So DNS does leave the
    # machine; application data does not, which is the property being claimed.
    check("outbound connection refused", "refusing an outbound connection" in str(e))
except Exception as e:  # noqa: BLE001 -- any other error is the wrong reason
    check("outbound connection refused", False, f"blocked, but by {type(e).__name__}: {e}")

# --- 2. urllib goes through the same door -----------------------------------
import urllib.error
import urllib.request

try:
    urllib.request.urlopen("https://paper-api.alpaca.markets/v2/account", timeout=5)
    check("urllib is blocked too", False, "it CONNECTED")
except config.NetworkRefusal:
    check("urllib is blocked too", True)
except urllib.error.URLError as e:
    check("urllib is blocked too", isinstance(e.reason, config.NetworkRefusal),
          f"URLError for another reason: {e.reason!r}")
except Exception as e:  # noqa: BLE001
    check("urllib is blocked too", False, f"{type(e).__name__}: {e}")

# --- 3. REGRESSION on the first fix: fake credentials still resolve ---------
for k, v in (("AAT_DEV_KEY_ID", "k"), ("AAT_DEV_SECRET_KEY", "s")):
    os.environ[k] = v
check("a planted FAKE credential still resolves under test mode",
      config.credentials("dev").role == "dev",
      "the block moved back onto credentials() and offline role tests break again")

# --- 4. loopback stays open -- blocking it protects nothing -----------------
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(1)
try:
    socket.create_connection(srv.getsockname(), timeout=5).close()
    check("loopback is still allowed", True)
except Exception as e:  # noqa: BLE001
    check("loopback is still allowed", False, f"{type(e).__name__}: {e}")
finally:
    srv.close()

# --- 5. THE ONE THAT MATTERS: a child process inherits the block ------------
child = subprocess.run(
    [sys.executable, "-c",
     "import socket\n"
     "from alpha import config\n"
     "try:\n"
     "    socket.create_connection(('data.alpaca.markets', 443), timeout=5); print('CONNECTED')\n"
     "except config.NetworkRefusal:\n"
     "    print('REFUSED')\n"
     "except Exception as e:\n"
     "    print('OTHER:' + type(e).__name__)\n"],
    cwd=ROOT, env={**os.environ, config.TEST_MODE_ENV: "1"},
    capture_output=True, text=True, timeout=120)
check("child process inherits the block", child.stdout.strip() == "REFUSED",
      f"child said {child.stdout.strip()!r} {child.stderr.strip()[:200]}")

# --- 6. and the block is what stops it, not a dead network -----------------
# Without the flag the same child must NOT be refused for our reason. Whether it
# connects depends on the machine's link, which is not ours to assert; what must
# not happen is our refusal firing when nobody asked for it.
loose = subprocess.run(
    [sys.executable, "-c",
     "import socket\n"
     "from alpha import config\n"
     "try:\n"
     "    socket.create_connection(('data.alpaca.markets', 443), timeout=8); print('CONNECTED')\n"
     "except config.NetworkRefusal:\n"
     "    print('REFUSED_BY_US')\n"
     "except Exception as e:\n"
     "    print('OTHER:' + type(e).__name__)\n"],
    cwd=ROOT, env={k: v for k, v in os.environ.items() if k != config.TEST_MODE_ENV},
    capture_output=True, text=True, timeout=120)
check("without the flag our refusal does not fire", loose.stdout.strip() != "REFUSED_BY_US",
      f"the block is on even unset: {loose.stdout.strip()!r}")

# --- 7. the runner sets it, so nobody has to remember ----------------------
src = (ROOT / "run_tests.py").read_text(encoding="utf-8")
check("run_tests.py sets the guard", 'env["AAT_TEST_MODE"] = "1"' in src)
check("run_tests.py can be opted out of deliberately", "--allow-venue" in src)
check("opting out is announced, not silent", "VENUE ALLOWED" in src)

# --- 8. no suite quietly re-enables the network ---------------------------
offenders = [p.name for p in ROOT.glob("tests_smoke*.py")
             if p.name != Path(__file__).name
             and "AAT_TEST_MODE" in p.read_text(encoding="utf-8")]
check("no other suite touches the guard", not offenders, f"{offenders}")

if not under_runner:
    os.environ.pop(config.TEST_MODE_ENV, None)
print("\n11 checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
