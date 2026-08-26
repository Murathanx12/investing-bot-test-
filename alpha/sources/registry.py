"""DATA_SOURCE_REGISTRY_v0 -- what a source IS, before anything is inferred from it.

WHY
===
Session 11 ended with four experiments and a lesson that keeps recurring in
different clothes: the number was fine and the CONTEXT of the number was not.
The pair trade died when the return convention changed. The Nikkei fade died
when the window changed. The wide PEAD drift died when the benchmark changed.
Each time, the fix was information ABOUT the measurement that had never been
written down beside it.

This registry writes it down. Every source carries the sixteen fields the
continuation brief named, and two of them do real work:

**`independence_group`.** Reuters restating an NVIDIA press release is not a
second confirmation of the press release. Neither is Bloomberg, nor a moomoo
preview quoting a consensus that came from the same sell-side estimates.
`independent_count()` collapses a set of source ids into the number of genuinely
separate observers, and it is normal for eight citations to collapse to two.
An evidence bundle that looks corroborated and is one issuer speaking eight
times is the single easiest way to be confidently wrong.

**`point_in_time_available` and `publication_lag`.** Taiwan's July export figure
is a fact about July that did not EXIST until 7 August. Any backtest that reads
it on 31 July is not optimistic, it is wrong. The lag is per source because it
is a property of the publisher, not of the metric.

APPEND-ONLY IS A RULE ABOUT WRITING, NOT A FIELD
------------------------------------------------
`revision_policy` says whether a source restates. Where it does, the OBSERVATION
store must keep both vintages: never overwrite yesterday's number with today's
revision. That is how point-in-time discipline dies, and it dies silently --
the backtest simply gets better and nothing announces why.

THIS IS SEEDED, NOT COMPLETE
----------------------------
Only what the NVDA print and Trade Pulse need. A registry that tried to describe
the internet would describe nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

#: Ranked. A restatement NEVER outranks the thing it restates.
SOURCE_TYPES = ("company_filing", "company_ir", "government", "exchange",
                "audited_industry", "wire_service", "media", "sell_side",
                "social", "derived")

#: How much of the ranking is load-bearing: a `media` fact whose independence
#: group is a `company_ir` release inherits the ISSUER's independence, not the
#: outlet's reach.
_TIER = {t: i for i, t in enumerate(SOURCE_TYPES)}


@dataclass(frozen=True)
class Source:
    source: str
    source_type: str
    metric: str
    entity: str
    frequency: str
    publication_lag: str
    revision_policy: str
    point_in_time_available: bool
    independence_group: str
    license: str = "unknown"
    cost: str = "free"
    reliability: str = "unrated"
    parser: str = "manual"
    failure_rate: str = "unmeasured"
    note: str = ""

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"{self.source}: unknown source_type {self.source_type!r}; "
                             f"one of {SOURCE_TYPES}")

    @property
    def tier(self) -> int:
        return _TIER[self.source_type]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Seeded for the 26 Aug NVDA print. Keys are the ids the evidence bundle cites.
REGISTRY: dict[str, Source] = {
    "nvda_ir": Source(
        source="NVIDIA Investor Relations quarterly release + CFO commentary",
        source_type="company_ir", metric="revenue, data center revenue, gross margin, guidance",
        entity="NVDA", frequency="quarterly", publication_lag="0d (is the event)",
        revision_policy="restated only in the subsequent 10-Q", point_in_time_available=True,
        independence_group="nvda_issuer", license="public", cost="free",
        reliability="primary", parser="pending (A3)",
        note="THE source for tonight. Everything else about tonight is a restatement of it."),
    "nvda_8k": Source(
        source="SEC 8-K Item 2.02", source_type="company_filing",
        metric="results release, exhibits", entity="NVDA", frequency="quarterly",
        publication_lag="minutes after the IR release", revision_policy="8-K/A",
        point_in_time_available=True, independence_group="nvda_issuer",
        license="public", cost="free", reliability="primary", parser="alpha.sources.sec"),
    "reuters": Source(
        source="Reuters", source_type="wire_service", metric="varies",
        entity="varies", frequency="continuous", publication_lag="minutes to hours",
        revision_policy="corrections appended", point_in_time_available=False,
        independence_group="wire", reliability="high", cost="free",
        note="Independent when reporting its OWN sourcing; a restatement of an issuer "
             "release inherits `nvda_issuer` and is not a second confirmation."),
    "consensus_sellside": Source(
        source="sell-side consensus as republished in previews (moomoo/Kiplinger)",
        source_type="sell_side", metric="consensus revenue / EPS", entity="NVDA",
        frequency="continuous, drifts into the print", publication_lag="varies",
        revision_policy="REVISED CONTINUOUSLY -- the vintage is the fact",
        point_in_time_available=False, independence_group="sellside_consensus",
        reliability="medium",
        note="A consensus quoted without an as-of stamp is not a number. Two previews "
             "quoting the same estimate pool are ONE observation."),
    "taiwan_moea": Source(
        source="Taiwan Ministry of Finance monthly exports", source_type="government",
        metric="export value y/y, electronics components", entity="TW",
        frequency="monthly", publication_lag="~7 days after month end",
        revision_policy="rarely revised", point_in_time_available=True,
        independence_group="taiwan_customs", reliability="high", cost="free",
        note="A genuinely independent read on AI hardware demand: it is customs data, "
             "not a company telling us how it is doing."),
    "tsmc_monthly": Source(
        source="TSMC monthly revenue report", source_type="company_ir",
        metric="net revenue, monthly", entity="TSM", frequency="monthly",
        publication_lag="~10 days after month end", revision_policy="none",
        point_in_time_available=True, independence_group="tsmc_issuer",
        reliability="primary", cost="free"),
    "foxconn_monthly": Source(
        source="Hon Hai monthly revenue report", source_type="company_ir",
        metric="net revenue, monthly; segment commentary", entity="2317.TW",
        frequency="monthly", publication_lag="~5 days after month end",
        revision_policy="none", point_in_time_available=True,
        independence_group="foxconn_issuer", reliability="primary",
        note="Assembles a large share of NVIDIA racks; the closest thing to a "
             "shipment counter that publishes monthly."),
    "micron_ir": Source(
        source="Micron earnings + supply commentary", source_type="company_ir",
        metric="HBM commitments, pricing, supply tightness", entity="MU",
        frequency="quarterly", publication_lag="0d", revision_policy="none",
        point_in_time_available=True, independence_group="micron_issuer",
        reliability="primary"),
    "hyperscaler_ir": Source(
        source="MSFT/AMZN/GOOGL/META capex and backlog disclosures",
        source_type="company_ir", metric="capex guidance, RPO/backlog",
        entity="hyperscalers", frequency="quarterly", publication_lag="0d",
        revision_policy="guidance is restated every quarter by design",
        point_in_time_available=True, independence_group="hyperscaler_issuers",
        reliability="primary",
        note="FOUR separate issuers -- genuinely four observations, unlike four "
             "outlets reporting one of them."),
    "alpaca_bars": Source(
        source="Alpaca SIP daily/minute bars", source_type="exchange",
        metric="OHLCV", entity="US equities", frequency="continuous",
        publication_lag="real time (SIP historical); IEX volume is 2-4% of consolidated",
        revision_policy="corrections rare", point_in_time_available=True,
        independence_group="market_tape", reliability="high",
        parser="alpha.broker.alpaca.stock_bars_multi",
        note="Measured 2026-08-26: the free plan serves HISTORICAL bars from the "
             "consolidated tape. A dollar-volume screen on IEX bars screens another market."),
    "alpaca_chain": Source(
        source="Alpaca options chain (indicative feed unless OPRA is provisioned)",
        source_type="exchange", metric="option bid/ask, implied move",
        entity="US options", frequency="continuous",
        publication_lag="~15 min on the indicative feed during RTH",
        revision_policy="none", point_in_time_available=True,
        independence_group="market_options", reliability="high",
        parser="alpha.data.chain",
        note="MEASURE the implied move here rather than quoting a number from a "
             "news article. Which feed was live is recorded on every snapshot."),
}


def get(source_id: str) -> Source | None:
    return REGISTRY.get(source_id)


def independent_count(source_ids: list[str]) -> int:
    """How many genuinely separate observers a citation list contains.

    Unknown ids count as one group EACH -- an unregistered source is treated as
    independent rather than silently folded in, because the alternative is a
    registry gap quietly deflating a real corroboration. Register it and the
    number becomes honest.
    """
    groups: set[str] = set()
    for sid in source_ids:
        src = REGISTRY.get(sid)
        groups.add(src.independence_group if src else f"unregistered:{sid}")
    return len(groups)


def corroboration(source_ids: list[str]) -> dict[str, Any]:
    """The citation list, its independent groups, and the strongest tier in it."""
    known = [REGISTRY[s] for s in source_ids if s in REGISTRY]
    groups: dict[str, list[str]] = {}
    for sid in source_ids:
        src = REGISTRY.get(sid)
        groups.setdefault(src.independence_group if src else f"unregistered:{sid}", []).append(sid)
    best = min((s.tier for s in known), default=len(SOURCE_TYPES))
    return {
        "cited": len(source_ids),
        "independent": len(groups),
        "groups": {g: ids for g, ids in sorted(groups.items())},
        "strongest_type": SOURCE_TYPES[best] if best < len(SOURCE_TYPES) else "unregistered",
        "note": ("cited count EXCEEDS independent count: some of these are restatements "
                 "of one another" if len(source_ids) > len(groups) else
                 "every citation is an independent observer"),
    }


def unregistered(source_ids: list[str]) -> list[str]:
    return sorted({s for s in source_ids if s not in REGISTRY})
