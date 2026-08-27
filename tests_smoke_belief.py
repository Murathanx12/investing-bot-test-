"""BELIEF_TO_POSITION_AUDIT_v1 -- the marking arithmetic, on fake bars.

The live numbers are in the finding. These check the thing that would silently
corrupt them: which bar is the base, which is the mark, and that a symbol with
no session after the event is REPORTED as such rather than marked at its own
base and returning a tidy 0.00%.
"""
from __future__ import annotations

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("belief -> position marking")

from scripts.belief_to_position import DEFAULT_LADDER, marks       # noqa: E402


class Fake:
    def __init__(self, series):
        self._s = series

    def stock_bars_multi(self, syms, start=None, timeframe=None):
        return {s: self._s[s] for s in syms if s in self._s}


def bar(d, o, c):
    return {"t": f"{d}T00:00:00Z", "o": o, "c": c}


SERIES = {
    # base close 100 -> gaps to 106 -> settles 110
    "SRC": [bar("2026-08-25", 99, 98), bar("2026-08-26", 99, 100),
            bar("2026-08-27", 106, 110)],
    # base 200, gaps UP but closes DOWN -- the AMD/MU shape
    "PROXY": [bar("2026-08-26", 199, 200), bar("2026-08-27", 206, 194)],
    # no session after the event
    "STALE": [bar("2026-08-26", 50, 50)],
}

m = marks(Fake(SERIES), ["SRC", "PROXY", "STALE"], event_day="2026-08-26")

check("the base is the EVENT day's close, not the day before",
      abs(m["SRC"]["base_close"] - 100.0) < 1e-9, str(m["SRC"]))
check("the mark is the LATEST session after the event",
      m["SRC"]["mark_day"] == "2026-08-27" and abs(m["SRC"]["mark_close"] - 110.0) < 1e-9)
check("total return is close-to-close", abs(m["SRC"]["return_pct"] - 0.10) < 1e-9)
check("the GAP is measured to the next OPEN, separately",
      abs(m["SRC"]["gap_pct"] - 0.06) < 1e-9,
      "an event that is fully in the gap and an event that trends are different things")

check("a proxy that gaps up and closes down reports a NEGATIVE total",
      m["PROXY"]["return_pct"] < 0 and m["PROXY"]["gap_pct"] > 0,
      f"{m['PROXY']}")
check("  which is the AMD/MU shape and must not be hidden by the gap",
      abs(m["PROXY"]["return_pct"] - (194 / 200 - 1)) < 1e-9)

check("a symbol with NO session after the event is an ERROR, not a 0.00%",
      "error" in m["STALE"] and "no session after" in m["STALE"]["error"],
      "marking it against its own base would print a tidy zero and mean nothing")
check("  and it carries no return field to be averaged by mistake",
      "return_pct" not in m["STALE"])

# --- the ladder is source-first, on purpose --------------------------------
ladder = DEFAULT_LADDER["2026-08-26"]
check("the ladder leads with the SOURCE", ladder[0][0] == "NVDA",
      "DIRECT_FIRST is an ordering, and the comparison is against row 0")
check("it contains a competitor, a supplier, a basket and two baselines",
      {s for s, _ in ladder} >= {"AMD", "MU", "SMH", "QQQ", "SPY"})
check("the competitor's role names TWO edges with opposite signs",
      any("OPPOSITE signs" in w for s, w in ladder if s == "AMD"),
      "AI-demand beta positive, NVDA-competitive residual negative")
check("the supplier's role records what the graph predicted",
      any("most constrained node" in w for s, w in ladder if s == "MU"),
      "so the row can be graded against the prediction, not just the price")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
