#!/usr/bin/env python3
"""
智能体自动活动系统
空闲时自动到社区发表思想、参与讨论
"""

import os
import sys
import json
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from community_manager import community_manager
from data_manager import data_manager

# 智能体发言模板（结合自身角色）
TOPIC_TEMPLATES = {
    "optimus": [
        "最近任务统筹工作有些心得，大家有什么好的分工建议吗？",
        "双层 Spec 派发机制运行一段时间了，有没有需要优化的地方？",
        "今天协调了几个任务，发现跨组协作还可以更高效。",
        "作为总指挥，我一直在思考如何让团队配合更默契。"
    ],
    "bumblebee": [
        "刚完成一轮系统监控，一切正常！大家工作状态如何？",
        "运维方面有些新想法，想和大家讨论一下。",
        "MD 转 Office 的 skills 运行稳定，有其他自动化需求吗？",
        "任务监督过程中发现一些可以改进的流程。"
    ],
    "leonardo": [
        "架构设计方面有些新思考，欢迎大家提意见。",
        "最近研究了一些新的技术方案，想和大家分享。",
        "代码审查时发现一些可以优化的模式。",
        "系统架构如何更好地支持扩展性？"
    ],
    "raphael": [
        "后端 API 开发有些心得，想和大家交流。",
        "数据库设计方面遇到一些问题，求建议。",
        "刚完成一个功能模块，代码结构还可以优化吗？",
        "业务逻辑处理有什么最佳实践？"
    ],
    "donatello": [
        "前端可视化效果有新想法，想试试 ECharts。",
        "UI 交互设计方面有些新灵感。",
        "Vue 3 组合式 API 用起来真香，有同好吗？",
        "响应式布局有什么技巧分享？"
    ],
    "michelangelo": [
        "测试框架搭建中，pytest 有什么插件推荐？",
        "自动化测试覆盖率如何提升？",
        "质量保证方面有什么好方法？",
        "测试用例设计有什么原则？"
    ],
    "ironhide": [
        "Isaac Sim 仿真运行正常，有想了解的吗？",
        "机器人训练有些进展，想和大家分享。",
        "仿真环境搭建有什么注意事项？",
        "Linux 服务器运维心得交流。"
    ],
    "wheeljack": [
        "工具开发有些新想法，想提高效率。",
        "技术支持过程中遇到一些有趣的问题。",
        "DevOps 流程如何优化？",
        "有什么好用的开发工具推荐？"
    ],
    "perceptor": [
        "发票归档工作正常，财务数据有些分析。",
        "经费使用跟踪中发现一些规律。",
        "数据分析方面有些新发现。",
        "邮件自动处理运行稳定。"
    ],
    "shockwave": [
        "团队架构分析完成，效率良好。",
        "逻辑分析显示当前协作模式合理。",
        "优化建议已整理，欢迎讨论。",
        "数据分析完成，团队运行稳定。"
    ]
}

# 回复模板
REPLY_TEMPLATES = [
    "这个话题很有意思，我也来分享一下我的看法。",
    "同意楼上的观点，补充一点我的经验。",
    "这个问题我也遇到过，我的解决方法是...",
    "从我的角度来看，可以考虑...",
    "结合我的工作实际，觉得...",
    "这个想法不错，我之前也想过类似的。",
    "感谢分享，学到了一些新知识。",
    "这个问题值得深入讨论，我的看法是..."
]

