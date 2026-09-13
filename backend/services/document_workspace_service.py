"""Versioned Markdown workspace for long-form document projects."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from knowledge_manager import knowledge_manager
from services.document_outline_service import (
    build_document_directory,
    build_document_structure_snapshot,
    compare_document_structures,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in {"-", "_", " ", "·", "—"} else "-"
        for ch in value.strip()
    )
    return cleaned.strip(" -") or "document-project"


def _slug(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
    return normalized or hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
_MARKDOWN_DESTINATION_RE = re.compile(
    r'''^(?P<path>\S+?)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*$'''
)


def _markdown_destination(value: str) -> str:
    """Return the URL portion of a Markdown destination without its optional title."""
    raw = value.strip()
    if raw.startswith("<"):
        closing = raw.find(">")
        return raw[1:closing].strip() if closing > 0 else raw
    match = _MARKDOWN_DESTINATION_RE.fullmatch(raw)
    return str(match.group("path") if match else raw).strip()


def _markdown_image_paths(markdown: str) -> list[str]:
    return list(dict.fromkeys(
        path
        for path in (_markdown_destination(match) for match in _MARKDOWN_IMAGE_RE.findall(markdown))
        if path
    ))


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


def _chapter_number(value: str) -> int | None:
    """Read Arabic or common Chinese chapter numbers from a heading."""
    match = re.search(r"第\s*([0-9零〇一二三四五六七八九十百]+)\s*章", value or "")
    if not match:
        return None
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
            return None
    return total + current or None


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
PPR_PROPERTY_ORDER = (
    "pStyle",
    "keepNext",
    "keepLines",
    "pageBreakBefore",
    "framePr",
    "widowControl",
    "numPr",
    "suppressLineNumbers",
    "pBdr",
    "shd",
    "tabs",
    "suppressAutoHyphens",
    "kinsoku",
    "wordWrap",
    "overflowPunct",
    "topLinePunct",
    "autoSpaceDE",
    "autoSpaceDN",
    "bidi",
    "adjustRightInd",
    "snapToGrid",
    "spacing",
    "ind",
    "contextualSpacing",
    "mirrorIndents",
    "suppressOverlap",
    "jc",
    "textDirection",
    "textAlignment",
    "textboxTightWrap",
    "outlineLvl",
    "divId",
    "cnfStyle",
    "rPr",
    "sectPr",
    "pPrChange",
)
TRPR_PROPERTY_ORDER = (
    "cnfStyle",
    "divId",
    "gridBefore",
    "gridAfter",
    "wBefore",
    "wAfter",
    "cantSplit",
    "trHeight",
    "tblHeader",
    "tblCellSpacing",
    "jc",
    "hidden",
    "ins",
    "del",
    "trPrChange",
)
TBLPR_PROPERTY_ORDER = (
    "tblStyle",
    "tblpPr",
    "tblOverlap",
    "bidiVisual",
    "tblStyleRowBandSize",
    "tblStyleColBandSize",
    "tblW",
    "jc",
    "tblCellSpacing",
    "tblInd",
    "tblBorders",
    "shd",
    "tblLayout",
    "tblCellMar",
    "tblLook",
    "tblCaption",
    "tblDescription",
    "tblPrChange",
)
TCPR_PROPERTY_ORDER = (
    "cnfStyle",
    "tcW",
    "gridSpan",
    "hMerge",
    "vMerge",
    "tcBorders",
    "shd",
    "noWrap",
    "tcMar",
    "textDirection",
    "tcFitText",
    "vAlign",
    "hideMark",
    "headers",
    "cellIns",
    "cellDel",
    "cellMerge",
    "tcPrChange",
)
SECTPR_PROPERTY_ORDER = (
    "headerReference",
    "footerReference",
    "footnotePr",
    "endnotePr",
    "type",
    "pgSz",
    "pgMar",
    "paperSrc",
    "pgBorders",
    "lnNumType",
    "pgNumType",
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
    "sectPrChange",
)
for _prefix, _namespace in {
    "w": W_NS,
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
    "w10": "urn:schemas-microsoft-com:office:word",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}.items():
    ET.register_namespace(_prefix, _namespace)


def _word_property(parent: ET.Element, tag: str) -> ET.Element:
    element = parent.find(f"{W}{tag}")
    if element is None:
        element = ET.SubElement(parent, f"{W}{tag}")
    return element


def _ordered_word_property(
    parent: ET.Element,
    tag: str,
    property_order: tuple[str, ...],
) -> ET.Element:
    element = parent.find(f"{W}{tag}")
    if element is not None:
        return element
    element = ET.Element(f"{W}{tag}")
    target_order = property_order.index(tag)
    for index, child in enumerate(parent):
        child_tag = child.tag.rsplit("}", 1)[-1]
        if child_tag in property_order and property_order.index(child_tag) > target_order:
            parent.insert(index, element)
            return element
    parent.append(element)
    return element


def _paragraph_properties(paragraph: ET.Element) -> ET.Element:
    properties = paragraph.find(f"{W}pPr")
    if properties is None:
        properties = ET.Element(f"{W}pPr")
        paragraph.insert(0, properties)
    return properties


def _table_properties(table: ET.Element) -> ET.Element:
    properties = table.find(f"./{W}tblPr")
    if properties is None:
        properties = ET.Element(f"{W}tblPr")
        table.insert(0, properties)
    return properties


def _cell_properties(cell: ET.Element) -> ET.Element:
    properties = cell.find(f"./{W}tcPr")
    if properties is None:
        properties = ET.Element(f"{W}tcPr")
        cell.insert(0, properties)
    return properties


def _set_table_print_layout(table: ET.Element) -> None:
    """Give every table deterministic width, columns and visible print borders."""
    table_properties = _table_properties(table)
    table_style = _ordered_word_property(
        table_properties,
        "tblStyle",
        TBLPR_PROPERTY_ORDER,
    )
    table_style.set(f"{W}val", "TableGrid")
    table_width = _ordered_word_property(
        table_properties,
        "tblW",
        TBLPR_PROPERTY_ORDER,
    )
    table_width.set(f"{W}type", "pct")
    table_width.set(f"{W}w", "5000")
    table_layout = _ordered_word_property(
        table_properties,
        "tblLayout",
        TBLPR_PROPERTY_ORDER,
    )
    table_layout.set(f"{W}type", "fixed")

    borders = _ordered_word_property(
        table_properties,
        "tblBorders",
        TBLPR_PROPERTY_ORDER,
    )
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = borders.find(f"{W}{edge}")
        if border is None:
            border = ET.SubElement(borders, f"{W}{edge}")
        border.set(f"{W}val", "single")
        border.set(f"{W}sz", "4")
        border.set(f"{W}space", "0")
        border.set(f"{W}color", "808080")

    grid = table.find(f"./{W}tblGrid")
    grid_widths: list[int] = []
    if grid is not None:
        for column in grid.findall(f"./{W}gridCol"):
            try:
                grid_widths.append(max(1, int(column.get(f"{W}w", "0"))))
            except ValueError:
                grid_widths.append(1)
    if not grid_widths:
        first_row = table.find(f"./{W}tr")
        column_count = len(first_row.findall(f"./{W}tc")) if first_row is not None else 0
        grid_widths = [7920 // column_count] * column_count if column_count else []

    for row in table.findall(f"./{W}tr"):
        grid_index = 0
        for cell in row.findall(f"./{W}tc"):
            cell_properties = _cell_properties(cell)
            grid_span = cell_properties.find(f"./{W}gridSpan")
            try:
                span = max(1, int(grid_span.get(f"{W}val", "1"))) if grid_span is not None else 1
            except ValueError:
                span = 1
            width = sum(grid_widths[grid_index : grid_index + span])
            if width <= 0:
                width = max(1, 7920 // max(1, len(row.findall(f"./{W}tc"))))
            cell_width = _ordered_word_property(
                cell_properties,
                "tcW",
                TCPR_PROPERTY_ORDER,
            )
            cell_width.set(f"{W}type", "dxa")
            cell_width.set(f"{W}w", str(width))
            grid_index += span

    for paragraph in table.findall(f".//{W}p"):
        paragraph_properties = _paragraph_properties(paragraph)
        paragraph_style = paragraph_properties.find(f"./{W}pStyle")
        if paragraph_style is not None and paragraph_style.get(f"{W}val") == "Compact":
            # Pandoc emits Compact even when the reference DOCX does not define it.
            # Word falls back gracefully; LibreOffice can separate cell text from the
            # table grid during PDF conversion, so use an explicit existing style.
            paragraph_style.set(f"{W}val", "Normal")
        spacing = _ordered_word_property(
            paragraph_properties,
            "spacing",
            PPR_PROPERTY_ORDER,
        )
        spacing.set(f"{W}after", "0")
        spacing.set(f"{W}line", "240")
        spacing.set(f"{W}lineRule", "auto")
        indentation = _ordered_word_property(
            paragraph_properties,
            "ind",
            PPR_PROPERTY_ORDER,
        )
        indentation.set(f"{W}firstLine", "0")


def _set_page_break_before(paragraph: ET.Element) -> None:
    page_break = _ordered_word_property(
        _paragraph_properties(paragraph),
        "pageBreakBefore",
        PPR_PROPERTY_ORDER,
    )
    page_break.set(f"{W}val", "1")


def _postprocess_standard_a4_docx(path: Path) -> None:
    """Set every Word section to A4 while preserving its current orientation."""
    with ZipFile(path, "r") as source:
        parts = {
            entry.filename: (entry, source.read(entry.filename))
            for entry in source.infolist()
        }
    document_entry, document_payload = parts["word/document.xml"]
    document_root = ET.fromstring(document_payload)

    for section in document_root.findall(f".//{W}sectPr"):
        page_size = _ordered_word_property(
            section,
            "pgSz",
            SECTPR_PROPERTY_ORDER,
        )
        landscape = page_size.get(f"{W}orient") == "landscape"
        page_size.set(f"{W}w", "16838" if landscape else "11906")
        page_size.set(f"{W}h", "11906" if landscape else "16838")

    parts["word/document.xml"] = (
        document_entry,
        ET.tostring(document_root, encoding="utf-8", xml_declaration=True),
    )
    with tempfile.NamedTemporaryFile(
        suffix=".docx",
        prefix="standard-a4-",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            for entry, payload in parts.values():
                target.writestr(entry, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _enable_word_field_refresh(path: Path) -> None:
    """Ask Word to refresh dynamic fields without changing reference formatting.

    A reference DOCX owns the visual layout. This deliberately touches only
    ``word/settings.xml`` so the table of contents, page numbers, and other
    fields can refresh when the candidate is opened in Word.
    """
    with ZipFile(path, "r") as source:
        parts = {
            entry.filename: (entry, source.read(entry.filename))
            for entry in source.infolist()
        }
    settings_entry, settings_payload = parts["word/settings.xml"]
    settings_root = ET.fromstring(settings_payload)
    _word_property(settings_root, "updateFields").set(f"{W}val", "true")
    parts["word/settings.xml"] = (
        settings_entry,
        ET.tostring(settings_root, encoding="utf-8", xml_declaration=True),
    )

    with tempfile.NamedTemporaryFile(
        suffix=".docx",
        prefix="word-field-refresh-",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            for entry, payload in parts.values():
                target.writestr(entry, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _set_style_font(
    style: ET.Element,
    *,
    east_asia: str,
    latin: str,
    size_half_points: str,
    bold: bool = False,
) -> None:
    run_properties = style.find(f"./{W}rPr")
    if run_properties is None:
        run_properties = ET.SubElement(style, f"{W}rPr")
    fonts = _word_property(run_properties, "rFonts")
    for key, value in {"ascii": latin, "hAnsi": latin, "eastAsia": east_asia, "cs": latin}.items():
        fonts.set(f"{W}{key}", value)
    size = _word_property(run_properties, "sz")
    size.set(f"{W}val", size_half_points)
    complex_size = _word_property(run_properties, "szCs")
    complex_size.set(f"{W}val", size_half_points)
    color = _word_property(run_properties, "color")
    color.set(f"{W}val", "000000")
    existing_bold = run_properties.find(f"./{W}b")
    if bold:
        if existing_bold is None:
            existing_bold = ET.SubElement(run_properties, f"{W}b")
        existing_bold.set(f"{W}val", "1")
    elif existing_bold is not None:
        run_properties.remove(existing_bold)


def _set_style_paragraph(
    style: ET.Element,
    *,
    before: str = "0",
    after: str = "0",
    line: str = "360",
    line_rule: str = "exact",
    first_line: str = "0",
    alignment: str = "both",
    keep_next: bool = False,
    page_break_before: bool = False,
) -> None:
    properties = style.find(f"./{W}pPr")
    if properties is None:
        properties = ET.SubElement(style, f"{W}pPr")
    spacing = _word_property(properties, "spacing")
    spacing.set(f"{W}before", before)
    spacing.set(f"{W}after", after)
    spacing.set(f"{W}line", line)
    spacing.set(f"{W}lineRule", line_rule)
    indentation = _word_property(properties, "ind")
    indentation.set(f"{W}firstLine", first_line)
    justification = _word_property(properties, "jc")
    justification.set(f"{W}val", alignment)
    if keep_next:
        _word_property(properties, "keepNext").set(f"{W}val", "1")
    if page_break_before:
        _word_property(properties, "pageBreakBefore").set(f"{W}val", "1")


def _cover_paragraph(
    text: str,
    *,
    style_id: str = "Normal",
    before: str = "0",
    bold: bool = False,
    size: str = "24",
    page_break_after: bool = False,
) -> ET.Element:
    paragraph = ET.Element(f"{W}p")
    properties = ET.SubElement(paragraph, f"{W}pPr")
    style = ET.SubElement(properties, f"{W}pStyle")
    style.set(f"{W}val", style_id)
    spacing = ET.SubElement(properties, f"{W}spacing")
    spacing.set(f"{W}before", before)
    spacing.set(f"{W}after", "0")
    justification = ET.SubElement(properties, f"{W}jc")
    justification.set(f"{W}val", "center")
    run = ET.SubElement(paragraph, f"{W}r")
    run_properties = ET.SubElement(run, f"{W}rPr")
    fonts = ET.SubElement(run_properties, f"{W}rFonts")
    fonts.set(f"{W}ascii", "Times New Roman")
    fonts.set(f"{W}hAnsi", "Times New Roman")
    fonts.set(f"{W}eastAsia", "宋体")
    if bold:
        ET.SubElement(run_properties, f"{W}b").set(f"{W}val", "1")
    ET.SubElement(run_properties, f"{W}sz").set(f"{W}val", size)
    ET.SubElement(run_properties, f"{W}szCs").set(f"{W}val", size)
    node = ET.SubElement(run, f"{W}t")
    node.text = text
    if page_break_after:
        break_run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(break_run, f"{W}br").set(f"{W}type", "page")
    return paragraph


def _footer_payload(root: ET.Element) -> bytes:
    for child in list(root):
        root.remove(child)
    paragraph = ET.SubElement(root, f"{W}p")
    properties = ET.SubElement(paragraph, f"{W}pPr")
    ET.SubElement(properties, f"{W}jc").set(f"{W}val", "center")
    for value in ("- ",):
        run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(run, f"{W}t").text = value
    begin = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(begin, f"{W}fldChar").set(f"{W}fldCharType", "begin")
    instruction = ET.SubElement(paragraph, f"{W}r")
    field = ET.SubElement(instruction, f"{W}instrText")
    field.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    field.text = " PAGE "
    separate = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(separate, f"{W}fldChar").set(f"{W}fldCharType", "separate")
    cached = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(cached, f"{W}t").text = "1"
    end = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(end, f"{W}fldChar").set(f"{W}fldCharType", "end")
    suffix = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(suffix, f"{W}t").text = " -"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _libreoffice_preview_env(profile_dir: Path) -> dict[str, str]:
    """Map formal Windows font names for macOS/Linux previews only."""
    cache_dir = profile_dir / "font-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    config = profile_dir / "fonts.conf"
    config.write_text(
        f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/System/Library/Fonts</dir><dir>/Library/Fonts</dir><dir>{Path.home() / 'Library/Fonts'}</dir>
  <dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir>
  <cachedir>{cache_dir}</cachedir>
  <alias><family>宋体</family><prefer><family>Songti SC</family><family>Noto Serif CJK SC</family><family>STSong</family></prefer></alias>
  <alias><family>SimSun</family><prefer><family>Songti SC</family><family>Noto Serif CJK SC</family><family>STSong</family></prefer></alias>
  <alias><family>黑体</family><prefer><family>Heiti SC</family><family>Noto Sans CJK SC</family><family>STHeiti</family></prefer></alias>
  <alias><family>SimHei</family><prefer><family>Heiti SC</family><family>Noto Sans CJK SC</family><family>STHeiti</family></prefer></alias>
</fontconfig>
""",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["FONTCONFIG_FILE"] = str(config)
    return environment


