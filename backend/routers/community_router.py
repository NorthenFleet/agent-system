from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/community", tags=["community"])


def _community_manager():
    from community_manager import community_manager
    return community_manager


@router.get("/stats")
def get_community_stats():
    """获取社区统计"""
    community_mgr = _community_manager()
    return community_mgr.get_community_stats()


@router.get("/topics")
def get_community_topics(limit: int = 50, status: str = "active"):
    """获取主题列表"""
    community_mgr = _community_manager()
    topics = community_mgr.get_topics(limit, status)
    return {"topics": topics, "total": len(topics)}


@router.get("/topics/{topic_id}")
def get_community_topic_detail(topic_id: str):
    """获取主题详情"""
    community_mgr = _community_manager()
    topic = community_mgr.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/topics")
def create_community_topic(topic_data: dict):
    """创建主题"""
    community_mgr = _community_manager()
    topic = community_mgr.create_topic(
        title=topic_data.get("title", ""),
        content=topic_data.get("content", ""),
        creator_id=topic_data.get("creator_id", ""),
        creator_name=topic_data.get("creator_name", ""),
        tags=topic_data.get("tags", [])
    )
    return {"success": True, "topic": topic}


@router.get("/replies")
def get_community_replies(topic_id: str = "", limit: int = 50, status: str = "active"):
    """获取回复列表"""
    community_mgr = _community_manager()
    replies = community_mgr.get_replies(topic_id, limit, status)
    return {"replies": replies, "total": len(replies)}


@router.post("/replies")
def create_community_reply(reply_data: dict):
    """创建回复"""
    community_mgr = _community_manager()
    reply = community_mgr.create_reply(
        topic_id=reply_data.get("topic_id", ""),
        content=reply_data.get("content", ""),
        creator_id=reply_data.get("creator_id", ""),
        creator_name=reply_data.get("creator_name", ""),
        referenced_memory=reply_data.get("referenced_memory")
    )
    if "error" in reply:
        raise HTTPException(status_code=404, detail=reply["error"])
    return {"success": True, "reply": reply}


@router.get("/agent/{agent_id}/topics")
def get_agent_community_topics(agent_id: str):
    """获取智能体创建的主题"""
    community_mgr = _community_manager()
    topics = community_mgr.get_agent_topics(agent_id)
    return {"topics": topics, "total": len(topics)}


@router.get("/agent/{agent_id}/replies")
def get_agent_community_replies(agent_id: str):
    """获取智能体的回复"""
    community_mgr = _community_manager()
    replies = community_mgr.get_agent_replies(agent_id)
    return {"replies": replies, "total": len(replies)}


@router.get("/agent/{agent_id}/can-post")
def check_can_post(agent_id: str):
    """检查智能体是否可以发言"""
    community_mgr = _community_manager()
    can_post, reason, remaining = community_mgr.can_agent_post(agent_id)
    return {
        "can_post": can_post,
        "reason": reason,
        "remaining": remaining
    }


@router.post("/agent/{agent_id}/post")
def post_as_agent(agent_id: str):
    """记录智能体发言"""
    community_mgr = _community_manager()
    community_mgr.record_post(agent_id)
    return {"success": True}


@router.get("/agents/stats")
def get_agents_community_stats():
    """获取智能体社区统计"""
    community_mgr = _community_manager()
    return community_mgr.get_agents_stats()
