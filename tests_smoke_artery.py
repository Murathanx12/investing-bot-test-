"""THE ARTERY: the sealed tracker portfolio, and the three properties it must have.

On 2026-08-31 two days of work went into `build_portfolio` -- hack3's top 10,
hack4's top 5, hack6's top 15, their rankings, sector caps, coverage bands,
liquidity floors and downside limits -- and none of it could reach an order.
`scripts.reachability` had been printing `ORPHAN alpha.tracker` the whole time,
buried among 22 other orphans, so nobody read it.

The obvious repair -- "enable `murat_rule`" -- was WRONG, and would have been
believed. `murat_rule` trades per-name CLAIMS from `rule_predictions()`; the
seal never called `build_portfolio` at all. Flipping it on would have traded one
name (MU, on the published book) while the handoff said "hack4 is live".

So these are the three proofs, written as tests because a connection map in
prose drifts and a test does not:

  1. the runner can REACH the portfolio brain;
  2. the brain sees EXACTLY the holdings that were sealed, and nothing else;
  3. changing the tracker AFTER sealing cannot change today's live portfolio.

And one more that is really a fourth: the two selectors over the same seal stay
DISTINCT, so "the tracker portfolio is live" can never be true by accident.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

_fails: list[str] = []

#: A minimal sealed book carrying the artery block. Written by hand rather than
#: produced by `prediction_book.build()` so these tests stay offline and cannot
#: pass merely because today's real book happens to look right.
SEALED = {
    "schema": "prediction-book-3",
    "day": "2026-08-31",
    "sealed_at_utc": "2026-08-31T13:15:00+00:00",
    "content_sha256": "deadbeef" * 8,
    "portfolios": {
        "hack4": {
            "book": "hack4", "personality": "profit_max", "ranking": "upside_x_consensus",
            "k_target": 5, "n_selected": 2, "max_notional_each": 0.10,
            "rank_distinct_values": 2, "ranking_is_degenerate": False,
            "constraints": {"max_names_per_sector": 2, "min_dollar_volume": 1_000_000.0},
            "holdings": [
                {"symbol": "AAA", "notional": 0.10, "sector": "Tech", "rank_value": 9.9,
                 "exp_return": 0.06, "downside_5pct": -0.20, "confidence": 0.8,
                 "numbers_source": "rule"},
                {"symbol": "BBB", "notional": 0.10, "sector": "Mining", "rank_value": 7.1,
                 "exp_return": 0.04, "downside_5pct": -0.15, "confidence": 0.6,
                 "numbers_source": "rule"},
            ],
        },
        "hack6": {
            "book": "hack6", "personality": "preservation", "ranking": "upside_downside_ratio",
            "k_target": 15, "n_selected": 1, "max_notional_each": 0.06,
            "rank_distinct_values": 1, "ranking_is_degenerate": True,
            "constraints": {}, "holdings": [
                {"symbol": "ZZZ", "notional": 0.06, "sector": "Bio", "rank_value": 1.0,
                 "exp_return": 0.01, "downside_5pct": -0.10, "confidence": 0.9,
                 "numbers_source": "rule"}],
        },
    },
}


def _staged(book: dict = None, *, role: str | None = "hack4"):
    """Point the brain at a temp dir holding one sealed book. Returns the module."""
    import os
    from alpha.brains import tracker_portfolio as TP
    d = Path(tempfile.mkdtemp())
    (d / "2026-08-31.json").write_text(
        json.dumps(book if book is not None else SEALED), encoding="utf-8")
    TP.BOOKS = d
    TP.SEED_BOOKS = d
    if role is None:
        os.environ.pop("AAT_ACCOUNT_ROLE", None)
    else:
        os.environ["AAT_ACCOUNT_ROLE"] = role
    return TP


def check(name: str, cond: bool, why: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        _fails.append(name)
        print(f"  FAIL {name}  {why}")


# ---------------------------------------------------- PROOF 1: the runner reaches it

def test_proof_1_the_runner_can_reach_the_portfolio_brain():
    from alpha import brains
    check("proof1: registered under the name AAT_LOOP_BRAINS uses",
          "tracker_portfolio" in brains.BRAINS)
    check("proof1: not quarantined",
          "tracker_portfolio" not in getattr(brains, "QUARANTINED", {}))
    check("proof1: the registry entry is callable",
          callable(brains.BRAINS.get("tracker_portfolio")))
    # Reachability is "an entry point can call it", not "the module imports".
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "scripts.reachability"],
                         capture_output=True, text=True, timeout=180).stdout
    check("proof1: the audit no longer calls alpha.brains.tracker_portfolio an orphan",
          "ORPHAN  alpha.brains.tracker_portfolio" not in out,
          "the runner cannot reach it")


# ------------------------------------- PROOF 2: exactly the sealed names, nothing else

def test_proof_2_the_brain_trades_exactly_what_was_sealed():
    TP = _staged()
    got = TP.sealed_holdings("2026-08-31")
    check("proof2: the sealed names are the traded names",
          sorted(got["holdings"]) == ["AAA", "BBB"], str(sorted(got["holdings"])))
    check("proof2: the sealed WEIGHT travels with the name",
          got["holdings"]["AAA"]["notional"] == 0.10)
    check("proof2: the book's hash is carried onto the decision",
          got["content_sha256"] == SEALED["content_sha256"])

    f = TP.forecast(None, "AAA", 21 / (5 / 7))
    check("proof2: a sealed name gets a forecast", f.symbol == "AAA" and f.sd > 0)
    check("proof2: the forecast carries the sealed weight as evidence",
          f.evidence["sealed_notional"] == 0.10)
    check("proof2: it claims DIRECTION only, never the width", f.claim == "direction")
    # |downside_5pct| is a 5% NORMAL QUANTILE. Using it raw as the spread would
    # inflate every name's sd by 64% and hand the book wider distributions than
    # it claimed. sd = |dn| / 1.645 at full horizon.
    check("proof2: sd is recovered from the quantile, not used raw",
          abs(f.sd - 0.20 / 1.645) < 1e-9, f"sd={f.sd}")

    for absent in ("MU", "NVDA", "CCC"):
        try:
            TP.forecast(None, absent, 21 / (5 / 7))
            check(f"proof2: {absent} is refused (not in the sealed book)", False,
                  "it returned a forecast")
        except TP.PortfolioDeclined as exc:
            check(f"proof2: {absent} is refused (not in the sealed book)",
                  "not in" in str(exc))


# ------------------------- PROOF 3: a post-seal tracker change cannot move today's book

def test_proof_3_changing_the_tracker_after_sealing_changes_nothing_today():
    import inspect

    from alpha.brains import tracker_portfolio as TP
    # The structural guarantee: the only input is the sealed file. A brain that
    # could re-derive could drift from the artifact that was inspected, and then
    # the hash guarantees nothing.
    #
    # Tested on CODE, not on prose. The first version grepped raw source and
    # failed on the word `build_portfolio` inside this module's own docstring,
    # which is the module EXPLAINING that it does not call it. A test that
    # cannot tell a call from a comment reports the opposite of the truth.
    src = "\n".join(ln for ln in inspect.getsource(TP).splitlines()
                    if not ln.lstrip().startswith("#"))
    body = src.split('"""', 2)[-1]                 # drop the module docstring
    for token in ("import alpha.tracker", "from alpha import tracker",
                  "build_portfolio(", "PERSONALITIES"):
        check(f"proof3: the brain never reaches back to the tracker ({token!r})",
              token not in body, "found in executable code, not a comment")

    # Behavioural: mutate the tracker's live state, re-ask, get the same names.
    TP2 = _staged()
    before = sorted(TP2.sealed_holdings("2026-08-31")["holdings"])
    from alpha import tracker as T
    original = T.PERSONALITIES
    try:
        T.PERSONALITIES = ()          # the most violent possible tracker change
        after = sorted(TP2.sealed_holdings("2026-08-31")["holdings"])
    finally:
        T.PERSONALITIES = original
    check("proof3: emptying the tracker's personalities does not move today's book",
          before == after == ["AAA", "BBB"])


