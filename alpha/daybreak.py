"""The daily-loss latch: one bad session cannot become the whole competition.

WHAT WAS WRONG
==============
The night audit (`docs/night/2026-08-26_EXECUTION_AUDIT.md`, defect 2) found two
halves of the same hole:

- **No daily-loss latch anywhere on the execution path.** `grep` for
  `last_equity|day_start|daily_loss|halt` over `alpha/` and `scripts/` hit
  nothing. Equity was read once per entry pass against a CONSTANT
  `starting_equity = 100_000`, never against the day's opening equity.
- **The sizer did the opposite of a latch.** `_tournament_multiplier` raised
  risk 1.6-2.0x when the book was behind or negative late in the window. A -3.5%
  Monday gap was met with MORE risk, and by the final session a losing book was
  sized at 2.0x.

The rank argument for leaning in when behind is real -- a small loss and a large
loss score the same on a leaderboard, so only the upside branch has value. It is
also exactly the argument that turns a drawdown into a disqualification, and the
judged criteria ask for risk gates. The resolution is not to delete the rank
logic but to stop it compounding INTO a loss: lean in from flat, never from red.

WHY `last_equity` AND NOT A FILE WE WRITE
------------------------------------------
Alpaca's account object carries `last_equity` -- the previous session's closing
equity. Reading it means the latch:

- survives a process restart with no state to reload (the loops have been
  restarted mid-session more than once, and Session 9 found both of them dead);
- cannot drift from the venue's own view of the account;
- needs no first-pass-of-the-day bookkeeping, which is the part that breaks when
  the first pass of the day is the one that crashed.

A file we write would have to be correct across restarts, timezones and the two
account roles. `last_equity` is correct by construction because it is the number
the venue computed.

FAIL-CLOSED, DELIBERATELY
-------------------------
If `last_equity` cannot be read, `latched()` returns True with a CANNOT DETERMINE
reason and entries are refused. A risk gate that fails open is not a risk gate.
This can still go green in every normal state -- it is red only when the account
endpoint is unreadable, and an account we cannot read is not one we should be
adding risk to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

logger = logging.getLogger(__name__)

#: Entries stop for the session at this drawdown from the previous close.
#: Exits are UNAFFECTED -- a latch that also blocked exits would trap the
#: position that caused it.
DAILY_LOSS_LATCH = -0.03


@dataclass(frozen=True)
class DayState:
    equity: float
    last_equity: float
    drawdown: float
    derived: bool
    reason: str

    @property
    def latched(self) -> bool:
        return (not self.derived) or self.drawdown <= DAILY_LOSS_LATCH


def read(client: AlpacaPaper, acct: dict[str, Any] | None = None) -> DayState:
    """Today's drawdown against the previous close, from the venue."""
    try:
        acct = acct if acct is not None else client.account()
    except BrokerRefusal as exc:
        return DayState(0.0, 0.0, 0.0, False,
                        f"CANNOT DETERMINE the day's drawdown: account unreadable ({exc}). "
                        "Entries refused -- a risk gate that fails open is not a risk gate.")

    try:
        equity = float(acct.get("equity") or 0.0)
        last = float(acct.get("last_equity") or 0.0)
    except (TypeError, ValueError):
        equity = last = 0.0

    if equity > 0.0 and last <= 0.0:
        # A BRAND-NEW account reports last_equity=0 until its first close, so on
        # its first session this gate refused every entry (measured on staging,
        # 28 Aug: 12 forecasts, 12 refused, "CANNOT DETERMINE"). Every fleet
        # account and the judged account are new on kickoff day, so this is the
        # judged account sitting in cash on day one. A guard DERIVES or refuses:
        # the previous close of a new account is its funding, and the genesis
        # record (`scripts.genesis --freeze`, required before the first order)
        # froze that number. No genesis -> still refused, and the message says
        # which step was skipped.
        try:
            from alpha import config as _config, genesis as _genesis
            g = _genesis.load(_config.role())
        except Exception as exc:                                          # noqa: BLE001
            g = None
            logger.info("daybreak: genesis unreadable: %s", exc)
        if g is not None and g.starting_equity > 0:
            dd = equity / g.starting_equity - 1.0
            return DayState(equity, g.starting_equity, dd, True,
                            f"FIRST SESSION: the venue has no prior close (last_equity={last!r}); drawdown "
                            f"{dd:+.2%} measured against the GENESIS starting equity ${g.starting_equity:,.2f}.")
        return DayState(equity, last, 0.0, False,
                        f"CANNOT DETERMINE the day's drawdown: equity={equity!r} last_equity={last!r} "
                        "(a new account has no prior close) and NO GENESIS RECORD for this role to measure "
                        "against. Run `scripts.genesis --freeze` before the first order. Entries refused.")
    if equity <= 0.0 or last <= 0.0:
        return DayState(equity, last, 0.0, False,
                        f"CANNOT DETERMINE the day's drawdown: equity={equity!r} "
                        f"last_equity={last!r}. Entries refused.")

    dd = equity / last - 1.0
    if dd <= DAILY_LOSS_LATCH:
        return DayState(equity, last, dd, True, (
            f"DAILY LOSS LATCH: {dd:+.2%} against the previous close "
            f"(${last:,.0f} -> ${equity:,.0f}), past the {DAILY_LOSS_LATCH:.0%} limit. "
            "No new entries this session. Exits and stops are unaffected -- the latch "
            "stops the bleeding from spreading, it does not trap the position causing it."))
    return DayState(equity, last, dd, True,
                    f"day {dd:+.2%} vs previous close ${last:,.0f}; latch at "
                    f"{DAILY_LOSS_LATCH:.0%}, not tripped.")
