"""Analyst TARGETS and consensus RATING -- the two legs of Murat's rule that
have been scored `unknown` since the rule was reconstructed.

WHAT WAS BLOCKED, AND WHAT ACTUALLY WAS
=======================================
`scripts/analyst_panel.py` states it plainly: Finnhub's free tier returns
HTTP 403 on `stock/price-target`, so *"the literal '>50% analyst upside' screen
from Murat's own process cannot be reproduced"*. That is true of the VENDOR
CONSENSUS endpoint and it was read as true of both conditions:

    (a) analyst 12-month target / price  >= ~1.5
    (b) consensus rating                 >= ~4.1 / 5

so 14 of 20 names scored 3/5 or 4/5 with `unk` on both, and the rule was
really out of three. Two things were available the whole time.

**(b) was never blocked.** A 1-5 consensus rating is a weighted mean of analyst
recommendation COUNTS, and `stock/recommendation` is free, is already fetched
every morning at 05:30, and is already written to
`state/research/analyst_panel/<date>.jsonl` with a `captured_utc` stamp. MU on
2026-08-29: 18 strongBuy / 33 buy / 4 hold / 1 sell / 0 strongSell over 56
analysts = **4.21**, which passes Murat's 4.1 bar. No new call, no new key.

**(a) was blocked at the vendor and open in the corpus.** The 12-month news
backfill carries **2,368 rows** that quote a price target, in Benzinga's
regular form -- *"Stifel Maintains Buy on Advanced Micro Devices, Raises Price
Target to $190"* -- and 1,574 of 1,575 title matches carry exactly ONE symbol,
so the join is unambiguous. It covers the thin names a vendor consensus tends
to miss: SRRK 70 rows, OLMA 55, ABSI 55, BHVN 79, NTLA 117.

That is BETTER than a consensus number, not a substitute for one: we get the
individual firm, its rating word, its target and the timestamp it became
knowable, so the panel can be rebuilt point-in-time at any past date instead of
being a single figure whose vintage nobody recorded. This is the lookahead the
panel's own docstring warns about, solved rather than deferred.

WHAT THIS MODULE REFUSES TO DO
==============================
* **No magnitude filter.** A target 3x above the price is exactly the tail
  Murat's rule is looking for (his greens are mostly >=2.0), so dropping
  "implausible" ratios would delete the signal and leave the noise -- the
  `rev_breadth` lesson, and the `abs(delta)` lesson after it. A split inside
  the window is instead FLAGGED (`split_suspect`) and counted, never dropped.
* **No single-firm consensus.** One firm is an opinion. `MIN_FIRMS` distinct
  firms are required before a ratio is reported at all; below that the status
  is `THIN`, which is a state, not a pass and not a fail.
* **No stale target read as current.** Targets older than `WINDOW_DAYS` are out
  of the panel, and the age of the newest is reported so a caller can see that
  a "current" target is four months old.
* **No network.** Everything here is pure over the corpus and over inputs the
  caller supplies. The 05:30 panel and the backfill do the fetching; this reads
  what they wrote.
"""

from __future__ import annotations

import re
import statistics as st
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

#: Murat's own bars, from the colour code in his spreadsheets (roadmap §3).
UPSIDE_BAR = 1.5
RATING_BAR = 4.1

#: Targets older than this are out of the panel. An analyst target is a
#: 12-month view but it is REVISED constantly; a 90-day window is the span over
#: which the standing set of targets is still what the street is quoting.
WINDOW_DAYS = 90
#: Distinct firms required before a ratio is reported. One firm is an opinion.
MIN_FIRMS = 2

#: The headline rating scale is NOT Finnhub's, and the 4.1 bar does not travel.
#:
#: MEASURED 2026-08-29 on the five names where both sources exist:
#:
#:     name   finnhub   headline   firms
#:     NVDA      4.26       4.06      16
#:     TSM       4.26       3.88       8
#:     MU        4.21       3.95      19
#:     MRVL      4.12       3.78      18
#:     AMD       4.10       3.96      23
#:
#: All five clear 4.10 on the counts; NOT ONE clears it on the words. The cause
#: is discretisation, not disagreement: Benzinga prints the firm's own word
#: (Buy / Overweight / Outperform, all 4.0) and says "Strong Buy" in 7 of 1,558
#: headlines, so a mean of the words is pinned just under 4 while Finnhub's
#: counts separate strongBuy from buy and can exceed it. Systematic offset
#: -0.27; correlation +0.47 on n=5, which is not a calibration of anything.
#:
#: So the fallback DOES NOT vote on Murat's bar. Applying 4.1 to it returned
#: `fail` for twelve names on an artefact of the scale -- a gate that could not
#: go green, which this project calls a broken gate, not a strict one. It votes
#: only where no offset could rescue the name: an average firm saying HOLD or
#: worse is a fail on any scale. Everything between is `unknown`, with the
#: number reported so a human can look.
#:
#: Revisit when the overlap is bigger. `analyst_panel` captures ~60 names a day
#: and the corpus keeps growing; at n>=30 this becomes a real calibration.
HEADLINE_FAIL_AT = 3.0

