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
from datetime import datetime, timezone

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
#: Flipping this to False is a ONE-LINE change and is his call, not mine. The
#: bottleneck rule says the right way to settle it is two selectors running
#: side by side rather than one weight being argued about -- so if it is
#: flipped, it should be flipped on ONE book, not on all of them.
EXCLUDE_PAST_WINNERS = True

#: Below this many rated names, a sector's own decile is not a decile -- it is
#: a small sample wearing one. Those names fall back to the market-wide decile
#: and the row says so in `past_winner_basis`.
MIN_SECTOR_N = 20

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

    # `past_ok` is what clause (f) actually asserts. With EXCLUDE_PAST_WINNERS
    # off, a past winner is no longer barred -- but `past_winner` is still
    # computed and still recorded on the row, because the flag is evidence
    # whether or not it is currently a gate.
    past_ok = (past is False) if EXCLUDE_PAST_WINNERS else (past is not None)
    can_strong = (up is not None and up >= STRONG_BUY_UPSIDE
                  and cons is not None and cons >= STRONG_BUY_CONSENSUS
                  and past_ok)
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
                "not a past winner",
                f"catalyst in {cat} calendar days"], blocked, 0)

    if (up is not None and up >= BUY_UPSIDE and cons is not None
            and cons >= BUY_CONSENSUS and past_ok):
        return StatusVerdict("BUY", [
            f"upside {up:+.1%} >= {BUY_UPSIDE:+.0%}",
            f"consensus {cons:.2f} >= {BUY_CONSENSUS}",
            "not a past winner"], blocked, 0)

    if past is True and EXCLUDE_PAST_WINNERS:
        blocked.append(f"past winner -- {row.get('past_winner_basis') or 'flagged'}")

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
    requires_catalyst: bool = False
    min_coverage_bucket: str | None = None
    max_sector_share: float | None = None


#: One personality per paper book. Each is its own PRODUCT_EXPERIMENT with its
#: own selector -- never a weight inside a shared composite, which is the
#: bottleneck rule: folding a new mechanism into a blend hides the only thing
#: being tested, whether its errors are DIFFERENT errors.
PERSONALITIES: tuple[Personality, ...] = (
    Personality("hack3", "balanced", k=10, max_notional=0.083, rank="risk_adjusted",
                max_sector_share=0.30),
    Personality("hack4", "profit_max", k=5, max_notional=0.10, rank="upside_x_consensus",
                requires_catalyst=True),
    Personality("hack6", "preservation", k=15, max_notional=0.06, rank="confidence",
                min_coverage_bucket="4-10"),
)


def rank_value(row: dict, how: str) -> float:
    """The ranking a personality sorts on. Missing inputs rank last, never zero.

    `-inf` for a missing input rather than 0.0 is deliberate: a zero would let
    an unmeasured name outrank a measured one whose number is genuinely
    negative, which is how an absence gets promoted into a position.
    """
    neg = float("-inf")
    if how == "risk_adjusted":
        er, dn = row.get("exp_return"), row.get("downside_5pct")
        return neg if er is None or dn is None else er - abs(dn)
    if how == "upside_x_consensus":
        up, cons = row.get("upside"), row.get("consensus")
        return neg if up is None or cons is None else up * cons
    if how == "confidence":
        c = row.get("confidence")
        return neg if c is None else float(c)
    if how == "upside":
        return row.get("upside") if row.get("upside") is not None else neg
    raise ValueError(f"unknown ranking {how!r}")


def build_portfolio(rows: list[dict], p: Personality) -> dict:
    """Select and weight one book's holdings from the candidate list.

    Every name that was excluded is COUNTED by reason. A portfolio that reports
    only what it holds cannot be debugged: on 2026-08-30 the sealed book held
    one name and the interesting number was not MU, it was the 150 it passed
    over and why.
    """
    pool = candidates(rows)
    excluded: dict[str, int] = {}

    def drop(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    eligible = []
    for r in pool:
        if p.requires_catalyst:
            cat = r.get("days_to_catalyst")
            if cat is None:
                drop("no readable catalyst")
                continue
            if cat > CATALYST_MAX_CALENDAR_DAYS:
                drop(f"catalyst beyond {CATALYST_MAX_CALENDAR_DAYS} calendar days")
                continue
        if p.min_coverage_bucket:
            br, need = bucket_rank(r.get("coverage_bucket")), bucket_rank(p.min_coverage_bucket)
            if br is None or need is None or br < need:
                drop(f"coverage below {p.min_coverage_bucket}")
                continue
        if rank_value(r, p.rank) == float("-inf"):
            drop(f"no {p.rank} value")
            continue
        eligible.append(r)

    eligible.sort(key=lambda r: -rank_value(r, p.rank))

    picked: list[dict] = []
    sector_notional: dict[str, float] = {}
    for r in eligible:
        if len(picked) >= p.k:
            break
        sec = r.get("sector") or "_UNKNOWN"
        if p.max_sector_share is not None:
            if sector_notional.get(sec, 0.0) + p.max_notional > p.max_sector_share + 1e-9:
                drop(f"sector {sec} at its {p.max_sector_share:.0%} cap")
                continue
        sector_notional[sec] = sector_notional.get(sec, 0.0) + p.max_notional
        picked.append({
            "symbol": r["symbol"], "notional": p.max_notional, "sector": sec,
            "rank_value": round(rank_value(r, p.rank), 6), "status": r.get("status"),
            "upside": r.get("upside"), "consensus": r.get("consensus"),
            "coverage_bucket": r.get("coverage_bucket"),
            "exp_return": r.get("exp_return"), "downside_5pct": r.get("downside_5pct"),
            "confidence": r.get("confidence"), "days_to_catalyst": r.get("days_to_catalyst"),
        })

    return {
        "book": p.book, "personality": p.name, "ranking": p.rank,
        "k_target": p.k, "n_selected": len(picked),
        "max_notional_each": p.max_notional,
        "requires_catalyst": p.requires_catalyst,
        "min_coverage_bucket": p.min_coverage_bucket,
        "max_sector_share": p.max_sector_share,
        "holdings": picked,
        "candidate_pool": len(pool), "eligible": len(eligible),
        "excluded_by_reason": excluded,
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
        cons = consensus_score(r.get("rec_counts"))
        row["consensus"] = round(cons[0], 3) if cons else None
        row["coverage"] = cons[1] if cons else (r.get("coverage") or 0)
        row["coverage_bucket"] = coverage_bucket(row["coverage"])
        row["upside"] = upside(r.get("mean_target"), r.get("close"))
        row["drawdown_60d"] = drawdown_60d(r.get("close"), r.get("high_60d"))
        rows.append(row)
    mark_past_winners(rows)
    return rows


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
                           "past_winner": False},
            "BUY": {"upside": BUY_UPSIDE, "consensus": BUY_CONSENSUS, "past_winner": False},
            "HOLD": {"upside": HOLD_UPSIDE, "requires": "already on the list"},
            "SELL": {"upside_below": SELL_UPSIDE, "consensus_below": SELL_CONSENSUS,
                     "or": "a stop hit on any book"},
            "DROP": {"sell_sessions": DROP_AFTER_SELL_SESSIONS, "min_price": MIN_PRICE_USD},
            "past_winner": {"excluded": EXCLUDE_PAST_WINNERS,
                            "sector_decile": PAST_WINNER_SECTOR_DECILE,
                            "or_absolute_return": PAST_WINNER_ABSOLUTE_RETURN,
                            "min_sector_n": MIN_SECTOR_N},
        },
    }
