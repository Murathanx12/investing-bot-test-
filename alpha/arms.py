"""ARMS -- one paper account per ALPHA SOURCE, and a refusal when two share one.

WHY THIS FILE EXISTS
====================
"More paper accounts is more data" is true only if the accounts disagree. The
parent project has the receipt for what happens when they do not: ten arena
books, each with its own name, its own NAV series and its own risk treatment,
and `selection: composite_top_k` over ONE signal in all ten. Five months of
forward record produced ONE observation, because

    independence is a property of the DATA, not of the account number.

The same lesson arrived again from the other end on 26 Aug: a $20bn book that
looked like 5.34 independent bets by weight was 1.43 by RISK, and 20 of its 21
names fell together on the day it mattered. Our own books measure 1.51 and 1.27.

So an arm is admitted on what INFORMATION it acts on, never on what it does with
that information afterwards. Two accounts running the same signal at different
position sizes are one arm with a size parameter. Two accounts running the same
signal on different sectors are one arm with a universe parameter -- and that is
the specific mistake most likely to be made here, because sector books LOOK
independent and share every factor.

WHAT AN ARM MUST DECLARE
========================
`alpha_source`  the information it acts on. Unique across live arms, enforced.
`hypothesis`    what it claims, in one sentence.
`falsifier`     the observation that would retire it. An arm with no falsifier
                is a hope; `validate()` refuses it.
`status`        proposed -> ready -> live -> retired. Only `live` arms trade, and
                nothing here flips that flag: seeding is attended (`seed-a-lane`).

WHAT THIS FILE DOES NOT DO
==========================
It does not create Alpaca accounts -- the Trading API cannot, that is a Broker
API capability, so each account is made by hand in the dashboard and its keys
pasted into `.env` as `AAT_<ROLE>_KEY_ID` / `AAT_<ROLE>_SECRET_KEY`. It does not
start loops and it does not place orders. It declares, checks, and measures.
"""
from __future__ import annotations

import math
import os
import statistics as st
from dataclasses import dataclass, field, asdict


class ArmRefusal(RuntimeError):
    """An arm registry that would produce correlated books wearing distinct names."""


@dataclass(frozen=True)
class Arm:
    role: str
    """Account role. Credentials live at AAT_<ROLE>_KEY_ID / _SECRET_KEY."""
    alpha_source: str
    """THE INFORMATION. Unique across live arms -- this is the whole point."""
    hypothesis: str
    falsifier: str
    """What observation retires this arm. Not 'it loses money' -- a measurement."""
    instruments: tuple[str, ...]
    universe: str
    status: str = "proposed"
    brains: tuple[str, ...] = ()
    notes: str = ""
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    """Named blockers. An arm with these cannot reach `ready`, and says why."""

    def credentials_present(self) -> bool:
        pre = "AAT_" + self.role.upper()
        return bool(os.getenv(pre + "_KEY_ID", "").strip()
                    and os.getenv(pre + "_SECRET_KEY", "").strip())


STATUSES = ("proposed", "ready", "live", "retired")


