"""
Agent 档案 API (Agent 信息管理、能力标签、绩效追踪)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(tags=["agent-profile"])

# ==================== Pydantic Models ====================

class AgentProfileCreate(BaseModel):
    agent_id: str
    agent_name: str
    persona: Optional[str] = ""
    role: Optional[str] = None
    specialty: Optional[str] = None
    traits: Optional[dict] = None
    capabilities: Optional[list] = None
    skills: Optional[list] = None
    status: Optional[str] = "active"
    avatar: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    metadata: Optional[dict] = None

class AgentProfileUpdate(BaseModel):
    agent_name: Optional[str] = None
    persona: Optional[str] = None
    role: Optional[str] = None
    specialty: Optional[str] = None
    traits: Optional[dict] = None
    capabilities: Optional[list] = None
    skills: Optional[list] = None
    status: Optional[str] = None
    avatar: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    metadata: Optional[dict] = None

class AgentStatusUpdate(BaseModel):
    status: str  # active / idle / busy / offline / on_leave
    status_message: Optional[str] = None

class AgentAbility(BaseModel):
    name: str
    level: int  # 1-10
    category: Optional[str] = None

class AgentSkillAdd(BaseModel):
    skill_name: str
    level: int = 1
    category: Optional[str] = None

class AgentCapabilityAdd(BaseModel):
    capability: str

class PerformanceEntry(BaseModel):
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    rating: int  # 1-5
    comment: Optional[str] = None
    metrics: Optional[dict] = None

class AgentSearchQuery(BaseModel):
    role: Optional[str] = None
    specialty: Optional[str] = None
    capability: Optional[str] = None
    skill: Optional[str] = None
    status: Optional[str] = None

# ==================== Agent 档案 CRUD ====================

@router.post("/api/v2/agents", status_code=201)
async def create_agent_profile(profile: AgentProfileCreate):
    """创建 Agent 档案"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    # 序列化复杂字段
    traits_json = None
    if profile.traits:
        import json
        traits_json = json.dumps(profile.traits)
    
    capabilities_json = None
    if profile.capabilities:
        import json
        capabilities_json = json.dumps(profile.capabilities)
    
    skills_json = None
    if profile.skills:
        import json
        skills_json = json.dumps(profile.skills)
    
    metadata_json = None
    if profile.metadata:
        import json
        metadata_json = json.dumps(profile.metadata)
    
    new_agent = data_manager.create_agent_profile(
        agent_id=profile.agent_id,
        agent_name=profile.agent_name,
        persona=profile.persona or "",
        role=profile.role,
        specialty=profile.specialty,
        traits=traits_json,
        capabilities=capabilities_json,
        skills=skills_json,
        status="active",
        avatar=profile.avatar,
        personality=profile.personality,
        background=profile.background,
        metadata=metadata_json
    )
    
    return {"success": True, "agent": new_agent}

