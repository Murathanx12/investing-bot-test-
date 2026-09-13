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
from datetime import date, timedelta
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
    manage_only: bool = False
    """This book may NOT open positions from the loop: exits, stops, fills,
    marking and the counterfactual continue, and the book can only get smaller.

    A MANDATE THAT LIVES ONLY IN PROSE IS NOT A MANDATE. hack1's `caveat` has
    said "the loop only manages exits and the +1-open drift" since the fleet was
    written, and nothing read it -- so on 2026-09-03 the SAFE anchor book shorted
    PANW and lost $475, and on 2026-09-04 it left a working short at 11:01 ET.
    `--manage-only` already existed in `scripts.agent_loop`; the defect was that
    no mandate could ask for it. This field is that ask, and `loop_args` emits
    it, so the declaration and the command line cannot disagree.

    Declared per role rather than inferred from `tier`: SAFE describes the SIZE
    of the risk a book may take, not whether the loop may originate it, and
    conflating the two would silently disarm any future SAFE book that is meant
    to trade."""
    allow_short: bool = False
    """May this book open a SHORT side at all (shares or short premium)?

    `tier` WAS DECLARATIVE ONLY, AND IT COST $725 (2026-09-03/04).
    `Mandate.tier` was read nowhere outside this module's own table-printing,
    so a SAFE anchor book opened five unhedged PANW shorts -- a structure whose
    theoretical loss is unbounded -- by OMISSION rather than by design, and the
    only enforcement anywhere in the repo was a test asserting SAFE roles do not
    run a gated profile. `alpha/admission.py` now refuses a short-side structure
    on a book that has not declared this flag, and `may_short()` below is the
    single place that answers the question.

    Declared per role rather than inferred from `tier`, for the same reason
    `manage_only` is: a future SAFE book that is MEANT to run a hedged short
    should say so in one line rather than be silently disarmed by its tier.
    """
    caveat: str = ""
    extra_args: tuple[str, ...] = ()
    env: dict = field(default_factory=dict)


