"""What KIND of refusal was that? -- one class per gate, derived from the row.

The ledger records `refusal_reason` as the sentence the gate wrote, which is the
right thing to store: it carries the numbers, the thresholds and the incident
each gate was built from. It is not groupable. 7,599 refused rows normalise to
43 distinct sentences, and grouping by prefix splits one gate across a dozen
buckets because the numbers are inside the text.

So the class is DERIVED here, from ordered patterns, and never guessed. A row
that matches nothing is `UNCLASSIFIED` and is COUNTED in every report that uses
this module -- a bucket that quietly absorbs a third of the ledger would let a
report claim it had measured the gates while measuring two of them.

Ordered longest/most-specific first: "BOOK LIMIT: MAX_BOOK_STRESS" must not be
read as the generic admission refusal.
"""

from __future__ import annotations

import re
from collections import Counter

#: (class, pattern). FIRST match wins, so order is meaning.
PATTERNS: tuple[tuple[str, str], ...] = (
    # -- FORECAST-level refusal, matched BEFORE the gate it quotes -------------
    # "8 structures enumerated at 2026-08-28, none cleared the gates. aggregate
    # convex risk is already 61%..." is a refusal of the whole FORECAST, and it
    # names the gate that stopped the best structure. Matching the tail first put
    # ~636 forecast-level rows into AGGREGATE_RISK / MDE / EDGE_BELOW_BAR and
    # inflated the biggest bucket in the table with rows of a different kind.
    # The wrapper is the class; the gate it quotes is the SUB-class.
    ("NO_STRUCTURE_CLEARED", r"structures enumerated at .* none cleared the gates"),
    # -- the 2026-08-29 Monday-safety gates -----------------------------------
    ("GROSS_NOTIONAL", r"^GROSS:|ADMISSION: GROSS:"),
    ("DRIVER_CONCENTRATION", r"^DRIVER:|ADMISSION: DRIVER:"),
    ("CROSS_BOOK", r"^CROSS-BOOK:"),
    ("OPENING_RANGE", r"^OPENING RANGE:"),
    ("CONVEX_RULE", r"^CONVEX RULE:"),
    # -- admission control ----------------------------------------------------
    ("BOOK_LIMIT", r"BOOK LIMIT:"),
    ("PER_NAME_CONCENTRATION", r"CONCENTRATION: .* would carry"),
    ("TOMORROWS_OPTIONALITY", r"TOMORROW'S OPTIONALITY"),
    ("THETA_BURN", r"THETA BURN:"),
    ("DELTA_STRESS", r"DELTA STRESS:"),
    # -- risk envelope --------------------------------------------------------
    ("DAILY_LOSS_LATCH", r"DAILY LOSS LATCH"),
    ("AGGREGATE_RISK", r"aggregate (convex )?risk is already"),
    ("CAPITAL_ROUNDS_TO_ZERO", r"Rounds to zero contracts"),
    # -- evidence and edge ----------------------------------------------------
    ("REFUTED_ROUTE", r"^REFUTED|refuted route|measured as negative"),
    ("MDE", r"minimum detectable move"),
    ("EDGE_BELOW_BAR", r"disagreement with the chain is"),
    ("CLAIM_MISMATCH", r"^CLAIM "),
    # -- the tournament between structures on ONE forecast ---------------------
    # These are not refusals of the IDEA; they are the ranker preferring another
    # expression of the same idea, or preferring cash. Counting them as "the gate
    # discarded edge" would be double counting -- the edge was usually taken, in
    # a different instrument. Their own class, and their own kind.
    ("OUTRANKED_BY_SIBLING", r"out-ranked on (median|mean|EV)/max-loss by"),
    ("CASH_BEATS_IT", r"^CASH beats it"),
    ("SPREAD_EATS_THE_EDGE", r"round-trip spread is .* of max loss"),
    ("CLAIM_MISMATCH_PAIR", r"DIRECTION-only forecast"),
    ("DRAWDOWN_UNKNOWN", r"CANNOT DETERMINE the day's drawdown"),
    # -- book state -----------------------------------------------------------
    ("ALREADY_HELD", r"already positioned in this book"),
    ("BOOK_UNBOUNDED", r"BOOK UNBOUNDED"),
    ("EVENT_NODE_CAP", r"event node .* already carries"),
    ("CHAIN_UNUSABLE", r"chain pro|no quotable chain|quote unusable"),
)

