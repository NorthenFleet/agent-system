import copy
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

import services.course_production_service as course_module
import scripts.migrate_surface_wargame_course_p0 as course_migration
from services.course_production_service import (
    COURSE_TEMPLATE_KEY,
    CourseProductionService,
    default_course_profile,
)
from services.document_workspace_service import (
    DocumentWorkspaceError,
    document_workspace_service,
)
from services.multi_document_service import multi_document_service
from scripts.migrate_surface_wargame_course_p0 import (
    _assessment_plan,
    _complete_lesson,
    _course_plan,
    _extract_pptx_text,
    _knowledge_selection_markdown,
    _lecture_material,
    _merge_lecture_supplement,
    _merge_practice_supplement,
    _practice_guide,
    _replace_course_markdown,
    _rule_verification_matrix,
    _teaching_schedule,
)


class FakeProjectManager:
    def __init__(self, project):
        self.project = copy.deepcopy(project)
        self._task_sequence = 0
        self._point_sequence = 0

    def get_project(self, project_id):
        return copy.deepcopy(self.project) if project_id == self.project["id"] else None

    def update_project(self, project_id, patch):
        if project_id != self.project["id"]:
            return None
        self.project.update(copy.deepcopy(patch))
        return copy.deepcopy(self.project)

    def get_project_relationship_context(self, _project_id):
        return {"relations": []}

    def add_task(self, project_id, payload):
        if project_id != self.project["id"]:
            return None
        self._task_sequence += 1
        task = {
            "id": f"task-{self._task_sequence}",
            "project_id": project_id,
            "development_points": [],
            **copy.deepcopy(payload),
        }
        self.project.setdefault("tasks", []).append(task)
        return copy.deepcopy(task)

    def update_task(self, task_id, payload):
        task = next(
            (row for row in self.project.get("tasks", []) if row["id"] == task_id),
            None,
        )
        if not task:
            return None
        task.update(copy.deepcopy(payload))
        return copy.deepcopy(task)

    def add_point(self, task_id, payload):
        task = next(
            (row for row in self.project.get("tasks", []) if row["id"] == task_id),
            None,
        )
        if not task:
            return None
        self._point_sequence += 1
        point = {
            "id": f"point-{self._point_sequence}",
            "task_id": task_id,
            **copy.deepcopy(payload),
        }
        task.setdefault("development_points", []).append(point)
        return copy.deepcopy(point)

    def update_point(self, point_id, payload):
        found = next(
            (
                (task, point)
                for task in self.project.get("tasks", [])
                for point in task.get("development_points", [])
                if point["id"] == point_id
            ),
            None,
        )
        if not found:
            return None
        _task, point = found
        point.update(copy.deepcopy(payload))
        return copy.deepcopy(point)

    def transition_point(
        self,
        point_id,
        action,
        agent_id="",
        reason="",
        completion_evidence="",
        result_summary="",
    ):
        status_by_action = {
            "claim": "in_progress",
            "block": "blocked",
            "submit_review": "review",
            "reject_review": "todo",
            "retry": "todo",
        }
        found = next(
            (
                (task, point)
                for task in self.project.get("tasks", [])
                for point in task.get("development_points", [])
                if point["id"] == point_id
            ),
            None,
        )
        if not found or action not in status_by_action:
            return None
        task, point = found
        point["status"] = status_by_action[action]
        if agent_id and action not in {"reject_review", "retry"}:
            point["assigned_agent"] = agent_id
        if completion_evidence or reason:
            point["completion_evidence"] = completion_evidence or reason
        if result_summary:
            task["result_summary"] = result_summary
        return {
            "project": copy.deepcopy(self.project),
            "task": copy.deepcopy(task),
            "point": copy.deepcopy(point),
        }

    def complete_point(
        self,
        point_id,
        agent_id,
        completion_evidence="",
        result_summary="",
    ):
        found = next(
            (
                (task, point)
                for task in self.project.get("tasks", [])
                for point in task.get("development_points", [])
                if point["id"] == point_id
            ),
            None,
        )
        if not found:
            return None
        task, point = found
        point["status"] = "done"
        point["completion_evidence"] = completion_evidence
        point["assigned_agent"] = point.get("assigned_agent") or agent_id
        task["result_summary"] = result_summary
        return {
            "project": copy.deepcopy(self.project),
            "task": copy.deepcopy(task),
            "point": copy.deepcopy(point),
        }


