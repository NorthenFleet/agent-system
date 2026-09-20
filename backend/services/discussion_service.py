"""AI discussion workspace with an Obsidian archive and research promotion."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_manager import knowledge_manager
from project_manager import project_manager
from unified_data_manager import unified_data_manager


STATUSES = {"captured", "exploring", "research_candidate", "promoted", "closed"}
LINK_TYPES = {"project", "agent", "knowledge", "discussion"}


class DiscussionError(ValueError):
    """A request conflicts with the discussion lifecycle or its scope."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:50]


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[\\/:*?\"<>|]+", "-", value or "讨论")
    clean = re.sub(r"\s+", " ", clean).strip(" .-")
    return clean[:80] or "讨论"


class DiscussionService:
    def __init__(self, db_manager=unified_data_manager):
        self.db_manager = db_manager
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.db_manager.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS discussions (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'captured',
                    summary TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL DEFAULT '',
                    current_conclusion TEXT NOT NULL DEFAULT '',
                    hypothesis TEXT NOT NULL DEFAULT '',
                    open_questions_json TEXT NOT NULL DEFAULT '[]',
                    topics_json TEXT NOT NULL DEFAULT '[]',
                    agent_ids_json TEXT NOT NULL DEFAULT '[]',
                    vault_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL DEFAULT '',
                    promoted_project_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_discussions_owner_updated
                    ON discussions(owner_user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_discussions_owner_status
                    ON discussions(owner_user_id, status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS discussion_links (
                    id TEXT PRIMARY KEY,
                    discussion_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL DEFAULT 'related',
                    created_at TEXT NOT NULL,
                    UNIQUE(discussion_id, target_type, target_id),
                    FOREIGN KEY(discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS discussion_revisions (
                    id TEXT PRIMARY KEY,
                    discussion_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(discussion_id, revision),
                    FOREIGN KEY(discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS discussion_messages (
                    id TEXT PRIMARY KEY,
                    discussion_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_discussion_messages_discussion
                    ON discussion_messages(discussion_id, created_at);
                """
            )
            # Existing local installations predate these columns.  SQLite has
            # no ADD COLUMN IF NOT EXISTS, so make this migration idempotent.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(discussions)")}
            if "hypothesis" not in columns:
                conn.execute("ALTER TABLE discussions ADD COLUMN hypothesis TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _serialize(row: sqlite3.Row, links: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        item = dict(row)
        item["open_questions"] = _loads(item.pop("open_questions_json", "[]"), [])
        item["topics"] = _loads(item.pop("topics_json", "[]"), [])
        item["agent_ids"] = _loads(item.pop("agent_ids_json", "[]"), [])
        item["links"] = links if links is not None else []
        return item

    @staticmethod
    def _messages(conn: sqlite3.Connection, discussion_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT id, role, content, created_at, metadata_json FROM discussion_messages WHERE discussion_id=? ORDER BY created_at, id",
            (discussion_id,),
        ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _loads(item.pop("metadata_json", "{}"), {})
            messages.append(item)
        return messages

    def _links(self, conn: sqlite3.Connection, discussion_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute(
            "SELECT id, target_type, target_id, relation, created_at FROM discussion_links WHERE discussion_id=? ORDER BY created_at",
            (discussion_id,),
        ).fetchall()]

    def _note_path(self, discussion_id: str, title: str) -> tuple[Path, str]:
        root = knowledge_manager.vault_path.resolve()
        relative = Path("04-笔记库-Notes") / "讨论记录" / f"{discussion_id}-{_safe_filename(title)}.md"
        return root / relative, relative.as_posix()

    @staticmethod
    def _note_content(item: dict[str, Any], body: str) -> str:
        def value(field: Any) -> str:
            return json.dumps(str(field or ""), ensure_ascii=False)

        topics = json.dumps(_text_list(item.get("topics")), ensure_ascii=False)
        agents = json.dumps(_text_list(item.get("agent_ids")), ensure_ascii=False)
        questions = "\n".join(f"- {entry}" for entry in _text_list(item.get("open_questions"))) or "- "
        return f"""---
id: {item['id']}
type: discussion
title: {value(item['title'])}
status: {item['status']}
topics: {topics}
agent_ids: {agents}
created_at: {item['created_at']}
updated_at: {item['updated_at']}
---

# {item['title']}

## 原始问题或灵感

{item.get('question', '').strip()}

## 讨论内容

{body.strip()}

## 当前结论

{item.get('current_conclusion', '').strip()}

## 初步假设

{item.get('hypothesis', '').strip()}

## 待验证问题

{questions}

## 摘要

{item.get('summary', '').strip()}

"""

    @staticmethod
    def _write_atomic(path: Path, content: str) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(path)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_note(self, vault_path: str) -> tuple[str, bool]:
        root = knowledge_manager.vault_path.resolve()
        target = (root / vault_path).resolve()
        if root not in target.parents or not target.is_file():
            return "", False
        return target.read_text(encoding="utf-8", errors="ignore"), True

    @staticmethod
    def _note_section(content: str, heading: str) -> str:
        """Extract a writable section without feeding the full note back into itself."""
        match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""

    def list(self, *, owner_user_id: str, status: str = "", query: str = "", topic: str = "", limit: int = 100) -> dict[str, Any]:
        if status and status not in STATUSES:
            raise DiscussionError("invalid discussion status")
        clauses, params = ["owner_user_id=?"], [owner_user_id]
        if status:
            clauses.append("status=?")
            params.append(status)
        with self.db_manager.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM discussions WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
                [*params, max(1, min(limit, 300))],
            ).fetchall()
            items = [self._serialize(row, self._links(conn, row["id"])) for row in rows]
        needle = query.strip().lower()
        selected_topic = topic.strip().lower()
        if needle:
            items = [item for item in items if needle in " ".join([
                item["title"], item["summary"], item["question"], item["current_conclusion"], *item["topics"], *item["open_questions"],
            ]).lower()]
        if selected_topic:
            items = [item for item in items if selected_topic in {entry.lower() for entry in item["topics"]}]
        return {"items": items, "total": len(items), "topics": sorted({topic for item in items for topic in item["topics"]})}

    def get(self, discussion_id: str, *, owner_user_id: str) -> dict[str, Any]:
        with self.db_manager.connect() as conn:
            row = conn.execute("SELECT * FROM discussions WHERE id=? AND owner_user_id=?", (discussion_id, owner_user_id)).fetchone()
            if not row:
                raise DiscussionError("discussion not found")
            item = self._serialize(row, self._links(conn, discussion_id))
            revisions = [dict(revision) for revision in conn.execute(
                "SELECT revision, content_hash, summary, action, created_at FROM discussion_revisions WHERE discussion_id=? ORDER BY revision DESC",
                (discussion_id,),
            ).fetchall()]
        content, available = self._read_note(item["vault_path"])
        return {
            **item,
            "content": content,
            "body": self._note_section(content, "讨论内容") if available else "",
            "content_available": available,
            "revisions": revisions,
            "messages": self.messages(discussion_id, owner_user_id=owner_user_id),
        }

    def messages(self, discussion_id: str, *, owner_user_id: str) -> list[dict[str, Any]]:
        with self.db_manager.connect() as conn:
            row = conn.execute("SELECT 1 FROM discussions WHERE id=? AND owner_user_id=?", (discussion_id, owner_user_id)).fetchone()
            if not row:
                raise DiscussionError("discussion not found")
            return self._messages(conn, discussion_id)

    def create_conversation(self, *, owner_user_id: str, agent_id: str = "optimus") -> dict[str, Any]:
        """Create a durable discussion draft; archive to Obsidian only on save."""
        now = _now()
        discussion_id = f"DISC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        with self.db_manager.connect() as conn:
            conn.execute(
                """INSERT INTO discussions (id, owner_user_id, title, status, summary, question, current_conclusion, hypothesis,
                   open_questions_json, topics_json, agent_ids_json, vault_path, content_hash, created_at, updated_at)
                   VALUES (?, ?, '新讨论', 'captured', '', '', '', '', '[]', '[]', ?, '', '', ?, ?)""",
                (discussion_id, owner_user_id, json.dumps([agent_id], ensure_ascii=False), now, now),
            )
        return self.get(discussion_id, owner_user_id=owner_user_id)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                result = json.loads(cleaned[start:end + 1])
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                return None

    def parse_agent_reply(self, raw: str) -> tuple[str, dict[str, Any]]:
        parsed = self._extract_json(raw)
        if not parsed or not str(parsed.get("reply") or "").strip():
            return raw.strip() or "我暂时没有生成回复，请再试一次。", {}
        fields = {
            "title": str(parsed.get("title") or "").strip()[:160],
            "summary": str(parsed.get("summary") or "").strip()[:2000],
            "question": str(parsed.get("question") or "").strip()[:6000],
            "current_conclusion": str(parsed.get("current_conclusion") or "").strip()[:6000],
            "hypothesis": str(parsed.get("hypothesis") or "").strip()[:6000],
            "topics": _text_list(parsed.get("topics")),
            "open_questions": _text_list(parsed.get("open_questions")),
        }
        status = str(parsed.get("status") or "")
        if status in STATUSES:
            fields["status"] = status
        return str(parsed["reply"]).strip(), fields

    def conversation_prompt(self, discussion_id: str, user_message: str, *, owner_user_id: str) -> str:
        item = self.get(discussion_id, owner_user_id=owner_user_id)
        history = item["messages"][-12:]
        transcript = "\n".join(
            f"{'用户' if entry['role'] == 'user' else '助手'}：{entry['content']}" for entry in history
        ) or "（这是第一轮对话。）"
        return f"""你是“讨论与研究”工作台的 AI 研究助手。请用自然、具体的中文和用户继续思考；不要虚构事实，也不要把不确定推断说成定论。

当前讨论（最近记录）：
{transcript}

用户刚刚说：{user_message.strip()}

你的输出必须是一个 JSON 对象，且不要使用 Markdown 代码块：
{{
  "reply": "给用户看的正常对话回复，使用段落或简短列表",
  "title": "不超过 24 字、能概括此讨论的标题",
  "topics": ["最多 5 个主题"],
  "question": "当前最核心的问题；没有则空字符串",
  "summary": "截至当前的一两句摘要",
  "current_conclusion": "当前已经形成的结论；没有则空字符串",
  "open_questions": ["仍需验证或回答的问题"],
  "hypothesis": "可检验的初步假设；没有则空字符串",
  "status": "captured、exploring 或 research_candidate"
}}
根据对话实时更新所有字段；不要因信息不足而杜撰。"""

    def add_turn(self, discussion_id: str, user_content: str, assistant_content: str, generated: dict[str, Any], *, owner_user_id: str) -> dict[str, Any]:
        content = user_content.strip()
        if not content:
            raise DiscussionError("message is required")
        current = self.get(discussion_id, owner_user_id=owner_user_id)
        now = _now()
        with self.db_manager.connect() as conn:
            conn.executemany(
                "INSERT INTO discussion_messages (id, discussion_id, role, content, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (f"discussion-message-{uuid.uuid4().hex[:12]}", discussion_id, "user", content[:12000], now, "{}"),
                    (f"discussion-message-{uuid.uuid4().hex[:12]}", discussion_id, "assistant", assistant_content.strip()[:24000], _now(), json.dumps(generated, ensure_ascii=False)),
                ],
            )
            item = {key: generated.get(key, current.get(key)) for key in ("title", "summary", "question", "current_conclusion", "hypothesis", "topics", "open_questions", "status")}
            item["title"] = str(item["title"] or current["title"] or "新讨论")[:160]
            item["status"] = item["status"] if item["status"] in STATUSES else current["status"]
            conn.execute(
                """UPDATE discussions SET title=?, status=?, summary=?, question=?, current_conclusion=?, hypothesis=?,
                   open_questions_json=?, topics_json=?, updated_at=? WHERE id=? AND owner_user_id=?""",
                (item["title"], str(item["status"]), str(item["summary"] or "")[:2000], str(item["question"] or "")[:6000],
                 str(item["current_conclusion"] or "")[:6000], str(item["hypothesis"] or "")[:6000],
                 json.dumps(_text_list(item["open_questions"]), ensure_ascii=False), json.dumps(_text_list(item["topics"]), ensure_ascii=False),
                 _now(), discussion_id, owner_user_id),
            )
        return self.get(discussion_id, owner_user_id=owner_user_id)

    def archive(self, discussion_id: str, *, owner_user_id: str) -> dict[str, Any]:
        """Render the entire conversation to the vault, preserving its readable form."""
        item = self.get(discussion_id, owner_user_id=owner_user_id)
        messages = item["messages"]
        if not messages:
            raise DiscussionError("cannot archive an empty conversation")
        transcript = "\n\n".join(
            f"### {'你' if entry['role'] == 'user' else '研究助手'}\n\n{entry['content'].strip()}" for entry in messages
        )
        return self.update(discussion_id, {"body": f"## 对话记录\n\n{transcript}"}, owner_user_id=owner_user_id)

    def create(self, payload: dict[str, Any], *, owner_user_id: str) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise DiscussionError("title is required")
        now = _now()
        item = {
            "id": f"DISC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}",
            "owner_user_id": owner_user_id,
            "title": title[:160],
            "status": str(payload.get("status") or "captured"),
            "summary": str(payload.get("summary") or "").strip()[:2000],
            "question": str(payload.get("question") or "").strip()[:6000],
            "current_conclusion": str(payload.get("current_conclusion") or "").strip()[:6000],
            "open_questions": _text_list(payload.get("open_questions")),
            "topics": _text_list(payload.get("topics")),
            "agent_ids": _text_list(payload.get("agent_ids")),
            "created_at": now,
            "updated_at": now,
        }
        if item["status"] not in STATUSES:
            raise DiscussionError("invalid discussion status")
        note_path, relative_path = self._note_path(item["id"], item["title"])
        item["vault_path"] = relative_path
        content_hash = self._write_atomic(note_path, self._note_content(item, str(payload.get("body") or "")))
        with self.db_manager.connect() as conn:
            conn.execute(
                """INSERT INTO discussions (id, owner_user_id, title, status, summary, question, current_conclusion,
                   open_questions_json, topics_json, agent_ids_json, vault_path, content_hash, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["id"], owner_user_id, item["title"], item["status"], item["summary"], item["question"], item["current_conclusion"],
                 json.dumps(item["open_questions"], ensure_ascii=False), json.dumps(item["topics"], ensure_ascii=False), json.dumps(item["agent_ids"], ensure_ascii=False),
                 relative_path, content_hash, now, now),
            )
            conn.execute(
                "INSERT INTO discussion_revisions (id, discussion_id, revision, content_hash, summary, action, created_at) VALUES (?, ?, 1, ?, ?, 'created', ?)",
                (f"discussion-revision-{uuid.uuid4().hex[:12]}", item["id"], content_hash, item["summary"], now),
            )
        return self.get(item["id"], owner_user_id=owner_user_id)

    def update(self, discussion_id: str, payload: dict[str, Any], *, owner_user_id: str) -> dict[str, Any]:
        current = self.get(discussion_id, owner_user_id=owner_user_id)
        editable = {"title", "status", "summary", "question", "current_conclusion", "hypothesis", "open_questions", "topics", "agent_ids"}
        item = {key: payload[key] if key in payload and key in editable else current[key] for key in editable}
        item["title"] = str(item["title"] or "").strip()[:160]
        if not item["title"]:
            raise DiscussionError("title is required")
        item["status"] = str(item["status"] or "captured")
        if item["status"] not in STATUSES:
            raise DiscussionError("invalid discussion status")
        for name in ("open_questions", "topics", "agent_ids"):
            item[name] = _text_list(item[name])
        for name in ("summary", "question", "current_conclusion", "hypothesis"):
            item[name] = str(item[name] or "").strip()[:6000]
        item.update({"id": discussion_id, "created_at": current["created_at"], "updated_at": _now()})
        note_path, relative_path = self._note_path(discussion_id, item["title"])
        old_path = (knowledge_manager.vault_path.resolve() / current["vault_path"]).resolve()
        body = str(payload.get("body")) if "body" in payload else current["body"]
        content_hash = self._write_atomic(note_path, self._note_content(item, body))
        if old_path != note_path and old_path.exists() and old_path.parent == note_path.parent:
            old_path.unlink()
        with self.db_manager.connect() as conn:
            revision = conn.execute("SELECT COALESCE(MAX(revision), 0) + 1 FROM discussion_revisions WHERE discussion_id=?", (discussion_id,)).fetchone()[0]
            conn.execute(
                """UPDATE discussions SET title=?, status=?, summary=?, question=?, current_conclusion=?, hypothesis=?, open_questions_json=?, topics_json=?,
                   agent_ids_json=?, vault_path=?, content_hash=?, updated_at=? WHERE id=? AND owner_user_id=?""",
                (item["title"], item["status"], item["summary"], item["question"], item["current_conclusion"], item["hypothesis"],
                 json.dumps(item["open_questions"], ensure_ascii=False), json.dumps(item["topics"], ensure_ascii=False), json.dumps(item["agent_ids"], ensure_ascii=False),
                 relative_path, content_hash, item["updated_at"], discussion_id, owner_user_id),
            )
            conn.execute(
                "INSERT INTO discussion_revisions (id, discussion_id, revision, content_hash, summary, action, created_at) VALUES (?, ?, ?, ?, ?, 'updated', ?)",
                (f"discussion-revision-{uuid.uuid4().hex[:12]}", discussion_id, revision, content_hash, item["summary"], item["updated_at"]),
            )
        return self.get(discussion_id, owner_user_id=owner_user_id)

    def add_link(self, discussion_id: str, payload: dict[str, Any], *, owner_user_id: str) -> dict[str, Any]:
        self.get(discussion_id, owner_user_id=owner_user_id)
        target_type, target_id = str(payload.get("target_type") or ""), str(payload.get("target_id") or "").strip()
        if target_type not in LINK_TYPES or not target_id:
            raise DiscussionError("target_type and target_id are required")
        now = _now()
        with self.db_manager.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO discussion_links (id, discussion_id, target_type, target_id, relation, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (f"discussion-link-{uuid.uuid4().hex[:12]}", discussion_id, target_type, target_id, str(payload.get("relation") or "related")[:100], now),
            )
            conn.execute("UPDATE discussions SET updated_at=? WHERE id=?", (now, discussion_id))
        return self.get(discussion_id, owner_user_id=owner_user_id)

    def promote(self, discussion_id: str, payload: dict[str, Any], *, owner_user_id: str) -> dict[str, Any]:
        item = self.get(discussion_id, owner_user_id=owner_user_id)
        if item.get("promoted_project_id"):
            project = project_manager.get_project(item["promoted_project_id"])
            return {"discussion": item, "project": project, "reused": True}
        project = project_manager.create_project({
            "name": str(payload.get("project_name") or item["title"]).strip()[:160],
            "project_type": "research",
            "description": str(payload.get("description") or item["question"] or item["summary"]).strip(),
            "status": "planning",
            "current_phase": "problem_framing",
            "owner_agent": str(payload.get("owner_agent") or "optimus"),
            "enabled_modules": ["knowledge", "discussions"],
            "context": {
                "project_type": "research",
                "source_discussion_id": discussion_id,
                "source_discussion_path": item["vault_path"],
                "research_question": item["question"],
                "initial_hypothesis": str(payload.get("hypothesis") or item.get("hypothesis") or item["current_conclusion"]),
                "open_questions": item["open_questions"],
                "discussion_topics": item["topics"],
            },
        })
        now = _now()
        with self.db_manager.connect() as conn:
            conn.execute("UPDATE discussions SET status='promoted', promoted_project_id=?, updated_at=? WHERE id=? AND owner_user_id=?", (project["id"], now, discussion_id, owner_user_id))
        self.add_link(discussion_id, {"target_type": "project", "target_id": project["id"], "relation": "promoted_to"}, owner_user_id=owner_user_id)
        return {"discussion": self.get(discussion_id, owner_user_id=owner_user_id), "project": project, "reused": False}


discussion_service = DiscussionService()
