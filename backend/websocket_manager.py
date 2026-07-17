"""
WebSocket 实时推送增强 — V3 架构（P3-B-002 心跳实时推送）

功能：
- 心跳变化实时推送：Agent 心跳上报后立即推送给所有连接的客户端
- 连接状态管理：前端断线自动重连（指数退避）
- 心跳保活：每 25s 发送 ping，客户端响应 pong
- 订阅机制：前端可订阅特定事件类型
- 限频保护：同类型消息最小间隔 5s

@task task-P3-B-002
@author 🟥 拉斐尔
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from fastapi import WebSocket


class _ConnInfo:
    """内部：记录每个连接的信息"""
    __slots__ = ("ws", "conn_id", "subscriptions", "last_pong", "active")

    def __init__(self, ws: WebSocket, conn_id: int, events: Optional[List[str]] = None):
        self.ws = ws
        self.conn_id = conn_id
        self.subscriptions: Set[str] = set(events) if events else {"*"}
        self.last_pong: float = time.monotonic()
        self.active = True


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self, rate_limit_seconds: float = 5.0):
        self._connections: Dict[int, _ConnInfo] = {}  # conn_id -> ConnInfo
        self._ws_to_conn_id: Dict[int, int] = {}  # id(ws) -> conn_id
        self._conn_id_counter = 0
        self._last_push_time: Dict[str, float] = {}
        self._rate_limit = rate_limit_seconds

    # ── 连接生命周期 ──

    async def connect(self, websocket: WebSocket, events: Optional[List[str]] = None) -> int:
        """接受新连接，返回 conn_id"""
        await websocket.accept()
        conn_id = self._conn_id_counter
        self._conn_id_counter += 1
        info = _ConnInfo(websocket, conn_id, events)
        self._connections[conn_id] = info
        self._ws_to_conn_id[id(websocket)] = conn_id
        self._print(f"新连接 #{conn_id}，订阅: {info.subscriptions}，当前连接数: {len(self._connections)}")
        # 发送连接确认
        await websocket.send_json({
            "type": "connected",
            "data": {"conn_id": conn_id, "message": "WebSocket 已连接"},
            "timestamp": datetime.now().isoformat(),
        })
        return conn_id

    def disconnect(self, websocket: WebSocket) -> Optional[int]:
        """断开连接，返回 conn_id"""
        wid = id(websocket)
        conn_id = self._ws_to_conn_id.pop(wid, None)
        if conn_id is not None:
            info = self._connections.pop(conn_id, None)
            if info:
                info.active = False
            self._print(f"连接 #{conn_id} 断开，剩余: {len(self._connections)}")
        return conn_id

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    # ── 发送 ──

    async def send_json(self, websocket: WebSocket, message: dict) -> bool:
        """发送 JSON 消息到指定连接"""
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            self._print(f"发送失败: {e}")
            return False

    async def broadcast(self, message: dict) -> int:
        """
        广播消息给所有活跃连接（带限频）。
        返回成功推送的连接数。
        """
        msg_type = message.get("type", "unknown")
        now = time.monotonic()
        last = self._last_push_time.get(msg_type, 0)
        if now - last < self._rate_limit:
            return 0  # 限频跳过
        self._last_push_time[msg_type] = now

        if not self._connections:
            return 0

        message_with_time = {**message, "timestamp": datetime.now().isoformat()}
        success_count = 0
        dead_ids: List[int] = []

        for conn_id, info in list(self._connections.items()):
            if not info.active:
                dead_ids.append(conn_id)
                continue
            # 订阅过滤
            if not self._should_push(info, msg_type):
                continue
            try:
                await info.ws.send_json(message_with_time)
                success_count += 1
            except Exception:
                dead_ids.append(conn_id)

        # 清理死连接
        for cid in dead_ids:
            info = self._connections.pop(cid, None)
            if info:
                info.active = False
                self._ws_to_conn_id.pop(id(info.ws), None)

        if dead_ids and self._connections:
            self._print(f"清理 {len(dead_ids)} 个失效连接，剩余: {len(self._connections)}")

        return success_count

    async def send_to_all(self, message: dict) -> int:
        """无条件推送给所有连接（不限频，用于心跳/连接确认等）"""
        if not self._connections:
            return 0
        message_with_time = {**message, "timestamp": datetime.now().isoformat()}
        success = 0
        dead_ids: List[int] = []
        for conn_id, info in list(self._connections.items()):
            if not info.active:
                dead_ids.append(conn_id)
                continue
            try:
                await info.ws.send_json(message_with_time)
                success += 1
            except Exception:
                dead_ids.append(conn_id)
        for cid in dead_ids:
            info = self._connections.pop(cid, None)
            if info:
                info.active = False
                self._ws_to_conn_id.pop(id(info.ws), None)
        return success

    # ── 心跳保活（服务端 ping） ──

    async def start_heartbeat_loop(self, interval: float = 25.0, timeout: float = 30.0):
        """
        全局心跳循环：定期向所有连接发送 ping，超时未响应则断开。
        应在 FastAPI startup 事件中调用一次。
        """
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            dead_ids: List[int] = []
            for conn_id, info in list(self._connections.items()):
                if not info.active:
                    dead_ids.append(conn_id)
                    continue
                # 发送 ping
                try:
                    await info.ws.send_json({"type": "ping"})
                except Exception:
                    dead_ids.append(conn_id)
                    continue
                # 检查上次 pong 是否超时
                if now - info.last_pong > timeout:
                    dead_ids.append(conn_id)
                    self._print(f"连接 #{conn_id} 心跳超时，断开")
            # 清理
            for cid in dead_ids:
                info = self._connections.pop(cid, None)
                if info:
                    info.active = False
                    self._ws_to_conn_id.pop(id(info.ws), None)

    def record_pong(self, websocket: WebSocket):
        """记录客户端 pong 响应"""
        wid = id(websocket)
        conn_id = self._ws_to_conn_id.get(wid)
        if conn_id is not None:
            info = self._connections.get(conn_id)
            if info:
                info.last_pong = time.monotonic()

    # ── 业务推送封装 ──

    async def push_heartbeat_change(self, heartbeat: dict) -> int:
        """Agent 心跳变化实时推送"""
        return await self.broadcast({
            "type": "heartbeat_update",
            "data": heartbeat,
        })

    async def push_status_update(self, agents: List[dict], tasks: List[dict]) -> int:
        """推送完整状态快照"""
        return await self.send_to_all({
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
                },
            },
        })

    async def push_queue_update(self, queue: dict) -> int:
        """推送 queue.json 变更"""
        return await self.broadcast({
            "type": "queue_update",
            "data": queue,
        })

    async def push_agent_status_change(self, agent_id: str, from_status: str,
                                        to_status: str, current_task: Optional[str] = None) -> int:
        """推送 Agent 状态变更"""
        return await self.broadcast({
            "type": "agent_status_change",
            "data": {
                "agent_id": agent_id,
                "from_status": from_status,
                "to_status": to_status,
                "current_task": current_task,
            },
        })

    async def push_task_status_change(self, task_id: str, from_status: str,
                                       to_status: str, assignee: Optional[str] = None) -> int:
        """推送任务状态变更"""
        return await self.broadcast({
            "type": "task_status_change",
            "data": {
                "task_id": task_id,
                "from_status": from_status,
                "to_status": to_status,
                "assignee": assignee,
            },
        })

    # ── 内部方法 ──

    def _should_push(self, info: _ConnInfo, msg_type: str) -> bool:
        return "*" in info.subscriptions or msg_type in info.subscriptions

    def _print(self, msg: str):
        print(f"[WS] {msg}")


# 全局管理器实例
manager = ConnectionManager()
