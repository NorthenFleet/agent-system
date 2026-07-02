"""
Legacy Scheduled Tasks routes extracted from main.py
"""
import os
import json
from fastapi import APIRouter, HTTPException
from path_config import data_path

router = APIRouter(prefix="/api/scheduled-tasks", tags=["legacy-scheduled-tasks"])


@router.get("")
def get_scheduled_tasks():
    data_file = data_path("scheduled-tasks.json")
    if not os.path.exists(data_file):
        raise HTTPException(status_code=404, detail="定时任务数据文件不存在")
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["total_tasks"] = len(data.get("tasks", []))
    data["active_tasks"] = sum(1 for t in data.get("tasks", []) if t.get("status") == "active")
    return data
