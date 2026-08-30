"""MURAT_RULE brain -- the selector that reads the SEALED book and nothing else.

WHAT IT IS
==========
`alpha/murat_rule.py` holds the rule and `scripts/prediction_book.py` seals it
before the open. This brain is the wire from that sealed file into the fleet:
it trades the names the book CLAIMED, at the numbers the book published, and it
declines everything else with the clause that blocked it.

WHY IT READS THE SEAL INSTEAD OF RE-DERIVING
============================================
Re-computing the rule at order time would be one line shorter and would break
the only property worth having: that what trades is what was written down
before the open. A selector that recomputes can drift from its own sealed book
between 09:15 and 09:31 -- new headlines land, the target panel moves, a rating
refreshes -- and every one of those drifts is invisible in the receipt. Reading
the seal makes the pre-open book the CONTRACT rather than a commentary on it,
and any disagreement between them becomes impossible instead of undetectable.

It also costs nothing. The book already paid the Finnhub calls for the ratings.

DIRECTION, NOT DISPERSION
=========================
`claim="direction"`. The rule is evidence about which WAY, and has no opinion
whatever about how wide the outcome is. Declaring `distribution` here would be
the exact bug `alpha/brains/base.py` documents: a directional brain whose `sd`
is a realised-vol estimate makes an accidental claim that the chain's width is
wrong, the EV ranker notices every long option looks overpriced, and a bullish
reading gets handed an IRON CONDOR that cannot see the sign. Measured on a real
NVDA chain, that condor won the ranking at centre +0.72% AND at -0.72%.

WHAT IT MAY NOT DO
==================
It sizes nothing. It does not widen a stop, raise a cap, or touch gross. Its
worst case is bounded by hack3's existing basket profile, printed in
`docs/` and unchanged by this file:

    n <= 12 names  x  <= 8.3% notional (gross cap 100% / 12)  x  8% stop  =  -8.0%

If the sealed book claims nothing, this brain declines every symbol and hack3
holds cash. That is a finding, and it is recorded as one.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from alpha import exits as _exits
from alpha.brains.base import Forecast

ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS = Path(os.getenv("AAT_LEDGER_DIR") or (ROOT / "state")) / "predictions"

#: SECOND PLACE TO LOOK, and the reason it is not under `state/`.
#:
#: On Railway `AAT_LEDGER_DIR=/app/state` is a mounted VOLUME, and a volume
#: SHADOWS whatever the image has at that path. So a book sealed on the laptop
#: and committed to `state/predictions/` is invisible to the running loop --
#: the repo copy is underneath the mount. The brain would decline every symbol
#: for a reason ("no sealed book") that looks like the rule having nothing to
#: say, on an account that was deliberately wired to act on it.
#:
#: `docs/seed/` is already how the theme universe reaches the container
#: (`fleet.THEMES_SEED`) and is NOT shadowed. Sealing locally, committing here
#: and pushing is therefore the whole deployment path for a day's book.
SEED_BOOKS = ROOT / "docs" / "seed" / "predictions"

BRAIN = "murat_rule"
GENERATOR = "murat_rule_v1"

#: The horizon the book's numbers were computed for. A loop running a shorter
#: horizon gets them SCALED, not reused: `centre` is a drift (linear in time),
#: `sd` is a diffusion (linear in sqrt time). Reusing a 21-session centre at a
#: 5-session horizon would overstate the claim by more than four times.
BOOK_HORIZON_SESSIONS = 21
SESSIONS_PER_CALENDAR_DAY = 5.0 / 7.0


class RuleDeclined(Exception):
    """This brain has nothing to say about this symbol, and says why."""


def _book_for(day: str) -> dict | None:
    """The NEWEST sealed book for `day`, from the ledger dir or the seed dir.

    A reseal writes a new file beside the original rather than replacing it, so
    `<day>.json` alone can be a superseded book. Sorting puts `resealed_HHMMSS`
    after the plain name, and the last one wins.
    """
    for base in (BOOKS, SEED_BOOKS):
        cands = sorted(base.glob(f"{day}.json")) + sorted(base.glob(f"{day}.resealed_*.json"))
        if not cands:
            continue
        try:
            return json.loads(cands[-1].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def forecast(client, symbol: str, horizon_days: float, *, day: str | None = None) -> Forecast:
    sym = str(symbol).upper()
    day = day or _exits.session_day()
    book = _book_for(day)
    if book is None:
        raise RuleDeclined(
            f"no sealed book for {day}: this brain trades only what was sealed before the "
            f"open (`python -m scripts.prediction_book --seal`). Declining rather than "
            f"re-deriving, because a selector that recomputes can drift from its own book.")

    rows = [p for p in (book.get("predictions") or [])
            if p.get("generator") == GENERATOR and p.get("symbol") == sym]
    if not rows:
        raise RuleDeclined(f"{sym} is not in the sealed book for {day} "
                           f"({book.get('universe_considered')} names considered)")
    row = rows[0]

    if not row.get("claims"):
        failed = ", ".join(row.get("failed_clauses") or []) or "no clause fired"
        unread = ", ".join(row.get("unreadable_clauses") or [])
        raise RuleDeclined(
            f"{sym} did not claim: failed [{failed}]"
            + (f", unreadable [{unread}]" if unread else "")
            + f"; variant {row.get('rule_variant')}")

    move = row.get("claimed_abs_move")
    p_up = row.get("p_up_21d")
    exp_r = row.get("exp_return")
    if move is None or p_up is None or exp_r is None:
        raise RuleDeclined(f"{sym} claimed but carries no numbers -- refusing rather than "
                           f"inventing them (move={move}, p_up={p_up}, exp_return={exp_r})")

    # Scale the book's 21-session numbers to the loop's horizon.
    sessions = max(1.0, float(horizon_days) * SESSIONS_PER_CALENDAR_DAY)
    t = min(1.0, sessions / BOOK_HORIZON_SESSIONS)
    centre = float(exp_r) * t
    sd = float(move) * math.sqrt(t)
    if sd <= 0:
        raise RuleDeclined(f"{sym} has a non-positive spread ({sd}); a point forecast with no "
                           f"stated uncertainty would size itself to the ceiling")

    return Forecast(
        brain=BRAIN, symbol=sym, horizon_days=float(horizon_days),
        centre=centre, sd=sd,
        conviction=max(0.05, min(1.0, float(row.get("confidence") or 0.05))),
        # DIRECTION only. See the module docstring: claiming the width here is
        # how a bullish reading gets handed an iron condor.
        claim="direction",
        signal_shape=None,
        rationale=(f"murat_rule_v1 ({row.get('rule_variant')}): target/price "
                   f"{row['clause_inputs'].get('target_ratio')}, catalyst in "
                   f"{row['clause_inputs'].get('days_to_next_catalyst')}d, drawdown "
                   f"{row['clause_inputs'].get('drawdown_from_60d_high')}; p_up {p_up} from "
                   f"the panel base rate (n={row.get('p_up_n')}, "
                   f"{row.get('p_up_n_blocks')} date blocks)"),
        evidence={
            "generator": GENERATOR,
            "sealed_day": day,
            "book_sha256": book.get("content_sha256"),
            "rule_variant": row.get("rule_variant"),
            "clauses": row.get("clauses"),
            "clause_inputs": row.get("clause_inputs"),
            "p_up_21d": p_up,
            "p_up_basis": row.get("p_up_basis"),
            "p_up_n": row.get("p_up_n"),
            "p_up_n_blocks": row.get("p_up_n_blocks"),
            "claimed_abs_move_21d": move,
            "exp_return_21d": exp_r,
            "downside_5pct_21d": row.get("downside_5pct"),
            "confidence": row.get("confidence"),
            "horizon_scaling": f"centre x {t:.3f} (linear), sd x sqrt({t:.3f}) (diffusion)",
            "licence": "PRODUCT_EXPERIMENT",
            "in_sample_prior": True,
            "caveat": ("the base rate behind p_up is IN-SAMPLE on the 152-name panel and stands "
                       "on clauses (a) and (e) only -- (b) has no rating history and (d) had an "
                       "empty calendar until 2026-08-30. It is a base rate for calibration, not "
                       "evidence that the rule works."),
        },
    )
