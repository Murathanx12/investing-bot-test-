"""Competition-required Alpaca CLI/MCP integration without contaminating the trading loop.

The hackathon requires the Trading API plus at least one of Alpaca's MCP server
or CLI. The numerical loop should NOT depend on either: they are agent/control
surfaces, while `alpha.broker.alpaca` remains the deterministic execution path.

This module bridges the repo's deliberately isolated `AAT_*` paper credentials
to the official Alpaca tools. It never enables live trading, never writes keys
to disk, and returns machine-readable CLI output for the audit/dashboard path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from alpha import config


class ToolingRefusal(RuntimeError):
    """Required official tooling is absent or attempted to route live."""


@dataclass(frozen=True)
class CliResult:
    command: tuple[str, ...]
    returncode: int
    data: Any
    stderr: str


def official_env(role: str | None = None) -> dict[str, str]:
    """Environment expected by Alpaca CLI/MCP, forced to paper trading."""
    creds = config.credentials(role)
    env = dict(os.environ)
    env.update({
        "ALPACA_API_KEY": creds.key_id,
        "ALPACA_SECRET_KEY": creds.secret_key,
        "ALPACA_LIVE_TRADE": "false",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_OUTPUT": "json",
        "ALPACA_QUIET": "true",
    })
    return env


def run_cli(args: list[str], *, role: str | None = None, timeout: float = 30.0) -> CliResult:
    """Run the official `alpaca` CLI against a declared paper role.

    The CLI is intentionally not a broker fallback. If it is absent, refuse and
    tell the operator how to install it rather than silently dropping the
    competition-required technology from the project.
    """
    binary = shutil.which("alpaca")
    if not binary:
        raise ToolingRefusal(
            "Official Alpaca CLI not found on PATH. Install with `go install "
            "github.com/alpacahq/cli/cmd/alpaca@latest` or Homebrew, then rerun "
            "`python -m scripts.tooling_probe --cli`."
        )
    env = official_env(role)
    if env.get("ALPACA_LIVE_TRADE", "").lower() == "true":
        raise ToolingRefusal("ALPACA_LIVE_TRADE resolved true; refusing official CLI invocation.")
    cmd = [binary, *args]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    parsed: Any = stdout
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    if proc.returncode != 0:
        raise ToolingRefusal(
            f"Alpaca CLI exited {proc.returncode}: {(stderr or stdout)[:500]}"
        )
    return CliResult(tuple(cmd), proc.returncode, parsed, stderr)


def cli_account(role: str | None = None) -> dict[str, Any]:
    result = run_cli(["account", "get", "--quiet"], role=role)
    if not isinstance(result.data, dict):
        raise ToolingRefusal("`alpaca account get` did not return JSON object output.")
    number = str(result.data.get("account_number", ""))
    if not number.startswith("PA"):
        raise ToolingRefusal(f"CLI resolved non-paper account {number!r}; refusing.")
    return result.data


def mcp_launch(role: str | None = None, *, toolsets: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Return the official MCP launch command + ephemeral environment.

    Callers can pass this to subprocess/Claude Code without ever creating a file
    containing credentials. `uvx alpaca-mcp-server` is Alpaca's documented V2
    launch path. Paper mode is forced even if the parent shell says otherwise.
    """
    if not shutil.which("uvx"):
        raise ToolingRefusal(
            "`uvx` not found. Install uv, then run `python -m scripts.tooling_probe --mcp`."
        )
    env = official_env(role)
    env.pop("ALPACA_LIVE_TRADE", None)
    env["ALPACA_PAPER_TRADE"] = "true"
    if toolsets:
        env["ALPACA_TOOLSETS"] = toolsets
    return ["uvx", "alpaca-mcp-server"], env


def redacted_mcp_spec(role: str | None = None, *, toolsets: str | None = None) -> dict[str, Any]:
    """Judge/demo-safe representation of the MCP integration; never contains keys."""
    creds = config.credentials(role)
    return {
        "command": "uvx",
        "args": ["alpaca-mcp-server"],
        "paper_trade": True,
        "role": creds.role,
        "key_id_prefix": creds.key_id[:4] + "...",
        "toolsets": toolsets or "all",
    }
