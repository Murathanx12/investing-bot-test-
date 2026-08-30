"""Tracker: the status rules, the cross-section, the portfolios and the bound.

Pure fixtures throughout -- no network, no venue, no clock. Everything here is
arithmetic over dicts, which is the reason `alpha/tracker.py` was split from
`scripts/tracker.py` in the first place.

WHAT THESE PIN, AND WHY EACH ONE EXISTS
=======================================
* MU is excluded. That is the whole point of the session: the rule fired on a
  name up ~700% because nothing asked about the twelve-month path.
* `past_winner` fires on EITHER limb. A sector-relative decile alone cannot
  catch a name whose whole sector ran; an absolute floor alone empties the list
  in a bull year.
* Unreadable is not failed. A name nobody covers must not look like a name the
  street rejected.
* The units of `days_to_catalyst` are CALENDAR DAYS. A silent 21-vs-30
  comparison would tighten the clause by ~30% and still print plausibly.
* The worst case takes the BINDING constraint. `n x notional x stop` and
  `gross_cap x stop` agree until they do not, and the day they stop agreeing is
  the day a book is twelve names deep.
"""

from __future__ import annotations

from alpha import tracker as T


# ------------------------------------------------------------------ arithmetic

def test_consensus_scale_is_five_is_best():
    """Five-is-best. The Refinitiv convention (1 = Strong Buy) under a >= 4.1
    bar would select exactly the names the street hates."""
    bullish = T.consensus_score(dict(strongBuy=10, buy=0, hold=0, sell=0, strongSell=0))
    bearish = T.consensus_score(dict(strongBuy=0, buy=0, hold=0, sell=0, strongSell=10))
    assert bullish[0] == 5.0 and bearish[0] == 1.0
    assert bullish[1] == 10
    assert T.consensus_score(None) is None
    assert T.consensus_score(dict(strongBuy=0, buy=0, hold=0, sell=0, strongSell=0)) is None


def test_coverage_bucket_starts_at_one_analyst():
    """A one-analyst name gets a bucket. That is the point of the tracker."""
    assert T.coverage_bucket(1) == "1-3"
    assert T.coverage_bucket(3) == "1-3"
    assert T.coverage_bucket(4) == "4-10"
    assert T.coverage_bucket(25) == "11-25"
    assert T.coverage_bucket(56) == "26+"
    # Zero coverage is NOT the thinnest bucket -- it is a different fact.
    assert T.coverage_bucket(0) is None
    assert T.coverage_bucket(None) is None


def test_bucket_rank_orders_thinnest_first():
    assert T.bucket_rank("1-3") < T.bucket_rank("4-10") < T.bucket_rank("26+")
    assert T.bucket_rank(None) is None


def test_upside_and_drawdown_refuse_nonpositive_inputs():
    assert abs(T.upside(15.0, 10.0) - 0.5) < 1e-12
    assert T.upside(None, 10.0) is None
    assert T.upside(15.0, 0.0) is None
    assert abs(T.drawdown_60d(8.0, 10.0) - (-0.2)) < 1e-12
    assert T.drawdown_60d(8.0, 0.0) is None


def test_price_stats_reports_what_it_could_not_compute():
    """A short history is a fact about a recent listing, not a reason to drop it."""
    short = [{"c": 10.0 + i, "h": 11.0 + i} for i in range(30)]
    st = T.price_stats(short)
    assert st["close"] == 39.0
    assert st["ret_12m"] is None            # fewer than 252 sessions: None, not a stub
    assert st["high_60d"] is not None
    assert st["sessions"] == 30
    assert T.price_stats([]) == {"sessions": 0}


def test_price_stats_emits_realised_vol_the_scorer_needs():
    bars = [{"c": 100.0 * (1.0 + 0.01 * ((-1) ** i)), "h": 120.0} for i in range(60)]
    assert T.price_stats(bars).get("realised_vol_20d") is not None


# -------------------------------------------------------------- the cross-section

def _sector(n, sector, base=0.0, step=0.02):
    return [dict(symbol=f"{sector[:3].upper()}{i}", close=10.0, high_60d=12.0,
                 ret_12m=base + step * i, sector=sector,
                 rec_counts=dict(strongBuy=1, buy=1, hold=1, sell=0, strongSell=0),
                 mean_target=11.0, days_to_catalyst=None) for i in range(n)]


