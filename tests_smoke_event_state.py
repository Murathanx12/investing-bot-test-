"""The event state vector, the shock graph, and the source registry.

The checks that matter most here are the REFUSALS. A sealed prediction that can
still be edited is not a prediction, and a price reaction read before the facts
produces a coherent story every single time -- which is exactly what makes it
worthless. Both are enforced in code and both are pinned here.
"""
import sys

fails = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


from alpha.event_state import (UNAVAILABLE, Field, Node, ShockGraph, StateVector,
                               group_power, measure_beta, residual_sd)
from alpha.sources import registry


def vec():
    return StateVector(
        subject="TEST", event="print", event_date="2026-08-27",
        release_expected_utc="2026-08-26T20:20:00+00:00",
        fields=[Field("guide", 1, "q?", "usd_bn", "prior", "rule", ["nvda_ir"]),
                Field("headline", 2, "q?", "usd_bn", "prior", "rule", ["nvda_ir"])],
        control_record="PH:TEST")


print("\n-- sealing is a commitment")

v = vec()
seal = v.seal_now()
check("sealing produces a hash and verifies", v.verify() and len(seal) == 32, seal)

try:
    v.seal_now()
    check("a second seal is refused", False)
except ValueError as exc:
    check("a second seal is refused", True, str(exc)[:48])

v2 = vec()
v2.seal_now()
v2.fields[0].prior = "something more convenient"
check("editing a PRIOR after sealing breaks the seal", not v2.verify())

v3 = vec()
v3.seal_now()
v3.fields[0].rank, v3.fields[1].rank = 2, 1
check("REORDERING THE HIERARCHY breaks the seal -- the ranking IS the claim",
      not v3.verify())

v4 = vec()
v4.seal_now()
v4.fields[0].realised = 104.0
check("filling a realised value does NOT break the seal (it is what sealing protects)",
      v4.verify())

print("\n-- the ordering guard: facts before the move")

v5 = vec()
v5.seal_now()
try:
    v5.reaction()
    check("the reaction is refused while the vector is unresolved", False)
except ValueError as exc:
    check("the reaction is refused while the vector is unresolved",
          "REFUSED" in str(exc) and "guide" in str(exc), str(exc)[:60])

still_open = v5.resolve({"guide": 108.0})
check("resolve reports what is still open", still_open == ["headline"], str(still_open))
try:
    v5.reaction()
    check("a PARTIALLY resolved vector still refuses", False)
except ValueError:
    check("a PARTIALLY resolved vector still refuses", True)

v5.resolve({"headline": UNAVAILABLE})
check("UNAVAILABLE resolves the field (an absent fact is a finding, not a blank)",
      v5.resolved_at is not None)
r = v5.reaction({"day0": 0.031})
check("once resolved, the reaction is readable", r == {"day0": 0.031}, str(r))

v6 = vec()
try:
    v6.resolve({"guide": 1.0})
    check("resolving an UNSEALED vector is refused", False)
except ValueError as exc:
    check("resolving an UNSEALED vector is refused", True, str(exc)[:46])

v7 = vec()
v7.seal_now()
try:
    v7.resolve({"invented_field": 1.0})
    check("a field invented after the fact is refused", False)
except KeyError:
    check("a field invented after the fact is refused", True)

print("\n-- the shock graph")

g = ShockGraph(subject="TEST", event_date="2026-08-27", nodes=[
    Node("AAA", "supplier", "guide", "m", +1, "high", 1, "obs"),
    Node("BBB", "competitor", "guide", "m", -1, "high", 1, "obs"),
])
g.nodes[0].nvda_beta, g.nodes[0].mde_1event = 1.2, 0.05
g.nodes[1].nvda_beta, g.nodes[1].mde_1event = 0.3, 0.05
g.seal_now()
check("the graph seals and verifies", g.verify())
g.nodes[0].frozen_price = 100.0
check("freezing a PRICE does not break the seal (only the hypothesis is sealed)",
      g.verify())
g.nodes[0].sign = -1
check("flipping an edge SIGN breaks the seal", not g.verify())

g2 = ShockGraph(subject="T", event_date="d", nodes=[
    Node("AAA", "supplier", "guide", "m", +1, "high", 1, "obs"),
    Node("BBB", "competitor", "guide", "m", -1, "high", 1, "obs"),
])
for n in g2.nodes:
    n.nvda_beta, n.resid_sd, n.mde_1event = 1.0, 0.02, 0.056