#: The arms. Ordered by how close each is to being able to trade, not by how
#: interesting it is. Every `alpha_source` string here is distinct, and
#: `validate()` fails the module if that ever stops being true.
ARMS: tuple[Arm, ...] = (
    Arm(
        role="dev",
        alpha_source="realised_vs_implied_variance",
        hypothesis="The gap between EWMA realised volatility and the chain's own quoted "
                   "width is tradeable once both are measured in the same units.",
        falsifier="scripts.index_premium_backtest reports the seller's edge UNRESOLVED or "
                  "negative after costs on >100 weeks, or vol_gap's sigma stops matching "
                  "independently computed truth.",
        instruments=("iron_condor", "credit_spread", "long_straddle"),
        universe="index ETFs + liquid mega-cap",
        status="live",
        brains=("vol_gap",),
        notes="The only brain measured ACCURATE against no-lookahead truth (0.97x on 25 Aug) "
              "while narrative_dispersion and options_attention ran 1.16-1.17x. "
              "Its arithmetic was wrong until 27 Aug, not its statistics.",
    ),
    Arm(
        role="exp1",
        alpha_source="llm_narrative_dispersion",
        hypothesis="Disagreement across generated narratives forecasts realised dispersion "
                   "beyond what the chain prices.",
        falsifier="its sigma stays >1.15x measured realised vol over 20+ sessions -- at which "
                  "point it is not forecasting dispersion, it is mis-estimating volatility.",
        instruments=("long_straddle", "iron_condor"),
        universe="index ETFs + liquid mega-cap",
        status="live",
        brains=("narrative_dispersion", "options_attention"),
        notes="ON NOTICE. Measured 1.16x/1.17x sigma inflation on 25 Aug and bought the SPY "
              "and IWM straddles that are this book's largest losses. The falsifier above is "
              "not hypothetical; it is one measurement away.",
    ),
    Arm(
        role="cash",
        alpha_source="null_no_position",
        hypothesis="None. This is the null, and it has beaten live arms before "
                   "(session 5: cash was a champion).",
        falsifier="Cannot be falsified; it is the benchmark the others must clear.",
        instruments=(),
        universe="none",
        status="retired",
        notes="RETIRED FROM THE ACCOUNT QUEUE on 27 Aug, not as a benchmark. A paper account "
              "holding $100,000 and never trading has an NAV of exactly $100,000 forever -- "
              "Alpaca pays no interest on paper cash -- so running it consumes an account to "
              "learn a number already known analytically. Keep charging every arm against "
              "zero; just do not spend a broker account proving that zero is zero. The null "
              "that DOES need an account is `market`, because its path is not known in advance.",
    ),
    Arm(
        role="market",
        alpha_source="passive_beta",
        hypothesis="None -- it is the bar. Buy the index at the open and never trade again. "
                   "Any arm that cannot beat this after costs is an expensive way to own beta.",
        falsifier="Cannot be falsified. It is the 'better than WHAT?' answer for the PRODUCT "
                  "question ('should I hold this instead of an index'), which is the question "
                  "the competition is judged on. It is NOT the right control for a claim about "
                  "a signal -- two books can beat the market for the same reason and neither "
                  "of them be the reason. Use the paired construction for that.",
        instruments=("shares",),
        universe="SPY (or SPY/QQQ/IWM equal-weight)",
        status="proposed",
        notes="Costs one account, one order, and zero attention thereafter. Unlike cash its "
              "path is NOT known in advance, which is the whole reason it is worth an account: "
              "the drawdown it takes on the way is the number every arm is really competing "
              "against, and it cannot be reconstructed after the fact from a closing level.",
    ),
    Arm(
        role="pead",
        alpha_source="post_earnings_drift_from_source",
        hypothesis="Drift after an earnings SOURCE document (not the wire) is tradeable in "
                   "the direction of the surprise.",
        falsifier="the pair (short loser / long IWM) loses its +0.35%/3d over 20 further "
                  "quarters, or edge stays confined to the >5% surprise tail.",
        instruments=("shares", "debit_spread"),
        universe="whole-market candidates, dollar-volume stratified",
        status="proposed",
        brains=("post_event_drift",),
        notes="Survived decomposition (session 6). The UNHEDGED wide-DOWN side is REFUSED "
              "and stays refused; this arm is the PAIR only.",
    ),
    Arm(
        role="bottleneck",
        alpha_source="supply_chain_constraint_ranking",
        hypothesis="The node of a build-out with revenue growth AND margin expansion is "
                   "capturing scarcity rent, and that ranking leads price.",
        falsifier="the ranking's top node fails to out-return the median node over 8 "
                  "quarters, or the binary keeps qualifying 6 of 7 nodes.",
        instruments=("shares", "debit_spread"),
        universe="AI build-out chain nodes",
        status="proposed",
        depends_on=("NEEDS_GRAPH binary discriminates nothing -- only the ORDERING survived; "
                    "an arm needs a rule, and ranking is not yet one",),
        notes="Its one cross-check is real: memory/HBM ranked most constrained hours before "
              "NVDA disclosed +$160bn of commitments 'primarily for memory'. One event.",
    ),
    Arm(
        role="torque",
        alpha_source="state_change_elasticity",
        hypothesis="The same shock is transformational for a small firm and immaterial for a "
                   "mega-cap; ranking by shock/revenue beats ranking by market cap.",
        falsifier="residual reactions of top-elasticity names fail to exceed matched controls "
                  "across 10+ anchor events.",
        instruments=("shares",),
        universe="anchor-linked names, non-USD reporters excluded and named",
        status="proposed",
        depends_on=("one event cannot resolve it -- ANCHOR_TO_TORQUE's first run cleared no "
                    "name's own MDE, which is the power limit working, not a failure",),
    ),
    Arm(
        role="unsupervised",
        alpha_source="unsupervised_return_clustering",
        hypothesis="Clusters found in return space without labels identify regimes or "
                   "co-movement groups that named sectors do not, and cluster membership "
                   "carries information a sector dummy does not.",
        falsifier="cluster assignment adds nothing over a sector dummy plus market beta in a "
                  "regression on forward returns -- which is the ONLY test that separates this "
                  "from an expensive re-derivation of GICS.",
        instruments=("shares",),
        universe="whole-market, dollar-volume stratified",
        status="proposed",
        depends_on=("no code yet",
                    "needs its OWN paper account. The spare key offered on 27 Aug "
                    "(PKLL7KBIPZ...) is NOT spare -- it is ALPACA_ARENA_API_KEY_ID in the "
                    "aegis-finance repo, the arena's account with its own seeded NAV history. "
                    "Pointing a second strategy at it would write foreign fills into a track "
                    "record that CANON forbids mutating. Provision a new one."),
        notes="The hardest arm to keep honest. Unsupervised methods always FIND clusters; the "
              "question is never whether clusters exist but whether they beat the free label. "
              "It ships with the control or it does not ship.",
    ),
    Arm(
        role="analyst",
        alpha_source="analyst_target_dislocation",
        hypothesis="Price far below a fresh analyst target, with revisions improving, is the "
                   "screen Murat traded by hand.",
        falsifier="target-gap quintiles show no monotone forward return once size and "
                  "momentum are controlled.",
        instruments=("shares",),
        universe="covered names, dollar-volume stratified",
        status="proposed",
        depends_on=("Finnhub free tier returns 403 on stock/price-target, so TARGET/PRICE-1 "
                    "cannot be computed at all -- recorded UNAVAILABLE_FREE_TIER, never "
                    "approximated",),
        notes="Recommendation BREADTH is already refuted as a substitute: 93% of covered names "
              "carry net-positive breadth, so it conditions on nothing. The target gap is a "
              "different variable and is still missing.",
    ),
)


