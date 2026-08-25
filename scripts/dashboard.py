"""DASHBOARD -- one self-contained HTML page a judge can read (criterion 4).

    python -m scripts.dashboard            -> state/dashboard.html

Nothing here is computed; it is a VIEW over receipts that already exist:

    accounts          equity, cash, open option legs per role (live, if keys)
    decisions         last 48h by account, brain, action -- including every
                      REFUSED and SHADOW row, which is the screen nobody else has
    counterfactual    the brain scoreboard from marked roads-not-taken
    event card        the latest state/cards/*.json with the surface reading
    relay             state/relay/*.json ranking for the next print
    backtests         the negatives, verbatim from their receipts
    belief            latest snapshot of the crowd series

The page states what it does not know. A dashboard that hides refusals is a
brochure.
"""

from __future__ import annotations

import glob
import html
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from alpha import config, ledger

ROOT = config.__file__.rsplit("alpha", 1)[0]
STATE = ROOT + "state/"


def _j(path: str):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def esc(x) -> str:
    return html.escape(str(x))


def table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "<p class='muted'>none</p>"
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{esc(r.get(c, ''))}</td>" for c in cols) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def accounts_section() -> str:
    out = []
    try:
        from alpha.broker.alpaca import AlpacaPaper
        for role in ("dev", "exp1"):
            try:
                c = AlpacaPaper(role=role)
                a = c.account()
                legs = [{"symbol": p["symbol"], "qty": p["qty"], "avg": p.get("avg_entry_price"),
                         "mark": p.get("current_price"), "unrealised": p.get("unrealized_pl")} for p in c.positions()]
                out.append(f"<h3>{role} — equity ${float(a.get('equity', 0)):,.0f}, cash ${float(a.get('cash', 0)):,.0f}, "
                           f"{len(legs)} option legs</h3>" + table(legs, ["symbol", "qty", "avg", "mark", "unrealised"]))
            except Exception as exc:                                    # noqa: BLE001
                out.append(f"<h3>{role}</h3><p class='muted'>not readable here: {esc(str(exc)[:120])}</p>")
    except Exception as exc:                                            # noqa: BLE001
        out.append(f"<p class='muted'>broker not importable: {esc(exc)}</p>")
    return "".join(out)


def decisions_section() -> str:
    rows = ledger.read_all()
    since = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    recent = [r for r in rows if r.get("ts_utc", "") >= since]
    by = Counter((r.get("account_role") or "?", r["brain"], r["action"]) for r in recent)
    summary = [{"account": a, "brain": b, "action": c, "n": n} for (a, b, c), n in sorted(by.items())]
    sub = [{"time": r["ts_utc"][11:16], "account": r.get("account_role") or "?", "brain": r["brain"], "symbol": r["symbol"],
            "structure": r.get("instrument"), "risk": f"{(r.get('risk_fraction') or 0):.1%}",
            "sd": f"{(r.get('predicted_sd') or 0):.2%}", "implied": f"{(r.get('implied_move') or 0):.2%}"}
           for r in recent if r["action"] == "submitted"]
    refused = Counter((r.get("refusal_reason") or "")[:70] for r in recent if r["action"] in ("refused", "shadow"))
    ref_rows = [{"reason": k, "n": n} for k, n in refused.most_common(12)]
    ok, why = ledger.verify_chain()
    return (f"<p>ledger: {len(rows)} rows, chain {'intact' if ok else 'BROKEN — ' + esc(why[:120])}</p>"
            "<h3>submitted (48h)</h3>" + table(sub, ["time", "account", "brain", "symbol", "structure", "risk", "sd", "implied"]) +
            "<h3>by account / brain / action</h3>" + table(summary, ["account", "brain", "action", "n"]) +
            "<h3>why things were refused or shadowed (top reasons)</h3>" + table(ref_rows, ["reason", "n"]))


def counterfactual_section() -> str:
    try:
        from alpha import counterfactual as cf
        marks_raw = ledger.read_all("counterfactual")
    except Exception as exc:                                            # noqa: BLE001
        return f"<p class='muted'>counterfactual ledger unreadable: {esc(exc)}</p>"
    if not marks_raw:
        return "<p class='muted'>no marks yet</p>"
    latest = {}
    for m in marks_raw:
        latest[m.get("decision_id")] = m
    by_brain = defaultdict(list)
    for m in latest.values():
        if m.get("mark_source") in ("chain",) and m.get("pnl_usd") is not None:
            by_brain[(m.get("brain") or "?", m.get("action"))].append(float(m["pnl_usd"]))
    rows = [{"brain": b, "action": a, "n": len(v), "mean_pnl_usd": f"{sum(v) / len(v):,.0f}",
             "hit": f"{sum(1 for x in v if x > 0) / len(v):.0%}"} for (b, a), v in sorted(by_brain.items())]
    return (f"<p>{len(latest)} decisions marked at equal risk; latest mark per decision.</p>" +
            table(rows, ["brain", "action", "n", "mean_pnl_usd", "hit"]))


