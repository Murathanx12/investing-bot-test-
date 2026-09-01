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

#: Every portfolio fixture needs a dollar volume now that the books carry a
#: liquidity floor. An UNREADABLE volume is a refusal, not a pass, so a fixture
#: that omits it is correctly dropped -- these tests are about rankings and
#: caps, so they declare a comfortably liquid name and vary what they mean to.
LIQUID = 25_000_000.0


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
                days_to_catalyst=10, coverage=8, coverage_bucket="4-10", tradable=True,
                median_dollar_volume=LIQUID)
    base.update(kw)
    return base


def test_strong_buy_needs_all_four_and_says_which_one_blocked_it():
    assert T.classify(_row()).status == "STRONG_BUY"
    # a catalyst too far away demotes, and names the clause
    v = T.classify(_row(days_to_catalyst=99))
    assert v.status != "STRONG_BUY"
    assert any("catalyst" in b for b in v.blocked_by)


def test_a_past_winner_is_reported_by_the_status_and_barred_only_by_the_book():
    """Murat's objection, as a test -- at its new address.

    MU's own shape: huge upside, top rating, last year's winner. Until
    2026-08-30 (e) the STATUS refused it. It no longer does, because hack3 and
    hack4 now want different answers about that name and a universe label
    cannot hold two. The status reports the flag; the BOOK decides.
    """
    row = _row(upside=0.62, consensus=4.21, past_winner=True,
               past_winner_basis="ret_12m +702%", days_to_catalyst=24)
    v = T.classify(row)
    assert v.status == "STRONG_BUY", v.status
    # ... but it must still SAY so, or the flag has been silently dropped.
    assert any("past winner" in b for b in v.blocked_by)

    row["status"] = v.status
    row.update(exp_return=0.01, downside_5pct=-0.10, confidence=0.9,
               coverage_bucket="11-25", sector="TECH")
    hack3 = next(x for x in T.PERSONALITIES if x.book == "hack3")
    hack4 = next(x for x in T.PERSONALITIES if x.book == "hack4")
    assert hack3.exclude_past_winners is True
    assert hack4.exclude_past_winners is False

    held3 = T.build_portfolio([row], hack3)
    assert held3["n_selected"] == 0
    assert any("past winner" in r for r in held3["excluded_by_reason"])

    held4 = T.build_portfolio([row], hack4)
    assert [h["symbol"] for h in held4["holdings"]] == [row["symbol"]]
    assert held4["holdings"][0]["past_winner"] is True


def test_a_book_that_excludes_winners_refuses_an_unreadable_history():
    """`past_winner is None` is not a pass. A book that cannot verify the name
    is not last year's winner has not verified it -- and the two must not be
    collapsed, which is the standing `unreadable is not failed` rule read in
    the direction that costs money rather than the flattering one."""
    row = _row(upside=0.62, consensus=4.21, past_winner=None, days_to_catalyst=24)
    row["status"] = T.classify(row).status
    row.update(exp_return=0.01, downside_5pct=-0.10, confidence=0.9,
               coverage_bucket="11-25", sector="TECH")
    hack3 = next(x for x in T.PERSONALITIES if x.book == "hack3")
    port = T.build_portfolio([row], hack3)
    assert port["n_selected"] == 0
    assert any("unreadable" in r for r in port["excluded_by_reason"])


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
    """A healthy candidate pool. EIGHT sectors, not four: every book now caps
    names per sector, and a four-sector pool cannot fill hack6's fifteen at
    three per sector -- that is the cap working, so the fixture widens rather
    than the cap loosening. Every fifth name is last year's winner, so the
    clause-(f) A/B is exercised by the ordinary personality tests rather than
    only by the one test that is about it."""
    rows = []
    for i in range(n):
        rows.append(dict(symbol=f"C{i}", status="BUY", sector=f"S{i % 8}",
                         upside=0.30 + 0.01 * i, consensus=4.0 + 0.01 * (i % 10),
                         coverage=12, coverage_bucket="11-25",
                         coverage_source=T.COVERAGE_SOURCE_CALIBRATED,
                         past_winner=(i % 5 == 0),
                         past_winner_basis="ret_12m +120%" if i % 5 == 0 else None,
                         exp_return=0.001 * i, downside_5pct=-0.20,
                         median_dollar_volume=LIQUID,
                         confidence=0.5 + 0.01 * i, days_to_catalyst=10))
    return rows


