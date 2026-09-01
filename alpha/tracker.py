"""TRACKER -- a whole-market analyst watchlist that accumulates its own data.

WHAT MURAT ASKED FOR, AND WHY IT IS ALSO A FIX
==============================================
    "Have a big list of stocks we keep track of. The list adapts: we add
     potential winners and drop losers, like a firm's strong-buy / hold / sell.
     Pull every strong-buy from analysts -- even names with ONE review, not just
     mega-caps with dozens -- see which have the most % upside and what the
     consensus is, add our own findings, and build multiple portfolios."

The sealed book on 2026-08-30 read 151 names and claimed exactly one: MU, a
name up ~700% in twelve months. It fired because "down 23% from the 60-day
high" says nothing at all about the twelve-month path, and because the 151-name
panel is mostly mega-caps carrying dozens of analysts. **The universe produced
that answer, not the rule** -- and the 50.8% base rate measured beside it is a
property of the same universe.

So this module is two things at once. It is the watchlist Murat described, and
it is the standing answer to `feedback-a-hand-picked-universe-is-survivorship-
bias`: a list rebuilt from the WHOLE market every day, whose every past day is
kept, is a point-in-time screen that we own rather than one we curated after
the fact.

WHAT IS PURE HERE AND WHAT IS NOT
=================================
Everything in this file is pure: it takes rows and returns rows. `scripts/
tracker.py` does the fetching (Alpaca assets + bars, Finnhub recommendation
counts, yfinance targets) and the writing. The split is the same one
`analyst_targets.py` uses, and it exists so the status rules can be tested on
fixtures without a network and replayed over any past day's file.

THE VINTAGE PROBLEM, STATED RATHER THAN HIDDEN
==============================================
`yfinance`'s consensus target carries NO vintage. We cannot know whether a mean
target was set yesterday or in March. `scripts/analyst_panel.py` warns about
exactly this and it is the reason the vendor consensus was refused for months.

It is admissible HERE, and only here, for one reason: we stamp `observed_at`
ourselves at capture and the value may be used strictly AFTER that stamp. A
forward-recorded panel is honest about what it is -- we know when WE learned
it, which is the only bound a live decision needs. What it is NOT is a
backtestable history: a target read today tells us nothing about what the
street was quoting in 2019. That is why the out-of-sample test of these same
rules runs on IBES (point-in-time, licensed) in the Aegis repo, and never on
this file. Two sources, two jobs, never merged into one column.

WHAT THIS MODULE REFUSES TO DO
==============================
* **No sizing, no stops, no caps.** It ranks and labels. `worst_case` computes
  a bound and asserts nothing about whether it may be taken.
* **No status from an unreadable input.** A name with no readable catalyst is
  not a name whose catalyst failed. `STRONG_BUY` asserts a dated catalyst
  exists, so absence of one blocks it -- and the row says which clause blocked
  it rather than silently scoring it lower. (`feedback-two-clocks-need-two-
  bounds`, and the broken-gate rule before it.)
* **No magnitude filter on upside that is not MEASURED.** A target 3x the price
  is exactly the tail the rule is hunting, so no ratio is dropped on grounds of
  looking implausible -- the `rev_breadth` lesson and the `abs(delta)` lesson
  after it. One bar exists and it was earned out of sample rather than assumed:
  above `UPSIDE_IMPLAUSIBLE_AT` the band is not optimism but a target quoted on
  a different share basis (median 44x), and buying it cost -26.47%/yr against
  the market at t -4.71 over 143 months. Those names are still measured, still
  written, still counted -- barred from CANDIDACY only.
"""

from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

SCHEMA = "tracker-1"

# --------------------------------------------------------------------------
# Frozen thresholds. These are the contract; changing one is a new version.
# --------------------------------------------------------------------------

#: Status bars, from `NEXT_SESSION_2026-08-30d_OPUS.md` §3b.
STRONG_BUY_UPSIDE = 0.50
STRONG_BUY_CONSENSUS = 4.1
BUY_UPSIDE = 0.30
BUY_CONSENSUS = 4.0
HOLD_UPSIDE = 0.15
SELL_UPSIDE = 0.10
SELL_CONSENSUS = 3.5
CATALYST_MAX_SESSIONS = 21
#: THE UNITS. `days_to_catalyst` arrives from `features.daily_features` in
#: CALENDAR days -- it is `(effective_at.date() - day).days`, straight
#: subtraction over a date, with no trading calendar anywhere in it. Murat's
#: clause is written in SESSIONS. Comparing the two directly would silently
#: apply a ~30% tighter window than the rule says, and a units error that still
#: produces plausible numbers is the one that survives review: the loops once
#: called a chain cheap on 96.4% of 6,070 decisions on exactly that kind of
#: mistake. 21 sessions x 7/5 = 29.4 -> 30 calendar days, matching
#: `murat_rule.CATALYST_MAX_CALENDAR_DAYS` so the two generators cannot drift.
CATALYST_MAX_CALENDAR_DAYS = 30

#: Sessions at SELL before a name leaves the list entirely.
DROP_AFTER_SELL_SESSIONS = 5
#: Hard exclusions, checked before any rating is read.
MIN_PRICE_USD = 1.0

#: `past_winner` -- Murat's MU objection, as a number.
#:
#: TWO conditions, joined by OR, because either one alone is wrong:
#:
#:   * the SECTOR DECILE alone fails in a year when a whole sector runs. If
#:     every semiconductor name doubled, MU at +700% could still sit outside
#:     its sector's top decile and the flag would not fire -- while the thing
#:     Murat objected to (the run already happened) is plainly true.
#:   * the ABSOLUTE FLOOR alone fails in a year when the whole market doubles,
#:     where it would flag everything and the list would empty.
#:
#: So a name is a past winner if it is in the top decile of its sector OR it
#: has doubled in twelve months. The row records WHICH fired, because a flag
#: whose reason is not recorded cannot be argued with later.
PAST_WINNER_SECTOR_DECILE = 0.90
PAST_WINNER_ABSOLUTE_RETURN = 1.00

#: DOES CLAUSE (f) EARN ITS PLACE? MEASURED 2026-08-30, AND THE ANSWER IS NO.
#:
#: On IBES + CRSP 2013-2024, 143 months, both arms carrying the SAME upside cap
#: so that clause (f) is the ONLY difference between them
#: (`scripts/tracker_ibes_backtest.py`, aegis-finance):
#:
#:     basket                          wealth   excess/yr   paired t   names/mo
#:     BUY, excluding past winners      4.107      +3.88%       2.16        416
#:     BUY, NOT excluding them          5.587      +6.74%       3.00        530
#:     past winners ONLY               18.174     +18.60%       3.31         56
#:
#: Excluding past winners COSTS about 2.9 percentage points a year, and the
#: names it excludes are the strongest sub-basket in the entire study. This is
#: twelve-month momentum, the most replicated effect in the cross-section, and
#: it does NOT contradict this project's Holm-surviving finding that SHORT-
#: horizon winner-chasing is an anti-signal: that was measured at five days,
#: this is a twelve-month formation with a one-month hold.
#:
#: SO WHY IS IT STILL True? Because Murat asked for it by name, and because his
#: objection to the MU pick was CORRECT about the cause and wrong about the
#: cure. MU was selected by a 151-name mega-cap panel; the fix for that is the
#: tracker's whole-market universe and the upside cap, both of which are now
#: live and both of which measure positive. Clause (f) is a separate claim and
#: it measures negative.
#:
#: MURAT'S DECISION, 2026-08-30 (e): clause (f) is ON for hack3 and OFF for
#: hack4 and hack6. Both arms run live and the books say which was right.
#:
#: SO THE SWITCH IS NO LONGER HERE. It is `Personality.exclude_past_winners`,
#: because a universe gate cannot express two answers at once: with the gate
#: here, a past winner became WATCH for everybody and hack4 could never see a
#: name hack3 had already demoted. A tracker STATUS is a property of the NAME
#: -- what the analysts say about it -- and must not silently carry one book's
#: taste. `past_winner` and `past_winner_basis` are computed and written on
#: every row either way, so the flag is evidence whether or not it is a gate,
#: and every book that declines a name for it COUNTS the decline by reason.
#:
#: That is the bottleneck rule applied to an idea cap: two selectors running
#: side by side, not one weight being argued about.