#: Rating word -> 1..5 with FIVE BEST, which is Murat's direction ("rating >= 4.1
#: / 5 (Buy-Strong Buy)"). Note this is the OPPOSITE of the Refinitiv/Yahoo
#: convention where 1 is Strong Buy; getting it backwards would invert the whole
#: screen, so the bar and the scale are stated together and pinned by a test.
#: Longest phrases first -- "strong buy" must not be matched as "buy".
_RATING_WORDS: tuple[tuple[str, float], ...] = (
    ("strong buy", 5.0), ("conviction buy", 5.0), ("strong sell", 1.0),
    ("market outperform", 4.0), ("sector outperform", 4.0), ("outperform", 4.0),
    ("market perform", 3.0), ("sector perform", 3.0), ("peer perform", 3.0),
    ("equal-weight", 3.0), ("equal weight", 3.0), ("in-line", 3.0), ("in line", 3.0),
    ("underperform", 2.0), ("underweight", 2.0), ("overweight", 4.0),
    ("accumulate", 4.0), ("positive", 4.0), ("neutral", 3.0), ("negative", 2.0),
    ("reduce", 2.0), ("buy", 4.0), ("hold", 3.0), ("sell", 2.0),
)
_RATING_RE = re.compile(r"(?i)\b(" + "|".join(re.escape(w) for w, _ in _RATING_WORDS) + r")\b")
_RATING_SCORE = dict(_RATING_WORDS)

#: PLURAL included on purpose. The 17 "Wall Street Boosts Price Targets"
#: summaries carry no single readable figure, and matching them lands each
#: one in `dropped_no_amount` where it is COUNTED. Matching only the
#: singular would make them invisible instead of unread, and an invisible
#: miss rate is a parser nobody can calibrate.
_HAS_TARGET = re.compile(r"(?i)\bprice targets?\b")
#: Prefer the value after "to" -- Benzinga writes both "Raises PT to $200" and
#: "Lowers PT From $200 To $168", and taking the last dollar figure gets the
#: second right and the variant "Raises PT to $200 From $180" wrong.
_TO_AMT = re.compile(r"(?i)\bto\s*\$\s*(\d[\d,]*(?:\.\d+)?)")
_OF_AMT = re.compile(r"(?i)\b(?:of|at)\s*\$\s*(\d[\d,]*(?:\.\d+)?)")
_ANY_AMT = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")

#: The action verb ends the firm name. "Raymond James Maintains Outperform on..."
_ACTION = re.compile(r"(?i)\b(maintains|reiterates|reinstates|initiates|resumes|upgrades|"
                     r"downgrades|assumes|announces|raises|lowers|keeps|begins)\b")


@dataclass(frozen=True)
class Target:
    symbol: str
    firm: str
    target_usd: float
    rating_word: str
    rating_score: float | None
    observed_at: str            # when it became KNOWABLE -- the PIT stamp
    title: str
    source: str = ""