def test_rank_value_sends_a_missing_input_last_not_to_zero():
    """A zero would let an unmeasured name outrank a measured negative one --
    that is how an absence gets promoted into a position."""
    missing = dict(exp_return=None, downside_5pct=None)
    negative = dict(exp_return=-0.05, downside_5pct=-0.10)
    assert T.rank_value(missing, "risk_adjusted_ratio") == float("-inf")
    assert (T.rank_value(negative, "risk_adjusted_ratio")
            > T.rank_value(missing, "risk_adjusted_ratio"))
    # A downside of exactly zero is an UNMEASURED downside, not a riskless
    # name: `er / 0` would rank the least-known name first, forever.
    assert T.rank_value(dict(exp_return=0.05, downside_5pct=0.0),
                        "risk_adjusted_ratio") == float("-inf")


def test_the_balanced_ranking_divides_because_subtracting_sorted_on_volatility():
    """The bug this ranking replaced, pinned so it cannot come back.

    Live rows carry `exp_return` ~0.0025 against `downside_5pct` ~0.25 -- two
    orders of magnitude apart. Under `er - |dn|` the difference was ~99% the
    downside term, so the "risk-adjusted" book ranked purely on LOW VOLATILITY
    and refilled itself with mega-caps. Here `mega` has the calmer bad case and
    `small` earns four times as much per unit of it; the ratio must prefer
    `small`, and the subtraction (asserted below) would not have.
    """
    mega = dict(exp_return=0.0025, downside_5pct=-0.12)
    small = dict(exp_return=0.0200, downside_5pct=-0.25)
    assert (T.rank_value(small, "risk_adjusted_ratio")
            > T.rank_value(mega, "risk_adjusted_ratio"))

    def subtraction(r):
        return r["exp_return"] - abs(r["downside_5pct"])

    assert subtraction(mega) > subtraction(small), "the old ranking preferred the mega-cap"


def test_the_balanced_book_caps_the_downside_it_will_rank_on():
    """A ratio is scale-free, which is the point of it and its one hole:
    +0.4% against -1% outranks +8% against -25%. `max_downside` is what stops
    "risk-adjusted" from silently meaning "tiny"."""
    hack3 = next(x for x in T.PERSONALITIES if x.book == "hack3")
    assert hack3.max_downside is not None
    row = dict(symbol="WIDE", status="BUY", sector="TECH", upside=0.40, consensus=4.2,
               coverage=12, coverage_bucket="11-25", past_winner=False,
               exp_return=0.30, downside_5pct=-(hack3.max_downside + 0.10),
               median_dollar_volume=LIQUID, confidence=0.9, days_to_catalyst=5)
    port = T.build_portfolio([row], hack3)
    assert port["n_selected"] == 0
    assert any("downside" in r for r in port["excluded_by_reason"]), port["excluded_by_reason"]


def test_each_personality_selects_its_own_k_and_counts_what_it_dropped():
    """`n_selected <= k` alone is an assertion that passes when NOTHING was
    selected, which is how a filter bug reads as a green test. Given a healthy
    pool of 30 candidates every book must actually fill."""
    rows = _candidates()
    for p in T.PERSONALITIES:
        port = T.build_portfolio(rows, p)
        assert port["n_selected"] == p.k, (p.book, port["n_selected"],
                                           port["excluded_by_reason"])
        assert port["book"] == p.book
        assert isinstance(port["excluded_by_reason"], dict)


