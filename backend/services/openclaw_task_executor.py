"""
OpenClaw 任务执行器 — 与 OpenClaw Gateway / CLI 通信
负责触发 Agent 执行定时任务，捕获执行结果。

支持两种执行模式：
  1. CLI 模式（推荐）：通过 `openclaw agent` CLI 命令触发
  2. HTTP API 模式：通过 OpenClaw Gateway REST API 触发

Dev Spec: DEV-SCHEDULED-TASKS v2.0
"""

import asyncio
import logging
import os
import shlex
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── 配置 ──
OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
OPENCLAW_BIN = os.getenv("OPENCLAW_BIN", "openclaw")
ALLOW_SCHEDULED_SHELL = os.getenv("ALLOW_SCHEDULED_SHELL", "false").lower() == "true"
SCHEDULED_SHELL_ALLOWLIST = {
    item.strip()
    for item in os.getenv("SCHEDULED_SHELL_ALLOWLIST", "").split(",")
    if item.strip()
}
SHELL_CONTROL_TOKENS = {"|", "&", ";", "&&", "||", ">", ">>", "<", "$(", "`"}


class ExecutionResult:
    """结构化执行结果"""

    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        duration_ms: int = 0,
        exit_code: Optional[int] = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.exit_code = exit_code

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
        }

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"ExecutionResult({status} {self.duration_ms}ms)"


