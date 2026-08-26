"""EVENT_CALENDAR_v1 -- sell the expiry that contains the print, own the one that does not.

    python -m scripts.event_calendar [--json]

The condor sells the event's tails and the straddle buys them; both hold a
view on the SIZE of the move. A calendar holds a view on the PRICE OF THE
EVENT VARIANCE ALONE: short the ATM straddle in the front expiry (the one the
print sits in), long the ATM straddle in the next monthly at the same strike.
After the print the front's event variance is gone and the back keeps most of
its ordinary vol. The trade is what an open-source earnings bot in the wild
runs (calendar + Kelly + a term-structure/IV-RV screen), so it is worth a
number on our own prints.

Construction, from real daily bars:
    entry   the pre-event entry close (same as the straddle backtest)
    front   the straddle backtest's ATM straddle (same contracts, SOLD)
    back    ATM straddle at the same strike in the first expiry >= front + 21 days
    exit    the first close reflecting the print (day 0)
    P&L     (back_exit - back_entry) - (front_exit - front_entry), per unit,
            over max loss approximated as the net debit paid (a long calendar's
            defined risk) -- reported in dollars per spot as well.

Assignment risk on the short front leg, and the pin at expiry, are not
modelled; the front is closed at the day-0 close in every case, which is the
only way the trade is run here. Early assignment is the reason this stays
shadow whatever the number says.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from scripts.event_straddle_backtest import option_bars

MIN_GAP_DAYS = 21


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def back_expiries(front: date) -> list[date]:
    """Candidate back expiries: the next weekly Fridays and monthlies >= front + gap."""
    out = []
    d = front + timedelta(days=7)
    while (d - front).days <= 60:
        if (d - front).days >= MIN_GAP_DAYS:
            out.append(d)
        d += timedelta(days=7)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    rows = []
    for e in events:
        sym = e["symbol"]; k = e["strike"]
        front = date.fromisoformat(e["expiry"])
        got = None
        for bexp in back_expiries(front):
            syms = [f"{sym}{bexp:%y%m%d}{r}{int(round(k * 1000)):08d}" for r in "CP"]
            try:
                bars = option_bars(client, syms, e["entry_day"], e["event_day"])
            except BrokerRefusal:
                continue
            cd = {b["t"][:10]: float(b["c"]) for b in (bars.get(syms[0]) or [])}
            pd_ = {b["t"][:10]: float(b["c"]) for b in (bars.get(syms[1]) or [])}
            if e["entry_day"] in cd and e["entry_day"] in pd_ and e["event_day"] in cd and e["event_day"] in pd_:
                got = (bexp, cd[e["entry_day"]] + pd_[e["entry_day"]], cd[e["event_day"]] + pd_[e["event_day"]])
                break
        if not got:
            continue
        bexp, back_entry, back_exit = got
        front_entry, front_exit = e["straddle_entry"], e["straddle_exit"]
        debit = back_entry - front_entry
        if debit <= 0:
            continue
        pnl = (back_exit - back_entry) - (front_exit - front_entry)
        rows.append({"symbol": sym, "event_day": e["event_day"], "strike": k, "front_expiry": e["expiry"],
                     "back_expiry": bexp.isoformat(), "gap_days": (bexp - front).days,
                     "front_entry": front_entry, "front_exit": front_exit, "back_entry": round(back_entry, 2),
                     "back_exit": round(back_exit, 2), "net_debit": round(debit, 2),
                     "pnl_per_unit": round(pnl, 2), "return_on_debit": pnl / debit,
                     "pnl_pct_spot": pnl / e["spot_entry"],
                     "front_over_back": front_entry / back_entry, "implied_move": e["implied_move"],
                     "realised_abs_move": e["realised_abs_move"], "straddle_return": e["straddle_return"]})
        print(f"  {sym:5s} {e['event_day']} front {front_entry:6.2f}->{front_exit:6.2f}  back({bexp}) {back_entry:6.2f}->{back_exit:6.2f}  "
              f"debit {debit:5.2f}  pnl {pnl:+6.2f} ({pnl / debit:+.0%} of debit)")
    if len(rows) < 15:
        print("too few calendars reconstructed -- an absence, not a result")
        return 1

    def t(xs):
        return statistics.mean(xs) / (statistics.pstdev(xs) / math.sqrt(len(xs))) if len(xs) > 2 and statistics.pstdev(xs) > 0 else None

    rod = [r["return_on_debit"] for r in rows]
    by_ratio = sorted(rows, key=lambda r: r["front_over_back"]); n = len(by_ratio)
    terc = [round(statistics.mean(r["return_on_debit"] for r in by_ratio[k * n // 3:(k + 1) * n // 3]), 4) for k in range(3)]
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": len(rows),
           "mean_return_on_debit": round(statistics.mean(rod), 4), "median_return_on_debit": round(statistics.median(rod), 4),
           "hit": round(sum(1 for x in rod if x > 0) / len(rod), 3), "t": round(t(rod), 2) if t(rod) else None,
           "worst": round(min(rod), 4), "best": round(max(rod), 4),
           "mean_pnl_pct_spot": round(statistics.mean(r["pnl_pct_spot"] for r in rows), 5),
           "return_by_front_over_back_tercile": terc,
           "median_front_over_back": round(statistics.median(r["front_over_back"] for r in rows), 3),
           "by_symbol": {s: {"n": sum(1 for r in rows if r["symbol"] == s),
                             "mean": round(statistics.mean(r["return_on_debit"] for r in rows if r["symbol"] == s), 4)}
                         for s in sorted({r["symbol"] for r in rows})},
           "rows": rows}
    print(f"\nEVENT_CALENDAR_v1 -- {len(rows)} calendars (short front straddle through the print, long back), real bars\n")
    print(f"  return on debit: mean {out['mean_return_on_debit']:+.1%} median {out['median_return_on_debit']:+.1%} hit {out['hit']:.0%} "
          f"t {out['t']} worst {out['worst']:+.0%} best {out['best']:+.0%} | mean P&L {out['mean_pnl_pct_spot']:+.3%} of spot")
    print(f"  by front/back straddle price ratio tercile (flat -> steep): {terc}; median ratio {out['median_front_over_back']}")
    print("  by name: " + ", ".join(f"{s} {v['mean']:+.0%}/{v['n']}" for s, v in out["by_symbol"].items()))
    print("  reading: the front/back ratio is the bot-in-the-wild's term-structure screen; if the steep tercile wins, the screen is the trade.")
    if args.json:
        path = _state_dir() / "event_calendar.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
