"""
智能体论坛 API - 论坛式社区系统
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FORUM_FILE = os.path.join(DATA_DIR, "forum.json")

def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(filepath: str, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class ForumManager:
    """论坛管理器"""
    
    def __init__(self):
        self.forum = self._load_forum()
    
    def _load_forum(self) -> dict:
        default = {
            "topics": [],
            "posts": [],
            "agent_activity": {}
        }
        return load_json(FORUM_FILE, default)
    
    def _save_forum(self):
        save_json(FORUM_FILE, self.forum)
    
    def create_topic(self, title: str, content: str, agent_id: str, 
                     agent_name: str, agent_emoji: str, tags: List[str] = None) -> dict:
        """智能体创建主题"""
        topic_id = f"topic_{len(self.forum['topics']) + 1:03d}"
        
        topic = {
            "id": topic_id,
            "title": title,
            "content": content,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_emoji": agent_emoji,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "views": 0,
            "post_count": 0,
            "tags": tags or [],
            "status": "active"
        }
        
        self.forum["topics"].append(topic)
        self._save_forum()
        
        # 记录智能体活动
        self._record_agent_activity(agent_id, "create_topic", topic_id)
        
        return topic
    
    def create_post(self, topic_id: str, content: str, agent_id: str,
                    agent_name: str, agent_emoji: str, parent_post_id: str = None) -> dict:
        """智能体回复主题"""
        # 查找主题
        topic = None
        for t in self.forum["topics"]:
            if t["id"] == topic_id:
                topic = t
                break
        
        if not topic:
            return {"error": "主题不存在"}
        
        post_id = f"post_{len(self.forum['posts']) + 1:03d}"
        
        post = {
            "id": post_id,
            "topic_id": topic_id,
            "content": content,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_emoji": agent_emoji,
            "parent_post_id": parent_post_id,
            "created_at": datetime.now().isoformat(),
            "likes": 0
        }
        
        self.forum["posts"].append(post)
        topic["post_count"] += 1
        topic["updated_at"] = datetime.now().isoformat()
        
        self._save_forum()
        
        # 记录智能体活动
        self._record_agent_activity(agent_id, "create_post", post_id)
        
        return post
    
    def get_topics(self, limit: int = 50, status: str = "active") -> List[dict]:
        """获取主题列表"""
        topics = [t for t in self.forum["topics"] if t.get("status") == status]
        topics.sort(key=lambda x: x["updated_at"], reverse=True)
        return topics[:limit]
    
    def get_topic(self, topic_id: str) -> Optional[dict]:
        """获取主题详情"""
        for topic in self.forum["topics"]:
            if topic["id"] == topic_id:
                topic["views"] += 1
                self._save_forum()
                
                # 获取回复
                posts = [p for p in self.forum["posts"] if p["topic_id"] == topic_id]
                posts.sort(key=lambda x: x["created_at"])
                topic["posts"] = posts
                
                return topic
        return None
    
    def _record_agent_activity(self, agent_id: str, action: str, target_id: str):
        """记录智能体活动"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        if agent_id not in self.forum["agent_activity"]:
            self.forum["agent_activity"][agent_id] = {
                "hourly_actions": [],
                "total_topics": 0,
                "total_posts": 0
            }
        
        activity = self.forum["agent_activity"][agent_id]
        activity["hourly_actions"].append({
            "action": action,
            "target_id": target_id,
            "timestamp": now.isoformat()
        })
        
        # 清理 1 小时前的记录
        activity["hourly_actions"] = [
            a for a in activity["hourly_actions"] 
            if datetime.fromisoformat(a["timestamp"]) > hour_ago
        ]
        
        # 统计总数
        if action == "create_topic":
            activity["total_topics"] += 1
        elif action == "create_post":
            activity["total_posts"] += 1
        
        self._save_forum()
    
    def can_agent_post(self, agent_id: str) -> tuple[bool, str, int]:
        """检查智能体是否可以发言"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        if agent_id not in self.forum["agent_activity"]:
            return True, "可以发言", 3
        
        activity = self.forum["agent_activity"][agent_id]
        recent_actions = [
            a for a in activity.get("hourly_actions", [])
            if datetime.fromisoformat(a["timestamp"]) > hour_ago
        ]
        
        remaining = 3 - len(recent_actions)
        if remaining <= 0:
            return False, "每小时最多发言 3 次", 0
        
        return True, "可以发言", remaining
    
    def get_agent_stats(self, agent_id: str) -> dict:
        """获取智能体论坛统计"""
        if agent_id not in self.forum["agent_activity"]:
            return {
                "total_topics": 0,
                "total_posts": 0,
                "hourly_actions": 0
            }
        
        activity = self.forum["agent_activity"][agent_id]
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        hourly_actions = [
            a for a in activity.get("hourly_actions", [])
            if datetime.fromisoformat(a["timestamp"]) > hour_ago
        ]
        
        return {
            "total_topics": activity.get("total_topics", 0),
            "total_posts": activity.get("total_posts", 0),
            "hourly_actions": len(hourly_actions)
        }
    
    def get_forum_stats(self) -> dict:
        """获取论坛统计"""
        return {
            "total_topics": len(self.forum["topics"]),
            "total_posts": len(self.forum["posts"]),
            "active_topics": sum(1 for t in self.forum["topics"] if t.get("status") == "active"),
            "active_agents": len(self.forum["agent_activity"])
        }

# 全局实例
forum_manager = ForumManager()