class FakeCommandCenter:
    def __init__(self):
        self.missions = []
        self.last_plan = None

    def list_missions(self, limit=500):
        return copy.deepcopy(self.missions[:limit])

    def create_preplanned_mission(
        self,
        *,
        objective,
        requested_by,
        plan,
        project_id="",
        title="",
        context=None,
        **_kwargs,
    ):
        self.last_plan = copy.deepcopy(plan)
        mission = {
            "id": f"mission-{len(self.missions) + 1}",
            "title": title,
            "objective": objective,
            "project_id": project_id,
            "requested_by": requested_by,
            "status": "awaiting_approval",
            "approval_status": "pending",
            "context": {"user_context": copy.deepcopy(context or {})},
            "updated_at": "2026-07-31T00:00:00+00:00",
        }
        self.missions.insert(0, mission)
        return copy.deepcopy(mission)

    def approve(self, mission_id, **_kwargs):
        mission = next(row for row in self.missions if row["id"] == mission_id)
        mission["status"] = "dispatching"
        mission["approval_status"] = "approved"
        return copy.deepcopy(mission)

    def cancel(self, mission_id, **_kwargs):
        mission = next(row for row in self.missions if row["id"] == mission_id)
        mission["status"] = "cancelled"
        return copy.deepcopy(mission)


class FakeWorkRuns:
    def __init__(self):
        self.rows = []

    def list(self, project_id="", limit=500):
        rows = [
            row for row in self.rows
            if not project_id or row.get("project_id") == project_id
        ]
        return copy.deepcopy(rows[:limit])

    def transition(self, run_id, status, **patch):
        run = next(row for row in self.rows if row["id"] == run_id)
        run["status"] = status
        run.update(copy.deepcopy(patch))
        return copy.deepcopy(run)


@pytest.fixture
def course_project(tmp_path, monkeypatch):
    monkeypatch.setattr(document_workspace_service, "vault", tmp_path)
    monkeypatch.setattr(document_workspace_service, "_find_source_word", lambda project: None)
    source = tmp_path / "10-成果库-Outputs" / "course" / "plan.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 《兵棋推演与智能决策》课程教学计划（16学时稿）\n\n"
        "# 第一章 兵棋概述\n\n原有课程正文。\n",
        encoding="utf-8",
    )
    project = {
        "id": "proj-course",
        "name": "水面舰艇作战软件与兵棋推演课程",
        "project_type": "document",
        "enabled_modules": ["writing"],
        "document_spec": {
            "working_markdown": {"path": str(source), "chapter_count": 1},
            "expected_chapters": 1,
        },
    }
    fake_manager = FakeProjectManager(project)
    monkeypatch.setattr(course_module, "project_manager", fake_manager)
    primary = multi_document_service.list_documents(project)["documents"][0]
    multi_document_service.update_document(
        project,
        primary["id"],
        {"title": "《兵棋推演与智能决策》课程教学计划（16学时稿）"},
    )
    return fake_manager


def test_default_course_profile_is_single_20_hour_authority():
    profile = default_course_profile()

    assert profile["template_key"] == COURSE_TEMPLATE_KEY
    assert profile["total_hours"] == 20
    assert profile["theory_hours"] == 4
    assert profile["practice_hours"] == 14
    assert profile["assessment_hours"] == 2
    assert profile["theory_sessions"] == 2
    assert profile["practice_sessions"] == 7
    assert profile["assessment_sessions"] == 1
    assert len(profile["units"]) == 10
    assert all(row["hours"] == 2 for row in profile["units"])
    assert [row["delivery_mode"] for row in profile["units"]].count("theory") == 2
    assert [row["delivery_mode"] for row in profile["units"]].count("practice") == 7
    assert [row["delivery_mode"] for row in profile["units"]].count("assessment") == 1
    assert profile["units"][-1]["title"].startswith("综合考核")


