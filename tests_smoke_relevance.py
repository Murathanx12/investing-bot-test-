"""The relevance layer: the encoder's contract, the PIT join, and BH-FDR.

Run: python tests_smoke_relevance.py  (also executed by run_tests.py)

Two things are worth pinning here and nothing else is. First, that the LLM is
used as an ENCODER and never as a forecaster -- the prompt must not contain a
price, a return or a request for direction, because the moment it does, the
backtest downstream is grading the model's memory of 2025 rather than a feature.
Second, that the statistics do what their names say: a per-day tercile is not a
full-sample tercile, and BH-FDR is not "the smallest p wins".
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("AAT_ACCOUNT_ROLE", "dev")

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from scripts import news_relevance as nr          # noqa: E402
from scripts import relevance_ic as ric           # noqa: E402

print("\n-- the model is an ENCODER: it is never shown, nor asked for, an outcome")
prompt = (nr.SYSTEM + " " + json.dumps(nr.SCHEMA)).lower()
for banned in ("price target", "will the stock", "predict", "forecast", "return",
               "outperform", "buy", "sell"):
    # `predict` and `return` appear only inside the REFUSAL ("You never predict
    # prices, returns or direction"), which is the opposite of asking for one.
    if banned in ("predict", "return"):
        continue
    check(f"the prompt never asks for {banned!r}", banned not in prompt)
check("...and it says so explicitly", "never predict" in prompt)
check("the schema's answer space contains no direction field",
      set(nr.SCHEMA["json_schema"]["schema"]["required"]) ==
      {"role", "is_new_fact", "event_type", "expectation"})

print("\n-- a STRICT schema, because prose enums leaked in the measured run")
sch = nr.SCHEMA["json_schema"]
check("strict mode is on", sch["strict"] is True)
check("additionalProperties is refused", sch["schema"]["additionalProperties"] is False)
check("event_type is a closed enum", sch["schema"]["properties"]["event_type"]["enum"] == nr.EVENT_TYPES)
check("'none' is IN the enum, so 'not an event' is sayable",
      "none" in nr.EVENT_TYPES)
check("role has exactly the three answers", set(nr.ROLES) == {"subject", "mentioned", "absent"})

print("\n-- the key is found under either name Murat has used")
for name in ("AAT_OPENAI_API_KEY", "GTP_TOKEN"):
    saved = {k: os.environ.pop(k, None) for k in ("AAT_OPENAI_API_KEY", "GTP_TOKEN", "OPENAI_API_KEY")}
    os.environ[name] = "sk-test-123"
    try:
        check(f"{name} is accepted", nr._key() == "sk-test-123")
    finally:
        os.environ.pop(name, None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
saved = {k: os.environ.pop(k, None) for k in ("AAT_OPENAI_API_KEY", "GTP_TOKEN", "OPENAI_API_KEY")}
try:
    try:
        nr._key()
        check("no key REFUSES rather than calling with an empty bearer", False)
    except nr.RelevanceRefusal:
        check("no key REFUSES rather than calling with an empty bearer", True)
finally:
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v

print("\n-- the run is resumable BECAUSE it flushes, not because it intends to")
src = Path(nr.__file__).read_text(encoding="utf-8")
check("labels are flushed mid-run, not only at the end",
      "FLUSH_EVERY" in src and src.count("flush()") >= 3)
check("a spend CEILING exists and is not optional", nr.DEFAULT_MAX_USD <= 10.0)

print("\n-- BH-FDR is Benjamini-Hochberg, not 'the smallest p wins'")
check("nothing survives when every p is 1.0", not any(ric.bh_fdr([1.0] * 8, 0.10)))
check("everything survives when every p is 0", all(ric.bh_fdr([0.0] * 8, 0.10)))
# Classic BH: with m=4, q=0.10 the thresholds are .025 .05 .075 .10
keep = ric.bh_fdr([0.001, 0.04, 0.30, 0.90], 0.10)
check("the step-up accepts p=0.04 at rank 2 (0.04 <= 0.05)", keep[0] and keep[1], str(keep))
check("...and rejects the two large ones", not keep[2] and not keep[3], str(keep))
# The step-UP property: a later hypothesis clearing its line rescues earlier ones.
keep2 = ric.bh_fdr([0.02, 0.04], 0.10)
check("step-up rescues a p that fails its own line but sits below a passing one",
      all(keep2), str(keep2))
check("an empty family is not an error", ric.bh_fdr([], 0.10) == [])

print("\n-- the CI-implied p is an ORDERING device and behaves like one")
check("a CI straddling zero gives a large p", ric.boot_p(0.01, -0.05, 0.07) > 0.5)
check("a CI far from zero gives a small p", ric.boot_p(0.30, 0.25, 0.35) < 0.01)
check("a missing CI is p=1, never p=0", ric.boot_p(0.5, None, None) == 1.0)
check("a degenerate CI is p=1, never a divide-by-zero", ric.boot_p(0.5, 0.2, 0.2) == 1.0)

print("\n-- terciles are cut PER DAY; a full-sample quantile would be lookahead")
rows = []
for day, vals in (("2026-01-02", [1, 2, 3, 4, 5, 6, 7, 8, 9]),
                  ("2026-01-03", [100, 200, 300, 400, 500, 600, 700, 800, 900])):
    for i, v in enumerate(vals):
        rows.append({"day": day, "cond": {"realised_vol_20d": float(v)}, "f": {}, "t": {}})
ric.tercile_by_day(rows, "realised_vol_20d")
d1 = [r for r in rows if r["day"] == "2026-01-02"]
d2 = [r for r in rows if r["day"] == "2026-01-03"]
check("day 1's smallest value is 'low'", d1[0]["tc_realised_vol_20d"] == "low")
check("day 2's SMALLEST value is also 'low' -- 100 is not 'high' just because "
      "day 1 was small", d2[0]["tc_realised_vol_20d"] == "low",
      d2[0]["tc_realised_vol_20d"])
check("each day has all three terciles",
      {r["tc_realised_vol_20d"] for r in d1} == {"low", "mid", "high"})
thin = [{"day": "2026-01-04", "cond": {"realised_vol_20d": float(i)}, "f": {}, "t": {}}
        for i in range(6)]
ric.tercile_by_day(thin, "realised_vol_20d")
check("a cross-section too thin to split is left UNLABELLED, not split anyway",
      all("tc_realised_vol_20d" not in r for r in thin))

print("\n-- the trailing window counts SESSIONS, and separates real from all")
sessions = [f"2026-02-{d:02d}" for d in range(1, 26)]
labels = [{"day": "2026-02-10", "role": "subject", "new": True, "type": "earnings"},
          {"day": "2026-02-10", "role": "subject", "new": False, "type": "none"},
          {"day": "2026-02-10", "role": "mentioned", "new": True, "type": "earnings"},
          {"day": "2026-02-11", "role": "subject", "new": True, "type": "product"}]
cnt = ric.counts_for(labels, sessions)
c = cnt["2026-02-11"]
check("ev_all_20d counts every tagged item", c["ev_all_20d"] == 4, str(c["ev_all_20d"]))
check("ev_real_20d counts only subject AND new", c["ev_real_20d"] == 2, str(c["ev_real_20d"]))
check("ev_real_hard_20d drops 'product' from the hard set", c["ev_real_hard_20d"] == 1,
      str(c["ev_real_hard_20d"]))
check("stale_share_20d is 1 - real/all", abs(c["stale_share_20d"] - 0.5) < 1e-12,
      str(c["stale_share_20d"]))
before = cnt["2026-02-09"]
check("nothing is counted BEFORE it happened", before["ev_all_20d"] == 0, str(before))
far = cnt["2026-02-25"]
check("an item ages out of the 5-session window", far["ev_all_5d"] == 0, str(far["ev_all_5d"]))
check("...while the 20-session window still holds it", far["ev_all_20d"] == 4, str(far["ev_all_20d"]))

print("\n-- the pre-registration is in the code, so editing it shows in the diff")
for k in ("question", "features", "targets", "null", "multiplicity", "pass", "conditioning"):
    check(f"PREREG names {k}", bool(ric.PREREG.get(k)))
check("the licence is declared", ric.PREREG["licence"] == "PRODUCT_EXPERIMENT")
check("the null is a SHUFFLE, not an absence", "shuffl" in ric.PREREG["null"].lower())
check("the control (the withdrawn encoding) is one of the tested features",
      any("ev_all_20d" in f for f in ric.PREREG["features"]))

print("\n-- the shuffled null destroys the cross-section it is meant to destroy")
import numpy as np  # noqa: E402
panel = []
for d in range(1, 13):
    day = f"2026-03-{d:02d}"
    for i in range(20):
        panel.append({"symbol": f"S{i}", "day": day, "month": day[:7],
                      "f": {"x": float(i)}, "t": {"fwd_5d_rel": float(i) * 0.01}, "cond": {}})
real = ric.ic_cell(panel, "x", "fwd_5d_rel")
null = ric.ic_cell(panel, "x", "fwd_5d_rel", shuffle_null=True)
check("a perfectly monotone feature scores IC ~ +1", real["ic"] > 0.99, str(real["ic"]))
check("its shuffled null does NOT", abs(null["ic"]) < 0.5, str(null["ic"]))
check("the null keeps every row (it permutes, it does not drop)", null["n"] == real["n"])

print("\n-- labels on disk round-trip through the loader")
with tempfile.TemporaryDirectory() as td:
    ric.REL = Path(td)
    (ric.REL / "2025-09.jsonl").write_text(
        json.dumps({"uid": "a", "symbol": "MU", "effective_at": "2025-09-10",
                    "role": "subject", "is_new_fact": True, "event_type": "earnings"}) + "\n"
        + "\n"                                       # a blank line is not a crash
        + "{not json}\n"                             # nor is a corrupt one
        + json.dumps({"uid": "b", "symbol": "MU", "effective_at": "2025-09-11",
                      "role": "mentioned", "is_new_fact": False, "event_type": "none"}) + "\n",
        encoding="utf-8")
    got = ric.load_labels()
    check("both good rows load past a corrupt one", len(got.get("MU", [])) == 2, str(got))
    check("and they come back in date order",
          [r["day"] for r in got["MU"]] == ["2025-09-10", "2025-09-11"])

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