rank = g2.underreaction(0.05, {"AAA": 0.01, "BBB": -0.01})
by = {r["ticker"]: r for r in rank}
check("a POSITIVE edge that barely moved shows a positive residual",
      by["AAA"]["residual_vs_declared"] > 0, f"{by['AAA']['residual_vs_declared']:+.4f}")
check("a NEGATIVE edge is scored in ITS OWN direction, not flipped by the sign",
      by["BBB"]["residual_vs_declared"] > 0, f"{by['BBB']['residual_vs_declared']:+.4f}")
check("every row carries the power number beside the residual",
      all(r["mde_1event"] is not None and r["resolvable_on_one_event"] is not None
          for r in rank))
check("a 4% residual against a 5.6% MDE is NOT resolvable on one event",
      by["AAA"]["resolvable_on_one_event"] is False,
      f"resid {by['AAA']['residual_vs_declared']:+.3f} vs mde {by['AAA']['mde_1event']}")
check("a node with no observed move is dropped, not defaulted to zero",
      len(g2.underreaction(0.05, {"AAA": 0.01})) == 1)

print("\n-- beta and residual measurement")


def bars(seq):
    return [{"t": f"2026-01-{i + 1:02d}T00:00:00Z", "c": c} for i, c in enumerate(seq)]


import math

# Returns must VARY or there is nothing to regress on: a constant 1%/day driver
# has zero variance and identifies no beta at all.
_r = [0.02 * math.sin(i) for i in range(40)]
drv, tgt, flat = [100.0], [100.0], [100.0]
for i, r in enumerate(_r):
    drv.append(drv[-1] * (1 + r))
    tgt.append(tgt[-1] * (1 + 2 * r))
    flat.append(flat[-1] * 1.01)
beta, r2, n = measure_beta(bars(tgt), bars(drv))
check("a target moving twice the driver measures beta ~2", beta is not None and 1.9 < beta < 2.1,
      f"beta={beta} r2={r2} n={n}")
_rsd = residual_sd(bars(tgt), bars(drv), beta)
check("a perfect relationship has residual sd ~0",
      _rsd is not None and _rsd < 1e-6, f"resid_sd={_rsd}")
b2, _, n2 = measure_beta(bars(tgt[:10]), bars(drv[:10]))
check("fewer than 30 overlapping days -> no beta, and the n is reported",
      b2 is None and n2 < 30, f"n={n2}")
b3, _, n3 = measure_beta(bars(tgt), bars(flat))
check("a driver with no variance identifies NO beta rather than a confident number",
      b3 is None, f"beta={b3} on {n3} days")

print("\n-- group power: the question that comes first")

rows = group_power({"AAA": bars(tgt), "BBB": bars(tgt)}, bars(drv), {"e": ["AAA", "BBB"]})
check("group_power reports an MDE and the events needed",
      rows and "mde_1event" in rows[0] and "events_for_target" in rows[0], str(rows[0])[:70])
thin = group_power({"AAA": bars(tgt[:10])}, bars(drv[:10]), {"e": ["AAA"]})
check("too few sessions -> CANNOT DETERMINE, not a number",
      "CANNOT DETERMINE" in thin[0].get("verdict", ""), str(thin[0])[:60])

print("\n-- the source registry: a restatement is not a confirmation")

c = registry.corroboration(["nvda_ir", "nvda_8k"])
check("an IR release and its own 8-K are ONE independent observation",
      c["cited"] == 2 and c["independent"] == 1, str(c["groups"]))
c2 = registry.corroboration(["nvda_ir", "taiwan_moea", "foxconn_monthly"])
check("issuer + customs + a different issuer are THREE", c2["independent"] == 3)
check("the note names the collapse when there is one",
      "restatements" in registry.corroboration(["nvda_ir", "nvda_8k"])["note"])
check("an unregistered source counts as independent rather than vanishing",
      registry.independent_count(["nvda_ir", "made_up_source"]) == 2)
check("unregistered() names it so the gap can be closed",
      registry.unregistered(["nvda_ir", "made_up_source"]) == ["made_up_source"])
check("the strongest tier is reported", c["strongest_type"] == "company_filing",
      c["strongest_type"])

try:
    registry.Source(source="x", source_type="rumour", metric="m", entity="e",
                    frequency="f", publication_lag="l", revision_policy="r",
                    point_in_time_available=True, independence_group="g")
    check("an unknown source_type is refused", False)
except ValueError:
    check("an unknown source_type is refused", True)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("ALL PASS")
