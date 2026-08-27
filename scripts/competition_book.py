"""Propose the five-session competition book. Prints orders; places none.

    python -m scripts.competition_book
    python -m scripts.competition_book --equity 100000 --conviction 0.5

THE ORDER OF OPERATIONS IS THE FINDING
======================================
This script used to start by asking which names to hold. That is the question
`FINDING_2026-08-28_VARIANCE_DRAG_ATE_THE_EDGE.md` says to ask LAST, because
over CRSP 1993-2024 at a five-day hold:

    CRSP value-weighted market          25.16x     +10.61%/yr
    our best five-day configuration      5.03x      +5.36%/yr
    the candidate the lab crowned        0.09x      -7.23%/yr

The tilt's measured 32-year contribution is negative. So the book is built in
the order the evidence supports: beta first, breadth second, structure third,
names last and small.

Nothing here submits. The output is a list of orders for a human to approve.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np

from alpha import config, lab, playbook
from scripts.today_book import effective_bets
from scripts.wealth_lab import UNIVERSE

# Reporting inside 2026-08-28 .. 2026-09-04, from `scripts.window_universe`.
# A momentum book in late August selects these by construction.
EARNINGS_IN_WINDOW = {
    "MRVL": "2026-08-28", "WDAY": "2026-08-28", "ADSK": "2026-08-28",
    "AFRM": "2026-08-28", "ULTA": "2026-08-28", "GAP": "2026-08-28",
    "NIO": "2026-09-01", "MDT": "2026-09-01",
    "PANW": "2026-09-02", "MDB": "2026-09-02", "DLTR": "2026-09-02",
    "AVGO": "2026-09-03", "HPE": "2026-09-03", "LULU": "2026-09-03",
    "SNOW": "2026-09-03", "NTAP": "2026-09-03", "CIEN": "2026-09-03",
    "DELL": "2026-09-04", "ZS": "2026-09-04", "DOCU": "2026-09-04",
    "PATH": "2026-09-04", "GWRE": "2026-09-04",
}

WORST_5D = 0.1331
"""Worst five-session window MEASURED for `momentum 12-1 k=20` over the last
year. The satellite's risk is stated against this rather than against an
invented stop, because a stop we have never tested is a number we made up."""

CORE = ["SPY", "QQQ", "IWM"]
"""The core is BETA, deliberately boring. It is the only term in this whole
project that has ever compounded, and it did so at +10.61% for 32 years."""


def trend_ok(panel: lab.Panel, i: int, symbol: str = "SPY", window: int = 200) -> bool:
    """Cash when the market is below its own 200-session average.

    Adding this filter to the CRSP sweep lifted nearly every cell and took the
    best configuration from 2.58x to 5.03x. It is the cheapest risk control we
    have and it was never once consulted by the book that lost $37,337.
    """
    if symbol not in panel.symbols or i < window:
        return True
    j = panel.symbols.index(symbol)
    ma = float(np.nanmean(panel.close[i - window:i + 1, j]))
    return bool(np.isfinite(ma) and panel.close[i, j] >= ma)


def price_spreads(names, spot_of, budget_total, label):
    """Short put spreads ~5% out, 5% wide. Long delta AND long theta -- the only
    family with a positive median once the drift is stripped out.

    Sizing goes through `playbook.size_leg`, which applies the RECONCILED cap
    (per-name vs book, whichever binds). Re-deriving it here would be a second
    copy of a limit that already exists, and the two would drift.
    """
    total = 0.0
    n_names = max(1, len(names))
    budget_per_name = budget_total / n_names
    for s in names:
        px = spot_of(s)
        if not np.isfinite(px) or px <= 0:
            print(f"   {s:<6} SKIP -- no usable close")
            continue
        width = max(1.0, round(px * 0.05))
        credit = width * 0.30
        risk_per = (width - credit) * 100.0
        n = playbook.size_leg(budget_per_name, risk_per)
        if n <= 0:
            print(f"   {s:<6} SKIP -- one contract risks ${risk_per:,.0f} "
                  f"> ${budget_per_name:,.0f}")
            continue
        total += n * risk_per
        print(f"   {s:<6} spot ${px:>7.2f}  sell {px * 0.95:>7.2f}P / "
              f"buy {px * 0.90:>7.2f}P  x{n:>3}  risk ${n * risk_per:>7,.0f}")
    print(f"   {label} risk ${total:,.0f}")
    return total


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--conviction", type=float, default=0.5,
                   help=">=0.70 buys convexity; below it the null-surviving "
                        "structure is used")
    p.add_argument("--k", type=int, default=playbook.MIN_BREADTH_K,
                   help="tilt breadth. Below 20 is refused with its own number.")
    args = p.parse_args()
    config.load_env()

    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    i = panel.n_dates - 1
    spot = panel.close[i]

    def spot_of(sym: str) -> float:
        return float(spot[panel.symbols.index(sym)]) if sym in panel.symbols else float("nan")

    core_risk, sat_risk = playbook.core_satellite(args.equity)
    # No single name may exceed the per-name cap even inside the core.
    core_risk = min(core_risk, playbook.name_budget(args.equity, len(CORE)) * len(CORE))
    print(f"COMPETITION BOOK  decision close {panel.dates[i]}  equity ${args.equity:,.0f}")
    print("=" * 84)
    print(f"Risk budget ${args.equity * playbook.MAX_LOSS_FRACTION:,.0f} "
          f"({playbook.MAX_LOSS_FRACTION:.0%}) = ${core_risk:,.0f} core "
          f"+ ${sat_risk:,.0f} satellite")

    # ---- 0. the regime gate, before anything is selected --------------------
    up = trend_ok(panel, i)
    print(f"\n0. REGIME  SPY {'ABOVE' if up else 'BELOW'} its 200-session average -> "
          f"{'deploy' if up else 'CASH'}")
    if not up:
        print("   The 32-year sweep improved in nearly every cell with this filter.")
        print("   Cash is a position and it is this one. NOTHING TO SEND.")
        return 0

    # ---- 1. core: beta, which is the only thing that has ever compounded ----
    print(f"\n1. CORE  {playbook.CORE_FRACTION:.0%} of risk in broad beta: {', '.join(CORE)}")
    print("   Over CRSP 1993-2024 the market did +10.61%/yr while our best")
    print("   five-day configuration did +5.36% and the lab's winner did -7.23%.")
    core_total = price_spreads(CORE, spot_of, core_risk, "CORE")

    # ---- 2. satellite: the tilt, broad and gated ----------------------------
    print(f"\n2. SATELLITE  {1 - playbook.CORE_FRACTION:.0%} of risk, tilt at k={args.k}")
    why = playbook.breadth_ok(args.k)
    if why:
        print(f"   REFUSAL: {why}")
        print("   No satellite. The core stands alone.")
        sat_total = 0.0
        kept = []
    else:
        sel = lab.cross_sectional(252, 21, args.k)
        w = sel(panel, i)
        idx = [j for j in range(panel.n_symbols) if w[j] != 0]
        raw = [panel.symbols[j] for j in idx]
        dropped = [(s, EARNINGS_IN_WINDOW[s]) for s in raw if s in EARNINGS_IN_WINDOW]
        kept_idx = [j for j in idx if panel.symbols[j] not in EARNINGS_IN_WINDOW]
        kept = [panel.symbols[j] for j in kept_idx]
        print(f"   12-1 momentum, top {args.k}: {', '.join(raw)}")
        for s, d in dropped:
            print(f"   DROP {s:<6} reports {d} -- inside the holding window. The "
                  f"measured distribution does not contain that print.")
        n_eff = effective_bets(panel, kept_idx, i)
        print(f"   {len(kept)} names, {n_eff:.2f} effective bets")
        for r in playbook.check_book(n_eff, len(kept)):
            print(f"   REFUSAL: {r}")
        # SHARES, not spreads. A defined-risk spread has a MINIMUM size -- one
        # contract on a $200 name risks ~$700 -- so a $9,000 satellite spread
        # over 20 names gives $450 each and buys nothing. The first version of
        # this section deployed $910 of $9,000 and skipped 16 of 18 names.
        # Breadth is the lever the 32-year sweep endorsed; shares are the only
        # instrument that delivers it at this account size.
        notional = sat_risk / WORST_5D
        per = notional / max(1, len(kept))
        print(f"   expressed as SHARES: a spread's minimum size defeats breadth here.")
        print(f"   ${sat_risk:,.0f} of risk / {WORST_5D:.1%} worst measured 5-day window")
        print(f"   = ${notional:,.0f} notional, ${per:,.0f} per name")
        sat_total = 0.0
        for s_ in kept:
            px = spot_of(s_)
            if not np.isfinite(px) or px <= 0:
                continue
            sh = int(per // px)
            if sh <= 0:
                print(f"   {s_:<6} SKIP -- ${px:,.2f} exceeds the ${per:,.0f} slot")
                continue
            sat_total += sh * px * WORST_5D
            print(f"   {s_:<6} buy {sh:>4} sh @ ${px:>7.2f} = ${sh * px:>8,.0f} notional")
        print(f"   SATELLITE risk ${sat_total:,.0f} at the worst measured window")

    # ---- 3. structure -------------------------------------------------------
    struct = playbook.structure_for(args.conviction, has_catalyst=False)
    print(f"\n3. STRUCTURE  conviction {args.conviction:.2f} -> {struct}")
    print("   Short put spreads: long delta AND long theta. Strip the drift from")
    print("   the measured five-session returns and every long-premium structure")
    print("   goes negative on the median (ATM call -10.95%, straddle -7.33%);")
    print("   only these stay positive. We have just FAILED to demonstrate a drift.")

    total = core_total + sat_total
    print(f"\n4. TOTAL  defined risk ${total:,.0f} = {total / args.equity:.1%} of equity")
    if total > args.equity * playbook.MAX_LOSS_FRACTION + 1.0:
        print(f"   REFUSAL: exceeds the {playbook.MAX_LOSS_FRACTION:.0%} cap.")
    print("\n5. TIMING  enter MARKET-ON-CLOSE, not at the next open.")
    print("   CRSP 1993-2024, equal-weight top 200: the overnight segment")
    print("   (close->open) compounded at +17.31% while intraday (open->close)")
    print("   returned -7.26%, and overnight was positive in ALL FOUR decades.")
    print("   The replay fills at the next open because a backtest cannot")
    print("   transact at a close it is still deciding on. LIVE, an MOC order")
    print("   can -- and filling at the open donates the only segment that pays.")
    print(f"\n6. ENTRY  at most {playbook.MAX_ENTRIES_PER_SESSION} names per session.")
    print("   100% of the $37,337 loss entered on ONE day. One entry date is one")
    print("   bet however many tickers carry it.")
    print("\nNOTHING WAS SENT. These are orders for a human to approve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
