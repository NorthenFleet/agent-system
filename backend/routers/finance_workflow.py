"""
财务报销业务流 API

提供完整的报销单管理、审批流程功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
from datetime import datetime
import uuid

from database import get_db
from workflow.models import (
    Reimbursement, ReimbursementItem, ReimbursementStatus, ReimbursementCategory,
    WorkflowDefinition, WorkflowInstance, WorkflowStatus, InstanceStatus,
    ApprovalRecord, NodeExecution, ApprovalAction
)
from workflow.engine import WorkflowEngine
from pydantic import BaseModel, Field

router = APIRouter(prefix="/finance/workflow", tags=["财务业务流"])


# ==================== Pydantic Schemas ====================

class ReceiptItem(BaseModel):
    name: str
    url: Optional[str] = None
    amount: float
    date: Optional[str] = None


class ReimbursementCreate(BaseModel):
    title: str = Field(..., description="报销标题")
    amount: float = Field(..., gt=0, description="报销金额")
    category: str = Field(..., description="报销类别")
    description: Optional[str] = Field(None, description="报销说明")
    receipts: Optional[List[ReceiptItem]] = Field(default_factory=list, description="发票列表")
    department: Optional[str] = Field(None, description="所属部门")


class ReimbursementUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    receipts: Optional[List[ReceiptItem]] = None


class ApprovalRequest(BaseModel):
    action: str = Field(..., description="审批动作: approve/reject/return")
    comment: Optional[str] = Field(None, description="审批意见")


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    business_type: str = "reimbursement"
    nodes: list
    form_schema: Optional[dict] = None


# ==================== 报销单 API ====================

@router.get("/reimbursements", summary="获取报销单列表")
async def list_reimbursements(
    status: Optional[str] = Query(None, description="状态筛选"),
    category: Optional[str] = Query(None, description="类别筛选"),
    applicant_id: Optional[int] = Query(None, description="申请人ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取报销单列表"""
    query = db.query(Reimbursement)
    
    if status:
        query = query.filter(Reimbursement.status == status)
    if category:
        query = query.filter(Reimbursement.category == category)
    if applicant_id:
        query = query.filter(Reimbursement.applicant_id == applicant_id)
    
    total = query.count()
    items = query.order_by(desc(Reimbursement.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "code": r.code,
                "title": r.title,
                "amount": r.amount,
                "category": r.category,
                "status": r.status,
                "applicant_id": r.applicant_id,
                "applicant_name": r.applicant_name,
                "department": r.department,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            }
            for r in items
        ]
    }


@router.post("/reimbursements", summary="创建报销单")
async def create_reimbursement(
    data: ReimbursementCreate,
    applicant_id: int = Query(..., description="申请人ID"),
    db: Session = Depends(get_db)
):
    """创建报销单（草稿状态）"""
    # 生成报销单号
    code = f"RB{datetime.utcnow().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
    
    reimbursement = Reimbursement(
        code=code,
        applicant_id=applicant_id,
        title=data.title,
        amount=data.amount,
        category=data.category,
        description=data.description,
        receipts=[r.dict() for r in data.receipts] if data.receipts else [],
        department=data.department,
        status=ReimbursementStatus.DRAFT.value
    )
    
    db.add(reimbursement)
    db.commit()
    db.refresh(reimbursement)
    
    return {
        "id": reimbursement.id,
        "code": reimbursement.code,
        "message": "报销单创建成功"
    }


