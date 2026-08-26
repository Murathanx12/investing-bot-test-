"""Grade a scheduled print by COMPONENT, not by "dev made $X".

    python -m scripts.event_grade NVDA --expiry 2026-08-28 --pre          # before the print: freeze the baseline
    python -m scripts.event_grade NVDA --expiry 2026-08-28 --post         # after day-0: grade against it
    python -m scripts.event_grade NVDA --expiry 2026-08-28 --post --day0-move 0.031 --resolve PH:NVDA:2026-08-27:b29d506d

A lucky flat print can crown the wrong brain. This grades the parts each brain
actually claimed:

  1. WIDTH   -- each brain's pre-print sd against the chain's implied move and
                against the REALISED day-0 move. Who was closest to the width?
  2. CRUSH   -- ATM implied move / IV on the post-print expiry before vs after.
                A short-premium structure's P&L should come from here and from
                theta, not from delta.
  3. DIRECTION -- the sign of the day-0 move against each brain's centre (most
                claimed centre 0; a P&L that came from delta was not predicted).
  4. STRUCTURE P&L BY GREEK -- delta / gamma / vega / theta / spread on every
                open structure in the name, per account, from `alpha.attribution`,
                and the share of the actual P&L that came from the mechanism the
                brain claimed (vega+theta for a condor, gamma for a straddle).
  5. PSYCHOHISTORY -- resolve the shadow record against the realised bucket.

`--pre` writes `state/event_grade/<SYMBOL>_<expiry>_pre.json`; `--post` reads it.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config, ledger
from alpha.broker.alpaca import AlpacaPaper

logger = logging.getLogger(__name__)
OUT = Path("state") / "event_grade"


def _chain(client, symbol: str, expiry: str) -> dict:
    from alpha.data import chain as chain_mod

    snap = chain_mod.fetch(client, symbol, expiry_from=expiry, expiry_to=expiry)
    atm_c, atm_p = snap.atm(expiry, "C"), snap.atm(expiry, "P")
    return {
        "t": datetime.now(timezone.utc).isoformat(), "spot": snap.spot, "spot_source": snap.spot_source,
        "implied_move": snap.implied_move(expiry),
        "atm_iv_call": atm_c.implied_vol if atm_c else None, "atm_iv_put": atm_p.implied_vol if atm_p else None,
        "atm_strike": atm_c.strike if atm_c else None,
        "straddle_mid": ((atm_c.adjusted_mid or atm_c.mid) + (atm_p.adjusted_mid or atm_p.mid)) if atm_c and atm_p else None,
        "median_quote_age_s": round(snap.median_quote_age_seconds, 1), "market_open": snap.market_open,
    }


def _pre_forecasts(symbol: str, before_utc: str) -> dict:
    latest = {}
    for r in ledger.read_all("forecasts"):
        if r.get("symbol") != symbol or (r.get("ts_utc") or "") > before_utc:
            continue
        b = r.get("brain")
        if b and (b not in latest or r["ts_utc"] > latest[b]["ts_utc"]):
            latest[b] = r
    return {b: {"centre": r.get("predicted_move"), "sd": r.get("predicted_sd"), "ts": r.get("ts_utc"),
                "claim": ((r.get("outcome") or {}).get("claim")), "thesis": (r.get("thesis") or "")[:160]}
            for b, r in latest.items()}


def _day0_move(client, symbol: str, event_day: str) -> float | None:
    from alpha.brains.vol_gap import _daily_bars

    bars = _daily_bars(client, symbol, 30)
    days = [b["t"][:10] for b in bars]
    if event_day not in days:
        return None
    i = days.index(event_day)
    if i == 0:
        return None
    return math.log(float(bars[i]["c"]) / float(bars[i - 1]["c"]))


def _structures(symbol: str, roles: list[str]) -> dict:
    from alpha import attribution

    out = {}
    for role in roles:
        try:
            client = AlpacaPaper(role=role)
            rep = attribution.attribute_book(client, account_role=role)
        except Exception as exc:                                         # noqa: BLE001
            out[role] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        rows = []
        for att in rep.get("_structs") or []:
            if att.symbol != symbol:
                continue
            claimed = {"iron_condor": att.vega_usd + att.theta_usd, "long_straddle": att.gamma_usd + att.vega_usd,
                       "long_call": att.delta_usd, "long_put": att.delta_usd,
                       "long_shares": att.delta_usd, "short_shares": att.delta_usd}.get(att.kind, 0.0)
            rows.append({
                "kind": att.kind, "brain": att.brain, "contracts": att.contracts, "actual": round(att.actual_usd),
                "delta": round(att.delta_usd), "gamma": round(att.gamma_usd), "vega": round(att.vega_usd),
                "theta": round(att.theta_usd), "spread": round(att.spread_usd), "residual": round(att.residual_usd),
                "max_loss": round(att.max_loss_usd),
                "claimed_mechanism_usd": round(claimed),
                "share_from_claimed_mechanism": (round(claimed / att.actual_usd, 2) if abs(att.actual_usd) > 1 else None),
                "unclaimed_delta_usd": round(att.delta_usd) if att.kind in ("iron_condor", "long_straddle") else 0,
            })
        out[role] = {"structures": rows, "equity": rep.get("equity")}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--expiry", required=True)
    p.add_argument("--event-day", default=None, help="first reflecting close, YYYY-MM-DD (default: next session after now)")
    p.add_argument("--pre", action="store_true")
    p.add_argument("--post", action="store_true")
    p.add_argument("--day0-move", type=float, default=None, help="override if bars are not final")
    p.add_argument("--roles", default="dev,exp1")
    p.add_argument("--resolve", default=None, help="psychohistory record id to resolve with the realised move")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    config.load_env()
    OUT.mkdir(parents=True, exist_ok=True)
    sym = args.symbol.upper()
    pre_path = OUT / f"{sym}_{args.expiry}_pre.json"
    roles = [r for r in args.roles.split(",") if r]
    client = AlpacaPaper(role=roles[0])

    if args.pre:
        now = datetime.now(timezone.utc).isoformat()
        pre = {"symbol": sym, "expiry": args.expiry, "frozen_utc": now, "chain": _chain(client, sym, args.expiry),
               "brains": _pre_forecasts(sym, now), "structures_before": _structures(sym, roles)}
        pre_path.write_text(json.dumps(pre, indent=1), encoding="utf-8")
        print(f"pre-print baseline frozen -> {pre_path}")
        print(f"  chain: spot {pre['chain']['spot']}, implied {pre['chain']['implied_move']:.2%}, ATM IV {pre['chain']['atm_iv_call']}")
        for b, f in pre["brains"].items():
            print(f"  {b:22s} centre {f['centre']:+.2%} sd {f['sd']:.2%} claim {f['claim']}")
        for role, d in pre["structures_before"].items():
            for s in d.get("structures", []):
                print(f"  {role}: {s['kind']} x{s['contracts']} P&L {s['actual']:+,} (d {s['delta']:+,} g {s['gamma']:+,} v {s['vega']:+,} t {s['theta']:+,})")
        return 0

    if not args.post:
        p.error("--pre or --post")
    if not pre_path.exists():
        print(f"no pre baseline at {pre_path}; run --pre before the print. Grading without one is a guess.")
        return 1
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    post_chain = _chain(client, sym, args.expiry)
    event_day = args.event_day or datetime.now(timezone.utc).date().isoformat()
    move = args.day0_move if args.day0_move is not None else _day0_move(client, sym, event_day)
    grade = {"symbol": sym, "expiry": args.expiry, "graded_utc": datetime.now(timezone.utc).isoformat(),
             "event_day": event_day, "day0_move": move, "pre_chain": pre["chain"], "post_chain": post_chain}
    print(f"\n== {sym} print graded by component  (day-0 {event_day}, move {move:+.2%})" if move is not None else
          f"\n== {sym}: day-0 close not in bars yet; pass --day0-move")
    # 1. width
    print("\n1. WIDTH -- who was closest to the size of the move?")
    im = pre["chain"]["implied_move"]
    rows = [("chain implied", im, 0.0)] + [(b, f["sd"], f["centre"] or 0.0) for b, f in pre["brains"].items()]
    width = []
    for name, sd, centre in rows:
        err = (abs(move) - sd) if move is not None else None
        z = ((move - centre) / sd) if (move is not None and sd) else None
        width.append({"who": name, "sd_or_implied": sd, "centre": centre, "abs_move_minus_width": err, "z": z})
        print(f"   {name:22s} width {sd:.2%}  centre {centre:+.2%}" + (f"  |move|-width {err:+.2%}  z {z:+.2f}" if err is not None else ""))
    grade["width"] = width
    # 2. crush
    print("\n2. CRUSH -- the post-print expiry before vs after")
    c0, c1 = pre["chain"], post_chain
    crush = {"implied_before": c0["implied_move"], "implied_after": c1["implied_move"],
             "iv_before": c0["atm_iv_call"], "iv_after": c1["atm_iv_call"],
             "straddle_before": c0["straddle_mid"], "straddle_after": c1["straddle_mid"]}
    grade["crush"] = crush
    if c0["implied_move"] and c1["implied_move"]:
        print(f"   implied move {c0['implied_move']:.2%} -> {c1['implied_move']:.2%}; ATM IV {c0['atm_iv_call']} -> {c1['atm_iv_call']}; "
              f"straddle {c0['straddle_mid']} -> {c1['straddle_mid']}")
    # 3. direction
    print("\n3. DIRECTION -- did anyone claim the sign?")
    for b, f in pre["brains"].items():
        c = f["centre"] or 0.0
        verdict = "claimed nothing" if abs(c) < 1e-4 else ("RIGHT" if (move or 0) * c > 0 else "WRONG")
        print(f"   {b:22s} centre {c:+.2%} -> {verdict}")
    # 4. structures
    print("\n4. STRUCTURE P&L BY GREEK, and the share from the CLAIMED mechanism")
    after = _structures(sym, roles)
    grade["structures_after"] = after
    for role, d in after.items():
        for s in d.get("structures", []):
            print(f"   {role}: {s['kind']:14s} x{s['contracts']:<3d} {s['brain'][:12]:12s} P&L {s['actual']:+,} = d {s['delta']:+,} g {s['gamma']:+,} "
                  f"v {s['vega']:+,} t {s['theta']:+,} spr {s['spread']:+,} | from claimed mechanism {s['claimed_mechanism_usd']:+,} "
                  f"({s['share_from_claimed_mechanism']}) | unclaimed delta {s['unclaimed_delta_usd']:+,}")
    # 5. psychohistory
    if args.resolve and move is not None:
        from alpha import psychohistory as ph

        rec = next((r for r in ph.read_all() if r["id"] == args.resolve), None)
        if rec:
            out = ph.resolve(rec, day0_move=move, notes="resolved by scripts.event_grade")
            ph.append(ph.Record(**{k: (out if k == "outcome" else rec[k]) for k in ph.Record.__dataclass_fields__}))
            grade["psychohistory"] = out
            print(f"\n5. PSYCHOHISTORY {args.resolve}: realised {out['realised_bucket']} | Brier model {out['brier_model']} vs market "
                  f"{out['brier_market']} -> {'MODEL' if out['model_beat_market'] else 'MARKET'} better | scenario: {out.get('scenario_realised')}")
    path = OUT / f"{sym}_{args.expiry}_post.json"
    path.write_text(json.dumps(grade, indent=1, default=str), encoding="utf-8")
    print(f"\nreceipt -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
