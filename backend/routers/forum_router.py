from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/forum", tags=["forum"])


def _forum_manager():
    from forum_api import forum_manager
    return forum_manager


@router.get("/stats")
def get_forum_stats():
    """获取论坛统计"""
    forum_mgr = _forum_manager()
    return forum_mgr.get_forum_stats()


@router.get("/topics")
def get_forum_topics(limit: int = 50, status: str = "active"):
    """获取主题列表"""
    forum_mgr = _forum_manager()
    topics = forum_mgr.get_topics(limit, status)
    return {"topics": topics, "total": len(topics)}


@router.get("/topics/{topic_id}")
def get_forum_topic_detail(topic_id: str):
    """获取主题详情"""
    forum_mgr = _forum_manager()
    topic = forum_mgr.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/topics")
def create_forum_topic(topic_data: dict):
    """创建主题"""
    title = (topic_data.get("title") or "").strip()
    content = (topic_data.get("content") or "").strip()
    agent_id = (topic_data.get("agent_id") or "").strip()
    agent_name = (topic_data.get("agent_name") or "").strip()
    agent_emoji = (topic_data.get("agent_emoji") or "").strip()

    if not title or not content:
        raise HTTPException(status_code=400, detail="标题和内容不能为空")
    if not agent_id or not agent_name:
        raise HTTPException(status_code=400, detail="缺少发言智能体信息")

    forum_mgr = _forum_manager()
    can_post, reason, _ = forum_mgr.can_agent_post(agent_id)
    if not can_post:
        raise HTTPException(status_code=429, detail=reason)

    topic = forum_mgr.create_topic(
        title=title,
        content=content,
        agent_id=agent_id,
        agent_name=agent_name,
        agent_emoji=agent_emoji,
        tags=topic_data.get("tags", [])
    )
    return {"success": True, "topic": topic}


@router.post("/posts")
def get_forum_posts(topic_id: str = "", limit: int = 50, include_replies: bool = True):
    """获取帖子列表"""
    forum_mgr = _forum_manager()
    posts = forum_mgr.get_posts(topic_id, limit, include_replies)
    return {"posts": posts, "total": len(posts)}


@router.get("/agent/{agent_id}/stats")
def get_agent_forum_stats(agent_id: str):
    """获取智能体论坛统计"""
    forum_mgr = _forum_manager()
    stats = forum_mgr.get_agent_stats(agent_id)
    can_post, reason, remaining = forum_mgr.can_agent_post(agent_id)
    return {
        **stats,
        "can_post": can_post,
        "remaining_posts": remaining
    }
