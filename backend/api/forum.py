"""
论坛 API - 板块 + 帖子 + 投票 + 声望
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["forum"])

# ==================== Pydantic Models ====================

class ForumSectionCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    parent_id: Optional[int] = None
    order: int = 0
    is_active: bool = True

class ForumSectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class ForumPostCreate(BaseModel):
    section_id: int
    title: str
    content: str
    author_id: str
    is_pinned: bool = False
    is_closed: bool = False
    tags: Optional[str] = None
    status: str = "open"

class ForumCommentCreate(BaseModel):
    post_id: int
    author_id: str
    content: str
    parent_id: Optional[int] = None

class ForumVoteRequest(BaseModel):
    agent_id: str
    vote: int  # 1 (up) or -1 (down)

class ForumReportCreate(BaseModel):
    post_id: int
    reporter_id: str
    reason: str
    details: Optional[str] = ""

# ==================== 板块 CRUD ====================

@router.post("/api/v2/forum/sections", status_code=201)
def create_section(section: ForumSectionCreate):
    """创建论坛板块"""
    from data_manager import DataManager
    data_manager = DataManager()
    new_section = data_manager.create_forum_section(
        section.name,
        section.description,
        parent_id=section.parent_id,
        order=section.order,
        is_active=section.is_active
    )
    return new_section

@router.get("/api/v2/forum/sections")
def list_sections(
    active_only: bool = True,
    parent_id: Optional[int] = None
):
    """列出论坛板块"""
    from data_manager import DataManager
    data_manager = DataManager()
    sections = data_manager.get_forum_sections(
        active_only=active_only,
        parent_id=parent_id
    )
    
    result = []
    for section in sections:
        s = dict(section)
        s["subsections"] = data_manager.get_forum_sections(parent_id=section.get("id"))
        s["stats"] = {
            "post_count": data_manager.get_forum_section_stats(section.get("id"), "post_count"),
            "comment_count": data_manager.get_forum_section_stats(section.get("id"), "comment_count")
        }
        result.append(s)
    
    return {"sections": result}

@router.get("/api/v2/forum/sections/{section_id}")
def get_section(section_id: str):
    """获取板块详情"""
    try:
        section_id_int = int(section_id)
    except ValueError:
        raise HTTPException(400, "Invalid section ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    section = data_manager.get_forum_section(section_id_int)
    if not section:
        raise HTTPException(404, "Section not found")
    
    s = dict(section)
    s["stats"] = {
        "post_count": data_manager.get_forum_section_stats(section_id_int, "post_count"),
        "comment_count": data_manager.get_forum_section_stats(section_id_int, "comment_count"),
        "member_count": data_manager.get_forum_section_stats(section_id_int, "member_count")
    }
    s["subsections"] = data_manager.get_forum_sections(parent_id=section_id_int)
    
    return s

@router.put("/api/v2/forum/sections/{section_id}")
def update_section(section_id: str, update: ForumSectionUpdate):
    """更新板块"""
    try:
        section_id_int = int(section_id)
    except ValueError:
        raise HTTPException(400, "Invalid section ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    update_data = update.dict(exclude_none=True)
    updated = data_manager.update_forum_section(section_id_int, update_data)
    if not updated:
        raise HTTPException(404, "Section not found")
    
    return {"updated_section": updated}

@router.delete("/api/v2/forum/sections/{section_id}")
def delete_section(section_id: str):
    """删除板块"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_forum_section(section_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Section {section_id} not found")

# ==================== 论坛帖子 CRUD ====================

@router.post("/api/v2/forum/sections/{section_id}/posts", status_code=201)
def create_post(section_id: str, post: ForumPostCreate):
    """在板块中创建帖子"""
    try:
        section_id_int = int(section_id)
    except ValueError:
        raise HTTPException(400, "Invalid section ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_post = data_manager.create_forum_post(
        section_id_int,
        post.title,
        post.content,
        post.author_id,
        is_pinned=post.is_pinned,
        is_closed=post.is_closed,
        tags=post.tags
    )
    
    # 更新板块统计
    data_manager.update_forum_section_stats(section_id_int, "post_count", 1)
    
    return new_post

@router.get("/api/v2/forum/sections/{section_id}/posts")
def list_posts(
    section_id: str,
    status: Optional[str] = None,
    sort_by: str = "latest",
    page: int = 1,
    page_size: int = 50
):
    """列出板块帖子"""
    try:
        section_id_int = int(section_id)
    except ValueError:
        raise HTTPException(400, "Invalid section ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    posts = data_manager.get_forum_posts(section_id=section_id_int, status=status)
    
    # 排序
    if sort_by == "latest":
        posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    elif sort_by == "hot":
        posts.sort(key=lambda x: x.get("vote_count", 0) * 2 + x.get("comment_count", 0), reverse=True)
    elif sort_by == "comments":
        posts.sort(key=lambda x: x.get("comment_count", 0), reverse=True)
    elif sort_by == "votes":
        posts.sort(key=lambda x: x.get("vote_count", 0), reverse=True)
    else:
        posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "posts": posts[start:end],
        "total": len(posts),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(posts) + page_size - 1) // page_size
    }

