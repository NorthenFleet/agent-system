"""
任务管理 API (增强版)

支持任务与开发计划的从属关系管理

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from models.task_plan import Task, DevelopmentPlan, TaskStatusEnum, TaskPriorityEnum
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/tasks', tags=['tasks'])


# ============================================================================
# 辅助函数
# ============================================================================

def generate_task_id() -> str:
    """生成任务 ID (格式：YYYYMMDD-XXX)"""
    date_str = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid4())[:3].upper()
    return f"{date_str}-{unique_id}"


def validate_task_status_transition(current_status: TaskStatusEnum, new_status: TaskStatusEnum) -> bool:
    """验证任务状态转换是否合法"""
    valid_transitions = {
        TaskStatusEnum.PENDING: [TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.BLOCKED],
        TaskStatusEnum.IN_PROGRESS: [TaskStatusEnum.TESTING, TaskStatusEnum.COMPLETED, TaskStatusEnum.BLOCKED, TaskStatusEnum.FAILED],
        TaskStatusEnum.TESTING: [TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.COMPLETED, TaskStatusEnum.FAILED],
        TaskStatusEnum.BLOCKED: [TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.FAILED],
        TaskStatusEnum.FAILED: [TaskStatusEnum.PENDING, TaskStatusEnum.IN_PROGRESS],
        TaskStatusEnum.COMPLETED: [],  # 已完成状态不可变更
    }
    
    if current_status == new_status:
        return True
    
    return new_status in valid_transitions.get(current_status, [])


# ============================================================================
# API 接口
# ============================================================================

@router.post('', response_model=dict, status_code=201)
def create_task(
    title: str,
    assignee: str,
    description: Optional[str] = None,
    priority: Optional[str] = 'normal',
    deadline: Optional[datetime] = None,
    context: Optional[dict] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    创建任务
    
    - **title**: 任务标题
    - **assignee**: 负责人
    - **description**: 任务描述 (可选)
    - **priority**: 优先级 (low/normal/high/critical)
    - **deadline**: 截止时间 (可选)
    - **context**: 任务上下文 (可选)
    - **tags**: 标签列表 (可选)
    """
    try:
        # 验证优先级
        try:
            priority_enum = TaskPriorityEnum(priority) if priority else TaskPriorityEnum.NORMAL
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
        
        # 创建任务
        task = Task(
            id=generate_task_id(),
            title=title,
            description=description,
            priority=priority_enum,
            status=TaskStatusEnum.PENDING,
            progress=0,
            assignee=assignee,
            creator='system',  # TODO: 从认证信息获取
            deadline=deadline,
            context=context or {},
            subtasks=[],
            tags=tags or [],
            extra_metadata=metadata or {},
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task created: {task.id} - {task.title}")
        
        return {
            'success': True,
            'data': task.to_dict(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{task_id}', response_model=dict)
def get_task(
    task_id: str,
    include_plans: bool = Query(False, description='是否包含所有计划'),
    include_active_plan: bool = Query(False, description='是否包含激活计划详情'),
    db: Session = Depends(get_db)
):
    """
    获取任务详情
    
    - **task_id**: 任务 ID
    - **include_plans**: 是否包含所有计划 (默认 false)
    - **include_active_plan**: 是否包含激活计划详情 (默认 false)
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    return {
        'success': True,
        'data': task.to_dict(include_plans=include_plans, include_active_plan=include_active_plan),
        'timestamp': datetime.utcnow().isoformat()
    }


@router.put('/{task_id}', response_model=dict)
def update_task(
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    assignee: Optional[str] = None,
    deadline: Optional[datetime] = None,
    context: Optional[dict] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    更新任务
    
    所有字段均为可选，仅更新提供的字段
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    try:
        # 更新字段
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            try:
                task.priority = TaskPriorityEnum(priority)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
        if status is not None:
            try:
                new_status = TaskStatusEnum(status)
                if not validate_task_status_transition(task.status, new_status):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid status transition from {task.status.value} to {new_status.value}"
                    )
                task.status = new_status
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        if progress is not None:
            if progress < 0 or progress > 100:
                raise HTTPException(status_code=400, detail='Progress must be between 0 and 100')
            task.progress = progress
        if assignee is not None:
            task.assignee = assignee
        if deadline is not None:
            task.deadline = deadline
        if context is not None:
            task.context = context
        if tags is not None:
            task.tags = tags
        if metadata is not None:
            task.extra_metadata = metadata
        
        db.commit()
        db.refresh(task)
        
        logger.info(f"Task updated: {task_id}")
        
        return {
            'success': True,
            'data': task.to_dict(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete('/{task_id}', status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """
    删除任务
    
    如果任务有激活计划，将一并删除
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    try:
        db.delete(task)
        db.commit()
        
        logger.info(f"Task deleted: {task_id}")
        
        return {'success': True, 'message': 'Task deleted successfully'}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('', response_model=dict)
def list_tasks(
    status: Optional[str] = Query(None, description='任务状态过滤'),
    priority: Optional[str] = Query(None, description='优先级过滤'),
    assignee: Optional[str] = Query(None, description='负责人过滤'),
    creator: Optional[str] = Query(None, description='创建人过滤'),
    tags: Optional[str] = Query(None, description='标签过滤 (逗号分隔)'),
    has_active_plan: Optional[bool] = Query(None, description='是否有激活计划'),
    created_after: Optional[datetime] = Query(None, description='创建时间起点'),
    created_before: Optional[datetime] = Query(None, description='创建时间终点'),
    deadline_after: Optional[datetime] = Query(None, description='截止时间起点'),
    deadline_before: Optional[datetime] = Query(None, description='截止时间终点'),
    sort_by: Optional[str] = Query('created_at', description='排序字段'),
    sort_order: Optional[str] = Query('desc', description='排序方向'),
    limit: Optional[int] = Query(20, ge=1, le=100, description='每页数量'),
    offset: Optional[int] = Query(0, ge=0, description='偏移量'),
    db: Session = Depends(get_db)
):
    """
    查询任务列表
    
    支持多种过滤和排序选项
    """
    try:
        query = db.query(Task)
        
        # 应用过滤
        if status:
            try:
                status_enum = TaskStatusEnum(status)
                query = query.filter(Task.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if priority:
            try:
                priority_enum = TaskPriorityEnum(priority)
                query = query.filter(Task.priority == priority_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")
        
        if assignee:
            query = query.filter(Task.assignee == assignee)
        
        if creator:
            query = query.filter(Task.creator == creator)
        
        if tags:
            tag_list = tags.split(',')
            query = query.filter(or_(*[Task.tags.contains([tag]) for tag in tag_list]))
        
        if has_active_plan is not None:
            if has_active_plan:
                query = query.filter(Task.active_plan_id.isnot(None))
            else:
                query = query.filter(Task.active_plan_id.is_(None))
        
        if created_after:
            query = query.filter(Task.created_at >= created_after)
        
        if created_before:
            query = query.filter(Task.created_at <= created_before)
        
        if deadline_after:
            query = query.filter(Task.deadline >= deadline_after)
        
        if deadline_before:
            query = query.filter(Task.deadline <= deadline_before)
        
        # 应用排序
        sort_field = getattr(Task, sort_by, Task.created_at)
        if sort_order == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
        
        # 分页
        total = query.count()
        tasks = query.offset(offset).limit(limit).all()
        
        return {
            'success': True,
            'data': {
                'tasks': [task.to_dict() for task in tasks],
                'pagination': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'has_more': offset + limit < total
                }
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 任务 - 计划关系接口
# ============================================================================

@router.get('/{task_id}/plans', response_model=dict)
def get_task_plans(task_id: str, db: Session = Depends(get_db)):
    """
    获取任务的所有开发计划
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    plans = db.query(DevelopmentPlan).filter(DevelopmentPlan.task_id == task_id).all()
    
    return {
        'success': True,
        'data': {
            'task_id': task_id,
            'task_title': task.title,
            'plans': [plan.to_dict() for plan in plans],
            'total': len(plans)
        },
        'timestamp': datetime.utcnow().isoformat()
    }


@router.post('/{task_id}/plans', response_model=dict, status_code=201)
def create_task_plan(
    task_id: str,
    title: str,
    type: str,
    steps: List[dict],
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    为任务添加新开发计划
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    try:
        # 验证计划类型
        from models.task_plan import PlanTypeEnum
        try:
            plan_type = PlanTypeEnum(type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid plan type: {type}")
        
        # 生成计划 ID
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 计算总工时
        estimated_hours = sum(step.get('estimatedHours', 0) for step in steps)
        
        # 创建计划
        plan = DevelopmentPlan(
            id=plan_id,
            task_id=task_id,
            title=title or f"{task.title} - 开发方案 V1",
            version=1,
            type=plan_type,
            status='pending_review',
            creator='system',  # TODO: 从认证信息获取
            steps=steps,
            estimated_total_hours=estimated_hours,
            extra_metadata=metadata or {},
        )
        
        db.add(plan)
        db.commit()
        db.refresh(plan)
        
        logger.info(f"Plan created: {plan_id} for task {task_id}")
        
        return {
            'success': True,
            'data': plan.to_dict(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/{task_id}/active_plan', response_model=dict)
def set_active_plan(
    task_id: str,
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    激活指定计划
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    plan = db.query(DevelopmentPlan).filter(
        DevelopmentPlan.id == plan_id,
        DevelopmentPlan.task_id == task_id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    if plan.status != 'approved':
        raise HTTPException(
            status_code=400,
            detail=f"Plan must be approved before activation. Current status: {plan.status.value}"
        )
    
    try:
        task.active_plan_id = plan_id
        db.commit()
        
        logger.info(f"Active plan set: {plan_id} for task {task_id}")
        
        return {
            'success': True,
            'data': {
                'task_id': task_id,
                'active_plan_id': plan_id,
                'previous_active_plan_id': task.active_plan_id if task.active_plan_id != plan_id else None,
                'updated_at': datetime.utcnow().isoformat()
            },
            'message': '激活计划已更新',
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set active plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))
