"""
业务流模型定义

支持通用业务流编排，财务报销作为第一个使用场景
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, JSON, Float, ForeignKey, Enum as SQLAEnum, Boolean
from sqlalchemy.orm import relationship
from database import Base
import uuid
import enum
from datetime import datetime


# ==================== 枚举定义 ====================

class WorkflowStatus(str, enum.Enum):
    """业务流状态"""
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 启用
    ARCHIVED = "archived"     # 归档


class InstanceStatus(str, enum.Enum):
    """实例运行状态"""
    RUNNING = "running"       # 运行中
    WAITING = "waiting"       # 等待审批
    COMPLETED = "completed"   # 已完成
    REJECTED = "rejected"     # 已拒绝
    CANCELLED = "cancelled"   # 已取消
    FAILED = "failed"         # 失败


class NodeType(str, enum.Enum):
    """节点类型"""
    START = "start"           # 开始
    APPROVAL = "approval"     # 审批
    CONDITION = "condition"   # 条件分支
    PARALLEL = "parallel"     # 并行审批
    NOTIFY = "notify"         # 通知
    END = "end"               # 结束


class ApprovalAction(str, enum.Enum):
    """审批动作"""
    APPROVE = "approve"       # 通过
    REJECT = "reject"         # 拒绝
    RETURN = "return"         # 退回
    TRANSFER = "transfer"     # 转交


class ReimbursementStatus(str, enum.Enum):
    """报销单状态"""
    DRAFT = "draft"           # 草稿
    SUBMITTED = "submitted"   # 已提交
    IN_REVIEW = "in_review"   # 审批中
    APPROVED = "approved"     # 已通过
    REJECTED = "rejected"     # 已拒绝
    PAID = "paid"             # 已付款
    ARCHIVED = "archived"     # 已归档


class ReimbursementCategory(str, enum.Enum):
    """报销类别"""
    TRAVEL = "travel"         # 差旅
    OFFICE = "office"         # 办公用品
    MEAL = "meal"             # 餐饮
    TRANSPORT = "transport"   # 交通
    TRAINING = "training"     # 培训
    OTHER = "other"           # 其他


# ==================== 业务流定义 ====================

class WorkflowDefinition(Base):
    """业务流定义"""
    __tablename__ = "workflow_definitions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, comment="流程名称")
    description = Column(Text, comment="流程描述")
    business_type = Column(String, nullable=False, comment="业务类型: reimbursement, purchase, etc.")
    version = Column(String, default="1.0", comment="版本号")
    
    # 流程节点定义 (JSON)
    # [
    #   {"id": "start", "type": "start", "next": "manager_approval"},
    #   {"id": "manager_approval", "type": "approval", "assignee_role": "manager", "next": "amount_check"},
    #   {"id": "amount_check", "type": "condition", "conditions": [
    #     {"expr": "amount > 5000", "next": "director_approval"},
    #     {"expr": "amount <= 5000", "next": "finance_confirm"}
    #   ]},
    #   ...
    # ]
    nodes = Column(JSON, nullable=False, comment="流程节点定义")
    
    # 表单字段定义
    form_schema = Column(JSON, comment="表单字段定义")
    
    status = Column(String, default=WorkflowStatus.ACTIVE.value)
    is_active = Column(Boolean, default=True)
    
    created_by = Column(Integer, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    instances = relationship("WorkflowInstance", back_populates="definition")


# ==================== 业务流实例 ====================

class WorkflowInstance(Base):
    """业务流实例"""
    __tablename__ = "workflow_instances"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    definition_id = Column(String, ForeignKey("workflow_definitions.id"))
    
    business_type = Column(String, nullable=False, comment="业务类型")
    business_id = Column(String, nullable=False, comment="关联业务ID")
    
    current_node_id = Column(String, comment="当前节点ID")
    status = Column(String, default=InstanceStatus.RUNNING.value)
    
    # 流程上下文数据
    context = Column(JSON, default=dict, comment="流程上下文数据")
    
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    definition = relationship("WorkflowDefinition", back_populates="instances")
    node_executions = relationship("NodeExecution", back_populates="instance", order_by="NodeExecution.started_at")
    approval_records = relationship("ApprovalRecord", back_populates="instance", order_by="ApprovalRecord.created_at")


# ==================== 节点执行记录 ====================

class NodeExecution(Base):
    """节点执行记录"""
    __tablename__ = "node_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id = Column(String, ForeignKey("workflow_instances.id"))
    
    node_id = Column(String, nullable=False, comment="节点ID")
    node_type = Column(String, nullable=False, comment="节点类型")
    node_name = Column(String, comment="节点名称")
    
    status = Column(String, default="pending")  # pending, running, waiting, completed, rejected, skipped
    assignee_role = Column(String, comment="处理角色")
    assignee_id = Column(Integer, comment="处理人ID")
    
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    result = Column(JSON, comment="执行结果")
    error_message = Column(Text, comment="错误信息")

    instance = relationship("WorkflowInstance", back_populates="node_executions")


# ==================== 审批记录 ====================

class ApprovalRecord(Base):
    """审批记录"""
    __tablename__ = "approval_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id = Column(String, ForeignKey("workflow_instances.id"))
    node_execution_id = Column(String, ForeignKey("node_executions.id"))
    
    step = Column(Integer, nullable=False, comment="步骤序号")
    approver_id = Column(Integer, nullable=False, comment="审批人ID")
    approver_name = Column(String, comment="审批人姓名")
    
    action = Column(String, nullable=False, comment="审批动作: approve/reject/return/transfer")
    comment = Column(Text, comment="审批意见")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    instance = relationship("WorkflowInstance", back_populates="approval_records")


# ==================== 财务报销模型 ====================

class Reimbursement(Base):
    """报销单（业务流引擎自有表；生产财务域的 reimbursements 由 models/finance_models.py 定义，两者互不冲突）"""
    __tablename__ = "wf_reimbursements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, unique=True, comment="报销单号")
    
    # 申请人信息
    applicant_id = Column(Integer, nullable=False, comment="申请人ID")
    applicant_name = Column(String, comment="申请人姓名")
    department = Column(String, comment="所属部门")
    
    # 报销信息
    amount = Column(Float, nullable=False, comment="报销金额")
    category = Column(String, nullable=False, comment="报销类别")
    title = Column(String, nullable=False, comment="报销标题")
    description = Column(Text, comment="报销说明")
    
    # 发票/附件
    receipts = Column(JSON, comment="发票列表 [{name, url, amount, date}]")
    attachments = Column(JSON, comment="附件列表")
    
    # 状态
    status = Column(String, default=ReimbursementStatus.DRAFT.value)
    workflow_instance_id = Column(String, ForeignKey("workflow_instances.id"))
    
    # 时间
    submitted_at = Column(DateTime, comment="提交时间")
    approved_at = Column(DateTime, comment="审批通过时间")
    paid_at = Column(DateTime, comment="付款时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflow_instance = relationship("WorkflowInstance")


class ReimbursementItem(Base):
    """报销明细"""
    __tablename__ = "wf_reimbursement_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reimbursement_id = Column(String, ForeignKey("reimbursements.id"))
    
    item_date = Column(DateTime, comment="消费日期")
    category = Column(String, comment="明细类别")
    description = Column(String, comment="明细说明")
    amount = Column(Float, nullable=False, comment="金额")
    receipt_name = Column(String, comment="发票名称")
    receipt_url = Column(String, comment="发票URL")

    reimbursement = relationship("workflow.models.Reimbursement", backref="items")