@router.get("/reimbursements/{reimbursement_id}", summary="获取报销单详情")
async def get_reimbursement(
    reimbursement_id: str,
    db: Session = Depends(get_db)
):
    """获取报销单详情"""
    reimbursement = db.query(Reimbursement).filter_by(id=reimbursement_id).first()
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    
    # 获取审批记录
    workflow_instance = reimbursement.workflow_instance
    approval_records = []
    if workflow_instance:
        approval_records = [
            {
                "step": r.step,
                "approver_id": r.approver_id,
                "approver_name": r.approver_name,
                "action": r.action,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in workflow_instance.approval_records
        ]
    
    return {
        "id": reimbursement.id,
        "code": reimbursement.code,
        "title": reimbursement.title,
        "amount": reimbursement.amount,
        "category": reimbursement.category,
        "description": reimbursement.description,
        "receipts": reimbursement.receipts,
        "status": reimbursement.status,
        "applicant_id": reimbursement.applicant_id,
        "applicant_name": reimbursement.applicant_name,
        "department": reimbursement.department,
        "workflow_instance_id": reimbursement.workflow_instance_id,
        "workflow_status": workflow_instance.status if workflow_instance else None,
        "current_node": workflow_instance.current_node_id if workflow_instance else None,
        "approval_records": approval_records,
        "created_at": reimbursement.created_at.isoformat() if reimbursement.created_at else None,
        "submitted_at": reimbursement.submitted_at.isoformat() if reimbursement.submitted_at else None,
        "approved_at": reimbursement.approved_at.isoformat() if reimbursement.approved_at else None,
    }


@router.put("/reimbursements/{reimbursement_id}", summary="更新报销单")
async def update_reimbursement(
    reimbursement_id: str,
    data: ReimbursementUpdate,
    db: Session = Depends(get_db)
):
    """更新报销单（仅草稿状态可更新）"""
    reimbursement = db.query(Reimbursement).filter_by(id=reimbursement_id).first()
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    
    if reimbursement.status != ReimbursementStatus.DRAFT.value:
        raise HTTPException(status_code=400, detail="仅草稿状态可编辑")
    
    if data.title is not None:
        reimbursement.title = data.title
    if data.amount is not None:
        reimbursement.amount = data.amount
    if data.category is not None:
        reimbursement.category = data.category
    if data.description is not None:
        reimbursement.description = data.description
    if data.receipts is not None:
        reimbursement.receipts = [r.dict() for r in data.receipts]
    
    db.commit()
    
    return {"message": "报销单更新成功"}


@router.post("/reimbursements/{reimbursement_id}/submit", summary="提交报销单")
async def submit_reimbursement(
    reimbursement_id: str,
    db: Session = Depends(get_db)
):
    """提交报销单，启动审批流程"""
    reimbursement = db.query(Reimbursement).filter_by(id=reimbursement_id).first()
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    
    if reimbursement.status != ReimbursementStatus.DRAFT.value:
        raise HTTPException(status_code=400, detail="仅草稿状态可提交")
    
    # 查找默认财务报销流程
    workflow_def = db.query(WorkflowDefinition).filter_by(
        business_type="reimbursement",
        status=WorkflowStatus.ACTIVE.value
    ).first()
    
    if not workflow_def:
        raise HTTPException(status_code=400, detail="未配置财务报销流程")
    
    # 创建流程实例
    engine = WorkflowEngine(db)
    instance = engine.start_workflow(
        definition_id=workflow_def.id,
        business_type="reimbursement",
        business_id=reimbursement.id,
        context={
            "amount": reimbursement.amount,
            "category": reimbursement.category,
            "applicant_id": reimbursement.applicant_id
        }
    )
    
    # 更新报销单状态
    reimbursement.status = ReimbursementStatus.SUBMITTED.value
    reimbursement.workflow_instance_id = instance.id
    reimbursement.submitted_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "报销单已提交",
        "workflow_instance_id": instance.id,
        "current_node": instance.current_node_id
    }


@router.post("/reimbursements/{reimbursement_id}/approve", summary="审批报销单")
async def approve_reimbursement(
    reimbursement_id: str,
    data: ApprovalRequest,
    approver_id: int = Query(..., description="审批人ID"),
    approver_name: str = Query(..., description="审批人姓名"),
    db: Session = Depends(get_db)
):
    """审批报销单"""
    reimbursement = db.query(Reimbursement).filter_by(id=reimbursement_id).first()
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    
    if not reimbursement.workflow_instance_id:
        raise HTTPException(status_code=400, detail="报销单未启动审批流程")
    
    # 执行审批
    engine = WorkflowEngine(db)
    instance = engine.complete_task(
        instance_id=reimbursement.workflow_instance_id,
        approver_id=approver_id,
        approver_name=approver_name,
        action=data.action,
        comment=data.comment
    )
    
    # 更新报销单状态
    if instance.status == InstanceStatus.COMPLETED.value:
        reimbursement.status = ReimbursementStatus.APPROVED.value
        reimbursement.approved_at = datetime.utcnow()
    elif instance.status == InstanceStatus.REJECTED.value:
        reimbursement.status = ReimbursementStatus.REJECTED.value
    else:
        reimbursement.status = ReimbursementStatus.IN_REVIEW.value
    
    db.commit()
    
    return {
        "message": "审批完成",
        "workflow_status": instance.status,
        "reimbursement_status": reimbursement.status
    }


