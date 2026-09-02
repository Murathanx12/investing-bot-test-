"""GRADE THE ENTRY-TIMING TOURNAMENT. Run after the close; network allowed.

    python -m scripts.entry_timing_grade --day 2026-09-02
    python -m scripts.entry_timing_grade --day 2026-09-02 --role hack4

THE QUESTION
============
Three books hold the same sealed names at the same sealed weights and differ
only in WHEN the weight went on. So the number that decides the tournament is
not "did hack4 make money" -- all three will move together on the names -- it is
the DIFFERENCE the entry moment made, per name:

    open -> 10:01     what the control paid for waiting (or was paid for it)
    fill vs print     what the auction actually cost us against its own print
    fill -> close     the session return the book actually earned

Computed AFTER the close, from bars, for names the receipt says were submitted.
It never places anything and never edits a receipt's `orders` block: it fills in
`fills` and `grade` beside them, so the pre-open claim and the post-close
measurement stay separable rows in the same file.

A NAME WITH NO FILL IS A RESULT
===============================
An `opg` order that the venue rejected, or that never printed, is recorded as
such rather than dropped. "The auction arm had four names" and "the auction arm
had five names and one did not fill" are different findings, and only one of
them is visible if unfilled names disappear.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


from alpha import config, entry_open, exits
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

log = logging.getLogger("entry_timing_grade")

#: The control arm's entry minute, in ET. The 10:01 pass is the 09:30+31 cadence
#: the loop has always run; this is the price it would have paid.
CONTROL_ET_HHMM = (10, 1)


def _utc_stamp(day: str, hh: int, mm: int) -> str:
    """`day` at ET hh:mm, expressed in UTC, using the repo's single ET offset."""
    from datetime import datetime, timezone
    et = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00+00:00")
    return (et - exits.ET_OFFSET).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _first_bar_at_or_after(bars: list[dict], stamp: str) -> dict | None:
    for b in bars:
        if str(b.get("t") or "") >= stamp:
            return b
    return None


def _session_bars(client, symbols: list[str], day: str) -> dict[str, list[dict]]:
    """One-minute bars for the session. SIP, because IEX volume is not the market."""
    from datetime import date, timedelta as _td
    end = (date.fromisoformat(day) + _td(days=1)).isoformat()
    return client.stock_bars_multi(symbols, start=day, end=end, timeframe="1Min",
                                   adjustment="all", feed="sip")


def _fills_by_client_id(client, day: str) -> dict[str, dict]:
    """Every order the venue closed today, keyed by our client_order_id."""
    after = _utc_stamp(day, 0, 0)
    rows = client._request("GET", "/v2/orders",
                           params={"status": "all", "after": after, "limit": 500}) or []
    return {str(r.get("client_order_id") or ""): r for r in rows if r.get("client_order_id")}


def grade_day(client, day: str, role: str) -> dict:
    receipt_path = entry_open.receipt_path(day, role)
    if not receipt_path.exists():
        return {"day": day, "role": role, "status": "NO RECEIPT",
                "why": f"{receipt_path} does not exist -- this role ran no pre-open pass"}
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    orders = payload.get("orders") or []
    if not orders:
        payload["grade"] = {"status": "NO ORDERS", "n": 0}
        receipt_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload["grade"]

    symbols = sorted({str(o["symbol"]).upper() for o in orders})
    bars = _session_bars(client, symbols, day)
    venue = _fills_by_client_id(client, day)
    control_stamp = _utc_stamp(day, *CONTROL_ET_HHMM)

    rows, fills = [], []
    for o in orders:
        sym = str(o["symbol"]).upper()
        sb = bars.get(sym) or []
        first = sb[0] if sb else None
        auction_print = float(first.get("o") or 0.0) if first else None
        ctl_bar = _first_bar_at_or_after(sb, control_stamp)
        control_px = float(ctl_bar.get("o") or 0.0) if ctl_bar else None
        close_px = float(sb[-1].get("c") or 0.0) if sb else None

        order = venue.get(str(o.get("client_order_id") or ""))
        filled_qty = float((order or {}).get("filled_qty") or 0.0)
        fill_px = float((order or {}).get("filled_avg_price") or 0.0) or None
        status = str((order or {}).get("status") or "NOT FOUND AT VENUE")
        fills.append({"symbol": sym, "client_order_id": o.get("client_order_id"),
                      "status": status, "filled_qty": filled_qty,
                      "filled_avg_price": fill_px,
                      "filled_at": (order or {}).get("filled_at")})

        def _rel(a, b):
            return None if not a or not b or b <= 0 else round(a / b - 1.0, 6)

        rows.append({
            "symbol": sym,
            "auction_print": auction_print,
            "control_price_1001_et": control_px,
            "close": close_px,
            # What waiting until 10:01 would have cost or saved on the entry.
            "open_to_1001": _rel(control_px, auction_print),
            # What our fill cost against the print it was supposed to be.
            "fill_slippage_vs_print": _rel(fill_px, auction_print),
            "fill_to_close": _rel(close_px, fill_px),
            "control_to_close": _rel(close_px, control_px),
            "filled": bool(fill_px),
        })

    got = [r for r in rows if r["filled"]]

    def _mean(key):
        vals = [r[key] for r in got if r.get(key) is not None]
        return round(sum(vals) / len(vals), 6) if vals else None

    grade = {
        "status": "GRADED",
        "day": day, "role": role, "entry_style": payload.get("entry_style"),
        "n_orders": len(orders), "n_filled": len(got),
        "mean_open_to_1001": _mean("open_to_1001"),
        "mean_fill_slippage_vs_print": _mean("fill_slippage_vs_print"),
        "mean_fill_to_close": _mean("fill_to_close"),
        "mean_control_to_close": _mean("control_to_close"),
        # THE TOURNAMENT NUMBER: the auction arm's session return minus the
        # return the 10:01 control would have earned on the same names.
        "mean_edge_vs_control": (
            None if _mean("fill_to_close") is None or _mean("control_to_close") is None
            else round(_mean("fill_to_close") - _mean("control_to_close"), 6)),
        "per_symbol": rows,
    }
    payload["fills"] = fills
    payload["grade"] = grade
    receipt_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return grade


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=None, help="YYYY-MM-DD (default: today's session day)")
    p.add_argument("--role", default=None, help="one role (default: every receipt for the day)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.load_env()
    day = args.day or exits.session_day()

    roles = [args.role.strip().lower()] if args.role else sorted(
        f.stem.split("_", 1)[1] for f in entry_open.state_dir().glob(f"{day}_*.json"))
    if not roles:
        print(f"no entry-timing receipts for {day}")
        return 0
    client = AlpacaPaper()
    bad = 0
    for role in roles:
        try:
            g = grade_day(client, day, role)
        except BrokerRefusal as exc:
            print(f"  {role}: REFUSED {exc}")
            bad += 1
            continue
        print(f"  {role:<8} {g.get('status')}  style={g.get('entry_style')}  "
              f"filled {g.get('n_filled')}/{g.get('n_orders')}  "
              f"open->10:01 {g.get('mean_open_to_1001')}  "
              f"slippage {g.get('mean_fill_slippage_vs_print')}  "
              f"edge vs control {g.get('mean_edge_vs_control')}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
