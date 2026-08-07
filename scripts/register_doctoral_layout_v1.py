"""Register the second-edition formal layout and bind the current v22 document."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path("/Users/apple/工作桌面/Workspace/agent-system")
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from project_manager import project_manager  # noqa: E402
from services.document_layout_service import document_layout_service  # noqa: E402
from services.document_workspace_service import (  # noqa: E402
    _libreoffice_preview_env,
    _postprocess_formal_docx,
    _refresh_toc_cache_from_pdf,
)
from services.multi_document_service import multi_document_service  # noqa: E402


PROJECT_ID = "proj-10fbeefae5"
DOCUMENT_ID = "doc-15def56e2401"
AUTHORITY_SOURCE = Path(
    "/Users/apple/工作桌面/knowledge/10-成果库-Outputs/毕业论文/博士论文/论文章节/版本/第三版/"
    "博士论文 - 面向海上无人集群作战的智能协同任务规划理论与方法研究.docx"
)
EXPECTED_AUTHORITY_SHA = "cce0e6ebb84f23f17b34c97cb57c59abcfc89ce5b191c98fecdb573a5b2b8a4c"
PROFILE_ID = "rich_text.doctoral.second_edition_formal.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not AUTHORITY_SOURCE.is_file():
        raise SystemExit(f"authority source missing: {AUTHORITY_SOURCE}")
    authority_sha = sha256(AUTHORITY_SOURCE)
    if authority_sha != EXPECTED_AUTHORITY_SHA:
        raise SystemExit(f"authority source hash mismatch: {authority_sha}")
    project = project_manager.get_project(PROJECT_ID)
    if not project:
        raise SystemExit("project missing")
    context = multi_document_service.rich_project_context(project, DOCUMENT_ID)
    workspace_root = Path(context.get("_workspace_root_override") or document_layout_service._root(context).parent)  # noqa: SLF001
    profile_root = workspace_root / "layout" / "profiles" / PROFILE_ID
    profile_root.mkdir(parents=True, exist_ok=True)
    template_path = profile_root / "second-edition-formal-reference-v1.docx"
    shutil.copy2(AUTHORITY_SOURCE, template_path)
    template_sha = sha256(template_path)

    sample_image = profile_root / "sample-figure.svg"
    sample_image.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="360" viewBox="0 0 1000 360">
<rect width="1000" height="360" fill="#ffffff"/><rect x="30" y="30" width="940" height="300" rx="12" fill="#f5f7fa" stroke="#222" stroke-width="2"/>
<text x="500" y="135" text-anchor="middle" font-family="Songti SC, serif" font-size="34" fill="#111">图表版式校验区域</text>
<text x="500" y="205" text-anchor="middle" font-family="Times New Roman, serif" font-size="28" fill="#333">Figure layout validation area</text>
<line x1="170" y1="260" x2="830" y2="260" stroke="#555" stroke-width="3"/>
</svg>""",
        encoding="utf-8",
    )
    sample_markdown = profile_root / "template-sample.md"
    sample_markdown.write_text(
        f"""# 摘要

【版式占位】本页只用于验证中文摘要的标题、正文、关键词、页边距和页码样式，不作为v22论文摘要内容。

**关键词：** 模板；排版；版式校验

# Abstract

[Layout placeholder] This page validates the English abstract, keywords, margins and pagination only.

**Keywords:** template; layout; validation

# 第1章 典型页面样张

## 1.1 二级标题样式

### 1.1.1 三级标题样式

这是正文段落样张。中文采用宋体，英文与数字采用 Times New Roman，字号10.5磅，固定18磅行距，首行缩进约两个汉字，段落两端对齐。该段用于检查中英文混排、标点、数字2026及行间节奏。

公式样张：

$$J(\\theta)=\\mathbb{{E}}_{{\\tau\\sim\\pi_\\theta}}\\left[\\sum_{{t=0}}^T \\gamma^t r_t\\right] \\qquad （1-1）$$

表1-1 典型表格版式

| 项目 | 规则 | 验收要求 |
|---|---|---|
| 表题 | 表上 | 与表格同页 |
| 表头 | 首行 | 跨页重复 |
| 表格行 | 不截断 | 完整显示 |

算法1-1 模板算法样张

输入：状态集合与约束集合。  
输出：满足约束的候选方案。  
步骤1：读取输入；步骤2：计算评价；步骤3：输出最优候选。

![模板图片]({sample_image.as_posix()})

图1-1 图片与图题同页样张

# 参考文献

[1] Template Author. Layout Validation Reference[J]. 2026.
""",
        encoding="utf-8",
    )
    sample_docx = profile_root / "第二版正式排版模板-v1-样张.docx"
    command = [
        "/opt/homebrew/bin/pandoc",
        str(sample_markdown),
        "--from", "markdown",
        "--to", "docx",
        "--reference-doc", str(template_path),
        "--resource-path", str(profile_root),
        "--toc",
        "--toc-depth", "3",
        "--metadata", "toc-title=目录",
        "--metadata", "lang=zh-CN",
        "--standalone",
        "--output", str(sample_docx),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise SystemExit(result.stderr[-1000:])
    cover = {
        "title": "博士学位论文排版模板样张",
        "author": "作者姓名",
        "advisor": "导师姓名",
        "advisor_title": "导师职称",
        "institution": "培养单位",
        "date": "2026年8月",
    }
    _postprocess_formal_docx(sample_docx, cover)
    sample_pdf = sample_docx.with_suffix(".pdf")
    def convert_sample_pdf() -> None:
        sample_pdf.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="layout-sample-soffice-", dir="/private/tmp") as profile:
            profile_path = Path(profile)
            result = subprocess.run(
                [
                    "/opt/homebrew/bin/soffice",
                    f"-env:UserInstallation={profile_path.as_uri()}",
                    "--headless", "--convert-to", "pdf", "--outdir", str(profile_root), str(sample_docx),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                env=_libreoffice_preview_env(profile_path),
            )
        if result.returncode != 0 or not sample_pdf.is_file():
            raise SystemExit(f"sample PDF failed: {result.stderr[-1000:]}")

    convert_sample_pdf()
    if _refresh_toc_cache_from_pdf(sample_docx, sample_pdf):
        convert_sample_pdf()

    profile_data = {
        "schema": "openclaw.document-layout-profile",
        "id": PROFILE_ID,
        "name": "博士论文第二版正式排版",
        "version": "v1",
        "applies_to": {"kind": "rich_text", "document_types": ["博士论文"]},
        "authority_source": {"path": str(AUTHORITY_SOURCE), "sha256": authority_sha},
        "template_path": str(template_path),
        "template_sha256": template_sha,
        "sample_docx_path": str(sample_docx),
        "sample_docx_sha256": sha256(sample_docx),
        "sample_pdf_path": str(sample_pdf),
        "sample_pdf_sha256": sha256(sample_pdf),
        "status": "validated",
        "page": {
            "size": "A4", "orientation": "portrait",
            "margin_top_mm": 37, "margin_bottom_mm": 35, "margin_left_mm": 28, "margin_right_mm": 26,
            "header_distance_mm": 15, "footer_distance_mm": 16, "different_first_page": True,
        },
        "styles": {
            "body": {"east_asia_font": "宋体", "latin_font": "Times New Roman", "size_pt": 10.5, "line_spacing_pt": 18, "alignment": "justify", "first_line_chars": 2},
            "heading_1": {"font": "黑体", "size_pt": 14, "page_break_before": True},
            "heading_2": {"font": "黑体", "size_pt": 12},
            "heading_3": {"font": "宋体", "size_pt": 10.5, "bold": True},
        },
        "rules": {
            "toc_depth": 3, "figure_caption": "below", "table_caption": "above",
            "repeat_table_header": True, "prevent_row_split": True,
            "footer": "- PAGE -", "first_page_number": False, "update_fields_on_open": True,
            "expected_image_count": 28,
        },
    }
    (profile_root / "profile.json").write_text(json.dumps(profile_data, ensure_ascii=False, indent=2), encoding="utf-8")

    binding = document_layout_service.binding_patch(
        context,
        profile_id=PROFILE_ID,
        layout_revision="R1",
        cover={
            "title": "面向海上无人集群作战的智能协同任务规划理论与方法研究",
            "author": "孙翼",
            "advisor": "史红权",
            "advisor_title": "研究员",
            "institution": "海军大连舰艇学院",
            "date": "2026年3月",
        },
    )
    binding["delivery_basename"] = "博士论文-第三版-七章工作稿-v22-排版R1"
    multi_document_service.update_document_metadata(project, DOCUMENT_ID, {"layout_binding": binding})
    result = {
        "profile": profile_data,
        "binding": binding,
        "authority_source_unchanged": sha256(AUTHORITY_SOURCE) == EXPECTED_AUTHORITY_SHA,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