def test_past_winner_fires_on_the_absolute_limb_when_the_whole_sector_ran():
    """The case a sector-relative decile ALONE would miss.

    Every name in the sector has doubled or more, so the +700% name is nowhere
    near its own sector's top decile -- and it is still exactly the name Murat
    objected to. The absolute limb is what catches it.
    """
    rows = _sector(30, "Semiconductors", base=1.0, step=0.30)   # +100% .. +970%
    mu = dict(symbol="MU", close=932.0, high_60d=1210.0, ret_12m=7.02,
              sector="Semiconductors",
              rec_counts=dict(strongBuy=18, buy=33, hold=4, sell=1, strongSell=0),
              mean_target=1513.0, days_to_catalyst=24)
    rows.append(mu)
    T.mark_past_winners(rows)
    got = [r for r in rows if r["symbol"] == "MU"][0]
    assert got["past_winner"] is True
    assert "100%" in got["past_winner_basis"]


def test_past_winner_fires_on_the_decile_limb_without_doubling():
    """The case an absolute floor ALONE would miss: a flat year, one leader."""
    rows = _sector(30, "Utilities", base=-0.10, step=0.01)      # -10% .. +19%
    T.mark_past_winners(rows)
    top = max(rows, key=lambda r: r["ret_12m"])
    assert top["past_winner"] is True
    assert "decile" in top["past_winner_basis"]
    assert all(r["ret_12m"] < T.PAST_WINNER_ABSOLUTE_RETURN for r in rows)


def test_thin_sector_falls_back_to_the_market_and_says_so():
    """Below MIN_SECTOR_N a sector's 'decile' is a small sample wearing one."""
    rows = _sector(40, "Biotechnology", base=0.0, step=0.05)
    rows += _sector(3, "Shipping", base=0.5, step=0.10)
    summary = T.mark_past_winners(rows)
    ship = [r for r in rows if r["sector"] == "Shipping"]
    assert all(r["past_winner_basis"].endswith("market decile")
               or "market" in r["past_winner_basis"] for r in ship)
    assert summary["judged_against_market"] == 3
    assert "Biotechnology" in summary["sectors_with_own_decile"]
    assert "Shipping" not in summary["sectors_with_own_decile"]


def test_no_history_is_not_a_past_winner_and_not_a_fresh_one():
    rows = _sector(25, "Biotechnology")
    rows.append(dict(symbol="IPO", close=10.0, high_60d=12.0, ret_12m=None,
                     sector="Biotechnology", rec_counts=None, mean_target=None,
                     days_to_catalyst=None))
    summary = T.mark_past_winners(rows)
    ipo = [r for r in rows if r["symbol"] == "IPO"][0]
    assert ipo["past_winner"] is None            # NOT False
    assert ipo["past_winner_basis"] == "NO_12M_HISTORY"
    assert summary["not_judged_no_history"] == 1


# --------------------------------------------------------------------- statuses

def _row(**kw):
    base = dict(symbol="X", close=10.0, upside=0.60, consensus=4.3, past_winner=False,
                days_to_catalyst=10, coverage=8, coverage_bucket="4-10", tradable=True)
    base.update(kw)
    return base


def test_strong_buy_needs_all_four_and_says_which_one_blocked_it():
    assert T.classify(_row()).status == "STRONG_BUY"
    # a catalyst too far away demotes, and names the clause
    v = T.classify(_row(days_to_catalyst=99))
    assert v.status != "STRONG_BUY"
    assert any("catalyst" in b for b in v.blocked_by)


def test_a_past_winner_cannot_be_a_candidate_however_good_the_numbers():
    """Murat's objection, as a test. MU's own shape: huge upside, top rating."""
    v = T.classify(_row(upside=0.62, consensus=4.21, past_winner=True,
                        days_to_catalyst=24))
    assert v.status not in T.CANDIDATE_STATUSES
    assert any("past winner" in b for b in v.blocked_by)


def test_unreadable_is_not_failed():
    """A name nobody covers must not look like a name the street rejected."""
    uncovered = T.classify(_row(consensus=None, coverage=0, coverage_bucket=None))
    disliked = T.classify(_row(consensus=1.9))
    assert uncovered.status == "WATCH"
    assert any("unreadable" in b for b in uncovered.blocked_by)
    assert disliked.status == "SELL"
    assert uncovered.status != disliked.status


