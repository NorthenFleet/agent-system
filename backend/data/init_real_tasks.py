#!/usr/bin/env python3
"""
初始化真实任务数据
从实际开发活动获取任务信息
"""
import os
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from path_config import backend_data_path

TASKS_FILE = backend_data_path("tasks.json")

# 基于实际开发活动创建任务数据
tasks = {
    "tasks": [
        {
            "id": "001",
            "title": "团队看板架构设计",
            "description": "设计团队看板的系统架构",
            "assignee": "李奥纳多",
            "status": "in_progress",
            "priority": "high",
            "progress": 30,
            "created_at": "2026-04-16T10:00:00",
            "updated_at": "2026-04-16T10:00:00",
            "cloud_dev": False,
            "dev_tool": None,
            "spec_version": None,
            "session_id": None,
            "cloud_session_active": False
        },
        {
            "id": "002",
            "title": "团队看板前端设计",
            "description": "Vue3 前端页面开发",
            "assignee": "多纳泰罗",
            "status": "pending",
            "priority": "normal",
            "progress": 0,
            "created_at": "2026-04-16T10:00:00",
            "updated_at": "2026-04-16T10:00:00",
            "cloud_dev": False,
            "dev_tool": None,
            "spec_version": None,
            "session_id": None,
            "cloud_session_active": False
        },
        {
            "id": "003",
            "title": "团队看板后端开发",
            "description": "FastAPI 后端开发",
            "assignee": "拉斐尔",
            "status": "pending",
            "priority": "normal",
            "progress": 0,
            "created_at": "2026-04-16T10:00:00",
            "updated_at": "2026-04-16T10:00:00",
            "cloud_dev": False,
            "dev_tool": None,
            "spec_version": None,
            "session_id": None,
            "cloud_session_active": False
        },
        {
            "id": "004",
            "title": "MD↔Office Skills",
            "description": "Markdown 与 Office 文档转换",
            "assignee": "大黄蜂",
            "status": "completed",
            "priority": "high",
            "progress": 100,
            "created_at": "2026-04-16T10:00:00",
            "updated_at": "2026-04-16T15:00:00",
            "completed_at": "2026-04-16T15:00:00",
            "cloud_dev": False,
            "dev_tool": None,
            "spec_version": None,
            "session_id": None,
            "cloud_session_active": False
        },
        {
            "id": "005",
            "title": "任务看板与开发计划整合",
            "description": "将任务看板与开发计划整合，建立从属关系",
            "assignee": "多纳泰罗",
            "status": "in_progress",
            "priority": "high",
            "progress": 85,
            "created_at": "2026-04-16T11:21:00",
            "updated_at": "2026-04-16T16:00:00",
            "cloud_dev": True,
            "dev_tool": "claude-code",
            "spec_version": "1.0",
            "session_id": "clear-shore",
            "cloud_session_active": False,
            "files_created": [
                "frontend/src/api/taskPlan.ts",
                "frontend/src/stores/taskPlanStore.ts",
                "frontend/src/components/PlanCard.vue",
                "frontend/src/components/PlanList.vue"
            ],
            "commits": 0
        },
        {
            "id": "006",
            "title": "西部小镇多智能体咖啡馆",
            "description": "创建西部小镇风格的智能体社交空间",
            "assignee": "全栈团队",
            "status": "in_progress",
            "priority": "high",
            "progress": 75,
            "created_at": "2026-04-16T11:21:00",
            "updated_at": "2026-04-16T16:00:00",
            "cloud_dev": True,
            "dev_tool": "claude-code",
            "spec_version": "1.0",
            "session_id": "tidy-claw",
            "cloud_session_active": False,
            "files_created": [
                "frontend/src/components/CafeScene.vue"
            ],
            "commits": 0
        },
        {
            "id": "007",
            "title": "新闻资讯热力图地球",
            "description": "构建热力图地球和新闻资讯动态交互界面",
            "assignee": "忍者神龟团队",
            "status": "in_progress",
            "priority": "high",
            "progress": 80,
            "created_at": "2026-04-16T11:21:00",
            "updated_at": "2026-04-16T16:00:00",
            "cloud_dev": True,
            "dev_tool": "claude-code",
            "spec_version": "1.0",
            "session_id": "glow-lagoon",
            "cloud_session_active": False,
            "files_created": [
                "frontend/src/components/NewsGlobe.vue",
                "backend/services/news_scraper.py",
                "backend/api/news.py"
            ],
            "commits": 0
        }
    ]
}

# 保存
os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
with open(TASKS_FILE, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)

print(f"✅ 任务数据已初始化：{TASKS_FILE}")
print(f"   总任务数：{len(tasks['tasks'])}")
print(f"   Cloud 开发任务：{sum(1 for t in tasks['tasks'] if t.get('cloud_dev'))}")
