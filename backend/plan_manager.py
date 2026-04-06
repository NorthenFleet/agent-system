# -*- coding: utf-8 -*-
"""
任务计划管理 - 李奥纳多自动制定计划，擎天柱审核
"""
from datetime import datetime
from typing import List, Dict, Optional
import json

class PlanManager:
    """计划管理器"""
    
    def __init__(self):
        self.plans_file = "data/task_plans.json"
        self.plans = self._load_plans()
    
    def _load_plans(self) -> Dict:
        """加载计划"""
        try:
            with open(self.plans_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_plans(self):
        """保存计划"""
        with open(self.plans_file, 'w', encoding='utf-8') as f:
            json.dump(self.plans, f, ensure_ascii=False, indent=2)
    
    def create_plan(self, task_id: str, plan_data: Dict, creator: str = "李奥纳多") -> Dict:
        """创建任务计划"""
        plan = {
            "id": f"plan_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "task_id": task_id,
            "creator": creator,
            "created_at": datetime.now().isoformat(),
            "status": "pending_review",  # pending_review, approved, rejected
            "reviewer": None,
            "reviewed_at": None,
            "review_comment": None,
            **plan_data
        }
        
        self.plans[plan["id"]] = plan
        self._save_plans()
        
        print(f"[Plan] 创建计划：{plan['id']} for task {task_id}")
        return plan
    
    def review_plan(self, plan_id: str, approved: bool, reviewer: str = "擎天柱", comment: str = "") -> bool:
        """审核计划"""
        if plan_id not in self.plans:
            return False
        
        plan = self.plans[plan_id]
        plan["status"] = "approved" if approved else "rejected"
        plan["reviewer"] = reviewer
        plan["reviewed_at"] = datetime.now().isoformat()
        plan["review_comment"] = comment
        
        self._save_plans()
        
        print(f"[Plan] 审核计划：{plan_id} - {'通过' if approved else '拒绝'} by {reviewer}")
        return True
    
    def get_plan_by_task(self, task_id: str) -> Optional[Dict]:
        """获取任务的计划"""
        for plan in self.plans.values():
            if plan["task_id"] == task_id:
                return plan
        return None
    
    def get_pending_plans(self) -> List[Dict]:
        """获取待审核计划"""
        return [p for p in self.plans.values() if p["status"] == "pending_review"]
    
    def get_approved_plans(self) -> List[Dict]:
        """获取已通过计划"""
        return [p for p in self.plans.values() if p["status"] == "approved"]
    
    def execute_plan_step(self, plan_id: str, step_index: int) -> Dict:
        """执行计划步骤"""
        if plan_id not in self.plans:
            return {"error": "计划不存在"}
        
        plan = self.plans[plan_id]
        if plan["status"] != "approved":
            return {"error": "计划未通过审核"}
        
        steps = plan.get("steps", [])
        if step_index >= len(steps):
            return {"error": "步骤索引超出范围"}
        
        step = steps[step_index]
        step["status"] = "completed"
        step["completed_at"] = datetime.now().isoformat()
        
        self._save_plans()
        
        return {"success": True, "step": step}
    
    def generate_plan_template(self, task: Dict) -> Dict:
        """李奥纳多生成计划模板"""
        assignee = task.get("assignee", "")
        task_type = self._detect_task_type(task)
        
        # 根据任务类型生成不同的计划模板
        if task_type == "frontend":
            return self._generate_frontend_plan(task)
        elif task_type == "backend":
            return self._generate_backend_plan(task)
        elif task_type == "testing":
            return self._generate_testing_plan(task)
        else:
            return self._generate_general_plan(task)
    
    def _detect_task_type(self, task: Dict) -> str:
        """检测任务类型"""
        title = task.get("title", "").lower()
        desc = task.get("description", "").lower()
        assignee = task.get("assignee", "")
        
        if "前端" in title or "frontend" in title or assignee == "多纳泰罗":
            return "frontend"
        elif "后端" in title or "backend" in title or assignee == "拉斐尔":
            return "backend"
        elif "测试" in title or "test" in title or assignee == "米开朗基罗":
            return "testing"
        else:
            return "general"
    
    def _generate_frontend_plan(self, task: Dict) -> Dict:
        """生成前端开发计划"""
        return {
            "type": "frontend",
            "estimated_hours": 8,
            "steps": [
                {
                    "index": 0,
                    "name": "需求分析",
                    "description": "分析任务需求，确定功能点",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "多纳泰罗"
                },
                {
                    "index": 1,
                    "name": "组件设计",
                    "description": "设计 Vue 组件结构和状态管理",
                    "estimated_hours": 2,
                    "status": "pending",
                    "executor": "多纳泰罗"
                },
                {
                    "index": 2,
                    "name": "页面开发",
                    "description": "实现页面布局和交互逻辑",
                    "estimated_hours": 3,
                    "status": "pending",
                    "executor": "多纳泰罗"
                },
                {
                    "index": 3,
                    "name": "API 对接",
                    "description": "对接后端 API，实现数据交互",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "多纳泰罗"
                },
                {
                    "index": 4,
                    "name": "自测",
                    "description": "功能自测和 bug 修复",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "多纳泰罗"
                }
            ],
            "resources": [
                {"name": "Vue 3 文档", "url": "https://vuejs.org/"},
                {"name": "Element Plus 文档", "url": "https://element-plus.org/"}
            ],
            "acceptance_criteria": [
                "页面功能完整",
                "UI 与设计一致",
                "API 对接正常",
                "无控制台错误"
            ]
        }
    
    def _generate_backend_plan(self, task: Dict) -> Dict:
        """生成后端开发计划"""
        return {
            "type": "backend",
            "estimated_hours": 6,
            "steps": [
                {
                    "index": 0,
                    "name": "需求分析",
                    "description": "分析 API 需求，确定接口规范",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "拉斐尔"
                },
                {
                    "index": 1,
                    "name": "数据模型设计",
                    "description": "设计数据结构和存储方案",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "拉斐尔"
                },
                {
                    "index": 2,
                    "name": "API 实现",
                    "description": "实现 FastAPI 接口",
                    "estimated_hours": 2,
                    "status": "pending",
                    "executor": "拉斐尔"
                },
                {
                    "index": 3,
                    "name": "单元测试",
                    "description": "编写和运行单元测试",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "拉斐尔"
                },
                {
                    "index": 4,
                    "name": "API 文档",
                    "description": "完善 Swagger 文档",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "拉斐尔"
                }
            ],
            "resources": [
                {"name": "FastAPI 文档", "url": "https://fastapi.tiangolo.com/"},
                {"name": "Pydantic 文档", "url": "https://docs.pydantic.dev/"}
            ],
            "acceptance_criteria": [
                "API 接口正常工作",
                "数据验证正确",
                "错误处理完善",
                "文档完整"
            ]
        }
    
    def _generate_testing_plan(self, task: Dict) -> Dict:
        """生成测试计划"""
        return {
            "type": "testing",
            "estimated_hours": 4,
            "steps": [
                {
                    "index": 0,
                    "name": "测试用例设计",
                    "description": "设计测试用例和场景",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "米开朗基罗"
                },
                {
                    "index": 1,
                    "name": "功能测试",
                    "description": "执行功能测试",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "米开朗基罗"
                },
                {
                    "index": 2,
                    "name": "回归测试",
                    "description": "执行回归测试",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "米开朗基罗"
                },
                {
                    "index": 3,
                    "name": "测试报告",
                    "description": "编写测试报告",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": "米开朗基罗"
                }
            ],
            "resources": [],
            "acceptance_criteria": [
                "所有测试用例通过",
                "无严重 bug",
                "性能达标"
            ]
        }
    
    def _generate_general_plan(self, task: Dict) -> Dict:
        """生成通用计划"""
        return {
            "type": "general",
            "estimated_hours": 4,
            "steps": [
                {
                    "index": 0,
                    "name": "需求确认",
                    "description": "确认任务需求和目标",
                    "estimated_hours": 0.5,
                    "status": "pending",
                    "executor": task.get("assignee", "")
                },
                {
                    "index": 1,
                    "name": "方案设计",
                    "description": "设计实现方案",
                    "estimated_hours": 1,
                    "status": "pending",
                    "executor": task.get("assignee", "")
                },
                {
                    "index": 2,
                    "name": "实现开发",
                    "description": "执行开发工作",
                    "estimated_hours": 2,
                    "status": "pending",
                    "executor": task.get("assignee", "")
                },
                {
                    "index": 3,
                    "name": "测试验证",
                    "description": "测试和验证结果",
                    "estimated_hours": 0.5,
                    "status": "pending",
                    "executor": task.get("assignee", "")
                }
            ],
            "resources": [],
            "acceptance_criteria": [
                "任务目标达成",
                "质量符合要求"
            ]
        }


# 全局实例
plan_manager = PlanManager()
