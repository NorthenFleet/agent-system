"""One-shot OpenClaw exec with operator-owned, non-inherited tool policies."""
import asyncio
import json
import tempfile
from pathlib import Path

from services.openclaw_cli import openclaw_command
from services.openclaw_task_executor import ExecutionResult
from services.agent_execution_profile_service import resolve_profile


def tool_config(role: str) -> dict:
    tools = {"profile": "coding", "fs": {"workspaceOnly": True}}
    if role == "advisor":
        tools["deny"] = ["*"]
    elif role == "worker":
        tools["allow"] = ["read", "write", "edit"]
        tools["deny"] = ["apply_patch"]
    else:
        raise ValueError("Unsupported isolated role")
    return {"tools": tools, "plugins": {"enabled": False},
            "skills": {"allowBundled": [], "load": {"watch": False}},
            "agents": {"defaults": {"skipBootstrap": True}},
            "env": {"shellEnv": {"enabled": False}}}


async def execute_isolated(role: str, prompt: str, *, cwd: str | None = None, timeout: int = 120, tool_control=None) -> ExecutionResult:
    profile = resolve_profile(role, required=True)
    provider = profile["requested_model"].split("/", 1)[0]
    if "/" not in profile["requested_model"] or provider.endswith("-cli"):
        raise ValueError("Isolated roles require a provider/model inference backend, not a CLI agent backend")
    if len(prompt.encode()) > 100_000:
        raise ValueError("Isolated prompt exceeds budget")
    with tempfile.TemporaryDirectory(prefix="command-isolated-") as directory:
        config = Path(directory) / "config.json"
        policy = tool_config(role)
        if tool_control is not None:
            if role != "worker":
                raise ValueError("Tool control is only available to isolated workers")
            policy = tool_control.config(policy)
        config.write_text(json.dumps(policy), encoding="utf-8")
        workspace = cwd if role == "worker" else directory
        if not workspace:
            raise ValueError("Worker requires an isolated worktree")
        command = openclaw_command("agent", "exec", "--config", str(config), "--cwd", workspace,
                                   "--model", profile["requested_model"], "--message-file", "-", "--json",
                                   "--timeout", str(timeout), "--code-mode", "direct")
        if profile["requested_thinking"]:
            command += ["--thinking", profile["requested_thinking"]]
        process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(prompt.encode()), timeout=timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if len(stdout) > 2_000_000:
            raise ValueError("Isolated result exceeds budget")
        try:
            envelope = json.loads(stdout)
        except (ValueError, UnicodeError):
            raise ValueError("OpenClaw exec did not return a JSON envelope") from None
        if not isinstance(envelope, dict) or not isinstance(envelope.get("final", ""), str):
            raise ValueError("Invalid OpenClaw exec envelope")
        profile.update(actual_model=envelope.get("model"), actual_provider=envelope.get("provider"),
                       usage=envelope.get("usage"), cost_usd=envelope.get("costUsd"))
        result = ExecutionResult(success=process.returncode == 0 and envelope.get("ok") is True,
                                 output=envelope.get("final", ""), error="" if envelope.get("ok") is True else "Isolated agent execution failed")
        result.execution_profile = profile
        return result
