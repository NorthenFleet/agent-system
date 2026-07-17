"""Long-term intelligence APIs."""

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from services.intelligence_service import intelligence_service

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/summary")
def intelligence_summary():
    return intelligence_service.summary()


@router.get("/topics")
def list_intelligence_topics():
    return {"topics": intelligence_service.list_topics()}


@router.post("/topics")
def save_intelligence_topic(payload: dict = Body(default_factory=dict)):
    try:
        return {"topic": intelligence_service.save_topic(payload)}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/topics/{topic_id}")
def delete_intelligence_topic(topic_id: str):
    if not intelligence_service.delete_topic(topic_id):
        raise HTTPException(status_code=404, detail="情报专题不存在")
    return {"status": "ok"}


@router.get("/world-cup-2026/summary")
def world_cup_2026_summary():
    return intelligence_service.world_cup_2026_summary()


@router.get("/world-cup-2026/matches")
def list_world_cup_2026_matches(
    stage: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    completed: Optional[bool] = Query(None),
):
    return {
        "matches": intelligence_service.list_world_cup_2026_matches(
            stage=stage,
            team=team,
            completed=completed,
        )
    }


@router.post("/world-cup-2026/sync")
def sync_world_cup_2026():
    try:
        return intelligence_service.sync_world_cup_2026()
    except (RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/world-cup-2026/import")
def import_world_cup_2026(payload: dict = Body(default_factory=dict)):
    try:
        return intelligence_service.import_world_cup_2026(payload, source_url="manual-import")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/events")
def list_intelligence_events(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    topic_id: Optional[str] = Query(None),
    vessel_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    return {
        "events": intelligence_service.list_events(
            severity=severity,
            status=status,
            topic_id=topic_id,
            vessel_id=vessel_id,
            limit=limit,
        )
    }


@router.post("/events")
def save_intelligence_event(payload: dict = Body(default_factory=dict)):
    try:
        return {"event": intelligence_service.save_event(payload)}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/events/{event_id}/status")
def update_intelligence_event_status(event_id: str, payload: dict = Body(default_factory=dict)):
    try:
        event = intelligence_service.update_event_status(event_id, str(payload.get("status") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not event:
        raise HTTPException(status_code=404, detail="情报事件不存在")
    return {"event": event}


@router.delete("/events/{event_id}")
def delete_intelligence_event(event_id: str):
    if not intelligence_service.delete_event(event_id):
        raise HTTPException(status_code=404, detail="情报事件不存在")
    return {"status": "ok"}


@router.get("/ais/vessels")
def list_ais_vessels(
    include_track: bool = Query(True),
    limit: int = Query(200, ge=1, le=1000),
):
    return {
        "vessels": intelligence_service.list_ais_vessels(include_track=include_track, limit=limit)
    }


@router.get("/ais/vessels/{vessel_id}/track")
def get_ais_track(
    vessel_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
):
    result = intelligence_service.get_ais_track(vessel_id=vessel_id, start=start, end=end, limit=limit)
    if not result["vessel"]:
        raise HTTPException(status_code=404, detail="AIS 舰艇不存在")
    return result


@router.get("/ais/points")
def list_ais_points(
    vessel_id: Optional[str] = Query(None),
    mmsi: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    return intelligence_service.list_ais_points(
        vessel_id=vessel_id,
        mmsi=mmsi,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.post("/ais/points")
def ingest_ais_points(payload: dict = Body(default_factory=dict)):
    points = payload.get("points")
    if not isinstance(points, list):
        raise HTTPException(status_code=400, detail="points 必须是数组")
    return intelligence_service.ingest_ais_points(points, source=str(payload.get("source") or "api"))


@router.post("/ais/import")
def import_ais_payload(payload: dict = Body(default_factory=dict)):
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    fmt = str(payload.get("format") or "csv").lower()
    source = str(payload.get("source") or fmt)
    try:
        if fmt == "csv":
            return intelligence_service.import_ais_csv(content, source=source)
        if fmt == "json":
            return intelligence_service.import_ais_json(content, source=source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"AIS 导入失败: {exc}") from exc
    raise HTTPException(status_code=400, detail="format 仅支持 csv 或 json")


@router.get("/ais/sources")
def list_ais_sources():
    return {"sources": intelligence_service.list_ais_sources()}


@router.post("/ais/sources")
def save_ais_source(payload: dict = Body(default_factory=dict)):
    result = intelligence_service.save_ais_source(payload)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.delete("/ais/sources/{source_id}")
def delete_ais_source(source_id: str):
    if not intelligence_service.delete_ais_source(source_id):
        raise HTTPException(status_code=404, detail="AIS 数据源不存在")
    return {"status": "ok"}


@router.post("/ais/sources/{source_id}/sync")
def sync_ais_source(source_id: str):
    result = intelligence_service.sync_ais_source(source_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
