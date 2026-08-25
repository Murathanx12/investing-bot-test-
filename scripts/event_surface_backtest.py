"""EVENT_SURFACE_BACKTEST -- strip the event variance, test SHORT structures, read the
skew. All walk-forward, on the same 117 SEC-dated prints and the same expired closes.

    AAT_ACCOUNT_ROLE=dev python -m scripts.event_surface_backtest
    AAT_ACCOUNT_ROLE=dev python -m scripts.event_surface_backtest --reuse   # re-analyse stored rows

Three corrections to docs/FINDING_2026-08-25_STRADDLE_BACKTEST.md, in one pull:

1. EVENT_VARIANCE_STRIP. The front straddle prices the print PLUS a few ordinary
   days plus a premium. Two expiries solve for both parts:

       sigma_f^2 * T_f = a * T_f + J        (front, spans the print)
       sigma_b^2 * T_b = a * T_b + J        (back, spans it too)

   so a = (sigma_b^2 T_b - sigma_f^2 T_f) / (T_b - T_f) and J = sigma_f^2 T_f - a T_f.
   sqrt(J) is the MARKET's event jump sd. The comparison becomes our jump sd
   (from the name's prior prints) against the market's jump sd -- two clean
   quantities instead of two contaminated ones.

2. SHORT STRUCTURES AT THE SAME CLOSES. "Long straddle loses" does not prove
   "iron condor wins": the loss can be theta and central gamma while a short
   structure still dies in the wings. Iron butterfly, iron condor, strangle,
   debit spreads and no-trade are priced on exactly the same events.

3. WALK-FORWARD. Event t sees only events < t: the name's prior is its earlier
   prints; the tercile cut-offs are the quantiles of gaps observed BEFORE t.
   No full-sample statistic enters an earlier decision.

Plus SKEW_DIRECTION at entry: IV(call K+w) - IV(put K-w), graded against the
signed move; and the surface's CURVATURE (wings vs ATM), graded against realised
size and straddle return (Alexiou et al., RoF 2025: concave = bimodal = paid for).

Closes, not crossed quotes. Every contract and price is in the receipt.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data.chain import _bs_price

R = 0.045
RECENT = 8
MIN_PRIOR_NAME = 3
MIN_PRIOR_POOL = 9
STRUCTURES = ("long_straddle", "long_strangle", "iron_butterfly", "iron_condor",
              "call_debit_spread", "put_debit_spread", "no_trade")


def occ(sym: str, expiry: date, right: str, k: float) -> str:
    return f"{sym}{expiry:%y%m%d}{right}{int(round(k * 1000)):08d}"


def _invert(price: float, f) -> float | None:
    lo, hi = 1e-4, 6.0
    if price <= 0 or f(hi) < price or f(lo) > price:
        return None
    for _ in range(80):
        m = (lo + hi) / 2.0
        if f(m) < price:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2.0


def iv_from_price(price: float, s: float, k: float, t: float, right: str) -> float | None:
    if t <= 0:
        return None
    return _invert(price, lambda v: _bs_price(s, k, t, v, right, R))


def straddle_iv(price: float, s: float, k: float, t: float) -> float | None:
    if t <= 0:
        return None
    return _invert(price, lambda v: _bs_price(s, k, t, v, "C", R) + _bs_price(s, k, t, v, "P", R))


def bars_for(client, syms: list[str], start: str, end: str) -> dict:
    out: dict = {}
    for i in range(0, len(syms), 100):
        try:
            page = client._request("GET", "/v1beta1/options/bars", base=config.data_url(),
                                   params={"symbols": ",".join(syms[i:i + 100]), "timeframe": "1Day",
                                           "start": start, "end": end, "limit": 1000})
        except BrokerRefusal:
            continue
        out.update((page or {}).get("bars") or {})
    return out


def close_on(bars: dict, sym: str, day: str) -> float | None:
    for b in bars.get(sym) or []:
        if b["t"][:10] == day:
            return float(b["c"])
    return None


def inc_for(spot: float) -> list[float]:
    base = 1.0 if spot < 50 else 2.5 if spot < 200 else 5.0 if spot < 600 else 10.0
    return [base] + [x for x in (5.0, 2.5, 1.0, 10.0) if x != base]


def one_event(client, ev: dict) -> dict | None:
    sym, entry, exit_ = ev["symbol"], ev["entry_day"], ev["event_day"]
    k, spot = float(ev["strike"]), float(ev["spot_entry"])
    fexp = date.fromisoformat(ev["expiry"])
    t_f = max((fexp - date.fromisoformat(entry)).days, 1) / 365.0
    for inc in inc_for(spot):
        w = max(inc, round(ev["implied_move"] * spot / inc) * inc)
        strikes = {"K": k, "Ku": k + w, "Kd": k - w, "Ku2": k + 2 * w, "Kd2": k - 2 * w}
        front = {f"{name}_{r}": occ(sym, fexp, r, ks) for name, ks in strikes.items() for r in "CP"}
        backs = {d: {r: occ(sym, fexp + timedelta(days=d), r, k) for r in "CP"} for d in (7, 14)}
        syms = list(front.values()) + [s for b in backs.values() for s in b.values()]
        bars = bars_for(client, syms, entry, exit_)
        px = {}
        ok = True
        for name, s in front.items():
            e, x = close_on(bars, s, entry), close_on(bars, s, exit_)
            if e is None or x is None:
                if name.startswith(("Ku2", "Kd2")):
                    continue            # the condor's outer wings are optional
                ok = False
                break
            px[name] = (e, x)
        if not ok:
            continue
        back = None
        for d in (7, 14):
            ce, pe = close_on(bars, backs[d]["C"], entry), close_on(bars, backs[d]["P"], entry)
            if ce is not None and pe is not None:
                back = (d, ce + pe)
                break
        if back is None:
            continue
        return build(ev, k, w, t_f, px, back, spot)
    return None


def build(ev: dict, k: float, w: float, t_f: float, px: dict, back: tuple, spot: float) -> dict:
    e = {n: v[0] for n, v in px.items()}
    x = {n: v[1] for n, v in px.items()}
    # --- variance strip
    straddle_f = e["K_C"] + e["K_P"]
    iv_f = straddle_iv(straddle_f, spot, k, t_f)
    t_b = t_f + back[0] / 365.0
    iv_b = straddle_iv(back[1], spot, k, t_b)
    strip = None
    if iv_f and iv_b:
        vf, vb = iv_f ** 2 * t_f, iv_b ** 2 * t_b
        a = max((vb - vf) / (t_b - t_f), 0.0)
        j = max(vf - a * t_f, 0.0)
        strip = {"iv_front": round(iv_f, 4), "iv_back": round(iv_b, 4), "t_front_days": round(t_f * 365),
                 "t_back_days": round(t_b * 365), "ambient_var_annual": round(a, 5),
                 "ambient_daily_sd": round(math.sqrt(a / 252), 5) if a > 0 else 0.0,
                 "market_jump_sd": round(math.sqrt(j), 5),
                 "event_share_of_front_var": round(j / vf, 3) if vf else None,
                 "back_straddle": round(back[1], 2), "back_offset_days": back[0]}
    # --- skew and curvature at entry
    ivs = {n: (iv_from_price(e[n], spot, ks, t_f, n[-1]) if n in e else None) for n, ks in
           (("K_C", k), ("K_P", k), ("Ku_C", k + w), ("Kd_P", k - w), ("Ku2_C", k + 2 * w), ("Kd2_P", k - 2 * w))}
    surf = None
    if all(ivs[n] for n in ("K_C", "K_P", "Ku_C", "Kd_P")):
        atm = (ivs["K_C"] + ivs["K_P"]) / 2
        surf = {"iv_atm": round(atm, 4), "iv_call_up": round(ivs["Ku_C"], 4), "iv_put_down": round(ivs["Kd_P"], 4),
                "skew": round(ivs["Ku_C"] - ivs["Kd_P"], 4),
                "curvature": round((ivs["Ku_C"] + ivs["Kd_P"]) / 2 - atm, 4),
                "wing_moneyness": round(w / spot, 4)}
        if ivs["Ku2_C"] and ivs["Kd2_P"]:
            surf["curvature_2w"] = round((ivs["Ku2_C"] + ivs["Kd2_P"]) / 2 - atm, 4)

    # --- structures: pnl per share over max loss
    def ror(pnl: float, risk: float) -> float | None:
        return round(pnl / risk, 4) if risk > 0 else None

    structs = {}
    cost = straddle_f
    structs["long_straddle"] = ror((x["K_C"] + x["K_P"]) - cost, cost)
    cost = e["Ku_C"] + e["Kd_P"]
    structs["long_strangle"] = ror((x["Ku_C"] + x["Kd_P"]) - cost, cost)
    credit = straddle_f - (e["Ku_C"] + e["Kd_P"])
    structs["iron_butterfly"] = ror(credit - ((x["K_C"] + x["K_P"]) - (x["Ku_C"] + x["Kd_P"])), w - credit)
    if "Ku2_C" in e and "Kd2_P" in e:
        credit = (e["Ku_C"] + e["Kd_P"]) - (e["Ku2_C"] + e["Kd2_P"])
        structs["iron_condor"] = ror(credit - ((x["Ku_C"] + x["Kd_P"]) - (x["Ku2_C"] + x["Kd2_P"])), w - credit)
    else:
        structs["iron_condor"] = None
    debit = e["K_C"] - e["Ku_C"]
    structs["call_debit_spread"] = ror((x["K_C"] - x["Ku_C"]) - debit, debit)
    debit = e["K_P"] - e["Kd_P"]
    structs["put_debit_spread"] = ror((x["K_P"] - x["Kd_P"]) - debit, debit)
    structs["no_trade"] = 0.0
    keep = ("symbol", "event_day", "entry_day", "expiry", "strike", "spot_entry",
            "implied_move", "realised_abs_move", "signed_move", "straddle_return")
    return {**{key: ev[key] for key in keep},
            "wing": w, "strip": strip, "surface": surf, "structures": structs,
            "entry_prices": {n: round(v, 2) for n, v in e.items()},
            "exit_prices": {n: round(v, 2) for n, v in x.items()}}


# ----------------------------------------------------------------- analysis
def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) < 4:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = math.sqrt(sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b))
    return round(num / den, 3) if den else None


def _stats(v: list[float]) -> dict:
    v = [z for z in v if z is not None]
    if not v:
        return {"n": 0}
    m, sd = statistics.mean(v), statistics.pstdev(v)
    return {"n": len(v), "mean_ror": round(m, 3), "median_ror": round(statistics.median(v), 3),
            "hit": round(sum(1 for z in v if z > 0) / len(v), 2),
            "t": round(m / (sd / math.sqrt(len(v))), 2) if sd and len(v) > 2 else None}


def assign_walkforward(rows: list[dict]) -> list[dict]:
    """Every row's prior, gap and tercile bucket use ONLY earlier rows."""
    rows = sorted(rows, key=lambda r: r["entry_day"])
    by_name: dict[str, list[dict]] = {}
    pools: dict[str, list[float]] = {"naive": [], "strip": []}
    for r in rows:
        prior = by_name.get(r["symbol"], [])[-RECENT:]
        r["prior_n"] = len(prior)
        if len(prior) >= MIN_PRIOR_NAME:
            our_jump_sd = math.sqrt(sum(p["signed_move"] ** 2 for p in prior) / len(prior))
            our_mean_abs = sum(p["realised_abs_move"] for p in prior) / len(prior)
            r["our_jump_sd"] = round(our_jump_sd, 4)
            r["gap_naive"] = round(our_mean_abs - r["implied_move"], 4)
            r["gap_strip"] = round(our_jump_sd - r["strip"]["market_jump_sd"], 4) if r.get("strip") else None
            for kind in ("naive", "strip"):
                g = r.get(f"gap_{kind}")
                if g is None:
                    continue
                pool = pools[kind]
                if len(pool) >= MIN_PRIOR_POOL:
                    s = sorted(pool)
                    lo, hi = s[len(s) // 3], s[2 * len(s) // 3]
                    r[f"bucket_{kind}"] = "top" if g > hi else "bottom" if g < lo else "middle"
                pool.append(g)
        by_name.setdefault(r["symbol"], []).append(r)
    return rows


def summarise(rows: list[dict]) -> dict:
    rows = assign_walkforward(rows)

    def bucket_table(kind: str) -> dict:
        out = {}
        for b in ("top", "middle", "bottom"):
            rs = [r for r in rows if r.get(f"bucket_{kind}") == b]
            if rs:
                out[b] = {"n": len(rs), **{s: _stats([r["structures"][s] for r in rs]) for s in STRUCTURES if s != "no_trade"}}
        return out

    def policy(kind: str) -> dict:
        seq = []
        for r in rows:
            b = r.get(f"bucket_{kind}")
            if b == "top":
                seq.append(r["structures"]["long_straddle"])
            elif b == "bottom":
                seq.append(r["structures"]["iron_butterfly"])
        return {**_stats(seq), "rule": "top tercile -> long straddle; bottom -> iron butterfly; middle -> no trade"}

    sk = [r for r in rows if r.get("surface")]
    signed = [r for r in sk if abs(r["surface"]["skew"]) > 0.005]
    hits = [(r["surface"]["skew"] > 0) == (r["signed_move"] > 0) for r in signed]
    strong = sorted(sk, key=lambda r: abs(r["surface"]["skew"]))[-max(len(sk) // 3, 1):]
    hits_strong = [(r["surface"]["skew"] > 0) == (r["signed_move"] > 0) for r in strong]
    # A directional policy from the skew: call spread when skew > 0, put spread when < 0.
    dir_seq = [r["structures"]["call_debit_spread"] if r["surface"]["skew"] > 0 else r["structures"]["put_debit_spread"]
               for r in strong]
    skew_out = {"n": len(hits), "direction_hit": round(sum(hits) / len(hits), 3) if hits else None,
                "n_strong_tercile": len(hits_strong),
                "direction_hit_strong": round(sum(hits_strong) / len(hits_strong), 3) if hits_strong else None,
                "mean_skew": round(statistics.mean(r["surface"]["skew"] for r in sk), 4) if sk else None,
                "corr_skew_signed_move": _corr([r["surface"]["skew"] for r in sk], [r["signed_move"] for r in sk]),
                "debit_spread_in_skew_direction_strong": _stats(dir_seq)}

    cv = [r for r in sk if r["surface"].get("curvature") is not None]

    def side(rs):
        if not rs:
            return {"n": 0}
        return {"n": len(rs), "median_realised_abs": round(statistics.median(r["realised_abs_move"] for r in rs), 4),
                "median_implied": round(statistics.median(r["implied_move"] for r in rs), 4),
                "long_straddle": _stats([r["structures"]["long_straddle"] for r in rs]),
                "iron_butterfly": _stats([r["structures"]["iron_butterfly"] for r in rs])}

    curv_out = {"concave_wings_below_atm": side([r for r in cv if r["surface"]["curvature"] < 0]),
                "convex_wings_above_atm": side([r for r in cv if r["surface"]["curvature"] >= 0])}

    st = [r for r in rows if r.get("strip")]
    wf = [r for r in rows if r.get("our_jump_sd")]
    strip_out = {"n": len(st),
                 "median_event_share_of_front_var": round(statistics.median(r["strip"]["event_share_of_front_var"] for r in st), 3) if st else None,
                 "median_market_jump_sd": round(statistics.median(r["strip"]["market_jump_sd"] for r in st), 4) if st else None,
                 "median_raw_implied": round(statistics.median(r["implied_move"] for r in st), 4) if st else None,
                 "median_realised_abs": round(statistics.median(r["realised_abs_move"] for r in st), 4) if st else None,
                 "corr_market_jump_vs_realised": _corr([r["strip"]["market_jump_sd"] for r in st], [r["realised_abs_move"] for r in st]),
                 "corr_raw_implied_vs_realised": _corr([r["implied_move"] for r in st], [r["realised_abs_move"] for r in st]),
                 "corr_our_prior_vs_realised_walkforward": _corr([r["our_jump_sd"] for r in wf], [r["realised_abs_move"] for r in wf]),
                 "n_walkforward": len(wf)}
    return {"n_rows": len(rows), "variance_strip": strip_out,
            "unconditional_structures": {s: _stats([r["structures"][s] for r in rows]) for s in STRUCTURES if s != "no_trade"},
            "walkforward_buckets_naive": bucket_table("naive"), "walkforward_buckets_strip": bucket_table("strip"),
            "policy_naive": policy("naive"), "policy_strip": policy("strip"),
            "skew_direction": skew_out, "curvature": curv_out}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--reuse", action="store_true", help="re-analyse the stored rows without pulling")
    args = p.parse_args()
    config.load_env()
    root = config.__file__.rsplit("alpha", 1)[0]
    out_path = root + "state/event_surface_backtest.json"
    if args.reuse:
        rows = json.load(open(out_path, encoding="utf-8"))["rows"]
    else:
        client = AlpacaPaper()
        events = json.load(open(root + "state/event_straddle_backtest.json", encoding="utf-8"))["events"]
        if args.symbols:
            events = [e for e in events if e["symbol"] in args.symbols]
        rows, missed = [], []
        for ev in events:
            r = one_event(client, ev)
            if r is None:
                missed.append(f"{ev['symbol']} {ev['event_day']}")
                continue
            rows.append(r)
            st, su, sx = r.get("strip") or {}, r.get("surface") or {}, r["structures"]
            print(f"{r['symbol']:5} {r['event_day']} w={r['wing']:<5} jump_mkt {st.get('market_jump_sd', float('nan')):6.2%} "
                  f"raw {r['implied_move']:6.2%} real {r['signed_move']:+6.2%} skew {su.get('skew', float('nan')):+.3f} "
                  f"curv {su.get('curvature', float('nan')):+.3f} strad {sx['long_straddle']:+.2f} "
                  f"bfly {sx['iron_butterfly']:+.2f} condor {sx['iron_condor'] if sx['iron_condor'] is not None else float('nan'):+.2f}")
        print(f"{len(rows)} reconstructed, {len(missed)} missed: {missed}")
    if not rows:
        return 1
    summary = summarise(rows)
    print(json.dumps(summary, indent=1))
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(), "rows": rows, "summary": summary}, fh, indent=1)
    print("written:", out_path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
