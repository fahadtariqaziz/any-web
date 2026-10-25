"""The coding agent (M8): Claude Agent SDK, confined to one session's app/ folder (handoff.md section 6 / M8).

Chosen after scripts/spike_agent_sdk.py passed every hard requirement (2026-10-25). The SDK runs its bundled Claude
Code CLI as a subprocess; this module decides what that agent may do:
- tools: the built-in Read / Write / Edit / Glob / Grep only, plus OUR `run_command` (an in-process MCP tool that
  calls workspace.sandbox.run). The built-in Bash is NOT offered: the CLI subprocess inherits the builder's
  environment (the SDK merges `env` over it), so its Bash would run commands next to our secrets;
- a PreToolUse hook (paths.tool_path_problem) denies any file access outside app/; permission_mode "dontAsk" refuses
  every tool that is not pre-approved;
- isolation from the user's own Claude Code: setting_sources=[] (no settings / CLAUDE.md), CLAUDE_CONFIG_DIR inside
  .builder/ (no user memory, history or login), skills=[]; auth = ANTHROPIC_API_KEY from backend/.env;
- LLM_PROVIDER=local: the same CLI talks to Ollama's Anthropic-compatible /v1/messages (ANTHROPIC_BASE_URL), every
  model slot it may use points to the local model, thinking off unless LOCAL_THINK, and cost is 0 (no USD cap);
- caps per attempt: max_turns, max_budget_usd, a wall-clock timeout;
- every tool call, denial and command is written to .builder/logs/<label>.log.
What the agent SAYS is never a success signal: the implementer runs the task's verify commands itself.
"""

import asyncio
import json
import time
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ai_decision_arena import tool_log
from ai_decision_arena.config import get_settings
from ai_decision_arena.workspace import sandbox
from ai_decision_arena.workspace.paths import Workspace, tool_path_problem

FILE_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]
COMMAND_TOOL = "mcp__workspace__run_command"
TOOL_OUTPUT_CHARS = 4000
# Emptied in the CLI's environment (it inherits the builder's): nothing the agent can reach should hold them.
SCRUBBED_FOR_CLI = ("DATABASE_URL", "TAVILY_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")


class AgentRun(BaseModel):
    """What happened in one agent attempt, as observed by Python."""

    ok: bool = False                 # the session ended normally (NOT "the task works": verify commands decide that)
    subtype: str = ""
    error: str | None = None
    num_turns: int = 0
    cost_usd: float = 0.0
    usage: dict = Field(default_factory=dict)
    duration_seconds: float = 0.0
    final_text: str = ""
    tool_calls: list[dict] = Field(default_factory=list)     # {tool, target, denied}
    commands: list[dict] = Field(default_factory=list)       # {command, ok, exit_code, refused}
    session_id: str | None = None


def _target(tool_input: dict) -> str:
    for key in ("file_path", "path", "pattern", "command"):
        if tool_input.get(key):
            return str(tool_input[key])[:200]
    return ""


