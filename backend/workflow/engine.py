"""
通用业务流引擎

支持：
- 多级审批
- 条件分支
- 并行审批
- 状态回调
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from sqlalchemy.orm import Session
from .models import WorkflowDefinition, WorkflowInstance, ApprovalRecord, NodeExecution


class WorkflowEngine:
    """业务流执行引擎"""
    
    def __init__(self, db: Session):
        self.db = db
        self._handlers: Dict[str, Callable] = {}
    
    def register_handler(self, node_type: str, handler: Callable):
        """注册节点类型处理器"""
        self._handlers[node_type] = handler
    
    def start_workflow(self, definition_id: str, business_type: str, business_id: str, context: Dict = None) -> WorkflowInstance:
        """启动业务流实例"""
        definition = self.db.query(WorkflowDefinition).filter_by(id=definition_id).first()
        if not definition:
            raise ValueError(f"Workflow definition not found: {definition_id}")
        
        instance = WorkflowInstance(
            definition_id=definition_id,
            business_type=business_type,
            business_id=business_id,
            current_step=1,
            status="running",
            context=context or {}
        )
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        
        # 执行第一个节点
        self._execute_current_node(instance)
        
        return instance
    
    def _execute_current_node(self, instance: WorkflowInstance):
        """执行当前节点"""
        definition = instance.definition
        steps = definition.steps
        
        if instance.current_step > len(steps):
            instance.status = "completed"
            instance.completed_at = datetime.utcnow()
            self.db.commit()
            return
        
        current_step = steps[instance.current_step - 1]
        node_type = current_step.get("type", "approval")
        
        # 记录节点执行
        execution = NodeExecution(
            instance_id=instance.id,
            node_id=f"step_{instance.current_step}",
            node_type=node_type,
            status="running"
        )
        self.db.add(execution)
        self.db.commit()
        
        # 调用对应处理器
        handler = self._handlers.get(node_type, self._default_handler)
        handler(instance, current_step, execution)
    
    def _default_handler(self, instance: WorkflowInstance, step: Dict, execution: NodeExecution):
        """默认处理器（审批节点）"""
        execution.status = "waiting"
        execution.assignee_role = step.get("approver_role")
        self.db.commit()
    
    def complete_task(self, instance_id: str, approver_id: int, action: str, comment: str = None) -> WorkflowInstance:
        """完成当前任务节点"""
        instance = self.db.query(WorkflowInstance).filter_by(id=instance_id).first()
        if not instance:
            raise ValueError(f"Workflow instance not found: {instance_id}")
        
        if instance.status != "running":
            raise ValueError(f"Workflow is not running: {instance.status}")
        
        # 记录审批
        record = ApprovalRecord(
            instance_id=instance_id,
            step=instance.current_step,
            approver_id=approver_id,
            action=action,
            comment=comment
        )
        self.db.add(record)
        
        # 更新节点执行状态
        execution = self.db.query(NodeExecution).filter_by(
            instance_id=instance_id,
            status="waiting"
        ).order_by(NodeExecution.started_at.desc()).first()
        
        if execution:
            execution.status = "completed" if action == "approve" else "rejected"
            execution.completed_at = datetime.utcnow()
        
        # 根据动作决定下一步
        if action == "approve":
            instance.current_step += 1
            self.db.commit()
            self._execute_current_node(instance)
        elif action == "reject":
            instance.status = "rejected"
            instance.completed_at = datetime.utcnow()
            self.db.commit()
        elif action == "return":
            # 退回到上一步
            if instance.current_step > 1:
                instance.current_step -= 1
            self.db.commit()
            self._execute_current_node(instance)
        else:
            self.db.commit()
        
        return instance
    
    def get_instance_status(self, instance_id: str) -> Dict[str, Any]:
        """获取实例状态"""
        instance = self.db.query(WorkflowInstance).filter_by(id=instance_id).first()
        if not instance:
            return None
        
        return {
            "id": instance.id,
            "status": instance.status,
            "current_step": instance.current_step,
            "total_steps": len(instance.definition.steps),
            "created_at": instance.created_at.isoformat() if instance.created_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "approval_records": [
                {
                    "step": r.step,
                    "approver_id": r.approver_id,
                    "action": r.action,
                    "comment": r.comment,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in instance.approval_records
            ]
        }
