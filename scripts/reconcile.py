"""Find orders that exist at the venue with no local record -- and REPORT them.

    AAT_ACCOUNT_ROLE=dev python -m scripts.reconcile
    AAT_ACCOUNT_ROLE=dev python -m scripts.reconcile --role market

WHAT IT ANSWERS
===============
`runner` writes an `intent` row before the POST and a `submitted` row after it.
An intent with no submitted means the process died in between, and there are
exactly two possible worlds:

- the POST never reached the venue -> nothing exists, the intent is benign;
- the POST succeeded and the reply was lost -> a REAL position exists that no
  local row describes.

Those are indistinguishable locally and identical in the log. The only authority
is the broker, and it can be asked because `client_order_id` is DERIVED from the
decision id (`aat-<sha256(decision_id)[:32]>`) rather than generated -- so the
order can be looked up from the intent row alone.

WHY IT REPORTS AND DOES NOT REPAIR
==================================
The ledger is a hash chain. Writing the missing row here would be a program
silently appending to a tamper-evident record on the strength of its own guess
about what happened -- which is the thing the chain exists to make impossible.
The 2026-08-27 backfill was done attended, labelled `backfilled`, and followed by
a correction row naming the order's `submitted_at` as the authority on timing.
That is the procedure; this tool finds the work, a person does it.

An empty report is a real result and says so. Silence is not evidence.
"""
from __future__ import annotations

import argparse
import urllib.error
import urllib.parse
import urllib.request

from alpha import config, ledger
from alpha.broker.alpaca import client_order_id


