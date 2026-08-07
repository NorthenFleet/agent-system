"""Deterministic Markdown projection for the structured writing authority.

The editor owns a Tiptap-compatible JSON tree. Markdown remains a projection
for OpenClaw, quality checks, knowledge indexing, and Pandoc export. Unsupported
syntax is represented as ``rawMarkdown`` so migration never drops source text.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Iterable


SCHEMA_VERSION = "tiptap-json-v1"
_BLOCK_ID_TYPES = {
    "paragraph",
    "heading",
    "bulletList",
    "orderedList",
    "blockquote",
    "codeBlock",
    "horizontalRule",
    "image",
    "table",
    "rawMarkdown",
}
_INLINE_NODE_TYPES = {"text", "hardBreak"}
_MARK_TYPES = {"bold", "italic", "strike", "underline", "code", "link"}
_CONTAINER_BLOCK_TYPES = {
    "paragraph",
    "heading",
    "bulletList",
    "orderedList",
    "blockquote",
    "codeBlock",
    "horizontalRule",
    "image",
    "table",
    "rawMarkdown",
}
_SPECIAL_LINE = re.compile(
    r"^(?:#{1,6}\s+|```|~~~|>\s?|[-+*]\s+|\d+\.\s+|!\[[^]]*]\(|<[^>]+>|\[\^[^]]+]:|:::)"
)
_IMAGE_LINE = re.compile(r'^!\[([^]]*)]\((\S+?)(?:\s+["\'](.*?)["\'])?\)\s*$')
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LIST_LINE = re.compile(r"^(\s*)([-+*]|\d+\.)\s+(.+)$")
_INLINE_TOKEN = re.compile(
    r"(`[^`]+`|\*\*[^*]+\*\*|~~[^~]+~~|<u>.*?</u>|\[[^]]+]\([^)]+\)|\*[^*]+\*)"
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _split_table_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", value)]


class StructuredDocumentCodec:
    schema_version = SCHEMA_VERSION

    def from_markdown(self, markdown: str, *, namespace: str) -> dict[str, Any]:
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        blocks: list[dict[str, Any]] = []
        index = 0

        if lines and lines[0].strip() == "---":
            closing = next((row for row in range(1, len(lines)) if lines[row].strip() == "---"), None)
            if closing is not None:
                blocks.append(self._raw("\n".join(lines[: closing + 1])))
                index = closing + 1

        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            stripped_line = line.strip()
            if stripped_line.startswith("$$"):
                math_block = [line]
                index += 1
                if stripped_line.count("$$") < 2:
                    while index < len(lines):
                        math_block.append(lines[index])
                        if "$$" in lines[index]:
                            index += 1
                            break
                        index += 1
                blocks.append(self._raw("\n".join(math_block)))
                continue

            fence = re.match(r"^(```|~~~)(.*)$", line)
            if fence:
                marker = fence.group(1)
                language = fence.group(2).strip()
                body: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].startswith(marker):
                    body.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                blocks.append({
                    "type": "codeBlock",
                    "attrs": {"language": language or None},
                    "content": [{"type": "text", "text": "\n".join(body)}] if body else [],
                })
                continue

            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading:
                blocks.append({
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": self._inline(heading.group(2)),
                })
                index += 1
                continue

            if line.strip() in {"---", "***", "___"}:
                blocks.append({"type": "horizontalRule", "attrs": {}})
                index += 1
                continue

            image = _IMAGE_LINE.match(line.strip())
            if image:
                blocks.append({
                    "type": "image",
                    "attrs": {"src": image.group(2), "alt": image.group(1), "title": image.group(3)},
                })
                index += 1
                continue

            if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR.match(lines[index + 1]):
                table_lines = [line, lines[index + 1]]
                index += 2
                while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                    table_lines.append(lines[index])
                    index += 1
                blocks.append(self._table(table_lines))
                continue

            list_match = _LIST_LINE.match(line)
            if list_match:
                rows: list[tuple[str, str, str]] = []
                while index < len(lines):
                    match = _LIST_LINE.match(lines[index])
                    if not match:
                        break
                    rows.append((match.group(1), match.group(2), match.group(3)))
                    index += 1
                if any(indent for indent, _, _ in rows) or len({token.endswith(".") for _, token, _ in rows}) > 1:
                    blocks.append(self._raw("\n".join(f"{indent}{token} {text}" for indent, token, text in rows)))
                else:
                    ordered = rows[0][1].endswith(".")
                    blocks.append({
                        "type": "orderedList" if ordered else "bulletList",
                        "attrs": {"start": int(rows[0][1][:-1]) if ordered else None},
                        "content": [
                            {
                                "type": "listItem",
                                "content": [{"type": "paragraph", "content": self._inline(text)}],
                            }
                            for _, _, text in rows
                        ],
                    })
                continue

            if line.startswith(">"):
                quote: list[str] = []
                while index < len(lines) and lines[index].startswith(">"):
                    quote.append(re.sub(r"^>\s?", "", lines[index]))
                    index += 1
                blocks.append({
                    "type": "blockquote",
                    "attrs": {},
                    "content": [{"type": "paragraph", "content": self._inline("\n".join(quote))}],
                })
                continue

            if line.startswith("[^" ) or line.startswith(":::") or line.lstrip().startswith("<"):
                raw = [line]
                index += 1
                while index < len(lines) and lines[index].strip():
                    raw.append(lines[index])
                    index += 1
                blocks.append(self._raw("\n".join(raw)))
                continue

            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip():
                if _SPECIAL_LINE.match(lines[index]) or (
                    index + 1 < len(lines) and "|" in lines[index] and _TABLE_SEPARATOR.match(lines[index + 1])
                ):
                    break
                paragraph.append(lines[index])
                index += 1
            paragraph_text = "\n".join(paragraph)
            if "![" in paragraph_text:
                blocks.append(self._raw(paragraph_text))
            else:
                blocks.append({"type": "paragraph", "attrs": {}, "content": self._inline(paragraph_text)})

        document = {
            "type": "doc",
            "attrs": {"schemaVersion": self.schema_version},
            "content": blocks or [{"type": "paragraph", "attrs": {}, "content": []}],
        }
        self.ensure_block_ids(document, namespace=namespace)
        self.validate_document(document)
        return document

    def validate_document(
        self,
        document: Any,
        *,
        require_block_ids: bool = True,
    ) -> dict[str, Any]:
        """Reject JSON that cannot be represented by the installed editor schema."""
        if not isinstance(document, dict) or document.get("type") != "doc":
            raise ValueError("正文根节点必须是 doc")
        content = document.get("content")
        if not isinstance(content, list):
            raise ValueError("正文 content 必须是数组")
        attrs = document.get("attrs") or {}
        if not isinstance(attrs, dict):
            raise ValueError("正文 attrs 必须是对象")
        schema_version = attrs.get("schemaVersion")
        if schema_version not in {None, self.schema_version}:
            raise ValueError(f"不支持的正文 schema_version：{schema_version}")

        seen: set[str] = set()
        for index, block in enumerate(content):
            self._validate_node(block, f"content[{index}]", top_level=True)
            block_attrs = block.get("attrs") or {}
            block_id = str(block_attrs.get("blockId") or "").strip()
            if require_block_ids and not block_id:
                raise ValueError(f"content[{index}] 缺少 blockId")
            if block_id:
                if block_id in seen:
                    raise ValueError(f"正文包含重复 blockId：{block_id}")
                seen.add(block_id)
            revision = block_attrs.get("blockRevision")
            if require_block_ids and (not isinstance(revision, int) or revision < 1):
                raise ValueError(f"content[{index}] 的 blockRevision 无效")
        return document

    def _validate_node(self, node: Any, path: str, *, top_level: bool = False) -> None:
        if not isinstance(node, dict):
            raise ValueError(f"{path} 必须是对象")
        kind = node.get("type")
        allowed = _BLOCK_ID_TYPES if top_level else (
            _CONTAINER_BLOCK_TYPES
            | _INLINE_NODE_TYPES
            | {"listItem", "tableRow", "tableHeader", "tableCell"}
        )
        if kind not in allowed:
            raise ValueError(f"{path} 包含不支持的节点：{kind}")
        attrs = node.get("attrs") or {}
        if not isinstance(attrs, dict):
            raise ValueError(f"{path}.attrs 必须是对象")

        content = node.get("content") or []
        if not isinstance(content, list):
            raise ValueError(f"{path}.content 必须是数组")
        if kind == "text":
            if not isinstance(node.get("text"), str):
                raise ValueError(f"{path}.text 必须是字符串")
            marks = node.get("marks") or []
            if not isinstance(marks, list):
                raise ValueError(f"{path}.marks 必须是数组")
            for mark_index, mark in enumerate(marks):
                if not isinstance(mark, dict) or mark.get("type") not in _MARK_TYPES:
                    raise ValueError(f"{path}.marks[{mark_index}] 包含不支持的标记")
                if mark.get("attrs") is not None and not isinstance(mark.get("attrs"), dict):
                    raise ValueError(f"{path}.marks[{mark_index}].attrs 必须是对象")
            return
        if kind == "hardBreak":
            if content:
                raise ValueError(f"{path} 不能包含子节点")
            return
        if kind in {"horizontalRule", "image", "rawMarkdown"}:
            if content:
                raise ValueError(f"{path} 不能包含子节点")
            if kind == "rawMarkdown" and not isinstance(attrs.get("markdown", ""), str):
                raise ValueError(f"{path}.attrs.markdown 必须是字符串")
            return

        child_types = {child.get("type") if isinstance(child, dict) else None for child in content}
        if kind in {"paragraph", "heading"} and not child_types.issubset(_INLINE_NODE_TYPES):
            raise ValueError(f"{path} 只能包含行内节点")
        if kind == "codeBlock" and not child_types.issubset({"text"}):
            raise ValueError(f"{path} 只能包含文本")
        if kind in {"bulletList", "orderedList"} and not child_types.issubset({"listItem"}):
            raise ValueError(f"{path} 只能包含 listItem")
        if kind == "listItem" and not child_types.issubset(_CONTAINER_BLOCK_TYPES):
            raise ValueError(f"{path} 包含无效列表内容")
        if kind == "blockquote" and not child_types.issubset(_CONTAINER_BLOCK_TYPES):
            raise ValueError(f"{path} 包含无效引用内容")
        if kind == "table" and not child_types.issubset({"tableRow"}):
            raise ValueError(f"{path} 只能包含 tableRow")
        if kind == "tableRow" and not child_types.issubset({"tableHeader", "tableCell"}):
            raise ValueError(f"{path} 只能包含表格单元格")
        if kind in {"tableHeader", "tableCell"}:
            if not child_types.issubset(_CONTAINER_BLOCK_TYPES):
                raise ValueError(f"{path} 包含无效单元格内容")
            if attrs.get("align") not in {None, "left", "center", "right"}:
                raise ValueError(f"{path}.attrs.align 无效")

        for index, child in enumerate(content):
            self._validate_node(child, f"{path}.content[{index}]")

    def ensure_block_ids(self, document: dict[str, Any], *, namespace: str) -> dict[str, Any]:
        seen: set[str] = set()
        for index, block in enumerate(document.get("content") or []):
            if block.get("type") not in _BLOCK_ID_TYPES:
                block["type"] = "rawMarkdown"
                block["attrs"] = {"markdown": self._inline_text(block)}
                block.pop("content", None)
            attrs = block.setdefault("attrs", {})
            block_id = str(attrs.get("blockId") or "").strip()
            if not block_id or block_id in seen:
                seed = copy.deepcopy(block)
                seed.setdefault("attrs", {}).pop("blockId", None)
                seed["attrs"].pop("blockRevision", None)
                digest = hashlib.sha256(f"{namespace}\0{index}\0{_canonical(seed)}".encode()).hexdigest()[:24]
                block_id = f"block-{digest}"
            attrs["blockId"] = block_id
            attrs["blockRevision"] = max(int(attrs.get("blockRevision") or 1), 1)
            seen.add(block_id)
        document.setdefault("attrs", {})["schemaVersion"] = self.schema_version
        return document

    def to_markdown(self, document: dict[str, Any]) -> str:
        blocks = [self._render_block(block).strip("\n") for block in document.get("content") or []]
        return "\n\n".join(block for block in blocks if block).strip() + "\n"

    def document_sha256(self, document: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()

    def block_sha256(self, block: dict[str, Any]) -> str:
        value = copy.deepcopy(block)
        attrs = value.setdefault("attrs", {})
        attrs.pop("blockRevision", None)
        return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()

    def metrics(self, document: dict[str, Any]) -> dict[str, Any]:
        blocks = document.get("content") or []
        text = self._plain_text(document)
        markdown = self.to_markdown(document)
        return {
            "block_count": len(blocks),
            "heading_count": sum(block.get("type") == "heading" for block in blocks),
            "table_count": sum(block.get("type") == "table" for block in blocks),
            "image_count": sum(block.get("type") == "image" for block in blocks),
            "citation_count": len(set(re.findall(r"\[(\d+)]", markdown))),
            "plain_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def block_markdown(self, block: dict[str, Any]) -> str:
        return self._render_block(block).strip() + "\n"

    def _raw(self, markdown: str) -> dict[str, Any]:
        return {"type": "rawMarkdown", "attrs": {"markdown": markdown}}

    def _table(self, lines: list[str]) -> dict[str, Any]:
        header = _split_table_row(lines[0])
        alignments = []
        for cell in _split_table_row(lines[1]):
            stripped = cell.strip()
            alignments.append("center" if stripped.startswith(":") and stripped.endswith(":") else "right" if stripped.endswith(":") else "left")
        rows = [header, *[_split_table_row(line) for line in lines[2:]]]
        width = max(len(row) for row in rows)
        content = []
        for row_index, row in enumerate(rows):
            cells = []
            for column in range(width):
                text = row[column] if column < len(row) else ""
                cells.append({
                    "type": "tableHeader" if row_index == 0 else "tableCell",
                    "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None, "align": alignments[column] if column < len(alignments) else "left"},
                    "content": [{"type": "paragraph", "content": self._inline(text)}],
                })
            content.append({"type": "tableRow", "content": cells})
        return {"type": "table", "attrs": {}, "content": content}

    def _inline(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        result: list[dict[str, Any]] = []
        cursor = 0
        for match in _INLINE_TOKEN.finditer(text):
            if match.start() > cursor:
                result.extend(self._text_with_breaks(text[cursor:match.start()]))
            token = match.group(0)
            if token.startswith("`"):
                result.append({"type": "text", "text": token[1:-1], "marks": [{"type": "code"}]})
            elif token.startswith("**"):
                result.append({"type": "text", "text": token[2:-2], "marks": [{"type": "bold"}]})
            elif token.startswith("~~"):
                result.append({"type": "text", "text": token[2:-2], "marks": [{"type": "strike"}]})
            elif token.startswith("<u>"):
                result.append({"type": "text", "text": token[3:-4], "marks": [{"type": "underline"}]})
            elif token.startswith("["):
                link = re.match(r"^\[([^]]+)]\(([^)]+)\)$", token)
                if link:
                    result.append({"type": "text", "text": link.group(1), "marks": [{"type": "link", "attrs": {"href": link.group(2), "target": None, "rel": "noopener noreferrer nofollow", "class": None}}]})
            else:
                result.append({"type": "text", "text": token[1:-1], "marks": [{"type": "italic"}]})
            cursor = match.end()
        if cursor < len(text):
            result.extend(self._text_with_breaks(text[cursor:]))
        return result

    def _text_with_breaks(self, text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        parts = text.split("\n")
        for index, part in enumerate(parts):
            part = part.rstrip()
            if part:
                rows.append({"type": "text", "text": part})
            if index < len(parts) - 1:
                rows.append({"type": "hardBreak"})
        return rows

    def _render_inline(self, nodes: Iterable[dict[str, Any]]) -> str:
        output = []
        for node in nodes:
            if node.get("type") == "hardBreak":
                output.append("  \n")
                continue
            if node.get("type") == "image":
                attrs = node.get("attrs") or {}
                output.append(f"![{attrs.get('alt') or ''}]({attrs.get('src') or ''})")
                continue
            text = str(node.get("text") or "")
            for mark in node.get("marks") or []:
                kind = mark.get("type")
                if kind == "code":
                    text = f"`{text}`"
                elif kind == "bold":
                    text = f"**{text}**"
                elif kind == "italic":
                    text = f"*{text}*"
                elif kind == "strike":
                    text = f"~~{text}~~"
                elif kind == "underline":
                    text = f"<u>{text}</u>"
                elif kind == "link":
                    text = f"[{text}]({(mark.get('attrs') or {}).get('href') or ''})"
            output.append(text)
        return "".join(output)

    def _render_block(self, block: dict[str, Any]) -> str:
        kind = block.get("type")
        attrs = block.get("attrs") or {}
        if kind == "rawMarkdown":
            return str(attrs.get("markdown") or "")
        if kind == "heading":
            return f"{'#' * max(1, min(int(attrs.get('level') or 1), 6))} {self._render_inline(block.get('content') or [])}"
        if kind == "paragraph":
            text = self._render_inline(block.get("content") or [])
            alignment = attrs.get("textAlign")
            return f'<p style="text-align: {alignment}">{text}</p>' if alignment and alignment != "left" else text
        if kind == "horizontalRule":
            return "---"
        if kind == "image":
            title = f' "{attrs.get("title")}"' if attrs.get("title") else ""
            return f"![{attrs.get('alt') or ''}]({attrs.get('src') or ''}{title})"
        if kind == "codeBlock":
            content = self._render_inline(block.get("content") or [])
            return f"```{attrs.get('language') or ''}\n{content}\n```"
        if kind == "blockquote":
            body = "\n\n".join(self._render_block(row) for row in block.get("content") or [])
            return "\n".join(f"> {line}" if line else ">" for line in body.splitlines())
        if kind in {"bulletList", "orderedList"}:
            start = int(attrs.get("start") or 1)
            lines = []
            for index, item in enumerate(block.get("content") or []):
                body = " ".join(self._render_block(row).replace("\n", " ") for row in item.get("content") or [])
                marker = f"{start + index}." if kind == "orderedList" else "-"
                lines.append(f"{marker} {body}".rstrip())
            return "\n".join(lines)
        if kind == "table":
            rows = []
            alignments: list[str] = []
            for row_index, row in enumerate(block.get("content") or []):
                cells = []
                for cell in row.get("content") or []:
                    cell_attrs = cell.get("attrs") or {}
                    if row_index == 0:
                        alignments.append(str(cell_attrs.get("align") or "left"))
                    cells.append(" ".join(self._render_block(child).replace("\n", " ") for child in cell.get("content") or []))
                rows.append(f"| {' | '.join(cells)} |")
            if not rows:
                return ""
            separators = {"left": "---", "center": ":---:", "right": "---:"}
            rows.insert(1, f"| {' | '.join(separators.get(value, '---') for value in alignments)} |")
            return "\n".join(rows)
        return str(attrs.get("markdown") or self._inline_text(block))

    def _inline_text(self, node: dict[str, Any]) -> str:
        if node.get("type") == "text":
            return str(node.get("text") or "")
        return "".join(self._inline_text(child) for child in node.get("content") or [])

    def _plain_text(self, document: dict[str, Any]) -> str:
        parts: list[str] = []
        for block in document.get("content") or []:
            if block.get("type") == "rawMarkdown":
                raw = str((block.get("attrs") or {}).get("markdown") or "")
                raw = re.sub(r"^---\n.*?\n---$", "", raw, flags=re.DOTALL)
                raw = re.sub(r"[#>*_`~|:\-]", " ", raw)
                parts.append(raw)
            elif block.get("type") == "image":
                parts.append(str((block.get("attrs") or {}).get("alt") or ""))
            else:
                parts.append(self._inline_text(block))
        return re.sub(r"\s+", " ", " ".join(parts)).strip()


structured_document_codec = StructuredDocumentCodec()
