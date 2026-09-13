"""Deterministic, read-only inventory for DOCX fidelity gold documents."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}

REQUIRED_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
)


def _sha256(data: bytes | str) -> str:
    value = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _attr(node: ET.Element | None, namespace: str, name: str, default: str = "") -> str:
    if node is None:
        return default
    return str(node.attrib.get(f"{{{NS[namespace]}}}{name}", default))


def _read_xml(archive: ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(archive.read(name))
    except KeyError:
        return None


def _canonical_xml_sha256(data: bytes) -> str:
    try:
        canonical = ET.canonicalize(data.decode("utf-8"), strip_text=False)
    except (ET.ParseError, UnicodeDecodeError):
        canonical = data.decode("utf-8", errors="replace")
    return _sha256(canonical)


def _xml_part_sha256(archive: ZipFile, name: str) -> str:
    try:
        return _canonical_xml_sha256(archive.read(name))
    except KeyError:
        return _canonical_sha256([])


def _element_sequence_sha256(nodes: list[ET.Element]) -> str:
    return _canonical_sha256(
        [ET.tostring(node, encoding="unicode") for node in nodes]
    )


def _part_group_sha256(archive: ZipFile, names: list[str]) -> str:
    return _canonical_sha256(
        {name: _xml_part_sha256(archive, name) for name in sorted(names)}
    )


def _paragraph_text(paragraph: ET.Element) -> str:
    chunks: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{{{NS['w']}}}t":
            chunks.append(node.text or "")
        elif node.tag == f"{{{NS['w']}}}tab":
            chunks.append("\t")
        elif node.tag == f"{{{NS['w']}}}br":
            chunks.append("\n")
    return "".join(chunks)


def _paragraph_style(paragraph: ET.Element) -> str:
    return _attr(paragraph.find("./w:pPr/w:pStyle", NS), "w", "val")


def _style_catalog(styles: ET.Element | None) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    catalog: dict[str, dict[str, Any]] = {}
    heading_levels: dict[str, int] = {}
    if styles is None:
        return catalog, heading_levels
    for style in styles.findall("./w:style", NS):
        style_id = _attr(style, "w", "styleId")
        if not style_id:
            continue
        name = _attr(style.find("./w:name", NS), "w", "val", style_id)
        style_type = _attr(style, "w", "type")
        outline = _attr(style.find("./w:pPr/w:outlineLvl", NS), "w", "val")
        catalog[style_id] = {"name": name, "type": style_type, "outline_level": outline}
        if style_type != "paragraph":
            continue
        match = re.search(r"(?:heading|标题)\s*([1-9])", name, flags=re.IGNORECASE)
        if match:
            heading_levels[style_id] = int(match.group(1))
        elif outline.isdigit() and 0 <= int(outline) <= 8:
            heading_levels[style_id] = int(outline) + 1
    return catalog, heading_levels


def _field_instructions(document: ET.Element) -> list[str]:
    values = [
        " ".join(_attr(node, "w", "instr").split())
        for node in document.findall(".//w:fldSimple", NS)
        if _attr(node, "w", "instr").strip()
    ]
    stacks: list[list[str]] = []
    for node in document.iter():
        if node.tag == f"{{{NS['w']}}}fldChar":
            field_type = _attr(node, "w", "fldCharType")
            if field_type == "begin":
                stacks.append([])
            elif field_type == "end" and stacks:
                instruction = " ".join("".join(stacks.pop()).split())
                if instruction:
                    values.append(instruction)
            continue
        if node.tag != f"{{{NS['w']}}}instrText":
            continue
        if stacks:
            stacks[-1].append(node.text or "")
        elif (node.text or "").strip():
            values.append(" ".join((node.text or "").split()))
    for fragments in stacks:
        instruction = " ".join("".join(fragments).split())
        if instruction:
            values.append(instruction)
    return values


def _field_counts(values: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        match = re.search(r"\b(TOC|REF|PAGEREF|SEQ|PAGE|NUMPAGES|HYPERLINK|STYLEREF|CITATION)\b", value.upper())
        counts[match.group(1) if match else "OTHER"] += 1
    return dict(sorted(counts.items()))


def _relationship_counts(root: ET.Element | None) -> tuple[dict[str, int], int]:
    counts: Counter[str] = Counter()
    external = 0
    if root is None:
        return {}, 0
    for relation in root.findall("./pr:Relationship", NS):
        relation_type = relation.attrib.get("Type", "").rsplit("/", 1)[-1] or "unknown"
        counts[relation_type] += 1
        if relation.attrib.get("TargetMode") == "External":
            external += 1
    return dict(sorted(counts.items())), external


def _app_properties(root: ET.Element | None) -> dict[str, Any]:
    if root is None:
        return {}
    values: dict[str, Any] = {}
    for name in ("Application", "AppVersion", "Pages", "Words", "Characters", "Paragraphs"):
        node = root.find(f"./ep:{name}", NS)
        if node is None or node.text is None:
            continue
        values[name[0].lower() + name[1:]] = int(node.text) if node.text.isdigit() else node.text
    return values


def _section_geometry(document: ET.Element) -> list[dict[str, Any]]:
    geometry: list[dict[str, Any]] = []
    for section in document.findall(".//w:sectPr", NS):
        page_size = section.find("./w:pgSz", NS)
        margins = section.find("./w:pgMar", NS)
        geometry.append(
            {
                "page_size_twips": {
                    "width": _attr(page_size, "w", "w"),
                    "height": _attr(page_size, "w", "h"),
                    "orientation": _attr(page_size, "w", "orient", "portrait"),
                },
                "margins_twips": {
                    name: _attr(margins, "w", name)
                    for name in ("top", "right", "bottom", "left", "header", "footer", "gutter")
                },
                "columns": _attr(section.find("./w:cols", NS), "w", "num", "1"),
            }
        )
    return geometry


def _note_count(root: ET.Element | None, tag: str) -> int:
    if root is None:
        return 0
    count = 0
    for node in root.findall(f"./w:{tag}", NS):
        note_id = _attr(node, "w", "id")
        if note_id.startswith("-"):
            continue
        count += 1
    return count


def _child_count(root: ET.Element | None, path: str) -> int:
    return len(root.findall(path, NS)) if root is not None else 0


def _structure_signature(
    document: ET.Element,
    heading_levels: dict[str, int],
    native_object_sha256: dict[str, str],
) -> str:
    rows: list[Any] = []
    for paragraph in document.findall(".//w:p", NS):
        style_id = _paragraph_style(paragraph)
        text = _paragraph_text(paragraph)
        rows.append(
            [
                "p",
                style_id,
                heading_levels.get(style_id, 0),
                len(text),
                len(paragraph.findall(".//w:drawing", NS)),
                _element_sequence_sha256(paragraph.findall(".//m:oMath", NS)),
                _canonical_sha256(_field_instructions(paragraph)),
            ]
        )
    for table in document.findall(".//w:tbl", NS):
        rows.append(
            [
                "tbl",
                len(table.findall("./w:tr", NS)),
                [len(row.findall("./w:tc", NS)) for row in table.findall("./w:tr", NS)],
            ]
        )
    rows.append(["sections", _section_geometry(document)])
    rows.append(["native_objects", native_object_sha256])
    return _canonical_sha256(rows)


def audit_docx(path: str | Path, *, expected_sha256: str = "") -> dict[str, Any]:
    source = Path(path).expanduser()
    normalized_expected_sha = expected_sha256.strip().lower()
    report: dict[str, Any] = {
        "path": str(source),
        "exists": source.is_file(),
        "expected_sha256": normalized_expected_sha,
        "status": "failed",
        "errors": [],
    }
    if not source.is_file():
        report["errors"].append("source_missing")
        return report

    data = source.read_bytes()
    actual_sha = _sha256(data)
    report.update({"size_bytes": len(data), "sha256": actual_sha})
    if not normalized_expected_sha:
        report["errors"].append("expected_sha256_required")
    elif not re.fullmatch(r"[0-9a-f]{64}", normalized_expected_sha):
        report["errors"].append("expected_sha256_invalid")
    elif actual_sha != normalized_expected_sha:
        report["errors"].append("sha256_mismatch")

    try:
        with ZipFile(io.BytesIO(data)) as archive:
            names = sorted(archive.namelist())
            bad_part = archive.testzip()
            missing_parts = [name for name in REQUIRED_PARTS if name not in names]
            if bad_part:
                report["errors"].append(f"zip_crc_error:{bad_part}")
            if missing_parts:
                report["errors"].append("missing_required_parts")
            document = _read_xml(archive, "word/document.xml")
            if document is None:
                report["errors"].append("document_xml_missing")
                report["missing_parts"] = missing_parts
                return report

            styles = _read_xml(archive, "word/styles.xml")
            style_catalog, heading_levels = _style_catalog(styles)
            paragraphs = document.findall(".//w:p", NS)
            paragraph_styles = Counter(filter(None, (_paragraph_style(node) for node in paragraphs)))
            heading_sequence = [
                {
                    "level": heading_levels[style_id],
                    "style_id": style_id,
                    "text": _paragraph_text(paragraph).strip(),
                }
                for paragraph in paragraphs
                if (style_id := _paragraph_style(paragraph)) in heading_levels
            ]
            caption_indices = {
                index
                for index, paragraph in enumerate(paragraphs)
                if "caption" in str(style_catalog.get(_paragraph_style(paragraph), {}).get("name", "")).lower()
                or "题注" in str(style_catalog.get(_paragraph_style(paragraph), {}).get("name", ""))
                or re.match(r"^\s*[图表]\s*\d+(?:[-－.]\d+)?", _paragraph_text(paragraph))
            }
            tables = document.findall(".//w:tbl", NS)
            media_names = [name for name in names if name.startswith("word/media/") and not name.endswith("/")]
            embedding_names = [
                name
                for name in names
                if name.startswith("word/embeddings/") and not name.endswith("/")
            ]
            relation_counts, external_relations = _relationship_counts(
                _read_xml(archive, "word/_rels/document.xml.rels")
            )
            text = "\n".join(_paragraph_text(node) for node in paragraphs)
            bookmark_names = sorted(
                filter(None, (_attr(node, "w", "name") for node in document.findall(".//w:bookmarkStart", NS)))
            )
            section_geometry = _section_geometry(document)
            settings = _read_xml(archive, "word/settings.xml")
            font_table = _read_xml(archive, "word/fontTable.xml")
            field_instructions = _field_instructions(document)
            grid_spans = document.findall(".//w:gridSpan", NS)
            horizontal_merge_markers = document.findall(".//w:hMerge", NS)
            vertical_merge_markers = document.findall(".//w:vMerge", NS)
            header_names = [name for name in names if re.fullmatch(r"word/header\d+\.xml", name)]
            footer_names = [name for name in names if re.fullmatch(r"word/footer\d+\.xml", name)]
            relationship_names = [name for name in names if name.endswith(".rels")]
            native_object_sha256 = {
                "math": _element_sequence_sha256(document.findall(".//m:oMath", NS)),
                "field_instructions": _canonical_sha256(field_instructions),
                "bookmarks": _element_sequence_sha256(
                    document.findall(".//w:bookmarkStart", NS)
                    + document.findall(".//w:bookmarkEnd", NS)
                ),
                "content_controls": _element_sequence_sha256(document.findall(".//w:sdt", NS)),
                "drawings": _element_sequence_sha256(
                    document.findall(".//w:drawing", NS)
                    + document.findall(".//w:pict", NS)
                ),
                "section_properties": _element_sequence_sha256(document.findall(".//w:sectPr", NS)),
                "styles": _xml_part_sha256(archive, "word/styles.xml"),
                "numbering": _xml_part_sha256(archive, "word/numbering.xml"),
                "settings": _xml_part_sha256(archive, "word/settings.xml"),
                "headers": _part_group_sha256(archive, header_names),
                "footers": _part_group_sha256(archive, footer_names),
                "footnotes": _xml_part_sha256(archive, "word/footnotes.xml"),
                "endnotes": _xml_part_sha256(archive, "word/endnotes.xml"),
                "comments": _xml_part_sha256(archive, "word/comments.xml"),
                "relationships": _part_group_sha256(archive, relationship_names),
            }
            metrics = {
                "paragraph_count": len(paragraphs),
                "nonempty_paragraph_count": sum(bool(_paragraph_text(node).strip()) for node in paragraphs),
                "heading_count": len(heading_sequence),
                "heading_level_counts": dict(sorted(Counter(row["level"] for row in heading_sequence).items())),
                "caption_paragraph_count": len(caption_indices),
                "table_count": len(tables),
                "table_row_count": len(document.findall(".//w:tr", NS)),
                "table_cell_count": len(document.findall(".//w:tc", NS)),
                "grid_span_element_count": len(grid_spans),
                "horizontal_merged_cell_extra_count": sum(
                    max(int(_attr(node, "w", "val", "1")) - 1, 0)
                    for node in grid_spans
                    if _attr(node, "w", "val", "1").isdigit()
                ),
                "horizontal_merge_marker_count": len(horizontal_merge_markers),
                "horizontal_merge_region_count": len(grid_spans)
                + sum(_attr(node, "w", "val", "continue") == "restart" for node in horizontal_merge_markers),
                "vertical_merge_marker_count": len(vertical_merge_markers),
                "vertical_merge_region_count": sum(
                    _attr(node, "w", "val", "continue") == "restart" for node in vertical_merge_markers
                ),
                "vertical_merge_continuation_count": sum(
                    _attr(node, "w", "val", "continue") != "restart" for node in vertical_merge_markers
                ),
                "drawing_count": len(document.findall(".//w:drawing", NS)),
                "inline_drawing_count": len(document.findall(".//wp:inline", NS)),
                "anchored_drawing_count": len(document.findall(".//wp:anchor", NS)),
                "legacy_picture_count": len(document.findall(".//w:pict", NS)),
                "legacy_shape_count": len(document.findall(".//v:shape", NS)),
                "text_box_count": len(document.findall(".//w:txbxContent", NS)),
                "alt_chunk_count": len(document.findall(".//w:altChunk", NS)),
                "media_part_count": len(media_names),
                "chart_part_count": len([name for name in names if re.fullmatch(r"word/charts/chart\d+\.xml", name)]),
                "diagram_part_count": len(
                    [
                        name
                        for name in names
                        if name.startswith("word/diagrams/") and name.endswith(".xml")
                    ]
                ),
                "custom_xml_part_count": len(
                    [name for name in names if re.fullmatch(r"customXml/item\d+\.xml", name)]
                ),
                "ole_object_count": len(document.findall(".//w:object", NS)),
                "embedding_part_count": len(embedding_names),
                "math_paragraph_count": len(document.findall(".//m:oMathPara", NS)),
                "math_object_count": len(document.findall(".//m:oMath", NS)),
                "bookmark_count": len(document.findall(".//w:bookmarkStart", NS)),
                "content_control_count": len(document.findall(".//w:sdt", NS)),
                "hyperlink_count": len(document.findall(".//w:hyperlink", NS)),
                "comment_count": _child_count(_read_xml(archive, "word/comments.xml"), "./w:comment"),
                "footnote_count": _note_count(_read_xml(archive, "word/footnotes.xml"), "footnote"),
                "endnote_count": _note_count(_read_xml(archive, "word/endnotes.xml"), "endnote"),
                "tracked_insertion_count": len(document.findall(".//w:ins", NS)),
                "tracked_deletion_count": len(document.findall(".//w:del", NS)),
                "section_count": len(section_geometry),
                "explicit_page_break_count": len(document.findall(".//w:br[@w:type='page']", NS)),
                "rendered_page_break_count": len(document.findall(".//w:lastRenderedPageBreak", NS)),
                "header_part_count": len(header_names),
                "footer_part_count": len(footer_names),
                "numbering_definition_count": _child_count(_read_xml(archive, "word/numbering.xml"), "./w:num"),
                "paragraph_style_count": sum(row.get("type") == "paragraph" for row in style_catalog.values()),
                "character_style_count": sum(row.get("type") == "character" for row in style_catalog.values()),
            }
            report.update(
                {
                    "package": {
                        "part_count": len(names),
                        "missing_required_parts": missing_parts,
                        "has_macros": any(name.endswith("vbaProject.bin") for name in names),
                        "relationship_type_counts": relation_counts,
                        "external_relationship_count": external_relations,
                        "update_fields_on_open": _attr(
                            settings.find("./w:updateFields", NS) if settings is not None else None,
                            "w",
                            "val",
                        ),
                        "font_names": sorted(
                            filter(
                                None,
                                (
                                    _attr(node, "w", "name")
                                    for node in (font_table.findall("./w:font", NS) if font_table is not None else [])
                                ),
                            )
                        ),
                    },
                    "properties": _app_properties(_read_xml(archive, "docProps/app.xml")),
                    "metrics": metrics,
                    "field_type_counts": _field_counts(field_instructions),
                    "field_instructions": field_instructions,
                    "paragraph_style_usage": dict(sorted(paragraph_styles.items())),
                    "heading_sequence": heading_sequence,
                    "bookmark_names": bookmark_names,
                    "section_geometry": section_geometry,
                    "text_sha256": _sha256(text),
                    "structure_sha256": _structure_signature(
                        document,
                        heading_levels,
                        native_object_sha256,
                    ),
                    "native_object_sha256": native_object_sha256,
                    "media_sha256": {name: _sha256(archive.read(name)) for name in media_names},
                    "embedding_sha256": {name: _sha256(archive.read(name)) for name in embedding_names},
                }
            )
    except (BadZipFile, ET.ParseError) as exc:
        report["errors"].append(f"invalid_docx:{type(exc).__name__}")

    report["status"] = "passed" if not report["errors"] else "failed"
    return report


def audit_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser()
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    documents: list[dict[str, Any]] = []
    for item in manifest.get("documents", []):
        audit = audit_docx(item["path"], expected_sha256=str(item.get("expected_sha256") or ""))
        documents.append(
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "authority_role": item.get("authority_role", ""),
                "authority_evidence": item.get("authority_evidence", []),
                "notes": item.get("notes", []),
                **audit,
            }
        )
    report: dict[str, Any] = {
        "schema": "openclaw.word-fidelity-gold-baseline.v1",
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(raw),
        "status": "passed" if documents and all(row["status"] == "passed" for row in documents) else "failed",
        "documents": documents,
        "acceptance_profiles": manifest.get("acceptance_profiles", {}),
    }
    report["report_sha256"] = _canonical_sha256(
        {key: value for key, value in report.items() if key != "manifest_path"}
    )
    return report
