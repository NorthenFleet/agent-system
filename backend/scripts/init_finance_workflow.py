"""
初始化财务报销业务流

创建默认的业务流定义
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from workflow.models import WorkflowDefinition, WorkflowStatus

def init_default_workflow():
    """初始化默认财务报销流程"""
    db = SessionLocal()
    
    try:
        # 检查是否已存在
        existing = db.query(WorkflowDefinition).filter_by(business_type="reimbursement").first()
        if existing:
            print(f"已存在财务报销流程定义: {existing.id}")
            return
        
        # 创建默认流程
        # 流程节点定义
        nodes = [
            {
                "id": "start",
                "type": "start",
                "name": "开始",
                "next": "manager_approval"
            },
            {
                "id": "manager_approval",
                "type": "approval",
                "name": "部门经理审批",
                "assignee_role": "manager",
                "next": "amount_check"
            },
            {
                "id": "amount_check",
                "type": "condition",
                "name": "金额判断",
                "conditions": [
                    {"expr": "amount > 5000", "next": "director_approval"},
                    {"expr": "amount <= 5000", "next": "finance_confirm"}
                ]
            },
            {
                "id": "director_approval",
                "type": "approval",
                "name": "总监审批",
                "assignee_role": "director",
                "next": "finance_confirm"
            },
            {
                "id": "finance_confirm",
                "type": "approval",
                "name": "财务确认",
                "assignee_role": "finance",
                "next": "end"
            },
            {
                "id": "end",
                "type": "end",
                "name": "结束"
            }
        ]
        
        # 表单字段定义
        form_schema = {
            "fields": [
                {"name": "title", "label": "报销标题", "type": "text", "required": True},
                {"name": "amount", "label": "报销金额", "type": "number", "required": True},
                {"name": "category", "label": "报销类别", "type": "select", "required": True, 
                 "options": ["travel", "office", "meal", "transport", "training", "other"]},
                {"name": "description", "label": "报销说明", "type": "textarea", "required": False},
                {"name": "receipts", "label": "发票附件", "type": "file", "required": False}
            ]
        }
        
        workflow = WorkflowDefinition(
            name="标准财务报销流程",
            description="适用于一般报销场景，金额超过5000需总监审批",
            business_type="reimbursement",
            version="1.0",
            nodes=nodes,
            form_schema=form_schema,
            status=WorkflowStatus.ACTIVE.value,
            is_active=True
        )
        
        db.add(workflow)
        db.commit()
        
        print(f"✅ 默认财务报销流程已创建: {workflow.id}")
        print(f"   流程节点: {len(nodes)} 个")
        print(f"   流程说明: 部门经理 → 金额判断 → (大额:总监审批) → 财务确认")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_default_workflow()
