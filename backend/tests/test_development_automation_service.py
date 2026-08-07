import json
import sqlite3

import pytest

from services.development_automation_service import DevelopmentAutomationService


def seed_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, project_type TEXT NOT NULL,
            description TEXT DEFAULT '', status TEXT DEFAULT 'active', current_phase TEXT DEFAULT '',
            context TEXT NOT NULL DEFAULT '{}', design_doc TEXT NOT NULL DEFAULT '{}',
            document_spec TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE project_tasks (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, type TEXT, title TEXT NOT NULL,
            description TEXT, acceptance_criteria TEXT DEFAULT '[]'
        );
        CREATE TABLE development_points (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, project_id TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT, created_at TEXT
        );
        """
    )
    relation = {
        "id": "relation-course-software",
        "source_project_id": "p3",
        "target_project_id": "p1",
        "relation_type": "course_implementation",
        "status": "active",
        "purpose": "课程与软件实作共享背景",
    }
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)",
        ('p1', '看板', 'software', '软件实现', 'active', 'development', json.dumps({"project_relations": [relation]}), '{}', '{}'),
    )
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)",
        ('p2', '论文', 'document', '论文写作', 'active', 'writing', '{}', '{}', '{}'),
    )
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)",
        (
            'p3',
            '水面舰艇作战软件与兵棋推演课程',
            'document',
            '课程文档',
            'active',
            'course-design',
            json.dumps({"goal": "形成课程教学计划、教案和实作指导书", "project_relations": [relation]}),
            '{}',
            json.dumps({
                "document_type": "课程建设项目",
                "writing_goal": "形成水面舰艇作战软件与兵棋推演课程",
                "target_audience": "任课教员和参训学员",
                "chapters": [{"title": "软件实作"}, {"title": "兵棋推演"}],
                "references": [{"title": "谋战·水面舰艇编队战术手工兵棋"}],
            }, ensure_ascii=False),
        ),
    )
    conn.execute(
        "INSERT INTO project_tasks VALUES (?,?,?,?,?,?)",
        ('t1', 'p1', 'frontend', '开发审批面板', '前端页面和 API 联动', json.dumps(['构建通过'])),
    )
    conn.execute(
        "INSERT INTO project_tasks VALUES (?,?,?,?,?,?)",
        ('tdoc', 'p2', 'writing', '撰写论文', '只进入文档写作通道', json.dumps(['完成审校'])),
    )
    conn.execute("INSERT INTO development_points VALUES ('dp1','t1','p1','实现计划卡片','', '2026-01-01')")
    conn.commit()
    conn.close()


def test_plan_requires_approval_before_loop(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    created = []

    def create_loop(**kwargs):
        created.append(kwargs)
        return {"id": "loop-1", "status": "queued"}

    service = DevelopmentAutomationService(str(db_path), loop_creator=create_loop, loop_getter=lambda _: None)
    assert service.target_execution_policy("t1") == "software_requires_plan"
    assert service.requires_approved_plan("t1") is True
    assert service.requires_approved_plan("dp1") is True
    plan = service.create_plan("p1", "task", "t1", "实现审批后的自动化开发", "agent-1")

    assert plan["status"] == "pending_approval"
    assert plan["task_type"] == "frontend"
    assert plan["review_score"] >= 70
    assert "水面舰艇作战软件与兵棋推演课程" in plan["plan_markdown"]
    assert "谋战·水面舰艇编队战术手工兵棋" in plan["plan_markdown"]
    assert created == []

    approved = service.decide_plan(plan["id"], "approve", "admin-1", "admin", "同意执行")
    assert approved["status"] == "running"
    assert approved["loop_id"] == "loop-1"
    assert created[0]["metadata"]["development_plan_id"] == plan["id"]
    assert "管理员批准" in created[0]["instruction"]


def test_reject_and_revision_never_start_loop(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    created = []
    service = DevelopmentAutomationService(str(db_path), loop_creator=lambda **kw: created.append(kw), loop_getter=lambda _: None)

    rejected = service.create_plan("p1", "development_point", "dp1", "调整页面布局和状态显示", "agent-1")
    rejected = service.decide_plan(rejected["id"], "reject", "admin-1", "admin", "范围不清")
    assert rejected["status"] == "rejected"
    assert created == []

    revised = service.create_plan("p1", "task", "t1", "补充 API 和界面联动测试", "agent-1")
    revised = service.decide_plan(revised["id"], "revise", "admin-1", "admin", "补充错误路径")
    assert revised["status"] == "revision_requested"
    assert created == []


def test_document_project_is_rejected(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    service = DevelopmentAutomationService(str(db_path), loop_creator=lambda **_: {}, loop_getter=lambda _: None)
    assert service.target_execution_policy("tdoc") == "document_forbidden"
    assert service.target_execution_policy("missing") == "unmanaged_compatibility"
    assert service.requires_approved_plan("tdoc") is True
    with pytest.raises((KeyError, ValueError)):
        service.create_plan("p2", "task", "missing", "不应进入开发自动化", "agent-1")
    with pytest.raises(ValueError, match="只适用于程序开发项目"):
        service.create_plan("p2", "task", "tdoc", "不应进入开发自动化", "agent-1")


def test_interrupted_approved_plan_can_be_redispatched(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    created = []

    def create_loop(**kwargs):
        created.append(kwargs)
        return {"id": f"loop-{len(created)}", "status": "queued"}

    service = DevelopmentAutomationService(str(db_path), loop_creator=create_loop, loop_getter=lambda _: None)
    plan = service.create_plan("p1", "task", "t1", "实现并验证课程软件实作入口", "agent-1")
    running = service.decide_plan(plan["id"], "approve", "admin-1", "admin", "同意执行")
    with service.connect() as conn:
        conn.execute(
            "UPDATE development_plans SET status='manual_takeover',handoff_reason='自动化 Loop 已中断：服务重启' WHERE id=?",
            (plan["id"],),
        )

    redispatched = service.redispatch_execution(plan["id"], "admin-2")

    assert running["loop_id"] == "loop-1"
    assert redispatched["status"] == "running"
    assert redispatched["loop_id"] == "loop-2"
    assert created[1]["metadata"]["previous_loop_id"] == "loop-1"
    assert "新的隔离工作树" in created[1]["instruction"]


def test_failed_plan_requires_redispatch_and_preserves_each_loop_round(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    loops = {}

    def create_loop(**kwargs):
        loop_id = f"loop-{len(loops) + 1}"
        loops[loop_id] = {"id": loop_id, "status": "queued", "rounds": []}
        return loops[loop_id]

    service = DevelopmentAutomationService(
        str(db_path),
        loop_creator=create_loop,
        loop_getter=lambda loop_id: loops.get(loop_id),
    )
    plan = service.create_plan("p1", "task", "t1", "实现并验证双项目背景", "agent-1")
    running = service.decide_plan(plan["id"], "approve", "admin-1", "admin", "同意执行")
    loops["loop-1"] = {
        "id": "loop-1",
        "status": "failed",
        "current_round": 1,
        "rounds": [{
            "round": 1,
            "jobs": ["old-job"],
            "evaluation": {"summary": "旧 Loop 失败证据"},
        }],
        "error": "旧 Loop 失败",
    }
    service.sync_execution_states(plan["id"])

    with pytest.raises(ValueError, match="必须批准"):
        service.execute_plan(plan["id"], "admin-2")

    redispatched = service.redispatch_execution(plan["id"], "admin-2")
    loops["loop-2"] = {
        "id": "loop-2",
        "status": "running",
        "current_round": 1,
        "rounds": [{
            "round": 1,
            "jobs": ["new-job"],
            "evaluation": {"summary": "新 Loop 证据"},
        }],
    }
    service.sync_execution_states(plan["id"])
    restored = service.get_plan(plan["id"], sync=False)

    assert running["loop_id"] == "loop-1"
    assert redispatched["loop_id"] == "loop-2"
    assert {(row["loop_id"], row["summary"]) for row in restored["loop_rounds"]} == {
        ("loop-1", "旧 Loop 失败证据"),
        ("loop-2", "新 Loop 证据"),
    }


def test_redispatch_claim_prevents_reentrant_second_loop(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    calls = []
    service = None

    def create_loop(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            with pytest.raises(ValueError, match="只有失败"):
                service.redispatch_execution(plan["id"], "admin-racing")
        return {"id": f"loop-{len(calls)}", "status": "queued"}

    def get_loop(loop_id):
        if loop_id == "loop-1":
            return {
                "id": "loop-1",
                "status": "failed",
                "current_round": 1,
                "rounds": [],
                "error": "old runner exited",
            }
        return None

    service = DevelopmentAutomationService(str(db_path), loop_creator=create_loop, loop_getter=get_loop)
    plan = service.create_plan("p1", "task", "t1", "验证重派发原子抢占", "agent-1")
    service.decide_plan(plan["id"], "approve", "admin-1", "admin", "同意执行")
    with service.connect() as conn:
        conn.execute(
            "UPDATE development_plans SET status='failed',execution_error='runner exited' WHERE id=?",
            (plan["id"],),
        )

    redispatched = service.redispatch_execution(plan["id"], "admin-2")

    assert redispatched["loop_id"] == "loop-2"
    assert len(calls) == 2


def test_manual_takeover_conflict_cannot_redispatch(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    service = DevelopmentAutomationService(
        str(db_path),
        loop_creator=lambda **_: {"id": "loop-1", "status": "queued"},
        loop_getter=lambda _: None,
    )
    plan = service.create_plan("p1", "task", "t1", "验证人工接管边界", "agent-1")
    service.decide_plan(plan["id"], "approve", "admin-1", "admin", "同意执行")
    with service.connect() as conn:
        conn.execute(
            """UPDATE development_plans
                SET status='manual_takeover',handoff_reason='集成工作树发生冲突'
                WHERE id=?""",
            (plan["id"],),
        )

    with pytest.raises(ValueError, match="只能使用重试集成"):
        service.redispatch_execution(plan["id"], "admin-2")


def test_legacy_loop_round_unique_key_migrates_without_losing_history(tmp_path):
    db_path = tmp_path / "automation.db"
    seed_db(db_path)
    service = DevelopmentAutomationService(str(db_path), loop_creator=lambda **_: {}, loop_getter=lambda _: None)
    plan = service.create_plan("p1", "task", "t1", "验证历史表迁移", "agent-1")
    with service.connect() as conn:
        conn.execute("DROP TABLE development_loop_rounds")
        conn.execute(
            """
            CREATE TABLE development_loop_rounds (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                loop_id TEXT NOT NULL,
                round_index INTEGER NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES development_plans(id) ON DELETE CASCADE,
                UNIQUE(plan_id, round_index, stage)
            )
            """
        )
        conn.execute(
            """INSERT INTO development_loop_rounds
                (id,plan_id,loop_id,round_index,stage,status,summary,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
            ("legacy-round", plan["id"], "loop-old", 1, "round", "failed", "旧证据", "2026-01-01", "2026-01-01"),
        )

    service.ensure_schema()

    with service.connect() as conn:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='development_loop_rounds'"
        ).fetchone()["sql"]
        rows = conn.execute(
            "SELECT loop_id,summary FROM development_loop_rounds WHERE plan_id=?",
            (plan["id"],),
        ).fetchall()
    assert "UNIQUE(plan_id, loop_id, round_index, stage)" in sql
    assert [(row["loop_id"], row["summary"]) for row in rows] == [("loop-old", "旧证据")]
