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
