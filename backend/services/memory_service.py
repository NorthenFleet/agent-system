"""智能体记忆库 — 文件系统扫描与搜索服务（只读）"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

# ── 配置 ──

OPENCLAW_ROOT = Path.home() / ".openclaw" / "workspace" / "agents"

AGENT_NAMES: dict[str, str] = {
    "main": "Main",
    "optimus": "擎天柱",
    "bumblebee": "大黄蜂",
    "perceptor": "感知器",
    "wheeljack": "千斤顶",
    "shockwave": "震荡波",
    "leonardo": "李奥纳多",
    "raphael": "拉斐尔",
    "donatello": "多纳泰罗",
    "michelangelo": "米开朗基罗",
    "ultra-magnus": "通天晓",
    "ironhide": "铁皮",
    "ratchet": "救护车",
    "soundwave": "声波",
    "jazz": "爵士",
    "inspector": "巡检员",
}

ALL_AGENT_IDS = list(AGENT_NAMES.keys())

SUPPORTED_TEXT_EXT = {".md", ".txt", ".markdown", ".json", ".yaml", ".yml"}

# 搜索时跳过的大文件阈值（字节）
SEARCH_SKIP_LARGE = 200_000


def _get_memory_dir(agent_id: str) -> Path:
    """获取指定智能体的 memory 目录绝对路径。"""
    return OPENCLAW_ROOT / agent_id / "workspace" / "memory"


def _safe_rel_path(path_str: str) -> str:
    """校验相对路径，拒绝目录穿越。"""
    if ".." in path_str:
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if path_str.startswith("/"):
        raise HTTPException(status_code=403, detail="Absolute paths not allowed")
    return path_str


def _guess_mime(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".md" or ext == ".markdown":
        return "text/markdown"
    if ext == ".txt":
        return "text/plain"
    if ext == ".json":
        return "application/json"
    if ext in {".yaml", ".yml"}:
        return "text/yaml"
    return "application/octet-stream"


def _is_text_file(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED_TEXT_EXT


def _format_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


# ── API 1: 列出智能体 ──────────────────────────────────────────

def list_agents() -> dict:
    """扫描所有智能体，返回记忆统计。"""
    agents = []
    total_files = 0

    for agent_id in ALL_AGENT_IDS:
        mem = _get_memory_dir(agent_id)
        if not mem.is_dir():
            agents.append({
                "id": agent_id,
                "name": AGENT_NAMES.get(agent_id, agent_id),
                "file_count": 0,
                "total_bytes": 0,
                "last_modified": None,
                "directories": [],
            })
            continue

        file_count = 0
        total_bytes = 0
        last_mtime = 0.0
        dirs: set[str] = set()

        for root, dirnames, filenames in os.walk(mem):
            for d in dirnames:
                dirs.add(d)
            for f in filenames:
                if f.startswith("."):
                    continue
                fp = Path(root) / f
                try:
                    st = fp.stat()
                    file_count += 1
                    total_bytes += st.st_size
                    if st.st_mtime > last_mtime:
                        last_mtime = st.st_mtime
                except OSError:
                    continue

        total_files += file_count
        agents.append({
            "id": agent_id,
            "name": AGENT_NAMES.get(agent_id, agent_id),
            "file_count": file_count,
            "total_bytes": total_bytes,
            "last_modified": _format_mtime(last_mtime) if last_mtime else None,
            "directories": sorted(dirs),
        })

    # 按 id 排序，main 优先
    agents.sort(key=lambda a: (0 if a["id"] == "main" else 1, a["id"]))

    return {
        "agents": agents,
        "total_agents": len(ALL_AGENT_IDS),
        "total_files": total_files,
        "scanned_at": _format_mtime(time.time()),
    }


# ── API 2: 文件树 ─────────────────────────────────────────────

def _build_tree(dir_path: Path, root: Path) -> list[dict]:
    """递归构建目录树节点列表。"""
    nodes: list[dict] = []
    try:
        items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (PermissionError, OSError):
        return nodes

    for item in items:
        if item.name.startswith("."):
            continue
        if item.is_dir():
            children = _build_tree(item, root)
            nodes.append({
                "name": item.name,
                "type": "directory",
                "children": children,
            })
        else:
            if not _is_text_file(item.name):
                continue
            try:
                st = item.stat()
            except OSError:
                continue
            nodes.append({
                "name": item.name,
                "type": "file",
                "size": st.st_size,
                "mtime": st.st_mtime,
                "mime_type": _guess_mime(item.name),
            })
    return nodes


def get_file_tree(agent_id: str, rel_path: str = "") -> dict:
    """返回指定智能体的记忆文件树。"""
    if agent_id not in ALL_AGENT_IDS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    mem = _get_memory_dir(agent_id)
    if not mem.is_dir():
        return {"agent_id": agent_id, "path": rel_path, "tree": []}

    _safe_rel_path(rel_path)

    target = mem / rel_path if rel_path else mem
    target = target.resolve()
    if not str(target).startswith(str(mem.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    tree = _build_tree(target, mem)
    return {"agent_id": agent_id, "path": rel_path, "tree": tree}


# ── API 3: 读取文件 ────────────────────────────────────────────

def read_file(agent_id: str, rel_path: str) -> dict:
    """读取指定智能体的记忆文件内容。"""
    if agent_id not in ALL_AGENT_IDS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    _safe_rel_path(rel_path)

    mem = _get_memory_dir(agent_id)
    if not mem.is_dir():
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' has no memory directory")

    target = (mem / rel_path).resolve()
    if not str(target).startswith(str(mem.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not _is_text_file(target.name):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {target.suffix}. Supported: {', '.join(sorted(SUPPORTED_TEXT_EXT))}",
        )

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    st = target.stat()
    return {
        "agent_id": agent_id,
        "path": rel_path,
        "name": target.name,
        "content": content,
        "size": st.st_size,
        "mime_type": _guess_mime(target.name),
        "mtime": _format_mtime(st.st_mtime),
    }


# ── API 4: 跨智能体搜索 ────────────────────────────────────────

def search_memory(q: str, agent_id: str | None = None, limit: int = 50) -> dict:
    """跨智能体 BM25 风格关键词搜索。"""
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    start = time.time()

    # 分词：中文按字符 ngram，英文按空格
    tokens = re.findall(r'[a-zA-Z]{2,}|[\u4e00-\u9fff]', q)
    if not tokens:
        tokens = list(q.strip())

    targets = [agent_id] if agent_id else ALL_AGENT_IDS
    results: list[dict] = []
    searched_agents = 0
    searched_files = 0

    for aid in targets:
        if aid not in ALL_AGENT_IDS:
            continue
        mem = _get_memory_dir(aid)
        if not mem.is_dir():
            searched_agents += 1
            continue

        searched_agents += 1

        for root, _, filenames in os.walk(mem):
            for fname in filenames:
                if not fname.endswith(".md") or fname.startswith("."):
                    continue
                fpath = Path(root) / fname
                rel = str(fpath.relative_to(mem))

                try:
                    st = fpath.stat()
                except OSError:
                    continue

                if st.st_size > SEARCH_SKIP_LARGE:
                    continue

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                searched_files += 1
                lines = content.splitlines()
                matched_lines: list[dict] = []

                for i, line in enumerate(lines, 1):
                    if any(t in line for t in tokens):
                        matched_lines.append({"line": i, "text": line.strip()})
                        if len(matched_lines) >= 3:
                            break

                if matched_lines:
                    score = len(matched_lines) / max(len(lines), 1)
                    snippet = matched_lines[0]["text"]
                    results.append({
                        "agent_id": aid,
                        "path": rel,
                        "name": fname,
                        "matched_lines": matched_lines,
                        "context_snippet": snippet[:200],
                        "score": round(score, 4),
                        "size": st.st_size,
                        "mtime": _format_mtime(st.st_mtime),
                    })

    results.sort(key=lambda r: r["score"], reverse=True)
    total = len(results)
    results = results[:limit]
    elapsed = (time.time() - start) * 1000

    return {
        "query": q,
        "total_matches": total,
        "results": results,
        "searched_agents": searched_agents,
        "searched_files": searched_files,
        "elapsed_ms": round(elapsed, 1),
        "truncated": total > limit,
    }


# ── API 5: 统计 ────────────────────────────────────────────────

def get_stats() -> dict:
    """记忆库聚合统计。"""
    total_files = 0
    total_bytes = 0
    active_agents = 0
    by_directory: dict[str, dict[str, int]] = {}

    agents_file_counts: list[dict] = []

    for agent_id in ALL_AGENT_IDS:
        mem = _get_memory_dir(agent_id)
        if not mem.is_dir():
            agents_file_counts.append({"id": agent_id, "files": 0})
            continue

        agent_files = 0
        agent_bytes = 0

        for root, dirnames, filenames in os.walk(mem):
            rel_dir = str(Path(root).relative_to(mem))
            for f in filenames:
                if f.startswith("."):
                    continue
                fp = Path(root) / f
                try:
                    sz = fp.stat().st_size
                except OSError:
                    continue
                agent_files += 1
                agent_bytes += sz
                total_files += 1
                total_bytes += sz

                dir_key = rel_dir if rel_dir != "." else "根目录"
                if dir_key not in by_directory:
                    by_directory[dir_key] = {"files": 0, "bytes": 0}
                by_directory[dir_key]["files"] += 1
                by_directory[dir_key]["bytes"] += sz

        if agent_files > 0:
            active_agents += 1
        agents_file_counts.append({"id": agent_id, "files": agent_files})

    # Top agents by file count
    agents_file_counts.sort(key=lambda x: x["files"], reverse=True)
    top_agents = agents_file_counts[:10]

    return {
        "total_agents": len(ALL_AGENT_IDS),
        "active_agents": active_agents,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "by_directory": dict(sorted(by_directory.items())),
        "top_agents_by_files": top_agents,
        "scanned_at": _format_mtime(time.time()),
    }
