"""Adaptive, source-preserving outline construction for rich-text documents."""

from __future__ import annotations

import re
from typing import Any


_DATE_HEADING = re.compile(
    r"^(?:\d{4}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?|"
    r"\d{4}\s*年\s*\d{1,2}\s*月)$"
)
_CHAPTER_HEADING = re.compile(r"^第\s*(?:\d+|[一二三四五六七八九十百零〇两]+)\s*章(?:\s|$)")
_CHINESE_TOP_LEVEL = re.compile(r"^[一二三四五六七八九十百]+[、.．]\s*")
_CHINESE_SECOND_LEVEL = re.compile(r"^[（(][一二三四五六七八九十百]+[）)]\s*")
_PARENTHESIZED_ARABIC = re.compile(r"^[（(]\d+[）)]\s*")
_ARABIC_NUMBERING = re.compile(r"^(\d+(?:\.\d+){0,5})\s*[、.．]?\s*")
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_MAX_DIRECTORY_SOURCE_LEVEL = 3


def _is_directory_heading(item: dict[str, Any]) -> bool:
    """Return whether a source heading belongs in the three-level navigator.

    Explicit fourth-level numbering and list-style substeps stay in the body.
    An unnumbered H4 can still repair a source-level jump (H1 -> H3 -> H4)
    into a legal three-level display tree.
    """
    source_level = int(item.get("level") or 1)
    if source_level <= _MAX_DIRECTORY_SOURCE_LEVEL:
        return True
    title = str(item.get("title") or "").strip()
    arabic = _ARABIC_NUMBERING.match(title)
    if arabic and arabic.group(1).count(".") + 1 > _MAX_DIRECTORY_SOURCE_LEVEL:
        return False
    return not _PARENTHESIZED_ARABIC.match(title)


def _normalized_title(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.casefold())


def _is_document_title(title: str, document_title: str) -> bool:
    heading = _normalized_title(title)
    document = _normalized_title(document_title)
    if len(heading) < 4 or len(document) < 4:
        return False
    return heading in document or document in heading


def _display_level(title: str, source_level: int) -> int:
    """Infer a display level without changing the source Markdown."""
    stripped = title.strip()
    if _CHAPTER_HEADING.match(stripped) or _CHINESE_TOP_LEVEL.match(stripped):
        return 1
    if _CHINESE_SECOND_LEVEL.match(stripped):
        return 2
    arabic = _ARABIC_NUMBERING.match(stripped)
    if arabic:
        depth = arabic.group(1).count(".") + 1
        return max(1, min(depth, 3))
    return max(1, min(int(source_level or 1), 3))


def _chapter_number(title: str, fallback: int) -> int:
    match = re.search(r"第\s*([0-9零〇一二三四五六七八九十百]+)\s*章", title)
    if not match:
        return fallback
    raw = match.group(1)
    if raw.isdigit():
        return int(raw)
    total = 0
    current = 0
    for char in raw:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return fallback
    return total + current or fallback


def _node_from_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": section["id"],
        "title": section["title"],
        "node_type": "section",
        "source_level": 1,
        "level": 1,
        "line": section["start_line"],
        "anchor": section.get("anchor") or "",
        "target_id": section.get("target_id") or "",
        "section_id": section["id"],
        "kind": section.get("kind"),
        "word_count": section.get("word_count", 0),
        "children": [],
    }


def _node_from_outline(item: dict[str, Any], section_id: str) -> dict[str, Any]:
    source_level = int(item.get("level") or 1)
    return {
        "id": item["id"],
        "title": item["title"],
        "node_type": "heading",
        "source_level": source_level,
        "level": _display_level(item["title"], source_level),
        "line": item["line"],
        "anchor": item.get("anchor") or "",
        "target_id": item.get("target_id") or "",
        "section_id": section_id,
        "word_count": None,
        "children": [],
    }


def build_document_directory(
    sections: list[dict[str, Any]],
    document_title: str,
    *,
    document_id: str = "",
) -> list[dict[str, Any]]:
    """Return one adaptive tree rooted at the current document.

    Markdown remains untouched. Standard heading levels are respected, while
    common Chinese and Arabic numbering supplies a stable fallback for mixed
    manuals and imported documents.
    """
    root_id = f"document-{document_id or 'root'}"
    root = {
        "id": root_id,
        "title": document_title or "正文文档",
        "node_type": "document",
        "source_level": 0,
        "level": 0,
        "line": 0,
        "anchor": "",
        "target_id": "",
        "section_id": "",
        "kind": "document",
        "word_count": sum(int(section.get("word_count") or 0) for section in sections),
        "metadata": {"labels": []},
        "children": [],
    }
    parents: dict[int, dict[str, Any]] = {0: root}

    for index, section in enumerate(sections):
        title = str(section.get("title") or "").strip()
        if _DATE_HEADING.fullmatch(title):
            root["metadata"]["labels"].append(title)
            continue
        if index == 0 and _is_document_title(title, document_title):
            continue

        section_node = _node_from_section(section)
        section_node["level"] = _display_level(title, 1)
        if section_node["level"] != 1:
            section_node["level"] = 1
        root["children"].append(section_node)
        parents = {0: root, 1: section_node}

        for item in section.get("outline") or []:
            if not _is_directory_heading(item):
                continue
            node = _node_from_outline(item, section["id"])
            level = max(2, node["level"])
            nearest_available_level = max((candidate for candidate in parents if candidate < level), default=1)
            level = min(level, nearest_available_level + 1)
            node["level"] = level
            parent = next(
                (parents[parent_level] for parent_level in range(level - 1, -1, -1) if parent_level in parents),
                section_node,
            )
            parent["children"].append(node)
            parents[level] = node
            for child_level in [key for key in parents if key > level]:
                parents.pop(child_level, None)

    return [root]