@dataclass
class TargetPanel:
    """The standing set of targets for one symbol, as of one moment."""
    symbol: str
    as_of: str
    targets: list[Target] = field(default_factory=list)
    window_days: int = WINDOW_DAYS
    dropped_no_amount: int = 0
    dropped_multi_symbol: int = 0

    @property
    def firms(self) -> list[str]:
        return sorted({t.firm for t in self.targets if t.firm})

    @property
    def n_firms(self) -> int:
        return len(self.firms)

    @property
    def median_target(self) -> float | None:
        vals = [t.target_usd for t in self.targets]
        return st.median(vals) if vals else None

    @property
    def newest_age_days(self) -> float | None:
        stamps = [_days_between(t.observed_at, self.as_of) for t in self.targets]
        stamps = [d for d in stamps if d is not None]
        return min(stamps) if stamps else None

    @property
    def dispersion(self) -> float | None:
        """(p75 - p25) / median. Wide dispersion is a fact about the name, not
        a reason to drop anything -- it is reported so a caller can weigh it."""
        vals = sorted(t.target_usd for t in self.targets)
        med = self.median_target
        if len(vals) < 4 or not med:
            return None
        q1 = vals[len(vals) // 4]
        q3 = vals[(3 * len(vals)) // 4]
        return (q3 - q1) / med

    @property
    def split_suspect(self) -> bool:
        """True when the window holds targets more than 5x apart.

        A split inside the window leaves pre- and post-split targets side by
        side and the ratio is then meaningless. It is FLAGGED rather than
        cleaned, because every cheap cleaning rule here is a filter on the same
        quantity the signal lives in.
        """
        vals = [t.target_usd for t in self.targets if t.target_usd > 0]
        return bool(vals) and max(vals) > 5.0 * min(vals)

    def rating_from_headlines(self) -> tuple[float, int] | None:
        """Mean rating score across firms, from the words in the headlines.

        The FALLBACK for condition (b): Finnhub's recommendation counts are the
        primary source and cover the large names well. They cover a 4-analyst
        biotech far less well, and those are the names Murat's rule is about.
        """
        by_firm: dict[str, float] = {}
        for t in self.targets:
            if t.rating_score is not None and t.firm:
                by_firm[t.firm] = t.rating_score        # a firm's latest wins
        if not by_firm:
            return None
        return st.mean(by_firm.values()), len(by_firm)

    def upside_ratio(self, price: float) -> float | None:
        med = self.median_target
        if not med or not price or price <= 0:
            return None
        return med / price


def _days_between(observed_at: str, as_of: str) -> float | None:
    try:
        a = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).total_seconds() / 86400.0


def parse_headline(title: str) -> tuple[str, float, str, float | None] | None:
    """(firm, target_usd, rating_word, rating_score) from one headline, or None.

    Returns None rather than a guess when the headline mentions a price target
    and no amount can be read -- the caller counts those, because a parser whose
    miss rate is invisible is a parser nobody can trust.
    """
    if not title or not _HAS_TARGET.search(title):
        return None
    tail = title[_HAS_TARGET.search(title).end():]
    m = _TO_AMT.search(tail) or _OF_AMT.search(tail) or _ANY_AMT.search(tail)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if amount <= 0:
        return None
    act = _ACTION.search(title)
    firm = (title[:act.start()] if act else title.split(" on ")[0]).strip(" ,-")
    rating = _RATING_RE.search(title)
    word = rating.group(1).lower() if rating else ""
    return firm, amount, word, _RATING_SCORE.get(word)


def panel(symbol: str, *, as_of: str | None = None, window_days: int = WINDOW_DAYS,
          rows: list[dict] | None = None) -> TargetPanel:
    """Every target for `symbol` that was KNOWABLE by `as_of`, inside the window.

    `as_of` is passed to `corpus.read` as the point-in-time bound, so this is
    replayable at any past date and cannot see a target published after the
    decision it is asked about. That is the whole reason the corpus carries two
    timestamps.
    """
    sym = str(symbol or "").strip().upper()
    now = as_of or datetime.now(timezone.utc).isoformat()
    since = (datetime.fromisoformat(now.replace("Z", "+00:00"))
             - timedelta(days=window_days)).date().isoformat()
    if rows is None:
        from alpha.sources import corpus
        rows = corpus.read(kinds=["news"], symbols=[sym], since=since, as_of=now)
    out = TargetPanel(symbol=sym, as_of=now, window_days=window_days)
    seen: set[tuple] = set()
    for row in rows:
        title = str(row.get("title") or "")
        if not _HAS_TARGET.search(title):
            continue
        syms = [str(s).upper() for s in (row.get("symbols") or [])]
        if syms != [sym]:
            # A headline naming two companies cannot be attributed to one of
            # them, and attributing it anyway is how a target lands on the
            # wrong ticker. One row in 1,575 -- named, not silently kept.
            out.dropped_multi_symbol += 1
            continue
        parsed = parse_headline(title)
        if parsed is None:
            out.dropped_no_amount += 1
            continue
        firm, amount, word, score = parsed
        key = (firm.lower(), round(amount, 2), str(row.get("observed_at"))[:10])
        if key in seen:
            continue                       # the same note carried by two wires
        seen.add(key)
        out.targets.append(Target(symbol=sym, firm=firm, target_usd=amount,
                                  rating_word=word, rating_score=score,
                                  observed_at=str(row.get("observed_at") or ""),
                                  title=title, source=str(row.get("source") or "")))
    out.targets.sort(key=lambda t: t.observed_at)
    return out


def consensus_rating(rec: dict) -> tuple[float, int] | None:
    """(rating on Murat's 1-5 scale, coverage) from Finnhub recommendation counts.

    FIVE IS BEST here, matching his ">= 4.1 / 5 (Buy-Strong Buy)". The vendor
    convention that puts 1 at Strong Buy is the other one; using it with a
    ">= 4.1" bar would select the names the street hates.
    """
    counts = {k: int(rec.get(k) or 0) for k in
              ("strongBuy", "buy", "hold", "sell", "strongSell")}
    total = sum(counts.values())
    if total <= 0:
        return None
    score = (5 * counts["strongBuy"] + 4 * counts["buy"] + 3 * counts["hold"]
             + 2 * counts["sell"] + 1 * counts["strongSell"]) / total
    return score, total


def conditions(symbol: str, *, price: float | None, rec: dict | None = None,
               as_of: str | None = None, rows: list[dict] | None = None) -> dict:
    """Conditions (a) and (b) of Murat's rule, each with its provenance.

    Every value carries WHERE it came from. A `pass` whose source is not named
    is the kind of number that ends up in prose and cannot be reproduced -- the
    parent project's `corr = 0.516`.
    """
    pan = panel(symbol, as_of=as_of, rows=rows)
    out: dict = {"symbol": pan.symbol, "as_of": pan.as_of}

    # -- (a) upside ratio --------------------------------------------------
    ratio = pan.upside_ratio(price) if price else None
    if ratio is None or pan.n_firms < MIN_FIRMS:
        out["upside_ratio"] = "unknown"
        out["upside_detail"] = {
            "status": ("NO_PRICE" if not price else
                       "NO_TARGETS" if not pan.targets else
                       f"THIN: {pan.n_firms} firm(s), {MIN_FIRMS} required"),
            "n_targets": len(pan.targets), "n_firms": pan.n_firms,
            "dropped_no_amount": pan.dropped_no_amount,
            "dropped_multi_symbol": pan.dropped_multi_symbol,
        }
    else:
        out["upside_ratio"] = "pass" if ratio >= UPSIDE_BAR else "fail"
        out["upside_detail"] = {
            "status": "HEADLINE_EXTRACTED", "ratio": round(ratio, 3), "bar": UPSIDE_BAR,
            "median_target_usd": pan.median_target, "price": price,
            "n_targets": len(pan.targets), "n_firms": pan.n_firms,
            "firms": pan.firms[:12],
            "newest_age_days": (round(pan.newest_age_days, 1)
                                if pan.newest_age_days is not None else None),
            "dispersion": (round(pan.dispersion, 3) if pan.dispersion is not None else None),
            "split_suspect": pan.split_suspect,
            "window_days": pan.window_days,
            "dropped_no_amount": pan.dropped_no_amount,
        }
        if pan.split_suspect:
            out["upside_detail"]["warning"] = (
                "targets in this window are more than 5x apart -- a split or a "
                "restatement is likely and the ratio may be meaningless. Flagged, "
                "not cleaned: every cheap cleaning rule here filters the tail the "
                "rule is looking for.")

    # -- (b) consensus rating ----------------------------------------------
    primary = consensus_rating(rec) if rec else None
    fallback = pan.rating_from_headlines()
    if primary:
        score, n = primary
        out["rating"] = "pass" if score >= RATING_BAR else "fail"
        out["rating_detail"] = {"status": "FINNHUB_RECOMMENDATION_COUNTS",
                                "rating": round(score, 2), "bar": RATING_BAR,
                                "coverage": n, "scale": "5 = Strong Buy"}
    elif fallback:
        score, n = fallback
        # NOT scored against RATING_BAR -- see HEADLINE_FAIL_AT. The words vote
        # only where no plausible offset could rescue the name.
        out["rating"] = "fail" if score <= HEADLINE_FAIL_AT else "unknown"
        out["rating_detail"] = {
            "status": ("HEADLINE_RATING_WORDS" if out["rating"] == "fail"
                       else "SCALE_NOT_COMPARABLE"),
            "rating": round(score, 2), "n_firms": n, "scale": "5 = Strong Buy",
            "fail_at": HEADLINE_FAIL_AT, "murat_bar": RATING_BAR,
            "note": ("a mean of the rating WORDS each firm last used, on a scale that is NOT "
                     f"Finnhub's: measured -0.27 against the counts on the 5 names carrying "
                     f"both, where 5 of 5 clear {RATING_BAR} on the counts and 0 of 5 clear it "
                     "on the words. Reported, not voted, unless it is at or below "
                     f"{HEADLINE_FAIL_AT} (hold or worse), which fails on any scale.")}
    else:
        out["rating"] = "unknown"
        out["rating_detail"] = {"status": "NO_COUNTS_AND_NO_RATED_HEADLINES"}
    return out
