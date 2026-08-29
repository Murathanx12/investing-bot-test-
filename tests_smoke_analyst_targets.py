"""Conditions (a) and (b) of Murat's rule, measured rather than asked.

Run: python tests_smoke_analyst_targets.py  (also executed by tests_smoke.py)

The handoff recorded both as structurally unknown "because no target-price
source is wired". (b) was never blocked -- a 1-5 consensus rating is a weighted
mean of recommendation counts, and those are free and already captured. (a) was
blocked at the VENDOR and open in the corpus, which carries 2,368 dated broker
notes in a regular form. These pin the parser, the scale (five is best -- the
opposite of the vendor convention, and getting it backwards inverts the whole
screen), the point-in-time filter, and every state that must stay `unknown`.
"""
from __future__ import annotations

import os

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import analyst_targets as at


def row(title, symbols=("AMD",), observed="2026-08-20T12:00:00+00:00", source="benzinga"):
    return {"title": title, "symbols": list(symbols), "observed_at": observed,
            "effective_at": observed[:10], "source": source, "kind": "news"}


print("\n-- the headline parser: firm, figure, rating word")
p = at.parse_headline("Stifel Maintains Buy on Advanced Micro Devices, Raises Price Target to $190")
check("firm, target and rating come out of a standard note",
      p and p[0] == "Stifel" and p[1] == 190.0 and p[2] == "buy", str(p))
p = at.parse_headline("Morgan Stanley Maintains Equal-Weight on AMD, Lowers Price Target From $200 To $168")
check("'From $200 To $168' takes the SECOND figure -- the new target",
      p and p[1] == 168.0, str(p))
p = at.parse_headline("Benchmark Maintains Buy on AMD, Raises Price Target to $210 From $180")
check("'to $210 From $180' takes the FIRST figure -- also the new target",
      p and p[1] == 210.0, str(p))
p = at.parse_headline("B of A Securities Initiates Coverage On Porch Group With Buy, Announces Price Target of $17")
check("'Price Target of $17' parses", p and p[1] == 17.0, str(p))
check("a comma-grouped figure parses",
      (at.parse_headline("X Maintains Buy on Y, Raises Price Target to $1,250") or (0, 0))[1] == 1250.0)
check("a headline with no price target is not a target", at.parse_headline("AMD beats on revenue") is None)
check("a price-target headline with NO figure returns None, never a guess",
      at.parse_headline("Analysts raise their price target after the print") is None)

print("\n-- the scale: FIVE is best, and it is the opposite of the vendor's")
check("strong buy is 5, not 1", at._RATING_SCORE["strong buy"] == 5.0)
check("strong sell is 1", at._RATING_SCORE["strong sell"] == 1.0)
check("'strong buy' is not matched as 'buy'",
      at.parse_headline("Firm Maintains Strong Buy on X, Raises Price Target to $10")[3] == 5.0)
check("equal-weight is a hold, not a buy", at._RATING_SCORE["equal-weight"] == 3.0)
check("Murat's bar sits between hold and buy", 3.0 < at.RATING_BAR < 4.5)

print("\n-- the consensus rating from recommendation counts")
mu = {"strongBuy": 18, "buy": 33, "hold": 4, "sell": 1, "strongSell": 0}
r = at.consensus_rating(mu)
check("MU 18/33/4/1/0 over 56 analysts -> 4.21, which PASSES 4.1",
      r and abs(r[0] - 4.2143) < 1e-3 and r[1] == 56, str(r))