#: Below this many rated names, a sector's own decile is not a decile -- it is
#: a small sample wearing one. Those names fall back to the market-wide decile
#: and the row says so in `past_winner_basis`.
MIN_SECTOR_N = 20

#: WHICH ANALYST COUNT THE BUCKETS ARE ON. Measured 2026-08-30 (e), and it is
#: not a detail.
#:
#: The IBES result that made thin coverage a live hypothesis bucketed on
#: `numrec` -- the count of brokers with a current recommendation. Finnhub's
#: `stock/recommendation` panel is a DIFFERENT quantity: it aggregates more
#: sources, and on a 56-name stratified sample its count ran a MEDIAN 1.80x
#: yfinance's `numberOfAnalystOpinions`, which is the field that means the same
#: thing IBES means. Two live examples, both currently on the candidate list:
#:
#:     SLDP   Finnhub 8   yfinance 2
#:     KULR   Finnhub 7   yfinance 1
#:
#: The consequences were exact and expensive. The live tracker had ZERO names
#: in the 1-3 bucket -- the best bucket in the eleven-year test -- and its
#: minimum was 5, not because the universe lacks thin names but because the
#: variable could not express them. And hack6, whose whole mandate is
#: PRESERVATION and which requires `4-10`, was on Finnhub's scale selecting
#: names covered by one or two analysts while believing it had required four.
#:
#: So: `coverage` is yfinance `numberOfAnalystOpinions` when it is readable,
#: and every row records `coverage_source`. A row bucketed on the Finnhub
#: count is USABLE but NOT COMPARABLE to the backtest, and any book whose rule
#: names a bucket must refuse it rather than read it on the wrong scale.
COVERAGE_SOURCE_CALIBRATED = "yfinance_numberOfAnalystOpinions"
COVERAGE_SOURCE_UNCALIBRATED = "finnhub_recommendation_panel"
COVERAGE_FINNHUB_OVER_YF_MEDIAN = 1.80      # n=56, stratified, 2026-08-30

#: Coverage buckets. The whole point of the tracker is that a 4-analyst biotech
#: gets a row at all, so the thinnest bucket starts at ONE.
COVERAGE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1-3", 1, 3), ("4-10", 4, 10), ("11-25", 11, 25), ("26+", 26, 10 ** 9),
)
_BUCKET_ORDER = [b[0] for b in COVERAGE_BUCKETS]

#: An upside ratio above this is kept, FLAGGED, and barred from CANDIDACY.
#:
#: It was a flag only until 2026-08-30, when the out-of-sample test measured
#: what it was hiding. On IBES + CRSP, 2013-2024, 434,295 name-months, monthly
#: rebalance, 10bps a side, graded as a PAIRED monthly spread against the
#: equal-weighted market (`scripts/tracker_ibes_backtest.py` in aegis-finance):
#:
#:     upside band          name-months   excess/yr   paired t
#:     +30% to +50%              47,357      +3.59%       2.02
#:     +50% to +100%             39,534      +5.98%       2.22
#:     +100% to +200%            20,301     +11.68%       2.41
#:     +200% to +400%            10,270     +17.19%       2.45
#:     +400% and above           54,232     -26.47%      -4.71   <-- median 44x
#:
#: The screen is monotone and strongly POSITIVE up to +400%, and then inverts
#: violently. The last band is not a set of very optimistic analysts: its median
#: upside is 4,424%, which is not a forecast anybody made. It is a stale target
#: read against a price on a different share basis -- a reverse split leaves the
#: old target a fraction of the new price and the ratio becomes arithmetic
#: rather than opinion.
#:
#: Uncapped, the BUY basket returns -5.48%/yr against the market at t -2.10.
#: Capped here, the SAME rule returns +3.88%/yr at t +2.16, terminal wealth
#: 4.107 against the market's 2.863. One line, and it is the difference between
#: a screen that significantly loses and one that significantly wins.
#:
#: THE LEVEL WAS NOT FITTED TO THAT DATA. 4.00 was already in this file, as a
#: flag, before the panel was built -- and the sensitivity is a plateau, not a
#: knife edge: every cap from 1.5x to 10x gives +2.9% to +4.2%/yr at t 1.8-2.3,
#: and only removing the cap entirely (<100x) collapses it to -1.31%. Positive
#: in all three eras (+4.66 / +2.81 / +4.11 %/yr), never pooled.
#:
#: The name still gets a row, a status and its numbers. It is barred from
#: CANDIDACY, not deleted -- counting these is how the next measurement finds
#: out whether any of them were the tail after all.
UPSIDE_IMPLAUSIBLE_AT = 4.00

#: WATCH is not in Murat's five and is not a sixth grade -- it is the ABSENCE
#: of one. A name we have never held, which today clears no buy bar, has
#: nothing to sell and nothing to drop; calling that "SELL" would fill the
#: transition log with exits that never happened and would teach a future
#: model that ~3,000 names are sold every morning. It is measured daily and is
#: free to qualify tomorrow.
STATUSES = ("STRONG_BUY", "BUY", "HOLD", "SELL", "DROP", "WATCH")
#: Statuses that put a name on the candidate list.
CANDIDATE_STATUSES = ("STRONG_BUY", "BUY")


# --------------------------------------------------------------------------
# Freshness -- the LOCK had a staleness rule and the DATA did not
# --------------------------------------------------------------------------
#
# The nightly refresh takes a lock with a staleness rule, so a dead refresh
# cannot wedge the next one. Nothing checked the age of what it LEFT BEHIND.
# `prediction_book.tracker_rows` calls `latest_day()`, which returns the newest
# file on disk regardless of when it was written -- so a refresh that dies on
# Sunday and again on Monday produces a Tuesday seal priced on Friday's closes,
# reported with Tuesday's date and no warning anywhere. That is the house
# failure mode exactly: green, silent, and wrong.
#
# Counted in SESSIONS, not calendar days. Monday reading Sunday's file is one
# session old and perfectly normal; a calendar rule would refuse every Monday
# and be switched off within a week.

#: Sessions of age at which the seal and the portfolio builder REFUSE.
MAX_TRACKER_AGE_SESSIONS = 2

#: US market holidays inside any plausible window. Labor Day 2026 is 7 Sep,
#: after the contest, so the set is empty -- STATED rather than assumed,
#: because an empty holiday set is a claim about the calendar, not a default.
TRACKER_HOLIDAYS: frozenset[str] = frozenset()


class StaleTrackerData(RuntimeError):
    """Raised when the tracker file being priced on is too old to use."""


def _sessions_between(a: date, b: date) -> int:
    """Trading sessions strictly after `a`, up to and including `b`."""
    if b <= a:
        return 0
    n, cur = 0, a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.isoformat() not in TRACKER_HOLIDAYS:
            n += 1
    return n


def freshness(day: str | None, *, asof: str | None = None) -> dict:
    """How old the tracker file for `day` is, in sessions. Never raises.

    Returns `determinable: False` rather than a number when either date is
    missing or unparseable. A guard DERIVES its input or REFUSES -- it does not
    fall back to 0, which would read as "fresh" precisely when the pipeline is
    broken enough to have lost the date.
    """
    if asof is None:
        from alpha.exits import session_day     # lazy: keeps this module light
        asof = session_day()
    try:
        d0 = date.fromisoformat(str(day))
        d1 = date.fromisoformat(str(asof))
    except (TypeError, ValueError):
        return {"determinable": False, "day": day, "asof": asof,
                "max_age_sessions": MAX_TRACKER_AGE_SESSIONS,
                "reason": f"CANNOT DETERMINE: day={day!r} asof={asof!r} is not a date"}
    age = _sessions_between(d0, d1)
    return {"determinable": True, "day": str(day), "asof": str(asof),
            "age_sessions": age, "max_age_sessions": MAX_TRACKER_AGE_SESSIONS,
            "stale": age > MAX_TRACKER_AGE_SESSIONS,
            "reason": (f"tracker data for {day} is {age} session(s) old as of {asof}"
                       f" (limit {MAX_TRACKER_AGE_SESSIONS})")}


