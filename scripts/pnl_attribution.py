"""PNL_ATTRIBUTION_v1 -- why every open structure is where it is.

    python -m scripts.pnl_attribution                 # this account (AAT_ACCOUNT_ROLE)
    python -m scripts.pnl_attribution --role exp1
    python -m scripts.pnl_attribution --all --json    # both books, receipt to state/

Per structure: P&L = delta + gamma + vega + theta + spread + residual, from the
entry snapshot the ledger kept. Realised and unrealised are split at the account.
The receipt is `state/pnl_attribution.json`; the number that matters is the VEGA
column on any short-premium structure with an event still ahead of it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alpha import attribution, config
from alpha.broker.alpaca import AlpacaPaper


def _report(role: str) -> dict:
    os.environ["AAT_ACCOUNT_ROLE"] = role
    client = AlpacaPaper()
    r = attribution.attribute_book(client, account_role=role)
    print(f"\n{role}: equity ${r['equity']:,.0f}  realised {r['realised_usd']:+,.0f}  "
          f"unrealised {r['unrealised_usd']:+,.0f}  |  TRUE max loss ${r['book']['true_max_loss_usd']:,.0f} "
          f"= {r['book']['fraction']:.1%} of equity (premium-paid view ${r['book']['premium_paid_usd']:,.0f})")
    if r["book"]["unbounded"]:
        print(f"  UNBOUNDED legs: {r['book']['unbounded_legs']}")
    for s in r["_structs"]:
        print("  " + s.line())
        for l in s.legs:
            if l.note:
                print(f"      {l.symbol}: {l.note}")
    t = r["totals"]
    print("  TOTAL   " + "  ".join(f"{k[:-4]} {v:+,.0f}" for k, v in t.items()))
    for res in r["book"]["residual_legs"]:
        print(f"  residual leg {res['symbol']} qty {res['qty']:+.0f}: {res['how']} (${res['charge_usd']:,.0f})")
    r.pop("_structs", None)
    return r


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", default=None)
    p.add_argument("--all", action="store_true", help="every known paper role")
    p.add_argument("--json", action="store_true", help="write state/pnl_attribution.json")
    args = p.parse_args()
    config.load_env()
    roles = config.known_roles() if args.all else [args.role or os.getenv("AAT_ACCOUNT_ROLE", "dev")]
    roles = [r for r in roles if r != "competition" or os.getenv("AAT_COMPETITION_KEY_ID")]
    out = {}
    for role in roles:
        try:
            out[role] = _report(role)
        except Exception as exc:                                         # noqa: BLE001
            print(f"\n{role}: could not attribute -- {type(exc).__name__}: {exc}")
    if args.json:
        path = Path(os.getenv("AAT_LEDGER_DIR", Path(__file__).resolve().parent.parent / "state")) / "pnl_attribution.json"
        path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"\n  receipt: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
