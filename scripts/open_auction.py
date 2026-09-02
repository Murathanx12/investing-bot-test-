"""THE PRE-OPEN PASS: today's sealed book into the OPENING AUCTION.

    python -m scripts.open_auction --expiry 2026-09-04              # dry, default
    AAT_ENTRY_STYLE=open_auction python -m scripts.open_auction --expiry 2026-09-04 --live

WHAT IT IS
==========
The entry-timing tournament's challenger pass. `hack3` keeps entering at 10:01
ET (the control); `hack4` sends the whole sealed weight as `opg` market-on-open;
`hack6` sends half and lets the ordinary 10:01 pass complete the rest. The
NAMES and the WEIGHTS are identical across all three -- they come from the same
sealed `content_sha256` -- so the only variable is when the weight goes on.

WHAT IT IS NOT
==============
It is not a second alpha path. It runs exactly one brain, `tracker_portfolio`,
over exactly the names in `portfolios[<role>].holdings`, and it goes through
`runner.run_pass` -- the same evaluation, the same sizer, the same
`admission.admit`, the same sealed-weight clamp, the same gross and book caps
as the 10:01 pass. The only differences are the ones the tournament is about:
the order body (`market`/`opg`), the decision id (deterministic in day+symbol),
and the opening-range gate, which cannot bind pre-open and is RECORDED as
bypassed on every decision row rather than skipped in silence.

EVERY PRECONDITION IS RE-DERIVED HERE
=====================================
`scripts.agent_loop` gates this cheaply before spawning it, but this script
re-reads the venue clock, the marker, the role and the book's own hash. A
precondition checked only by the caller is a precondition that stops existing
the moment somebody runs the module by hand -- and the thing being run by hand
places orders.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import brains, config, entry_open, exits, genesis, ledger, runner
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

log = logging.getLogger("open_auction")

BRAIN = "tracker_portfolio"


def _mins_to_open(client) -> float:
    """Minutes until the next open, or a refusal-sized number when unreadable.

    An unreadable clock returns a value OUTSIDE the window, so the pass declines.
    A pre-open pass that cannot tell the time is not one that should be guessing
    whether the auction cutoff has passed.
    """
    clock = client.clock()
    if bool(clock.get("is_open")):
        return -1.0
    nxt = datetime.fromisoformat(str(clock.get("next_open")))
    return (nxt - datetime.now(nxt.tzinfo)).total_seconds() / 60.0


def _submitted_rows(decision_ids: list[str]) -> list[dict]:
    """The ledger rows this pass wrote for the orders it actually sent."""
    wanted = set(decision_ids)
    out = []
    for row in ledger.read_all():
        if row.get("decision_id") in wanted and row.get("action") == "submitted":
            out.append(row)
    return out


def write_receipt(*, day: str, role: str, style: str, book: dict, result,
                  sealed: dict, live: bool, note: str = "",
                  ledger_dir: str | Path | None = None) -> Path:
    """One receipt per day per role. The measurement is the point of the pass."""
    orders = []
    for row in _submitted_rows(list(getattr(result, "decisions", []) or [])):
        o = row.get("order") or {}
        sym = str(row.get("symbol") or "").upper()
        h = (sealed.get("holdings") or {}).get(sym) or {}
        orders.append({
            "symbol": sym,
            "decision_id": row.get("decision_id"),
            "client_order_id": entry_open.opg_client_order_id(day, sym),
            "alpaca_order_id": row.get("alpaca_order_id"),
            "submitted_utc": row.get("ts_utc"),
            "qty": o.get("qty"), "side": o.get("side"),
            "type": o.get("type"), "time_in_force": o.get("time_in_force"),
            "sealed_notional": h.get("notional"),
            "auction_fraction": entry_open.auction_fraction(style),
            "risk_fraction": row.get("risk_fraction"),
        })
    payload = {
        "schema": "entry-timing-1",
        "day": day, "role": role, "entry_style": style,
        "auction_fraction": entry_open.auction_fraction(style),
        "leaves_remainder_for_1001": entry_open.leaves_remainder(style),
        "book_sha256": book.get("content_sha256"),
        "sealed_at_utc": book.get("sealed_at_utc"),
        "sealed_names": sorted(sealed.get("holdings") or {}),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "live": bool(live),
        "note": note,
        "pass": {
            "considered": result.considered, "submitted": result.submitted,
            "refused": result.refused, "dry_run": result.dry_run,
            "shadow": result.shadow, "errors": result.errors,
            "by_reason": dict(result.by_reason or {}),
        },
        "orders": orders,
        # Filled in after the close by `scripts.entry_timing_grade`.
        "fills": None, "grade": None,
    }
    p = entry_open.receipt_path(day, role, ledger_dir=ledger_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return p


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--expiry", required=True, help="YYYY-MM-DD, as run_pass takes it")
    p.add_argument("--profile", default=None, help="risk profile (default: AAT_RISK_PROFILE)")
    p.add_argument("--live", action="store_true", help="actually send orders")
    p.add_argument("--day", default=None, help="session day override (tests / replay)")
    p.add_argument("--ignore-window", action="store_true",
                   help="ATTENDED ONLY: skip the clock window check. Never set by the loop.")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config.load_env()

    try:
        style = entry_open.entry_style()
    except entry_open.EntryStyleRefusal as exc:
        log.error("REFUSED: %s", exc)
        return 2
    if style is None:
        log.info("%s is unset: this account is the CONTROL arm and has no pre-open pass. "
                 "Nothing done.", entry_open.ENV_VAR)
        return 0

    role = (os.getenv("AAT_ACCOUNT_ROLE") or "").strip().lower()
    if not role:
        log.error("REFUSED: AAT_ACCOUNT_ROLE is unset, so there is no book to express.")
        return 2
    day = args.day or exits.session_day()

    # -- SEALING IS NOT ENABLING --------------------------------------------
    # The pre-open pass expresses the sealed portfolio. An account whose loop
    # does not run `tracker_portfolio` has not been enabled for it, and a
    # pre-open pass that ran anyway would be trading a book the 10:01 pass does
    # not trade -- two different strategies under one equity curve.
    enabled = [b.strip() for b in (os.getenv("AAT_LOOP_BRAINS") or "").split(",") if b.strip()]
    if enabled and BRAIN not in enabled:
        log.error("REFUSED: AAT_LOOP_BRAINS=%s does not contain %s. %s expresses the sealed "
                  "portfolio and nothing else; enabling it here while the ordinary pass runs "
                  "other brains would put two strategies on one equity curve.",
                  ",".join(enabled), BRAIN, entry_open.ENV_VAR)
        return 2

    client = AlpacaPaper()

    if not args.ignore_window:
        try:
            mins = _mins_to_open(client)
        except (BrokerRefusal, TypeError, ValueError) as exc:
            log.error("REFUSED: the venue clock is unreadable (%s). A pre-open pass that "
                      "cannot tell the time must not guess whether the 09:28 ET `opg` "
                      "cutoff has passed.", exc)
            return 2
        ok, why = entry_open.should_run(style=style, is_open=(mins < 0), mins_to_open=mins,
                                        day=day, role=role)
        if not ok:
            log.info("no pre-open pass: %s", why)
            return 0
        log.info("pre-open pass: %s", why)

    # -- THE BOOK, RE-HASHED -------------------------------------------------
    try:
        book = entry_open.verified_book(day)
    except (entry_open.EntryStyleRefusal, ValueError) as exc:
        log.error("REFUSED: %s", exc)
        return 2
    from alpha.brains import tracker_portfolio as tp
    try:
        sealed = tp.sealed_holdings(day, book=role)
    except tp.PortfolioDeclined as exc:
        log.error("REFUSED: %s", exc)
        return 2
    symbols = sorted(sealed["holdings"])
    if not symbols:
        log.info("%s's sealed book for %s is EMPTY (a valid decision, not a bug). "
                 "Nothing to send into the auction.", role, day)
        return 0
    log.info("sealed book %s %s sha %s: %d name(s) %s", role, day,
             str(book.get("content_sha256"))[:12], len(symbols), ",".join(symbols))

    # -- THE JUDGED ACCOUNT STILL NEEDS ITS GENESIS RECORD -------------------
    if config.role() == genesis.JUDGED_ROLE and args.live:
        ok_gen, gen_lines = genesis.verify(client, role=genesis.JUDGED_ROLE)
        if not ok_gen:
            log.error("REFUSED -- the judged account cannot be traded:")
            for line in gen_lines:
                log.error("  %s", line)
            return 2

    try:
        runner.check_expiry_against_deadline(args.expiry, slack_days=runner.MAX_EXPIRY_SLACK_DAYS)
    except runner.ExpiryPastDeadline as exc:
        log.error("REFUSED: %s", exc)
        return 2

    from alpha.engine.structures import _days as _sessions_to

    class _Now:
        fetched_at = datetime.now(timezone.utc)
    horizon = _sessions_to(_Now(), args.expiry)
    if horizon <= 0:
        log.error("horizon resolved to %.2f sessions; refusing a zero-length window", horizon)
        return 2

    forecasts, declined = brains.forecast_all(
        client, symbols, horizon, brains=[BRAIN], expiries=[args.expiry])
    for d in declined:
        log.info("declined %-6s %s", d["symbol"], d["why"])
    if not forecasts:
        log.error("no forecasts from the sealed book; refusing an empty auction pass")
        return 1
    fraction = entry_open.auction_fraction(style)
    forecasts = entry_open.scaled_forecasts(forecasts, fraction)
    log.info("%s: %d forecast(s) at %.0f%% of the sealed weight", style, len(forecasts),
             fraction * 100)

    # -- CLAIM THE DAY BEFORE ANY ORDER IS BUILT -----------------------------
    # Deliberately before, not after. A crash between here and the POST costs
    # today's auction entry and the ordinary 10:01 pass buys the book instead --
    # the challenger degrades into the control, which is the harmless direction.
    # Claiming afterwards would let a restart re-submit, with nothing but the
    # venue's duplicate-id rejection between that and a doubled position.
    if not args.ignore_window:
        if not entry_open.claim_today(day, role, style=style):
            log.info("no pre-open pass: another cycle already claimed %s for %s", day, role)
            return 0

    result = runner.run_pass(
        client, forecasts, expiry=args.expiry,
        risk_profile=args.profile or (os.getenv("AAT_RISK_PROFILE") or None),
        dry_run=not args.live, shadow_brains=(),
        entry_style=style, seal_day=day,
    )
    ok, msg = ledger.verify_chain()
    log.info("auction pass: considered=%d submitted=%d refused=%d dry_run=%d errors=%d "
             "| refusals: %s | ledger: %s", result.considered, result.submitted,
             result.refused, result.dry_run, result.errors, result.decomposition(), msg)
    receipt = write_receipt(day=day, role=role, style=style, book=book, result=result,
                            sealed=sealed, live=bool(args.live))
    log.info("receipt %s", receipt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