def test_days_to_catalyst_is_compared_in_calendar_days_not_sessions():
    """21 sessions is 30 calendar days. Comparing the two silently tightens the
    clause by ~30% while still printing a plausible number."""
    assert T.CATALYST_MAX_CALENDAR_DAYS == 30
    # 24 calendar days is INSIDE 21 sessions and would fail a naive `<= 21`.
    assert T.classify(_row(days_to_catalyst=24)).status == "STRONG_BUY"
    assert T.classify(_row(days_to_catalyst=31)).status != "STRONG_BUY"


def test_hold_requires_having_been_on_the_list():
    """'Already on the list' is a statement about history; without `prev` it
    cannot be true, and a status function without memory cannot express it."""
    mid = _row(upside=0.20, consensus=4.3)          # between HOLD and BUY bars
    assert T.classify(mid).status == "WATCH"
    assert T.classify(mid, prev={"status": "BUY"}).status == "HOLD"


def test_sell_streak_accumulates_into_a_drop():
    r = _row(upside=0.02)
    v = T.classify(r, prev={"status": "SELL", "sell_streak": T.DROP_AFTER_SELL_SESSIONS - 1})
    assert v.status == "DROP"
    early = T.classify(r, prev={"status": "SELL", "sell_streak": 1})
    assert early.status == "SELL" and early.sell_streak == 2


def test_a_live_stop_forces_a_sell_whatever_the_rating_says():
    v = T.classify(_row(), stopped=True)
    assert v.status == "SELL"
    assert any("stop" in x for x in v.reasons)


def test_penny_and_untradable_names_drop_before_any_rating_is_read():
    assert T.classify(_row(close=0.40)).status == "DROP"
    assert T.classify(_row(tradable=False)).status == "DROP"


def test_watch_is_not_a_sell():
    """A name we never held has nothing to sell. Calling it SELL would fill the
    transition log with exits that never happened."""
    v = T.classify(_row(upside=0.20, consensus=4.3))
    assert v.status == "WATCH"
    assert v.sell_streak == 0


# ------------------------------------------------------------------ transitions

def test_transitions_record_only_changes_and_carry_their_causes():
    rows = [_row(symbol="A", status="BUY"), _row(symbol="B", status="BUY")]
    prev = {"A": {"status": "BUY"}, "B": {"status": "WATCH"}}
    got = T.transitions(rows, prev, day="2026-08-30")
    assert [t["symbol"] for t in got] == ["B"]
    assert got[0]["from"] == "WATCH" and got[0]["to"] == "BUY"
    # the numbers that caused it travel with the label -- a label whose inputs
    # were not kept cannot be learned from later
    assert "upside" in got[0] and "consensus" in got[0]


# ------------------------------------------------------------------- portfolios

def _candidates(n=30):
    rows = []
    for i in range(n):
        rows.append(dict(symbol=f"C{i}", status="BUY", sector=f"S{i % 4}",
                         upside=0.30 + 0.01 * i, consensus=4.0 + 0.01 * (i % 10),
                         coverage=12, coverage_bucket="11-25",
                         exp_return=0.001 * i, downside_5pct=-0.20,
                         confidence=0.5 + 0.01 * i, days_to_catalyst=10))
    return rows


def test_rank_value_sends_a_missing_input_last_not_to_zero():
    """A zero would let an unmeasured name outrank a measured negative one --
    that is how an absence gets promoted into a position."""
    missing = dict(exp_return=None, downside_5pct=None)
    negative = dict(exp_return=-0.05, downside_5pct=-0.10)
    assert T.rank_value(missing, "risk_adjusted") == float("-inf")
    assert T.rank_value(negative, "risk_adjusted") > T.rank_value(missing, "risk_adjusted")


def test_each_personality_selects_its_own_k_and_counts_what_it_dropped():
    rows = _candidates()
    for p in T.PERSONALITIES:
        port = T.build_portfolio(rows, p)
        assert port["n_selected"] <= p.k
        assert port["book"] == p.book
        assert isinstance(port["excluded_by_reason"], dict)


