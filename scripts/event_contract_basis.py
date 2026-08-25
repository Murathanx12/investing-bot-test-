"""EVENT_CONTRACT_BASIS_v1 -- one market prices the jobs number, another prices
its equity consequence. Trade the inconsistency, not the straddle.

    AAT_ACCOUNT_ROLE=dev python -m scripts.event_contract_basis --release 2026-09-04

Endpoints we already hold:

  Kalshi KXPAYROLLS      P(headline > x) for a ladder of x        -> a histogram
  ALFRED PAYEMS vintages the FIRST-PRINT headline of every past release, as it
                         was known that morning (no revisions leaking backwards)
  nfp_straddle_backtest  SPY's move from the prior close to 10:45 ET on each of
                         those releases, and the 0DTE straddle's implied move
  SPY chain today        the expiry spanning the release, stripped against the
                         next one for the market's event jump sd

Model, deliberately small (28 releases cannot carry more):

  surprise_t   = first_print_t - mean(previous three first prints)     [public at t]
  move_t       = beta * surprise_t + eps,   eps ~ N(0, s_resid)         [fit on t' < t]

Today: Kalshi ladder -> bucket probabilities -> surprise per bucket -> a MIXTURE
of normals for SPY's move -> its sd and its P(|move| > straddle break-even).
Compare with the chain. The basis is the disagreement, and the direction of the
disagreement chooses the structure. Written to state/event_contract_basis/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

from alpha import config, surface
from alpha.broker.alpaca import AlpacaPaper
from alpha.data import chain as chain_mod
from alpha.sources.belief import kalshi_markets
from alpha.sources.http import get_json


def first_prints(key: str, start: str = "2023-10-01") -> dict[str, int]:
    """release_date -> first-print headline change (thousands), from ALFRED vintages."""
    d, _ = get_json("https://api.stlouisfed.org/fred/series/observations",
                    {"series_id": "PAYEMS", "api_key": key, "file_type": "json", "observation_start": start,
                     "realtime_start": "2024-01-01", "realtime_end": "9999-12-31", "output_type": "2"})
    obs = d["observations"]
    vintages = sorted({k for o in obs for k in o if k.startswith("PAYEMS_")})
    out = {}
    for v in vintages:
        col = [(o["date"], o.get(v)) for o in obs if o.get(v) not in (None, ".")]
        if len(col) < 2:
            continue
        (_, prev), (_, last) = col[-2], col[-1]
        rel = f"{v[7:11]}-{v[11:13]}-{v[13:15]}"
        out[rel] = int(float(last)) - int(float(prev))
    return out


def ladder_to_buckets(markets: list[dict]) -> list[dict]:
    """P(above x) ladder -> bucket probabilities with midpoints (thousands)."""
    pts = []
    for m in markets:
        t = m["ticker"].rsplit("-T", 1)[-1]
        try:
            x = int(t)
        except ValueError:
            continue
        p = m.get("last") if m.get("last") is not None else (m.get("yes_bid", 0) + m.get("yes_ask", 0)) / 2
        pts.append((x / 1000.0, float(p)))
    pts.sort()
    # enforce monotone non-increasing P(above x)
    for i in range(1, len(pts)):
        pts[i] = (pts[i][0], min(pts[i][1], pts[i - 1][1]))
    buckets = []
    prev_x, prev_p = None, 1.0
    for x, p in pts:
        prob = prev_p - p
        mid = (x - 50) if prev_x is None else (prev_x + x) / 2
        buckets.append({"lo": prev_x, "hi": x, "mid": mid, "p": round(prob, 4)})
        prev_x, prev_p = x, p
    buckets.append({"lo": prev_x, "hi": None, "mid": prev_x + 50, "p": round(prev_p, 4)})
    return [b for b in buckets if b["p"] > 0]


def fit(rows: list[dict]) -> dict:
    x = [r["surprise"] for r in rows]
    y = [r["move"] for r in rows]
    mx, my = statistics.mean(x), statistics.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    beta = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else 0.0
    alpha = my - beta * mx
    resid = [b - (alpha + beta * a) for a, b in zip(x, y)]
    return {"n": len(rows), "alpha": alpha, "beta_per_100k": beta, "s_resid": statistics.pstdev(resid),
            "s_total": statistics.pstdev(y), "corr": (beta * math.sqrt(sxx / len(x)) / statistics.pstdev(y)) if statistics.pstdev(y) else 0.0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release", default="2026-09-04")
    p.add_argument("--symbol", default="SPY")
    args = p.parse_args()
    config.load_env()
    key = os.getenv("AAT_FRED_API_KEY", "").strip()
    root = config.__file__.rsplit("alpha", 1)[0]
    client = AlpacaPaper()

    prints = first_prints(key)
    nfp = json.load(open(root + "state/nfp_straddle_backtest.json", encoding="utf-8"))["rows"]
    hist = []
    rel_sorted = sorted(prints)
    for r in nfp:
        if r["symbol"] != args.symbol or r.get("move_to_1045") is None:
            continue
        rel = r["release"]
        if rel not in prints:
            continue
        prior = [prints[d] for d in rel_sorted if d < rel][-3:]
        if len(prior) < 3:
            continue
        hist.append({"release": rel, "first_print": prints[rel], "prior3_mean": statistics.mean(prior),
                     "surprise": (prints[rel] - statistics.mean(prior)) / 100.0,   # units: 100k jobs
                     "move": r["move_to_1045"], "implied_move_0dte": r["implied_move"],
                     "straddle_return": r["straddle_return"]})
    for h in hist:
        h["surprise"] = round(h["surprise"], 4)          # units: hundreds of thousands of jobs
    hist.sort(key=lambda h: h["release"])
    print(f"{len(hist)} releases with first print, prior-3 mean and 10:45 move")
    for h in hist:
        print(f"  {h['release']} print {h['first_print']:+5d}k prior3 {h['prior3_mean']:+7.0f}k surprise {h["surprise"]*100:+6.0f}k "
              f"move {h['move']:+.2%} straddle {h['straddle_return']:+.0%}")
    full = fit(hist)
    # walk-forward residual check: fit on t' < t, score |move| forecast vs the 0DTE implied
    wf = []
    for i in range(10, len(hist)):
        f = fit(hist[:i])
        h = hist[i]
        mu = f["alpha"] + f["beta_per_100k"] * h["surprise"]
        wf.append({"release": h["release"], "pred_centre": mu, "s_resid": f["s_resid"], "move": h["move"]})
    print(json.dumps({"fit_full": {k: round(v, 5) for k, v in full.items()}}, indent=1))

    # ---- today: Kalshi ladder -> mixture
    series = f"KXPAYROLLS"
    markets = kalshi_markets(series, closes_before=(datetime.fromisoformat(args.release) + timedelta(days=2)).strftime("%Y-%m-%d"))
    markets = [m for m in markets if m.get("close_time", "").startswith(args.release)]
    buckets = ladder_to_buckets(markets)
    prior3 = statistics.mean([prints[d] for d in rel_sorted[-3:]])
    mix = []
    for b in buckets:
        surprise = (b["mid"] - prior3) / 100.0
        mu = full["alpha"] + full["beta_per_100k"] * surprise
        mix.append({**b, "surprise": round(surprise, 3), "centre": round(mu, 5), "sd": round(full["s_resid"], 5)})
    m_mean = sum(c["p"] * c["centre"] for c in mix)
    m_var = sum(c["p"] * (c["sd"] ** 2 + (c["centre"] - m_mean) ** 2) for c in mix)
    m_sd = math.sqrt(m_var)
    crowd_expected_print = sum(c["p"] * c["mid"] for c in mix)

    # ---- the chain: expiry spanning the release, stripped against the next one
    back = (datetime.fromisoformat(args.release) + timedelta(days=7)).strftime("%Y-%m-%d")
    chain_out = None
    try:
        snap = chain_mod.fetch(client, args.symbol, expiry_from=args.release, expiry_to=back)
        reading = surface.read(snap, event_before=args.release)
        chain_out = {"front": reading["expiries"][0] if reading["expiries"] else None, "strip": reading.get("strip")}
    except Exception as exc:                                    # noqa: BLE001
        chain_out = {"refusal": f"{type(exc).__name__}: {str(exc)[:140]}"}

    def p_beyond(be: float) -> float:
        tot = 0.0
        for c in mix:
            z1, z2 = (be - c["centre"]) / c["sd"], (-be - c["centre"]) / c["sd"]
            tot += c["p"] * ((1 - _cdf(z1)) + _cdf(z2))
        return tot

    basis = {"release": args.release, "symbol": args.symbol, "generated_utc": datetime.now(timezone.utc).isoformat(),
             "history": hist, "fit": {k: round(v, 5) for k, v in full.items()}, "walkforward": wf,
             "kalshi_buckets": mix, "crowd_expected_print_k": round(crowd_expected_print, 1),
             "prior3_mean_k": round(prior3), "aegis_move_centre": round(m_mean, 5), "aegis_move_sd": round(m_sd, 5),
             "chain": chain_out}
    mkt_jump = (chain_out.get("strip") or {}).get("market_jump_sd") if chain_out else None
    if mkt_jump:
        basis["market_jump_sd_to_expiry"] = mkt_jump
        basis["note"] = ("market_jump_sd is the print's variance to the CLOSE of release day; aegis_move_sd is to "
                         "10:45 ET. They are not the same window -- compare the 0DTE implied at the prior close on "
                         "3 Sep, which the history column carries for past releases (median 0.77%).")
    be_hist = statistics.median(h["implied_move_0dte"] for h in hist)
    basis["p_beyond_typical_0dte_breakeven"] = round(p_beyond(be_hist), 3)
    basis["typical_0dte_breakeven"] = round(be_hist, 4)
    print(json.dumps({k: v for k, v in basis.items() if k not in ("history", "walkforward", "kalshi_buckets")}, indent=1))
    print("buckets:", json.dumps(mix))
    os.makedirs(root + "state/event_contract_basis", exist_ok=True)
    path = f"{root}state/event_contract_basis/{args.symbol}_{args.release}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(basis, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


if __name__ == "__main__":
    sys.exit(main())