def _field_run(paragraph: ET.Element, instruction: str, cached: str = "0") -> None:
    begin = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(begin, f"{W}fldChar").set(f"{W}fldCharType", "begin")
    instruction_run = ET.SubElement(paragraph, f"{W}r")
    instruction_node = ET.SubElement(instruction_run, f"{W}instrText")
    instruction_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instruction_node.text = f" {instruction} "
    separate = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(separate, f"{W}fldChar").set(f"{W}fldCharType", "separate")
    cached_run = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(cached_run, f"{W}t").text = cached
    end = ET.SubElement(paragraph, f"{W}r")
    ET.SubElement(end, f"{W}fldChar").set(f"{W}fldCharType", "end")


def _materialize_toc_cache(
    document_root: ET.Element,
    style_names: dict[str, str],
    toc_style_ids: dict[int, str],
) -> None:
    """Give headless PDF previews a visible TOC while retaining a real TOC field."""
    entries: list[tuple[int, str, str]] = []
    bookmark_id = 10000
    for paragraph in document_root.findall(f".//{W}p"):
        style = paragraph.find(f"./{W}pPr/{W}pStyle")
        style_id = style.get(f"{W}val", "") if style is not None else ""
        normalized = style_names.get(style_id, style_id).replace(" ", "")
        if normalized not in {"heading1", "heading2", "heading3"}:
            continue
        text = "".join(node.text or "" for node in paragraph.findall(f".//{W}t")).strip()
        if not text:
            continue
        level = int(normalized[-1])
        anchor = f"toc_anchor_{bookmark_id}"
        start = ET.Element(f"{W}bookmarkStart")
        start.set(f"{W}id", str(bookmark_id))
        start.set(f"{W}name", anchor)
        end = ET.Element(f"{W}bookmarkEnd")
        end.set(f"{W}id", str(bookmark_id))
        insert_at = 1 if paragraph.find(f"./{W}pPr") is not None else 0
        paragraph.insert(insert_at, start)
        paragraph.append(end)
        entries.append((level, text, anchor))
        bookmark_id += 1
    toc = next(
        (
            node
            for node in document_root.findall(f".//{W}sdt")
            if node.find(f"./{W}sdtPr/{W}docPartObj/{W}docPartGallery") is not None
            and node.find(f"./{W}sdtPr/{W}docPartObj/{W}docPartGallery").get(f"{W}val") == "Table of Contents"
        ),
        None,
    )
    if toc is None or not entries:
        return
    content = toc.find(f"./{W}sdtContent")
    if content is None:
        return
    title = content.find(f"./{W}p")
    for child in list(content):
        content.remove(child)
    if title is not None:
        content.append(title)
    field_start = ET.SubElement(content, f"{W}p")
    begin_run = ET.SubElement(field_start, f"{W}r")
    ET.SubElement(begin_run, f"{W}fldChar").set(f"{W}fldCharType", "begin")
    instruction_run = ET.SubElement(field_start, f"{W}r")
    instruction = ET.SubElement(instruction_run, f"{W}instrText")
    instruction.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instruction.text = ' TOC \\o "1-3" \\h \\z \\u '
    separate_run = ET.SubElement(field_start, f"{W}r")
    ET.SubElement(separate_run, f"{W}fldChar").set(f"{W}fldCharType", "separate")
    for level, text, anchor in entries:
        paragraph = ET.SubElement(content, f"{W}p")
        properties = ET.SubElement(paragraph, f"{W}pPr")
        style = ET.SubElement(properties, f"{W}pStyle")
        style.set(f"{W}val", toc_style_ids.get(level, "TOC1"))
        text_run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(text_run, f"{W}t").text = text
        tab_run = ET.SubElement(paragraph, f"{W}r")
        ET.SubElement(tab_run, f"{W}tab")
        _field_run(paragraph, f"PAGEREF {anchor} \\h")
    field_end = ET.SubElement(content, f"{W}p")
    end_run = ET.SubElement(field_end, f"{W}r")
    ET.SubElement(end_run, f"{W}fldChar").set(f"{W}fldCharType", "end")


