"""Embed a registered Word task-pane add-in into a candidate DOCX copy."""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo
from xml.etree import ElementTree as ET


CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PACKAGE_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WEBEXT_NS = "http://schemas.microsoft.com/office/webextensions/webextension/2010/11"
TASKPANES_NS = "http://schemas.microsoft.com/office/webextensions/taskpanes/2010/11"

TASKPANES_REL_TYPE = "http://schemas.microsoft.com/office/2011/relationships/webextensiontaskpanes"
WEBEXT_REL_TYPE = "http://schemas.microsoft.com/office/2011/relationships/webextension"
TASKPANES_CONTENT_TYPE = "application/vnd.ms-office.webextensiontaskpanes+xml"
WEBEXT_CONTENT_TYPE = "application/vnd.ms-office.webextension+xml"

TASKPANES_PART = "word/webextensions/taskpanes.xml"
TASKPANES_RELS_PART = "word/webextensions/_rels/taskpanes.xml.rels"
WEBEXT_PART = "word/webextensions/webextension.xml"
ADDED_PARTS = (TASKPANES_PART, TASKPANES_RELS_PART, WEBEXT_PART)
REQUIRED_PARTS = ("[Content_Types].xml", "_rels/.rels", "word/document.xml")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")

ET.register_namespace("", CONTENT_TYPES_NS)