def test_the_two_clause_f_arms_see_different_pools_from_the_same_universe():
    """The whole point of running both arms: one universe, two eligible sets.
    If these ever match, clause (f) has stopped doing anything and the
    experiment is quietly over."""
    rows = _candidates()
    hack3 = next(x for x in T.PERSONALITIES if x.book == "hack3")
    hack4 = next(x for x in T.PERSONALITIES if x.book == "hack4")
    on = T.build_portfolio(rows, hack3)
    off = T.build_portfolio(rows, hack4)
    assert on["candidate_pool"] == off["candidate_pool"]      # same universe
    assert on["eligible"] < off["eligible"]                   # different books
    assert not any(h["past_winner"] for h in on["holdings"])


def test_a_ranking_where_every_name_ties_is_reported_as_degenerate():
    """The DETECTOR, driven through whatever column hack6 currently ranks on.

    MEASURED 2026-08-30 on the live book: hack6 sorted on `confidence`, the rule
    publishes the same confidence for every non-claiming name, all 607 eligible
    names scored +0.9170, so "the top 15 by confidence" was the first 15 in dict
    order and came out as 13 biotechs. The ranking was replaced on 2026-08-31
    (see `test_no_book_ranks_on_a_column_that_cannot_rank`), but the DETECTOR is
    what makes the next such column visible, so it is pinned against the live
    personality rather than against the retired one.
    """
    p6 = next(x for x in T.PERSONALITIES if x.book == "hack6")
    # Sectors are spread because hack6 now caps at 3 names per sector; a
    # one-sector fixture would test the cap, not the ranking.
    rows = [dict(symbol=f"T{i}", status="BUY", sector=f"S{i % 8}", consensus=4.2,
                 coverage=12, coverage_bucket="11-25",
                 coverage_source=T.COVERAGE_SOURCE_CALIBRATED, past_winner=False,
                 upside=0.40, exp_return=0.01, downside_5pct=-0.10,
                 median_dollar_volume=LIQUID, confidence=0.9170,
                 days_to_catalyst=5) for i in range(24)]
    port = T.build_portfolio(rows, p6)
    assert port["n_selected"] == p6.k
    assert port["rank_distinct_values"] == 1
    assert port["ranking_is_degenerate"] is True

    # Vary the live ranking's inputs and the degeneracy must clear.
    for i, r in enumerate(rows):
        r["upside"] = 0.20 + 0.05 * i
    port2 = T.build_portfolio(rows, p6)
    assert port2["ranking_is_degenerate"] is False
    assert port2["rank_distinct_values"] == len(rows)


def test_no_book_ranks_on_a_column_that_cannot_rank():
    """`confidence` is `(clauses readable / 4) x min(1, date blocks / N)` -- a
    property of how much of the ROW could be read, not of the name. Every name
    whose four clauses were readable carries the SAME value, so sorting on it
    returns insertion order. No live book may rank on it again.

    This is the general form, not a hack6 special case: any ranking that is
    constant across a realistic pool is a no-op sort wearing a column name.
    """
    rows = [dict(symbol=f"D{i}", status="BUY", sector=f"S{i % 8}", consensus=4.2,
                 coverage=12, coverage_bucket="11-25",
                 coverage_source=T.COVERAGE_SOURCE_CALIBRATED, past_winner=False,
                 upside=0.30 + 0.02 * i, exp_return=0.001 * i,
                 downside_5pct=-0.10 - 0.002 * i, median_dollar_volume=LIQUID,
                 confidence=0.9170, days_to_catalyst=5) for i in range(24)]
    for p in T.PERSONALITIES:
        assert p.rank != "confidence", f"{p.book} ranks on a constant column"
        port = T.build_portfolio(rows, p)
        if port["eligible"] >= 2:
            assert not port["ranking_is_degenerate"], (
                f"{p.book}'s ranking {p.rank!r} is constant over a pool whose "
                f"upside, exp_return and downside all vary")


