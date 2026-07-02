#!/usr/bin/env python3
"""
SSE (Server-Sent Events) 管理器
实时推送事件到前端
"""

import asyncio
import json
from typing import Dict, List, Set
from datetime import datetime


class SSEManager:
    """SSE 事件管理器"""
    
    def __init__(self):
        self.connections: Dict[str, asyncio.Queue] = {}
    
    def add_connection(self, client_id: str) -> asyncio.Queue:
        """添加新连接"""
        queue = asyncio.Queue()
        self.connections[client_id] = queue
        return queue
    
    def remove_connection(self, client_id: str):
        """移除连接"""
        if client_id in self.connections:
            del self.connections[client_id]
    
    async def broadcast(self, event: str, data: dict):
        """广播事件到所有连接"""
        message = {
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        disconnected = []
        for client_id, queue in self.connections.items():
            try:
                await queue.put(message)
            except Exception:
                disconnected.append(client_id)
        
        # 清理断开的连接
        for client_id in disconnected:
            self.remove_connection(client_id)
    
    async def send_to_client(self, client_id: str, event: str, data: dict):
        """发送事件到指定客户端"""
        if client_id in self.connections:
            message = {
                "event": event,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            await self.connections[client_id].put(message)
    
    def get_connected_clients(self) -> int:
        """获取连接数"""
        return len(self.connections)


# 全局实例
sse_manager = SSEManager()


# 事件类型常量
class Events:
    TASK_DISPATCHED = "task_dispatched"
    TASK_COMPLETED = "task_completed"
    TASK_UPDATED = "task_updated"
    MESSAGE_RECEIVED = "message_received"
    AGENT_STATUS = "agent_status"
    HEARTBEAT = "heartbeat"


if __name__ == "__main__":
    print("SSE Manager ready")
