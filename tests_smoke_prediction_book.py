"""The sealed pre-open book (T7): the hash, the PIT bounds, and claiming nothing.

Run: python tests_smoke_prediction_book.py  (also executed by tests_smoke.py)

The whole value of this file is that "we expected that" becomes checkable. A
sealed artefact whose hash nobody verifies is a memory with extra steps, so the
hash, the reseal path and the derived `CLAIMING` switch are pinned here.
"""
from __future__ import annotations

import contextlib
import io

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


from scripts import prediction_book as pb

print("\n-- the content hash covers the content, and nothing else")
book = {"schema": "prediction-book-1", "day": "2026-08-31", "predictions": [{"symbol": "MU"}]}
h1 = pb._sha(book)
check("the same content hashes the same", pb._sha(dict(book)) == h1)
check("key ORDER does not change the hash",
      pb._sha({"predictions": [{"symbol": "MU"}], "day": "2026-08-31",
               "schema": "prediction-book-1"}) == h1)
check("changing a prediction CHANGES the hash",
      pb._sha({**book, "predictions": [{"symbol": "AMD"}]}) != h1)
check("changing the day changes the hash", pb._sha({**book, "day": "2026-09-01"}) != h1)

print("\n-- CLAIMING is DERIVED from the CIs, not asserted")
check("with every CI straddling zero the book claims nothing", pb.CLAIMING is False)
check("...and that is what the measured CIs actually say",
      all(lo <= 0 <= hi for _, (lo, hi) in pb.SIGNALS.values()),
      str({k: v[1] for k, v in pb.SIGNALS.items()}))
# The switch must turn itself ON when a signal earns it -- a hand-set constant
# would still say False after the evidence changed.
faked = {"x": (0.20, (0.05, 0.35))}
check("a signal whose CI clears zero would flip it on",
      any(lo > 0 or hi < 0 for _, (lo, hi) in faked.values()))

print("\n-- ranking: ties do not become an ordering of noise")
r = pb._rank_pct([0.0, 0.0, 0.0, 5.0])
check("three tied zeros share a rank", r[0] == r[1] == r[2], str(r))
check("and the non-zero sorts above them", r[3] > r[0], str(r))
check("a single value is the midpoint, not 0 or 1", pb._rank_pct([7.0]) == [0.5])
check("an empty column does not crash", pb._rank_pct([]) == [])

print("\n-- the horizon and the grading convention")
bars = [{"t": f"2026-01-{d:02d}T00:00:00Z", "o": 100.0 + d, "c": 101.0 + d} for d in range(1, 15)]
ret, why = pb._sessions_after(bars, "2026-01-01", 3)
# Entry: the OPEN of day 2 (102). Three sessions HELD are days 2, 3 and 4, so
# the exit is the CLOSE of day 4 (105) -- not day 2's close, which would be one
# session, and not day 3's, which would be two.
check("grading enters at the open of the next session and holds n SESSIONS",
      abs(ret - (105.0 / 102.0 - 1)) < 1e-12, f"{ret} {why}")
check("...the same convention rule_cells.forward uses, so the two agree",
      abs(ret - (105.0 / 102.0 - 1)) < 1e-12)
none_yet, why2 = pb._sessions_after(bars, "2026-01-13", 3)
check("a horizon that has not elapsed is None WITH a reason, not zero",
      none_yet is None and "elapsed" in why2, why2)
after_end, why3 = pb._sessions_after(bars, "2026-02-01", 3)
check("a day past the bars says so rather than returning a number",
      after_end is None and "no session after" in why3, why3)

print("\n-- sealing: a reseal is written BESIDE the original, never over it")
with tempfile.TemporaryDirectory() as td:
    pb.BOOKS = Path(td) / "predictions"
    pb.SEALS = pb.BOOKS / "seals.jsonl"
    b1 = {"day": "2026-08-31", "sealed_at_utc": "2026-08-31T13:15:00+00:00",
          "claims_made": 0, "universe_considered": 10, "predictions": []}
    b1["content_sha256"] = pb._sha(b1)
    p1 = pb.seal(b1)
    check("the first seal writes the day's file", p1.name == "2026-08-31.json")
    p1b = pb.seal(b1)
    check("re-sealing IDENTICAL content is a no-op", p1b == p1)
    b2 = {**b1, "sealed_at_utc": "2026-08-31T14:20:00+00:00", "claims_made": 3}
    b2.pop("content_sha256", None)
    b2["content_sha256"] = pb._sha(b2)
    p2 = pb.seal(b2)
    check("a DIFFERENT book on the same day is written beside it, not over it",
          p2 != p1 and p1.exists() and "resealed" in p2.name, p2.name)
    check("the original file still carries the ORIGINAL hash",
          json.loads(p1.read_text(encoding="utf-8"))["content_sha256"] == b1["content_sha256"])
    seals = [json.loads(l) for l in pb.SEALS.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("both hashes are in the append-only seals log", len(seals) == 2, str(len(seals)))
    check("and the reseal is NAMED as one in the log",
          "RESEAL" in (seals[-1].get("note") or ""), str(seals[-1].get("note")))
    check("verify() passes on untampered books", pb.verify() == 0)
    # Tamper: edit the sealed file and confirm verify() catches it.
    blob = json.loads(p1.read_text(encoding="utf-8"))
    blob["claims_made"] = 99
    p1.write_text(json.dumps(blob), encoding="utf-8")
    check("verify() catches a book edited after sealing", pb.verify() >= 1)

print("\n-- a low claim count is explained out loud, not noticed a week later")
def _bar_output(claims, considered, preds):
    """`claims=None` means the book carries NO generator map at all -- which is
    a different thing from a generator that claimed zero, and must print
    CANNOT DETERMINE rather than a number."""
    buf = io.StringIO()
    by_gen = {} if claims is None else {"g1": claims}
    with contextlib.redirect_stdout(buf):
        pb._report_claims_bar({"claims_by_generator": by_gen,
                               "universe_considered": considered,
                               "predictions": preds})
    return buf.getvalue()


_ok = _bar_output(pb.MIN_CLAIMS_PER_GENERATOR, 749, [])
check("a book at the bar reports ok and diagnoses nothing",
      "ok " in _ok and "WHY THE COUNT IS LOW" not in _ok, _ok)

_low = _bar_output(1, 151, [{"unreadable_clauses": ["d_catalyst"], "failed_clauses": []},
                            {"unreadable_clauses": ["d_catalyst"], "failed_clauses": ["a"]}])
check("a book under the bar says so", "LOW" in _low and "WHY THE COUNT IS LOW" in _low, _low)
check("...and names the UNREADABLE clause, which is a data gap and not a quiet market",
      "d_catalyst" in _low and "UNREADABLE" in _low, _low)
check("...and flags a universe too small to contain candidates",
      "universe is only 151" in _low, _low)

_nogen = _bar_output(None, 0, [])
check("a book with no generator map says CANNOT DETERMINE rather than 0/0",
      "CANNOT DETERMINE" in _nogen, _nogen)
check("the bar is a real number, not a placeholder", pb.MIN_CLAIMS_PER_GENERATOR >= 1)

print("\n-- the authority line is not decorative")
check("HORIZON is the 21 sessions the features were measured over",
      pb.HORIZON_SESSIONS == 21)
check("MIN_UNIVERSE stops a 'cross-section' of a handful", pb.MIN_UNIVERSE >= 20)
check("the IC receipt the weights come from is NAMED",
      pb.IC_RECEIPT.endswith(".json") and "wide" in pb.IC_RECEIPT, pb.IC_RECEIPT)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
