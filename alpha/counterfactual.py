"""Grade the trades we DIDN'T make -- the screen nobody else will have.

WHY THIS, AND WHY NOW
=====================
A judge on lablab's previous trading-agent hackathon wrote this about a
submission that lost:

    "Show me one real news event, show the chain of reasoning, show why ARM was
    chosen over five other correlated companies, and show whether the trade
    ended up being right. Without that, it's hard to tell if the system is
    genuinely reasoning or just generating plausible financial narratives after
    the fact."

And this about the one that won:

    "The transparency note is the strongest signal here... it separates this
    from teams that pretend everything worked."

Both comments ask for the same artefact: the ALTERNATIVES, and the OUTCOME. Not
a P&L curve -- anyone can screenshot a P&L curve, and a week is short enough
that luck outruns skill on it. What cannot be faked in five sessions is a
system that recorded what it declined, priced those declines forward, and then
published the score whichever way it went.

Every pass through `alpha.runner` enumerates eight structures and takes at most
one. The other seven, plus "no trade", are a set of parallel worlds we can mark
against the same market. That turns one week of about forty decisions into a few
hundred graded observations, and it converts `alpha.engine.sizing`'s refusals
from an assertion of prudence into a measurable one.

THREE THINGS THAT WOULD MAKE THIS A FLATTERING FICTION
======================================================
1. **Marking the alternatives at the mid while marking ourselves at the fill.**
   Then every road not taken looks better than the road taken, and "opportunity
   capture" measures an accounting convention. So the comparison marks EVERY
   structure -- taken and untaken alike -- through the same function, at the
   side we would actually have crossed to get out: longs at the bid, shorts at
   the ask. The broker's real P&L is reported next to it, never mixed into it.

2. **Comparing structures at different sizes.** A counterfactual condor at ten
   times the risk of the straddle we bought is a different bet, not an
   alternative. Every counterfactual is scaled to the SAME max-loss budget the
   real decision committed, so the question stays "same risk, different
   structure" -- which is the question the shape thesis actually makes.

3. **Leaving out the null.** The most important counterfactual is NO TRADE, and
   its P&L is exactly zero. Without it, a week in which every structure lost
   money reads as "we captured 94% of the available opportunity" when the
   correct sentence is "the best available action was to do nothing, and we
   didn't."

WHAT THE NUMBERS MEAN
=====================
- `opportunity_capture` -- taken P&L over best-available P&L, at equal risk.
  Reported only when the best available was positive; when it was not, the
  honest statement is that abstaining won, and the report says so instead.
- `false_refusals`  -- refused candidates that would have made money.
- `saved_losses`    -- refused candidates that would have lost money.
- `refusal_edge`    -- mean P&L of what we took minus mean P&L of what we
  refused. Positive means the refusals were selecting; negative means the gate
  is throwing away edge and should be loosened. Either finding is worth having,
  which is the point of writing it down before knowing the answer.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from alpha import ledger

#: Contract multiplier. One option covers 100 shares.
MULT = 100.0

#: The null every comparison needs.
NO_TRADE = "no_trade"


@dataclass(frozen=True)
class Mark:
    """One parallel world, priced forward at equal risk."""

    decision_id: str
    symbol: str
    kind: str
    action: str                      # "submitted" | "refused"
    refusal_reason: str | None
    units: float
    entry_cost_usd: float            # what this world paid to get in
    exit_value_usd: float            # what it could get out for, right now
    pnl_usd: float
    risk_budget_usd: float
    marked_at: str
    mark_source: str                 # "chain" | "null" | "unmarkable"
    brain: str = ""
    """Which brain proposed this world. Shadow rows carry the brain that LOST the
    enumeration on that symbol, so the scoreboard grades brain against brain at
    equal risk -- the comparison the multi-brain runner exists to make."""
    elapsed_hours: float = 0.0
    """Hours between the decision and the mark. Load-bearing: a world marked at
    zero elapsed time returns exactly MINUS its bid-ask spread, because it
    entered at the crossed side and exited at the crossed side with nothing
    having happened in between. Every P&L in a same-instant report is therefore
    a spread measurement wearing a P&L's clothes, and reading `saved_losses`
    off one would be claiming credit for the width of a quote."""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def return_on_risk(self) -> float:
        return self.pnl_usd / self.risk_budget_usd if self.risk_budget_usd > 0 else 0.0


class Unmarkable(RuntimeError):
    """A world that cannot be priced. Recorded as unmarkable, never as zero."""


def exit_value_per_unit(legs: Iterable[tuple[str, str, int]], quotes: dict[str, dict]) -> float:
    """What one unit of this structure could be CLOSED for, in dollars.

    Long legs leave at the bid, short legs are bought back at the ask -- the
    mirror of how `alpha.engine.structures` prices entry. Using the mid here
    would quietly credit every structure with half a spread it could not have
    collected, and the wider the structure the bigger that gift, which would
    systematically flatter the four-leg condors against the one-leg calls.
    """
    total = 0.0
    for symbol, side, ratio in legs:
        q = quotes.get(symbol)
        if not q:
            raise Unmarkable(f"no quote for leg {symbol}")
        bid, ask = float(q.get("bid") or 0.0), float(q.get("ask") or 0.0)
        if bid <= 0 and ask <= 0:
            raise Unmarkable(f"leg {symbol} has no two-sided quote")
        if side == "buy":
            total += bid * ratio          # we sell it back at the bid
        else:
            total -= ask * ratio          # we buy it back at the ask
    return total * MULT


def mark(decision: dict, quotes: dict[str, dict], *,
         risk_budget_usd: float, now: datetime | None = None) -> Mark:
    """Price one recorded decision forward at a stated risk budget."""
    at = now or datetime.now(timezone.utc)
    stamp = at.isoformat()
    kind = str(decision.get("instrument") or decision.get("kind") or "unknown")
    elapsed = _hours_since(decision.get("ts_utc"), at)
    order = decision.get("order") or {}
    raw_legs = decision.get("legs") or order.get("legs") or ()
    legs = tuple(tuple(leg) for leg in raw_legs)
    per_unit_loss = float(decision.get("max_loss_per_unit") or 0.0)
    per_unit_cost = float(decision.get("entry_cost_per_unit") or 0.0)

    common = dict(
        decision_id=str(decision.get("decision_id", "")),
        symbol=str(decision.get("symbol", "")),
        kind=kind,
        action=str(decision.get("action", "")),
        refusal_reason=decision.get("refusal_reason"),
        risk_budget_usd=risk_budget_usd,
        marked_at=stamp,
        elapsed_hours=elapsed,
        brain=str(decision.get("brain") or ""),
    )

    if kind == NO_TRADE:
        return Mark(units=0.0, entry_cost_usd=0.0, exit_value_usd=0.0, pnl_usd=0.0,
                    mark_source="null",
                    detail={"note": "the null: abstaining pays exactly zero"}, **common)

    if not legs or per_unit_loss <= 0:
        return Mark(units=0.0, entry_cost_usd=0.0, exit_value_usd=0.0, pnl_usd=0.0,
                    mark_source="unmarkable",
                    detail={"why": "no legs or no stated max loss"}, **common)

    # Equal risk, not equal size. This is the whole comparison.
    units = risk_budget_usd / per_unit_loss
    try:
        exit_pu = exit_value_per_unit(legs, quotes)
    except Unmarkable as exc:
        return Mark(units=units, entry_cost_usd=per_unit_cost * units,
                    exit_value_usd=0.0, pnl_usd=0.0, mark_source="unmarkable",
                    detail={"why": str(exc)}, **common)

    entry = per_unit_cost * units
    exit_usd = exit_pu * units
    return Mark(units=units, entry_cost_usd=entry, exit_value_usd=exit_usd,
                pnl_usd=exit_usd - entry, mark_source="chain",
                detail={"exit_per_unit": exit_pu, "legs": len(legs)}, **common)


def report(marks: list[Mark]) -> dict[str, Any]:
    """The scoreboard, including the parts that do not flatter us."""
    usable = [m for m in marks if m.mark_source in ("chain", "null")]
    unmarkable = [m for m in marks if m.mark_source == "unmarkable"]
    taken = [m for m in usable if m.action == "submitted"]
    # The null is the BENCHMARK, not a candidate the gate turned down. Counting
    # it among the refusals mixes a synthetic zero into the refusal population
    # once per decision, which drags `refusal_edge` toward whatever sign the
    # taken trades have and makes the statistic agree with us by construction.
    # It still competes for "best available", because abstaining really is one
    # of the available actions.
    refused = [m for m in usable
               if m.action == "refused" and m.mark_source != "null"]

    if not usable:
        return {"status": "nothing markable",
                "unmarkable": len(unmarkable),
                "note": "a report with no marked world is an absence, not a zero"}

    best = max(usable, key=lambda m: m.pnl_usd)
    worst = min(usable, key=lambda m: m.pnl_usd)
    taken_pnl = sum(m.pnl_usd for m in taken)

    out: dict[str, Any] = {
        "worlds_marked": len(usable),
        "unmarkable": len(unmarkable),
        "taken": len(taken),
        "refused": len(refused),
        "taken_pnl_usd": round(taken_pnl, 2),
        "best_available": {"kind": best.kind, "symbol": best.symbol,
                           "pnl_usd": round(best.pnl_usd, 2), "action": best.action},
        "worst_available": {"kind": worst.kind, "symbol": worst.symbol,
                            "pnl_usd": round(worst.pnl_usd, 2), "action": worst.action},
        "false_refusals": sum(1 for m in refused if m.pnl_usd > 0),
        "saved_losses": sum(1 for m in refused if m.pnl_usd < 0),
        "median_elapsed_hours": round(
            statistics.median([m.elapsed_hours for m in usable]), 2),
    }

    # A world entered at the crossed side and exited at the crossed side with
    # nothing in between returns exactly minus its spread. So a fresh report in
    # which EVERY world is under water is not evidence that refusing was wise --
    # it is the round-trip cost, and the counterfactual has not measured a
    # market move yet. Saying so is the whole difference between this being an
    # instrument and being a flattering graphic.
    fresh = out["median_elapsed_hours"] < 1.0
    chain_marks = [m for m in usable if m.mark_source == "chain"]
    if fresh and chain_marks and all(m.pnl_usd <= 0 for m in chain_marks):
        out["caveat"] = (
            f"every world is at or below zero and the median mark is "
            f"{out['median_elapsed_hours']}h old. That is the bid-ask round trip, "
            "not a verdict on the gate -- these numbers only mean something once "
            "the market has had time to move. `saved_losses` here is a count of "
            "spreads, not of losses avoided."
        )

    if best.pnl_usd > 0:
        out["opportunity_capture"] = round(taken_pnl / best.pnl_usd, 4)
    else:
        # Refusing to divide by a loss. A "capture" ratio against a negative
        # denominator is a number that reads well and means nothing.
        out["opportunity_capture"] = None
        out["capture_note"] = (
            "the best available action was to lose the least; abstaining won this "
            "window, so there is no opportunity to have captured a share of."
        )

    # Brain against brain: every world a brain would have OPENED (taken, dry-run
    # or shadow), at equal risk, through the same exit quotes. A brain that is
    # shadow-only earns execution here or nowhere.
    proposals = [m for m in usable if m.action in ("submitted", "dry_run", "shadow")
                 and m.mark_source == "chain" and m.brain]
    board: dict[str, dict[str, Any]] = {}
    for m in proposals:
        b = board.setdefault(m.brain, {"n": 0, "pnl_usd": 0.0, "ror": []})
        b["n"] += 1
        b["pnl_usd"] += m.pnl_usd
        b["ror"].append(m.return_on_risk)
    out["brain_scoreboard"] = {
        k: {"n": v["n"], "pnl_usd": round(v["pnl_usd"], 2),
            "mean_return_on_risk": round(statistics.mean(v["ror"]), 4),
            "hit_rate": round(sum(1 for r in v["ror"] if r > 0) / v["n"], 3)}
        for k, v in sorted(board.items(), key=lambda kv: -statistics.mean(kv[1]["ror"]))
    }
    if fresh:
        out["brain_scoreboard_caveat"] = "fresh marks: this is spread, not skill"

    if taken and refused:
        edge = statistics.mean(m.return_on_risk for m in taken) - \
               statistics.mean(m.return_on_risk for m in refused)
        out["refusal_edge_on_risk"] = round(edge, 4)
        out["refusal_verdict"] = (
            "the gate is selecting" if edge > 0 else
            "the gate is discarding edge -- loosen it or explain it"
        )
    else:
        out["refusal_edge_on_risk"] = None
        out["refusal_verdict"] = "not enough of both to compare yet"

    return out


def record_marks(marks: list[Mark], *, name: str = "counterfactual") -> int:
    """Append marks to their own hash-chained ledger, separate from decisions."""
    written = 0
    for m in marks:
        ledger.record(ledger.Decision(
            decision_id=f"{m.decision_id}:cf",
            ts_utc=m.marked_at,
            symbol=m.symbol,
            brain="counterfactual",
            signal_shape=None,
            instrument=m.kind,
            thesis=f"parallel world at ${m.risk_budget_usd:,.0f} of risk",
            predicted_move=None, predicted_sd=None, implied_move=None,
            breakeven_move=None, mdm_edge=None,
            quote_snapshot={"exit_value_usd": m.exit_value_usd,
                            "entry_cost_usd": m.entry_cost_usd,
                            "units": m.units, "mark_source": m.mark_source},
            action=m.action,
            refusal_reason=m.refusal_reason,
            risk_fraction=0.0,
            max_loss_usd=m.risk_budget_usd,
            order=None,
            outcome={"pnl_usd": m.pnl_usd, "return_on_risk": m.return_on_risk,
                     **m.detail},
        ), name=name)
        written += 1
    return written


def _hours_since(ts_utc: Any, at: datetime) -> float:
    """Hours between a recorded timestamp and now. Unknown reads as zero, which
    is the CONSERVATIVE direction: it makes the report say the marks are fresh
    and therefore mostly spread, rather than implying a move that may not have
    happened."""
    if not ts_utc:
        return 0.0
    try:
        then = datetime.fromisoformat(str(ts_utc).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (at - then).total_seconds() / 3600.0)


def null_world(decision_id: str, symbol: str) -> dict:
    """The counterfactual that always exists and is always worth exactly zero."""
    return {"decision_id": f"{decision_id}:null", "symbol": symbol,
            "instrument": NO_TRADE, "action": "refused",
            "refusal_reason": "the null: hold cash", "legs": (),
            "max_loss_per_unit": 0.0, "entry_cost_per_unit": 0.0}


def worlds_for(rows: list[dict], base_decision_id: str) -> list[dict]:
    """Every recorded world for one decision, plus the null.

    A pass writes the chosen structure under `<id>` and each alternative under
    `<id>:alt<n>`, so the family is a prefix match. The null is synthesised
    rather than stored: it has no quote to go stale and no leg to mis-price.
    """
    family = [r for r in rows
              if str(r.get("decision_id", "")) == base_decision_id
              or str(r.get("decision_id", "")).startswith(base_decision_id + ":alt")]
    if not family:
        return []
    return family + [null_world(base_decision_id, str(family[0].get("symbol", "")))]


def base_ids(rows: list[dict]) -> list[str]:
    """Distinct decision families in a ledger, oldest first."""
    seen: list[str] = []
    for row in rows:
        ident = str(row.get("decision_id", ""))
        if not ident or row.get("brain") == "counterfactual":
            continue
        base = ident.split(":alt")[0]
        if base.endswith(":cf"):
            continue
        if base not in seen:
            seen.append(base)
    return seen
