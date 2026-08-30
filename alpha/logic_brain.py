"""The logic brain ON the tracker: an ADJUSTER of the rule, never a picker.

WHAT THIS IS
============
For each name the tracker already grades BUY or STRONG_BUY, an LLM reads two
things -- the row's numbers, and the company's genuinely new dated facts from
the last few sessions -- and moves the rule's `p_up_21d` up or down. That is
all it may do. It cannot add a name, cannot remove one, and cannot set a
probability from nothing.

WHY IT IS SHAPED THAT WAY, AND NOT AS "ASK THE MODEL WHAT TO BUY"
=================================================================
Three results in this project's own history, in the order they were paid for:

1. **News count is the wrong shape.** Only 7.7% of corpus items are a new dated
   fact about the company they are tagged with (T12, 2026-08-30), and the clean
   count predicts nothing. So the brain is shown the FILTERED facts
   (`role == "subject" and is_new_fact`), never a headline count.
2. **A model given prose and asked for direction produces direction.** It will
   always have an opinion, and an opinion with no named cause cannot be graded,
   improved or refused. So a non-zero adjustment REQUIRES naming which supplied
   fact caused it, by id, and the id is checked against what was supplied --
   in code, not in the prompt. A prompt instruction is a request; this is a
   guard.
3. **Better than WHAT.** The rule's own number is kept on every row beside the
   brain's. The question is never "is the brain any good" -- it is "does the
   brain beat the rule it was given", which is only answerable if both numbers
   are written down before the outcome.

WHAT BOUNDS IT
==============
`MAX_ADJUSTMENT` caps how far the brain may move the rule. An adjuster that can
move a base rate from 0.50 to 0.95 is not an adjuster; it is a picker wearing an
adjuster's interface, and the cap is what makes the distinction enforceable
rather than aspirational. Clamps are COUNTED and reported: if the brain is
hitting the cap often, that is the finding, not a nuisance.

NOTHING HERE PLACES AN ORDER. It writes numbers onto rows; the books rank on
them under their own caps.
"""
from __future__ import annotations

SCHEMA_NAME = "logic_brain-1"

#: The furthest the brain may move the rule's probability, in absolute terms.
#: 0.10 on a base rate near 0.5 is a meaningful opinion (0.40 -> 0.60 changes a
#: ranking completely) and is not enough to manufacture a certainty.
#:
#: THE PROMPT DOES NOT MENTION THIS NUMBER, and that is deliberate. The first
#: version did, and on 2026-08-30 eleven of thirteen adjustments came back at
#: EXACTLY the cap -- the model was reading the bound as a target and returning
#: a sign wearing a magnitude's clothes. A bound the model can see is an anchor;
#: a bound only the code applies is a bound, and `n_clipped` then measures
#: something real: how often its own opinion was stronger than we allow.
MAX_ADJUSTMENT = 0.10

#: And the furthest it may move the rule's expected return, as a MULTIPLE of the
#: rule's own downside estimate. Expressed relative to the name's own bad case
#: rather than as a fixed percentage, because a fixed cap means one thing for a
#: utility and another for a clinical-stage biotech.
MAX_EXP_RETURN_SHIFT_VS_DOWNSIDE = 0.25

#: Facts older than this are not news to a 21-session forecast; they are context
#: the price has had time to absorb. Five sessions is the brief's window.
FACT_LOOKBACK_SESSIONS = 5

#: And at most this many facts per name, newest first. NVDA came back with 67
#: labelled facts in a ten-day window against USAR's one -- the same 390:1
#: coverage asymmetry that made the old book pick MU. Sixty-seven facts is a
#: prompt nobody can audit and an instruction to "cite the one that mattered"
#: that means almost nothing. The count that was AVAILABLE is recorded on the
#: row beside the count that was SHOWN, because the difference is data.
MAX_FACTS_PER_NAME = 12

#: A hard ceiling per run. The expected cost is ~$0.12 for 200 names on
#: deepseek-chat; anything wanting more than this has gone wrong.
DEFAULT_MAX_USD = 1.00

#: How many names may be scored in one run. The brief's number.
DEFAULT_MAX_NAMES = 200

REQUIRED_KEYS = ("p_up_21d", "exp_return", "downside_5pct", "confidence",
                 "fact_id", "reason")

NO_FACT = "none"