def test_course_baseline_rejects_non_20_hour_payload(course_project):
    service = CourseProductionService()
    invalid = default_course_profile()
    invalid["total_hours"] = 16

    with pytest.raises(DocumentWorkspaceError, match="20学时"):
        service.set_baseline(course_project.get_project("proj-course"), invalid)


def test_course_template_is_idempotent_and_creates_complete_product_architecture(course_project):
    service = CourseProductionService()
    project = course_project.get_project("proj-course")

    first = service.apply_template(project)
    refreshed = course_project.get_project("proj-course")
    second = service.apply_template(refreshed)
    documents = multi_document_service.list_documents(
        course_project.get_project("proj-course")
    )["documents"]

    assert first["summary"] == {"total": 20, "create": 19, "update": 1}
    assert second["summary"] == {"total": 20, "create": 0, "update": 20}
    assert len(documents) == 20
    assert sum(row["product_type"] == "lesson_plan" for row in documents) == 10
    assert sum(row["required_for_release"] for row in documents) == 16
    assert sum(not row["is_output_product"] for row in documents) == 4
    assert (
        course_project.project["document_spec"]["course_profile"]["total_hours"]
        == 20
    )
    empty_presentations = [
        row
        for row in documents
        if row["kind"] == "presentation" and not row["stats"].get("slide_count")
    ]
    assert len(empty_presentations) == 2
    assert all(row["structure_binding"]["status"] == "missing" for row in empty_presentations)
    schedule = next(row for row in documents if row["product_type"] == "teaching_schedule")
    assert schedule["expected_chapters"] == 2
    practice_guide = next(row for row in documents if row["product_type"] == "practice_guide")
    assessment = next(row for row in documents if row["product_type"] == "assessment")
    lecture_material = next(row for row in documents if row["product_type"] == "lecture_material")
    verification_matrix = next(
        row
        for row in documents
        if row["product_type"] == "rule_verification_matrix"
    )
    knowledge_selection = next(
        row
        for row in documents
        if row["title"] == "课程知识库优选底稿与融合说明"
    )
    practice_template = next(
        row
        for row in documents
        if row["title"] == "实作指导书编写模板（反潜专业基础课程参考）"
    )
    assert practice_guide["course_unit_ids"] == [f"L{index:02d}" for index in range(3, 10)]
    assert assessment["course_unit_ids"] == ["L10"]
    assert lecture_material["is_output_product"] is False
    assert verification_matrix["is_output_product"] is False
    assert knowledge_selection["product_type"] == "internal_reference"
    assert knowledge_selection["id"] != practice_template["id"]
    assert all(row["data_version"] == "course-baseline-20h-v4" for row in documents)
    assert all(
        {
            lecture_material["id"],
            verification_matrix["id"],
            knowledge_selection["id"],
        }
        <= set(row["data_source_ids"])
        for row in documents
        if row["is_output_product"]
    )


def test_course_work_plan_adopts_tasks_binds_documents_and_is_idempotent(course_project):
    service = CourseProductionService()
    service.apply_template(course_project.get_project("proj-course"))

    first = service.apply_work_plan(course_project.get_project("proj-course"))
    second = service.apply_work_plan(course_project.get_project("proj-course"))
    tasks = course_project.get_project("proj-course")["tasks"]

    assert first["summary"] == {
        "total": 6,
        "create": 6,
        "update": 0,
        "points_added": 22,
    }
    assert second["summary"] == {
        "total": 6,
        "create": 0,
        "update": 6,
        "points_added": 0,
    }
    assert len(tasks) == 6
    assert sum(len(task["development_points"]) for task in tasks) == 22
    assert {
        task["context"]["workstream_key"] for task in tasks
    } == {"baseline", "lessons", "practice", "assessment", "courseware", "release"}
    assert all(task["context"]["document_ids"] for task in tasks)
    assert all(
        point["context"]["document_ids"]
        for task in tasks
        for point in task["development_points"]
    )

    release = next(
        task for task in tasks if task["context"]["workstream_key"] == "release"
    )
    assert len(release["dependencies"]) == 5
    assert release["assignee_agent"] == "ultra-magnus"
    assert second["work_plan"]["summary"] == {
        "required": 6,
        "tracked": 6,
        "completed": 0,
        "active": 0,
        "points": 22,
        "completed_points": 0,
        "ready": True,
    }


