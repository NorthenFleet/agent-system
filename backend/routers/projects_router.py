import os
import json

from fastapi import APIRouter, HTTPException

PROJECTS_FILE = os.path.join(os.path.dirname(__file__), "data", "projects.json")


def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"projects": []}


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def get_projects():
    data = load_projects()
    return {"projects": data.get("projects", [])}


@router.get("/burndown")
def get_burndown():
    """获取所有项目的燃尽图数据"""
    data = load_projects()
    burndown_data = []
    for p in data.get("projects", []):
        burndown_data.append({
            "project_id": p["id"],
            "burndown": p.get("burndown", [])
        })
    return {"burndown": burndown_data}


@router.get("/{project_id}/burndown")
def get_project_burndown(project_id: str):
    data = load_projects()
    for p in data.get("projects", []):
        if p["id"] == project_id:
            return {"project_id": project_id, "burndown": p.get("burndown", [])}
    raise HTTPException(status_code=404, detail="项目不存在")


@router.get("/{project_id}/milestones")
def get_project_milestones(project_id: str):
    data = load_projects()
    for p in data.get("projects", []):
        if p["id"] == project_id:
            return {"project_id": project_id, "milestones": p.get("milestones", [])}
    raise HTTPException(status_code=404, detail="项目不存在")
