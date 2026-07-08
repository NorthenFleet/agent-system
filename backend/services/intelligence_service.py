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
                """
            )
            self._seed_if_empty(conn)

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

    def summary(self) -> dict[str, Any]:
        with self.connect() as conn:
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
            "vessels": vessel_count,
            "points": point_count,
            "latest_timestamp": latest,
            "sources": [dict(row) for row in sources],
            "database": str(self.db_path),
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


intelligence_service = IntelligenceService()
