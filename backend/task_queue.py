"""
任务队列管理 - 基于内存的简单任务队列
"""
import json
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, dict] = {}
        self.task_counter = 0
    
    def create_task(self, title: str, assignee: str, priority: str = "normal", description: str = "") -> str:
        """创建新任务"""
        self.task_counter += 1
        task_id = f"{self.task_counter:03d}"
        
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
            "completed_at": None
        }
        
        self.tasks[task_id] = task
        print(f"[Task] 创建任务：{task_id} - {title}")
        return task_id
    
    def update_task_status(self, task_id: str, status: str, progress: Optional[int] = None):
        """更新任务状态"""
        if task_id not in self.tasks:
            print(f"[Task] 任务不存在：{task_id}")
            return False
        
        task = self.tasks[task_id]
        task["status"] = status
        task["updated_at"] = datetime.now().isoformat()
        
        if progress is not None:
            task["progress"] = progress
        
        if status == TaskStatus.COMPLETED.value:
            task["completed_at"] = datetime.now().isoformat()
            task["progress"] = 100
        
        print(f"[Task] 更新任务：{task_id} - 状态={status}, 进度={progress}")
        return True
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务详情"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[dict]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def get_pending_tasks(self, assignee: str) -> List[dict]:
        """获取待处理任务"""
        return [
            task for task in self.tasks.values()
            if task["status"] == TaskStatus.PENDING.value and task["assignee"] == assignee
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
    """初始化示例任务"""
    task_manager.create_task(
        title="团队看板架构设计",
        assignee="李奥纳多",
        priority="high",
        description="设计团队看板的系统架构"
    )
    task_manager.create_task(
        title="团队看板前端设计",
        assignee="多纳泰罗",
        priority="normal",
        description="Vue3 前端页面开发"
    )
    task_manager.create_task(
        title="团队看板后端开发",
        assignee="拉斐尔",
        priority="normal",
        description="FastAPI 后端开发"
    )
    task_manager.create_task(
        title="MD↔Office Skills",
        assignee="大黄蜂",
        priority="high",
        description="Markdown 与 Office 文档转换"
    )
    # 更新最后一个任务为完成状态
    task_manager.update_task_status("004", TaskStatus.COMPLETED.value, 100)
    # 更新第一个任务为进行中
    task_manager.update_task_status("001", TaskStatus.IN_PROGRESS.value, 30)