_COMPILED = tuple((name, re.compile(pat, re.IGNORECASE)) for name, pat in PATTERNS)

UNCLASSIFIED = "UNCLASSIFIED"

#: Classes the engine imposes because of the BOOK's state rather than the
#: candidate's merit. A counterfactual on these asks "should the book have had
#: room", which is a different question from "was this idea good", and mixing
#: the two is how a refusal report turns into an argument for more leverage.
BOOK_STATE_CLASSES = frozenset({
    "GROSS_NOTIONAL", "DRIVER_CONCENTRATION", "CROSS_BOOK", "BOOK_LIMIT",
    "PER_NAME_CONCENTRATION", "TOMORROWS_OPTIONALITY", "THETA_BURN", "DELTA_STRESS",
    "DAILY_LOSS_LATCH", "AGGREGATE_RISK", "CAPITAL_ROUNDS_TO_ZERO", "ALREADY_HELD",
    "BOOK_UNBOUNDED", "EVENT_NODE_CAP", "DRAWDOWN_UNKNOWN",
})

#: The ranker preferring a SIBLING structure on the same forecast, or preferring
#: cash. Neither a book-state limit nor a judgement on the idea: the idea was
#: usually taken, in another instrument. Counting these as "edge the gate threw
#: away" double-counts the same forecast, which is how a refusal report inflates
#: its own indictment.
TOURNAMENT_CLASSES = frozenset({
    "OUTRANKED_BY_SIBLING", "CASH_BEATS_IT", "SPREAD_EATS_THE_EDGE",
})

#: Classes about the CANDIDATE: its edge, its evidence, its structure.
MERIT_CLASSES = frozenset({
    "REFUTED_ROUTE", "MDE", "EDGE_BELOW_BAR", "CLAIM_MISMATCH",
    "NO_STRUCTURE_CLEARED", "OPENING_RANGE", "CONVEX_RULE", "CHAIN_UNUSABLE",
    "CLAIM_MISMATCH_PAIR",
})


def classify(reason: str | None) -> str:
    text = str(reason or "").strip()
    if not text:
        return UNCLASSIFIED
    for name, rx in _COMPILED:
        if rx.search(text):
            return name
    return UNCLASSIFIED


_WRAPPER = re.compile(r"none cleared the gates\.\s*", re.IGNORECASE)


def sub_classify(reason: str | None) -> str | None:
    """For a forecast-level refusal, WHICH gate stopped the best structure.

    None when the row is not a wrapper. Kept separate from `classify` so the
    table can report "719 forecasts declined, and here is what stopped them"
    without those rows being double-counted inside the gates' own totals.
    """
    text = str(reason or "")
    m = _WRAPPER.search(text)
    if not m:
        return None
    tail = text[m.end():].strip()
    return classify(tail) if tail else UNCLASSIFIED


def kind_of(cls: str) -> str:
    """'book state', 'merit', or 'unknown' -- which question a counterfactual on
    this class is actually asking."""
    if cls in BOOK_STATE_CLASSES:
        return "book state"
    if cls in MERIT_CLASSES:
        return "merit"
    if cls in TOURNAMENT_CLASSES:
        return "tournament"
    return "unknown"


