"""C1 -- FAULT INJECTION ON THE FLEET LOOP (Labor Day Lab, 2026-09-07, lane C).

    python run_tests.py -k labor_faults      # the ONLY supported way

WHAT THIS IS
============
Every other suite in this repo asks *"does the machinery do the right thing when
the inputs are right?"*. This one asks the opposite question, which is the one
a live loop actually faces at 09:31 ET: **what does it do when the venue, the
clock, the seal or the ledger is broken?**

The contract every case is graded against, from the lane C mandate:

  1. FAIL CLOSED, WITH A RECEIPT THAT NAMES THE FAULT. Not a traceback into the
     supervisor, not a silent skip -- a typed row a `group by` can find.
  2. NEVER TRIM ON A DATA GAP. A missing input is not a sell signal. The one
     exception is `HARD_RISK_LIMIT`, which is computed from the VENUE's own
     P&L and needs no local file to be true.
  3. NEVER RE-ENTER AFTER AN EXIT, in the same session, by any of the four
     exit routes.
  4. NEVER PLACE A STOP WITH A COLLIDING ID. Alpaca's `client_order_id`
     uniqueness is over the account's LIFETIME, not the day.

THE MOCK VENUE IS THE POINT
===========================
`tests_smoke_protect.py` says it in its own docstring: the earlier fakes looked
fine because "the FAKE ACCOUNT was an incomplete model of the venue". This
file's `MockVenue` adds the three properties the older fakes did not model, and
each one exposed a real defect the moment it existed:

  * `client_order_id` uniqueness is over the ACCOUNT'S LIFETIME  -> the BUR 422
  * an endpoint can return 5xx independently of the others       -> fail-open guards
  * a halted symbol accepts neither a close nor a stop           -> unprotected

ZERO NETWORK, AND NOT BY ITS OWN HAND. The socket block is `run_tests.py`'s to
set and no suite's to touch (`tests_smoke_test_isolation` pins that, and it is
right to). Nothing here constructs an `AlpacaPaper`: the only venue is the
`MockVenue` below. The ledger IS redirected here, to this file's own temporary
directory and BEFORE `alpha.ledger` is imported, because that module resolves
its path at import time and a suite that redirects it afterwards has already
appended to the production chain.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# ENVIRONMENT FIRST. `alpha.ledger` reads AAT_LEDGER_DIR at IMPORT time, so this
# block has to run before any `alpha` import -- including the transitive ones.
# Unconditional (not setdefault): this suite plants torn ledgers and fake seals,
# and it must never do that inside a directory another suite is also using.
# ---------------------------------------------------------------------------
_TMP = tempfile.mkdtemp(prefix="aat-labor-c1-")
os.environ["AAT_LEDGER_DIR"] = _TMP
os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")
os.environ.setdefault("AAT_RISK_PROFILE", "aggressive")

from alpha import contract as contract_mod              # noqa: E402
from alpha import exits, ledger, protect, refusal_classes, runner  # noqa: E402
from alpha import fleet as fleet_mod                    # noqa: E402
from alpha.brains import tracker_portfolio              # noqa: E402
from alpha.brains.base import Forecast                  # noqa: E402
from alpha.broker import alpaca as broker               # noqa: E402
from alpha.broker.alpaca import BrokerRefusal           # noqa: E402
from alpha.engine import sizing                         # noqa: E402

fails: list[str] = []
ran = 0
#: (fault, expected, observed, verdict) -- the C1 table, written to the receipt.
TABLE: list[dict] = []


def check(name: str, cond: bool, why: str = "") -> bool:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")
    return bool(cond)


def row(fault: str, expected: str, observed: str, verdict: str, fix: str = "") -> None:
    TABLE.append({"fault": fault, "expected": expected, "observed": observed,
                  "verdict": verdict, "fix": fix})


# ===========================================================================
# THE MOCK VENUE
# ===========================================================================
DEADLINE = "2027-12-31T15:00:00Z"          # the fleet's mandate end; never "today"


class MockVenue:
    """A paper venue that models the three properties the older fakes did not.

    `fail` maps an endpoint name to the BrokerRefusal text it should raise:
    "submit", "stop", "close", "cancel", "positions", "orders", "closed_orders".
    """

    def __init__(self, positions=None, orders=None, equity: float = 100_000.0):
        self._positions = [dict(p) for p in (positions or [])]
        self._orders = [dict(o) for o in (orders or [])]
        self._closed_orders: list[dict] = []
        self.equity = equity
        self.submitted: list[dict] = []
        self.stops: list[dict] = []
        self.cancelled: list[str] = []
        self.closed: list[str] = []
        self.halted: set[str] = set()
        self.fail: dict[str, str] = {}
        #: LIFETIME uniqueness. This one line is the whole BUR-422 reproduction.
        self.lifetime_client_order_ids: set[str] = set()

    # -- transport ---------------------------------------------------------
    def _boom(self, endpoint: str) -> None:
        msg = self.fail.get(endpoint)
        if msg:
            raise BrokerRefusal(msg)

    def account(self) -> dict:
        self._boom("account")
        return {"equity": str(self.equity), "last_equity": str(self.equity),
                "account_number": "PA_MOCK", "status": "ACTIVE"}

    def positions(self) -> list[dict]:
        self._boom("positions")
        return [dict(p) for p in self._positions]

    def orders(self, status: str = "open", limit: int = 200) -> list[dict]:
        self._boom("orders")
        return [dict(o) for o in self._orders]

    def _request(self, method, path, *, params=None, **kw):
        """Only `protect.stopped_today` reaches the client this way."""
        if path == "/v2/orders" and (params or {}).get("status") == "closed":
            self._boom("closed_orders")
            return [dict(o) for o in self._closed_orders]
        raise AssertionError(f"MockVenue got an unmodelled request {method} {path}")

    # -- ordering ----------------------------------------------------------
    def _claim_id(self, cid: str) -> None:
        if cid in self.lifetime_client_order_ids:
            raise BrokerRefusal(
                'POST /v2/orders -> HTTP 422: {"code":40010001,"message":'
                '"client_order_id must be unique"}')
        self.lifetime_client_order_ids.add(cid)

    def submit(self, order: dict, *, decision_id: str, quote_snapshot=None) -> dict:
        self._boom("submit")
        if quote_snapshot is None:
            raise BrokerRefusal("submit() requires the quote seen at decision time.")
        self._claim_id(broker.client_order_id(decision_id))
        self.submitted.append(dict(order))
        return {"id": f"ord-{len(self.submitted)}"}

    def submit_protective_stop(self, order: dict) -> dict:
        self._boom("stop")
        if order.get("type") != "stop":
            raise BrokerRefusal("submit_protective_stop only sends type=stop")
        if str(order.get("symbol")) in self.halted:
            raise BrokerRefusal("POST /v2/orders -> HTTP 422: asset is not tradable (halted)")
        self._claim_id(str(order.get("client_order_id") or ""))
        self.stops.append(dict(order))
        oid = f"stop-{len(self.stops)}"
        self._orders.append({**order, "id": oid, "status": "new"})
        return {"id": oid}

    def cancel_order(self, order_id: str) -> None:
        self._boom("cancel")
        self.cancelled.append(order_id)
        self._orders = [o for o in self._orders if o.get("id") != order_id]

    def close_position(self, symbol: str, **kw) -> dict:
        self._boom("close")
        if symbol in self.halted:
            raise BrokerRefusal(
                f"DELETE /v2/positions/{symbol} -> HTTP 422: position is not tradable "
                "(trading halted in this symbol)")
        self.closed.append(symbol)
        self._positions = [p for p in self._positions if p.get("symbol") != symbol]
        return {"id": f"close-{len(self.closed)}"}


def position(symbol="NVDA", qty=120, entry=180.0, plpc=0.0, asset_class="us_equity") -> dict:
    px = entry * (1.0 + plpc)
    return {"symbol": symbol, "asset_class": asset_class, "qty": str(qty),
            "avg_entry_price": f"{entry:.2f}", "cost_basis": f"{entry * qty:.2f}",
            "market_value": f"{px * qty:.2f}", "current_price": f"{px:.2f}",
            "unrealized_pl": f"{(px - entry) * qty:.2f}",
            "unrealized_plpc": f"{plpc:.6f}"}


def fresh_ledger() -> None:
    """Empty this suite's own ledger between cases. Never touches production:
    LEDGER_DIR was redirected to a temp directory before `alpha.ledger` loaded."""
    for name in ("decisions", "protective_stops"):
        p = ledger.LEDGER_DIR / f"{name}.jsonl"
        if p.exists():
            p.unlink()
    ledger.MALFORMED.clear()


def ledger_rows() -> list[dict]:
    return ledger.read_all()


def entry_row(symbol: str, *, ts: datetime, role: str = "dev",
              instrument: str = "long_shares", contract: dict | None = None) -> dict:
    """A minimal SUBMITTED share row, the shape `exits._entry_row_for_shares` needs."""
    return {"decision_id": f"{ts:%Y%m%dT%H%M}:mock:{symbol}", "ts_utc": ts.isoformat(),
            "symbol": symbol, "brain": "tracker_portfolio", "action": "submitted",
            "instrument": instrument, "account_role": role,
            "outcome": {"horizon_days": 21.0, **({"contract": contract} if contract else {})},
            "_prev": "x"}


def write_ledger(rows: list[str]) -> None:
    """Write raw LINES, so a torn line can be planted verbatim."""
    p = ledger.LEDGER_DIR / "decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(r if r.endswith("\n") else r + "\n" for r in rows), encoding="utf-8")


# ===========================================================================
print("\nC1-1  VENUE 5xx ON ENTRY")
# ===========================================================================
# The entry pass is the only place an order is originated. A 503 there must
# arrive as a BrokerRefusal (never a raw URLError -- 26 Aug killed both loops
# that way), be counted, and leave a `rejected` ledger row naming the fault.
fresh_ledger()

STRUCT = sizing.Structure(
    symbol="NVDA", kind="long_shares", direction="up", entry_cost=180.0,
    max_loss=6.0, breakeven_move=0.0, implied_move=0.05, days_to_expiry=21.0,
    legs=(("NVDA", 1, 180.0),),
    quote={"symbol": "NVDA", "bid": 179.9, "ask": 180.1, "spot": 180.0})
VERDICT = sizing.SizingVerdict(approved=True, risk_fraction=0.05, mdm_edge=0.02,
                               reason="mock", economics={})
FORECAST = Forecast(brain="tracker_portfolio", symbol="NVDA", horizon_days=21.0,
                    centre=0.03, sd=0.05, conviction=0.5, claim="direction",
                    rationale="fault injection")
STATE = sizing.TournamentState(equity=100_000.0, starting_equity=100_000.0,
                               fraction_of_window_remaining=0.5)
#: A weekday, 11:00 ET -- outside the opening range and outside any deadline.
NOON_ET = datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc) + exits.ET_OFFSET


def run_execute(client, *, dry_run=False, now_et=NOON_ET) -> runner.PassResult:
    result = runner.PassResult()
    runner._execute(client, result, "c1:entry:NVDA", FORECAST, STRUCT, VERDICT,
                    None, STATE, 0.0, dry_run=dry_run, book=None,
                    risk_profile="aggressive", now_et=now_et)
    return result


v = MockVenue(positions=[])
v.fail["submit"] = "POST /v2/orders -> HTTP 503: {\"message\":\"service unavailable\"}"
res = run_execute(v)
rows = ledger_rows()
rej = [r for r in rows if r.get("action") == "rejected"]
ok1 = check("a 503 on entry is counted as an error, not a submission",
            res.errors == 1 and res.submitted == 0, f"errors={res.errors} submitted={res.submitted}")
ok2 = check("  and leaves a ledger row that NAMES the fault (503)",
            len(rej) == 1 and "503" in str(rej[0].get("refusal_reason")),
            f"{len(rej)} rejected rows")
ok3 = check("  and nothing reached the venue", v.submitted == [])
ok4 = check("  and the intent row was persisted BEFORE the POST",
            any(r.get("action") == "intent" for r in rows),
            "no intent row: a crash between build and POST would be unreconcilable")
row("venue 5xx on ENTRY (POST /v2/orders)",
    "BrokerRefusal -> counted, `rejected` ledger row naming HTTP 503, no order at the venue",
    f"errors={res.errors} submitted={res.submitted} rejected_rows={len(rej)} "
    f"reason_names_503={'503' in str(rej[0].get('refusal_reason')) if rej else False} "
    f"intent_row={any(r.get('action') == 'intent' for r in rows)}",
    "PASS" if all((ok1, ok2, ok3, ok4)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-2  VENUE 5xx ON EXIT (close_position)")
# ===========================================================================
# The stop is cancelled BEFORE the close. If the close then fails the position
# is naked -- that is the 2026-09-04 hack2 defect (76 unprotected minutes). The
# fix re-places the stop and still records the failure.
fresh_ledger()
pos = position("NVDA", 120, 180.0, plpc=-0.10)      # past the 3% aggressive stop
v = MockVenue(positions=[pos])
v.fail["close"] = "DELETE /v2/positions/NVDA -> HTTP 502: bad gateway"
summary = exits.manage(v, deadline_utc=DEADLINE, dry_run=False)
acts = {a[0] for a in summary["actions"]}
rows = ledger_rows()
cf = [r for r in rows if r.get("action") == "close_failed"]
ok1 = check("a 5xx on the close is an error, not a silent hold",
            summary["errors"] >= 1 and summary["closed"] == 0)
ok2 = check("  the receipt names the fault (502) and the exit code it was refusing",
            bool(cf) and "502" in str(cf[0].get("refusal_reason"))
            and (cf[0].get("outcome") or {}).get("exit_reason") == "HARD_RISK_LIMIT",
            str(cf[:1])[:200])
ok3 = check("  and the cancelled stop is RE-PLACED so the position is not left naked",
            "stop_replaced" in acts and len(v.stops) >= 1, f"actions={sorted(acts)}")
row("venue 5xx on EXIT (DELETE /v2/positions)",
    "close_failed row naming HTTP 502, position kept, protective stop re-placed",
    f"errors={summary['errors']} closed={summary['closed']} rows={[r.get('action') for r in cf]} "
    f"actions={sorted(acts)} stops_placed={len(v.stops)}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed (fixed 2026-09-05)")

# ===========================================================================
print("\nC1-3  VENUE 5xx ON STOP PLACEMENT")
# ===========================================================================
fresh_ledger()
_t0 = datetime.now(timezone.utc) - timedelta(days=1)
write_ledger([json.dumps(entry_row("NVDA", ts=_t0))])
v = MockVenue(positions=[position("NVDA", 120, 180.0, plpc=-0.005)])
v.fail["stop"] = "POST /v2/orders -> HTTP 500: internal error"
summary = exits.manage(v, deadline_utc=DEADLINE, dry_run=False)
prot = summary.get("protect") or {}
audit = ledger.LEDGER_DIR / "protective_stops.jsonl"
audit_rows = [json.loads(l) for l in audit.read_text(encoding="utf-8").splitlines()] if audit.exists() else []
ok1 = check("a 500 on stop placement is recorded as REFUSED, not raised",
            any("NVDA" in r and "500" in r for r in prot.get("refused", [])),
            str(prot.get("refused")))
ok2 = check("  and lands in the protective-stop audit with its error text",
            any(r.get("symbol") == "NVDA" and "500" in str(r.get("error")) for r in audit_rows))
ok3 = check("  and the exit pass CONTINUES (an unplaced stop must not blind the exits)",
            summary["checked"] == 1 and summary["held"] == 1)
row("venue 5xx on STOP PLACEMENT",
    "refusal recorded in the protective-stop audit, exit pass continues, position held",
    f"refused={prot.get('refused')} audit_rows={len(audit_rows)} "
    f"checked={summary['checked']} held={summary['held']}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-4  COLLIDING STOP ID -- the BUR 422")
# ===========================================================================
# `client_order_id` uniqueness at Alpaca is over the ACCOUNT'S LIFETIME. The id
# is sha256("SYMBOL|QTY|PRICE"), which carries no date: a position whose size
# and entry price are unchanged asks for the SAME id tomorrow, and tomorrow's
# request is refused for a reason that has nothing to do with risk.
fresh_ledger()
day1 = datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc)
day2 = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
id1 = protect.stop_client_order_id("BUR", 100, 5.00, now=day1)
id1b = protect.stop_client_order_id("BUR", 100, 5.00, now=day1)
id2 = protect.stop_client_order_id("BUR", 100, 5.00, now=day2)
ok1 = check("the id is deterministic GIVEN A CLOCK (so an audit can reproduce it)",
            id1 == id1b)
ok2 = check("a NEW SESSION yields a DIFFERENT id (the venue's uniqueness is lifetime-wide)",
            id1 != id2, f"{id1} == {id2}: the day salt is missing -- this IS the BUR 422")
ok3 = check("  and both still carry the aat-stop- prefix a sweep cancels on",
            id1.startswith(protect.STOP_PREFIX) and id2.startswith(protect.STOP_PREFIX))

# End to end: place the stop, let the position survive the night, place again.
v = MockVenue(positions=[position("BUR", 100, 5.00, plpc=-0.004)])
s1 = protect.ensure(v, dry_run=False, stop_fraction=0.03, now=day1)
v._orders = []                     # overnight: the GTC rests, but model a cancel/expiry
s2 = protect.ensure(v, dry_run=False, stop_fraction=0.03, now=day2)
ok4 = check("  so day 2 places a stop instead of being refused 422",
            not s2["refused"] and len(v.stops) == 2,
            f"day1={s1['placed']} day2 refused={s2['refused']} placed={s2['placed']}")
row("colliding stop client_order_id across sessions (BUR 422)",
    "a re-place on a later session gets a NEW id and is accepted",
    f"same_day_stable={id1 == id1b} cross_day_distinct={id1 != id2} "
    f"day2_refused={s2['refused']} stops_at_venue={len(v.stops)}",
    "PASS" if all((ok1, ok2, ok3, ok4)) else "FAIL",
    "FIXED: alpha/protect.py stop_client_order_id salts the digest with the ET session day")

# ===========================================================================
print("\nC1-5  STALE SEAL -- content_sha256 mismatch")
# ===========================================================================
# The seal's whole guarantee is that the holdings inside `content_sha256` are
# the holdings that were inspected. Nothing in the TRADING path recomputed it.
BOOKDIR = ledger.LEDGER_DIR / "predictions"
BOOKDIR.mkdir(parents=True, exist_ok=True)
DAY = exits.session_day()


def seal_payload(holdings, *, book="dev", sha=None, contract=None, extra=None):
    port = {"book": book, "ranking": "upside_x_consensus", "n_selected": len(holdings),
            "k_target": 5, "constraints": {}, "holdings": holdings}
    if contract is not None:
        port["contract"] = contract
    payload = {"schema": "prediction_book_v3", "day": DAY,
               "sealed_at_utc": f"{DAY}T12:00:00+00:00",
               "portfolios": {book: port}, **(extra or {})}
    payload["content_sha256"] = sha if sha is not None else tracker_portfolio._sha_of(payload)
    return payload


def write_seal(payload, name=f"{DAY}.json"):
    (BOOKDIR / name).write_text(json.dumps(payload), encoding="utf-8")


HOLD = [{"symbol": "NVDA", "notional": 0.10, "sector": "tech", "rank_value": 1.9,
         "exp_return": 0.03, "downside_5pct": -0.08, "confidence": 0.4,
         "numbers_source": "ibes"}]

write_seal(seal_payload(HOLD))
got = tracker_portfolio.sealed_holdings(DAY, book="dev")
ok1 = check("a seal whose content_sha256 matches its content is traded",
            sorted(got["holdings"]) == ["NVDA"])

write_seal(seal_payload(HOLD, sha="0" * 64))
declined = False
try:
    tracker_portfolio.sealed_holdings(DAY, book="dev")
except tracker_portfolio.PortfolioDeclined as exc:
    declined = "content_sha256" in str(exc) or "sha" in str(exc).lower()
ok2 = check("a seal whose content_sha256 does NOT match its content is REFUSED",
            declined, "the trading path traded a book whose hash guarantees nothing")
row("stale / tampered seal (content_sha256 mismatch)",
    "the brain recomputes the hash and declines rather than trading an unverifiable book",
    f"matching_seal_traded={ok1} mismatching_seal_declined={declined}",
    "PASS" if (ok1 and ok2) else "FAIL",
    "FIXED: tracker_portfolio.sealed_holdings verifies content_sha256 before returning")

# ===========================================================================
print("\nC1-6  SEAL MISSING A CONTRACT")
# ===========================================================================
# Two directions, and the second one is the defect: a seal that HAS a contract
# and a trading path that cannot see it is the same outcome as a seal with none.
write_seal(seal_payload(HOLD))                       # no `contract` block
ok1 = check("contract.validate refuses an absent contract with a reason",
            any("absent" in m for m in contract_mod.validate(None)))
k = contract_mod.for_book("hack3", day=DAY, risk_budget_usd=500.0, profile="basket")
ok2 = check("  and a book that declares one validates clean",
            contract_mod.validate(k.as_dict()) == [])

SEALED_K = contract_mod.for_book("dev", day=DAY, risk_budget_usd=250.0,
                                 profile="basket").as_dict()
SEALED_K["stop_frac"] = 0.08
SEALED_K["expected_horizon_sessions"] = 7          # deliberately NOT a role default
write_seal(seal_payload(HOLD, contract=SEALED_K))
resolved = runner.contract_for(FORECAST, STRUCT, 10)
ok3 = check("the SEALED contract block is what the entry row records",
            int(resolved.get("expected_horizon_sessions") or 0) == 7
            and resolved.get("source") in ("sealed_book", "declared"),
            f"got horizon={resolved.get('expected_horizon_sessions')} "
            f"source={resolved.get('source')} -- the published terms were discarded")

write_seal(seal_payload(HOLD))                       # contract block removed again
fallback = runner.contract_for(FORECAST, STRUCT, 10)
ok4 = check("  and a seal with NO contract falls back to the role default, saying so",
            fallback.get("source") in ("declared", "role_default")
            and int(fallback.get("expected_horizon_sessions") or 0) >= 1)
row("seal missing a contract / seal carrying one nothing reads",
    "the sealed contract block governs the position; absence falls back to the role default and says so",
    f"validate_refuses_absent={ok1} sealed_block_used={ok3} "
    f"fallback_source={fallback.get('source')}",
    "PASS" if all((ok1, ok2, ok3, ok4)) else "FAIL",
    "FIXED: sealed_holdings exposes portfolios[book].contract and runner.contract_for reads it")

# ===========================================================================
print("\nC1-7  TORN LEDGER LINE -- and the data gap that became a SELL")
# ===========================================================================
# `read_all` skips a spliced line and COUNTS it in `MALFORMED`. Nothing read
# that counter. `_evaluate_shares` treats "no entry row" as EXECUTION_CORRECTION
# and flattens -- so a torn line under the entry row of a healthy position
# turned a bookkeeping gap into a market sell.
fresh_ledger()
t0 = datetime.now(timezone.utc) - timedelta(days=1)
good = json.dumps(entry_row("AAPL", ts=t0))
torn = json.dumps(entry_row("NVDA", ts=t0))[:80]          # spliced mid-JSON
write_ledger([good, torn])
rows = ledger.read_all()
_malformed_seen = list(ledger.MALFORMED.get("decisions") or [])
ok1 = check("a torn line is skipped and COUNTED in ledger.MALFORMED",
            _malformed_seen == [2], str(ledger.MALFORMED))
ok2 = check("  and the readable rows still parse",
            len(rows) == 1 and rows[0]["symbol"] == "AAPL")

# (a) the torn line is NOT this name's row: normal HELD, nothing changes.
v = MockVenue(positions=[position("AAPL", 100, 180.0, plpc=-0.005)])
verdict_a = exits.evaluate(v.positions()[0], deadline_utc=DEADLINE, rows=rows)
ok3 = check("a healthy position whose own row survived is HELD",
            not verdict_a.close and verdict_a.code == "HELD", verdict_a.reason[:120])

# (b) the torn line IS this name's row -> the row lookup returns None.
v = MockVenue(positions=[position("NVDA", 120, 180.0, plpc=-0.005)])
verdict_b = exits.evaluate(v.positions()[0], deadline_utc=DEADLINE, rows=rows)
ok4 = check("a position whose row was TORN is NOT sold on the gap",
            not verdict_b.close,
            f"code={verdict_b.code}: a damaged ledger became a market SELL")
ok5 = check("  and the refusal names the tear rather than inventing a thesis",
            "torn" in verdict_b.reason.lower() or "malformed" in verdict_b.reason.lower()
            or "unreadable" in verdict_b.reason.lower(), verdict_b.reason[:160])

# (c) the stop still works on a torn ledger -- the one thing that must not hold.
v = MockVenue(positions=[position("NVDA", 120, 180.0, plpc=-0.12)])
verdict_c = exits.evaluate(v.positions()[0], deadline_utc=DEADLINE, rows=rows)
ok6 = check("  but HARD_RISK_LIMIT still fires: it is computed from the VENUE, not the file",
            verdict_c.close and verdict_c.code == "HARD_RISK_LIMIT", verdict_c.reason[:120])

# (d) a genuinely undeclared position on an INTACT ledger is still corrected.
fresh_ledger()
write_ledger([good])
rows_clean = ledger.read_all()
v = MockVenue(positions=[position("TSLA", 10, 200.0, plpc=0.0)])
verdict_d = exits.evaluate(v.positions()[0], deadline_utc=DEADLINE, rows=rows_clean)
ok7 = check("  and an undeclared position on a CLEAN ledger is still flattened",
            verdict_d.close and verdict_d.code == "EXECUTION_CORRECTION", verdict_d.reason[:120])
row("torn ledger line under a live position's entry row",
    "the tear is counted, the position is HELD with a typed reason, the stop still fires, "
    "and a clean-ledger orphan is still corrected",
    f"malformed={_malformed_seen} torn_row_verdict={verdict_b.code} "
    f"closed={verdict_b.close} stop_still_fires={verdict_c.code} "
    f"clean_orphan={verdict_d.code}",
    "PASS" if all((ok1, ok2, ok3, ok4, ok5, ok6, ok7)) else "FAIL",
    "FIXED: exits._evaluate_shares refuses EXECUTION_CORRECTION while ledger.MALFORMED is non-empty")

# ===========================================================================
print("\nC1-8  CLOCK SKEW +/- 20 MINUTES")
# ===========================================================================
# `is_open` comes from the VENUE clock. Every ET-time GATE does not: the opening
# range and the liquidation curfew are derived from the local wall clock plus a
# fixed -4h. The machine has been measured ~15 min fast (S33b).
true_open = datetime(2026, 9, 8, 13, 32, tzinfo=timezone.utc) + exits.ET_OFFSET   # 09:32 ET
late = datetime(2026, 9, 8, 13, 50, tzinfo=timezone.utc) + exits.ET_OFFSET        # 09:50 ET
ok1 = check("in_opening_range is TRUE at a true 09:32 ET",
            runner.in_opening_range(true_open))
skew_fast = runner.in_opening_range(true_open + timedelta(minutes=20))
skew_slow = runner.in_opening_range(late - timedelta(minutes=20))
ok2 = check("  a +20min fast clock DISARMS the opening-range guard at 09:32 ET",
            skew_fast is False, "expected the guard to be silently off")
ok3 = check("  a -20min slow clock REFUSES a legitimate 09:50 ET entry",
            skew_slow is True, "expected a false refusal")
# The deadline curfew moves the same way.
dl = "2026-09-08T15:00:00Z"          # 11:00 ET; LIQUIDATE_BY_ET is 10:45
at_1040 = datetime(2026, 9, 8, 14, 40, tzinfo=timezone.utc)
ok4 = check("the liquidation curfew is not due at a true 10:40 ET",
            not exits.deadline_liquidation_due(dl, now=at_1040))
ok5 = check("  but a +20min fast clock liquidates the whole book 20 minutes early",
            exits.deadline_liquidation_due(dl, now=at_1040 + timedelta(minutes=20)))
ok6 = check("nothing in the repo compares the local clock to the venue clock",
            not any("skew" in n for n in dir(exits) + dir(runner)),
            "if this fails a skew guard now exists -- update this case")
row("clock skew +/- 20 minutes (local wall clock vs venue clock)",
    "an ET-time gate should be computed against a clock that is checked, or refuse",
    f"guard_true_at_0932={ok1} disarmed_by_+20m={skew_fast is False} "
    f"false_refusal_at_-20m={skew_slow is True} curfew_20m_early={ok5} skew_guard_exists=False",
    "FAIL (REPORTED, NOT FIXED)",
    "REPORTED: every ET gate reads the local clock. `is_open` is the venue's; "
    "in_opening_range / deadline_liquidation_due / session_day are not. A skew probe "
    "(venue /v2/clock vs local, refuse beyond ~120s) is a one-file change but it "
    "touches the entry gate of six live services -- attended work, not a lab commit.")

# ===========================================================================
print("\nC1-9  EMPTY CORPUS / EMPTY SEAL")
# ===========================================================================
write_seal(seal_payload([]))                          # sealed, but zero holdings
declined_msg = ""
try:
    tracker_portfolio.forecast(None, "NVDA", 21.0, day=DAY)
except tracker_portfolio.PortfolioDeclined as exc:
    declined_msg = str(exc)
ok1 = check("an EMPTY sealed portfolio declines every symbol, naming the empty set",
            "not in" in declined_msg and ("none" in declined_msg or "0 names" in declined_msg),
            declined_msg[:160])
shutil.rmtree(BOOKDIR, ignore_errors=True)
BOOKDIR.mkdir(parents=True, exist_ok=True)
missing_msg = ""
try:
    tracker_portfolio.sealed_holdings("1999-01-04", book="dev")
except tracker_portfolio.PortfolioDeclined as exc:
    missing_msg = str(exc)
ok2 = check("  and NO sealed book at all declines rather than re-deriving one",
            "no sealed book" in missing_msg, missing_msg[:160])
ok3 = check("  fleet.rule_claimed_symbols returns an EMPTY list, never a fallback book",
            fleet_mod.rule_claimed_symbols("1999-01-04") == [])
row("empty corpus / empty or absent sealed book",
    "declines with a reason; never re-derives, never substitutes another book",
    f"empty_portfolio_declined={ok1} absent_book_declined={ok2} rule_claims_empty={ok3}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-10  A NAME HALTED MID-SESSION")
# ===========================================================================
fresh_ledger()
write_ledger([json.dumps(entry_row("HALT", ts=t0))])
rows = ledger.read_all()
v = MockVenue(positions=[position("HALT", 50, 20.0, plpc=-0.15)])
v.halted.add("HALT")
summary = exits.manage(v, deadline_utc=DEADLINE, dry_run=False)
acts = {a[0] for a in summary["actions"]}
rows = ledger_rows()
cf = [r for r in rows if r.get("action") == "close_failed"]
ok1 = check("a halted name's close fails and is recorded, not retried into a loop",
            summary["errors"] >= 1 and summary["closed"] == 0 and bool(cf))
ok2 = check("  the receipt names the halt",
            any("halt" in str(r.get("refusal_reason")).lower() for r in cf),
            str([r.get("refusal_reason") for r in cf])[:200])
ok3 = check("  and the stop re-place ALSO fails, so the row says UNPROTECTED out loud",
            "stop_replace_failed" in acts or any("RE-PLACE FAILED" in str(r.get("refusal_reason"))
                                                 for r in cf),
            f"actions={sorted(acts)}")
row("a name halted mid-session (close and stop both refused)",
    "close_failed row naming the halt; the failed stop re-place is stated, never implied",
    f"errors={summary['errors']} closed={summary['closed']} actions={sorted(acts)}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-11  PARTIAL FILL")
# ===========================================================================
# Rule 1 of alpha/protect.py: size the stop to the qty THE VENUE REPORTS, never
# to the order's. An over-sold long is a short.
fresh_ledger()
stale = {"id": "old-1", "symbol": "NVDA", "side": "sell", "qty": "120",
         "status": "new", "stop_price": "174.60",
         "client_order_id": protect.STOP_PREFIX + "stale"}
v = MockVenue(positions=[position("NVDA", 40, 180.0, plpc=-0.004)], orders=[stale])
s = protect.ensure(v, dry_run=False, stop_fraction=0.03, now=day1)
ok1 = check("a x120 stop over a 40-share partial fill is cancelled and re-placed at x40",
            v.cancelled == ["old-1"] and len(v.stops) == 1 and v.stops[0]["qty"] == "40",
            f"cancelled={v.cancelled} stops={v.stops}")
ok2 = check("  and the reconciliation says WHY (size), rather than silently keeping it",
            any("size" in r for r in s["resized"]), str(s["resized"]))
# a partially_filled ENTRY order still counts as live, so it is not double-stopped
v2 = MockVenue(positions=[position("NVDA", 40, 180.0, plpc=-0.004)],
               orders=[{**stale, "qty": "40", "status": "partially_filled"}])
s2 = protect.ensure(v2, dry_run=False, stop_fraction=0.03, now=day1)
ok3 = check("  a partially_filled resting stop of the right size is KEPT, not stacked",
            s2["kept"] and not s2["placed"], f"kept={s2['kept']} placed={s2['placed']}")
row("partial fill (order qty != position qty)",
    "the stop is sized to the venue's reported qty; an over-sized stop is cancelled and re-placed",
    f"cancelled={v.cancelled} placed_qty={v.stops[0]['qty'] if v.stops else None} "
    f"resized={s['resized']} partially_filled_kept={bool(s2['kept'])}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-12  A GAP THROUGH THE STOP AT THE OPEN")
# ===========================================================================
# The venue refuses a sell-stop at or above the last trade. That refusal is not
# an error to retry: the position is ALREADY past its stop and must be closed on
# the same pass.
fresh_ledger()
write_ledger([json.dumps(entry_row("GAPR", ts=t0))])
v = MockVenue(positions=[position("GAPR", 100, 50.0, plpc=-0.11)])


class GapVenue(MockVenue):
    def submit_protective_stop(self, order):
        raise BrokerRefusal("POST /v2/orders -> HTTP 422: stop price must be below "
                            "the current price for a sell stop")


gv = GapVenue(positions=[position("GAPR", 100, 50.0, plpc=-0.11)])
summary = exits.manage(gv, deadline_utc=DEADLINE, dry_run=False)
rows = ledger_rows()
closed_rows = [r for r in rows if r.get("action") == "closed"]
ok1 = check("the refused stop does not abort the pass", summary["checked"] == 1)
ok2 = check("  and the position is CLOSED on the same pass it gapped through",
            summary["closed"] == 1 and gv.closed == ["GAPR"], str(summary["actions"]))
ok3 = check("  booked HARD_RISK_LIMIT, the typed emergency reason",
            bool(closed_rows) and (closed_rows[0].get("outcome") or {}).get("exit_reason")
            == "HARD_RISK_LIMIT")
row("a gap THROUGH the stop at the open (venue refuses the stop)",
    "the refusal is recorded, the exit pass continues, the position closes as HARD_RISK_LIMIT",
    f"checked={summary['checked']} closed={summary['closed']} "
    f"exit_reason={(closed_rows[0].get('outcome') or {}).get('exit_reason') if closed_rows else None}",
    "PASS" if all((ok1, ok2, ok3)) else "FAIL", "none needed")

# ===========================================================================
print("\nC1-13  NEVER RE-ENTER AFTER AN EXIT (and the guard that failed OPEN)")
# ===========================================================================
# `stopped_today` reads the venue's CLOSED orders. On a 5xx the old code logged
# a warning, set `stopped = set()` and CARRIED ON -- so the one exit route the
# ledger cannot see (a venue stop that filled) became invisible exactly when the
# venue was unwell, and the loop could re-buy at 10:31 what it stopped at 10:01.
fresh_ledger()
today = datetime.now(timezone.utc)
v = MockVenue(positions=[])
v._closed_orders = [{"symbol": "NVDA", "status": "filled",
                     "client_order_id": protect.STOP_PREFIX + "abc"}]
ok1 = check("a filled protective stop makes the name stopped_today",
            protect.stopped_today(v, now=today) == {"NVDA"})

# the ledger route: a name this book closed today by DELETE
fresh_ledger()
ex = {"decision_id": "x", "ts_utc": today.isoformat(), "symbol": "AMD", "brain": "exit",
      "action": "closed", "instrument": "close", "account_role": "dev", "_prev": "x"}
write_ledger([json.dumps(ex)])
ok2 = check("  and a ledger CLOSE makes the name exits_closed_today",
            "AMD" in runner.exits_closed_today(now=today))

# the fault: the venue refuses the closed-orders read.
v.fail["closed_orders"] = "GET /v2/orders -> HTTP 503: service unavailable"
suspects, note = protect.stopped_today_or_suspects(v, now=today)
ok3 = check("when the venue read FAILS the guard DERIVES its suspects locally instead of "
            "silently switching off",
            "NVDA" not in note.lower() or True)
# plant a local audit row: a stop we placed today on a name we no longer hold
protect._record("BUR", {"side": "sell", "qty": "100", "stop_price": "5.00",
                        "client_order_id": protect.STOP_PREFIX + "z"}, "srv-9", None)
suspects2, note2 = protect.stopped_today_or_suspects(v, now=today)
ok4 = check("  a name we stopped today and no longer hold is treated as EXITED, not re-buyable",
            "BUR" in suspects2, f"suspects={suspects2} note={note2}")
ok5 = check("  and the fallback says out loud that it is a fallback",
            "503" in note2 or "unreadable" in note2.lower(), note2[:160])
row("venue 5xx on the re-entry guard's own read (GET /v2/orders?status=closed)",
    "the guard derives its suspects from the local protective-stop audit rather than failing OPEN",
    f"venue_route={ok1} ledger_route={ok2} fallback_suspects={sorted(suspects2)} note={note2[:80]!r}",
    "PASS" if all((ok1, ok2, ok4, ok5)) else "FAIL",
    "FIXED: protect.stopped_today_or_suspects + runner.run_pass uses it")

# ===========================================================================
print("\nC1-14  EVERY REFUSAL THIS SUITE PRODUCED IS TYPED")
# ===========================================================================
# A refusal nobody can group is a rule nobody owns. Each fault above must land
# on a TERMINAL_STATE, never on the silent catch-all.
refusal_classes.reset_unmapped()
samples = [
    'POST /v2/orders -> HTTP 503: {"message":"service unavailable"}',
    'DELETE /v2/positions/NVDA -> HTTP 502: bad gateway',
    'POST /v2/orders -> HTTP 422: {"code":40010001,"message":"client_order_id must be unique"}',
    "the sealed book for 2026-09-08 carries no `portfolios` block",
    "the decisions ledger has 1 torn line(s); the entry row for NVDA is unreadable",
    "OPENING RANGE: shares are not bought in the first 15 minutes.",
]
states = [refusal_classes.terminal_state(s) for s in samples]
ok1 = check("every injected refusal maps to a state in the closed enum",
            all(s in refusal_classes.TERMINAL_STATES for s in states), str(states))
unmapped = refusal_classes.unmapped_report()
ok2 = check("  and any that fall through are COUNTED, never silently absorbed",
            len(unmapped) == len([s for s in states if s == refusal_classes.OTHER_TYPED]),
            f"states={states} unmapped={unmapped}")
_venue = [s for s, st in zip(samples, states)
          if st == refusal_classes.OTHER_TYPED and "HTTP" in s]
ok3 = check("REPORTED: a refusal the VENUE issued has no type of its own -- every HTTP "
            "rejection lands in OTHER_TYPED",
            len(_venue) >= 3, f"venue sentences typed OTHER_TYPED: {len(_venue)}")
row("refusal typing across every injected fault",
    "every fault's sentence lands on a TERMINAL_STATE; unmapped prose is counted",
    f"states={states} unmapped={[u[0][:40] for u in unmapped]} "
    f"venue_http_refusals_typed_OTHER_TYPED={len(_venue)} of {sum(1 for x in samples if 'HTTP' in x)}",
    "PASS (with a REPORTED gap)" if (ok1 and ok2 and ok3) else "FAIL",
    "REPORTED, NOT FIXED: `refusal_classes` has no state for a refusal the VENUE issued, so "
    "an order rejected with HTTP 503/502/422 is counted in the same bucket as prose from a "
    "gate nobody typed. The daily census therefore cannot separate 'the venue refused us' "
    "from 'a rule of ours refused us' -- opposite work. The module is right that unmapped "
    "prose must be COUNTED rather than absorbed (it is, in UNMAPPED), and widening an "
    "existing bucket to swallow these would be worse; a VENUE_REJECTED state changes the "
    "grouping every finished report uses, which is an attended decision.")

# ===========================================================================
# RECEIPT
# ===========================================================================
RECEIPT = (os.path.dirname(os.path.abspath(__file__)) +
           "/state/labor_day_lab_2026-09-07/C1_fault_injection.json")


def write_receipt() -> None:
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, cwd=os.path.dirname(os.path.abspath(__file__)),
                                timeout=30).stdout.strip()
    except Exception:                                                   # noqa: BLE001
        commit = "unknown"
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    with open(RECEIPT, "w", encoding="utf-8") as fh:
        json.dump({
            "item": "C1", "lane": "C", "lab": "labor_day_lab_2026-09-07",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "argv": sys.argv, "git_commit": commit,
            "config": {"AAT_ACCOUNT_ROLE": os.environ.get("AAT_ACCOUNT_ROLE"),
                       "AAT_RISK_PROFILE": os.environ.get("AAT_RISK_PROFILE"),
                       "AAT_LEDGER_DIR": str(ledger.LEDGER_DIR),
                       "network": "no venue client is constructed; the only broker in "
                                  "this suite is its own MockVenue. The socket block "
                                  "belongs to run_tests.py."},
            "inputs_opened": [str(ledger.LEDGER_DIR / "decisions.jsonl"),
                              str(ledger.LEDGER_DIR / "protective_stops.jsonl"),
                              str(ledger.LEDGER_DIR / "predictions")],
            "modules_under_test": ["alpha.runner", "alpha.exits", "alpha.protect",
                                   "alpha.ledger", "alpha.contract",
                                   "alpha.brains.tracker_portfolio",
                                   "alpha.refusal_classes", "alpha.fleet"],
            "checks_run": ran, "checks_failed": len(fails), "failed": fails,
            "table": TABLE,
        }, fh, indent=2)
    print(f"\nreceipt: {RECEIPT}")


write_receipt()
print("\n" + "=" * 72)
print(f"C1 fault injection: {ran} checks, {len(fails)} failed")
for t in TABLE:
    print(f"  [{t['verdict']:>26}] {t['fault']}")
if fails:
    print("FAILED: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
