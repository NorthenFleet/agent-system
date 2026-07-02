"""
JSON → PostgreSQL 数据迁移脚本

将现有 JSON 文件中的数据迁移到 PostgreSQL 数据库中。

@task task-005-P2-1
@author 🟥 拉斐尔
"""
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ─── 数据库连接 ───
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/team_dashboard"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# ─── 导入 ORM 模型 ───
from models.v2_models import (
    Agent, Task, TaskComment, TaskHistory, TaskTemplate,
    Sprint, ActivityLog, AgentSession, AgentStatusHistory,
    Device, Product, ProductDependency,
    AlertRule, AlertEvent, User,
    AgentHeartbeat
)

# ─── 路径 ───
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEAM_DASHBOARD_DIR = BASE_DIR  # ~/.openclaw/workspace/team-dashboard

# Queue JSON (the single source of truth for tasks)
QUEUE_PATH = os.path.join(BASE_DIR, "..", "agents", "ninja-turtles", "dev-loop", "queue.json")

# Data JSONs
AGENTS_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "agents.json")
DEVICES_JSON = os.path.join(TEAM_DASHBOARD_DIR, "data", "devices.json")
ACTIVITY_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "agent_activity.json")
SCHEDULED_JSON = os.path.join(TEAM_DASHBOARD_DIR, "data", "scheduled-tasks.json")
CHAT_SESSIONS_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "chat_sessions.json")
AUTO_PLAN_LOG_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "auto_plan_log.json")
PRODUCTS_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "products.json")
COMMUNITY_JSON = os.path.join(TEAM_DASHBOARD_DIR, "backend", "data", "community.json")

# ─── 统计 ───
stats = {"inserted": 0, "skipped": 0, "errors": 0, "details": {}}


def safe_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        if isinstance(val, str):
            # Handle various formats
            val = val.replace("Z", "+00:00")
            if "+" not in val and val[-1] != "Z":
                val += "+00:00"
            return datetime.fromisoformat(val)
        return val
    except Exception:
        return None


def migrate_agents(session):
    """agents.json → agents table"""
    print("\n🔄 Migrating agents.json → agents table")
    if not os.path.exists(AGENTS_JSON):
        print(f"  ⚠ File not found: {AGENTS_JSON}")
        stats["skipped"] += 1
        stats["details"]["agents"] = "file_not_found"
        return

    with open(AGENTS_JSON, encoding="utf-8") as f:
        agents_data = json.load(f)

    inserted = 0
    for ag in agents_data:
        # Check if already exists
        existing = session.query(Agent).filter_by(name=ag.get("name", "")).first()
        if existing:
            stats["skipped"] += 1
            stats["details"][f"agent_{ag.get('name','?')}"] = "already_exists"
            continue

        agent = Agent(
            name=ag.get("name", ""),
            role=ag.get("role", "worker"),
            status=ag.get("status", "offline"),
            team=ag.get("team"),
            capabilities=ag.get("responsibilities", []),
            model_name=None,
            last_heartbeat=None,
        )
        session.add(agent)
        inserted += 1

    session.flush()
    print(f"  ✅ Inserted {inserted} agents")
    stats["inserted"] += inserted
    stats["details"]["agents"] = f"inserted_{inserted}"


