"""Routes this project has already REFUTED with evidence, enforced in code.

WHY THIS FILE EXISTS
====================
On 25 Aug the engine opened a long straddle on AMD into NVDA's print, and short
NVDA calls into the same print. Both are routes this project had already killed
in writing, with samples:

- **peer straddle into a print** -- 290 relay legs, mean **-4.2%**, hit **34%**;
- **long premium into a mega-cap print** -- the chain OVERPRICES these. NVDA is
  **0 for 8**. Buying the straddle is the documented losing side.

The findings existed. The code did not know them. The AMD straddle lost **-$4,125**
and the NVDA structures **-$5,629**, and every one of those dollars was spent
re-learning something already on file.

**A finding that lives in a document instead of a guard is not a finding, it is a
memory.** This file is where a corpse becomes a refusal.

WHAT THIS IS NOT
================
Not a view on whether the underlying MECHANISM is dead. `MECHANISM_REJECTED` is
reserved for genuinely broad evidence (CLAUDE.md, "explore dirty, promote clean").
These are specific EXPRESSIONS with measured negative expectancy, and each row
names the measurement so it can be argued with rather than obeyed.

Each rule states what would REOPEN it. A guard with no reopening condition is a
permanent red line, and permanent red lines teach the reader to skim.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Structures that are LONG premium -- they pay theta and need a move to exceed
#: what the chain already charges for it.
LONG_PREMIUM = frozenset({"long_straddle", "long_strangle", "long_call", "long_put"})

#: Names whose prints the chain has been measured to OVERPRICE. Deliberately a
#: short, evidenced list rather than "any large cap": the measurement is on these.
MEGA_CAP_PRINTERS = frozenset({"NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO"})


@dataclass(frozen=True)
class Refusal:
    route: str
    reason: str
    evidence: str
    reopens_if: str

    def line(self) -> str:
        return f"REFUTED ROUTE {self.route}: {self.reason} [{self.evidence}]"


def check(*, symbol: str, kind: str, event_ahead_on_symbol: bool,
          originators_printing: list[str] | None = None) -> Refusal | None:
    """The refusal for this (symbol, structure) pair, or None.

    `event_ahead_on_symbol` -- this symbol's OWN print is still ahead.
    `originators_printing` -- names whose print is ahead and for which `symbol`
    is a declared peer (from `relay.RELAY_MAP`). A peer trade is only refuted
    when the ORIGINATOR is the one printing; peers with no pending print are
    ordinary names and this says nothing about them.
    """
    if kind not in LONG_PREMIUM:
        return None

    if event_ahead_on_symbol and symbol.upper() in MEGA_CAP_PRINTERS:
        return Refusal(
            route="LONG_PREMIUM_INTO_MEGACAP_PRINT",
            reason=(f"{kind} on {symbol} whose own print is still ahead. The chain OVERPRICES "
                    "these events, so buying the move is the documented losing side."),
            evidence="NVDA straddle into its own print: 0 for 8",
            reopens_if=("a forward sample of >=20 mega-cap prints in which the realised move "
                        "beats the entry straddle after costs"),
        )

    if originators_printing:
        orig = ", ".join(sorted(originators_printing))
        return Refusal(
            route="PEER_LONG_PREMIUM_INTO_PRINT",
            reason=(f"{kind} on {symbol}, a declared peer of {orig} whose print is ahead. "
                    "Paying premium on the PEER of an event is refuted, not merely unproven."),
            evidence="290 relay legs, mean -4.2%, hit 34%",
            reopens_if=("a pre-registered re-test on >=100 fresh legs clearing zero after costs; "
                        "the 2026-08-25 AMD straddle (-$4,125) is one more negative sample"),
        )
    return None


def peers_printing(symbol: str, printing: set[str]) -> list[str]:
    """Originators in `printing` for which `symbol` is a declared peer."""
    from alpha.brains.relay import RELAY_MAP

    sym = symbol.upper()
    return [o for o, peers in RELAY_MAP.items()
            if o.upper() in {p.upper() for p in printing}
            and sym in {p.upper() for p in peers}]
