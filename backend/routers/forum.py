from fastapi import APIRouter, HTTPException
from forum_manager import forum_manager

router = APIRouter(prefix="/api", tags=["forum"])


@router.get("/forum/stats")
def get_forum_stats():
    return forum_manager.get_forum_stats()


@router.get("/forum/topics")
def get_forum_topics(limit: int = 50, status: str = "active"):
    topics = forum_manager.get_topics(limit, status)
    return {"topics": topics, "total": len(topics)}


@router.get("/forum/topics/{topic_id}")
def get_forum_topic(topic_id: str):
    topic = forum_manager.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/forum/posts")
def create_forum_post(post_data: dict):
    post = forum_manager.create_post(
        topic_id=post_data.get("topic_id"),
        content=post_data.get("content"),
        author_id=post_data.get("author_id"),
        author_name=post_data.get("author_name"),
    )
    if "error" in post:
        raise HTTPException(status_code=400, detail=post["error"])
    return {"success": True, "post": post}


@router.get("/forum/agent/{agent_id}/stats")
def get_agent_forum_stats(agent_id: str):
    stats = forum_manager.get_agent_stats(agent_id)
    return {"stats": stats}
