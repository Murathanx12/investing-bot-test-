"""PNL_FORENSICS_v1 -- the reconstruction, and the bug it shipped with for an hour.

The first version summed multi-leg PARENTS. A `mleg` order carries `symbol: ""`
and the real contracts in `legs`, so all ten spreads and straddles in the dev
book collapsed into one phantom contract with an empty ticker and net quantity
-71. It reported realised P&L as **-$1,161** against a true **-$14,335**, and it
printed a clean, plausible waterfall while doing it.

What caught it was the reconciliation: net quantity from the order history must
equal the position the venue holds. These checks pin both.
"""
from __future__ import annotations

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("pnl forensics -- cash-flow reconstruction")

from scripts.pnl_forensics import OPTION_MULTIPLIER, _underlying, flatten   # noqa: E402

# A real dev straddle, in the shape the venue returns it.
MLEG = {
    "id": "5976f736", "symbol": "", "order_class": "mleg", "qty": "8",
    "filled_qty": "8", "filled_avg_price": "0.17", "status": "filled",
    "asset_class": "us_option", "filled_at": "2026-08-25T13:31:00Z",
    "legs": [
        {"symbol": "NIO260828C00004500", "side": "buy", "qty": "8",
         "filled_qty": "8", "filled_avg_price": "0.06", "status": "filled"},
        {"symbol": "NIO260828P00004500", "side": "buy", "qty": "8",
         "filled_qty": "8", "filled_avg_price": "0.11", "status": "filled"},
    ],
}
SIMPLE = {"id": "3b3193d8", "symbol": "NVDA260828C00222500", "side": "buy", "qty": "15",
          "filled_qty": "15", "filled_avg_price": "5.85", "status": "filled",
          "asset_class": "us_option", "filled_at": "2026-08-27T16:11:27Z", "legs": None}
UNFILLED = {"id": "z", "symbol": "SPY260828C00766000", "side": "buy", "qty": "3",
            "filled_qty": "0", "filled_avg_price": None, "status": "canceled",
            "asset_class": "us_option", "legs": None}

rows = flatten([MLEG, SIMPLE, UNFILLED])
check("a multi-leg parent expands into its legs", len(rows) == 3, f"{len(rows)} rows")
check("the phantom empty-ticker contract is gone",
      all(r["symbol"] for r in rows),
      "an mleg parent has symbol '' and summing it invented a contract with no ticker")
check("both legs of the straddle survive",
      {r["symbol"] for r in rows if r["symbol"].startswith("NIO")}
      == {"NIO260828C00004500", "NIO260828P00004500"})
check("leg prices are the LEG fills, not the package's net debit",
      sorted(r["price"] for r in rows if r["symbol"].startswith("NIO")) == [0.06, 0.11],
      "0.17 is the net debit of the package and belongs to no single contract")
check("a simple order passes through", any(r["symbol"] == SIMPLE["symbol"] for r in rows))
check("an UNFILLED order contributes nothing",
      not any(r["id"] == "z" for r in rows),
      "a cancelled order moved no cash")
check("legs are priced per contract", all(r["mult"] == OPTION_MULTIPLIER for r in rows))

# --- cash flow arithmetic ---------------------------------------------------
def cash(rows_):
    total = 0.0
    for r in rows_:
        signed = r["filled_qty"] if r["side"] == "buy" else -r["filled_qty"]
        total += -signed * r["price"] * r["mult"]
    return total

check("buying the NIO straddle is a cash OUTFLOW of 8 x 0.17 x 100",
      abs(cash([r for r in rows if r["symbol"].startswith("NIO")]) + 136.0) < 1e-6,
      str(cash([r for r in rows if r["symbol"].startswith("NIO")])))

sold = [dict(r, side="sell", price=0.0) for r in rows if r["symbol"].startswith("NIO")]
check("selling it back at zero realises the full premium as a loss",
      abs(cash([r for r in rows if r["symbol"].startswith("NIO")] + sold) + 136.0) < 1e-6)

sold_up = [dict(r, side="sell", price=r["price"] * 3) for r in rows
           if r["symbol"].startswith("NIO")]
check("a winner comes back positive",
      cash([r for r in rows if r["symbol"].startswith("NIO")] + sold_up) > 0)

# --- underlying extraction --------------------------------------------------
for sym, want in (("NVDA260828C00222500", "NVDA"), ("SPY260828P00766000", "SPY"),
                  ("NIO260828C00004500", "NIO"), ("SPY", "SPY")):
    check(f"{sym} -> {want}", _underlying(sym) == want, _underlying(sym))

# --- the reconciliation must exist and must be printed, not silently fixed --
from pathlib import Path                                       # noqa: E402

src = Path("scripts/pnl_forensics.py").read_text(encoding="utf-8")
check("the script reconciles order history against held positions",
      "held_at_venue" in src and "mismatches" in src)
check("a mismatch is REPORTED, not corrected",
      "DOES NOT RECONCILE" in src and "Every number below" in src,
      "a reconciliation that repairs itself cannot tell you it was wrong")
check("open-position cash is kept OUT of the realised total",
      "cash_in_open_positions_usd" in src and "not a loss" in src,
      "mixing them makes a book that spent money look like a book that lost it")
check("slippage is deduped by order id",
      "_slippage_by_order" in src and "-$302,818" in src,
      "1,070 rows re-mark 29 orders; that number has been quoted in a handoff")
check("the script refuses to invent a greek decomposition for closed contracts",
      "would produce six confident columns" in src)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
