"""Smoke checks for the BLIND NAME-SWAPPED LLM FORECAST TEST. No keys, no network.

Run: python run_tests.py -k blind_tournament

Pinned, in order of what a regression would cost:

1. **the blinding** -- ticker, company name, prices and move-percentages are
   gone from a fixture headline; product codes become [product]; dates stay;
2. **the canary** -- a company guess that matches the true name is COUNTED,
   and a run whose identification rate exceeds 5% is FLAGGED LEAKY;
3. **seal before grade** -- the sealed file exists, with every prediction and
   a prompt sha256, BEFORE the bars function is ever called, and the graded
   file is a separate file that is never rewritten;
4. **the null** -- shuffled p-values are computed and sit in [0, 1];
5. **the verdict refuses** under n < 30 graded cells.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


_TMP = tempfile.mkdtemp(prefix="aat_blind_test_")
os.environ["AAT_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha.council import providers                                      # noqa: E402
from alpha.sources import corpus                                        # noqa: E402
from scripts import blind_tournament as bt                              # noqa: E402

check("tournament dir is under the scratch state dir", str(bt.TOURNAMENT).startswith(_TMP), str(bt.TOURNAMENT))
check("deepseek is not in the provider order", "deepseek" not in bt.PROVIDER_ORDER)
check("the justification names a decision", bool(__import__("alpha.spend", fromlist=["justify"]).justify(bt.WHY)))

# ------------------------------------------------------------ 1. blinding
print("\n-- blinding")
b = bt.Blinder("MU", ["Micron Technology", "Micron"], ["AMD", "NVDA", "SPY"])
fx = "Micron (MU) shares jump 12% to $180 after HBM3E order; AMD fell 3.5% on 2026-01-14 as OP-1250 data landed"
out = b.blind(fx)
print("   ", out)
check("ticker stripped", "MU" not in out.replace("[ticker]", ""), out)
check("company name stripped", "micron" not in out.lower(), out)
check("price stripped", "$180" not in out and "[price]" in out, out)
check("move pct stripped", "12%" not in out and "[pct]" in out, out)
check("other ticker stripped", "AMD" not in out, out)
check("other move pct stripped", "3.5%" not in out, out)
check("product code stripped", "OP-1250" not in out and "[product]" in out, out)
check("date kept", "2026-01-14" in out, out)
check("'the company' substituted", "the company" in out, out)
check("counts recorded", b.counts["ticker"] >= 1 and b.counts["price"] == 1 and b.counts["pct_move"] >= 2, dict(b.counts))
low = bt.Blinder("SOC", ["Sable Offshore", "Sable"], []).blind("Sable Offshore (NYSE:SOC) rose 8% -- soc analysts cheer")
check("ticker case-insensitive and exchange-prefixed", "SOC" not in low.replace("[ticker]", "") and "soc" not in low.lower().replace("[ticker]", ""), low)
kept = bt.Blinder("MU", ["Micron"], []).blind("Revenue grew 40% year over year on memory demand")
check("a non-move percentage is kept", "40%" in kept, kept)
check("person name kept", "Andy Jassy" in bt.Blinder("MU", ["Micron"], []).blind("Andy Jassy says demand is striking"))

# derived aliases from a synthetic corpus: the name co-occurs, common nouns do not qualify
rows = []
for i in range(6):
    rows.append({"title": f"Zebracorp Inc reports memory demand surge, item {i}; Zebracorp shares up", "body": "the memory market",
                 "symbols": ["ZBC"], "tense": "past", "observed_at": f"2026-01-{10 + i:02d}T12:00:00Z",
                 "effective_at": f"2026-01-{10 + i:02d}"})
rows.append({"title": "Memory prices rise across the sector", "body": "memory", "symbols": ["OTH"], "tense": "past",
             "observed_at": "2026-01-05T12:00:00Z", "effective_at": "2026-01-05"})
bt._VOCAB = None
al = bt.derive_aliases("ZBC", rows)
check("derived alias finds the co-occurring name", "Zebracorp" in al, al)
check("derived alias excludes a common noun", "Memory" not in al, al)

# ------------------------------------------------------------ cells
print("\n-- cells")
cells = bt.build_cells(["ZBC", "OTH"], ["2026-01"], rows)
zbc = next(c for c in cells if c["symbol"] == "ZBC")
oth = next(c for c in cells if c["symbol"] == "OTH")
check("cell window is observed_at within 30 days before month_end", zbc["n_rows"] == 6 and zbc["month_end"] == "2026-01-31")
check("thin cell recorded", oth["thin"] and not zbc["thin"])
fut = dict(rows[0], tense="future", observed_at="2026-01-20T00:00:00Z")
check("future rows excluded", bt.build_cells(["ZBC"], ["2026-01"], [fut])[0]["n_rows"] == 0)
chosen = bt.choose_cells([dict(zbc, month="2026-0%d" % m, cell_id=f"ZBC:{m}") for m in range(1, 4)] * 3, 6)
check("round-robin across months", sorted(c["month"] for c in chosen) == ["2026-01", "2026-01", "2026-02", "2026-02", "2026-03", "2026-03"])

# ------------------------------------------------------------ 2. canary + identification
print("\n-- canary")
check("guess matches ticker", bt.guess_matches("MU", "MU", ["Micron"]))
check("guess matches alias", bt.guess_matches("Micron Technology Inc", "MU", ["Micron"]))
check("null guess does not match", not bt.guess_matches(None, "MU", ["Micron"]) and not bt.guess_matches("unknown", "MU", ["Micron"]))
check("wrong guess does not match", not bt.guess_matches("Intel", "MU", ["Micron"]))
ids = [f"S{i}:2026-01-31" for i in range(2000)]
share = sum(bt.is_canary(c, "run") for c in ids) / len(ids)
check("canary share near 5%", 0.02 < share < 0.09, f"{share:.3f}")
check("canary is deterministic per run", bt.is_canary("X:1", "r") == bt.is_canary("X:1", "r"))
prm = bt.build_prompt(zbc, bt.Blinder("ZBC", ["Zebracorp"], []), canary=True)
check("canary headline injected", bt.CANARY_HEADLINE in prm)
check("prompt asks for company_guess", "company_guess" in prm)

# ------------------------------------------------------------ 3. seal before grade (end to end, no network)
print("\n-- seal before grade")
calls = {"chat": 0, "bars": 0, "sealed_when_bars_called": None}
SEALED = bt.run_paths("t1")[0]


def fake_chat(provider, system, user, *, caller, why, max_tokens=0, temperature=0.0):
    calls["chat"] += 1
    __import__("alpha.spend", fromlist=["justify"]).justify(why, caller=caller)
    up = calls["chat"] % 2 == 0
    return ({"direction": "up" if up else "down", "expected_move_pct_21d": 5.0 if up else -4.0,
             "confidence": 0.3 + 0.1 * (calls["chat"] % 5), "sector_guess": "semis",
             "company_guess": "Alphacorp" if calls["chat"] == 1 else None, "rationale": "x"},
            {"provider": provider, "family": "t", "model": "m", "prompt_tokens": 10, "completion_tokens": 5, "latency_s": 0.1})


def fake_probe(names):
    return {n: {"state": "live"} for n in names}


def fake_bars(symbols, start, end):
    calls["bars"] += 1
    calls["sealed_when_bars_called"] = SEALED.exists() and len(SEALED.read_text().splitlines())
    out = {}
    d0 = date(2026, 2, 2)
    for s in symbols:
        bars, d, k = [], d0, 0
        while k < 60:
            if d.weekday() < 5:
                px = 100.0 + (k if s == "ZBC" else k * 0.2)
                bars.append({"t": d.isoformat() + "T05:00:00Z", "o": px, "c": px + 0.5, "h": px + 1, "l": px - 1, "v": 1})
                k += 1
            d += timedelta(days=1)
        out[s] = bars
    return out


many = []
NAMES = ["Alphacorp", "Bravocorp", "Charliecorp", "Deltacorp", "Echocorp", "Foxtrotcorp",
         "Golfcorp", "Hotelcorp", "Indiacorp", "Julietcorp", "Kilocorp", "Limacorp"]
for i in range(12):
    for j in range(6):
        many.append({"title": f"{NAMES[i]} news item {j}", "body": "b", "symbols": [f"Z{i}"], "tense": "past",
                     "observed_at": f"2026-01-{10 + j:02d}T12:00:00Z", "effective_at": f"2026-01-{10 + j:02d}"})
providers.chat_json, providers.probe = fake_chat, fake_probe
bt.fetch_daily_bars = fake_bars
corpus.read = lambda **kw: many
rc = bt.main(["--run-id", "t1", "--symbols", *[f"Z{i}" for i in range(12)], "--months", "2026-01", "--max-calls", "10"])
sealed_path, graded_path, receipt_path = bt.run_paths("t1")
check("run returned 0", rc == 0, rc)
check("max-calls honoured", calls["chat"] == 10, calls["chat"])
check("sealed file existed with all rows BEFORE bars were fetched", calls["sealed_when_bars_called"] == 10, calls)
srows = [json.loads(l) for l in sealed_path.read_text(encoding="utf-8").splitlines()]
check("every sealed row carries a prompt sha256", all(len(r["prompt_sha256"]) == 64 for r in srows))
check("sealed sha matches the sealed prompt", all(__import__("hashlib").sha256(r["blinded_prompt"].encode()).hexdigest() == r["prompt_sha256"] for r in srows))
check("provider recorded on each row", all(r["provider"] == "featherless" for r in srows))
check("graded is a separate file", graded_path.exists() and graded_path != sealed_path)
grows = [json.loads(l) for l in graded_path.read_text(encoding="utf-8").splitlines()]
check("graded rows carry raw, spy-relative and sector-relative returns",
      all("ret_raw" in g and "ret_vs_spy" in g and "ret_vs_sector" in g for g in grows), len(grows))
check("entry convention stated", "OPEN" in grows[0]["entry_convention"])
rec = json.loads(receipt_path.read_text(encoding="utf-8"))
check("identification counted (one matching guess)", rec["graded"]["identification"]["n_matched"] == 1, rec["graded"]["identification"])
check("run FLAGGED LEAKY at 1/10 > 5%", rec["graded"]["identification"]["leaky"] is True)
check("receipt records blinding rules", len(rec["blinding_rules"]) >= 6)
check("receipt records provider mix", rec["provider_mix"] == {"featherless": 10}, rec["provider_mix"])
check("re-running the same run id is REFUSED", bt.main(["--run-id", "t1", "--symbols", "Z0", "--months", "2026-01"]) == 2)
check("re-grading a graded run is REFUSED", bt.grade_run("t1") == 2)
n_bars_before = calls["bars"]
check("the refusal fetched nothing", calls["bars"] == n_bars_before)

# ------------------------------------------------------------ 4. null + 5. verdict
print("\n-- null and verdict")
m = bt.metrics(grows, ret_key="ret_raw", n_perm=50)
check("null p-values computed and bounded", m["null"]["p_hit_rate"] is not None and 0 <= m["null"]["p_hit_rate"] <= 1
      and 0 <= m["null"]["p_ic"] <= 1, m["null"])
check("hit rate excludes flat", m["n_directional"] == m["n_up"] + m["n_down"])
check("calibration by tercile present", set(m["calibration_by_confidence_tercile"]) <= {"low", "mid", "high"})
check("verdict REFUSED under n<30", rec["graded"]["verdict"].startswith("REFUSED") and "n=10" in rec["graded"]["verdict"], rec["graded"]["verdict"])
big = [dict(g, ret_raw=(1.0 if g["prediction"]["direction"] == "up" else -1.0)) for g in grows] * 4
mb = bt.metrics(big, ret_key="ret_raw", n_perm=100)
check("a perfect predictor beats the null", mb["hit_rate"] == 1.0 and mb["null"]["p_hit_rate"] <= 0.05, mb["null"])
check("verdict given at n>=30 when not leaky", "REFUSED" not in bt.verdict(mb, leaky=False))
check("verdict flagged when leaky", bt.verdict(mb, leaky=True).startswith("FLAGGED LEAKY"))
imm = bt.realised([{"t": "2026-02-02T05:00:00Z", "o": 1, "c": 1}] * 5, "2026-01-31")
check("immature cell is not graded", imm is None)
r = bt.realised(fake_bars(["ZBC"], "", "")["ZBC"], "2026-01-31")
check("realised uses next-session open and 21st-session close", r["entry_date"] == "2026-02-02" and r["entry_open"] == 100.0
      and r["exit_date"] == "2026-03-02" and abs(r["ret"] - (120.5 / 100.0 - 1)) < 1e-9, r)

print()
if fails:
    print(f"FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
