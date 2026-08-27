"""Routes this project has already REFUTED with evidence, enforced in code.

WHY THIS FILE EXISTS
====================
On 25 Aug the engine opened a long straddle on AMD into NVDA's print, and long
NVDA premium into the same print. Both are routes this project had already killed
in writing, with samples:

- **peer straddle into a print** -- 290 relay legs, mean **-4.2%**, hit **34%**;
- **NVDA's own straddle into its own print** -- **0 for 8**.

The findings existed. The code did not know them. The AMD straddle lost **-$4,125**
and the NVDA structures **-$5,629**, and every one of those dollars was spent
re-learning something already on file.

**A finding that lives in a document instead of a guard is not a finding, it is a
memory.** This file is where a corpse becomes a refusal.

EVIDENCE DOES NOT INHERIT BY ANALOGY (rewritten 2026-08-27)
===========================================================
The first draft of this file did what it was built to prevent. It defined
`LONG_PREMIUM = {long_straddle, long_strangle, long_call, long_put}` and
`MEGA_CAP_PRINTERS = {NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AVGO}`, then
refused every pair of the two on the strength of one sample: **NVDA straddles,
0 for 8**.

That sample contains no AAPL, no MSFT, and **not one directional call**. Both
underlying measurements -- the 0-for-8 and the 290 relay legs
(`scripts/relay_backtest.py`, peer ATM straddles bought at the close before and
sold at the close after) -- measure ONE claim: *the chain does not underprice
E|move| into these prints*. A straddle pays only if the ABSOLUTE move beats the
price of both sides. A call pays if the SIGNED move clears one side. They are
bets on different moments of the same distribution, and evidence about the
second moment is silent about the first.

Left as written, the guard would have refused a bullish NVDA call on 26 Aug --
the print where the guide surprised by +3.8 sigma and the stock rose ~6.8%
against an implied move of ~5.4%. A guard that blocks the trade the research was
RIGHT about is worse than no guard: it converts a good finding into a permanent
tax, and it does so invisibly, because a refusal looks like discipline.

So every row now carries the scope of its own sample, and `check` refuses only
inside it. Where a route is untested, that is recorded in `UNMEASURED` and it
stays ADMISSIBLE -- a check that did not run is not a check that passed, and it
is not a check that failed either.

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

#: Structures whose payoff depends on the ABSOLUTE move -- long the second
#: moment, which is what both measurements below actually tested.
LONG_VOL = frozenset({"long_straddle", "long_strangle"})

#: Structures whose payoff depends on the SIGNED move. NOTHING in this file has
#: evidence about these into a print. Named so the gap is visible rather than
#: inferred from an absence.
LONG_DIRECTIONAL = frozenset({"long_call", "long_put"})

#: Back-compat alias. Deliberately NOT the union of the two above: nothing may
#: refuse on that union again without a sample covering both halves.
LONG_PREMIUM = LONG_VOL

#: Names whose OWN prints have been measured, mapped to the sample. One entry,
#: because one name has been measured. Adding a symbol here requires adding its
#: sample -- the dict IS the evidence scope, not a convenience list.
MEASURED_OWN_PRINT: dict[str, str] = {
    # 1 FOR 9, and the ONE is the most recent event. Recorded 2026-08-27 by
    # pricing the 26 Aug print straddle directly, because the backtest could not
    # reconstruct it yet (the 28 Aug contracts have not expired):
    #   NVDA260828 @210, entry 26 Aug close $12.45 (implied 5.94%), exit 27 Aug
    #   $20.01 -> +60.7%. Realised +9.61% CLEARED the breakeven.
    # Hiding an inconvenient winner is the same failure as hiding a loser, and
    # this is the first observation toward this row's own reopening condition.
    # The other eight average -45.8% at t -4.37, so the row STANDS -- but see
    # docs/FINDING_2026-08-27_THE_NINTH_EVENT.md: the CALL paid +219% against the
    # straddle's +60.7%, so even on the event that broke the streak the sign-blind
    # structure was the wrong way to own it.
    "NVDA": ("NVDA straddle into its own print: 1 for 9, mean about -34%; the 8 "
             "reconstructed events run -45.8% at paired t -4.37 and the 9th (2026-08-26) "
             "PAID +60.7% (docs/FINDING_2026-08-25_STRADDLE_BACKTEST.md, "
             "docs/FINDING_2026-08-27_THE_NINTH_EVENT.md)"),
    # Measured 2026-08-27 because PANW prints on 1 Sep, inside the contest, and
    # was admissible only because nobody had looked. Six reconstructed prints,
    # ATM straddle bought at the close before and sold at the close after:
    #   2025-02-14 -63.5%  2025-05-21  -2.5%  2025-08-19 -57.0%
    #   2025-11-20  -6.5%  2026-02-18 -21.0%  2026-06-03 -47.4%
    # ALL SIX NEGATIVE. Not a mean dragged down by a tail -- every event.
    "PANW": ("PANW straddle into its own print: 0 for 6, mean -33.0%, median -34.2%, "
             "paired t(realised-implied) -2.5 (scripts/event_straddle_backtest, "
             "docs/FINDING_2026-08-27_PANW_AND_AVGO.md)"),
}

#: Broad index ETFs whose weekly ATM straddle has been measured to expiry.
#: `scripts/index_premium_backtest`, 381 weeks 2024-02 -> 2026-08, 1.3% haircut
#: per side. This is the row that closes the gap named in
#: `docs/FINDING_2026-08-27_NINETY_FOUR_PERCENT_WAS_ONE_STRUCTURE.md`: SPY and
#: QQQ straddles cost $14,711 of the $23,306 realised loss, and nothing refused
#: them because they carried no print and no peer relation.
MEASURED_INDEX_STRADDLE: dict[str, str] = {
    "SPY": "SPY weekly ATM straddle to expiry: buyer -31.8%/wk, t -5.90, hit 24.4%, n=127",
    "QQQ": "QQQ weekly ATM straddle to expiry: buyer -2.5%/wk, t -0.39, hit 38.6%, n=127",
    "IWM": "IWM weekly ATM straddle to expiry: buyer -25.1%/wk, t -4.83, hit 29.1%, n=127",
}

#: The honest caveat, carried on the refusal itself so it cannot be read as
#: stronger than it is. Pooled the buyer is -19.8%/wk on t -5.90 against an MDE
#: of 9.4% -- resolvable. BY YEAR it decays hard and 2026 does NOT resolve.
INDEX_STRADDLE_CAVEAT = (
    "pooled buyer -19.8%/wk t -5.90 n=381 (RESOLVABLE, MDE 9.4%); but 2024 -31.7%, "
    "2025 -19.5%, 2026 -1.8% t -0.24 (NOT resolvable), and QQQ 2026 is +14.9% for the "
    "buyer. The refusal rests on the MEDIAN, which is negative in every year including "
    "2026 (-15.9%), and on hit rate staying a minority (42.2% in 2026). Over a five-"
    "decision window terminal wealth follows the median path, not the mean"
)

#: Routes that are simply untested. Kept in code so a reader can tell "we looked
#: and it lost" from "we never looked" without reading eight documents, and so
#: that adding evidence has an obvious home.
UNMEASURED: tuple[tuple[str, str], ...] = (
    ("long_call / long_put into any print",
     "no sample. The 0-for-8 and the 290 relay legs are both ABSOLUTE-move tests; "
     "neither contains a directional leg. ADMISSIBLE."),
    ("long straddle into AAPL / MSFT / GOOGL / AMZN / META / TSLA / AMD / MU prints",
     "MEASURED 2026-08-27 and NONE OF THEM RESOLVES. Per-event mean vs the smallest "
     "effect each sample could detect at 80% power: AAPL -16.8% (MDE 29%, win 20%), "
     "AMZN -13.2% (42%), GOOGL -12.9% (45%), MU -2.6% (45%), AMD +7.7% (54%), "
     "META +5.1% (53%), MSFT +14.1% (60%), TSLA +20.8% (46%, n=17). Not one observed "
     "effect exceeds its own MDE. Pooling does not rescue it -- 86 events, mean +1.9%, "
     "median -11.8%, t 0.31 -- and pooling is the wrong instrument anyway, because "
     "PANW is 0-for-6 at t -2.5 while TSLA is +20.8%: an average of different things. "
     "So the standing belief that 'the chain overprices mega-cap prints' is TWO NAMES, "
     "NVDA and PANW, and the old guard was wrong on the majority of the eight it "
     "covered. ALL ADMISSIBLE. "
     "docs/FINDING_2026-08-27_THE_MEGA_CAP_BELIEF_DOES_NOT_GENERALISE.md"),
    ("peer DIRECTIONAL premium into an originator's print",
     "no sample. relay_backtest measured peer STRADDLES. ADMISSIBLE."),
    ("long straddle into AVGO's own print",
     "MEASURED and UNRESOLVED, which is why it is here rather than above. 8 prints, "
     "mean +32.0%, median +21.6%, 5 of 8 positive, paired t +1.18. It does NOT survive "
     "the tail: dropping the single 2024-12-13 event (+191%) takes the mean to +9.2% and "
     "t to 0.66, and that one observation is 62% of all positive return. MDE at 80% power "
     "on n=8 is 74.8% per event against an observed 32% -- the sample cannot resolve this "
     "either way, and the returns are at CLOSES, before crossing a spread twice on an "
     "option costing ~8.6% of spot. ADMISSIBLE, and buying it is a coin flip with a "
     "receipt, not an edge. AVGO prints 2 Sep, inside the contest, and is the obvious "
     "thing to buy; this row exists so nobody buys it on the +32%."),
)


@dataclass(frozen=True)
class Refusal:
    route: str
    reason: str
    evidence: str
    reopens_if: str
    #: The exact population the evidence was measured on, printed with the
    #: refusal so a reader can see whether this trade is inside it.
    scope: str = ""

    def line(self) -> str:
        tail = f" scope: {self.scope}" if self.scope else ""
        return f"REFUTED ROUTE {self.route}: {self.reason} [{self.evidence}]{tail}"


#: Below this many days to expiry, the index-straddle sample says NOTHING.
#:
#: The measurement is a WEEKLY ATM straddle HELD TO EXPIRY -- entry about five
#: sessions out, carrying overnight theta the whole way. A 0DTE structure opened
#: at a prior close and closed at 10:45 the next morning is a different object
#: with a different sample: 28 NFP releases, SPY 0DTE ATM straddle, prior close
#: -> 10:45 ET, mean +16.8%, median +6.8%, hit 57%, 9 of the last 12 positive
#: (`scripts/nfp_trade.py`, a frozen contract with two gates).
#:
#: THIS CONSTANT EXISTS BECAUSE THE FIRST VERSION OF THE INDEX RULE DID NOT HAVE
#: IT. Its `scope` string said "weekly ATM held to expiry" while `check()` looked
#: only at symbol and kind, so it refused EVERY SPY straddle -- including the NFP
#: trade, which is the best-evidenced opportunity in the contest window. Written
#: on 2026-08-27, four hours after this same file was rewritten to stop evidence
#: inheriting by analogy. A scope that lives in a docstring is not a scope.
#:
#: 2, not 1: the SPY and QQQ straddles that cost $14,711 were opened 25 Aug
#: against a 28 Aug expiry -- three days -- and must stay refused.
INDEX_STRADDLE_MIN_DTE = 2.0

#: Above this many days to expiry, the PRINT-straddle samples say nothing.
#:
#: Both print samples -- NVDA 0-for-8, PANW 0-for-6, and the 290 relay legs --
#: reconstruct the ATM straddle at the NEAREST EXPIRY AFTER the print, which is
#: 0-7 days out. That structure is almost entirely event variance. A 30-day
#: straddle opened into the same print is mostly ordinary vol with the event as a
#: minority of its price, and nothing here has measured it.
#:
#: Added in the same pass that fixed the index rule, by asking the same question
#: of every other row rather than only of the one that had just bitten. The bound
#: is generous (10 vs a 0-7 sample) because the direction of error matters:
#: refusing slightly outside the sample costs a trade, and the trades inside the
#: sample are the ones that lost the money.
PRINT_STRADDLE_MAX_DTE = 10.0


def check(*, symbol: str, kind: str, event_ahead_on_symbol: bool,
          originators_printing: list[str] | None = None,
          days_to_expiry: float | None = None) -> Refusal | None:
    """The refusal for this (symbol, structure) pair, or None.

    `event_ahead_on_symbol` -- this symbol's OWN print is still ahead.
    `originators_printing` -- names whose print is ahead and for which `symbol`
    is a declared peer (from `relay.RELAY_MAP`). A peer trade is only refuted
    when the ORIGINATOR is the one printing; peers with no pending print are
    ordinary names and this says nothing about them.

    Only LONG-VOL structures can be refused here. A `long_call` reaching this
    function returns None by design -- see the module docstring.
    """
    if kind not in LONG_VOL:
        return None

    sym = symbol.upper()

    _dte_in_scope = days_to_expiry is None or days_to_expiry <= PRINT_STRADDLE_MAX_DTE

    if event_ahead_on_symbol and sym in MEASURED_OWN_PRINT and _dte_in_scope:
        return Refusal(
            route="LONG_VOL_INTO_OWN_MEASURED_PRINT",
            reason=(f"{kind} on {sym} whose own print is still ahead. On the sample below the "
                    "chain did not underprice the absolute move, so buying both sides is the "
                    "documented losing side. A DIRECTIONAL structure is not covered by this."),
            evidence=MEASURED_OWN_PRINT[sym],
            reopens_if=("a forward sample of >=20 prints on this symbol in which the realised "
                        "absolute move beats the entry straddle after costs. ONE of those "
                        "twenty now exists: 2026-08-26 paid +60.7%. Nineteen to go, and the "
                        "count is kept on the row rather than in a document"),
            scope=(f"{sym} only, long_straddle/long_strangle only, own print ahead, "
                   f"<= {PRINT_STRADDLE_MAX_DTE:g} days to expiry (the sample reconstructs "
                   "the NEAREST expiry after the print)"),
        )

    if sym in MEASURED_INDEX_STRADDLE and (days_to_expiry is None
                                           or days_to_expiry >= INDEX_STRADDLE_MIN_DTE):
        return Refusal(
            route="INDEX_STRADDLE_TO_EXPIRY",
            reason=(f"{kind} on {sym}. Buying the broad index's ABSOLUTE move and holding it "
                    "to expiry is measured negative: the buyer wins a minority of weeks and "
                    "the median week is a large loss. This project has one more negative "
                    "sample of its own -- SPY and QQQ straddles opened 2026-08-25 realised "
                    "-$14,711, 63% of both books' losses, with slippage only 3.2% of it."),
            evidence=f"{MEASURED_INDEX_STRADDLE[sym]}; {INDEX_STRADDLE_CAVEAT}",
            reopens_if=("a forward sample on this symbol clearing zero after costs, OR a "
                        "structure that is NOT held to expiry -- the measurement is of the "
                        "hold-to-expiry payoff and the loss mechanism is theta (exp1's open "
                        "book decomposes to delta +$3,106, gamma +$1,054, vega +$1,168 "
                        "against theta -$5,048: right three ways and still losing to rent). "
                        "A spread-financed or early-exit expression is a different object "
                        "and this says nothing about it"),
            scope=(f"{sym} only, long_straddle/long_strangle only, >= "
                   f"{INDEX_STRADDLE_MIN_DTE:g} days to expiry (the sample is a WEEKLY straddle "
                   "held to expiry; a 0DTE intraday structure is a different object with its "
                   "own 28-release sample), 2024-02 to 2026-08"),
        )

    if originators_printing and _dte_in_scope:
        orig = ", ".join(sorted(originators_printing))
        return Refusal(
            route="PEER_LONG_VOL_INTO_PRINT",
            reason=(f"{kind} on {sym}, a declared peer of {orig} whose print is ahead. "
                    "The peers' chains already widen for the originator's date by more than "
                    "the peers then move. Paying for the peer's absolute move is refuted."),
            evidence="290 relay legs, mean -4.2%, hit 34%, t -2.0 (scripts/relay_backtest.py)",
            reopens_if=("a pre-registered re-test on >=100 fresh legs clearing zero after costs; "
                        "the 2026-08-25 AMD straddle (-$4,125) is one more negative sample"),
            scope=(f"peer ATM straddles/strangles only, originator print ahead, <= "
                   f"{PRINT_STRADDLE_MAX_DTE:g} days to expiry (the 290 legs are all at the "
                   "nearest expiry after the originator's print)"),
        )
    return None


def peers_printing(symbol: str, printing: set[str]) -> list[str]:
    """Originators in `printing` for which `symbol` is a declared peer."""
    from alpha.brains.relay import RELAY_MAP

    sym = symbol.upper()
    return [o for o, peers in RELAY_MAP.items()
            if o.upper() in {p.upper() for p in printing}
            and sym in {p.upper() for p in peers}]
