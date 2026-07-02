"""
后台自动任务 API - 李奥纳多生成 + 擎天柱审核
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import asyncio
from datetime import datetime

router = APIRouter(tags=["auto-tasks"])

# 后台自动任务状态
auto_task_running = False
auto_task_interval_generate = 1800  # 李奥纳多生成计划：30 分钟
auto_task_interval_review = 600     # 擎天柱审核计划：10 分钟


async def run_auto_task_bootstrap():
    """在后台执行首次自动任务，避免阻塞服务启动。"""
    try:
        print("[Auto] 初始执行...")
        from auto_plan_manager import auto_plan_manager
        auto_plan_manager.leonardo_auto_generate()
        await asyncio.sleep(2)
        auto_plan_manager.optimus_auto_review(auto_approve=True)
    except Exception as e:
        print(f"[Auto] 初始执行出错：{e}")


async def leonardo_auto_generate_task(initial_delay: int = 0):
    """李奥纳多后台自动生成计划"""
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    
    while auto_task_running:
        try:
            print("[Auto] 李奥纳多开始自动生成计划...")
            from auto_plan_manager import auto_plan_manager
            result = auto_plan_manager.leonardo_auto_generate()
            print(f"[Auto] 李奥纳多完成：生成{len(result.get('generated', []))}个计划")
        except Exception as e:
            print(f"[Auto] 李奥纳多出错：{e}")
        
        await asyncio.sleep(auto_task_interval_generate)


async def optimus_auto_review_task(initial_delay: int = 0):
    """擎天柱后台自动审核计划"""
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)
    
    while auto_task_running:
        try:
            print("[Auto] 擎天柱开始自动审核计划...")
            from auto_plan_manager import auto_plan_manager
            result = auto_plan_manager.optimus_auto_review(auto_approve=True)
            print(f"[Auto] 擎天柱完成：通过{len(result.get('approved', []))}个计划")
        except Exception as e:
            print(f"[Auto] 擎天柱出错：{e}")
        
        await asyncio.sleep(auto_task_interval_review)


async def start_auto_tasks():
    """启动后台自动任务"""
    global auto_task_running
    if auto_task_running:
        print("[Auto] 后台自动任务已在运行，跳过重复启动")
        return

    auto_task_running = True
    print("[Auto] 启动后台自动任务...")
    asyncio.create_task(run_auto_task_bootstrap())
    asyncio.create_task(leonardo_auto_generate_task(auto_task_interval_generate))
    asyncio.create_task(optimus_auto_review_task(auto_task_interval_review))
    print("[Auto] 后台自动任务已启动")
    print(f"[Auto] 李奥纳多生成计划间隔：{auto_task_interval_generate}秒")
    print(f"[Auto] 擎天柱审核计划间隔：{auto_task_interval_review}秒")


# ==================== Auto Tasks API ====================

@router.get("/api/auto/status")
async def get_auto_status():
    """获取自动任务状态"""
    return {
        "running": auto_task_running,
        "leonardo_interval": auto_task_interval_generate,
        "optimus_interval": auto_task_interval_review,
        "leonardo_interval_min": auto_task_interval_generate // 60,
        "optimus_interval_min": auto_task_interval_review // 60
    }


@router.get("/api/auto/logs")
def get_auto_logs(limit: int = 50):
    """获取自动任务执行日志"""
    from auto_plan_manager import auto_plan_manager
    return {"logs": auto_plan_manager.get_auto_logs(limit)}


@router.post("/api/auto/leonardo/generate")
def trigger_leonardo_generate():
    """手动触发李奥纳多生成计划"""
    from auto_plan_manager import auto_plan_manager
    result = auto_plan_manager.leonardo_auto_generate()
    return result


@router.post("/api/auto/optimus/review")
def trigger_optimus_review():
    """手动触发擎天柱审核计划"""
    from auto_plan_manager import auto_plan_manager
    result = auto_plan_manager.optimus_auto_review(auto_approve=True)
    return result


@router.post("/api/auto/start")
async def start_auto_tasks_api():
    """启动后台自动任务"""
    await start_auto_tasks()
    return {"success": True, "message": "后台自动任务已启动"}


@router.post("/api/auto/stop")
def stop_auto_tasks_api():
    """停止后台自动任务"""
    global auto_task_running
    auto_task_running = False
    return {"success": True, "message": "后台自动任务已停止"}
