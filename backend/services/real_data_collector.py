"""
真实数据采集服务
从实际运行的智能体、Cloud Code 会话、Git 仓库采集数据
"""
import os
import json
import subprocess
from datetime import datetime
from typing import List, Dict, Optional
from path_config import project_path

class RealDataCollector:
    """真实数据采集器"""
    
    def __init__(self):
        self.workspace = project_path()
        self.backend_dir = os.path.join(self.workspace, "backend")
        self.frontend_dir = os.path.join(self.workspace, "frontend")
        
    def get_cloud_sessions(self) -> List[Dict]:
        """获取活跃的 Cloud Code 会话"""
        # 从进程列表获取 Claude Code 会话
        sessions = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'claude' in line.lower() or 'codex' in line.lower():
                    # 解析会话信息
                    sessions.append({
                        "tool": "claude-code" if "claude" in line.lower() else "codex",
                        "active": True,
                        "pid": line.split()[1]
                    })
        except Exception as e:
            print(f"获取 Cloud 会话失败：{e}")
        
        return sessions if sessions else []
    
    def get_git_commits(self, days: int = 7) -> List[Dict]:
        """获取 Git 提交记录"""
        commits = []
        try:
            # 在 team-dashboard 目录执行 git log
            result = subprocess.run(
                ["git", "log", f"--since={days} days ago", "--pretty=format:%H|%an|%ae|%ad|%s"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.workspace
            )
            for line in result.stdout.split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        commits.append({
                            "hash": parts[0],
                            "author": parts[1],
                            "email": parts[2],
                            "date": parts[3],
                            "message": parts[4]
                        })
        except Exception as e:
            print(f"获取 Git 提交失败：{e}")
        
        return commits
    
    def get_spec_documents(self) -> List[Dict]:
        """获取 Spec 文档列表"""
        specs = []
        spec_dirs = [
            os.path.join(self.workspace, "specs"),
            os.path.join(self.workspace, "docs"),
            os.path.join(self.workspace, "task-records")
        ]
        
        for spec_dir in spec_dirs:
            if os.path.exists(spec_dir):
                for root, dirs, files in os.walk(spec_dir):
                    for file in files:
                        if file.endswith('.md') or file.endswith('.yaml') or file.endswith('.yml'):
                            filepath = os.path.join(root, file)
                            specs.append({
                                "name": file,
                                "path": filepath,
                                "created": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
                                "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                            })
        
        return specs
    
    def get_file_changes(self, hours: int = 24) -> Dict:
        """获取文件变更统计"""
        changes = {
            "created": 0,
            "modified": 0,
            "deleted": 0,
            "files": []
        }
        
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.workspace
            )
            for line in result.stdout.split('\n'):
                if line.strip():
                    status = line[:2]
                    filepath = line[3:]
                    if status.startswith('??'):
                        changes["created"] += 1
                        changes["files"].append({"action": "created", "path": filepath})
                    elif status.startswith('M'):
                        changes["modified"] += 1
                        changes["files"].append({"action": "modified", "path": filepath})
                    elif status.startswith('D'):
                        changes["deleted"] += 1
                        changes["files"].append({"action": "deleted", "path": filepath})
        except Exception as e:
            print(f"获取文件变更失败：{e}")
        
        return changes
    
    def calculate_task_progress(self, task_id: str) -> int:
        """根据实际开发活动计算任务进度"""
        # 获取相关 Git 提交
        commits = self.get_git_commits(days=7)
        task_commits = [c for c in commits if task_id in c.get("message", "")]
        
        # 获取相关 Spec 文档
        specs = self.get_spec_documents()
        task_specs = [s for s in specs if task_id in s.get("name", "") or task_id in s.get("path", "")]
        
        # 获取 Cloud 会话
        sessions = self.get_cloud_sessions()
        
        # 计算进度 (简化算法)
        progress = 0
        if task_commits:
            progress += min(len(task_commits) * 10, 40)  # 最多 40 分
        if task_specs:
            progress += min(len(task_specs) * 15, 30)  # 最多 30 分
        if sessions:
            progress += 30  # 有活跃会话加 30 分
        
        return min(progress, 100)
    
    def get_real_time_stats(self) -> Dict:
        """获取实时统计"""
        return {
            "cloud_sessions": len(self.get_cloud_sessions()),
            "git_commits_7d": len(self.get_git_commits(days=7)),
            "spec_documents": len(self.get_spec_documents()),
            "file_changes_24h": self.get_file_changes(hours=24),
            "timestamp": datetime.now().isoformat()
        }

# 全局实例
collector = RealDataCollector()
