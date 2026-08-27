"""EXECUTION_REACHABILITY_AUDIT, and the shape claim it found.

`alpha/book_limits.py` said in its own docstring that it was "implemented,
tested, and called by NOTHING" while the book it should have bounded reached
72.9% of equity. On 2026-08-27 the same audit found a second one:
`alpha/engine/shape.py`, whose first line calls it "the idea this whole agent is
built on", had ZERO importers -- and five of six brains were hardcoding
`signal_shape="tail"`, the shape that means "buy convexity", with no curve
behind it.

A module with no caller is indistinguishable from a module that works, from the
outside and from a green suite. So the audit is a suite.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

fails: list[str] = []
ran = 0


def check(name: str, cond: bool, why: str = "") -> None:
    global ran
    ran += 1
    if cond:
        print(f"  ok   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}  {why}")


print("execution reachability + shape claim provenance")

# --- the audit runs and its instrument is sane ------------------------------
out = subprocess.run([sys.executable, "-m", "scripts.reachability"],
                     capture_output=True, text=True, timeout=180)
check("the audit runs", out.returncode == 0, out.stderr[-300:])
text = out.stdout
check("it reports module reachability", "MODULE REACHABILITY" in text)
check("it reports guard reachability", "GUARD REACHABILITY" in text)

# The first run reported 22 orphans and most were the walker's own bug:
# alpha/brains/__init__.py resolved to `alpha.brains.__init__`, so no package
# import ever matched. Distrust the instrument before the result.
check("package __init__ resolves to the package name, not `.__init__`",
      "alpha.brains.__init__" not in text and "alpha.brains " not in text.split("GUARD")[0],
      "an unresolved package name makes every re-exported module read as an orphan")

# --- shape.py is now reachable ---------------------------------------------
check("alpha.engine.shape is no longer an orphan",
      "ORPHAN  alpha.engine.shape" not in text,
      "it is imported by brains/base.py, which every forecast passes through")

# --- the shape claim guard --------------------------------------------------
from alpha.brains.base import Forecast                        # noqa: E402
from alpha.engine import shape                                # noqa: E402


def fc(**kw):
    base = dict(brain="vol_gap", symbol="X", horizon_days=3.0, centre=0.0, sd=0.02)
    base.update(kw)
    return Forecast(**base)


def refuses(**kw):
    try:
        fc(**kw)
        return None
    except ValueError as exc:
        return str(exc)

check("an UNQUALIFIED 'tail' from a brain with no curve is REFUSED",
      (r := refuses(signal_shape="tail")) is not None and "no entry for it" in r, str(r))
check("  and the refusal says the literal was the standing case for buying premium",
      r is not None and "buying premium" in r)
check("'declared:tail' is accepted", fc(signal_shape="declared:tail").signal_shape
      == "declared:tail")
check("no shape claim at all is accepted", fc(signal_shape=None).signal_shape is None)
check("a nonsense shape is REFUSED",
      (r := refuses(signal_shape="declared:banana")) is not None and "is not a shape" in r, str(r))

# The subtle one: an earlier draft asked only whether ANY curve in SHAPE_PRIOR
# had the claimed shape. `mom_12_1` is a measured TAIL, so every brain would
# have passed "tail" by borrowing an unrelated signal's geometry -- the same
# evidence-by-analogy the refuted-routes rewrite removed the same morning.
check("'tail' is measured for SOME signal in the prior",
      "tail" in shape.measured_shapes(),
      "so a shape-only check would have passed every brain")
check("  yet an unqualified 'tail' still fails, because the curve must be THIS signal's",
      refuses(signal_shape="tail") is not None,
      "borrowing another signal's curve because they share an adjective is the bug")

check("a DECLARED shape may not be cited as evidence for convexity",
      shape.licenses_convexity("declared:tail")[0] is False
      and "hypothesis about geometry" in shape.licenses_convexity("declared:tail")[1])
check("a measured TAIL may be", shape.licenses_convexity("tail")[0] is True)
check("but not when the brain has no curve of its own",
      shape.licenses_convexity("tail", brain="vol_gap")[0] is False,
      "borrows another signal's geometry")
check("no claim licenses nothing", shape.licenses_convexity(None)[0] is False)

# --- every brain now carries provenance -------------------------------------
import ast                                                    # noqa: E402

unqualified = []
for f in sorted(Path("alpha/brains").glob("*.py")) + [Path("scripts/nfp_trade.py")]:
    for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if isinstance(node, ast.keyword) and node.arg == "signal_shape":
            v = node.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str) \
                    and not v.value.startswith("declared:"):
                unqualified.append(f"{f.name}:{v.value}")
check("no brain asserts an unqualified shape any more", not unqualified, str(unqualified))

check("the constructor is where it is enforced",
      "validate_claim" in Path("alpha/brains/base.py").read_text(encoding="utf-8"),
      "a brain called from a script or a notebook must not be able to skip it")

print(f"\n{ran} checks")
print("ALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
if __name__ == "__main__":
    raise SystemExit(1 if fails else 0)