FLEET: dict[str, Mandate] = {
    "hack1": Mandate(
        role="hack1", tier="RISKY", label="THEME BASKET: the human-heuristic themes, shares only",
        question="Does the theme basket -- the one brain with a positive live counterfactual on the marks (+$3,564 on 7, hit 0.43, fresh) -- pay as a fully invested 21-session book?",
        brains=("theme_basket",), shadow=("post_event_drift", "murat_rule"), profile="aggressive", universe="themes",
        rank_objective="median", structure_kinds=("long_shares",),
        manage_only=False,
        caveat="v2, 2026-09-09 (Murat: 'make sure the paper accounts are all active and using their buying power'). "
               "Until then this was the hand-entered SAFE anchor (SPY/QQQ/IWM + one index call), manage-only since "
               "2026-09-04 and EMPTY since. Contract in contract.HORIZON_REMAP['hack1']: horizon 21, min hold 5, "
               "10% stop, no target; sizing intent 8 x 12.5% = 100% gross, no leverage. Worst case, printed: -10% of "
               "equity. Shares only; the old index anchor is retired, not shadowed."),
    "hack2": Mandate(
        role="hack2", tier="SAFE", label="DRIFT: measured edge only",
        question="Does the one brain with a positive live counterfactual (+1-open post-print drift, +1.08%, t 2.82) pay at aggressive size?",
        brains=("post_event_drift",), shadow=("narrative_dispersion",), profile="aggressive", universe="window",
        rank_objective="median", extra_args=("--window-universe",),
        # UN-MANAGE-ONLY 2026-09-07, BY THE CONDITION THIS CAVEAT ITSELF SET.
        # The caveat below said hack2 "stays manage-only until its own contract
        # is frozen". It is now frozen, in `contract.HORIZON_REMAP`: horizon 5,
        # minimum hold 2, NO profit target, and an 8% stop instead of the
        # aggressive profile's 3%. Every clause of the stated objection is
        # answered -- the zero minimum hold, the +2.5% target and the 3% stop
        # were the three things named -- so the flag is lifted rather than left
        # standing out of habit. A gate whose condition has been met and which
        # stays shut is not caution, it is an unread gate.
        manage_only=False,
        caveat="MANAGE-ONLY from 2026-09-06 to 2026-09-07, now LIFTED. The original objection (Fable, Murat's decision): this book's contract "
               "is the EVENT defaults field-for-field (horizon 3, min hold 0, +2.5% target on a "
               "3% stop) -- the same-day churn B2 was built to stop. It stays manage-only until "
               "its own contract is frozen (aegis-finance/docs/"
               "CONTRACT_DRAFT_2026-09-06_REVISION_BOOK.md -- the OTHER repo; that file has "
               "never existed here and a reader who trusted this path got a 404 -- or a "
               "successor). The runbook's AAT_MANAGE_ONLY=1 line was inert: nothing reads that "
               "variable; Mandate.manage_only is the only switch that exists. "
               "RESOLVED 2026-09-07: contract.HORIZON_REMAP['hack2'] freezes horizon 5, "
               "min hold 2, no profit target, 8% stop -- so the book can no longer round-trip "
               "inside a session, which was the whole objection. Worst case, printed: "
               "8 names x 6% x 8% = -3.84% of equity, gross 48%."),
    "hack3": Mandate(
        role="hack3", tier="RISKY", label="SEASONALITY (Book F): same-calendar-month 11-20y tilt, k=10, shares only",
        question="Does Book F -- the only one of the four 2026-09 night books positive AT THE $10M FLOOR in the current era (+0.4328%/month vs its turnover-matched twin, t 3.1178, 419 blocks; 2017-24 +0.76%/month, t 2.30) -- pay on real fills at hack3's UNCHANGED construction (k=10 x 8.3%, 12% stop)?",
        # ENGINE SWITCH 2026-09-13 (chunk 13b, roadmap 11c "Third read"). The
        # sealed tracker artery is the fleet's biggest loser ($83,342 of
        # $100,000 on 09-13 against SPY -0.66% over the same window) and it has
        # no historical edge of its own. F replaces the RANKING and nothing
        # else: `profile`, `structure_kinds`, k, notional% and the stop are
        # untouched, so `contract.worst_case("hack3")` is byte-identical before
        # and after (pinned in `tests_smoke_engine_seasonality`).
        #
        # `tracker_portfolio` moves to SHADOW rather than being deleted: the
        # displaced engine keeps marking, so the SWITCH ITSELF is gradeable
        # instead of being an unmeasured before/after. A book is never shown
        # without its twin, and an engine swap is a book.
        brains=("seasonality_f",),
        shadow=("tracker_portfolio", "theme_basket", "murat_rule"),
        profile="basket", universe="engine_f",
        allow_maximum=True,
        rank_objective="median", structure_kinds=("long_shares",),
        caveat="ENGINE F, PRODUCT_EXPERIMENT, 2026-09-13. F is CONDITIONAL, not a claim: its two "
               "registered falsifiers passed (shift placebo +0.08%/month t 0.59; ex-January "
               "+0.38% t 2.44) and its primary did NOT clear the declared 0.65%/month effect "
               "size. The ranking is a FROZEN MONTHLY FILE exported by the research repo "
               "(`docs/seed/engines/F_seasonality_<YYYY-MM>.json`) and hash-verified in the "
               "order path; there is no engine file for a month, there is no book that month -- "
               "the loop fails CLOSED, so THIS BOOK NEEDS A REDEPLOY EVERY CALENDAR MONTH. "
               "Deviation from the receipt, printed on every forecast: the replay measured "
               "k=30 over the CRSP $10M band; this mandate holds the first k=10 of the same "
               "ranking over the venue's own tradable universe. Worst case UNCHANGED: "
               "10 x 10% = 100% gross at a 12% stop = -12% of equity. "
               "SUPERSEDES (kept because the question it answered is still open): APPROVED by Murat 2026-08-31 ('make sure all the other paper accounts are also wired "
               "and not empty ... up to the engine'): the thesis basket and murat_rule move to SHADOW "
               "with their adjudicated rules intact (dip cell -0.31%/5d t -2.35 still refused there). "
               "Shares only; sealed notional is a reduce-only ceiling; exact names from "
               "portfolios[hack3] in the sealed artifact. Worst case BOTH ways, 2026-08-31 seal: "
               "stop-based -6.64% AND all-names-gap-to-modelled-5%-downside ~-23.3% -- WORSE than "
               "hack4's gap case because breadth was bought with gross (83% vs 50%), a stated "
               "property of the balanced personality, not an accident."),
    "hack4": Mandate(
        role="hack4", tier="RISKY", label="TRACKER PROFIT-MAX: sealed upside x consensus, shares only",
        question="Does upside x consensus + catalyst selection (sealed pre-open, k=5 x 10%) create better P&L and opportunity recall than measured drift (hack2) and balanced breadth (hack3)?",
        brains=("tracker_portfolio",), shadow=("post_event_drift",), profile="maximum", universe="window",
        allow_maximum=True, rank_objective="median", structure_kinds=("long_shares",),
        extra_args=("--window-universe",),
        # ENTRY-TIMING TOURNAMENT (2026-09-02). Same sealed names, same sealed
        # weights as hack3; the only variable is WHEN the weight goes on. hack4
        # sends the whole book into the opening auction (`opg`, before 09:28 ET);
        # hack3 is the untouched 10:01 control. Delete this one line to disarm.
        env={"AAT_ENTRY_STYLE": "open_auction"},
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
        role="hack6", tier="RISKY", label="TRACKER DIVERSIFIED: sealed upside x consensus, k=15, shares only",
        question="Same sealed-tracker artery at k=15 x 6%: does diversification keep the upside family's edge with the smallest worst case of the three tracker books (hack4 k=5, hack3 k=10)?",
        brains=("tracker_portfolio",), shadow=("council_vector", "post_event_drift", "theme_basket"),
        profile="aggressive", universe="window_plus_themes",
        rank_objective="median", structure_kinds=("long_shares",),
        extra_args=("--window-universe", "--council"),
        # ENTRY-TIMING TOURNAMENT (2026-09-02): the STAGGERED arm. Half of each
        # sealed weight into the opening auction, the remainder completed by the
        # ordinary 10:01 pass (`entry_open.topup_headroom` admits the remainder
        # and only the remainder). Delete this one line to disarm.
        env={"AAT_ENTRY_STYLE": "staggered"},
        caveat="APPROVED by Murat 2026-08-31 ('make sure all the other paper accounts are also wired "
               "and not empty ... up to the engine'): the council blend moves to SHADOW (still fed by "
               "scripts.dislocation_scan --deep; a packet-less day now trades the sealed book instead "
               "of holding cash). Shares only; sealed notional is a reduce-only ceiling; exact names "
               "from portfolios[hack6] in the sealed artifact. Worst case BOTH ways, 2026-08-31 seal: "
               "stop-based -2.70% AND all-names-gap-to-modelled-5%-downside ~-13.0%."),
}

