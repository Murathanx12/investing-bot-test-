"""ONE command that checks the whole estate and refuses to lie about any of it.

    python -m scripts.fleet_health              # everything local + venue + website
    python -m scripts.fleet_health --railway    # + Railway service status (slower)

WHY (Murat, 2026-09-02): "make an easier command to check all works... if one
fails the project should not collapse." Every check here is independent: a
failure is COLLECTED, never fatal to the sweep. And a check that cannot run
reports CANNOT_DETERMINE -- house canon: a guard DERIVES its inputs or REFUSES;
a green line that merely means "did not look" teaches the reader to skim.

WHAT ALREADY FAILS CLOSED (the fail-safes this command watches, not replaces):
- tracker books REFUSE to trade without today's sealed, hash-verified book;
- execution_authority authorises NOTHING on unknown liquidity;
- prediction_book_sync refuses any artifact whose hash or day mismatches;
- protective STOPS rest at the BROKER: they execute even if every service of
  ours is down -- the broker is the backstop of last resort;
- scripts/flatten.py is the attended go-to-zero command when nothing else is
  trustworthy.

READ-ONLY. Places nothing, cancels nothing, writes nothing but stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")
SEALED_ROLES = ("hack3", "hack4", "hack6")
WEBSITE = "https://aegis-finance-production.up.railway.app/api/health/full"

OK, FAIL, CANNOT = "ok  ", "FAIL", "????"


class Sweep:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, note: str = "") -> None:
        # A Windows cp1252 console must not crash on Railway's status glyphs.
        note = note.encode("ascii", "replace").decode("ascii")
        self.rows.append((status, name, note))
        print(f"  {status}  {name}" + (f"  ({note})" if note else ""), flush=True)

    @property
    def failed(self) -> list[str]:
        return [n for s, n, _ in self.rows if s == FAIL]

    @property
    def unknown(self) -> list[str]:
        return [n for s, n, _ in self.rows if s == CANNOT]


def check_venue_and_roles(s: Sweep) -> None:
    try:
        from alpha import config
        config.load_env()
        from alpha.broker.alpaca import AlpacaPaper
    except Exception as exc:  # noqa: BLE001
        s.add(CANNOT, "broker layer importable", str(exc))
        return
    clock = None
    for role in ROLES:
        try:
            b = AlpacaPaper(role)
            if clock is None:
                clock = b.clock()
                s.add(OK, "venue clock",
                      f"open={clock.get('is_open')} next_open={str(clock.get('next_open'))[:16]}")
            a = b.account()
            blocked = a.get("trading_blocked") or a.get("account_blocked")
            npos = len(b.positions())
            nord = len(b.orders())
            status = FAIL if blocked else OK
            s.add(status, f"{role} account",
                  f"equity {float(a.get('equity') or 0):,.0f}  pos {npos}  open_orders {nord}"
                  + ("  TRADING BLOCKED" if blocked else ""))
        except Exception as exc:  # noqa: BLE001
            s.add(FAIL, f"{role} account", str(exc)[:90])


def check_seal(s: Sweep) -> None:
    """Today's book: local, published, and hash-true. A missing pre-open seal is
    the single failure that froze the fleet on 2026-09-02."""
    try:
        from zoneinfo import ZoneInfo
        day = datetime.now(ZoneInfo("America/New_York")).date()
        weekday = day.weekday() < 5
        day = day.isoformat()
    except Exception as exc:  # noqa: BLE001
        s.add(CANNOT, "ET day derivable", str(exc))
        return
    if not weekday:
        s.add(OK, "sealed book", f"{day} is a weekend; no seal required")
        return
    try:
        from scripts import prediction_book
    except Exception as exc:  # noqa: BLE001
        s.add(CANNOT, "prediction_book importable", str(exc))
        return
    for label, path in (("local seal", ROOT / "state" / "predictions" / f"{day}.json"),
                        ("published seal", ROOT / "docs" / "seed" / "predictions" / f"{day}.json")):
        if not path.exists():
            s.add(FAIL, f"{label} {day}", "MISSING -- runners will (correctly) decline everything")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            claimed = payload.pop("content_sha256", None)
            actual = prediction_book._sha(payload)
            if claimed != actual:
                s.add(FAIL, f"{label} {day}", "HASH MISMATCH -- tampered or truncated")
            else:
                books = {k: (v.get("n_selected"), len(v.get("holdings") or []))
                         for k, v in (payload.get("portfolios") or {}).items()}
                s.add(OK, f"{label} {day}", f"sha {actual[:10]} books {books}")
        except (OSError, ValueError) as exc:
            s.add(FAIL, f"{label} {day}", str(exc)[:90])


def check_freshness(s: Sweep) -> None:
    now = datetime.now(timezone.utc)
    tracker_dir = ROOT / "state" / "tracker"
    days = sorted(tracker_dir.glob("2*.jsonl")) if tracker_dir.exists() else []
    if not days:
        s.add(FAIL, "tracker day files", "none exist")
    else:
        latest = days[-1]
        age_h = (now.timestamp() - latest.stat().st_mtime) / 3600
        n = sum(1 for _ in latest.open(encoding="utf-8"))
        s.add(OK if age_h < 36 else FAIL, "tracker freshness",
              f"{latest.name} rows {n} age {age_h:.1f}h")
    wl = ROOT / "state" / "research" / "ownership" / "attention_watchlist.json"
    if not wl.exists():
        s.add(FAIL, "attention watchlist", "missing -- ownership_watch never ran here")
    else:
        try:
            w = json.loads(wl.read_text(encoding="utf-8"))
            s.add(OK, "attention watchlist",
                  f"{w.get('n_symbols')} symbols as_of {w.get('as_of')} "
                  f"(pre-cap {w.get('n_symbols_before_cap')})")
        except (OSError, ValueError) as exc:
            s.add(FAIL, "attention watchlist", str(exc)[:90])


def check_website(s: Sweep) -> None:
    last_exc: Exception | None = None
    for _ in range(2):  # one retry: a chunked-read hiccup is not an outage
        try:
            with urllib.request.urlopen(WEBSITE, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            status = d.get("status")
            reasons = d.get("degraded_reasons") or []
            s.add(OK if status == "ok" else FAIL, "website /api/health/full",
                  f"{status} {reasons if reasons else ''}".strip())
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    # Could not READ it twice; that is "cannot determine", not "down" -- a
    # separate uptime probe would be the down/up authority.
    s.add(CANNOT, "website /api/health/full", str(last_exc)[:90])


def check_railway(s: Sweep) -> None:
    import shutil
    railway = shutil.which("railway") or shutil.which("railway.cmd")
    if not railway:
        s.add(CANNOT, "railway CLI", "not on PATH for this interpreter")
        return
    services = [f"aat-loop-{r}" for r in ROLES] + ["seal-authority"]
    for svc in services:
        try:
            subprocess.run([railway, "service", svc], cwd=ROOT, capture_output=True,
                           timeout=30, check=False)
            r = subprocess.run([railway, "status"], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=30, check=False)
            line = next((ln.strip() for ln in r.stdout.splitlines() if "status:" in ln), "")
            healthy = "Online" in line and "failed" not in line.lower()
            # seal-authority is allowed to be offline while it is shadow-only
            if svc == "seal-authority" and "Offline" in line:
                s.add(OK, f"railway {svc}", "offline (shadow mode, deliberate)")
            else:
                s.add(OK if healthy else FAIL, f"railway {svc}", line.replace("status:", "").strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            s.add(CANNOT, f"railway {svc}", str(exc)[:70])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--railway", action="store_true", help="also query Railway per service (slow)")
    a = ap.parse_args()
    s = Sweep()
    print(f"FLEET HEALTH  {datetime.now(timezone.utc).isoformat()[:19]}Z")
    check_venue_and_roles(s)
    check_seal(s)
    check_freshness(s)
    check_website(s)
    if a.railway:
        check_railway(s)
    print()
    n = len(s.rows)
    if s.failed:
        print(f"{len(s.failed)}/{n} FAILED: {s.failed}")
    if s.unknown:
        print(f"{len(s.unknown)}/{n} CANNOT DETERMINE: {s.unknown}")
    if not s.failed and not s.unknown:
        print(f"ALL GREEN ({n} checks)")
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())