def test_course_iteration_releases_only_ready_workstream_in_order(course_project):
    command_center = FakeCommandCenter()
    work_runs = FakeWorkRuns()
    service = CourseProductionService(
        command_service=command_center,
        work_runs=work_runs,
    )
    service.apply_template(course_project.get_project("proj-course"))
    service.apply_work_plan(course_project.get_project("proj-course"))

    preview = service.start_iteration(
        course_project.get_project("proj-course"),
        rounds=2,
        parallelism=2,
        dry_run=True,
    )

    assert preview["iteration"] == {
        "iteration_start": 1,
        "iteration_end": 2,
        "requested_rounds": 2,
        "actual_rounds": 2,
        "parallelism": 2,
        "point_count": 3,
    }
    assert {row["task_title"] for row in preview["selected_points"]} == {
        "编制课程教学计划"
    }
    assert preview["plan"]["steps"][2]["depends_on"] == [1, 2]

    started = service.start_iteration(
        course_project.get_project("proj-course"),
        rounds=2,
        parallelism=2,
        requested_by="admin",
    )
    baseline = next(
        task
        for task in course_project.project["tasks"]
        if task["context"]["workstream_key"] == "baseline"
    )

    assert started["mission"]["status"] == "dispatching"
    assert [point["status"] for point in baseline["development_points"]] == [
        "ready",
        "ready",
        "ready",
    ]
    assert [
        point["context"]["iteration"]
        for point in baseline["development_points"]
    ] == [1, 1, 2]
    assert started["work_plan"]["execution"]["queued_points"] == 3
    assert started["work_plan"]["execution"]["eligible_points"] == 0


def test_course_point_requires_review_before_completion(course_project):
    command_center = FakeCommandCenter()
    work_runs = FakeWorkRuns()
    service = CourseProductionService(
        command_service=command_center,
        work_runs=work_runs,
    )
    service.apply_template(course_project.get_project("proj-course"))
    service.apply_work_plan(course_project.get_project("proj-course"))
    baseline = next(
        task
        for task in course_project.project["tasks"]
        if task["context"]["workstream_key"] == "baseline"
    )
    point = baseline["development_points"][0]
    course_project.update_point(
        point["id"],
        {"status": "review", "context": {**point["context"], "iteration": 1}},
    )
    work_runs.rows.append(
        {
            "id": "run-1",
            "project_id": "proj-course",
            "task_id": baseline["id"],
            "development_point_id": point["id"],
            "status": "review",
            "input_context": {"course_iteration": 1},
        }
    )

    approved = service.review_point(
        course_project.get_project("proj-course"),
        point["id"],
        decision="approve",
        reviewer="admin",
        comment="证据完整，评审通过",
    )

    assert approved["point"]["status"] == "done"
    assert approved["work_run"]["status"] == "completed"
    assert approved["work_plan"]["summary"]["completed_points"] == 1


def test_course_source_refs_follow_manual_practice_and_assessment_flow():
    service = CourseProductionService()

    plan_refs = service._source_refs_for(  # noqa: SLF001
        {"product_type": "course_plan", "course_unit_ids": []}
    )
    l01_refs = service._source_refs_for(  # noqa: SLF001
        {"product_type": "lesson_plan", "course_unit_ids": ["L01"]}
    )
    l03_refs = service._source_refs_for(  # noqa: SLF001
        {"product_type": "lesson_plan", "course_unit_ids": ["L03"]}
    )
    l09_refs = service._source_refs_for(  # noqa: SLF001
        {"product_type": "lesson_plan", "course_unit_ids": ["L09"]}
    )
    l10_refs = service._source_refs_for(  # noqa: SLF001
        {"product_type": "lesson_plan", "course_unit_ids": ["L10"]}
    )

    expected_rule_relations = {
        "authoritative_rule",
        "adjudication_rule",
        "operator_table",
    }
    assert expected_rule_relations <= {row["relation"] for row in plan_refs}
    assert {"practice_runtime", "planning_runtime"} <= {
        row["relation"] for row in plan_refs
    }
    assert {row["relation"] for row in l01_refs} == expected_rule_relations
    assert {row["relation"] for row in l03_refs} == expected_rule_relations
    assert {"authoritative_rule", "practice_runtime", "planning_runtime"} <= {
        row["relation"] for row in l09_refs
    }
    assert {"authoritative_rule", "practice_runtime", "planning_runtime"} <= {
        row["relation"] for row in l10_refs
    }


