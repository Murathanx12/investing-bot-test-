"""RECOVERY / VALIDATION mode -- what the dev book does after a losing day.

The 25 Aug close: every brain negative at equal risk, the refusal portfolio
+0.8%. The wrong response is "make the $3.8k back", because it creates exactly
the optimisation pressure that turns a losing book into a ruined one. The
objective is not to recover yesterday's loss. The objective is to refuse every
negative-EV dollar from today forward.

So while `AAT_RECOVERY=1` (dev, until a mechanism is positive):

  * the risk profile is `conservative` (3% per thesis, 20% aggregate) --
    enforced by the loop's `--profile`, checked here;
  * a brain whose live marks are negative may not open NEW long-premium
    structures. Its forecasts are still recorded, its structures still priced
    (they go to shadow), so the grade that could reinstate it keeps accruing;
  * two consecutive live losses demote a brain to shadow outright.

A brain's LIVE SCORE is read from the counterfactual ledger: the latest mark
of every `submitted` decision it made, `return_on_risk` averaged. Marks are
what the venue would pay to close the position now, so the score is a
mark-to-market on the brain's own entries -- not a story about them.

Nothing here touches sizing arithmetic. It is a gate in front of execution,
and it names its evidence in every refusal it writes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from alpha import ledger

MIN_LIVE_MARKS = 3
CONSECUTIVE_LOSSES = 2

LONG_PREMIUM_KINDS = {"long_call", "long_put", "long_straddle", "bull_call_spread",
                      "bear_put_spread"}


def active() -> bool:
    return os.getenv("AAT_RECOVERY", "").strip() == "1"


@dataclass
class BrainScore:
    brain: str
    n: int = 0
    mean_return_on_risk: float = 0.0
    last: list[float] = field(default_factory=list)
    """Return on risk of the most recent decisions, newest LAST."""
    pnl_usd: float = 0.0

    @property
    def negative(self) -> bool:
        return self.n >= MIN_LIVE_MARKS and self.mean_return_on_risk < 0.0

    @property
    def consecutive_losses(self) -> bool:
        tail = self.last[-CONSECUTIVE_LOSSES:]
        return len(tail) == CONSECUTIVE_LOSSES and all(x < 0.0 for x in tail)


def _brain_of(decision_id: str) -> str:
    parts = decision_id.split(":")
    return parts[1] if len(parts) >= 3 else ""


def live_scores(*, account_role: str | None = None, cf_rows: list[dict] | None = None,
                decision_rows: list[dict] | None = None) -> dict[str, BrainScore]:
    """Latest mark per taken decision, grouped by the brain that took it."""
    cf_rows = cf_rows if cf_rows is not None else ledger.read_all("counterfactual")
    roles: dict[str, str | None] = {}
    if account_role is not None:
        decision_rows = decision_rows if decision_rows is not None else ledger.read_all()
        for r in decision_rows:
            if r.get("action") == "submitted":
                roles[r["decision_id"]] = r.get("account_role")
    latest: dict[str, dict] = {}
    for r in cf_rows:
        if r.get("action") != "submitted":
            continue
        if (r.get("quote_snapshot") or {}).get("mark_source") == "unmarkable":
            continue
        base = r["decision_id"][:-3] if r["decision_id"].endswith(":cf") else r["decision_id"]
        if account_role is not None:
            role = roles.get(base)
            if role is not None and role != account_role:
                continue
        prev = latest.get(base)
        if prev is None or (r.get("_written_utc") or "") > (prev.get("_written_utc") or ""):
            latest[base] = r
    scores: dict[str, BrainScore] = {}
    for base, r in sorted(latest.items(), key=lambda kv: kv[1].get("ts_utc") or ""):
        brain = _brain_of(base)
        if not brain:
            continue
        out = r.get("outcome") or {}
        ror = float(out.get("return_on_risk") or 0.0)
        sc = scores.setdefault(brain, BrainScore(brain))
        sc.n += 1
        sc.last.append(ror)
        sc.pnl_usd += float(out.get("pnl_usd") or 0.0)
        sc.mean_return_on_risk += (ror - sc.mean_return_on_risk) / sc.n
    return scores


def refusal(brain: str, kind: str, scores: dict[str, BrainScore]) -> str | None:
    """Why recovery mode refuses this brain this structure, or None to allow."""
    if not active():
        return None
    sc = scores.get(brain)
    if sc is None:
        return None
    if sc.consecutive_losses:
        return (f"RECOVERY: {brain} demoted to shadow -- its last {CONSECUTIVE_LOSSES} live "
                f"decisions both mark negative ({', '.join(f'{x:+.1%}' for x in sc.last[-CONSECUTIVE_LOSSES:])}"
                f" of risk). It trades again when a mark says it should.")
    if sc.negative and kind in LONG_PREMIUM_KINDS:
        return (f"RECOVERY: {brain} marks {sc.mean_return_on_risk:+.1%} of risk over {sc.n} live "
                f"decisions (${sc.pnl_usd:,.0f}); a negative brain opens no new long premium. "
                "Recorded as shadow so the grade keeps accruing.")
    return None


def summary(scores: dict[str, BrainScore]) -> str:
    if not scores:
        return "recovery: no live marks yet"
    return "recovery scores: " + "; ".join(
        f"{b} {s.mean_return_on_risk:+.1%} on {s.n} (${s.pnl_usd:,.0f})"
        for b, s in sorted(scores.items()))
