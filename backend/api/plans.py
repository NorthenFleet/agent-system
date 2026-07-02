"""
开发计划 CRUD API

提供开发计划的创建、读取、更新、删除接口
支持计划状态管理和版本控制

@author 拉斐尔 (🐢 后端开发)
@created 2026-04-16
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.task_plan import (
    DevelopmentPlan, Task, PlanStatusEnum, PlanTypeEnum, PlanStepStatusEnum
)
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/plans', tags=['plans'])


# ============================================================================
# 辅助函数
# ============================================================================

def generate_plan_id() -> str:
    """生成计划 ID (格式：plan_YYYYMMDDHHMMSS)"""
    return f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def validate_plan_status_transition(current_status: PlanStatusEnum, new_status: PlanStatusEnum) -> bool:
    """验证计划状态转换是否合法"""
    valid_transitions = {
        PlanStatusEnum.DRAFT: [PlanStatusEnum.PENDING_REVIEW, PlanStatusEnum.ARCHIVED],
        PlanStatusEnum.PENDING_REVIEW: [PlanStatusEnum.APPROVED, PlanStatusEnum.REJECTED, PlanStatusEnum.DRAFT],
        PlanStatusEnum.APPROVED: [PlanStatusEnum.IN_PROGRESS, PlanStatusEnum.ARCHIVED],
        PlanStatusEnum.REJECTED: [PlanStatusEnum.DRAFT, PlanStatusEnum.ARCHIVED],
        PlanStatusEnum.IN_PROGRESS: [PlanStatusEnum.COMPLETED, PlanStatusEnum.BLOCKED, PlanStatusEnum.ARCHIVED],
        PlanStatusEnum.COMPLETED: [PlanStatusEnum.ARCHIVED],
        PlanStatusEnum.ARCHIVED: [],  # 已归档状态不可变更
    }
    
    if current_status == new_status:
        return True
    
    return new_status in valid_transitions.get(current_status, [])


def calculate_total_hours(steps: List[dict]) -> float:
    """计算总预估工时"""
    return sum(step.get('estimatedHours', 0) for step in steps)


# ============================================================================
# API 接口
# ============================================================================

@router.post('', response_model=dict, status_code=201)
def create_plan(
    task_id: str,
    title: Optional[str] = None,
    type: str = 'general',
    steps: Optional[List[dict]] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    创建开发计划
    
    - **task_id**: 所属任务 ID
    - **title**: 计划标题 (可选，默认使用任务标题)
    - **type**: 计划类型 (frontend/backend/testing/design/research/general)
    - **steps**: 执行步骤列表
    - **metadata**: 元数据
    """
    # 验证任务存在
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    
    try:
        # 验证计划类型
        try:
            plan_type = PlanTypeEnum(type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid plan type: {type}")
        
        # 获取任务的最新版本号
        last_plan = db.query(DevelopmentPlan).filter(
            DevelopmentPlan.task_id == task_id
        ).order_by(DevelopmentPlan.version.desc()).first()
        
        new_version = (last_plan.version + 1) if last_plan else 1
        
        # 生成计划 ID
        plan_id = generate_plan_id()
        
        # 计算总工时
        steps = steps or []
        estimated_hours = calculate_total_hours(steps)
        
        # 创建计划
        plan = DevelopmentPlan(
            id=plan_id,
            task_id=task_id,
            title=title or f"{task.title} - 开发方案 V{new_version}",
            version=new_version,
            type=plan_type,
            status=PlanStatusEnum.PENDING_REVIEW,
            creator='system',  # TODO: 从认证信息获取
            steps=steps,
            estimated_total_hours=estimated_hours,
            extra_metadata=metadata or {},
            is_based_on=last_plan.id if last_plan else None,
        )
        
        db.add(plan)
        db.commit()
        db.refresh(plan)
        
        logger.info(f"Plan created: {plan_id} for task {task_id} (version {new_version})")
        
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


@router.get('/{plan_id}', response_model=dict)
def get_plan(
    plan_id: str,
    include_task: bool = Query(False, description='是否包含所属任务详情'),
    db: Session = Depends(get_db)
):
    """
    获取计划详情
    
    - **plan_id**: 计划 ID
    - **include_task**: 是否包含所属任务详情 (默认 false)
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    return {
        'success': True,
        'data': plan.to_dict(include_task=include_task),
        'timestamp': datetime.utcnow().isoformat()
    }


@router.put('/{plan_id}', response_model=dict)
def update_plan(
    plan_id: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
    steps: Optional[List[dict]] = None,
    review_comment: Optional[str] = None,
    rejection_reason: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    更新开发计划
    
    所有字段均为可选，仅更新提供的字段
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    try:
        # 更新字段
        if title is not None:
            plan.title = title
        
        if status is not None:
            try:
                new_status = PlanStatusEnum(status)
                if not validate_plan_status_transition(plan.status, new_status):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid status transition from {plan.status.value} to {new_status.value}"
                    )
                plan.status = new_status
                
                # 自动设置审核时间
                if new_status in [PlanStatusEnum.APPROVED, PlanStatusEnum.REJECTED]:
                    plan.reviewed_at = datetime.utcnow()
                
                # 自动设置完成时间
                if new_status == PlanStatusEnum.COMPLETED:
                    plan.completed_at = datetime.utcnow()
                    
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if steps is not None:
            plan.steps = steps
            plan.estimated_total_hours = calculate_total_hours(steps)
        
        if review_comment is not None:
            plan.review_comment = review_comment
        
        if rejection_reason is not None:
            plan.rejection_reason = rejection_reason
        
        if metadata is not None:
            plan.extra_metadata = metadata
        
        db.commit()
        db.refresh(plan)
        
        logger.info(f"Plan updated: {plan_id}")
        
        return {
            'success': True,
            'data': plan.to_dict(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete('/{plan_id}', status_code=204)
def delete_plan(plan_id: str, db: Session = Depends(get_db)):
    """
    删除开发计划
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    try:
        # 如果该计划是任务的激活计划，先清除关联
        task = db.query(Task).filter(Task.active_plan_id == plan_id).first()
        if task:
            task.active_plan_id = None
        
        db.delete(plan)
        db.commit()
        
        logger.info(f"Plan deleted: {plan_id}")
        
        return {'success': True, 'message': 'Plan deleted successfully'}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('', response_model=dict)
def list_plans(
    task_id: Optional[str] = Query(None, description='所属任务 ID'),
    status: Optional[str] = Query(None, description='计划状态过滤'),
    type: Optional[str] = Query(None, description='计划类型过滤'),
    creator: Optional[str] = Query(None, description='创建人过滤'),
    reviewer: Optional[str] = Query(None, description='审核人过滤'),
    created_after: Optional[datetime] = Query(None, description='创建时间起点'),
    created_before: Optional[datetime] = Query(None, description='创建时间终点'),
    sort_by: Optional[str] = Query('created_at', description='排序字段'),
    sort_order: Optional[str] = Query('desc', description='排序方向'),
    limit: Optional[int] = Query(20, ge=1, le=100, description='每页数量'),
    offset: Optional[int] = Query(0, ge=0, description='偏移量'),
    db: Session = Depends(get_db)
):
    """
    查询计划列表
    
    支持多种过滤和排序选项
    """
    try:
        query = db.query(DevelopmentPlan)
        
        # 应用过滤
        if task_id:
            query = query.filter(DevelopmentPlan.task_id == task_id)
        
        if status:
            try:
                status_enum = PlanStatusEnum(status)
                query = query.filter(DevelopmentPlan.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if type:
            try:
                type_enum = PlanTypeEnum(type)
                query = query.filter(DevelopmentPlan.type == type_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid type: {type}")
        
        if creator:
            query = query.filter(DevelopmentPlan.creator == creator)
        
        if reviewer:
            query = query.filter(DevelopmentPlan.reviewer == reviewer)
        
        if created_after:
            query = query.filter(DevelopmentPlan.created_at >= created_after)
        
        if created_before:
            query = query.filter(DevelopmentPlan.created_at <= created_before)
        
        # 应用排序
        sort_field = getattr(DevelopmentPlan, sort_by, DevelopmentPlan.created_at)
        if sort_order == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
        
        # 分页
        total = query.count()
        plans = query.offset(offset).limit(limit).all()
        
        return {
            'success': True,
            'data': {
                'plans': [plan.to_dict() for plan in plans],
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
        logger.error(f"Failed to list plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 计划审核接口
# ============================================================================

@router.post('/{plan_id}/review', response_model=dict)
def review_plan(
    plan_id: str,
    approved: bool,
    comment: Optional[str] = None,
    rejection_reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    审核开发计划
    
    - **plan_id**: 计划 ID
    - **approved**: 是否通过审核
    - **comment**: 审核意见
    - **rejection_reason**: 拒绝原因 (仅在拒绝时提供)
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    if plan.status != PlanStatusEnum.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Plan must be in pending_review status. Current status: {plan.status.value}"
        )
    
    try:
        # 更新计划状态
        if approved:
            plan.status = PlanStatusEnum.APPROVED
            plan.review_comment = comment
            message = '计划已通过审核'
        else:
            plan.status = PlanStatusEnum.REJECTED
            plan.rejection_reason = rejection_reason or comment
            message = '计划已被拒绝'
        
        plan.reviewed_at = datetime.utcnow()
        plan.reviewer = 'system'  # TODO: 从认证信息获取
        
        db.commit()
        db.refresh(plan)
        
        logger.info(f"Plan reviewed: {plan_id} - {'approved' if approved else 'rejected'}")
        
        return {
            'success': True,
            'data': {
                'id': plan.id,
                'status': plan.status.value,
                'reviewer': plan.reviewer,
                'reviewed_at': plan.reviewed_at.isoformat(),
                'review_comment': plan.review_comment,
                'rejection_reason': plan.rejection_reason,
            },
            'message': message,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to review plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 计划执行进度接口
# ============================================================================

@router.get('/{plan_id}/progress', response_model=dict)
def get_plan_progress(plan_id: str, db: Session = Depends(get_db)):
    """
    获取计划执行进度
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    steps = plan.steps or []
    total_steps = len(steps)
    
    if total_steps == 0:
        return {
            'success': True,
            'data': {
                'plan_id': plan_id,
                'task_id': plan.task_id,
                'total_steps': 0,
                'completed_steps': 0,
                'progress_percentage': 0,
                'estimated_remaining_hours': float(plan.estimated_total_hours) if plan.estimated_total_hours else 0,
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    # 计算已完成步骤数
    completed_steps = sum(1 for step in steps if step.get('status') == 'completed')
    
    # 计算进度百分比
    progress_percentage = round((completed_steps / total_steps) * 100, 2)
    
    # 找到当前步骤
    current_step_index = None
    next_step_name = None
    for i, step in enumerate(steps):
        if step.get('status') in ['pending', 'in_progress']:
            current_step_index = i
            next_step_name = step.get('name')
            break
    
    # 计算剩余工时
    remaining_hours = sum(
        step.get('estimatedHours', 0) for i, step in enumerate(steps)
        if step.get('status') not in ['completed', 'skipped']
    )
    
    return {
        'success': True,
        'data': {
            'plan_id': plan_id,
            'task_id': plan.task_id,
            'total_steps': total_steps,
            'completed_steps': completed_steps,
            'progress_percentage': progress_percentage,
            'current_step_index': current_step_index,
            'next_step_name': next_step_name,
            'estimated_remaining_hours': remaining_hours,
        },
        'timestamp': datetime.utcnow().isoformat()
    }


@router.post('/{plan_id}/steps/{step_index}/execute', response_model=dict)
def execute_plan_step(
    plan_id: str,
    step_index: int,
    status: str,
    output: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    执行计划步骤
    
    - **plan_id**: 计划 ID
    - **step_index**: 步骤索引
    - **status**: 步骤状态 (completed/in_progress/blocked/skipped)
    - **output**: 产出物描述
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    steps = plan.steps or []
    
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=404, detail=f"Step index out of range: {step_index}")
    
    try:
        # 验证步骤状态转换
        try:
            new_status = PlanStepStatusEnum(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid step status: {status}")
        
        # 更新步骤
        step = steps[step_index]
        step['status'] = new_status.value
        
        if new_status == PlanStepStatusEnum.IN_PROGRESS:
            step['started_at'] = datetime.utcnow().isoformat()
        elif new_status == PlanStepStatusEnum.COMPLETED:
            step['completed_at'] = datetime.utcnow().isoformat()
        
        if output:
            step['output'] = output
        
        plan.steps = steps
        db.commit()
        db.refresh(plan)
        
        logger.info(f"Step {step_index} executed: {plan_id} - {new_status.value}")
        
        return {
            'success': True,
            'data': {
                'plan_id': plan_id,
                'step_index': step_index,
                'step_name': step.get('name'),
                'status': new_status.value,
                'completed_at': step.get('completed_at'),
                'output': output,
            },
            'message': '步骤执行完成',
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to execute step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 任务 - 计划关系接口
# ============================================================================

@router.get('/{plan_id}/relation', response_model=dict)
def get_plan_relation(plan_id: str, db: Session = Depends(get_db)):
    """
    获取计划与任务的关系摘要
    """
    plan = db.query(DevelopmentPlan).filter(DevelopmentPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    
    task = db.query(Task).filter(Task.id == plan.task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {plan.task_id}")
    
    # 获取任务的所有计划统计
    total_plans = db.query(DevelopmentPlan).filter(
        DevelopmentPlan.task_id == plan.task_id
    ).count()
    
    approved_plans = db.query(DevelopmentPlan).filter(
        DevelopmentPlan.task_id == plan.task_id,
        DevelopmentPlan.status == PlanStatusEnum.APPROVED
    ).count()
    
    return {
        'success': True,
        'data': {
            'plan_id': plan_id,
            'plan_title': plan.title,
            'plan_version': plan.version,
            'plan_status': plan.status.value,
            'task_id': task.id,
            'task_title': task.title,
            'task_status': task.status.value,
            'is_active': task.active_plan_id == plan_id,
            'total_plans': total_plans,
            'approved_plans': approved_plans,
        },
        'timestamp': datetime.utcnow().isoformat()
    }
