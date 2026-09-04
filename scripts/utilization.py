"""CAPITAL UTILIZATION -- how much of each book is working, and why the rest is not.

    python -m scripts.utilization                 # live scoreboard, every role
    python -m scripts.utilization --why-idle      # + marginal exclusion funnel
    python -m scripts.utilization --role hack4 --json

WHY THIS EXISTS
===============
Murat, 2026-09-01: "Do not tell the engine 'use 50% of the $400k buying power.'
With roughly $100k equity, $400k buying power is mostly intraday leverage." He
is right, and the engine already agrees: `alpha/admission.py` sizes against
`gross/equity`, and `buying_power` appears in no sizing path anywhere in this
repo. That was never the gap.

The gap is that NOTHING REPORTED UTILIZATION, so the interesting number was
invisible. On 2026-09-01 hack4 held 29.7% of equity against a 150% ceiling and
seeing that took three API calls and a calculator. A book that reports only
what it holds cannot be debugged -- the lesson `build_portfolio` already
learned about exclusions, one level up.

THE THREE NUMBERS, AND WHY THEY ARE THREE
=========================================
    ACTUAL   Sigma|notional| / equity, from the venue. What is at work.
    INTENT   k x max_notional, from the sealed book. What the book MEANT to
             deploy -- and note this is EMERGENT: no personality declares a
             utilization target, so `derived_gross` is an arithmetic
             consequence of two parameters chosen for other reasons. hack4,
             the profit-max book, intends 50% against a 150% ceiling; hack3,
             the balanced one, intends 75%. Nobody decided that ordering.
    CEILING  `sizing.gross_cap(profile)`. What it may never exceed.

CEILING is a cap, INTENT is an accident, and only ACTUAL is measured. There is
no FLOOR anywhere in the system, which is exactly why 29.7% deployed reads as
compliant: nothing in the engine has an opinion about idle capital.

This script does NOT add a floor. A floor would force trades to fill a number,
which is the error Murat explicitly refused ("do not force-buy enough stocks to
make the number disappear"). It makes the number visible so the real question --
"was the 93rd dollar better deployed than left in cash?" -- can be ASKED.

READ-ONLY. Issues GETs and reads files. Sizes nothing, submits nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal, _is_option

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# The live side: what is actually at work, from the venue
# --------------------------------------------------------------------------

def live_row(role: str) -> dict:
    """Exposure for one role, straight from the broker. Never estimated."""
    os.environ["AAT_ACCOUNT_ROLE"] = role
    client = AlpacaPaper(role=role)
    acct = client.account()
    positions = client.positions()
    try:
        orders = client.orders(status="all", limit=500)
    except BrokerRefusal:
        orders = client.orders(status="open")

    equity = float(acct.get("equity") or 0.0)
    if equity <= 0:
        # A NEW account reports last_equity 0 and the latch refuses every entry;
        # dividing by it would print an infinity and read as a bug in the book.
        return {"role": role, "status": "CANNOT DETERMINE",
                "why": "equity is zero or unreadable at the venue"}

    long_mv = float(acct.get("long_market_value") or 0.0)
    short_mv = float(acct.get("short_market_value") or 0.0)
    cash = float(acct.get("cash") or 0.0)
    gross_usd = abs(long_mv) + abs(short_mv)

    # PREMIUM AT RISK IS NOT NOTIONAL. A long option's entire loss is what was
    # paid for it, so the options sleeve's real exposure is its COST BASIS.
    # Reporting market value would shrink the measured risk every time the
    # position lost money, which is backwards.
    premium_at_risk, n_opt = 0.0, 0
    for p in positions:
        if _is_option(str(p.get("symbol") or "")):
            n_opt += 1
            try:
                premium_at_risk += abs(float(p.get("cost_basis") or 0.0))
            except (TypeError, ValueError):
                premium_at_risk = float("nan")

    day = _session_day()
    today = [o for o in orders if str(o.get("submitted_at") or "").startswith(day)]

    return {
        "role": role, "status": "ok",
        "equity": equity, "cash": cash,
        "gross_usd": gross_usd,
        "gross_frac": gross_usd / equity,
        "net_frac": (long_mv + short_mv) / equity,
        "cash_frac": cash / equity,
        "n_positions": len(positions),
        "n_option_legs": n_opt,
        "premium_at_risk_usd": premium_at_risk,
        "premium_at_risk_frac": premium_at_risk / equity,
        "orders_today": len(today),
        "filled_today": sum(1 for o in today if str(o.get("status")) == "filled"),
        "symbols": sorted(str(p.get("symbol")) for p in positions),
    }


def _session_day() -> str:
    from alpha import exits as _exits
    return str(_exits.session_day())


# --------------------------------------------------------------------------
# The intent side: what the sealed book meant to deploy
# --------------------------------------------------------------------------

def sealed_book(day: str) -> dict | None:
    """The newest sealed book for `day`. Same two locations, same order, and
    for the same reason as `alpha/brains/tracker_portfolio._book_for`: on
    Railway `AAT_LEDGER_DIR` is a mounted volume that SHADOWS the image, so a
    book under `state/` is invisible to the loop and `docs/seed/` is not.
    """
    books = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "predictions"
    seed = ROOT / "docs" / "seed" / "predictions"
    for base in (books, seed):
        cands = (sorted(base.glob(f"{day}.json"))
                 + sorted(base.glob(f"{day}.resealed_*.json")))
        if not cands:
            continue
        try:
            return json.loads(cands[-1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def intent_row(payload: dict | None, role: str) -> dict:
    if payload is None:
        return {"status": "CANNOT DETERMINE", "why": "no sealed book for this day"}
    port = (payload.get("portfolios") or {}).get(role)
    if port is None:
        return {"status": "no book", "why": f"role {role!r} has no portfolio in the seal"}
    wc = port.get("worst_case") or {}
    return {
        "status": "ok",
        "personality": port.get("personality"),
        "k_target": port.get("k_target"),
        "n_selected": port.get("n_selected"),
        "max_notional_each": port.get("max_notional_each"),
        "derived_gross": port.get("derived_gross"),
        "gross_cap": wc.get("gross_cap"),
        "profile": wc.get("profile"),
        "worst_case_pct": wc.get("worst_case_pct"),
        "candidate_pool": port.get("candidate_pool"),
        "eligible": port.get("eligible"),
        "symbols": [h.get("symbol") for h in (port.get("holdings") or [])],
    }


# --------------------------------------------------------------------------
# --why-idle: the marginal funnel, read from the seal's own receipt
# --------------------------------------------------------------------------

def why_idle(payload: dict | None, day: str) -> dict:
    """What each eligibility rule actually costs, per book.

    Read from the seal when it carries `excluded_marginal` -- that block is
    computed by `build_portfolio` on the real rows at seal time, so there is no
    second expression of the rules here to drift away from the ones that
    actually filtered. A seal written before the block existed is REPLAYED
    through the same function, and says so.

    Why this is not `excluded_by_reason`: that chain short-circuits, so a name
    is owned by the earliest rule it fails. On the 2026-09-01 seal it reads
    "hack6: 541 names above the 20% downside cap", which is true and does NOT
    mean the downside cap is why hack6 is empty -- dropping it alone yields 23
    names. Dropping the coherence floor alone yields 151.
    """
    ports = (payload or {}).get("portfolios") or {}
    if ports and all("excluded_marginal" in (p or {}) for p in ports.values()):
        return {"source": "seal", "books": {
            b: dict(p["excluded_marginal"], eligible=p.get("eligible"),
                    pool=p.get("candidate_pool"), status="ok")
            for b, p in ports.items()}}

    try:
        from alpha import tracker as _t
        from scripts.prediction_book import tracker_rows
        _rows, _prov, cands = tracker_rows(day)
        # The seal copies the rule's numbers onto the candidate rows; replaying
        # means putting them back, from the seal itself rather than recomputing
        # them (a recomputation would be a different book).
        nums: dict = {}
        for _b, _p in ports.items():
            for h in (_p.get("holdings") or []):
                nums[h["symbol"]] = h
        for pr in (payload or {}).get("predictions", []):
            nums.setdefault(pr["symbol"], pr)
        for c in cands:
            src = nums.get(c["symbol"]) or {}
            for k in ("exp_return", "downside_5pct", "confidence", "p_up_21d"):
                if src.get(k) is not None:
                    c[k] = src[k]

        out: dict = {}
        for pers in _t.PERSONALITIES:
            got = _t.build_portfolio(cands, pers)
            sealed = ports.get(pers.book) or {}
            block = dict(got["excluded_marginal"], eligible=got["eligible"],
                         pool=got["candidate_pool"])
            # THE SELF-CHECK. A replay that disagrees with the seal describes a
            # different book, and a confident wrong funnel is worse than none.
            # ZERO-VS-ZERO IS NOT AGREEMENT: an empty pool agrees with anything,
            # which is how the first version of this script printed a clean
            # all-zero table for hack6 and called it ok.
            if not got["candidate_pool"]:
                block |= {"status": "REFUSED",
                          "why": "replay produced an EMPTY candidate pool -- nothing "
                                 "to attribute, and an empty funnel agrees with every seal"}
            elif sealed.get("eligible") is not None and got["eligible"] != sealed["eligible"]:
                block |= {"status": "REFUSED",
                          "why": f"replay eligible {got['eligible']} != sealed "
                                 f"{sealed['eligible']} -- this is not the sealed book"}
            else:
                block |= {"status": "ok"}
            out[pers.book] = block
        return {"source": "replay (this seal predates excluded_marginal)", "books": out}
    except Exception as exc:                                     # noqa: BLE001
        return {"source": "CANNOT DETERMINE", "why": str(exc)[:200], "books": {}}


# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# ENTRY AUTHORITY -- armed or disarmed, and by WHAT (2026-09-05)
# --------------------------------------------------------------------------

def entry_authority(role: str, *, now=None) -> dict:
    """Whether this book may OPEN a position right now, and what stops it.

    WHY THIS IS A REPORT AND NOT AN ASSERTION
    =========================================
    Between 2026-09-04 and 2026-09-08 the fleet held nothing, and the reason was
    a stack of four independent disarms -- a mandate flag, a Railway
    `--manage-only` argument, a deleted `AAT_ENTRY_STYLE`, and a deadline
    predicate that fired every morning. Each was deliberate; nothing printed
    them together, so "why are the accounts empty?" cost a session to answer.

    Two of the four live in RAILWAY VARIABLES, which this process cannot read.
    They are reported as CANNOT DETERMINE with the command that answers them,
    never guessed -- a guard that invents its inputs is worse than one that
    refuses (CLAUDE.md, the monday_gate lesson).
    """
    from alpha import exits as _exits, fleet as _fleet

    m = _fleet.FLEET.get(role)
    env = _fleet.env_for(m) if m else {}
    local_args = os.getenv("AAT_LOOP_ARGS", "")
    declared_args = env.get("AAT_LOOP_ARGS", "")
    blockers = []
    if m is None:
        blockers.append(f"role {role!r} is not one of the six declared mandates")
    else:
        if m.manage_only:
            blockers.append("Mandate.manage_only=True (declared in alpha/fleet.py)")
        if "--manage-only" in declared_args:
            blockers.append("--manage-only in the mandate's own loop args")
    if "--manage-only" in local_args:
        blockers.append("--manage-only in this process's AAT_LOOP_ARGS")
    dl = config.deadline_utc()
    if _exits.deadline_liquidation_due(dl, now=now):
        blockers.append(f"past {_exits.LIQUIDATE_BY_ET:%H:%M} ET on the mandate end date "
                        f"{dl[:10]} -- the exit pass is liquidating on sight")
    return {
        "role": role,
        "armed": not blockers,
        "binding": blockers[0] if blockers else None,
        "blockers": blockers,
        "mandate_end_utc": dl,
        "entry_style_declared": env.get("AAT_ENTRY_STYLE"),
        "railway": ("CANNOT DETERMINE from here: the live AAT_LOOP_ARGS and AAT_ENTRY_STYLE are "
                    f"Railway variables. `railway variables --service aat-loop-{role}` answers it."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", action="append", help="limit to these roles")
    ap.add_argument("--day", default=None, help="session day (default: today)")
    ap.add_argument("--why-idle", action="store_true",
                    help="marginal exclusion funnel per sealed book")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass
    config.load_env()

    day = args.day or _session_day()
    payload = sealed_book(day)
    roles = args.role or config.known_roles()

    report = {"day": day, "sealed_sha": (payload or {}).get("content_sha256"),
              "roles": {}, "why_idle": {}}
    for role in roles:
        try:
            live = live_row(role)
        except Exception as exc:                                 # noqa: BLE001
            live = {"role": role, "status": "ERROR", "why": str(exc)[:160]}
        report["roles"][role] = {"live": live, "intent": intent_row(payload, role)}
    if args.why_idle:
        report["why_idle"] = why_idle(payload, day)

    if args.json:
        print(json.dumps(report, indent=1, default=str))
        return 0

    print(f"CAPITAL UTILIZATION -- {day}   seal {str(report['sealed_sha'])[:12] or 'none'}\n")
    print(f"{'role':<8} {'equity':>10} {'gross':>9} {'gross/eq':>9} {'cash':>6} "
          f"{'prem@risk':>10} {'pos':>4} {'ord':>4} {'intent':>7} {'cap':>6}  book")
    print("-" * 106)
    for role in roles:
        lv, it = report["roles"][role]["live"], report["roles"][role]["intent"]
        if lv.get("status") != "ok":
            print(f"{role:<8} {lv.get('status')}: {str(lv.get('why', ''))[:70]}")
            continue
        intent, cap = it.get("derived_gross"), it.get("gross_cap")
        fmt = lambda v: f"{v:.0%}" if isinstance(v, (int, float)) else "--"    # noqa: E731
        print(f"{role:<8} {lv['equity']:>10,.0f} {lv['gross_usd']:>9,.0f} "
              f"{lv['gross_frac']:>8.1%} {lv['cash_frac']:>6.0%} "
              f"{lv['premium_at_risk_frac']:>10.1%} {lv['n_positions']:>4} "
              f"{lv['orders_today']:>4} {fmt(intent):>7} {fmt(cap):>6}  "
              f"{it.get('personality') or it.get('status')}")
        if lv["symbols"]:
            print(f"{'':<8} holds: {', '.join(lv['symbols'])}")
        if it.get("status") == "ok":
            held = set(lv["symbols"])
            sealed_syms = list(it.get("symbols") or [])
            missing = [s for s in sealed_syms if s not in held]
            if missing:
                print(f"{'':<8} sealed but NOT held: {', '.join(missing)}  "
                      f"({len(sealed_syms) - len(missing)}/{len(sealed_syms)} expressed)")

    print("\nENTRY AUTHORITY -- may this book OPEN a position?\n")
    print(f"{'role':<8} {'entries':<10} binding constraint")
    print("-" * 106)
    for role in roles:
        ea = entry_authority(role)
        report["roles"][role]["entry_authority"] = ea
        print(f"{role:<8} {'ARMED' if ea['armed'] else 'DISARMED':<10} "
              f"{ea['binding'] or 'nothing -- this book may enter'}")
        for extra in ea["blockers"][1:]:
            print(f"{'':<19}also: {extra}")
    print(f"\n  mandate end (liquidation date): {config.deadline_utc()}")
    print("  Two disarms live in RAILWAY VARIABLES and are invisible from here:")
    print("  `railway variables --service aat-loop-<role> | grep -E 'LOOP_ARGS|ENTRY_STYLE'`")

    print("\nACTUAL is measured; INTENT is k x notional_each -- EMERGENT, no book declares\n"
          "a utilization target; CEILING is sizing.gross_cap. There is no FLOOR anywhere:\n"
          "idle capital violates nothing, which is why it stays invisible until printed.")

    if args.why_idle:
        wi = report["why_idle"]
        print(f"\n\nWHY IS THE CAPITAL IDLE -- marginal, not first-fired   "
              f"[{wi.get('source')}]\n")
        if not wi.get("books"):
            print(f"  {wi.get('why', 'no books')}")
        for book, f in (wi.get("books") or {}).items():
            print(f"  {book}: pool {f.get('pool')} -> eligible {f.get('eligible')}")
            if f.get("status") == "REFUSED":
                print(f"    REFUSED -- {f.get('why')}\n")
                continue
            fails, only = f.get("fails", {}), f.get("fails_only", {})
            print(f"    {'constraint':<52}{'fails':>7}{'fails ONLY this':>16}")
            for k in sorted(set(fails) | set(only), key=lambda k: -only.get(k, 0)):
                print(f"    {str(k)[:50]:<52}{fails.get(k, 0):>7}{only.get(k, 0):>16}")
            print()
        print("  `fails ONLY this` is the price of the rule: the names that would become\n"
              "  eligible if it alone were dropped, every other rule kept. A rule with a\n"
              "  large `fails` and a near-zero `fails ONLY this` is not what is binding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