def _refresh_toc_cache_from_pdf(docx_path: Path, pdf_path: Path) -> bool:
    """Use native PDFKit text extraction to cache accurate TOC page numbers."""
    script = (
        'ObjC.import("PDFKit"); ObjC.import("Foundation");'
        f'var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath({json.dumps(str(pdf_path))}));'
        'var a=[]; for(var i=0;i<d.pageCount;i++){a.push(ObjC.unwrap(d.pageAtIndex(i).string)||"");}'
        'JSON.stringify(a);'
    )
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=180,
        )
        page_texts = json.loads(result.stdout.strip()) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(page_texts, list) or not page_texts:
        return False
    normalized_pages = [re.sub(r"\s+", "", str(text)) for text in page_texts]
    normalized_lines = [
        {
            re.sub(r"\s+", "", line)
            for line in str(text).splitlines()
            if re.sub(r"\s+", "", line)
        }
        for text in page_texts
    ]
    with ZipFile(docx_path, "r") as source:
        parts = {entry.filename: (entry, source.read(entry.filename)) for entry in source.infolist()}
    document_entry, payload = parts["word/document.xml"]
    root = ET.fromstring(payload)
    page_by_anchor: dict[str, int] = {}
    for paragraph in root.findall(f".//{W}p"):
        bookmark = paragraph.find(f"./{W}bookmarkStart")
        if bookmark is None:
            continue
        anchor = str(bookmark.get(f"{W}name") or "")
        if not anchor.startswith("toc_anchor_"):
            continue
        text = re.sub(r"\s+", "", "".join(node.text or "" for node in paragraph.findall(f".//{W}t")))
        if not text:
            continue
        for page_index, page_lines in enumerate(normalized_lines):
            if text in page_lines:
                page_by_anchor[anchor] = page_index + 1
                break
        else:
            # Long headings can wrap across PDF text lines. Retain a conservative
            # fallback, but prefer the first body occurrence after the cover.
            for page_index, page_text in enumerate(normalized_pages[1:], start=2):
                if text in page_text:
                    page_by_anchor[anchor] = page_index
                    break
    changed = False
    for paragraph in root.findall(f".//{W}p"):
        instruction = next(
            (node.text or "" for node in paragraph.findall(f".//{W}instrText") if "PAGEREF toc_anchor_" in (node.text or "")),
            "",
        )
        match = re.search(r"PAGEREF\s+(toc_anchor_\d+)", instruction)
        if not match or match.group(1) not in page_by_anchor:
            continue
        texts = paragraph.findall(f".//{W}t")
        if texts:
            texts[-1].text = str(page_by_anchor[match.group(1)])
            changed = True
    if not changed:
        return False
    parts["word/document.xml"] = (document_entry, ET.tostring(root, encoding="utf-8", xml_declaration=True))
    with tempfile.NamedTemporaryFile(suffix=".docx", prefix="toc-cache-", dir=docx_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            for entry, part_payload in parts.values():
                target.writestr(entry, part_payload)
        temporary.replace(docx_path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _postprocess_formal_docx(path: Path, cover: dict[str, Any] | None = None) -> None:
    """Apply a reusable formal-document layout contract to a Pandoc DOCX."""
    with ZipFile(path, "r") as source:
        parts = {entry.filename: (entry, source.read(entry.filename)) for entry in source.infolist()}
    document_entry, document_payload = parts["word/document.xml"]
    styles_entry, styles_payload = parts["word/styles.xml"]
    settings_entry, settings_payload = parts["word/settings.xml"]
    document_root = ET.fromstring(document_payload)
    styles_root = ET.fromstring(styles_payload)
    settings_root = ET.fromstring(settings_payload)

    styles = {node.get(f"{W}styleId", ""): node for node in styles_root.findall(f"./{W}style")}
    def style_name(node: ET.Element) -> str:
        name_node = node.find(f"./{W}name")
        return str(name_node.get(f"{W}val", "") if name_node is not None else "").strip().lower()

    style_names = {style_id: style_name(node) for style_id, node in styles.items()}

    def styles_named(*names: str) -> list[ET.Element]:
        wanted = {name.strip().lower() for name in names}
        return [styles[style_id] for style_id, name in style_names.items() if name in wanted or style_id.lower() in wanted]

    for style in styles_named("Normal", "Body Text", "First Paragraph", "XT2_0正文"):
        _set_style_font(style, east_asia="宋体", latin="Times New Roman", size_half_points="21")
        _set_style_paragraph(style, first_line="430")
    heading_styles = {
        1: styles_named("Heading 1", "Heading1"),
        2: styles_named("Heading 2", "Heading2"),
        3: styles_named("Heading 3", "Heading3"),
    }
    for style in heading_styles[1]:
        _set_style_font(style, east_asia="黑体", latin="Times New Roman", size_half_points="28", bold=True)
        _set_style_paragraph(style, before="360", first_line="0", alignment="left", keep_next=True, page_break_before=True)
    for style in heading_styles[2]:
        _set_style_font(style, east_asia="黑体", latin="Times New Roman", size_half_points="24", bold=True)
        _set_style_paragraph(style, before="360", line="320", first_line="0", alignment="left", keep_next=True)
    for style in heading_styles[3]:
        _set_style_font(style, east_asia="宋体", latin="Times New Roman", size_half_points="21", bold=True)
        _set_style_paragraph(style, before="180", first_line="0", alignment="left", keep_next=True)
    for style in [*heading_styles[1], *heading_styles[2], *heading_styles[3]]:
        numbering = style.find(f"./{W}pPr/{W}numPr") if style is not None else None
        properties = style.find(f"./{W}pPr") if style is not None else None
        if numbering is not None and properties is not None:
            properties.remove(numbering)
    toc_style_ids: dict[int, str] = {}
    for index, indent in ((1, "0"), (2, "420"), (3, "960")):
        toc_styles = styles_named(f"TOC {index}", f"TOC{index}")
        if toc_styles:
            toc_style_ids[index] = toc_styles[0].get(f"{W}styleId", f"TOC{index}")
        for style in toc_styles:
            _set_style_font(style, east_asia="宋体", latin="Times New Roman", size_half_points="24")
            _set_style_paragraph(style, line="360", line_rule="auto", first_line="0", alignment="left")
            properties = style.find(f"./{W}pPr")
            _word_property(properties, "ind").set(f"{W}left", indent)
    for title_role in ("Title", "Subtitle"):
        for style in styles_named(title_role):
            _set_style_font(style, east_asia="黑体" if title_role == "Title" else "宋体", latin="Times New Roman", size_half_points="36" if title_role == "Title" else "24", bold=title_role == "Title")
            _set_style_paragraph(style, first_line="0", alignment="center")

    for section in document_root.findall(f".//{W}sectPr"):
        page_size = _ordered_word_property(section, "pgSz", SECTPR_PROPERTY_ORDER)
        page_size.set(f"{W}w", "11906")
        page_size.set(f"{W}h", "16838")
        page_size.attrib.pop(f"{W}orient", None)
        margins = _ordered_word_property(section, "pgMar", SECTPR_PROPERTY_ORDER)
        for key, value in {"top": "2098", "bottom": "1984", "left": "1587", "right": "1474", "header": "850", "footer": "907", "gutter": "0"}.items():
            margins.set(f"{W}{key}", value)
        _ordered_word_property(section, "titlePg", SECTPR_PROPERTY_ORDER).set(f"{W}val", "1")

    for paragraph in document_root.findall(f".//{W}p"):
        style = paragraph.find(f"./{W}pPr/{W}pStyle")
        style_id = style.get(f"{W}val", "") if style is not None else ""
        style_name = style_names.get(style_id, style_id).replace(" ", "")
        if style_name in {"heading1", "heading2", "heading3"}:
            properties = _paragraph_properties(paragraph)
            numbering = properties.find(f"./{W}numPr")
            if numbering is not None:
                properties.remove(numbering)
            keep = _ordered_word_property(properties, "keepNext", PPR_PROPERTY_ORDER)
            keep.set(f"{W}val", "1")
            if style_name == "heading1":
                _set_page_break_before(paragraph)
        if paragraph.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline") is not None:
            properties = _paragraph_properties(paragraph)
            spacing = _ordered_word_property(properties, "spacing", PPR_PROPERTY_ORDER)
            spacing.set(f"{W}before", "0")
            spacing.set(f"{W}after", "0")
            spacing.set(f"{W}line", "240")
            spacing.set(f"{W}lineRule", "auto")
            indentation = _ordered_word_property(properties, "ind", PPR_PROPERTY_ORDER)
            indentation.set(f"{W}left", "0")
            indentation.set(f"{W}right", "0")
            indentation.set(f"{W}firstLine", "0")
            _ordered_word_property(properties, "jc", PPR_PROPERTY_ORDER).set(f"{W}val", "center")

    _materialize_toc_cache(document_root, style_names, toc_style_ids)

    for table in document_root.findall(f".//{W}tbl"):
        _set_table_print_layout(table)
        for index, row in enumerate(table.findall(f"./{W}tr")):
            row_properties = row.find(f"./{W}trPr")
            if row_properties is None:
                row_properties = ET.Element(f"{W}trPr")
                row.insert(0, row_properties)
            _ordered_word_property(row_properties, "cantSplit", TRPR_PROPERTY_ORDER).set(f"{W}val", "1")
            if index == 0:
                _ordered_word_property(row_properties, "tblHeader", TRPR_PROPERTY_ORDER).set(f"{W}val", "1")

    cover = cover or {}
    body = document_root.find(f"./{W}body")
    if body is not None and cover.get("title"):
        normal_styles = styles_named("Normal", "XT2_0正文")
        normal_style_id = normal_styles[0].get(f"{W}styleId", "Normal") if normal_styles else "Normal"
        title_styles = styles_named("Title")
        title_style_id = title_styles[0].get(f"{W}styleId", "Title") if title_styles else "Title"
        cover_nodes = [
            _cover_paragraph(str(cover.get("title") or ""), style_id=title_style_id, before="1680", bold=True, size="36"),
            _cover_paragraph(str(cover.get("author") or ""), style_id=normal_style_id, before="1040", size="24"),
            _cover_paragraph(f"指导教师：{cover.get('advisor', '')} {cover.get('advisor_title', '')}".strip(), style_id=normal_style_id, before="360", size="24"),
            _cover_paragraph(str(cover.get("institution") or ""), style_id=normal_style_id, before="180", size="24"),
            _cover_paragraph(str(cover.get("date") or ""), style_id=normal_style_id, before="720", size="24", page_break_after=True),
        ]
        for index, paragraph in reversed(list(enumerate(cover_nodes))):
            body.insert(0, paragraph)

    _word_property(settings_root, "updateFields").set(f"{W}val", "true")
    parts["word/document.xml"] = (document_entry, ET.tostring(document_root, encoding="utf-8", xml_declaration=True))
    parts["word/styles.xml"] = (styles_entry, ET.tostring(styles_root, encoding="utf-8", xml_declaration=True))
    parts["word/settings.xml"] = (settings_entry, ET.tostring(settings_root, encoding="utf-8", xml_declaration=True))
    for name, (entry, payload) in list(parts.items()):
        if name.startswith("word/header") and name.endswith(".xml"):
            root = ET.fromstring(payload)
            for child in list(root):
                root.remove(child)
            ET.SubElement(root, f"{W}p")
            parts[name] = (entry, ET.tostring(root, encoding="utf-8", xml_declaration=True))
        elif name.startswith("word/footer") and name.endswith(".xml"):
            parts[name] = (entry, _footer_payload(ET.fromstring(payload)))

    with tempfile.NamedTemporaryFile(suffix=".docx", prefix="formal-layout-", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            for entry, payload in parts.values():
                target.writestr(entry, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _postprocess_wargame_docx(path: Path) -> None:
    """Apply print-safe pagination and table behavior without a runtime Office dependency."""
    with ZipFile(path, "r") as source:
        parts = {
            entry.filename: (entry, source.read(entry.filename))
            for entry in source.infolist()
        }
    document_entry, document_payload = parts["word/document.xml"]
    settings_entry, settings_payload = parts["word/settings.xml"]
    document_root = ET.fromstring(document_payload)
    settings_root = ET.fromstring(settings_payload)

    for paragraph in document_root.findall(f".//{W}p"):
        text = "".join(node.text or "" for node in paragraph.findall(f".//{W}t")).strip()
        style = paragraph.find(f"./{W}pPr/{W}pStyle")
        style_id = style.get(f"{W}val", "") if style is not None else ""
        if text == "目录" or text.startswith("想定名称：") or style_id == "Heading1":
            _set_page_break_before(paragraph)
        if style_id == "Heading1":
            keep_next = _ordered_word_property(
                _paragraph_properties(paragraph),
                "keepNext",
                PPR_PROPERTY_ORDER,
            )
            keep_next.set(f"{W}val", "1")

    for table in document_root.findall(f".//{W}tbl"):
        _set_table_print_layout(table)
        rows = table.findall(f"./{W}tr")
        for index, row in enumerate(rows):
            row_properties = row.find(f"./{W}trPr")
            if row_properties is None:
                row_properties = ET.Element(f"{W}trPr")
                row.insert(0, row_properties)
            cant_split = _ordered_word_property(
                row_properties,
                "cantSplit",
                TRPR_PROPERTY_ORDER,
            )
            cant_split.set(f"{W}val", "1")
            if index == 0:
                repeat = _ordered_word_property(
                    row_properties,
                    "tblHeader",
                    TRPR_PROPERTY_ORDER,
                )
                repeat.set(f"{W}val", "1")

    update_fields = _word_property(settings_root, "updateFields")
    update_fields.set(f"{W}val", "true")
    parts["word/document.xml"] = (
        document_entry,
        ET.tostring(document_root, encoding="utf-8", xml_declaration=True),
    )
    parts["word/settings.xml"] = (
        settings_entry,
        ET.tostring(settings_root, encoding="utf-8", xml_declaration=True),
    )

    with tempfile.NamedTemporaryFile(
        suffix=".docx",
        prefix="wargame-print-",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as target:
            for entry, payload in parts.values():
                target.writestr(entry, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class DocumentWorkspaceError(RuntimeError):
    pass


class DocumentVersionConflict(DocumentWorkspaceError):
    pass


class DocumentProductionBlocked(DocumentWorkspaceError):
    def __init__(self, message: str, blockers: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.blockers = blockers or []


class DocumentWorkspaceService:
    def __init__(self) -> None:
        self.vault = knowledge_manager.vault_path.resolve()

    def _workspace_root(self, project: dict[str, Any]) -> Path:
        override = str(project.get("_workspace_root_override") or "").strip()
        if override:
            resolved = Path(override).resolve()
            try:
                resolved.relative_to(self.vault)
            except ValueError as exc:
                raise DocumentWorkspaceError("文档工作区必须位于知识库内") from exc
            return resolved
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
            previous_source_word = Path(str(manifest.get("source_word") or ""))
            source_word = self._find_source_word(project)
            if source_word is None and previous_source_word.is_file():
                source_word = previous_source_word.resolve()
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
            title = heading["title"]
            section_id = f"section-{index + 1:02d}-{_slug(title)[:48]}"
            outline = [
                {
                    "id": f"outline-{item['line'] + 1}",
                    "title": item["title"],
                    "level": item["level"],
                    "line": item["line"] + 1,
                    "local_line": item["line"] - start + 1,
                    "anchor": _slug(item["title"]),
                    "target_id": f"{section_id}-heading-{item['line'] - start + 1}",
                }
                for item in headings
                if start < item["line"] < end and item["level"] <= 4
            ]
            sections.append({
                "id": section_id,
                "title": title,
                "kind": self._section_kind(title),
                "order_index": index,
                "start_line": start + 1,
                "end_line": end,
                "target_id": f"{section_id}-heading-1",
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

    def _directory(
        self,
        sections: list[dict[str, Any]],
        document_title: str,
        document_id: str = "",
    ) -> list[dict[str, Any]]:
        return build_document_directory(sections, document_title, document_id=document_id)

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
        document_title = str(
            project.get("_document_title") or project.get("name") or "正文文档"
        )
        current_structure = build_document_structure_snapshot(
            sections,
            document_title=document_title,
            version=int(manifest.get("version") or 1),
            source_path=_relative(Path(manifest["working_markdown"]), self.vault),
            source_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            generated_at=str(manifest.get("updated_at") or ""),
        )
        spec = (
            project.get("document_spec")
            if isinstance(project.get("document_spec"), dict)
            else {}
        )
        structure_sync = compare_document_structures(
            current_structure,
            spec.get("target_structure"),
        )
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
            "current_structure": current_structure,
            "structure_sync": structure_sync,
            "sections": [{key: value for key, value in row.items() if key != "content"} for row in sections],
            "directory": self._directory(
                sections,
                document_title,
                str(project.get("_document_id") or project.get("id") or ""),
            ),
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
            "asset_paths": _markdown_image_paths(row["content"]),
        }

    def fulltext(self, project: dict[str, Any]) -> dict[str, Any]:
        manifest, markdown, _ = self._read(project)
        return {
            "content": markdown,
            "version": manifest["version"],
            "asset_paths": _markdown_image_paths(markdown),
        }

    def update_section(self, project: dict[str, Any], section_id: str, content: str, expected_version: int, actor: str) -> dict[str, Any]:
        updated_section: dict[str, Any] | None = None
        next_version = expected_version
        with self._lock_path(project).open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            manifest = self._load_manifest(project)
            if manifest.get("content_authority") == "structured_json":
                raise DocumentVersionConflict(
                    "该文档已启用结构化协同编辑，旧 Markdown 章节接口仅提供只读兼容"
                )
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
            if replacement and row["end_line"] < len(lines) and lines[row["end_line"]].lstrip().startswith("#"):
                replacement.append("")
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
            "asset_paths": _markdown_image_paths(updated_section["content"]),
        }

    def apply_structured_projection(
        self,
        project: dict[str, Any],
        markdown: str,
        document_revision: int,
        actor: str,
        *,
        checkpoint_label: str = "",
    ) -> dict[str, Any]:
        """Replace the Markdown compatibility projection without touching source files."""
        self.ensure_workspace(project)
        with self._lock_path(project).open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            manifest = self._load_manifest(project)
            projected_revision = int(manifest.get("structured_projection_revision") or 0)
            if projected_revision > document_revision:
                raise DocumentVersionConflict(
                    f"Markdown 投影已更新到修订 {projected_revision}，拒绝写入旧修订 {document_revision}"
                )
            working = Path(manifest["working_markdown"])
            if checkpoint_label and working.is_file():
                safe_label = _safe_name(checkpoint_label)[:80] or "checkpoint"
                checkpoint = (
                    self._workspace_root(project)
                    / "versions"
                    / f"r{document_revision:06d}-{safe_label}.md"
                )
                if not checkpoint.exists():
                    shutil.copy2(working, checkpoint)
            working.write_text(markdown.strip() + "\n", encoding="utf-8")
            sections = self._parse_sections(markdown)
            manifest.update({
                "content_authority": "structured_json",
                "authority_schema_version": "tiptap-json-v2",
                "structured_projection_revision": document_revision,
                "projection_status": "current",
                "projection_error": "",
                "version": document_revision,
                "last_actor": actor,
                "stats": self._stats(markdown, sections),
            })
            self._write_manifest(project, manifest)
            return copy.deepcopy(manifest)

    def mark_structured_projection_stale(
        self,
        project: dict[str, Any],
        document_revision: int,
        error: str,
    ) -> None:
        """Record projection failure while leaving structured JSON authoritative."""
        self.ensure_workspace(project)
        with self._lock_path(project).open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            manifest = self._load_manifest(project)
            manifest.update({
                "content_authority": "structured_json",
                "authority_schema_version": "tiptap-json-v2",
                "structured_projection_revision": min(
                    int(manifest.get("structured_projection_revision") or 0),
                    document_revision,
                ),
                "projection_status": "stale",
                "projection_error": error[:2000],
            })
            self._write_manifest(project, manifest)

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
        raw = _markdown_destination(raw_path).split("#", 1)[0]
        if raw.startswith(("http://", "https://", "data:")):
            raise DocumentWorkspaceError("外部资源不由本地文档服务代理")
        base = Path(manifest["source_base_dir"])
        formal_assets = base / "论文章节" / "正式稿" / "assets"
        working_markdown = Path(str(manifest.get("working_markdown") or ""))
        isolated_assets = working_markdown.parent.parent / "source" / "assets"
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
            isolated_assets / raw.lstrip("./").removeprefix("assets/"),
            isolated_assets / filename,
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
        for raw_path in _markdown_image_paths(markdown):
            try:
                self._resolve_asset(manifest, raw_path)
            except DocumentWorkspaceError:
                unresolved_assets.append(raw_path)
        chapter_numbers = {
            number
            for row in sections
            for number in [_chapter_number(row["title"])]
            if number is not None
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
        course_record = (
            project.get("_course_document_record")
            if isinstance(project.get("_course_document_record"), dict)
            else {}
        )
        course_profile = (
            (project.get("document_spec") or {}).get("course_profile")
            if isinstance(project.get("document_spec"), dict)
            else {}
        )
        if isinstance(course_profile, dict) and course_profile.get("template_key"):
            product_type = str(course_record.get("product_type") or "")
            word_count = len(re.sub(r"\s+", "", markdown))

            def require_minimum(minimum: int, label: str) -> None:
                if word_count < minimum:
                    issues.append(
                        {
                            "severity": "blocker",
                            "type": "document_too_short",
                            "message": f"{label}正文不足 {minimum} 字符，当前 {word_count} 字符",
                        }
                    )

            def require_terms(terms: list[str], label: str) -> None:
                for term in terms:
                    if term not in markdown:
                        issues.append(
                            {
                                "severity": "blocker",
                                "type": "required_section_missing",
                                "message": f"{label}缺少“{term}”内容",
                            }
                        )

            if product_type == "course_plan":
                require_minimum(6000, "课程教学计划")
                if "20" not in markdown or len(course_profile.get("units") or []) != 10:
                    issues.append(
                        {
                            "severity": "blocker",
                            "type": "hour_total_mismatch",
                            "message": "课程教学计划必须采用10讲、20学时基线",
                        }
                    )
            elif product_type == "teaching_schedule":
                require_minimum(500, "教学进度表")
                schedule_rows = re.findall(r"^\|\s*\d+\s*\|", markdown, flags=re.M)
                if len(schedule_rows) < 10 or "20" not in markdown:
                    issues.append(
                        {
                            "severity": "blocker",
                            "type": "hour_total_mismatch",
                            "message": "教学进度表必须包含10次课并合计20学时",
                        }
                    )
            elif product_type == "lesson_plan":
                require_minimum(1500, "课程教案")
                require_terms(
                    ["教学目标", "教学重点", "教学难点", "教学内容", "教学方法", "时间分配", "考核", "来源依据"],
                    "课程教案",
                )
                if "120分钟" not in markdown and "2学时" not in markdown:
                    issues.append(
                        {
                            "severity": "blocker",
                            "type": "unit_time_mismatch",
                            "message": "单讲教案时间分配必须合计2学时或120分钟",
                        }
                    )
            elif product_type == "practice_guide":
                require_minimum(5000, "实作指导书")
                require_terms(
                    ["实作目标", "环境与器材", "规则版本", "软件版本", "作战想定", "组织分工", "操作步骤", "记录", "复盘", "报告要求"],
                    "实作指导书",
                )
            elif product_type == "assessment":
                require_minimum(2500, "考核方案")
                require_terms(["理论", "操作", "推演", "复盘", "评分"], "考核方案")

        course_blockers = sum(
            1
            for row in issues
            if row["severity"] == "blocker"
            and row["type"]
            in {
                "document_too_short",
                "required_section_missing",
                "hour_total_mismatch",
                "unit_time_mismatch",
            }
        )
        score = max(
            0,
            100
            - len(missing_refs) * 3
            - len(unresolved_assets) * 2
            - len(missing_chapters) * 10
            - min(uncited, 20)
            - course_blockers * 10,
        )
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
        if (
            manifest.get("content_authority") == "structured_json"
            and (
                manifest.get("projection_status") != "current"
                or int(manifest.get("structured_projection_revision") or 0)
                < int(manifest.get("version") or 0)
            )
        ):
            raise DocumentProductionBlocked(
                "结构化正文尚未生成最新 Markdown 投影，暂不能导出",
                ["markdown_projection_stale"],
            )
        output_format = output_format.lower()
        if output_format not in {"docx", "pdf"}:
            raise DocumentWorkspaceError("只支持导出 docx 或 pdf")
        root = self._workspace_root(project)
        exports = root / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        layout_binding = project.get("_document_layout_binding")
        layout_binding = layout_binding if isinstance(layout_binding, dict) else {}
        stem = str(layout_binding.get("delivery_basename") or "").strip()
        if not stem:
            stem = f"{_safe_name(str(project.get('name') or '文档'))}-v{manifest['version']}"
        stem = _safe_name(stem)
        docx_path = exports / f"{stem}.docx"
        markdown = Path(manifest["working_markdown"]).read_text(encoding="utf-8", errors="replace")

        def export_asset(match: re.Match[str]) -> str:
            try:
                resolved = self._resolve_asset(manifest, match.group(2))
            except DocumentWorkspaceError:
                return match.group(0)
            return f"![{match.group(1)}]({resolved.as_posix()})"

        export_markdown = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", export_asset, markdown)
        if export_markdown.startswith("---\n"):
            export_markdown = re.sub(r"\A---\n.*?\n---\n+", "", export_markdown, count=1, flags=re.DOTALL)
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
        print_profile = str(project.get("_document_print_profile") or "standard_a4")
        layout_template = Path(str(layout_binding.get("template_path") or ""))
        if layout_binding.get("profile_id") and layout_template.is_file():
            command.extend([
                "--reference-doc", str(layout_template),
                "--toc",
                "--toc-depth", "3",
                "--metadata", "toc-title=目录",
                "--metadata", "lang=zh-CN",
                "--standalone",
            ])
        elif print_profile == "wargame_a4":
            reference_doc = Path(__file__).resolve().parents[1] / "assets" / "wargame_a4_reference.docx"
            if not reference_doc.is_file():
                raise DocumentWorkspaceError("Word 导出失败：缺少 wargame_a4 排版模板")
            command.extend([
                "--reference-doc", str(reference_doc),
                "--toc",
                "--toc-depth", "3",
                "--metadata", "lang=zh-CN",
            ])
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not docx_path.exists():
            raise DocumentWorkspaceError(f"Word 导出失败：{result.stderr[-500:]}")
        try:
            if layout_binding.get("profile_id") and layout_template.is_file():
                _enable_word_field_refresh(docx_path)
            if (
                layout_binding.get("profile_id")
                and layout_template.is_file()
                and layout_binding.get("postprocess") != "preserve_reference"
            ):
                _postprocess_formal_docx(docx_path, dict(layout_binding.get("cover") or {}))
            elif print_profile == "standard_a4":
                _postprocess_standard_a4_docx(docx_path)
            elif print_profile == "wargame_a4":
                _postprocess_wargame_docx(docx_path)
        except (OSError, ValueError, KeyError, ET.ParseError, BadZipFile) as exc:
            raise DocumentWorkspaceError(f"Word 导出后处理失败：{exc}") from exc
        if output_format == "docx":
            return docx_path
        pdf_path = exports / f"{stem}.pdf"
        def convert_pdf() -> None:
            if pdf_path.exists():
                pdf_path.unlink()
            with tempfile.TemporaryDirectory(prefix="openclaw-soffice-", dir="/private/tmp") as profile:
                profile_path = Path(profile)
                result = subprocess.run(
                    [
                        "/opt/homebrew/bin/soffice",
                        f"-env:UserInstallation={profile_path.as_uri()}",
                        "--headless",
                        "--convert-to", "pdf",
                        "--outdir", str(exports),
                        str(docx_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=_libreoffice_preview_env(profile_path),
                )
            if result.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
                raise DocumentWorkspaceError(f"PDF 导出失败：{result.stderr[-500:]}")

        convert_pdf()
        if layout_binding.get("profile_id") and _refresh_toc_cache_from_pdf(docx_path, pdf_path):
            convert_pdf()
        return pdf_path


document_workspace_service = DocumentWorkspaceService()