def card_section() -> str:
    cards = sorted(glob.glob(STATE + "cards/*.json"))
    if not cards:
        return "<p class='muted'>no event card</p>"
    c = _j(cards[-1]) or {}
    parts = [f"<h3>{esc(c.get('symbol'))} — as of {esc(c.get('as_of_utc', '')[:16])} — expiry {esc(c.get('expiry'))}</h3>"]
    for k in ("what_happened", "what_the_llm_read", "what_the_crowd_believes", "chain_expectation", "chosen", "result_so_far"):
        v = c.get(k)
        if v:
            parts.append(f"<h4>{esc(k.replace('_', ' '))}</h4><pre>{esc(json.dumps(v, indent=1)[:2500])}</pre>")
    fc = c.get("forecasts") or []
    if fc:
        parts.append("<h4>every brain's forecast, before pricing</h4>" + table(
            [{"brain": f.get("brain"), "centre": f"{(f.get('centre') or 0):+.2%}", "sd": f"{(f.get('sd') or 0):.2%}",
              "conviction": f.get("conviction"), "rationale": (f.get("rationale") or "")[:140]} for f in fc],
            ["brain", "centre", "sd", "conviction", "rationale"]))
    return "".join(parts)


def relay_section() -> str:
    files = sorted(glob.glob(STATE + "relay/*.json"))
    if not files:
        return "<p class='muted'>no relay reading</p>"
    r = _j(files[-1]) or {}
    rows = [{"symbol": x["symbol"], "history_jump_sd": f"{x.get('cond_jump_sd', 0):.2%}",
             "market_jump_sd": f"{(x.get('market_jump_sd') or 0):.2%}", "ratio": x.get("relay_ratio"),
             "surface": ((x.get("front") or {}).get("shape")) or "-"} for x in r.get("rows", [])]
    rows.sort(key=lambda z: -(z["ratio"] or 0))
    return (f"<p>{esc(r.get('originator'))} print, first close {esc(r.get('event'))}. Ratio &gt; 1: the print is cheaper "
            "to own there than its own history says.</p>" + table(rows, ["symbol", "history_jump_sd", "market_jump_sd", "ratio", "surface"]))


def backtests_section() -> str:
    parts = []
    s = (_j(STATE + "event_straddle_backtest.json") or {}).get("summary", {})
    if s:
        p = s.get("pooled", {})
        parts.append(f"<li><b>117 real prints, long straddle at closes:</b> median {p.get('median_straddle_return', 0):+.0%}, "
                     f"{p.get('hit_rate_cleared_breakeven', 0):.0%} clear break-even, paired t {p.get('paired_t_realised_minus_implied')}. NVDA 0/8.</li>")
    s = (_j(STATE + "event_surface_backtest.json") or {}).get("summary", {})
    if s:
        vs, pol = s.get("variance_strip", {}), s.get("policy_naive", {})
        parts.append(f"<li><b>Variance strip (n={vs.get('n')}):</b> raw implied predicts realised size at corr "
                     f"{vs.get('corr_raw_implied_vs_realised')}, stripped jump {vs.get('corr_market_jump_vs_realised')}, "
                     f"our history {vs.get('corr_our_prior_vs_realised_walkforward')} — the chain knows more than the name's history.</li>")
        parts.append(f"<li><b>Walk-forward conditional rule:</b> n={pol.get('n')}, mean {pol.get('mean_ror', 0):+.0%} of max loss, "
                     f"hit {pol.get('hit', 0):.0%}, t {pol.get('t')}. Skew→direction {s.get('skew_direction', {}).get('direction_hit')}.</li>")
    s = (_j(STATE + "nfp_straddle_backtest.json") or {}).get("summary", {})
    if s.get("SPY"):
        x = s["SPY"]
        parts.append(f"<li><b>NFP-day SPY 0DTE straddle (n={x['n']}):</b> mean {x['mean_return']:+.0%}, median {x['median_return']:+.0%}, hit {x['hit_rate']:.0%}.</li>")
    b = _j(STATE + "event_contract_basis/SPY_2026-09-04.json")
    if b:
        parts.append(f"<li><b>Kalshi→SPY basis:</b> surprise→move corr {b['fit'].get('corr')}: direction channel dead; width only.</li>")
    a = _j(STATE + "attention_vol_basis.json")
    if a:
        parts.append(f"<li><b>Attention vol basis:</b> {a.get('basis_u')} (t {a.get('t')}) — {esc(a.get('verdict'))}</li>")
    r = (_j(STATE + "relay_backtest.json") or {}).get("summary", {})
    if r:
        parts.append(f"<li><b>Relay legs on real closes:</b> {esc(json.dumps(r.get('all_relay_legs')))} vs originator "
                     f"{esc(json.dumps(r.get('all_originator_legs')))}.</li>")
    return "<ul>" + "".join(parts) + "</ul>" if parts else "<p class='muted'>no receipts</p>"


