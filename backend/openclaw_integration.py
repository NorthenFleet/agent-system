#!/usr/bin/env python3
"""
OpenClaw API 集成模块
实时同步智能体状态、会话、任务数据
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any

# OpenClaw 配置
OPENCLAW_WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
TASKS_DIR = os.path.join(OPENCLAW_WORKSPACE, "tasks")
LOGS_DIR = os.path.join(OPENCLAW_WORKSPACE, "logs")


class OpenClawIntegration:
    """OpenClaw 数据集成器"""
    
    def __init__(self):
        self.last_sync = None
    
    def get_email_stats(self) -> Dict:
        """获取邮件检查统计"""
        stats = {
            "last_check": None,
            "total_unread": 0,
            "today_checked": 0,
            "today_invoices": 0,
            "today_papers": 0,
            "ignored": 0
        }
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            today_log = os.path.join(LOGS_DIR, f"email-dispatch-{today}.json")
            
            if os.path.exists(today_log):
                with open(today_log, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 处理数组或字典格式
                    if isinstance(data, list):
                        if len(data) > 0:
                            last_entry = data[-1]
                            stats["last_check"] = last_entry.get("check_time", "")
                            stats["total_unread"] = last_entry.get("total_unread", 0)
                            stats["today_checked"] = last_entry.get("checked_count", 0)
                            stats["today_invoices"] = last_entry.get("invoice_count", 0)
                            stats["today_papers"] = last_entry.get("paper_count", 0)
                            stats["ignored"] = last_entry.get("ignored_count", 0)
                    elif isinstance(data, dict):
                        stats["last_check"] = data.get("check_time", "")
                        stats["total_unread"] = data.get("total_unread", 0)
                        stats["today_checked"] = data.get("checked_count", 0)
                        stats["today_invoices"] = data.get("invoice_count", 0)
                        stats["today_papers"] = data.get("paper_count", 0)
                        stats["ignored"] = data.get("ignored_count", 0)
        except Exception as e:
            print(f"[OpenClaw] 获取邮件统计失败：{e}")
        
        return stats
    
    def get_codex_tasks(self) -> List[Dict]:
        """获取 Codex 任务列表"""
        tasks = []
        
        try:
            if os.path.exists(TASKS_DIR):
                for filename in sorted(os.listdir(TASKS_DIR), reverse=True):
                    if filename.startswith("task_") and filename.endswith(".json"):
                        filepath = os.path.join(TASKS_DIR, filename)
                        with open(filepath, 'r', encoding='utf-8') as f:
                            task = json.load(f)
                            tasks.append({
                                "task_id": task.get("task_id", filename),
                                "mode": task.get("mode", "agent"),
                                "assignee": task.get("assignee", ""),
                                "description": task.get("description", ""),
                                "status": task.get("status", "pending"),
                                "model": task.get("model", "codex"),
                                "created_at": task.get("created_at", ""),
                                "estimated_files": task.get("estimated_files", 0),
                                "estimated_lines": task.get("estimated_lines", 0)
                            })
        except Exception as e:
            print(f"[OpenClaw] 获取 Codex 任务失败：{e}")
        
        return tasks
    
    def get_heartbeat_state(self) -> Dict:
        """获取心跳状态"""
        state = {
            "last_heartbeat": None,
            "next_report": None,
            "tasks_completed_today": 0
        }
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            # 查找最新的 heartbeat 报告
            if os.path.exists(LOGS_DIR):
                heartbeat_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"heartbeat-report-{today}")]
                if heartbeat_files:
                    state["last_heartbeat"] = today + " 09:00"
                    state["next_report"] = today + " 12:00"
        except Exception as e:
            print(f"[OpenClaw] 获取心跳状态失败：{e}")
        
        return state
    
    def sync_data(self) -> Dict:
        """同步数据"""
        email_stats = self.get_email_stats()
        codex_tasks = self.get_codex_tasks()
        heartbeat = self.get_heartbeat_state()
        
        self.last_sync = datetime.now().isoformat()
        
        return {
            "email_stats": email_stats,
            "codex_tasks": codex_tasks,
            "heartbeat": heartbeat,
            "last_sync": self.last_sync
        }


# 全局实例
openclaw_integration = OpenClawIntegration()


if __name__ == "__main__":
    stats = openclaw_integration.sync_data()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
