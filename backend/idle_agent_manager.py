# -*- coding: utf-8 -*-
"""
空闲智能体检测与自动分工管理
- 定时扫描所有智能体状态
- 识别 status=idle 或 current_task=待分配 的智能体
- 根据职责匹配任务
- 生成开发计划建议
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os

class IdleAgentManager:
    """空闲智能体管理器"""
    
    def __init__(self):
        self.state_file = "data/idle_agent_state.json"
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """加载状态"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {
            "agent_idle_since": {},  # agent_id -> ISO timestamp
            "last_scan": None,
            "assignment_history": []
        }
    
    def _save_state(self):
        """保存状态"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def scan_idle_agents(self, agents: List[Dict]) -> List[Dict]:
        """
        扫描所有智能体，识别空闲智能体
        返回空闲智能体列表（包含空闲时长）
        """
        now = datetime.now()
        idle_agents = []
        
        for agent in agents:
            agent_id = agent.get("id", "")
            status = agent.get("status", "")
            current_task = agent.get("current_task", "")
            
            # 判断是否空闲
            is_idle = (status == "idle") or (current_task == "待分配") or (current_task == "")
            
            if is_idle:
                # 记录空闲开始时间
                if agent_id not in self.state["agent_idle_since"]:
                    self.state["agent_idle_since"][agent_id] = now.isoformat()
                
                # 计算空闲时长
                idle_since = datetime.fromisoformat(self.state["agent_idle_since"][agent_id])
                idle_duration = (now - idle_since).total_seconds()
                
                idle_agents.append({
                    "id": agent_id,
                    "name": agent.get("name", ""),
                    "role": agent.get("role", ""),
                    "emoji": agent.get("emoji", ""),
                    "team": agent.get("team", ""),
                    "responsibilities": agent.get("responsibilities", []),
                    "status": status,
                    "current_task": current_task,
                    "idle_since": self.state["agent_idle_since"][agent_id],
                    "idle_duration_seconds": idle_duration,
                    "idle_duration_formatted": self._format_duration(idle_duration)
                })
            else:
                # 清除非空闲智能体的记录
                if agent_id in self.state["agent_idle_since"]:
                    del self.state["agent_idle_since"][agent_id]
        
        self.state["last_scan"] = now.isoformat()
        self._save_state()
        
        return idle_agents
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds / 60)}分钟"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}小时{minutes}分钟"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            return f"{days}天{hours}小时"
    
    def match_task_to_agent(self, agent: Dict, tasks: List[Dict]) -> Optional[Dict]:
        """
        根据智能体职责匹配最适合的任务
        返回推荐的任务
        """
        responsibilities = agent.get("responsibilities", [])
        best_match = None
        best_score = 0
        
        for task in tasks:
            if task.get("status") not in ["pending", "todo"]:
                continue
            
            score = 0
            task_type = task.get("type", "").lower()
            task_title = task.get("title", "").lower()
            task_description = task.get("description", "").lower()
            task_tags = task.get("tags", [])
            
            # 如果没有 type 字段，从标题/描述推断
            if not task_type:
                if "后端" in task_title or "api" in task_title or "backend" in task_description:
                    task_type = "backend"
                elif "前端" in task_title or "vue" in task_description or "ui" in task_description:
                    task_type = "frontend"
                elif "测试" in task_title or "test" in task_description:
                    task_type = "testing"
                elif "架构" in task_title or "设计" in task_title:
                    task_type = "architecture"
                else:
                    task_type = "general" 
            
            # 职责匹配
            for resp in responsibilities:
                resp_lower = resp.lower()
                if resp_lower in task_title or resp_lower in task_type:
                    score += 10
                for tag in task_tags:
                    if resp_lower in tag.lower():
                        score += 5
            
            # 角色特殊匹配
            role = agent.get("role", "").lower()
            role_keywords = {
                "后端": ["backend", "api", "database", "后端"],
                "前端": ["frontend", "ui", "vue", "前端"],
                "架构": ["architecture", "design", "架构", "设计"],
                "测试": ["testing", "qa", "测试"],
            }
            for role_key, type_keywords in role_keywords.items():
                if role_key in role:
                    # 检查任务类型或标题/描述是否匹配
                    if task_type in type_keywords or any(kw in task_title or kw in task_description for kw in type_keywords):
                        score += 15
                        break
            
            if score > best_score:
                best_score = score
                best_match = task
        
        if best_match:
            return {
                "task_id": best_match["id"],
                "task_title": best_match["title"],
                "task_type": best_match.get("type", "general"),
                "match_score": best_score,
                "match_reason": self._get_match_reason(agent, best_match)
            }
        
        return None
    
    def _get_match_reason(self, agent: Dict, task: Dict) -> str:
        """生成匹配原因说明"""
        responsibilities = agent.get("responsibilities", [])
        role = agent.get("role", "")
        task_type = task.get("type", "general")
        
        reasons = []
        for resp in responsibilities[:2]:  # 最多显示 2 个职责
            reasons.append(resp)
        
        return f"基于职责：{', '.join(reasons)} | 角色：{role}"
    
    def generate_development_plan(self, agent: Dict, recommended_task: Dict) -> Dict:
        """
        为智能体生成下一步开发计划
        """
        now = datetime.now()
        
        plan = {
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "agent_role": agent["role"],
            "recommended_task": recommended_task,
            "next_steps": self._generate_next_steps(agent, recommended_task),
            "estimated_hours": self._estimate_hours(agent, recommended_task),
            "priority": self._calculate_priority(agent, recommended_task),
            "generated_at": now.isoformat(),
            "status": "recommended"  # recommended, assigned, in_progress
        }
        
        return plan
    
    def _generate_next_steps(self, agent: Dict, task: Dict) -> List[Dict]:
        """生成具体的下一步行动"""
        role = agent.get("role", "")
        task_type = task.get("type", "general")
        
        steps = []
        
        # 通用步骤
        steps.append({
            "order": 1,
            "action": "阅读任务详情",
            "description": f"查看任务 '{task.get('task_title', 'Unknown')}' 的完整需求和背景",
            "estimated_minutes": 15
        })
        
        # 根据角色定制步骤
        if "后端" in role or task_type in ["backend", "api"]:
            steps.append({
                "order": 2,
                "action": "设计 API 接口",
                "description": "定义请求/响应格式和数据模型",
                "estimated_minutes": 30
            })
            steps.append({
                "order": 3,
                "action": "实现业务逻辑",
                "description": "编写核心代码和单元测试",
                "estimated_minutes": 120
            })
        elif "前端" in role or task_type in ["frontend", "ui"]:
            steps.append({
                "order": 2,
                "action": "设计 UI 组件",
                "description": "规划组件结构和状态管理",
                "estimated_minutes": 30
            })
            steps.append({
                "order": 3,
                "action": "实现页面交互",
                "description": "编写 Vue 组件和样式",
                "estimated_minutes": 120
            })
        elif "架构" in role or task_type in ["architecture", "design"]:
            steps.append({
                "order": 2,
                "action": "技术方案设计",
                "description": "编写技术规格文档",
                "estimated_minutes": 60
            })
            steps.append({
                "order": 3,
                "action": "方案评审",
                "description": "与团队讨论并优化方案",
                "estimated_minutes": 30
            })
        elif "测试" in role or task_type in ["testing", "qa"]:
            steps.append({
                "order": 2,
                "action": "编写测试用例",
                "description": "设计测试场景和预期结果",
                "estimated_minutes": 30
            })
            steps.append({
                "order": 3,
                "action": "执行测试",
                "description": "运行自动化测试并记录结果",
                "estimated_minutes": 60
            })
        else:
            steps.append({
                "order": 2,
                "action": "制定实施方案",
                "description": "规划具体执行步骤",
                "estimated_minutes": 30
            })
            steps.append({
                "order": 3,
                "action": "执行任务",
                "description": "按照计划完成工作",
                "estimated_minutes": 90
            })
        
        return steps
    
    def _estimate_hours(self, agent: Dict, task: Dict) -> float:
        """估算任务耗时（小时）"""
        task_type = task.get("type", "general")
        
        estimates = {
            "backend": 4.0,
            "frontend": 3.0,
            "api": 2.0,
            "testing": 2.0,
            "architecture": 6.0,
            "design": 4.0,
            "general": 3.0
        }
        
        base_estimate = estimates.get(task_type, 3.0)
        
        # 根据空闲时长调整优先级（空闲越久优先级越高）
        agent_id = agent.get("id", "")
        if agent_id in self.state["agent_idle_since"]:
            idle_seconds = (datetime.now() - datetime.fromisoformat(self.state["agent_idle_since"][agent_id])).total_seconds()
            if idle_seconds > 86400:  # 超过 1 天
                base_estimate *= 0.8  # 优先处理
        
        return round(base_estimate, 1)
    
    def _calculate_priority(self, agent: Dict, task: Dict) -> str:
        """计算优先级"""
        agent_id = agent.get("id", "")
        
        if agent_id in self.state["agent_idle_since"]:
            idle_seconds = (datetime.now() - datetime.fromisoformat(self.state["agent_idle_since"][agent_id])).total_seconds()
            
            if idle_seconds > 86400:  # 超过 1 天
                return "high"
            elif idle_seconds > 3600:  # 超过 1 小时
                return "medium"
        
        return "normal"
    
    def assign_task_to_agent(self, agent_id: str, task_id: str, plan: Dict) -> Dict:
        """
        将任务分配给智能体
        记录分配历史
        """
        now = datetime.now()
        
        assignment = {
            "timestamp": now.isoformat(),
            "agent_id": agent_id,
            "task_id": task_id,
            "plan": plan,
            "status": "assigned"
        }
        
        self.state["assignment_history"].append(assignment)
        
        # 保留最近 100 条记录
        if len(self.state["assignment_history"]) > 100:
            self.state["assignment_history"] = self.state["assignment_history"][-100:]
        
        self._save_state()
        
        return assignment
    
    def get_assignment_history(self, limit: int = 20) -> List[Dict]:
        """获取分配历史"""
        return self.state["assignment_history"][-limit:]
    
    def get_idle_stats(self, agents: List[Dict]) -> Dict:
        """获取空闲统计"""
        idle_agents = self.scan_idle_agents(agents)
        
        total = len(agents)
        idle_count = len(idle_agents)
        busy_count = total - idle_count
        
        # 按团队统计
        team_stats = {}
        for agent in idle_agents:
            team = agent.get("team", "unknown")
            if team not in team_stats:
                team_stats[team] = {"idle": 0, "total": 0}
            team_stats[team]["idle"] += 1
        
        for agent in agents:
            team = agent.get("team", "unknown")
            if team not in team_stats:
                team_stats[team] = {"idle": 0, "total": 0}
            team_stats[team]["total"] += 1
        
        return {
            "total_agents": total,
            "idle_count": idle_count,
            "busy_count": busy_count,
            "idle_rate": round(idle_count / total * 100, 1) if total > 0 else 0,
            "team_stats": team_stats,
            "last_scan": self.state["last_scan"]
        }


# 全局实例
idle_agent_manager = IdleAgentManager()
