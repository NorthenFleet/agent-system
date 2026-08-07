from services.project_task_sync import build_command_center_task_records, build_project_task_records, external_task_id


def test_build_project_task_records_preserves_parent_child_relationship():
    project = {
        "id": "proj-demo",
        "name": "示例项目",
        "project_type": "software",
        "tasks": [{
            "id": "task-demo",
            "title": "实现任务总账",
            "status": "in_progress",
            "priority": "high",
            "progress": 50,
            "assignee_agent": "leonardo",
            "development_points": [{
                "id": "point-demo",
                "title": "接入数据库",
                "status": "done",
                "assigned_agent": "raphael",
                "completion_evidence": "接口测试通过",
            }],
        }],
    }

    parent, child = build_project_task_records(project)

    assert parent["source"] == "project-dev"
    assert parent["parent_task_id"] is None
    assert child["parent_task_id"] == parent["task_id"]
    assert child["type"] == "development-point"
    assert child["progress"] == 100
    assert "完成反馈：接口测试通过" in child["description"]
    assert "managed:project-ledger" in child["tags"]


def test_document_points_are_classified_as_writing_work():
    project = {
        "id": "proj-doc",
        "name": "论文",
        "project_type": "document",
        "tasks": [{
            "id": "task-doc",
            "title": "撰写章节",
            "development_points": [{"id": "point-doc", "title": "完成初稿"}],
        }],
    }

    parent, child = build_project_task_records(project)

    assert parent["source"] == "project-doc"
    assert child["source"] == "project-doc"
    assert child["type"] == "writing-point"


def test_external_task_id_stays_stable_and_within_database_limit():
    first = external_task_id("p" * 80, "point", "x" * 80)
    second = external_task_id("p" * 80, "point", "x" * 80)

    assert first == second
    assert len(first) <= 64


def test_build_command_center_task_records_maps_mission_and_steps():
    mission = {
        "id": "mission-demo",
        "title": "执行看板优化",
        "objective": "完善指挥中心任务列表",
        "status": "running",
        "mission_type": "software",
        "project_id": "project-software",
        "priority": "normal",
        "steps": [{
            "id": "step-demo",
            "title": "后端投影 API",
            "description": "实现 task-workbench",
            "task_type": "backend",
            "agent_id": "raphael",
            "status": "running",
            "work_run_id": "run-1",
        }],
    }

    parent, child = build_command_center_task_records(mission)

    assert parent["source"] == "command-center"
    assert parent["status"] == "in_progress"
    assert parent["assignee"] == "optimus"
    assert child["parent_task_id"] == parent["task_id"]
    assert child["assignee"] == "raphael"
    assert child["status"] == "in_progress"
    assert "mission-id:mission-demo" in child["tags"]
