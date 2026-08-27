"""Propose the five-session competition book. Prints orders; places none.

    python -m scripts.competition_book                  # the plan
    python -m scripts.competition_book --equity 100000
    python -m scripts.competition_book --chains         # price against the live chain

Nothing here submits. The output is a list of orders for a human to approve,
because seeding a lane is attended and env-gated and a corrected engine with no
prospective evidence does not get the keys on its first night.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np

from alpha import config, lab, playbook
from scripts.today_book import effective_bets
from scripts.wealth_lab import SECTORS, UNIVERSE

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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--conviction", type=float, default=0.5,
                   help="how much of the measured drift we bet on. >=0.70 buys "
                        "convexity; below it the null-surviving structure is used.")
    p.add_argument("--chains", action="store_true", help="price against the live chain")
    args = p.parse_args()
    config.load_env()

    panel = lab.build_panel(UNIVERSE, start=(date.today() - timedelta(days=1100)).isoformat())
    i = panel.n_dates - 1
    print(f"COMPETITION BOOK  decision close {panel.dates[i]}  equity ${args.equity:,.0f}")
    print("=" * 84)

    # --- selection: the two rules that cleared their own noise floor ----------
    sel = lab.blend([(lab.rotate(SECTORS, 63, k=3), 0.5),
                     (lab.cross_sectional(63, 0, 5), 0.5)])
    w = sel(panel, i)
    idx = [j for j in range(panel.n_symbols) if w[j] != 0]
    names = [panel.symbols[j] for j in idx]

    print("\n1. SELECTION  (sector rotate 3m top3 + mega-cap mom 3m k=5, equal blend)")
    print(f"   raw book: {', '.join(names)}")

    # --- exclusion: a catalyst inside the window changes the distribution -----
    kept_idx, dropped = [], []
    for j in idx:
        s = panel.symbols[j]
        if s in EARNINGS_IN_WINDOW:
            dropped.append((s, EARNINGS_IN_WINDOW[s]))
        else:
            kept_idx.append(j)
    print("\n2. CATALYST EXCLUSION")
    if dropped:
        for s, d in dropped:
            print(f"   DROP {s:<6} reports {d} -- inside the holding window.")
        print("   The five-session distribution we measured does NOT contain these")
        print("   prints. Repricing that distribution from nothing is exactly what the")
        print("   NVDA condor did, and it cost $14,315.")
    else:
        print("   none of the selected names report inside the window.")

    kept = [panel.symbols[j] for j in kept_idx]
    n_eff = effective_bets(panel, kept_idx, i)
    print(f"\n3. CONCENTRATION  {len(kept)} names, {n_eff:.2f} effective bets")
    proposal = playbook.Proposal(effective_bets=n_eff)
    for why in playbook.check_book(n_eff, len(kept)):
        proposal.refuse(why)
        print(f"   REFUSAL: {why}")
    if not proposal.refusals:
        print(f"   OK -- above the {playbook.MIN_EFFECTIVE_BETS} floor.")

    # --- structure ------------------------------------------------------------
    struct = playbook.structure_for(args.conviction, has_catalyst=False)
    print(f"\n4. STRUCTURE  conviction {args.conviction:.2f} -> {struct}")
    if struct == "short_put_spread":
        print("   Long delta AND long theta. The only family with a POSITIVE median")
        print("   when the drift is stripped out (+2.09% vs ATM call -10.95%).")
        print("   Win small often, lose big rarely -- so the size cap is the trade.")
    else:
        print("   Debit call spread: convexity, but capped and much less theta than a")
        print("   naked call. Justified only because conviction >= 0.70 was declared.")

    # --- sizing ---------------------------------------------------------------
    budget_per_name = playbook.name_budget(args.equity, len(kept_idx))
    print(f"\n5. SIZING  max {playbook.MAX_LOSS_FRACTION:.0%} of equity at risk, "
          f"{playbook.MAX_LOSS_PER_NAME:.0%} per name -> "
          f"${budget_per_name:,.0f} per name binds")
    spot = panel.close[i]
    total = 0.0
    for j in kept_idx:
        s, px = panel.symbols[j], float(spot[j])
        width = max(1.0, round(px * 0.05))          # ~5% wide, a tradeable strike gap
        credit = width * 0.30                        # ~30% of width is a typical 1SD-ish credit
        risk_per = (width - credit) * 100.0
        n = playbook.size_leg(args.equity, risk_per, n_names=len(kept_idx))
        if n <= 0:
            print(f"   {s:<6} SKIP -- one contract risks ${risk_per:,.0f} > ${budget_per_name:,.0f}")
            continue
        total += n * risk_per
        print(f"   {s:<6} spot ${px:>7.2f}  sell {px*0.95:>7.2f}P / buy {px*0.90:>7.2f}P "
              f"x{n:>2}  risk ${n*risk_per:>7,.0f}")
    print(f"   {'TOTAL':<6} defined risk ${total:,.0f} = {total/args.equity:.1%} of equity")
    if total > args.equity * playbook.MAX_LOSS_FRACTION:
        print(f"   REFUSAL: exceeds the {playbook.MAX_LOSS_FRACTION:.0%} cap. Cut contracts.")

    print(f"\n6. ENTRY  at most {playbook.MAX_ENTRIES_PER_SESSION} names per session.")
    print("   100% of the $37,337 loss entered on ONE day. One entry date is one bet")
    print("   however many tickers carry it.")
    print("\nNOTHING WAS SENT. These are orders for a human to approve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
