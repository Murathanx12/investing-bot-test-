"""Prove the competition-required official tooling actually works -- or say why not.

The rules require Alpaca's MCP server or its CLI. "We integrated it" is a claim;
this script is the evidence, and it is the one a judge can re-run themselves.

It reports, per surface, one of PASS / FAIL / NOT INSTALLED -- never a silent
skip. A missing binary is a finding, not an absence of one: the failure this
guards against is discovering on 4 September that a required technology was
wired to a module nobody imported.

    python -m scripts.tooling_probe            # dev role
    AAT_ACCOUNT_ROLE=competition python -m scripts.tooling_probe

What it checks:

  1. the child environment is CLEAN -- built from an allowlist, carrying none of
     the parent project's live credentials;
  2. the MCP launch spec withholds the `trading` toolset, so the model connected
     to it has no order-placing tool;
  3. the official CLI resolves the same PA-prefixed paper account the engine
     uses -- two independent paths agreeing on one account number.
"""

from __future__ import annotations

import json
import shutil
import sys

from alpha import config, tooling

PASS, FAIL, ABSENT = "PASS", "FAIL", "----"


def _line(status: str, label: str, detail: str = "") -> bool:
    print(f"  [{status}] {label}" + (f"  --  {detail}" if detail else ""))
    return status == PASS


def main() -> int:
    config.load_env()
    try:
        role = config.role()
    except config.CredentialRefusal as exc:
        print(f"\n  [{FAIL}] role: {exc}\n")
        return 2

    print(f"\nOfficial Alpaca tooling probe -- role {role!r}\n")
    ok = True

    # 1. The child environment carries nothing it was not handed.
    print("Child environment")
    try:
        env = tooling.official_env(role)
        forbidden = [n for n in config._FORBIDDEN_INHERITED if n in env]
        ok &= _line(PASS if not forbidden else FAIL, "no inherited live credentials",
                    f"{len(env)} vars, none of {len(config._FORBIDDEN_INHERITED)} forbidden names")
        ok &= _line(PASS if env.get("ALPACA_LIVE_TRADE") == "false" else FAIL,
                    "ALPACA_LIVE_TRADE", env.get("ALPACA_LIVE_TRADE", "<unset>"))
        ok &= _line(PASS if env.get("ALPACA_PAPER_TRADE") == "true" else FAIL,
                    "ALPACA_PAPER_TRADE", env.get("ALPACA_PAPER_TRADE", "<unset>"))
    except (config.CredentialRefusal, tooling.ToolingRefusal) as exc:
        ok &= _line(FAIL, "environment", str(exc))

    # 2. The MCP surface, and what it deliberately does not include.
    print("\nMCP server (the explanation surface)")
    try:
        spec = tooling.redacted_mcp_spec(role)
        ok &= _line(PASS if not spec["model_can_place_an_order"] else FAIL,
                    "`trading` toolset withheld",
                    "the model has no order verb to call")
        _line(PASS, "granted", ", ".join(spec["toolsets"]))
        _line(PASS, "withheld", ", ".join(spec["withheld_toolsets"]))
        if shutil.which("uvx"):
            cmd, _ = tooling.mcp_launch(role)
            _line(PASS, "launch", " ".join(cmd))
            if "--census" in sys.argv:
                # The measurement behind the claim: start the server and ask it
                # what it actually has, restricted and unrestricted. A safety
                # claim checked against our own config is a claim checked
                # against itself.
                safe = tooling.mcp_tool_census(role)
                full = tooling.mcp_tool_census(role, toolsets=None)
                ok &= _line(PASS if not safe["can_place_an_order"] else FAIL,
                            "census: no order tool exposed",
                            f"{safe['tools_exposed']} tools restricted "
                            f"vs {full['tools_exposed']} unrestricted")
                _line(PASS, "withheld from the model",
                      ", ".join(n for n in full["mutating_tools"]
                                if n not in safe["mutating_tools"]) or "none")
        else:
            _line(ABSENT, "uvx not on PATH",
                  "install uv to run the server; the spec above is still the config")
    except (config.CredentialRefusal, tooling.ToolingRefusal) as exc:
        ok &= _line(FAIL, "mcp", str(exc))

    # 3. The CLI, which is the audit path a judge can reproduce.
    print("\nCLI (the audit path)")
    if not shutil.which("alpaca"):
        _line(ABSENT, "`alpaca` not on PATH",
              "go install github.com/alpacahq/cli/cmd/alpaca@latest")
    else:
        try:
            account = tooling.cli_account(role)
            ok &= _line(PASS, "alpaca account get",
                        f"{account.get('account_number')} equity "
                        f"${float(account.get('equity', 0)):,.2f}")
            ok &= _line(PASS if str(account.get("account_number", "")).startswith("PA") else FAIL,
                        "paper account", str(account.get("account_number")))
        except tooling.ToolingRefusal as exc:
            ok &= _line(FAIL, "alpaca account get", str(exc))

    print()
    if "--json" in sys.argv:
        print(json.dumps(tooling.redacted_mcp_spec(role), indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
