"""BELIEF_TO_POSITION_AUDIT_v1 -- where the information died between knowing and owning.

    AAT_ACCOUNT_ROLE=dev python -m scripts.belief_to_position --event 2026-08-26
    AAT_ACCOUNT_ROLE=dev python -m scripts.belief_to_position --event 2026-08-26 --json

THE QUESTION
============
Not "did we make money". Not "was the research right". The research WAS right:
the sealed vector ranked NVDA's Q3 guide the #1 variable, flagged memory as the
constrained node hours before the filing confirmed $160bn of memory commitments,
and Murat said beforehand that NVDA would beat.

The question is **at which stage the information stopped being worth money**:

    PREDICTION   was the direction right?
    SECURITY     did we express it on the right NAME?
    INSTRUMENT   did we express it in the right STRUCTURE?
    SIZING       was it big enough to matter?
    TIMING       did we get in and out at the right moment?
    GATING       did a guard refuse the trade that would have worked?

Those call for completely different fixes and they are usually collapsed into
"the strategy lost". This separates them by marking every alternative that was
available at the same timestamp, at real prices.

WHY IT MARKS PROXIES IT DID NOT TAKE
====================================
A causal graph will happily say NVDA-beats -> AI-demand-up -> AMD-up. Whether
that edge is worth trading is a question about MAGNITUDE and SIGN, not about
whether the arrow exists. The only way to know is to mark them both.

Every proxy is priced from the same close as the direct expression, so the
comparison is like-for-like: no lookahead, no benchmark switch, no compounding
convention change midway.

WHAT IT CANNOT DO
=================
It marks SHARES. It does not reconstruct what an option would have paid, because
that needs the entry chain and this runs after the fact. The shares comparison is
the DIRECT_FIRST question -- "did the proxy beat the source" -- which is the one
the 25 Aug book got wrong, and it is answerable without a chain.

`--json` writes `state/belief_to_position_<event>.json`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper

STATE = Path(os.getenv("AAT_LEDGER_DIR") or "state")

#: The source of the information, and every alternative expression of it that
#: was liquid and available at the same close. Ordered source-first on purpose.
DEFAULT_LADDER: dict[str, list[tuple[str, str]]] = {
    "2026-08-26": [
        ("NVDA", "THE SOURCE -- the company whose print produced the information"),
        ("AVGO", "causal peer: the other large AI accelerator vendor"),
        ("AMD",  "causal peer: the competitor. TWO edges with OPPOSITE signs -- a "
                 "positive AI-demand beta and a negative NVDA-competitive residual"),
        ("MU",   "supplier: memory. NEEDS_GRAPH ranked it the most constrained node, "
                 "and the filing then disclosed +$160bn of commitments 'primarily "
                 "related to the procurement of memory'"),
        ("SMH",  "sector basket: the theme with the stock-selection removed"),
        ("QQQ",  "market baseline: the index the whole thesis floats on"),
        ("SPY",  "market baseline: broader still"),
    ],
}


def marks(client: AlpacaPaper, symbols: list[str], *, event_day: str,
          horizon_days: int = 6) -> dict[str, dict]:
    """Close before the reaction -> latest close, per symbol. Real bars only."""
    start = (
        f"{event_day[:4]}-{event_day[5:7]}-"
        f"{max(1, int(event_day[8:10]) - horizon_days):02d}"
    )
    bars = client.stock_bars_multi(sorted(set(symbols)), start=start, timeframe="1Day")
    out: dict[str, dict] = {}
    for sym, rows in bars.items():
        rows = [r for r in rows if r.get("t")]
        base = next((r for r in rows if r["t"][:10] == event_day), None)
        after = [r for r in rows if r["t"][:10] > event_day]
        if base is None or not after:
            out[sym] = {"error": f"no bar on {event_day}" if base is None
                        else "no session after the event yet"}
            continue
        b, a = float(base["c"]), float(after[-1]["c"])
        out[sym] = {
            "base_day": event_day, "base_close": b,
            "mark_day": after[-1]["t"][:10], "mark_close": a,
            "open_next": float(after[0]["o"]),
            "gap_pct": float(after[0]["o"]) / b - 1.0,
            "return_pct": a / b - 1.0,
        }
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event", default="2026-08-26",
                   help="the close BEFORE the market reacts (the print's own day for amc)")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()

    ladder = DEFAULT_LADDER.get(args.event)
    if args.symbols:
        ladder = [(s, "supplied on the command line") for s in args.symbols]
    if not ladder:
        print(f"no ladder defined for {args.event}; pass --symbols")
        return 2

    client = AlpacaPaper()
    m = marks(client, [s for s, _ in ladder], event_day=args.event)

    print(f"BELIEF -> POSITION   event close {args.event}")
    print(f"  every row priced from the SAME close, so the comparison is like-for-like\n")
    print(f"  {'sym':<6}{'gap':>9}{'total':>9}   role")
    src = m.get(ladder[0][0], {})
    rows = []
    for sym, why in ladder:
        d = m.get(sym, {})
        if "error" in d:
            print(f"  {sym:<6}{'--':>9}{'--':>9}   {d['error']}")
            continue
        rows.append((sym, d["return_pct"], why))
        print(f"  {sym:<6}{d['gap_pct']:>+8.2%}{d['return_pct']:>+9.2%}   {why[:70]}")

    if src and "return_pct" in src and len(rows) > 1:
        source_sym, source_r, _ = rows[0]
        print(f"\n  THE DIRECT-FIRST QUESTION: did any proxy beat the source?")
        beat = [(s, r) for s, r, _ in rows[1:] if r > source_r]
        for s, r, _ in rows[1:]:
            delta = r - source_r
            verdict = "BEAT the source" if delta > 0 else "lost to the source"
            print(f"    {s:<6}{r:>+8.2%}  vs {source_sym} {source_r:+.2%}  "
                  f"= {delta:+.2%}  {verdict}")
        print(f"\n  {len(beat)} of {len(rows)-1} proxies beat the source.")
        neg = [(s, r) for s, r, _ in rows[1:] if r < 0]
        if neg:
            print(f"  {len(neg)} moved the WRONG WAY entirely: "
                  + ", ".join(f"{s} {r:+.2%}" for s, r in neg))
            print("  A causal arrow that exists is not an edge with a sign you can spend.")

    if args.json:
        dest = STATE / f"belief_to_position_{args.event}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(
            {"event": args.event, "ladder": [{"symbol": s, "role": w} for s, w in ladder],
             "marks": m}, indent=2, sort_keys=True) + "\n")
        print(f"\n  receipt: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
