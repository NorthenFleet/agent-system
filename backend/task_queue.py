"""
任务队列管理 - 支持上下文的增强版任务系统
"""
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    """任务管理器 - 支持完整上下文"""
    
    def __init__(self):
        self.tasks: Dict[str, dict] = {}
        self.task_counter = 0
        self.task_logs: Dict[str, list] = {}  # 任务日志
    
    def create_task(self, title: str, assignee: str, priority: str = "normal", 
                    description: str = "", context: Optional[dict] = None) -> str:
        """创建新任务"""
        self.task_counter += 1
        task_id = f"{self.task_counter:03d}"
        
        # 默认上下文结构
        default_context = {
            "background": "",  # 任务背景
            "requirements": [],  # 需求列表
            "resources": [],  # 相关资源链接
            "acceptance_criteria": [],  # 验收标准
            "dependencies": [],  # 依赖任务
            "tech_stack": [],  # 技术栈
            "notes": ""  # 备注
        }
        
        if context:
            default_context.update(context)
        
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "assignee": assignee,
            "status": TaskStatus.PENDING.value,
            "priority": priority,
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": None,
            "context": default_context,
            "subtasks": [],  # 子任务列表
            "tags": []  # 标签
        }
        
        self.tasks[task_id] = task
        self.task_logs[task_id] = [{
            "timestamp": datetime.now().isoformat(),
            "action": "created",
            "content": f"任务创建：{title}"
        }]
        
        print(f"[Task] 创建任务：{task_id} - {title}")
        return task_id
    
    def update_task_status(self, task_id: str, status: str, progress: Optional[int] = None) -> bool:
        """更新任务状态"""
        if task_id not in self.tasks:
            print(f"[Task] 任务不存在：{task_id}")
            return False
        
        task = self.tasks[task_id]
        old_status = task["status"]
        task["status"] = status
        task["updated_at"] = datetime.now().isoformat()
        
        if progress is not None:
            task["progress"] = progress
        
        if status == TaskStatus.COMPLETED.value:
            task["completed_at"] = datetime.now().isoformat()
            task["progress"] = 100
        
        # 记录日志
        self._add_log(task_id, "status_change", f"状态变更：{old_status} → {status}")
        
        print(f"[Task] 更新任务：{task_id} - 状态={status}, 进度={progress}")
        return True
    
    def update_task_context(self, task_id: str, context_updates: dict) -> bool:
        """更新任务上下文"""
        if task_id not in self.tasks:
            print(f"[Task] 任务不存在：{task_id}")
            return False
        
        task = self.tasks[task_id]
        if "context" not in task:
            task["context"] = {}
        
        # 更新上下文字段
        for key, value in context_updates.items():
            task["context"][key] = value
        
        task["updated_at"] = datetime.now().isoformat()
        self._add_log(task_id, "context_update", f"上下文更新：{list(context_updates.keys())}")
        
        print(f"[Task] 更新上下文：{task_id}")
        return True
    
    def add_subtask(self, task_id: str, subtask_title: str, 
                    assignee: str = "", completed: bool = False) -> bool:
        """添加子任务"""
        if task_id not in self.tasks:
            print(f"[Task] 任务不存在：{task_id}")
            return False
        
        subtask = {
            "id": f"{task_id}-{len(self.tasks[task_id]['subtasks']) + 1}",
            "title": subtask_title,
            "assignee": assignee,
            "completed": completed,
            "created_at": datetime.now().isoformat()
        }
        
        self.tasks[task_id]["subtasks"].append(subtask)
        self.tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        self._add_log(task_id, "subtask_add", f"添加子任务：{subtask_title}")
        
        print(f"[Task] 添加子任务：{task_id} - {subtask_title}")
        return True
    
    def update_subtask(self, task_id: str, subtask_id: str, completed: bool) -> bool:
        """更新子任务状态"""
        if task_id not in self.tasks:
            return False
        
        for subtask in self.tasks[task_id]["subtasks"]:
            if subtask["id"] == subtask_id:
                subtask["completed"] = completed
                self._add_log(task_id, "subtask_update", 
                            f"子任务 {subtask_id} {'完成' if completed else '未完成'}")
                return True
        
        return False
    
    def add_task_log(self, task_id: str, content: str, action: str = "note") -> bool:
        """添加任务日志/备注"""
        if task_id not in self.tasks:
            return False
        
        self._add_log(task_id, action, content)
        return True
    
    def _add_log(self, task_id: str, action: str, content: str):
        """内部方法：添加日志"""
        if task_id not in self.task_logs:
            self.task_logs[task_id] = []
        
        self.task_logs[task_id].append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "content": content
        })
        
        # 限制日志数量
        if len(self.task_logs[task_id]) > 100:
            self.task_logs[task_id] = self.task_logs[task_id][-100:]
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务详情"""
        return self.tasks.get(task_id)
    
    def get_task_logs(self, task_id: str, limit: int = 50) -> list:
        """获取任务日志"""
        if task_id not in self.task_logs:
            return []
        return self.task_logs[task_id][-limit:]
    
    def get_all_tasks(self) -> List[dict]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_pending_tasks(self, assignee: str) -> List[dict]:
        """获取待处理任务"""
        return [
            task for task in self.tasks.values()
            if task["status"] == TaskStatus.PENDING.value and task["assignee"] == assignee
        ]
    
    def get_tasks_by_assignee(self, assignee: str) -> List[dict]:
        """获取某人的所有任务"""
        return [
            task for task in self.tasks.values()
            if task["assignee"] == assignee
        ]
    
    def get_stats(self) -> dict:
        """获取任务统计"""
        tasks = list(self.tasks.values())
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t["status"] == TaskStatus.PENDING.value),
            "in_progress": sum(1 for t in tasks if t["status"] == TaskStatus.IN_PROGRESS.value),
            "completed": sum(1 for t in tasks if t["status"] == TaskStatus.COMPLETED.value),
            "failed": sum(1 for t in tasks if t["status"] == TaskStatus.FAILED.value),
        }

# 全局任务管理器实例
task_manager = TaskManager()

# 初始化示例任务
def init_sample_tasks():
    """初始化示例任务 - 带完整上下文"""
    
    # 任务 1: 团队看板架构设计
    task_manager.create_task(
        title="团队看板架构设计",
        assignee="李奥纳多",
        priority="high",
        description="设计团队看板的系统架构",
        context={
            "background": "需要为汽车人和忍者神龟团队创建一个统一的状态看板，展示智能体状态、任务进度、设备信息等",
            "requirements": [
                "支持 10+ 智能体状态展示",
                "实时任务进度跟踪",
                "设备清单和状态监控",
                "团队架构可视化",
                "响应式设计，支持移动端"
            ],
            "resources": [
                {"name": "团队架构图", "url": "docs/architecture.md"},
                {"name": "API 设计文档", "url": "docs/api-design.md"}
            ],
            "acceptance_criteria": [
                "所有智能体状态正确显示",
                "任务数据实时同步 (<5s 延迟)",
                "页面加载时间 <2s",
                "移动端适配完成"
            ],
            "dependencies": [],
            "tech_stack": ["Vue 3", "FastAPI", "Element Plus", "ECharts"],
            "notes": "优先完成核心功能，图表可以后续优化"
        }
    )
    
    # 任务 2: 团队看板前端设计
    task_manager.create_task(
        title="团队看板前端设计",
        assignee="多纳泰罗",
        priority="normal",
        description="Vue3 前端页面开发",
        context={
            "background": "基于架构设计实现前端界面",
            "requirements": [
                "仪表盘视图",
                "任务看板视图",
                "智能体团队视图",
                "设备清单视图",
                "活动社区视图"
            ],
            "resources": [
                {"name": "Vue 3 文档", "url": "https://vuejs.org"},
                {"name": "Element Plus", "url": "https://element-plus.org"}
            ],
            "acceptance_criteria": [
                "5 个核心视图完成",
                "响应式布局",
                "与后端 API 对接完成",
                "无明显 UI bug"
            ],
            "dependencies": ["001"],
            "tech_stack": ["Vue 3", "Element Plus", "ECharts"],
            "notes": ""
        }
    )
    
    # 任务 3: 团队看板后端开发
    task_manager.create_task(
        title="团队看板后端开发",
        assignee="拉斐尔",
        priority="normal",
        description="FastAPI 后端开发",
        context={
            "background": "实现看板所需的后端 API 服务",
            "requirements": [
                "智能体管理 API",
                "任务管理 API",
                "设备管理 API",
                "实时 WebSocket 推送",
                "数据持久化"
            ],
            "resources": [
                {"name": "FastAPI 文档", "url": "https://fastapi.tiangolo.com"}
            ],
            "acceptance_criteria": [
                "所有 API 端点正常工作",
                "API 响应时间 <200ms",
                "WebSocket 连接稳定",
                "数据持久化正常"
            ],
            "dependencies": ["001"],
            "tech_stack": ["FastAPI", "Uvicorn", "SQLite"],
            "notes": ""
        }
    )
    
    # 任务 4: MD↔Office Skills (已完成)
    task_manager.create_task(
        title="MD↔Office Skills",
        assignee="大黄蜂",
        priority="high",
        description="Markdown 与 Office 文档转换",
        context={
            "background": "实现知识库内容的流入和流出转换",
            "requirements": [
                "Markdown → Word/PPT 转换",
                "Word/PPT → YAML 转换",
                "支持表格、公式、图片",
                "学术论文格式支持"
            ],
            "resources": [
                {"name": "pandoc 文档", "url": "https://pandoc.org"},
                {"name": "python-docx", "url": "https://python-docx.readthedocs.io"}
            ],
            "acceptance_criteria": [
                "转换成功率 >95%",
                "格式保持完整",
                "中文字体正确显示",
                "表格自动编号"
            ],
            "dependencies": [],
            "tech_stack": ["pandoc", "python-docx", "python-pptx", "pyyaml"],
            "notes": "已完成并通过测试"
        }
    )
    
    # 更新任务状态
    task_manager.update_task_status("004", TaskStatus.COMPLETED.value, 100)
    task_manager.update_task_status("001", TaskStatus.IN_PROGRESS.value, 30)
    
    # 为任务 1 添加子任务
    task_manager.add_subtask("001", "设计系统架构图", "李奥纳多", True)
    task_manager.add_subtask("001", "定义 API 接口规范", "李奥纳多", True)
    task_manager.add_subtask("001", "确定技术栈", "李奥纳多", True)
    task_manager.add_subtask("001", "编写架构文档", "李奥纳多", False)
    task_manager.add_subtask("001", "评审架构设计", "李奥纳多", False)
