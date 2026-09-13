"""High-fidelity DOCX import through Pandoc's typed JSON AST."""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from services.document_workspace_service import DocumentWorkspaceError
from services.structured_document_service import StructuredDocumentCodec, structured_document_codec


def _alignment(value: Any) -> str:
    token = str((value or {}).get("t") if isinstance(value, dict) else value or "")
    return {"AlignCenter": "center", "AlignRight": "right"}.get(token, "left")


class PandocDocxImporter:
    def __init__(self, codec: StructuredDocumentCodec = structured_document_codec) -> None:
        self.codec = codec
        self.assets: dict[str, bytes] = {}
        self.warnings: list[str] = []
        self.unsupported: list[str] = []
        self.media_root = Path()

    def convert(self, data: bytes, title: str) -> dict[str, Any]:
        self.assets = {}
        self.warnings = []
        self.unsupported = []
        pandoc = os.getenv("PANDOC_BIN", "").strip() or shutil.which("pandoc")
        if not pandoc:
            raise DocumentWorkspaceError("服务器缺少 Pandoc，Word 高保真导入已阻止")
        with tempfile.TemporaryDirectory(prefix="openclaw-docx-") as temporary:
            root = Path(temporary)
            source = root / "source.docx"
            ast_path = root / "document.json"
            self.media_root = root / "media"
            source.write_bytes(data)
            result = subprocess.run(
                [pandoc, str(source), "--from=docx", "--to=json", f"--extract-media={self.media_root}", "--output", str(ast_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode or not ast_path.is_file():
                detail = (result.stderr or result.stdout or "Pandoc 未生成结构化结果").strip()
                raise DocumentWorkspaceError(f"Word 高保真导入失败：{detail[:400]}")
            ast = json.loads(ast_path.read_text(encoding="utf-8"))
            frontmatter = self._frontmatter(title).strip()
            blocks = [{"type": "rawMarkdown", "attrs": {"markdown": frontmatter}}, *self._blocks(ast.get("blocks") or [])]
            document = {
                "type": "doc",
                "attrs": {"schemaVersion": self.codec.schema_version, "sourceFormat": "docx-pandoc-json"},
                "content": blocks or [{"type": "paragraph", "attrs": {}, "content": []}],
            }
            self.codec.ensure_block_ids(document, namespace=f"docx/{hashlib.sha256(data).hexdigest()}")
            self.codec.validate_document(document)
            markdown = self.codec.to_markdown(document)
            metrics = self.codec.metrics(document)
            status = "degraded" if self.unsupported or metrics["replacement_character_count"] else "passed"
            if self.unsupported:
                self.warnings.append("存在尚未结构化的 Pandoc 节点：" + "、".join(sorted(set(self.unsupported))))
            return {
                "markdown": markdown,
                "document": document,
                "assets": self.assets,
                "stats": {
                    **metrics,
                    "paragraph_count": sum(node.get("type") == "paragraph" for node in self.codec._walk_nodes(document)),
                    "list_count": sum(node.get("type") in {"bulletList", "orderedList"} for node in self.codec._walk_nodes(document)),
                    "size_chars": len(markdown),
                    "fidelity_status": status,
                    "unsupported_node_count": len(self.unsupported),
                },
                "warnings": self.warnings,
            }

    @staticmethod
    def _frontmatter(title: str) -> str:
        return "---\n" + f"title: {json.dumps(title, ensure_ascii=False)}\nstatus: imported\nimporter: pandoc-json\n---\n\n"

    def _blocks(self, blocks: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for block in blocks:
            kind, value = block.get("t"), block.get("c")
            if kind in {"Para", "Plain"}:
                result.extend(self._paragraph_blocks(value or []))
            elif kind == "Header":
                level, _attr, inlines = value
                result.append({"type": "heading", "attrs": {"level": max(1, min(int(level), 6))}, "content": self._inlines(inlines)})
            elif kind == "CodeBlock":
                attr, code = value
                classes = attr[1] if isinstance(attr, list) and len(attr) > 1 else []
                result.append({"type": "codeBlock", "attrs": {"language": classes[0] if classes else None}, "content": [{"type": "text", "text": str(code)}]})
            elif kind == "BlockQuote":
                result.append({"type": "blockquote", "attrs": {}, "content": self._blocks(value or [])})
            elif kind == "BulletList":
                result.append(self._list(value or [], ordered=False))
            elif kind == "OrderedList":
                list_attrs, items = value
                start = int(list_attrs[0] or 1) if isinstance(list_attrs, list) else 1
                result.append(self._list(items or [], ordered=True, start=start))
            elif kind == "HorizontalRule":
                result.append({"type": "horizontalRule", "attrs": {}})
            elif kind == "Table":
                result.append(self._table(value))
            elif kind == "Div":
                result.extend(self._blocks(value[1] if isinstance(value, list) and len(value) > 1 else []))
            elif kind == "Figure":
                result.extend(self._figure(value))
            elif kind in {"RawBlock", "Null"}:
                if kind == "RawBlock" and isinstance(value, list) and len(value) > 1 and value[1]:
                    result.append({"type": "rawMarkdown", "attrs": {"markdown": str(value[1])}})
            else:
                self.unsupported.append(str(kind))
                result.append({"type": "rawMarkdown", "attrs": {"markdown": json.dumps(block, ensure_ascii=False)}})
        return result

    def _paragraph_blocks(self, inlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        for inline in inlines:
            if inline.get("t") == "Image":
                if current:
                    rows.append({"type": "paragraph", "attrs": {}, "content": current})
                    current = []
                rows.append(self._image(inline.get("c") or []))
            elif inline.get("t") == "Math" and (inline.get("c") or [{}])[0].get("t") == "DisplayMath":
                if current:
                    rows.append({"type": "paragraph", "attrs": {}, "content": current})
                    current = []
                rows.append({"type": "mathBlock", "attrs": {"latex": str(inline["c"][1]), "suffix": "", "sourceFormat": "omml"}})
            else:
                current.extend(self._inline(inline))
        if current or not rows:
            rows.append({"type": "paragraph", "attrs": {}, "content": current})
        return rows

    def _inlines(self, inlines: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for inline in inlines:
            result.extend(self._inline(inline))
        return result

    def _inline(self, inline: dict[str, Any], marks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        kind, value = inline.get("t"), inline.get("c")
        marks = list(marks or [])
        if kind == "Str":
            return [{"type": "text", "text": str(value), **({"marks": marks} if marks else {})}]
        if kind in {"Space", "SoftBreak"}:
            return [{"type": "text", "text": " ", **({"marks": marks} if marks else {})}]
        if kind == "LineBreak":
            return [{"type": "hardBreak"}]
        if kind == "Math":
            math_kind, latex = value
            if math_kind.get("t") == "DisplayMath":
                return [{"type": "mathInline", "attrs": {"latex": str(latex), "displayHint": True}}]
            return [{"type": "mathInline", "attrs": {"latex": str(latex)}}]
        mark_types = {
            "Strong": "bold", "Emph": "italic", "Strikeout": "strike", "Underline": "underline",
            "Superscript": "superscript", "Subscript": "subscript",
        }
        if kind in mark_types:
            return self._inlines_marked(value or [], [*marks, {"type": mark_types[kind]}])
        if kind == "Code":
            return [{"type": "text", "text": str(value[1]), "marks": [*marks, {"type": "code"}]}]
        if kind == "Link":
            _attr, children, target = value
            href = str(target[0] if isinstance(target, list) else target)
            return self._inlines_marked(children or [], [*marks, {"type": "link", "attrs": {"href": href, "target": None, "rel": "noopener noreferrer nofollow", "class": None}}])
        if kind in {"Span", "Quoted", "Cite", "SmallCaps"}:
            children = value[-1] if isinstance(value, list) and value else []
            return self._inlines_marked(children or [], marks)
        if kind == "RawInline":
            return [{"type": "text", "text": str(value[1] if isinstance(value, list) and len(value) > 1 else ""), **({"marks": marks} if marks else {})}]
        if kind == "Note":
            text = " ".join(self._plain_block_text(block) for block in (value or []))
            return [{"type": "text", "text": f"〔{text}〕", **({"marks": marks} if marks else {})}]
        self.unsupported.append(str(kind))
        text = self._plain_inline_text(inline)
        return [{"type": "text", "text": text, **({"marks": marks} if marks else {})}] if text else []

    def _inlines_marked(self, inlines: Iterable[dict[str, Any]], marks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for inline in inlines:
            result.extend(self._inline(inline, marks))
        return result

    def _image(self, value: list[Any]) -> dict[str, Any]:
        attr, alt, target = value
        source = str(target[0] if isinstance(target, list) else target)
        title = str(target[1] if isinstance(target, list) and len(target) > 1 else "")
        path = Path(source)
        if not path.is_absolute():
            path = self.media_root / path
        if not path.is_file():
            candidates = list(self.media_root.rglob(Path(source).name))
            path = candidates[0] if candidates else path
        if not path.is_file():
            self.warnings.append(f"图片资源不存在：{source}")
            asset_path = source
        else:
            data = path.read_bytes()
            filename = f"{hashlib.sha256(data).hexdigest()[:12]}-{path.name}"
            self.assets.setdefault(filename, data)
            asset_path = f"assets/{filename}"
        keyvals = dict(attr[2] if isinstance(attr, list) and len(attr) > 2 else [])
        return {
            "type": "image",
            "attrs": {
                "src": asset_path,
                "alt": self._plain_inlines_text(alt or []),
                "title": title or None,
                "width": keyvals.get("width"),
                "height": keyvals.get("height"),
                "sourceFormat": "docx",
            },
        }

    def _list(self, items: list[Any], *, ordered: bool, start: int = 1) -> dict[str, Any]:
        return {
            "type": "orderedList" if ordered else "bulletList",
            "attrs": {"start": start if ordered else None},
            "content": [{"type": "listItem", "content": self._blocks(item) or [{"type": "paragraph", "attrs": {}, "content": []}]} for item in items],
        }

    def _table(self, value: list[Any]) -> dict[str, Any]:
        _attr, _caption, colspecs, head, bodies, foot = value
        alignments = [_alignment(spec[0]) for spec in colspecs]
        rows: list[tuple[bool, Any]] = []
        rows.extend((True, row) for row in (head[1] or []))
        for body in bodies or []:
            rows.extend((True, row) for row in (body[2] or []))
            rows.extend((False, row) for row in (body[3] or []))
        rows.extend((False, row) for row in (foot[1] or []))
        content = []
        for header, row in rows:
            cells = []
            for column, cell in enumerate(row[1] or []):
                _cell_attr, cell_align, rowspan, colspan, cell_blocks = cell
                blocks = self._blocks(cell_blocks or []) or [{"type": "paragraph", "attrs": {}, "content": []}]
                cells.append({
                    "type": "tableHeader" if header else "tableCell",
                    "attrs": {
                        "colspan": max(int(colspan or 1), 1),
                        "rowspan": max(int(rowspan or 1), 1),
                        "colwidth": None,
                        "align": _alignment(cell_align) or (alignments[column] if column < len(alignments) else "left"),
                    },
                    "content": blocks,
                })
            content.append({"type": "tableRow", "content": cells})
        return {"type": "table", "attrs": {"sourceFormat": "docx-pandoc-json"}, "content": content}

    def _figure(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list) and value:
            body = value[-1]
            if isinstance(body, list):
                return self._blocks(body)
        self.unsupported.append("Figure")
        return []

    def _plain_inline_text(self, inline: dict[str, Any]) -> str:
        kind, value = inline.get("t"), inline.get("c")
        if kind == "Str":
            return str(value)
        if kind in {"Space", "SoftBreak", "LineBreak"}:
            return " "
        if kind == "Math":
            return str(value[1])
        if isinstance(value, list):
            return "".join(self._plain_inline_text(item) for item in value if isinstance(item, dict))
        return ""

    def _plain_inlines_text(self, inlines: Iterable[dict[str, Any]]) -> str:
        return "".join(self._plain_inline_text(item) for item in inlines).strip()

    def _plain_block_text(self, block: dict[str, Any]) -> str:
        value = block.get("c")
        if block.get("t") in {"Para", "Plain"}:
            return self._plain_inlines_text(value or [])
        return ""


pandoc_docx_importer = PandocDocxImporter()
