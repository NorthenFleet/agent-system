#!/usr/bin/env python3
"""Incrementally extract durable OpenClaw conversation memory.

The extractor reads user-facing main/direct session JSONL files, writes concise
conversation excerpts into each agent's standard ``workspace/memory`` tree, and
optionally asks OpenClaw to incrementally refresh that agent's memory index.
It never truncates or deletes session history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_AGENTS = (
    "main",
    "optimus",
    "bumblebee",
    "perceptor",
    "wheeljack",
    "shockwave",
    "ultra-magnus",
    "ironhide",
    "ratchet",
    "leonardo",
    "donatello",
    "raphael",
    "michelangelo",
)

TOKEN_WARNING = 200_000
TOKEN_CRITICAL = 500_000
BLOCKED_PROMPT_MARKERS = (
    "<hook_prompt",
    "[Inter-session message]",
    "sourceTool=sessions_send",
    "heartbeat",
    "HEARTBEAT_OK",
    "OMX cannot authorize Stop",
    "COMMAND_CENTER_E2E_OK",
    "ROUTE-AGENT-",
    "JSON schema:",
    "只输出一个 JSON 对象",
    "当前步骤：",
    "做最终验收总结",
    "你是擎天柱，负责把用户目标拆解",
    "这是一个已获批准的任务步骤",
)


def _default_state() -> dict[str, Any]:
    return {
        "version": 2,
        "files": {},
        "seen_ids": [],
        "last_run": None,
        "agents_updated": 0,
        "total_entries": 0,
    }


class MemoryExtractor:
    def __init__(
        self,
        openclaw_home: str | Path = "~/.openclaw",
        *,
        agents: tuple[str, ...] = DEFAULT_AGENTS,
        now: Callable[[], datetime] = datetime.now,
        backfill_lines: int = 80,
        max_entries_per_agent: int = 30,
    ):
        self.home = Path(openclaw_home).expanduser()
        self.agents = agents
        self.now = now
        self.backfill_lines = max(20, backfill_lines)
        self.max_entries_per_agent = max(5, max_entries_per_agent)
        self.agents_root = self.home / "agents"
        self.workspace_root = self.home / "workspace" / "agents"
        self.state_path = self.home / "cron" / "memory-extract-state.json"

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return _default_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_state()
        if payload.get("version") != 2:
            return _default_state()
        state = _default_state()
        state.update(payload)
        state["files"] = payload.get("files") if isinstance(payload.get("files"), dict) else {}
        state["seen_ids"] = payload.get("seen_ids") if isinstance(payload.get("seen_ids"), list) else []
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)

    def run(
        self,
        *,
        dry_run: bool = False,
        index: bool = True,
    ) -> dict[str, Any]:
        state = self.load_state()
        seen_ids = set(str(item) for item in state.get("seen_ids", []))
        next_file_state = dict(state.get("files") or {})
        agents_updated = 0
        total_entries = 0
        index_results: dict[str, dict[str, Any]] = {}
        alerts = self.session_token_alerts()
        previews: dict[str, list[dict[str, Any]]] = {}

        for agent in self.agents:
            entries, cursors = self.collect_agent(agent, state, seen_ids)
            if len(entries) > self.max_entries_per_agent:
                entries = entries[-self.max_entries_per_agent :]
            if entries:
                previews[agent] = entries
                if not dry_run:
                    self.write_entries(agent, entries)
                agents_updated += 1
                total_entries += len(entries)
                seen_ids.update(entry["event_id"] for entry in entries)
                if index and not dry_run:
                    index_results[agent] = self.refresh_index(agent)
            next_file_state.update(cursors)

        result = {
            "agents_updated": agents_updated,
            "total_entries": total_entries,
            "alerts": alerts,
            "index_results": index_results,
            "dry_run": dry_run,
            "previews": {
                agent: [
                    {
                        "role": entry["role"],
                        "session": entry["session_key"],
                        "timestamp": entry["timestamp"],
                        "text": entry["text"][:160],
                    }
                    for entry in entries
                ]
                for agent, entries in previews.items()
            },
        }
        if not dry_run:
            state.update(
                {
                    "version": 2,
                    "files": next_file_state,
                    "seen_ids": list(seen_ids)[-2000:],
                    "last_run": self.now().isoformat(),
                    "agents_updated": agents_updated,
                    "total_entries": total_entries,
                }
            )
            self.save_state(state)
        return result

    def collect_agent(
        self,
        agent: str,
        state: dict[str, Any],
        seen_ids: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        entries: list[dict[str, Any]] = []
        cursor_updates: dict[str, dict[str, Any]] = {}
        for session_key, session_path in self.user_session_files(agent):
            file_key = str(session_path)
            previous = (state.get("files") or {}).get(file_key) or {}
            records, cursor = self.read_new_records(session_path, previous)
            cursor_updates[file_key] = cursor
            for record in records:
                entry = self.record_to_entry(record, session_key)
                if not entry or entry["event_id"] in seen_ids:
                    continue
                entries.append(entry)
        entries.sort(key=lambda item: (item["timestamp"], item["event_id"]))
        return entries, cursor_updates

    def user_session_files(self, agent: str) -> list[tuple[str, Path]]:
        registry = self.agents_root / agent / "sessions" / "sessions.json"
        if not registry.exists():
            return []
        try:
            sessions = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        found: list[tuple[str, Path]] = []
        for session_key, session in sessions.items():
            if not self.is_user_session(str(session_key)) or not isinstance(session, dict):
                continue
            raw_path = str(session.get("sessionFile") or "")
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if path.exists() and path.is_file():
                found.append((str(session_key), path))
        return sorted(found, key=lambda item: item[0])

    @staticmethod
    def is_user_session(session_key: str) -> bool:
        return session_key.endswith(":main") or ":direct:" in session_key

    def read_new_records(
        self,
        path: Path,
        previous: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        stat = path.stat()
        previous_offset = int(previous.get("offset") or 0)
        previous_inode = int(previous.get("inode") or 0)
        first_seen = not previous
        reset = previous_inode not in {0, stat.st_ino} or previous_offset > stat.st_size
        if first_seen or reset:
            start_offset = self._tail_start(path, self.backfill_lines)
        else:
            start_offset = previous_offset

        records = []
        with path.open("rb") as handle:
            handle.seek(start_offset)
            for raw_line in handle:
                try:
                    record = json.loads(raw_line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
            final_offset = handle.tell()
        return records, {
            "offset": final_offset,
            "inode": stat.st_ino,
            "size": stat.st_size,
            "updated_at": self.now().isoformat(),
        }

    @staticmethod
    def _tail_start(path: Path, max_lines: int, max_bytes: int = 2_000_000) -> int:
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read()
        if start:
            separator = data.find(b"\n")
            if separator >= 0:
                data = data[separator + 1 :]
        lines = data.splitlines(keepends=True)
        selected = lines[-max_lines:]
        return size - sum(len(line) for line in selected)

    def record_to_entry(
        self,
        record: dict[str, Any],
        session_key: str,
    ) -> dict[str, Any] | None:
        if record.get("type") != "message" or not isinstance(record.get("message"), dict):
            return None
        message = record["message"]
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            return None
        text = self.clean_text(self.extract_text(message.get("content")))
        if not self.is_meaningful(text):
            return None
        raw_event_id = str(record.get("id") or "").strip()
        event_id = hashlib.sha256(
            f"{session_key}|{raw_event_id}|{record.get('timestamp')}|{role}|{text}".encode("utf-8")
        ).hexdigest()[:24]
        return {
            "event_id": event_id,
            "role": role,
            "text": text[:800],
            "timestamp": str(record.get("timestamp") or ""),
            "session_key": session_key,
        }

    @staticmethod
    def extract_text(content: Any) -> str:
        if isinstance(content, str):
            parts = [content]
        elif isinstance(content, list):
            parts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
        else:
            parts = []
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    @staticmethod
    def clean_text(text: str) -> str:
        value = str(text or "").strip()
        value = re.sub(
            r"^\[[A-Z][a-z]{2}\s+\d{4}-\d{2}-\d{2}[^\]]*\]\s*",
            "",
            value,
        )
        value = re.sub(
            r"^\[message_id:\s*[^\]]+\]\s*[A-Za-z0-9_-]+:\s*",
            "",
            value,
        )
        return value.strip()

    @staticmethod
    def is_meaningful(text: str) -> bool:
        if len(text) < 20:
            return False
        if any(marker.lower() in text.lower() for marker in BLOCKED_PROMPT_MARKERS):
            return False
        if text.startswith(("<system", "System:", "[tool]", "{\"schema\"")):
            return False
        visible = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
        return len(visible) >= 12

    def write_entries(self, agent: str, entries: list[dict[str, Any]]) -> Path:
        now = self.now()
        target = (
            self.workspace_root
            / agent
            / "workspace"
            / "memory"
            / "short-term"
            / f"{now:%Y-%m-%d}.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        is_new = not target.exists()
        with target.open("a", encoding="utf-8") as handle:
            if is_new:
                handle.write(f"# {now:%Y-%m-%d} 自动记忆\n")
            handle.write(f"\n## 会话摘录 {now:%H:%M}\n\n")
            for entry in entries:
                label = "用户" if entry["role"] == "user" else "智能体"
                timestamp = entry["timestamp"] or now.isoformat()
                handle.write(
                    f"- **{label}** `{timestamp}` ({entry['session_key']}): "
                    f"{entry['text']}\n"
                )
        return target

    def session_token_alerts(self) -> list[dict[str, Any]]:
        alerts = []
        for agent in self.agents:
            registry = self.agents_root / agent / "sessions" / "sessions.json"
            if not registry.exists():
                continue
            try:
                sessions = json.loads(registry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for session_key, session in sessions.items():
                if not isinstance(session, dict):
                    continue
                tokens = int(session.get("inputTokens") or 0)
                if tokens < TOKEN_WARNING:
                    continue
                alerts.append(
                    {
                        "agent_id": agent,
                        "session_key": session_key,
                        "tokens": tokens,
                        "level": "critical" if tokens >= TOKEN_CRITICAL else "warning",
                        "action": "alert_only",
                    }
                )
        return alerts

    @staticmethod
    def find_openclaw_command() -> list[str] | None:
        configured_node = os.getenv("OPENCLAW_NODE", "").strip()
        configured_entry = os.getenv("OPENCLAW_ENTRY", "").strip()
        if configured_node and configured_entry:
            node = Path(configured_node).expanduser()
            entry = Path(configured_entry).expanduser()
            if node.exists() and entry.exists():
                return [str(node), str(entry)]

        node_candidates = [
            *sorted(Path("/opt/homebrew/Cellar/node@22").glob("*/bin/node"), reverse=True),
            *sorted(Path("~/.nvm/versions/node").expanduser().glob("v22*/bin/node"), reverse=True),
            *sorted(Path("/opt/homebrew/Cellar/node@20").glob("*/bin/node"), reverse=True),
        ]
        entry_candidates = [
            *sorted(
                Path("/opt/homebrew/Cellar/node").glob(
                    "*/lib/node_modules/@qingchencloud/openclaw-zh/dist/index.js"
                ),
                reverse=True,
            ),
            Path("/opt/homebrew/lib/node_modules/@qingchencloud/openclaw-zh/dist/index.js"),
        ]
        node = next((path for path in node_candidates if path.exists()), None)
        entry = next((path for path in entry_candidates if path.exists()), None)
        if node and entry:
            return [str(node), str(entry)]

        configured = os.getenv("OPENCLAW_BIN", "").strip()
        executable = Path(configured).expanduser() if configured else None
        if executable and executable.exists():
            return [str(executable)]
        discovered = shutil.which("openclaw")
        return [discovered] if discovered else None

    def refresh_index(self, agent: str) -> dict[str, Any]:
        command = self.find_openclaw_command()
        if not command:
            return {"success": False, "error": "working OpenClaw runtime not found"}
        env = os.environ.copy()
        runtime_dir = Path(command[0]).parent
        env["PATH"] = f"{runtime_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        try:
            result = subprocess.run(
                [*command, "memory", "index", "--agent", agent],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"success": False, "error": str(exc)[:500]}
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "output": (result.stdout or "")[-1000:],
            "error": (result.stderr or "")[-1000:],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default=os.getenv("OPENCLAW_HOME", "~/.openclaw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--backfill-lines", type=int, default=80)
    args = parser.parse_args()

    extractor = MemoryExtractor(args.home, backfill_lines=args.backfill_lines)
    result = extractor.run(dry_run=args.dry_run, index=not args.no_index)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
