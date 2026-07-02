import os
import json
from fastapi import APIRouter

PROJECTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "projects.json")
PROJECTS_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "projects.json"))


def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"projects": []}


router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects")
def get_projects():
    data = load_projects()
    return {"projects": data.get("projects", [])}


@router.get("/projects/{project_id}/burndown")
def get_project_burndown(project_id: str):
    data = load_projects()
    for p in data.get("projects", []):
        if p["id"] == project_id:
            return {"project_id": project_id, "burndown": p.get("burndown", [])}
    return {"error": "project not found"}


@router.get("/projects/{project_id}/milestones")
def get_project_milestones(project_id: str):
    data = load_projects()
    for p in data.get("projects", []):
        if p["id"] == project_id:
            return {"project_id": project_id, "milestones": p.get("milestones", [])}
    return {"error": "project not found"}