@router.delete("/reimbursements/{reimbursement_id}", summary="删除报销单")
async def delete_reimbursement(
    reimbursement_id: str,
    db: Session = Depends(get_db)
):
    """删除报销单（仅草稿状态可删除）"""
    reimbursement = db.query(Reimbursement).filter_by(id=reimbursement_id).first()
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    
    if reimbursement.status != ReimbursementStatus.DRAFT.value:
        raise HTTPException(status_code=400, detail="仅草稿状态可删除")
    
    db.delete(reimbursement)
    db.commit()
    
    return {"message": "报销单已删除"}


# ==================== 审批任务 API ====================

@router.get("/approvals/pending", summary="获取待审批列表")
async def list_pending_approvals(
    approver_id: int = Query(..., description="审批人ID"),
    db: Session = Depends(get_db)
):
    """获取指定审批人的待审批任务"""
    # 查找当前节点需要该审批人处理的实例
    instances = db.query(WorkflowInstance).filter(
        WorkflowInstance.status.in_([InstanceStatus.RUNNING.value, InstanceStatus.WAITING.value])
    ).all()
    
    pending_tasks = []
    for instance in instances:
        # 检查当前节点是否需要该审批人
        current_node = instance.definition.nodes[instance.current_node_id] if instance.current_node_id else None
        if current_node and current_node.get("assignee_id") == approver_id:
            reimbursement = db.query(Reimbursement).filter_by(id=instance.business_id).first()
            if reimbursement:
                pending_tasks.append({
                    "instance_id": instance.id,
                    "reimbursement_id": reimbursement.id,
                    "reimbursement_code": reimbursement.code,
                    "title": reimbursement.title,
                    "amount": reimbursement.amount,
                    "applicant_name": reimbursement.applicant_name,
                    "submitted_at": reimbursement.submitted_at.isoformat() if reimbursement.submitted_at else None
                })
    
    return {"items": pending_tasks, "total": len(pending_tasks)}


# ==================== 流程定义 API ====================

@router.get("/definitions", summary="获取流程定义列表")
async def list_workflow_definitions(
    business_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取流程定义列表"""
    query = db.query(WorkflowDefinition)
    if business_type:
        query = query.filter_by(business_type=business_type)
    
    definitions = query.all()
    
    return {
        "items": [
            {
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "business_type": d.business_type,
                "version": d.version,
                "status": d.status,
                "nodes_count": len(d.nodes) if d.nodes else 0,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in definitions
        ]
    }


@router.post("/definitions", summary="创建流程定义")
async def create_workflow_definition(
    data: WorkflowCreate,
    db: Session = Depends(get_db)
):
    """创建新的流程定义"""
    definition = WorkflowDefinition(
        name=data.name,
        description=data.description,
        business_type=data.business_type,
        nodes=data.nodes,
        form_schema=data.form_schema,
        status=WorkflowStatus.ACTIVE.value
    )
    
    db.add(definition)
    db.commit()
    db.refresh(definition)
    
    return {
        "id": definition.id,
        "message": "流程定义创建成功"
    }


@router.get("/definitions/{definition_id}", summary="获取流程定义详情")
async def get_workflow_definition(
    definition_id: str,
    db: Session = Depends(get_db)
):
    """获取流程定义详情"""
    definition = db.query(WorkflowDefinition).filter_by(id=definition_id).first()
    if not definition:
        raise HTTPException(status_code=404, detail="流程定义不存在")
    
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "business_type": definition.business_type,
        "version": definition.version,
        "nodes": definition.nodes,
        "form_schema": definition.form_schema,
        "status": definition.status,
        "created_at": definition.created_at.isoformat() if definition.created_at else None
    }


# ==================== 统计 API ====================

@router.get("/statistics", summary="获取财务统计")
async def get_finance_statistics(
    db: Session = Depends(get_db)
):
    """获取财务统计数据"""
    total_reimbursements = db.query(Reimbursement).count()
    pending_count = db.query(Reimbursement).filter(
        Reimbursement.status.in_([ReimbursementStatus.SUBMITTED.value, ReimbursementStatus.IN_REVIEW.value])
    ).count()
    approved_count = db.query(Reimbursement).filter_by(status=ReimbursementStatus.APPROVED.value).count()
    rejected_count = db.query(Reimbursement).filter_by(status=ReimbursementStatus.REJECTED.value).count()
    
    # 计算总金额
    from sqlalchemy import func
    total_amount = db.query(func.sum(Reimbursement.amount)).scalar() or 0
    approved_amount = db.query(func.sum(Reimbursement.amount)).filter(
        Reimbursement.status == ReimbursementStatus.APPROVED.value
    ).scalar() or 0
    
    return {
        "total_reimbursements": total_reimbursements,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "total_amount": total_amount,
        "approved_amount": approved_amount
    }