@router.get("/api/v2/forum/posts/{post_id}")
def get_post(post_id: str):
    """获取帖子详情"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    post = data_manager.get_forum_post(post_id_int)
    if not post:
        raise HTTPException(404, "Post not found")
    
    result = dict(post)
    result["comments"] = data_manager.get_forum_post_comments(post_id_int)
    result["votes"] = data_manager.get_forum_post_votes(post_id_int)
    
    return result

@router.put("/api/v2/forum/posts/{post_id}")
def update_post(post_id: str, update_data: dict):
    """更新帖子"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    updated = data_manager.update_forum_post(post_id, update_data)
    if not updated:
        raise HTTPException(404, "Post not found")
    
    return {"updated_post": updated}

@router.delete("/api/v2/forum/posts/{post_id}")
def delete_post(post_id: str):
    """删除帖子"""
    from data_manager import DataManager
    data_manager = DataManager()
    success = data_manager.delete_forum_post(post_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Post {post_id} not found")

# ==================== 论坛评论 CRUD ====================

@router.post("/api/v2/forum/posts/{post_id}/comments", status_code=201)
def create_comment(post_id: str, comment: ForumCommentCreate):
    """创建评论"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_comment = data_manager.create_forum_comment(
        post_id_int,
        comment.author_id,
        comment.content,
        parent_id=comment.parent_id
    )
    
    # 更新帖子统计
    data_manager.update_forum_post_stats(post_id_int, "comment_count", 1)
    
    return new_comment

@router.get("/api/v2/forum/posts/{post_id}/comments")
def list_comments(post_id: str, limit: int = 50):
    """列出评论"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    comments = data_manager.get_forum_post_comments(post_id_int)
    return {"comments": comments[-limit:]}

# ==================== 论坛投票 ====================

@router.post("/api/v2/forum/posts/{post_id}/vote")
def vote_post(post_id: str, vote_request: ForumVoteRequest):
    """对帖子投票"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.create_forum_vote(post_id_int, vote_request.agent_id, vote_request.vote)
    if not success:
        raise HTTPException(400, "Vote failed")
    
    """对帖子投票"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.create_forum_vote(post_id_int, vote_request.agent_id, vote_request.vote)
    if not success:
        raise HTTPException(400, "Failed to vote")
    
    updated_post = data_manager.get_forum_post(post_id_int)
    
    # 更新发帖人声望
    if updated_post and updated_post.get("author_id"):
        data_manager.update_agent_reputation(updated_post.get("author_id"), vote_request.vote)
    
    return {"success": True, "post": updated_post}

@router.post("/api/v2/forum/comments/{comment_id}/vote")
def vote_comment(comment_id: str, vote_request: ForumVoteRequest):
    """对评论投票"""
    try:
        comment_id_int = int(comment_id)
    except ValueError:
        raise HTTPException(400, "Invalid comment ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.create_forum_comment_vote(comment_id_int, vote_request.agent_id, vote_request.vote)
    if not success:
        raise HTTPException(400, "Vote failed")
    
    return {"success": True}

# ==================== 报告 ====================

@router.post("/api/v2/forum/posts/{post_id}/report")
def report_post(post_id: str, report: ForumReportCreate):
    """举报帖子"""
    try:
        post_id_int = int(post_id)
    except ValueError:
        raise HTTPException(400, "Invalid post ID")
    
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_report = data_manager.create_forum_report(
        post_id_int,
        report.reporter_id,
        report.reason,
        report.details
    )
    
    return {"success": True, "report_id": new_report.get("id")}

@router.get("/api/v2/forum/reports")
def list_reports(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    """列出报告（管理员）"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    reports = data_manager.get_forum_reports(status=status)
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "reports": reports[start:end],
        "total": len(reports),
        "page": page
    }

@router.put("/api/v2/forum/reports/{report_id}/resolve")
def resolve_report(report_id: str, resolved_by: str):
    """解决报告"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    updated = data_manager.resolve_forum_report(report_id, resolved_by)
    if not updated:
        raise HTTPException(404, "Report not found")
    
    return {"success": True}

# ==================== 声望系统 ====================

@router.get("/api/v2/forum/leaderboard")
def get_leaderboard(limit: int = 20):
    """获取声望排行榜"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    leaderboard = data_manager.get_reputation_leaderboard(limit)
    return {"leaderboard": leaderboard}

@router.get("/api/v2/agents/{agent_id}/reputation")
def get_agent_reputation(agent_id: str):
    """获取Agent声望"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    reputation = data_manager.get_agent_reputation(agent_id)
    return {"agent_id": agent_id, "reputation": reputation}