class OpenClawTaskExecutor:
    """
    OpenClaw 任务执行器

    职责：
      - 解析 task 的 command / command_args
      - 通过 CLI 或 HTTP 触发 Agent 执行
      - 捕获输出/错误/耗时
      - 返回结构化 ExecutionResult
    """

    def __init__(
        self,
        gateway_url: str = OPENCLAW_GATEWAY_URL,
        default_timeout: int = 300,
    ):
        self.gateway_url = gateway_url.rstrip("/")
        self.default_timeout = default_timeout

    async def execute(
        self,
        command: str,
        command_args: Optional[dict] = None,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        执行一个任务命令

        Args:
            command: 命令类型，如 "agent_run", "shell", "http_request" 等
            command_args: 命令参数
            timeout_seconds: 超时时间（秒）

        Returns:
            ExecutionResult 结构化结果
        """
        command_args = command_args or {}
        start_time = time.monotonic()

        try:
            if command == "agent_run":
                result = await self._execute_agent_run(command_args, timeout_seconds)
            elif command == "shell":
                result = await self._execute_shell(command_args, timeout_seconds)
            elif command == "http_request":
                result = await self._execute_http_request(command_args, timeout_seconds)
            elif command == "echo":
                result = ExecutionResult(
                    success=True,
                    output=str(command_args.get("message", "echo")),
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
            elif command == "":
                # 空命令视为模拟执行
                result = ExecutionResult(
                    success=True,
                    output="模拟执行：command 为空",
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
            else:
                result = ExecutionResult(
                    success=False,
                    error=f"未知命令类型: {command}",
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )

        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start_time) * 1000)
            result = ExecutionResult(
                success=False,
                error=f"任务执行超时（{timeout_seconds}s）",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.error(f"任务执行异常: {e}", exc_info=True)
            result = ExecutionResult(
                success=False,
                error=f"执行异常: {str(e)}",
                duration_ms=elapsed,
            )

        return result

    # ── Agent 执行 ──

    async def _execute_agent_run(
        self, args: dict, timeout_seconds: int
    ) -> ExecutionResult:
        """通过 OpenClaw CLI 触发 Agent 执行"""
        agent_id = args.get("agent_id", "")
        message = args.get("message", "")

        if not agent_id:
            return ExecutionResult(
                success=False, error="agent_run 缺少 agent_id 参数"
            )
        if not message:
            return ExecutionResult(
                success=False, error="agent_run 缺少 message 参数"
            )

        # 优先尝试 CLI 方式
        try:
            return await self._execute_via_cli(agent_id, message, timeout_seconds)
        except FileNotFoundError:
            logger.warning("openclaw CLI 不可用，回退到 HTTP API")

        # 回退到 HTTP API 方式
        return await self._execute_via_http_api(agent_id, message, timeout_seconds)

    async def _execute_via_cli(
        self, agent_id: str, message: str, timeout_seconds: int
    ) -> ExecutionResult:
        """
        使用 `openclaw agent` CLI 命令触发 Agent

        命令格式: openclaw agent --agent <id> "<message>"
        """
        cmd = [OPENCLAW_BIN, "agent", "--agent", agent_id, message]
        logger.info(f"CLI 执行: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        success = proc.returncode == 0
        output = stdout or stderr

        return ExecutionResult(
            success=success,
            output=output,
            error=stderr if not success else "",
            exit_code=proc.returncode,
        )

    async def _execute_via_http_api(
        self, agent_id: str, message: str, timeout_seconds: int
    ) -> ExecutionResult:
        """
        通过 OpenClaw Gateway HTTP API 触发 Agent

        使用 POST /api/v1/sessions/send 或类似的端点
        如果 Gateway 不支持直接 agent 调用，则回退到 sessions send
        """
        logger.info(
            f"HTTP API 执行: agent={agent_id}, message={message[:100]}..."
        )

        errors = []

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # 尝试多种方式触发 Agent
            # 方式 1: 通过 sessions send
            try:
                resp = await client.post(
                    f"{self.gateway_url}/api/v1/sessions/send",
                    json={
                        "agent_id": agent_id,
                        "message": message,
                    },
                )
                if resp.status_code in (200, 201):
                    return ExecutionResult(
                        success=True,
                        output=resp.text[:2000],
                    )
                errors.append(f"/api/v1/sessions/send HTTP {resp.status_code}: {resp.text[:500]}")
            except httpx.RequestError as exc:
                errors.append(f"/api/v1/sessions/send request error: {exc}")

            # 方式 2: 通过 agent 端点
            try:
                resp = await client.post(
                    f"{self.gateway_url}/api/v1/agents/{agent_id}/run",
                    json={"message": message},
                )
                if resp.status_code in (200, 201):
                    return ExecutionResult(
                        success=True,
                        output=resp.text[:2000],
                    )
                errors.append(f"/api/v1/agents/{agent_id}/run HTTP {resp.status_code}: {resp.text[:500]}")
            except httpx.RequestError as exc:
                errors.append(f"/api/v1/agents/{agent_id}/run request error: {exc}")

        return ExecutionResult(
            success=False,
            error=f"无法通过 HTTP API 连接到 Gateway ({self.gateway_url}): " + " | ".join(errors),
        )

    # ── Shell 执行 ──

    async def _execute_shell(
        self, args: dict, timeout_seconds: int
    ) -> ExecutionResult:
        """执行显式允许的命令，不经过 shell 解释器。"""
        shell_cmd = args.get("command", "")
        if not shell_cmd:
            return ExecutionResult(
                success=False, error="shell 命令不能为空"
            )

        if not ALLOW_SCHEDULED_SHELL:
            return ExecutionResult(
                success=False,
                error="shell 命令执行已禁用；如确需启用，请设置 ALLOW_SCHEDULED_SHELL=true 并配置 SCHEDULED_SHELL_ALLOWLIST",
            )

        try:
            cmd = shlex.split(shell_cmd)
        except ValueError as exc:
            return ExecutionResult(success=False, error=f"shell 命令解析失败: {exc}")

        if not cmd:
            return ExecutionResult(success=False, error="shell 命令不能为空")

        if any(token in shell_cmd for token in SHELL_CONTROL_TOKENS):
            return ExecutionResult(
                success=False,
                error="shell 命令包含控制符，已拒绝执行；请改用单一可执行文件和参数",
            )

        if not SCHEDULED_SHELL_ALLOWLIST or cmd[0] not in SCHEDULED_SHELL_ALLOWLIST:
            return ExecutionResult(
                success=False,
                error=f"shell 命令 '{cmd[0]}' 未在 SCHEDULED_SHELL_ALLOWLIST 中，已拒绝执行",
            )

        logger.info("Shell 执行: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        success = proc.returncode == 0

        return ExecutionResult(
            success=success,
            output=stdout if success else stderr,
            error=stderr if not success else "",
            exit_code=proc.returncode,
        )

    # ── HTTP 请求执行 ──

    async def _execute_http_request(
        self, args: dict, timeout_seconds: int
    ) -> ExecutionResult:
        """执行 HTTP 请求"""
        url = args.get("url", "")
        method = args.get("method", "GET").upper()
        headers = args.get("headers", {})
        body = args.get("body")

        if not url:
            return ExecutionResult(
                success=False, error="http_request 缺少 url 参数"
            )

        logger.info(f"HTTP 请求: {method} {url}")

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            kwargs: dict = {"url": url, "headers": headers}
            if body:
                kwargs["json"] = body if isinstance(body, dict) else body
                kwargs["content"] = body if isinstance(body, str) else None

            try:
                resp = await client.request(method, **{k: v for k, v in kwargs.items() if v is not None or k in ("url", "headers")})
                return ExecutionResult(
                    success=resp.status_code < 400,
                    output=resp.text[:2000],
                    error=f"HTTP {resp.status_code}" if resp.status_code >= 400 else "",
                )
            except httpx.RequestError as e:
                return ExecutionResult(
                    success=False,
                    error=f"HTTP 请求失败: {str(e)}",
                )


# ── 全局单例 ──
openclaw_task_executor = OpenClawTaskExecutor()