async def _run(ws: Workspace, prompt: str, system_append: str, model: str, label: str) -> AgentRun:
    from claude_agent_sdk import (ClaudeAgentOptions, HookMatcher, ResultMessage, create_sdk_mcp_server, query,
                                  tool)

    settings = get_settings()
    run = AgentRun()
    log_path = ws.logs / f"{label}.log"

    def log(line: str) -> None:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {line}\n")

    async def pre_tool_use(input_data, tool_use_id, context):
        name, tool_input = input_data["tool_name"], input_data.get("tool_input") or {}
        reason = None if name == COMMAND_TOOL else tool_path_problem(ws, name, tool_input)
        if name not in FILE_TOOLS and name != COMMAND_TOOL:
            reason = f"tool {name} is not available here"
        run.tool_calls.append({"tool": name, "target": _target(tool_input), "denied": reason})
        tool_log.record(ws.session_id, "agent", name, target=_target(tool_input), ok=reason is None, reason=reason,
                        label=label)
        log(f"{'DENIED ' if reason else ''}{name} {_target(tool_input)}" + (f" ({reason})" if reason else ""))
        if reason:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
        return {}

    @tool("run_command", "Run ONE command in the project root and get its exit code and output. No shell: no &&, "
          "pipes, redirects or env assignments. Allowed executables: " + ", ".join(sandbox.ALLOWED_EXECUTABLES)
          + ". Long installs are allowed (npm install).", {"command": str})
    async def run_command(args):
        result = await asyncio.to_thread(sandbox.run, ws, str(args.get("command", "")), label=label)
        run.commands.append({"command": result.command, "ok": result.ok, "exit_code": result.exit_code,
                             "refused": result.refused})
        log(f"command {result.command!r}: {result.summary()}")
        text = json.dumps({"ok": result.ok, "exit_code": result.exit_code, "refused": result.refused,
                           "timed_out": result.timed_out, "stdout": result.stdout_tail[-TOOL_OUTPUT_CHARS:],
                           "stderr": result.stderr_tail[-TOOL_OUTPUT_CHARS:]})
        return {"content": [{"type": "text", "text": text}], "is_error": not result.ok}

    config_dir = ws.builder / "claude-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    if settings.is_local:
        auth = {"ANTHROPIC_BASE_URL": settings.local_base_url, "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": "",
                # the CLI's background calls (titles, summaries) use the "small fast" / haiku slot: keep them local too
                **{slot: model for slot in ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                                            "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_SMALL_FAST_MODEL")},
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                **({} if settings.local_think else {"MAX_THINKING_TOKENS": "0"})}
    else:
        auth = {"ANTHROPIC_API_KEY": settings.anthropic_api_key.get_secret_value()}
    options = ClaudeAgentOptions(
        cwd=str(ws.app),
        model=model,
        effort=None if settings.is_local else settings.implementer_effort,
        system_prompt={"type": "preset", "preset": "claude_code", "append": system_append},
        tools=FILE_TOOLS,
        allowed_tools=[*FILE_TOOLS, COMMAND_TOOL],
        permission_mode="dontAsk",
        mcp_servers={"workspace": create_sdk_mcp_server("workspace", tools=[run_command])},
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_use])]},
        setting_sources=[],
        skills=[],
        max_turns=settings.implementer_max_turns,
        max_budget_usd=None if settings.is_local else settings.implementer_task_budget_usd,
        env={**auth, "CLAUDE_CONFIG_DIR": str(config_dir), **{name: "" for name in SCRUBBED_FOR_CLI}},
        stderr=lambda line: log(f"[cli] {line[:300]}"),
    )
    log(f"--- attempt start: model {model}" + (f" (local, {settings.local_base_url})" if settings.is_local
                                               else f", effort {settings.implementer_effort}"))

    async def consume() -> None:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                run.subtype, run.num_turns, run.session_id = message.subtype, message.num_turns, message.session_id
                # local: the CLI prices unknown models with its own guess; Ollama costs nothing
                run.cost_usd = 0.0 if settings.is_local else float(message.total_cost_usd or 0.0)
                run.usage = message.usage or {}
                run.final_text = (message.result or "")[:4000]
                run.ok = not message.is_error and message.subtype == "success"
                if not run.ok:
                    run.error = f"agent ended with {message.subtype}" + (
                        f": {'; '.join(message.errors)}" if message.errors else "")

    t0 = time.monotonic()
    try:
        await asyncio.wait_for(consume(), timeout=settings.implementer_task_timeout_seconds)
    except TimeoutError:
        run.ok, run.error = False, f"agent timed out after {settings.implementer_task_timeout_seconds:.0f} s"
    except Exception as exc:          # CLI crash, API error after its retries...
        run.ok, run.error = False, f"{type(exc).__name__}: {str(exc)[:500]}"
    run.duration_seconds = round(time.monotonic() - t0, 1)
    log(f"--- attempt end: {'ok' if run.ok else run.error} · {run.num_turns} turns · ${run.cost_usd:.4f} · "
        f"{run.duration_seconds}s\n{run.final_text}")
    return run


def run_agent_task(ws: Workspace, prompt: str, system_append: str, *, model: str, label: str) -> AgentRun:
    """Run the agent once for one task (blocking; call from a worker thread, e.g. a graph node)."""
    ws.logs.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_run(ws, prompt, system_append, model, label))
