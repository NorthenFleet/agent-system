#!/usr/bin/env python3
"""
团队数据管理器 - 动态管理智能体、设备、任务数据
支持实时更新和持久化存储
包含每个智能体的配置和记忆
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")

# 默认数据 - 包含配置和记忆
DEFAULT_AGENTS = [
    {
        "id": "optimus",
        "slogan": "🤖 使命必达",
        "name": "擎天柱",
        "role": "Team Leader",
        "status": "online",
        "team": "autobots",
        "current_task": "任务统筹",
        "device_id": "mac-pro-1",
        "emoji": "🤖",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=optimus",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "off",
            "tools": ["sessions_spawn", "message", "exec", "web_search"],
            "permissions": ["task_dispatch", "result_aggregate", "spec_generate"],
            "spec_role": "Commander + Spec Officer"
        },
        "memory": [
            "2026-03-27: 完成双层 Spec 派发机制设计",
            "2026-03-27: 开始任务统筹工作",
            "2026-03-20: 确立擎天柱工作原则 - 只分工不执行"
        ],
        "stats": {"tasks_completed": 15, "tasks_in_progress": 1, "total_messages": 234},
        "created_at": "2026-03-17"
    },
    {
        "id": "bumblebee",
        "slogan": "🐝 守护系统",
        "name": "大黄蜂",
        "role": "运维负责人",
        "status": "busy",
        "team": "autobots",
        "current_task": "运维监控与任务监督",
        "device_id": "mac-pro-1",
        "emoji": "🐝",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=bumblebee",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "off",
            "tools": ["exec", "process", "nodes", "message"],
            "permissions": ["system_monitor", "task_supervise", "service_deploy"],
            "responsibilities": ["运维监控", "任务监督", "跨团队协调"]
        },
        "memory": [
            "2026-03-27: 完成 MD↔Office Skills (100%)",
            "2026-03-27: 开始运维监控与任务监督",
            "2026-03-27: 职责从架构师变更为运维负责人",
            "2026-03-18: 完成团队看板架构搭建"
        ],
        "stats": {"tasks_completed": 8, "tasks_in_progress": 0, "total_messages": 156},
        "created_at": "2026-03-17"
    },
    {
        "id": "leonardo",
        "slogan": "🐢 架构至上",
        "name": "李奥纳多",
        "role": "架构师",
        "status": "busy",
        "team": "ninja_turtles",
        "current_task": "架构设计",
        "device_id": "mac-pro-1",
        "emoji": "🐢",
        "avatar": "/static/icons/turtles/leonardo.svg",
        "config": {
            "model": "claude-opus",
            "thinking": "on",
            "tools": ["read", "write", "edit", "exec"],
            "permissions": ["dev_spec_generate", "tech_design", "task_decompose"],
            "spec_role": "Architect"
        },
        "memory": [
            "2026-03-27: 团队看板架构设计 (30%)",
            "2026-03-27: 学习双层 Spec 派发机制",
            "2026-03-27: 确立开发级 Spec 职责"
        ],
        "stats": {"tasks_completed": 5, "tasks_in_progress": 1, "total_messages": 89},
        "created_at": "2026-03-17"
    },
    {
        "id": "raphael",
        "slogan": "🥷 代码为王",
        "name": "拉斐尔",
        "role": "后端工程师",
        "status": "idle",
        "team": "ninja_turtles",
        "current_task": "等待任务",
        "device_id": "mac-pro-1",
        "emoji": "🥷",
        "avatar": "/static/icons/turtles/raphael.svg",
        "config": {
            "model": "codex",
            "thinking": "off",
            "tools": ["read", "write", "edit", "exec"],
            "permissions": ["backend_dev", "api_design", "database"],
            "specialties": ["FastAPI", "Python", "数据库设计"]
        },
        "memory": [
            "2026-03-27: 等待看板后端开发任务",
            "2026-03-18: 学习 FastAPI 框架"
        ],
        "stats": {"tasks_completed": 3, "tasks_in_progress": 0, "total_messages": 45},
        "created_at": "2026-03-17"
    },
    {
        "id": "donatello",
        "slogan": "🥷 体验至上",
        "name": "多纳泰罗",
        "role": "前端工程师",
        "status": "idle",
        "team": "ninja_turtles",
        "current_task": "等待任务",
        "device_id": "macbook-pro-1",
        "emoji": "🥷",
        "avatar": "/static/icons/turtles/donatello.svg",
        "config": {
            "model": "gemini",
            "thinking": "off",
            "tools": ["read", "write", "edit", "browser"],
            "permissions": ["frontend_dev", "ui_design", "pwa"],
            "specialties": ["Vue3", "TypeScript", "响应式设计"]
        },
        "memory": [
            "2026-03-27: 等待看板前端开发任务",
            "2026-03-18: 学习 Vue3 和 Element Plus"
        ],
        "stats": {"tasks_completed": 4, "tasks_in_progress": 0, "total_messages": 52},
        "created_at": "2026-03-17"
    },
    {
        "id": "michelangelo",
        "slogan": "🥷 质量为本",
        "name": "米开朗基罗",
        "role": "测试工程师",
        "status": "idle",
        "team": "ninja_turtles",
        "current_task": "等待任务",
        "device_id": "macbook-pro-1",
        "emoji": "🥷",
        "avatar": "/static/icons/turtles/michelangelo.svg",
        "config": {
            "model": "codex",
            "thinking": "off",
            "tools": ["exec", "read", "write"],
            "permissions": ["test_write", "e2e_test", "ci_cd"],
            "specialties": ["Playwright", "pytest", "CI/CD"]
        },
        "memory": [
            "2026-03-27: 等待测试配置任务",
            "2026-03-18: 学习 Playwright 测试框架"
        ],
        "stats": {"tasks_completed": 2, "tasks_in_progress": 0, "total_messages": 31},
        "created_at": "2026-03-17"
    },
    {
        "id": "ironhide",
        "slogan": "🛡️ 铁皮永远忠诚",
        "name": "铁皮",
        "role": "训练专家",
        "status": "idle",
        "team": "autobots",
        "current_task": "Isaac Sim 测试",
        "device_id": "linux-workstation-1",
        "emoji": "🛡️",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=ironhide",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "off",
            "tools": ["exec", "nodes", "process"],
            "permissions": ["sim_run", "robot_train", "isaac_sim"],
            "environment": "Ubuntu 24.04 + Isaac Sim 6.0"
        },
        "memory": [
            "2026-03-27: 六足机器人项目 (83% 完成)",
            "2026-03-27: 创建 URDF 模型 (3 个文件)",
            "2026-03-21: Isaac Sim 安装完成",
            "2026-03-20: 铁皮服务器配置完成"
        ],
        "stats": {"tasks_completed": 6, "tasks_in_progress": 1, "total_messages": 78},
        "created_at": "2026-03-17"
    },
    {
        "id": "perceptor",
        "slogan": "🚗 精打细算",
        "name": "感知器",
        "role": "财务管理员",
        "status": "idle",
        "team": "autobots",
        "current_task": "等待发票",
        "device_id": "mac-pro-1",
        "emoji": "🚗",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=perceptor",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "off",
            "tools": ["read", "exec", "message"],
            "permissions": ["finance_manage", "invoice_process", "paper_monitor"],
            "email_monitor": ["发票邮件", "论文邮件"]
        },
        "memory": [
            "2026-03-27: 增加论文邮件检索职责",
            "2026-03-27: 等待发票邮件",
            "2026-03-19: 确立只处理发票邮件策略",
            "2026-03-17: 感知器角色创建"
        ],
        "stats": {"tasks_completed": 12, "tasks_in_progress": 0, "total_messages": 167},
        "created_at": "2026-03-17"
    },
    {
        "id": "wheeljack",
        "slogan": "🔧 工具驱动",
        "name": "千斤顶",
        "role": "工程师",
        "status": "idle",
        "team": "autobots",
        "current_task": "等待任务",
        "device_id": "mac-pro-1",
        "emoji": "🔧",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=wheeljack",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "off",
            "tools": ["exec", "read", "write", "process"],
            "permissions": ["cicd_build", "automation", "tool_dev"],
            "specialties": ["CI/CD", "自动化脚本", "工具链"]
        },
        "memory": [
            "2026-03-27: 千斤顶角色创建",
            "2026-03-27: 等待 CI/CD 流水线任务"
        ],
        "stats": {"tasks_completed": 0, "tasks_in_progress": 0, "total_messages": 5},
        "created_at": "2026-03-27"
    },
    {
        "id": "shockwave",
        "slogan": "🟣 逻辑至上",
        "name": "震荡波",
        "role": "团队优化师",
        "status": "online",
        "team": "decepticons",
        "current_task": "组织架构分析",
        "device_id": "mac-pro-1",
        "emoji": "🟣",
        "avatar": "https://api.dicebear.com/7.x/bottts/svg?seed=shockwave",
        "config": {
            "model": "qwen3.5-plus",
            "thinking": "on",
            "tools": ["read", "write", "analysis"],
            "permissions": ["org_analyze", "process_optimize", "role_define"],
            "specialties": ["组织架构", "业务流程", "效率分析"]
        },
        "memory": [
            "2026-03-27: 创建双层 Spec 派发机制文档",
            "2026-03-27: 震荡波角色创建",
            "2026-03-27: 逻辑至上，分析团队架构"
        ],
        "stats": {"tasks_completed": 2, "tasks_in_progress": 1, "total_messages": 23},
        "created_at": "2026-03-27"
    },
]

DEFAULT_DEVICES = [
    {"id": "mac-pro-1", "name": "擎天柱-MacPro", "ip": "192.168.31.41", "os": "macOS Sonoma", "role": "核心开发服务器", "status": "online", "assigned_agents": ["optimus", "bumblebee", "leonardo", "raphael", "perceptor", "wheeljack", "shockwave"]},
    {"id": "macbook-pro-1", "name": "李奥纳多-MacBookPro", "ip": "192.168.31.41", "os": "macOS Sonoma", "role": "开发工作站", "status": "online", "assigned_agents": ["donatello", "michelangelo"]},
    {"id": "linux-workstation-1", "name": "铁皮-LinuxWS", "ip": "192.168.1.4", "os": "Ubuntu 24.04", "role": "AI 训练服务器", "status": "online", "assigned_agents": ["ironhide"]},
]

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filepath: str, default: Any) -> Any:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(filepath: str, data: Any):
    ensure_data_dir()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

class DataManager:
    def __init__(self):
        ensure_data_dir()
        self.agents = load_json(AGENTS_FILE, DEFAULT_AGENTS)
        self.devices = load_json(DEVICES_FILE, DEFAULT_DEVICES)
        self.tasks = load_json(TASKS_FILE, {"tasks": []})
    
    def get_agents(self) -> List[Dict]:
        return self.agents
    
    def get_devices(self) -> List[Dict]:
        return self.devices
    
    def get_tasks(self) -> List[Dict]:
        return self.tasks.get("tasks", [])
    
    def update_agent(self, agent_id: str, updates: Dict) -> bool:
        for agent in self.agents:
            if agent["id"] == agent_id:
                agent.update(updates)
                agent["updated_at"] = datetime.now().isoformat()
                save_json(AGENTS_FILE, self.agents)
                return True
        return False
    
    def update_task(self, task_id: str, updates: Dict) -> bool:
        for task in self.tasks.get("tasks", []):
            if task["id"] == task_id:
                task.update(updates)
                task["updated_at"] = datetime.now().isoformat()
                save_json(TASKS_FILE, self.tasks)
                return True
        return False
    
    def add_task(self, task: Dict) -> Dict:
        task["created_at"] = datetime.now().isoformat()
        task["updated_at"] = task["created_at"]
        self.tasks.setdefault("tasks", []).append(task)
        save_json(TASKS_FILE, self.tasks)
        return task
    
    def get_team_status(self) -> Dict:
        total = len(self.agents)
        online = sum(1 for a in self.agents if a["status"] == "online")
        busy = sum(1 for a in self.agents if a["status"] == "busy")
        idle = sum(1 for a in self.agents if a["status"] == "idle")
        
        tasks = self.tasks.get("tasks", [])
        task_stats = {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t["status"] == "pending"),
            "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
            "failed": sum(1 for t in tasks if t["status"] == "failed"),
        }
        
        return {
            "total_agents": total,
            "online": online,
            "busy": busy,
            "idle": idle,
            "pending": 0,
            "autobots_count": sum(1 for a in self.agents if a["team"] == "autobots"),
            "ninja_turtles_count": sum(1 for a in self.agents if a["team"] == "ninja_turtles"),
            "task_stats": task_stats,
        }

# 单例
data_manager = DataManager()

if __name__ == "__main__":
    print("Agents:", len(data_manager.get_agents()))
    print("Devices:", len(data_manager.get_devices()))
    print("Tasks:", len(data_manager.get_tasks()))
    print("Team Status:", data_manager.get_team_status())
