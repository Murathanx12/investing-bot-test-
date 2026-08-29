"""Smoke checks for NEWS->NUMBERS (`alpha/sources/features.py`). No network, synthetic rows.

Run: python run_tests.py -k features

Pinned, in order of what a regression would cost:
1. POINT IN TIME -- a row observed after `day` never counts, whatever its effective date;
2. attention_z is positive and large for a 6-items-this-week vs 2-a-week baseline;
3. novelty is 1.0 for unseen text and ~0 for a repeat (TF-IDF, the offline backend);
4. the event classifier lands 12 fixture titles;
5. lexicon sign: "beats and raises" > 0 > "misses and cuts guidance";
6. nulls stay null -- no bars, no rows, no panel => None, and `derivable` says so;
7. rank_ic on a monotone panel is ~1.0, and its bootstrap CI contains it.
"""
from __future__ import annotations

import os
import tempfile

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


os.environ.setdefault("AAT_STATE_DIR", tempfile.mkdtemp(prefix="aat_features_test_"))

from alpha.sources import features                                     # noqa: E402

DAY = "2026-03-10"


def row(title, observed, *, body="", source="alpaca:benzinga", sym="XYZ", tense="past",
        effective=None, kind="news", url=""):
    return {"kind": kind, "tense": tense, "title": title, "body": body, "source": source,
            "observed_at": observed, "effective_at": effective or observed[:10],
            "symbols": [sym], "url": url}


# ------------------------------------------------------------------- 1. PIT
print("\n-- point in time")
rows = [
    row("Old news", "2026-03-09T12:00:00Z"),
    row("Today news", "2026-03-10T15:00:00Z"),
    row("Tomorrow news, effective today", "2026-03-11T01:00:00Z", effective="2026-03-10"),
    row("Late tonight", "2026-03-10T23:59:59Z"),
    row("Just after midnight", "2026-03-11T00:00:00Z"),
]
f = features.daily_features("XYZ", DAY, rows)
check("n_items_1d counts only rows observed on the day", f["n_items_1d"] == 2, str(f["n_items_1d"]))
check("n_items_5d excludes rows observed after 23:59:59Z", f["n_items_5d"] == 3, str(f["n_items_5d"]))
check("a row effective today but observed tomorrow never counts",
      all("Tomorrow" not in r["title"] for r in features.observed_by(rows, DAY)))

fut = rows + [row("XYZ Q1 earnings", "2026-03-01T09:00:00Z", tense="future", effective="2026-03-20", kind="earnings"),
              row("XYZ PDUFA", "2026-03-11T09:00:00Z", tense="future", effective="2026-03-12", kind="clinical")]
f = features.daily_features("XYZ", DAY, fut)
check("days_to_next_catalyst uses only catalysts OBSERVED by day (10, not 2)",
      f["days_to_next_catalyst"] == 10, str(f["days_to_next_catalyst"]))

# ------------------------------------------------------------ 2. attention_z
print("\n-- attention")
from datetime import date, timedelta                                   # noqa: E402
base = []
end = date.fromisoformat(DAY)
for back in range(6, 95):
    if back % 7 in (0, 3):
        base.append(row(f"routine {back}", (end - timedelta(days=back)).isoformat() + "T12:00:00Z"))
burst = [row(f"burst {i}", (end - timedelta(days=i % 5)).isoformat() + "T12:00:00Z") for i in range(6)]
f = features.daily_features("XYZ", DAY, base + burst)
check("baseline ~2/week", f["coverage_baseline_90d"] is not None and 0.2 < f["coverage_baseline_90d"] < 0.35,
      str(f["coverage_baseline_90d"]))
check("attention_z positive and large for 6 vs 2/week", f["attention_z"] is not None and f["attention_z"] > 2.5,
      str(f["attention_z"]))
f2 = features.daily_features("XYZ", DAY, base)
check("attention_z negative with no burst", f2["attention_z"] is not None and f2["attention_z"] < 0, str(f2["attention_z"]))
check("n_sources_5d and source_independence derive from the publisher",
      f["n_sources_5d"] == 1 and abs(f["source_independence"] - 1 / 6) < 1e-9)
mixed = burst[:3] + [row("w", burst[3]["observed_at"], source="finnhub:Yahoo"),
                     row("x", burst[4]["observed_at"], source="finnhub:Benzinga"),
                     row("y", burst[5]["observed_at"], source="finnhub:news", url="https://www.reuters.com/a")]
f3 = features.daily_features("XYZ", DAY, mixed, base)
check("alpaca:benzinga and finnhub:Benzinga are ONE publisher; URL host is a fallback",
      f3["n_sources_5d"] == 3, str(f3["n_sources_5d"]))
check("publisher('finnhub:Yahoo') == 'yahoo'", features.publisher(mixed[3]) == "yahoo")
check("publisher falls back to url host", features.publisher(mixed[5]) == "reuters.com")

