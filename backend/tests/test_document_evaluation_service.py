import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from services.document_evaluation_service import (
    DocumentEvaluationError,
    DocumentEvaluationService,
)
from services.document_workspace_service import document_workspace_service
from services.multi_document_service import MultiDocumentService


@pytest.fixture
def evaluation_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "10-成果库-Outputs" / "evaluation" / "body.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 摘要\n\n研究摘要。\n\n"
        "# 第1章 绪论\n\n## 1.1 研究问题\n\n问题正文。\n\n"
        "# 第2章 理论\n\n## 2.1 理论基础\n\n理论正文。\n\n"
        "# 参考文献\n\n[1] 测试文献。\n",
        encoding="utf-8",
    )
    project = {
        "id": "proj-evaluation",
        "name": "评价测试",
        "enabled_modules": ["writing"],
        "document_spec": {
            "document_type": "博士论文",
            "working_markdown": {"path": str(source), "chapter_count": 2},
            "expected_chapters": 2,
        },
    }
    multi = MultiDocumentService()
    evaluator = DocumentEvaluationService()
    monkeypatch.setattr(evaluator, "_multi", lambda: multi)
    primary = multi.list_documents(project)["documents"][0]
    return evaluator, multi, project, primary, source, tmp_path


def _presentation_bytes() -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation />")
        archive.writestr("ppt/slides/slide1.xml", "<slide />")
    return output.getvalue()


@pytest.mark.parametrize(
    ("document_type", "profile_id"),
    [
        ("博士论文", "rich_text.doctoral.v1"),
        ("学术论文", "rich_text.academic_paper.v1"),
        ("研究报告", "rich_text.research_report.v1"),
        ("技术报告", "rich_text.technical_report.v1"),
        ("专利文档", "rich_text.patent.v1"),
        ("项目方案", "rich_text.project_plan.v1"),
        ("博士论文 / 专利申报 / 技术报告", "rich_text.doctoral.v1"),
    ],
)
def test_six_rich_text_types_select_their_own_profile(document_type, profile_id):
    evaluator = DocumentEvaluationService()
    project = {"document_spec": {"document_type": document_type}}
    assert evaluator._default_profile_id(project, {"kind": "rich_text"}) == profile_id  # noqa: SLF001


def test_profile_selection_covers_document_shape_and_content_type(
    evaluation_setup, monkeypatch
):
    evaluator, multi, project, primary, _, tmp_path = evaluation_setup
    assert evaluator.resolved_profile(project, primary["id"])["id"] == "rich_text.doctoral.v1"

    workbook_path = tmp_path / "evidence.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "evidence"
    workbook.save(workbook_path)
    workbook_record = multi.create_document(
        project, "实验数据", "workbook", source_path=str(workbook_path)
    )
    assert (
        evaluator.resolved_profile(project, workbook_record["id"])["id"]
        == "workbook.research_evidence.v1"
    )

    monkeypatch.setattr(
        multi,
        "_render_presentation",
        lambda _project, _record: {"status": "completed", "slide_count": 1},
    )
    presentation_path = tmp_path / "defense.pptx"
    presentation_path.write_bytes(_presentation_bytes())
    presentation = multi.create_document(
        project, "答辩PPT", "presentation", source_path=str(presentation_path)
    )
    assert (
        evaluator.resolved_profile(project, presentation["id"])["id"]
        == "presentation.doctoral_defense.v1"
    )


def test_pending_dimensions_are_not_reported_as_zero(evaluation_setup):
    evaluator, _, project, primary, _, _ = evaluation_setup
    report = evaluator.run_technical(project, primary["id"])
    pending = [row for row in report["dimensions"] if row["status"] == "pending"]
    assert pending
    assert all(row["score"] is None for row in pending)
    assert report["provisional_score"] is None


def test_failed_required_gate_blocks_even_with_high_score(evaluation_setup):
    evaluator, _, project, primary, _, _ = evaluation_setup
    profile = evaluator.resolved_profile(project, primary["id"])
    report = evaluator.run_technical(project, primary["id"])
    for dimension in report["dimensions"]:
        dimension["score"] = 95
        dimension["status"] = "pass"
    for gate in report["gates"]:
        gate["status"] = "pass"
    next(row for row in report["gates"] if row["id"] == "academic_ethics")[
        "status"
    ] = "fail"
    evaluator._recalculate(report, profile)  # noqa: SLF001
    assert report["provisional_score"] == 95
    assert report["decision"] == "blocked"
    assert report["maturity_level"] != "L4"


def test_source_and_profile_changes_mark_previous_report_stale(evaluation_setup):
    evaluator, multi, project, primary, _, _ = evaluation_setup
    evaluator.run_technical(project, primary["id"])
    manifest = document_workspace_service.ensure_workspace(
        multi._rich_project(project, primary)  # noqa: SLF001
    )
    working = Path(manifest["working_markdown"])
    working.write_text(
        working.read_text(encoding="utf-8") + "\n补充正文。\n",
        encoding="utf-8",
    )
    assert evaluator.latest(project, primary["id"])["status"] == "stale"

    evaluator.run_technical(project, primary["id"])
    evaluator.update_policy(
        project,
        primary["id"],
        profile_id="rich_text.doctoral.v1",
        overrides={"pass_threshold": 82},
        actor="tester",
    )
    assert evaluator.latest(project, primary["id"])["status"] == "stale"


