"""TIMEZONE_LEAD_v1 -- does the Asian session of a parent/supplier lead the US session of its ADR and customers?

    python -m scripts.night_timezone_lead [--years 3]

Taiwan closes 13:30 TST (01:30 ET) and Korea 15:30 KST (02:30 ET): both BEFORE the
US open. The US open gap should absorb the Asian session; the test is whether it
does. For each Asian parent (2330.TW->TSM, 005930.KS/000660.KS->MU etc.) and each
US name, regress the US OPEN->CLOSE log return on the Asian session return, and
the ADR's overnight GAP on the same. beta_gap ~ 1 and beta_oc ~ 0 = efficient;
beta_oc > 0 = under-reaction (a lead); beta_oc < 0 = over-reaction (a fade).
yfinance daily bars, no broker, no LLM. Receipt: `state/night_shadow/timezone_lead.json`.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

import yfinance as yf

OUT = Path("state") / "night_shadow" / "timezone_lead.json"
LEADS = {"2330.TW": ["TSM", "NVDA", "AMD", "AVGO", "AMAT", "LRCX", "SMH"],
         "000660.KS": ["MU", "NVDA", "SMH"], "005930.KS": ["MU", "AAPL", "SMH"],
         "^TWII": ["TSM", "SMH", "SPY"], "^KS11": ["MU", "SPY"], "^N225": ["SONY", "TM", "SPY"],
         "6758.T": ["SONY"], "7203.T": ["TM"], "9984.T": ["ARM"], "3231.TW": ["SMCI", "DELL"], "2317.TW": ["AAPL"],
         # is the Nikkei fade a JAPAN-ADR phenomenon? banks, autos, pharma, the country ETFs
         "^N225x": ["MUFG", "SMFG", "MFG", "HMC", "NMR", "TAK", "EWJ", "DXJ", "BBJP"]}
#: parent for the index pairs, so the index effect is measured GIVEN the parent's own session
PARENT = {"SONY": "6758.T", "TM": "7203.T", "MUFG": "8306.T", "SMFG": "8316.T", "MFG": "8411.T", "HMC": "7267.T",
          "NMR": "8604.T", "TAK": "4502.T", "TSM": "2330.TW", "MU": "000660.KS"}


def ols(x, y):
    n = len(x)
    if n < 30:
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    b = sxy / sxx if sxx else 0.0
    res = [yy - my - b * (xx - mx) for xx, yy in zip(x, y)]
    s2 = sum(r * r for r in res) / (n - 2)
    se = math.sqrt(s2 / sxx) if sxx else float("inf")
    syy = sum((yy - my) ** 2 for yy in y)
    r2 = 1 - sum(r * r for r in res) / syy if syy else 0
    return {"n": n, "beta": round(b, 3), "t": round(b / se, 2) if se else None, "r2": round(r2, 4)}


def ols2(g, x, y):
    """y = a + b1*gap + b2*asia: does Asia add anything beyond the US gap itself (Lou-Polk-Skouras tug of war)?"""
    n = len(y)
    if n < 30:
        return None
    mg, mx, my = statistics.mean(g), statistics.mean(x), statistics.mean(y)
    G = [a - mg for a in g]
    X = [a - mx for a in x]
    Y = [a - my for a in y]
    sgg = sum(a * a for a in G)
    sxx = sum(a * a for a in X)
    sgx = sum(a * b for a, b in zip(G, X))
    sgy = sum(a * b for a, b in zip(G, Y))
    sxy = sum(a * b for a, b in zip(X, Y))
    det = sgg * sxx - sgx * sgx
    if det <= 0:
        return None
    b1 = (sxx * sgy - sgx * sxy) / det
    b2 = (sgg * sxy - sgx * sgy) / det
    res = [yy - b1 * gg - b2 * xx for gg, xx, yy in zip(G, X, Y)]
    s2 = sum(r * r for r in res) / (n - 3)
    se1 = math.sqrt(s2 * sxx / det)
    se2 = math.sqrt(s2 * sgg / det)
    return {"n": n, "b_gap": round(b1, 3), "t_gap": round(b1 / se1, 2), "b_asia_given_gap": round(b2, 3), "t_asia_given_gap": round(b2 / se2, 2)}


def ols_k(cols, y):
    """OLS of y on several regressors (centred), via normal equations; returns betas and t's."""
    n = len(y)
    k = len(cols)
    if n < 30 + k:
        return None
    means = [statistics.mean(c) for c in cols]
    my = statistics.mean(y)
    Xc = [[c[i] - means[j] for j, c in enumerate(cols)] for i in range(n)]
    Yc = [v - my for v in y]
    A = [[sum(Xc[i][a] * Xc[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    bvec = [sum(Xc[i][a] * Yc[i] for i in range(n)) for a in range(k)]
    # solve A beta = b by Gauss-Jordan, keep inverse for SEs
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, row in enumerate(A)]
    for i in range(k):
        piv = M[i][i]
        if abs(piv) < 1e-18:
            return None
        M[i] = [v / piv for v in M[i]]
        for r in range(k):
            if r != i:
                f = M[r][i]
                M[r] = [a - f * b for a, b in zip(M[r], M[i])]
    inv = [row[k:] for row in M]
    beta = [sum(inv[a][b] * bvec[b] for b in range(k)) for a in range(k)]
    res = [Yc[i] - sum(beta[j] * Xc[i][j] for j in range(k)) for i in range(n)]
    s2 = sum(r * r for r in res) / (n - k - 1)
    return {"n": n, "beta": [round(b, 3) for b in beta],
            "t": [round(beta[j] / math.sqrt(s2 * inv[j][j]), 2) if inv[j][j] > 0 else None for j in range(k)]}


def by_year(x, g, oc, dates):
    out = {}
    for y in sorted({d[:4] for d in dates}):
        idx = [i for i, d in enumerate(dates) if d[:4] == y]
        r = ols2([g[i] for i in idx], [x[i] for i in idx], [oc[i] for i in idx])
        if r:
            out[y] = {"n": r["n"], "b_asia_given_gap": r["b_asia_given_gap"], "t": r["t_asia_given_gap"]}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--years", type=int, default=3)
    a = p.parse_args()
    FX = {"^N225": "JPY=X", "6758.T": "JPY=X", "7203.T": "JPY=X", "9984.T": "JPY=X", "^TWII": "TWD=X", "2330.TW": "TWD=X",
          "3231.TW": "TWD=X", "2317.TW": "TWD=X", "^KS11": "KRW=X", "000660.KS": "KRW=X", "005930.KS": "KRW=X"}
    syms = sorted({k.rstrip("x") for k in LEADS} | {s for v in LEADS.values() for s in v} | set(FX.values()) | set(PARENT.values()))
    df = yf.download(syms, period=f"{a.years}y", auto_adjust=True, progress=False, group_by="ticker", threads=True)
    series = {}
    for s in syms:
        try:
            d = df[s].dropna()
        except KeyError:
            continue
        series[s] = {str(i.date()): (float(r["Open"]), float(r["Close"])) for i, r in d.iterrows() if r["Open"] > 0}
    rep = {"years": a.years, "pairs": {}}
    print("TIMEZONE LEAD: Asian session return -> US gap / US open->close (same calendar date)")
    print("  asia       us         n   b_gap      t     b_oc      t   b_nextgap      t   asia>+2%: oc | asia<-2%: oc")
    for asia, uss in LEADS.items():
        asia = asia.rstrip("x")
        A = series.get(asia)
        if not A:
            continue
        ad = sorted(A)
        aret = {ad[i]: math.log(A[ad[i]][1] / A[ad[i - 1]][1]) for i in range(1, len(ad))}
        F = series.get(FX.get(asia, ""), {})
        fd = sorted(F)
        # USD per local: yfinance JPY=X is USDJPY (local per USD); log change of USDJPY > 0 = local currency WEAKER
        fxret = {fd[i]: math.log(F[fd[i]][1] / F[fd[i - 1]][1]) for i in range(1, len(fd))}
        for us in uss:
            U = series.get(us)
            if not U:
                continue
            ud = sorted(U)
            x, g, oc, ng, big_up, big_dn, dates, prev_cc, prev_oc, fx, par, nxt_asia = [], [], [], [], [], [], [], [], [], [], [], []
            P = series.get(PARENT.get(us, ""), {})
            pd_ = sorted(P)
            pret = {pd_[i]: math.log(P[pd_[i]][1] / P[pd_[i - 1]][1]) for i in range(1, len(pd_))}
            for i in range(2, len(ud) - 1):
                d = ud[i]
                if d not in aret or d not in fxret or (P and d not in pret):
                    continue
                nd = next((z for z in ad if z > d), None)
                if nd is None:
                    continue
                nxt_asia.append(aret.get(nd, 0.0))
                par.append(pret.get(d, 0.0))
                fx.append(fxret[d])
                prev_cc.append(math.log(U[ud[i - 1]][1] / U[ud[i - 2]][1]))
                prev_oc.append(math.log(U[ud[i - 1]][1] / U[ud[i - 1]][0]))
                gap = math.log(U[d][0] / U[ud[i - 1]][1])
                o2c = math.log(U[d][1] / U[d][0])
                x.append(aret[d])
                dates.append(d)
                g.append(gap)
                oc.append(o2c)
                ng.append(math.log(U[ud[i + 1]][0] / U[d][1]))
                if aret[d] > 0.02:
                    big_up.append(o2c)
                elif aret[d] < -0.02:
                    big_dn.append(o2c)
            r = {"gap": ols(x, g), "open_close": ols(x, oc), "next_gap": ols(x, ng),
                 "rival_gap_reversal": ols2(g, x, oc), "by_year": by_year(x, g, oc, dates),
                 "given_gap_and_prior_us": ols_k([g, prev_cc, prev_oc, x], oc),
                 "given_gap_prior_us_and_fx": ols_k([g, prev_cc, prev_oc, fx, x], oc),
                 "given_all_and_parent": ols_k([g, prev_cc, prev_oc, fx, par, x], oc) if P else None,
                 "asia_next_session_on_today": ols(x, nxt_asia),
                 "big_up": {"n": len(big_up), "oc_mean": round(statistics.mean(big_up), 5) if big_up else None},
                 "big_dn": {"n": len(big_dn), "oc_mean": round(statistics.mean(big_dn), 5) if big_dn else None}}
            rep["pairs"][f"{asia}->{us}"] = r
            if r["gap"]:
                bu = (r["big_up"]["oc_mean"] or 0) * 100
                bd = (r["big_dn"]["oc_mean"] or 0) * 100
                rv = r["rival_gap_reversal"] or {}
                yrs = " ".join(f"{y[2:]}:{v['t']:+.1f}" for y, v in r["by_year"].items())
                print(f"  {asia:10s} {us:6s} {r['gap']['n']:5d}  {r['gap']['beta']:6.3f} {r['gap']['t']:6.2f}   "
                      f"{r['open_close']['beta']:6.3f} {r['open_close']['t']:6.2f}  {r['next_gap']['beta']:9.3f} {r['next_gap']['t']:6.2f}   "
                      f"{r['big_up']['n']:3d}:{bu:+.2f}% | {r['big_dn']['n']:3d}:{bd:+.2f}%")
                k4 = r["given_gap_and_prior_us"] or {}
                k6 = r["given_all_and_parent"] or {}
                na = r["asia_next_session_on_today"] or {}
                if k6:
                    print(f"     + parent's own session: b_asia {k6.get('beta', [None]*6)[5]} t {k6.get('t', [None]*6)[5]} | b_parent {k6.get('beta', [None]*6)[4]} t {k6.get('t', [None]*6)[4]} | Asia next session on today: b {na.get('beta')} t {na.get('t')}")
                k5 = r["given_gap_prior_us_and_fx"] or {}
                print(f"     + FX (USD/local same day): b_asia {k5.get('beta', [None]*5)[4]} t {k5.get('t', [None]*5)[4]} | b_fx {k5.get('beta', [None]*5)[3]} t {k5.get('t', [None]*5)[3]}")
                print(f"     given gap: b_asia {rv.get('b_asia_given_gap')} t {rv.get('t_asia_given_gap')} | given gap+prior US cc+oc: b_asia {k4.get('beta', [None]*4)[3]} t {k4.get('t', [None]*4)[3]} (t gap {k4.get('t', [None]*4)[0]}, prev_cc {k4.get('t', [None]*4)[1]}, prev_oc {k4.get('t', [None]*4)[2]}) | by year t: {yrs}")
    # ---- NIKKEI_ADR_FADE_v1: the tradeable version -----------------------------------------
    # On a US session whose same-date Nikkei move is |r| >= thr, at the US OPEN take the OPPOSITE
    # direction in an equal-weight basket of the Japanese ADRs, close at the US CLOSE. 5 bp round trip.
    basket = ["SONY", "TM", "HMC", "TAK", "MFG", "SMFG", "MUFG", "NMR"]
    N = series.get("^N225", {})
    nd_ = sorted(N)
    nret = {nd_[i]: math.log(N[nd_[i]][1] / N[nd_[i - 1]][1]) for i in range(1, len(nd_))}
    strat = {}
    for thr in (0.01, 0.015, 0.02, 0.03):
        trades = []
        for d, rn in sorted(nret.items()):
            if abs(rn) < thr:
                continue
            legs = []
            for us in basket:
                U = series.get(us, {})
                if d in U:
                    legs.append(-math.copysign(1.0, rn) * (U[d][1] / U[d][0] - 1.0))
            if len(legs) >= 4:
                trades.append({"date": d, "nikkei": round(rn, 4), "ret": statistics.mean(legs) - 0.0005, "n_legs": len(legs)})
        if len(trades) < 5:
            continue
        rs = [t["ret"] for t in trades]
        by_y = {}
        for y in sorted({t["date"][:4] for t in trades}):
            ys = [t["ret"] for t in trades if t["date"][:4] == y]
            by_y[y] = {"n": len(ys), "mean": round(statistics.mean(ys), 5), "sum": round(sum(ys), 4)}
        up = [t["ret"] for t in trades if t["nikkei"] > 0]
        dn = [t["ret"] for t in trades if t["nikkei"] < 0]
        strat[f"thr_{thr}"] = {"n": len(trades), "mean_net": round(statistics.mean(rs), 5), "sd": round(statistics.pstdev(rs), 5),
                               "t": round(statistics.mean(rs) / statistics.pstdev(rs) * math.sqrt(len(rs)), 2),
                               "hit": round(sum(1 for r in rs if r > 0) / len(rs), 3), "sum": round(sum(rs), 4),
                               "after_nikkei_up_short": {"n": len(up), "mean": round(statistics.mean(up), 5) if up else None},
                               "after_nikkei_down_long": {"n": len(dn), "mean": round(statistics.mean(dn), 5) if dn else None},
                               "by_year": by_y, "worst": round(min(rs), 4), "best": round(max(rs), 4)}
    rep["NIKKEI_ADR_FADE_v1"] = {"basket": basket, "rule": "|Nikkei| >= thr -> opposite direction, US open->close, EW basket, 5bp", "results": strat}
    print("\nNIKKEI_ADR_FADE_v1 (EW basket of 8 Japanese ADRs, opposite the Nikkei, US open->close, net 5bp):")
    for k, v in strat.items():
        print(f"  {k:9s} n={v['n']:4d} mean {v['mean_net']*100:+.3f}% sd {v['sd']*100:.2f}% t {v['t']:5.2f} hit {v['hit']:.2f} sum {v['sum']*100:+.1f}%  "
              f"short-after-up {v['after_nikkei_up_short']['n']}:{(v['after_nikkei_up_short']['mean'] or 0)*100:+.3f}%  long-after-down {v['after_nikkei_down_long']['n']}:{(v['after_nikkei_down_long']['mean'] or 0)*100:+.3f}%  worst {v['worst']*100:+.2f}%")
        print("            by year: " + "  ".join(f"{y}: n={b['n']} mean {b['mean']*100:+.3f}% sum {b['sum']*100:+.1f}%" for y, b in v["by_year"].items()))
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"receipt -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