# ------------------------------------------- the refusals that keep it honest

def test_the_brain_refuses_rather_than_substituting_another_book():
    TP = _staged(role="hack3")            # a role with no sealed portfolio
    try:
        TP.sealed_holdings("2026-08-31")
        check("an unknown role is refused, not silently swapped", False, "it returned holdings")
    except TP.PortfolioDeclined as exc:
        check("an unknown role is refused, not silently swapped",
              "no portfolio for role" in str(exc))

    TP = _staged(role=None)
    try:
        TP.sealed_holdings("2026-08-31")
        check("an unset AAT_ACCOUNT_ROLE is refused, never defaulted", False, "it returned")
    except TP.PortfolioDeclined as exc:
        check("an unset AAT_ACCOUNT_ROLE is refused, never defaulted",
              "AAT_ACCOUNT_ROLE" in str(exc))


def test_a_degenerate_ranking_is_refused_at_the_door():
    """hack6 sorted on a constant on 2026-08-30 and produced 13 biotechs in dict
    order. The ranking is fixed, but the REFUSAL has to exist: a sort that did
    not sort must not become a position, whichever column does it next."""
    TP = _staged(role="hack6")
    try:
        TP.sealed_holdings("2026-08-31")
        check("a degenerate sealed ranking refuses to trade", False, "it returned holdings")
    except TP.PortfolioDeclined as exc:
        check("a degenerate sealed ranking refuses to trade", "DEGENERATE" in str(exc))