def validate(arms: tuple[Arm, ...] = ARMS) -> None:
    """Refuse a registry that would produce correlated books under distinct names."""
    seen: dict[str, str] = {}
    for a in arms:
        if a.status not in STATUSES:
            raise ArmRefusal(f"{a.role}: status {a.status!r} not in {STATUSES}")
        if not a.role.replace("_", "").isalnum() or a.role != a.role.lower():
            raise ArmRefusal(f"{a.role!r} is not a valid role name")
        if not a.falsifier.strip():
            raise ArmRefusal(
                f"{a.role}: no falsifier. An arm that cannot be retired by an observation is "
                "a hope with an account number.")
        if a.status in ("live", "ready") and a.alpha_source in seen:
            raise ArmRefusal(
                f"{a.role} and {seen[a.alpha_source]} both claim alpha_source "
                f"{a.alpha_source!r}. That is two accounts running one bet -- the arena "
                "bottleneck, rebuilt. Give one of them a different SOURCE or merge them.")
        if a.status in ("live", "ready"):
            seen[a.alpha_source] = a.role
        if a.status in ("live", "ready") and a.depends_on:
            raise ArmRefusal(
                f"{a.role} is {a.status} but still declares blockers: {a.depends_on}")


def readiness(arms: tuple[Arm, ...] = ARMS) -> list[dict]:
    """Per arm: what stands between it and a forward record. No side effects."""
    validate(arms)
    out = []
    for a in arms:
        missing = list(a.depends_on)
        if not a.credentials_present():
            missing.append(
                f"no credentials: create a paper account in the Alpaca dashboard and set "
                f"AAT_{a.role.upper()}_KEY_ID / AAT_{a.role.upper()}_SECRET_KEY")
        out.append({**asdict(a), "credentials_present": a.credentials_present(),
                    "blocked_by": missing, "can_seed": not missing and a.status != "retired"})
    return out


def effective_n(series: dict[str, list[float]]) -> dict:
    """How many INDEPENDENT bets a set of arms is really making.

    `series` maps role -> daily NAV returns, already aligned by date. Effective N
    is `(sum w)^2 / (w' C w)` at equal weights -- the same quantity that read
    1.43 on a $20bn book which looked like 5.34 by weight.

    Refuses rather than reassures: fewer than MIN_OBS overlapping observations
    returns None with a reason, because a correlation from four days is a
    correlation from four days however confidently it is printed.
    """
    MIN_OBS = 20
    roles = sorted(k for k, v in series.items() if v)
    n = len(roles)
    if n < 2:
        return {"effective_n": None, "why": f"{n} arm(s) with data; need 2"}
    length = min(len(series[r]) for r in roles)
    if length < MIN_OBS:
        return {"effective_n": None, "n_obs": length, "arms": n,
                "why": f"only {length} overlapping observations across {n} arms; "
                       f"{MIN_OBS} is the floor. The forward record is too young to say "
                       f"whether these arms are independent -- and 'we could not tell' must "
                       f"not be written down as 'they are'."}
    cols = {r: series[r][-length:] for r in roles}
    means = {r: st.mean(cols[r]) for r in roles}
    sds = {r: st.stdev(cols[r]) for r in roles}
    if any(s <= 0 for s in sds.values()):
        flat = [r for r in roles if sds[r] <= 0]
        return {"effective_n": None, "why": f"arm(s) {flat} have zero variance over the window"}

    def rho(a: str, b: str) -> float:
        return sum((cols[a][i] - means[a]) * (cols[b][i] - means[b]) for i in range(length)) \
            / ((length - 1) * sds[a] * sds[b])

    w = 1.0 / n
    var = sum(w * w * sds[a] * sds[b] * (1.0 if a == b else rho(a, b))
              for a in roles for b in roles)
    avg_sd = st.mean(list(sds.values()))
    eff = (avg_sd ** 2) / var * (1.0 / n) if var > 0 else None
    pairs = {f"{a}|{b}": round(rho(a, b), 3)
             for i, a in enumerate(roles) for b in roles[i + 1:]}
    return {"effective_n": round(eff, 2) if eff else None, "arms": n, "n_obs": length,
            "pairwise_rho": pairs,
            "avg_rho": round(st.mean(list(pairs.values())), 3) if pairs else None,
            "reference": "a $20bn book measured 1.43 here on the day it was liquidated"}
