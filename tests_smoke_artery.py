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


# The __main__ guard stays at the BOTTOM: `_run_all` collects from globals() at
# call time, so a test defined below it would never run while the suite still
# printed ALL PASS. That happened once already, on 2026-08-31, to five checks.
if __name__ == "__main__":
    raise SystemExit(_run_all())