def migrate_tasks(session):
    """queue.json → tasks table (+ task_comments, task_history)"""
    print("\n🔄 Migrating queue.json → tasks table")
    if not os.path.exists(QUEUE_PATH):
        print(f"  ⚠ File not found: {QUEUE_PATH}")
        stats["skipped"] += 1
        stats["details"]["tasks"] = "file_not_found"
        return

    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue_data = json.load(f)

    tasks_inserted = 0
    comments_inserted = 0
    history_inserted = 0

    # Phase 1: Insert all tasks (parents first, then subtasks)
    for task_entry in queue_data.get("tasks", []):
        # Always insert the parent-level task record
        _upsert_task(session, task_entry)
        tasks_inserted += 1

        # Then insert subtasks
        subtasks = task_entry.get("subtasks", [])
        for sub in subtasks:
            _upsert_task(session, sub)
            tasks_inserted += 1

    # Flush to ensure all tasks are in DB before inserting history
    session.flush()

    # Phase 2: Migrate workflow_history into task_history
    for hist in queue_data.get("workflow_history", []):
        task_id = hist.get("task_id", "")
        changed_at = safe_dt(hist.get("at"))
        existing = session.query(TaskHistory).filter_by(
            task_id=task_id,
            field="status",
            new_value=hist.get("to"),
            changed_by=hist.get("by"),
            changed_at=changed_at,
        ).first()
        if existing:
            continue

        th = TaskHistory(
            task_id=task_id,
            field="status",
            old_value=hist.get("from"),
            new_value=hist.get("to"),
            changed_by=hist.get("by"),
            changed_at=changed_at,
        )
        session.add(th)
        history_inserted += 1

    print(f"  ✅ Inserted {tasks_inserted} tasks, {history_inserted} history records")
    stats["inserted"] += tasks_inserted + history_inserted
    stats["details"]["tasks"] = f"inserted_{tasks_inserted}"
    stats["details"]["task_history"] = f"inserted_{history_inserted}"


def _upsert_task(session, task_data: dict):
    """Insert or skip a single task record"""
    task_id = task_data.get("id", "")
    existing = session.query(Task).filter_by(task_id=task_id).first()
    if existing:
        stats["skipped"] += 1
        stats["details"][f"task_{task_id}"] = "already_exists"
        return

    status_map = {"assigned": "in_progress", "pending": "pending", "done": "done", "drafted": "pending"}

    task = Task(
        task_id=task_id,
        title=task_data.get("title", ""),
        description="",
        type=task_data.get("type", "general"),
        status=status_map.get(task_data.get("status", "pending"), "pending"),
        priority=task_data.get("priority", "medium"),
        assignee=task_data.get("assignee"),
        source="queue_json",
        created_by=task_data.get("assignee"),
        parent_task_id=None,
    )
    if "completed_at" in task_data and task_data["completed_at"]:
        task.completed_at = safe_dt(task_data["completed_at"])

    session.add(task)


def migrate_devices(session):
    """devices.json → devices table"""
    print("\n🔄 Migrating devices.json → devices table")
    if not os.path.exists(DEVICES_JSON):
        print(f"  ⚠ File not found: {DEVICES_JSON}")
        stats["skipped"] += 1
        stats["details"]["devices"] = "file_not_found"
        return

    with open(DEVICES_JSON, encoding="utf-8") as f:
        devices_data = json.load(f)

    inserted = 0
    for dev in devices_data:
        existing = session.query(Device).filter_by(name=dev.get("name", "")).first()
        if existing:
            stats["skipped"] += 1
            continue

        device = Device(
            name=dev.get("name", ""),
            ip=dev.get("ip"),
            type="mac-mini" if "MacMini" in dev.get("name", "") else "unknown",
            status=dev.get("status", "offline"),
            extra_data={
                "os": dev.get("os"),
                "role": dev.get("role"),
                "location": dev.get("location"),
                "description": dev.get("description"),
                "specs": dev.get("specs", {}),
                "ports": dev.get("ports", []),
                "assigned_agents": dev.get("assigned_agents", []),
            },
        )
        session.add(device)
        inserted += 1

    print(f"  ✅ Inserted {inserted} devices")
    stats["inserted"] += inserted
    stats["details"]["devices"] = f"inserted_{inserted}"


def migrate_activity_logs(session):
    """agent_activity.json → activity_logs table"""
    print("\n🔄 Migrating agent_activity.json → activity_logs")
    if not os.path.exists(ACTIVITY_JSON):
        print(f"  ⚠ File not found: {ACTIVITY_JSON}")
        stats["skipped"] += 1
        stats["details"]["activity_logs"] = "file_not_found"
        return

    with open(ACTIVITY_JSON, encoding="utf-8") as f:
        activity_data = json.load(f)

    inserted = 0
    for agent_id, activities in activity_data.items():
        if not isinstance(activities, list) or not activities:
            continue
        for act in activities:
            log = ActivityLog(
                agent_id=agent_id,
                action=act.get("action", act.get("type", "unknown")),
                details=act,
                created_at=safe_dt(act.get("timestamp", act.get("time", act.get("created_at")))),
            )
            session.add(log)
            inserted += 1

    print(f"  ✅ Inserted {inserted} activity logs")
    stats["inserted"] += inserted
    stats["details"]["activity_logs"] = f"inserted_{inserted}"