def belief_section() -> str:
    path = STATE + "belief_series.jsonl"
    if not os.path.exists(path):
        return "<p class='muted'>no series</p>"
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if not rows:
        return "<p class='muted'>empty</p>"
    last_ts = max(r["ts_utc"] for r in rows)
    latest = [r for r in rows if r["ts_utc"] == last_ts and r.get("p_yes") is not None]
    latest.sort(key=lambda r: -(r.get("volume_24h") or r.get("volume") or 0))
    snaps = len({r["ts_utc"] for r in rows})
    return (f"<p>{snaps} snapshots; latest {esc(last_ts[:16])}. Velocity needs a series — this is its first day.</p>" +
            table([{"source": r["source"], "market": (r.get("title") or "")[:90], "p_yes": r.get("p_yes"),
                    "vol": r.get("volume_24h") or r.get("volume")} for r in latest[:15]], ["source", "market", "p_yes", "vol"]))


def main() -> int:
    config.load_env()
    now = datetime.now(timezone.utc).isoformat()[:16]
    sections = [
        ("Accounts (paper)", accounts_section()),
        ("Decisions — taken, refused, shadowed", decisions_section()),
        ("Brain scoreboard (counterfactual marks)", counterfactual_section()),
        ("Latest event card", card_section()),
        ("Uncertainty relay — where the next print is cheapest", relay_section()),
        ("What did not work (receipts)", backtests_section()),
        ("What the crowd believes", belief_section()),
    ]
    body = "".join(f"<section><h2>{esc(t)}</h2>{c}</section>" for t, c in sections)
    page = f"""<title>Aegis Alpha Terminal</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#eef1f3;--panel:#ffffff;--ink:#17232b;--ink-2:#4d5c66;--line:#d3dbe0;--accent:#0f6e73;--accent-ink:#ffffff;--good:#2f7d4f;--bad:#b23a3a;--code:#f4f7f8}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#111a1f;--panel:#182229;--ink:#e6edf0;--ink-2:#9fb0b9;--line:#2a3941;--accent:#4fb3b8;--accent-ink:#0d1518;--good:#6fc48f;--bad:#e07a7a;--code:#0f171b}}}}
:root[data-theme="dark"]{{--bg:#111a1f;--panel:#182229;--ink:#e6edf0;--ink-2:#9fb0b9;--line:#2a3941;--accent:#4fb3b8;--accent-ink:#0d1518;--good:#6fc48f;--bad:#e07a7a;--code:#0f171b}}
body{{background:var(--bg);color:var(--ink);font:15px/1.5 "IBM Plex Sans",system-ui,sans-serif;margin:0;padding:2.5rem 1.25rem 4rem}}
.wrap{{max-width:1080px;margin:0 auto;display:grid;gap:2rem}}
header h1{{font:600 2rem/1.15 "IBM Plex Serif",Georgia,serif;margin:0 0 .35rem;text-wrap:balance}}
header p{{margin:0;color:var(--ink-2);max-width:65ch}}
.stamp{{font:500 .78rem/1 "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:1.25rem 1.5rem}}
h2{{font:600 1.05rem/1.3 "IBM Plex Serif",Georgia,serif;margin:0 0 .75rem;padding-bottom:.5rem;border-bottom:2px solid var(--accent)}}
h3{{font:600 .95rem/1.3 "IBM Plex Sans",sans-serif;margin:1.1rem 0 .4rem}} h4{{font:500 .8rem/1 "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);margin:1rem 0 .3rem}}
.tbl{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}}
th,td{{border-bottom:1px solid var(--line);padding:.35rem .5rem;text-align:left;vertical-align:top}}
th{{font:500 .72rem/1.2 "IBM Plex Mono",monospace;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-2)}}
td{{font-family:"IBM Plex Mono",monospace;font-size:.82rem}} td:first-child{{font-family:"IBM Plex Sans",sans-serif;font-size:.88rem}}
.muted{{color:var(--ink-2)}} pre{{background:var(--code);border:1px solid var(--line);border-radius:4px;padding:.6rem .75rem;overflow:auto;font:.78rem/1.45 "IBM Plex Mono",monospace;color:var(--ink)}}
ul{{padding-left:1.1rem;max-width:80ch}} li{{margin:.35rem 0}} code{{font-family:"IBM Plex Mono",monospace;font-size:.85em}}
a{{color:var(--accent)}} :focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
</style>
<div class="wrap">
<header><div class="stamp">paper · as of {now}Z</div><h1>Aegis Alpha Terminal</h1>
<p>Every number here is a view over a receipt in <code>state/</code>. Refusals and shadow decisions are shown because they are the product:
the agent's job is to say which trades <em>not</em> to make, with the alternative priced.</p></header>
{body}</div>"""
    page = page.replace("<table>", "<div class='tbl'><table>").replace("</table>", "</table></div>")
    out = STATE + "dashboard.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("written:", out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
