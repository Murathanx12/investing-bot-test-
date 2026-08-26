"""EVENT STATE VECTOR and SHOCK PROPAGATION -- a print is information, not a move.

THE CHANGE THIS FILE MAKES
==========================
Every earnings artefact in this repo so far reduces a print to a MOVE: a day-0
bucket, an implied-vs-realised comparison, a drift in the direction of the gap.
That is the market's summary of the information, and summarising a summary is
how five months produced a demonstrated edge of 0%.

A print is a dozen separate facts arriving at once, with wildly different
information content, and the market's single number is a weighted average of
them whose weights nobody wrote down. So:

1. **`StateVector`** -- the print as a typed vector of twelve fields, each with
   a pre-print PRIOR, a RESOLUTION RULE saying how it will be read off the
   release, and a RANK in the information hierarchy.

   The rank IS the falsifiable claim. We say before the print that the Q3 guide
   carries more information than the Q2 headline EPS. If tomorrow's move is
   explained by EPS and not by the guide, the ranking was wrong, and the record
   will say so because it was written first.

2. **`ShockGraph`** -- the propagation, frozen with pre-print prices. Each edge
   declares SIGN, LAG and an OBSERVABLE intermediate outcome. The question after
   the event is not "did NVDA move" but *which connected name moved less than
   its exposure to the realised state vector implies*.

THE ORDERING GUARD (and it is the point)
========================================
`resolve()` fills the vector from the RELEASE. `reaction()` refuses to return
the price move until `resolve()` has run. That ordering is not politeness -- a
number you already saw contaminates the reading of the facts that caused it, and
every after-the-fact earnings post-mortem in existence is proof. The guard makes
the discipline mechanical instead of intentional.

WHAT THIS IS NOT
================
Not a trade, not a signal, not authority over anything. `SHADOW_ONLY`, like
`psychohistory`. It is a measurement instrument pointed at an event, and the
competition account does not even exist tonight -- NVDA on 26 Aug is a
CALIBRATION EVENT, and the opportunity, if any, is a second-order laggard on the
28th.

DELIBERATELY BESIDE, NEVER INSTEAD OF, `PH:NVDA:2026-08-27:b29d506d`
====================================================================
That record is the old brain's, and it is the CONTROL. This one is the
data-richer brain. Two predictions about one outcome, sealed independently, is
the only way to find out whether the extra structure bought anything. Modifying
the earlier record would destroy the comparison it exists for.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "EVENT_STATE_v1"
STORE = Path(__file__).resolve().parent.parent / "state" / "event_state"

#: A field that could not be read off the release. Explicit, because a missing
#: value and a zero value are opposite findings and look identical as `None`.
UNAVAILABLE = "UNAVAILABLE"


@dataclass
class Field:
    """One dimension of the print, with the rule that will fill it."""
    name: str
    rank: int
    """Position in the information hierarchy. 1 carries the most information."""
    question: str
    unit: str
    prior: str
    """What is expected, in words, WITH the vintage. A consensus without an
    as-of stamp is not a number."""
    resolution_rule: str
    """How this is read off the release. Written before the release exists, so
    it cannot be bent to fit what arrived."""
    sources: list[str] = field(default_factory=list)
    realised: Any = None
    realised_note: str = ""

    @property
    def resolved(self) -> bool:
        return self.realised is not None


@dataclass
class Node:
    """One security in the propagation graph."""
    ticker: str
    role: str
    edge_from: str
    mechanism: str
    sign: int
    """+1 if a STRONGER NVDA state helps this name, -1 if it hurts it."""
    exposure: str
    """Declared economic exposure class: high / medium / low. Judgment, stated
    before the event so it can be wrong in public."""
    lag_sessions: int
    observable: str
    """The intermediate outcome that would confirm the edge INDEPENDENTLY of the
    price -- the thing that makes this an edge rather than a correlation."""
    frozen_price: float | None = None
    frozen_at: str | None = None
    nvda_beta: float | None = None
    """MEASURED. How much this name already moves with NVDA. The interesting
    cell is high declared exposure with LOW measured beta: the market does not
    yet trade it as an NVDA name."""
    beta_r2: float | None = None
    beta_n: int | None = None
    resid_sd: float | None = None
    """Daily sd of this name's return AFTER removing its NVDA component. This is
    the noise a one-event underreaction has to be seen through, and for most of
    this graph it is LARGER than the signal."""
    mde_1event: float | None = None
    """Smallest underreaction one event could resolve at ~80% power
    (2.8 x resid_sd). Print it beside every residual or the residual reads as a
    finding when it is a coin flip."""


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class StateVector:
    subject: str
    event: str
    event_date: str
    release_expected_utc: str
    fields: list[Field]
    market_expectation: dict[str, Any] = field(default_factory=dict)
    control_record: str = ""
    action: str = "SHADOW_ONLY"
    schema: str = SCHEMA
    sealed_at: str | None = None
    seal: str | None = None
    resolved_at: str | None = None
    _reaction: dict[str, Any] | None = None

    # ------------------------------------------------------------------ sealing
    def _sealable(self) -> dict[str, Any]:
        """Everything that must not change after the print. Realised values and
        the reaction are excluded -- they are the things sealing protects."""
        return {
            "schema": self.schema, "subject": self.subject, "event": self.event,
            "event_date": self.event_date,
            "release_expected_utc": self.release_expected_utc,
            "market_expectation": self.market_expectation,
            "control_record": self.control_record,
            "fields": [
                {"name": f.name, "rank": f.rank, "question": f.question, "unit": f.unit,
                 "prior": f.prior, "resolution_rule": f.resolution_rule,
                 "sources": sorted(f.sources)}
                for f in sorted(self.fields, key=lambda f: f.name)
            ],
        }

    def seal_now(self) -> str:
        if self.seal is not None:
            raise ValueError("already sealed; a second seal would overwrite the commitment")
        self.sealed_at = datetime.now(timezone.utc).isoformat()
        self.seal = hashlib.sha256(
            (_canonical(self._sealable()) + self.sealed_at).encode()).hexdigest()[:32]
        return self.seal

    def verify(self) -> bool:
        if not self.seal or not self.sealed_at:
            return False
        return self.seal == hashlib.sha256(
            (_canonical(self._sealable()) + self.sealed_at).encode()).hexdigest()[:32]

    # --------------------------------------------------------------- resolution
    @property
    def hierarchy(self) -> list[str]:
        return [f.name for f in sorted(self.fields, key=lambda f: f.rank)]

    def resolve(self, values: dict[str, Any], *, notes: dict[str, str] | None = None) -> list[str]:
        """Fill the vector FROM THE RELEASE. Returns the fields still open.

        Every field must end up with a value or the explicit `UNAVAILABLE`
        string: a field the release did not address is a finding about the
        release, and it must not be indistinguishable from a field we forgot.
        """
        if not self.verify():
            raise ValueError("refusing to resolve an unsealed or tampered vector: "
                             "a prediction that can still be edited is not one")
        notes = notes or {}
        by_name = {f.name: f for f in self.fields}
        for name, value in values.items():
            if name not in by_name:
                raise KeyError(f"{name!r} is not a field of this vector; the twelve "
                               "dimensions were fixed before the print")
            by_name[name].realised = value
            by_name[name].realised_note = notes.get(name, "")
        open_fields = [f.name for f in self.fields if not f.resolved]
        if not open_fields:
            self.resolved_at = datetime.now(timezone.utc).isoformat()
        return open_fields

    def reaction(self, move: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record or read the price reaction. REFUSES until the vector is resolved.

        This is the whole ordering discipline in one method. Reading the move
        first and the facts second produces a post-hoc story every single time,
        and the story is always coherent, which is exactly what makes it useless.
        """
        if self.resolved_at is None:
            still_open = [f.name for f in self.fields if not f.resolved]
            raise ValueError(
                "REFUSED: the price reaction is not readable until the state vector is "
                f"resolved from the release. Still open: {still_open}. "
                "A move you have already seen cannot be un-seen while reading the facts "
                "that caused it.")
        if move is not None:
            self._reaction = move
        return self._reaction or {}

    # ------------------------------------------------------------------- storage
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hierarchy"] = self.hierarchy
        d["seal_valid"] = self.verify()
        return d

    def save(self, path: Path | None = None) -> Path:
        path = path or STORE / f"{self.subject}_{self.event_date}_vector.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "StateVector":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d.pop("hierarchy", None)
        d.pop("seal_valid", None)
        d["fields"] = [Field(**f) for f in d["fields"]]
        return cls(**d)


