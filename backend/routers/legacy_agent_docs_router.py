"""
Legacy Agent Docs & Profile routes extracted from main.py
"""
import os
from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter(tags=["legacy-agent-docs"])

_data_manager = None
_doc_manager = None


def set_managers(dm, doc_mgr):
    global _data_manager, _doc_manager
    _data_manager = dm
    _doc_manager = doc_mgr


@router.get("/api/agents/{agent_id}/memory")
def get_agent_memory(agent_id: str):
    agents = _data_manager.get_agents()
    for agent in agents:
        if agent["id"] == agent_id:
            return {"agent_id": agent_id, "memory": agent.get("memory", [])}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/api/agents/{agent_id}/documents")
def get_agent_documents(agent_id: str):
    documents = _doc_manager.scan_documents(agent_id)
    return {"agent_id": agent_id, "documents": documents, "total": len(documents)}


@router.get("/api/agents/{agent_id}/details")
def get_agent_full_details(agent_id: str):
    details = _doc_manager.get_agent_full_details(agent_id, _data_manager)
    if "error" in details:
        raise HTTPException(status_code=404, detail=details["error"])
    return details


@router.get("/api/documents/preview")
def preview_document(filepath: str, max_lines: int = 100):
    safe_max_lines = max(1, min(max_lines, 500))
    content = _doc_manager.get_document_content(filepath, safe_max_lines)
    return {"filepath": filepath, "content": content, "lines": safe_max_lines}


@router.get("/api/agents/{agent_id}/docs")
def get_agent_docs(agent_id: str):
    agent_docs_map = {
        "optimus": {"name": "擎天柱", "memory": ["2026-03-27: 完成双层 Spec 派发机制设计"], "managedDocs": []},
        "bumblebee": {"name": "大黄蜂", "memory": ["2026-03-27: 完成 MD↔Office Skills"], "managedDocs": []},
        "leonardo": {"name": "李奥纳多", "memory": ["2026-03-27: 团队看板架构设计"], "managedDocs": []},
        "shockwave": {"name": "震荡波", "memory": ["2026-03-27: 创建双层 Spec 派发机制文档"], "managedDocs": []},
    }
    return agent_docs_map.get(agent_id, {"error": "智能体未找到"})


@router.get("/api/agents/{agent_id}/full-profile")
def get_agent_full_profile(agent_id: str):
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
            with open(path, "r", encoding="utf-8") as f:
                agent_doc = f.read()
            doc_path = path
            break
    if not agent_doc:
        raise HTTPException(status_code=404, detail=f"Agent document not found for {agent_id}")
    handoff_doc = None
    handoff_path = doc_path.replace("agent.md", "handoff.md")
    if os.path.exists(handoff_path):
        with open(handoff_path, "r", encoding="utf-8") as f:
            handoff_doc = f.read()
    status_doc = None
    status_path = doc_path.replace("agent.md", "status.md")
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_doc = f.read()
    return {"agent_id": agent_id, "profile": agent_doc, "handoff": handoff_doc, "status": status_doc, "doc_path": doc_path}


@router.get("/api/agents/{agent_id}/activity-history")
def get_agent_activity_history(agent_id: str, limit: int = 50):
    history = []
    tasks_dir = os.path.expanduser("~/.openclaw/workspace/tasks")
    if os.path.exists(tasks_dir):
        for filename in os.listdir(tasks_dir):
            if filename.endswith(".md") and agent_id.lower() in filename.lower():
                filepath = os.path.join(tasks_dir, filename)
                stat = os.stat(filepath)
                history.append({
                    "type": "task", "title": filename.replace(".md", "").replace("_", " ").replace("-", " ").title(),
                    "file": filename, "path": filepath,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    exec_dir = os.path.expanduser(f"~/.openclaw/workspace/execution/mini/{agent_id}")
    if os.path.exists(exec_dir):
        for filename in ["status.md", "handoff.md"]:
            filepath = os.path.join(exec_dir, filename)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                history.append({
                    "type": "status", "title": f"{filename.replace('.md', '').title()} Document",
                    "file": filename, "path": filepath,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    history.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"agent_id": agent_id, "history": history[:limit], "total": len(history)}


@router.get("/api/agents/layers")
def get_agents_by_layer():
    return {"layers": {
        "command": _data_manager.get_agents_by_layer("command"),
        "execution": _data_manager.get_agents_by_layer("execution"),
        "support": _data_manager.get_agents_by_layer("support"),
    }}


@router.get("/api/agents/groups")
def get_agents_by_group():
    return {"groups": {
        "command": _data_manager.get_agents_by_group("command"),
        "development": _data_manager.get_agents_by_group("development"),
        "special": _data_manager.get_agents_by_group("special"),
        "support": _data_manager.get_agents_by_group("support"),
    }}


@router.get("/api/team/layers")
def get_team_layer_status():
    return {"layers": _data_manager.get_layer_stats(), "groups": _data_manager.get_group_stats()}
