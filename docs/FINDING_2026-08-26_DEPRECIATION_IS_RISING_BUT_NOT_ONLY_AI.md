# Implied useful life IS rising — and Apple is why that is not yet an AI story

**2026-08-26, session 13, unattended.** `python -m scripts.depreciation_gap`.
Source: **SEC XBRL company facts** (`data.sec.gov`) — the companies' own filed
numbers, not a vendor normalisation and not a scrape of prose.
`AI_DEPRECIATION_REALITY_GAP_v1`, phase 1.

## The claim, and its correction

Murat raised this from a Coffeezilla recollection. The correction on record is
that the concern is **hyperscaler** accounting rather than NVIDIA's own books:
if Microsoft, Amazon, Meta and Alphabet extend the assumed useful life of
servers, annual depreciation falls, reported profit rises, and AI build-out
economics look better than they are.

That is checkable without anyone's opinion:

```
implied useful life  =  gross PP&E / annual depreciation
```

A company depreciating $100bn of PP&E at $25bn a year is behaving as if the
assets last four years. **If the ratio rises, the assumed life is being
stretched** — whatever a footnote says in words.

## What the filings say

| | span | implied life | change |
|---|---|---|---|
| AMZN | 2016→2025 | 6.6y → 12.8y | **+92%** ⚠ |
| AAPL | 2019→2025 | 8.5y → 15.7y | **+85%** |
| ORCL | 2020→2026 | 10.0y → 16.1y | +61% |
| MSFT | 2020→2026 | 8.2y → 12.6y | +54% |
| META | 2013→2019 | 4.8y → 6.1y | +26% ⚠ |
| **NVDA** | 2020→2026 | 7.6y → **7.1y** | **−7%** |
| GOOGL | — | only 2 comparable years | not readable |

⚠ **AMZN's series has a five-year hole** (2020–2024 missing; the tag changes),
so its "+92%" is two points across a gap, not a trend. META's usable series ends
in 2019. Both are flagged in the output rather than quoted as continuous.

MSFT and ORCL are the clean ones: seven consecutive years each, both rising
monotonically in the back half.

## The one row that matters most, and it is a problem for the story

**Apple is up 85% — the second-largest rise in the table.**

Apple is not building AI datacentres at hyperscaler scale. If the rise were an
AI-capex phenomenon, Apple should not show it, and it shows it strongly. So on
this evidence the trend is **large-cap tech generally**, or **a mix shift toward
long-lived assets** (datacentre shells and land last decades; servers do not),
or both — but it is **not cleanly an AI story**.

The control was not requested and is not flattering. It is the most useful thing
in the run.

## The one thing the original claim got right

**NVDA moves the other way** (−7%, and flat-to-falling across all seven years).
Its PP&E is fabs and test equipment, not datacentre shells. That is exactly the
correction: *the concern is customer accounting, not NVIDIA's own books.*

## What this cannot see

- **Mix.** Gross PP&E lumps shells, land, servers and network gear together. A
  company shifting spend toward shells raises implied life honestly. **A rising
  ratio is a question, not a verdict.**
- **The stated assumption.** "We extended useful life from four years to six"
  lives in the filing text, not in these tags. XBRL gives the *behaviour*, not
  the *policy*.
- **Economic life.** Nothing here says what the assets are worth. That needs
  used-GPU pricing and performance-per-dollar decay, and **it is not attempted**.

**This is the accounting half of the gap only.** Half a measurement presented as
a whole one is how a plausible story becomes a believed one.

## What would make this decisive

1. **Split PP&E by class.** `PropertyPlantAndEquipmentByTypeAxis` sometimes
   carries servers separately. If server-class life is rising, the mix defence
   dies.
2. **Read the stated policy change from the text** for MSFT and ORCL, the two
   clean series, and date it against the ratio's inflection.
3. **A non-tech control group.** If industrials show the same rise, this is an
   accounting-wide trend and the AI framing should be dropped entirely.

Until at least (1), this is a **lead, not a finding**, and nothing should be
traded on it.

## The rule worth keeping

> **Run the control you would not have chosen.** Apple was in the list as a
> convenience, and it is the row that stops a clean AI narrative from being
> written. A confirmation without a control is a story with numbers attached.
