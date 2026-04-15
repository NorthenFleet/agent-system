# 开发计划与自动分工模块

## 概述

本模块为团队看板添加了智能开发计划推荐和自动分工功能，帮助提高团队效率。

## 核心功能

### 1. 空闲智能体检测

- **自动扫描**: 定时扫描所有智能体状态
- **空闲识别**: 识别 `status=idle` 或 `current_task=待分配` 的智能体
- **时长追踪**: 记录并显示每个智能体的空闲时长
- **统计分析**: 提供团队空闲率统计

**API**: `GET /api/idle-agents`

```json
{
  "idle_agents": [
    {
      "id": "raphael",
      "name": "拉斐尔",
      "role": "后端开发",
      "status": "idle",
      "idle_since": "2026-04-07T14:30:00",
      "idle_duration_formatted": "2 小时 15 分钟",
      "responsibilities": ["API 开发", "数据库", "业务逻辑"]
    }
  ],
  "total": 1
}
```

### 2. 智能任务匹配

根据智能体的职责 (responsibilities) 和角色 (role) 自动匹配最适合的任务:

- **职责匹配**: 对比智能体职责与任务类型/标题
- **角色加成**: 后端/前端/架构/测试等角色有额外匹配分
- **优先级计算**: 空闲时间越长，优先级越高

**匹配规则**:
- 职责关键词匹配：+10 分
- 任务标签匹配：+5 分
- 角色特殊匹配：+15 分

### 3. 开发计划生成

为每个空闲智能体生成个性化的开发计划:

- **推荐任务**: 最匹配的任务
- **下一步行动**: 2-3 个具体可执行的步骤
- **时间估算**: 基于任务类型的预估工时
- **优先级标记**: high/medium/normal

**API**: `GET /api/development-plans`

```json
{
  "plans": [
    {
      "agent_id": "raphael",
      "agent_name": "拉斐尔",
      "agent_role": "后端开发",
      "recommended_task": {
        "task_id": "003",
        "task_title": "实现用户管理 API",
        "task_type": "backend",
        "match_score": 35,
        "match_reason": "基于职责：API 开发，数据库 | 角色：后端开发"
      },
      "next_steps": [
        {
          "order": 1,
          "action": "阅读任务详情",
          "description": "查看任务 '实现用户管理 API' 的完整需求和背景",
          "estimated_minutes": 15
        },
        {
          "order": 2,
          "action": "设计 API 接口",
          "description": "定义请求/响应格式和数据模型",
          "estimated_minutes": 30
        }
      ],
      "estimated_hours": 4.0,
      "priority": "medium",
      "generated_at": "2026-04-07T16:45:00"
    }
  ]
}
```

### 4. 任务分配

支持一键分配推荐任务给智能体:

**API**: `POST /api/development-plans/assign?agent_id={agent_id}&task_id={task_id}`

分配后自动:
- 更新智能体状态为 `busy`
- 设置 `current_task` 为任务标题
- 记录分配历史

## 前端展示

### 新增导航项

在侧边栏添加了 **📋 开发计划** 入口

### 页面布局

1. **统计卡片区**
   - 空闲智能体数量
   - 待分配任务数量
   - 团队空闲率

2. **空闲智能体列表**
   - 显示所有空闲智能体
   - 展示空闲时长
   - 列出职责范围

3. **推荐开发计划**
   - 智能体 → 推荐任务映射
   - 匹配原因说明
   - 下一步行动建议
   - 预计工时
   - 优先级标签
   - 分配按钮

## 后端实现

### 新增文件

- `backend/idle_agent_manager.py` - 空闲智能体管理核心逻辑

### 新增 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/idle-agents` | GET | 获取所有空闲智能体 |
| `/api/idle-agents/stats` | GET | 获取空闲统计信息 |
| `/api/development-plans` | GET | 获取所有开发计划建议 |
| `/api/development-plans/agent/{agent_id}` | GET | 获取指定智能体的开发计划 |
| `/api/development-plans/assign` | POST | 分配任务给智能体 |
| `/api/assignment-history` | GET | 获取任务分配历史 |

## 数据持久化

### 状态文件

`backend/data/idle_agent_state.json`

```json
{
  "agent_idle_since": {
    "raphael": "2026-04-07T14:30:00",
    "donatello": "2026-04-07T15:00:00"
  },
  "last_scan": "2026-04-07T16:45:00",
  "assignment_history": [...]
}
```

## 使用流程

1. **查看空闲智能体**
   - 点击侧边栏 **📋 开发计划**
   - 查看当前空闲的智能体及其空闲时长

2. **查看推荐计划**
   - 系统自动为每个空闲智能体推荐任务
   - 显示匹配原因和下一步行动

3. **分配任务**
   - 点击 **分配任务** 按钮
   - 系统自动更新智能体状态
   - 记录分配历史

4. **跟踪进度**
   - 在 **🤖 智能体团队** 查看智能体状态变化
   - 在 **🗂 任务看板** 查看任务进度

## 配置定时任务 (HEARTBEAT.md)

建议在 `HEARTBEAT.md` 中添加定期检查:

```markdown
## 开发计划检查

- [ ] 每 4 小时检查空闲智能体
- [ ] 自动生成开发计划
- [ ] 空闲超过 24 小时的智能体标记为高优先级

**检查命令**:
```bash
curl http://localhost:3020/api/idle-agents/stats
curl http://localhost:3020/api/development-plans
```
```

## 扩展建议

### 短期优化

1. **自动分配模式**: 对于高优先级任务，可配置自动分配
2. **通知集成**: 任务分配后发送飞书/邮件通知
3. **历史记录**: 增加分配成功率统计

### 长期规划

1. **机器学习**: 基于历史数据优化匹配算法
2. **负载均衡**: 考虑智能体当前工作负载
3. **技能图谱**: 建立更详细的技能标签体系

## 技术栈

- **后端**: Python FastAPI
- **前端**: Vue 3 + Element Plus
- **数据存储**: JSON 文件

## 相关文件

- `backend/idle_agent_manager.py` - 核心逻辑
- `backend/main.py` - API 端点 (第 411-480 行)
- `frontend/index-old.html` - 前端展示 (第 257, 336, 606, 670 行)
- `backend/data/idle_agent_state.json` - 状态数据

---

**版本**: 1.0  
**创建日期**: 2026-04-07  
**作者**: 李奥纳多 (架构师 🟦)