SYSTEM = (
    "You are adjusting an existing quantitative forecast for ONE US-listed company. "
    "You are NOT choosing what to buy and you are NOT writing an opinion piece. "
    "You are given the rule's own numbers and a list of that company's genuinely new "
    "dated facts from the last few sessions, each with an id. "
    "Your job: decide whether those FACTS make the rule's 21-session probability of "
    "outperforming too high or too low, and by how much. "
    "If no supplied fact changes the picture, return the rule's numbers unchanged and "
    f"set fact_id to '{NO_FACT}'. That is a correct and common answer. "
    f"If you do adjust, fact_id MUST be the id of one of the supplied facts, and reason "
    "must say in one sentence what that fact implies for the next 21 sessions. "
    "Never cite a fact that is not in the list. Never reason from the ticker's reputation, "
    "the sector's story, or anything you remember about the company from training -- only "
    "from the numbers and the facts in front of you. "
    "Answer in English only."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "required": list(REQUIRED_KEYS),
    "properties": {
        "p_up_21d": {"type": "number"},
        "exp_return": {"type": "number"},
        "downside_5pct": {"type": "number"},
        "confidence": {"type": "number"},
        "fact_id": {"type": "string"},
        "reason": {"type": "string"},
    },
}


def facts_for(labels: list[dict], symbol: str, *, as_of: str,
              lookback_days: int) -> list[dict]:
    """The company's genuinely new dated facts, newest first, with ids.

    FILTERED, not counted. `role == 'subject'` drops the listicles that name
    twenty tickers; `is_new_fact` drops the recaps. Together they removed ~92%
    of corpus rows on the 2026-08-30 measurement, and the 8% that survive are
    the only ones that could carry information a price has not already had.
    """
    from datetime import date, timedelta

    try:
        floor = (date.fromisoformat(as_of[:10]) - timedelta(days=lookback_days)).isoformat()
    except ValueError:
        return []
    out = []
    for r in labels:
        if (r.get("symbol") or "").upper() != symbol.upper():
            continue
        if r.get("role") != "subject" or not r.get("is_new_fact"):
            continue
        eff = str(r.get("effective_at") or "")[:10]
        # BOTH clocks. `effective_at` bounds which window of the world; the
        # caller has already bounded `observed_at` to what was knowable. A
        # single bound on one of them is how the catalyst clause spent a week
        # silently reading zero rows.
        if not eff or eff < floor or eff > as_of[:10]:
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("effective_at") or ""), reverse=True)
    for i, r in enumerate(out, 1):
        r = dict(r)
        r["fact_id"] = f"F{i}"
        out[i - 1] = r
    return out


def build_user_prompt(row: dict, rule: dict, facts: list[dict]) -> str:
    """Everything the brain is allowed to see, and nothing else.

    Deliberately absent: the ticker's market cap, its fame, its price history in
    words, and any of the other names being scored. A cross-sectional view would
    let the model rank, and ranking is the rule's job.
    """
    def num(v, pct=False):
        if v is None:
            return "unreadable"
        return f"{v:+.1%}" if pct else f"{v:.4g}"

    lines = [
        f"COMPANY: {row.get('symbol')}  sector: {row.get('sector') or 'unknown'}",
        "",
        "WHAT THE TRACKER MEASURED TODAY",
        f"  analyst consensus (5 = strong buy): {num(row.get('consensus'))}"
        f"   from {row.get('coverage') or 'unknown'} analysts",
        f"  upside to the mean price target:    {num(row.get('upside'), pct=True)}",
        f"  drawdown from its 60-day high:      {num(row.get('drawdown_60d'), pct=True)}",
        f"  twelve-month return:                {num(row.get('ret_12m'), pct=True)}",
        f"  realised 20-day volatility:         {num(row.get('realised_vol_20d'), pct=True)}",
        f"  next dated catalyst:                "
        f"{row.get('days_to_catalyst') if row.get('days_to_catalyst') is not None else 'none known'}"
        f" calendar days away",
        f"  tracker status:                     {row.get('status')}",
        "",
        "THE RULE'S FORECAST, WHICH YOU ARE ADJUSTING",
        f"  p_up_21d (prob. of beating the market over 21 sessions): "
        f"{num(rule.get('p_up_21d'))}",
        f"  exp_return:    {num(rule.get('exp_return'), pct=True)}",
        f"  downside_5pct: {num(rule.get('downside_5pct'), pct=True)}",
        f"  confidence:    {num(rule.get('confidence'))}",
        "",
    ]
    if facts:
        lines.append(f"NEW DATED FACTS ABOUT THIS COMPANY, last "
                     f"{FACT_LOOKBACK_SESSIONS} sessions (newest first):")
        for f in facts:
            lines.append(
                f"  [{f['fact_id']}] {str(f.get('effective_at'))[:10]}"
                f"  type={f.get('event_type')}  expectation={f.get('expectation')}"
                f"  source={f.get('source')}")
            if f.get("title"):
                lines.append(f"        {str(f['title'])[:200]}")
    else:
        lines.append("NEW DATED FACTS ABOUT THIS COMPANY: none in the window.")
        lines.append("  With no fact to cite you must return the rule's numbers unchanged "
                     f"and fact_id '{NO_FACT}'.")
    lines += [
        "",
        "Return your own p_up_21d for the next 21 sessions. State the number you "
        "actually believe, not a nudge in a direction: if the facts barely matter, "
        "move the rule barely.",
    ]
    return "\n".join(lines)