def test_the_balanced_book_respects_its_sector_cap():
    """One sector cannot take the whole book -- a one-sector portfolio
    CONCENTRATES that sector's factor rather than diversifying it."""
    rows = [dict(symbol=f"Z{i}", status="BUY", sector="OneSector",
                 upside=0.5, consensus=4.2, coverage=12, coverage_bucket="11-25",
                 exp_return=0.01, downside_5pct=-0.10, confidence=0.8,
                 days_to_catalyst=5) for i in range(20)]
    p = [x for x in T.PERSONALITIES if x.book == "hack3"][0]
    port = T.build_portfolio(rows, p)
    assert port["sector_notional"]["OneSector"] <= p.max_sector_share + 1e-9
    assert any("cap" in k for k in port["excluded_by_reason"])


def test_profit_max_requires_a_readable_catalyst():
    rows = _candidates()
    for r in rows:
        r["days_to_catalyst"] = None
    p = [x for x in T.PERSONALITIES if x.book == "hack4"][0]
    port = T.build_portfolio(rows, p)
    assert port["n_selected"] == 0
    assert port["excluded_by_reason"].get("no readable catalyst") == len(rows)


def test_preservation_excludes_the_thinnest_coverage_bucket():
    rows = _candidates()
    for r in rows:
        r["coverage_bucket"] = "1-3"
    p = [x for x in T.PERSONALITIES if x.book == "hack6"][0]
    assert T.build_portfolio(rows, p)["n_selected"] == 0


# ---------------------------------------------------------------- the worst case

def test_worst_case_takes_the_binding_constraint():
    """`n x notional x stop` and `gross_cap x stop` agree until they do not."""
    small = T.worst_case(n=5, notional_each=0.10, stop_fraction=0.08, gross_cap=1.50)
    assert small["binding"] == "name_count"
    assert abs(small["worst_case_fraction"] - (-0.04)) < 1e-9

    big = T.worst_case(n=12, notional_each=0.25, stop_fraction=0.08, gross_cap=1.00)
    assert big["binding"] == "gross_cap"
    # 300% requested, capped to 100%: -8%, NOT -24%.
    assert abs(big["worst_case_fraction"] - (-0.08)) < 1e-9


def test_the_three_personalities_stay_inside_the_nine_percent_bound():
    """Every book's bound, computed the same way it is enforced."""
    caps = {"hack3": 1.00, "hack4": 1.50, "hack6": 1.00}
    for p in T.PERSONALITIES:
        wc = T.worst_case(n=p.k, notional_each=p.max_notional,
                          stop_fraction=0.08, gross_cap=caps[p.book])
        assert wc["worst_case_fraction"] >= -0.09, (p.book, wc)


def test_a_wider_stop_on_uncapped_gross_is_a_bigger_loss():
    """The 29 Aug lesson, pinned: widening the stop without capping gross
    RAISES the worst case. -9% became -24% exactly this way."""
    tight = T.worst_case(n=12, notional_each=0.25, stop_fraction=0.03, gross_cap=3.00)
    wide = T.worst_case(n=12, notional_each=0.25, stop_fraction=0.08, gross_cap=3.00)
    assert wide["worst_case_fraction"] < tight["worst_case_fraction"]
    # and capping gross is what actually bounds it
    capped = T.worst_case(n=12, notional_each=0.25, stop_fraction=0.08, gross_cap=1.00)
    assert capped["worst_case_fraction"] > wide["worst_case_fraction"]


# ------------------------------------------------------------------- assembly

def test_build_rows_derives_every_computed_column():
    raw = [dict(symbol="A", close=10.0, high_60d=20.0, ret_12m=0.1, sector="S",
                rec_counts=dict(strongBuy=2, buy=2, hold=0, sell=0, strongSell=0),
                mean_target=16.0, days_to_catalyst=7)]
    rows = T.build_rows(raw)
    r = rows[0]
    assert abs(r["upside"] - 0.6) < 1e-9
    assert abs(r["drawdown_60d"] - (-0.5)) < 1e-9
    assert r["consensus"] == 4.5
    assert r["coverage"] == 4 and r["coverage_bucket"] == "4-10"
    assert "past_winner" in r


def test_summary_reports_flags_and_the_coverage_split():
    raw = [dict(symbol=f"A{i}", close=10.0, high_60d=12.0, ret_12m=0.05 * i, sector="S",
                rec_counts=dict(strongBuy=2, buy=2, hold=0, sell=0, strongSell=0),
                mean_target=14.0, days_to_catalyst=7) for i in range(25)]
    rows = T.build_rows(raw)
    hist = T.apply_status(rows)
    pw = T.mark_past_winners(rows)
    s = T.summary(rows, day="2026-08-30", hist=hist, pw=pw)
    assert s["n_symbols"] == 25
    assert s["schema"] == T.SCHEMA
    assert "flags" in s and "no_catalyst" in s["flags"]
    assert "coverage_split_by_status" in s
    assert s["thresholds"]["STRONG_BUY"]["catalyst_calendar_days"] == 30


