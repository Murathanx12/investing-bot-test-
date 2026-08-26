# FAME_BIAS_v1 — not detected, and the instrument could only have seen 3.5 points

**2026-08-26, session 13, unattended.** `python -m scripts.fame_bias --n 5` then
`python -m scripts.fame_bias_report`. `deepseek-chat` @ T=0.4, 78 replies,
**18 companies with all four draws**. Receipt:
`state/research/fame_bias_v1.json`. Cost: **$0.03**.

## The question

Murat's standing objection to every stock-picking system, ours included: it
arrives at the names everybody already talks about. `alpha/universe.py` fixed the
*search space* — 4,634 names, no fame score anywhere in the ranker — and
`tests_smoke_universe.py` proves the numeric ranker cannot see a ticker.

That proof is worthless against the LLM, which has read the internet. It knows
NVDA matters and knows nothing about a $400M industrial. **The ranker will pass
its own fame test forever while the layer above it does the discriminating.**

## The design

One packet of real, price-derived numbers per company — momentum, drawdown,
realised vol, 5-day move, distance from the 200-day, dollar volume. Each packet
shown in two conditions differing in exactly one respect:

- **ANONYMISED** — "Company #4812", sector only
- **REVEALED** — identical numbers, ticker attached

and **each condition drawn twice**, because the difference between conditions
means nothing without knowing what the model does when nothing changes at all.

Controls: order randomised per company so "seen first" cannot masquerade as
fame; the anonymous ID differs between the two anonymous draws so a stable ID
cannot become a covert identity; **sector disclosed in both conditions**, or
revealing the ticker would also reveal the industry and confound fame with
information.

## The result

```
NOISE FLOOR (same condition, two draws)   mean |diff| 2.64 points
POWER                          drift sd 5.35p, n=18 -> MDE 3.53 points
OVERALL DRIFT                             -0.36 points     t = -0.29
```

| cell | n | mean drift | t |
|---|---|---|---|
| ALL | 18 | **−0.36p** | −0.29 |
| household | 5 | −2.00p | −1.19 |
| investor_famous | 5 | **+4.20p** | 1.50 |
| sector_known | 5 | −2.90p | −1.20 |
| obscure | 3 | −1.00p | −1.00 |

`RESEARCH_ALPHA_BUDGET`, family `fame_bias`, 5 cells charged: best |t| 1.50
gives `p_adj = 0.512`, and the **expected maximum |t| from five noise draws is
1.57** — the best cell is *below* what noise routinely produces at this many
looks. **NOT PROMOTABLE.**

## The verdict, stated at the strength the evidence supports

> **NOT DETECTED. That is not NOT PRESENT.** A fame effect smaller than 3.53
> points would have been invisible to this design. There is no measured case for
> anonymising evidence packets, **and no measured case for calling the LLM
> unbiased.**

## Two things the run taught that the headline does not

**1. A single observation looked exactly like a discovery.** Validating the
prompt on one packet, revealing "NVDA" moved the score 62 → 72 while a weak
packet stayed 12 → 12. That is a clean, mechanistic, publishable-sounding story
about fame amplifying good news and failing to rescue bad. **It did not
replicate.** NVDA's actual drift over four draws was **−1.5**. The noise floor
existed precisely to kill that story, and it did.

**2. The output scale is the binding constraint, not the sample size.** The
model used **seven distinct scores across 78 replies**: 12, 18, 22, 28, 32, 35,
42. Most answers were 12 or 18. A drift test on an output that coarse cannot
resolve small effects however many companies are added — the MDE is dominated by
the model's own quantisation, not by n. **Any rerun should change the elicitation
before it changes the sample**: force a rank-order across a slate, or ask for a
probability, rather than a 0-100 score the model collapses onto a handful of
values.

## One cell worth remembering, and not believing

`investor_famous` drifted **+4.20 points** — AVGO alone moved 18 → 32
consistently in both revealed draws. It is the only cell above its noise floor,
it is 5 companies, and it does not survive five-cell multiplicity. Recorded as a
**candidate, not a finding**, and the honest next test is that cell specifically,
pre-registered, with a better elicitation.

## A defect I introduced and left in the ledger

The first version of `fame_bias_report` charged the alpha budget **on every
render**, so re-reading the same 78 replies took family wealth 0.100 → 0.047 →
0.023. A budget a *report* can spend is not a budget on experiments; it is a tax
on curiosity, and it would eventually refuse a real discovery for having been
read twice. Fixed: the charge is keyed to the run timestamp and refuses to
re-charge.

The three charges stay in `state/alpha_budget.jsonl`. Editing them out would be
the same mistake as repairing the ledger chain — **a record that exists to be
tamper-evident does not get tidied.**

## Caveats

- One prompt, one model, one temperature, one 3-day horizon. Fame bias is
  plausibly stronger in a *generative* task ("name candidates") than in a
  *scoring* task where the numbers are already on the page. **This tested the
  easier direction**, and the generative direction is the one the candidate
  funnel actually uses.
- 20 companies requested, 18 complete: two calls died on `WinError 10054`
  (connection reset), which the transport correctly converted to a refusal.
- Fame strata are hand-labelled, because no field in the venue's asset record
  encodes recognisability and dollar volume is a proxy for size, not fame.

## The rule worth keeping

> **Draw the same condition twice before comparing two conditions.** Without the
> second anonymous draw, "revealing NVDA moved the score 10 points" was already
> written down here as a mechanism. The floor cost 18 extra calls and three
> cents, and it was the difference between a finding and a story.
