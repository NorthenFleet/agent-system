"""
数据管理 - 智能体团队数据（增强版 - 支持记忆展开）
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

from unified_data_manager import unified_data_manager

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Dev Loop 路径
DEV_LOOP_DIR = os.path.expanduser("~/.openclaw/workspace/agents/ninja-turtles/dev-loop")
QUEUE_FILE = os.path.join(DEV_LOOP_DIR, "queue.json")

def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(filepath: str, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_queue_json() -> Optional[dict]:
    """加载 queue.json，失败返回 None"""
    return load_json(QUEUE_FILE)


def merge_tasks() -> list[dict]:
    """合并 queue.json + tasks.json 的任务数据，去重后返回统一列表。
    
    优先使用 queue.json 中的 Loop 任务（含 subtasks、workflow_history），
    再补充 task_queue.py 内存任务列表（兼容旧版 tasks.json 数据源）。
    相同 id 的任务以 queue.json 为准。
    """
    merged: dict[str, dict] = {}

    # 1) queue.json 中的 Loop 任务（最高优先级）
    queue = load_queue_json()
    if queue:
        for task in queue.get("tasks", []):
            task_id = task["id"]
            merged[task_id] = {
                **task,
                "source": "loop",
            }

    # 2) 从 task_queue 补充内存中的任务（旧数据源兼容）
    try:
        from task_queue import task_manager
        in_memory = task_manager.get_all_tasks()
        for task in in_memory:
            tid = task["id"]
            if tid not in merged:
                merged[tid] = {
                    **task,
                    "source": "legacy",
                }
    except Exception:
        pass

    return list(merged.values())

DEFAULT_DEVICES = []

class DataManager:
    """数据管理器"""
    
    def __init__(self):
        self.agents_file = os.path.join(DATA_DIR, "agents.json")
        self.agents = self._load_agents()
    
    def _load_agents(self) -> List[dict]:
        agents = unified_data_manager.list_agents()
        if agents:
            return agents
        if os.path.exists(self.agents_file):
            with open(self.agents_file, 'r', encoding='utf-8') as f:
                agents = json.load(f)
            unified_data_manager.save_agents(agents, actor="data_manager:init", audit=False)
            return agents
        return self._init_default_agents()
    
    def _init_default_agents(self) -> List[dict]:
        agents = [
            {"id": "optimus", "name": "擎天柱", "role": "总指挥", "emoji": "🤖", "team": "autobots", "layer": "command", "group": "command", "status": "online", "current_task": "任务统筹", "device_id": "mac-mini", "slogan": "🤖 使命必达"},
            {"id": "bumblebee", "name": "大黄蜂", "role": "运维负责人", "emoji": "🐝", "team": "autobots", "layer": "execution", "group": "development", "status": "busy", "current_task": "运维监控", "device_id": "mac-mini", "slogan": "🐝 守护系统"},
            {"id": "leonardo", "name": "李奥纳多", "role": "架构师", "emoji": "🟦", "team": "ninja_turtles", "layer": "execution", "group": "development", "status": "online", "current_task": "架构设计", "device_id": "macbook-pro", "slogan": "🟦 架构至上"},
            {"id": "raphael", "name": "拉斐尔", "role": "后端开发", "emoji": "🟥", "team": "ninja_turtles", "layer": "execution", "group": "development", "status": "idle", "current_task": "待分配", "device_id": "macbook-pro", "slogan": "🟥 代码先锋"},
            {"id": "donatello", "name": "多纳泰罗", "role": "前端开发", "emoji": "🟪", "team": "ninja_turtles", "layer": "execution", "group": "development", "status": "idle", "current_task": "待分配", "device_id": "macbook-pro", "slogan": "🟪 界面专家"},
            {"id": "michelangelo", "name": "米开朗基罗", "role": "测试工程", "emoji": "🟧", "team": "ninja_turtles", "layer": "execution", "group": "development", "status": "idle", "current_task": "待分配", "device_id": "macbook-pro", "slogan": "🟧 质量守护"},
            {"id": "ironhide", "name": "铁皮", "role": "仿真专家", "emoji": "🛡️", "team": "autobots", "layer": "execution", "group": "special", "status": "online", "current_task": "Isaac Sim 仿真", "device_id": "linux-192.168.1.4", "slogan": "🛡️ 仿真专家"},
            {"id": "wheeljack", "name": "千斤顶", "role": "工程师", "emoji": "🔧", "team": "autobots", "layer": "execution", "group": "special", "status": "idle", "current_task": "待分配", "device_id": "tbd", "slogan": "🔧 工具大师"},
            {"id": "perceptor", "name": "感知器", "role": "财务专家", "emoji": "🚗", "team": "autobots", "layer": "support", "group": "support", "status": "idle", "current_task": "发票归档", "device_id": "mac-mini", "slogan": "🚗 数据洞察"},
            {"id": "shockwave", "name": "震荡波", "role": "团队优化师", "emoji": "🟣", "team": "decepticons", "layer": "support", "group": "support", "status": "idle", "current_task": "架构分析", "device_id": "mac-mini", "slogan": "🟣 逻辑至上"}
        ]
        self._save_agents(agents)
        return agents
    
    def _load_agent_memory(self, agent_id: str) -> list:
        """从 memory.md 文件加载智能体记忆（带详情）"""
        memory_file = os.path.expanduser(f"~/.openclaw/workspace/agents/{agent_id}/memory.md")
        memories = []
        
        if os.path.exists(memory_file):
            with open(memory_file, 'r', encoding='utf-8') as f:
                content = f.read()
                current_date = ""
                current_section = ""
                
                for line in content.split('\n'):
                    line = line.strip()
                    
                    # 提取日期分组（## 2026-03）
                    if line.startswith('## '):
                        current_section = line[3:].strip()
                    
                    # 提取子日期（### 2026-03-20）
                    elif line.startswith('### '):
                        current_date = line[4:].strip()
                    
                    # 提取记忆条目
                    elif line.startswith('- ✅') or line.startswith('-'):
                        memory_text = line[1:].strip()
                        if memory_text.startswith('✅'):
                            memory_text = memory_text[1:].strip()
                        
                        if memory_text:
                            memories.append({
                                "text": memory_text,
                                "date": current_date,
                                "section": current_section,
                                "expandable": True,
                                "details": self._get_memory_details(agent_id, memory_text)
                            })
        
        return memories if memories else [{"text": "记忆加载中...", "date": "", "section": "", "expandable": False, "details": ""}]
    
    def _get_memory_details(self, agent_id: str, memory_text: str) -> str:
        """获取记忆的详细信息（相关任务、文档等）"""
        details = []
        
        # 查找相关任务文件
        tasks_dir = os.path.expanduser(f"~/.openclaw/workspace/agents/{agent_id}/tasks/")
        if os.path.exists(tasks_dir):
            for filename in os.listdir(tasks_dir):
                if filename.endswith('.md') and memory_text.split()[0] in filename:
                    details.append(f"📋 相关任务：{filename.replace('.md', '')}")
        
        # 查找相关文档
        profile_file = os.path.expanduser(f"~/.openclaw/workspace/agents/{agent_id}/profile.md")
        if os.path.exists(profile_file):
            details.append("📖 完整档案：profile.md")
        
        return "\n".join(details) if details else "点击展开查看更多详情..."
    
    def _save_agents(self, agents: List[dict]):
        unified_data_manager.save_agents(agents, actor="data_manager")
    
    def get_agents(self) -> List[dict]:
        """获取所有智能体 - 动态加载记忆"""
        self.agents = unified_data_manager.list_agents()
        for agent in self.agents:
            agent_id = agent.get("id", "")
            if agent_id:
                agent["memory"] = self._load_agent_memory(agent_id)
        return self.agents
    
    def get_agents_by_layer(self, layer: str) -> List[dict]:
        return [a for a in self.agents if a.get("layer") == layer]
    
    def get_agents_by_group(self, group: str) -> List[dict]:
        return [a for a in self.agents if a.get("group") == group]
    
    def get_agent(self, agent_id: str) -> Optional[dict]:
        for agent in self.agents:
            if agent["id"] == agent_id:
                return agent
        return None
    
    def update_agent(self, agent_id: str, updates: dict) -> bool:
        updated = unified_data_manager.update_agent(agent_id, updates, actor="data_manager")
        if not updated:
            return False
        self.agents = unified_data_manager.list_agents()
        return True
    
    def get_layer_stats(self) -> dict:
        layers = {}
        for agent in self.agents:
            layer = agent.get("layer", "unknown")
            if layer not in layers:
                layers[layer] = {"total": 0, "online": 0, "busy": 0, "idle": 0}
            layers[layer]["total"] += 1
            status = agent.get("status", "idle")
            if status in layers[layer]:
                layers[layer][status] += 1
        return layers
    
    def get_group_stats(self) -> dict:
        groups = {}
        for agent in self.agents:
            group = agent.get("group", "unknown")
            if group not in groups:
                groups[group] = {"total": 0, "online": 0, "busy": 0, "idle": 0}
            groups[group]["total"] += 1
            status = agent.get("status", "idle")
            if status in groups[group]:
                groups[group][status] += 1
        return groups

    def get_merged_tasks(self) -> list[dict]:
        """返回 queue.json + tasks.json 合并后的任务列表"""
        return merge_tasks()

data_manager = DataManager()
