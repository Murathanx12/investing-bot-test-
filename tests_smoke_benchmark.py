"""PASSIVE_BETA_v2 -- replayed against the state the market account is really in.

Read from the venue on 2026-08-27: `PA3I7VTCC0BM`, equity $100,000.00, 0
positions, 1 SPY order with status `expired`. For nine days the scoreboard
quoted a benchmark that did not exist, because the seed script printed
SUBMITTED and everything downstream read that as SEEDED.
"""
from __future__ import annotations

from pathlib import Path

from alpha import benchmark

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


print("passive beta benchmark state")


class Fake:
    def __init__(self, positions=(), orders=()):
        self._p, self._o = list(positions), list(orders)

    def positions(self):
        return self._p

    def orders(self, status="open", limit=200):
        # The real defect: under status="open" the expired order is invisible.
        if status != "all":
            return [o for o in self._o if o.get("status") in benchmark.WORKING]
        return self._o


EXPIRED = [{"symbol": "SPY", "status": "expired", "filled_qty": "0"}]

st = benchmark.read(Fake(orders=EXPIRED))
check("the real 27-Aug state reads EXPIRED_UNFILLED", st.state == benchmark.EXPIRED_UNFILLED,
      st.line())
check("it is NOT active", not st.is_active)
check("EXPIRED_UNFILLED is distinct from UNSEEDED",
      benchmark.read(Fake()).state == benchmark.UNSEEDED,
      "'we tried and it failed' and 'we never tried' call for different acts")
check("the detail explains the OPG auction rule", "opening auction" in st.detail)

check("a working order is ORDER_SENT, not ACTIVE",
      (s := benchmark.read(Fake(orders=[{"symbol": "SPY", "status": "new"}]))).state
      == benchmark.ORDER_SENT and not s.is_active, s.line())
check("  and it says SUBMITTED is not SEEDED", "SUBMITTED is not" in s.detail)

check("a held position is ACTIVE",
      (s := benchmark.read(Fake(positions=[{"symbol": "SPY", "qty": "126"}],
                                orders=[{"symbol": "SPY", "status": "filled",
                                         "filled_qty": "126"}]))).is_active, s.line())
check("  and reports the quantity", abs(s.qty - 126) < 1e-9)

check("a second symbol in the benchmark account is OVERSEEDED",
      benchmark.read(Fake(positions=[{"symbol": "SPY", "qty": "1"},
                                     {"symbol": "QQQ", "qty": "1"}])).state
      == benchmark.OVERSEEDED)

# A partial fill is a position, and it is active. But a filled_qty with no
# position is not: that is a fill we have not been able to confirm.
check("filled_qty>0 with NO position is not ACTIVE",
      not benchmark.read(Fake(orders=[{"symbol": "SPY", "status": "filled",
                                       "filled_qty": "126"}])).is_active,
      "a fill that produced no position is not a fill this module will report")

# --- the wiring -------------------------------------------------------------
src = Path("scripts/seed_market.py").read_text(encoding="utf-8")
check("seed_market reads the state machine", "benchmark.read(" in src)
check("seed_market no longer refuses on `positions or orders`",
      "if positions or orders:" not in src,
      "that test reads EXPIRED_UNFILLED as 'already seeded' and blocks the fix forever")
check("seed_market REFUSES to resend an OPG order after one expired",
      "EXPIRED_UNFILLED" in src and "identical convention" in src)
check("seed_market offers the post_open convention", "post_open" in src)
check("seed_market verifies a POSITION after submitting",
      "final = benchmark.read(" in src and "final.is_active" in src)
check("and exits non-zero when none exists", "return 2" in src)

st_src = Path("scripts/benchmark_state.py").read_text(encoding="utf-8")
check("there is a standalone state reader", "benchmark.read(" in st_src)
check("which exits non-zero unless ACTIVE", "0 if st.is_active else 1" in st_src)

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