def test_implausible_upside_is_flagged_and_never_dropped():
    """A 4x target is usually a stale split and occasionally the tail. Counting
    them is how we find out which; filtering them deletes the tail."""
    raw = [dict(symbol="SPLIT", close=1.0, high_60d=2.0, ret_12m=0.0, sector="S",
                rec_counts=dict(strongBuy=1, buy=1, hold=0, sell=0, strongSell=0),
                mean_target=90.0, days_to_catalyst=3)]
    rows = T.build_rows(raw)
    f = T.flags(rows)
    assert f["upside_implausible"]["n"] == 1
    assert "SPLIT" in f["upside_implausible"]["symbols"]
    assert len(rows) == 1                    # kept


def test_implausible_upside_is_barred_from_candidacy_measured_out_of_sample():
    """The 2026-08-30 IBES result, pinned as a rule.

    Uncapped, the BUY basket ran -5.48%/yr against the market at paired t -2.10
    over 143 months; capped here it runs +3.88%/yr at t +2.16. The band above
    the cap has a MEDIAN upside of 44x, which is a stale target on a different
    share basis, not an opinion.
    """
    ok = T.classify(_row(upside=2.0))                    # 200%: inside the cap
    bad = T.classify(_row(upside=45.0))                  # 4,500%: arithmetic, not a view
    assert ok.status == "STRONG_BUY"
    assert bad.status not in T.CANDIDATE_STATUSES
    assert any("share basis" in b for b in bad.blocked_by)


def test_the_cap_bars_candidacy_but_never_deletes_the_row():
    """Kept and counted. The next measurement needs them to find out whether
    any of that band was the tail after all."""
    raw = [dict(symbol="STALE", close=1.0, high_60d=2.0, ret_12m=0.0, sector="S",
                rec_counts=dict(strongBuy=5, buy=1, hold=0, sell=0, strongSell=0),
                mean_target=90.0, days_to_catalyst=3)]
    rows = T.build_rows(raw)
    T.apply_status(rows)
    assert len(rows) == 1
    assert rows[0]["upside"] > T.UPSIDE_IMPLAUSIBLE_AT
    assert rows[0]["status"] not in T.CANDIDATE_STATUSES
    assert T.flags(rows)["upside_implausible"]["n"] == 1


def test_clause_f_is_a_switch_and_the_flag_survives_it_being_off():
    """Flipping the exclusion must not stop `past_winner` being COMPUTED.

    The flag is evidence whether or not it is currently a gate: the out-of-
    sample test needs it recorded on every row in order to grade the clause at
    all, and a gate that deletes its own evidence can never be re-argued.
    """
    import importlib
    winner = _row(past_winner=True, past_winner_basis="ret_12m +702%")
    assert T.EXCLUDE_PAST_WINNERS is True
    assert T.classify(winner).status not in T.CANDIDATE_STATUSES

    T.EXCLUDE_PAST_WINNERS = False
    try:
        v = T.classify(winner)
        assert v.status == "STRONG_BUY", v.status
        assert not any("past winner" in b for b in v.blocked_by)
    finally:
        importlib.reload(T)
    assert T.EXCLUDE_PAST_WINNERS is True      # restored for every later test


# ---------------------------------------------------------------------------
# House convention: `run_tests.py` counts `  ok   <name>` lines, and a suite
# that prints none is reported as having asserted nothing. Keeping the tests as
# plain `test_*` functions makes each one runnable on its own; this block makes
# them VISIBLE to the runner. A suite that passes silently is indistinguishable
# from a suite that never ran, which is the same failure shape as a gate that
# cannot go green.
# ---------------------------------------------------------------------------

_fails: list[str] = []


def _run_all() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    print(f"\n-- TRACKER: status rules, cross-section, portfolios, worst case "
          f"({len(tests)} checks)")
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as exc:                                        # noqa: BLE001
            _fails.append(name)
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(_fails)} failures" + (": " + ", ".join(_fails) if _fails else ""))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
