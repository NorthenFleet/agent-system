"""
Legacy Community, Chat & Forum routes extracted from main.py
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["legacy-community-chat-forum"])

_community_manager = None
_chat_manager = None
_forum_manager = None


def set_managers(cm, chat_mgr, forum_mgr):
    global _community_manager, _chat_manager, _forum_manager
    _community_manager = cm
    _chat_manager = chat_mgr
    _forum_manager = forum_mgr


# ─── Community ───

@router.get("/api/community/stats")
def get_community_stats():
    return _community_manager.get_community_stats()


@router.get("/api/community/topics")
def get_topics(limit: int = 50, status: str = "active"):
    topics = _community_manager.get_topics(limit, status)
    return {"topics": topics, "total": len(topics)}


@router.get("/api/community/topics/{topic_id}")
def get_topic(topic_id: str):
    topic = _community_manager.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/api/community/topics")
def create_topic(topic_data: dict):
    topic = _community_manager.create_topic(
        title=topic_data.get("title", ""), content=topic_data.get("content", ""),
        creator_id=topic_data.get("creator_id", ""), creator_name=topic_data.get("creator_name", ""),
        tags=topic_data.get("tags", []),
    )
    return {"success": True, "topic": topic}


@router.post("/api/community/replies")
def create_reply(reply_data: dict):
    reply = _community_manager.create_reply(
        topic_id=reply_data.get("topic_id", ""), content=reply_data.get("content", ""),
        creator_id=reply_data.get("creator_id", ""), creator_name=reply_data.get("creator_name", ""),
        referenced_memory=reply_data.get("referenced_memory"),
    )
    if "error" in reply:
        raise HTTPException(status_code=404, detail=reply["error"])
    return {"success": True, "reply": reply}


@router.get("/api/community/agent/{agent_id}/topics")
def get_agent_topics(agent_id: str):
    return {"topics": _community_manager.get_agent_topics(agent_id), "total": len(_community_manager.get_agent_topics(agent_id))}


@router.get("/api/community/agent/{agent_id}/replies")
def get_agent_replies(agent_id: str):
    return {"replies": _community_manager.get_agent_replies(agent_id), "total": len(_community_manager.get_agent_replies(agent_id))}


@router.get("/api/community/agent/{agent_id}/can-post")
def check_can_post(agent_id: str):
    can_post, reason, remaining = _community_manager.can_agent_post(agent_id)
    return {"can_post": can_post, "reason": reason, "remaining": remaining}


@router.post("/api/community/agent/{agent_id}/post")
def record_post(agent_id: str):
    _community_manager.record_post(agent_id)
    return {"success": True}


@router.get("/api/community/agents/stats")
def get_community_agents_stats():
    from routers.legacy_agents_router import get_agent_emoji
    agents = []  # Need data_manager reference
    return {"agents": agents, "total": 0}


# ─── Chat ───

@router.post("/api/chat/send")
def send_chat_message(agent_id: str, agent_name: str, text: str):
    return _chat_manager.send_to_agent(agent_id, agent_name, text)


@router.get("/api/chat/conversations/{agent_id}")
def get_chat_conversations(agent_id: str):
    return _chat_manager.get_conversations(agent_id)


@router.get("/api/chat/conversations")
def get_all_chat_conversations():
    return _chat_manager.get_all_conversations()


@router.post("/api/chat/conversations/{agent_id}/clear")
def clear_chat_conversations(agent_id: str):
    success = _chat_manager.clear_conversations(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": "已清空"}


# ─── Forum ───

@router.get("/api/forum/stats")
def get_forum_stats():
    return _forum_manager.get_forum_stats()


@router.get("/api/forum/topics")
def get_forum_topics(limit: int = 50, status: str = "active"):
    topics = _forum_manager.get_topics(limit, status)
    return {"topics": topics, "total": len(topics)}


@router.get("/api/forum/topics/{topic_id}")
def get_forum_topic(topic_id: str):
    topic = _forum_manager.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.post("/api/forum/topics")
def create_forum_topic(topic_data: dict):
    topic = _forum_manager.create_topic(
        title=topic_data.get("title", ""), content=topic_data.get("content", ""),
        agent_id=topic_data.get("agent_id", ""), agent_name=topic_data.get("agent_name", ""),
        agent_emoji=topic_data.get("agent_emoji", ""), tags=topic_data.get("tags", []),
    )
    return {"success": True, "topic": topic}


@router.post("/api/forum/posts")
def create_forum_post(post_data: dict):
    post = _forum_manager.create_post(
        topic_id=post_data.get("topic_id", ""), content=post_data.get("content", ""),
        agent_id=post_data.get("agent_id", ""), agent_name=post_data.get("agent_name", ""),
        agent_emoji=post_data.get("agent_emoji", ""), parent_post_id=post_data.get("parent_post_id"),
    )
    if "error" in post:
        raise HTTPException(status_code=404, detail=post["error"])
    return {"success": True, "post": post}


@router.get("/api/forum/agent/{agent_id}/stats")
def get_agent_forum_stats(agent_id: str):
    stats = _forum_manager.get_agent_stats(agent_id)
    can_post, reason, remaining = _forum_manager.can_agent_post(agent_id)
    return {**stats, "can_post": can_post, "remaining_posts": remaining}