SAFE = tuple(r for r, m in FLEET.items() if m.tier == "SAFE")
RISKY = tuple(r for r, m in FLEET.items() if m.tier == "RISKY")

COMMON_ENV = {
    "AAT_TRADING_BASE": "https://paper-api.alpaca.markets",
    "AAT_DATA_BASE": "https://data.alpaca.markets",
    "AAT_OPTIONS_FEED": "indicative",
    "AAT_STOCK_FEED": "iex",
    "AAT_LEDGER_DIR": "/app/state",
    #: THE ALLOCATOR'S DAILY CUT, over the same artery as the sealed book
    #: (chunk 13c). `scripts/allocator_sync.py` falls back to
    #: AAT_PREDICTION_BOOK_BASE_URL when this is unset, so hack3/4/6 already
    #: read it -- but hack1 and hack5 never carried the seal variable, and the
    #: two books the allocator silently could not reach would have been exactly
    #: the two nobody would have thought to check. Named here so every deploy
    #: sets it and the fleet is uniform.
    "AAT_ALLOCATOR_BASE_URL": "http://seal-authority.railway.internal:8080",
    #: THE MANDATE END, and the fleet's dated liquidation (`config.deadline_utc`).
    #: Moved out from the hackathon deadline on 2026-09-05: judging closed on
    #: 09-04 and the books keep trading, so a 09-04 deadline would have been a
    #: 10:45 ET liquidation every morning for ever (`exits.deadline_liquidation_due`).
    #: A future contest sets this back to the contest date -- one variable.
    "AAT_MANDATE_END_UTC": "2027-12-31T15:00:00Z",
    #: Fallback only. `expiry_for(m)` decides per role: a share-only book has no
    #: option to expire and takes the mandate end; an options book takes the
    #: next monthly expiry at least two weeks out, DERIVED from today so it
    #: cannot go stale in the file the way a hardcoded date does.
    "AAT_LOOP_EXPIRY": "2027-12-31",
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


def engine_f_symbols(day: str | None = None) -> list[str]:
    """This calendar month's Book F selection, from the installed engine file.

    Raises `seasonality_f.EngineDeclined` when there is no VERIFIED engine file
    for the current month. That refusal is deliberate and it is the point of the
    design: a role whose universe cannot be stated must not be deployed with a
    universe the loop invents for it. `--deploy hack3` therefore fails loudly in
    the month before the export has been installed, which is exactly when it
    should fail -- rather than shipping and trading a window universe under a
    seasonality mandate's name.
    """
    from alpha.brains import seasonality_f as _f
    return _f.universe_symbols(day)


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
    if m.universe == "engine_f":
        # THE ENGINE'S OWN k=30 SELECTION, not the book's k=10 prefix: the loop
        # is asked about everything the month's ranking chose, so the receipt
        # records what was considered, and `seasonality_f` admits the prefix.
        #
        # This CANNOT raise the worst case, for the same reason
        # `themes_plus_rule` could not: hack3's bound is
        # `gross_cap('basket') x stop_fraction('basket')` and that expression
        # has no name-count term. More names divide the same gross.
        return engine_f_symbols()
    if m.universe == "themes_with_options":
        return theme_symbols(with_options_only=True)
    if m.universe == "window_plus_themes":
        # `--window-universe` supplies the printers on the loop side; the explicit
        # list here is ADDED to it (agent_loop unions --universe with the window).
        return theme_symbols()
    return list(m.fixed_symbols)


def gross_scale_for(m: Mandate) -> tuple[float | None, str]:
    """The ALLOCATOR's gross budget for this book, and where it came from.

    `None` for a role the allocator does not allocate to (`hack2` went to lane D
    on 2026-09-13). For an allocated role this RAISES `AllocatorUnavailable`
    when no allocator record exists at all -- which stops `--deploy` until
    `python -m scripts.allocator --anchor` and `--run` have been run, and that is
    the intended behaviour: a book whose budget nobody has stated must not
    deploy at 100% by default. A STALE record is used and SAID; only the total
    absence of one refuses.
    """
    from alpha import allocator as _a

    if m.role not in _a.ROLES:
        return None, f"{m.role} is not an allocated role (lane D); no budget flag emitted"
    b = _a.budget_for(m.role)
    return b["scale"], b["note"]


def loop_args(m: Mandate) -> list[str]:
    """The `scripts.agent_loop` flags this mandate prescribes (after --expiry/--live)."""
    args = ["--brains", ",".join(m.brains), "--profile", m.profile]
    scale, _why = gross_scale_for(m)
    if scale is not None:
        args += ["--gross-scale", f"{scale:.6f}"]
    # Before `extra_args` and before `--universe`: `--universe` takes nargs="*"
    # and must stay LAST, or argparse folds the following flag into the symbol
    # list on any Python that does not recognise it as an option string.
    if m.manage_only:
        args += ["--manage-only"]
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
    e["AAT_LOOP_EXPIRY"] = expiry_for(m)
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


def may_short(role: str | None) -> bool:
    """May this role open a short-side structure? Unknown role -> NO.

    An unknown role is refused rather than permitted: the fleet is six declared
    books, and a process whose `AAT_ACCOUNT_ROLE` does not name one of them has
    no mandate at all, let alone a mandate to be short.
    """
    m = FLEET.get((role or "").strip().lower())
    return bool(m and m.allow_short)


def expiry_for(m: Mandate, *, today: date | None = None) -> str:
    """The `--expiry` this mandate runs with (YYYY-MM-DD).

    A SHARE-ONLY book has no option to expire, and its horizon now comes from
    its strategy contract rather than from this flag (`alpha/contract.py`), so
    it takes the mandate end. An options book takes the next monthly expiry at
    least fourteen days out -- DERIVED from the date this is called on, because
    a literal expiry in a config file is correct until the day it passes and
    then silently wrong (CLAUDE.md, the fixture lesson).
    """
    if m.structure_kinds and all(k.endswith("_shares") for k in m.structure_kinds):
        return COMMON_ENV["AAT_LOOP_EXPIRY"]
    d = (today or date.today()) + timedelta(days=14)
    #: third Friday of d's month, or of the next month when that is already past
    for month_offset in (0, 1, 2):
        y, mo = divmod((d.month - 1) + month_offset, 12)
        first = date(d.year + y, mo + 1, 1)
        fridays = [first + timedelta(days=i) for i in range(31)
                   if (first + timedelta(days=i)).month == first.month
                   and (first + timedelta(days=i)).weekday() == 4]
        third = fridays[2]
        if third >= d:
            return third.isoformat()
    return d.isoformat()


def env_template() -> str:
    lines = ["# THE FLEET -- one key pair per role; paste each account's keys here",
             "# The $25 API credit: paste it under its provider's own name (AAT_DEEPSEEK_API_KEY /",
             "# AAT_NVIDIA_API_KEY / AAT_HF_TOKEN / AAT_OPENAI_API_KEY) and `scripts.council --probe` will find it.",
             "# Featherless.ai ($25 credit):", "AAT_FEATHERLESS_API_KEY=", ""]
    for r, m in FLEET.items():
        lines += [f"# {r:<10} {m.tier:<5} {m.label}", f"AAT_{r.upper()}_KEY_ID=", f"AAT_{r.upper()}_SECRET_KEY=", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# THE SEAL AUTHORITY (chunk 13c, 2026-09-13)
#
# It is NOT in `FLEET`: it has no mandate, no universe, no brains and places no
# orders, and putting it in the table would give it `--deploy all`, a volume and
# a `--gross-scale`. It is a seventh service with a variable set of its own.
# ---------------------------------------------------------------------------

SEAL_AUTHORITY_SERVICE = "seal-authority"

#: The role the authority already runs under, and whose key pair it already
#: carries as a LITERAL value (`docs/RUNBOOK_2026-09-08_REARM.md` C.0). It seals
#: and it does not trade. Its own pair is deliberately NOT re-emitted as a
#: reference below: overwriting a working literal with a template that might not
#: resolve would trade "the allocator cannot read four accounts" for "the whole
#: fleet gets no sealed book", which is a much worse day.
SEAL_AUTHORITY_ROLE = "hack3"


def seal_authority_key_references() -> dict[str, str]:
    """The allocated roles' key pairs, as Railway CROSS-SERVICE REFERENCES.

    Railway resolves `${{SERVICE.VAR}}` server-side inside one project
    (https://docs.railway.com/guides/variables, "Reference Variables"), so the
    authority's environment ends up holding all five pairs while no value is
    ever typed, echoed, logged or committed. The service name is used as-is,
    which here is `aat-loop-<role>` -- the service that already owns that pair.

    `SEAL_AUTHORITY_ROLE` is excluded: see the constant. Its pair is already on
    the service as a literal and this must not replace it.
    """
    from alpha import allocator as _a

    out: dict[str, str] = {}
    for role in _a.ROLES:
        if role == SEAL_AUTHORITY_ROLE:
            continue
        pre = f"AAT_{role.upper()}"
        for suffix in ("KEY_ID", "SECRET_KEY"):
            out[f"{pre}_{suffix}"] = f"${{{{aat-loop-{role}.{pre}_{suffix}}}}}"
    return out


def seal_authority_env() -> dict[str, str]:
    """Every variable `--deploy seal-authority` writes, and only those.

    NO `AAT_LOOP_*`, no `--gross-scale`, no mandate end: this service has no
    mandate, and `docs/RUNBOOK_2026-09-08_REARM.md` C.1(2) records that giving
    it loop variables is how a non-trading service inherits a trading one's
    stale deadline. NO volume either -- the authority rebuilds from the image on
    every boot on purpose, which is exactly why
    `scripts/allocator_venue.py` re-derives the curves instead of appending them.
    """
    env = {
        "AAT_TRADING_BASE": COMMON_ENV["AAT_TRADING_BASE"],
        "AAT_DATA_BASE": COMMON_ENV["AAT_DATA_BASE"],
        "AAT_STOCK_FEED": COMMON_ENV["AAT_STOCK_FEED"],
        "AAT_LEDGER_DIR": COMMON_ENV["AAT_LEDGER_DIR"],
        "AAT_ACCOUNT_ROLE": SEAL_AUTHORITY_ROLE,
    }
    env.update(seal_authority_key_references())
    return env


def seal_authority_commands() -> str:
    """What `--deploy seal-authority` does, as the lines a person could run."""
    svc = SEAL_AUTHORITY_SERVICE
    sets = " ".join(f'--set "{k}={v}"' for k, v in seal_authority_env().items())
    secrets = " ".join(f'--set "{k}=${k}"' for k in SECRETS)
    return "\n".join([
        f"railway service {svc}",
        f"# NO `railway volume add` -- the authority has no volume, by design.",
        f"railway variables --service {svc} --skip-deploys {sets} {secrets}",
        f"railway up --service {svc} -d",
        f"railway logs --service {svc}",
    ])


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
    """Every mandate as data, with its loop args -- or the REASON they are absent.

    `loop_args` reaches `universe_for`, and one universe kind (`engine_f`) can
    honestly refuse: a month with no installed engine file has no Book F
    universe. A refusal must not take down `--plan`, `--json` or an audit that
    only wanted to read the table, so it is recorded as a string on the row it
    belongs to instead of being raised out of a whole-fleet dump. The deploy
    path still fails: `scripts.fleet --deploy` calls `env_for` directly.
    """
    out = {}
    for r, m in FLEET.items():
        row = asdict(m)
        try:
            row["loop_args"] = loop_args(m)
        except Exception as exc:                                    # noqa: BLE001
            row["loop_args"] = None
            row["loop_args_refused"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        out[r] = row
    return out
