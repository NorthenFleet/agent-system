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
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402

PROJECT_ID = "proj-10fbeefae5"
CURRENT_ID = "doc-15def56e2401"
THESIS = Path("/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文")
FIRST = THESIS / "博士论文 - 面向海上无人集群作战的智能协同任务规划理论与方法研究.md"
SECOND_NAMES = [
    "第0章：面向海上无人集群智能协同任务规划的理论与方法研究.md",
    "第1章-绪论.md",
    "第2章-无人集群任务规划的理论基础.md",
    "第3章-基于作战意图与杀伤链逻辑的任务分解.md",
    "第4章 基于优势驱动的任务分配与集群编成.md",
    "第5章-面向优势场的多智能体协同路径规划.md",
    "第6章-仿真与评估.md",
    "第7章-总结与展望.md",
    "参考文献.md",
]
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


def normalize_second_frontmatter(markdown):
    return markdown.replace("# 第0章 摘要", "# 文档说明", 1).replace("# 三、英文摘要（直接可用 SCI风格）", "# 英文摘要", 1)


def repair_second_structure(project, document_id):
    state = writing_collaboration_service.get_state(project, document_id)
    document = state.get("document") or state.get("content") or {}
    changed = False
    for block in document.get("content") or []:
        if block.get("type") != "heading":
            continue
        text = "".join(node.get("text", "") for node in block.get("content") or [] if node.get("type") == "text")
        replacement = "文档说明" if text == "第0章 摘要" else "英文摘要" if text.startswith("三、英文摘要") else ""
        if replacement and block.get("content"):
            block["content"] = [{"type": "text", "text": replacement}]
            changed = True
    if changed:
        writing_collaboration_service.patch_draft(project, document_id, {
            "content": document, "expected_revision": state["revision"],
            "client_change_id": "thesis-edition-2-frontmatter-v1",
        }, "thesis-version-migration")


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
    state = writing_collaboration_service.get_state(project, current["id"])
    (target / "structured-body.json").write_text(json.dumps(state.get("document") or state.get("content") or {}, ensure_ascii=False), encoding="utf-8")
    return target


def register(project, rows, *, sequence, title, source, asset_base, checksum, expected, source_type, paths, parent=""):
    found = edition(rows, sequence)
    if found:
        writing_collaboration_service.ensure_state(project, found["id"])
        if sequence == 2:
            repair_second_structure(project, found["id"])
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
    if sequence == 2:
        repair_second_structure(project, created["id"])
    return multi_document_service.update_document(project, created["id"], {
        "edit_policy": "read_only", "delivery_role": "historical_reference", "expected_chapters": expected,
    })


def run(apply=False):
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise RuntimeError(f"论文项目不存在：{PROJECT_ID}")
    if not FIRST.is_file():
        raise RuntimeError(f"第一版源文件不存在：{FIRST}")
    second_root = THESIS / "论文章节" / "正式稿"
    second_paths = [second_root / name for name in SECOND_NAMES]
    missing = [str(path) for path in second_paths if not path.is_file()]
    if missing:
        raise RuntimeError("第二版章节缺失：" + "、".join(missing))
    listing = multi_document_service.list_documents(project)
    current = next((row for row in listing["documents"] if row["id"] == CURRENT_ID), None)
    if not current:
        raise RuntimeError(f"第三版权威文档不存在：{CURRENT_ID}")
    first_checksum = sha(FIRST.read_bytes())
    bundle_checksum = sha("\n".join(f"{path}:{sha(path.read_bytes())}" for path in second_paths).encode())
    result = {
        "project_id": PROJECT_ID,
        "first": {"path": str(FIRST), "checksum": first_checksum},
        "second": {"paths": [str(path) for path in second_paths], "checksum": bundle_checksum},
        "third": {"document_id": CURRENT_ID, "revision": current.get("revision"), "checksum": current.get("source_checksum")},
    }
    if not apply:
        return {"status": "dry_run", **result}
    target = multi_document_service._project_root(project) / "imports" / "博士论文-第二版-Obsidian正式稿.md"  # noqa: SLF001
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(normalize_second_frontmatter("\n\n".join(path.read_text(encoding="utf-8").strip() for path in second_paths) + "\n"), encoding="utf-8")
    saved = backup(project, current)
    first = register(project, listing["documents"], sequence=1, title="博士论文·第一版（十章初稿）", source=FIRST, asset_base=FIRST.parent, checksum=first_checksum, expected=10, source_type="markdown", paths=[FIRST])
    rows = multi_document_service.list_documents(project)["documents"]
    second = register(project, rows, sequence=2, title="博士论文·第二版（Obsidian正式稿）", source=target, asset_base=second_root, checksum=bundle_checksum, expected=7, source_type="chapter_bundle", paths=second_paths, parent=first["id"])
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
