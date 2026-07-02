"""
工作流状态机 API

端点:
  GET  /api/workflow/states          → 状态机定义（7 个状态 + 转换规则 + 颜色）
  GET  /api/workflow/{task_id}/history → 任务流转历史
  GET  /api/workflow/transitions     → 允许的转换规则

@author 拉斐尔 (🟥 后端开发)
@created 2026-06-24
"""

import json
import os
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["workflow"])

DEV_LOOP_DIR = os.path.expanduser("~/.openclaw/workspace/agents/ninja-turtles/dev-loop")
QUEUE_FILE = os.path.join(DEV_LOOP_DIR, "queue.json")

# ---------- 状态机定义 ----------

WORKFLOW_STATES = [
    {"id": "pending", "label": "待处理", "color": "#909399"},
    {"id": "assigned", "label": "已分配", "color": "#409EFF"},
    {"id": "in_progress", "label": "进行中", "color": "#E6A23C"},
    {"id": "review", "label": "审查中", "color": "#F56C6C"},
    {"id": "testing", "label": "测试中", "color": "#8B5CF6"},
    {"id": "done", "label": "已完成", "color": "#67C23A"},
    {"id": "archived", "label": "已归档", "color": "#909399"},
]

TRANSITIONS = {
    "pending": ["assigned"],
    "assigned": ["in_progress", "pending"],
    "in_progress": ["review", "assigned"],
    "review": ["testing", "in_progress"],
    "testing": ["done", "review"],
    "done": ["archived"],
    "archived": [],
}

STATE_LABELS = {s["id"]: s["label"] for s in WORKFLOW_STATES}
STATE_COLORS = {s["id"]: s["color"] for s in WORKFLOW_STATES}


# ---------- API ----------

@router.get("/api/workflow/states")
def get_workflow_states():
    """状态机定义"""
    return {
        "states": WORKFLOW_STATES,
        "state_labels": STATE_LABELS,
        "state_colors": STATE_COLORS,
    }


@router.get("/api/workflow/transitions")
def get_workflow_transitions():
    """允许的转换规则"""
    rules = []
    for from_state, to_states in TRANSITIONS.items():
        for to_state in to_states:
            rules.append({
                "from": from_state,
                "to": to_state,
                "from_label": STATE_LABELS.get(from_state, from_state),
                "to_label": STATE_LABELS.get(to_state, to_state),
            })
    return {"transitions": rules}


@router.get("/api/workflow/{task_id}/history")
def get_task_history(task_id: str):
    """任务流转历史"""
    if not os.path.exists(QUEUE_FILE):
        raise HTTPException(status_code=404, detail="queue.json 不存在")

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue = json.load(f)

    history = queue.get("workflow_history", [])
    task_history = [h for h in history if h.get("task_id") == task_id]

    if not task_history and not history:
        # 检查任务是否存在
        found = False
        for task in queue.get("tasks", []):
            if task.get("id") == task_id:
                found = True
                break
            for sub in task.get("subtasks", []):
                if sub.get("id") == task_id:
                    found = True
                    break
            if found:
                break
        if not found:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return {
        "task_id": task_id,
        "history": task_history,
        "total": len(task_history),
    }
