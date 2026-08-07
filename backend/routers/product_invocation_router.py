"""Product Invocation Bridge API router.

暴露给 3021 前端的 API，让擎天柱可以：
1. 查看可用产品动作列表
2. 发起单次调用
3. 批量调用
4. 查看调用日志
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from services.auth_service import get_current_user
from services.product_invocation_bridge import product_invocation_bridge

router = APIRouter(prefix="/api/v2/product-invocation", tags=["product-invocation"])


@router.get("/actions")
async def list_available_actions(
    product_id: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """列出可用的产品调用动作。"""
    return {
        "actions": product_invocation_bridge.get_available_actions(product_id),
    }


@router.post("/invoke")
async def invoke_product(
    req: dict[str, Any],
    _user: dict = Depends(get_current_user),
):
    """执行一次产品调用。

    Request body:
    {
        "product_id": "one-sim",
        "action": "one-sim.health",          # 预定义动作
        "endpoint": "/api/custom/path",       # 可选：自定义端点（覆盖 action）
        "method": "GET",                      # 可选：HTTP 方法
        "payload": {},                        # 可选：POST/PUT 请求体
        "params": {},                         # 可选：URL 查询参数
    }
    """
    product_id = req.get("product_id")
    if not product_id:
        raise HTTPException(status_code=400, detail="缺少 product_id")

    action = req.get("action", "custom")
    result = await product_invocation_bridge.invoke(
        product_id=product_id,
        action=action,
        endpoint=req.get("endpoint"),
        method=req.get("method"),
        payload=req.get("payload"),
        params=req.get("params"),
        invoked_by="optimus",
    )
    return {"invocation": result}


@router.post("/invoke/batch")
async def batch_invoke_products(
    req: dict[str, Any],
    _user: dict = Depends(get_current_user),
):
    """批量调用多个产品动作。

    Request body:
    {
        "calls": [
            {"product_id": "one-sim", "action": "one-sim.health"},
            {"product_id": "ai-planning-5130", "action": "planning.supervisor-status"},
        ],
        "concurrency": 3  # 可选，默认 3
    }
    """
    calls = req.get("calls")
    if not calls or not isinstance(calls, list):
        raise HTTPException(status_code=400, detail="缺少 calls 列表")

    concurrency = int(req.get("concurrency", 3))
    results = await product_invocation_bridge.batch_invoke(
        calls=calls,
        invoked_by="optimus",
        concurrency=concurrency,
    )
    return {"results": results, "count": len(results)}


@router.get("/logs")
async def get_invoke_logs(
    limit: int = 50,
    product_id: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """查询调用日志。"""
    return {
        "logs": product_invocation_bridge.get_invoke_log(limit=limit, product_id=product_id),
        "count": limit,
    }


@router.get("/products/{product_id}/logs")
async def get_product_invoke_logs(
    product_id: str,
    limit: int = 50,
    _user: dict = Depends(get_current_user),
):
    """查询指定产品的调用日志。"""
    return {
        "product_id": product_id,
        "logs": product_invocation_bridge.get_invoke_log(limit=limit, product_id=product_id),
    }
