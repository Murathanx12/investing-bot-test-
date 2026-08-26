"""POST_EVENT_RELAY_v1 -- after the SOURCE reports, which linked name has not caught up?

    python -m scripts.post_event_relay [--json]

The pre-event RELAY (buy peer vol cheaply before the source prints) is refuted
on 290 legs and stays dead. This is the other half of the question, and it is
about DIRECTION after the information is public:

    source S prints; day 0 is the first close reflecting it
    each peer P moves r_P(0) on day 0; historically it moves beta_P * r_S(0)
    residual   e_P = r_P(0) - beta_P * r_S(0)      (how much P has NOT reacted)
    forward    f_P = r_P(+1..+3) - beta_mkt * r_QQQ(+1..+3)

If the peer continues in the direction of the residual -- f_P has the same sign
as e_P -- there is a post-event underreaction to buy with a directional spread
after the print. If f_P has the opposite sign the day-0 move was an over-
reaction and the trade is the reverse. If neither, the relay is dead in both
directions.

Everything is close-to-close stock bars; betas are fitted on the 120 sessions
BEFORE each print (never including it). The receipt also grades the plain
"continuation" of the source itself (PEAD on S), which is the same test with
P = S.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from alpha import config
from alpha.brains.vol_gap import _daily_bars
from alpha.broker.alpaca import AlpacaPaper

SOURCES = {"NVDA": ["AMD", "AVGO", "MU", "TSM", "SMH", "ARM", "MRVL"],
           "AVGO": ["NVDA", "AMD", "MRVL", "SMH", "MU"],
           "AMD": ["NVDA", "AVGO", "MU", "SMH"],
           "MU": ["NVDA", "AMD", "SMH", "WDC"],
           "TSLA": ["RIVN", "NIO", "LCID"],
           "META": ["GOOGL", "SNAP", "PINS"],
           "MSFT": ["AMZN", "GOOGL", "ORCL"],
           "AMZN": ["MSFT", "GOOGL", "SHOP"],
           "GOOGL": ["META", "MSFT", "AMZN"],
           "AAPL": ["QCOM", "SWKS", "AVGO"],
           "PANW": ["CRWD", "ZS", "FTNT"]}
BETA_WINDOW = 120
FORWARD_DAYS = 3


def _state_dir() -> Path:
    return Path(config.__file__).resolve().parent.parent / "state"


def _rets(bars: list[dict]) -> tuple[list[str], dict[str, float]]:
    days = [b["t"][:10] for b in bars]
    cl = [float(b["c"]) for b in bars]
    return days, {days[i]: cl[i] / cl[i - 1] - 1.0 for i in range(1, len(days))}


def _beta(x: list[float], y: list[float]) -> float:
    mx, my = statistics.mean(x), statistics.mean(y)
    vx = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / vx if vx > 0 else 0.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    config.load_env()
    client = AlpacaPaper()
    events = json.loads((_state_dir() / "event_straddle_backtest.json").read_text(encoding="utf-8"))["events"]
    names = sorted(set(SOURCES) | {q for v in SOURCES.values() for q in v} | {"QQQ"})
    data = {}
    for n in names:
        try:
            data[n] = _rets(_daily_bars(client, n, 800))
        except Exception as exc:                                         # noqa: BLE001
            print(f"  {n}: no bars ({exc})")
    qdays, qr = data["QQQ"]

    legs = []
    for e in events:
        s = e["symbol"]
        if s not in SOURCES or s not in data:
            continue
        sdays, sr = data[s]
        if e["event_day"] not in sdays:
            continue
        i0 = sdays.index(e["event_day"])
        if i0 < BETA_WINDOW + 2 or i0 + FORWARD_DAYS >= len(sdays):
            continue
        window = sdays[i0 - BETA_WINDOW:i0]
        r_s0 = sr[e["event_day"]]
        fwd_days = sdays[i0 + 1:i0 + 1 + FORWARD_DAYS]
        q_fwd = sum(qr.get(d, 0.0) for d in fwd_days)
        for peer in SOURCES[s] + [s]:
            if peer not in data:
                continue
            pdays, pr = data[peer]
            if any(d not in pr for d in window + [e["event_day"]] + fwd_days):
                continue
            xs = [sr[d] for d in window]
            ys = [pr[d] for d in window]
            beta_sp = _beta(xs, ys) if peer != s else 1.0
            beta_q = _beta([qr.get(d, 0.0) for d in window], ys)
            r_p0 = pr[e["event_day"]]
            resid = r_p0 - beta_sp * r_s0
            fwd = sum(pr[d] for d in fwd_days) - beta_q * q_fwd
            legs.append({"source": s, "event_day": e["event_day"], "peer": peer, "is_source": peer == s,
                         "r_source_0": r_s0, "r_peer_0": r_p0, "beta": beta_sp, "expected_peer_0": beta_sp * r_s0,
                         "residual_0": resid, "forward_excess_3d": fwd})

    def grade(rows: list[dict], key: str) -> dict:
        if len(rows) < 5:
            return {"n": len(rows)}
        x = [r[key] for r in rows]; y = [r["forward_excess_3d"] for r in rows]
        mx, my = statistics.mean(x), statistics.mean(y)
        sx, sy = statistics.pstdev(x), statistics.pstdev(y)
        corr = (sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x)) / (sx * sy) if sx > 0 and sy > 0 else 0.0
        same = [r["forward_excess_3d"] * (1 if r[key] > 0 else -1) for r in rows if r[key] != 0]
        t = statistics.mean(same) / (statistics.pstdev(same) / math.sqrt(len(same))) if len(same) > 2 and statistics.pstdev(same) > 0 else None
        hit = sum(1 for v in same if v > 0) / len(same) if same else None
        return {"n": len(rows), "corr_signal_vs_forward": round(corr, 3),
                "mean_forward_in_signal_direction": round(statistics.mean(same), 4) if same else None,
                "hit_rate": round(hit, 3) if hit is not None else None, "t": round(t, 2) if t is not None else None}

    peers = [l for l in legs if not l["is_source"]]
    sources = [l for l in legs if l["is_source"]]
    big = [l for l in peers if abs(l["r_source_0"]) > 0.05]
    out = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n_legs": len(legs),
           "peer_underreaction_residual": grade(peers, "residual_0"),
           "peer_underreaction_residual_big_source_moves": grade(big, "residual_0"),
           "peer_plain_continuation_day0": grade(peers, "r_peer_0"),
           "source_pead_day0": grade(sources, "r_source_0"),
           "by_source": {s: grade([l for l in peers if l["source"] == s], "residual_0") for s in SOURCES},
           "legs": legs}
    print(f"\nPOST_EVENT_RELAY_v1 -- {len(peers)} peer legs, {len(sources)} source legs; forward = {FORWARD_DAYS}d excess over QQQ beta\n")
    for k in ("peer_underreaction_residual", "peer_underreaction_residual_big_source_moves",
              "peer_plain_continuation_day0", "source_pead_day0"):
        g = out[k]
        print(f"  {k:46s} n={g.get('n'):4d} corr {g.get('corr_signal_vs_forward')} "
              f"mean-in-direction {g.get('mean_forward_in_signal_direction')} hit {g.get('hit_rate')} t {g.get('t')}")
    print("  by source: " + ", ".join(f"{s} n={g.get('n')} t={g.get('t')}" for s, g in out["by_source"].items() if g.get("n")))
    print("\n  reading: residual sign == forward sign (positive corr, t>2) is UNDERREACTION -> buy the residual's direction after"
          " the print; negative is OVERREACTION -> fade it; neither is a dead relay in both directions.")
    if args.json:
        path = _state_dir() / "post_event_relay.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\n  receipt: {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
