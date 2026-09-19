"""The sealed-book poller, as a file (2026-09-20).

    python -m scripts.seal_sync_poll            # forever, every 120 s
    python -m scripts.seal_sync_poll --once     # one attempt, exit 0 either way

WHERE THIS CAME FROM
====================
Until 2026-09-20 this logic lived ONLY in the Railway dashboard, as a Custom
Start Command on `aat-loop-hack3`, `hack4` and `hack6`: a `sh -c` line that
ran this exact `python -c` one-liner in a background loop and then `exec`'d
`scripts.agent_loop`. It was invisible from the repository, it bypassed the
Dockerfile's CMD (which is why the market-window wrapper of the same day
booted on hack1 and hack5 and not on the other three), and a start command
that lives in a dashboard field is a birth certificate that only exists on
one website. It is now this module, started by `scripts/market_window.sh`
inside the window when `AAT_PREDICTION_BOOK_BASE_URL` is set, and the
dashboard field is cleared so the Dockerfile is the whole truth.

WHAT IT DOES, unchanged from the one-liner
==========================================
Every 120 s: ask the seal authority for TODAY's session book
(`<base>/<day>.json`), verify it exactly the way the authority does (size cap,
`day` matches, a `portfolios` block, `content_sha256` over the canonical
serialisation), and install it atomically at
`$AAT_LEDGER_DIR/predictions/<day>.json`. A missing book (a 404 on a weekend,
or before the authority has sealed) is logged as `SEAL SYNC waiting` and is not
an error: no sealed book means no trade, by design (README).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

MAX_BYTES = 8_388_608
PERIOD_S = 120.0


def sync_once() -> bool:
    from alpha import exits
    d = exits.session_day()
    p = pathlib.Path(os.getenv("AAT_LEDGER_DIR") or "state") / "predictions" / f"{d}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    base = os.environ["AAT_PREDICTION_BOOK_BASE_URL"].rstrip("/")
    url = f"{base}/{d}.json"
    try:
        raw = urllib.request.urlopen(url, timeout=12).read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError) as exc:
        print(f"SEAL SYNC waiting day={d} url={url}: {exc}", flush=True)
        return False
    x = json.loads(raw.decode("utf-8"))
    claimed = x.pop("content_sha256", None)
    actual = hashlib.sha256(json.dumps(
        x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if not (len(raw) <= MAX_BYTES and x.get("day") == d and x.get("portfolios") and claimed == actual):
        print(f"SEAL SYNC refused day={d}: size={len(raw)} day_ok={x.get('day') == d} "
              f"portfolios={bool(x.get('portfolios'))} hash_ok={claimed == actual}", flush=True)
        return False
    tmp = p.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, p)
    print(f"SEAL SYNC installed {d} {actual[:16]}", flush=True)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seal_sync_poll")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--period", type=float, default=PERIOD_S)
    a = ap.parse_args(argv)
    if "AAT_PREDICTION_BOOK_BASE_URL" not in os.environ:
        print("SEAL SYNC not configured: AAT_PREDICTION_BOOK_BASE_URL is unset; nothing to poll",
              flush=True)
        return 0
    while True:
        try:
            sync_once()
        except Exception as exc:  # noqa: BLE001 -- the poller must outlive one bad response
            print(f"SEAL SYNC error: {type(exc).__name__}: {exc}", flush=True)
        if a.once:
            return 0
        time.sleep(a.period)


if __name__ == "__main__":
    sys.exit(main())