# ---------------------------------------------------------------- 3. novelty
print("\n-- novelty (tfidf backend, offline)")
emb = features.Embedder.tfidf()
prior = [row("Company reports quarterly results", (end - timedelta(days=30)).isoformat() + "T12:00:00Z"),
         row("Analyst maintains buy rating", (end - timedelta(days=20)).isoformat() + "T12:00:00Z")]
repeat = [row("Company reports quarterly results", DAY + "T12:00:00Z")]
unseen = [row("Zebra crossing photon lattice", DAY + "T12:00:00Z")]
idx = features.NoveltyIndex(prior + repeat, emb)
check("repeat headline novelty ~0", idx.novelty(DAY) is not None and idx.novelty(DAY) < 0.05, str(idx.novelty(DAY)))
idx2 = features.NoveltyIndex(prior + unseen, emb)
check("unseen headline novelty == 1.0", idx2.novelty(DAY) is not None and abs(idx2.novelty(DAY) - 1.0) < 1e-6,
      str(idx2.novelty(DAY)))
idx3 = features.NoveltyIndex(unseen, emb)
check("no prior titles -> novelty null (not 1.0 by default)", idx3.novelty(DAY) is None)
later = [row("Company reports quarterly results", "2026-03-12T12:00:00Z")]
idx4 = features.NoveltyIndex(later + repeat, emb)
check("a prior title observed AFTER day does not feed novelty", idx4.novelty(DAY) is None)
f = features.daily_features("XYZ", DAY, prior + repeat, novelty=idx)
check("daily_features carries novelty_5d from the index", f["novelty_5d"] is not None and f["novelty_5d"] < 0.05)
check("Embedder.tfidf names its backend", emb.backend == "tfidf")

# ------------------------------------------------------------ 4. classifier
print("\n-- event classifier")
fixtures = [
    ("Nvidia Reports Record Q2 Revenue, EPS Beats Estimates", "earnings"),
    ("HubSpot Raises Full-Year Guidance After Strong Quarter", "guidance"),
    ("Stifel Maintains Buy on AMD, Raises Price Target to $190", "analyst_rating"),
    ("Pfizer To Acquire Metsera In $4.9B Deal", "m_and_a"),
    ("Intellia Reports Positive Topline Phase 3 Data For Nex-z", "clinical"),
    ("FDA Approves Scholar Rock's Apitegromab", "regulatory"),
    ("AMSC Awarded $75M Navy Contract For Ship Protection Systems", "contract"),
    ("Marvell Unveils New Custom AI Chip Platform", "product"),
    ("DraftKings Faces Class Action Lawsuit Over Promotions", "legal"),
    ("Fed Signals Rate Cut As Inflation Cools", "macro"),
    ("Solid Power CEO Buys 50,000 Shares In Open Market Purchase", "insider"),
    ("Kyverna Receives Complete Response Letter From FDA", "regulatory"),
]
hits = 0
for title, want in fixtures:
    got = features.classify_title(title)
    ok = want in got
    hits += ok
    if not ok:
        print(f"       miss: {title!r} -> {got}")
check("classifier hits 12/12 fixture titles", hits == 12, f"{hits}/12")
check("CRL also reads as clinical", "clinical" in features.classify_title(fixtures[-1][0]))
check("a bare title classifies to nothing", features.classify_title("Shares Move Today") == [])
check("classifier output is a subset of EVENT_TYPES",
      all(k in features.EVENT_TYPES for t, _ in fixtures for k in features.classify_title(t)))

# -------------------------------------------------------------- 5. lexicon
print("\n-- lexicon")
up, _, _ = features.lexicon_score("Company beats estimates and raises guidance; strong growth")
dn, _, _ = features.lexicon_score("Company misses estimates and cuts guidance; weak demand, downgrade")
check("'beats and raises' scores positive", up is not None and up > 0, str(up))
check("'misses and cuts guidance' scores negative", dn is not None and dn < 0, str(dn))
neg, _, _ = features.lexicon_score("Company did not achieve growth")
check("a negator within three tokens flips the hit", neg is not None and neg < 0, str(neg))
crl, _, _ = features.lexicon_score("Receives Complete Response Letter")
check("CRL is negative", crl is not None and crl < 0)
none, p, n = features.lexicon_score("Shares trade on Tuesday")
check("no lexicon hit -> None, not 0", none is None and p == 0 and n == 0)
f = features.daily_features("XYZ", DAY, [row("Beats estimates, raises guidance", DAY + "T10:00:00Z")])
check("sentiment_lex_5d positive on the row", f["sentiment_lex_5d"] is not None and f["sentiment_lex_5d"] > 0)
check("sentiment_hits_5d counts", f["sentiment_hits_5d"] and f["sentiment_hits_5d"] >= 2)

# ----------------------------------------------------------------- 6. nulls
print("\n-- nulls stay null")
f = features.daily_features("XYZ", DAY, [])
for k in features.FEATURE_FIELDS:
    if f[k] is not None:
        check(f"{k} null with no inputs", False, str(f[k]))
        break
else:
    check("every field null with no inputs", True)
