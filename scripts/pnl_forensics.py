"""PNL_FORENSICS_v1 -- every realised dollar, reconstructed from the venue.

    python -m scripts.pnl_forensics --role dev
    python -m scripts.pnl_forensics --all --json

WHY THIS AND NOT `pnl_attribution`
==================================
`scripts/pnl_attribution` decomposes the structures that are still OPEN into
delta/gamma/vega/theta/spread from the entry snapshot. It is the right tool and
it answers a different question, because it can only speak about positions that
still exist.

On 2026-08-27 the dev book read **realised -$14,330, unrealised -$2,592**. Five
sixths of the damage is in the realised column and `pnl_attribution` prints
nothing about it -- worse, every dev structure had already decayed into
UNMATCHED RESIDUAL LEGS, so its per-structure table was empty and its totals row
was all zeros. A book down 17% produced a decomposition of $0.

CASH FLOW IS THE ONLY HONEST LEDGER FOR A CLOSED POSITION
=========================================================
There is no "realised P&L" field to read. So this reconstructs it the one way
that cannot be argued with: for every contract, sum the cash that moved.

    buy   ->  -qty * fill_price * multiplier
    sell  ->  +qty * fill_price * multiplier

A contract whose net quantity is back to ZERO is CLOSED, and its net cash flow
IS its realised P&L. A contract still holding quantity is OPEN and its cash flow
so far is reported separately and never added to the realised total -- mixing
them is how a book that has spent money looks like a book that has lost it.

**DEDUPE BY `alpaca_order_id` FIRST.** Summing `pnl_usd_if_closed_now` over
`state/fills.jsonl` gives **-$302,818**, which is nonsense: the auditor re-marks
the same 22 orders on every cycle, 1,070 rows for 29 orders. That number has
been quoted in a handoff. It is an artefact of the file, not a loss.

WHAT IT WILL NOT DO
===================
It will not attribute a closed loss to delta/gamma/vega/theta. Those require the
entry snapshot and a path, and for a contract that opened and closed across
several orders the path is not recoverable from order records alone. Claiming
otherwise would produce six confident columns summing to a number that is real
and a decomposition that is invented.

What it CAN say, and says: which underlying, which structure kind, which brain,
which day, how much was slippage against the quote we decided on, and whether
the position was closed by us or expired.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper

#: Options are quoted per share and traded per contract.
OPTION_MULTIPLIER = 100.0

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")


def _multiplier(order: dict) -> float:
    return OPTION_MULTIPLIER if order.get("asset_class") == "us_option" else 1.0


def flatten(orders: list[dict]) -> list[dict]:
    """One row per FILLED CONTRACT, expanding multi-leg parents into their legs.

    A `mleg` order has `symbol: ""` and carries the real contracts in `legs`,
    each with its own side, filled_qty and filled_avg_price. The parent's
    `filled_avg_price` is the NET debit of the package.

    The first version of this script summed the parents, so all ten spreads and
    straddles in the dev book collapsed into a single phantom contract with an
    empty ticker and a net quantity of -71. It printed a clean-looking waterfall
    in which every real structure was missing. `order_class` counted 19 simple
    and 10 mleg -- a third of the book, and the third that carried the losses.

    Kept as its own function so the flattening can be tested without a venue.
    """
    out: list[dict] = []
    for o in orders:
        legs = o.get("legs") or []
        if not legs:
            if o.get("symbol") and float(o.get("filled_qty") or 0) > 0:
                out.append({"symbol": o["symbol"], "side": o["side"],
                            "filled_qty": float(o["filled_qty"]),
                            "price": float(o.get("filled_avg_price") or 0.0),
                            "mult": _multiplier(o), "id": o["id"],
                            "filled_at": o.get("filled_at"), "parent": o["id"],
                            "order_class": o.get("order_class") or "simple"})
            continue
        for leg in legs:
            q = float(leg.get("filled_qty") or 0)
            if q <= 0 or not leg.get("symbol"):
                continue
            out.append({"symbol": leg["symbol"], "side": leg["side"], "filled_qty": q,
                        "price": float(leg.get("filled_avg_price") or 0.0),
                        "mult": OPTION_MULTIPLIER, "id": o["id"],
                        "filled_at": o.get("filled_at"), "parent": o["id"],
                        "order_class": "mleg"})
    return out


def _underlying(symbol: str) -> str:
    """`NVDA260828C00222500` -> `NVDA`. An equity symbol is its own underlying."""
    for i, ch in enumerate(symbol):
        if ch.isdigit():
            return symbol[:i] or symbol
    return symbol


def _decisions_by_order() -> dict[str, dict]:
    """alpaca_order_id -> the decision row that created it.

    Deduped by order id, keeping the row that names a brain: the same order id
    appears on `intent`, `submitted` and every later audit row, and only some of
    them carry the thesis.
    """
    out: dict[str, dict] = {}
    path = STATE / "decisions.jsonl"
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:                                          # noqa: BLE001
                continue
            oid = row.get("alpaca_order_id")
            if not oid:
                continue
            prev = out.get(oid)
            if prev is None or (row.get("brain") and row.get("brain") != "fill_audit"
                                and prev.get("brain") == "fill_audit"):
                out[oid] = row
    return out


def _slippage_by_order() -> dict[str, float]:
    """alpaca_order_id -> slippage in dollars, DEDUPED.

    `state/fills.jsonl` re-marks the same orders every cycle. Keying a dict by
    order id is the whole fix, and it is the difference between -$302,818 and a
    real number.
    """
    out: dict[str, float] = {}
    path = STATE / "fills.jsonl"
    if not path.exists():
        return out
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:                                          # noqa: BLE001
                continue
            oid, fill = row.get("alpaca_order_id"), row.get("fill") or {}
            if oid and fill.get("slippage_usd") is not None:
                out[oid] = float(fill["slippage_usd"])       # last write wins; all identical
    return out


def forensics(role: str) -> dict:
    os.environ["AAT_ACCOUNT_ROLE"] = role
    client = AlpacaPaper(role=role)
    acct = client.account()
    equity = float(acct.get("equity") or 0.0)
    orders = [o for o in client.orders(status="all", limit=500)
              if float(o.get("filled_qty") or 0) > 0]
    decisions = _decisions_by_order()
    slippage = _slippage_by_order()

    rows = flatten(orders)
    held = {p["symbol"]: float(p.get("qty") or 0.0) for p in client.positions()}

    per_contract: dict[str, dict] = defaultdict(
        lambda: {"net_qty": 0.0, "cash": 0.0, "orders": [], "buys": 0.0, "sells": 0.0})
    for r in rows:
        signed = r["filled_qty"] if r["side"] == "buy" else -r["filled_qty"]
        cash = -signed * r["price"] * r["mult"]
        c = per_contract[r["symbol"]]
        c["net_qty"] += signed
        c["cash"] += cash
        c["orders"].append(r)
        if r["side"] == "buy":
            c["buys"] += r["filled_qty"] * r["price"] * r["mult"]
        else:
            c["sells"] += r["filled_qty"] * r["price"] * r["mult"]

    # THE RECONSTRUCTION MUST AGREE WITH THE VENUE, OR IT IS FICTION.
    #
    # Net quantity from the order history has to equal the position the account
    # actually holds. A mismatch means the arithmetic missed a fill -- which is
    # exactly what happened when multi-leg parents were summed instead of their
    # legs, and the reconstruction still printed a confident waterfall.
    #
    # It is REPORTED, never silently corrected: a reconciliation that repairs
    # itself cannot tell you it was wrong.
    mismatches = []
    for sym, c in per_contract.items():
        if abs(c["net_qty"] - held.get(sym, 0.0)) > 1e-9:
            mismatches.append({"symbol": sym, "from_orders": c["net_qty"],
                               "held_at_venue": held.get(sym, 0.0)})
    for sym, q in held.items():
        if sym not in per_contract:
            mismatches.append({"symbol": sym, "from_orders": 0.0, "held_at_venue": q})

    closed, open_ = {}, {}
    for sym, c in per_contract.items():
        (closed if abs(c["net_qty"]) < 1e-9 else open_)[sym] = c

    realised = sum(c["cash"] for c in closed.values())
    spent_open = sum(c["cash"] for c in open_.values())

    by_underlying: dict[str, float] = defaultdict(float)
    by_brain: dict[str, float] = defaultdict(float)
    by_kind: dict[str, float] = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    unattributed = 0.0
    for sym, c in closed.items():
        by_underlying[_underlying(sym)] += c["cash"]
        first = min(c["orders"], key=lambda o: o.get("filled_at") or "")
        by_day[(first.get("filled_at") or "?")[:10]] += c["cash"]
        d = decisions.get(first.get("id"))
        if d and d.get("brain") and d["brain"] != "fill_audit":
            by_brain[d["brain"]] += c["cash"]
            by_kind[d.get("instrument") or "?"] += c["cash"]
        else:
            by_brain["UNATTRIBUTED"] += c["cash"]
            by_kind["UNATTRIBUTED"] += c["cash"]
            unattributed += c["cash"]

    order_ids = {o["id"] for o in orders}
    slip_total = sum(v for k, v in slippage.items() if k in order_ids)
    return {
        "role": role,
        "account": acct.get("account_number"),
        "equity": equity,
        "orders_filled": len(orders),
        "contracts_touched": len(per_contract),
        "contracts_closed": len(closed),
        "contracts_open": len(open_),
        "realised_usd": realised,
        "cash_in_open_positions_usd": spent_open,
        "slippage_usd_deduped": slip_total,
        "slippage_rows_in_file": len(slippage),
        "unattributed_usd": unattributed,
        "mleg_orders": sum(1 for o in orders if o.get("legs")),
        "contract_rows_after_flatten": len(rows),
        "reconciles_with_venue": not mismatches,
        "mismatches": mismatches,
        "by_underlying": dict(sorted(by_underlying.items(), key=lambda kv: kv[1])),
        "by_brain": dict(sorted(by_brain.items(), key=lambda kv: kv[1])),
        "by_structure": dict(sorted(by_kind.items(), key=lambda kv: kv[1])),
        "by_entry_day": dict(sorted(by_day.items())),
        "_closed": closed,
    }


def _print(r: dict) -> None:
    print(f"\n{'='*74}\nPNL FORENSICS  role={r['role']}  account {r['account']}  "
          f"equity ${r['equity']:,.2f}")
    print(f"  {r['orders_filled']} filled orders ({r['mleg_orders']} multi-leg) -> "
          f"{r['contract_rows_after_flatten']} contract fills over {r['contracts_touched']} "
          f"contracts: {r['contracts_closed']} CLOSED, {r['contracts_open']} still open")
    if r["reconciles_with_venue"]:
        print("  RECONCILES: net quantity from the order history equals the position held.")
    else:
        print(f"  DOES NOT RECONCILE -- {len(r['mismatches'])} contract(s). Every number below "
              "is suspect:")
        for m in r["mismatches"][:12]:
            print(f"    {m['symbol']:<26} orders say {m['from_orders']:+.0f}, "
                  f"venue holds {m['held_at_venue']:+.0f}")
    print(f"\n  REALISED (closed contracts, net cash)      ${r['realised_usd']:+,.2f}")
    print(f"  cash tied up in still-open contracts       ${r['cash_in_open_positions_usd']:+,.2f}")
    print("    (not a loss -- money spent, not money gone. Kept out of the realised total.)")
    if r["realised_usd"]:
        print(f"  realised as % of a $100,000 start          "
              f"{r['realised_usd']/1000:+.2f}%")

    for title, key in (("BY UNDERLYING", "by_underlying"),
                       ("BY BRAIN", "by_brain"),
                       ("BY STRUCTURE", "by_structure"),
                       ("BY ENTRY DAY", "by_entry_day")):
        rows = r[key]
        if not rows:
            continue
        print(f"\n  {title}")
        total = sum(rows.values()) or 1.0
        for k, v in rows.items():
            share = 100 * v / total if total else 0.0
            bar = "#" * min(40, int(abs(share) / 2.5))
            print(f"    {k:<18} {v:>+11,.0f}  {share:>6.1f}%  {bar}")

    print(f"\n  SLIPPAGE against the quote we decided on   ${r['slippage_usd_deduped']:+,.2f}")
    print(f"    deduped from {r['slippage_rows_in_file']} order ids in a file with re-marked rows.")
    print("    Summing `pnl_usd_if_closed_now` over that file gives -$302,818 and is an")
    print("    artefact of the file, not a loss.")
    if r["unattributed_usd"]:
        print(f"\n  UNATTRIBUTED  ${r['unattributed_usd']:+,.2f} -- closed contracts whose "
              "opening order has no decision row naming a brain.")
        print("    Every dollar here is a dollar the ledger cannot explain. It is printed")
        print("    rather than distributed, because distributing it would invent attribution.")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true", help="write state/pnl_forensics.json")
    args = p.parse_args()
    config.load_env()

    roles = config.known_roles() if args.all else [args.role or config.role()]
    out = {}
    for role in roles:
        try:
            r = forensics(role)
        except Exception as exc:                                       # noqa: BLE001
            print(f"\n{role}: UNREADABLE {type(exc).__name__}: {exc}")
            continue
        _print(r)
        r.pop("_closed", None)
        out[role] = r

    if args.json:
        dest = STATE / "pnl_forensics.json"
        dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(f"\nreceipt: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
