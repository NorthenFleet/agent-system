"""
Skill registry for OpenClaw/team-dashboard.

The registry is intentionally file-backed: skills are discovered from known
workspace directories, while lightweight management state such as agent bindings
is stored under backend/data.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
BINDINGS_FILE = DATA_DIR / "skill-bindings.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "skill"


def _read_bindings() -> dict[str, Any]:
    if not BINDINGS_FILE.exists():
        return {"version": 1, "agent_skills": {}, "skill_overrides": {}}
    try:
        with BINDINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    return {
        "version": data.get("version", 1),
        "agent_skills": data.get("agent_skills", {}),
        "skill_overrides": data.get("skill_overrides", {}),
    }


def _write_bindings(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with BINDINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_skill_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            header = text[3:end].strip()
            body = text[end + 4 :]
            for raw in header.splitlines():
                if ":" not in raw:
                    continue
                key, value = raw.split(":", 1)
                meta[key.strip().lower()] = value.strip().strip("'\"")
    if not meta.get("name"):
        heading = re.search(r"^#\s+(.+)$", body, re.M)
        if heading:
            meta["name"] = heading.group(1).strip()
    if not meta.get("description"):
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                meta["description"] = line[:300]
                break
    meta["_body"] = body
    return meta


def _infer_category(name: str, description: str, source: str) -> str:
    haystack = f"{name} {description}".lower()
    checks = [
        ("frontend", ("frontend", "browser", "ui", "playwright", "screenshot")),
        ("backend", ("api", "backend", "database", "python", "server")),
        ("documents", ("doc", "pdf", "spreadsheet", "presentation", "word")),
        ("cloud", ("cloud", "aliyun", "ecs", "deploy")),
        ("communication", ("gmail", "mail", "lark", "calendar", "im")),
        ("automation", ("automation", "workflow", "agent", "tool")),
    ]
    for category, keywords in checks:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "openclaw" if source == "openclaw-workspace" else "general"


def _extract_triggers(name: str, description: str, body: str) -> list[str]:
    text = f"{name} {description} {body[:2000]}".lower()
    candidates = [
        "api", "backend", "frontend", "browser", "playwright", "screenshot",
        "pdf", "docx", "spreadsheet", "gmail", "lark", "calendar", "cloud",
        "github", "search", "skill", "agent", "workflow", "test", "security",
    ]
    triggers = [word for word in candidates if word in text]
    return triggers[:10]


def _extract_required_tools(body: str) -> list[str]:
    tools = []
    for tool in ("playwright", "node", "python", "lark-cli", "gh", "git", "curl"):
        if re.search(rf"\b{re.escape(tool)}\b", body, re.I):
            tools.append(tool)
    return tools


def _skill_roots() -> list[tuple[str, Path]]:
    configured = os.getenv("SKILL_ROOTS", "")
    roots: list[tuple[str, Path]] = []
    if configured:
        for item in configured.split(","):
            if not item.strip():
                continue
            if "=" in item:
                source, raw_path = item.split("=", 1)
            else:
                source, raw_path = "custom", item
            roots.append((source.strip() or "custom", Path(os.path.expanduser(raw_path.strip()))))
    roots.extend([
        ("openclaw-workspace", Path(os.path.expanduser("~/.openclaw/workspace/skills"))),
        ("codex", Path(os.path.expanduser("~/.codex/skills"))),
        ("local-agents", Path(os.path.expanduser("~/.agents/skills"))),
        ("repo-agents", Path.cwd() / ".agents" / "skills"),
    ])
    return roots


def scan_skills() -> list[dict[str, Any]]:
    bindings = _read_bindings()
    assigned_by_skill: dict[str, list[str]] = {}
    for agent_id, skill_ids in bindings["agent_skills"].items():
        for skill_id in skill_ids:
            assigned_by_skill.setdefault(skill_id, []).append(agent_id)

    observed_at = _now_utc()
    rows: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for source, root in _skill_roots():
        if not root.exists() or not root.is_dir():
            continue
        for doc in sorted(root.glob("*/SKILL.md")):
            meta = _parse_skill_doc(doc)
            name = meta.get("name") or doc.parent.name
            base_id = _slug(name or doc.parent.name)
            skill_id = base_id
            if skill_id in used_ids:
                skill_id = _slug(f"{source}-{base_id}")
            used_ids.add(skill_id)
            description = meta.get("description", "")
            body = meta.get("_body", "")
            override = bindings["skill_overrides"].get(skill_id, {})
            enabled = bool(override.get("enabled", True))
            status = "available" if enabled else "disabled"
            rows.append({
                "id": skill_id,
                "name": name,
                "description": description,
                "category": override.get("category") or _infer_category(name, description, source),
                "source": source,
                "path": str(doc.parent),
                "version": meta.get("version") or override.get("version") or "unknown",
                "enabled": enabled,
                "status": status,
                "triggers": _extract_triggers(name, description, body),
                "required_tools": _extract_required_tools(body),
                "assigned_agents": sorted(assigned_by_skill.get(skill_id, [])),
                "last_checked_at": observed_at,
            })
    rows.sort(key=lambda item: (item["source"], item["category"], item["name"].lower()))
    return rows


def list_skills(query: str = "", category: str = "", source: str = "", status: str = "") -> list[dict[str, Any]]:
    rows = scan_skills()
    if query:
        q = query.lower()
        rows = [
            row for row in rows
            if q in row["id"].lower()
            or q in row["name"].lower()
            or q in row.get("description", "").lower()
            or any(q in trigger.lower() for trigger in row.get("triggers", []))
        ]
    if category:
        rows = [row for row in rows if row.get("category") == category]
    if source:
        rows = [row for row in rows if row.get("source") == source]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return rows


def get_skill(skill_id: str) -> dict[str, Any] | None:
    for skill in scan_skills():
        if skill["id"] == skill_id:
            return skill
    return None


def get_agent_skills(agent_id: str) -> list[dict[str, Any]]:
    bindings = _read_bindings()
    selected = set(bindings["agent_skills"].get(agent_id, []))
    return [skill for skill in scan_skills() if skill["id"] in selected]


def set_agent_skills(agent_id: str, skill_ids: list[str]) -> list[dict[str, Any]]:
    known = {skill["id"] for skill in scan_skills()}
    clean = []
    for skill_id in skill_ids:
        sid = _slug(skill_id)
        if sid in known and sid not in clean:
            clean.append(sid)
    bindings = _read_bindings()
    bindings["agent_skills"][agent_id] = clean
    _write_bindings(bindings)
    return get_agent_skills(agent_id)


def skill_summary_by_agent() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for skill in scan_skills():
        for agent_id in skill.get("assigned_agents", []):
            row = result.setdefault(agent_id, {"total": 0, "skills": [], "issues": 0})
            row["total"] += 1
            row["skills"].append({
                "id": skill["id"],
                "name": skill["name"],
                "category": skill["category"],
                "status": skill["status"],
            })
            if skill["status"] != "available":
                row["issues"] += 1
    return result