class WordAddinEmbeddingError(ValueError):
    """Raised when candidate-only embedding cannot be completed safely."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _read_xml(parts: dict[str, bytes], name: str) -> ET.Element:
    try:
        return ET.fromstring(parts[name])
    except KeyError as error:
        raise WordAddinEmbeddingError(f"missing_required_part:{name}") from error
    except ET.ParseError as error:
        raise WordAddinEmbeddingError(f"invalid_xml_part:{name}") from error


def _next_relationship_id(root: ET.Element) -> str:
    existing = {node.attrib.get("Id", "") for node in root}
    base = "rId3021WordAddin"
    if base not in existing:
        return base
    suffix = 2
    while f"{base}{suffix}" in existing:
        suffix += 1
    return f"{base}{suffix}"


def _add_content_type(root: ET.Element, part_name: str, content_type: str) -> None:
    namespace = f"{{{CONTENT_TYPES_NS}}}"
    for node in root.findall(f"{namespace}Override"):
        if node.attrib.get("PartName") == part_name:
            raise WordAddinEmbeddingError(f"webextension_content_type_exists:{part_name}")
    ET.SubElement(
        root,
        f"{namespace}Override",
        {"PartName": part_name, "ContentType": content_type},
    )


def _build_taskpanes(relationship_id: str) -> bytes:
    ET.register_namespace("wetp", TASKPANES_NS)
    ET.register_namespace("r", OFFICE_RELS_NS)
    root = ET.Element(f"{{{TASKPANES_NS}}}taskpanes")
    taskpane = ET.SubElement(
        root,
        f"{{{TASKPANES_NS}}}taskpane",
        {"dockstate": "", "visibility": "1", "width": "350", "row": "1"},
    )
    ET.SubElement(
        taskpane,
        f"{{{TASKPANES_NS}}}webextensionref",
        {f"{{{OFFICE_RELS_NS}}}id": relationship_id},
    )
    return _xml_bytes(root)


def _build_taskpanes_relationships(relationship_id: str) -> bytes:
    ET.register_namespace("", PACKAGE_RELS_NS)
    root = ET.Element(f"{{{PACKAGE_RELS_NS}}}Relationships")
    ET.SubElement(
        root,
        f"{{{PACKAGE_RELS_NS}}}Relationship",
        {
            "Id": relationship_id,
            "Type": WEBEXT_REL_TYPE,
            "Target": "/word/webextensions/webextension.xml",
        },
    )
    return _xml_bytes(root)


def _build_webextension(addin_id: str, version: str) -> bytes:
    ET.register_namespace("we", WEBEXT_NS)
    root = ET.Element(f"{{{WEBEXT_NS}}}webextension", {"id": f"{{{addin_id}}}"})
    ET.SubElement(
        root,
        f"{{{WEBEXT_NS}}}reference",
        {
            "id": addin_id,
            "version": version,
            "store": "developer",
            "storeType": "Registry",
        },
    )
    ET.SubElement(root, f"{{{WEBEXT_NS}}}alternateReferences")
    properties = ET.SubElement(root, f"{{{WEBEXT_NS}}}properties")
    ET.SubElement(
        properties,
        f"{{{WEBEXT_NS}}}property",
        {"name": "Office.AutoShowTaskpaneWithDocument", "value": "true"},
    )
    ET.SubElement(root, f"{{{WEBEXT_NS}}}bindings")
    return _xml_bytes(root)


def _copy_info(info: ZipInfo) -> ZipInfo:
    copied = ZipInfo(info.filename, date_time=info.date_time)
    copied.compress_type = info.compress_type
    copied.comment = info.comment
    copied.extra = info.extra
    copied.internal_attr = info.internal_attr
    copied.external_attr = info.external_attr
    copied.create_system = info.create_system
    copied.flag_bits = info.flag_bits
    return copied


def embed_word_addin(
    source: Path,
    output: Path,
    *,
    expected_source_sha256: str,
    addin_id: str,
    version: str,
) -> dict[str, object]:
    """Create a candidate DOCX with an auto-open reference to a registered add-in."""

    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise WordAddinEmbeddingError("candidate_output_must_differ_from_source")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
        raise WordAddinEmbeddingError("expected_source_sha256_invalid")
    try:
        normalized_addin_id = str(uuid.UUID(addin_id))
    except ValueError as error:
        raise WordAddinEmbeddingError("addin_id_invalid") from error
    if not VERSION_RE.fullmatch(version):
        raise WordAddinEmbeddingError("addin_version_invalid")

    source_bytes = source.read_bytes()
    source_sha256 = _sha256(source_bytes)
    if source_sha256 != expected_source_sha256:
        raise WordAddinEmbeddingError("source_sha256_mismatch")

    try:
        with ZipFile(io.BytesIO(source_bytes)) as archive:
            entries = archive.infolist()
            parts = {info.filename: archive.read(info.filename) for info in entries}
    except BadZipFile as error:
        raise WordAddinEmbeddingError("source_not_docx_zip") from error

    for name in REQUIRED_PARTS:
        if name not in parts:
            raise WordAddinEmbeddingError(f"missing_required_part:{name}")
    conflicts = sorted(name for name in ADDED_PARTS if name in parts)
    if conflicts:
        raise WordAddinEmbeddingError(f"webextension_parts_exist:{','.join(conflicts)}")

    content_types = _read_xml(parts, "[Content_Types].xml")
    _add_content_type(content_types, "/word/webextensions/taskpanes.xml", TASKPANES_CONTENT_TYPE)
    _add_content_type(content_types, "/word/webextensions/webextension.xml", WEBEXT_CONTENT_TYPE)
    parts["[Content_Types].xml"] = _xml_bytes(content_types)

    package_rels = _read_xml(parts, "_rels/.rels")
    for relation in package_rels:
        if relation.attrib.get("Type") == TASKPANES_REL_TYPE:
            raise WordAddinEmbeddingError("webextension_taskpanes_relationship_exists")
    package_relation_id = _next_relationship_id(package_rels)
    ET.SubElement(
        package_rels,
        f"{{{PACKAGE_RELS_NS}}}Relationship",
        {
            "Id": package_relation_id,
            "Type": TASKPANES_REL_TYPE,
            "Target": "/word/webextensions/taskpanes.xml",
        },
    )
    parts["_rels/.rels"] = _xml_bytes(package_rels)

    taskpane_relation_id = "rId3021Taskpane"
    parts[TASKPANES_PART] = _build_taskpanes(taskpane_relation_id)
    parts[TASKPANES_RELS_PART] = _build_taskpanes_relationships(taskpane_relation_id)
    parts[WEBEXT_PART] = _build_webextension(normalized_addin_id, version)

    output.parent.mkdir(parents=True, exist_ok=True)
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as target:
        for info in entries:
            target.writestr(_copy_info(info), parts[info.filename])
        for name in ADDED_PARTS:
            target.writestr(name, parts[name])
    output_bytes = stream.getvalue()
    with ZipFile(io.BytesIO(output_bytes)) as verification:
        damaged = verification.testzip()
        if damaged:
            raise WordAddinEmbeddingError(f"output_crc_failed:{damaged}")

    output.write_bytes(output_bytes)
    return {
        "source": str(source),
        "output": str(output),
        "source_sha256": source_sha256,
        "output_sha256": _sha256(output_bytes),
        "addin_id": normalized_addin_id,
        "addin_version": version,
        "changed_parts": ["[Content_Types].xml", "_rels/.rels"],
        "added_parts": list(ADDED_PARTS),
    }