@dataclass
class ShockGraph:
    subject: str
    event_date: str
    nodes: list[Node]
    chains: list[str] = field(default_factory=list)
    action: str = "SHADOW_ONLY"
    schema: str = SCHEMA
    sealed_at: str | None = None
    seal: str | None = None

    def _sealable(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "subject": self.subject, "event_date": self.event_date,
            "chains": self.chains,
            "nodes": [
                {"ticker": n.ticker, "role": n.role, "edge_from": n.edge_from,
                 "mechanism": n.mechanism, "sign": n.sign, "exposure": n.exposure,
                 "lag_sessions": n.lag_sessions, "observable": n.observable}
                for n in sorted(self.nodes, key=lambda n: n.ticker)
            ],
        }

    def seal_now(self) -> str:
        if self.seal is not None:
            raise ValueError("already sealed")
        self.sealed_at = datetime.now(timezone.utc).isoformat()
        self.seal = hashlib.sha256(
            (_canonical(self._sealable()) + self.sealed_at).encode()).hexdigest()[:32]
        return self.seal

    def verify(self) -> bool:
        if not self.seal or not self.sealed_at:
            return False
        return self.seal == hashlib.sha256(
            (_canonical(self._sealable()) + self.sealed_at).encode()).hexdigest()[:32]

    def underreaction(self, nvda_move: float, node_moves: dict[str, float]) -> list[dict[str, Any]]:
        """Rank the graph by `declared exposure x small realised response`.

        Two benchmarks per node, and the gap between them is the point:

        - `expected_beta` = measured NVDA-beta x the realised NVDA move. This is
          what the MARKET already thinks the linkage is worth.
        - the declared economic `exposure`. This is what we said the linkage
          IS, before the print.

        A node whose realised move falls short of `expected_beta` is a
        statistical laggard. A node with HIGH declared exposure and LOW measured
        beta that also did not move is the more interesting case: the market has
        not repriced it because it does not yet trade it as an NVDA name.

        `residual` is signed in the direction the edge predicts, so a positive
        residual always means "moved LESS than the edge implies", whatever the
        sign of the edge.
        """
        weight = {"high": 1.0, "medium": 0.5, "low": 0.2}
        out = []
        for n in self.nodes:
            realised = node_moves.get(n.ticker)
            if realised is None:
                continue
            expected_beta = (n.nvda_beta or 0.0) * nvda_move
            directed_expected = n.sign * abs(nvda_move) * weight.get(n.exposure, 0.2)
            residual = (directed_expected - realised) * (1 if n.sign > 0 else -1)
            out.append({
                "ticker": n.ticker, "role": n.role, "edge_from": n.edge_from,
                "sign": n.sign, "exposure": n.exposure, "lag_sessions": n.lag_sessions,
                "nvda_beta": n.nvda_beta, "beta_r2": n.beta_r2,
                "realised": realised,
                "expected_from_beta": expected_beta,
                "expected_from_declared_exposure": directed_expected,
                "residual_vs_declared": residual,
                "residual_vs_beta": (expected_beta - realised) * (1 if n.sign > 0 else -1),
                "observable": n.observable,
                "resid_sd": n.resid_sd,
                "mde_1event": n.mde_1event,
                "resolvable_on_one_event": (
                    None if n.mde_1event is None
                    else abs(residual) >= n.mde_1event),
                "market_prices_the_link": (
                    "yes" if (n.nvda_beta or 0) >= 1.0 else
                    "partly" if (n.nvda_beta or 0) >= 0.5 else "barely"),
            })
        return sorted(out, key=lambda r: r["residual_vs_declared"], reverse=True)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["seal_valid"] = self.verify()
        return d

    def save(self, path: Path | None = None) -> Path:
        path = path or STORE / f"{self.subject}_{self.event_date}_shock.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "ShockGraph":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d.pop("seal_valid", None)
        d["nodes"] = [Node(**n) for n in d["nodes"]]
        return cls(**d)


