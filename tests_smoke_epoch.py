"""Ledger epochs: historical damage is DATED, never laundered."""
import json
import sys
import tempfile
from dataclasses import asdict, fields as dc_fields
from pathlib import Path

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha import epoch, ledger
from alpha.ledger import Decision

tmp = Path(tempfile.mkdtemp())
ledger.LEDGER_DIR = tmp
epoch.ANCHOR = tmp / "ledger_epochs.json"

_DEFAULTS = {"action": "refused", "ts_utc": "2026-08-26T00:00:00+00:00",
             "signal_shape": "tail", "instrument": "none", "thesis": "t",
             "predicted_move": 0.0, "predicted_sd": 0.01, "implied_move": 0.01,
             "breakeven_move": 0.01, "mdm_edge": 0.0, "quote_snapshot": None,
             "refusal_reason": "x", "risk_fraction": 0.0, "max_loss_usd": 0.0,
             "order": None, "brain": "t"}


def rec(sym):
    kw = {f.name: _DEFAULTS.get(f.name) for f in dc_fields(Decision)
          if not f.name.startswith("_")}
    kw["decision_id"] = f"id:{sym}"
    kw["symbol"] = sym
    return ledger.record(Decision(**kw))


def corrupt(idx, prev):
    """Overwrite line `idx` (0-based) with a bad _prev, in place."""
    p = ledger._path("decisions")
    lines = list(p.open("rb"))
    row = json.loads(lines[idx])
    row["_prev"] = prev
    body = json.dumps(row, sort_keys=True, separators=(",", ":"))
    lines[idx] = body.encode() + b"\r\n"
    p.open("wb").write(b"".join(lines))


print("\n-- a clean chain verifies, with no anchor at all")
for s in ("A", "B", "C"):
    rec(s)
ok, msg = ledger.verify_chain()
check("clean chain is intact", ok and "intact" in msg, msg)
check("scan finds no breaks", ledger.scan_chain()[0] == [])

print("\n-- corrupt a middle row: the chain goes red and NAMES the line")
corrupt(1, "0" * 64)
ok, msg = ledger.verify_chain()
check("a break fails the chain", not ok, msg[:70])
breaks, _, _ = ledger.scan_chain()
# EDITING a row cascades: the edited row's _prev is wrong, AND the next row's
# _prev was the hash of the ORIGINAL bytes. Two breaks from one edit -- that is
# the signature of a POST-HOC EDIT.
#
# The real 25 Aug damage looks different: breaks at 1203, 1372, 1376 and 1380
# with clean runs between them, because each writer recomputed _prev from the
# bytes actually on disk. A concurrent-write incident RE-SYNCS; an edit does
# not. The SHAPE of the break says which one happened, and that is why this
# distinction is worth a test rather than a comment.
check("editing a row breaks it AND its successor (the post-hoc-edit signature)",
      [b["line"] for b in breaks] == [2, 3], str([b["line"] for b in breaks]))

print("\n-- declare them as an epoch boundary: the gate can go GREEN again")
objs = [epoch.Break(line=ln, kind="CONCURRENT_WRITE", decision_id=None,
                    detail="two unlocked writers") for ln in (2, 3)]
epoch.ANCHOR.write_text(json.dumps({"decisions": {
    "breaks": [asdict(o) for o in objs],
    "manifest_hash": epoch.manifest_hash("decisions", objs)}}), encoding="utf-8")
ok, msg = ledger.verify_chain()
check("a DECLARED historical break no longer fails", ok, msg[:70])
check("...and the message still says the damage is there",
      "declared historical break" in msg, msg[:70])

print("\n-- but a NEW break is still red. This is the whole property.")
rec("D")                        # a fresh row, chained off the bytes really on disk
corrupt(3, "f" * 64)
ok, msg = ledger.verify_chain()
check("an UNDECLARED break fails even beside declared ones", not ok, msg[:80])
check("and the message counts declared vs undeclared", "UNDECLARED" in msg, msg[:80])

print("\n-- an anchor widened by hand is REFUSED, not honoured")
rec2 = json.loads(epoch.ANCHOR.read_text(encoding="utf-8"))
rec2["decisions"]["breaks"].append({"line": 4, "kind": "UNKNOWN", "decision_id": None,
                                    "detail": "quietly added to make the dashboard green"})
epoch.ANCHOR.write_text(json.dumps(rec2), encoding="utf-8")   # manifest_hash NOT updated
ok, msg = ledger.verify_chain()
check("hand-widening the accepted list is refused", not ok and "TAMPERED" in msg, msg[:80])

print("\n-- the manifest hash is what makes that true")
a = epoch.manifest_hash("decisions", objs)
b = epoch.manifest_hash("decisions", objs + [epoch.Break(9, "UNKNOWN", None, "one more")])
check("adding a break changes the manifest hash", a != b)
check("order does not change it",
      epoch.manifest_hash("decisions", objs) == epoch.manifest_hash("decisions", objs[::-1]))

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
