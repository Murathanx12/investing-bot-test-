"""GUARD_CLASS_v1 -- not every refusal is the same kind of rule.

THE WORRY THIS ANSWERS
======================
Six months of negative research can turn an engine into one whose only legal
action is cash, and it happens without anyone deciding it: an EMPIRICAL guard
("peer straddles lost 0-for-8") starts being treated with the reverence owed to
a HARD invariant ("never trade the judged account before genesis"). They are not
the same kind of thing. A hard invariant has no reopening condition. An
empirical guard is a conclusion from a sample, has a scope, and is OWED a
measurement of what it costs: `scripts.refusal_regret` reads the counterfactual
ledger and prices every refusal, by guard.

CLASSES
=======
    HARD        never bends; no reopening condition; a breach is a bug.
    EMPIRICAL   a conclusion from evidence; scoped; reopens on named evidence;
                its blocked candidates are shadow-priced and its saved/lost
                P&L is reported.
    TOURNAMENT  a policy that MOVES with equity, time and opportunity
                (BASE/ATTACK, caps, concentration); changed by `mode_for`,
                never by mood.
    RETEST_DUE  an EMPIRICAL guard whose sample or regime has aged past its
                reopening condition; still binds, flagged loudly.

This registry is DATA about the guards, keyed by the reason-prefix each one
writes on a refused ledger row, so the regret report can group refusals without
parsing prose. A guard not listed here is reported as UNCLASSIFIED -- which is
itself a finding, because an unclassified refusal is a rule nobody owns.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Guard:
    key: str
    cls: str                       # HARD | EMPIRICAL | TOURNAMENT | RETEST_DUE
    where: str                     # module.function
    reason_prefixes: tuple[str, ...]
    scope: str
    evidence: str = ""
    reopens_when: str = ""


GUARDS: list[Guard] = [
    # ---------------------------------------------------------------- HARD
    Guard("paper_host_only", "HARD", "alpha.config.base_url", ("Refusing", "host"),
          "every order", "a smoke sync once placed 12 real orders on a live key"),
    Guard("role_declared", "HARD", "alpha.config.role", ("AAT_ACCOUNT_ROLE",),
          "every process", "an unset role choosing the judged account has no undo"),
    Guard("genesis_verified", "HARD", "alpha.genesis.verify", ("GENESIS",),
          "competition role, --live", "a reused account is ineligible"),
    Guard("denied_accounts", "HARD", "alpha.genesis.DENIED_ACCOUNTS", ("denylisted", "DENIED"),
          "competition role", "legacy account numbers, keyed on the venue's number"),
    Guard("quote_snapshot_required", "HARD", "alpha.broker.alpaca.submit", ("submit() requires the quote",),
          "every order", "a fill with no quote is not evidence"),
    Guard("idempotent_order_id", "HARD", "alpha.broker.alpaca.client_order_id", ("duplicate", "already exists"),
          "every order", "a replay after a crash must collide, not double"),
    Guard("options_tif_day", "HARD", "alpha.timing.validate_payload", ("time_in_force=",),
          "every option order", "venue rejects cls/opg on options; proven live 28 Aug"),
    Guard("multileg_needs_limit", "HARD", "alpha.timing.validate_payload", ("limit order without a limit_price", "multileg option order should be a LIMIT"),
          "multileg", "an unbounded fill on a 10%-wide quote"),
    Guard("zero_egress_tests", "HARD", "run_tests / AAT_TEST_MODE", ("getaddrinfo",),
          "the suite", "a test once placed 338 rows on the venue through a subprocess"),
    Guard("no_llm_order_path", "HARD", "alpha.council (no broker import)", (),
          "every LLM", "no model has capital authority; pinned by tests_smoke_council"),
    # ------------------------------------------------------------ EMPIRICAL
    Guard("claim_matrix", "EMPIRICAL", "alpha.claims.admissible", ("CLAIM ",),
          "direction claim -> no sign-blind structure",
          "an NVDA condor won whether the print was up or down; sign moved EV by $6 on $54",
          "a brain that declares a magnitude claim with its own evidence"),
    Guard("mdm_floor", "EMPIRICAL", "alpha.engine.sizing.size", ("disagreement with the chain is", "minimum detectable move"),
          "every structure: >=5pp of probability mass beyond the MDM",
          "per-trade cost arithmetic; a +0.2% centre on a 7% sd never clears it. REGRET MEASURED "
          "2026-08-28 on 805 refused worlds marked after the 27 Aug rally: win% 26-33% in EVERY edge "
          "bucket (0-1pp .. >=5pp); the positive net is long_call +$685k (72% hit) against long_put "
          "-$563k (5% hit) -- the tape's sign, not the gate's. Not evidence to lower the floor.",
          "a BASKET sizing that aggregates many small legs (the pair lane), or a win% by edge bucket "
          "that rises as the floor is approached on >= 2 regimes -- research item"),
    Guard("cash_beats_it", "EMPIRICAL", "alpha.runner.evaluate", ("CASH beats it",),
          "EV after spread <= 0", "cash is a structure with EV exactly zero"),
    Guard("index_straddle", "EMPIRICAL", "alpha.refuted", ("index straddle", "long_straddle on SPY", "INDEX_STRADDLE"),
          "SPY/QQQ/IWM straddles held >= 2 DTE",
          "381 weekly ATM straddles, buyer -19.8%/wk; this book -$14,711; OptionMetrics 26y t -5.66..-8.72",
          "a state variable that predicts NET straddle return after costs (none found: vrp corr ~0)"),
    Guard("nvda_peer_straddle", "EMPIRICAL", "alpha.refuted", ("straddle into", "peer straddle"),
          "straddles into NVDA's print or a peer's", "0-for-8 and 290 relay legs",
          "a print class where the chain UNDERprices the move (none of 8 mega-caps clears its MDE)"),
    Guard("wide_up_no_edge", "EMPIRICAL", "alpha.brains.post_event_drift", ("is UP and", "outside the eleven names"),
          "UP prints outside the mega-11", "2,532 names / 25,856 legs: +0.25% raw t 2.49 = the index's own drift; vs QQQ t -1.99",
          "a two-sided drift measured on a wider population than eleven names"),
    Guard("wide_down_pair_only", "EMPIRICAL", "alpha.brains.post_event_drift", ("wide-universe DROP",),
          "DOWN prints outside the mega-11 are expressed ONLY as a pair", "unhedged short +0.04% simple, nothing",
          "recomputed 28 Aug: hedged pair t 1.34/0.79 -- a breadth claim; see WIDE_HEDGED_IWM_RECOMPUTED_2026_08_28"),
    Guard("flat_tercile", "EMPIRICAL", "alpha.brains.post_event_drift", ("inside the flat tercile",),
          "|day-0 move| < 3.5%", "t 0.66: nothing to continue", "n/a"),
    Guard("drift_window_spent", "EMPIRICAL", "alpha.brains.post_event_drift", ("sessions since the print",),
          "> 2 sessions after the print", "+1..+3 window; day +3 alone t 1.67", "n/a"),
    Guard("vol_gap_quarantine", "RETEST_DUE", "alpha.sentinels", ("vol_gap loses", "SENTINEL: vol_gap"),
          "vol_gap brain", "5 of 6 losing structures, -$14,335, pre-units-fix arithmetic",
          "RE-SCORE on corrected arithmetic -- overdue since 27 Aug"),
    Guard("sigma_inflation_shadow", "RETEST_DUE", "alpha.sentinels", ("narrative_dispersion loses", "options_attention loses", "relay loses"),
          "narrative_dispersion / options_attention / relay", "1.16-1.17x sigma inflation; relay t -2.0",
          "a corrected sigma measured against realised on >= 30 events"),
    # ----------------------------------------------------------- TOURNAMENT
    Guard("rank_objective", "TOURNAMENT", "alpha.runner.rank_objective", ("out-ranked on",),
          "BASE -> median/max-loss; ATTACK -> EV", "five compounding sessions follow the median", "mode_for flips"),
    Guard("event_node_cap", "TOURNAMENT", "alpha.runner (EVENT_NODE_CAP)", ("event node", "one bet"),
          "25% of equity per event node", "policy", "mode_for / equity"),
    Guard("daily_latch", "TOURNAMENT", "alpha.daybreak", ("latch",),
          "-3% day -> no new risk", "policy; audit patch 2", "next session"),
    Guard("book_limits", "TOURNAMENT", "alpha.book_limits", ("aggregate", "per underlying", "entries per session"),
          "<=30% defined risk, <=6% per underlying, <=3 entries/session", "policy", "mode_for"),
    Guard("one_position_per_underlying", "TOURNAMENT", "alpha.runner (held_underlyings)", ("already positioned in this book",),
          "no second structure on a held underlying", "policy; two expressions of one event are one bet", "mode_for"),
    Guard("approved_but_tiny", "TOURNAMENT", "alpha.runner.contracts_for", ("approved 0.0",),
          "an approved fraction that rounds to zero contracts", "arithmetic of lot size vs risk budget", "equity grows"),
    Guard("concentration", "TOURNAMENT", "alpha.concentration", ("effective", "concentration"),
          "effective bets by TRUE max loss", "a 24-issuer book behaved like 1.43 bets", "mode_for"),
]


def classify(reason: str) -> Guard | None:
    r = reason or ""
    for g in GUARDS:
        if any(p and p in r for p in g.reason_prefixes):
            return g
    return None


def by_class() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for g in GUARDS:
        out.setdefault(g.cls, []).append(g.key)
    return out
