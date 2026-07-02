from fastapi import APIRouter

router = APIRouter(prefix="/api/auto", tags=["auto"])


def _get_auto_plan_manager():
    from auto_plan_manager import auto_plan_manager
    return auto_plan_manager


def _get_auto_status():
    # 需要从 main.py 导入这些变量
    import main
    return {
        "running": main.auto_task_running,
        "leonardo_interval": main.auto_task_interval_generate,
        "optimus_interval": main.auto_task_interval_review,
        "leonardo_interval_min": main.auto_task_interval_generate // 60,
        "optimus_interval_min": main.auto_task_interval_review // 60
    }


@router.get("/logs")
def get_auto_log(limit: int = 50):
    """获取自动任务执行日志"""
    auto_mgr = _get_auto_plan_manager()
    return {"logs": auto_mgr.get_auto_logs(limit)}


@router.post("/leonardo/generate")
def leonardo_generate():
    """手动触发李奥纳多生成计划"""
    auto_mgr = _get_auto_plan_manager()
    result = auto_mgr.leonardo_auto_generate()
    return result


@router.post("/optimus/review")
def optimus_review():
    """手动触发擎天柱审核计划"""
    auto_mgr = _get_auto_plan_manager()
    result = auto_mgr.optimus_auto_review(auto_approve=True)
    return result


@router.get("/status")
def get_auto_status():
    """获取自动任务状态"""
    return _get_auto_status()
