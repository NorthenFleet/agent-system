"""Long-term intelligence APIs."""

from fastapi import APIRouter, Body, HTTPException, Query

from services.intelligence_service import intelligence_service

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/summary")
def intelligence_summary():
    return intelligence_service.summary()


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
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
):
    result = intelligence_service.get_ais_track(vessel_id=vessel_id, start=start, end=end, limit=limit)
    if not result["vessel"]:
        raise HTTPException(status_code=404, detail="AIS 舰艇不存在")
    return result


@router.get("/ais/points")
def list_ais_points(
    vessel_id: str | None = Query(None),
    mmsi: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
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