def build_document_structure_snapshot(
    sections: list[dict[str, Any]],
    *,
    document_title: str,
    version: int | str,
    source_path: str,
    source_sha256: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build the canonical current structure from parsed Markdown sections."""
    directory_heading_count = sum(
        1 + sum(1 for item in section.get("outline") or [] if _is_directory_heading(item))
        for section in sections
    )
    source_heading_count = sum(int(row.get("heading_count") or 0) for row in sections)
    chapters = []
    for index, section in enumerate(
        row for row in sections if str(row.get("kind") or "") == "chapter"
    ):
        chapters.append(
            {
                "number": _chapter_number(str(section.get("title") or ""), index + 1),
                "title": str(section.get("title") or "").strip(),
                "outline": [
                    {
                        "title": str(item.get("title") or "").strip(),
                        "level": int(item.get("level") or 1),
                    }
                    for item in section.get("outline") or []
                    if _is_directory_heading(item)
                ],
            }
        )
    version_label = str(version).strip()
    if version_label and not version_label.lower().startswith("v"):
        version_label = f"v{version_label}"
    return {
        "title": f"{document_title or '正文文档'}当前结构",
        "version": version_label,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "generated_at": generated_at,
        "chapter_count": len(chapters),
        "heading_count": directory_heading_count,
        "source_heading_count": source_heading_count,
        "chapters": chapters,
    }


def _structure_chapter_signature(chapter: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(chapter.get("number") or 0),
        str(chapter.get("title") or "").strip(),
        tuple(
            (
                str(item.get("title") or "").strip(),
                int(item.get("level") or 0),
            )
            for item in chapter.get("outline") or []
        ),
    )


def compare_document_structures(
    current: dict[str, Any],
    target: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare current and target directory structures without business-specific rules."""
    target = target if isinstance(target, dict) else {}
    target_chapters = target.get("chapters")
    if not isinstance(target_chapters, list) or not target_chapters:
        return {
            "status": "missing",
            "message": "未设置目标目录，当前结构仍可正常使用。",
            "current_version": str(current.get("version") or ""),
            "target_version": "",
            "current_sha256": str(current.get("source_sha256") or ""),
            "target_sha256": "",
            "source_matches": False,
            "chapter_count_delta": int(current.get("chapter_count") or 0),
            "heading_count_delta": int(current.get("heading_count") or 0),
            "changed_chapters": [
                int(chapter.get("number") or index + 1)
                for index, chapter in enumerate(current.get("chapters") or [])
            ],
        }

    current_by_number = {
        int(chapter.get("number") or index + 1): chapter
        for index, chapter in enumerate(current.get("chapters") or [])
    }
    target_by_number = {
        int(chapter.get("number") or index + 1): chapter
        for index, chapter in enumerate(target_chapters)
    }
    changed_chapters = [
        number
        for number in sorted(set(current_by_number) | set(target_by_number))
        if _structure_chapter_signature(current_by_number.get(number, {}))
        != _structure_chapter_signature(target_by_number.get(number, {}))
    ]
    chapter_delta = int(current.get("chapter_count") or 0) - int(
        target.get("chapter_count") or len(target_chapters)
    )
    heading_delta = int(current.get("heading_count") or 0) - int(
        target.get("heading_count") or 0
    )
    aligned = not changed_chapters and chapter_delta == 0 and heading_delta == 0
    current_sha256 = str(current.get("source_sha256") or "")
    target_sha256 = str(target.get("source_sha256") or "")
    return {
        "status": "aligned" if aligned else "diverged",
        "message": (
            "当前结构与目标目录一致。"
            if aligned
            else f"当前结构与目标目录存在差异，涉及{len(changed_chapters)}章。"
        ),
        "current_version": str(current.get("version") or ""),
        "target_version": str(target.get("version") or ""),
        "current_sha256": current_sha256,
        "target_sha256": target_sha256,
        "source_matches": bool(
            current_sha256 and target_sha256 and current_sha256 == target_sha256
        ),
        "chapter_count_delta": chapter_delta,
        "heading_count_delta": heading_delta,
        "changed_chapters": changed_chapters,
    }