def assert_fresh(day: str | None, *, asof: str | None = None,
                 what: str = "tracker data") -> dict:
    """`freshness`, but REFUSES. Raises `StaleTrackerData` when stale.

    An undeterminable age is also a refusal here: the seal is about to commit
    real orders to whatever this file says, and "I could not tell how old it
    is" is not a licence to proceed.
    """
    f = freshness(day, asof=asof)
    if not f["determinable"]:
        raise StaleTrackerData(f"REFUSED: {what} -- {f['reason']}")
    if f["stale"]:
        raise StaleTrackerData(
            f"REFUSED: {what} is {f['age_sessions']} sessions old "
            f"({f['day']}, as of {f['asof']}); the limit is "
            f"{MAX_TRACKER_AGE_SESSIONS}. The nightly refresh has probably died "
            f"-- run `python -m scripts.tracker --refresh` and re-seal. Pricing "
            f"Monday's book on stale closes is worse than not trading.")
    return f


# --------------------------------------------------------------------------
# Per-name arithmetic
# --------------------------------------------------------------------------

def consensus_score(counts: dict | None) -> tuple[float, int] | None:
    """(rating on a 1-5 scale where FIVE IS BEST, coverage), or None.

    Five-is-best matches Murat's ">= 4.1 / 5 (Buy-Strong Buy)". The Refinitiv /
    Yahoo convention puts 1 at Strong Buy; using it under a ">= 4.1" bar would
    select precisely the names the street hates, so the scale and the bar are
    always stated together. Delegates to `analyst_targets` so there is one
    implementation, not two that can drift.
    """
    if not counts:
        return None
    from alpha import analyst_targets
    return analyst_targets.consensus_rating(counts)


def coverage_bucket(n_analysts: int | None) -> str | None:
    """'1-3' / '4-10' / '11-25' / '26+'. None when nobody covers the name.

    Zero coverage and thin coverage are different facts and must not collapse
    into one bucket -- that is the `net_breadth` lesson, where a formula-derived
    bound quietly deleted the informative tail.
    """
    if not n_analysts or n_analysts < 1:
        return None
    for name, lo, hi in COVERAGE_BUCKETS:
        if lo <= n_analysts <= hi:
            return name
    return None


def bucket_rank(bucket: str | None) -> int | None:
    """Ordinal of a coverage bucket, thinnest first. For '<=' comparisons."""
    return _BUCKET_ORDER.index(bucket) if bucket in _BUCKET_ORDER else None


def upside(mean_target: float | None, close: float | None) -> float | None:
    """mean_target / close - 1. None when either leg is missing or non-positive."""
    if not mean_target or not close or mean_target <= 0 or close <= 0:
        return None
    return mean_target / close - 1.0


def drawdown_60d(close: float | None, high_60d: float | None) -> float | None:
    if not close or not high_60d or high_60d <= 0:
        return None
    return close / high_60d - 1.0


def price_stats(bars: list[dict]) -> dict:
    """close, high_60d, ret_12m, realised_vol_20d, sessions -- from a daily bar list.

    Returns whatever it can and names what it could not. A short history is a
    fact about a recent listing, not a reason to drop the name: an IPO from
    March has no `ret_12m` and can still be a perfectly good BUY.
    """
    closes = [float(b["c"]) for b in bars if b.get("c")]
    highs = [float(b.get("h") or b["c"]) for b in bars if b.get("c")]
    out: dict = {"sessions": len(closes)}
    if not closes:
        return out
    out["close"] = closes[-1]
    out["high_60d"] = max(highs[-60:]) if highs else None
    # 252 sessions is the twelve-month convention used everywhere else in this
    # repo. A name with fewer sessions gets None, never a scaled-up stub.
    out["ret_12m"] = (closes[-1] / closes[-252] - 1.0) if len(closes) >= 252 else None
    # Annualised 20-session realised vol. The book's scorer turns this into the
    # magnitude it is willing to claim, so a row without it gets `exp_return`
    # None rather than a magnitude borrowed from some other name -- which is why
    # it is computed here from the same bars, not fetched again later.
    if len(closes) >= 21:
        rets = [math.log(closes[i] / closes[i - 1])
                for i in range(len(closes) - 20, len(closes)) if closes[i - 1] > 0]
        if len(rets) >= 10:
            out["realised_vol_20d"] = st.pstdev(rets) * math.sqrt(252)
    return out


# --------------------------------------------------------------------------
# Cross-sectional: past_winner
# --------------------------------------------------------------------------

