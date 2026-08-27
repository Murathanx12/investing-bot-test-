"""Grade every recorded belief-vs-chain reading whose market has resolved.

    AAT_ACCOUNT_ROLE=dev python -m scripts.belief_vs_chain_grade

For each row recorded by `scripts.belief_vs_chain` with a resolution date on
or before the last completed session, look up the actual close and score both
forecasters with the Brier score (lower is better). Pooled over enough rows
this answers "does Polymarket lead the chain, or lag it?" -- and it answers
it from outcomes, which is the only way the belief-gap idea earns a trade.
"""

from __future__ import annotations

import glob
import json
import statistics
import sys
from datetime import datetime, timezone

from alpha import config
from alpha.broker.alpaca import AlpacaPaper


def main() -> int:
    config.load_env()
    client = AlpacaPaper()
    root = config.__file__.rsplit("alpha", 1)[0] + "state/belief_vs_chain"
    # THE OUTPUT LIVES IN THE INPUT DIRECTORY, so it must be excluded by name.
    #
    # This script writes `GRADES.json` into `root` and then globs `root/*.json`
    # on the next run. The first run succeeded and wrote a 110-element LIST; every
    # run since crashed on `rec["symbol"]` with "list indices must be integers".
    # It has been dead since its first success, inside a loop that calls it every
    # cycle via a bare subprocess.call whose return code nobody read -- so it
    # failed silently for as long as it has existed.
    OUTPUT_NAME = "GRADES.json"
    files = [f for f in sorted(glob.glob(f"{root}/*.json"))
             if not f.endswith(OUTPUT_NAME)]
    if not files:
        print("no readings recorded")
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    closes: dict[tuple[str, str], float] = {}
    graded = []
    for path in files:
        rec = json.load(open(path, encoding="utf-8"))
        if not isinstance(rec, dict) or "symbol" not in rec:
            # Report and continue: one bad file must not cost the other 97.
            print(f"  SKIP {path}: not a reading "
                  f"({type(rec).__name__}, keys "
                  f"{sorted(rec)[:4] if isinstance(rec, dict) else 'n/a'})")
            continue
        sym = rec["symbol"]
        for r in rec["rows"]:
            if r["resolves"] >= today:
                continue
            key = (sym, r["resolves"])
            if key not in closes:
                bars = client.stock_bars(sym, start=r["resolves"], timeframe="1Day", adjustment="raw")["bars"].get(sym) or []
                hit = [b for b in bars if b["t"][:10] == r["resolves"]]
                if not hit:
                    continue
                closes[key] = float(hit[0]["c"])
            y = 1.0 if closes[key] > r["K"] else 0.0
            graded.append({"symbol": sym, "resolves": r["resolves"], "K": r["K"], "close": closes[key], "outcome": y,
                           "p_crowd": r["p_crowd"], "p_chain": r["p_chain"], "recorded": rec["generated_utc"],
                           "brier_crowd": (r["p_crowd"] - y) ** 2, "brier_chain": (r["p_chain"] - y) ** 2})
    if not graded:
        print("nothing resolved yet")
        return 0
    for g in graded:
        print(f"{g['symbol']} {g['resolves']} K={g['K']:<7} close {g['close']:<8} y={g['outcome']:.0f} "
              f"crowd {g['p_crowd']:.2f} chain {g['p_chain']:.2f}  brier crowd {g['brier_crowd']:.3f} chain {g['brier_chain']:.3f}")
    bc, bk = statistics.mean(g["brier_crowd"] for g in graded), statistics.mean(g["brier_chain"] for g in graded)
    print(json.dumps({"n": len(graded), "brier_crowd": round(bc, 4), "brier_chain": round(bk, 4),
                      "verdict": "crowd sharper" if bc < bk else "chain sharper" if bk < bc else "tie",
                      "caveat": "n is tiny until the loop records readings daily"}, indent=1))
    with open(f"{root}/GRADES.json", "w", encoding="utf-8") as fh:
        json.dump(graded, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
