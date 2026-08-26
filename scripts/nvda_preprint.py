"""Freeze the NVDA print as an information state, BEFORE the information arrives.

    python -m scripts.nvda_preprint --seal          # build, measure, seal (pre-print only)
    python -m scripts.nvda_preprint --show          # read back what was sealed
    python -m scripts.nvda_preprint --refresh-prices  # re-freeze prices, keep the seal

WHAT IT SEALS
=============
Two artefacts, both `SHADOW_ONLY`, both hashed:

- `state/event_state/NVDA_2026-08-27_vector.json` -- thirteen typed fields with a
  prior, a resolution rule and a RANK. The rank is the falsifiable claim: we say
  before the print that the Q3 guide carries more information than the Q2
  headline, and tomorrow can prove that wrong.
- `state/event_state/NVDA_2026-08-27_shock.json` -- the propagation graph, each
  edge carrying a sign, a lag, an observable, a frozen pre-print price and a
  MEASURED NVDA-beta.

WHAT IS MEASURED HERE RATHER THAN QUOTED
========================================
The option-implied move comes from OUR chain, not from a news article. The
existing evidence bundle carries `reported_implied_move_28aug: 0.0558` sourced
to a Reuters preview -- fine as a cross-check, useless as a measurement, because
we cannot know what it was computed from. Same for the betas: whether the market
already trades COHR as an NVDA name is a fact about the tape, and the tape is
right here.

THE REFUSAL
===========
`--seal` refuses to run after the release. A "pre-print" artefact written at
17:00 ET is not evidence of anything, and the failure mode is not dishonesty --
it is a script that runs late and produces a file nobody re-reads the timestamp
on.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha import config
from alpha.broker.alpaca import AlpacaPaper, BrokerRefusal
from alpha.data import chain as chain_mod
from alpha.event_state import (Field, Node, ShockGraph, StateVector, measure_beta,
                               residual_sd)
from alpha.sources import registry

SUBJECT = "NVDA"
EVENT_DATE = "2026-08-27"          # day-0: the session that PRICES the print
RELEASE_UTC = "2026-08-26T20:20:00+00:00"   # ~16:20 ET, after the close
EXPIRY = "2026-08-28"
CONTROL = "PH:NVDA:2026-08-27:b29d506d"


# --------------------------------------------------------------------- the vector
def build_vector() -> StateVector:
    """Thirteen fields. Twelve are the brief's; the thirteenth is the one its own
    ranking put FIRST and its own field list omitted -- the forward guide."""
    f = [
        Field("q3_guide_surprise", 1,
              "What does the company guide Q3 FY2027 revenue to, against the ~$104.2bn "
              "the street carries?",
              "usd_bn",
              "Street ~$104.2bn (+~83% y/y), as of 25 Aug previews. NVIDIA guides a point "
              "with a +/-2% band; the guide is the number the stock trades on.",
              "Read the guidance paragraph of the CFO commentary. Record the midpoint in "
              "$bn and the band. Surprise = midpoint - 104.2.",
              ["nvda_ir", "consensus_sellside"]),
        Field("gross_margin_surprise", 2,
              "Non-GAAP gross margin, reported and guided, against ~75%?",
              "pct",
              "Company guided ~75% for Q2. The live question is whether HBM cost inflation "
              "is being absorbed or passed through, and what the Q3 guide implies.",
              "Record reported non-GAAP GM and the Q3 GM guide. Surprise = reported - 75.0. "
              "A Q3 GM guide below 74% is the bear trigger regardless of the revenue line.",
              ["nvda_ir"]),
        Field("HBM_cost_pressure", 3,
              "Does management quantify memory cost inflation, and does it flow to price?",
              "ordinal",
              "Micron reports ~$22bn of committed long-term supply and tightness into 2027; "
              "customers were notified (22 Aug) of AI-system price rises above 15% for some "
              "early-2027 systems, linked to HBM. So the cost is real and the pass-through "
              "is attempted; whether it holds is unknown.",
              "ordinal in {absorbed, passed_through, partially_passed, not_addressed}, plus "
              "any quantified figure. This is the MECHANISM behind field 2 and it forecasts "
              "the next three quarters, not this one.",
              ["nvda_ir", "micron_ir", "reuters"]),
        Field("Rubin_timing_change", 4,
              "Is Rubin on schedule, and what does the ramp language change?",
              "ordinal",
              "Rubin debut is the quarter's headline product question. Foxconn has said "
              "rack production prepares to start in Q4.",
              "ordinal in {ahead, on_schedule, slipped, not_addressed}. Record the exact "
              "ramp phrasing -- 'production' vs 'sampling' vs 'volume' are different claims. "
              "A slip is a bigger fact than a revenue miss because it moves FY2028.",
              ["nvda_ir", "foxconn_monthly"]),
        Field("customer_financing_quality", 5,
              "How much of the demand is internally funded, and how much is "
              "financing-dependent?",
              "ordinal",
              "NVIDIA has helped arrange very large AI-infrastructure financing and carries "
              "commitments connected to the buildout, while AI-related corporate borrowing "
              "has grown quickly. This is the question the street has started asking and "
              "nobody has a number for.",
              "ordinal in {not_addressed, addressed_qualitatively, quantified}. Record any "
              "figure for vendor financing, backstops, guarantees or receivable "
              "concentration. NOT_ADDRESSED is itself informative and must be recorded as "
              "such, not left blank.",
              ["nvda_ir", "reuters"]),
        Field("future_capacity_constraint", 6,
              "What is named as the binding constraint on the next four quarters?",
              "ordinal",
              "Candidates: CoWoS/advanced packaging, HBM supply, power availability, "
              "grid interconnect, or none.",
              "ordinal in {packaging, memory, power, grid, none, not_addressed}. The named "
              "constraint decides which SUPPLIER the demand actually reaches -- it is the "
              "single most useful field for the propagation graph.",
              ["nvda_ir"]),
        Field("datacenter_surprise", 7,
              "Data Center revenue against the ~$85bn the street carries?",
              "usd_bn",
              "Q1 Data Center was $75.2bn, +92% y/y. Street around $85bn for Q2.",
              "Record reported Data Center revenue in $bn. Surprise = reported - 85.0.",
              ["nvda_ir", "consensus_sellside"]),
        Field("hyperscale_growth", 8,
              "What share of Data Center revenue is the large cloud customers, and is "
              "concentration rising?",
              "pct",
              "Recent 10-Qs disclose significant customer concentration. AWS backlog ~$496bn "
              "with 2026 capex ~$220bn; Alphabet 2026 capex ~$195-205bn.",
              "Record the disclosed large-customer percentage if given. Rising concentration "
              "raises the financing question in field 5 rather than settling it.",
              ["nvda_ir", "hyperscaler_ir"]),
        Field("custom_silicon_competition", 9,
              "Does the print or the call acknowledge accelerating custom-silicon "
              "substitution?",
              "ordinal",
              "Google/Marvell arrangement worth up to ~$120bn to Marvell through FY2033 if "
              "targets are met. Hyperscalers are building substitutes; that is a fact "
              "regardless of tonight.",
              "ordinal in {denied, acknowledged, quantified, not_addressed}. Higher value = "
              "MORE competition. The graph's AVGO/MRVL nodes are signed off THIS field.",
              ["nvda_ir", "reuters"]),
        Field("Blackwell_demand", 10,
              "Blackwell shipment/demand language: sold out, in balance, or normalising?",
              "ordinal",
              "The prior cycle's language was persistent supply shortage.",
              "ordinal in {sold_out, tight, in_balance, normalising, not_addressed}.",
              ["nvda_ir"]),
        Field("ACIE_growth", 11,
              "Non-data-centre segments (auto, robotics, gaming, professional viz) -- "
              "growth and any inflection?",
              "pct",
              "Small relative to Data Center; matters only as an option on a second engine.",
              "Record segment revenue and y/y growth. A surprise here is a change in the "
              "STORY, not in the quarter.",
              ["nvda_ir"]),
        Field("China_optional_revenue", 12,
              "Is any China revenue included in guidance, or explicitly excluded?",
              "ordinal",
              "Recent guidance practice has been to exclude uncertain China revenue, making "
              "it a free option on the guide rather than a component of it.",
              "ordinal in {excluded, partially_included, included, not_addressed}, plus any "
              "$ figure. EXCLUDED is bullish for the quality of the guide in field 1.",
              ["nvda_ir"]),
        Field("revenue_surprise", 13,
              "Q2 headline revenue against consensus ~$92.05bn?",
              "usd_bn",
              "Consensus ~$92.05bn (+96.9% y/y) as of 25 Aug, ABOVE the company's own May "
              "guide of $91bn +/-2%. Adjusted EPS ~$2.07.",
              "Record reported revenue in $bn. Surprise = reported - 92.05. RANKED LAST ON "
              "PURPOSE: the quarter is nine weeks old and largely pre-announced by the "
              "supply chain; the guide is the news.",
              ["nvda_ir", "consensus_sellside"]),
    ]
    return StateVector(
        subject=SUBJECT, event="Q2 FY2027 earnings", event_date=EVENT_DATE,
        release_expected_utc=RELEASE_UTC, fields=f, control_record=CONTROL,
    )


# ---------------------------------------------------------------------- the graph
def build_graph() -> ShockGraph:
    n = [
        # --- the demand chain: a stronger NVDA state pulls these up
        Node("TSM", "foundry + advanced packaging", "future_capacity_constraint",
             "CoWoS capacity is the named bottleneck in most cycles; every accelerator "
             "shipped is TSMC wafer and packaging.", +1, "high", 1,
             "TSMC monthly revenue (~10 days after month end) and any CoWoS capacity comment"),
        Node("MU", "HBM", "HBM_cost_pressure",
             "HBM is the scarce input; tight supply and rising price are REVENUE to Micron "
             "and COST to NVIDIA. Same fact, opposite signs.", +1, "high", 1,
             "Micron quarterly HBM commentary, contract pricing, take-or-pay terms"),
        Node("AMAT", "semicap", "future_capacity_constraint",
             "Capacity named as the constraint becomes equipment orders, at a lag.",
             +1, "medium", 3,
             "WFE order commentary; TSMC/Samsung capex plans"),
        Node("LRCX", "semicap (deposition/etch, HBM-levered)", "HBM_cost_pressure",
             "HBM stack build-out is disproportionately deposition and etch intensive.",
             +1, "medium", 3, "HBM-attributed revenue share in quarterly commentary"),
        Node("KLAC", "semicap (process control)", "future_capacity_constraint",
             "Advanced packaging yield is inspection-intensive.", +1, "medium", 3,
             "process-control intensity commentary on advanced packaging"),
        Node("ANET", "datacentre networking", "datacenter_surprise",
             "Scale-out clusters need switching in near-fixed ratio to accelerators.",
             +1, "high", 1, "cloud-titan revenue concentration; 800G port shipments"),
        Node("COHR", "optical components/transceivers", "datacenter_surprise",
             "Cluster size drives optical port count faster than accelerator count.",
             +1, "high", 2, "datacom transceiver revenue and 800G/1.6T mix"),
        Node("LITE", "optical components", "datacenter_surprise",
             "Same mechanism as COHR; different customer mix.", +1, "high", 2,
             "cloud/datacom segment revenue"),
        Node("AAOI", "optical (small cap, high beta)", "datacenter_surprise",
             "Same edge, far smaller and noisier -- included as a HIGH-beta control: if it "
             "moves and COHR does not, the move is beta, not information.",
             +1, "medium", 2, "datacenter transceiver bookings"),
        Node("GLW", "optical fibre/glass", "datacenter_surprise",
             "Interconnect volume at one further remove; a slower, cleaner read.",
             +1, "medium", 3, "optical communications segment growth"),
        Node("SMCI", "AI server ODM", "Blackwell_demand",
             "Rack-scale systems ship through ODMs; demand language converts to backlog.",
             +1, "high", 1, "quarterly backlog and rack shipment commentary"),
        Node("DELL", "AI server OEM", "Blackwell_demand",
             "Same edge, larger and more diluted by a non-AI business.", +1, "medium", 1,
             "AI server backlog disclosure"),
        Node("HPE", "AI server OEM", "Blackwell_demand",
             "Smallest share of the three; the weakest version of the same edge.",
             +1, "low", 2, "AI systems orders"),
        Node("VRT", "power and thermal for datacentres", "future_capacity_constraint",
             "Power/cooling is the constraint most often named after packaging, and it is "
             "the one with the longest lead time.", +1, "high", 2,
             "orders and backlog; book-to-bill"),
        Node("ETN", "electrical infrastructure", "future_capacity_constraint",
             "Datacentre electrical distribution; broad industrial base dilutes it.",
             +1, "medium", 3, "datacentre vertical growth in segment commentary"),
        Node("GEV", "grid + power generation", "future_capacity_constraint",
             "If POWER rather than packaging is named, this is where the constraint lands.",
             +1, "medium", 5, "grid equipment orders; interconnect queue commentary"),
        Node("PWR", "electrical construction", "future_capacity_constraint",
             "Builds the interconnect. Longest lag in the graph.", +1, "medium", 5,
             "backlog attributable to datacentre and transmission"),
        Node("MOD", "thermal management/liquid cooling", "future_capacity_constraint",
             "Rack density forces liquid cooling; a small, direct read.", +1, "medium", 3,
             "datacentre cooling revenue growth"),
        # --- the substitution chain: signed OFF the competition field, not the demand
        Node("AVGO", "custom silicon (XPU) + networking", "custom_silicon_competition",
             "Two edges of OPPOSITE sign: the AI capex tide lifts it, and every custom "
             "accelerator it wins is an accelerator NVIDIA did not sell. Signed off the "
             "COMPETITION field so the two are not silently averaged.", +1, "high", 1,
             "custom XPU revenue and named programme wins"),
        Node("MRVL", "custom silicon", "custom_silicon_competition",
             "Same edge; the Google arrangement makes it the purest listed expression of "
             "substitution.", +1, "high", 1, "custom compute revenue and programme milestones"),
        # --- the affordability chain: the buyers
        Node("MSFT", "hyperscale buyer", "customer_financing_quality",
             "A buyer, not a supplier: a strong print confirms its AI revenue AND raises "
             "its cost. The sign is genuinely ambiguous and the exposure is declared LOW "
             "for exactly that reason.", +1, "low", 1,
             "capex guidance, RPO/backlog, and depreciation schedule changes"),
        Node("AMZN", "hyperscale buyer", "customer_financing_quality",
             "AWS backlog and 2026 capex are the largest single demand disclosure outside "
             "NVIDIA itself.", +1, "low", 1, "AWS revenue growth, backlog, capex guide"),
        Node("GOOGL", "hyperscale buyer + custom silicon owner", "custom_silicon_competition",
             "The one buyer that is also the substitution threat, via TPU and the Marvell "
             "arrangement.", +1, "low", 1, "TPU deployment commentary; capex guide"),
        Node("META", "hyperscale buyer", "customer_financing_quality",
             "Pure buyer with no cloud resale, so its capex is the cleanest read on "
             "internally-funded demand.", +1, "low", 1, "capex guide and depreciation life"),
    ]
    return ShockGraph(
        subject=SUBJECT, event_date=EVENT_DATE, nodes=n,
        chains=[
            "NVDA demand -> HBM -> advanced packaging -> optical -> server ODM",
            "NVDA demand -> power -> cooling -> grid interconnect",
            "memory inflation -> server BOM -> customer AI ROI -> capex affordability",
            "capex affordability -> custom silicon substitution -> NVDA share",
        ],
    )


# ------------------------------------------------------------------- measurement
def measure(client: AlpacaPaper, graph: ShockGraph) -> dict:
    """Freeze prices, measure NVDA-betas, and measure the implied move ourselves."""
    tickers = [n.ticker for n in graph.nodes]
    start = (datetime.now(timezone.utc) - timedelta(days=260)).date().isoformat()
    bars = client.stock_bars_multi(tickers + [SUBJECT], start=start, timeframe="1Day")
    nvda_bars = bars.get(SUBJECT, [])

    now = datetime.now(timezone.utc).isoformat()
    for node in graph.nodes:
        b = bars.get(node.ticker, [])
        beta, r2, n = measure_beta(b, nvda_bars)
        node.nvda_beta, node.beta_r2, node.beta_n = beta, r2, n
        if beta is not None:
            node.resid_sd = residual_sd(b, nvda_bars, beta)
            # 2.8 sigma is the usual 80%-power two-sided constant. On ONE event
            # there is no sqrt(T) to help, so this number is large on purpose.
            node.mde_1event = (round(2.8 * node.resid_sd, 4)
                               if node.resid_sd is not None else None)
        if b:
            node.frozen_price = float(b[-1].get("c") or 0.0)
            node.frozen_at = str(b[-1].get("t") or "")

    out = {"bars_start": start, "measured_at": now,
           "nvda_last_close": float(nvda_bars[-1].get("c") or 0.0) if nvda_bars else None,
           "nvda_last_bar_t": str(nvda_bars[-1].get("t") or "") if nvda_bars else None,
           "coverage": f"{sum(1 for n in graph.nodes if n.nvda_beta is not None)}/{len(graph.nodes)}"}

    # The implied move, MEASURED from our own chain rather than quoted.
    try:
        ch = chain_mod.fetch(client, SUBJECT, expiry_from=EXPIRY, expiry_to=EXPIRY)
        im = ch.implied_move(EXPIRY)
        out["implied_move_measured"] = round(im, 4) if im else None
        out["implied_move_expiry"] = EXPIRY
        out["options_feed"] = config.options_feed()
        out["implied_move_note"] = (
            "measured from our own chain at the timestamp above. The evidence bundle's "
            "0.0558 is a REPORTED figure from a 25 Aug preview and is kept only as a "
            "cross-check -- we cannot know what it was computed from.")
    except (BrokerRefusal, Exception) as exc:   # noqa: BLE001 - a failed measurement is recorded, not raised
        out["implied_move_measured"] = None
        out["implied_move_error"] = str(exc)[:300]
    return out


def _too_late() -> bool:
    return datetime.now(timezone.utc) >= datetime.fromisoformat(RELEASE_UTC)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seal", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--refresh-prices", action="store_true")
    p.add_argument("--power", action="store_true",
                   help="can this graph resolve an underreaction at all, and on how many "
                        "events. ASK THIS BEFORE reading any ranking it produces.")
    p.add_argument("--control", default="SMH",
                   help="sector control in the residual regression; '' for none")
    p.add_argument("--target", type=float, default=0.02,
                   help="the underreaction size we would want to detect")
    p.add_argument("--role", default="dev")
    p.add_argument("--force-late", action="store_true",
                   help="seal after the release anyway. The artefact is then NOT pre-print "
                        "evidence and is stamped as such.")
    a = p.parse_args()
    config.load_env()

    from alpha.event_state import STORE
    vpath = STORE / f"{SUBJECT}_{EVENT_DATE}_vector.json"
    gpath = STORE / f"{SUBJECT}_{EVENT_DATE}_shock.json"

    if a.show:
        for path in (vpath, gpath):
            if not path.exists():
                print(f"MISSING {path}")
                continue
            d = json.loads(path.read_text(encoding="utf-8"))
            print(f"\n=== {path.name} ===")
            print(f"sealed_at {d.get('sealed_at')}  seal {d.get('seal')}  "
                  f"valid {d.get('seal_valid')}")
            if "fields" in d:
                print("information hierarchy (1 = most informative):")
                for f in sorted(d["fields"], key=lambda x: x["rank"]):
                    print(f"  {f['rank']:2d}. {f['name']:<30} {f['question'][:64]}")
            if "nodes" in d:
                print(f"{len(d['nodes'])} nodes")
                for n in sorted(d["nodes"], key=lambda x: -(x.get("nvda_beta") or 0)):
                    print(f"  {n['ticker']:<6} beta {str(n.get('nvda_beta')):>6} "
                          f"r2 {str(n.get('beta_r2')):>5}  {n['exposure']:<6} "
                          f"lag {n['lag_sessions']}  <- {n['edge_from']}")
        return 0

    if a.power:
        from alpha.event_state import group_power

        if not gpath.exists():
            print("nothing sealed yet; run --seal first")
            return 2
        graph = ShockGraph.load(gpath)
        client = AlpacaPaper(role=a.role)
        tickers = [n.ticker for n in graph.nodes]
        extra = [SUBJECT] + ([a.control] if a.control else [])
        start = (datetime.now(timezone.utc) - timedelta(days=260)).date().isoformat()
        bars = client.stock_bars_multi(tickers + extra, start=start, timeframe="1Day")
        groups: dict[str, list[str]] = {}
        for n in graph.nodes:
            groups.setdefault(n.edge_from, []).append(n.ticker)
        rows = group_power(
            {t: bars.get(t, []) for t in tickers}, bars.get(SUBJECT, []), groups,
            control_bars=bars.get(a.control) if a.control else None, target=a.target)
        print(f"\nPOWER OF THE SHOCK GRAPH  (driver NVDA, control {a.control or 'none'}, "
              f"target underreaction {a.target:.1%})")
        print(f"{'edge':<30}{'n':>3}{'residSD':>10}{'MDE 1 event':>13}"
              f"{'events needed':>15}")
        for r in rows:
            if "mde_1event" not in r:
                print(f"{r['edge']:<30}{len(r['tickers']):>3}  {r['verdict']}")
                continue
            print(f"{r['edge']:<30}{len(r['tickers']):>3}{r['group_resid_sd']:>10.4f}"
                  f"{r['mde_1event']:>13.1%}{r['events_for_target']:>15.1f}")
        print("\nRead this BEFORE any ranking: an edge whose MDE exceeds the move the "
              "driver can produce is a rank with no resolution behind it.")
        return 0

    if not (a.seal or a.refresh_prices):
        p.error("choose --seal, --show, --power or --refresh-prices")

    if _too_late() and not a.force_late:
        print(f"REFUSED: it is {datetime.now(timezone.utc).isoformat()} and the release was "
              f"expected {RELEASE_UTC}.\nA 'pre-print' artefact written after the print is "
              "not pre-print evidence. Use --force-late only to write a clearly-stamped "
              "post-hoc record.")
        return 2

    client = AlpacaPaper(role=a.role)

    if a.refresh_prices:
        if not gpath.exists():
            print("nothing sealed yet; run --seal first")
            return 2
        graph = ShockGraph.load(gpath)
        m = measure(client, graph)
        # The seal covers the HYPOTHESIS (edges, signs, lags, observables), not the
        # price snapshot, so re-freezing prices closer to the print leaves it valid.
        graph.save(gpath)
        obs = STORE / f"{SUBJECT}_{EVENT_DATE}_observations.jsonl"
        with obs.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(m) + "\n")
        print(f"prices refreshed, seal still valid: {graph.verify()}")
        print(f"observation appended to {obs.name} -- the SEALED market_expectation is a "
              "commitment and is never rewritten; later readings are new observations.")
        print(json.dumps(m, indent=1))
        return 0

    if vpath.exists() or gpath.exists():
        print(f"REFUSED: {vpath.name} or {gpath.name} already exists. A second seal would "
              "overwrite a commitment. Delete deliberately if this is a re-run.")
        return 2

    vector = build_vector()
    graph = build_graph()

    print(f"measuring {len(graph.nodes)} nodes ...")
    m = measure(client, graph)
    vector.market_expectation = {
        "consensus_revenue_usd_bn": 92.05,
        "consensus_revenue_asof": "2026-08-25",
        "consensus_eps_adj": 2.07,
        "consensus_q3_revenue_usd_bn": 104.2,
        "company_guide_usd_bn": 91.0,
        "company_guide_band": 0.02,
        "company_gm_guide_pct": 75.0,
        "reported_implied_move_28aug": 0.0558,
        "reported_implied_move_source": "reuters/moomoo previews 24-25 Aug (CROSS-CHECK ONLY)",
        **m,
        "our_own_backtest": "NVDA straddles 0/8 on the last 8 SEC-dated prints, median -46%",
        "corroboration_of_the_bundle": registry.corroboration(
            ["nvda_ir", "reuters", "consensus_sellside", "taiwan_moea", "tsmc_monthly",
             "foxconn_monthly", "micron_ir", "hyperscaler_ir"]),
    }

    vector.seal_now()
    graph.seal_now()
    vector.save(vpath)
    graph.save(gpath)

    print(f"\nSEALED  vector {vector.seal}  at {vector.sealed_at}")
    print(f"SEALED  graph  {graph.seal}  at {graph.sealed_at}")
    print(f"control record (NOT modified): {CONTROL}")
    print(f"\nimplied move measured: {m.get('implied_move_measured')} "
          f"(reported cross-check 0.0558)  feed={m.get('options_feed')}")
    print(f"beta coverage: {m['coverage']}   NVDA last close {m.get('nvda_last_close')}")
    print("\ninformation hierarchy, as committed:")
    for name in vector.hierarchy:
        print(f"  {name}")
    print("\nthe market already prices these links (beta >= 1.0):")
    for n in sorted(graph.nodes, key=lambda x: -(x.nvda_beta or 0)):
        if (n.nvda_beta or 0) >= 1.0:
            print(f"  {n.ticker:<6} {n.nvda_beta}")
    print("\nHIGH declared exposure the market BARELY prices (beta < 0.5) -- "
          "where an underreaction can live:")
    for n in graph.nodes:
        if n.exposure == "high" and (n.nvda_beta or 0) < 0.5:
            print(f"  {n.ticker:<6} beta {n.nvda_beta}  <- {n.edge_from}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
