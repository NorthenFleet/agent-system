from pathlib import Path

import pytest

from scripts.sync_presentation_structure_binding import (
    _install_versioned_artifact,
    _sha256,
    _validate_preview_pdf,
)


def test_install_versioned_artifact_copies_and_reuses_identical_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pptx"
    target = tmp_path / "formal" / "versioned.pptx"
    source.write_bytes(b"verified-presentation")

    installed = _install_versioned_artifact(source, target)
    reused = _install_versioned_artifact(source, target)

    assert installed == target
    assert reused == target
    assert _sha256(target) == _sha256(source)


def test_install_versioned_artifact_refuses_different_existing_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "formal" / "mapping.json"
    source.write_bytes(b'{"version":"v16"}')
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"version":"old"}')

    with pytest.raises(RuntimeError, match="内容不同"):
        _install_versioned_artifact(source, target)

    assert target.read_bytes() == b'{"version":"old"}'


def test_validate_preview_pdf_checks_hash_and_presentation_binding(
    tmp_path: Path,
) -> None:
    preview = tmp_path / "preview.pdf"
    preview.write_bytes(b"%PDF-1.7\nstatic preview\n%%EOF\n")
    preview_sha256 = _sha256(preview)
    presentation_sha256 = "a" * 64

    summary = _validate_preview_pdf(
        preview,
        {
            "sha256": preview_sha256,
            "source_presentation_sha256": presentation_sha256,
            "page_count": 53,
        },
        presentation_sha256,
        53,
    )

    assert summary["sha256"] == preview_sha256
    assert summary["page_count"] == 53
    assert summary["size_bytes"] == preview.stat().st_size


def test_validate_preview_pdf_rejects_stale_or_invalid_preview(
    tmp_path: Path,
) -> None:
    preview = tmp_path / "preview.pdf"
    preview.write_bytes(b"%PDF-1.7\nstatic preview\n%%EOF\n")

    with pytest.raises(RuntimeError, match="PPT哈希"):
        _validate_preview_pdf(
            preview,
            {
                "sha256": _sha256(preview),
                "source_presentation_sha256": "a" * 64,
                "page_count": 53,
            },
            "b" * 64,
            53,
        )

    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not-a-pdf")
    with pytest.raises(RuntimeError, match="完整PDF"):
        _validate_preview_pdf(invalid, {}, "b" * 64, 53)
