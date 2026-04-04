"""
WebSocket 管理器 - 实时状态推送
"""
import asyncio
import json
from datetime import datetime
from typing import List, Set
from fastapi import WebSocket

class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"[WebSocket] 新连接，当前连接数：{len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)
        print(f"[WebSocket] 连接断开，当前连接数：{len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息给所有连接"""
        if not self.active_connections:
            return
        
        message_with_time = {
            **message,
            "timestamp": datetime.now().isoformat()
        }
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message_with_time)
            except Exception as e:
                print(f"[WebSocket] 发送失败：{e}")
                disconnected.add(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_status_update(self, agents: List[dict], tasks: List[dict]):
        """发送状态更新"""
        await self.broadcast({
            "type": "status_update",
            "data": {
                "agents": agents,
                "tasks": tasks,
                "stats": {
                    "total_agents": len(agents),
                    "online": sum(1 for a in agents if a.get("status") == "online"),
                    "busy": sum(1 for a in agents if a.get("status") == "busy"),
                    "idle": sum(1 for a in agents if a.get("status") == "idle"),
                }
            }
        })

# 全局管理器实例
manager = ConnectionManager()
