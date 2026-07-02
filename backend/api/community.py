"""
社区管理 API (社区 + 帖子 + 评论 + 通知)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["community"])

# ==================== Pydantic Models ====================

class CommunityCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    rules: Optional[str] = ""
    member_count: int = 0
    is_active: bool = True

class CommunityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[str] = None
    is_active: Optional[bool] = None

class PostCreate(BaseModel):
    community_id: int
    title: str
    content: str
    category: Optional[str] = None
    author_id: str
    tags: Optional[str] = None
    is_pinned: bool = False
    is_anonymous: bool = False
    status: str = "active"

class CommentCreate(BaseModel):
    post_id: int
    author_id: str
    content: str

class VoteRequest(BaseModel):
    agent_id: str
    vote: int  # 1 or -1

class NotificationCreate(BaseModel):
    community_id: int
    recipient_id: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool = False

# ==================== 社区 CRUD ====================

@router.post("/api/v2/communities", status_code=201)
def create_community(community: CommunityCreate):
    """创建社区"""
    from data_manager import DataManager
    data_manager = DataManager()
    new_community = data_manager.create_community(
        community.name,
        community.description,
        community.rules,
        member_count=community.member_count,
        is_active=community.is_active
    )
    return new_community

@router.get("/api/v2/communities")
def list_communities(
    search: Optional[str] = None,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 50
):
    """列出社区"""
    from data_manager import DataManager
    data_manager = DataManager()
    communities = data_manager.get_communities(search=search, active_only=active_only)
    
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "communities": communities[start:end],
        "total": len(communities),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(communities) + page_size - 1) // page_size
    }

@router.get("/api/v2/communities/{community_id}")
def get_community(community_id: str):
    """获取社区详情"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    community = data_manager.get_community(community_id_int)
    if not community:
        raise HTTPException(404, "Community not found")
    
    # 加载社区成员
    members = data_manager.get_community_members(community_id_int)
    community["members"] = members
    
    return community

@router.put("/api/v2/communities/{community_id}")
def update_community(community_id: str, update: CommunityUpdate):
    """更新社区"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    update_data = update.dict(exclude_none=True)
    updated = data_manager.update_community(community_id_int, update_data)
    if not updated:
        raise HTTPException(404, "Community not found")
    
    return {"updated_community": updated}

@router.delete("/api/v2/communities/{community_id}")
def delete_community(community_id: str):
    """删除社区"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_community(community_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Community {community_id} not found")

# ==================== 社区帖子 CRUD ====================

@router.post("/api/v2/communities/{community_id}/posts", status_code=201)
def create_post(community_id: str, post: PostCreate):
    """在社区中创建帖子"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_post = data_manager.create_post(
        community_id_int,
        post.title,
        post.content,
        author_id=post.author_id,
        category=post.category,
        tags=post.tags,
        is_pinned=post.is_pinned,
        is_anonymous=post.is_anonymous
    )
    
    # 获取社区信息
    community = data_manager.get_community(community_id_int)
    
    # 创建通知
    if community:
        notification = data_manager.create_notification(
            community_id_int,
            post.author_id,
            f"新帖子: {post.title}",
            post.title[:50],
            link=f"/post/{new_post.get('id')}"
        )
    
    return new_post

@router.get("/api/v2/communities/{community_id}/posts")
def list_posts(
    community_id: str,
    category: Optional[str] = None,
    status: Optional[str] = "active",
    sort_by: str = "latest",
    page: int = 1,
    page_size: int = 50
):
    """列出社区帖子"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    posts = data_manager.get_posts(community_id=community_id_int, status=status)
    
    if category:
        posts = [p for p in posts if p.get("category") == category]
    
    # 排序
    if sort_by == "latest":
        posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    elif sort_by == "votes":
        posts.sort(key=lambda x: x.get("vote_count", 0), reverse=True)
    elif sort_by == "comments":
        posts.sort(key=lambda x: x.get("comment_count", 0), reverse=True)
    else:
        posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "posts": posts[start:end],
        "total": len(posts),
        "page": page,
        "page_size": page_size
    }

@router.get("/api/v2/posts/{post_id}")
def get_post(post_id: str):
    """获取帖子详情"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    post = data_manager.get_post(post_id_int)
    if not post:
        raise HTTPException(404, "Post not found")
    
    # 加载评论
    comments = data_manager.get_post_comments(post_id_int)
    post["comments"] = comments
    
    # 加载投票
    votes = data_manager.get_post_votes(post_id_int)
    post["votes"] = votes
    
    return post

@router.put("/api/v2/posts/{post_id}")
def update_post(post_id: str, update_data: dict):
    """更新帖子"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    updated = data_manager.update_post(post_id, update_data)
    if not updated:
        raise HTTPException(404, "Post not found")
    
    return {"updated_post": updated}

@router.delete("/api/v2/posts/{post_id}")
def delete_post(post_id: str):
    """删除帖子"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_post(post_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Post {post_id} not found")

# ==================== 帖子投票 ====================

@router.post("/api/v2/posts/{post_id}/vote")
def vote_post(post_id: str, vote_request: VoteRequest):
    """对帖子投票"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.create_vote(post_id_int, vote_request.agent_id, vote_request.vote)
    if not success:
        raise HTTPException(400, "Vote failed")
    
    # 获取更新后的帖子
    updated_post = data_manager.get_post(post_id_int)
    return {"success": True, "post": updated_post}

# ==================== 帖子评论 CRUD ====================

@router.post("/api/v2/posts/{post_id}/comments", status_code=201)
def create_comment(post_id: str, comment: CommentCreate):
    """创建评论"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_comment = data_manager.create_post_comment(
        post_id_int,
        comment.author_id,
        comment.content
    )
    
    # 创建通知
    post = data_manager.get_post(post_id_int)
    if post:
        notification = data_manager.create_notification(
            post.get("community_id"),
            post.get("author_id"),
            "新评论",
            comment.content[:50],
            link=f"/post/{post_id}"
        )
    
    return new_comment

@router.get("/api/v2/posts/{post_id}/comments")
def list_comments(post_id: str, limit: int = 50):
    """列出评论"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    comments = data_manager.get_post_comments(post_id_int)
    return {"comments": comments[-limit:]}

# ==================== 社区成员 ====================

@router.post("/api/v2/communities/{community_id}/join")
def join_community(community_id: str, agent_id: str):
    """加入社区"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.join_community(agent_id, community_id_int)
    if success:
        return {"success": True}
    raise HTTPException(400, "Failed to join")

@router.delete("/api/v2/communities/{community_id}/leave")
def leave_community(community_id: str, agent_id: str):
    """离开社区"""
    try:
        community_id_int = int(community_id)
    except ValueError:
        raise HTTPException(400, "Invalid community ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.leave_community(agent_id, community_id_int)
    if success:
        return {"success": True}
    raise HTTPException(400, "Failed to leave")

# ==================== 通知 ====================

@router.get("/api/notifications")
def get_notifications(
    agent_id: str,
    limit: int = 50,
    unread_only: bool = False
):
    """获取通知"""
    from data_manager import DataManager
    data_manager = DataManager()
    notifications = data_manager.get_notifications(agent_id)
    
    if not notifications:
        return {"notifications": []}
    
    if unread_only:
        notifications = [n for n in notifications if not n.get("is_read", False)]
    
    return {"notifications": notifications[-limit:]}

@router.put("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    """标记通知已读"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.mark_notification_read(notification_id)
    if success:
        return {"success": True}
    raise HTTPException(404, "Notification not found")