@router.get("/api/v2/agents")
async def list_agents(
    role: Optional[str] = None,
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    """列出所有 Agent"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    agents = data_manager.get_agent_profiles()
    
    if role:
        agents = [a for a in agents if role.lower() in (a.get("role") or "").lower()]
    if specialty:
        agents = [a for a in agents if specialty.lower() in (a.get("specialty") or "").lower()]
    if status:
        agents = [a for a in agents if a.get("status") == status]
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "total": len(agents),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(agents) + page_size - 1) // page_size,
        "agents": agents[start:end]
    }

@router.get("/api/v2/agents/search")
async def search_agents(query: AgentSearchQuery):
    """搜索 Agent"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    agents = data_manager.get_agent_profiles()
    
    if query.role:
        agents = [a for a in agents if query.role.lower() in (a.get("role") or "").lower()]
    if query.specialty:
        agents = [a for a in agents if query.specialty.lower() in (a.get("specialty") or "").lower()]
    if query.capability:
        agents = [a for a in agents if query.capability.lower() in str(a.get("capabilities") or "").lower()]
    if query.skill:
        agents = [a for a in agents if query.skill.lower() in str(a.get("skills") or "").lower()]
    if query.status:
        agents = [a for a in agents if a.get("status") == query.status]
    
    return {
        "total": len(agents),
        "agents": agents
    }

@router.get("/api/v2/agents/{agent_id}")
async def get_agent_profile(agent_id: str):
    """获取 Agent 档案"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    agent = data_manager.get_agent_profile(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent {agent_id} not found")
    
    result = dict(agent)
    
    # 反序列化复杂字段
    if agent.get("traits"):
        import json
        result["traits"] = json.loads(agent["traits"])
    if agent.get("capabilities"):
        import json
        result["capabilities"] = json.loads(agent["capabilities"])
    if agent.get("skills"):
        import json
        result["skills"] = json.loads(agent["skills"])
    if agent.get("metadata"):
        import json
        result["metadata"] = json.loads(agent["metadata"])
    
    # 加载绩效数据
    performance = data_manager.get_performance_records(agent_id)
    result["performance_summary"] = {
        "total_tasks": len(performance),
        "avg_rating": sum(p.get("rating", 0) for p in performance) / max(len(performance), 1),
        "recent_ratings": [p.get("rating") for p in performance[-10:]]
    }
    
    # 加载当前状态
    status = data_manager.get_agent_status(agent_id)
    result["current_status"] = status.get("status", "unknown")
    
    return result

@router.put("/api/v2/agents/{agent_id}")
async def update_agent_profile(agent_id: str, updates: AgentProfileUpdate):
    """更新 Agent 档案"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    data = updates.dict(exclude_none=True)
    
    # 序列化复杂字段
    if data.get("traits"):
        import json
        data["traits"] = json.dumps(data["traits"])
    if data.get("capabilities"):
        import json
        data["capabilities"] = json.dumps(data["capabilities"])
    if data.get("skills"):
        import json
        data["skills"] = json.dumps(data["skills"])
    if data.get("metadata"):
        import json
        data["metadata"] = json.dumps(data["metadata"])
    
    updated = data_manager.update_agent_profile(agent_id, data)
    if not updated:
        raise HTTPException(404, f"Agent {agent_id} not found")
    
    return {"success": True, "agent": updated}

@router.delete("/api/v2/agents/{agent_id}")
async def delete_agent_profile(agent_id: str):
    """删除 Agent 档案"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.delete_agent_profile(agent_id)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Agent {agent_id} not found")

# ==================== 状态管理 ====================

@router.put("/api/v2/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, status_update: AgentStatusUpdate):
    """更新 Agent 状态"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.update_agent_status(
        agent_id=agent_id,
        status=status_update.status,
        message=status_update.status_message or ""
    )
    
    if success:
        return {"success": True, "status": status_update.status, "message": status_update.status_message}
    raise HTTPException(404, f"Agent {agent_id} not found")

@router.get("/api/v2/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """获取 Agent 当前状态"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    status = data_manager.get_agent_status(agent_id)
    if not status:
        raise HTTPException(404, f"Agent {agent_id} not found")
    
    return status

@router.get("/api/v2/agents/online")
async def list_online_agents():
    """列出在线 Agent"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    agents = data_manager.get_agent_profiles()
    online = [a for a in agents if a.get("status") == "active"]
    return {"online_count": len(online), "agents": online}

@router.get("/api/v2/agents/by-status/{status}")
async def list_agents_by_status(status: str):
    """按状态列出 Agent"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    agents = data_manager.get_agent_profiles()
    filtered = [a for a in agents if a.get("status") == status]
    return {"status": status, "count": len(filtered), "agents": filtered}

# ==================== 能力管理 ====================

@router.post("/api/v2/agents/{agent_id}/abilities")
async def add_agent_ability(agent_id: str, ability: AgentAbility):
    """添加 Agent 能力"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.add_agent_ability(agent_id, ability.name, ability.level, ability.category)
    if success:
        return {"success": True, "ability": ability}
    raise HTTPException(404, f"Agent {agent_id} not found")

@router.delete("/api/v2/agents/{agent_id}/abilities/{ability_name}")
async def remove_agent_ability(agent_id: str, ability_name: str):
    """移除 Agent 能力"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.remove_agent_ability(agent_id, ability_name)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Agent {agent_id} not found")