def test_generated_plan_and_schedule_use_two_seven_one_baseline_idempotently():
    profile = default_course_profile()
    original = """---
title: old
---

# 第一章 兵棋基础理论（第1—2讲）

学时安排：本模块安排4学时，包含2次课。

## 20学时课程总体安排

| old |

## 二、课程内容与教学要求

## 四、实施过程

本课程共10学时，其中理论4学时、实践6学时。

| 合计 | 8次课 | 4 | 12 | 16 |

谋战谋战兵棋。

## 六、考核评价

保留本节。
"""

    first = _course_plan(original, profile)
    second = _course_plan(first, profile)
    schedule = _teaching_schedule(profile)

    assert second.count("## 20学时课程总体安排") == 1
    assert "2次理论、7次实作、1次考核" in second
    assert "| 第10讲 | 综合考核：想定分析、对抗推演与复盘答辩 | 综合考核 | 2 |" in second
    assert second.count("## 四、实施过程") == 1
    assert "| 合计 | 10次课 | 2次理论、7次实作、1次考核 | 4 | 14 | 2 | 20 |" in second
    assert "| 合计 | 第3—9次课 | 7次《谋战》兵棋实作 | 14 |" in second
    assert "10学时" not in second
    assert "16学时" not in second
    assert "谋战谋战" not in second
    assert "## 六、考核评价" in second
    assert "| 合计 | 10次课 | 10讲 |  | 4 | 14 | 2 | 20 |" in schedule
    assert schedule.count("《谋战》兵棋实作") >= 7


def test_knowledge_selection_note_records_sources_boundaries_and_ten_unit_mapping():
    records = [
        {
            "title": "来源一",
            "relative_path": "08-教学库-Teaching/来源一.md",
            "version": "v1",
            "sha256": "a" * 64,
            "selection": "补充来源",
            "allowed_use": "结构参考",
            "snapshot_path": "06-项目库-Projects/course/_workspace/imported_sources/来源一.md",
        }
    ]

    note = _knowledge_selection_markdown(records, default_course_profile())

    assert 'data_version: "course-baseline-20h-v4"' in note
    assert "proj-c57e28f8e0" in note
    assert "R1.2/D1.2" in note
    assert "R1.1/D1.1" in note
    assert "理论10＋实作10" in note
    assert "未经规则核验不得进入正式裁决" in note
    assert note.count("| L") == 10
    assert "| L03 | 第3讲：" in note
    assert "| L10 | 第10讲：" in note


def test_course_markdown_replacement_uses_structured_authority_for_collaborative_documents(
    monkeypatch,
):
    calls = {}
    monkeypatch.setattr(
        course_migration.multi_document_service,
        "rich_project_context",
        lambda project, document_id: {"id": document_id},
    )
    monkeypatch.setattr(
        course_migration.document_workspace_service,
        "ensure_workspace",
        lambda _context: {"content_authority": "structured_json"},
    )

    def replace_authority(project, document_id, markdown, *, label, actor):
        calls.update(
            {
                "project": project,
                "document_id": document_id,
                "markdown": markdown,
                "label": label,
                "actor": actor,
            }
        )

    monkeypatch.setattr(
        course_migration.writing_collaboration_service,
        "replace_authority_from_markdown",
        replace_authority,
    )
    monkeypatch.setattr(
        course_migration.multi_document_service,
        "replace_rich_text_markdown",
        lambda *_args, **_kwargs: pytest.fail("不应调用旧Markdown替换入口"),
    )

    project = {"id": "proj-course"}
    _replace_course_markdown(project, "doc-structured", "# 新正文", "course-migration")

    assert calls == {
        "project": project,
        "document_id": "doc-structured",
        "markdown": "# 新正文",
        "label": "课程20学时v4知识库融合",
        "actor": "course-migration",
    }