def measure_beta(target_bars: list[dict], nvda_bars: list[dict],
                 *, lookback: int = 120) -> tuple[float | None, float | None, int]:
    """OLS beta of a name's daily returns on NVDA's, plus R^2 and n.

    Deliberately plain. This is not a risk model -- it is one number answering
    "does the market already trade this as an NVDA name", and a fancier estimate
    would not change which side of 1.0 the answer falls on.
    """
    def rets(bars: list[dict]) -> dict[str, float]:
        out, prev = {}, None
        for b in bars:
            close = float(b.get("c") or 0.0)
            day = str(b.get("t") or "")[:10]
            if prev and prev > 0 and close > 0:
                out[day] = close / prev - 1.0
            prev = close or prev
        return out

    a, b = rets(target_bars), rets(nvda_bars)
    days = sorted(set(a) & set(b))[-lookback:]
    n = len(days)
    if n < 30:
        return None, None, n
    xs = [b[d] for d in days]
    ys = [a[d] for d in days]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    # A driver with (almost) no variance cannot identify a beta. `sxx <= 0` does
    # not catch it: floating-point dust in a near-constant series yields a
    # confident-looking number regressed on nothing. 1e-12 on summed squared
    # daily returns is ~1e-7 daily sd -- far below any real tape, so this
    # refuses only the degenerate case.
    if sxx <= 1e-12:
        return None, None, n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    beta = sxy / sxx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy ** 2) / (sxx * syy) if syy > 0 else None
    return round(beta, 3), (round(r2, 3) if r2 is not None else None), n


