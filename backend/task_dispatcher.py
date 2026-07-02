#!/usr/bin/env python3
"""
任务派发服务
通过 OpenClaw 派发任务到各智能体
"""

import json
import os
import subprocess
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# 任务存储目录
TASKS_DIR = os.path.expanduser("~/.openclaw/workspace/tasks")
os.makedirs(TASKS_DIR, exist_ok=True)


class TaskDispatcher:
    """任务派发管理器"""
    
    def __init__(self):
        self.tasks_dir = TASKS_DIR
    
    def _get_tasks_file(self) -> str:
        return os.path.join(self.tasks_dir, "dispatched_tasks.json")
    
    def load_tasks(self) -> List[Dict]:
        filepath = self._get_tasks_file()
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_tasks(self, tasks: List[Dict]):
        filepath = self._get_tasks_file()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    def dispatch_task(self, agent_id: str, task_desc: str, priority: str = "normal") -> Dict:
        """派发任务到智能体"""
        tasks = self.load_tasks()
        
        task_id = f"task_{len(tasks) + 1:04d}"
        task = {
            "task_id": task_id,
            "agent_id": agent_id,
            "description": task_desc,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None
        }
        
        tasks.append(task)
        self.save_tasks(tasks)
        
        return task
    
    def update_task_status(self, task_id: str, status: str, result: str = None) -> Dict:
        """更新任务状态"""
        tasks = self.load_tasks()
        for task in tasks:
            if task["task_id"] == task_id:
                task["status"] = status
                if result:
                    task["result"] = result
                if status == "in_progress" and not task["started_at"]:
                    task["started_at"] = datetime.now().isoformat()
                if status in ["completed", "failed"]:
                    task["completed_at"] = datetime.now().isoformat()
                break
        
        self.save_tasks(tasks)
        return task
    
    def get_tasks(self, agent_id: str = None, status: str = None) -> List[Dict]:
        """获取任务列表（可过滤）"""
        tasks = self.load_tasks()
        
        if agent_id:
            tasks = [t for t in tasks if t["agent_id"] == agent_id]
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        
        return tasks
    
    def get_task_stats(self) -> Dict:
        """获取任务统计"""
        tasks = self.load_tasks()
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t["status"] == "pending"),
            "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
            "failed": sum(1 for t in tasks if t["status"] == "failed")
        }


# 全局实例
task_dispatcher = TaskDispatcher()


if __name__ == "__main__":
    dispatcher = TaskDispatcher()
    task = dispatcher.dispatch_task("optimus", "测试任务", "high")
    print(json.dumps(task, indent=2, ensure_ascii=False))