def test_preservation_ranks_on_reward_per_unit_of_its_own_bad_case():
    """hack6's replacement ranking, and the direction it must sort in.

    Two names, same upside, different downside: the calmer one ranks first.
    That is what `preservation` has to mean, and it is the property the
    retired `confidence` column could not express at all.
    """
    p6 = next(x for x in T.PERSONALITIES if x.book == "hack6")
    assert p6.rank == "upside_downside_ratio"
    calm = dict(symbol="CALM", status="BUY", sector="S0", consensus=4.2, coverage=12,
                coverage_bucket="11-25", coverage_source=T.COVERAGE_SOURCE_CALIBRATED,
                past_winner=False, upside=0.40, downside_5pct=-0.10,
                exp_return=0.01, median_dollar_volume=LIQUID, days_to_catalyst=5)
    wild = dict(calm, symbol="WILD", sector="S1", downside_5pct=-0.19)
    port = T.build_portfolio([wild, calm], p6)
    assert [h["symbol"] for h in port["holdings"]] == ["CALM", "WILD"]

    # A zero downside is an UNMEASURED downside, not a riskless name: ranking
    # it +inf would put the least-known name at the top of the book.
    assert T.rank_value(dict(upside=0.4, downside_5pct=0.0),
                        "upside_downside_ratio") == float("-inf")
    assert T.rank_value(dict(upside=None, downside_5pct=-0.1),
                        "upside_downside_ratio") == float("-inf")