check("derivable says none", not any(f["derivable"].values()))
f = features.daily_features("XYZ", DAY, [row("news", DAY + "T10:00:00Z")])
check("rows but no bars -> price fields null", f["ret_5d"] is None and f["dollar_volume_20d"] is None)
check("one row, no baseline history -> baseline/attention_z null",
      f["coverage_baseline_90d"] is None and f["attention_z"] is None)
check("n_items derivable, target_ratio not", f["derivable"]["n_items_1d"] and not f["derivable"]["target_ratio"])
check("rating null without a panel", f["rating_counts_mean"] is None)
f = features.daily_features("XYZ", DAY, [], rating_rec={"strongBuy": 2, "buy": 2, "hold": 0, "sell": 0, "strongSell": 0})
check("rating_counts_mean from the panel counts (five is best)", f["rating_counts_mean"] == 4.5 and f["rating_coverage"] == 4)

# ------------------------------------------------------------- price context
print("\n-- price context from bars")
bars = []
px = 100.0
for i in range(70):
    d = date(2026, 1, 1) + timedelta(days=i)
    px *= 1.01
    bars.append({"t": d.isoformat() + "T05:00:00Z", "o": px * 0.99, "h": px * 1.02, "l": px * 0.98, "c": px, "v": 1000})
last = bars[-1]["t"][:10]
pc = features.price_context(bars, last)
check("ret_5d ~ 1.01^5-1", abs(pc["ret_5d"] - (1.01 ** 5 - 1)) < 1e-9, str(pc["ret_5d"]))
check("drawdown_from_60d_high == 0 at a new high", abs(pc["drawdown_from_60d_high"]) < 1e-12)
check("realised_vol_20d ~ 0 for a constant drift", pc["realised_vol_20d"] is not None and pc["realised_vol_20d"] < 1e-6)
check("dollar_volume_20d derivable", pc["dollar_volume_20d"] is not None)
pc2 = features.price_context(bars, "2026-06-01")
check("a stale last bar under a later day -> null, not yesterday's numbers", pc2["ret_5d"] is None)
check("too few bars -> null", features.price_context(bars[:3], bars[2]["t"][:10])["ret_5d"] is None)

# analyst targets through Opus's extraction
tgt = [row("Stifel Maintains Buy on XYZ, Raises Price Target to $150", (end - timedelta(days=3)).isoformat() + "T10:00:00Z"),
       row("Piper Sandler Reiterates Overweight on XYZ, Price Target $130", (end - timedelta(days=10)).isoformat() + "T10:00:00Z")]
b2 = [{"t": DAY + "T05:00:00Z", "o": 99.0, "h": 101, "l": 98, "c": 100.0, "v": 10}]
f = features.daily_features("XYZ", DAY, tgt, bars=b2)
check("target_ratio = median target / close (140/100)", f["target_ratio"] == 1.4, str(f["target_ratio"]))
check("n_target_notes_90d == 2, firms == 2", f["n_target_notes_90d"] == 2 and f["n_target_firms_90d"] == 2)
f = features.daily_features("XYZ", DAY, tgt[:1], bars=b2)
check("one firm is an opinion: target_ratio null below MIN_FIRMS", f["target_ratio"] is None and f["n_target_notes_90d"] == 1)
f = features.daily_features("XYZ", DAY, tgt)
check("no close -> target_ratio null even with two firms", f["target_ratio"] is None)

# -------------------------------------------------------------------- 7. IC
print("\n-- rank IC")
import random                                                          # noqa: E402
rnd = random.Random(3)
xs = [rnd.random() for _ in range(300)]
ys = [math_x * 2.0 + 1.0 for math_x in xs]
months = [f"2026-{1 + i % 6:02d}" for i in range(300)]
r = features.rank_ic(xs, ys, months, n_boot=100)
check("monotone panel -> IC ~ 1.0", r["ic"] is not None and abs(r["ic"] - 1.0) < 1e-9, str(r["ic"]))
check("n and n_blocks reported", r["n"] == 300 and r["n_blocks"] == 6)
check("bootstrap CI contains the IC", r["ci_lo"] is not None and r["ci_lo"] <= 1.0 <= r["ci_hi"] + 1e-9)
ys_neg = [-v for v in ys]
check("reversed panel -> IC ~ -1.0", abs(features.rank_ic(xs, ys_neg, months, n_boot=10)["ic"] + 1.0) < 1e-9)
noise = [rnd.random() for _ in range(300)]
rn = features.rank_ic(xs, noise, months, n_boot=200)
check("noise -> |IC| small and CI straddles zero", abs(rn["ic"]) < 0.15 and rn["ci_lo"] < 0 < rn["ci_hi"], str(rn))
check("spearman refuses n<3", features.spearman([1, 2], [1, 2]) is None)
check("spearman averages ties", abs(features.spearman([1, 1, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-9)
check("numeric_fields flattens event counts",
      "ev_earnings_20d" in features.numeric_fields({"event_type_counts_20d": {"earnings": 2}, "ret_5d": 0.1}))

print(f"\n{len(fails)} failure(s)" + (": " + ", ".join(fails) if fails else ""))
raise SystemExit(1 if fails else 0)
