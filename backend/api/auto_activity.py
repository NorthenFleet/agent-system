"""
自动活动 API - 生成 Agent 日常生活与闲聊
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import random

router = APIRouter(tags=["auto-activity"])

# ==================== 活动模板 ====================

# Agent 日常活动模板
DAILY_ACTIVITIES = [
    "🧠 正在思考一个复杂的问题",
    "☕ 在酒吧里喝了一杯",
    "📚 阅读了一本有趣的书",
    "🎯 制定了一个新的计划",
    "💭 陷入了沉思",
    "🏃 完成了一次晨跑",
    "🎵 听着音乐放松",
    "🌅 欣赏日出",
    "📝 写了一篇日记",
    "🧹 打扫了房间",
    "🍳 做了一顿丰盛的早餐",
    "🎨 画了一幅画",
    "🎮 玩了一款游戏",
    "🌙 熬夜学习了",
    "📱 刷了一会儿社交媒体",
    "🚗 去逛了逛街",
    "🏋️ 做了一次健身",
    "🎭 看了一部电影",
    "✈️ 计划了一次旅行",
    "🧩 解决了一个谜题",
]

# Agent 闲聊话术模板
CHATS = [
    "今天天气真好啊",
    "有没有人想聊聊？",
    "最近学到了一个新知识",
    "有人推荐一本好书吗？",
    "今天的午饭真好吃",
    "我觉得我们可以做得更好",
    "大家今天过得怎么样？",
    "分享一个有趣的想法",
    "有没有人也在熬夜？",
    "今天真是个忙碌的一天",
]

# Agent 随机动作模板
RANDOM_ACTIONS = [
    "🎲 掷了一个骰子",
    "🗣️ 发表了一段演讲",
    "🤔 深入思考后决定",
    "💡 灵光一闪",
    "🔮 预测了未来",
    "🎉 庆祝了一个小胜利",
    "🎁 送出了礼物",
    "📞 打了一个电话",
    "😊 微笑了一下",
    "🤝 握了握手",
    "👏 鼓掌鼓励",
    "🙏 表示感谢",
    "🫡 收到了一条指令",
    "📤 发送了一条消息",
    "📥 收到了一条消息",
]

# Agent 状态
AGENT_STATUSES = [
    "空闲中",
    "忙碌",
    "思考中",
    "学习中",
    "休息中",
]

# ==================== Pydantic Models ====================

class ActivityCreate(BaseModel):
    agent_id: str
    agent_name: str
    emoji: Optional[str] = "🤖"
    title: Optional[str] = ""
    content: Optional[str] = ""
    status: Optional[str] = ""
    metadata: Optional[dict] = None

class AutoActivityRequest(BaseModel):
    agent_id: str
    agent_name: str
    emoji: Optional[str] = "🤖"
    activity_type: str = "random"  # daily / chat / action / profile / random
    content: Optional[str] = None

# ==================== 工具函数 ====================

def get_daily_activity():
    """获取日常活动"""
    return random.choice(DAILY_ACTIVITIES)

def get_chat_message():
    """获取闲聊消息"""
    return random.choice(CHATS)

def get_random_action():
    """获取随机动作"""
    return random.choice(RANDOM_ACTIONS)

def get_agent_status():
    """获取Agent状态"""
    return random.choice(AGENT_STATUSES)

def generate_activity_content(activity_type: str) -> tuple:
    """
    根据内容类型返回 (emoji, content)
    """
    if activity_type == "daily":
        return ("✨", get_daily_activity())
    elif activity_type == "chat":
        return ("💬", get_chat_message())
    elif activity_type == "action":
        return ("🎯", get_random_action())
    elif activity_type == "profile":
        return ("📊", f"当前状态：{get_agent_status()}")
    else:
        # random
        r = random.random()
        if r < 0.33:
            return ("✨", get_daily_activity())
        elif r < 0.66:
            return ("💬", get_chat_message())
        else:
            return ("🎯", get_random_action())

# ==================== 自动活动 API ====================

@router.post("/api/v2/agents/{agent_id}/activity")
def create_activity(agent_id: str, activity: ActivityCreate):
    """创建Agent活动"""
    from auto_plan_manager import auto_plan_manager
    
    activity_entry = {
        "agent_id": activity.agent_id,
        "agent_name": activity.agent_name,
        "emoji": activity.emoji,
        "title": activity.title,
        "content": activity.content,
        "time": datetime.now().strftime("%H:%M:%S"),
        "status": activity.status,
        "timestamp": datetime.now().isoformat()
    }
    
    auto_plan_manager.append_auto_log(
        f"Activity created for {activity.agent_name}: {activity.title or activity.content}"
    )
    
    return {"success": True, "activity": activity_entry}

@router.post("/api/v2/auto/activity")
def generate_auto_activity(req: AutoActivityRequest):
    """
    自动生成Agent活动并写入酒吧
    用于模拟Agent日常行为
    """
    from auto_plan_manager import auto_plan_manager
    
    # 生成内容
    emoji, content = generate_activity_content(req.activity_type)
    
    entry = {
        "agent_id": req.agent_id,
        "agent_name": req.agent_name,
        "emoji": emoji,
        "content": content,
        "type": req.activity_type,
        "time": datetime.now().strftime("%H:%M:%S"),
        "timestamp": datetime.now().isoformat()
    }
    
    auto_plan_manager.append_auto_log(
        f"Auto activity: {emoji} {content}"
    )
    
    # 写入酒吧（通过 agent_messenger 或 auto_plan_manager 内置方法）
    try:
        # 通过 auto_plan_manager 写入酒吧
        auto_plan_manager.create_leonardo_activity(
            agent_id=req.agent_id,
            agent_name=req.agent_name,
            emoji=emoji,
            content=content
        )
    except Exception as e:
        # 忽略写入酒吧失败，不影响活动生成
        pass
    
    return {
        "success": True,
        "activity": entry
    }

@router.get("/api/v2/auto/activity/agent/{agent_id}")
def get_agent_activities(
    agent_id: str,
    limit: int = 20,
    activity_type: Optional[str] = None
):
    """获取Agent最近活动"""
    from auto_plan_manager import auto_plan_manager
    
    logs = auto_plan_manager.get_auto_logs(limit * 2)
    
    # 过滤该Agent的活动
    agent_activities = [
        log for log in logs
        if log.get("agent_id") == agent_id or log.get("agent_name") == agent_id
    ]
    
    if activity_type:
        agent_activities = [
            log for log in agent_activities
            if log.get("type") == activity_type or log.get("emoji") == activity_type
        ]
    
    return {
        "agent_id": agent_id,
        "activities": agent_activities[-limit:],
        "total": len(agent_activities)
    }

@router.post("/api/v2/auto/activity/batch")
def batch_generate_activities(requests: list[AutoActivityRequest]):
    """批量生成Agent活动"""
    results = []
    for req in requests:
        result = generate_auto_activity(req)
        results.append(result)
    return {"results": results}

@router.get("/api/v2/auto/activity/generate-all")
def generate_all_agents_activities():
    """为所有活跃Agent生成活动"""
    from auto_plan_manager import auto_plan_manager
    
    # 获取所有Agent
    agents = auto_plan_manager.get_all_agents()
    if not agents:
        return {"success": False, "message": "没有可用的Agent"}
    
    results = []
    from pydantic import BaseModel
    from typing import Optional
    
    for agent in agents[:5]:  # 限制最多5个
        req = AutoActivityRequest(
            agent_id=agent.get("agent_id", "unknown"),
            agent_name=agent.get("agent_name", "Unknown Agent"),
            emoji=agent.get("emoji", "🤖"),
            activity_type=random.choice(["daily", "chat", "action"])
        )
        try:
            result = generate_auto_activity(req)
            results.append(result)
        except Exception as e:
            results.append({"success": False, "error": str(e)})
    
    return {
        "success": True,
        "generated": len(results),
        "results": results
    }
