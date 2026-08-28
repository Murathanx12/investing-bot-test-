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
    "anchor": Mandate(
        role="anchor", tier="SAFE", label="Beta core + defined-risk sleeve",
        question="Does the attended book (SPY/QQQ/IWM shares + one ATM index call at 5%) hold +0.3% median over five sessions?",
        brains=("post_event_drift",), profile="conservative", universe="index",
        fixed_symbols=("SPY", "QQQ", "IWM", "NVDA", "AVGO", "PANW"), rank_objective="median",
        caveat="Entered by hand via scripts.competition_book after 15:45 ET; the loop only manages exits and the +1-open drift on the index-linked printers."),
    "drift": Mandate(
        role="drift", tier="SAFE", label="Measured edge only",
        question="Does the one brain with a positive live counterfactual (+1-open post-print drift, +1.08%, t 2.82) pay at aggressive size?",
        brains=("post_event_drift",), shadow=("narrative_dispersion",), profile="aggressive", universe="window",
        rank_objective="median", extra_args=("--window-universe",)),
    "thesis": Mandate(
        role="thesis", tier="RISKY", label="Murat's future-state basket",
        question="Do robotics-sensors, quantum, nuclear, storage, grid and raw-materials names beat IWM this week when bought after a 20-50% drawdown?",
        brains=("theme_basket",), profile="basket", universe="themes", allow_maximum=True,
        rank_objective="median", structure_kinds=("long_shares", "bull_call_spread", "long_call"),
        caveat="Hand-curated universe (survivorship-shaped); basket down 20-50%/20 sessions, rv60 60-170%. Graded vs IWM and vs `drift`."),
    "predator": Mandate(
        role="predator", tier="RISKY", label="Small-cap post-print continuation",
        question="Does the 116,231-event continuation cell (surprise and reaction agree) pay outside the mega-11 via shares and the short-loser/long-IWM pair?",
        brains=("post_event_drift",), shadow=("narrative_dispersion",), profile="maximum", universe="window",
        allow_maximum=True, rank_objective="median", extra_args=("--window-universe",)),
    "convexity": Mandate(
        role="convexity", tier="RISKY", label="Options only, EV-ranked",
        question="When the ranker is allowed to chase the mean (long calls, bull call spreads) on the high-vol theme names, does five sessions of it end above the median book?",
        brains=("theme_basket", "post_event_drift"), profile="convex", universe="themes_with_options",
        allow_maximum=False, rank_objective="mean", structure_kinds=("long_call", "bull_call_spread"),
        caveat="Long premium on 100%-vol names: the receipt says P(profit) ~33-51% per structure; this account exists to measure the tail, not to be the safe one."),
    "council": Mandate(
        role="council", tier="RISKY", label="LLM council vector",
        question="Does a thesis vector synthesised by specialised models (fact/expectations/cube/causal/skeptic of another family) beat the price-only drift brain on the same printers?",
        brains=("council_vector", "post_event_drift"), profile="aggressive", universe="window",
        rank_objective="median", extra_args=("--window-universe",),
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


def universe_for(m: Mandate) -> list[str] | None:
    """Explicit symbol list, or None when the loop builds it (`--window-universe`)."""
    if m.universe == "window":
        return None
    if m.universe == "themes":
        return theme_symbols()
    if m.universe == "themes_with_options":
        return theme_symbols(with_options_only=True)
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
             "# AAT_NVIDIA_API_KEY / AAT_HF_TOKEN / AAT_OPENAI_API_KEY) and `scripts.council --probe` will find it.", ""]
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
