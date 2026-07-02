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
    
    def sync_agents(self) -> List[Dict]:
        """从 OpenClaw 工作区实时读取智能体状态"""
        agents = []
        agents_dir = os.path.join(OPENCLAW_WORKSPACE, "agents")
        if not os.path.isdir(agents_dir):
            return agents

        # 只读取包含 AGENTS.md/SOUL.md/IDENTITY.md 的目录（排除 README.md、data/ 等非智能体目录）
        for name in sorted(os.listdir(agents_dir)):
            agent_dir = os.path.join(agents_dir, name)
            if not os.path.isdir(agent_dir):
                continue

            # 排除已知非智能体目录
            if name in ("data", "command", "execution", "knowledge", "main", "planning"):
                continue

            # 检查是否为智能体目录（包含 workspace 或 agent 配置文件）
            is_agent = False
            for check_path in ["workspace/AGENTS.md", "workspace/IDENTITY.md", "workspace/SOUL.md", "AGENT.md", "agent.md"]:
                if os.path.exists(os.path.join(agent_dir, check_path)):
                    is_agent = True
                    break
            if not is_agent:
                continue

            agent_info: Dict[str, Any] = {
                "id": name,
                "name": name.capitalize(),
                "role": "",
                "status": "idle",
                "current_task": "待分配",
            }

            # 读取 workspace 中的身份文件
            for fname in ["IDENTITY.md", "SOUL.md", "AGENT.md", "agent.md"]:
                role_file = os.path.join(agent_dir, "workspace", fname)
                if not os.path.exists(role_file):
                    role_file = os.path.join(agent_dir, fname)
                if os.path.exists(role_file):
                    try:
                        with open(role_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        for line in content.split('\n'):
                            line = line.strip()
                            if '**Name**' in line or '**name**' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    agent_info['name'] = parts[1].strip().strip('*').strip()
                            if '**Role**' in line or '**role**' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    agent_info['role'] = parts[1].strip().strip('*').strip()
                            if '**Emoji**' in line or '**emoji**' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    agent_info['emoji'] = parts[1].strip().strip('*').strip()
                            if '**状态**' in line or '**status**' in line:
                                parts = line.split(':', 1)
                                if len(parts) == 2:
                                    agent_info['status'] = parts[1].strip().strip('*').strip()
                    except Exception:
                        pass
                    break

            # 从 dev-loop/queue.json 中查找当前任务
            queue_file = os.path.join(OPENCLAW_WORKSPACE, "agents", "ninja-turtles", "dev-loop", "queue.json")
            if os.path.exists(queue_file):
                try:
                    with open(queue_file, 'r', encoding='utf-8') as f:
                        queue_data = json.load(f)
                    for task in queue_data.get("tasks", []):
                        if task.get("assignee") == name and task.get("status") in ("assigned", "in_progress", "review"):
                            agent_info["current_task"] = task.get("title", task["id"])
                            agent_info["status"] = "busy" if task.get("status") == "in_progress" else "online"
                            break
                        for sub in task.get("subtasks", []):
                            if sub.get("assignee") == name and sub.get("status") in ("assigned", "in_progress", "review"):
                                agent_info["current_task"] = sub.get("title", sub["id"])
                                agent_info["status"] = "busy" if sub.get("status") == "in_progress" else "online"
                                break
                except Exception:
                    pass

            agents.append(agent_info)

        return agents

    def sync_data(self) -> Dict:
        """同步数据"""
        email_stats = self.get_email_stats()
        codex_tasks = self.get_codex_tasks()
        heartbeat = self.get_heartbeat_state()
        agents = self.sync_agents()

        self.last_sync = datetime.now().isoformat()

        return {
            "agents": agents,
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
