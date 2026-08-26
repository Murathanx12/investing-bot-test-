"""Resolve the sealed NVDA state vector FROM THE RELEASE, then read the price.

    python -m scripts.nvda_resolve --template            # write a blank answer file
    python -m scripts.nvda_resolve --answers ans.json    # resolve (facts only)
    python -m scripts.nvda_resolve --answers ans.json --read-move   # ...then the move
    python -m scripts.nvda_resolve --status              # what is still open

THE ORDER IS THE EXPERIMENT
===========================
`StateVector.reaction()` REFUSES until every field is resolved. That refusal is
the whole point: reading the move first and the facts second produces a coherent
story every single time, and its coherence is exactly what makes it worthless.
This script cannot reverse that order even if asked -- `--read-move` simply
fails while any field is open.

FILL FROM THE RELEASE, NOT FROM COMMENTARY
==========================================
Each field carries its own `resolution_rule` (`--status` prints them). A field
the release genuinely did not address is `"UNAVAILABLE"` -- a fact about the
release, and it must never be indistinguishable from a field we forgot to fill.

The seal covers the HYPOTHESIS, not the answers: filling a realised value is
expected and does not break it. Editing a prior or reordering the hierarchy
does, and `resolve()` refuses on a broken seal.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.event_state import StateVector
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal

STORE = Path(__file__).resolve().parent.parent / "state" / "event_state"
VECTOR = STORE / "NVDA_2026-08-27_vector.json"


def _load() -> StateVector:
    if not VECTOR.exists():
        raise SystemExit(f"no sealed vector at {VECTOR}")
    return StateVector.load(VECTOR)


def cmd_status(sv: StateVector) -> int:
    print(f"{sv.subject} {sv.event}  sealed {sv.sealed_at}  seal_valid={sv.verify()}")
    print(f"resolved_at: {sv.resolved_at or 'NOT RESOLVED'}\n")
    for f in sorted(sv.fields, key=lambda x: x.rank):
        mark = "OK " if f.resolved else "-> "
        val = f.realised if f.resolved else ""
        print(f"{mark}{f.rank:>2}. {f.name:26s} [{f.unit}] {str(val)[:40]}")
        if not f.resolved:
            print(f"      rule: {f.resolution_rule[:150]}")
    return 0


def cmd_template(sv: StateVector) -> int:
    out = {f.name: ("UNAVAILABLE" if f.unit == "ordinal" else None)
           for f in sorted(sv.fields, key=lambda x: x.rank) if not f.resolved}
    path = STORE / "NVDA_2026-08-27_answers.json"
    path.write_text(json.dumps({"_README": (
        "Fill each field FROM THE RELEASE using its resolution_rule "
        "(python -m scripts.nvda_resolve --status). Use the string UNAVAILABLE for "
        "anything the release did not address. Do NOT look at the after-hours move "
        "until this file is complete -- the tooling refuses, but the discipline is yours."),
        "values": out, "notes": {}}, indent=1), encoding="utf-8")
    print(f"template -> {path}\n{len(out)} fields to fill")
    return 0


def measure_move(client: AlpacaPaper) -> dict:
    """The after-hours reaction, measured from our own data, not from a headline."""
    out = {"measured_utc": datetime.now(timezone.utc).isoformat()}
    try:
        q = client.stock_quote(["NVDA"])
        t = client.latest_trade(["NVDA"])
        bars = client.stock_bars_multi(["NVDA", "SMH", "QQQ"], start="2026-08-20", timeframe="1Day")
        prev = {s: (b[-1]["c"] if b else None) for s, b in bars.items()}
        last = None
        tr = (t.get("trades") or {}).get("NVDA") or {}
        last = tr.get("p")
        out["nvda_prev_close"] = prev.get("NVDA")
        out["nvda_last"] = last
        if last and prev.get("NVDA"):
            out["nvda_move"] = last / prev["NVDA"] - 1
        out["quote"] = (q.get("quotes") or {}).get("NVDA")
        out["prev_closes"] = prev
    except BrokerRefusal as exc:
        out["error"] = str(exc)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    p.add_argument("--template", action="store_true")
    p.add_argument("--answers", default=None, help="JSON file of realised values")
    p.add_argument("--read-move", action="store_true",
                   help="after resolving, measure and record the price reaction")
    args = p.parse_args()
    config.load_env()
    sv = _load()

    if args.template:
        return cmd_template(sv)
    if args.status or not (args.answers or args.read_move):
        return cmd_status(sv)

    if args.answers:
        doc = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        values = {k: v for k, v in (doc.get("values") or doc).items()
                  if not k.startswith("_") and v is not None}
        still = sv.resolve(values, notes=doc.get("notes") or {})
        sv.save(VECTOR)
        print(f"resolved {len(values)} field(s); {len(still)} still open")
        if still:
            print("  open:", ", ".join(still))
            print("  (the price reaction stays REFUSED until these are filled)")
        else:
            print(f"  ALL FIELDS RESOLVED at {sv.resolved_at}")

    if args.read_move:
        try:
            sv.reaction()           # raises while anything is open
        except ValueError as exc:
            print(f"\n{exc}")
            return 1
        client = AlpacaPaper()
        move = measure_move(client)
        sv.reaction(move)
        sv.save(VECTOR)
        print("\nPRICE REACTION (recorded AFTER the facts):")
        print(json.dumps(move, indent=1)[:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