def bound(answer: dict, rule: dict, facts: list[dict]) -> tuple[dict, list[str]]:
    """Enforce every rule the prompt only ASKS for. Returns (row, notes).

    Nothing here trusts the model. A prompt that says "you must cite a fact" is
    a request; this function is what makes it true, and every intervention is
    recorded on the row rather than applied silently -- a clip that is not
    counted is a cap nobody can audit.
    """
    notes: list[str] = []
    valid_ids = {f["fact_id"] for f in facts}
    fact_id = str(answer.get("fact_id") or NO_FACT).strip()

    if fact_id != NO_FACT and fact_id not in valid_ids:
        notes.append(f"cited fact {fact_id!r} was not supplied -- adjustment discarded")
        fact_id = NO_FACT

    base_p = rule.get("p_up_21d")
    out = {
        "fact_id": fact_id,
        "reason": str(answer.get("reason") or "")[:400],
        "rule_p_up_21d": base_p,
        "rule_exp_return": rule.get("exp_return"),
        "rule_downside_5pct": rule.get("downside_5pct"),
        "rule_confidence": rule.get("confidence"),
    }

    # NO FACT, NO MOVE. Enforced, not requested: this is the difference between
    # an adjuster and a model that always has an opinion.
    if fact_id == NO_FACT:
        if _is_num(answer.get("p_up_21d")) and _is_num(base_p) \
                and abs(_num(answer["p_up_21d"]) - _num(base_p)) > 1e-6:
            notes.append("moved p_up without naming a fact -- reverted to the rule")
        out.update(p_up_21d=base_p, exp_return=rule.get("exp_return"),
                   downside_5pct=rule.get("downside_5pct"),
                   confidence=rule.get("confidence"),
                   adjustment=0.0, clipped=False)
        return out, notes

    p = answer.get("p_up_21d")
    if not _is_num(p) or not _is_num(base_p):
        notes.append("p_up unreadable on one side -- rule kept")
        out.update(p_up_21d=base_p, exp_return=rule.get("exp_return"),
                   downside_5pct=rule.get("downside_5pct"),
                   confidence=rule.get("confidence"), adjustment=0.0, clipped=False)
        return out, notes

    p, base_p = _num(p), _num(base_p)
    delta = p - base_p
    clipped = abs(delta) > MAX_ADJUSTMENT + 1e-9
    if clipped:
        notes.append(f"p_up moved {delta:+.3f}, clipped to {MAX_ADJUSTMENT:.2f}")
        delta = MAX_ADJUSTMENT if delta > 0 else -MAX_ADJUSTMENT
    p_final = min(0.99, max(0.01, base_p + delta))

    # exp_return moves too, bounded against the name's OWN bad case rather than
    # a fixed percentage -- the same shift means different things to a utility
    # and to a clinical-stage biotech.
    er_rule, dn_rule = rule.get("exp_return"), rule.get("downside_5pct")
    er = answer.get("exp_return")
    if _is_num(er) and _is_num(er_rule) and _is_num(dn_rule):
        cap = abs(_num(dn_rule)) * MAX_EXP_RETURN_SHIFT_VS_DOWNSIDE
        shift = _num(er) - _num(er_rule)
        if abs(shift) > cap + 1e-12:
            notes.append(f"exp_return moved {shift:+.4f}, clipped to {cap:.4f}")
            shift = cap if shift > 0 else -cap
            clipped = True
        er_final = _num(er_rule) + shift
    else:
        er_final = er_rule

    # The DOWNSIDE is never allowed to shrink. A model that talks itself into a
    # smaller bad case has done the one thing this project has been burned by
    # most often, and it is the number the position size is built on.
    dn = answer.get("downside_5pct")
    if _is_num(dn) and _is_num(dn_rule):
        dn_final = -max(abs(_num(dn)), abs(_num(dn_rule)))
        if abs(_num(dn)) < abs(_num(dn_rule)) - 1e-12:
            notes.append("tried to shrink the downside -- the rule's bad case kept")
    else:
        dn_final = dn_rule

    conf = answer.get("confidence")
    conf_final = (min(1.0, max(0.0, _num(conf))) if _is_num(conf)
                  else rule.get("confidence"))

    out.update(p_up_21d=round(p_final, 4),
               exp_return=(round(er_final, 6) if _is_num(er_final) else None),
               downside_5pct=(round(dn_final, 6) if _is_num(dn_final) else None),
               confidence=(round(conf_final, 4) if _is_num(conf_final) else None),
               adjustment=round(p_final - base_p, 4), clipped=clipped)
    return out, notes


