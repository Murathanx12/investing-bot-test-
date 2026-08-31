"""THE FLEET -- six paper accounts, six DECLARED mandates, one equity curve each.

    python -m scripts.fleet --plan            # the table
    python -m scripts.fleet --env-template    # the .env lines to fill
    python -m scripts.fleet --railway thesis  # the Railway commands for one role
    AAT_ACCOUNT_ROLE=thesis python -m scripts.fleet --check   # is the account fresh?

WHY SIX ACCOUNTS AND NOT ONE ARGUMENT
=====================================
Murat, 28 Aug: "one or two safe, the rest try your best to maximise P&L --
options, risky trades, small caps, the themes I believe in." An Alpaca account
is ONE equity curve, so every mandate below is a separate account: the verdict
on "was the safe book or the thesis book right this week" is then a number in a
ledger, not a memory of who argued louder. This is the parent project's farm
with real fills.

A mandate is DATA, not prose: which brains may spend, which universe, which
sizing envelope, which ranking objective, which structure kinds. The loop reads
it through `loop_args()`, so the Railway service for a role is the same image
with `AAT_ACCOUNT_ROLE` set and nothing else decided by hand at 11:00 ET.

WHAT DOES NOT CHANGE PER MANDATE
================================
The HARD guards (`alpha/guards.py`): paper host only, genesis verified, no LLM
order path, tif=day options, bounded worst case per structure. `maximum`
raises the SIZE of a bounded bet; it never unbounds one. The `thesis` and
`convexity` mandates carry a written caveat -- the whole future-state basket
was measured DOWN 20-50% over the prior 20 sessions at 60-170% annualised vol
(`scripts.theme_screen`, 28 Aug). Five sessions of that is a ~14% one-sigma
swing on the basket. That is the bet the human asked for; the number is on the
mandate so nobody reads the outcome as a surprise.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "docs" / "seed"
THEMES_SEED = SEED_DIR / "universe" / "THEMES_2026-08-28.json"


@dataclass(frozen=True)
class Mandate:
    role: str
    tier: str                       # SAFE | RISKY
    label: str
    question: str                   # what this equity curve answers
    brains: tuple[str, ...]
    shadow: tuple[str, ...] = ()
    profile: str = "aggressive"     # alpha/engine/sizing.PROFILES
    universe: str = "window"        # window | themes | themes_with_options | index | fixed
    fixed_symbols: tuple[str, ...] = ()
    rank_objective: str | None = None   # None -> tournament mode decides; "mean" | "median"
    structure_kinds: tuple[str, ...] = ()   # () = every kind the engine enumerates
    allow_maximum: bool = False
    caveat: str = ""
    extra_args: tuple[str, ...] = ()
    env: dict = field(default_factory=dict)


FLEET: dict[str, Mandate] = {
    "hack1": Mandate(
        role="hack1", tier="SAFE", label="ANCHOR: beta core + defined-risk sleeve",
        question="Does the attended book (SPY/QQQ/IWM shares + one ATM index call at 5%) hold +0.3% median over five sessions?",
        brains=("post_event_drift",), profile="conservative", universe="index",
        fixed_symbols=("SPY", "QQQ", "IWM", "NVDA", "AVGO", "PANW"), rank_objective="median",
        caveat="Entered by hand via scripts.competition_book after 15:45 ET; the loop only manages exits and the +1-open drift on the index-linked printers."),
    "hack2": Mandate(
        role="hack2", tier="SAFE", label="DRIFT: measured edge only",
        question="Does the one brain with a positive live counterfactual (+1-open post-print drift, +1.08%, t 2.82) pay at aggressive size?",
        brains=("post_event_drift",), shadow=("narrative_dispersion",), profile="aggressive", universe="window",
        rank_objective="median", extra_args=("--window-universe",)),
    "hack3": Mandate(
        role="hack3", tier="RISKY", label="THESIS: Murat's future-state basket",
        question="Do robotics-sensors, quantum, nuclear, storage, grid and raw-materials names beat IWM this week when bought NEAR THEIR 20-SESSION HIGH (half tilt)? The original dip-buy (20-50% drawdown) was adjudicated against on CRSP 2013-2024 (-0.31%/5d, t -2.35) and is REFUSED by the brain; any dip entry is a typed human thesis (scripts.thesis).",
        brains=("theme_basket", "murat_rule"), profile="basket", universe="themes_plus_rule",
        allow_maximum=True,
        rank_objective="median", structure_kinds=("long_shares", "bull_call_spread", "long_call"),
        caveat="ADJUDICATED 28 Aug (Aegis knife_basket_backtest, CRSP 2013-2024): the -50..-20% drawdown cell LOSES -0.31%/5d (t -2.35); only >50%-down at >100% vol pays (+2.32%, t 2.60, n=88). theme_basket now buys only that cell and near-high names; the middle is declined with the number. Graded vs IWM and vs `hack2`."),
    "hack4": Mandate(
        role="hack4", tier="RISKY", label="TRACKER PROFIT-MAX: sealed upside x consensus, shares only",
        question="Does upside x consensus + catalyst selection (sealed pre-open, k=5 x 10%) create better P&L and opportunity recall than measured drift (hack2) and balanced breadth (hack3)?",
        brains=("tracker_portfolio",), shadow=("post_event_drift",), profile="maximum", universe="window",
        allow_maximum=True, rank_objective="median", structure_kinds=("long_shares",),
        extra_args=("--window-universe",),
        caveat="APPROVED 2026-08-31 (docs/DECISION_2026-08-31_HACK4_TRACKER_APPROVED.md): shares only, "
               "the sealed notional is a reduce-only ceiling, exact names from the sealed artifact. "
               "STATED PROPERTY, not an accident: profit_max has NO max_downside, so it selects "
               "high-modelled-downside names BY CONSTRUCTION -- report the worst case BOTH ways "
               "(stop-based AND all-names-gap-to-modelled-5%-downside; on 2026-08-31 those were "
               "-3.00% and ~-18.4%). The old post-print continuation mandate runs as shadow."),
    "hack5": Mandate(
        role="hack5", tier="RISKY", label="CONVEXITY: options only, EV-ranked",
        question="When the ranker is allowed to chase the mean (long calls, bull call spreads) on the high-vol theme names, does five sessions of it end above the median book?",
        brains=("theme_basket", "post_event_drift"), profile="convex", universe="themes_with_options",
        allow_maximum=False, rank_objective="mean", structure_kinds=("long_call", "bull_call_spread"),
        caveat="Long premium on 100%-vol names: the receipt says P(profit) ~33-51% per structure; this account exists to measure the tail, not to be the safe one."),
    "hack6": Mandate(
        role="hack6", tier="RISKY", label="BLEND: council vector + drift + basket",
        question="Does MIXING three independent selectors (council vector, post-print drift, theme basket) in one aggressive book beat each of them alone? (Murat: 'the best will be mixing them')",
        brains=("council_vector", "post_event_drift", "theme_basket"), profile="aggressive", universe="window_plus_themes",
        rank_objective="median", extra_args=("--window-universe", "--council"),
        caveat="The council is fed by `scripts.dislocation_scan --deep` each morning; a day with no packets is a day this account holds cash, and that is recorded, not hidden."),
}

SAFE = tuple(r for r, m in FLEET.items() if m.tier == "SAFE")
RISKY = tuple(r for r, m in FLEET.items() if m.tier == "RISKY")

COMMON_ENV = {
    "AAT_TRADING_BASE": "https://paper-api.alpaca.markets",
    "AAT_DATA_BASE": "https://data.alpaca.markets",
    "AAT_OPTIONS_FEED": "indicative",
    "AAT_STOCK_FEED": "iex",
    "AAT_LEDGER_DIR": "/app/state",
    "AAT_LOOP_EXPIRY": "2026-09-04",
}
SECRETS = ("AAT_DEEPSEEK_API_KEY", "AAT_FINNHUB_API_KEY", "AAT_FRED_API_KEY", "AAT_NVIDIA_API_KEY", "AAT_HF_TOKEN")


def theme_symbols(*, with_options_only: bool = False) -> list[str]:
    if not THEMES_SEED.exists():
        raise FileNotFoundError(f"{THEMES_SEED} missing: run `python -m scripts.theme_screen` first")
    d = json.loads(THEMES_SEED.read_text(encoding="utf-8"))
    return list(d["with_options"] if with_options_only else d["tradable"])


def rule_claimed_symbols(day: str | None = None) -> list[str]:
    """Names TODAY'S SEALED BOOK claimed under `murat_rule_v1`, in rank order.

    Read from the seal, never re-derived. If there is no sealed book, or it
    claimed nothing, this returns `[]` and the account trades its theme names
    alone -- which is the correct behaviour and is visible in the receipt as an
    empty list rather than as an absent one.
    """
    from alpha.brains import murat_rule as _mr
    from alpha import exits as _ex
    book = _mr._book_for(day or _ex.session_day())
    if not book:
        return []
    return [r["symbol"] for r in (book.get("predictions") or [])
            if r.get("generator") == "murat_rule_v1" and r.get("claims")]


def universe_for(m: Mandate) -> list[str] | None:
    """Explicit symbol list, or None when the loop builds it (`--window-universe`)."""
    if m.universe == "window":
        return None
    if m.universe == "themes":
        return theme_symbols()
    if m.universe == "themes_plus_rule":
        # The rule's claims are UNIONED onto the theme list because the two
        # selectors do not share a universe: `murat_rule_v1` ranks the whole
        # 152-name panel and its best name on 2026-08-30 (MU) is not a theme
        # name at all. Without the union the selector would be wired in and
        # never asked about the only name it claimed -- live, and silent.
        #
        # This CANNOT raise the worst case. hack3's bound is
        # `gross_cap('basket') x stop_fraction('basket')` = 1.00 x 8% = -8.00%
        # of equity, and that expression has no name-count term in it: more
        # names divide the same gross, they do not add to it. Only raising the
        # cap or the stop moves the bound, and neither is touched here.
        return sorted(set(theme_symbols()) | set(rule_claimed_symbols()))
    if m.universe == "themes_with_options":
        return theme_symbols(with_options_only=True)
    if m.universe == "window_plus_themes":
        # `--window-universe` supplies the printers on the loop side; the explicit
        # list here is ADDED to it (agent_loop unions --universe with the window).
        return theme_symbols()
    return list(m.fixed_symbols)


def loop_args(m: Mandate) -> list[str]:
    """The `scripts.agent_loop` flags this mandate prescribes (after --expiry/--live)."""
    args = ["--brains", ",".join(m.brains), "--profile", m.profile]
    if m.shadow:
        args += ["--shadow", ",".join(m.shadow)]
    args += list(m.extra_args)
    syms = universe_for(m)
    if syms:
        args += ["--universe", *syms]
    return args


def env_for(m: Mandate) -> dict[str, str]:
    e = {**COMMON_ENV, "AAT_ACCOUNT_ROLE": m.role, "AAT_RISK_PROFILE": m.profile,
         "AAT_LOOP_BRAINS": ",".join(m.brains)}
    if m.shadow:
        e["AAT_LOOP_SHADOW"] = ",".join(m.shadow)
    if m.rank_objective:
        e["AAT_RANK_OBJECTIVE"] = m.rank_objective
    if m.structure_kinds:
        e["AAT_STRUCTURE_KINDS"] = ",".join(m.structure_kinds)
    if m.allow_maximum:
        e["AAT_ALLOW_MAXIMUM"] = "1"
    rest = loop_args(m)
    # the brains/shadow/profile are carried by their own variables; the remainder is AAT_LOOP_ARGS
    tail = []
    skip = 0
    for i, a in enumerate(rest):
        if skip:
            skip -= 1
            continue
        if a in ("--brains", "--shadow"):
            skip = 1
            continue
        tail.append(a)
    e["AAT_LOOP_ARGS"] = " ".join(tail)
    e.update(m.env)
    return e


def env_template() -> str:
    lines = ["# THE FLEET -- one key pair per role; paste each account's keys here",
             "# The $25 API credit: paste it under its provider's own name (AAT_DEEPSEEK_API_KEY /",
             "# AAT_NVIDIA_API_KEY / AAT_HF_TOKEN / AAT_OPENAI_API_KEY) and `scripts.council --probe` will find it.",
             "# Featherless.ai ($25 credit):", "AAT_FEATHERLESS_API_KEY=", ""]
    for r, m in FLEET.items():
        lines += [f"# {r:<10} {m.tier:<5} {m.label}", f"AAT_{r.upper()}_KEY_ID=", f"AAT_{r.upper()}_SECRET_KEY=", ""]
    return "\n".join(lines)


def railway_commands(m: Mandate) -> str:
    svc = f"aat-loop-{m.role}"
    sets = " ".join(f'--set "{k}={v}"' for k, v in env_for(m).items())
    keys = f'--set "AAT_{m.role.upper()}_KEY_ID=$AAT_{m.role.upper()}_KEY_ID" --set "AAT_{m.role.upper()}_SECRET_KEY=$AAT_{m.role.upper()}_SECRET_KEY"'
    secrets = " ".join(f'--set "{k}=${k}"' for k in SECRETS)
    return "\n".join([
        f"railway add --service {svc}",
        f"railway service {svc}",
        "railway volume add -m /app/state",
        f"railway variables --service {svc} --skip-deploys {sets} {keys} {secrets}",
        f"railway up --service {svc} -d",
        f"railway logs --service {svc}",
    ])


def as_dict() -> dict:
    return {r: {**asdict(m), "loop_args": loop_args(m)} for r, m in FLEET.items()}
