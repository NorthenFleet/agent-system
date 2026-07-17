"""Long-term intelligence data service.

This service is intentionally separate from the news module. News is daily
content; intelligence is accumulated domain data such as AIS points and tracks.
"""

from __future__ import annotations

import sqlite3
import json
import csv
import io
import time
import urllib.request
from urllib.error import URLError, HTTPError
from uuid import uuid4
from pathlib import Path
from typing import Any

from path_config import backend_data_path


class IntelligenceService:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or backend_data_path("intelligence.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ais_vessels (
                    id TEXT PRIMARY KEY,
                    mmsi TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    vessel_type TEXT NOT NULL DEFAULT '',
                    flag TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'unknown',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ais_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vessel_id TEXT NOT NULL,
                    mmsi TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    speed REAL NOT NULL DEFAULT 0,
                    course REAL NOT NULL DEFAULT 0,
                    heading REAL,
                    nav_status TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual',
                    raw_payload TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(vessel_id) REFERENCES ais_vessels(id)
                );

                CREATE INDEX IF NOT EXISTS idx_ais_points_vessel_time
                ON ais_points(vessel_id, timestamp);

                CREATE INDEX IF NOT EXISTS idx_ais_points_mmsi_time
                ON ais_points(mmsi, timestamp);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_ais_points_unique_position
                ON ais_points(mmsi, timestamp, lat, lng);

                CREATE TABLE IF NOT EXISTS ais_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'http',
                    url TEXT NOT NULL DEFAULT '',
                    method TEXT NOT NULL DEFAULT 'GET',
                    format TEXT NOT NULL DEFAULT 'csv',
                    headers_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    poll_interval_seconds INTEGER NOT NULL DEFAULT 3600,
                    last_run_at TEXT,
                    last_status TEXT NOT NULL DEFAULT 'idle',
                    last_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS intelligence_topics (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    icon TEXT NOT NULL DEFAULT '📍',
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planning',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    records_label TEXT NOT NULL DEFAULT '0',
                    record_value INTEGER NOT NULL DEFAULT 0,
                    updated_label TEXT NOT NULL DEFAULT '尚未更新',
                    goal TEXT NOT NULL DEFAULT '',
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    location_name TEXT NOT NULL DEFAULT '',
                    related_locations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_intelligence_topics_status
                ON intelligence_topics(status, updated_at);

                CREATE TABLE IF NOT EXISTS intelligence_events (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT,
                    vessel_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'observation',
                    severity TEXT NOT NULL DEFAULT 'info',
                    status TEXT NOT NULL DEFAULT 'open',
                    source TEXT NOT NULL DEFAULT 'manual',
                    occurred_at TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    location_name TEXT NOT NULL DEFAULT '',
                    evidence_url TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    assignee_agent_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(topic_id) REFERENCES intelligence_topics(id),
                    FOREIGN KEY(vessel_id) REFERENCES ais_vessels(id)
                );

                CREATE INDEX IF NOT EXISTS idx_intelligence_events_time
                ON intelligence_events(occurred_at DESC, severity, status);

                CREATE INDEX IF NOT EXISTS idx_intelligence_events_links
                ON intelligence_events(topic_id, vessel_id, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS world_cup_matches (
                    id TEXT PRIMARY KEY,
                    kickoff_at TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '',
                    stage_label TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    status_label TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0,
                    home_team_id TEXT NOT NULL DEFAULT '',
                    home_team TEXT NOT NULL,
                    home_code TEXT NOT NULL DEFAULT '',
                    home_logo TEXT NOT NULL DEFAULT '',
                    home_score INTEGER NOT NULL DEFAULT 0,
                    away_team_id TEXT NOT NULL DEFAULT '',
                    away_team TEXT NOT NULL,
                    away_code TEXT NOT NULL DEFAULT '',
                    away_logo TEXT NOT NULL DEFAULT '',
                    away_score INTEGER NOT NULL DEFAULT 0,
                    venue TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'ESPN',
                    source_url TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_world_cup_matches_stage_time
                ON world_cup_matches(stage, kickoff_at);

                CREATE TABLE IF NOT EXISTS world_cup_goals (
                    id TEXT PRIMARY KEY,
                    match_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    team_id TEXT NOT NULL DEFAULT '',
                    team_name TEXT NOT NULL DEFAULT '',
                    scorer_id TEXT NOT NULL DEFAULT '',
                    scorer_name TEXT NOT NULL DEFAULT '',
                    minute INTEGER NOT NULL DEFAULT 0,
                    stoppage_minute INTEGER NOT NULL DEFAULT 0,
                    minute_label TEXT NOT NULL DEFAULT '',
                    goal_type TEXT NOT NULL DEFAULT 'goal',
                    penalty INTEGER NOT NULL DEFAULT 0,
                    own_goal INTEGER NOT NULL DEFAULT 0,
                    score_value INTEGER NOT NULL DEFAULT 1,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(match_id) REFERENCES world_cup_matches(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_world_cup_goals_match_sequence
                ON world_cup_goals(match_id, sequence);

                CREATE INDEX IF NOT EXISTS idx_world_cup_goals_scorer
                ON world_cup_goals(scorer_name, team_name);
                """
            )
            self._seed_if_empty(conn)
            self._seed_topics_if_empty(conn)
            self._seed_events_if_empty(conn)

    def _seed_if_empty(self, conn: sqlite3.Connection) -> None:
        count = conn.execute("SELECT COUNT(*) AS count FROM ais_vessels").fetchone()["count"]
        if count:
            return
        vessels = [
            {
                "id": "ddg-172",
                "mmsi": "412001172",
                "name": "示例驱逐舰 DDG-172",
                "vessel_type": "水面舰艇",
                "flag": "示例",
                "area": "台湾以东海域",
                "status": "underway",
                "notes": "AIS 数据结构验证样例",
                "track": [
                    ("2026-07-08T00:00:00+08:00", 23.9, 121.2, 14.2, 42),
                    ("2026-07-08T02:00:00+08:00", 24.2, 121.8, 15.1, 48),
                    ("2026-07-08T04:00:00+08:00", 24.55, 122.25, 14.8, 53),
                    ("2026-07-08T06:00:00+08:00", 24.9, 122.74, 16.0, 58),
                ],
            },
            {
                "id": "ffg-529",
                "mmsi": "412001529",
                "name": "示例护卫舰 FFG-529",
                "vessel_type": "护卫舰",
                "flag": "示例",
                "area": "巴士海峡",
                "status": "loitering",
                "notes": "AIS 数据结构验证样例",
                "track": [
                    ("2026-07-08T00:00:00+08:00", 20.8, 119.3, 9.4, 95),
                    ("2026-07-08T02:00:00+08:00", 20.75, 120.0, 8.9, 100),
                    ("2026-07-08T04:00:00+08:00", 20.7, 120.62, 7.8, 94),
                    ("2026-07-08T06:00:00+08:00", 20.82, 121.18, 8.1, 76),
                ],
            },
            {
                "id": "aux-886",
                "mmsi": "412001886",
                "name": "示例补给舰 AUX-886",
                "vessel_type": "辅助舰",
                "flag": "示例",
                "area": "南海北部",
                "status": "silent",
                "notes": "AIS 数据结构验证样例",
                "track": [
                    ("2026-07-08T00:00:00+08:00", 18.4, 113.5, 11.2, 22),
                    ("2026-07-08T02:00:00+08:00", 18.75, 113.72, 10.8, 28),
                    ("2026-07-08T04:00:00+08:00", 19.05, 113.95, 0, 0),
                    ("2026-07-08T06:00:00+08:00", 19.05, 113.95, 0, 0),
                ],
            },
        ]
        for vessel in vessels:
            conn.execute(
                """
                INSERT INTO ais_vessels
                (id, mmsi, name, vessel_type, flag, area, status, notes)
                VALUES (:id, :mmsi, :name, :vessel_type, :flag, :area, :status, :notes)
                """,
                vessel,
            )
            for timestamp, lat, lng, speed, course in vessel["track"]:
                conn.execute(
                    """
                    INSERT INTO ais_points
                    (vessel_id, mmsi, timestamp, lat, lng, speed, course, nav_status, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vessel["id"],
                        vessel["mmsi"],
                        timestamp,
                        lat,
                        lng,
                        speed,
                        course,
                        vessel["status"],
                        "seed",
                    ),
                )

    def _seed_topics_if_empty(self, conn: sqlite3.Connection) -> None:
        count = conn.execute("SELECT COUNT(*) AS count FROM intelligence_topics").fetchone()["count"]
        if count:
            return
        topics = [
            {
                "id": "task-planning",
                "name": "任务规划项目情报",
                "icon": "📋",
                "description": "长期记录任务规划、拆解、执行反馈和复盘结果",
                "status": "active",
                "sources": ["项目管理", "任务列表", "智能体反馈", "复盘记录"],
                "records": "12,480",
                "recordValue": 12480,
                "updatedAt": "持续更新",
                "goal": "形成可追溯的项目规划知识库，支持项目经理复用历史任务拆解、风险识别和执行模式。",
                "lat": 31.2304,
                "lng": 121.4737,
                "locationName": "上海 / 项目中心",
                "relatedLocations": ["shanghai", "beijing"],
            },
            {
                "id": "naval-ais",
                "name": "海上军舰 AIS 情报",
                "icon": "🌊",
                "description": "围绕特定海域和目标舰船积累 AIS 轨迹与活动历史",
                "status": "planning",
                "sources": ["AIS 数据", "海域网格", "舰船档案", "轨迹时间线"],
                "records": "待接入",
                "recordValue": 0,
                "updatedAt": "规划中",
                "goal": "长期沉淀舰船位置、航速、航向、靠泊和异常轨迹，形成历史活动画像。",
                "lat": 23.5,
                "lng": 121.0,
                "locationName": "西太平洋 / 近海航道",
                "relatedLocations": ["tokyo", "shenzhen", "singapore"],
            },
            {
                "id": "knowledge-assets",
                "name": "知识资产情报",
                "icon": "🗂️",
                "description": "沉淀资料、文档、知识节点与业务主题之间的关系",
                "status": "active",
                "sources": ["知识库", "文档撰写", "项目资料", "会议摘要"],
                "records": "3,260",
                "recordValue": 3260,
                "updatedAt": "每日同步",
                "goal": "构建跨项目、跨智能体可复用的背景材料和证据链，减少重复调研。",
                "lat": 39.9042,
                "lng": 116.4074,
                "locationName": "北京 / 知识节点",
                "relatedLocations": ["beijing"],
            },
            {
                "id": "external-watch",
                "name": "外部环境专题",
                "icon": "🛰️",
                "description": "对指定行业、区域或组织进行长期跟踪，而不是一次性新闻浏览",
                "status": "paused",
                "sources": ["RSS", "公开网页", "人工标注", "趋势摘要"],
                "records": "860",
                "recordValue": 860,
                "updatedAt": "暂停采集",
                "goal": "把每日碎片信息转化为长期趋势、实体画像和专题判断。",
                "lat": 37.7749,
                "lng": -122.4194,
                "locationName": "旧金山 / 外部技术源",
                "relatedLocations": ["sanfrancisco", "newyork", "london"],
            },
        ]
        for topic in topics:
            self._write_topic(conn, topic)

    def summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            topic_count = conn.execute("SELECT COUNT(*) AS count FROM intelligence_topics").fetchone()["count"]
            event_count = conn.execute("SELECT COUNT(*) AS count FROM intelligence_events").fetchone()["count"]
            open_alerts = conn.execute(
                """
                SELECT COUNT(*) AS count FROM intelligence_events
                WHERE status != 'resolved' AND severity IN ('high', 'critical')
                """
            ).fetchone()["count"]
            vessel_count = conn.execute("SELECT COUNT(*) AS count FROM ais_vessels").fetchone()["count"]
            point_count = conn.execute("SELECT COUNT(*) AS count FROM ais_points").fetchone()["count"]
            latest = conn.execute("SELECT MAX(timestamp) AS timestamp FROM ais_points").fetchone()["timestamp"]
            sources = conn.execute(
                """
                SELECT source, COUNT(*) AS count
                FROM ais_points
                GROUP BY source
                ORDER BY count DESC, source ASC
                """
            ).fetchall()
        return {
            "topics": topic_count,
            "events": event_count,
            "open_alerts": open_alerts,
            "vessels": vessel_count,
            "points": point_count,
            "latest_timestamp": latest,
            "sources": [dict(row) for row in sources],
            "database": str(self.db_path),
        }

    def list_topics(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM intelligence_topics ORDER BY updated_at DESC, name ASC"
            ).fetchall()
        return [self._topic_row(row) for row in rows]

    def save_topic(self, payload: dict[str, Any]) -> dict[str, Any]:
        topic = self._normalize_topic(payload)
        with self.connect() as conn:
            self._write_topic(conn, topic)
            row = conn.execute("SELECT * FROM intelligence_topics WHERE id = ?", (topic["id"],)).fetchone()
        return self._topic_row(row)

    def delete_topic(self, topic_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM intelligence_topics WHERE id = ?", (topic_id,))
            return bool(cursor.rowcount)

    def _normalize_topic(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name 不能为空")
        topic_id = str(payload.get("id") or f"topic-{uuid4().hex[:10]}").strip()
        status = str(payload.get("status") or "planning")
        if status not in {"active", "planning", "paused"}:
            raise ValueError("status 仅支持 active/planning/paused")
        lat = float(payload.get("lat"))
        lng = float(payload.get("lng"))
        if not -90 <= lat <= 90:
            raise ValueError("纬度必须在 -90 到 90 之间")
        if not -180 <= lng <= 180:
            raise ValueError("经度必须在 -180 到 180 之间")
        sources = payload.get("sources") or []
        related = payload.get("relatedLocations") or []
        if not isinstance(sources, list) or not isinstance(related, list):
            raise ValueError("sources 和 relatedLocations 必须是数组")
        return {
            "id": topic_id,
            "name": name,
            "icon": str(payload.get("icon") or "📍"),
            "description": str(payload.get("description") or ""),
            "status": status,
            "sources": [str(value).strip() for value in sources if str(value).strip()],
            "records": str(payload.get("records") or "0"),
            "recordValue": max(0, int(payload.get("recordValue") or 0)),
            "updatedAt": str(payload.get("updatedAt") or "尚未更新"),
            "goal": str(payload.get("goal") or ""),
            "lat": lat,
            "lng": lng,
            "locationName": str(payload.get("locationName") or "未命名位置"),
            "relatedLocations": [str(value).strip() for value in related if str(value).strip()],
        }

    def _write_topic(self, conn: sqlite3.Connection, topic: dict[str, Any]) -> None:
        topic = self._normalize_topic(topic)
        conn.execute(
            """
            INSERT INTO intelligence_topics
            (id, name, icon, description, status, sources_json, records_label,
             record_value, updated_label, goal, lat, lng, location_name, related_locations_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                icon = excluded.icon,
                description = excluded.description,
                status = excluded.status,
                sources_json = excluded.sources_json,
                records_label = excluded.records_label,
                record_value = excluded.record_value,
                updated_label = excluded.updated_label,
                goal = excluded.goal,
                lat = excluded.lat,
                lng = excluded.lng,
                location_name = excluded.location_name,
                related_locations_json = excluded.related_locations_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                topic["id"], topic["name"], topic["icon"], topic["description"], topic["status"],
                json.dumps(topic["sources"], ensure_ascii=False), topic["records"], topic["recordValue"],
                topic["updatedAt"], topic["goal"], topic["lat"], topic["lng"], topic["locationName"],
                json.dumps(topic["relatedLocations"], ensure_ascii=False),
            ),
        )

    def _topic_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "icon": row["icon"],
            "description": row["description"],
            "status": row["status"],
            "sources": json.loads(row["sources_json"] or "[]"),
            "records": row["records_label"],
            "recordValue": row["record_value"],
            "updatedAt": row["updated_label"],
            "goal": row["goal"],
            "lat": row["lat"],
            "lng": row["lng"],
            "locationName": row["location_name"],
            "relatedLocations": json.loads(row["related_locations_json"] or "[]"),
            "createdAt": row["created_at"],
            "databaseUpdatedAt": row["updated_at"],
        }

    def _seed_events_if_empty(self, conn: sqlite3.Connection) -> None:
        count = conn.execute("SELECT COUNT(*) AS count FROM intelligence_events").fetchone()["count"]
        if count:
            return
        events = [
            {
                "id": "event-ais-course-change",
                "topicId": "naval-ais",
                "vesselId": "ddg-172",
                "title": "示例驱逐舰航向明显调整",
                "summary": "目标在台湾以东海域连续转向，建议结合后续航迹持续观察。",
                "category": "movement",
                "severity": "high",
                "status": "monitoring",
                "source": "AIS 轨迹规则",
                "occurredAt": "2026-07-08T06:00:00+08:00",
                "lat": 24.9,
                "lng": 122.74,
                "locationName": "台湾以东海域",
                "confidence": 0.86,
                "assigneeAgentId": "perceptor",
            },
            {
                "id": "event-ais-silent",
                "topicId": "naval-ais",
                "vesselId": "aux-886",
                "title": "示例补给舰出现静默停留",
                "summary": "航速降为零且位置未变化，记录为待核实的停留事件。",
                "category": "anomaly",
                "severity": "medium",
                "status": "open",
                "source": "AIS 轨迹规则",
                "occurredAt": "2026-07-08T06:00:00+08:00",
                "lat": 19.05,
                "lng": 113.95,
                "locationName": "南海北部",
                "confidence": 0.74,
                "assigneeAgentId": "perceptor",
            },
            {
                "id": "event-knowledge-sync",
                "topicId": "knowledge-assets",
                "title": "知识资产专题完成每日同步",
                "summary": "项目资料和会议摘要已完成本轮归档，可进入关联分析。",
                "category": "collection",
                "severity": "info",
                "status": "resolved",
                "source": "知识库同步任务",
                "occurredAt": "2026-07-14T08:00:00+08:00",
                "lat": 39.9042,
                "lng": 116.4074,
                "locationName": "北京 / 知识节点",
                "confidence": 1.0,
                "assigneeAgentId": "ratchet",
            },
        ]
        for event in events:
            self._write_event(conn, self._normalize_event(event, conn))

    def list_events(
        self,
        severity: str | None = None,
        status: str | None = None,
        topic_id: str | None = None,
        vessel_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("severity", severity),
            ("status", status),
            ("topic_id", topic_id),
            ("vessel_id", vessel_id),
        ):
            if value:
                where.append(f"e.{column} = ?")
                params.append(value)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT e.*, t.name AS topic_name, v.name AS vessel_name
                FROM intelligence_events e
                LEFT JOIN intelligence_topics t ON t.id = e.topic_id
                LEFT JOIN ais_vessels v ON v.id = e.vessel_id
                {where_sql}
                ORDER BY e.occurred_at DESC, e.created_at DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        return [self._event_row(row) for row in rows]

    def save_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            event = self._normalize_event(payload, conn)
            self._write_event(conn, event)
            row = conn.execute(
                """
                SELECT e.*, t.name AS topic_name, v.name AS vessel_name
                FROM intelligence_events e
                LEFT JOIN intelligence_topics t ON t.id = e.topic_id
                LEFT JOIN ais_vessels v ON v.id = e.vessel_id
                WHERE e.id = ?
                """,
                (event["id"],),
            ).fetchone()
        return self._event_row(row)

    def update_event_status(self, event_id: str, status: str) -> dict[str, Any] | None:
        if status not in {"open", "monitoring", "resolved"}:
            raise ValueError("status 仅支持 open/monitoring/resolved")
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE intelligence_events SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, event_id),
            )
            if not cursor.rowcount:
                return None
            row = conn.execute(
                """
                SELECT e.*, t.name AS topic_name, v.name AS vessel_name
                FROM intelligence_events e
                LEFT JOIN intelligence_topics t ON t.id = e.topic_id
                LEFT JOIN ais_vessels v ON v.id = e.vessel_id
                WHERE e.id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._event_row(row)

    def delete_event(self, event_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM intelligence_events WHERE id = ?", (event_id,))
            return bool(cursor.rowcount)

    def _normalize_event(self, payload: dict[str, Any], conn: sqlite3.Connection) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("title 不能为空")
        severity = str(payload.get("severity") or "info")
        status = str(payload.get("status") or "open")
        if severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError("severity 仅支持 info/low/medium/high/critical")
        if status not in {"open", "monitoring", "resolved"}:
            raise ValueError("status 仅支持 open/monitoring/resolved")
        lat = float(payload.get("lat"))
        lng = float(payload.get("lng"))
        if not -90 <= lat <= 90:
            raise ValueError("纬度必须在 -90 到 90 之间")
        if not -180 <= lng <= 180:
            raise ValueError("经度必须在 -180 到 180 之间")
        topic_id = str(payload.get("topicId") or payload.get("topic_id") or "").strip() or None
        vessel_id = str(payload.get("vesselId") or payload.get("vessel_id") or "").strip() or None
        if topic_id and not conn.execute("SELECT 1 FROM intelligence_topics WHERE id = ?", (topic_id,)).fetchone():
            raise ValueError("关联的情报专题不存在")
        if vessel_id and not conn.execute("SELECT 1 FROM ais_vessels WHERE id = ?", (vessel_id,)).fetchone():
            raise ValueError("关联的 AIS 舰艇不存在")
        confidence = float(payload.get("confidence") if payload.get("confidence") is not None else 0.5)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence 必须在 0 到 1 之间")
        return {
            "id": str(payload.get("id") or f"event-{uuid4().hex[:10]}"),
            "topic_id": topic_id,
            "vessel_id": vessel_id,
            "title": title,
            "summary": str(payload.get("summary") or ""),
            "category": str(payload.get("category") or "observation"),
            "severity": severity,
            "status": status,
            "source": str(payload.get("source") or "manual"),
            "occurred_at": str(payload.get("occurredAt") or payload.get("occurred_at") or time.strftime("%Y-%m-%dT%H:%M:%S")),
            "lat": lat,
            "lng": lng,
            "location_name": str(payload.get("locationName") or payload.get("location_name") or "未命名位置"),
            "evidence_url": str(payload.get("evidenceUrl") or payload.get("evidence_url") or ""),
            "confidence": confidence,
            "assignee_agent_id": str(payload.get("assigneeAgentId") or payload.get("assignee_agent_id") or ""),
        }

    def _write_event(self, conn: sqlite3.Connection, event: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO intelligence_events
            (id, topic_id, vessel_id, title, summary, category, severity, status, source,
             occurred_at, lat, lng, location_name, evidence_url, confidence, assignee_agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                topic_id = excluded.topic_id,
                vessel_id = excluded.vessel_id,
                title = excluded.title,
                summary = excluded.summary,
                category = excluded.category,
                severity = excluded.severity,
                status = excluded.status,
                source = excluded.source,
                occurred_at = excluded.occurred_at,
                lat = excluded.lat,
                lng = excluded.lng,
                location_name = excluded.location_name,
                evidence_url = excluded.evidence_url,
                confidence = excluded.confidence,
                assignee_agent_id = excluded.assignee_agent_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event["id"], event["topic_id"], event["vessel_id"], event["title"], event["summary"],
                event["category"], event["severity"], event["status"], event["source"], event["occurred_at"],
                event["lat"], event["lng"], event["location_name"], event["evidence_url"],
                event["confidence"], event["assignee_agent_id"],
            ),
        )

    def _event_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        data = dict(row)
        return {
            "id": data["id"],
            "topicId": data.get("topic_id"),
            "topicName": data.get("topic_name"),
            "vesselId": data.get("vessel_id"),
            "vesselName": data.get("vessel_name"),
            "title": data["title"],
            "summary": data["summary"],
            "category": data["category"],
            "severity": data["severity"],
            "status": data["status"],
            "source": data["source"],
            "occurredAt": data["occurred_at"],
            "lat": data["lat"],
            "lng": data["lng"],
            "locationName": data["location_name"],
            "evidenceUrl": data["evidence_url"],
            "confidence": data["confidence"],
            "assigneeAgentId": data["assignee_agent_id"],
            "createdAt": data["created_at"],
            "updatedAt": data["updated_at"],
        }

    def list_ais_vessels(self, include_track: bool = True, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT v.*,
                       p.timestamp AS latest_timestamp,
                       p.lat AS latest_lat,
                       p.lng AS latest_lng,
                       p.speed AS latest_speed,
                       p.course AS latest_course
                FROM ais_vessels v
                LEFT JOIN ais_points p ON p.id = (
                    SELECT id FROM ais_points
                    WHERE vessel_id = v.id
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1
                )
                ORDER BY v.updated_at DESC, v.name ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            vessels = [self._vessel_row(row) for row in rows]
            if include_track:
                for vessel in vessels:
                    vessel["track"] = self.get_ais_track(vessel["id"])["track"]
            return vessels

    def get_ais_track(
        self,
        vessel_id: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        where = ["vessel_id = ?"]
        params: list[Any] = [vessel_id]
        if start:
            where.append("timestamp >= ?")
            params.append(start)
        if end:
            where.append("timestamp <= ?")
            params.append(end)
        params.append(limit)
        with self.connect() as conn:
            vessel = conn.execute("SELECT * FROM ais_vessels WHERE id = ?", (vessel_id,)).fetchone()
            points = conn.execute(
                f"""
                SELECT timestamp, lat, lng, speed, course, heading, nav_status, source
                FROM ais_points
                WHERE {' AND '.join(where)}
                ORDER BY timestamp ASC, id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return {
            "vessel": self._vessel_row(vessel) if vessel else None,
            "track": [dict(point) for point in points],
        }

    def list_ais_points(
        self,
        vessel_id: str | None = None,
        mmsi: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if vessel_id:
            where.append("p.vessel_id = ?")
            params.append(vessel_id)
        if mmsi:
            where.append("p.mmsi = ?")
            params.append(mmsi)
        if start:
            where.append("p.timestamp >= ?")
            params.append(start)
        if end:
            where.append("p.timestamp <= ?")
            params.append(end)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS count FROM ais_points p {where_sql}",
                params,
            ).fetchone()["count"]
            rows = conn.execute(
                f"""
                SELECT p.id, p.vessel_id, p.mmsi, v.name AS vessel_name,
                       p.timestamp, p.lat, p.lng, p.speed, p.course,
                       p.heading, p.nav_status, p.source, p.created_at
                FROM ais_points p
                LEFT JOIN ais_vessels v ON v.id = p.vessel_id
                {where_sql}
                ORDER BY p.timestamp DESC, p.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return {"points": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def ingest_ais_points(self, points: list[dict[str, Any]], source: str = "api") -> dict[str, Any]:
        inserted = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        with self.connect() as conn:
            for index, point in enumerate(points):
                mmsi = str(point.get("mmsi") or "").strip()
                timestamp = str(point.get("timestamp") or "").strip()
                if not mmsi or not timestamp or point.get("lat") is None or point.get("lng") is None:
                    skipped += 1
                    errors.append({"index": index, "reason": "缺少 mmsi/timestamp/lat/lng"})
                    continue
                vessel_id = str(point.get("vessel_id") or f"mmsi-{mmsi}")
                vessel = conn.execute("SELECT id FROM ais_vessels WHERE id = ? OR mmsi = ?", (vessel_id, mmsi)).fetchone()
                if not vessel:
                    conn.execute(
                        """
                        INSERT INTO ais_vessels (id, mmsi, name, vessel_type, flag, area, status, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            vessel_id,
                            mmsi,
                            str(point.get("name") or f"MMSI {mmsi}"),
                            str(point.get("vessel_type") or ""),
                            str(point.get("flag") or ""),
                            str(point.get("area") or ""),
                            str(point.get("status") or "unknown"),
                            "自动接入 AIS 点时创建",
                        ),
                    )
                else:
                    vessel_id = vessel["id"]
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO ais_points
                    (vessel_id, mmsi, timestamp, lat, lng, speed, course, heading, nav_status, source, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vessel_id,
                        mmsi,
                        timestamp,
                        float(point["lat"]),
                        float(point["lng"]),
                        float(point.get("speed") or 0),
                        float(point.get("course") or 0),
                        point.get("heading"),
                        str(point.get("nav_status") or point.get("status") or ""),
                        str(point.get("source") or source),
                        self._raw_payload(point.get("raw_payload")),
                    ),
                )
                if cursor.rowcount:
                    conn.execute("UPDATE ais_vessels SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (vessel_id,))
                    inserted += 1
                else:
                    skipped += 1
        return {"inserted": inserted, "skipped": skipped, "errors": errors[:20]}

    def import_ais_csv(self, content: str, source: str = "csv") -> dict[str, Any]:
        reader = csv.DictReader(io.StringIO(content.strip()))
        if not reader.fieldnames:
            return {"inserted": 0, "skipped": 0, "errors": [{"index": 0, "reason": "CSV 缺少表头"}]}
        points = [self._normalize_csv_row(row) for row in reader]
        result = self.ingest_ais_points(points, source=source)
        result["rows"] = len(points)
        return result

    def import_ais_json(self, content: str, source: str = "json") -> dict[str, Any]:
        payload = json.loads(content)
        points = payload.get("points") if isinstance(payload, dict) else payload
        if not isinstance(points, list):
            return {"inserted": 0, "skipped": 0, "errors": [{"index": 0, "reason": "JSON 必须是数组或包含 points 数组"}]}
        result = self.ingest_ais_points(points, source=source)
        result["rows"] = len(points)
        return result

    def list_ais_sources(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM ais_sources
                ORDER BY updated_at DESC, name ASC
                """
            ).fetchall()
        return [self._source_row(row) for row in rows]

    def save_ais_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = str(payload.get("id") or f"ais-src-{uuid4().hex[:10]}")
        name = str(payload.get("name") or "").strip()
        url = str(payload.get("url") or "").strip()
        fmt = str(payload.get("format") or "csv").lower()
        if not name:
            return {"status": "error", "message": "name 不能为空"}
        if not url:
            return {"status": "error", "message": "url 不能为空"}
        if fmt not in {"csv", "json"}:
            return {"status": "error", "message": "format 仅支持 csv/json"}
        headers = payload.get("headers") or {}
        if isinstance(headers, str):
            headers_json = headers
        else:
            headers_json = json.dumps(headers, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ais_sources
                (id, name, source_type, url, method, format, headers_json, enabled, poll_interval_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    source_type = excluded.source_type,
                    url = excluded.url,
                    method = excluded.method,
                    format = excluded.format,
                    headers_json = excluded.headers_json,
                    enabled = excluded.enabled,
                    poll_interval_seconds = excluded.poll_interval_seconds,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    source_id,
                    name,
                    str(payload.get("source_type") or "http"),
                    url,
                    str(payload.get("method") or "GET").upper(),
                    fmt,
                    headers_json,
                    1 if payload.get("enabled", True) else 0,
                    int(payload.get("poll_interval_seconds") or 3600),
                ),
            )
            row = conn.execute("SELECT * FROM ais_sources WHERE id = ?", (source_id,)).fetchone()
        return {"status": "ok", "source": self._source_row(row)}

    def delete_ais_source(self, source_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM ais_sources WHERE id = ?", (source_id,))
            return bool(cursor.rowcount)

    def sync_ais_source(self, source_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ais_sources WHERE id = ?", (source_id,)).fetchone()
        source = self._source_row(row)
        if not source:
            return {"status": "error", "message": "AIS 数据源不存在"}
        if source["source_type"] != "http":
            return {"status": "error", "message": "当前仅支持 http 数据源"}
        started = time.time()
        try:
            content = self._fetch_http_source(source)
            if source["format"] == "json":
                result = self.import_ais_json(content, source=source["id"])
            else:
                result = self.import_ais_csv(content, source=source["id"])
            message = f"写入 {result.get('inserted', 0)} 条，跳过 {result.get('skipped', 0)} 条"
            self._update_source_run(source_id, "ok", message)
            return {"status": "ok", "source": source, "duration_ms": int((time.time() - started) * 1000), **result}
        except Exception as exc:
            message = str(exc)
            self._update_source_run(source_id, "error", message)
            return {"status": "error", "source": source, "message": message}

    def _vessel_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        if "vessel_type" in data:
            data["type"] = data.pop("vessel_type")
        if data.get("latest_timestamp"):
            data["latest"] = {
                "timestamp": data.pop("latest_timestamp"),
                "lat": data.pop("latest_lat"),
                "lng": data.pop("latest_lng"),
                "speed": data.pop("latest_speed"),
                "course": data.pop("latest_course"),
            }
        return data

    def _raw_payload(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _normalize_csv_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = {str(key).strip(): value for key, value in row.items() if key is not None}
        aliases = {
            "longitude": "lng",
            "lon": "lng",
            "latitude": "lat",
            "sog": "speed",
            "cog": "course",
            "ship_name": "name",
            "vessel_name": "name",
            "ship_type": "vessel_type",
            "type": "vessel_type",
            "time": "timestamp",
            "ts": "timestamp",
        }
        for src, dst in aliases.items():
            if src in normalized and dst not in normalized:
                normalized[dst] = normalized[src]
        return normalized

    def _source_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        try:
            data["headers"] = json.loads(data.pop("headers_json") or "{}")
        except json.JSONDecodeError:
            data["headers"] = {}
        data["enabled"] = bool(data.get("enabled"))
        return data

    def _fetch_http_source(self, source: dict[str, Any]) -> str:
        headers = {str(k): str(v) for k, v in (source.get("headers") or {}).items() if v is not None}
        request = urllib.request.Request(source["url"], headers=headers, method=source.get("method") or "GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"网络请求失败: {exc.reason}") from exc

    def _update_source_run(self, source_id: str, status: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ais_sources
                SET last_run_at = CURRENT_TIMESTAMP,
                    last_status = ?,
                    last_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, message[:500], source_id),
            )

    def sync_world_cup_2026(self) -> dict[str, Any]:
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/"
            "fifa.world/scoreboard?limit=200&dates=2026"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "OpenClaw-Intelligence/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"世界杯数据同步失败: {exc}") from exc
        return self.import_world_cup_2026(payload, source_url=url)

    def import_world_cup_2026(self, payload: dict[str, Any], source_url: str = "") -> dict[str, Any]:
        events = payload.get("events")
        if not isinstance(events, list) or not events:
            raise ValueError("世界杯数据缺少 events")

        matches: list[dict[str, Any]] = []
        goals: list[dict[str, Any]] = []
        for event in events:
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            competition = competitions[0]
            competitors = competition.get("competitors") or []
            home = next((item for item in competitors if item.get("homeAway") == "home"), None)
            away = next((item for item in competitors if item.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            status_type = (competition.get("status") or event.get("status") or {}).get("type") or {}
            venue = competition.get("venue") or {}
            venue_address = venue.get("address") or {}
            season = event.get("season") or {}
            match_id = str(event.get("id") or competition.get("id") or "").strip()
            if not match_id:
                continue

            def team_data(item: dict[str, Any]) -> dict[str, str]:
                team = item.get("team") or {}
                return {
                    "id": str(team.get("id") or item.get("id") or ""),
                    "name": str(team.get("displayName") or team.get("name") or ""),
                    "code": str(team.get("abbreviation") or ""),
                    "logo": str(team.get("logo") or ""),
                }

            home_team = team_data(home)
            away_team = team_data(away)
            match = {
                "id": match_id,
                "kickoff_at": str(event.get("date") or competition.get("date") or ""),
                "stage": str(season.get("slug") or ""),
                "stage_label": str(competition.get("altGameNote") or season.get("slug") or ""),
                "status": str(status_type.get("name") or "STATUS_SCHEDULED"),
                "status_label": str(status_type.get("shortDetail") or status_type.get("detail") or ""),
                "completed": 1 if status_type.get("completed") else 0,
                "home_team_id": home_team["id"],
                "home_team": home_team["name"],
                "home_code": home_team["code"],
                "home_logo": home_team["logo"],
                "home_score": int(home.get("score") or 0),
                "away_team_id": away_team["id"],
                "away_team": away_team["name"],
                "away_code": away_team["code"],
                "away_logo": away_team["logo"],
                "away_score": int(away.get("score") or 0),
                "venue": str(venue.get("fullName") or (event.get("venue") or {}).get("displayName") or ""),
                "location": ", ".join(filter(None, [venue_address.get("city"), venue_address.get("country")])),
                "source": "ESPN",
                "source_url": source_url,
                "raw_json": json.dumps(event, ensure_ascii=False),
            }
            matches.append(match)

            team_names = {home_team["id"]: home_team["name"], away_team["id"]: away_team["name"]}
            scoring_plays = [
                detail for detail in (competition.get("details") or [])
                if detail.get("scoringPlay") and not detail.get("shootout")
            ]
            for sequence, detail in enumerate(scoring_plays, start=1):
                clock = detail.get("clock") or {}
                athlete = ((detail.get("athletesInvolved") or [{}])[0])
                team_id = str((detail.get("team") or {}).get("id") or "")
                display = str(clock.get("displayValue") or "")
                base_minute, stoppage = self._parse_goal_minute(display)
                goals.append({
                    "id": f"{match_id}:{sequence}",
                    "match_id": match_id,
                    "sequence": sequence,
                    "team_id": team_id,
                    "team_name": team_names.get(team_id, ""),
                    "scorer_id": str(athlete.get("id") or ""),
                    "scorer_name": str(athlete.get("displayName") or "未知球员"),
                    "minute": base_minute,
                    "stoppage_minute": stoppage,
                    "minute_label": display,
                    "goal_type": str((detail.get("type") or {}).get("text") or "Goal"),
                    "penalty": 1 if detail.get("penaltyKick") else 0,
                    "own_goal": 1 if detail.get("ownGoal") else 0,
                    "score_value": int(detail.get("scoreValue") or 1),
                    "raw_json": json.dumps(detail, ensure_ascii=False),
                })

        if not matches:
            raise ValueError("世界杯数据中没有可用比赛")
        with self.connect() as conn:
            for match in matches:
                conn.execute(
                    """
                    INSERT INTO world_cup_matches (
                        id, kickoff_at, stage, stage_label, status, status_label, completed,
                        home_team_id, home_team, home_code, home_logo, home_score,
                        away_team_id, away_team, away_code, away_logo, away_score,
                        venue, location, source, source_url, raw_json, fetched_at, updated_at
                    ) VALUES (
                        :id, :kickoff_at, :stage, :stage_label, :status, :status_label, :completed,
                        :home_team_id, :home_team, :home_code, :home_logo, :home_score,
                        :away_team_id, :away_team, :away_code, :away_logo, :away_score,
                        :venue, :location, :source, :source_url, :raw_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        kickoff_at=excluded.kickoff_at, stage=excluded.stage,
                        stage_label=excluded.stage_label, status=excluded.status,
                        status_label=excluded.status_label, completed=excluded.completed,
                        home_team_id=excluded.home_team_id, home_team=excluded.home_team,
                        home_code=excluded.home_code, home_logo=excluded.home_logo,
                        home_score=excluded.home_score, away_team_id=excluded.away_team_id,
                        away_team=excluded.away_team, away_code=excluded.away_code,
                        away_logo=excluded.away_logo, away_score=excluded.away_score,
                        venue=excluded.venue, location=excluded.location, source=excluded.source,
                        source_url=excluded.source_url, raw_json=excluded.raw_json,
                        fetched_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                    """,
                    match,
                )
            match_ids = [match["id"] for match in matches]
            placeholders = ",".join("?" for _ in match_ids)
            conn.execute(f"DELETE FROM world_cup_goals WHERE match_id IN ({placeholders})", match_ids)
            conn.executemany(
                """
                INSERT INTO world_cup_goals (
                    id, match_id, sequence, team_id, team_name, scorer_id, scorer_name,
                    minute, stoppage_minute, minute_label, goal_type, penalty, own_goal,
                    score_value, raw_json
                ) VALUES (
                    :id, :match_id, :sequence, :team_id, :team_name, :scorer_id, :scorer_name,
                    :minute, :stoppage_minute, :minute_label, :goal_type, :penalty, :own_goal,
                    :score_value, :raw_json
                )
                """,
                goals,
            )
            completed = sum(match["completed"] for match in matches)
            conn.execute(
                """
                INSERT INTO intelligence_topics (
                    id, name, icon, description, status, sources_json, records_label,
                    record_value, updated_label, goal, lat, lng, location_name,
                    related_locations_json, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, '刚刚同步', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    description=excluded.description, status='active', sources_json=excluded.sources_json,
                    records_label=excluded.records_label, record_value=excluded.record_value,
                    updated_label=excluded.updated_label, goal=excluded.goal, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    "world-cup-2026", "2026 美加墨世界杯", "⚽",
                    "逐场比分、进球球员与进球时间专题数据",
                    json.dumps(["FIFA 官方赛程", "ESPN 比赛事件"], ensure_ascii=False),
                    f"{completed} 场完赛 / {len(goals)} 球", completed,
                    "持续沉淀赛事结果与进球时间，支持球队、阶段和时间分布分析。",
                    39.0997, -94.5786, "加拿大 / 墨西哥 / 美国",
                    json.dumps(["canada", "mexico", "usa"], ensure_ascii=False),
                ),
            )
        return {"status": "ok", "matches": len(matches), "completed": completed, "goals": len(goals)}

    def world_cup_2026_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            totals = dict(conn.execute(
                """
                SELECT COUNT(*) AS matches, SUM(completed) AS completed,
                       SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) AS scheduled,
                       MAX(fetched_at) AS updated_at
                FROM world_cup_matches
                """
            ).fetchone())
            goals = conn.execute("SELECT COUNT(*) AS count FROM world_cup_goals").fetchone()["count"]
            scorers = [dict(row) for row in conn.execute(
                """
                SELECT scorer_name AS name, team_name AS team, COUNT(*) AS goals
                FROM world_cup_goals WHERE own_goal = 0
                GROUP BY scorer_id, scorer_name, team_name
                ORDER BY goals DESC, name ASC LIMIT 12
                """
            )]
            periods = [dict(row) for row in conn.execute(
                """
                SELECT CASE
                    WHEN minute <= 15 THEN '1-15'
                    WHEN minute <= 30 THEN '16-30'
                    WHEN minute <= 45 THEN '31-45+'
                    WHEN minute <= 60 THEN '46-60'
                    WHEN minute <= 75 THEN '61-75'
                    WHEN minute <= 90 THEN '76-90+'
                    ELSE '加时赛' END AS period,
                    COUNT(*) AS goals
                FROM world_cup_goals
                GROUP BY period
                ORDER BY MIN(minute)
                """
            )]
        totals["goals"] = goals
        totals["average_goals"] = round(goals / totals["completed"], 2) if totals.get("completed") else 0
        totals["top_scorers"] = scorers
        totals["goal_periods"] = periods
        return totals

    def list_world_cup_2026_matches(
        self, stage: str | None = None, team: str | None = None, completed: bool | None = None
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if stage:
            where.append("stage = ?")
            params.append(stage)
        if team:
            where.append("(home_team LIKE ? OR away_team LIKE ? OR home_code LIKE ? OR away_code LIKE ?)")
            term = f"%{team}%"
            params.extend([term, term, term, term])
        if completed is not None:
            where.append("completed = ?")
            params.append(1 if completed else 0)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM world_cup_matches {clause} ORDER BY kickoff_at DESC", params
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["completed"] = bool(item["completed"])
                item.pop("raw_json", None)
                item["goals"] = [
                    {**dict(goal), "penalty": bool(goal["penalty"]), "own_goal": bool(goal["own_goal"])}
                    for goal in conn.execute(
                        """
                        SELECT id, sequence, team_name, scorer_name, minute, stoppage_minute,
                               minute_label, goal_type, penalty, own_goal
                        FROM world_cup_goals WHERE match_id = ? ORDER BY sequence
                        """,
                        (item["id"],),
                    )
                ]
                result.append(item)
        return result

    def _parse_goal_minute(self, label: str) -> tuple[int, int]:
        clean = label.replace("'", "").strip()
        if "+" in clean:
            base, extra = clean.split("+", 1)
            return int(base or 0), int(extra or 0)
        try:
            return int(clean or 0), 0
        except ValueError:
            return 0, 0


intelligence_service = IntelligenceService()
