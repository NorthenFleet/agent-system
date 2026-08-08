"""Derived, read-only comparisons between project rich-text documents."""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from services.document_workspace_service import DocumentVersionConflict, DocumentWorkspaceError
from services.multi_document_service import MultiDocumentService, multi_document_service


HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
NUMBER_RE = re.compile(r"^(?:第\s*)?([0-9一二三四五六七八九十]+)(?:\s*章|[.、\s])")


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _title_key(title: str) -> str:
    value = _normalise_text(re.sub(r"[*_`#]", "", title))
    match = NUMBER_RE.match(value)
    return f"chapter:{match.group(1)}" if match else re.sub(r"[^\w\u4e00-\u9fff]", "", value).casefold()


def _paragraphs(lines: list[str]) -> list[str]:
    values: list[str] = []
    buffer: list[str] = []
    in_fence = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if buffer:
                values.append("\n".join(buffer).strip())
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        values.append("\n".join(buffer).strip())
    return [value for value in values if value]


def _sections(markdown: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = {"title": "文前内容", "key": "frontmatter", "lines": []}
    for line in markdown.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            if current["lines"] or rows:
                rows.append(current)
            title = match.group(2).strip()
            current = {"title": title, "key": _title_key(title), "lines": []}
        else:
            current["lines"].append(line)
    if current["lines"] or not rows:
        rows.append(current)
    for row in rows:
        row["paragraphs"] = _paragraphs(row.pop("lines"))
    return rows


class DocumentComparisonService:
    def __init__(self, documents_service: MultiDocumentService = multi_document_service) -> None:
        self.documents_service = documents_service

    def _content(self, project: dict[str, Any], document_id: str, revision: int | None) -> tuple[dict[str, Any], str]:
        record = self.documents_service.get_document(project, document_id)
        if record.get("kind") != "rich_text":
            raise DocumentWorkspaceError("版本比对仅支持正文文档")
        current_revision = int(record.get("revision") or 1)
        if revision is not None and int(revision) != current_revision:
            raise DocumentVersionConflict(
                f"文档 {record.get('title')} 已更新，当前修订为 {current_revision}"
            )
        payload = self.documents_service.rich_call(project, document_id, "fulltext")
        content = str(payload.get("content") or "")
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        record["source_checksum"] = checksum
        return record, content

    def _compare_paragraphs(self, left: list[str], right: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        matcher = SequenceMatcher(None, [_normalise_text(x) for x in left], [_normalise_text(x) for x in right], autojunk=False)
        changes: list[dict[str, Any]] = []
        summary = {"added": 0, "deleted": 0, "modified": 0, "unchanged": 0}
        for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
            if tag == "equal":
                for offset in range(left_end - left_start):
                    changes.append({
                        "operation": "unchanged",
                        "left_index": left_start + offset,
                        "right_index": right_start + offset,
                        "left_text": left[left_start + offset],
                        "right_text": right[right_start + offset],
                        "similarity": 1.0,
                    })
                    summary["unchanged"] += 1
                continue
            if tag == "delete":
                for index in range(left_start, left_end):
                    changes.append({"operation": "deleted", "left_index": index, "right_index": None, "left_text": left[index], "right_text": "", "similarity": 0.0})
                    summary["deleted"] += 1
                continue
            if tag == "insert":
                for index in range(right_start, right_end):
                    changes.append({"operation": "added", "left_index": None, "right_index": index, "left_text": "", "right_text": right[index], "similarity": 0.0})
                    summary["added"] += 1
                continue
            width = max(left_end - left_start, right_end - right_start)
            for offset in range(width):
                left_text = left[left_start + offset] if left_start + offset < left_end else ""
                right_text = right[right_start + offset] if right_start + offset < right_end else ""
                if left_text and right_text:
                    operation = "modified"
                    summary["modified"] += 1
                elif left_text:
                    operation = "deleted"
                    summary["deleted"] += 1
                else:
                    operation = "added"
                    summary["added"] += 1
                changes.append({
                    "operation": operation,
                    "left_index": left_start + offset if left_text else None,
                    "right_index": right_start + offset if right_text else None,
                    "left_text": left_text,
                    "right_text": right_text,
                    "similarity": round(SequenceMatcher(None, _normalise_text(left_text), _normalise_text(right_text), autojunk=False).ratio(), 4) if left_text and right_text else 0.0,
                })
        return changes, summary

    def compare(self, project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        left_id = str(payload.get("left_document_id") or "")
        right_id = str(payload.get("right_document_id") or "")
        if not left_id or not right_id or left_id == right_id:
            raise DocumentWorkspaceError("请选择两个不同的正文文档进行比对")
        left_record, left_content = self._content(project, left_id, payload.get("left_revision"))
        right_record, right_content = self._content(project, right_id, payload.get("right_revision"))
        cache_key = hashlib.sha256(f"{left_id}:{left_record['source_checksum']}:{right_id}:{right_record['source_checksum']}".encode()).hexdigest()
        cache_dir = self.documents_service._project_root(project) / "comparisons"  # noqa: SLF001
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("section_key"):
                cached["sections"] = [row for row in cached["sections"] if row["key"] == payload["section_key"]]
            cached["cached"] = True
            return cached

        left_sections = _sections(left_content)
        right_sections = _sections(right_content)
        left_by_key = {row["key"]: row for row in left_sections}
        right_by_key = {row["key"]: row for row in right_sections}
        ordered_keys = list(dict.fromkeys([row["key"] for row in left_sections] + [row["key"] for row in right_sections]))
        total = {"added": 0, "deleted": 0, "modified": 0, "unchanged": 0}
        section_rows = []
        for key in ordered_keys:
            left = left_by_key.get(key)
            right = right_by_key.get(key)
            changes, summary = self._compare_paragraphs(
                list(left.get("paragraphs") or []) if left else [],
                list(right.get("paragraphs") or []) if right else [],
            )
            for name in total:
                total[name] += summary[name]
            section_rows.append({
                "key": key,
                "left_title": str(left.get("title") or "") if left else "",
                "right_title": str(right.get("title") or "") if right else "",
                "matched": bool(left and right),
                "summary": summary,
                "changes": changes,
            })
        result = {
            "cache_key": cache_key,
            "cached": False,
            "left": {"document_id": left_id, "title": left_record.get("title"), "revision": left_record.get("revision"), "checksum": left_record["source_checksum"]},
            "right": {"document_id": right_id, "title": right_record.get("title"), "revision": right_record.get("revision"), "checksum": right_record["source_checksum"]},
            "summary": total,
            "sections": section_rows,
        }
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        if payload.get("section_key"):
            result["sections"] = [row for row in section_rows if row["key"] == payload["section_key"]]
        return result


document_comparison_service = DocumentComparisonService()