def _decile_cut(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 2:
        return None
    idx = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return vals[idx]


def mark_past_winners(rows: list[dict]) -> dict:
    """Set `past_winner` and `past_winner_basis` on every row, in place.

    Cross-sectional and computed per day -- a full-sample quantile would be
    lookahead, and this is the same rule the corpus screens already follow.

    Returns a summary naming how many names were judged against their own
    sector, how many fell back to the market, and how many could not be judged
    at all (no twelve-month history). A name that cannot be judged is NOT a
    past winner and NOT silently a fresh one: `past_winner` is None and the
    status rules treat None as "not established".
    """
    by_sector: dict[str, list[float]] = {}
    market: list[float] = []
    for r in rows:
        ret = r.get("ret_12m")
        if ret is None:
            continue
        market.append(ret)
        by_sector.setdefault(r.get("sector") or "_UNKNOWN", []).append(ret)

    market_cut = _decile_cut(market, PAST_WINNER_SECTOR_DECILE)
    sector_cut = {s: _decile_cut(v, PAST_WINNER_SECTOR_DECILE)
                  for s, v in by_sector.items() if len(v) >= MIN_SECTOR_N}

    n_sector = n_market = n_unknown = 0
    for r in rows:
        ret = r.get("ret_12m")
        if ret is None:
            r["past_winner"] = None
            r["past_winner_basis"] = "NO_12M_HISTORY"
            n_unknown += 1
            continue
        sec = r.get("sector") or "_UNKNOWN"
        cut, basis = (sector_cut[sec], f"sector:{sec}") if sec in sector_cut else (market_cut, "market")
        if sec in sector_cut:
            n_sector += 1
        else:
            n_market += 1
        by_decile = cut is not None and ret >= cut
        by_absolute = ret >= PAST_WINNER_ABSOLUTE_RETURN
        r["past_winner"] = bool(by_decile or by_absolute)
        reasons = []
        if by_decile:
            reasons.append(f"top decile of {basis} (cut {cut:+.1%})")
        if by_absolute:
            reasons.append(f"ret_12m {ret:+.1%} >= +{PAST_WINNER_ABSOLUTE_RETURN:.0%}")
        r["past_winner_basis"] = "; ".join(reasons) if reasons else f"below {basis} decile"
    return {"judged_against_sector": n_sector, "judged_against_market": n_market,
            "not_judged_no_history": n_unknown,
            "sectors_with_own_decile": sorted(sector_cut),
            "market_decile_cut": market_cut,
            "min_sector_n": MIN_SECTOR_N}


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------

@dataclass
class StatusVerdict:
    status: str
    reasons: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    sell_streak: int = 0

    def as_dict(self) -> dict:
        return {"status": self.status, "status_reasons": self.reasons,
                "status_blocked_by": self.blocked_by, "sell_streak": self.sell_streak}


def classify(row: dict, *, prev: dict | None = None, stopped: bool = False) -> StatusVerdict:
    """The frozen status rule. One row in, one label out.

    ```
    STRONG_BUY  upside >= 0.50 and consensus >= 4.1 and not past_winner
                and a dated catalyst inside 21 sessions
    BUY         upside >= 0.30 and consensus >= 4.0 and not past_winner
    HOLD        already on the list and still upside >= 0.15
    SELL        upside < 0.10, or consensus < 3.5, or a stop hit on any book
    DROP        5 sessions at SELL, or delisted / < $1 / not tradable
    ```

    `prev` carries yesterday's row so HOLD ("already on the list") and DROP
    ("five sessions at SELL") can be evaluated at all -- both are statements
    about history, and a status function without memory can express neither.

    UNREADABLE IS NOT FAILED. A missing consensus does not fail the consensus
    bar; it blocks every status that ASSERTS one and lands the name at HOLD or
    below with the clause named in `blocked_by`. Collapsing "nobody covers it"
    into "the street dislikes it" would make an uncovered biotech identical to
    a name analysts have actually rejected, which is the distinction the whole
    tracker exists to preserve.
    """
    prev_status = (prev or {}).get("status")
    prev_streak = int((prev or {}).get("sell_streak") or 0)
    on_list = prev_status in CANDIDATE_STATUSES or prev_status == "HOLD"

    up = row.get("upside")
    cons = row.get("consensus")
    past = row.get("past_winner")
    cat = row.get("days_to_catalyst")
    price = row.get("close")
    tradable = row.get("tradable", True)

    reasons: list[str] = []
    blocked: list[str] = []

    # -- hard exclusions, before any rating is read ------------------------
    if price is not None and price < MIN_PRICE_USD:
        return StatusVerdict("DROP", [f"price ${price:.2f} < ${MIN_PRICE_USD:.2f}"], [], prev_streak)
    if not tradable:
        return StatusVerdict("DROP", ["not tradable at the venue"], [], prev_streak)

    # -- SELL, checked before the buy bars: it is an exit, not a ranking ----
    sell_now = False
    if stopped:
        sell_now = True
        reasons.append("a stop was hit on a live book")
    if up is not None and up < SELL_UPSIDE:
        sell_now = True
        reasons.append(f"upside {up:+.1%} < {SELL_UPSIDE:+.0%}")
    if cons is not None and cons < SELL_CONSENSUS:
        sell_now = True
        reasons.append(f"consensus {cons:.2f} < {SELL_CONSENSUS}")
    if sell_now:
        streak = prev_streak + 1
        if streak >= DROP_AFTER_SELL_SESSIONS:
            return StatusVerdict(
                "DROP", reasons + [f"{streak} sessions at SELL"], [], streak)
        return StatusVerdict("SELL", reasons, [], streak)

    # -- the buy bars ------------------------------------------------------
    # The implausibility bar comes FIRST among them: measured out of sample, an
    # upside above this is not an optimistic analyst but a stale target read
    # across a corporate action, and buying that band cost -26.47%/yr against
    # the market at t -4.71. See UPSIDE_IMPLAUSIBLE_AT for the whole table.
    if up is not None and up >= UPSIDE_IMPLAUSIBLE_AT:
        return StatusVerdict("WATCH", [], [
            f"upside {up:+.0%} >= {UPSIDE_IMPLAUSIBLE_AT:.0%}: not a forecast, almost always a "
            "target quoted on a different share basis. Barred from candidacy, kept and counted."
        ], 0)
    if up is None:
        blocked.append("upside unreadable (no target or no price)")
    if cons is None:
        blocked.append("consensus unreadable (no analyst coverage)")
    if past is None:
        blocked.append("past_winner not established (no 12-month history)")

    # CLAUSE (f) IS NOT ASSERTED HERE ANY MORE. It is a per-book preference
    # (`Personality.exclude_past_winners`), because the status is a property of
    # the NAME and two books now want two different answers about it. What the
    # status does instead is REPORT the flag, so a reader of this verdict can
    # see it without the book's opinion baked in.
    if past is True:
        blocked.append(f"past winner -- {row.get('past_winner_basis') or 'flagged'} "
                       "(reported, not barred: clause (f) is per book)")
    can_strong = (up is not None and up >= STRONG_BUY_UPSIDE
                  and cons is not None and cons >= STRONG_BUY_CONSENSUS)
    if can_strong:
        if cat is None:
            blocked.append(f"no dated catalyst readable (STRONG_BUY asserts one inside "
                           f"{CATALYST_MAX_SESSIONS} sessions / "
                           f"{CATALYST_MAX_CALENDAR_DAYS} calendar days)")
        elif cat > CATALYST_MAX_CALENDAR_DAYS:
            blocked.append(f"next catalyst in {cat} calendar days > "
                           f"{CATALYST_MAX_CALENDAR_DAYS}")
        else:
            return StatusVerdict("STRONG_BUY", [
                f"upside {up:+.1%} >= {STRONG_BUY_UPSIDE:+.0%}",
                f"consensus {cons:.2f} >= {STRONG_BUY_CONSENSUS}",
                f"past winner: {past}",
                f"catalyst in {cat} calendar days"], blocked, 0)

    if (up is not None and up >= BUY_UPSIDE and cons is not None
            and cons >= BUY_CONSENSUS):
        return StatusVerdict("BUY", [
            f"upside {up:+.1%} >= {BUY_UPSIDE:+.0%}",
            f"consensus {cons:.2f} >= {BUY_CONSENSUS}",
            f"past winner: {past}"], blocked, 0)

    if on_list and up is not None and up >= HOLD_UPSIDE:
        return StatusVerdict("HOLD", [f"on the list, upside {up:+.1%} >= {HOLD_UPSIDE:+.0%}"],
                             blocked, 0)

    # Not on the list and not clearing a buy bar: it simply is not a candidate.
    # That is NOT a SELL -- there is nothing to sell -- and it is not a DROP,
    # because a name we never held cannot be dropped from a book. It stays
    # WATCH: measured every day, holding nothing, free to qualify tomorrow.
    return StatusVerdict("WATCH", [], blocked, 0)


def apply_status(rows: list[dict], *, prev_by_symbol: dict[str, dict] | None = None,
                 stopped_symbols: set[str] | None = None) -> dict:
    """Label every row. Returns a histogram of the labels."""
    prev_by_symbol = prev_by_symbol or {}
    stopped_symbols = stopped_symbols or set()
    hist: dict[str, int] = {}
    for r in rows:
        v = classify(r, prev=prev_by_symbol.get(r["symbol"]),
                     stopped=r["symbol"] in stopped_symbols)
        r.update(v.as_dict())
        hist[v.status] = hist.get(v.status, 0) + 1
    return hist


def transitions(rows: list[dict], prev_by_symbol: dict[str, dict], *, day: str) -> list[dict]:
    """Every status CHANGE, as an append-only event.

    This log is the "add potential winners, drop losers" history Murat asked
    for, and it is the label source a network would later be trained on. A
    transition is recorded with the numbers that caused it, because a label
    whose inputs were not kept cannot be learned from.
    """
    out = []
    for r in rows:
        was = (prev_by_symbol.get(r["symbol"]) or {}).get("status")
        now = r.get("status")
        if was == now:
            continue
        out.append({
            "day": day, "symbol": r["symbol"], "from": was, "to": now,
            "upside": r.get("upside"), "consensus": r.get("consensus"),
            "coverage": r.get("coverage"), "coverage_bucket": r.get("coverage_bucket"),
            "ret_12m": r.get("ret_12m"), "past_winner": r.get("past_winner"),
            "days_to_catalyst": r.get("days_to_catalyst"),
            "sector": r.get("sector"), "close": r.get("close"),
            "reasons": r.get("status_reasons"), "blocked_by": r.get("status_blocked_by"),
        })
    return out


def build_diff(today: list[dict], prev: list[dict], *, day: str,
               prev_day: str) -> dict:
    """Yesterday to today, as the premarket digest reads it.

    THE DISTINCTION THIS EXISTS TO MAKE. A name that vanished from the file and
    a name that lost its rating look identical in a status histogram, and they
    mean opposite things: the first is a data gap, the second is a decision.
    So churn (`arrived` / `departed`) is separated from grade changes
    (`entered` / `left`), and a name is only ever counted in one of them.

    Both sides must already be LABELLED -- pass rows through `apply_status`
    first. Re-deriving the previous day's status here would silently grade
    yesterday with today's rules and turn every rule change into a fake
    market event.
    """
    t_by = {r["symbol"]: r for r in today}
    p_by = {r["symbol"]: r for r in prev}
    both = set(t_by) & set(p_by)

    arrived = sorted(set(t_by) - set(p_by))
    departed = sorted(set(p_by) - set(t_by))

    def is_cand(r: dict | None) -> bool:
        return bool(r) and r.get("status") in CANDIDATE_STATUSES

    entered, left, regraded = [], [], []
    for sym in sorted(both):
        a, b = p_by[sym], t_by[sym]
        was, now = a.get("status"), b.get("status")
        if was == now:
            continue
        row = {"symbol": sym, "from": was, "to": now,
               "sector": b.get("sector"), "upside": b.get("upside"),
               "consensus": b.get("consensus"), "coverage": b.get("coverage"),
               "coverage_bucket": b.get("coverage_bucket"),
               "past_winner": b.get("past_winner"),
               "days_to_catalyst": b.get("days_to_catalyst"),
               "close": b.get("close"),
               "why": b.get("status_reasons") or b.get("status_blocked_by") or []}
        if is_cand(b) and not is_cand(a):
            entered.append(row)
        elif is_cand(a) and not is_cand(b):
            left.append(row)
        else:
            regraded.append(row)

    # Biggest moves in the number the rule actually reads. Only names present
    # BOTH days, so a new listing cannot appear as a huge "change".
    moves = []
    for sym in both:
        u0, u1 = p_by[sym].get("upside"), t_by[sym].get("upside")
        if u0 is None or u1 is None:
            continue
        moves.append({"symbol": sym, "upside_prev": u0, "upside": u1,
                      "delta": u1 - u0, "status": t_by[sym].get("status"),
                      "sector": t_by[sym].get("sector"),
                      "close_prev": p_by[sym].get("close"), "close": t_by[sym].get("close")})
    moves.sort(key=lambda m: -abs(m["delta"]))

    def by_sector(rows: list[dict]) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in rows:
            if r.get("status") in CANDIDATE_STATUSES:
                k = r.get("sector") or "_UNKNOWN"
                out[k] = out.get(k, 0) + 1
        return out

    st, sp = by_sector(today), by_sector(prev)
    sectors = {k: {"today": st.get(k, 0), "prev": sp.get(k, 0),
                   "delta": st.get(k, 0) - sp.get(k, 0)}
               for k in sorted(set(st) | set(sp))}

    def hist(rows: list[dict]) -> dict[str, int]:
        h: dict[str, int] = {}
        for r in rows:
            h[r.get("status") or "_NONE"] = h.get(r.get("status") or "_NONE", 0) + 1
        return h

    return {
        "day": day, "prev_day": prev_day,
        "n_today": len(today), "n_prev": len(prev), "n_both": len(both),
        "status_histogram": {"today": hist(today), "prev": hist(prev)},
        "n_candidates": {"today": sum(1 for r in today if is_cand(r)),
                         "prev": sum(1 for r in prev if is_cand(r))},
        "entered": entered, "left": left, "regraded": regraded,
        "arrived": [{"symbol": s_, "status": t_by[s_].get("status"),
                     "sector": t_by[s_].get("sector")} for s_ in arrived],
        "departed": [{"symbol": s_, "was": p_by[s_].get("status"),
                      "sector": p_by[s_].get("sector")} for s_ in departed],
        "biggest_upside_moves": moves[:40],
        "sectors": sectors,
        "churn_note": ("`arrived`/`departed` are UNIVERSE changes -- a name that was not "
                       "fetched is not a name that was downgraded. They are counted apart "
                       "from `entered`/`left` so a bad refresh cannot read as a market move."),
    }


def candidates(rows: list[dict]) -> list[dict]:
    """The candidate list: BUY or better, best upside first."""
    got = [r for r in rows if r.get("status") in CANDIDATE_STATUSES]
    return sorted(got, key=lambda r: -(r.get("upside") or 0.0))


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def sector_top(rows: list[dict], *, n: int = 10) -> dict[str, list[dict]]:
    """Per sector, the top `n` candidates by upside. Murat's sector table."""
    out: dict[str, list[dict]] = {}
    for r in candidates(rows):
        out.setdefault(r.get("sector") or "_UNKNOWN", []).append(r)
    return {s: v[:n] for s, v in sorted(out.items())}


def coverage_split(rows: list[dict], key: str = "status") -> dict[str, dict[str, int]]:
    """Cross-tabulate any label against the coverage bucket.

    This is Murat's thin-coverage hypothesis kept as a QUESTION rather than an
    assumption: the tracker does not prefer thin names, it reports whether they
    behave differently, and the answer decides the weighting later.
    """
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        b = r.get("coverage_bucket") or "none"
        out.setdefault(b, {})
        v = str(r.get(key))
        out[b][v] = out[b].get(v, 0) + 1
    return {b: out[b] for b in (_BUCKET_ORDER + ["none"]) if b in out}


def flags(rows: list[dict]) -> dict:
    """Everything counted rather than cleaned. Read this before the rankings."""
    impl = [r["symbol"] for r in rows
            if (r.get("upside") or 0) >= UPSIDE_IMPLAUSIBLE_AT]
    return {
        "upside_implausible": {"threshold": UPSIDE_IMPLAUSIBLE_AT, "n": len(impl),
                               "symbols": sorted(impl)[:40],
                               "note": "kept and flagged, never dropped -- a 4x target is "
                                       "usually a stale split and occasionally the tail"},
        "no_target": sum(1 for r in rows if r.get("mean_target") is None),
        "no_coverage": sum(1 for r in rows if not r.get("coverage")),
        "no_12m_history": sum(1 for r in rows if r.get("ret_12m") is None),
        "no_catalyst": sum(1 for r in rows if r.get("days_to_catalyst") is None),
        "no_sector": sum(1 for r in rows if not r.get("sector")),
    }


# --------------------------------------------------------------------------
# Portfolios -- three personalities over one candidate list
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Personality:
    book: str
    name: str
    k: int
    max_notional: float          # per name, as a fraction of equity
    rank: str                    # which ranking this personality sorts on
    #: Clause (f). DECLARED, never defaulted: a switch measured at -2.9pp/yr
    #: should not be something a new personality acquires by forgetting to
    #: mention it. See the EXCLUDE_PAST_WINNERS block above for the evidence.
    exclude_past_winners: bool = None       # type: ignore[assignment]
    requires_catalyst: bool = False
    min_coverage_bucket: str | None = None
    #: The TOP of the coverage band. A book with a floor and no ceiling is a
    #: one-sided guard, and the one-sided version of this rule is what let
    #: hack6 -- a 4-10 book -- fill with 26+ mega-caps whenever they qualified.
    #: `min` and `max` are written in the same edit on purpose.
    max_coverage_bucket: str | None = None
    #: Median dollar volume floor. NOTE, so nobody reads more into this than is
    #: there: `universe.MIN_DOLLAR_VOLUME` already screens the whole tracker at
    #: $3m/day, so a $1m floor here excludes NOTHING today and is declared only
    #: so the book states its own requirement rather than inheriting one. The
    #: $5m floor on hack6 is the one that actually binds (580 -> 514 names on
    #: 2026-08-30). `excluded_by_reason` reports the count either way, so an
    #: inert floor is visible as inert rather than mistaken for a screen.
    min_dollar_volume: float | None = None
    max_sector_share: float | None = None
    #: A hard CONSTRAINT on the downside, separate from the ranking. A ratio
    #: ranking is scale-free, which is the point of it and also its one hole:
    #: +0.4% expected against a -1% bad case outranks +8% against -25%. The
    #: constraint is what stops "risk-adjusted" from meaning "tiny".
    max_downside: float | None = None

    def __post_init__(self) -> None:
        if self.exclude_past_winners is None:
            raise ValueError(
                f"{self.book}: exclude_past_winners must be declared explicitly. "
                "It is worth ~2.9pp/yr on eleven years of IBES and it is currently "
                "ON for hack3 and OFF for hack4/hack6 as a live A/B -- a silent "
                "default would quietly end that experiment.")


#: One personality per paper book. Each is its own PRODUCT_EXPERIMENT with its
#: own selector -- never a weight inside a shared composite, which is the
#: bottleneck rule: folding a new mechanism into a blend hides the only thing
#: being tested, whether its errors are DIFFERENT errors.
#: CLAUSE (f) IS A LIVE A/B, NOT A SETTING. hack3 excludes past winners because
#: Murat's rule says so; hack4 and hack6 do not because eleven years of IBES say
#: the exclusion costs ~2.9pp/yr and throws away the strongest sub-basket in the
#: study (+18.60%/yr, t 3.31). Neither side is asserted to be right. Both run,
#: on real paper money, and the books settle it -- which is the only way this
#: project has ever settled anything.
PERSONALITIES: tuple[Personality, ...] = (
    Personality("hack3", "balanced", k=10, max_notional=0.083,
                rank="risk_adjusted_ratio", exclude_past_winners=True,
                min_dollar_volume=1_000_000.0,
                max_sector_share=0.30, max_downside=0.30),
    Personality("hack4", "profit_max", k=5, max_notional=0.10, rank="upside_x_consensus",
                exclude_past_winners=False, requires_catalyst=True,
                min_dollar_volume=1_000_000.0, max_sector_share=0.20),
    Personality("hack6", "preservation", k=15, max_notional=0.06,
                rank="upside_downside_ratio", exclude_past_winners=False,
                min_coverage_bucket="4-10", max_coverage_bucket="11-25",
                min_dollar_volume=5_000_000.0, max_sector_share=0.18,
                max_downside=0.20),
)

#: THE SECTOR CAP IS A NAME COUNT WEARING A NOTIONAL. `max_sector_share` is a
#: fraction of equity because that is what the risk system reads, but it is
#: CHOSEN as `names_allowed x max_notional`, so it must be re-derived whenever
#: `k` or `max_notional` moves or it silently becomes a different rule:
#:
#:     hack3   3 x 0.083 = 0.249 -> 0.30   (3 of 10)
#:     hack4   2 x 0.10  = 0.20  -> 0.20   (2 of 5)
#:     hack6   3 x 0.06  = 0.18  -> 0.18   (3 of 15)
#:
#: Why at all: 20 of 21 names falling together on 28 Aug was ONE bet wearing 20
#: tickers. A ranking column without a sector cap re-creates that in whichever
#: sector is cheapest that day -- which is exactly how hack6's degenerate sort
#: came out as 12 biotechs rather than 12 of anything else.
SECTOR_CAP_NAMES: dict[str, int] = {"hack3": 3, "hack4": 2, "hack6": 3}

#: WHY hack6 GAINED A `max_downside` IT WAS NOT ASKED FOR (2026-08-31).
#:
#: Not in the brief. It is here because the ranking change above CREATED the
#: exposure and shipping one without the other would have been a regression
#: introduced by a bug fix. With `confidence` constant the selection was
#: arbitrary; `upside / |downside|` actively SELECTS FOR HIGH UPSIDE, and high
#: upside is high vol, so the first build put this in the *preservation* book:
#:
#:     FRMI -52.5%   NB -41.6%   RZLV -38.0%   WVE -37.8%   APLD -35.1%
#:     worst -52.5%, mean -27.4% -- against hack3's -30% CAP
#:
#: The preservation book was carrying more per-name downside than the balanced
#: one, and hack6's stop is 3%: a name whose 5% quantile is -38% does not get
#: stopped at -3%, it gaps through it. The stop and the downside cap have to
#: agree or the stop is decoration.
#:
#: 0.20 was chosen off a measured sweep, not asserted. Eligible names at each
#: cap, and whether the book still fills 15:
#:
#:     none 514 (15/15)  0.35 378 (15/15)  0.30 314 (15/15)  0.25 231 (15/15)
#:     0.20 132 (15/15)  0.15  44 (15/15)  0.12  13 (13/15)  0.10 3 (3/15)
#:
#: A plateau from 0.35 to 0.15, a cliff below. 0.20 is mid-plateau with 8.8x
#: headroom over the 15 it needs, so a thin refresh day still fills; 0.15 fills
#: today on 44 names and is the edge of the cliff. Result: worst -18.7%, mean
#: -14.5%, still 9 sectors. Tighter than balanced, which is what the word
#: preservation has to mean or the personalities are only names.
#: REVERT: delete `max_downside=0.20` from hack6 -- nothing else depends on it.


def rank_value(row: dict, how: str) -> float:
    """The ranking a personality sorts on. Missing inputs rank last, never zero.

    `-inf` for a missing input rather than 0.0 is deliberate: a zero would let
    an unmeasured name outrank a measured one whose number is genuinely
    negative, which is how an absence gets promoted into a position.
    """
    neg = float("-inf")
    if how == "risk_adjusted_ratio":
        # RETIRED 2026-08-30 (e): this used to be `er - abs(dn)`, and that
        # SUBTRACTION was the bug. In live rows `exp_return` is about 0.0025
        # and `downside_5pct` is about 0.25 -- a hundred times larger -- so the
        # difference was ~99% the downside term and the "balanced" book was
        # sorting on LOW VOLATILITY alone. It put TSM, AVGO and NVDA on top:
        # the mega-cap bias the whole tracker exists to remove, walking back in
        # through the ranking. Two numbers on different scales must be divided,
        # not subtracted. The scale-freeness is paid for by `max_downside`,
        # which is checked as a constraint in `build_portfolio`.
        er, dn = row.get("exp_return"), row.get("downside_5pct")
        if er is None or dn is None:
            return neg
        # A downside of exactly zero is an UNMEASURED downside, not a riskless
        # name; ranking it +inf would put the least-known name first.
        return neg if abs(dn) < 1e-6 else er / abs(dn)
    if how == "upside_x_consensus":
        up, cons = row.get("upside"), row.get("consensus")
        return neg if up is None or cons is None else up * cons
    if how == "upside_downside_ratio":
        # ADOPTED 2026-08-31, replacing `confidence` on hack6. `confidence` is
        # `(clauses readable / 4) x min(1, date blocks / N)`: a property of how
        # much of the ROW could be read, not of the name. Every name whose four
        # clauses were readable scored the same 0.9170, so 607 eligible names
        # carried 2 distinct values, the sort was a no-op, and Python's stable
        # sort handed back insertion order -- which surfaced as 12 biotechs and
        # 3 others. Same class as hack3's subtraction sorting on volatility:
        # the column was not wrong, it was CONSTANT.
        #
        # `upside` (consensus target vs last close) and `downside_5pct` (the 5%
        # normal quantile at the name's own realised vol) both vary per name,
        # and their ratio is what "preservation" means: reward per unit of the
        # name's own bad case. Deliberately NOT `risk_adjusted_ratio` -- that
        # one divides `exp_return`, which carries the rule's p_up, and hack6 is
        # the book that is supposed to rank on the STREET's number, not ours.
        up, dn = row.get("upside"), row.get("downside_5pct")
        if up is None or dn is None:
            return neg
        # A zero downside is an UNMEASURED downside, not a riskless name.
        return neg if abs(dn) < 1e-6 else up / abs(dn)
    if how == "confidence":
        c = row.get("confidence")
        return neg if c is None else float(c)
    if how == "upside":
        return row.get("upside") if row.get("upside") is not None else neg
    raise ValueError(f"unknown ranking {how!r}")


def _eligibility_checks(p: Personality) -> list:
    """Every eligibility rule as an INDEPENDENT test, IN CHAIN ORDER.

    One expression per rule, used twice. The FIRST failure is what
    `excluded_by_reason` reports -- the historical sequential attribution,
    unchanged byte for byte. The FULL failure set is what `excluded_marginal`
    reports. Writing the rules twice (once to filter, once to explain) is
    exactly how an explanation drifts away from the filter it describes, so
    these are the same objects and there is nothing to keep in sync.

    Each check returns None to pass, or `(reason, detail)` to fail. Checks must
    be TOTAL: the sequential chain never evaluated a rule after an earlier one
    fired, and this evaluates all of them on every row, so a rule that raises
    on data the chain used to skip would turn a report into a crash.
    """
    checks: list = []

    if p.exclude_past_winners:
        def _past_winner(r):
            pw = r.get("past_winner")
            if pw is True:
                return ("past winner",
                        f"{r['symbol']}: {r.get('past_winner_basis') or 'flagged'}")
            if pw is None:
                return ("past_winner unreadable (no 12-month history)", "")
            return None
        checks.append(_past_winner)

    if p.max_downside is not None:
        def _downside(r, cap=p.max_downside):
            dn = r.get("downside_5pct")
            if dn is None:
                return ("downside unreadable", "")
            if abs(dn) > cap + 1e-9:
                return (f"downside above the {cap:.0%} cap", f"{r['symbol']}: {abs(dn):.0%}")
            return None
        checks.append(_downside)

    if p.requires_catalyst:
        def _catalyst(r):
            cat = r.get("days_to_catalyst")
            if cat is None:
                return ("no readable catalyst", "")
            if cat > CATALYST_MAX_CALENDAR_DAYS:
                return (f"catalyst beyond {CATALYST_MAX_CALENDAR_DAYS} calendar days", "")
            return None
        checks.append(_catalyst)

    if p.min_coverage_bucket:
        def _cov_min(r, need=p.min_coverage_bucket):
            # A GUARD DERIVES ITS INPUT OR REFUSES. Reading a Finnhub-panel
            # count against a bucket calibrated on IBES `numrec` would let a
            # one-analyst name in through a rule written to keep it out -- the
            # count runs ~1.80x on that scale. Refuse, and say which.
            if r.get("coverage_source") != COVERAGE_SOURCE_CALIBRATED:
                return ("coverage on an uncalibrated scale",
                        f"{r['symbol']}: {r.get('coverage_source') or 'unknown'} scale, "
                        f"which {need} was not calibrated for")
            br, nd = bucket_rank(r.get("coverage_bucket")), bucket_rank(need)
            if br is None or nd is None or br < nd:
                return (f"coverage below {need}", "")
            return None
        checks.append(_cov_min)

    if p.max_coverage_bucket:
        def _cov_max(r, top=p.max_coverage_bucket):
            # Same calibration refusal as the floor: a ceiling read against a
            # Finnhub count that runs ~1.80x the IBES scale would admit a
            # 40-analyst name into a 4-25 book.
            if r.get("coverage_source") != COVERAGE_SOURCE_CALIBRATED:
                return ("coverage on an uncalibrated scale",
                        f"{r['symbol']}: {r.get('coverage_source') or 'unknown'} scale, "
                        f"which {top} was not calibrated for")
            br, tp = bucket_rank(r.get("coverage_bucket")), bucket_rank(top)
            if br is None or tp is None or br > tp:
                return (f"coverage above {top}", "")
            return None
        checks.append(_cov_max)

    if p.min_dollar_volume is not None:
        def _liquidity(r, floor=p.min_dollar_volume):
            # A GUARD DERIVES ITS INPUT OR REFUSES. An unreadable dollar volume
            # is not a liquid name; passing it through on `or 0` would admit
            # exactly the names the floor exists to keep out.
            dv = r.get("median_dollar_volume")
            if dv is None:
                return ("dollar volume unreadable", "")
            if dv < floor:
                return (f"below the ${floor / 1e6:.0f}m/day liquidity floor",
                        f"{r['symbol']}: ${dv / 1e6:.1f}m/day")
            return None
        checks.append(_liquidity)

    def _coherence(r):
        # LONG-BOOK COHERENCE (2026-09-01). These books are long-only, and the
        # runner's brain forecasts each name from the SAME sealed numbers -- so
        # a name whose own calibrated exp_return is not positive forecasts DOWN
        # and is refused at trade time, every time. Sealing it seals dead
        # weight: on 2026-08-31 hack6 sealed 15/15 such names and correctly
        # entered nothing, and RZLV (ranked #1 by upside x consensus) sat out
        # the same way. This is the panel base rate speaking -- the rule-firing
        # cell (high target ratio) MEASURES below 0.5 (the S30b toxicity band)
        # -- and the book now agrees with its own calibration instead of
        # arguing with it at the broker. The exclusion is counted, not silent.
        exp_r = r.get("exp_return")
        if exp_r is None:
            return ("exp_return unreadable (the brain would refuse the numberless name)", "")
        if exp_r <= 0:
            return ("exp_return not positive (own base rate says this cell loses; "
                    "a long book cannot hold it)",
                    f"{r['symbol']}: exp_return {exp_r:+.4f}")
        return None
    checks.append(_coherence)

    def _rankable(r, how=p.rank):
        try:
            bad = rank_value(r, how) == float("-inf")
        except Exception:                                        # noqa: BLE001
            bad = True
        return (f"no {how} value", "") if bad else None
    checks.append(_rankable)

    return checks


def build_portfolio(rows: list[dict], p: Personality) -> dict:
    """Select and weight one book's holdings from the candidate list.

    Every name that was excluded is COUNTED by reason. A portfolio that reports
    only what it holds cannot be debugged: on 2026-08-30 the sealed book held
    one name and the interesting number was not MU, it was the 150 it passed
    over and why.

    TWO attributions, because one of them answers a question it looks like it
    answers and does not (2026-09-01):

      `excluded_by_reason`  FIRST-FIRED. The chain short-circuits, so a name is
                            owned by the earliest rule it fails. On the
                            2026-09-01 seal this reads "hack4: 603 excluded by
                            catalyst-beyond-30-days", which is true and does
                            NOT mean the catalyst rule is what binds -- hack4
                            simply has no past-winner or downside rule ahead of
                            it. Sequential attribution answers "what fired
                            first", never "what would relaxing X buy".
      `excluded_marginal`   INDEPENDENT. `fails` counts every name that fails a
                            rule at all; `fails_only` counts names that fail
                            ONLY that rule -- the names that would become
                            eligible if it alone were dropped, every other rule
                            kept. That is the price of the rule, in
                            opportunities, and it is the number to read when
                            asking why capital is idle.

    A rule with a large `fails` and a near-zero `fails_only` is redundant, not
    binding: something else was already rejecting those names.
    """
    pool = candidates(rows)
    excluded: dict[str, int] = {}

    examples: dict[str, str] = {}

    def drop(reason: str, detail: str = "") -> None:
        """Count by CATEGORY, keep one example of the detail.

        The first version counted the full reason string, and because a
        past-winner reason names that name's own twelve-month return, 145
        exclusions became 140 distinct keys and the report was unreadable --
        which is the same failure as no report at all.
        """
        excluded[reason] = excluded.get(reason, 0) + 1
        if detail and reason not in examples:
            examples[reason] = detail

    # ONE pass, TWO attributions. `checks` is the single expression of every
    # eligibility rule (see `_eligibility_checks`); the first failure feeds the
    # historical sequential report and the whole failure set feeds the marginal
    # one. Nothing about SELECTION changes: the first-failure reason and its
    # detail string are identical to the short-circuiting chain this replaced.
    checks = _eligibility_checks(p)
    marginal_fails: dict[str, int] = {}
    marginal_only: dict[str, int] = {}

    eligible = []
    for r in pool:
        failures = [f for f in (c(r) for c in checks) if f is not None]
        for reason, _detail in failures:
            marginal_fails[reason] = marginal_fails.get(reason, 0) + 1
        if len(failures) == 1:
            marginal_only[failures[0][0]] = marginal_only.get(failures[0][0], 0) + 1
        if failures:
            reason, detail = failures[0]
            drop(reason, detail)
            continue
        eligible.append(r)

    # A RANKING THAT DOES NOT RANK. Measured 2026-08-30: hack6 sorts on
    # `confidence`, and the rule publishes the SAME confidence for every
    # non-claiming name -- so all 607 eligible names scored +0.9170 and "the
    # top 15 by confidence" was the first 15 in dict order, which came out as
    # 13 biotechs. That is the same class of failure as hack3's subtraction
    # sorting on volatility, and it is invisible unless something counts the
    # distinct values. It is reported rather than repaired: which column a book
    # ranks on is a selection decision, not a bug fix.
    distinct = len({round(rank_value(r, p.rank), 9) for r in eligible})
    eligible.sort(key=lambda r: -rank_value(r, p.rank))

    picked: list[dict] = []
    sector_notional: dict[str, float] = {}
    for r in eligible:
        if len(picked) >= p.k:
            break
        sec = r.get("sector") or "_UNKNOWN"
        if p.max_sector_share is not None:
            if sector_notional.get(sec, 0.0) + p.max_notional > p.max_sector_share + 1e-9:
                drop("sector at its cap", f"{sec} at {p.max_sector_share:.0%}")
                continue
        sector_notional[sec] = sector_notional.get(sec, 0.0) + p.max_notional
        picked.append({
            "symbol": r["symbol"], "notional": p.max_notional, "sector": sec,
            "rank_value": round(rank_value(r, p.rank), 6), "status": r.get("status"),
            "upside": r.get("upside"), "consensus": r.get("consensus"),
            "coverage_bucket": r.get("coverage_bucket"),
            "exp_return": r.get("exp_return"), "downside_5pct": r.get("downside_5pct"),
            "confidence": r.get("confidence"), "days_to_catalyst": r.get("days_to_catalyst"),
            "past_winner": r.get("past_winner"),
            # WHOSE NUMBER RANKED THIS NAME. A book built from two number
            # sources that does not say which is which cannot be graded, and
            # grading one against the other is the entire point.
            "numbers_source": r.get("numbers_source") or "rule",
            "brain_adjustment": r.get("brain_adjustment"),
        })

    return {
        "book": p.book, "personality": p.name, "ranking": p.rank,
        "rank_distinct_values": distinct,
        "ranking_is_degenerate": bool(eligible and distinct < 2),
        "k_target": p.k, "n_selected": len(picked),
        "max_notional_each": p.max_notional,
        "requires_catalyst": p.requires_catalyst,
        "exclude_past_winners": p.exclude_past_winners,
        "min_coverage_bucket": p.min_coverage_bucket,
        "max_coverage_bucket": p.max_coverage_bucket,
        "min_dollar_volume": p.min_dollar_volume,
        "max_sector_share": p.max_sector_share,
        "max_names_per_sector": SECTOR_CAP_NAMES.get(p.book),
        "max_downside": p.max_downside,
        "holdings": picked,
        "candidate_pool": len(pool), "eligible": len(eligible),
        "excluded_by_reason": dict(sorted(excluded.items(), key=lambda kv: -kv[1])),
        # THE PRICE OF EACH RULE, not the order they fired in. `fails_only` is
        # the count of names that would become eligible if this rule alone were
        # dropped -- read this one when asking why capital is idle.
        "excluded_marginal": {
            "note": ("`fails` = names failing this rule at all; `fails_only` = names "
                     "failing ONLY this rule, i.e. what relaxing it alone would buy. "
                     "`excluded_by_reason` above is first-fired attribution and cannot "
                     "answer that question."),
            "fails": dict(sorted(marginal_fails.items(), key=lambda kv: -kv[1])),
            "fails_only": dict(sorted(marginal_only.items(), key=lambda kv: -kv[1])),
        },
        "excluded_examples": examples,
        "sector_notional": {k: round(v, 4) for k, v in sorted(sector_notional.items())},
    }


def worst_case(*, n: int, notional_each: float, stop_fraction: float,
               gross_cap: float) -> dict:
    """The loss if every name gaps to its stop on the same day.

        gross    = min(n x notional_each, gross_cap)
        worst    = gross x stop_fraction

    THE `min` IS THE WHOLE POINT. `n x notional x stop` and `gross_cap x stop`
    agree only until the name count is large enough that the cap binds first,
    and confusing them is the arithmetic that produced -9% on 28 Aug (twelve
    names x 25% = 300% gross) and then -24% when the "fix" widened the stop on
    uncapped gross. Whichever binds, this returns the binding one and says
    which -- because a bound that does not name what binds it invites the next
    edit to loosen the other side.
    """
    requested = n * notional_each
    gross = min(requested, gross_cap)
    return {
        "n": n, "notional_each": notional_each, "requested_gross": round(requested, 4),
        "gross_cap": gross_cap, "gross": round(gross, 4),
        "binding": "gross_cap" if requested > gross_cap + 1e-9 else "name_count",
        "stop_fraction": stop_fraction,
        "worst_case_fraction": round(-gross * stop_fraction, 6),
        "worst_case_pct": f"{-gross * stop_fraction:.2%}",
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build_rows(raw: list[dict]) -> list[dict]:
    """Derive every computed column from the fetched ones, in place-safe copies.

    `raw` rows carry only what was FETCHED: symbol, close, high_60d, ret_12m,
    counts, mean_target, sector, days_to_catalyst, observed_at. Everything else
    on the row is derived here, so a past day's file can be re-derived under a
    changed rule without re-fetching anything -- which is the property that
    makes the accumulated history worth keeping.
    """
    rows = []
    for r in raw:
        row = dict(r)
        # The RATING comes from Finnhub's panel (an average over whoever is in
        # it is a fair rating); the COUNT does not, because the panel's size is
        # not the number of analysts covering the name. See
        # COVERAGE_SOURCE_CALIBRATED above for the measurement.
        cons = consensus_score(r.get("rec_counts"))
        row["consensus"] = round(cons[0], 3) if cons else None
        row["coverage_finnhub"] = cons[1] if cons else None
        n_yf = r.get("n_analysts_yf")
        if isinstance(n_yf, (int, float)) and n_yf > 0:
            row["coverage"] = int(n_yf)
            row["coverage_source"] = COVERAGE_SOURCE_CALIBRATED
        elif row["coverage_finnhub"]:
            row["coverage"] = row["coverage_finnhub"]
            row["coverage_source"] = COVERAGE_SOURCE_UNCALIBRATED
        else:
            row["coverage"] = r.get("coverage") or 0
            row["coverage_source"] = None
        row["coverage_bucket"] = coverage_bucket(row["coverage"])
        row["upside"] = upside(r.get("mean_target"), r.get("close"))
        row["drawdown_60d"] = drawdown_60d(r.get("close"), r.get("high_60d"))
        rows.append(row)
    mark_past_winners(rows)
    return rows


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def summary(rows: list[dict], *, day: str, hist: dict, pw: dict) -> dict:
    ups = [r["upside"] for r in rows if r.get("upside") is not None]
    return {
        "schema": SCHEMA, "day": day,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_symbols": len(rows),
        "n_with_coverage": sum(1 for r in rows if r.get("coverage")),
        "n_with_target": sum(1 for r in rows if r.get("mean_target") is not None),
        "status_histogram": hist,
        "n_candidates": sum(hist.get(s, 0) for s in CANDIDATE_STATUSES),
        "coverage_source_counts": _count_by(rows, "coverage_source"),
        "coverage_split_by_status": coverage_split(rows, "status"),
        "coverage_split_by_past_winner": coverage_split(rows, "past_winner"),
        "past_winner": pw,
        "n_past_winners": sum(1 for r in rows if r.get("past_winner") is True),
        "upside_median": round(st.median(ups), 4) if ups else None,
        "flags": flags(rows),
        "thresholds": {
            "STRONG_BUY": {"upside": STRONG_BUY_UPSIDE, "consensus": STRONG_BUY_CONSENSUS,
                           "catalyst_sessions": CATALYST_MAX_SESSIONS,
                           "catalyst_calendar_days": CATALYST_MAX_CALENDAR_DAYS,
                           "days_to_catalyst_units": "CALENDAR DAYS",
                           "past_winner": "reported, not a status bar"},
            "BUY": {"upside": BUY_UPSIDE, "consensus": BUY_CONSENSUS,
                    "past_winner": "reported, not a status bar"},
            "HOLD": {"upside": HOLD_UPSIDE, "requires": "already on the list"},
            "SELL": {"upside_below": SELL_UPSIDE, "consensus_below": SELL_CONSENSUS,
                     "or": "a stop hit on any book"},
            "DROP": {"sell_sessions": DROP_AFTER_SELL_SESSIONS, "min_price": MIN_PRICE_USD},
            "past_winner": {"excluded_by_book": {p.book: p.exclude_past_winners
                                                for p in PERSONALITIES},
                            "excluded_from_status": False,
                            "sector_decile": PAST_WINNER_SECTOR_DECILE,
                            "or_absolute_return": PAST_WINNER_ABSOLUTE_RETURN,
                            "min_sector_n": MIN_SECTOR_N},
        },
    }
