"""ATTENTION_VOL_BASIS -- does attention move REALISED more than it moves IMPLIED?

    AAT_ACCOUNT_ROLE=dev python -m scripts.attention_vol_basis

`attention_backtest` found a Wikipedia pageview spike (z > 2) widens the next
day's |return| by ~27%. That is not an edge: if the chain also widens by 27% on
the same days there is nothing to buy. The attention brains widen sigma by
construction and therefore win the long-premium comparison by construction --
so their promotion rule has to be this number, not the raw widening:

    basis  =  E[ |r_(t+1)| / iv_t ]_spike   -   E[ |r_(t+1)| / iv_t ]_control

where iv_t is the ATM straddle-implied daily vol at the close of day t (the
first close at which the day-t pageview count is knowable), from EXPIRED
option bars at the nearest weekly with >= 3 sessions left. The control set is
every fifth non-spike day of the same name. Also reported: the IV CHANGE into
the spike (iv_t - iv_(t-1)) -- how much the chain already noticed.

A positive basis says attention predicts movement the chain did not price. A
zero or negative basis says the chain already knows, and the attention brains
should stay in shadow. Closes; every row is in the receipt.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper
from alpha.sources.attention import WIKI, WIKI_ARTICLE
from alpha.sources.http import get_json
from scripts.event_surface_backtest import bars_for, close_on, inc_for, occ, straddle_iv

DEFAULT = ["TSLA", "NVDA", "AVGO", "AMD", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "NIO", "PANW", "MU"]
CONTROL_EVERY = 5


def next_friday_after(d: date, min_days: int) -> date:
    x = d + timedelta(days=min_days)
    return x + timedelta(days=(4 - x.weekday()) % 7)


def iv_on(client, sym: str, day_prev: str, day: str, spot_prev: float, spot: float) -> dict | None:
    exp = next_friday_after(date.fromisoformat(day), 4)
    for inc in inc_for(spot_prev)[:2]:
        k = round(spot_prev / inc) * inc
        syms = [occ(sym, exp, r, k) for r in "CP"]
        bars = bars_for(client, syms, day_prev, day)
        vals = {}
        for d, s in ((day_prev, spot_prev), (day, spot)):
            c, p = close_on(bars, syms[0], d), close_on(bars, syms[1], d)
            if c is None or p is None:
                break
            t = max((exp - date.fromisoformat(d)).days, 1) / 365.0
            iv = straddle_iv(c + p, s, k, t)
            if iv is None:
                break
            vals[d] = iv
        if len(vals) == 2:
            return {"expiry": exp.isoformat(), "strike": k, "iv_prev": vals[day_prev], "iv": vals[day]}
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=DEFAULT)
    p.add_argument("--start", default="20240801")
    p.add_argument("--z", type=float, default=2.0)
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    end = datetime.now(timezone.utc).strftime("%Y%m%d")
    rows = []
    for sym in args.symbols:
        art = WIKI_ARTICLE.get(sym)
        if not art:
            continue
        data, _ = get_json(f"{WIKI}/{art}/daily/{args.start}/{end}")
        views = {it["timestamp"][:8]: int(it["views"]) for it in data.get("items", [])}
        bars = client.stock_bars(sym, start=f"{args.start[:4]}-{args.start[4:6]}-{args.start[6:]}",
                                 timeframe="1Day", adjustment="raw")["bars"][sym]
        days = [b["t"][:10] for b in bars]
        closes = [float(b["c"]) for b in bars]
        n_ctrl = 0
        got = 0
        for i in range(31, len(days) - 1):
            d8 = days[i].replace("-", "")
            if d8 not in views:
                continue
            base = [views[x.replace("-", "")] for x in days[i - 30:i] if x.replace("-", "") in views]
            if len(base) < 20:
                continue
            sd = statistics.pstdev(base) or 1.0
            z = (views[d8] - statistics.mean(base)) / sd
            spike = z > args.z
            if not spike:
                n_ctrl += 1
                if n_ctrl % CONTROL_EVERY:
                    continue
            ivs = iv_on(client, sym, days[i - 1], days[i], closes[i - 1], closes[i])
            if not ivs:
                continue
            r_next = math.log(closes[i + 1] / closes[i])
            daily_iv = ivs["iv"] / math.sqrt(252)
            rows.append({"symbol": sym, "day": days[i], "z": round(z, 2), "spike": spike, **ivs,
                         "d_iv": round(ivs["iv"] - ivs["iv_prev"], 4), "r_next": round(r_next, 5),
                         "u_next": round(abs(r_next) / daily_iv, 3) if daily_iv else None})
            got += 1
        print(f"{sym}: {got} rows ({sum(1 for r in rows if r['symbol'] == sym and r['spike'])} spikes)")

    def side(rs):
        u = [r["u_next"] for r in rs if r["u_next"] is not None]
        if len(u) < 5:
            return {"n": len(u)}
        return {"n": len(u), "mean_u": round(statistics.mean(u), 3), "median_u": round(statistics.median(u), 3),
                "mean_d_iv": round(statistics.mean(r["d_iv"] for r in rs), 4),
                "mean_iv": round(statistics.mean(r["iv"] for r in rs), 4),
                "mean_abs_r_next_bp": round(statistics.mean(abs(r["r_next"]) for r in rs) * 1e4, 1),
                "share_u_gt_1": round(sum(1 for x in u if x > 1) / len(u), 3)}

    sp, ct = [r for r in rows if r["spike"]], [r for r in rows if not r["spike"]]
    s_sp, s_ct = side(sp), side(ct)
    basis = (s_sp.get("mean_u", 0) - s_ct.get("mean_u", 0)) if s_sp.get("n", 0) >= 5 and s_ct.get("n", 0) >= 5 else None
    # t on the difference of u
    t = None
    if basis is not None:
        u1, u0 = [r["u_next"] for r in sp], [r["u_next"] for r in ct]
        se = math.sqrt(statistics.pvariance(u1) / len(u1) + statistics.pvariance(u0) / len(u0))
        t = round(basis / se, 2) if se else None
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "z_threshold": args.z,
           "spike": s_sp, "control": s_ct, "basis_u": round(basis, 3) if basis is not None else None, "t": t,
           "verdict": ("attention predicts movement the chain did not price -- promotion candidate" if basis and t and t > 2
                       else "the chain already knows: attention brains stay in shadow"),
           "rows": rows}
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    path = config.__file__.rsplit("alpha", 1)[0] + "state/attention_vol_basis.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print("written:", path, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
