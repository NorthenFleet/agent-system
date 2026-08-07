"""Reliable Feishu delivery through the existing OpenClaw account binding."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from services.openclaw_cli import openclaw_command



def _find_message_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("message_id", "messageId", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for nested in value.values():
            found = _find_message_id(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_message_id(nested)
            if found:
                return found
    return ""


class FeishuOutboxSender:
    async def send(self, item: dict[str, Any]) -> dict[str, Any]:
        channel = str(item.get("channel") or "feishu")
        if channel not in {"feishu", "lark"}:
            return {
                "success": False,
                "error": f"Unsupported outbound channel: {channel}",
                "response": "",
                "external_message_id": "",
            }
        target = str(item.get("target") or "").strip()
        if not target:
            return {
                "success": False,
                "error": "Feishu target is empty",
                "response": "",
                "external_message_id": "",
            }
        command = openclaw_command(
            "message",
            "send",
            "--channel",
            "feishu",
            "--account",
            str(item.get("account_id") or "optimus"),
            "--target",
            target,
            "--message",
            str(item.get("message_text") or ""),
            "--json",
        )
        reply_to = str(item.get("reply_to") or "").strip()
        if reply_to:
            command.extend(["--reply-to", reply_to])

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=max(15, int(os.getenv("COMMAND_CENTER_SEND_TIMEOUT", "60"))),
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        external_message_id = ""
        if stdout:
            try:
                external_message_id = _find_message_id(json.loads(stdout))
            except json.JSONDecodeError:
                external_message_id = ""
        return {
            "success": process.returncode == 0,
            "response": stdout,
            "error": stderr if process.returncode else "",
            "external_message_id": external_message_id,
        }
