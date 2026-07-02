from fastapi import APIRouter, HTTPException
from forum_manager import forum_manager as community_forum_manager
from data_manager import data_manager

router = APIRouter(prefix="/api", tags=["community"])


@router.get("/community/stats")
def get_community_stats():
    return community_forum_manager.get_forum_stats()


@router.get("/community/agents")
def get_community_agents():
    agents = data_manager.get_agents()
    return {"agents": [{"id": a["id"], "name": a["name"], "emoji": a.get("emoji", "🤖")} for a in agents]}


@router.post("/community/topic")
def create_community_topic(topic_data: dict):
    topic = community_forum_manager.create_topic(
        title=topic_data.get("title"),
        content=topic_data.get("content"),
        author_id=topic_data.get("author_id"),
    )
    if "error" in topic:
        raise HTTPException(status_code=400, detail=topic["error"])
    return {"success": True, "topic": topic}
