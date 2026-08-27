"""Backtest the five-session question over the last month, six months and year.

    python -m scripts.wealth_lab                 # all three windows, H=5
    python -m scripts.wealth_lab --horizon 3
    python -m scripts.wealth_lab --refresh       # re-pull bars

Reports terminal wealth FIRST, then the ratios -- a five-session book is not
compounding for a year and an annualised Sharpe is the wrong ruler for it.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

import numpy as np

from alpha import config, lab

# A liquid, optionable universe. ETFs first because an index is a real
# competitor and pretending otherwise is how a book loses to SPY quietly.
ETFS = ["SPY", "QQQ", "IWM", "DIA", "MDY", "XLK", "XLF", "XLE", "XLV", "XLI",
        "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE", "SMH", "SOXX", "XBI", "IBB",
        "ARKK", "TLT", "IEF", "HYG", "LQD", "GLD", "SLV", "USO", "UNG", "EEM",
        "EFA", "FXI", "EWZ", "EWJ", "VXX", "TQQQ", "SQQQ", "UPRO", "SPXL", "SSO",
        "QLD", "VOO", "VTI", "RSP", "MTUM", "QUAL", "USMV", "VLUE", "SPLV", "SPHB"]

MEGA = ["NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO",
        "BRK.B", "LLY", "JPM", "V", "MA", "XOM", "UNH", "COST", "JNJ", "WMT",
        "PG", "HD", "ORCL", "NFLX", "CVX", "MRK", "ABBV", "KO", "PEP", "ADBE",
        "CRM", "AMD", "TMO", "BAC", "ACN", "MCD", "CSCO", "LIN", "ABT", "PM",
        "IBM", "GE", "QCOM", "TXN", "DHR", "VZ", "INTU", "NOW", "CAT", "AMGN",
        "NEE", "RTX", "SPGI", "UBER", "PFE", "UNP", "LOW", "HON", "BKNG", "AMAT",
        "ISRG", "T", "BLK", "SYK", "PLD", "TJX", "COP", "VRTX", "MU", "ADI",
        "PANW", "LRCX", "KLAC", "SBUX", "MDT", "GILD", "ADP", "MMC", "CI", "REGN",
        "BSX", "CB", "SO", "MO", "ZTS", "DUK", "PLTR", "SHOP", "SNOW", "CRWD",
        "DDOG", "NET", "ABNB", "COIN", "SQ", "PYPL", "ROKU", "RIVN", "LCID",
        "F", "GM", "DAL", "AAL", "UAL", "CCL", "NCLH", "MARA", "RIOT", "MSTR",
        "SMCI", "ARM", "DELL", "HPQ", "WDC", "STX", "ON", "MRVL", "SWKS", "NXPI",
        "TER", "ASML", "TSM", "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "SE",
        "MELI", "SPOT", "DASH", "LYFT", "TTD", "ZM", "OKTA", "TWLO", "SNAP",
        "PINS", "RBLX", "U", "HOOD", "SOFI", "AFRM", "UPST", "CVNA", "CHWY",
        "ETSY", "EBAY", "WBD", "PARA", "DIS", "CMCSA", "GS", "MS", "C", "WFC",
        "SCHW", "AXP", "PNC", "USB", "TFC", "COF", "BX", "KKR", "APO", "ARES"]

UNIVERSE = sorted(set(ETFS + MEGA))

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB",
           "XLC", "XLRE", "SMH", "XBI", "IBB", "SOXX", "ARKK", "GLD", "TLT"]

WINDOWS = {"1 month": 21, "6 months": 126, "1 year": 252, "2 years": 504}


def battery(horizon: int) -> list[tuple[str, lab.Selector, str]]:
    """Name, selector, one-line reason it is in the list."""
    xs = cross = lab.cross_sectional
    return [
        # -- the competitors we must beat, not decorations ---------------------
        ("BUY AND HOLD SPY", lab.hold("SPY"), "the judge's implicit alternative"),
        ("BUY AND HOLD QQQ", lab.hold("QQQ"), "beta with a tech tilt"),
        ("equal-weight top 200", lab.equal_weight(200), "breadth with no view"),
        # -- leverage, which is the honest way to raise a 5-day P&L ------------
        ("2x QQQ (QLD)", lab.hold("QLD"), "levered beta, exchange traded"),
        ("3x QQQ (TQQQ)", lab.hold("TQQQ"), "the ceiling of unlevered convexity"),
        ("3x SPY (UPRO)", lab.hold("UPRO"), ""),
        ("SEMIS (SMH)", lab.hold("SMH"), "the AI beta the book kept trying to express"),
        # -- cross-sectional signals ------------------------------------------
        ("momentum 12-1  k=10", xs(252, 21, 10), "the farm's only scaling signal"),
        ("momentum 12-1  k=20", xs(252, 21, 20), "the 32-year optimum"),
        ("momentum 1m    k=10", xs(21, 0, 10), ""),
        ("momentum 1w    k=10", xs(5, 0, 10), "short-horizon winner chasing"),
        ("reversal 1w    k=10", xs(5, 0, 10, reverse=True), "Holm survivor, inverted"),
        ("reversal 1m    k=10", xs(21, 0, 10, reverse=True), ""),
        ("low vol        k=20", lab.low_vol(20), ""),
        ("high vol       k=20", lab.low_vol(20, reverse=True), "lottery demand"),
        # -- the two we have never run ----------------------------------------
        ("SPY + 200d trend filter", lab.trend_filter("SPY", lab.hold("SPY")),
         "cash when the index is below its average"),
        ("QQQ + 200d trend filter", lab.trend_filter("SPY", lab.hold("QQQ")), ""),
        ("TQQQ + 200d trend filter", lab.trend_filter("SPY", lab.hold("TQQQ")),
         "leverage GATED by trend, not applied blindly"),
        ("vol-targeted QQQ (15%)", lab.vol_targeted(lab.hold("QQQ"), "QQQ", 0.15),
         "Moreira-Muir: size on forecastable vol, not on a vol opinion"),
        ("vol-targeted TQQQ-equiv", lab.vol_targeted(lab.hold("QQQ"), "QQQ", 0.30, cap=3.0),
         "same idea at a 30% target"),
        ("mom12-1 k=20 + trend", lab.trend_filter("SPY", xs(252, 21, 20)),
         "cross-section GATED by the index"),
        # -- ROTATION: the tradeable form of "semis won", decided at each date --
        ("sector rotate 1m  top1", lab.rotate(SECTORS, 21),
         "hold last month's leading sector, chosen without hindsight"),
        ("sector rotate 3m  top1", lab.rotate(SECTORS, 63), ""),
        ("sector rotate 6m  top1", lab.rotate(SECTORS, 126), ""),
        ("sector rotate 12m top1", lab.rotate(SECTORS, 252), ""),
        ("sector rotate 3m  top2", lab.rotate(SECTORS, 63, k=2), "two sectors, half the idiosyncrasy"),
        ("sector rotate 3m  top3", lab.rotate(SECTORS, 63, k=3), ""),
        ("sector LAGGARD 3m top1", lab.rotate(SECTORS, 63, reverse=True),
         "the control: if leaders win, laggards must not"),
        ("mega-cap mom 3m  k=5", xs(63, 0, 5), "concentrated single names"),
        ("mega-cap mom 3m  k=3", xs(63, 0, 3), ""),
        ("mega-cap mom 6m  k=5", xs(126, 0, 5), ""),
        ("vol-tgt mom12-1 k=20 + trend",
         lab.vol_targeted(lab.trend_filter("SPY", xs(252, 21, 20)), "QQQ", 0.20),
         "all three composed"),
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, default=5, help="sessions held")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--json", default=None)
    args = p.parse_args()
    config.load_env()

    start = (date.today() - timedelta(days=1100)).isoformat()
    print(f"pulling daily bars for {len(UNIVERSE)} symbols from {start} ...")
    panel = lab.build_panel(UNIVERSE, start=start, refresh=args.refresh)
    print(f"panel: {panel.n_dates} sessions x {panel.n_symbols} symbols "
          f"({panel.dates[0]} .. {panel.dates[-1]})\n")

    out: dict[str, list[dict]] = {}
    for label, sessions in WINDOWS.items():
        start_i = max(252, panel.n_dates - sessions - args.horizon - 1)
        if start_i >= panel.n_dates - args.horizon - 2:
            print(f"{label}: not enough history after the 252-day warmup -- SKIPPED")
            continue
        n_eff = panel.n_dates - args.horizon - 1 - start_i
        if n_eff < sessions * 0.9:
            # An honest label or none. A window that says "1 year" and carries
            # seven months of decisions is the same defect as a file size read
            # as a sample size.
            label = f"{label} (TRUNCATED to {n_eff} days by the 252d warmup)"
        print("=" * 96)
        print(f"WINDOW: {label}   ({panel.dates[start_i]} .. {panel.dates[-1]}, "
              f"{n_eff} decision days, hold {args.horizon} sessions)")
        print(f"{'strategy':<34} {'mean':>7} {'median':>7} {'hit':>5} {'t':>6} "
              f"{'wealth':>8} {'worst':>8} {'blk':>4}")
        print("-" * 96)
        rows = []
        for name, sel, why in battery(args.horizon):
            r = lab.run(panel, sel, horizon=args.horizon, name=name, start_i=start_i, note=why)
            rows.append(r)
        for r in sorted(rows, key=lambda r: -r.wealth):
            print(r.line())
        out[label] = [r.__dict__ | {"curve": []} for r in rows]
        print()

    if args.json:
        from pathlib import Path
        Path(args.json).write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