def test_policy_protects_weights_and_critical_gate(evaluation_setup):
    evaluator, _, project, primary, _, _ = evaluation_setup
    with pytest.raises(DocumentEvaluationError, match="权重合计"):
        evaluator.update_policy(
            project,
            primary["id"],
            profile_id="rich_text.doctoral.v1",
            overrides={"dimension_weights": {"innovation": 10}},
            actor="tester",
        )
    with pytest.raises(DocumentEvaluationError, match="关键门槛"):
        evaluator.update_policy(
            project,
            primary["id"],
            profile_id="rich_text.doctoral.v1",
            overrides={"gate_required": {"academic_ethics": False}},
            actor="tester",
        )


def test_expert_confirmation_is_audited_and_required_for_l4(evaluation_setup):
    evaluator, _, project, primary, _, _ = evaluation_setup
    profile = evaluator.resolved_profile(project, primary["id"])
    report = evaluator.run_technical(project, primary["id"])
    for dimension in report["dimensions"]:
        dimension["score"] = 88
        dimension["status"] = "pass"
    for gate in report["gates"]:
        gate["status"] = "pass"
    evaluator._recalculate(report, profile)  # noqa: SLF001
    evaluator._save_report(project, primary["id"], report)  # noqa: SLF001
    assert report["maturity_level"] == "L3"
    assert report["decision"] == "pending"

    confirmed = evaluator.confirm(
        project,
        primary["id"],
        dimension_scores={row["id"]: 90 for row in report["dimensions"]},
        gate_statuses={row["id"]: "pass" for row in report["gates"]},
        comment="同意送审",
        actor="expert-a",
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["decision"] == "qualified"
    assert confirmed["maturity_level"] == "L4"
    assert confirmed["confirmed_score"] == 90
    assert confirmed["audit"][-1]["actor"] == "expert-a"


def test_model_failure_keeps_technical_result_without_fabricated_score(
    evaluation_setup, monkeypatch
):
    _, multi, project, primary, _, _ = evaluation_setup

    def unavailable(_prompt):
        raise DocumentEvaluationError("模型不可用")

    evaluator = DocumentEvaluationService(ollama_call=unavailable)
    monkeypatch.setattr(evaluator, "_multi", lambda: multi)
    report = evaluator.run_full_sync(project, primary["id"])
    assert report["status"] == "failed"
    assert report["technical_score"] is not None
    assert report["provisional_score"] is None
    assert report["decision"] == "pending"


def test_gpt_oss_uses_low_thinking_and_bounded_output(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"message": {"content": json.dumps({"dimensions": []})}}
            ).encode()

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        "services.document_evaluation_service.urllib.request.urlopen",
        fake_open,
    )
    evaluator = DocumentEvaluationService()
    result = evaluator._ollama_json("测试")  # noqa: SLF001
    assert result == {"dimensions": []}
    assert captured["payload"]["think"] == "low"
    assert captured["payload"]["options"]["num_predict"] == 2500
    assert captured["timeout"] == 300


def test_empty_model_actions_fall_back_to_low_dimensions_and_pending_gates():
    evaluator = DocumentEvaluationService()
    actions = evaluator._derive_priority_actions(  # noqa: SLF001
        {
            "dimensions": [
                {
                    "name": "实验与证据",
                    "score": 72,
                    "min_score": 70,
                    "recommendations": [],
                },
                {
                    "name": "创新性",
                    "score": 90,
                    "min_score": 70,
                    "recommendations": [],
                },
            ],
            "gates": [
                {
                    "name": "格式合规",
                    "source": "human",
                    "required": True,
                    "status": "pending",
                },
                {
                    "name": "学术伦理确认",
                    "source": "external",
                    "required": True,
                    "status": "pending",
                },
            ],
        }
    )
    assert any("实验与证据" in row for row in actions)
    assert any("专家人工确认" in row for row in actions)
    assert any("外部合规确认" in row for row in actions)


def test_doctoral_l5_requires_qualified_presentation_and_workbook(monkeypatch):
    documents = [
        {
            "id": "body",
            "title": "论文正文",
            "kind": "rich_text",
            "structure_binding": {},
        },
        {
            "id": "ppt",
            "title": "答辩PPT",
            "kind": "presentation",
            "structure_binding": {"status": "aligned"},
        },
    ]

    class FakeMulti:
        def list_documents(self, _project):
            return {"documents": documents}

    reports = {
        "body": {
            "status": "confirmed",
            "decision": "qualified",
            "maturity_level": "L4",
            "technical_score": 100,
            "confirmed_score": 88,
            "provisional_score": 86,
        },
        "ppt": {
            "status": "confirmed",
            "decision": "qualified",
            "maturity_level": "L4",
            "technical_score": 100,
            "confirmed_score": 90,
            "provisional_score": 89,
        },
        "data": {
            "status": "confirmed",
            "decision": "qualified",
            "maturity_level": "L4",
            "technical_score": 100,
            "confirmed_score": 92,
            "provisional_score": 90,
        },
    }
    evaluator = DocumentEvaluationService()
    monkeypatch.setattr(evaluator, "_multi", lambda: FakeMulti())
    monkeypatch.setattr(
        evaluator,
        "latest",
        lambda _project, document_id, create_if_missing=True: reports[document_id],
    )
    project = {"document_spec": {"document_type": "博士论文"}}
    blocked = evaluator.linked_summary(project)
    assert blocked["defense_ready"] is False
    assert any("工作簿" in row for row in blocked["blockers"])

    documents.append(
        {
            "id": "data",
            "title": "实验数据",
            "kind": "workbook",
            "structure_binding": {},
        }
    )
    ready = evaluator.linked_summary(project)
    assert ready["defense_ready"] is True
    assert ready["maturity_level"] == "L5"
    assert ready["blockers"] == []
