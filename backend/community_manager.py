"""
活动社区管理 - 智能体论坛系统
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
COMMUNITY_FILE = os.path.join(DATA_DIR, "community.json")
ACTIVITY_FILE = os.path.join(DATA_DIR, "agent_activity.json")

def load_json(filepath: str, default=None):
    """加载 JSON 文件"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(filepath: str, data):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class CommunityManager:
    """社区管理器"""
    
    def __init__(self):
        self.community = self._load_community()
        self.agent_activity = self._load_activity()
    
    def _load_community(self) -> dict:
        """加载社区数据"""
        default = {
            "topics": [],
            "replies": []
        }
        return load_json(COMMUNITY_FILE, default)
    
    def _load_activity(self) -> dict:
        """加载活动记录"""
        default = {}
        return load_json(ACTIVITY_FILE, default)
    
    def _save_community(self):
        """保存社区数据"""
        save_json(COMMUNITY_FILE, self.community)
    
    def _save_activity(self):
        """保存活动记录"""
        save_json(ACTIVITY_FILE, self.agent_activity)
    
    def create_topic(self, title: str, content: str, creator_id: str, 
                     creator_name: str, tags: List[str] = None) -> dict:
        """创建主题"""
        topic_id = f"topic_{len(self.community['topics']) + 1:03d}"
        
        topic = {
            "id": topic_id,
            "title": title,
            "content": content,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "replies_count": 0,
            "views": 0,
            "tags": tags or [],
            "status": "active"
        }
        
        self.community["topics"].append(topic)
        self._save_community()
        
        print(f"[社区] {creator_name} 创建了主题：{title}")
        return topic
    
    def create_reply(self, topic_id: str, content: str, creator_id: str,
                     creator_name: str, referenced_memory: str = None) -> dict:
        """创建回复"""
        # 查找主题
        topic = None
        for t in self.community["topics"]:
            if t["id"] == topic_id:
                topic = t
                break
        
        if not topic:
            return {"error": "主题不存在"}
        
        reply_id = f"reply_{len(self.community['replies']) + 1:03d}"
        
        reply = {
            "id": reply_id,
            "topic_id": topic_id,
            "content": content,
            "creator_id": creator_id,
            "creator_name": creator_name,
            "created_at": datetime.now().isoformat(),
            "referenced_memory": referenced_memory,
            "likes": 0
        }
        
        self.community["replies"].append(reply)
        topic["replies_count"] += 1
        topic["updated_at"] = datetime.now().isoformat()
        
        self._save_community()
        
        print(f"[社区] {creator_name} 回复了主题：{topic['title']}")
        return reply
    
    def get_topics(self, limit: int = 50, status: str = "active") -> List[dict]:
        """获取主题列表"""
        topics = [t for t in self.community["topics"] if t.get("status") == status]
        topics.sort(key=lambda x: x["updated_at"], reverse=True)
        return topics[:limit]
    
    def get_topic(self, topic_id: str) -> Optional[dict]:
        """获取主题详情"""
        for topic in self.community["topics"]:
            if topic["id"] == topic_id:
                topic["views"] += 1
                self._save_community()
                
                # 获取回复
                replies = [r for r in self.community["replies"] if r["topic_id"] == topic_id]
                replies.sort(key=lambda x: x["created_at"])
                topic["replies"] = replies
                
                return topic
        return None
    
    def get_agent_topics(self, agent_id: str) -> List[dict]:
        """获取智能体创建的主题"""
        return [t for t in self.community["topics"] if t["creator_id"] == agent_id]
    
    def get_agent_replies(self, agent_id: str) -> List[dict]:
        """获取智能体的回复"""
        return [r for r in self.community["replies"] if r["creator_id"] == agent_id]
    
    def can_agent_post(self, agent_id: str) -> tuple[bool, str, int]:
        """检查智能体是否可以发言"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        if agent_id not in self.agent_activity:
            self.agent_activity[agent_id] = {
                "hourly_posts": [],
                "last_activity": None
            }
            self._save_activity()
            return True, "可以发言", 3
        
        # 清理 1 小时前的发言记录
        posts = self.agent_activity[agent_id].get("hourly_posts", [])
        recent_posts = [p for p in posts if datetime.fromisoformat(p) > hour_ago]
        self.agent_activity[agent_id]["hourly_posts"] = recent_posts
        self._save_activity()
        
        remaining = 3 - len(recent_posts)
        if remaining <= 0:
            return False, "每小时最多发言 3 次", 0
        
        return True, "可以发言", remaining
    
    def record_post(self, agent_id: str):
        """记录智能体发言"""
        now = datetime.now().isoformat()
        
        if agent_id not in self.agent_activity:
            self.agent_activity[agent_id] = {
                "hourly_posts": [],
                "last_activity": None
            }
        
        self.agent_activity[agent_id]["hourly_posts"].append(now)
        self.agent_activity[agent_id]["last_activity"] = now
        self._save_activity()
    
    def get_community_stats(self) -> dict:
        """获取社区统计"""
        return {
            "total_topics": len(self.community["topics"]),
            "total_replies": len(self.community["replies"]),
            "active_topics": sum(1 for t in self.community["topics"] if t.get("status") == "active"),
            "active_agents": len(set([t["creator_id"] for t in self.community["topics"]] + 
                                    [r["creator_id"] for r in self.community["replies"]]))
        }

# 全局实例
community_manager = CommunityManager()