check("no coverage at all is None, never 0.0 and never 3.0",
      at.consensus_rating({"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}) is None)
check("all strong sells -> 1.0", at.consensus_rating({"strongSell": 5})[0] == 1.0)
check("all strong buys -> 5.0", at.consensus_rating({"strongBuy": 5})[0] == 5.0)

print("\n-- the panel: dedupe, multi-symbol, and what cannot be read")
rows = [
    row("Stifel Maintains Buy on AMD, Raises Price Target to $190"),
    row("Stifel Maintains Buy on AMD, Raises Price Target to $190"),          # same note, two wires
    row("Barclays Maintains Overweight on AMD, Raises Price Target to $210"),
    row("Analysts Raise Price Targets across chips", symbols=("AMD", "MU")),   # cannot be attributed
    row("Truist Maintains Hold on AMD, Price Target unchanged"),               # no figure
    row("AMD beats on revenue"),                                              # not a target note
]
pan = at.panel("AMD", as_of="2026-08-25T00:00:00+00:00", rows=rows)
check("the duplicate note is counted once", len(pan.targets) == 2, str(len(pan.targets)))
check("two distinct firms", pan.n_firms == 2 and pan.firms == ["Barclays", "Stifel"], str(pan.firms))
check("the median is the median of the targets", pan.median_target == 200.0, str(pan.median_target))
check("a two-symbol headline is DROPPED and counted, not attributed",
      pan.dropped_multi_symbol == 1, str(pan.dropped_multi_symbol))
check("a target note with no figure is counted as unread, not skipped in silence",
      pan.dropped_no_amount == 1, str(pan.dropped_no_amount))
check("age of the newest note is measured against as_of",
      pan.newest_age_days is not None and 4.4 < pan.newest_age_days < 4.6,
      str(pan.newest_age_days))

print("\n-- POINT IN TIME: a note published after the decision is not in the panel")
rows_pit = rows + [row("Goldman Sachs Maintains Buy on AMD, Raises Price Target to $400",
                       observed="2026-08-27T12:00:00+00:00")]
early = at.panel("AMD", as_of="2026-08-25T00:00:00+00:00", rows=[
    r for r in rows_pit if r["observed_at"] <= "2026-08-25T00:00:00+00:00"])
late = at.panel("AMD", as_of="2026-08-28T00:00:00+00:00", rows=rows_pit)
check("the later note is absent from the earlier panel", early.n_firms == 2, str(early.firms))
check("and present in the later one", late.n_firms == 3, str(late.firms))
check("so the median moves only after the note was knowable",
      early.median_target == 200.0 and late.median_target == 210.0,
      f"{early.median_target} -> {late.median_target}")

print("\n-- a split is FLAGGED, never quietly cleaned")
split_rows = [row("A Maintains Buy on X, Raises Price Target to $200", symbols=("X",)),
              row("B Maintains Buy on X, Raises Price Target to $20", symbols=("X",)),
              row("C Maintains Buy on X, Raises Price Target to $21", symbols=("X",))]
sp = at.panel("X", as_of="2026-08-25T00:00:00+00:00", rows=split_rows)
check("targets more than 5x apart set split_suspect", sp.split_suspect, str([t.target_usd for t in sp.targets]))
check("and NOTHING was dropped -- a magnitude filter would delete the tail the rule wants",
      len(sp.targets) == 3, str(len(sp.targets)))

print("\n-- conditions(): pass, fail, and the states that must stay unknown")
c = at.conditions("AMD", price=100.0, rec=mu, as_of="2026-08-25T00:00:00+00:00", rows=rows)
check("target 200 on a price of 100 -> ratio 2.0 -> (a) PASSES",
      c["upside_ratio"] == "pass" and c["upside_detail"]["ratio"] == 2.0, str(c["upside_detail"].get("ratio")))
check("(a) names its source", c["upside_detail"]["status"] == "HEADLINE_EXTRACTED")
check("(b) passes from the counts and names ITS source",
      c["rating"] == "pass" and c["rating_detail"]["status"] == "FINNHUB_RECOMMENDATION_COUNTS")
c = at.conditions("AMD", price=200.0, rec=mu, as_of="2026-08-25T00:00:00+00:00", rows=rows)
check("the same targets on a price of 200 -> ratio 1.0 -> (a) FAILS",
      c["upside_ratio"] == "fail", str(c["upside_detail"].get("ratio")))
c = at.conditions("AMD", price=None, rec=mu, as_of="2026-08-25T00:00:00+00:00", rows=rows)
check("no price -> (a) unknown, and the status SAYS no price",
      c["upside_ratio"] == "unknown" and c["upside_detail"]["status"] == "NO_PRICE")
c = at.conditions("AMD", price=100.0, rec=mu, as_of="2026-08-25T00:00:00+00:00",
                  rows=[rows[0]])
check("ONE firm is an opinion -> (a) unknown, status THIN",
      c["upside_ratio"] == "unknown" and c["upside_detail"]["status"].startswith("THIN"),
      c["upside_detail"]["status"])
c = at.conditions("AMD", price=100.0, rec=None, as_of="2026-08-25T00:00:00+00:00", rows=rows)
check("no counts -> (b) reads the rating WORDS and says the scale is not comparable",
      c["rating_detail"]["status"] == "SCALE_NOT_COMPARABLE", str(c["rating_detail"]["status"]))
check("buy(4) + overweight(4) -> 4.0, and that is UNKNOWN, not a fail against 4.1 "
      "(0 of 5 dual-source names clear 4.1 on the words; the bar does not travel)",
      c["rating"] == "unknown" and abs(c["rating_detail"]["rating"] - 4.0) < 1e-9,
      f"{c['rating']} @ {c['rating_detail'].get('rating')}")
c_bad = at.conditions("AMD", price=100.0, rec=None, as_of="2026-08-25T00:00:00+00:00",
                      rows=[row("A Maintains Sell on AMD, Lowers Price Target to $10"),
                            row("B Maintains Hold on AMD, Lowers Price Target to $12")])
check("but HOLD-or-worse across firms still FAILS -- no offset rescues 2.5",
      c_bad["rating"] == "fail" and c_bad["rating_detail"]["status"] == "HEADLINE_RATING_WORDS",
      f"{c_bad['rating']} @ {c_bad['rating_detail'].get('rating')}")
c = at.conditions("ZZZZ", price=100.0, rec=None, as_of="2026-08-25T00:00:00+00:00", rows=[])
check("nothing at all -> both unknown, neither invented",
      c["upside_ratio"] == "unknown" and c["rating"] == "unknown"
      and c["upside_detail"]["status"] == "NO_TARGETS")

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
