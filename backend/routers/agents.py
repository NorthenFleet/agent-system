from fastapi import APIRouter, HTTPException
from typing import Optional

from data_manager import data_manager
from task_queue import task_manager
from document_manager import doc_manager

router = APIRouter(prefix="/api", tags=["agents"])


def _get_agent_emoji(agent_id: str) -> str:
    """根据智能体 ID 返回对应的 emoji"""
    emoji_map = {
        "optimus": "🤖",
        "bumblebee": "🐝",
        "leonardo": "🟦",
        "raphael": "🟥",
        "donatello": "🟪",
        "michelangelo": "🟧",
        "ironhide": "🛡️",
        "perceptor": "🔬",
        "wheeljack": "🔧",
        "shockwave": "🟣",
    }
    return emoji_map.get(agent_id, "👤")


@router.get("/agents")
def get_agents():
    return {"agents": data_manager.get_agents(), "total": len(data_manager.get_agents())}


@router.get("/team/status")
def get_team_status():
    agents = data_manager.get_agents()
    return {
        "total_agents": len(agents),
        "online": sum(1 for a in agents if a["status"] == "online"),
        "busy": sum(1 for a in agents if a["status"] == "busy"),
        "idle": sum(1 for a in agents if a["status"] == "idle"),
        "pending": sum(1 for a in agents if a["status"] == "pending"),
        "autobots_count": sum(1 for a in agents if a["team"] == "autobots"),
        "ninja_turtles_count": sum(1 for a in agents if a["team"] == "ninja_turtles"),
        "task_stats": task_manager.get_stats()
    }


@router.get("/agents/{agent_id}/memory")
def get_agent_memory(agent_id: str):
    agents = data_manager.get_agents()
    for agent in agents:
        if agent["id"] == agent_id:
            return {"agent_id": agent_id, "memory": agent.get("memory", [])}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/agents/{agent_id}/documents")
def get_agent_documents(agent_id: str):
    documents = doc_manager.scan_documents(agent_id)
    return {"agent_id": agent_id, "documents": documents, "total": len(documents)}


@router.get("/agents/{agent_id}/details")
def get_agent_full_details(agent_id: str):
    details = doc_manager.get_agent_full_details(agent_id, data_manager)
    if "error" in details:
        raise HTTPException(status_code=404, detail=details["error"])
    return details


@router.get("/agents/{agent_id}/docs")
def get_agent_docs(agent_id: str):
    """获取智能体管理的文档"""
    agent_docs_map = {
        "optimus": {
            "name": "擎天柱",
            "memory": [
                "2026-03-27: 完成双层 Spec 派发机制设计",
                "2026-03-27: 开始任务统筹工作",
                "2026-03-20: 确立擎天柱工作原则 - 只分工不执行"
            ],
            "managedDocs": [
                {"name": "团队任务看板", "path": "tasks/dashboard.md", "type": "任务管理"},
                {"name": "智能体分工表", "path": "agents/assignments.md", "type": "团队管理"}
            ]
        },
        "bumblebee": {
            "name": "大黄蜂",
            "memory": [
                "2026-03-27: 完成 MD↔Office Skills (100%)",
                "2026-03-27: 开始运维监控与任务监督",
                "2026-03-27: 职责从架构师变更为运维负责人",
                "2026-03-18: 完成团队看板架构搭建"
            ],
            "managedDocs": [
                {"name": "任务分配记录", "path": "tasks/assignments.md", "type": "任务管理"},
                {"name": "运维监控日志", "path": "ops/monitoring.md", "type": "运维管理"},
                {"name": "Skills 文档", "path": "skills/md-office.md", "type": "技能文档"}
            ]
        },
        "leonardo": {
            "name": "李奥纳多",
            "memory": [
                "2026-03-27: 团队看板架构设计 (30%)",
                "2026-03-27: 学习双层 Spec 派发机制",
                "2026-03-27: 确立开发级 Spec 职责"
            ],
            "managedDocs": [
                {"name": "系统架构设计", "path": "architecture/system.md", "type": "架构文档"},
                {"name": "技术方案文档", "path": "architecture/tech-specs.md", "type": "技术方案"}
            ]
        },
        "shockwave": {
            "name": "震荡波",
            "memory": [
                "2026-03-27: 创建双层 Spec 派发机制文档",
                "2026-03-27: 震荡波角色创建",
                "2026-03-27: 逻辑至上，分析团队架构"
            ],
            "managedDocs": [
                {"name": "团队架构文档", "path": "architecture/team-structure.md", "type": "架构管理"},
                {"name": "Spec 派发机制", "path": "specs/dispatch-mechanism.md", "type": "流程文档"},
                {"name": "效率分析报告", "path": "analysis/efficiency.md", "type": "分析报告"}
            ]
        }
    }

    return agent_docs_map.get(agent_id, {"error": "智能体未找到"})


