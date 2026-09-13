import hashlib
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

import pytest

from services.word_addin_ooxml_embedder import (
    ADDED_PARTS,
    TASKPANES_REL_TYPE,
    WEBEXT_NS,
    WordAddinEmbeddingError,
    embed_word_addin,
)


ADDIN_ID = "f5402ad8-9081-4c4c-b573-668273dfb9a1"
VERSION = "0.1.0.0"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _fixture(tmp_path):
    path = tmp_path / "source.docx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="/word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr("word/document.xml", "<document>untouched</document>")
        archive.writestr("word/styles.xml", "<styles>untouched</styles>")
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_embed_word_addin_changes_only_package_metadata_and_adds_official_parts(tmp_path):
    source = _fixture(tmp_path)
    output = tmp_path / "candidate.docx"

    report = embed_word_addin(
        source,
        output,
        expected_source_sha256=_sha(source),
        addin_id=ADDIN_ID,
        version=VERSION,
    )

    with ZipFile(source) as original, ZipFile(output) as candidate:
        assert candidate.testzip() is None
        assert candidate.read("word/document.xml") == original.read("word/document.xml")
        assert candidate.read("word/styles.xml") == original.read("word/styles.xml")
        assert all(name in candidate.namelist() for name in ADDED_PARTS)

        package_rels = ET.fromstring(candidate.read("_rels/.rels"))
        taskpane_relations = [
            node for node in package_rels.findall(f"{{{REL_NS}}}Relationship")
            if node.attrib.get("Type") == TASKPANES_REL_TYPE
        ]
        assert len(taskpane_relations) == 1
        assert taskpane_relations[0].attrib["Target"] == "/word/webextensions/taskpanes.xml"

        webextension = ET.fromstring(candidate.read("word/webextensions/webextension.xml"))
        reference = webextension.find(f"{{{WEBEXT_NS}}}reference")
        property_node = webextension.find(f"{{{WEBEXT_NS}}}properties/{{{WEBEXT_NS}}}property")
        assert webextension.attrib["id"] == f"{{{ADDIN_ID}}}"
        assert reference is not None and reference.attrib == {
            "id": ADDIN_ID,
            "version": VERSION,
            "store": "developer",
            "storeType": "Registry",
        }
        assert property_node is not None and property_node.attrib == {
            "name": "Office.AutoShowTaskpaneWithDocument",
            "value": "true",
        }

    assert report["source_sha256"] == _sha(source)
    assert report["output_sha256"] == _sha(output)
    assert report["changed_parts"] == ["[Content_Types].xml", "_rels/.rels"]


def test_embed_word_addin_fails_closed_on_source_hash_mismatch(tmp_path):
    source = _fixture(tmp_path)

    with pytest.raises(WordAddinEmbeddingError, match="source_sha256_mismatch"):
        embed_word_addin(
            source,
            tmp_path / "candidate.docx",
            expected_source_sha256="0" * 64,
            addin_id=ADDIN_ID,
            version=VERSION,
        )


def test_embed_word_addin_does_not_overwrite_source_or_existing_webextension(tmp_path):
    source = _fixture(tmp_path)
    original_sha = _sha(source)

    with pytest.raises(WordAddinEmbeddingError, match="candidate_output_must_differ_from_source"):
        embed_word_addin(
            source,
            source,
            expected_source_sha256=original_sha,
            addin_id=ADDIN_ID,
            version=VERSION,
        )
    assert _sha(source) == original_sha

    conflicting = tmp_path / "conflicting.docx"
    with ZipFile(source) as original, ZipFile(conflicting, "w", ZIP_DEFLATED) as target:
        for info in original.infolist():
            target.writestr(info, original.read(info.filename))
        target.writestr("word/webextensions/webextension.xml", "<existing/>")

    with pytest.raises(WordAddinEmbeddingError, match="webextension_parts_exist"):
        embed_word_addin(
            conflicting,
            tmp_path / "candidate.docx",
            expected_source_sha256=_sha(conflicting),
            addin_id=ADDIN_ID,
            version=VERSION,
        )
