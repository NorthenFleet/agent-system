#!/usr/bin/env python3
"""
智能体文档管理器
扫描、索引、提供智能体相关文档
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# 工作区路径
OPENCLAW_WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
TEAM_DASHBOARD = os.path.expanduser("~/WorkSpace/team-dashboard")

MAX_PREVIEW_LINES = 500
MAX_PREVIEW_BYTES = 1024 * 1024
ALLOWED_PREVIEW_ROOTS = tuple(
    Path(root).expanduser().resolve()
    for root in (
        OPENCLAW_WORKSPACE,
        f"{TEAM_DASHBOARD}/docs",
        f"{TEAM_DASHBOARD}/specs",
        f"{TEAM_DASHBOARD}/backend",
        f"{TEAM_DASHBOARD}/frontend",
        f"{TEAM_DASHBOARD}/tests",
    )
)

def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

# 智能体文档映射
AGENT_DOC_MAP = {
    "optimus": {
        "name": "擎天柱",
        "paths": [
            {"path": f"{OPENCLAW_WORKSPACE}/MEMORY.md", "type": "memory", "name": "长期记忆"},
            {"path": f"{OPENCLAW_WORKSPACE}/tasks/", "type": "task", "name": "任务文件", "pattern": "*.md"},
        ]
    },
    "bumblebee": {
        "name": "大黄蜂",
        "paths": [
            {"path": f"{OPENCLAW_WORKSPACE}/skills/", "type": "skill", "name": "技能库"},
            {"path": f"{TEAM_DASHBOARD}/docs/", "type": "doc", "name": "项目文档"},
        ]
    },
    "leonardo": {
        "name": "李奥纳多",
        "paths": [
            {"path": f"{TEAM_DASHBOARD}/docs/", "type": "architecture", "name": "架构设计"},
            {"path": f"{TEAM_DASHBOARD}/specs/", "type": "spec", "name": "技术规格"},
        ]
    },
    "raphael": {
        "name": "拉斐尔",
        "paths": [
            {"path": f"{TEAM_DASHBOARD}/backend/", "type": "code", "name": "后端代码", "pattern": "*.py"},
        ]
    },
    "donatello": {
        "name": "多纳泰罗",
        "paths": [
            {"path": f"{TEAM_DASHBOARD}/frontend/", "type": "code", "name": "前端代码", "pattern": "*.html"},
        ]
    },
    "michelangelo": {
        "name": "米开朗基罗",
        "paths": [
            {"path": f"{TEAM_DASHBOARD}/tests/", "type": "test", "name": "测试代码"},
        ]
    },
    "perceptor": {
        "name": "感知器",
        "paths": [
            {"path": f"{OPENCLAW_WORKSPACE}/scripts/", "type": "script", "name": "财务脚本", "pattern": "email*.py"},
            {"path": f"{OPENCLAW_WORKSPACE}/logs/", "type": "log", "name": "邮件日志", "pattern": "email*.json"},
        ]
    },
    "ironhide": {
        "name": "铁皮",
        "paths": [
            {"path": "ssh://sun@192.168.1.4/~/isaac-sim/", "type": "remote", "name": "仿真报告 (远程)"},
        ]
    },
    "shockwave": {
        "name": "震荡波",
        "paths": [
            {"path": f"{OPENCLAW_WORKSPACE}/MEMORY.md", "type": "memory", "name": "团队记忆"},
            {"path": f"{OPENCLAW_WORKSPACE}/docs/", "type": "doc", "name": "团队文档"},
            {"path": f"{TEAM_DASHBOARD}/docs/", "type": "architecture", "name": "架构文档"},
        ]
    },
}


class DocumentManager:
    """文档管理器"""

    def __init__(self):
        self.cache = {}
        self.last_scan = None

    def scan_documents(self, agent_id: str) -> List[Dict]:
        """扫描智能体相关文档"""
        if agent_id not in AGENT_DOC_MAP:
            return []

        docs = []
        config = AGENT_DOC_MAP[agent_id]

        for item in config.get("paths", []):
            path = item["path"]
            doc_type = item["type"]
            doc_name = item["name"]
            pattern = item.get("pattern", "*")

            if path.startswith("ssh://"):
                docs.append({
                    "name": doc_name,
                    "type": doc_type,
                    "path": path,
                    "size": "N/A",
                    "modified": "N/A",
                    "remote": True
                })
            elif os.path.exists(path):
                if os.path.isfile(path):
                    stat = os.stat(path)
                    docs.append({
                        "name": os.path.basename(path),
                        "type": doc_type,
                        "path": path,
                        "size": self._format_size(stat.st_size),
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "remote": False
                    })
                elif os.path.isdir(path):
                    for root, dirs, files in os.walk(path):
                        depth = root.replace(path, '').count(os.sep)
                        if depth > 2:
                            continue

                        for filename in files:
                            if self._match_pattern(filename, pattern):
                                filepath = os.path.join(root, filename)
                                try:
                                    stat = os.stat(filepath)
                                    rel_path = os.path.relpath(filepath, OPENCLAW_WORKSPACE)
                                    docs.append({
                                        "name": filename,
                                        "type": doc_type,
                                        "path": filepath,
                                        "relative_path": rel_path,
                                        "size": self._format_size(stat.st_size),
                                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                        "remote": False
                                    })
                                except Exception as e:
                                    print(f"[DocManager] 读取文件失败 {filepath}: {e}")

        docs.sort(key=lambda x: x.get("modified", ""), reverse=True)
        return docs[:50]

    def get_document_content(self, filepath: str, max_lines: int = 100) -> str:
        """获取文档内容预览"""
        try:
            requested = Path(filepath).expanduser().resolve()
            if not any(_is_relative_to(requested, root) for root in ALLOWED_PREVIEW_ROOTS):
                return "拒绝访问：文件不在允许预览目录内"
            if not requested.exists():
                return "文件不存在"
            if not requested.is_file():
                return "拒绝访问：只能预览文件"
            if requested.stat().st_size > MAX_PREVIEW_BYTES:
                return "拒绝访问：文件超过 1MB 预览上限"

            max_lines = max(1, min(int(max_lines), MAX_PREVIEW_LINES))
            with requested.open('r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... (预览已截断，最多显示 {max_lines} 行)")
                        break
                    lines.append(line)
                return ''.join(lines)
        except UnicodeDecodeError:
            return "拒绝访问：仅支持 UTF-8 文本预览"
        except Exception as e:
            return f"读取失败：{e}"

    def get_agent_full_details(self, agent_id: str, data_manager) -> Dict:
        """获取智能体完整详情"""
        agents = data_manager.get_agents()
        agent = None

        for a in agents:
            if a["id"] == agent_id:
                agent = a
                break

        if not agent:
            return {"error": "智能体不存在"}

        documents = self.scan_documents(agent_id)
        memory = agent.get("memory", [])

        return {
            "agent": agent,
            "memory": memory,
            "documents": documents,
            "document_count": len(documents),
            "last_scan": self.last_scan
        }

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """简单的文件名模式匹配"""
        if pattern == "*":
            return True
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)


# 全局实例
doc_manager = DocumentManager()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        agent_id = sys.argv[1]
        docs = doc_manager.scan_documents(agent_id)
        print(f"\n📁 {agent_id} 的文档 ({len(docs)}):")
        for doc in docs[:10]:
            print(f"  - {doc['name']} ({doc['type']}) - {doc['size']}")
    else:
        print("用法：python document_manager.py [agent_id]")
