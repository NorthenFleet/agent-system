"""
Cloud Code 会话监控器
持续监控活跃的 Cloud Code 会话并更新任务状态
"""
import os
import json
import subprocess
import time
from datetime import datetime
from typing import List, Dict

class CloudSessionMonitor:
    """Cloud Code 会话监控器"""
    
    def __init__(self):
        self.sessions_file = os.path.expanduser("~/WorkSpace/team-dashboard/backend/data/cloud_sessions.json")
        self.task_map = {
            "clear-shore": "005",  # 任务看板与开发计划整合
            "tidy-claw": "006",    # 西部小镇咖啡馆
            "glow-lagoon": "007",  # 新闻资讯地球
        }
    
    def detect_cloud_sessions(self) -> List[Dict]:
        """检测活跃的 Cloud Code 会话"""
        sessions = []
        try:
            # 获取所有 Python/Node 进程
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            for line in result.stdout.split('\n'):
                if 'claude' in line.lower() or 'codex' in line.lower():
                    parts = line.split()
                    if len(parts) >= 11:
                        pid = parts[1]
                        # 尝试从命令行参数中提取会话 ID
                        cmd = ' '.join(parts[10:])
                        session_id = self.extract_session_id(cmd)
                        
                        if session_id:
                            sessions.append({
                                "session_id": session_id,
                                "task_id": self.task_map.get(session_id),
                                "tool": "claude-code" if "claude" in line.lower() else "codex",
                                "pid": pid,
                                "active": True,
                                "started": datetime.now().isoformat()
                            })
        except Exception as e:
            print(f"检测 Cloud 会话失败：{e}")
        
        return sessions
    
    def extract_session_id(self, cmd: str) -> str:
        """从命令行提取会话 ID"""
        # 常见的会话 ID 模式
        import re
        patterns = [
            r'session[-_]([a-z]+[-_][a-z0-9]+)',
            r'--session[-_]?[=]?([a-z]+[-_][a-z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""
    
    def save_sessions(self, sessions: List[Dict]):
        """保存会话数据"""
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        data = {
            "sessions": sessions,
            "last_update": datetime.now().isoformat(),
            "total": len(sessions)
        }
        with open(self.sessions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def monitor(self, interval: int = 30):
        """持续监控"""
        print(f"开始监控 Cloud Code 会话 (间隔：{interval}秒)")
        while True:
            sessions = self.detect_cloud_sessions()
            self.save_sessions(sessions)
            print(f"检测到 {len(sessions)} 个活跃 Cloud 会话")
            time.sleep(interval)

# 主程序
if __name__ == "__main__":
    monitor = CloudSessionMonitor()
    monitor.monitor(interval=30)
