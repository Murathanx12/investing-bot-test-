"""EXPIRY DAY IS EXIT-ONLY (red-team R1, 2026-09-02).

The 10:45 ET deadline liquidation flattens the book; before this guard the
11:00 entry pass re-bought it (~9 round trips of the judged session). run_pass
now refuses every entry when the pass's expiry IS today, before touching the
venue -- so this suite needs no broker at all.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

_fails: list[str] = []


def check(name, ok, note=""):
    print(f"  {'ok ' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


os.environ["AAT_LEDGER_DIR"] = tempfile.mkdtemp()
from alpha import runner
from alpha.brains.base import Forecast


class _NeverCalled:
    def __getattr__(self, name):
        raise AssertionError(f"expiry-day pass touched the venue via .{name}")


f = Forecast("tracker_portfolio", "ABAT", 2.0, 0.01, 0.03, 1.0, "", None,
             {"last_close": 2.6, "sealed_notional": 0.10}, claim="direction")
from alpha import exits as _ex
today = _ex.now_et().date().isoformat()
res = runner.run_pass(_NeverCalled(), [f], expiry=today, dry_run=True)
check("expiry-day pass returns without touching the venue", True)
check("  and submits nothing", not getattr(res, "submitted", []) and not getattr(res, "orders", []),
      str(vars(res))[:80])

tomorrow = (_ex.now_et() + timedelta(days=1)).date().isoformat()
try:
    runner.run_pass(_NeverCalled(), [], expiry=tomorrow, dry_run=True)
    check("an ordinary session DOES touch the venue (guard is expiry-day only)", False)
except AssertionError as exc:
    check("an ordinary session DOES touch the venue (guard is expiry-day only)",
          "touched the venue" in str(exc))

print()
if _fails:
    print(f"FAILED: {_fails}")
    raise SystemExit(1)
print("ALL PASS tests_smoke_expiry_day")