def test_the_balanced_book_respects_its_sector_cap():
    """One sector cannot take the whole book -- a one-sector portfolio
    CONCENTRATES that sector's factor rather than diversifying it."""
    rows = [dict(symbol=f"Z{i}", status="BUY", sector="OneSector",
                 upside=0.5, consensus=4.2, coverage=12, coverage_bucket="11-25",
                 past_winner=False,
                 exp_return=0.01, downside_5pct=-0.10, confidence=0.8,
                 median_dollar_volume=LIQUID,
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


def test_clause_f_is_a_live_ab_across_the_books_not_one_setting():
    """The exclusion costs ~2.9pp/yr on eleven years and Murat asked for it by
    name. Neither of those settles it, so BOTH run: ON for hack3, OFF for
    hack4 and hack6. This test exists so a later tidy-up cannot quietly make
    the three books agree again and end the experiment without a result."""
    by_book = {p.book: p.exclude_past_winners for p in T.PERSONALITIES}
    assert by_book == {"hack3": True, "hack4": False, "hack6": False}, by_book
    assert len(set(by_book.values())) == 2, "both arms must be live"


def test_a_personality_must_declare_clause_f_rather_than_inherit_it():
    """A switch worth 2.9pp/yr must not be acquired by forgetting to type it."""
    try:
        T.Personality("hack9", "test", k=5, max_notional=0.05, rank="upside")
    except ValueError as e:
        assert "exclude_past_winners" in str(e)
    else:
        raise AssertionError("a personality without clause (f) was accepted")


def test_the_flag_is_computed_and_written_whether_or_not_a_book_gates_on_it():
    """A gate that deletes its own evidence can never be re-argued. hack4 does
    not exclude winners -- and must still record which of its holdings are."""
    winner = _row(upside=0.62, consensus=4.21, past_winner=True,
                  past_winner_basis="ret_12m +702%", days_to_catalyst=24)
    winner["status"] = T.classify(winner).status
    winner.update(exp_return=0.01, downside_5pct=-0.10, confidence=0.9,
                  coverage_bucket="11-25", sector="TECH")
    hack4 = next(x for x in T.PERSONALITIES if x.book == "hack4")
    h = T.build_portfolio([winner], hack4)["holdings"][0]
    assert h["past_winner"] is True


def test_coverage_comes_from_the_calibrated_source_when_it_is_there():
    """The analyst COUNT is not Finnhub's panel size.

    Measured 2026-08-30: Finnhub's recommendation panel ran a median 1.80x
    yfinance `numberOfAnalystOpinions` on a 56-name stratified sample, and on
    the two thinnest live examples it was 4x and 7x (SLDP 8 vs 2, KULR 7 vs 1).
    The buckets were calibrated on IBES `numrec`, which is the same quantity as
    the yfinance field and NOT the same quantity as the panel size.
    """
    raw = [dict(symbol="SLDP", close=3.0, mean_target=6.875, n_analysts_yf=2,
                rec_counts=dict(strongBuy=2, buy=5, hold=1, sell=0, strongSell=0))]
    row = T.build_rows(raw)[0]
    assert row["coverage"] == 2
    assert row["coverage_finnhub"] == 8
    assert row["coverage_source"] == T.COVERAGE_SOURCE_CALIBRATED
    assert row["coverage_bucket"] == "1-3"
    # the RATING still comes from the panel: an average over whoever is in it
    # is a fair rating even when the panel's SIZE is not the analyst count.
    assert row["consensus"] is not None


def test_coverage_falls_back_but_says_which_scale_it_is_on():
    raw = [dict(symbol="X", close=3.0, mean_target=6.0,
                rec_counts=dict(strongBuy=2, buy=5, hold=1, sell=0, strongSell=0))]
    row = T.build_rows(raw)[0]
    assert row["coverage"] == 8
    assert row["coverage_source"] == T.COVERAGE_SOURCE_UNCALIBRATED


def test_a_bucket_rule_refuses_a_count_on_the_wrong_scale():
    """hack6's mandate is PRESERVATION and it requires 4-10 analysts. On the
    Finnhub scale that admitted one- and two-analyst names -- the exact opposite
    of what the rule was written to do. A guard derives its input or refuses."""
    hack6 = next(x for x in T.PERSONALITIES if x.book == "hack6")
    assert hack6.min_coverage_bucket == "4-10"
    base = dict(symbol="Y", status="BUY", sector="TECH", upside=0.4, consensus=4.2,
                past_winner=False, coverage=8, coverage_bucket="4-10",
                exp_return=0.01, downside_5pct=-0.10, confidence=0.9,
                median_dollar_volume=LIQUID, days_to_catalyst=5)
    wrong = dict(base, coverage_source=T.COVERAGE_SOURCE_UNCALIBRATED)
    port = T.build_portfolio([wrong], hack6)
    assert port["n_selected"] == 0
    assert any("scale" in r for r in port["excluded_by_reason"]), port["excluded_by_reason"]

    right = dict(base, coverage_source=T.COVERAGE_SOURCE_CALIBRATED)
    assert T.build_portfolio([right], hack6)["n_selected"] == 1


# ---------------------------------------------------------------------------
# The daily diff
# ---------------------------------------------------------------------------

def _labelled_pair():
    """Yesterday and today, differing in every way the diff must separate."""
    prev = [
        dict(symbol="ENTER", status="WATCH", sector="TECH", upside=0.10, close=10.0),
        dict(symbol="LEAVE", status="BUY", sector="BIO", upside=0.40, close=5.0),
        dict(symbol="STAY", status="BUY", sector="BIO", upside=0.35, close=8.0),
        dict(symbol="GONE", status="BUY", sector="BANK", upside=0.50, close=7.0),
    ]
    today = [
        dict(symbol="ENTER", status="BUY", sector="TECH", upside=0.45, close=9.0),
        dict(symbol="LEAVE", status="WATCH", sector="BIO", upside=0.08, close=6.0),
        dict(symbol="STAY", status="BUY", sector="BIO", upside=0.36, close=8.1),
        dict(symbol="NEW", status="BUY", sector="BANK", upside=0.55, close=3.0),
    ]
    return today, prev


def test_the_diff_separates_a_downgrade_from_a_name_that_was_not_fetched():
    """A missing row and a downgraded row look identical in a histogram and
    mean opposite things: the first is a data gap, the second is a decision."""
    today, prev = _labelled_pair()
    d = T.build_diff(today, prev, day="2026-08-31", prev_day="2026-08-30")
    assert [r["symbol"] for r in d["entered"]] == ["ENTER"]
    assert [r["symbol"] for r in d["left"]] == ["LEAVE"]
    assert [r["symbol"] for r in d["arrived"]] == ["NEW"]
    assert [r["symbol"] for r in d["departed"]] == ["GONE"]
    # GONE was a candidate yesterday and is absent today -- it must NOT be
    # reported as having left the list, because nobody decided that.
    assert "GONE" not in {r["symbol"] for r in d["left"]}
    assert "NEW" not in {r["symbol"] for r in d["entered"]}


def test_the_diff_only_ranks_moves_for_names_present_both_days():
    """A new listing has no yesterday, so it cannot have moved. Letting it in
    would put the largest fake move at the top of the table every morning."""
    today, prev = _labelled_pair()
    d = T.build_diff(today, prev, day="2026-08-31", prev_day="2026-08-30")
    syms = {m["symbol"] for m in d["biggest_upside_moves"]}
    assert "NEW" not in syms and "GONE" not in syms
    top = d["biggest_upside_moves"][0]
    assert top["symbol"] == "ENTER"          # +35pp, the largest real move
    assert abs(top["delta"] - 0.35) < 1e-9


def test_the_diff_counts_candidates_per_sector_both_days():
    today, prev = _labelled_pair()
    d = T.build_diff(today, prev, day="2026-08-31", prev_day="2026-08-30")
    assert d["sectors"]["TECH"] == {"today": 1, "prev": 0, "delta": 1}
    assert d["sectors"]["BIO"] == {"today": 1, "prev": 2, "delta": -1}
    assert d["n_candidates"] == {"today": 3, "prev": 3}


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



# ------------------------------------------------- 2026-08-31: floors, caps, age

def test_every_book_declares_a_liquidity_floor_and_refuses_an_unreadable_volume():
    """A missing dollar volume is a REFUSAL, not a pass.

    `or 0` on this field would admit exactly the names the floor exists to keep
    out, which is the `net_breadth` collapse in a new place: an absence read as
    a value. Note what this floor does NOT do -- `universe.MIN_DOLLAR_VOLUME`
    already screens the tracker at $3m/day, so hack3's and hack4's $1m floors
    exclude nothing today. They are declared so each book states its own
    requirement rather than inheriting one silently.
    """
    for p in T.PERSONALITIES:
        assert p.min_dollar_volume is not None, f"{p.book} declares no liquidity floor"
    p6 = next(x for x in T.PERSONALITIES if x.book == "hack6")
    base = dict(symbol="THIN", status="BUY", sector="S0", consensus=4.2, coverage=12,
                coverage_bucket="11-25", coverage_source=T.COVERAGE_SOURCE_CALIBRATED,
                past_winner=False, upside=0.40, downside_5pct=-0.10, exp_return=0.01,
                days_to_catalyst=5)

    unreadable = dict(base)                       # no median_dollar_volume at all
    port = T.build_portfolio([unreadable], p6)
    assert port["n_selected"] == 0
    assert any("unreadable" in r for r in port["excluded_by_reason"]), \
        port["excluded_by_reason"]

    too_thin = dict(base, median_dollar_volume=p6.min_dollar_volume - 1.0)
    port = T.build_portfolio([too_thin], p6)
    assert port["n_selected"] == 0
    assert any("liquidity floor" in r for r in port["excluded_by_reason"]), \
        port["excluded_by_reason"]

    ok = dict(base, median_dollar_volume=p6.min_dollar_volume)
    assert T.build_portfolio([ok], p6)["n_selected"] == 1


def test_the_coverage_band_has_a_ceiling_as_well_as_a_floor():
    """A one-sided guard catches half the error. hack6 is a 4-25 book: without
    a ceiling it fills with 26+ mega-caps whenever they qualify, which is the
    mega-cap bias the tracker exists to remove walking back in through the
    coverage rule."""
    p6 = next(x for x in T.PERSONALITIES if x.book == "hack6")
    assert p6.min_coverage_bucket == "4-10" and p6.max_coverage_bucket == "11-25"
    base = dict(symbol="BIG", status="BUY", sector="S0", consensus=4.2,
                coverage_source=T.COVERAGE_SOURCE_CALIBRATED, past_winner=False,
                upside=0.40, downside_5pct=-0.10, exp_return=0.01,
                median_dollar_volume=LIQUID, days_to_catalyst=5)

    for bucket, n in (("26+", 44), ("1-3", 2)):
        port = T.build_portfolio([dict(base, coverage=n, coverage_bucket=bucket)], p6)
        assert port["n_selected"] == 0, f"{bucket} should not be admissible"
    inside = dict(base, coverage=12, coverage_bucket="11-25")
    assert T.build_portfolio([inside], p6)["n_selected"] == 1
    # The ceiling refuses an uncalibrated count for the same reason the floor
    # does: Finnhub's panel runs ~1.80x the scale these buckets were fitted on.
    wrong_scale = dict(inside, coverage_source=T.COVERAGE_SOURCE_UNCALIBRATED)
    assert T.build_portfolio([wrong_scale], p6)["n_selected"] == 0


def test_every_book_caps_its_sector_and_the_cap_is_a_name_count():
    """20 of 21 names falling together on 28 Aug was ONE bet wearing 20 tickers.
    `max_sector_share` is a notional because that is what the risk system reads,
    but it is CHOSEN as `names x max_notional` -- so the two must agree, or a
    later edit to `k` or `max_notional` silently changes the rule."""
    for p in T.PERSONALITIES:
        assert p.max_sector_share is not None, f"{p.book} has no sector cap"
        want = T.SECTOR_CAP_NAMES[p.book]
        got = int(p.max_sector_share / p.max_notional + 1e-9)
        assert got == want, (f"{p.book}: {p.max_sector_share} / {p.max_notional} "
                             f"admits {got} names, not the declared {want}")
        rows = [dict(symbol=f"{p.book}{i}", status="BUY", sector="OneSector",
                     consensus=4.2, coverage=8, coverage_bucket="4-10",
                     coverage_source=T.COVERAGE_SOURCE_CALIBRATED, past_winner=False,
                     upside=0.50 - 0.01 * i, downside_5pct=-0.10, exp_return=0.05,
                     median_dollar_volume=LIQUID, days_to_catalyst=5)
                for i in range(20)]
        port = T.build_portfolio(rows, p)
        assert port["n_selected"] == want, (
            f"{p.book} took {port['n_selected']} names from one sector, cap is {want}")
        assert port["sector_notional"]["OneSector"] <= p.max_sector_share + 1e-9


def test_stale_tracker_data_is_refused_and_the_age_is_in_sessions():
    """The lock had a staleness rule and the DATA did not.

    `latest_day()` returns the newest file on disk however old it is, so a
    refresh that dies on Sunday and again on Monday produces a Tuesday seal
    priced on Friday's closes with no warning. Counted in SESSIONS: a Monday
    reading Sunday's file is one session old and perfectly normal, and a
    calendar-day rule would refuse every Monday and be switched off in a week.
    """
    # Fri 2026-08-28 -> Mon 2026-08-31 is ONE session, not three calendar days.
    f = T.freshness("2026-08-28", asof="2026-08-31")
    assert f["determinable"] and f["age_sessions"] == 1 and f["stale"] is False
    # Sunday's file read on Monday: same session count as Friday's.
    assert T.freshness("2026-08-30", asof="2026-08-31")["age_sessions"] == 1
    # Two dead refreshes: Friday's file read on Wednesday is 3 sessions.
    late = T.freshness("2026-08-28", asof="2026-09-02")
    assert late["age_sessions"] == 3 and late["stale"] is True

    # A guard DERIVES its input or REFUSES -- it never reads an absence as 0.
    unknown = T.freshness(None, asof="2026-08-31")
    assert unknown["determinable"] is False
    assert "CANNOT DETERMINE" in unknown["reason"]

    T.assert_fresh("2026-08-28", asof="2026-08-31")          # does not raise
    for bad in ("2026-08-28", None):
        try:
            T.assert_fresh(bad, asof="2026-09-02" if bad else "2026-08-31")
        except T.StaleTrackerData:
            pass
        else:
            raise AssertionError(f"assert_fresh({bad!r}) should have refused")


def test_the_books_are_analysis_and_the_only_bridge_to_an_order_is_named():
    """WHAT THE BOOKS ACTUALLY REACH, pinned because a handoff got it wrong.

    The 2026-08-31 connection map read:

        | book -> portfolios (hack3/4/6) | ranked names | ... |
        | portfolios -> runner | orders  | admission, day latch | none known |

    "none known" was wrong: there is no such link. `build_portfolio` is called
    by `scripts/tracker.py --portfolios` (a print) and by these tests, and by
    nothing the runner can reach -- `scripts.reachability` says so out loud
    (`ORPHAN alpha.tracker`), buried among 22 other orphans, which is why a
    session read past it and shipped a fix believing it would trade Monday.

    The ONLY path from a tracker candidate to an order is:

        tracker --refresh
          -> prediction_book --seal --universe tracker   (claims per name)
          -> --publish  (docs/seed/predictions/<day>.json; /app/state is a
             VOLUME and shadows state/, so the seed dir is the delivery path)
          -> the `murat_rule` BRAIN, which reads that file
          -> only if that brain is in AAT_LOOP_BRAINS for an account.

    So enabling a book is an env-var decision on Railway, invisible from here.
    This test pins the half that IS visible: the personalities do not reach the
    runner on their own, and `murat_rule` is the named bridge. If someone wires
    the books directly later, this test should be REWRITTEN, not deleted -- the
    point is that the answer is stated somewhere a reader will hit.
    """
    import inspect
    from alpha import brains

    # The bridge exists and is registered under the name the loop asks for.
    assert "murat_rule" in brains.BRAINS, \
        "the only sealed-book -> order bridge is no longer registered"
    assert "murat_rule" not in brains.QUARANTINED, (
        "the bridge is quarantined -- it cannot trade even if an account enables it")

    # The bridge reads a SEALED BOOK, not the personalities.
    from alpha.brains import murat_rule as bridge
    src = inspect.getsource(bridge)
    assert "SEED_BOOKS" in src and "predictions" in src
    assert "build_portfolio" not in src, \
        "the bridge now calls build_portfolio -- rewrite this test and the map"

    # The personalities are not reachable from the runner's entry point.
    import scripts.agent_loop as loop
    loop_src = inspect.getsource(loop)
    for token in ("build_portfolio", "PERSONALITIES", "alpha.tracker", "alpha import tracker"):
        assert token not in loop_src, (
            f"agent_loop now references {token!r}: the books may have been wired "
            f"to the runner. Update the connection map and this test.")



def test_a_long_book_cannot_hold_a_name_its_own_numbers_call_negative():
    """2026-09-01 coherence rule. On 08-31 hack6 sealed 15/15 negative-exp
    names and correctly entered NOTHING (the brain forecasts each name from
    the same sealed numbers, so exp_return<=0 -> direction down -> a long-only
    book refuses, every time). The book now agrees with its own calibration at
    SEAL time instead of arguing with it at the broker."""
    hack4 = next(x for x in T.PERSONALITIES if x.book == "hack4")

    def eligible_row(sym, exp):
        r = _row(symbol=sym, days_to_catalyst=10)
        r["status"] = T.classify(r).status
        r.update(exp_return=exp, downside_5pct=-0.10, confidence=0.9, sector="TECH")
        return r

    good, bad, none_ = eligible_row("GOOD", 0.02), eligible_row("BAD", -0.01), eligible_row("NONE", None)
    none_.pop("exp_return")
    port = T.build_portfolio([good, bad, none_], hack4)
    assert [h["symbol"] for h in port["holdings"]] == ["GOOD"], port["holdings"]
    reasons = port["excluded_by_reason"]
    assert any("exp_return not positive" in r for r in reasons), reasons
    assert any("exp_return unreadable" in r for r in reasons), reasons
    # exactly zero is not positive either -- a coin flip is not a long thesis
    port2 = T.build_portfolio([eligible_row("ZERO", 0.0)], hack4)
    assert port2["n_selected"] == 0


# The __main__ guard MUST stay at the very bottom. `_run_all` collects from
# globals() at call time, so any test defined BELOW the guard is invisible to it:
# on 2026-08-31 five new checks sat under it and run_tests.py counted 49 while
# pytest counted 54, reporting ALL PASS over five checks that never executed.
# A check that did not run is not a check that passed.
if __name__ == "__main__":
    raise SystemExit(_run_all())
