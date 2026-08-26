# NEEDS_GRAPH_v1: the binary does not discriminate, but the ordering does — and one node validates the metric

**2026-08-26, session 13, unattended.** `python -m scripts.needs_graph`.
Finnhub fundamentals over one bounded chain, 23 companies, 7 nodes. Shadow only.

## The question, in Murat's words

> *What will the world need, and who fulfils that need?*

Then the part that decides the trade: **which link is the bottleneck**, because
that is where pricing power settles.

Capacity, backlog and lead times are the direct evidence and we do not have
them. What a constrained supplier leaves in filed numbers is a **joint**
signature:

```
revenue GROWING          demand is real, not a story
AND gross margin RISING  it can raise price without losing the order
```

Either alone means nothing. **Growth with falling margin is a supplier taking
volume at someone else's price** — the opposite of a bottleneck.

## The result

| node | n | median growth | median GM vs 5y |
|---|---|---|---|
| **memory / HBM** | 3 | **+167.0%** | **+39.9pp** |
| datacentre ops | 3 | +364.9% | +7.3pp |
| networking / optics | 5 | +61.9% | +5.6pp |
| accelerators | 2 | +55.1% | +5.8pp |
| power / thermal | 4 | +27.5% | +2.5pp |
| foundry + packaging | 5 | +11.7% | +2.1pp |
| **servers / ODM** | 2 | +47.4% | **−4.6pp** |

## The honest problem with it

**Six of seven nodes qualify.** A screen that keeps 86% of what it looks at is
not a screen, and this is the same failure the analyst panel produced the same
day: conditioning on "analysts are still bullish" selects 93% of the market, and
conditioning on "growing with expanding margin" selects nearly the whole AI
complex. **A condition true of almost everything carries almost no information.**

The tool now says so in its own output rather than printing a column of green
labels that look like agreement.

## What survives, and why the failure matters most

**The ordering.** Memory/HBM is not marginally ahead — it is **+39.9pp of margin
expansion against +7.3pp for the next node**, a five-fold gap, on +167% revenue
growth. If pricing power is anywhere in this chain right now, the filed numbers
say memory.

**And servers/ODM is the row that makes the metric credible.** SMCI and DELL
grow 47% while margin *contracts* 4.6pp. That is exactly what theory predicts an
assembler looks like: real demand, no pricing power, volume at someone else's
price. **A metric that flagged everything including the assemblers would be
measuring growth and calling it scarcity.** It didn't.

That single negative row is worth more than the six positives.

## The node is the diagnosis; the company is the trade

Carried across from `STATE_CHANGE_ELASTICITY`, because "which layer is
constrained" and "who moves on it" are different questions:

```
memory / HBM        WDC 9%   SNDK 5%   MU 1%
datacentre ops      CORZ 230%  APLD 170%  NBIS 81%
networking/optics   AAOI 171%  CRDO 77%  LITE 36%  COHR 15%
```

Note the tension this exposes: **the node with the strongest pricing-power
signature (memory) has the LOWEST torque** — MU at 1%, because it is already a
$89bn-revenue company. The high-torque names sit in datacentre ops, whose margin
expansion is a fifth of memory's. *Diagnosis and expression point at different
places*, which is precisely what `ANCHOR_TO_TORQUE` exists to arbitrate and not
something either metric could have shown alone.

## Limits

- **This is the financial shadow of a constraint, not the constraint.** Capacity,
  backlog and lead times would be direct evidence.
- **Gross margin moves with MIX as well as with price.** A company selling more
  of its best product looks identical to one raising prices.
- **Membership is a judgement**, written into the file so it can be argued with
  rather than inferred and hidden.
- Two-name nodes (accelerators, servers) have a median of two.
- Nothing here forecasts that a shortage happens or persists.

## The rule worth keeping

> **Check whether the condition is rare — and look hardest at what FAILS it.**
> Six green rows told me nothing. The one red row told me the metric works.