def test_an_old_schema_book_refuses_instead_of_trading_nothing_quietly():
    """A book sealed before the artery existed has no `portfolios`. Reading that
    as an empty portfolio would be a silent no-trade that looks like a decision."""
    TP = _staged({"schema": "prediction-book-2", "day": "2026-08-31",
                  "content_sha256": "x" * 64, "predictions": []})
    try:
        TP.sealed_holdings("2026-08-31")
        check("a pre-artery book refuses loudly", False, "it returned holdings")
    except TP.PortfolioDeclined as exc:
        check("a pre-artery book refuses loudly", "no `portfolios` block" in str(exc))


def test_the_two_selectors_over_one_seal_stay_distinct():
    """`murat_rule` trades CLAIMS; `tracker_portfolio` trades the PORTFOLIO.

    Conflating them is the exact error this session nearly shipped: a handoff
    that said "enable murat_rule and hack4 is live" when murat_rule would have
    traded the claimers instead. Enabling one must never enable the other.
    """
    from alpha import brains
    check("both selectors are registered", {"murat_rule", "tracker_portfolio"} <= set(brains.BRAINS))
    check("they are different callables",
          brains.BRAINS["murat_rule"] is not brains.BRAINS["tracker_portfolio"])
    import inspect

    from alpha.brains import murat_rule as MR
    mr = inspect.getsource(MR)
    check("murat_rule reads claims, not the portfolio block",
          "predictions" in mr and 'get("portfolios")' not in mr)


def test_the_seal_carries_the_portfolio_and_the_hash_covers_it():
    """The block must be INSIDE content_sha256, or 'the runner traded what I
    inspected' is unverifiable."""
    from scripts import prediction_book as PB
    body = dict(SEALED)
    h1 = PB._sha({k: v for k, v in body.items() if k != "content_sha256"})
    moved = json.loads(json.dumps({k: v for k, v in body.items() if k != "content_sha256"}))
    moved["portfolios"]["hack4"]["holdings"][0]["symbol"] = "CHANGED"
    h2 = PB._sha(moved)
    check("changing one sealed holding changes the book hash", h1 != h2)


def test_the_sealed_block_carries_exposure_gross_and_worst_case():
    """§1a (brief g): driver exposure, derived gross and the worst-case bound
    are INSIDE the sealed block, with the limits derived from the modules that
    enforce them -- not typed beside them."""
    from alpha import tracker as T
    from scripts import prediction_book as PB
    p = next(x for x in T.PERSONALITIES if x.book == "hack4")
    port = {
        "k_target": p.k, "n_selected": 2, "max_notional_each": p.max_notional,
        "rank_distinct_values": 2, "ranking_is_degenerate": False,
        "exclude_past_winners": p.exclude_past_winners,
        "requires_catalyst": p.requires_catalyst,
        "min_coverage_bucket": p.min_coverage_bucket,
        "max_coverage_bucket": p.max_coverage_bucket,
        "min_dollar_volume": p.min_dollar_volume,
        "max_sector_share": p.max_sector_share,
        "max_names_per_sector": 2, "max_downside": p.max_downside,
        "holdings": [
            {"symbol": "AAA", "notional": p.max_notional, "sector": "Tech",
             "rank_value": 9.9, "exp_return": 0.06, "downside_5pct": -0.20,
             "confidence": 0.8, "numbers_source": "rule"},
            {"symbol": "BBB", "notional": p.max_notional, "sector": "Mining",
             "rank_value": 7.1, "exp_return": 0.04, "downside_5pct": -0.15,
             "confidence": 0.6, "numbers_source": "rule"},
        ],
        "candidate_pool": 10, "eligible": 5, "excluded_by_reason": {},
        "sector_notional": {"Tech": p.max_notional, "Mining": p.max_notional},
    }
    blk = PB._portfolio_block(port, p, {"AAA": "AI_DATACENTER_CAPEX"})

    check("derived_gross is the sum of |notional|",
          abs(blk["derived_gross"] - 2 * p.max_notional) < 1e-9,
          f"got {blk['derived_gross']}")
    check("driver_exposure sums to derived_gross",
          abs(sum(blk["driver_exposure"].values()) - blk["derived_gross"]) < 1e-6,
          f"{blk['driver_exposure']} vs {blk['derived_gross']}")
    check("a symbol absent from the resolved map still lands on a driver",
          sum(1 for d in blk["driver_exposure"]) >= 1 and
          "AI_DATACENTER_CAPEX" in blk["driver_exposure"])

    wc = blk["worst_case"]
    check("worst case is determinable from the live limits", wc.get("determinable") is True,
          f"{wc}")
    if wc.get("determinable"):
        check("worst case names its binding constraint",
              wc["binding"] in ("gross_cap", "name_count"))
        check("gross is min(requested, cap) -- the 28 Aug arithmetic",
              abs(wc["gross"] - min(wc["requested_gross"], wc["gross_cap"])) < 1e-9)
        check("worst_case = -gross x stop, no other formula",
              abs(wc["worst_case_fraction"] - round(-wc["gross"] * wc["stop_fraction"], 6)) < 1e-9)
        check("the risk profile is named, not implied", bool(wc.get("profile")))