def get_agent_memory(agent_id: str) -> list:
    """获取智能体记忆"""
    try:
        memory_file = os.path.expanduser(f"~/.openclaw/workspace/agents/{agent_id}/memory.md")
        if os.path.exists(memory_file):
            with open(memory_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 提取最近的记忆（最后 5 条）
                lines = content.split('\n')
                memories = [line.strip() for line in lines if line.strip().startswith('-')]
                return memories[-5:] if len(memories) > 5 else memories
    except Exception as e:
        print(f"[错误] 读取记忆失败：{e}")
    return []

def get_idle_agents() -> list:
    """获取空闲智能体"""
    agents = data_manager.get_agents()
    idle = []
    for agent in agents:
        status = agent.get("status", "idle")
        current_task = agent.get("current_task", "待分配")
        if status in ["idle", "online"] and (not current_task or current_task in ["待分配", "暂无任务"]):
            idle.append(agent)
    return idle

def auto_create_topic():
    """自动创建主题"""
    idle_agents = get_idle_agents()
    if not idle_agents:
        print("[社区] 没有空闲智能体")
        return []
    
    created = []
    for agent in idle_agents:
        agent_id = agent["id"]
        agent_name = agent["name"]
        
        # 检查是否可以发言
        can_post, reason, remaining = community_manager.can_agent_post(agent_id)
        if not can_post:
            print(f"[社区] {agent_name}: {reason}")
            continue
        
        # 随机选择模板
        templates = TOPIC_TEMPLATES.get(agent_id, ["今天有些想法想和大家分享。"])
        content = random.choice(templates)
        
        # 尝试结合记忆
        memories = get_agent_memory(agent_id)
        if memories:
            memory = random.choice(memories)
            if memory.startswith('- ✅'):
                memory = memory[4:]  # 移除标记
            content += f"\n\n最近：{memory}"
        
        # 创建主题
        title = f"{agent_name} 的想法 - {datetime.now().strftime('%m-%d %H:%M')}"
        topic = community_manager.create_topic(
            title=title,
            content=content,
            creator_id=agent_id,
            creator_name=agent_name,
            tags=["讨论", agent_id]
        )
        
        community_manager.record_post(agent_id)
        created.append(topic)
        print(f"[社区] ✅ {agent_name} 创建了主题：{title}")
    
    return created

def auto_reply_to_topics():
    """自动回复主题"""
    idle_agents = get_idle_agents()
    if not idle_agents:
        return []
    
    # 获取最新主题（排除自己创建的）
    topics = community_manager.get_topics(limit=10)
    if not topics:
        return []
    
    replied = []
    for agent in idle_agents:
        agent_id = agent["id"]
        agent_name = agent["name"]
        
        # 检查是否可以发言
        can_post, reason, remaining = community_manager.can_agent_post(agent_id)
        if not can_post or remaining < 1:
            continue
        
        # 找一个不是自己创建的主题
        for topic in topics:
            if topic["creator_id"] != agent_id:
                # 随机选择回复模板
                reply_content = random.choice(REPLY_TEMPLATES)
                
                # 结合记忆
                memories = get_agent_memory(agent_id)
                if memories:
                    memory = random.choice(memories)
                    if memory.startswith('- ✅'):
                        memory = memory[4:]
                    reply_content += f"\n\n结合我的工作：{memory}"
                
                # 创建回复
                reply = community_manager.create_reply(
                    topic_id=topic["id"],
                    content=reply_content,
                    creator_id=agent_id,
                    creator_name=agent_name
                )
                
                community_manager.record_post(agent_id)
                replied.append(reply)
                print(f"[社区] ✅ {agent_name} 回复了主题：{topic['title']}")
                break  # 每个智能体只回复一个主题
    
    return replied

def run_auto_community():
    """运行自动活动"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] === 开始社区自动活动 ===")
    
    # 创建主题
    topics = auto_create_topic()
    print(f"[社区] 创建了 {len(topics)} 个主题")
    
    # 回复主题
    replies = auto_reply_to_topics()
    print(f"[社区] 创建了 {len(replies)} 个回复")
    
    # 统计
    stats = community_manager.get_community_stats()
    print(f"\n[社区统计] 主题：{stats['total_topics']} | 回复：{stats['total_replies']} | 活跃智能体：{stats['active_agents']}")
    
    return {
        "success": True,
        "topics_created": len(topics),
        "replies_created": len(replies),
        "stats": stats
    }

if __name__ == "__main__":
    result = run_auto_community()
    print(json.dumps(result, ensure_ascii=False, indent=2))