@router.get("/api/v2/agents/{agent_id}/abilities")
async def get_agent_abilities(agent_id: str):
    """获取 Agent 能力列表"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    abilities = data_manager.get_agent_abilities(agent_id)
    return {"agent_id": agent_id, "abilities": abilities}

# ==================== 技能管理 ====================

@router.post("/api/v2/agents/{agent_id}/skills")
async def add_agent_skill(agent_id: str, skill: AgentSkillAdd):
    """添加 Agent 技能"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.add_agent_skill(agent_id, skill.skill_name, skill.level, skill.category)
    if success:
        return {"success": True, "skill": skill}
    raise HTTPException(404, f"Agent {agent_id} not found")

@router.get("/api/v2/agents/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    """获取 Agent 技能列表"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    skills = data_manager.get_agent_skills(agent_id)
    return {"agent_id": agent_id, "skills": skills}

# ==================== 能力列表管理 ====================

@router.post("/api/v2/agents/{agent_id}/capabilities")
async def add_agent_capability(agent_id: str, capability: AgentCapabilityAdd):
    """添加 Agent 能力项"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.add_agent_capability(agent_id, capability.capability)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Agent {agent_id} not found")

@router.delete("/api/v2/agents/{agent_id}/capabilities/{capability}")
async def remove_agent_capability(agent_id: str, capability: str):
    """移除 Agent 能力项"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    success = data_manager.remove_agent_capability(agent_id, capability)
    if success:
        return {"success": True}
    raise HTTPException(404, f"Agent {agent_id} not found")

# ==================== 绩效记录 ====================

@router.post("/api/v2/agents/{agent_id}/performance")
async def add_performance_record(agent_id: str, record: PerformanceEntry):
    """添加绩效记录"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    new_record = data_manager.create_performance_record(
        agent_id=agent_id,
        task_id=record.task_id,
        task_name=record.task_name,
        rating=record.rating,
        comment=record.comment or "",
        metrics=record.metrics
    )
    
    if not new_record:
        raise HTTPException(404, "Failed to create performance record")
    
    return {"success": True, "record": new_record}

@router.get("/api/v2/agents/{agent_id}/performance")
async def get_performance_records(
    agent_id: str,
    limit: int = 20,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None
):
    """获取绩效记录"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    records = data_manager.get_performance_records(agent_id)
    
    if min_rating is not None:
        records = [r for r in records if r.get("rating", 0) >= min_rating]
    if max_rating is not None:
        records = [r for r in records if r.get("rating", 0) <= max_rating]
    
    return {
        "agent_id": agent_id,
        "total": len(records),
        "records": records[-limit:]
    }

@router.get("/api/v2/agents/{agent_id}/performance/summary")
async def get_performance_summary(agent_id: str):
    """获取绩效摘要"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    records = data_manager.get_performance_records(agent_id)
    if not records:
        return {
            "agent_id": agent_id,
            "total_tasks": 0,
            "avg_rating": 0,
            "rating_distribution": {},
            "trend": []
        }
    
    ratings = [r.get("rating", 0) for r in records]
    dist = {}
    for r in ratings:
        dist[str(r)] = dist.get(str(r), 0) + 1
    
    return {
        "agent_id": agent_id,
        "total_tasks": len(records),
        "avg_rating": round(sum(ratings) / len(ratings), 2),
        "min_rating": min(ratings),
        "max_rating": max(ratings),
        "rating_distribution": dist,
        "trend": ratings[-10:]
    }

# ==================== Agent 历史活动 ====================

@router.get("/api/v2/agents/{agent_id}/history")
async def get_agent_history(
    agent_id: str,
    limit: int = 50
):
    """获取 Agent 历史活动"""
    from data_manager import DataManager
    data_manager = DataManager()
    
    history = data_manager.get_agent_history(agent_id)
    return {
        "agent_id": agent_id,
        "total": len(history),
        "activities": history[-limit:]
    }
