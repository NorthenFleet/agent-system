#!/usr/bin/env python3
"""Register the three doctoral-thesis editions without changing source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project_manager import project_manager  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import _convert_docx, multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402

PROJECT_ID = "proj-10fbeefae5"
CURRENT_ID = "doc-15def56e2401"
THESIS = Path("/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文")
FIRST = THESIS / "博士论文 - 面向海上无人集群作战的智能协同任务规划理论与方法研究.md"
SECOND_WORD = THESIS / "排版权威源" / "博士论文-第二版正式排版母稿-20260324.docx"
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
OBSIDIAN_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edition(rows, sequence):
    return next((row for row in rows if (row.get("lineage") or {}).get("series_id") == "doctoral-thesis" and int((row.get("lineage") or {}).get("sequence") or 0) == sequence), None)


def localize_assets(markdown, base, target):
    target.mkdir(parents=True, exist_ok=True)

    def copy(raw, label):
        token = raw.strip().strip("<>").split("#", 1)[0]
        if token.startswith(("http://", "https://", "data:")):
            return f"![{label}]({raw})"
        candidates = [base / token, THESIS / token, THESIS / "论文章节" / token, THESIS / "论文章节" / "正式稿" / "assets" / Path(token).name]
        source = next((path.resolve() for path in candidates if path.is_file()), None)
        if not source:
            return f"![{label}]({raw})"
        name = f"{sha(str(source).encode())[:10]}-{source.name}"
        shutil.copy2(source, target / name)
        return f"![{label}](assets/{name})"

    markdown = IMAGE_RE.sub(lambda match: copy(match.group(2), match.group(1)), markdown)
    return OBSIDIAN_RE.sub(lambda match: copy(match.group(1), Path(match.group(1)).stem), markdown)


def backup(project, current):
    workspace = multi_document_service._project_root(project)  # noqa: SLF001
    target = workspace / "backups" / f"thesis-comparison-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    target.mkdir(parents=True)
    index = multi_document_service._index_path(project)  # noqa: SLF001
    if index.is_file():
        shutil.copy2(index, target / "documents.json")
    manifest = multi_document_service.rich_call(project, current["id"], "ensure_workspace")
    (target / "workspace-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    body = multi_document_service.rich_call(project, current["id"], "fulltext")
    (target / "current-body.md").write_text(str(body.get("content") or ""), encoding="utf-8")
    try:
        state = writing_collaboration_service.get_state(project, current["id"])
    except Exception as exc:  # Third edition can legitimately still be Markdown-only.
        (target / "structured-body.json").write_text(
            json.dumps({"status": "not_enabled", "reason": str(exc)}, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        (target / "structured-body.json").write_text(
            json.dumps(state.get("document") or state.get("content") or {}, ensure_ascii=False),
            encoding="utf-8",
        )
    return target


def register(project, rows, *, sequence, title, source, asset_base, checksum, expected, source_type, paths, parent=""):
    found = edition(rows, sequence)
    if found:
        writing_collaboration_service.ensure_state(project, found["id"])
        return multi_document_service.update_document(project, found["id"], {
            "edit_policy": "read_only", "delivery_role": "historical_reference", "expected_chapters": expected,
        })
    created = multi_document_service.create_document(
        project, title, "rich_text", source_path=str(source), is_output_product=True,
        output_format="docx", publication_status="approved", edit_policy="editable",
        delivery_role="historical_reference", data_version=f"thesis-edition-{sequence}",
        lineage={
            "series_id": "doctoral-thesis", "edition_label": f"第{sequence}版", "sequence": sequence,
            "source_type": source_type, "parent_document_id": parent, "source_checksum": checksum,
            "generated_at": datetime.now(timezone.utc).isoformat(), "source_paths": [str(path) for path in paths],
        },
    )
    document_root = multi_document_service._document_root(project, created["id"])  # noqa: SLF001
    markdown = localize_assets(source.read_text(encoding="utf-8"), asset_base, document_root / "source" / "assets")
    multi_document_service.replace_rich_text_markdown(project, created["id"], markdown, "thesis-version-migration")
    writing_collaboration_service.ensure_state(project, created["id"])
    return multi_document_service.update_document(project, created["id"], {
        "edit_policy": "read_only", "delivery_role": "historical_reference", "expected_chapters": expected,
    })


def register_second_word_authority(project, rows, first_id, backup_root):
    """Install the frozen second-edition Word master as the read-only baseline."""
    data = SECOND_WORD.read_bytes()
    checksum = sha(data)
    converted = _convert_docx(data, "博士论文·第二版（Word正式母稿）")
    found = edition(rows, 2)
    if not found:
        created = multi_document_service.import_docx(
            project,
            "博士论文·第二版（Word正式母稿）",
            data,
            SECOND_WORD.name,
            is_primary=False,
            actor="thesis-word-authority-migration",
        )
        document_id = created["id"]
        writing_collaboration_service.ensure_state(project, document_id)
        migration_snapshot = ""
    else:
        document_id = found["id"]
        writing_collaboration_service.ensure_state(project, document_id)
        root = multi_document_service._document_root(project, document_id)  # noqa: SLF001
        migration_snapshot = backup_root / f"{document_id}-before-word-authority"
        shutil.copytree(root, migration_snapshot)
        source = root / "source" / "document.md"
        original = root / "source" / "original.docx"
        assets = root / "source" / "assets"
        staging = root / "source" / ".word-authority-assets"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for asset_name, asset_data in converted["assets"].items():
            (staging / asset_name).write_bytes(asset_data)
        original.write_bytes(data)
        source.write_text(converted["markdown"], encoding="utf-8")
        if assets.exists():
            shutil.rmtree(assets)
        staging.rename(assets)
        context = multi_document_service.rich_project_context(project, document_id)
        manifest = document_workspace_service.ensure_workspace(context)
        manifest.update({
            "source_markdown": str(source),
            "source_base_dir": str(source.parent),
            "source_word": str(original),
        })
        document_workspace_service._write_manifest(context, manifest)  # noqa: SLF001
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            document_id,
            converted["markdown"],
            label="第二版 Word 正式母稿导入",
            actor="thesis-word-authority-migration",
        )

    lineage = {
        "series_id": "doctoral-thesis",
        "edition_label": "第二版·Word正式母稿",
        "sequence": 2,
        "source_type": "docx",
        "parent_document_id": first_id,
        "source_checksum": checksum,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_paths": [str(SECOND_WORD)],
    }
    updated = multi_document_service.update_document(project, document_id, {
        "title": "博士论文·第二版（Word正式母稿）",
        "edit_policy": "read_only",
        "delivery_role": "historical_reference",
        "expected_chapters": 10,
        "lineage": lineage,
    })
    multi_document_service._update_record(project, document_id, {  # noqa: SLF001
        "source_path": str(SECOND_WORD),
        "source_checksum": checksum,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            **(updated.get("metadata") or {}),
            "word_authority": {
                "source_path": str(SECOND_WORD),
                "source_checksum": checksum,
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "import_summary": converted["stats"],
                "warnings": converted["warnings"],
                "previous_obsidian_snapshot": str(migration_snapshot) if migration_snapshot else "",
            },
        },
    })
    return multi_document_service.get_document(project, document_id)


def run(apply=False):
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise RuntimeError(f"论文项目不存在：{PROJECT_ID}")
    if not FIRST.is_file():
        raise RuntimeError(f"第一版源文件不存在：{FIRST}")
    if not SECOND_WORD.is_file():
        raise RuntimeError(f"第二版 Word 权威源不存在：{SECOND_WORD}")
    listing = multi_document_service.list_documents(project)
    current = next((row for row in listing["documents"] if row["id"] == CURRENT_ID), None)
    if not current:
        raise RuntimeError(f"第三版权威文档不存在：{CURRENT_ID}")
    first_checksum = sha(FIRST.read_bytes())
    second_checksum = sha(SECOND_WORD.read_bytes())
    result = {
        "project_id": PROJECT_ID,
        "first": {"path": str(FIRST), "checksum": first_checksum},
        "second": {"path": str(SECOND_WORD), "checksum": second_checksum},
        "third": {"document_id": CURRENT_ID, "revision": current.get("revision"), "checksum": current.get("source_checksum")},
    }
    if not apply:
        return {"status": "dry_run", **result}
    saved = backup(project, current)
    first = register(project, listing["documents"], sequence=1, title="博士论文·第一版（十章初稿）", source=FIRST, asset_base=FIRST.parent, checksum=first_checksum, expected=10, source_type="markdown", paths=[FIRST])
    rows = multi_document_service.list_documents(project)["documents"]
    second = register_second_word_authority(project, rows, first["id"], saved)
    third = multi_document_service.update_document(project, CURRENT_ID, {
        "edit_policy": "editable", "delivery_role": "deliverable", "sort_order": 2,
        "lineage": {"series_id": "doctoral-thesis", "edition_label": "第三版", "sequence": 3, "source_type": "structured_authority", "parent_document_id": second["id"], "source_checksum": current.get("source_checksum") or "", "generated_at": datetime.now(timezone.utc).isoformat(), "source_paths": [current.get("source_path") or ""]},
    })
    rows = multi_document_service.list_documents(project)["documents"]
    ordered = [first["id"], second["id"], third["id"], *[row["id"] for row in rows if row["id"] not in {first["id"], second["id"], third["id"]}]]
    multi_document_service.reorder_documents(project, ordered)
    return {"status": "applied", "backup": str(saved), "documents": multi_document_service.list_documents(project)["documents"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.apply), ensure_ascii=False, indent=2))
