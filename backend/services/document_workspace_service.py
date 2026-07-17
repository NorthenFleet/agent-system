"""Versioned Markdown workspace for long-form document projects."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_manager import knowledge_manager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", " "} else "-" for ch in value.strip())
    return cleaned.strip(" -") or "document-project"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
    return normalized or hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def _citation_numbers(text: str) -> list[int]:
    """Expand numeric citation groups such as [1, 3-5] without matching Markdown links."""
    numbers: list[int] = []
    for group in re.findall(r"\[([0-9０-９,，、;；\-–—\s]+)\](?!\()", text):
        normalized = group.translate(str.maketrans("０１２３４５６７８９，、；–—", "0123456789,,;--"))
        if re.search(r"(?:^|[,;\s])0(?:$|[,;\s])", normalized.strip()):
            continue
        for token in re.split(r"[,;\s]+", normalized.strip()):
            if not token:
                continue
            range_match = re.fullmatch(r"(\d+)-(\d+)", token)
            if range_match:
                start, end = map(int, range_match.groups())
                if 0 < start <= end <= start + 100:
                    numbers.extend(range(start, end + 1))
            elif token.isdigit() and int(token) > 0:
                numbers.append(int(token))
    return numbers


class DocumentWorkspaceError(RuntimeError):
    pass


class DocumentVersionConflict(DocumentWorkspaceError):
    pass


class DocumentWorkspaceService:
    def __init__(self) -> None:
        self.vault = knowledge_manager.vault_path.resolve()

    def _workspace_root(self, project: dict[str, Any]) -> Path:
        projects_root = self.vault / "06-项目库-Projects"
        project_name = _safe_name(str(project.get("name") or project.get("id")))
        project_id = _safe_name(str(project.get("id") or "document"))
        legacy_root = projects_root / project_name / "_workspace"
        legacy_manifest = legacy_root / "manifest.json"
        if legacy_manifest.exists():
            try:
                data = json.loads(legacy_manifest.read_text(encoding="utf-8"))
                if str(data.get("project_id") or "") == str(project.get("id") or ""):
                    return legacy_root
            except (OSError, json.JSONDecodeError):
                pass
        isolated_root = projects_root / f"{project_name}--{project_id}" / "_workspace"
        if isolated_root.exists():
            return isolated_root
        for manifest_path in projects_root.glob(f"*--{project_id}/_workspace/manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if str(data.get("project_id") or "") == str(project.get("id") or ""):
                    return manifest_path.parent
            except (OSError, json.JSONDecodeError):
                continue
        return isolated_root

    def _manifest_path(self, project: dict[str, Any]) -> Path:
        return self._workspace_root(project) / "manifest.json"

    def _lock_path(self, project: dict[str, Any]) -> Path:
        return self._workspace_root(project) / ".workspace.lock"

    def initialize_project(self, project: dict[str, Any], outline: list[str] | None = None) -> dict[str, Any]:
        """Create an isolated Markdown source for a new document project."""
        root = self._workspace_root(project)
        source = root / "source" / "document.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        chapters = [str(item).strip() for item in (outline or []) if str(item).strip()]
        if not chapters:
            chapters = ["第一章 背景与目标", "第二章 核心内容", "第三章 总结与后续工作"]
        if not source.exists():
            name = str(project.get("name") or "未命名文档")
            description = str(project.get("description") or "").strip()
            spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
            goal = str(spec.get("writing_goal") or "").strip()
            audience = str(spec.get("target_audience") or "").strip()
            lines = [
                "# 文档说明",
                "",
                f"**文档名称：** {name}",
                "",
                f"**文档简介：** {description or '待补充'}",
                "",
                f"**写作目标：** {goal or '待补充'}",
                "",
                f"**目标读者：** {audience or '待补充'}",
                "",
            ]
            for chapter in chapters:
                lines.extend([f"# {chapter}", "", "## 本章要点", "", "待撰写。", ""])
            lines.extend(["# 参考文献", "", "待补充。", ""])
            source.write_text("\n".join(lines), encoding="utf-8")
        return {
            "path": str(source.resolve()),
            "relative_path": _relative(source, self.vault),
            "status": "initialized",
            "generated_from": "document-project-create",
            "size_chars": source.stat().st_size,
            "chapter_count": len(chapters),
        }

    def _load_manifest(self, project: dict[str, Any]) -> dict[str, Any]:
        path = self._manifest_path(project)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DocumentWorkspaceError(f"文档工作空间清单损坏：{path}") from exc

    def _write_manifest(self, project: dict[str, Any], manifest: dict[str, Any]) -> None:
        path = self._manifest_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest["updated_at"] = _now()
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _candidate_score(self, path: Path, project: dict[str, Any]) -> int:
        text = str(path).lower()
        name = str(project.get("name") or "").lower()
        score = min(path.stat().st_size // 10_000, 50)
        if name and name in text:
            score += 40
        if "博士论文 -" in path.name:
            score += 100
        if "10-成果库-outputs" in text.lower():
            score += 30
        if "正式稿" in text:
            score += 12
        if "_workdraft" in text:
            score -= 20
        if any(token in text for token in ["参考文献", "总稿预览", "_pandoc_temp", "模板", "备份"]):
            score -= 80
        return int(score)

    def _find_source_markdown(self, project: dict[str, Any], manifest: dict[str, Any]) -> Path:
        spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
        configured = Path(str((spec.get("working_markdown") or {}).get("path") or ""))
        if configured.exists() and configured.is_file():
            return configured.resolve()
        existing = Path(str(manifest.get("source_markdown") or ""))
        if existing.exists() and existing.is_file():
            return existing.resolve()
        candidates = []
        outputs = self.vault / "10-成果库-Outputs"
        if outputs.exists():
            candidates.extend(path.resolve() for path in outputs.rglob("*.md") if path.is_file())
        candidates = list(dict.fromkeys(candidates))
        candidates.sort(key=lambda path: self._candidate_score(path, project), reverse=True)
        if not candidates or self._candidate_score(candidates[0], project) < 20:
            raise DocumentWorkspaceError("未找到可作为工作正文的完整 Markdown 文档")
        return candidates[0]

    def _find_source_word(self, project: dict[str, Any]) -> Path | None:
        spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
        configured = Path(str((spec.get("source_word") or {}).get("path") or ""))
        if configured.exists() and configured.is_file():
            return configured.resolve()
        candidates = []
        for path in self.vault.rglob("*.docx"):
            text = str(path).lower()
            if path.name.startswith("~$") or "_pandoc_temp" in text:
                continue
            score = 0
            if "博士论文" in text or "毕业论文" in text:
                score += 30
            if "已排版" in text:
                score += 30
            if "10章" in path.name:
                score += 120
            if "9章" in path.name:
                score -= 40
            if ".before-" in path.name or "before-" in path.name:
                score -= 50
            score += min(path.stat().st_size // 1_000_000, 20)
            candidates.append((score, path.resolve()))
        candidates.sort(key=lambda row: row[0], reverse=True)
        return candidates[0][1] if candidates and candidates[0][0] >= 30 else None

    def ensure_workspace(self, project: dict[str, Any]) -> dict[str, Any]:
        root = self._workspace_root(project)
        for name in ["working", "versions", "exports"]:
            (root / name).mkdir(parents=True, exist_ok=True)
        with self._lock_path(project).open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            manifest = self._load_manifest(project)
            source = self._find_source_markdown(project, manifest)
            working = root / "working" / "document.md"
            previous_source = Path(str(manifest.get("source_markdown") or ""))
            source_changed = bool(manifest) and previous_source.resolve() != source.resolve()
            version = max(int(manifest.get("version") or 1), 1)
            if source_changed and working.exists():
                backup = root / "versions" / f"v{version:04d}-before-source-switch.md"
                if not backup.exists():
                    shutil.copy2(working, backup)
                shutil.copy2(source, working)
                version += 1
            elif not working.exists():
                shutil.copy2(source, working)
            initial = root / "versions" / "v0001-import.md"
            if not initial.exists():
                shutil.copy2(working, initial)
            source_word = self._find_source_word(project)
            spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
            working_spec = spec.get("working_markdown") if isinstance(spec.get("working_markdown"), dict) else {}
            asset_base_value = str(spec.get("asset_base_dir") or working_spec.get("asset_base_dir") or "").strip()
            configured_asset_base = Path(asset_base_value) if asset_base_value else None
            source_base = configured_asset_base.resolve() if configured_asset_base and configured_asset_base.is_dir() else source.parent
            expected_chapters = max(int(spec.get("expected_chapters") or working_spec.get("chapter_count") or 10), 1)
            edition = str(spec.get("edition") or working_spec.get("edition") or "")
            markdown = working.read_text(encoding="utf-8", errors="replace")
            sections = self._parse_sections(markdown)
            manifest.update({
                "schema": "openclaw.document-workspace",
                "project_id": project.get("id"),
                "project_name": project.get("name"),
                "version": version,
                "edition": edition,
                "expected_chapters": expected_chapters,
                "source_markdown": str(source),
                "source_base_dir": str(source_base),
                "source_word": str(source_word) if source_word else "",
                "working_markdown": str(working),
                "created_at": manifest.get("created_at") or _now(),
                "stats": self._stats(markdown, sections),
            })
            self._write_manifest(project, manifest)
            return copy.deepcopy(manifest)

    def _section_kind(self, title: str) -> str:
        if re.search(r"第\s*(?:\d+|[一二三四五六七八九十百]+)\s*章", title):
            return "chapter"
        if "参考文献" in title:
            return "references"
        if "参数设定表" in title or "附录" in title:
            return "appendix"
        return "frontmatter"

    def _summary(self, content: str) -> str:
        for block in re.split(r"\n\s*\n", content):
            text = re.sub(r"[#>*`|\[\]()]", " ", block)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= 30 and not text.startswith("---"):
                return text[:220]
        return ""

    def _parse_sections(self, markdown: str) -> list[dict[str, Any]]:
        lines = markdown.splitlines()
        headings = []
        for index, line in enumerate(lines):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                headings.append({"line": index, "level": len(match.group(1)), "title": match.group(2).strip()})
        top = [heading for heading in headings if heading["level"] == 1]
        sections = []
        for index, heading in enumerate(top):
            start = heading["line"]
            end = top[index + 1]["line"] if index + 1 < len(top) else len(lines)
            content = "\n".join(lines[start:end]).strip() + "\n"
            outline = [
                {
                    "id": f"outline-{item['line'] + 1}",
                    "title": item["title"],
                    "level": item["level"],
                    "line": item["line"] + 1,
                    "anchor": _slug(item["title"]),
                }
                for item in headings
                if start < item["line"] < end and item["level"] <= 4
            ]
            title = heading["title"]
            section_id = f"section-{index + 1:02d}-{_slug(title)[:48]}"
            sections.append({
                "id": section_id,
                "title": title,
                "kind": self._section_kind(title),
                "order_index": index,
                "start_line": start + 1,
                "end_line": end,
                "summary": self._summary("\n".join(lines[start + 1:end])),
                "outline": outline,
                "word_count": len(re.sub(r"\s+", "", content)),
                "heading_count": 1 + len(outline),
                "image_count": len(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)),
                "citation_count": len(set(_citation_numbers(content))),
                "status": "draft" if len(content) < 1200 else "writing",
                "content": content,
            })
        return sections

    def _stats(self, markdown: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "size_chars": len(markdown),
            "word_count": len(re.sub(r"\s+", "", markdown)),
            "section_count": len(sections),
            "chapter_count": sum(1 for row in sections if row["kind"] == "chapter"),
            "heading_count": sum(row["heading_count"] for row in sections),
            "image_count": len(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown)),
            "formal_reference_count": len(re.findall(r"^\[(\d+)\]\s+.+$", markdown, flags=re.M)),
        }

    def _read(self, project: dict[str, Any]) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        manifest = self.ensure_workspace(project)
        markdown = Path(manifest["working_markdown"]).read_text(encoding="utf-8", errors="replace")
        return manifest, markdown, self._parse_sections(markdown)

    def workspace(self, project: dict[str, Any]) -> dict[str, Any]:
        manifest, markdown, sections = self._read(project)
        quality = self.quality(project, prepared=(manifest, markdown, sections))
        references = self.references(project, prepared=(manifest, markdown, sections))
        return {
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "description": project.get("description"),
                "status": project.get("status"),
                "progress": project.get("progress"),
                "owner_agent": project.get("owner_agent"),
                "document_spec": project.get("document_spec") or {},
            },
            "manifest": self._public_manifest(manifest),
            "stats": manifest["stats"],
            "sections": [{key: value for key, value in row.items() if key != "content"} for row in sections],
            "quality": quality["summary"],
            "reference_summary": references["summary"],
        }

    def _public_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            **manifest,
            "source_markdown": _relative(Path(manifest["source_markdown"]), self.vault),
            "source_word": _relative(Path(manifest["source_word"]), self.vault) if manifest.get("source_word") else "",
            "working_markdown": _relative(Path(manifest["working_markdown"]), self.vault),
        }

    def section(self, project: dict[str, Any], section_id: str) -> dict[str, Any]:
        manifest, _, sections = self._read(project)
        row = next((item for item in sections if item["id"] == section_id), None)
        if not row:
            raise DocumentWorkspaceError("章节不存在")
        return {
            **row,
            "version": manifest["version"],
            "asset_paths": list(dict.fromkeys(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", row["content"]))),
        }

    def fulltext(self, project: dict[str, Any]) -> dict[str, Any]:
        manifest, markdown, _ = self._read(project)
        return {
            "content": markdown,
            "version": manifest["version"],
            "asset_paths": list(dict.fromkeys(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown))),
        }

    def update_section(self, project: dict[str, Any], section_id: str, content: str, expected_version: int, actor: str) -> dict[str, Any]:
        updated_section: dict[str, Any] | None = None
        next_version = expected_version
        with self._lock_path(project).open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            manifest = self._load_manifest(project)
            current_version = int(manifest.get("version") or 1)
            if expected_version != current_version:
                raise DocumentVersionConflict(f"工作稿已更新，当前版本为 v{current_version}")
            working = Path(manifest["working_markdown"])
            markdown = working.read_text(encoding="utf-8", errors="replace")
            sections = self._parse_sections(markdown)
            row = next((item for item in sections if item["id"] == section_id), None)
            if not row:
                raise DocumentWorkspaceError("章节不存在")
            lines = markdown.splitlines()
            replacement = content.strip().splitlines()
            next_markdown = "\n".join(lines[:row["start_line"] - 1] + replacement + lines[row["end_line"]:]).strip() + "\n"
            version_path = self._workspace_root(project) / "versions" / f"v{current_version:04d}-before-{_safe_name(actor)}.md"
            if not version_path.exists():
                shutil.copy2(working, version_path)
            working.write_text(next_markdown, encoding="utf-8")
            next_sections = self._parse_sections(next_markdown)
            manifest["version"] = current_version + 1
            manifest["last_actor"] = actor
            manifest["stats"] = self._stats(next_markdown, next_sections)
            self._write_manifest(project, manifest)
            updated_section = next((item for item in next_sections if item["title"] == row["title"]), None)
            next_version = int(manifest["version"])
        if not updated_section:
            raise DocumentWorkspaceError("章节保存后无法重新定位")
        return {
            **updated_section,
            "version": next_version,
            "asset_paths": list(dict.fromkeys(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", updated_section["content"]))),
        }

    def references(self, project: dict[str, Any], prepared=None) -> dict[str, Any]:
        manifest, markdown, sections = prepared or self._read(project)
        formal = []
        body = markdown.split("# 参考文献", 1)[0]
        used_counts: dict[int, int] = {}
        for number in _citation_numbers(body):
            used_counts[number] = used_counts.get(number, 0) + 1
        section_usage: dict[int, list[dict[str, Any]]] = {}
        section_coverage = []
        for section in sections:
            if section["kind"] == "references":
                continue
            citations = _citation_numbers(section["content"])
            counts: dict[int, int] = {}
            for number in citations:
                counts[number] = counts.get(number, 0) + 1
            if counts:
                section_coverage.append({
                    "section_id": section["id"],
                    "title": section["title"],
                    "kind": section["kind"],
                    "unique_references": len(counts),
                    "citation_occurrences": sum(counts.values()),
                    "reference_numbers": sorted(counts),
                })
            for number, count in counts.items():
                section_usage.setdefault(number, []).append({
                    "section_id": section["id"],
                    "title": section["title"],
                    "kind": section["kind"],
                    "count": count,
                })
        for match in re.finditer(r"^\[(\d+)\]\s+(.+)$", markdown, flags=re.M):
            number = int(match.group(1))
            text = match.group(2).strip()
            year = next(iter(re.findall(r"(?:19|20)\d{2}", text)), "")
            type_match = re.search(r"\[([JMDCR]/?OL?|J|M|D|C|R)\]", text)
            locations = section_usage.get(number, [])
            formal.append({
                "id": f"ref-{number}",
                "number": number,
                "text": text,
                "year": year,
                "document_type": type_match.group(1) if type_match else "",
                "usage_count": used_counts.get(number, 0),
                "section_count": len(locations),
                "locations": locations,
                "status": "cited" if used_counts.get(number) else "uncited",
            })
        spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
        knowledge = []
        for index, item in enumerate(spec.get("references") or []):
            row = item if isinstance(item, dict) else {"title": str(item)}
            if row.get("source_type") in {"paper_citation", "formal"}:
                continue
            knowledge.append({"id": row.get("id") or f"knowledge-{index + 1}", **row})
        return {
            "formal": formal,
            "knowledge": knowledge,
            "section_coverage": section_coverage,
            "summary": {
                "formal": len(formal),
                "cited": sum(1 for row in formal if row["usage_count"]),
                "uncited": sum(1 for row in formal if not row["usage_count"]),
                "knowledge": len(knowledge),
                "in_text_citations": sum(used_counts.values()),
                "sections_with_citations": len(section_coverage),
            },
        }

    def _resolve_asset(self, manifest: dict[str, Any], raw_path: str) -> Path:
        raw = raw_path.strip().split("#", 1)[0]
        if raw.startswith(("http://", "https://", "data:")):
            raise DocumentWorkspaceError("外部资源不由本地文档服务代理")
        base = Path(manifest["source_base_dir"])
        formal_assets = base / "论文章节" / "正式稿" / "assets"
        aliases = {
            "fig1-1-overall-research-framework.jpg": "图1-1-海上无人集群智能协同任务规划总体研究框架.jpg",
            "fig1-2-technical-route.jpg": "图1-2-海上无人集群智能协同任务规划技术路线图.jpg",
            "ch4-advantage-dynamics-landscape-light.svg": "图2-1-优势动力学引擎与OODA闭环-旧版.svg",
            "作战构想.png": "图2-1-海上无人集群作战构想图.png",
            "ch3-info-control-loop-light.svg": "图3-1-海上无人集群作战体系统一信息流控制流闭环架构-旧版.svg",
            "ch3-system-architecture-light.svg": "图3-3-海上无人集群作战体系结构与多流耦合关系-旧版.svg",
            "ch3-planning-mechanism-landscape-light.svg": "图3-4-海上无人集群任务规划运行机制-旧版.svg",
            "4-1总体模型.png": "图4-1-总体模型-旧版.png",
            "ch4-task-attribute-structure-light.svg": "图4-2-MissionInput任务属性结构-旧版.svg",
            "ch4-intelligent-planning-framework-light.svg": "图4-3-海上无人集群任务规划功能框架-旧版.svg",
            "ch5-task-decomposition-structure-light.svg": "图5-1-任务分解多视图映射结构-旧版.svg",
            "ch5-task-decomposition-flow-light.svg": "图5-2-基于杀伤链的逆向任务分解计算流程-旧版.svg",
            "ch6-task-allocation-model-light.svg": "图6-1-任务分配优化模型结构-旧版.svg",
            "ch7-formation-model-light.svg": "图7-1-集群编成与组织熵控制模型结构-旧版.svg",
            "ch8-hybrid-path-framework-light.svg": "图8-1-混合路径规划框架与算法流程-旧版.svg",
            "ch9-execution-monitor-interface-light.svg": "图9-1-执行监控与态势显示界面.png",
            "ch9-planning-workbench-light.svg": "图9-2-预先规划方案编排与节点属性展示图.png",
            "ch9-evaluation-dashboard-light.svg": "图9-3-任务规划效能评估看板.png",
            "ch9-parameter-config-interface-light.svg": "图9-4-环境与目标参数管理界面.png",
        }
        filename = Path(raw).name
        candidates = [
            base / raw,
            base / raw.lstrip("./"),
            base / "论文章节" / raw,
            base / "论文章节" / "正式稿" / raw,
            formal_assets / filename,
        ]
        if filename in aliases:
            candidates.append(formal_assets / aliases[filename])
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if self.vault not in resolved.parents or not resolved.is_file():
                continue
            return resolved
        raise DocumentWorkspaceError(f"文档资源不存在：{raw_path}")

    def asset_path(self, project: dict[str, Any], raw_path: str) -> Path:
        return self._resolve_asset(self.ensure_workspace(project), raw_path)

    def quality(self, project: dict[str, Any], prepared=None) -> dict[str, Any]:
        manifest, markdown, sections = prepared or self._read(project)
        references = self.references(project, prepared=(manifest, markdown, sections))
        formal_numbers = {row["number"] for row in references["formal"]}
        body = markdown.split("# 参考文献", 1)[0]
        cited_numbers = set(_citation_numbers(body))
        missing_refs = sorted(cited_numbers - formal_numbers)
        unresolved_assets = []
        for raw_path in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown):
            try:
                self._resolve_asset(manifest, raw_path)
            except DocumentWorkspaceError:
                unresolved_assets.append(raw_path)
        chapter_numbers = {
            int(match.group(1))
            for row in sections
            for match in [re.search(r"第\s*(\d+)\s*章", row["title"])]
            if match
        }
        expected_chapters = max(int(manifest.get("expected_chapters") or 10), 1)
        missing_chapters = sorted(set(range(1, expected_chapters + 1)) - chapter_numbers)
        issues = []
        for number in missing_refs[:30]:
            issues.append({"severity": "blocker", "type": "missing_reference", "message": f"正文引用 [{number}] 未出现在参考文献表"})
        for path in unresolved_assets[:30]:
            issues.append({"severity": "warning", "type": "missing_asset", "message": f"图片资源无法解析：{path}"})
        for number in missing_chapters:
            issues.append({"severity": "blocker", "type": "missing_chapter", "message": f"缺少第 {number} 章"})
        uncited = references["summary"]["uncited"]
        if uncited:
            issues.append({"severity": "warning", "type": "uncited_references", "message": f"{uncited} 条正式文献尚未在正文中检出引用"})
        score = max(0, 100 - len(missing_refs) * 3 - len(unresolved_assets) * 2 - len(missing_chapters) * 10 - min(uncited, 20))
        return {
            "summary": {
                "score": score,
                "blockers": sum(1 for row in issues if row["severity"] == "blocker"),
                "warnings": sum(1 for row in issues if row["severity"] == "warning"),
                "missing_assets": len(unresolved_assets),
                "missing_references": len(missing_refs),
                "uncited_references": uncited,
            },
            "issues": issues,
        }

    def graph(self, project: dict[str, Any]) -> dict[str, Any]:
        _, markdown, sections = self._read(project)
        graph = knowledge_manager.concept_backbone_graph(limit_edges=1000, node_type="概念")
        section_nodes = [
            {"id": row["id"], "name": row["title"], "type": "section", "category": row["kind"], "value": row["word_count"]}
            for row in sections if row["kind"] in {"chapter", "frontmatter"}
        ]
        concept_hits = []
        section_edges = []
        for node in graph.get("nodes", []):
            title = str(node.get("title") or node.get("name") or Path(str(node.get("id") or "")).stem)
            if len(title) < 2:
                continue
            count = markdown.lower().count(title.lower())
            if count:
                concept_hits.append((count, node, title))
        concept_hits.sort(key=lambda row: row[0], reverse=True)
        concept_hits = concept_hits[:70]
        concept_ids = {str(row[1].get("id")) for row in concept_hits}
        concept_nodes = [
            {"id": str(node.get("id")), "name": title, "type": "concept", "category": node.get("domain") or "概念", "value": count}
            for count, node, title in concept_hits
        ]
        for _, node, title in concept_hits:
            for section in sections:
                occurrences = section["content"].lower().count(title.lower())
                if occurrences:
                    section_edges.append({"source": str(node.get("id")), "target": section["id"], "relation": "章节使用", "weight": occurrences})
        backbone_edges = [
            {"source": row.get("source"), "target": row.get("target"), "relation": row.get("relation") or "概念关联", "weight": row.get("weight", 1)}
            for row in graph.get("relations", [])
            if row.get("source") in concept_ids and row.get("target") in concept_ids
        ]
        argument_nodes = []
        argument_edges = []
        claim_pattern = re.compile(r"(?:本文|本章|研究|结果|实验).{0,24}(?:提出|构建|表明|证明|验证|认为|发现).{8,160}[。；]")
        for section in sections:
            for match in claim_pattern.finditer(re.sub(r"\s+", "", section["content"])):
                text = match.group(0)
                node_id = f"claim-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"
                argument_nodes.append({"id": node_id, "name": text[:72], "type": "claim", "category": "论点", "value": 1, "detail": text})
                argument_edges.append({"source": section["id"], "target": node_id, "relation": "提出论点", "weight": 1})
                if len(argument_nodes) >= 30:
                    break
            if len(argument_nodes) >= 30:
                break
        return {
            "nodes": section_nodes + concept_nodes + argument_nodes,
            "edges": backbone_edges + section_edges + argument_edges,
            "summary": {
                "sections": len(section_nodes),
                "concepts": len(concept_nodes),
                "claims": len(argument_nodes),
                "relations": len(backbone_edges) + len(section_edges) + len(argument_edges),
            },
        }

    def versions(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = self.ensure_workspace(project)
        rows = []
        for path in sorted((self._workspace_root(project) / "versions").glob("*.md"), reverse=True):
            stat = path.stat()
            rows.append({"name": path.name, "size_bytes": stat.st_size, "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
        rows.insert(0, {"name": f"当前工作稿 v{manifest['version']}", "size_bytes": Path(manifest["working_markdown"]).stat().st_size, "created_at": manifest["updated_at"], "current": True})
        return rows

    def export(self, project: dict[str, Any], output_format: str) -> Path:
        manifest = self.ensure_workspace(project)
        output_format = output_format.lower()
        if output_format not in {"docx", "pdf"}:
            raise DocumentWorkspaceError("只支持导出 docx 或 pdf")
        root = self._workspace_root(project)
        exports = root / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        stem = f"{_safe_name(str(project.get('name') or '文档'))}-v{manifest['version']}"
        docx_path = exports / f"{stem}.docx"
        markdown = Path(manifest["working_markdown"]).read_text(encoding="utf-8", errors="replace")

        def export_asset(match: re.Match[str]) -> str:
            try:
                resolved = self._resolve_asset(manifest, match.group(2))
            except DocumentWorkspaceError:
                return match.group(0)
            return f"![{match.group(1)}]({resolved.as_posix()})"

        export_markdown = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", export_asset, markdown)
        export_source = exports / f".{stem}-export.md"
        export_source.write_text(export_markdown, encoding="utf-8")
        resource_path = str(Path(manifest["source_base_dir"]))
        command = [
            "/opt/homebrew/bin/pandoc",
            str(export_source),
            "--from", "markdown",
            "--to", "docx",
            "--resource-path", resource_path,
            "--output", str(docx_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not docx_path.exists():
            raise DocumentWorkspaceError(f"Word 导出失败：{result.stderr[-500:]}")
        if output_format == "docx":
            return docx_path
        pdf_path = exports / f"{stem}.pdf"
        html_path = exports / f".{stem}-export.html"
        html_result = subprocess.run(
            [
                "/opt/homebrew/bin/pandoc", str(export_source),
                "--from", "markdown", "--to", "html5", "--standalone",
                "--resource-path", resource_path, "--output", str(html_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if html_result.returncode != 0 or not html_path.exists():
            raise DocumentWorkspaceError(f"PDF 中间稿生成失败：{html_result.stderr[-500:]}")
        html = html_path.read_text(encoding="utf-8", errors="replace")
        print_style = """<style>
