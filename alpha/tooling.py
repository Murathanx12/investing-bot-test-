"""The official Alpaca CLI and MCP server -- and the toolset that makes the LLM harmless.

WHY THIS MODULE EXISTS TWICE OVER
=================================
The rules require the Trading API **plus** Alpaca's MCP server or its CLI. That
is criterion 2. But there is a second, better reason to route through them, and
it is the one worth putting in front of a judge.

**The MCP server can be started with the `trading` toolset withheld.**
`ALPACA_TOOLSETS` is a documented, server-side filter: the client is handed
whatever tools the server exposes and there is no way to ask for more. So an LLM
connected to `LLM_SAFE_TOOLSETS` does not have an order-placing tool to call. Not
"is instructed not to trade", not "is checked before trading" -- has no such
verb. Ask it to buy a call and it can only tell you it cannot.

That is this project's canon ("no LLM authority over capital") expressed as a
capability boundary rather than a prompt, and it is worth one screen of the demo:
show the tool list, show the model refusing, show the deterministic engine
placing the same order through `alpha.broker.alpaca`.

THE DIVISION OF LABOUR
======================
- `alpha.broker.alpaca`  -- execution. Deterministic, allowlisted, paper-only.
- the **CLI**            -- the audit path. JSON out, reproducible by a judge on
                            their own machine with two exports and one command.
- the **MCP server**     -- the explanation surface, read-only by construction.

The trading loop must never depend on either: a subprocess that shells out on
every tick is a new failure mode bolted to the one path that must not fail.

WHY THE CHILD ENVIRONMENT IS BUILT, NOT INHERITED
=================================================
`config` refuses to read `ALPACA_API_KEY_ID` because those variables are LIVE on
this machine and once placed twelve real sell orders. Copying `os.environ` into a
subprocess hands the child every one of them and makes that refusal cosmetic --
the guard would still pass in-process while the actual trading binary ran with
the parent's ambient credentials. So the child environment is **assembled from
nothing**: a short allowlist of OS variables the binary needs to run, and the
`ALPACA_*` values we set on purpose. Anything else is absent, and
`_assert_clean()` fails loudly if a forbidden name ever appears in it.
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
    """Required official tooling is absent, misconfigured, or routing live."""


#: Every toolset the V2 server can expose, per its README. Used to report what
#: we withheld -- a claim of restriction is only meaningful against the full set.
ALL_TOOLSETS = (
    "account", "trading", "watchlists", "assets", "stock-data", "crypto-data",
    "options-data", "corporate-actions", "news", "fixed-income-data", "locates",
)

#: Toolsets an LLM may hold. `trading` (orders, positions, exercise) is absent,
#: and that absence is the guarantee -- the model has no order verb to call.
#: `account` is included because "what is my equity" is the question the demo
#: asks most, and it is read-only.
LLM_SAFE_TOOLSETS = (
    "account", "assets", "stock-data", "options-data", "crypto-data", "news",
)

#: OS variables a spawned binary legitimately needs. Everything else is dropped.
_ENV_PASSTHROUGH = (
    "PATH", "SystemRoot", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "LANG", "LC_ALL", "APPDATA", "LOCALAPPDATA",
    "PATHEXT", "WINDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)


@dataclass(frozen=True)
class CliResult:
    command: tuple[str, ...]
    returncode: int
    data: Any
    stderr: str


def official_env(role: str | None = None, *,
                 toolsets: tuple[str, ...] | None = None) -> dict[str, str]:
    """A minimal environment for the official tools, forced to paper.

    Built up from an allowlist rather than copied down from `os.environ`, so a
    forbidden parent credential cannot ride along into the child process.
    """
    creds = config.credentials(role)
    env = {k: os.environ[k] for k in _ENV_PASSTHROUGH if k in os.environ}
    env.update({
        # The names the official CLI and MCP server actually read (verified
        # against the alpacahq/cli and alpacahq/alpaca-mcp-server READMEs).
        "ALPACA_API_KEY": creds.key_id,
        "ALPACA_SECRET_KEY": creds.secret_key,
        # CLI: "true" routes live, anything else routes paper. MCP: paper unless
        # explicitly false. Both are set; neither is left to a default.
        "ALPACA_LIVE_TRADE": "false",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_OUTPUT": "json",
        "ALPACA_QUIET": "true",
        # A stray profile in ~/.config/alpaca must not decide which account this
        # is. Env credentials take precedence, but the profile is named away too.
        "ALPACA_PROFILE": "",
    })
    if toolsets is not None:
        env["ALPACA_TOOLSETS"] = ",".join(toolsets)
    _assert_clean(env)
    return env


def _assert_clean(env: dict[str, str]) -> None:
    """No parent-project credential may exist in a child environment."""
    leaked = [name for name in config._FORBIDDEN_INHERITED if name in env]
    if leaked:
        raise ToolingRefusal(
            f"Refusing to spawn official tooling: {', '.join(leaked)} present in the "
            "child environment. Those belong to a LIVE account and this repo severs "
            "them by name."
        )
    if env.get("ALPACA_LIVE_TRADE", "").lower() == "true":
        raise ToolingRefusal("ALPACA_LIVE_TRADE resolved true; refusing to spawn.")
    if env.get("ALPACA_PAPER_TRADE", "").lower() != "true":
        raise ToolingRefusal("ALPACA_PAPER_TRADE is not true; refusing to spawn.")


def run_cli(args: list[str], *, role: str | None = None,
            timeout: float = 30.0) -> CliResult:
    """Run the official `alpaca` CLI against a declared paper role.

    Not a broker fallback. If the binary is absent this REFUSES and says how to
    install it, rather than silently dropping a required technology and leaving
    the gap to be discovered by a judge.
    """
    binary = shutil.which("alpaca")
    if not binary:
        raise ToolingRefusal(
            "Official Alpaca CLI not found on PATH. Install with `go install "
            "github.com/alpacahq/cli/cmd/alpaca@latest` (or `brew install "
            "alpacahq/tap/cli`), then rerun `python -m scripts.tooling_probe`."
        )
    env = official_env(role)
    cmd = [binary, *args]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout)
    stdout, stderr = proc.stdout.strip(), proc.stderr.strip()
    parsed: Any = stdout
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    if proc.returncode != 0:
        raise ToolingRefusal(f"Alpaca CLI exited {proc.returncode}: {(stderr or stdout)[:500]}")
    return CliResult(tuple(cmd), proc.returncode, parsed, stderr)


def cli_account(role: str | None = None) -> dict[str, Any]:
    """Account state via the official CLI -- the judge-reproducible audit path."""
    result = run_cli(["account", "get"], role=role)
    if not isinstance(result.data, dict):
        raise ToolingRefusal("`alpaca account get` did not return a JSON object.")
    number = str(result.data.get("account_number", ""))
    if not number.startswith("PA"):
        raise ToolingRefusal(
            f"CLI resolved account {number!r}, which has no 'PA' prefix and is "
            "therefore not a paper account. Refusing."
        )
    return result.data


def mcp_launch(role: str | None = None, *,
               toolsets: tuple[str, ...] | None = LLM_SAFE_TOOLSETS,
               ) -> tuple[list[str], dict[str, str]]:
    """Launch command + ephemeral environment for the official MCP server.

    Default toolsets EXCLUDE `trading`. Pass `toolsets=None` for the full surface
    only if you have a reason an LLM should be able to place an order, and write
    that reason down first.

    Credentials travel in the environment of the spawned process and are never
    written to a config file.
    """
    if not shutil.which("uvx"):
        raise ToolingRefusal(
            "`uvx` not found. Install uv (https://docs.astral.sh/uv/), then rerun "
            "`python -m scripts.tooling_probe`."
        )
    env = official_env(role, toolsets=toolsets)
    return ["uvx", "alpaca-mcp-server"], env


def redacted_mcp_spec(role: str | None = None, *,
                      toolsets: tuple[str, ...] | None = LLM_SAFE_TOOLSETS) -> dict[str, Any]:
    """Demo-safe description of the MCP integration. Contains no secret."""
    creds = config.credentials(role)
    granted = tuple(toolsets) if toolsets is not None else ALL_TOOLSETS
    withheld = [name for name in ALL_TOOLSETS if name not in granted]
    return {
        "command": "uvx",
        "args": ["alpaca-mcp-server"],
        "paper_trade": True,
        "role": creds.role,
        "key_id_prefix": creds.key_id[:4] + "...",
        "toolsets": list(granted),
        "withheld_toolsets": withheld,
        "model_can_place_an_order": "trading" in granted,
    }


#: Tool-name fragments that indicate the power to change an account's state.
#: Matched case-insensitively against the MCP server's advertised tool names, so
#: the census reports what the server SAYS it offers rather than what we assume.
_MUTATING_FRAGMENTS = ("place_", "cancel_", "close_", "exercise_", "replace_",
                       "create_", "delete_", "add_", "remove_", "update_")


def mcp_tool_census(role: str | None = None, *,
                    toolsets: tuple[str, ...] | None = LLM_SAFE_TOOLSETS,
                    timeout: float = 240.0) -> dict[str, Any]:
    """Start the MCP server, ask it what tools it has, and count the dangerous ones.

    This is the measurement behind the claim. `redacted_mcp_spec` says which
    toolsets we asked for; this says what the server actually exposed -- and the
    difference between those two things is exactly the sort of gap that turns a
    safety claim into a decoration. Run it before putting the claim on a slide.
    """
    cmd, env = mcp_launch(role, toolsets=toolsets)
    proc = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)

    def send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    names: list[str] | None = None
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "aegis-alpha-terminal", "version": "1"}}})
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 1:
                send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            elif msg.get("id") == 2:
                names = [t["name"] for t in msg.get("result", {}).get("tools", [])]
                break
    finally:
        proc.kill()

    if names is None:
        raise ToolingRefusal("MCP server did not return a tool list.")

    mutating = sorted(n for n in names
                      if any(f in n.lower() for f in _MUTATING_FRAGMENTS))
    return {
        "toolsets_requested": list(toolsets) if toolsets is not None else "all",
        "tools_exposed": len(names),
        "mutating_tools": mutating,
        "can_place_an_order": any("place_" in n.lower() for n in names),
        "tool_names": sorted(names),
    }