def residual_sd(target_bars: list[dict], nvda_bars: list[dict], beta: float,
                *, lookback: int = 120) -> float | None:
    """Daily sd of the target's return with its NVDA component removed.

    THE POINT OF THIS FUNCTION. An underreaction ranking without it is a list of
    numbers with no scale: a node whose residual sd is 2.7% a day cannot resolve
    a 1% underreaction on ONE event, however suggestive the ordering looks. The
    project's standing rule is that the power check comes BEFORE the
    confirmation, and this is the power check for the shock graph.
    """
    def rets(bars: list[dict]) -> dict[str, float]:
        out, prev = {}, None
        for b in bars:
            close = float(b.get("c") or 0.0)
            day = str(b.get("t") or "")[:10]
            if prev and prev > 0 and close > 0:
                out[day] = close / prev - 1.0
            prev = close or prev
        return out

    a, b = rets(target_bars), rets(nvda_bars)
    days = sorted(set(a) & set(b))[-lookback:]
    if len(days) < 30:
        return None
    res = [a[d] - beta * b[d] for d in days]
    m = sum(res) / len(res)
    var = sum((r - m) ** 2 for r in res) / (len(res) - 1)
    return round(var ** 0.5, 4)


def _returns(bars: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    prev = None
    for b in bars:
        close = float(b.get("c") or 0.0)
        day = str(b.get("t") or "")[:10]
        if prev and prev > 0 and close > 0:
            out[day] = close / prev - 1.0
        prev = close or prev
    return out


def group_power(node_bars: dict[str, list[dict]], driver_bars: list[dict],
                groups: dict[str, list[str]], *, control_bars: list[dict] | None = None,
                lookback: int = 120, target: float = 0.02) -> list[dict[str, Any]]:
    """Can this graph resolve an underreaction AT ALL, and on how many events?

    THE QUESTION THAT COMES FIRST. Every ranked list this graph can produce is a
    rank with no resolution behind it unless this function says otherwise, and
    the answer on the NVDA print of 26 Aug 2026 was mostly NO -- measured before
    the event rather than discovered after it.

    Two things it establishes, and the second was a surprise:

    1. **Averaging a group does not diversify the noise.** Five optical and
       datacentre names carry a HIGHER group residual sd than several of them do
       individually. The residual is not idiosyncratic -- it is a SECTOR FACTOR,
       and adding more names from the same sector concentrates it.
    2. **So the control belongs in the regression, not in the sample size.**
       With a sector control alongside the driver, the capacity edge's
       one-event MDE falls 7.5% -> 3.8% and the memory edge 12.4% -> 5.9%,
       while the optical and server-ODM edges barely move because they carry
       their own factor that the sector proxy does not span.

    `events_for_target` is `(MDE / target)^2`: the number of comparable events
    needed before a `target`-sized underreaction is resolvable at ~80% power.
    """
    driver = _returns(driver_bars)
    control = _returns(control_bars) if control_bars else None
    rets = {t: _returns(b) for t, b in node_bars.items()}

    out: list[dict[str, Any]] = []
    for edge, tickers in sorted(groups.items()):
        have = [t for t in tickers if rets.get(t)]
        if not have:
            continue
        common = set(driver) & set.intersection(*[set(rets[t]) for t in have])
        if control:
            common &= set(control)
        days = sorted(common)[-lookback:]
        n = len(days)
        if n < 30:
            out.append({"edge": edge, "tickers": have, "n_days": n,
                        "verdict": "CANNOT DETERMINE: fewer than 30 overlapping sessions"})
            continue
        y = [sum(rets[t][d] for t in have) / len(have) for d in days]
        x1 = [driver[d] for d in days]
        x2 = [control[d] for d in days] if control else None
        sd = _resid_sd_ols(y, x1, x2)
        if sd is None:
            out.append({"edge": edge, "tickers": have, "n_days": n,
                        "verdict": "CANNOT DETERMINE: singular design matrix"})
            continue
        mde = 2.8 * sd
        out.append({
            "edge": edge, "tickers": have, "n_days": n,
            "group_resid_sd": round(sd, 4),
            "mde_1event": round(mde, 4),
            "events_for_target": round((mde / target) ** 2, 1),
            "target": target,
            "control_used": bool(control),
        })
    return sorted(out, key=lambda r: r.get("mde_1event", 9.9))


def _resid_sd_ols(y: list[float], x1: list[float],
                  x2: list[float] | None) -> float | None:
    """Residual sd of y on x1 (and x2 when given). Plain OLS, no library."""
    import statistics as st

    n = len(y)
    my, m1 = sum(y) / n, sum(x1) / n
    Y = [v - my for v in y]
    A = [v - m1 for v in x1]
    if x2 is None:
        saa = sum(a * a for a in A)
        if saa <= 0:
            return None
        b1 = sum(a * v for a, v in zip(A, Y)) / saa
        res = [v - b1 * a for v, a in zip(Y, A)]
        return st.stdev(res) if len(res) > 1 else None
    m2 = sum(x2) / n
    B = [v - m2 for v in x2]
    saa, sbb = sum(a * a for a in A), sum(b * b for b in B)
    sab = sum(a * b for a, b in zip(A, B))
    say = sum(a * v for a, v in zip(A, Y))
    sby = sum(b * v for b, v in zip(B, Y))
    det = saa * sbb - sab * sab
    if abs(det) < 1e-18:
        return None
    b1 = (sbb * say - sab * sby) / det
    b2 = (saa * sby - sab * say) / det
    res = [v - b1 * a - b2 * b for v, a, b in zip(Y, A, B)]
    return st.stdev(res) if len(res) > 1 else None
