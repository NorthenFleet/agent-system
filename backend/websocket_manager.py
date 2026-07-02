"""
WebSocket 实时推送增强 — V3 架构

新增功能：
- 按需推送（任务/Agent 状态变更时主动触发）
- 订阅机制（前端可订阅特定事件类型）
- 心跳保活（每 25s 发送 ping，30s 无响应断开）

@task task-005-P4-2
@author 🟥 拉斐尔
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._subscriptions: Dict[int, Set[str]] = {}  # conn_id -> {event_types}
        self._conn_id_counter = 0
        self._last_push_time: Dict[str, float] = {}
        self._heartbeat_tasks: Dict[int, asyncio.Task] = {}
        self.rate_limit_seconds: float = 30.0

    async def connect(self, websocket: WebSocket, events: Optional[List[str]] = None):
        """接受新连接，支持订阅特定事件类型"""
        await websocket.accept()
        conn_id = self._conn_id_counter
        self._conn_id_counter += 1
        self.active_connections.add(websocket)
        self._subscriptions[conn_id] = set(events) if events else {"*"}
        print(f"[WS] 新连接 #{conn_id}，订阅: {self._subscriptions[conn_id]}，当前连接数: {len(self.active_connections)}")
        self._start_heartbeat(conn_id)

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        for conn_id in list(self._subscriptions.keys()):
            if websocket in self.active_connections:
                self.active_connections.discard(websocket)
                self._subscriptions.pop(conn_id, None)
                self._heartbeat_tasks.pop(conn_id, None)
                print(f"[WS] 连接 #{conn_id} 断开，剩余: {len(self.active_connections)}")

    async def send_to(self, websocket: WebSocket, message: dict):
        """发送消息到指定连接"""
        try:
            msg = {**message, "timestamp": datetime.now().isoformat()}
            await websocket.send_json(msg)
            return True
        except Exception as e:
            print(f"[WS] 发送失败: {e}")
            return False

    async def broadcast(self, message: dict) -> bool:
        """广播消息给所有连接（带 30s 限频）"""
        msg_type = message.get("type", "unknown")
        now = time.monotonic()
        last = self._last_push_time.get(msg_type, 0)
        if now - last < self.rate_limit_seconds:
            return False
        self._last_push_time[msg_type] = now
        if not self.active_connections:
            return True
        disconnected = set()
        message_with_time = {**message, "timestamp": datetime.now().isoformat()}
        for conn_id, conn in list(self._iter_connections_with_id()):
            if not self._should_push(conn_id, msg_type):
                continue
            try:
                await conn.send_json(message_with_time)
            except Exception as e:
                print(f"[WS] 发送失败: {e}")
                disconnected.add(conn_id)
        for conn_id in disconnected:
            self.active_connections.discard(list(self._iter_connections_with_id())[0][1] if any(k==conn_id for k in self._subscriptions) else None)
        return True

    async def send_status_update(self, agents: List[dict], tasks: List[dict]):
        """发送状态更新（受限频控制）"""
        pushed = await self.broadcast({
            "type": "status_update",
            "data": {
                "agents": agents,
                "tasks": tasks,
                "stats": {
                    "total_agents": len(agents),
                    "online": sum(1 for a in agents if a.get("status") == "online"),
                    "busy": sum(1 for a in agents if a.get("status") == "busy"),
                    "idle": sum(1 for a in agents if a.get("status") == "idle"),
                    "completed_tasks": sum(1 for t in tasks if t.get("status") == "done"),
                }
            }
        })
        if pushed:
            print("[WS] ✅ 状态已推送给前端")
        else:
            print("[WS] ⏭ 跳过推送（30s 限频内）")

    async def push_queue_update(self, queue: dict):
        """推送 queue.json 变更事件"""
        pushed = await self.broadcast({
            "type": "queue_update",
            "data": queue
        })
        if pushed:
            print("[WS] ✅ Loop 队列已推送")
        else:
            print("[WS] ⏭ 跳过队列推送（30s 限频内）")

    def _should_push(self, conn_id: int, msg_type: str) -> bool:
        """检查是否应该推送给指定订阅者"""
        subs = self._subscriptions.get(conn_id, set())
        return "*" in subs or msg_type in subs

    def _start_heartbeat(self, conn_id: int):
        """启动心跳保活"""
        async def hb():
            try:
                while True:
                    await asyncio.sleep(25)
                    for conn in list(self.active_connections):
                        try:
                            await conn.send_text('{"type":"ping"}')
                        except:
                            break
            except asyncio.CancelledError:
                pass
        task = asyncio.create_task(hb())
        self._heartbeat_tasks[conn_id] = task

    async def _iter_connections_with_id(self):
        """内部：迭代连接及其 ID"""
        for cid in list(self._subscriptions.keys()):
            yield cid, list(self.active_connections)[0] if self.active_connections else None


# 全局管理器实例
manager = ConnectionManager()
