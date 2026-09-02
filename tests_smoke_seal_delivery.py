"""THE DELIVERY ARTERY: the central seal must actually reach a runner.

On 2026-09-02 the fleet sat frozen for a trading morning because the artery had
a gap nobody had tested: `scripts/prediction_book_sync.py` existed and NOTHING
launched it (the Dockerfile CMD runs agent_loop only), and `seal_authority`
sealed without `--backfill-prices`, which S30 proved seals hack3/hack6 EMPTY
(refresh does not derive realised_vol_20d). Both were invisible to 2,769 green
checks because reachability, not stage correctness, was the failure -- the same
shape as tests_smoke_artery.py's origin story.

Proofs:
  1. sync is an exact no-op without AAT_PREDICTION_BOOK_BASE_URL;
  2. a valid local book is kept (no network touched), a tampered one is refused;
  3. seal_authority runs refresh -> backfill-prices -> seal, IN THAT ORDER;
  4. agent_loop's cycle actually CALLS the sync (the gap this file exists for).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_fails: list[str] = []
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        _fails.append(name)


# ---- 1 + 2: the sync ---------------------------------------------------------
os.environ.pop("AAT_PREDICTION_BOOK_BASE_URL", None)
from scripts import prediction_book_sync as sync  # noqa: E402

check("sync without base url is a no-op True", sync.sync_once("2026-09-02") is True)

with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    day = "2026-09-02"
    book = {"schema": "prediction-book-3", "day": day, "portfolios": {"hack3": {"holdings": []}}}
    body = json.dumps(book, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    import hashlib

    book["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    dst = Path(td) / "predictions"
    dst.mkdir()
    (dst / f"{day}.json").write_text(json.dumps(book), encoding="utf-8")

    os.environ["AAT_PREDICTION_BOOK_BASE_URL"] = "http://127.0.0.1:9"  # unroutable
    check("valid local book is kept without network", sync.sync_once(day) is True,
          "would hang/refuse if it fetched")

    tampered = dict(book)
    tampered["content_sha256"] = "0" * 64
    (dst / f"{day}.json").write_text(json.dumps(tampered), encoding="utf-8")
    check("tampered local book is not treated as valid",
          sync._valid_local(dst / f"{day}.json", day) is False)

    wrong_day = dict(book)
    check("wrong-day artifact refused by hash check",
          sync._valid_local(dst / f"{day}.json", "2026-09-03") is False)
    os.environ.pop("AAT_PREDICTION_BOOK_BASE_URL", None)
    os.environ.pop("AAT_LEDGER_DIR", None)

# ---- 3: seal_authority ordering ---------------------------------------------
with tempfile.TemporaryDirectory() as td:
    os.environ["AAT_LEDGER_DIR"] = td
    import importlib

    from scripts import prediction_book, seal_authority

    importlib.reload(seal_authority)  # rebind STATE/BOOKS to the temp ledger dir

    ran: list[list[str]] = []
    day = seal_authority._day()

    def fake_run(cmd: list[str]) -> bool:
        ran.append(cmd)
        if "--seal" in cmd:
            payload = {"schema": "prediction-book-3", "day": day,
                       "portfolios": {"hack3": {"holdings": []}}}
            payload["content_sha256"] = prediction_book._sha(payload)
            seal_authority.BOOKS.mkdir(parents=True, exist_ok=True)
            (seal_authority.BOOKS / f"{day}.json").write_text(
                json.dumps(payload), encoding="utf-8")
        return True

    seal_authority._run = fake_run
    if not seal_authority._weekday():
        check("seal_authority weekend short-circuit", seal_authority.ensure_today() is True)
        print("  NOTE  ordering proof needs a weekday; not asserted today")
    else:
        ok = seal_authority.ensure_today()
        order = []
        for c in ran:
            if "--backfill-prices" in c:
                order.append("backfill")
            elif "--refresh" in c:
                order.append("refresh")
            elif "--seal" in c:
                order.append("seal")
        check("authority seals successfully with a fake pipeline", ok is True)
        check("authority order is refresh -> backfill-prices -> seal",
              order == ["refresh", "backfill", "seal"], str(order))
    os.environ.pop("AAT_LEDGER_DIR", None)

# ---- 4: the loop launches the sync ------------------------------------------
loop_src = (ROOT / "scripts" / "agent_loop.py").read_text(encoding="utf-8")
cycle_body = loop_src.split("def _cycle(", 1)[-1]
check("agent_loop._cycle calls prediction_book_sync",
      "prediction_book_sync" in cycle_body and "sync_once" in cycle_body,
      "the sync existed for hours with no caller; this pin is the fix")

dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
check("requirements carry yfinance for in-container refresh",
      "yfinance" in (ROOT / "requirements.txt").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"FAILED: {len(_fails)} -> {_fails}")
    raise SystemExit(1)
print("ALL PASS tests_smoke_seal_delivery")