# =====================================================================
# E3 (a) -- TYPED TERMINAL STATES, DERIVED AT WRITE TIME
# =====================================================================
#
# Everything above is POST-HOC: it reads 43 sentences off a finished ledger and
# normalises them. That is the right tool for a retrospective and the wrong tool
# for the live question, which is *"did every candidate that entered this pass
# finish somewhere?"* On 2026-09-02 hack1/hack2/hack5 ran passes that refused
# 100% of candidates and the only record of WHY was prose. Prose does not group,
# so "the alpha layer is barren" and "the risk layer is too strict" -- which call
# for opposite work -- printed identically.
#
# So the same mapping logic is reused, at WRITE time, to stamp one field:
#
#     terminal_state  EXACTLY ONE of TERMINAL_STATES, on every disposition row
#
# The prose stays beside it, untouched and in full: the type is for grouping, the
# sentence carries the numbers, the thresholds and the incident the gate was
# built from, and throwing that away to gain a label would be a bad trade.
#
# THREE PROPERTIES THIS MUST HAVE, AND EACH ONE COST SOMETHING TO LEARN
#  * NEVER CRASH. A bookkeeping field that can raise takes down an order path.
#  * NEVER BLANK. A missing type reads as "no disposition", and an absence that
#    looks like a category is how `daily_latch` came to report 312 wins of 312.
#  * NEVER SILENTLY SWALLOW. An unmapped sentence becomes OTHER_TYPED **and is
#    counted** (`UNMAPPED`), so a new gate's sentence surfaces as a number
#    instead of dissolving into a bucket that absorbs a third of the ledger.

#: The closed enum. A state not in here cannot be written.
TERMINAL_STATES: tuple[str, ...] = (
    "ADMITTED",         # the candidate became an order (or an order we chose not to send)
    "ALREADY_HELD",     # the book already carries this name
    "RANKED_OUT",       # a sibling expression of the SAME idea was preferred
    "NEGATIVE_EV",      # the idea was priced and lost to cash, or to its own costs
    "CONFIDENCE",       # the move is not distinguishable from noise (MDE)
    "LIQUIDITY",        # the spread or the traded volume eats the edge
    "CAPACITY",         # the book has no room, or the size buys no unit
    "GROSS",            # the gross-notional ceiling
    "CONCENTRATION",    # per-name, per-driver, per-sector or per-event-node
    "OPENING_RANGE",    # the first fifteen minutes
    "MANDATE",          # this account/book may not express this claim
    "STRUCTURE",        # no instrument expressed the forecast acceptably
    "DATA_STALE",       # the input existed and was too old to act on
    "DATA_MISSING",     # the input to decide was not there at all
    "RISK",             # the risk envelope: latch, theta, delta stress, unbounded book
    "DUPLICATE",        # a peer book, a resting order, or a stop already spoke today
    "OTHER_TYPED",      # UNMAPPED, and counted -- never a silent catch-all
)

OTHER_TYPED = "OTHER_TYPED"
ADMITTED = "ADMITTED"

#: Post-hoc class -> terminal state. The mapping is REUSED rather than
#: reimplemented: two pattern tables for one vocabulary is how the tracker's
#: `close` fix landed on one producer of two (L1-18).
CLASS_TO_TERMINAL: dict[str, str] = {
    "NO_STRUCTURE_CLEARED": "STRUCTURE",
    "GROSS_NOTIONAL": "GROSS",
    "DRIVER_CONCENTRATION": "CONCENTRATION",
    "CROSS_BOOK": "DUPLICATE",
    "OPENING_RANGE": "OPENING_RANGE",
    "CONVEX_RULE": "STRUCTURE",
    "BOOK_LIMIT": "CAPACITY",
    "PER_NAME_CONCENTRATION": "CONCENTRATION",
    "TOMORROWS_OPTIONALITY": "CAPACITY",
    "THETA_BURN": "RISK",
    "DELTA_STRESS": "RISK",
    "DAILY_LOSS_LATCH": "RISK",
    "AGGREGATE_RISK": "RISK",
    "CAPITAL_ROUNDS_TO_ZERO": "CAPACITY",
    "REFUTED_ROUTE": "NEGATIVE_EV",
    "MDE": "CONFIDENCE",
    "EDGE_BELOW_BAR": "NEGATIVE_EV",
    "CLAIM_MISMATCH": "MANDATE",
    "OUTRANKED_BY_SIBLING": "RANKED_OUT",
    "CASH_BEATS_IT": "NEGATIVE_EV",
    "SPREAD_EATS_THE_EDGE": "LIQUIDITY",
    "CLAIM_MISMATCH_PAIR": "MANDATE",
    "DRAWDOWN_UNKNOWN": "DATA_MISSING",
    "ALREADY_HELD": "ALREADY_HELD",
    # A short leg with no protective long is the RISK envelope refusing to size
    # against a worst case that cannot be stated -- not a missing input.
    "BOOK_UNBOUNDED": "RISK",
    "EVENT_NODE_CAP": "CONCENTRATION",
    "CHAIN_UNUSABLE": "DATA_MISSING",
}