def migrate_sprints(session):
    """Extract sprint info from queue.json → sprints table"""
    print("\n🔄 Migrating sprints from queue.json → sprints table")

    if not os.path.exists(QUEUE_PATH):
        return

    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue_data = json.load(f)

    sprint_num = queue_data.get("sprint", 3)
    existing = session.query(Sprint).filter_by(id=sprint_num).first()
    if existing:
        print(f"  ⚠ Sprint {sprint_num} already exists")
        stats["skipped"] += 1
        return

    sprint = Sprint(
        id=sprint_num,
        name=f"Sprint {sprint_num}",
        status=queue_data.get("status", "running"),
        created_at=datetime.now(timezone.utc),
    )
    session.add(sprint)
    stats["inserted"] += 1
    stats["details"]["sprints"] = f"inserted_1"
    print(f"  ✅ Inserted sprint {sprint_num}")


def migrate_agent_sessions(session):
    """chat_sessions.json → agent_sessions table"""
    print("\n🔄 Migrating chat_sessions.json → agent_sessions")
    if not os.path.exists(CHAT_SESSIONS_JSON):
        print(f"  ⚠ File not found: {CHAT_SESSIONS_JSON}")
        stats["skipped"] += 1
        stats["details"]["agent_sessions"] = "file_not_found"
        return

    with open(CHAT_SESSIONS_JSON, encoding="utf-8") as f:
        chat_data = json.load(f)

    inserted = 0
    conversations = chat_data.get("conversations", {})
    if isinstance(conversations, dict):
        for session_key, conv in conversations.items():
            if not isinstance(conv, dict):
                continue
            agent_id = conv.get("agent_id", conv.get("agent_name", conv.get("agent", "")))

            if not agent_id or not session_key:
                continue

            existing = session.query(AgentSession).filter_by(session_key=str(session_key)).first()
            if existing:
                stats["skipped"] += 1
                continue

            agent_session = AgentSession(
                agent_id=str(agent_id),
                session_key=str(session_key),
                started_at=safe_dt(conv.get("started_at", conv.get("created_at"))),
                ended_at=safe_dt(conv.get("ended_at", conv.get("closed_at"))),
                model=conv.get("model"),
            )
            session.add(agent_session)
            inserted += 1
    elif isinstance(conversations, list):
        for conv in conversations:
            if not isinstance(conv, dict):
                continue
            agent_id = conv.get("agent_id", conv.get("agent", ""))
            session_key = conv.get("session_key", conv.get("id", conv.get("session_id", "")))

            if not agent_id or not session_key:
                continue

            existing = session.query(AgentSession).filter_by(session_key=str(session_key)).first()
            if existing:
                stats["skipped"] += 1
                continue

            agent_session = AgentSession(
                agent_id=str(agent_id),
                session_key=str(session_key),
                started_at=safe_dt(conv.get("started_at", conv.get("created_at"))),
                ended_at=safe_dt(conv.get("ended_at", conv.get("closed_at"))),
                model=conv.get("model"),
            )
            session.add(agent_session)
            inserted += 1

    print(f"  ✅ Inserted {inserted} agent sessions")
    stats["inserted"] += inserted
    stats["details"]["agent_sessions"] = f"inserted_{inserted}"


