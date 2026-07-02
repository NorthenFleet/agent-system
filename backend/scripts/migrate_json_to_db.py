#!/usr/bin/env python
"""
数据迁移脚本：旧 JSON 数据 → V2 SQLite

从以下旧数据源读取并写入 tasks 表：
- backend/data/task_plans.json  — 任务计划（含任务 ID）
- dev-loop/queue.json            — 任务队列（含子任务）

去重策略：按 task_id 判断是否已存在，已存在则跳过。
"""
import os
import sys
import json
from datetime import datetime, timezone

# 确保能导入项目模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BACKEND_DIR)

from models.v2_models import init_db, get_session, Task


def parse_dt(s: str) -> datetime:
    """解析 ISO 时间字符串"""
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


def migrate_task_plans() -> int:
    """从 task_plans.json 迁移任务数据"""
    plans_file = os.path.join(BACKEND_DIR, "data", "task_plans.json")
    if not os.path.exists(plans_file):
        print(f"  [SKIP] {plans_file} 不存在")
        return 0

    with open(plans_file, "r", encoding="utf-8") as f:
        plans = json.load(f)

    db = get_session()
    inserted = 0

    for plan_id, plan in plans.items():
        task_id = plan.get("task_id", "")
        if not task_id:
            continue

        # 去重
        existing = db.query(Task).filter(Task.task_id == task_id).first()
        if existing:
            print(f"  [SKIP] task-{task_id} 已存在")
            continue

        status = plan.get("status", "pending")
        steps = plan.get("steps", [])
        completed_steps = sum(1 for s in steps if s.get("status") == "completed")
        total_steps = len(steps)
        progress = int((completed_steps / total_steps * 100) if total_steps > 0 else 0)

        task = Task(
            task_id=task_id,
            title=f"任务 {task_id}",
            description="",
            type=plan.get("type", "general"),
            status=status,
            priority="medium",
            assignee=steps[0].get("executor") if steps else None,
            progress=progress,
            source="migrated",
            created_by=plan.get("creator"),
            created_at=parse_dt(plan.get("created_at", "")),
            tags=[],
        )
        db.add(task)
        inserted += 1
        print(f"  [INSERT] task-{task_id}: {task.title} (status={status}, progress={progress}%)")

    db.commit()
    db.close()
    return inserted


def migrate_queue_tasks() -> int:
    """从 dev-loop/queue.json 迁移任务数据"""
    # 搜索 queue.json 的可能路径（优先 ninja-turtles，再回退全局）
    possible_paths = [
        os.path.join(os.path.dirname(BACKEND_DIR), "agents", "ninja-turtles", "dev-loop", "queue.json"),
        os.path.join(os.path.expanduser("~/.openclaw/workspace"), "agents", "ninja-turtles", "dev-loop", "queue.json"),
        os.path.join(os.path.dirname(BACKEND_DIR), "dev-loop", "queue.json"),
        os.path.join(os.path.expanduser("~/.openclaw/workspace"), "dev-loop", "queue.json"),
    ]
    queue_file = None
    for p in possible_paths:
        if os.path.exists(p):
            queue_file = p
            break
    if not queue_file:
        print(f"  [SKIP] queue.json 未找到（已搜索 {len(possible_paths)} 个路径）")
        return 0

    with open(queue_file, "r", encoding="utf-8") as f:
        queue_data = json.load(f)

    db = get_session()
    inserted = 0

    for task in queue_data.get("tasks", []):
        task_id = task.get("id", "")
        if not task_id:
            continue

        # 跳过已完成任务的旧记录
        subtasks = task.get("subtasks", [])
        if not subtasks:
            # 普通任务
            existing = db.query(Task).filter(Task.task_id == task_id).first()
            if existing:
                print(f"  [SKIP] {task_id} 已存在")
                continue

            t = Task(
                task_id=task_id,
                title=task.get("title", task_id),
                description="",
                type=task.get("type", "general"),
                status=task.get("status", "pending"),
                priority="medium",
                source="migrated",
                sprint=queue_data.get("sprint"),
                created_at=parse_dt(task.get("created_at", "")),
            )
            db.add(t)
            inserted += 1
            print(f"  [INSERT] {task_id}: {t.title}")
        else:
            # 有子任务的任务 → 迁移每个子任务
            for st in subtasks:
                st_id = st.get("id", "")
                if not st_id:
                    continue

                existing = db.query(Task).filter(Task.task_id == st_id).first()
                if existing:
                    print(f"  [SKIP] {st_id} 已存在")
                    continue

                # 确定负责人
                assignee_map = {
                    "raphael": "raphael",
                    "donatello": "donatello",
                    "leonardo": "leonardo",
                    "michelangelo": "michelangelo",
                }
                raw_assignee = st.get("assignee", "")
                assignee = assignee_map.get(raw_assignee, raw_assignee)

                t = Task(
                    task_id=st_id,
                    title=st.get("title", st_id),
                    description="",
                    type=st.get("type", "general"),
                    status=st.get("status", "pending"),
                    priority=st.get("priority", "medium"),
                    assignee=assignee,
                    parent_task_id=task_id,
                    sprint=queue_data.get("sprint"),
                    source="migrated",
                    created_at=parse_dt(queue_data.get("created", "")),
                )
                db.add(t)
                inserted += 1
                print(f"  [INSERT] {st_id}: {t.title} (assignee={assignee}, status={t.status})")

    db.commit()
    db.close()
    return inserted


def main():
    print("=" * 50)
    print("V2 数据迁移：JSON → SQLite")
    print("=" * 50)

    # 确保表已创建
    init_db()

    print("\n[1/2] 迁移 task_plans.json ...")
    n1 = migrate_task_plans()

    print(f"\n[2/2] 迁移 dev-loop/queue.json ...")
    n2 = migrate_queue_tasks()

    # 汇总
    db = get_session()
    total = db.query(Task).count()
    db.close()

    print(f"\n{'=' * 50}")
    print(f"迁移完成：本次插入 {n1 + n2} 条，数据库共 {total} 条任务")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
