"""Decompose each held name's daily move into market + sector + company.

    python -m scripts.move_decomposition --day 2026-09-01
    python -m scripts.move_decomposition --day 2026-09-01 --symbols RZLV,NB,LAES

WHY (Murat, 2026-09-01)
=======================
    "If NVDA falls 2% on a day when semiconductors are -2.2%, that is very
     different from NVDA falling 2% while semiconductors are +1%. The second
     case contains company-specific information. The first largely doesn't."

A six-to-twelve-month thesis must not be re-adjudicated by a macro morning.
This tool gives the autopsy (and eventually the tactical layer) the number it
needs: how much of today's move was the MARKET, how much the SECTOR, and how
much the COMPANY. Method: trailing-window OLS per name,

    r_i = a + b_mkt * r_SPY + b_sec * (r_sector_etf - r_SPY) + e

then today's return splits into b_mkt*r_SPY | b_sec*(r_sec - r_SPY) | residual
(the residual absorbs a; over one day the intercept is noise-sized). A name
whose sector has no ETF mapping is decomposed on the market leg alone and the
row says so -- derived or refused, never silently zero.

READ-ONLY: data API bars only; no orders, no state mutation beyond its own
output file. Bars come from the sealed universe's own broker credentials.
Output: state/decomposition/<day>.json (+ stdout table).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "decomposition"

#: Finnhub-style sector labels -> SPDR sector ETF. Unmapped -> market-only.
SECTOR_ETF = {
    "Technology": "XLK", "Information Technology": "XLK",
    "Health Care": "XLV", "Healthcare": "XLV",
    "Energy": "XLE",
    "Financial Services": "XLF", "Financials": "XLF",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY", "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP", "Consumer Staples": "XLP",
    "Basic Materials": "XLB", "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    # Finnhub uses INDUSTRY-grained labels on most tracker rows; map the ones
    # observed in the live day files (2026-09-01 histogram) to their sector
    # ETF. SMH for semis specifically -- the XLK blend hides exactly the
    # semi-vs-market split Murat's NVDA example is about.
    "Biotechnology": "XBI",
    "Pharmaceuticals": "XLV",
    "Banking": "KBE",
    "Insurance": "XLF",
    "Semiconductors": "SMH",
    "Electrical Equipment": "XLI",
    "Machinery": "XLI",
    "Aerospace & Defense": "XLI",
    "Retail": "XRT",
    "Media": "XLC",
    "Hotels, Restaurants & Leisure": "XLY",
    "Metals & Mining": "XME",
    "Chemicals": "XLB",
    "Consumer products": "XLP",
}

LOOKBACK_SESSIONS = 120
MIN_SESSIONS = 40


def _returns(closes: list[float]) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    return c[1:] / c[:-1] - 1.0


def decompose(day: str, symbols: list[str] | None) -> dict:
    from alpha.broker.alpaca import AlpacaPaper  # late import: needs env
    from alpha import config
    config.load_env()
    b = AlpacaPaper(config.role())

    # names + sectors from the sealed book unless symbols were given
    sectors: dict[str, str | None] = {}
    if symbols is None:
        seal = json.loads((ROOT / "docs" / "seed" / "predictions" / f"{day}.json").read_text())
        symbols = []
        for book, port in (seal.get("portfolios") or {}).items():
            for h in (port.get("holdings") or []):
                s = h.get("symbol")
                if s and s not in sectors:
                    symbols.append(s)
                    sectors[s] = h.get("sector")
    else:
        sectors = {s: None for s in symbols}
        # sector from the tracker day file when available
        tf = ROOT / "state" / "tracker" / f"{day}.jsonl"
        if tf.exists():
            for line in tf.read_text().splitlines():
                r = json.loads(line)
                if r.get("symbol") in sectors:
                    sectors[r["symbol"]] = r.get("sector")

    etfs = sorted({e for e in (SECTOR_ETF.get(sectors.get(s) or "") for s in symbols) if e})
    start = (datetime.fromisoformat(day) - timedelta(days=int(LOOKBACK_SESSIONS * 1.7))).date().isoformat()
    bars = b.stock_bars_multi(symbols + etfs + ["SPY"], start=start)

    series: dict[str, dict[str, float]] = {}
    for sym, rows in bars.items():
        series[sym] = {r["t"][:10]: float(r["c"]) for r in rows if r.get("c")}

    spy = series.get("SPY") or {}
    days_all = sorted(d for d in spy if d <= day)
    if day not in spy:
        raise SystemExit(f"REFUSED: no SPY bar for {day} yet -- run after the close.")
    window = days_all[-(LOOKBACK_SESSIONS + 1):]

    def aligned(sym: str, dates: list[str]) -> np.ndarray | None:
        s = series.get(sym) or {}
        if any(d not in s for d in dates):
            common = [d for d in dates if d in s]
            if len(common) < MIN_SESSIONS + 1 or common[-1] != day:
                return None
            return None  # strict alignment only in v1; partial histories refuse
        return _returns([s[d] for d in dates])

    r_spy = _returns([spy[d] for d in window])
    out_rows = []
    for sym in symbols:
        sec = sectors.get(sym)
        etf = SECTOR_ETF.get(sec or "")
        s = series.get(sym) or {}
        dates = [d for d in window if d in s]
        if len(dates) < MIN_SESSIONS + 1 or dates[-1] != day:
            out_rows.append({"symbol": sym, "status": "REFUSED: insufficient aligned history",
                             "sessions": len(dates)})
            continue
        r_i = _returns([s[d] for d in dates])
        r_m = _returns([spy[d] for d in dates])
        X_cols = [np.ones(len(r_m)), r_m]
        r_s_ex = None
        if etf and etf in series and all(d in series[etf] for d in dates):
            r_sec = _returns([series[etf][d] for d in dates])
            r_s_ex = r_sec - r_m
            X_cols.append(r_s_ex)
        X = np.column_stack(X_cols)
        beta, *_ = np.linalg.lstsq(X[:-1], r_i[:-1], rcond=None)  # fit EXCLUDES today
        today_m = float(beta[1] * r_m[-1])
        today_s = float(beta[2] * r_s_ex[-1]) if r_s_ex is not None else None
        today_r = float(r_i[-1])
        idio = today_r - today_m - (today_s or 0.0)
        out_rows.append({
            "symbol": sym, "sector": sec, "sector_etf": etf or None,
            "return": round(today_r, 5),
            "market_component": round(today_m, 5),
            "sector_component": round(today_s, 5) if today_s is not None else None,
            "company_component": round(idio, 5),
            "beta_market": round(float(beta[1]), 3),
            "beta_sector_ex_market": round(float(beta[2]), 3) if r_s_ex is not None else None,
            "sessions": len(dates) - 1,
            "note": None if etf else "no sector ETF mapping -- market leg only",
        })

    ok = [r for r in out_rows if "return" in r]
    summary = {
        "day": day,
        "spy_return": round(float(r_spy[-1]), 5),
        "names": len(out_rows),
        "decomposed": len(ok),
        "mean_market_share_of_move": (round(float(np.mean(
            [abs(r["market_component"]) / max(abs(r["return"]), 1e-9) for r in ok])), 3)
            if ok else None),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "fit": f"trailing {LOOKBACK_SESSIONS} sessions, today excluded from the fit",
        "rows": out_rows,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--symbols", help="comma-separated; default = the day's sealed holdings")
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    summary = decompose(args.day, syms)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.day}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"SPY {summary['spy_return']:+.2%}  ({summary['day']})")
    for r in summary["rows"]:
        if "return" not in r:
            print(f"  {r['symbol']:6s} {r['status']}")
            continue
        sec = f"{r['sector_component']:+.2%}" if r["sector_component"] is not None else "   --  "
        print(f"  {r['symbol']:6s} {r['return']:+7.2%} = mkt {r['market_component']:+.2%} "
              f"+ sec {sec} + company {r['company_component']:+.2%}")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
