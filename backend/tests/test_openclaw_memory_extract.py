import json
from datetime import datetime
from pathlib import Path

from scripts.openclaw_memory_extract import MemoryExtractor


NOW = datetime(2026, 7, 31, 9, 30)


def _record(record_type, event_id, role=None, text=""):
    payload = {
        "type": record_type,
        "id": event_id,
        "timestamp": f"2026-07-31T09:00:0{event_id[-1:]}+08:00",
    }
    if role:
        payload["message"] = {"role": role, "content": [{"type": "text", "text": text}]}
    return json.dumps(payload, ensure_ascii=False)


def _session(home: Path, agent: str, session_key: str, filename: str, lines, tokens=10):
    session_dir = home / "agents" / agent / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / filename
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    registry_path = session_dir / "sessions.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    registry[session_key] = {
        "sessionFile": str(session_file),
        "inputTokens": tokens,
    }
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return session_file


def test_extracts_main_and_direct_messages_without_touching_sessions(tmp_path):
    home = tmp_path / ".openclaw"
    direct_file = _session(
        home,
        "optimus",
        "agent:optimus:feishu:optimus:direct:user-1",
        "direct.jsonl",
        [
            _record("session", "event-0"),
            _record("message", "event-1", "user", "请规划 OpenClaw 智能体系统的审批与任务分发。"),
            _record("message", "event-2", "assistant", "已形成计划，等待批准后再执行相关开发任务。"),
            _record("message", "event-3", "toolResult", "这段工具输出不得进入记忆。"),
            _record(
                "message",
                "event-5",
                "user",
                "[Inter-session message] sourceTool=sessions_send 这段智能体转发不得进入记忆。",
            ),
        ],
        tokens=500_001,
    )
    _session(
        home,
        "optimus",
        "agent:optimus:cron:job-1",
        "cron.jsonl",
        [_record("message", "cron-1", "user", "这段定时任务内容不得进入用户记忆。")],
    )
    original = direct_file.read_text(encoding="utf-8")
    extractor = MemoryExtractor(home, agents=("optimus",), now=lambda: NOW)

    result = extractor.run(index=False)
    target = (
        home
        / "workspace"
        / "agents"
        / "optimus"
        / "workspace"
        / "memory"
        / "short-term"
        / "2026-07-31.md"
    )
    content = target.read_text(encoding="utf-8")
    assert result["total_entries"] == 2
    assert "审批与任务分发" in content
    assert "等待批准" in content
    assert "工具输出" not in content
    assert "定时任务内容" not in content
    assert "智能体转发" not in content
    assert result["alerts"][0]["action"] == "alert_only"
    assert direct_file.read_text(encoding="utf-8") == original

    size = target.stat().st_size
    duplicate_run = extractor.run(index=False)
    assert duplicate_run["total_entries"] == 0
    assert target.stat().st_size == size

    with direct_file.open("a", encoding="utf-8") as handle:
        handle.write(
            _record("message", "event-4", "user", "批准计划，执行后请返回测试记录和可追踪证据。")
            + "\n"
        )
    incremental = extractor.run(index=False)
    assert incremental["total_entries"] == 1
    assert "可追踪证据" in target.read_text(encoding="utf-8")


def test_internal_orchestration_prompts_are_filtered(tmp_path):
    home = tmp_path / ".openclaw"
    _session(
        home,
        "optimus",
        "agent:optimus:main",
        "main.jsonl",
        [
            _record(
                "message",
                "event-1",
                "user",
                "你是擎天柱，负责把用户目标拆解。只输出一个 JSON 对象，JSON schema: {}",
            ),
            _record(
                "message",
                "event-2",
                "assistant",
                "用户要求统一上下文检索，并且所有任务都需要审批和执行证据。",
            ),
        ],
    )
    extractor = MemoryExtractor(home, agents=("optimus",), now=lambda: NOW)
    result = extractor.run(index=False)
    assert result["total_entries"] == 1
    content = next(
        (home / "workspace" / "agents" / "optimus").rglob("*.md")
    ).read_text(encoding="utf-8")
    assert "JSON schema" not in content
    assert "统一上下文检索" in content
