"""
Knowledge graph service for the Obsidian vault-backed dashboard.

The first implementation intentionally serves the existing graph-index.json
artifact instead of rebuilding the graph on every request.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_VAULT_PATH = "~/工作桌面/knowledge"
DEFAULT_INDEX_RELATIVE_PATH = "14-映射库-Maps/graph-index.json"
DEFAULT_CONCEPT_MOC_RELATIVE_PATH = "03-概念库-Concepts/MOC-概念总索引.md"
TREE_SKIP_NAMES = {
    ".agents",
    ".claude",
    ".cursor",
    ".git",
    ".obsidian",
    ".smart-env",
    ".smtcmp_json_db",
    ".stfolder",
    ".trae",
    ".uploads",
    ".vault-meta",
    "__pycache__",
    "node_modules",
}
TREE_FILE_EXTENSIONS = {".md", ".markdown", ".pdf", ".docx", ".xlsx", ".csv", ".json"}


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

    def directory_tree(
        self,
        max_depth: int = 4,
        include_files: bool = True,
        max_entries: int = 1200,
    ) -> dict[str, Any]:
        root = self.vault_path
        if not root.exists() or not root.is_dir():
            return {
                "available": False,
                "vault_path": str(root),
                "root": self._tree_node(root, root, "directory", children=[]),
                "total_files": 0,
                "total_directories": 0,
                "truncated": False,
                "max_depth": max_depth,
            }

        indexed_nodes = self._indexed_nodes_by_relative_path()
        counters = {"entries": 0, "files": 0, "directories": 0}
        tree = self._build_tree_node(
            root,
            root,
            depth=0,
            max_depth=max_depth,
            include_files=include_files,
            max_entries=max_entries,
            counters=counters,
            indexed_nodes=indexed_nodes,
        )
        return {
            "available": True,
            "vault_path": str(root),
            "root": tree,
            "total_files": counters["files"],
            "total_directories": counters["directories"],
            "truncated": counters["entries"] >= max_entries,
            "max_depth": max_depth,
        }

    def list_nodes(
        self,
        node_type: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        nodes = self._all_nodes(include_concept_files=True)
        if node_type:
            nodes = [n for n in nodes if n.get("type") == node_type]
        if q:
            query = q.lower()
            nodes = [n for n in nodes if self._node_matches(n, query)]
        total = len(nodes)
        return {"nodes": nodes[offset : offset + limit], "total": total, "limit": limit, "offset": offset}

    def get_node(self, node_id: str) -> Optional[dict[str, Any]]:
        for node in self._all_nodes(include_concept_files=True):
            if node.get("id") == node_id or node.get("title") == node_id:
                return node
        return None

    def search(self, q: str, limit: int = 20, node_type: str | None = None) -> dict[str, Any]:
        query = (q or "").strip().lower()
        if not query:
            return {"query": q, "nodes": [], "total": 0}
        nodes = self._all_nodes(include_concept_files=True)
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

    def graph(
        self,
        limit_edges: int = 500,
        node_type: str | None = None,
        mode: str = "concept_backbone",
    ) -> dict[str, Any]:
        if mode == "concept_backbone":
            return self.concept_backbone_graph(limit_edges=limit_edges, node_type=node_type)

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
            "mode": "full",
            "stats": self.get_stats(),
            "nodes": nodes,
            "relations": relations[:limit_edges],
            "total_relations": len(relations),
            "limit_edges": limit_edges,
        }

    def concept_backbone_graph(self, limit_edges: int = 500, node_type: str | None = None) -> dict[str, Any]:
        index = self.load_index()
        all_nodes = self._all_nodes(include_concept_files=True)
        nodes_by_id = {node["id"]: node for node in all_nodes}
        lookup = self._node_lookup(all_nodes)
        moc_text = self._read_concept_moc()
        concept_ids, concept_domains = self._extract_moc_concepts(moc_text, lookup)

        for node in all_nodes:
            if self._is_concept_node(node):
                concept_ids.add(node["id"])

        backbone_nodes: dict[str, dict[str, Any]] = {}
        for node_id in concept_ids:
            node = nodes_by_id.get(node_id)
            if not node or not self._is_concept_node(node):
                continue
            backbone_nodes[node_id] = {
                **node,
                "backbone": True,
                "layer": "concept",
                "domain": concept_domains.get(node_id, ""),
            }

        relations = []
        for relation in index.get("relations", []):
            source = relation.get("source")
            target = relation.get("target")
            if source in backbone_nodes and target in backbone_nodes:
                relations.append({**relation, "backbone": True})

        relations.extend(self._extract_moc_relations(moc_text, lookup, set(backbone_nodes)))

        attached_nodes: dict[str, dict[str, Any]] = {}
        attachment_types = {"项目", "文献", "成果", "规范", "模型", "工具", "论文", "教学", "映射", "文档"}
        max_attached = 260
        for relation in index.get("relations", []):
            source = relation.get("source")
            target = relation.get("target")
            if source in backbone_nodes and target not in backbone_nodes:
                concept_id, attached_id = source, target
            elif target in backbone_nodes and source not in backbone_nodes:
                concept_id, attached_id = target, source
            else:
                continue

            attached = nodes_by_id.get(attached_id)
            if not attached or attached.get("type") not in attachment_types:
                continue
            if node_type and node_type != "概念" and attached.get("type") != node_type:
                continue
            if len(attached_nodes) >= max_attached and attached_id not in attached_nodes:
                continue

            attached_nodes[attached_id] = {**attached, "backbone": False, "layer": "attachment"}
            relations.append(
                {
                    **relation,
                    "source": concept_id if source == concept_id else source,
                    "target": attached_id if target == attached_id else target,
                    "backbone": False,
                }
            )

        nodes = list(backbone_nodes.values())
        if node_type and node_type != "概念":
            nodes.extend(attached_nodes.values())
        elif not node_type:
            nodes.extend(attached_nodes.values())

        allowed = {node["id"] for node in nodes}
        relations = [
            relation
            for relation in self._dedupe_relations(relations)
            if relation.get("source") in allowed and relation.get("target") in allowed
        ]
        stats = self._graph_stats(nodes, relations)
        stats.update(
            {
                "build_time": index.get("build_time"),
                "vault_path": str(self.vault_path),
                "index_path": str(self.index_path),
                "concept_moc_path": str(self._concept_moc_path()),
                "available": self.index_path.exists(),
                "concept_count": len(backbone_nodes),
                "attached_count": len(attached_nodes) if node_type != "概念" else 0,
                "source_stats": self.get_stats(),
            }
        )
        return {
            "mode": "concept_backbone",
            "stats": stats,
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

    def _all_nodes(self, include_concept_files: bool = False) -> list[dict[str, Any]]:
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
        if include_concept_files:
            for node in self._concept_file_nodes():
                existing = nodes_by_id.get(node["id"])
                if existing:
                    existing.update({key: value for key, value in node.items() if value})
                else:
                    nodes_by_id[node["id"]] = node
        return list(nodes_by_id.values())

    def _indexed_nodes_by_relative_path(self) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for node in self._all_nodes(include_concept_files=True):
            candidates = [str(node.get("id") or ""), str(node.get("path") or "")]
            for candidate in candidates:
                if not candidate:
                    continue
                path = Path(os.path.expanduser(candidate))
                try:
                    if path.is_absolute():
                        relative = path.resolve().relative_to(self.vault_path.resolve())
                    else:
                        relative = path
                except (OSError, ValueError):
                    continue
                key = relative.as_posix()
                mapping[key] = node
                if not key.endswith(".md"):
                    mapping[f"{key}.md"] = node
        return mapping

    def _build_tree_node(
        self,
        path: Path,
        root: Path,
        depth: int,
        max_depth: int,
        include_files: bool,
        max_entries: int,
        counters: dict[str, int],
        indexed_nodes: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        children = []
        file_count = 0
        dir_count = 0
        if depth < max_depth and counters["entries"] < max_entries:
            for child in self._iter_tree_children(path, include_files):
                if counters["entries"] >= max_entries:
                    break
                counters["entries"] += 1
                if child.is_dir():
                    counters["directories"] += 1
                    dir_count += 1
                    children.append(
                        self._build_tree_node(
                            child,
                            root,
                            depth + 1,
                            max_depth,
                            include_files,
                            max_entries,
                            counters,
                            indexed_nodes,
                        )
                    )
                elif include_files and child.is_file():
                    counters["files"] += 1
                    file_count += 1
                    relative = self._safe_relative(child, root)
                    node = indexed_nodes.get(relative)
                    children.append(
                        self._tree_node(
                            child,
                            root,
                            "file",
                            extension=child.suffix.lower(),
                            node_id=node.get("id") if node else None,
                            node_type_name=node.get("type") if node else None,
                            children=[],
                        )
                    )
        node = self._tree_node(path, root, "directory", children=children)
        node["file_count"] = file_count + sum(int(item.get("file_count", 0)) for item in children)
        node["dir_count"] = dir_count + sum(int(item.get("dir_count", 0)) for item in children)
        return node

    def _iter_tree_children(self, path: Path, include_files: bool) -> list[Path]:
        try:
            children = list(path.iterdir())
        except OSError:
            return []
        visible = []
        for child in children:
            if child.name.startswith(".") or child.name in TREE_SKIP_NAMES:
                continue
            if child.is_dir():
                visible.append(child)
            elif include_files and child.suffix.lower() in TREE_FILE_EXTENSIONS:
                visible.append(child)
        return sorted(visible, key=lambda item: (not item.is_dir(), item.name.lower()))

    def _tree_node(
        self,
        path: Path,
        root: Path,
        kind: str,
        children: list[dict[str, Any]] | None = None,
        extension: str | None = None,
        node_id: str | None = None,
        node_type_name: str | None = None,
    ) -> dict[str, Any]:
        relative = self._safe_relative(path, root)
        node: dict[str, Any] = {
            "id": relative or "__root__",
            "name": path.name or "知识库",
            "path": str(path),
            "relative_path": relative,
            "type": kind,
        }
        if children is not None:
            node["children"] = children
        if extension:
            node["extension"] = extension
        if node_id:
            node["node_id"] = node_id
        if node_type_name:
            node["node_type"] = node_type_name
        return node

    def _safe_relative(self, path: Path, root: Path) -> str:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return ""

    def _concept_moc_path(self) -> Path:
        return self.vault_path / DEFAULT_CONCEPT_MOC_RELATIVE_PATH

    def _is_concept_node(self, node: dict[str, Any]) -> bool:
        return node.get("type") == "概念" or str(node.get("id", "")).startswith("03-概念库-Concepts/")

    def _concept_dir(self) -> Path:
        return self.vault_path / "03-概念库-Concepts"

    def _concept_file_nodes(self) -> list[dict[str, Any]]:
        concept_dir = self._concept_dir()
        if not concept_dir.exists():
            return []
        nodes = []
        for path in sorted(concept_dir.rglob("*.md")):
            if path.name.startswith(".") or path.stem.lower() in {"readme", "index"} or path.name.startswith("MOC-"):
                continue
            try:
                node_id = str(path.relative_to(self.vault_path))
            except ValueError:
                node_id = str(path)
            nodes.append({"id": node_id, "title": path.stem, "type": "概念", "path": str(path)})
        return nodes

    def _read_concept_moc(self) -> str:
        try:
            return self._concept_moc_path().read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _node_lookup(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for node in nodes:
            node_id = str(node.get("id") or "")
            title = str(node.get("title") or "")
            path = str(node.get("path") or "")
            is_concept = node.get("type") == "概念" or node_id.startswith("03-概念库-Concepts/")
            candidates = {
                node_id,
                title,
                Path(node_id).stem,
                Path(path).stem,
                node_id.removesuffix(".md"),
                title.removesuffix(".md"),
            }
            for candidate in candidates:
                normalized = self._normalize_key(candidate)
                if normalized and (normalized not in lookup or is_concept):
                    lookup[normalized] = node_id
        return lookup

    def _normalize_key(self, value: str) -> str:
        return value.strip().strip("#").strip("/").removesuffix(".md").lower()

    def _resolve_node_id(self, raw_name: str, lookup: dict[str, str]) -> str | None:
        name = raw_name.split("|", 1)[0].strip()
        name = re.sub(r"[#^].*$", "", name).strip()
        if not name:
            return None
        direct = lookup.get(self._normalize_key(name))
        if direct:
            return direct
        return lookup.get(self._normalize_key(Path(name).stem))

    def _extract_moc_concepts(
        self,
        moc_text: str,
        lookup: dict[str, str],
    ) -> tuple[set[str], dict[str, str]]:
        concept_ids: set[str] = set()
        domains: dict[str, str] = {}
        current_domain = ""
        for line in moc_text.splitlines():
            heading = re.match(r"^##+\s+(?:[一二三四五六七八九十]+[、.]\s*)?(.*)$", line.strip())
            if heading:
                current_domain = heading.group(1).strip()
                continue
            for raw_link in re.findall(r"\[\[([^\]]+)\]\]", line):
                if current_domain in {"概念关系速查", "子目录索引"}:
                    continue
                node_id = self._resolve_node_id(raw_link, lookup)
                if not node_id:
                    continue
                concept_ids.add(node_id)
                if current_domain:
                    domains[node_id] = current_domain
        return concept_ids, domains

    def _extract_moc_relations(
        self,
        moc_text: str,
        lookup: dict[str, str],
        concept_ids: set[str],
    ) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        blocks = re.findall(r"```(.*?)```", moc_text, flags=re.S)
        if not blocks:
            return relations

        anchors_by_indent: dict[int, str] = {}
        for raw_line in blocks[-1].splitlines():
            if not raw_line.strip():
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line_concepts = [
                node_id for node_id in self._line_concepts(raw_line, lookup, concept_ids) if node_id in concept_ids
            ]
            if not line_concepts:
                continue

            parent = self._nearest_anchor(anchors_by_indent, indent)
            relation_name = "概念耦合" if "↔" in raw_line else "概念骨干"
            if parent and parent != line_concepts[0]:
                relations.append({"source": parent, "target": line_concepts[0], "relation": relation_name, "weight": 2, "backbone": True})
            for source, target in zip(line_concepts, line_concepts[1:]):
                if source != target:
                    relations.append({"source": source, "target": target, "relation": relation_name, "weight": 2, "backbone": True})

            anchors_by_indent[indent] = line_concepts[-1]
            for child_indent in [key for key in anchors_by_indent if key > indent]:
                anchors_by_indent.pop(child_indent, None)
        return relations

    def _line_concepts(
        self,
        line: str,
        lookup: dict[str, str],
        concept_ids: set[str],
    ) -> list[str]:
        matches: list[tuple[int, str]] = []
        for key, node_id in lookup.items():
            if node_id not in concept_ids or len(key) < 2:
                continue
            pos = line.lower().find(key)
            if pos >= 0:
                matches.append((pos, node_id))
        ordered: list[str] = []
        for _, node_id in sorted(matches, key=lambda item: item[0]):
            if node_id not in ordered:
                ordered.append(node_id)
        return ordered

    def _nearest_anchor(self, anchors_by_indent: dict[int, str], indent: int) -> str | None:
        lower_indents = [key for key in anchors_by_indent if key < indent]
        if not lower_indents:
            return None
        return anchors_by_indent[max(lower_indents)]

    def _dedupe_relations(self, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        unique = []
        for relation in relations:
            source = str(relation.get("source") or "")
            target = str(relation.get("target") or "")
            name = str(relation.get("relation") or relation.get("type") or "关联")
            key = (source, target, name)
            if not source or not target or source == target or key in seen:
                continue
            seen.add(key)
            unique.append(relation)
        return unique

    def _graph_stats(self, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, Any]:
        entity_types: dict[str, int] = {}
        for node in nodes:
            node_type = str(node.get("type") or "知识")
            entity_types[node_type] = entity_types.get(node_type, 0) + 1
        return {"nodes": len(nodes), "edges": len(relations), "entity_types": entity_types}

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