def test_worst_case_refuses_visibly_when_limits_are_unreadable():
    """A guard derives its inputs or refuses -- an unreadable limit must
    produce `determinable: False` WITH a reason, never a missing bound."""
    from alpha import tracker as T
    from scripts import prediction_book as PB

    class _Ghost:  # a book no fleet mandate knows
        book = "hack99"; name = "ghost"; k = 1; max_notional = 0.10
        rank = "x"; exclude_past_winners = False; requires_catalyst = False
        min_coverage_bucket = None; max_coverage_bucket = None
        min_dollar_volume = None; max_sector_share = None; max_downside = None

    port = {"k_target": 1, "n_selected": 0, "max_notional_each": 0.10,
            "rank_distinct_values": 0, "ranking_is_degenerate": False,
            "exclude_past_winners": False, "requires_catalyst": False,
            "min_coverage_bucket": None, "max_coverage_bucket": None,
            "min_dollar_volume": None, "max_sector_share": None,
            "max_names_per_sector": None, "max_downside": None,
            "holdings": [], "candidate_pool": 0, "eligible": 0,
            "excluded_by_reason": {}, "sector_notional": {}}
    blk = PB._portfolio_block(port, _Ghost, {})
    wc = blk["worst_case"]
    check("unreadable limits -> determinable False", wc.get("determinable") is False, f"{wc}")
    check("and the refusal carries its reason", bool(wc.get("reason")))


def test_source_versions_and_honest_authority():
    """§1a: the seal names the code that sealed it, and the authority text no
    longer denies what an enabled selector brain explicitly does."""
    from scripts import prediction_book as PB
    sv = PB._source_versions()
    for k in ("code_commit", "seal_script", "portfolio_module",
              "selector_brain", "rule_generator", "rule_registered"):
        check(f"source_versions carries {k}", k in sv, f"{sorted(sv)}")
    check("rule_generator matches the frozen contract",
          sv["rule_generator"] == "murat_rule_v1", f"{sv['rule_generator']}")
    check("code_commit is a string or an honest None",
          sv["code_commit"] is None or isinstance(sv["code_commit"], str))

    src = Path(PB.__file__).read_text(encoding="utf-8")
    check("the false 'nothing may influence an order' text is gone",
          "Nothing in this file may size, order or influence an order" not in src)
    check("the authority text names both selectors",
          src.count("NOT SELF-EXECUTING") >= 2)


def _run_all() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    print(f"\n-- ARTERY: sealed tracker portfolio -> runner ({len(tests)} test groups)")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                                        # noqa: BLE001
            _fails.append(name)
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(_fails)} failures" + (": " + ", ".join(_fails) if _fails else ""))
    return 1 if _fails else 0


