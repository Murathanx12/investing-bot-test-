"""NEWSMAKERS: the day decides the universe, and raw article count must not rank it.

The digest used to build a fixed ~141-name list and ask the feed what had been
written about it. A name making news today was invisible unless it was already
on the list. These pin the inversion and, more importantly, the NORMALISATION --
because ranking on raw count is a mega-cap filter wearing a number, and Benzinga
files 1,566 items on NVDA against 3 on a small biotech.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from alpha import newsmakers as N

_fails: list[str] = []


def check(name: str, cond: bool, why: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        _fails.append(name)
        print(f"  FAIL {name}  {why}")


def _items(*specs):
    """(symbols, source, headline) -> feed items."""
    return [{"symbols": list(s), "source": src, "headline": h, "at": "2026-08-31T01:00:00Z"}
            for s, src, h in specs]


def test_crypto_and_junk_symbols_are_not_equities():
    for bad in ("BTCUSD", "ZECUSD", "USDT", "", "TOOLONGSYM", "BRK.B", "123"):
        check(f"{bad!r} is not tradeable", not N.is_tradeable_symbol(bad))
    for good in ("NVDA", "MU", "F", "WBUY"):
        check(f"{good} is tradeable", N.is_tradeable_symbol(good))


def test_a_market_wrap_tagging_fifteen_tickers_does_not_nominate_them_all():
    """A round-up tagged with fifteen names is not news about any one of them.
    It still counts, weighted down, or an index wrap would fill the universe."""
    wrap = _items((tuple("ABCDEFGHIJKLMNO"), "wire", "20 stocks moving today"))
    focused = _items((("MU",), "wire", "Micron raises guidance"))
    t = N.tally(wrap + focused)
    check("the wrap's names each weigh less than a focused story",
          t["A"]["weighted"] < t["MU"]["weighted"],
          f"{t['A']['weighted']} vs {t['MU']['weighted']}")
    check("but the wrap is still counted, not dropped", t["A"]["n_articles"] == 1)


def test_syndication_is_counted_as_corroboration_not_as_events():
    """Ten outlets republishing one wire is one event corroborated ten times."""
    t = N.tally(_items(*[(("XYZ",), f"outlet{i}", "Same story") for i in range(10)]))
    check("ten copies -> 10 articles", t["XYZ"]["n_articles"] == 10)
    check("ten copies -> 10 distinct sources counted apart",
          t["XYZ"]["n_sources"] == 10)


def test_raw_count_does_not_rank_a_megacap_above_a_quiet_name():
    """THE POINT. NVDA gets 40 articles every day; a biotech gets 4 today and
    normally 0. The biotech is the news."""
    today = N.tally(_items(*([(("NVDA",), "wire", "nvidia daily")] * 40
                             + [(("TINY",), "wire", "TINY wins FDA approval")] * 4)))
    baseline = {"NVDA": [40.0, 41.0, 39.0, 40.0, 38.0], "TINY": [0.0, 0.0, 1.0, 0.0, 0.0]}
    ranked = N.score(today, baseline)
    order = [r["symbol"] for r in ranked]
    check("the quiet name with 4 articles outranks the mega-cap with 40",
          order.index("TINY") < order.index("NVDA"), str(order))
    check("NVDA's own z is ~0 on a normal day",
          abs(ranked[order.index("NVDA")]["attention_z"]) < 1.5)


def test_a_flat_history_cannot_produce_an_infinite_z():
    """A name whose history is identical every day has sd 0. One extra article
    would be an infinite z, and it would top the list forever."""
    today = N.tally(_items((("FLAT",), "w", "h")))
    ranked = N.score(today, {"FLAT": [1.0, 1.0, 1.0, 1.0]})
    z = ranked[0]["attention_z"]
    check("a zero-variance history yields a finite z", z is not None and abs(z) < 100, str(z))


def test_a_name_we_have_never_seen_is_visible_not_last():
    """A never-covered name is precisely what we want to surface -- the
    coverage-initiation signal. Ranking it last rebuilds the fame filter."""
    today = N.tally(_items(*([(("KNOWN",), "w", "h")] * 5 + [(("NEWCO",), "w", "h")] * 3)))
    ranked = N.score(today, {"KNOWN": [5.0, 5.0, 5.0, 5.0]})
    by = {r["symbol"]: r for r in ranked}
    check("the unseen name is flagged NEW", by["NEWCO"]["is_new"] is True)
    check("and has no invented z", by["NEWCO"]["attention_z"] is None)
    check("and says why", "NEW" in by["NEWCO"]["basis"])
    order = [r["symbol"] for r in ranked]
    check("a NEW name is not automatically ranked last",
          order.index("NEWCO") <= order.index("KNOWN"), str(order))


def test_the_universe_is_news_first_and_says_where_each_name_came_from():
    ranked = N.score(N.tally(_items((("AAA",), "w", "h"), (("BBB",), "w", "h"))), {})
    uni = N.adaptive_universe(newsmakers=ranked, candidates=["CCC", "AAA"],
                              always=["SPY"], extra=["ZZZ"])
    check("news names come first", uni["symbols"][0] in ("AAA", "BBB"))
    check("candidates follow", "CCC" in uni["symbols"])
    check("index proxies are present", "SPY" in uni["symbols"])
    check("manual extras are present", "ZZZ" in uni["symbols"])
    check("no duplicates", len(uni["symbols"]) == len(set(uni["symbols"])))
    check("a name in BOTH news and candidates records both origins",
          "news" in uni["origin"]["AAA"] and "candidate" in uni["origin"]["AAA"],
          uni["origin"]["AAA"])
    check("every name has a stated origin",
          all(s in uni["origin"] for s in uni["symbols"]))


def test_the_universe_has_no_fixed_size():
    """`top_news=None` is the default: adaptive. The old failure was a constant."""
    small = N.score(N.tally(_items((("A",), "w", "h"))), {})
    # Ticker-shaped names: `S0` is not alpha and would be dropped by the
    # tradeable filter, so the test would measure the filter, not the ranking.
    import string
    many = [a + b + c for a in string.ascii_uppercase[:6]
            for b in string.ascii_uppercase[:6] for c in string.ascii_uppercase[:6]][:200]
    big = N.score(N.tally(_items(*[((m,), "w", "h") for m in many])), {})
    u1 = N.adaptive_universe(newsmakers=small, candidates=[], always=[])
    u2 = N.adaptive_universe(newsmakers=big, candidates=[], always=[])
    check("the universe grows with the day's news", u2["n_total"] > u1["n_total"] + 100,
          f"{u1['n_total']} vs {u2['n_total']}")
    capped = N.adaptive_universe(newsmakers=big, candidates=[], always=[], top_news=10)
    check("and can still be capped explicitly when asked", capped["n_news"] == 10)


def test_the_baseline_is_append_only_and_survives_a_bad_line():
    d = Path(tempfile.mkdtemp()) / "base.jsonl"
    N.append_baseline("2026-08-30", {"AAA": 3}, path=d)
    N.append_baseline("2026-08-31", {"AAA": 5, "BBB": 1}, path=d)
    with d.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")      # a truncated write must not erase history
    hist = N.load_baseline(d)
    check("both days are kept", hist["AAA"] == [3.0, 5.0], str(hist))
    check("a corrupt line is skipped, not fatal", hist["BBB"] == [1.0])
    check("a missing baseline file is an empty dict, not a crash",
          N.load_baseline(Path(tempfile.mkdtemp()) / "nope.jsonl") == {})


def test_a_feed_refusal_is_not_read_as_no_news():
    """A rate-limited page must not silently shrink the day's universe."""
    t = N.tally(_items((("AAA",), "w", "h")) + [{"refusal": "page 3: HTTPError 429"}])
    check("the refusal row is not counted as a symbol", set(t) == {"AAA"})


def _run_all() -> int:
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    print(f"\n-- NEWSMAKERS: news-first adaptive universe ({len(tests)} groups)")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:                                        # noqa: BLE001
            _fails.append(name)
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(_fails)} failures" + (": " + ", ".join(_fails) if _fails else ""))
    return 1 if _fails else 0


# Guard at the BOTTOM: `_run_all` reads globals() at call time.
if __name__ == "__main__":
    raise SystemExit(_run_all())
