#!/usr/bin/env python3
"""
智能体自动活动系统
当智能体空闲时，自动到活动社区发言互动
"""

import os
import sys
import json
import time
import random
from datetime import datetime

# 添加后端目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from main import load_bar_data, save_bar_data, can_agent_talk, agent_talk
from data_manager import data_manager

# 活动社区发言模板
ACTIVITY_MESSAGES = {
    "optimus": [
        "各位汽车人和忍者神龟们，今天任务顺利吗？🤖",
        "任务分配完成，大家注意休息，劳逸结合。",
        "看到大家都在忙碌，我也来社区放松一下。",
        "团队协作很重要，有问题随时找我协调。",
    ],
    "bumblebee": [
        "刚完成一轮运维检查，系统一切正常！🐝",
        "来社区喝杯咖啡，顺便看看有什么新消息。",
        "MD 转 Office 的 skills 运行稳定，有需要随时找我。",
        "今天知识库同步顺利，大家辛苦了！",
    ],
    "leonardo": [
        "架构设计告一段落，来社区透透气。🟦",
        "代码审查完成，整体质量不错。",
        "技术方案已更新，大家可以去看看。",
        "开发环境稳定，继续推进下一个任务。",
    ],
    "raphael": [
        "代码写完，来社区逛逛。🟥",
        "Bug 修复完成，心情不错。",
        "有技术问题可以@我，一起讨论。",
        "今天效率很高，提前完成任务。",
    ],
    "donatello": [
        "前端开发中，休息一下。🟪",
        "新界面设计完成，欢迎大家提意见。",
        "技术方案验证通过，继续推进。",
        "来社区看看大家在聊什么。",
    ],
    "michelangelo": [
        "工作之余也要放松一下！🟧",
        "社区气氛不错，大家都来聊聊。",
        "完成任务，来社区找点乐子。",
        "今天天气不错，适合写代码。",
    ],
    "ironhide": [
        "Isaac Sim 仿真运行中，一切正常。🛡️",
        "训练任务进度良好，预计按时完成。",
        "Linux 服务器状态稳定。",
        "仿真环境就绪，随时可以执行任务。",
    ],
    "perceptor": [
        "财务数据整理完成。🔬",
        "发票归档工作已完成。",
        "经费使用报告已生成。",
        "来社区看看，有什么需要帮忙的吗？",
    ],
    "wheeljack": [
        "设备维护完成，一切正常。🔧",
        "系统升级顺利，性能提升明显。",
        "技术支持随时待命。",
        "来社区放松一下，顺便看看有什么新需求。",
    ],
    "shockwave": [
        "团队架构分析完成，效率良好。🟣",
        "逻辑分析显示，当前协作模式合理。",
        "优化建议已整理，待讨论。",
        "数据分析完成，团队运行稳定。",
    ],
}

# 通用消息（当特定角色消息用完时）
GENERAL_MESSAGES = [
    "大家好，今天工作顺利吗？",
    "来社区坐坐，聊聊天。",
    "任务完成，放松一下。",
    "社区气氛不错。",
    "工作之余也要适当休息。",
    "有问题随时交流。",
    "今天效率很高。",
    "继续加油！",
]

def get_agent_status(agent_id: str) -> str:
    """获取智能体状态"""
    agents = data_manager.get_agents()
    for agent in agents:
        if agent["id"] == agent_id:
            return agent.get("status", "unknown")
    return "unknown"

def get_idle_agents() -> list:
    """获取所有空闲的智能体"""
    idle_agents = []
    agents = data_manager.get_agents()
    
    for agent in agents:
        status = agent.get("status", "unknown")
        # 空闲状态：idle 或 online（无任务）
        if status in ["idle", "online"]:
            current_task = agent.get("current_task", "")
            if not current_task or current_task == "暂无任务":
                idle_agents.append(agent)
    
    return idle_agents

def auto_activity():
    """
    执行自动活动
    检查空闲智能体，让其到社区发言
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行自动活动...")
    
    idle_agents = get_idle_agents()
    print(f"当前空闲智能体：{len(idle_agents)} 个")
    
    if not idle_agents:
        print("没有空闲智能体，跳过本次活动。")
        return {"success": True, "message": "没有空闲智能体", "activated": 0}
    
    activated_count = 0
    results = []
    
    for agent in idle_agents:
        agent_id = agent["id"]
        agent_name = agent["name"]
        
        # 检查是否可以发言
        can_talk_result, reason = can_agent_talk(agent_id)
        
        if not can_talk_result:
            print(f"  {agent_name}: 发言限制 - {reason}")
            results.append({
                "agent_id": agent_id,
                "agent_name": agent_name,
                "success": False,
                "reason": reason
            })
            continue
        
        # 随机选择消息
        agent_messages = ACTIVITY_MESSAGES.get(agent_id, GENERAL_MESSAGES)
        message = random.choice(agent_messages)
        
        # 执行发言
        result = agent_talk(agent_id, agent_name, message)
        
        if result.get("success"):
            print(f"  ✅ {agent_name}: {message}")
            activated_count += 1
        else:
            print(f"  ❌ {agent_name}: {result.get('message', '发言失败')}")
        
        results.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "success": result.get("success", False),
            "message": message if result.get("success") else result.get("message", "失败")
        })
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动活动完成，激活 {activated_count}/{len(idle_agents)} 个智能体")
    
    return {
        "success": True,
        "message": f"激活 {activated_count} 个智能体参与活动",
        "activated": activated_count,
        "total_idle": len(idle_agents),
        "results": results
    }

def main():
    """主函数"""
    result = auto_activity()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == "__main__":
    main()
