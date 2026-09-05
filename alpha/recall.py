"""THE OPPORTUNITY-RECALL LEDGER -- how far down our own pipeline each day's
biggest movers got before we lost them.

    from alpha import recall
    row = recall.classify("MU", observed=True, ranked=True, bought=False)
    row["miss_type"]        # RANKED_NOT_BOUGHT

WHY A TYPE AND NOT A COUNT (B3, 2026-09-05)
===========================================
`scripts/discovery_autopsy` already asked the second autopsy question -- what
were today's largest movers across the WHOLE market, and did AEGIS ever put the
name on a list? -- and answered it with a location (`digest_bet`,
`window_universe`, `NOT_GENERATED`). A location is where the name WAS. It does
not say **which of our stages dropped it**, and those stages have completely
different repairs:

    NOT_OBSERVED          the name never entered any AEGIS list. The repair is
                          COVERAGE: a wider universe, another source, a language
                          we do not read. ("Find Micron before it was Micron"
                          is only testable if we count the Microns we never
                          looked at -- vision file 4.3.)
    GENERATED_NOT_RANKED  we had the name and our ranking did not surface it.
                          The repair is the MODEL, or the features it reads.
    RANKED_NOT_BOUGHT     the sealed book named it and no fill exists. The
                          repair is EXECUTION or an admission gate -- and this
                          is the class the fleet has been losing names in:
                          hack3 sealed ten names on 2026-09-03 and entered NONE
                          (the UNCLASSIFIED driver bucket's 40% ceiling).
    BOUGHT_SOLD_EARLY     we owned it and closed before the contract's minimum
                          hold. The repair is the EXIT RULE, and it is measured:
                          60% of this fleet's round trips finished in the
                          session they opened, on a 21-session thesis.

Anything past that is CAPTURED and is not a miss.

BOTH SIDES OF THE TAPE, ALWAYS
==============================
The informative unit is winner vs matched loser, never a gallery of survivors
(mission rule 4). So every mover is classified, WIN and LOSS alike, and the row
carries `recall_kind`:

    missed_winner   a WIN we did not capture      -- an opportunity lost
    captured_winner a WIN we held                 -- the system working
    avoided_loser   a LOSS we did not hold        -- the system ALSO working
    held_loser      a LOSS we held                -- the expensive one

A ledger that counted only missed winners would score a book that buys
everything as perfect. `summarise` reports recall on winners and avoidance on
losers side by side for exactly that reason.

Pure. No IO, no venue, no clock: every input is passed in, which is what makes
the classification testable offline and identical wherever it runs.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

#: The four stages a name can be lost at, ordered EARLIEST-loss first. The order
#: is load-bearing: `classify` returns the first stage the name failed to clear,
#: which is the stage whose repair would have changed the outcome.
MISS_TYPES: tuple[str, ...] = (
    "NOT_OBSERVED",
    "GENERATED_NOT_RANKED",
    "RANKED_NOT_BOUGHT",
    "BOUGHT_SOLD_EARLY",
)

#: Not a miss. The name got all the way through.
CAPTURED = "CAPTURED"

#: Every value `miss_type` may take.
RECALL_STATES: tuple[str, ...] = MISS_TYPES + (CAPTURED,)

WIN, LOSS = "WIN", "LOSS"

#: How to read a state given which way the name moved.
RECALL_KINDS = ("missed_winner", "captured_winner", "avoided_loser", "held_loser")


def classify(symbol: str, *, side: str = WIN,
             observed: bool = False, ranked: bool = False, bought: bool = False,
             sold_early: bool | None = None, **extra) -> dict:
    """One mover's row: where in OUR pipeline it was lost, and how to read that.

    The four booleans are a LADDER, and each implies the ones before it: a name
    that was bought was necessarily ranked and observed. Callers that can only
    establish the later ones (a fill without a sealed book, say) get the implied
    earlier ones for free rather than a row that says "bought but never
    observed", which would be a bug wearing a category.

    `sold_early` is TRI-STATE on purpose. None means "we hold it, or we cannot
    yet tell" -- a position opened this morning has not failed its minimum hold,
    and recording that as False would claim we checked. Only an explicit True
    demotes a captured name to BOUGHT_SOLD_EARLY.
    """
    if bought:
        ranked = True
    if ranked:
        observed = True
    if not observed:
        state = "NOT_OBSERVED"
    elif not ranked:
        state = "GENERATED_NOT_RANKED"
    elif not bought:
        state = "RANKED_NOT_BOUGHT"
    elif sold_early is True:
        state = "BOUGHT_SOLD_EARLY"
    else:
        state = CAPTURED
    up = str(side).upper() == WIN
    got = state == CAPTURED
    kind = ("captured_winner" if (up and got) else "missed_winner" if up
            else "held_loser" if got else "avoided_loser")
    return {"symbol": str(symbol).upper(), "side": WIN if up else LOSS,
            "miss_type": state, "recall_kind": kind,
            "observed": observed, "ranked": ranked, "bought": bought,
            "sold_early": sold_early, **extra}


def classify_day(movers: Iterable[Mapping], *, observed: set[str], ranked: set[str],
                 bought: set[str], sold_early: Mapping[str, bool] | None = None,
                 side_key: str = "side", symbol_key: str = "symbol") -> list[dict]:
    """Every mover of a session, typed. `movers` rows keep their own fields
    (return, dollar volume, headline count) -- the classification is ADDED to
    them so the ledger row carries the evidence beside the verdict."""
    sold = dict(sold_early or {})
    out = []
    for m in movers:
        sym = str(m.get(symbol_key) or "").upper()
        if not sym:
            continue
        row = classify(sym, side=str(m.get(side_key) or WIN),
                       observed=sym in observed, ranked=sym in ranked,
                       bought=sym in bought, sold_early=sold.get(sym))
        out.append({**dict(m), **row})
    return out


def summarise(rows: Sequence[Mapping]) -> dict:
    """Counts by state and by kind, plus the two rates that matter.

    `winner_recall` is captured winners / all winners. `loser_avoidance` is
    avoided losers / all losers. They are reported TOGETHER because either one
    alone can be driven to 1.0 by a book with no discipline at all -- buy
    everything and recall is perfect, buy nothing and avoidance is.

    A rate over ZERO movers is None, not 1.0 and not 0.0. An empty night has no
    recall; saying it does is the 312-wins-on-$0.00 error.
    """
    by_state = {s: 0 for s in RECALL_STATES}
    by_kind = {k: 0 for k in RECALL_KINDS}
    for r in rows:
        st, kd = r.get("miss_type"), r.get("recall_kind")
        if st in by_state:
            by_state[st] += 1
        if kd in by_kind:
            by_kind[kd] += 1
    n_win = by_kind["captured_winner"] + by_kind["missed_winner"]
    n_loss = by_kind["avoided_loser"] + by_kind["held_loser"]
    return {
        "n": len(list(rows)),
        "by_miss_type": by_state,
        "by_recall_kind": by_kind,
        "n_winners": n_win,
        "n_losers": n_loss,
        "winner_recall": (round(by_kind["captured_winner"] / n_win, 3) if n_win else None),
        "loser_avoidance": (round(by_kind["avoided_loser"] / n_loss, 3) if n_loss else None),
        "reading": ("Where the winners are lost names the stage to repair: NOT_OBSERVED is "
                    "coverage, GENERATED_NOT_RANKED is the model, RANKED_NOT_BOUGHT is "
                    "execution or an admission gate, BOUGHT_SOLD_EARLY is the exit rule. "
                    "Read winner_recall BESIDE loser_avoidance -- either alone is gamed by "
                    "a book with no discipline."),
    }
