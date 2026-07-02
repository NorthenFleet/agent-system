"""
智能体会话管理器 — 简单会话管理（B5 / task-003-5）

功能:
- 系统给智能体发送消息
- 获取智能体会话记录
- JSON 文件持久化

@author 拉斐尔 (🟥 后端开发)
@created 2026-06-25
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CHAT_FILE = os.path.join(DATA_DIR, "chat_sessions.json")


def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return default if default is not None else {}


def save_json(filepath: str, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ChatManager:
    """简单会话管理器"""

    def __init__(self):
        self.data = load_json(CHAT_FILE, {"conversations": {}})

    def _save(self):
        save_json(CHAT_FILE, self.data)

    def send_to_agent(self, agent_id: str, agent_name: str, text: str) -> dict:
        """系统给智能体发送消息"""
        if agent_id not in self.data["conversations"]:
            self.data["conversations"][agent_id] = {
                "agent_name": agent_name,
                "messages": []
            }

        msg = {
            "id": f"msg_{len(self.data['conversations'][agent_id]['messages']) + 1:04d}",
            "from": "system",
            "to": agent_id,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        }

        self.data["conversations"][agent_id]["messages"].append(msg)
        self._save()

        return {"success": True, "message_id": msg["id"], "message": msg}

    def get_conversations(self, agent_id: str) -> dict:
        """获取智能体的完整会话记录"""
        if agent_id not in self.data["conversations"]:
            return {"agent_id": agent_id, "messages": [], "total": 0}

        conv = self.data["conversations"][agent_id]
        return {
            "agent_id": agent_id,
            "agent_name": conv.get("agent_name", ""),
            "messages": conv["messages"],
            "total": len(conv["messages"]),
        }

    def get_all_conversations(self) -> dict:
        """获取所有智能体会话概要"""
        result = {}
        for agent_id, conv in self.data["conversations"].items():
            msgs = conv.get("messages", [])
            result[agent_id] = {
                "agent_name": conv.get("agent_name", ""),
                "total_messages": len(msgs),
                "last_message": msgs[-1]["text"] if msgs else "",
                "last_timestamp": msgs[-1]["timestamp"] if msgs else None,
            }
        return result

    def clear_conversations(self, agent_id: str) -> bool:
        """清空指定智能体会话"""
        if agent_id in self.data["conversations"]:
            self.data["conversations"][agent_id]["messages"] = []
            self._save()
            return True
        return False


chat_manager = ChatManager()