def test_lecture_material_is_normalised_mapped_and_mergeable_idempotently():
    lecture = _lecture_material()
    lesson = "# 第4讲：单回合操作\n"
    practice = "# 实作指导书\n"

    merged_lesson = _merge_lecture_supplement(lesson, "L04")
    merged_lesson_twice = _merge_lecture_supplement(merged_lesson, "L04")
    merged_practice = _merge_practice_supplement(practice)
    merged_practice_twice = _merge_practice_supplement(merged_practice)

    assert "个人—战术—全局三级能力模型" in lecture
    assert "五人编组与指挥关系" in lecture
    assert "待规则核验事项" in lecture
    assert "病例”“电站”“蛋" in lecture
    assert merged_lesson_twice.count("<!-- LECTURE-MATERIAL:START -->") == 1
    assert "多舰重复拦截造成的弹药浪费" in merged_lesson_twice
    assert merged_practice_twice.count("<!-- LECTURE-PRACTICE:START -->") == 1
    assert "第9次 | 阶段目标" in merged_practice_twice


def test_rule_verification_matrix_keeps_oral_examples_out_of_current_authority():
    matrix = _rule_verification_matrix()

    assert "当前R1.2/D1.2已核验" in matrix
    assert "仅旧版V2/V3参考" in matrix
    assert "口述案例、当前无规则证据" in matrix
    assert "与当前数据冲突" in matrix
    assert "不适用于0522想定" in matrix
    assert "有效压制半径40公里" in matrix
    assert "只取最强效果，不叠加" in matrix
    assert "每回合可以开关雷达或刷新三次" in matrix
    assert "状态为“口述案例、当前无规则证据”" in matrix
    assert "不强制凑成两波次" in matrix


def test_complete_course_documents_meet_content_quality_profiles():
    profile = default_course_profile()

    for unit in profile["units"]:
        lesson = _merge_lecture_supplement(_complete_lesson(unit), unit["id"])
        assert len(re.sub(r"\s+", "", lesson)) >= 1500
        assert len(re.findall(r"(?m)^# 第[一二三四五六七]+章", lesson)) == 7
        assert "120分钟" in lesson
        for term in [
            "教学目标",
            "教学重点",
            "教学难点",
            "教学内容",
            "教学方法",
            "时间分配",
            "考核",
            "来源依据",
        ]:
            assert term in lesson

    practice = _merge_practice_supplement(_practice_guide(profile))
    assert len(re.sub(r"\s+", "", practice)) >= 5000
    assert len(re.findall(r"(?m)^# 第[一二三四五六七八九十]+章", practice)) == 10
    for term in [
        "实作目标",
        "环境与器材",
        "规则版本",
        "软件版本",
        "作战想定",
        "组织分工",
        "操作步骤",
        "记录",
        "复盘",
        "报告要求",
    ]:
        assert term in practice

    assessment = _assessment_plan(profile)
    assert len(re.sub(r"\s+", "", assessment)) >= 2500
    assert len(re.findall(r"(?m)^# 第[一二三四五]+章", assessment)) == 5
    for term in ["理论", "操作", "推演", "复盘", "评分"]:
        assert term in assessment


def test_pptx_text_audit_reads_slide_xml_without_presentation_dependency(tmp_path):
    deck = tmp_path / "course.pptx"
    with ZipFile(deck, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                "<a:t>兵棋推演与智能决策</a:t><a:t>16学时</a:t></p:sld>"
            ),
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                "<a:t>《谋战》规则查用</a:t></p:sld>"
            ),
        )

    pages, text = _extract_pptx_text(deck)

    assert pages == 2
    assert "兵棋推演与智能决策" in text
    assert "16学时" in text
    assert "《谋战》规则查用" in text
