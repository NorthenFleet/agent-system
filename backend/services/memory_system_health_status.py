"""Read memory gate state and publish deduplicated dashboard notifications."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models.v2_models import Notification, User
from services.notification_service import NotificationService


DEFAULT_STATUS_PATH = Path(__file__).resolve().parents[1] / "data" / "memory-system-health.json"
DEFAULT_MATRIX_PATH = Path(__file__).resolve().parents[1] / "data" / "memory-system-matrix.json"
MAX_STATUS_BYTES = 1_000_000
DEFAULT_STALE_AFTER_SECONDS = 35 * 60
SOURCE_PREFIX = "memory-system:"


class MemorySystemHealthStatusError(RuntimeError):
    pass


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _status_path(path: str | Path | None = None) -> Path:
    configured = path or os.getenv("MEMORY_SYSTEM_HEALTH_PATH") or DEFAULT_STATUS_PATH
    return Path(configured).expanduser()


def read_memory_system_health(
    path: str | Path | None = None,
    *,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a safe operational snapshot; missing or stale state fails closed."""
    selected = _status_path(path)
    if not selected.is_file():
        return {
            "schema_version": "memory-system-monitor.v1",
            "status": "missing",
            "healthy": False,
            "checked_at": None,
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "summary": {},
            "failures": [{"check": "health_state", "expected": "present", "actual": "missing"}],
        }
    try:
        if selected.stat().st_size > MAX_STATUS_BYTES:
            raise MemorySystemHealthStatusError("memory health state exceeds size limit")
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, MemorySystemHealthStatusError) as exc:
        return {
            "schema_version": "memory-system-monitor.v1",
            "status": "invalid",
            "healthy": False,
            "checked_at": None,
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "summary": {},
            "failures": [{"check": "health_state", "expected": "valid JSON", "actual": str(exc)[:500]}],
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "memory-system-monitor.v1",
            "status": "invalid",
            "healthy": False,
            "checked_at": None,
            "age_seconds": None,
            "stale_after_seconds": stale_after_seconds,
            "summary": {},
            "failures": [{"check": "health_state", "expected": "object", "actual": type(payload).__name__}],
        }

    checked = _parse_time(payload.get("checked_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = max(0, int((current - checked).total_seconds())) if checked else None
    stale = checked is None or age is None or age > stale_after_seconds
    reported_healthy = payload.get("healthy") is True
    status = "stale" if stale else ("healthy" if reported_healthy else "unhealthy")
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if stale:
        failures = [
            *failures,
            {
                "check": "freshness",
                "expected": {"maximum_age_seconds": stale_after_seconds},
                "actual": age,
            },
        ]
    return {
        "schema_version": "memory-system-monitor.v1",
        "status": status,
        "healthy": status == "healthy",
        "reported_healthy": reported_healthy,
        "checked_at": checked.isoformat() if checked else None,
        "age_seconds": age,
        "stale_after_seconds": stale_after_seconds,
        "case_id": str(payload.get("case_id") or ""),
        "attempt": payload.get("attempt"),
        "attempts_configured": payload.get("attempts_configured"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "failures": failures[:50],
    }


def read_memory_system_matrix(
    path: str | Path | None = None,
    *,
    stale_after_seconds: int = 26 * 60 * 60,
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = Path(
        path or os.getenv("MEMORY_SYSTEM_MATRIX_PATH") or DEFAULT_MATRIX_PATH
    ).expanduser()
    if not selected.is_file():
        return {
            "status": "missing",
            "healthy": False,
            "checked_at": None,
            "age_seconds": None,
            "summary": {"total_cases": 0, "passed_cases": 0, "failed_cases": []},
            "failures": [{"check": "matrix_state", "expected": "present", "actual": "missing"}],
        }
    try:
        if selected.stat().st_size > MAX_STATUS_BYTES:
            raise MemorySystemHealthStatusError("memory matrix state exceeds size limit")
        payload = json.loads(selected.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise MemorySystemHealthStatusError("memory matrix state must be an object")
    except (OSError, json.JSONDecodeError, MemorySystemHealthStatusError) as exc:
        return {
            "status": "invalid",
            "healthy": False,
            "checked_at": None,
            "age_seconds": None,
            "summary": {"total_cases": 0, "passed_cases": 0, "failed_cases": []},
            "failures": [{"check": "matrix_state", "expected": "valid JSON", "actual": str(exc)[:500]}],
        }
    checked = _parse_time(payload.get("checked_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = max(0, int((current - checked).total_seconds())) if checked else None
    stale = checked is None or age is None or age > stale_after_seconds
    reported_healthy = payload.get("healthy") is True
    status = "stale" if stale else ("healthy" if reported_healthy else "unhealthy")
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    if stale:
        failures = [
            *failures,
            {"check": "matrix_freshness", "expected": {"maximum_age_seconds": stale_after_seconds}, "actual": age},
        ]
    return {
        "status": status,
        "healthy": status == "healthy",
        "checked_at": checked.isoformat() if checked else None,
        "age_seconds": age,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "failures": failures[:50],
        "cases": payload.get("cases") if isinstance(payload.get("cases"), list) else [],
    }


def publish_memory_health_notification(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Publish one notification per state transition, fan-out to active admins."""
    monitor_key = str(payload.get("monitor_key") or "primary").strip().lower()
    if monitor_key not in {"primary", "matrix"}:
        raise MemorySystemHealthStatusError("unsupported memory health monitor key")
    current_state = "healthy" if payload.get("healthy") is True else "unhealthy"
    monitor_prefix = f"{SOURCE_PREFIX}{monitor_key}:"
    latest = (
        db.query(Notification)
        .filter(Notification.source_id.like(f"{monitor_prefix}%"))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .first()
    )
    latest_state = ""
    if latest and latest.source_id:
        parts = str(latest.source_id).split(":", 3)
        latest_state = parts[2] if len(parts) > 2 else ""

    if latest_state == current_state or (not latest_state and current_state == "healthy"):
        return {
            "status": "unchanged",
            "state": current_state,
            "notifications_created": 0,
        }

    admins = (
        db.query(User)
        .filter(User.role == "admin", User.is_active == True)  # noqa: E712
        .order_by(User.id.asc())
        .all()
    )
    if not admins:
        raise MemorySystemHealthStatusError("no active administrator can receive memory health notifications")

    checked_at = str(payload.get("checked_at") or datetime.now(timezone.utc).isoformat())
    failure_checks = [
        str(item.get("check") or "unknown")
        for item in payload.get("failures") or []
        if isinstance(item, dict)
    ][:10]
    fingerprint = hashlib.sha256(
        json.dumps(
            {"state": current_state, "checked_at": checked_at, "failures": failure_checks},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:20]
    source_id = f"{monitor_prefix}{current_state}:{fingerprint}"
    if db.query(Notification).filter(Notification.source_id == source_id).first():
        return {"status": "duplicate", "state": current_state, "notifications_created": 0}

    if current_state == "unhealthy":
        title = "多智能体记忆矩阵异常" if monitor_key == "matrix" else "记忆系统健康门禁异常"
        detail = "失败检查：" + ("、".join(failure_checks) if failure_checks else "未知检查")
        notification_type = "alert"
    else:
        title = "多智能体记忆矩阵已恢复" if monitor_key == "matrix" else "记忆系统已恢复"
        detail = "身份绑定、3021 权威记忆、检索通道和桥接部署校验已恢复。"
        notification_type = "system"

    service = NotificationService(db)
    for admin in admins:
        service.create_notification(
            user_id=admin.id,
            type=notification_type,
            title=title,
            content=f"{detail}\n检查时间：{checked_at}",
            source_id=source_id,
            link="/monitoring",
        )
    return {
        "status": "published",
        "monitor_key": monitor_key,
        "state": current_state,
        "notifications_created": len(admins),
        "source_id": source_id,
    }