def _lookup(coid: str, creds) -> dict | None:
    """The order at the venue with this client id, or None if there is none."""
    url = (config.base_url() + "/v2/orders:by_client_order_id?"
           + urllib.parse.urlencode({"client_order_id": coid}))
    req = urllib.request.Request(url, headers=creds.headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            import json
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _from_venue(role: str, rows: list[dict], creds) -> int:
    """The OTHER direction: every order the venue holds, checked for a local row.

    `--from-venue` is the complete check and the intent scan is not. The intent
    scan can only see orders whose intent row exists, so it says nothing about
    the 4,178 dev rows and 3,179 exp1 rows written before the protocol existed --
    exactly the books most likely to hold an old orphan. Asking the VENUE for its
    orders needs no local artefact at all, so it covers every era.

    It is not the default because it is O(all orders) and pages against the
    broker, where the intent scan is a local set difference.
    """
    import json

    # ALL rows, not the role-filtered ones. "Does a local row exist for this
    # order" is not a role-scoped question, and scoping it produced a false
    # alarm on the first run: 10 dev and 6 exp1 orders were reported as having no
    # record when every one of them was in the ledger with the right
    # alpaca_order_id. Their rows carry account_role=None -- written before role
    # stamping -- so the filter dropped exactly the rows that answered the
    # question. A filter on the informative tail is invisible.
    every = ledger.read_all()
    known = {r.get("alpaca_order_id") for r in every if r.get("alpaca_order_id")}
    known_coid = {client_order_id(r["decision_id"]) for r in every if r.get("decision_id")}

    LIMIT = 500
    url = (config.base_url() + "/v2/orders?"
           + urllib.parse.urlencode({"status": "all", "limit": LIMIT, "direction": "desc",
                                     "nested": "false"}))
    req = urllib.request.Request(url, headers=creds.headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        orders = json.loads(r.read().decode())

    orphans = [o for o in orders
               if o.get("id") not in known and o.get("client_order_id") not in known_coid]
    print(f"venue holds {len(orders)} order(s); {len(orphans)} have no local row")
    if len(orders) >= LIMIT:
        # A page-sized result is a truncation until proven otherwise. Saying so
        # is the difference between "no orphans" and "no orphans in the part I read".
        print(f"WARNING: the venue returned exactly {LIMIT} orders, the page size. This is "
              "TRUNCATED and older orders were not examined. Narrow with --after or raise the "
              "page size before reading 'no orphans' as a clean result.")
    # Two populations, and only one of them is a defect.
    #
    # An order carrying an `aat-` client id came from `submit()`, so a missing row
    # means we lost it -- that is the seed_market failure and it needs a person.
    #
    # An order with a broker-generated UUID was never given one by us: exits go
    # out as DELETE /v2/positions, and the venue names the resulting order
    # itself. Those have no decision row BY CONSTRUCTION and calling them
    # "foreign" (as a first draft did) reads as an intrusion when it is the
    # normal shape of every close.
    lost = [o for o in orphans if str(o.get("client_order_id") or "").startswith("aat-")]
    broker_named = [o for o in orphans if o not in lost]

    for o in lost[:50]:
        print(f"  LOST-ROW    {o.get('id')}  {o.get('side')} {o.get('qty')} {o.get('symbol')}  "
              f"status={o.get('status')}  coid={o.get('client_order_id')}  {o.get('submitted_at')}")
    if lost:
        print(f"\n{len(lost)} order(s) carry OUR client id and have no ledger row. Backfill "
              "attended, label the row `backfilled`, cite submitted_at as the timing authority.")
    if broker_named:
        print(f"{len(broker_named)} order(s) carry a broker-generated id (exits go out as "
              "DELETE /v2/positions and are named by the venue). Expected, not a defect; "
              "their P&L is reconciled through fills, not through a decision row.")
    # Only a lost row is a failure. A broker-named exit is the normal case and
    # exiting non-zero on it would train the reader to ignore this command.
    return 1 if lost else 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", help="account role to reconcile (default: AAT_ACCOUNT_ROLE)")
    p.add_argument("--from-venue", action="store_true",
                   help="ask the broker for every order and check each for a local row "
                        "(the complete check; covers books written before intent rows existed)")
    args = p.parse_args()
    config.load_env()
    role = args.role or config.role()

    rows = [r for r in ledger.read_all() if (r.get("account_role") or "") == role]
    intents = {r["decision_id"]: r for r in rows if r.get("action") == "intent"}
    settled = {r["decision_id"] for r in rows if r.get("action") in ("submitted", "refused")}
    orphans = {k: v for k, v in intents.items() if k not in settled}

    print(f"role {role}: {len(rows)} rows, {len(intents)} intents, {len(orphans)} unsettled")

    if args.from_venue:
        return _from_venue(role, rows, config.credentials(role))

    if not orphans:
        # An empty result is a measurement, not an absence of one. Say which
        # question was asked, so a reader cannot mistake this for a run that
        # found nothing because it looked nowhere.
        print("NO UNSETTLED INTENTS. Every intent row has a matching submitted or refused row, "
              "so no order can exist at the venue without a local record.")
        if not intents:
            print("NOTE: there are no intent rows at all for this role. Rows written before "
                  "2026-08-27 predate the intent-before-POST protocol and cannot be checked "
                  "this way -- this says nothing about them.")
        return 0

    creds = config.credentials(role)
    found, missing, unknown = [], [], []
    for did, row in sorted(orphans.items()):
        coid = client_order_id(did)
        try:
            order = _lookup(coid, creds)
        except Exception as exc:  # noqa: BLE001 -- an unanswered question is its own state
            unknown.append((did, coid, str(exc)[:120]))
            continue
        (found if order else missing).append((did, coid, order))

    print()
    for did, coid, order in found:
        print(f"AT THE VENUE  {did}")
        print(f"  client_order_id {coid}  broker id {order.get('id')}")
        print(f"  {order.get('side')} {order.get('qty')} {order.get('symbol')}  "
              f"status={order.get('status')}  submitted_at={order.get('submitted_at')}")
        print(f"  filled {order.get('filled_qty')} @ {order.get('filled_avg_price')}")
        print("  -> a REAL order with no submitted row. Backfill it attended, label the row "
              "`backfilled`, and cite submitted_at as the authority on timing.")
    for did, coid, _ in missing:
        print(f"never sent   {did}  ({coid}) -- no such order at the venue; the intent is benign.")
    for did, coid, why in unknown:
        print(f"UNKNOWN      {did}  ({coid}) -- the broker could not be asked: {why}")
        print("  -> NOT the same as 'never sent'. Re-run before concluding anything.")

    print(f"\n{len(found)} at the venue, {len(missing)} never sent, {len(unknown)} unanswered")
    # Non-zero only for the state that needs a human: an unanswered question is
    # also not a pass, because "could not ask" reads exactly like "nothing there".
    return 1 if (found or unknown) else 0


if __name__ == "__main__":
    raise SystemExit(main())