#: Sentences the post-hoc table never had to name, because they never reached
#: the counterfactual ledger. Consulted ONLY after `classify` returns
#: UNCLASSIFIED, so adding one here can never move a row's post-hoc class and
#: cannot silently rewrite the retrospective tables. FIRST match wins.
TERMINAL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("DUPLICATE", r"order\(s\) IN FLIGHT"),
    ("DUPLICATE", r"protective stop closed this name earlier today"),
    ("NEGATIVE_EV", r"^CASH:"),
    ("DATA_MISSING", r"no equity to admit against"),
    ("DATA_STALE", r"\bstale\b|quote is .* old|staleness"),
    ("LIQUIDITY", r"dollar volume|OBSERVE_ONLY|spread too wide|too thin to"),
    ("MANDATE", r"not in .* sealed portfolio|mandate|not tradable|not shortable"),
    ("CAPACITY", r"buying power|rounds to zero|no room"),
    ("DATA_MISSING", r"CANNOT DETERMINE|could not be (read|derived|measured)|unreadable"),
)

_TERMINAL_COMPILED = tuple((s, re.compile(p, re.IGNORECASE)) for s, p in TERMINAL_PATTERNS)

#: Which action already IS the answer. A submitted order does not need its
#: sentence parsed to know it was admitted, and `dry_run` is deliberately here
#: rather than among the refusals -- it built the order and chose not to send it
#: (`runner.REFUSAL_CLASSES`: a dry pass and a blocked pass must never print
#: alike).
ACTION_STATES: dict[str, str] = {
    "submitted": ADMITTED,
    "alternative": ADMITTED,
    "intent": ADMITTED,
    "filled": ADMITTED,
    "dry_run": ADMITTED,
}

#: Unmapped prose, counted by a NORMALISED key so one gate does not appear as
#: four hundred entries because its sentence carries a dollar figure. Process
#: local and advisory: it exists so an operator can ask "what is falling through
#: today?" and get a number rather than a shrug.
UNMAPPED: "Counter[str]" = Counter()

_NUMBERS = re.compile(r"[-+]?[\d,]*\.?\d+%?")


def _unmapped_key(reason: str) -> str:
    """A stable key for one unmapped SENTENCE, with its numbers blanked."""
    return _NUMBERS.sub("#", str(reason or "").strip())[:80] or "<blank>"


def terminal_state(reason: str | None, *, action: str | None = None) -> str:
    """The ONE typed state this record finishes in. Never raises, never blank.

    `action` short-circuits for the dispositions that are their own answer
    (`submitted`, `intent`, ...). Everything else is derived from the prose:
    the post-hoc class first -- so the live type and the retrospective table
    speak one vocabulary -- then the live-only patterns, then OTHER_TYPED with
    the sentence counted in `UNMAPPED`.
    """
    try:
        act = str(action or "").strip().lower()
        if act in ACTION_STATES:
            return ACTION_STATES[act]
        text = str(reason or "").strip()
        cls = classify(text)
        if cls != UNCLASSIFIED:
            got = CLASS_TO_TERMINAL.get(cls)
            if got:
                return got
        for state, rx in _TERMINAL_COMPILED:
            if rx.search(text):
                return state
        UNMAPPED[_unmapped_key(text)] += 1
        return OTHER_TYPED
    except Exception:                                            # noqa: BLE001
        # A field that classifies a refusal must never be the reason an order
        # path dies. Unmappable IS a typed answer, and it is counted above when
        # it can be; here we have already failed and say so with the enum.
        return OTHER_TYPED


def unmapped_report(top: int = 20) -> list[tuple[str, int]]:
    """The unmapped sentences seen by THIS process, commonest first.

    A rising count here is the signal that a gate was added without a type --
    which is the failure this whole section exists to make visible.
    """
    return UNMAPPED.most_common(top)


def reset_unmapped() -> None:
    """For tests and for a long-lived loop that reports per pass."""
    UNMAPPED.clear()
