"""
Knowledge graph service for the Obsidian vault-backed dashboard.

The first implementation intentionally serves the existing graph-index.json
artifact instead of rebuilding the graph on every request.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_VAULT_PATH = "~/工作桌面/knowledge"
DEFAULT_INDEX_RELATIVE_PATH = "14-映射库-Maps/graph-index.json"


@dataclass
class _Cache:
    mtime: float = -1
    data: Optional[dict[str, Any]] = None


class KnowledgeManager:
    def __init__(self, vault_path: str | None = None, index_path: str | None = None):
        self.vault_path = Path(
            os.path.expanduser(vault_path or os.getenv("KNOWLEDGE_VAULT_PATH", DEFAULT_VAULT_PATH))
        )
        configured_index = index_path or os.getenv("KNOWLEDGE_GRAPH_INDEX")
        self.index_path = (
            Path(os.path.expanduser(configured_index))
            if configured_index
            else self.vault_path / DEFAULT_INDEX_RELATIVE_PATH
        )
        self._cache = _Cache()

    def configure(self, vault_path: str | None = None, index_path: str | None = None) -> None:
        if vault_path is not None:
            self.vault_path = Path(os.path.expanduser(vault_path))
        if index_path is not None:
            self.index_path = Path(os.path.expanduser(index_path))
        self._cache = _Cache()

    def load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._empty_index()
        mtime = self.index_path.stat().st_mtime
        if self._cache.data is not None and self._cache.mtime == mtime:
            return self._cache.data
        with self.index_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("stats", {})
        data.setdefault("entities", {})
        data.setdefault("relations", [])
        data.setdefault("top_concepts", [])
        self._cache = _Cache(mtime=mtime, data=data)
        return data

    def _empty_index(self) -> dict[str, Any]:
        return {
            "build_time": None,
            "stats": {"nodes": 0, "edges": 0, "entity_types": {}},
            "entities": {},
            "relations": [],
            "top_concepts": [],
        }

    def get_stats(self) -> dict[str, Any]:
        index = self.load_index()
        stats = dict(index.get("stats") or {})
        stats["build_time"] = index.get("build_time")
        stats["vault_path"] = str(self.vault_path)
        stats["index_path"] = str(self.index_path)
        stats["available"] = self.index_path.exists()
        return stats

    def list_nodes(
        self,
        node_type: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        nodes = self._all_nodes()
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
        if q:
            query = q.lower()
            nodes = [n for n in nodes if self._node_matches(n, query)]
        total = len(nodes)
        return {"nodes": nodes[offset : offset + limit], "total": total, "limit": limit, "offset": offset}

    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        for node in self._all_nodes():
            if node.get("id") == node_id or node.get("title") == node_id:
                return node
        return None

    def search(self, q: str, limit: int = 20, node_type: str | None = None) -> dict[str, Any]:
        query = (q or "").strip().lower()
        if not query:
            return {"query": q, "nodes": [], "total": 0}
        nodes = self._all_nodes()
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
        ranked = []
        for node in nodes:
            score = self._score_node(node, query)
            if score > 0:
                ranked.append({**node, "score": score})
        ranked.sort(key=lambda n: (-n["score"], n.get("title", "")))
        return {"query": q, "nodes": ranked[:limit], "total": len(ranked)}

    def neighbors(self, node_id: str, limit: int = 50) -> dict[str, Any]:
        index = self.load_index()
        node = self.get_node(node_id) or {"id": node_id, "title": node_id, "type": "引用", "path": ""}
        relations = []
        neighbor_ids: set[str] = set()
        for relation in index.get("relations", []):
            source = relation.get("source")
            target = relation.get("target")
            if source == node_id or target == node_id:
                relations.append(relation)
                neighbor_ids.add(target if source == node_id else source)
            if len(relations) >= limit:
                break
        neighbors = [
            self.get_node(nid) or {"id": nid, "title": nid, "type": "引用", "path": ""}
            for nid in neighbor_ids
        ]
        return {"node": node, "neighbors": neighbors, "relations": relations, "total": len(relations)}

    def node_content(self, node_id: str, max_chars: int = 6000) -> dict[str, Any]:
        node = self.get_node(node_id)
        if not node:
            return {"node": {"id": node_id, "title": node_id, "type": "引用", "path": ""}, "content": "", "excerpt": "", "available": False}
        raw_path = str(node.get("path") or "")
        candidates = []
        if raw_path:
            candidates.append(Path(raw_path))
        if node.get("id"):
            candidates.append(self.vault_path / str(node.get("id")))
        if node.get("title"):
            candidates.append(self.vault_path / f"{node.get('title')}.md")

        file_path = None
        vault_root = self.vault_path.resolve()
        for candidate in candidates:
            expanded = Path(os.path.expanduser(str(candidate)))
            if not expanded.is_absolute():
                expanded = self.vault_path / expanded
            try:
                resolved = expanded.resolve()
                if vault_root in resolved.parents or resolved == vault_root:
                    if resolved.exists() and resolved.is_file():
                        file_path = resolved
                        break
            except OSError:
                continue

        if not file_path:
            return {"node": node, "content": "", "excerpt": "", "available": False}

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except OSError:
            return {"node": node, "content": "", "excerpt": "", "available": False}

        excerpt = self._markdown_excerpt(content)
        return {
            "node": node,
            "content": content,
            "excerpt": excerpt,
            "path": str(file_path),
            "available": True,
        }

    def _markdown_excerpt(self, content: str, max_len: int = 420) -> str:
        lines = content.splitlines()
        if lines and lines[0].strip() == "---":
            for idx in range(1, min(len(lines), 80)):
                if lines[idx].strip() == "---":
                    lines = lines[idx + 1 :]
                    break
        cleaned = []
        for line in lines:
            item = line.strip()
            if not item or item.startswith("!") or item.startswith("# "):
                continue
            if item.startswith("#"):
                item = item.lstrip("#").strip()
            cleaned.append(item)
            if len(" ".join(cleaned)) >= max_len:
                break
        excerpt = " ".join(cleaned)
        return excerpt[:max_len].strip()

    def graph(self, limit_edges: int = 500, node_type: str | None = None) -> dict[str, Any]:
        index = self.load_index()
        nodes = self._all_nodes()
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
            allowed = {n["id"] for n in nodes}
            relations = [
                r for r in index.get("relations", []) if r.get("source") in allowed and r.get("target") in allowed
            ]
        else:
            relations = list(index.get("relations", []))
        return {
            "stats": self.get_stats(),
            "nodes": nodes,
            "relations": relations[:limit_edges],
            "total_relations": len(relations),
            "limit_edges": limit_edges,
        }

    def project_context(self, project: dict[str, Any], limit: int = 12) -> dict[str, Any]:
        keywords = self._project_keywords(project)
        linked_nodes = self._collect_explicit_links(project)
        suggestions = []
        seen = {n.get("id") for n in linked_nodes}
        for keyword in keywords:
            for node in self.search(keyword, limit=5).get("nodes", []):
                if node.get("id") in seen:
                    continue
                suggestions.append({**node, "matched_keyword": keyword})
                seen.add(node.get("id"))
                if len(suggestions) >= limit:
                    break
            if len(suggestions) >= limit:
                break
        return {
            "project_id": project.get("id"),
            "project_name": project.get("name"),
            "matched_keywords": keywords,
            "linked_nodes": linked_nodes,
            "suggested_nodes": suggestions,
            "stats": self.get_stats(),
        }

    def _all_nodes(self) -> list[dict[str, Any]]:
        index = self.load_index()
        nodes_by_id: dict[str, dict[str, Any]] = {}
        for title, entity in (index.get("entities") or {}).items():
            node_id = entity.get("id") or title
            nodes_by_id[node_id] = {
                "id": node_id,
                "title": title,
                "type": entity.get("type", "文档"),
                "path": entity.get("path", ""),
            }
        for relation in index.get("relations", []):
            for key in ("source", "target"):
                node_id = relation.get(key)
                if node_id and node_id not in nodes_by_id:
                    nodes_by_id[node_id] = {
                        "id": node_id,
                        "title": node_id.removeprefix("_unlinked/"),
                        "type": "引用" if node_id.startswith("_unlinked/") else "文档",
                        "path": "",
                    }
        return list(nodes_by_id.values())

    def _node_matches(self, node: dict[str, Any], query: str) -> bool:
        haystack = " ".join(str(node.get(k, "")) for k in ("id", "title", "type", "path")).lower()
        return query in haystack

    def _score_node(self, node: dict[str, Any], query: str) -> int:
        title = str(node.get("title", "")).lower()
        node_id = str(node.get("id", "")).lower()
        path = str(node.get("path", "")).lower()
        node_type = str(node.get("type", "")).lower()
        if title == query or node_id == query:
            return 100
        score = 0
        if query in title:
            score += 60
        if query in node_id:
            score += 30
        if query in path:
            score += 10
        if query in node_type:
            score += 5
        return score

    def _project_keywords(self, project: dict[str, Any]) -> list[str]:
        values = [project.get("name", ""), project.get("description", ""), project.get("current_phase", "")]
        context = project.get("context") if isinstance(project.get("context"), dict) else {}
        values.extend(str(v) for v in context.values() if isinstance(v, (str, int, float)))
        for task in project.get("tasks", []) or []:
            values.extend([task.get("title", ""), task.get("description", "")])
            for criterion in task.get("acceptance_criteria", []) or []:
                values.append(str(criterion))
            task_context = task.get("context") if isinstance(task.get("context"), dict) else {}
            values.extend(str(v) for v in task_context.values() if isinstance(v, (str, int, float)))
            for point in task.get("development_points", []) or []:
                values.extend([point.get("title", ""), point.get("description", "")])
        keywords: list[str] = []
        for value in values:
            for token in self._split_keywords(str(value)):
                if token not in keywords:
                    keywords.append(token)
        return keywords[:20]

    def _split_keywords(self, text: str) -> list[str]:
        separators = "，。；：、,. ;:/|()（）[]【】\n\t"
        normalized = text
        for sep in separators:
            normalized = normalized.replace(sep, " ")
        raw = [part.strip() for part in normalized.split() if part.strip()]
        keywords = []
        for item in raw:
            if len(item) >= 2 and item.lower() not in {"api", "v3"}:
                keywords.append(item)
        return keywords[:8]

    def _collect_explicit_links(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        links = []
        for target_type, target_id, target_title, payload in self._iter_context_payloads(project):
            raw_links = payload.get("knowledge_links", [])
            if not isinstance(raw_links, list):
                continue
            for link in raw_links:
                if not isinstance(link, dict):
                    continue
                node_id = link.get("node_id") or link.get("id") or link.get("title")
                if not node_id:
                    continue
                node = self.get_node(node_id) or {
                    "id": node_id,
                    "title": link.get("title", node_id),
                    "type": "引用",
                    "path": "",
                }
                links.append(
                    {
                        **node,
                        "relation": link.get("relation", "related"),
                        "reason": link.get("reason", ""),
                        "confirmed_by": link.get("confirmed_by", ""),
                        "confirmed_at": link.get("confirmed_at", ""),
                        "target_type": target_type,
                        "target_id": target_id,
                        "target_title": target_title,
                    }
                )
        return links

    def _iter_context_payloads(self, project: dict[str, Any]):
        if isinstance(project.get("context"), dict):
            yield "project", project.get("id", ""), project.get("name", ""), project["context"]
        for task in project.get("tasks", []) or []:
            if isinstance(task.get("context"), dict):
                yield "task", task.get("id", ""), task.get("title", ""), task["context"]
            for point in task.get("development_points", []) or []:
                if isinstance(point.get("context"), dict):
                    yield "point", point.get("id", ""), point.get("title", ""), point["context"]


knowledge_manager = KnowledgeManager()