def _num(v):
    """A number, or None. Accepts a numeric STRING -- that is a parse, not a
    repair: '0.55' has exactly one reading. Anything ambiguous stays None and
    the caller keeps the rule's value and says so."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _is_num(v) -> bool:
    return _num(v) is not None


def run_summary(rows: list[dict]) -> dict:
    """What the run did, in the numbers a reader needs to distrust it.

    `n_adjusted` and `n_clipped` are the two that matter. A brain that adjusts
    nothing is not adding anything and is costing money to say so; a brain that
    clips constantly is being held back by the cap and the cap is the finding.
    """
    adj = [r for r in rows if r.get("fact_id") != NO_FACT]
    ups = [r for r in adj if (r.get("adjustment") or 0) > 0]
    downs = [r for r in adj if (r.get("adjustment") or 0) < 0]
    moves = [abs(r.get("adjustment") or 0) for r in adj]
    return {
        "n_scored": len(rows),
        "n_adjusted": len(adj),
        "n_unchanged_no_fact": len(rows) - len(adj),
        "n_up": len(ups), "n_down": len(downs),
        "n_clipped": sum(1 for r in rows if r.get("clipped")),
        "mean_abs_adjustment": (round(sum(moves) / len(moves), 4) if moves else 0.0),
        "max_abs_adjustment": (round(max(moves), 4) if moves else 0.0),
        # News framing is overwhelmingly positive and a reader that inherits
        # that framing will adjust up almost every time. This is the number
        # that shows it before a grade is available.
        "share_adjusted_up": (round(len(ups) / len(adj), 3) if adj else None),
        "at_the_cap": sum(1 for r in adj
                          if abs(abs(r.get("adjustment") or 0) - MAX_ADJUSTMENT) < 1e-9),
        "notes_raised": sum(len(r.get("brain_notes") or []) for r in rows),
    }


def grade(rows: list[dict], outcomes: dict[str, float]) -> dict:
    """Did the brain beat the RULE it was given? Not "was the brain any good".

    `outcomes[symbol]` is the realised market-relative return over the horizon.
    Only names the brain actually MOVED are graded -- scoring the untouched ones
    would dilute the comparison with rows where the two forecasts are identical
    by construction, which is how a null gets reported as a small positive.
    """
    graded = [r for r in rows
              if r.get("fact_id") != NO_FACT and r["symbol"] in outcomes
              and _is_num(r.get("p_up_21d")) and _is_num(r.get("rule_p_up_21d"))]
    if not graded:
        return {"n": 0, "verdict": "NOT GRADEABLE",
                "why": "no name was both adjusted and resolved"}

    def brier(key: str) -> float:
        return sum((r[key] - (1.0 if outcomes[r["symbol"]] > 0 else 0.0)) ** 2
                   for r in graded) / len(graded)

    b_brain, b_rule = brier("p_up_21d"), brier("rule_p_up_21d")
    # The paired difference, which is the only honest test: the same names, the
    # same outcomes, two forecasts.
    diffs = [((r["rule_p_up_21d"] - (1.0 if outcomes[r["symbol"]] > 0 else 0.0)) ** 2
              - (r["p_up_21d"] - (1.0 if outcomes[r["symbol"]] > 0 else 0.0)) ** 2)
             for r in graded]
    mean = sum(diffs) / len(diffs)
    if len(diffs) > 1:
        var = sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1)
        t = mean / ((var / len(diffs)) ** 0.5) if var > 0 else None
    else:
        t = None
    # Did the adjustment point the right way? Direction is a coarser question
    # than calibration and it is the one a reader asks first.
    right = sum(1 for r in graded
                if (r["adjustment"] > 0) == (outcomes[r["symbol"]] > 0))
    return {
        "n": len(graded),
        "brier_brain": round(b_brain, 5),
        "brier_rule": round(b_rule, 5),
        "brier_improvement": round(b_rule - b_brain, 5),
        "paired_t": (round(t, 3) if t is not None else None),
        "adjustment_direction_right": round(right / len(graded), 4),
        "verdict": ("BRAIN BETTER" if b_brain < b_rule else
                    "RULE BETTER" if b_rule < b_brain else "TIED"),
        "note": ("Brier is lower-is-better. Only ADJUSTED names are graded -- on the "
                 "untouched ones the two forecasts are identical by construction and "
                 "including them would dilute any real difference towards zero."),
    }