def migrate_products(session):
    """products.json → products table + product_dependencies"""
    print("\n🔄 Migrating products.json → products + product_dependencies")
    if not os.path.exists(PRODUCTS_JSON):
        print(f"  ⚠ File not found: {PRODUCTS_JSON}")
        stats["skipped"] += 1
        stats["details"]["products"] = "file_not_found"
        return

    with open(PRODUCTS_JSON, encoding="utf-8") as f:
        products_data = json.load(f)

    products_inserted = 0
    deps_inserted = 0

    for prod in products_data.get("products", []):
        existing = session.query(Product).filter_by(name=prod.get("name", "")).first()
        if existing:
            stats["skipped"] += 1
            continue

        product = Product(
            name=prod.get("name", ""),
            category=prod.get("type"),
            description=prod.get("positioning", ""),
            modules=prod.get("modules", []),
            milestones=prod.get("milestones", []),
            status=prod.get("status", "planning"),
            owner=prod.get("owner"),
            emoji=prod.get("emoji"),
            product_type=prod.get("type"),
            positioning=prod.get("positioning", ""),
        )
        session.add(product)
        session.flush()  # get ID
        products_inserted += 1

    # Map product IDs to DB IDs
    product_map: Dict[str, int] = {}
    for prod in products_data.get("products", []):
        db_prod = session.query(Product).filter_by(name=prod.get("name", "")).first()
        if db_prod:
            product_map[prod["id"]] = db_prod.id

    for dep in products_data.get("progression", []):
        from_id = product_map.get(dep.get("from"))
        to_id = product_map.get(dep.get("to"))
        if from_id and to_id:
            existing = session.query(ProductDependency).filter_by(
                from_product_id=from_id, to_product_id=to_id
            ).first()
            if existing:
                stats["skipped"] += 1
                continue
            pd = ProductDependency(
                from_product_id=from_id,
                to_product_id=to_id,
                relation_type="progresses_to",
                description=dep.get("label", ""),
            )
            session.add(pd)
            deps_inserted += 1

    print(f"  ✅ Inserted {products_inserted} products, {deps_inserted} dependencies")
    stats["inserted"] += products_inserted + deps_inserted
    stats["details"]["products"] = f"inserted_{products_inserted}"
    stats["details"]["product_dependencies"] = f"inserted_{deps_inserted}"


def migrate_auto_plan_log(session):
    """auto_plan_log.json → activity_logs table"""
    print("\n🔄 Migrating auto_plan_log.json → activity_logs")
    if not os.path.exists(AUTO_PLAN_LOG_JSON):
        print(f"  ⚠ File not found: {AUTO_PLAN_LOG_JSON}")
        stats["skipped"] += 1
        return

    with open(AUTO_PLAN_LOG_JSON, encoding="utf-8") as f:
        log_data = json.load(f)

    inserted = 0
    for entry in log_data:
        log = ActivityLog(
            agent_id=entry.get("actor", entry.get("agent", "system")),
            action=entry.get("action", "unknown"),
            details=entry,
            created_at=safe_dt(entry.get("timestamp", entry.get("time"))),
        )
        session.add(log)
        inserted += 1

    print(f"  ✅ Inserted {inserted} plan log entries")
    stats["inserted"] += inserted
    stats["details"]["auto_plan_log"] = f"inserted_{inserted}"


def print_report():
    """Print migration summary report"""
    print("\n" + "=" * 60)
    print("📊 迁移报告 (Migration Report)")
    print("=" * 60)
    print(f"  ✅ 插入记录总数: {stats['inserted']}")
    print(f"  ⏭️ 跳过记录总数: {stats['skipped']}")
    print(f"  ❌ 错误总数:     {stats['errors']}")
    print("-" * 60)
    print("  详细统计:")
    for table, detail in stats["details"].items():
        print(f"    📦 {table}: {detail}")
    print("=" * 60)


def main():
    print("🚀 开始 JSON → PostgreSQL 数据迁移")
    print(f"📍 Database: {DATABASE_URL}")

    session = SessionLocal()
    try:
        migrate_agents(session)
        migrate_tasks(session)
        migrate_devices(session)
        migrate_activity_logs(session)
        migrate_sprints(session)
        migrate_agent_sessions(session)
        migrate_products(session)
        migrate_auto_plan_log(session)

        session.commit()
        print("\n✅ 迁移完成！数据已提交到数据库。")

    except Exception as e:
        session.rollback()
        print(f"\n❌ 迁移失败！已回滚。错误: {e}")
        stats["errors"] += 1
        stats["details"]["error"] = str(e)
        raise
    finally:
        session.close()

    print_report()


if __name__ == "__main__":
    main()