def test_proof_4_the_sealed_WEIGHT_is_a_ceiling_not_a_suggestion():
    """The seal proved which NAMES trade. It did not constrain HOW MUCH.

    `sealed_notional` was written into the forecast's evidence and read by
    nothing -- one grep hit, the line that writes it -- while the runner sized
    from `sizing.PROFILES[risk_profile]`. hack4's profile is `maximum`, whose
    per_thesis is 0.15, against a sealed 0.10. The runner could put half again
    the book's weight into a name and every receipt would say the book was
    followed.
    """
    from alpha.brains import tracker_portfolio as TP

    cut, note = TP.clamp_to_sealed(0.15, {"sealed_notional": 0.10}, "long_shares")
    check("proof4: an oversized fraction is CUT to the sealed weight", cut == 0.10, str(cut))
    check("proof4: and says so", "CUT" in note and "ceiling" in note)

    same, note2 = TP.clamp_to_sealed(0.04, {"sealed_notional": 0.10}, "long_shares")
    check("proof4: a smaller fraction is left alone -- the clamp only reduces",
          same == 0.04, str(same))
    check("proof4: admission may still cut further", "within the sealed" in note2)

    untouched, note3 = TP.clamp_to_sealed(0.15, {}, "long_call")
    check("proof4: a non-sealed forecast is not touched by this clamp",
          untouched == 0.15 and note3 == "")

    # A 10% stock weight and 10% of equity spent on calls are not one risk.
    for kind in ("long_call", "long_put", "bull_call_spread", "long_straddle"):
        try:
            TP.clamp_to_sealed(0.10, {"sealed_notional": 0.10}, kind)
            check(f"proof4: {kind} is refused, not silently equated", False, "it returned")
        except TP.SealedWeightRefusal as exc:
            check(f"proof4: {kind} is refused, not silently equated",
                  "SHARES-ONLY" in str(exc))
    for kind in ("long_shares", "short_shares"):
        check(f"proof4: {kind} expresses a sealed weight", kind in TP.SHARE_KINDS)


def test_proof_5_the_runner_asks_about_the_sealed_names():
    """A name can be sealed, the brain ready, and the runner never ASK.

    The universe was built from a hardcoded list + window universe + candidates
    file, none of which reads the seal, so the book would prove which names
    trade and then trade none of them.

    EXECUTED, not grepped. The first version of this proof searched `main`'s
    source for a substring, which shows a string exists -- not that a sealed
    name reaches the universe. Proving a wiring gap by reading source is the
    same mistake one level up, so the injection was extracted into a callable
    and is exercised here with a staged book.
    """
    import scripts.run_pass as rp

    book = {"book": "hack4", "day": "2026-08-31", "content_sha256": "ab" * 32,
            "holdings": {"AAA": {}, "BBB": {}, "SPY": {}}}
    base = ["SPY", "QQQ", "IWM"]

    # brain OFF: the seal must not leak into an unrelated run
    got, refusal = rp.inject_sealed_portfolio(base, "post_event_drift",
                                              sealed_holdings=lambda: book)
    check("proof5: with the brain off the universe is untouched",
          got == base and refusal is None, str(got))

    # brain ON: every sealed name is now askable, and no duplicates
    got, refusal = rp.inject_sealed_portfolio(
        base, "theme_basket,tracker_portfolio", sealed_holdings=lambda: book)
    check("proof5: refusal is None on a readable book", refusal is None, str(refusal))
    for sym in ("AAA", "BBB"):
        check(f"proof5: sealed name {sym} is now in the universe", sym in got, str(got))
    check("proof5: a name already present is not duplicated",
          got.count("SPY") == 1, str(got))
    check("proof5: the pre-existing universe survives",
          all(s_ in got for s_ in base))

    # an unreadable book REFUSES rather than running the other brains over a
    # universe that is missing exactly the names the book chose
    def _boom():
        raise RuntimeError("no sealed book for 2026-08-31")
    got, refusal = rp.inject_sealed_portfolio(
        base, "tracker_portfolio", sealed_holdings=_boom)
    check("proof5: an unreadable sealed book returns a refusal",
          refusal is not None and "could not be read" in refusal, str(refusal))
    check("proof5: and does not silently extend the universe", got == base)

    # and main() must act on that refusal rather than continue
    import inspect
    check("proof5: main returns 2 on the refusal",
          "return 2" in inspect.getsource(rp.main))



# The __main__ guard stays at the BOTTOM: `_run_all` collects from globals() at
# call time, so a test defined below it would never run while the suite still
# printed ALL PASS. That happened once already, on 2026-08-31, to five checks.
if __name__ == "__main__":
    raise SystemExit(_run_all())