@page { size: A4; margin: 22mm 20mm 22mm 25mm; }
body { font-family: 'Songti SC', 'Noto Serif CJK SC', serif; font-size: 11pt; line-height: 1.75; color: #111; }
h1 { font-size: 20pt; text-align: center; page-break-before: always; margin: 0 0 18pt; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 16pt; margin-top: 18pt; } h3 { font-size: 14pt; margin-top: 14pt; }
p { text-align: justify; margin: 0 0 7pt; } img { display: block; max-width: 92%; max-height: 210mm; margin: 12pt auto; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #777; padding: 4pt; } pre, code { font-family: Menlo, monospace; font-size: 8.5pt; }
</style>"""
        html_path.write_text(html.replace("</head>", print_style + "</head>"), encoding="utf-8")
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if not chrome.exists():
            raise DocumentWorkspaceError("PDF 导出失败：未安装 Google Chrome")
        if pdf_path.exists():
            pdf_path.unlink()
        with tempfile.TemporaryDirectory(prefix="openclaw-chrome-", dir="/private/tmp") as profile:
            process = subprocess.Popen(
                [
                    str(chrome), "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--disable-background-networking", "--disable-component-update", "--no-first-run",
                    "--allow-file-access-from-files", "--no-pdf-header-footer",
                    f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", html_path.as_uri(),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.monotonic() + 180
            stable_size = -1
            stable_since = time.monotonic()
            while time.monotonic() < deadline:
                size = pdf_path.stat().st_size if pdf_path.exists() else 0
                if size > 0 and size == stable_size and time.monotonic() - stable_since >= 1:
                    break
                if size != stable_size:
                    stable_size = size
                    stable_since = time.monotonic()
                if process.poll() is not None and size > 0:
                    break
                time.sleep(0.25)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                raise DocumentWorkspaceError("PDF 导出失败：浏览器打印未生成文件")
        return pdf_path


document_workspace_service = DocumentWorkspaceService()
