"""Seed the `market` arm: ONE index purchase at the next regular open, then never again.

    AAT_ACCOUNT_ROLE=market python -m scripts.seed_market        # dry by default
    AAT_ACCOUNT_ROLE=market python -m scripts.seed_market --live

WHY THIS IS ITS OWN SCRIPT AND NOT A BRAIN
==========================================
`market` has no signal, so `run_pass` has nothing to forecast and the whole
brain/gate/sizer path is inapplicable. But the order still has to leave a
DECISION ROW: a position with no ledger entry is invisible to pnl_attribution,
counterfactual and daily_autopsy, and the hash chain silently stops covering the
book. So this writes the row the same way every other order does.

WHY BUY-AND-HOLD EARNS AN ACCOUNT AT ALL
========================================
Cash does not: a paper account holding $100,000 and never trading has an NAV of
exactly $100,000 forever, so it spends a broker account to learn a number already
known analytically. `market` is different because its PATH is not known in
advance, and the drawdown it takes on the way is the number every other arm is
really competing against. That path cannot be reconstructed afterwards from a
closing level.

THE FOUR REFUSALS
=================
1. no frozen contract, or one that no longer matches -> refuse;
2. the account has already traded -> refuse (this is a ONE-TIME seed);
3. the role does not resolve to the market account -> refuse;
4. --live not passed -> print and exit 0.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from alpha import benchmark, config, ledger
from scripts import contract as contract_mod

#: The benchmark instrument. SPY alone rather than a basket: the bar should be
#: the thing a person would actually have bought instead, and a three-ETF blend
#: is already a portfolio decision the benchmark is not entitled to make.
SYMBOL = "SPY"

#: Fraction of equity deployed. Not 100%: a market-on-open order is priced at an
#: unknown open, and an order for more shares than the cash covers is rejected
#: outright, which would leave the benchmark unseeded for the day.
DEPLOY_FRACTION = 0.97


def _get(path: str, creds, *, absolute: bool = False) -> object:
    url = path if absolute else config.base_url() + path
    req = urllib.request.Request(url, headers=creds.headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        if absolute:                      # a missing reference price is handled by the caller
            return {}
        raise


def _post(path: str, creds, body: dict) -> dict:
    req = urllib.request.Request(
        config.base_url() + path, method="POST",
        data=json.dumps(body).encode(),
        headers={**creds.headers, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class _ClientShim:
    """`benchmark.read` speaks the AlpacaPaper interface; this script speaks urllib.

    A shim rather than a rewrite: the seed path is the one place in the repo that
    must keep working when the broker client itself is what is being distrusted.
    """

    def __init__(self, creds):
        self._c = creds

    def positions(self):
        return _get("/v2/positions", self._c) or []

    def orders(self, status="open", limit=200):
        return _get(f"/v2/orders?status={status}&limit={limit}", self._c) or []


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true", help="actually send the order")
    p.add_argument("--symbol", default=SYMBOL)
    p.add_argument("--convention", choices=("opg", "post_open"), default="post_open",
                   help=("opg = PASSIVE_BETA_v1, market-on-open (eligible ONLY for the "
                         "opening auction; cancelled if it does not fill there -- this is "
                         "what left the arm unseeded). post_open = PASSIVE_BETA_v2, a market "
                         "DAY order during regular hours, with the fill verified."))
    args = p.parse_args()
    config.load_env()
    role = "market"

    # 1. THE CONTRACT COMES FIRST. An arm with no frozen contract must not trade.
    if contract_mod.verify(role) != 0:
        print("REFUSED: seed the contract before the account "
              "(`python -m scripts.contract --freeze market`).")
        return 1

    creds = config.credentials(role)
    acct = _get("/v2/account", creds)
    positions = _get("/v2/positions", creds)
    orders = _get("/v2/orders?status=all&limit=5", creds)

    # 2. ONE-TIME, BUT "AN ORDER EXISTS" IS NOT "A BENCHMARK EXISTS".
    #
    # The first version refused on `positions or orders`, which is right for a
    # topped-up book and WRONG for the state this account is actually in: one
    # OPG order that expired unfilled, zero positions, equity still exactly
    # $100,000. Under the old test that reads as "already seeded, refuse" -- so
    # the arm stays permanently unseeded and the refusal message says the
    # opposite of the truth. `alpha/benchmark.py` separates the five states.
    state = benchmark.read(_ClientShim(creds), symbol=args.symbol)
    print(f"benchmark state  {state.line()}")
    if state.state in (benchmark.ACTIVE, benchmark.OVERSEEDED):
        print(f"REFUSED: nothing to seed. This seed is one-time by construction -- a "
              "benchmark that gets topped up is not a buy-and-hold record any more.")
        return 1
    if state.state == benchmark.ORDER_SENT:
        print("REFUSED: an order is still working. Wait for it to fill or terminate; "
              "sending a second one is how a benchmark becomes a double position.")
        return 1
    if state.state == benchmark.EXPIRED_UNFILLED and args.convention == "opg":
        print("REFUSED: the previous OPG order did not fill, and this would send another "
              "one under the identical convention. An OPG order is eligible only for the "
              "opening auction. Re-run with --convention post_open (PASSIVE_BETA_v2), which "
              "submits a market DAY order during regular hours and VERIFIES the fill.")
        return 1

    equity = float(acct["equity"])
    budget = equity * DEPLOY_FRACTION

    # WHOLE SHARES, not notional. Alpaca refuses `notional` with `tif=opg`
    # ("fractional orders must be DAY orders"), and a DAY order fills whenever it
    # is submitted rather than at the open -- which is a different convention from
    # the one the contract names. So the size is rounded DOWN to whole shares and
    # the leftover cash is reported rather than deployed at the wrong time.
    ref = _get(f"{config.data_url()}/v2/stocks/{args.symbol}/trades/latest"
               f"?feed={config.stock_feed()}", creds, absolute=True)
    price = float(((ref or {}).get("trade") or {}).get("p") or 0.0)
    if price <= 0:
        print(f"REFUSED: no reference price for {args.symbol}; refusing to size a seed "
              "against an unknown price.")
        return 1
    qty = int(budget // price)
    if qty < 1:
        print(f"REFUSED: ${budget:,.2f} buys 0 whole shares at ${price:,.2f}.")
        return 1
    est = qty * price
    print(f"account   {acct['account_number']}  equity ${equity:,.2f}")
    print(f"reference {args.symbol} last trade ${price:,.2f}")
    print(f"order     BUY {qty} {args.symbol}  ~${est:,.2f}  type=market  tif=opg "
          f"(fills at the next regular open, at the OPEN price, not this one)")
    print(f"          ${equity - est:,.2f} stays in cash from rounding down to whole shares")
    print(f"contract  PASSIVE_BETA_v1 -- one purchase, never sold, never retired")

    if not args.live:
        print("\nDRY RUN. Nothing sent. Re-run with --live to seed.")
        return 0

    tif = "opg" if args.convention == "opg" else "day"
    body = {"symbol": args.symbol, "qty": str(qty), "side": "buy",
            "type": "market", "time_in_force": tif}
    notional = round(est, 2)
    try:
        placed = _post("/v2/orders", creds, body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        # A notional market-on-open order is not accepted by every venue path;
        # say so rather than silently falling back to a different order type,
        # which would seed the benchmark under conventions its contract does not
        # describe.
        print(f"REFUSED by the broker: HTTP {exc.code} {detail}")
        print("NOT retried with a different order type -- the contract names "
              "'next regular-session open, market order' and a substitute would "
              "seed the benchmark under a convention it does not describe.")
        return 1

    _record(args.symbol, body, placed.get("id"), equity, notional, role)
    print(f"\nSUBMITTED order {placed.get('id')}  status={placed.get('status')}")

    # SUBMITTED IS NOT SEEDED. v1 stopped here and printed a line that every
    # downstream reader took as "the benchmark is live". The OPG order it sent
    # was cancelled at the open and the arm stayed empty for nine days while
    # the scoreboard quoted it. So the last thing this script does is ask the
    # venue whether a POSITION exists, and it exits non-zero when one does not.
    final = benchmark.read(_ClientShim(creds), symbol=args.symbol)
    print(f"venue state      {final.line()}")
    if not final.is_active:
        print("\nNOT SEEDED. The order was accepted and no position exists yet.")
        if tif == "opg":
            print("  An OPG order fills only in the opening auction, so this is EXPECTED "
                  "outside it -- re-run this check after the next open:")
        else:
            print("  A market DAY order outside regular hours does not fill until the "
                  "session opens. Re-check then:")
        print("      AAT_ACCOUNT_ROLE=market python -m scripts.benchmark_state")
        print("  Until the state reads ACTIVE, nothing may quote a benchmark number.")
        return 2
    print("\nSEEDED. A position exists; the benchmark may be quoted.")
    print("ledger row written. Verify with: python -c \"from alpha import ledger,config; "
          "config.load_env(); print(ledger.verify_chain())\"")
    return 0


def _record(symbol: str, body: dict, order_id: str | None, equity: float,
            notional: float, role: str, *, backfilled: bool = False) -> str:
    """Write the decision row for the seed.

    Split out so an order that reached the broker while the ledger write failed
    can still be recorded. That is not hypothetical: the first live run placed
    order 5b9ee74e and then died on a missing `decision_id`, leaving a real
    position with no row -- the precise failure this repo warns about. When that
    happens the row is written LATE and says so, because a backfilled row that
    pretends to be contemporaneous is worse than a missing one.
    """
    note = ("" if not backfilled else
            " ROW BACKFILLED: the order reached the broker but the ledger write raised "
            "TypeError (missing decision_id) before this row existed. Written after the fact "
            "and labelled so; the order's own submitted_at is the authority on timing.")
    return ledger.record(ledger.Decision(
        decision_id=ledger.new_decision_id(symbol, "passive_beta"),
        ts_utc=datetime.now(timezone.utc).isoformat(),
        symbol=symbol, brain="passive_beta", signal_shape=None,
        instrument="shares",
        thesis=("PASSIVE_BETA_v1 seed: one index purchase at the next regular open, never sold. "
                "This arm has no signal; it is the bar every other arm must clear, and its PATH "
                "is the number they are competing against." + note),
        predicted_move=None, predicted_sd=None, implied_move=None,
        breakeven_move=None, mdm_edge=None,
        quote_snapshot={"convention": "market-on-open, WHOLE SHARES (notional is refused with "
                                      "tif=opg: fractional orders must be DAY orders)",
                        "equity_at_seed": equity, "deploy_fraction": DEPLOY_FRACTION},
        action="submitted", refusal_reason=None,
        risk_fraction=DEPLOY_FRACTION, max_loss_usd=notional,
        order=body, alpaca_order_id=order_id,
        account_role=role,
        outcome={"contract": "PASSIVE_BETA_v1", "one_time": True, "backfilled": backfilled},
    ))


if __name__ == "__main__":
    raise SystemExit(main())
