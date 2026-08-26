# NVDA Q2 FY2027: resolved from the filing before the price, and the guide is the story

**2026-08-26.** 8-K filed ~16:22 ET (acc `0001045810-26-000073`). All 13 sealed
fields resolved at **20:25:32 UTC** from `q2fy27pr.htm` and
`q2fy27cfocommentary.htm` — the filing itself, not a wire summary — **before any
price was observed**. `seal_valid=True`, 13/13 realised.

## The ordering held

`StateVector.reaction()` refuses until every field is resolved, and it was not
called until it could not refuse. The point of that discipline is that a move you
have already seen cannot be un-seen while reading the facts that caused it.
Everything below was written without knowing the reaction.

## The sealed hierarchy, scored

| rank | field | realised |
|---|---|---|
| 1 | `q3_guide_surprise` | **+3.8** ($108.0bn ±2% vs street $104.2bn) |
| 2 | `gross_margin_surprise` | **0.0** (75.0% reported = guided) — **but Q3 guided to 74.0% ±50bp** |
| 3 | `HBM_cost_pressure` | **partially_passed** |
| 4 | `Rubin_timing_change` | **ahead** |
| 5 | `customer_financing_quality` | **quantified — $105bn** |
| 6 | `future_capacity_constraint` | **power** |
| 7 | `datacenter_surprise` | +4.023 ($89.023bn) |
| 8 | `hyperscale_growth` | 54.7% of Data Center |
| 9 | `custom_silicon_competition` | **not_addressed** |
| 10 | `Blackwell_demand` | **not_addressed** |
| 11 | `ACIE_growth` | +138% y/y |
| 12 | `China_optional_revenue` | **excluded** |
| 13 | `revenue_surprise` | +4.171 ($96.221bn) |

**The headline beat by $4.2bn and it is rank 13 of 13.** That ranking was frozen
on 25 August, and nothing in the release argues it was wrong.

## What the sealed order was right about

**The guide is the number.** $108.0bn against $104.2bn is a larger surprise than
the quarter, and it is a **China-free** number: *"NVIDIA is not assuming any Data
Center compute revenue from China in its outlook."* Realised China Hopper
shipments were **under 1% of Data Center revenue**. Per the sealed rule,
exclusion is bullish for the *quality* of the guide — the $108.0bn does not
depend on a licence.

**And the margin line is exactly where the seal said to look.** Reported GM was
75.0%, precisely as guided, so the backward-looking surprise is zero. The forward
number is not: **Q3 is guided to 74.0% ±50bp**, and the sealed rule named
*"a Q3 GM guide below 74% is the bear trigger regardless of the revenue line"*.

It lands **exactly on the line**, with a band reaching 73.5%. Not tripped. Not
cleared either. A pre-registered threshold hitting its own boundary to the basis
point is the most useful thing a seal can do — it converts an argument about
sentiment into a single number that was written down first.

## The disclosure the seal ranked 5th, and it is the biggest number in the filing

> *"AI clouds and model makers are seeing extraordinary demand for AI
> infrastructure, yet many are growing faster than their balance sheets and
> long-term credit profiles can support."*

- existing land/power/shell guarantees: **$3.5bn** maximum gross exposure
- **August 2026: new guarantees capped at $105 BILLION**, phased, for ~**4.25 GW**
  at SB Energy's PORTS-Pike campus in Ohio — exclusively hosting NVIDIA
  infrastructure under 20-year leases **to OpenAI**
- a further **$56bn** of AI-cloud agreements and third-party leases

The sealed rule for field 8 said rising hyperscale concentration *"raises the
financing question in field 5 rather than settling it."* Hyperscale came in at
**54.7% of Data Center**. Both readings moved the same way: **more concentrated,
and more vendor credit standing behind it.** They compound.

## The constraint moved off silicon

> *"Securing land, power and shell for data centers has become the next critical
> phase in the AI infrastructure buildout."*

Supply-and-capacity commitments **$279bn**, front-loaded at $92bn / $87bn / $88bn
across FY27–29, and total commitments rose **$119bn → $279bn, "primarily related
to the procurement of memory."**

That clause is worth flagging against work finished **earlier the same afternoon,
before the print**: `NEEDS_GRAPH_v1` ranked **memory/HBM the most constrained
node in the chain** on filed fundamentals alone (+39.9pp of margin expansion
against +7.3pp for the next node). NVIDIA then disclosed a **$160bn commitment
increase primarily for memory**. Independent method, same conclusion, and the
graph never saw the filing.

## Two fields the release did not address, recorded as findings

`custom_silicon_competition` and `Blackwell_demand` are **not_addressed**.
"Competition" appears only in the boilerplate risk paragraph; *"sold out"*,
*"tight"*, *"supply constrained"*, *"backlog"*, *"lead time"* and *"allocation"*
appear nowhere in either document. Tightness is **inferable** from commitments
tripling — it is not **stated**, and the difference is recorded rather than
quietly resolved in our favour.

## The price is NOT graded, and forcing it would be the error

The feed returns the **16:00 ET close** (209.50 against a 209.66 prior close,
−0.08%) and an after-hours quote of **201.81 / 223.13** — a **10.0% wide**
indicative spread whose midpoint would imply +1.34%.

**That is not a price.** It is recorded as uninformative rather than converted
into a number the feed cannot support.

The sealed `event_date` is **2026-08-27** — the *session after* the print — so
the graded reaction is tomorrow's move. Tomorrow, after the close:

```
python -m scripts.contagion        --event 2026-08-27
python -m scripts.anchor_to_torque --event 2026-08-27
```

Read the **SPY/QQQ rows** (one-event MDE ~1.4%). Per-node MDE is 3.9–20.8% and
accumulates rather than concludes.

## What the book carried in

Captured at **16:10:44 ET**, before the release:

| | dev | exp1 |
|---|---|---|
| equity | $94,721 | $93,267 |
| day | −2.61% | **−5.53%, LATCHED** |
| true max loss | 56.4% of equity | 60.8% |
| largest thesis | **NVDA 52.7%** | SPY 42.7% |
| effective N by risk | 1.49 | **1.26** |

The two NVDA condors profit between roughly **−4.9% and +5.8/+7.0%**, priced
*before* the outcome at mean +$2,349 / worst −$17,739, with the known asymmetry
that 6 of 8 historical prints moved **down** and the short put is the tighter
side. That receipt exists precisely so tomorrow's grade compares against a number
written in advance rather than against a memory.

## The rule this run was for

> **Read the facts before the price, and the ranking before either.** The
> headline beat by $4.2bn and was rank 13 of 13, frozen a day earlier. The guide
> and the margin line were ranks 1 and 2, and both landed exactly where the seal
> said to look — one of them on its own threshold, to the basis point.