@router.get("/agents/{agent_id}/full-profile")
def get_agent_full_profile(agent_id: str):
    """获取智能体完整档案（从文档读取）"""
    import os

    possible_paths = [
        os.path.expanduser(f"~/.openclaw/workspace/execution/mini/{agent_id}/agent.md"),
        os.path.expanduser(f"~/.openclaw/workspace/agents/{agent_id}.md"),
        os.path.expanduser(f"~/.openclaw/workspace/agents/command/{agent_id}.md"),
        os.path.expanduser(f"~/.openclaw/workspace/agents/planning/{agent_id}.md"),
    ]

    agent_doc = None
    doc_path = None

    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                agent_doc = f.read()
            doc_path = path
            break

    if not agent_doc:
        raise HTTPException(status_code=404, detail=f"Agent document not found for {agent_id}")

    handoff_doc = None
    handoff_path = doc_path.replace("agent.md", "handoff.md")
    if os.path.exists(handoff_path):
        with open(handoff_path, 'r', encoding='utf-8') as f:
            handoff_doc = f.read()

    status_doc = None
    status_path = doc_path.replace("agent.md", "status.md")
    if os.path.exists(status_path):
        with open(status_path, 'r', encoding='utf-8') as f:
            status_doc = f.read()

    return {
        "agent_id": agent_id,
        "profile": agent_doc,
        "handoff": handoff_doc,
        "status": status_doc,
        "doc_path": doc_path
    }


@router.get("/agents/{agent_id}/activity-history")
def get_agent_activity_history(agent_id: str, limit: int = 50):
    """获取智能体活动历史"""
    import os
    from datetime import datetime

    history = []

    tasks_dir = os.path.expanduser("~/.openclaw/workspace/tasks")
    if os.path.exists(tasks_dir):
        for filename in os.listdir(tasks_dir):
            if filename.endswith('.md') and agent_id.lower() in filename.lower():
                filepath = os.path.join(tasks_dir, filename)
                stat = os.stat(filepath)
                history.append({
                    "type": "task",
                    "title": filename.replace('.md', '').replace('_', ' ').replace('-', ' ').title(),
                    "file": filename,
                    "path": filepath,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

    exec_dir = os.path.expanduser(f"~/.openclaw/workspace/execution/mini/{agent_id}")
    if os.path.exists(exec_dir):
        for filename in ['status.md', 'handoff.md']:
            filepath = os.path.join(exec_dir, filename)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                history.append({
                    "type": "status",
                    "title": f"{filename.replace('.md', '').title()} Document",
                    "file": filename,
                    "path": filepath,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

    history.sort(key=lambda x: x['updated_at'], reverse=True)

    return {
        "agent_id": agent_id,
        "history": history[:limit],
        "total": len(history)
    }


@router.get("/agents/layers")
def get_agents_by_layer():
    """按层级获取智能体"""
    layers = {
        "command": data_manager.get_agents_by_layer("command"),
        "execution": data_manager.get_agents_by_layer("execution"),
        "support": data_manager.get_agents_by_layer("support")
    }
    return {"layers": layers}


@router.get("/agents/groups")
def get_agents_by_group():
    """按组获取智能体"""
    groups = {
        "command": data_manager.get_agents_by_group("command"),
        "development": data_manager.get_agents_by_group("development"),
        "special": data_manager.get_agents_by_group("special"),
        "support": data_manager.get_agents_by_group("support")
    }
    return {"groups": groups}


@router.get("/team/layers")
def get_team_layer_status():
    """获取团队层级状态"""
    return {
        "layers": data_manager.get_layer_stats(),
        "groups": data_manager.get_group_stats()
    }
