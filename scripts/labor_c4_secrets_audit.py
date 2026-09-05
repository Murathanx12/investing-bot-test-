"""C4 -- SECRETS AND SURFACE AUDIT. Never prints a matched value.

    python -m scripts.labor_c4_secrets_audit           # write both receipts
    python -m scripts.labor_c4_secrets_audit --print

THREE QUESTIONS, ONE RULE
=========================
The rule first, because it is the part that is easy to get wrong while doing
the right thing: **a finding names the file, the line and the SHAPE. Never the
value.** A grep that prints its match turns an audit receipt into the leak it
was written to find, and this receipt is committed to a public repository.

  1. Did anything key-shaped get COMMITTED since 2026-09-01, in either repo --
     receipts, logs, docs, test fixtures included?
  2. Is the seal-authority's public surface GET/HEAD only (POST -> 501), and
     does it serve only the books directory?
  3. Is `.env.bak.*` ignored, untracked, absent from history, and read by no
     code path?

WHY THE SWEEP IS RE-RUNNABLE AND THE ANSWERS ARE NOT
====================================================
Question 1 is executed here, live, every run: it is cheap and its answer can
change with the next commit. Questions 2 and 3 were answered by READING
`scripts/seal_authority.py` against the stdlib it inherits from, and by
`git check-ignore` / `git log --diff-filter=A` over both repos' whole history;
those answers are recorded with the exact evidence rather than re-derived,
because "does SimpleHTTPRequestHandler normalise %2e%2e" is a question about
CPython, not about this repo, and re-running a grep would not answer it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = Path(__file__).resolve().parent.parent
FINANCE = TERMINAL.parent / "aegis-finance"

#: (class, compiled pattern). Deliberately broad: a false positive costs a line
#: of adjudication, a false negative costs a key.
PATTERNS: tuple[tuple[str, str], ...] = (
    ("openai_or_deepseek", r"sk-[A-Za-z0-9_-]{16,}"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("aws_like", r"\bAK[A-Z0-9]{10,}\b"),
    ("huggingface", r"\bhf_[A-Za-z0-9]{20,}\b"),
    ("alpaca_key_id", r"\b[PC]K[A-Z0-9]{10,}\b"),
    ("github", r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("slack", r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("labelled_credential",
     r"(?i)\b(api[_-]?key|secret|token|password|passwd|bearer)\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"),
)
_COMPILED = tuple((n, re.compile(p)) for n, p in PATTERNS)

#: Adjudicated NOT credentials, with the reason. A hit is only dismissed by
#: NAME, never by pattern -- widening the pattern to make a hit go away is how
#: the next real one goes away with it.
KNOWN_FALSE_POSITIVES: tuple[dict, ...] = (
    {"token": "sk-better-than-what", "class": "openai_or_deepseek",
     "why": "the wiki-link [[feedback-ask-better-than-what]] -- the 'a' of 'ask' is "
            "consumed by the surrounding word, leaving a literal 'sk-' followed by 16 "
            "word characters. Dismissed by the exact TOKEN, never by widening the "
            "pattern: a pattern loosened to make a hit disappear takes the next real "
            "one with it.",
     "seen_in": ["learner/benchmark.py", "learner/neural_long.py"]},
    {"token": "AKTIENGESELLSCHAFT", "class": "aws_like",
     "why": "a German corporate suffix. Appears in the c6b counterparty stoplist and "
            "in SEC company titles inside edgar_8k/company_tickers.json",
     "seen_in": ["scripts/c6b_counterparty_bias.py",
                 "backend/data/optimus/edgar_8k/company_tickers.json"]},
    {"token": "AKTIEBOLAG", "class": "aws_like",
     "why": "the Swedish corporate suffix, same stoplist",
     "seen_in": ["scripts/c6b_counterparty_bias.py"]},
)
_FP_TOKENS = tuple(f["token"] for f in KNOWN_FALSE_POSITIVES)

#: A value that is obviously a placeholder is not a leak. Matched on the VALUE,
#: which is why this is the only place a value is looked at and it is never
#: emitted.
_PLACEHOLDER = re.compile(
    r"(?i)^(x+|0+|a+|your[-_ ]?|<|\.\.\.|\*{3,}|redact|example|placeholder|dummy|fake|test)")


def _redacted_shape(value: str, cls: str) -> str:
    """What a finding is allowed to say about a match. Never the value."""
    v = value.strip()
    head = v[:3]
    return f"class={cls} len={len(v)} prefix={head!r} tail_len={max(0, len(v) - 3)}"


def _git(repo: Path, args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                              text=True, timeout=120).stdout
    except Exception as exc:                                            # noqa: BLE001
        return f"<git unavailable: {exc}>"


def committed_since(repo: Path, since: str = "2026-09-01") -> list[str]:
    out = _git(repo, ["log", f"--since={since}", "--name-only", "--pretty=format:"])
    return sorted({l.strip() for l in out.splitlines() if l.strip()})


def sweep(repo: Path, since: str = "2026-09-01") -> dict:
    """Scan every file committed since `since` that still exists. Values never leave."""
    names = committed_since(repo, since)
    counts = {n: 0 for n, _ in PATTERNS}
    hits: list[dict] = []
    dismissed = 0
    scanned = skipped_missing = skipped_binary = 0
    for rel in names:
        p = repo / rel
        if not p.is_file():
            skipped_missing += 1
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            skipped_binary += 1
            continue
        scanned += 1
        for i, line in enumerate(text.splitlines(), start=1):
            for cls, rx in _COMPILED:
                m = rx.search(line)
                if not m:
                    continue
                counts[cls] += 1
                val = m.group(0)
                if any(tok in line for tok in _FP_TOKENS):
                    dismissed += 1
                    continue
                if _PLACEHOLDER.match(val.split("-", 1)[-1] if "-" in val else val):
                    dismissed += 1
                    continue
                hits.append({"repo": repo.name, "file": rel, "line": i,
                             "shape": _redacted_shape(val, cls),
                             "adjudication": "NEEDS REVIEW"})
    return {"repo": repo.name, "repo_path": str(repo),
            "commit": _git(repo, ["rev-parse", "HEAD"]).strip(),
            "since": since,
            "files_committed_since": len(names), "files_scanned": scanned,
            "skipped_deleted_or_moved": skipped_missing,
            "skipped_binary_or_undecodable": skipped_binary,
            "raw_matches_by_class": counts,
            "dismissed_as_known_false_positive_or_placeholder": dismissed,
            "unadjudicated_hits": hits}


# --------------------------------------------------------------------------
# Q2 and Q3: read once, recorded with the evidence.
# --------------------------------------------------------------------------
SEAL_AUTHORITY_SURFACE = {
    "file": "aegis-alpha-terminal/scripts/seal_authority.py",
    "handler": ("class QuietHandler(SimpleHTTPRequestHandler) at :142, overriding "
                "log_message and NOTHING else -- so the method set is the stdlib's."),
    "methods": {
        "GET": "IMPLEMENTED (inherited SimpleHTTPRequestHandler.do_GET)",
        "HEAD": "IMPLEMENTED (inherited SimpleHTTPRequestHandler.do_HEAD)",
        "POST/PUT/DELETE/PATCH": (
            "501 NOT IMPLEMENTED, via BaseHTTPRequestHandler.handle_one_request: "
            "`if not hasattr(self, 'do_' + self.command): send_error(NOT_IMPLEMENTED)`. "
            "No do_POST exists anywhere in the class chain, so there is no fall-through "
            "to anything else. Verified against the local stdlib, Python 3.12.10."),
    },
    "verdict_on_the_claim": (
        "the standing claim -- 'GET/HEAD only, serves only the books dir, POST=501' "
        "(docs/FINDING_2026-09-04_THE_INVISIBLE_40PCT_CEILING.md:88-91) -- is ACCURATE."),
    "served_root": {
        "code": "STATE = Path(AAT_LEDGER_DIR or ROOT/'state'); BOOKS = STATE/'predictions'; "
                "os.chdir(BOOKS) at :157 before ThreadingHTTPServer at :158",
        "on_railway": "/app/state/predictions (AAT_LEDGER_DIR=/app/state, alpha/fleet.py:174)",
        "chdir_is_safe": "every subprocess the maintainer thread spawns passes cwd=ROOT "
                         "explicitly (_run, :71), so the chdir cannot mis-target a command",
    },
    "traversal": {
        "..": "DROPPED by SimpleHTTPRequestHandler.translate_path "
              "(`word in (os.curdir, os.pardir): continue`), after posixpath.normpath",
        "%2e%2e": "unquoted BEFORE the filter, so it becomes '..' and is then dropped",
        "absolute paths / drive letters": "any component with a non-empty os.path.dirname "
                                          "is dropped; the join always restarts from "
                                          "self.directory",
        "symlinks": "NOT RESOLVED -- translate_path never calls realpath. This is the one "
                    "real escape vector and it depends on VOLUME CONTENTS, not on request "
                    "input. None exist today and nothing in either repo creates one.",
    },
    "what_is_reachable": (
        "every file in state/predictions, not only today's book: the reseal history "
        "(<day>.resealed_HHMMSS.json) and seals.jsonl, plus a DIRECTORY LISTING at GET / "
        "because there is no index.html. Grepped the whole served directory against every "
        "pattern class above: ZERO matches -- no credential material is exposed. Nothing "
        "above the served root is reachable: the ledger, state/fills, .env and the code "
        "tree all sit outside it."),
    "authentication": (
        "NONE. It binds 0.0.0.0 on PORT (default 8080); access control is entirely "
        "network-level. Its log_message prints the full request line INCLUDING the query "
        "string, so a secret a client appended to a URL would reach the Railway log."),
    "public_domain": (
        "https://seal-authority-production.up.railway.app, recorded at "
        "docs/FINDING_2026-09-04_THE_INVISIBLE_40PCT_CEILING.md:87-88 as created "
        "inadvertently by `railway domain`, kept deliberately, and already flagged there "
        "for review. The INTERNAL consumer is seal-authority.railway.internal:8080 via "
        "scripts/prediction_book_sync.py, whose base URL comes from "
        "AAT_PREDICTION_BOOK_BASE_URL and which is an exact no-op when unset; that client "
        "verifies `day`, re-derives content_sha256 and caps the download at 8 MiB, so a "
        "compromised authority cannot install an altered book."),
    "residual_risks_ranked": [
        "1. unauthenticated public exposure of the full book and reseal history plus "
        "seals.jsonl. Low impact -- the books are published in-repo anyway -- but the "
        "directory listing makes reseal TIMING enumerable.",
        "2. request paths, with query strings, land in the Railway log.",
        "3. symlink-following, if anything ever creates one inside the volume's "
        "predictions/ directory.",
    ],
    "checked_without_any_network_call": True,
}

ENV_BAK = {
    "terminal": {
        "gitignore": [".env  (.gitignore:3)", ".env.*  (.gitignore:4)"],
        "coverage": "a true catch-all: .env, .env.bak, .env.bak.<anything>, .env.local, "
                    ".env.production, .env.staging, .env.test, .env.example, scripts/.env, "
                    "state/.env all resolve to line 3 or 4",
        "tracked": "NONE -- `git ls-files | grep -i env` is empty",
        "history": "`git log --all --diff-filter=A --name-only` has NEVER added any .env* "
                   "path in this repo's entire history",
        "read_by_code": "NO. Zero references to dotenv, load_dotenv or `.bak` in tracked "
                        "code. alpha/config.py:49 is the repo's own loader and reads exactly "
                        "one path (`.env`), skipping keys already in os.environ.",
        "on_disk": [".env (2,591 bytes)", ".env.bak.2026-08-27 (971 bytes)",
                    ".env.example (1,136 bytes)"],
    },
    "finance": {
        "gitignore": [".env (:27)", ".env.local (:28)", ".env.production (:29)",
                      ".env.hidden (:34)", ".env.*.hidden (:35)",
                      ".env.bak (:175)", ".env.bak.* (:176)"],
        "coverage": "`git check-ignore -v --no-index` confirms .env.bak -> :175 and "
                    ".env.bak.test / .env.bak.<date> -> :176; backend/.env and config/.env "
                    "-> :27 (basename patterns match at any depth); frontend/.env.local -> "
                    "frontend/.gitignore:44",
        "tracked": ".env.example only (empty values for every secret key: FRED_API_KEY=, "
                   "FINNHUB_API_KEY=, FMP_API_KEY=, DEEPSEEK_API_KEY=; only PORT, "
                   "ALLOWED_ORIGINS and NEXT_PUBLIC_API_URL carry values, all non-secret). "
                   "Plus two test files whose NAMES contain 'env'.",
        "history": "exactly one .env* path ever added -- .env.example, in 5f585bc / eb783bb "
                   "/ 4e4dc60, with empty secret values. No .env.bak* blob exists in "
                   "history, so the ignore rules are not papering over a past commit.",
        "read_by_code": "NO. Every reference targets `.env` explicitly or a bare "
                        "load_dotenv() (which searches only for .env): backend/config.py:17,97 "
                        "(gated on AEGIS_IGNORE_DOTENV), services/llm_research.py:161-164, and "
                        "four scripts/run_*.py. Every `.bak` mention is documentation only "
                        "(.gitignore, DATA_MANIFEST, FORENSICS, two handoffs).",
        "on_disk": [".env (3,750 bytes)", ".env.bak.2026-08-27 (2,304 bytes)",
                    ".env.example (1,014 bytes)", "frontend/.env.local (1,354 bytes)"],
        "GAP": ("LOW SEVERITY. Finance ENUMERATES variants instead of using terminal's "
                "`.env.*` catch-all, so .env.staging, .env.test, .env.deepseek, .env.backup, "
                ".env.old and .env.save are NOT ignored. None exist on disk. The .env.bak* "
                "shape this item asked about IS covered. Closing it is `.env.*` plus "
                "`!.env.example` -- one line, NOT made here: .gitignore is a shared file "
                "and three peer lanes are committing into these repos tonight."),
    },
    "standing_rule_honoured": (
        "Both .env.bak.2026-08-27 files contain live keys (docs/DATA_MANIFEST.md:258). "
        "Neither was opened, moved or deleted by this audit -- names and sizes only. If "
        "they should leave the tree, a human moves them."),
}


def build() -> dict:
    repos = [sweep(TERMINAL)] + ([sweep(FINANCE)] if FINANCE.exists() else [])
    total_hits = sum(len(r["unadjudicated_hits"]) for r in repos)
    return {
        "item": "C4", "lane": "C", "lab": "labor_day_lab_2026-09-07",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv,
        "config": {"since": "2026-09-01", "network": "none", "llm_calls": 0,
                   "rule": "a finding names FILE, LINE and a redacted SHAPE. "
                           "No matched value is ever printed, logged or stored."},
        "q1_key_shaped_sweep": {
            "verdict": ("CLEAN -- 0 unadjudicated hits in either repo"
                        if total_hits == 0 else
                        f"{total_hits} hit(s) NEED REVIEW"),
            "per_repo": repos,
            "known_false_positives": list(KNOWN_FALSE_POSITIVES),
            "deliberate_redactions_found": [
                "aegis-finance/docs/FORENSICS_2026-09-03_HEALTH_EPISODE.md:203,210 describes "
                "the DEAD Alpaca pair by SHAPE only ('26-char PK id, 44-char secret'); the "
                "pair is documented as revoked at Alpaca. No material.",
                "aegis-finance/docs/FORENSICS_2026-09-03_HEALTH_EPISODE.md:220 and the "
                "terminal Dockerfile show `--set ALPACA_API_KEY_ID=...` ellipsis placeholders.",
            ],
        },
        "q2_seal_authority_surface": SEAL_AUTHORITY_SURFACE,
        "q3_env_bak": ENV_BAK,
        "summary": {
            "q1": "CLEAN" if total_hits == 0 else "REVIEW",
            "q2": "SOUND (GET/HEAD only, POST->501, books dir only) with three residual "
                  "risks, none of them a credential exposure",
            "q3": "SAFE (.env.bak* ignored in both repos, never tracked, never in history, "
                  "read by no code path) with one low-severity gitignore gap in finance",
            "nothing_requires_rotation_from_the_committed_surface": total_hits == 0,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--print", action="store_true")
    a = p.parse_args()
    payload = build()
    for base in (TERMINAL / "state" / "labor_day_lab_2026-09-07",
                 FINANCE / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"):
        if not base.parent.exists():
            continue
        base.mkdir(parents=True, exist_ok=True)
        (base / "C4_secrets_and_surface.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        print(f"receipt: {base / 'C4_secrets_and_surface.json'}")
    for r in payload["q1_key_shaped_sweep"]["per_repo"]:
        print(f"\n{r['repo']}: {r['files_committed_since']} file(s) committed since "
              f"{r['since']}, {r['files_scanned']} scanned, "
              f"{r['skipped_deleted_or_moved']} deleted/moved, "
              f"{r['skipped_binary_or_undecodable']} binary")
        print(f"  raw matches by class: "
              f"{ {k: v for k, v in r['raw_matches_by_class'].items() if v} or 'none'}")
        print(f"  dismissed (known false positive / placeholder): "
              f"{r['dismissed_as_known_false_positive_or_placeholder']}")
        print(f"  UNADJUDICATED: {len(r['unadjudicated_hits'])}")
        for h in r["unadjudicated_hits"][:20]:
            print(f"    {h['file']}:{h['line']}  {h['shape']}")
    if a.print:
        print("\nQ2 " + payload["summary"]["q2"])
        print("Q3 " + payload["summary"]["q3"])
    print(f"\nVERDICT  q1={payload['summary']['q1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
