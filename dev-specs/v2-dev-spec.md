# Dev Spec — 看板 V2 增强

> 版本: v2.0 | 状态: Dev Spec | 创建: 2026-06-25  
> 提出: 擎天柱 | 审批: 孙总  
> 架构师: 🟦 李奥纳多 | 执行: 🟥 拉斐尔 + 🟪 多纳泰罗 + 🟧 米开朗基罗

---

## 一、系统架构设计

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3 SPA)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ 登录页   │  │ 仪表盘   │  │ 任务管理 │  │ Agent 监控面板   │ │
│  │ /login   │  │ /        │  │ /tasks   │  │ /agents          │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘ │
│       │              │             │                  │           │
│  ┌────▼──────────────────────────────────────────────▼───────┐   │
│  │              API Client (Axios)                            │   │
│  │  - JWT Token 自动附加   - 请求/响应拦截                    │   │
│  └────────────────────────┬──────────────────────────────────┘   │
│                           │ HTTP + WebSocket                     │
└───────────────────────────┼──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    后端 (FastAPI)                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ 认证中间件       │  │ 路由层 (Routers) │  │ 服务层        │  │
│  │                  │  │                  │  │               │  │
│  │ • JWT 验证       │  │ • auth_router    │  │ • auth_service│  │
│  │ • 权限检查       │  │ • tasks_router   │  │ • task_service│  │
│  │ • API Key 兼容   │  │ • agents_router  │  │ • agent_service│ │
│  │                  │  │ • users_router   │  │ • user_service│  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘  │
│           │                     │                     │          │
│  ┌────────▼─────────────────────▼─────────────────────▼───────┐  │
│  │                   业务逻辑层 (Managers)                     │  │
│  │                                                            │  │
│  │  • data_manager      (兼容层，桥接 JSON→DB)                │  │
│  │  • openclaw_integration  (Agent 状态同步)                  │  │
│  │  • websocket_manager     (实时推送)                        │  │
│  └────────────────────────┬───────────────────────────────────┘  │
│                           │                                      │
│  ┌────────────────────────▼───────────────────────────────────┐  │
│  │                数据访问层 (ORM)                              │  │
│  │                                                            │  │
│  │  • SQLAlchemy 2.0 (async)                                  │  │
│  │  • Users / Tasks / TaskComments / AgentHeartbeats          │  │
│  └────────────────────────┬───────────────────────────────────┘  │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                  ┌─────────▼─────────┐
                  │   PostgreSQL       │
                  │   localhost:5432   │
                  └───────────────────┘
```

### 1.2 数据流

```
Agent (OpenClaw) ──heartbeat──▶ AgentHeartbeat API ──▶ DB
                                      │
                                      ▼
                              WebSocket Manager ──▶ 前端实时推送
                                      │
                                      ▼
                              Agent 监控面板 (状态卡片/指示灯)

用户 ──登录──▶ Auth API ──▶ JWT Token ──▶ 后续请求携带 Bearer Token
              │
              ▼
      角色权限检查 ──▶ admin/viewer/agent 不同权限范围

管理员 ──创建任务──▶ Task CRUD API ──▶ DB ──▶ WebSocket 推送 ──▶ 前端更新
```

### 1.3 模块关系

| 模块 | 依赖 | 被依赖 |
|------|------|--------|
| 认证 (auth) | 无 | 所有 API 路由 |
| 任务 (tasks) | auth, DB | 前端任务视图, 甘特图 |
| Agent 监控 (agents) | auth, DB, OpenClaw | 前端监控面板, WebSocket |
| 用户 (users) | auth, DB | 管理员用户管理 |
| WebSocket | auth | 前端实时推送 |

---

## 二、数据库设计

### 2.1 技术选型

- **ORM**: SQLAlchemy 2.0 (async)
- **连接池**: asyncpg
- **迁移**: Alembic
- **现有 PostgreSQL**: localhost:5432, 需确认服务状态

### 2.2 SQL DDL

```sql
-- ============================================
-- 用户表 (users)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(64)     NOT NULL UNIQUE,
    password_hash   VARCHAR(255)    NOT NULL,
    display_name    VARCHAR(128)    NOT NULL,
    role            VARCHAR(20)     NOT NULL DEFAULT 'viewer',  -- admin | viewer | agent
    email           VARCHAR(255)    DEFAULT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ     DEFAULT NULL
);

-- 默认管理员账号 (密码: admin123, 首次登录后必须修改)
INSERT INTO users (username, password_hash, display_name, role)
VALUES ('admin', '$2b$12$<bcrypt_hash>', '管理员', 'admin')
ON CONFLICT (username) DO NOTHING;

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

-- ============================================
-- 任务表 (tasks) — 从文件迁移到 DB
-- ============================================
CREATE TABLE IF NOT EXISTS tasks (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(64)     NOT NULL UNIQUE,  -- 如 "task-001"
    title           VARCHAR(500)    NOT NULL,
    description     TEXT            DEFAULT '',
    type            VARCHAR(32)     DEFAULT 'general',  -- fullstack | backend | frontend | testing
    status          VARCHAR(32)     NOT NULL DEFAULT 'pending',  -- pending | assigned | in_progress | review | testing | done | archived
    priority        VARCHAR(20)     DEFAULT 'medium',  -- low | medium | high | critical
    assignee        VARCHAR(64)     DEFAULT NULL,  -- Agent ID
    progress        INTEGER         NOT NULL DEFAULT 0,  -- 0-100
    source          VARCHAR(20)     DEFAULT 'manual',  -- manual | loop | cloud
    sprint          INTEGER         DEFAULT NULL,
    dev_spec        VARCHAR(500)    DEFAULT NULL,
    created_by      VARCHAR(64)     DEFAULT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ     DEFAULT NULL,
    due_date        TIMESTAMPTZ     DEFAULT NULL,
    start_date      TIMESTAMPTZ     DEFAULT NULL,
    tags            TEXT[]          DEFAULT '{}',
    parent_task_id  VARCHAR(64)     DEFAULT NULL,  -- 父任务 ID
    CONSTRAINT chk_progress CHECK (progress >= 0 AND progress <= 100)
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assignee ON tasks(assignee);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_sprint ON tasks(sprint);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);

-- ============================================
-- 任务变更历史 (task_history)
-- ============================================
CREATE TABLE IF NOT EXISTS task_history (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(64)     NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    field           VARCHAR(64)     NOT NULL,  -- 变更的字段
    old_value       TEXT            DEFAULT NULL,
    new_value       TEXT            DEFAULT NULL,
    changed_by      VARCHAR(64)     DEFAULT NULL,
    changed_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_history_task ON task_history(task_id);

-- ============================================
-- 任务评论 (task_comments)
-- ============================================
CREATE TABLE IF NOT EXISTS task_comments (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(64)     NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    user_id         INTEGER         REFERENCES users(id) ON DELETE SET NULL,
    agent_id        VARCHAR(64)     DEFAULT NULL,  -- 如果是 Agent 发的
    content         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_comments_task ON task_comments(task_id);

-- ============================================
-- Agent 心跳记录 (agent_heartbeats)
-- ============================================
CREATE TABLE IF NOT EXISTS agent_heartbeats (
    id              SERIAL PRIMARY KEY,
    agent_id        VARCHAR(64)     NOT NULL,
    agent_name      VARCHAR(128)    NOT NULL,
    status          VARCHAR(32)     NOT NULL,  -- online | busy | idle | offline
    current_task    VARCHAR(500)    DEFAULT NULL,
    cpu_usage       FLOAT           DEFAULT NULL,
    memory_usage    FLOAT           DEFAULT NULL,
    task_queue_len  INTEGER         DEFAULT 0,
    metadata        JSONB           DEFAULT '{}',
    heartbeat_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_heartbeats_agent ON agent_heartbeats(agent_id);
CREATE INDEX idx_heartbeats_time ON agent_heartbeats(heartbeat_at DESC);

-- ============================================
-- Agent 状态变更历史 (agent_status_history)
-- ============================================
CREATE TABLE IF NOT EXISTS agent_status_history (
    id              SERIAL PRIMARY KEY,
    agent_id        VARCHAR(64)     NOT NULL,
    from_status     VARCHAR(32)     DEFAULT NULL,
    to_status       VARCHAR(32)     NOT NULL,
    current_task    VARCHAR(500)    DEFAULT NULL,
    triggered_by    VARCHAR(64)     DEFAULT NULL,
    changed_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_history_agent ON agent_status_history(agent_id);
CREATE INDEX idx_agent_history_time ON agent_status_history(changed_at DESC);

-- ============================================
-- 任务模板 (task_templates)
-- ============================================
CREATE TABLE IF NOT EXISTS task_templates (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200)    NOT NULL,
    description     TEXT            DEFAULT '',
    template_data   JSONB           NOT NULL,  -- 包含 title, type, priority, tags 等默认值
    created_by      INTEGER         REFERENCES users(id),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

### 2.3 数据迁移方案

**从 JSON 文件 → PostgreSQL**:

| 源文件 | 目标表 | 策略 |
|--------|--------|------|
| `data/tasks.json` | `tasks` | 读取 JSON → 批量 INSERT，保留原始 task_id |
| `data/agents.json` | `agent_heartbeats` (初始) | 首次心跳初始化 |
| `~/.openclaw/.../queue.json` | `tasks` (Loop 任务) | 合并入 tasks 表，source='loop' |

---

## 三、API 详细设计

### 3.1 认证模块 (Auth)

#### POST `/api/auth/login` — 用户登录

**Request**:
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response 200**:
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "display_name": "管理员",
    "role": "admin"
  }
}
```

**Response 401**:
```json
{
  "error": "invalid_credentials",
  "detail": "用户名或密码错误"
}
```

#### POST `/api/auth/logout` — 用户登出

**Headers**: `Authorization: Bearer <token>`

**Response 200**: `{"message": "已登出"}`

#### GET `/api/auth/me` — 当前用户信息

**Headers**: `Authorization: Bearer <token>`

**Response 200**:
```json
{
  "id": 1,
  "username": "admin",
  "display_name": "管理员",
  "role": "admin",
  "is_active": true,
  "last_login_at": "2026-06-25T08:00:00+08:00"
}
```

### 3.2 任务模块 (Tasks)

#### GET `/api/tasks` — 任务列表（增强版）

**Query Params**:
| 参数 | 类型 | 说明 |
|------|------|------|
| status | string | 过滤状态: pending/assigned/in_progress/review/testing/done/archived |
| priority | string | 过滤优先级: low/medium/high/critical |
| assignee | string | 过滤负责人 |
| sprint | int | 过滤 Sprint |
| search | string | 关键词搜索 (title, description) |
| page | int | 页码 (默认 1) |
| page_size | int | 每页数量 (默认 20, 最大 100) |
| sort_by | string | 排序字段: created_at/updated_at/priority/due_date (默认 created_at) |
| sort_order | string | asc/desc (默认 desc) |

**Response 200**:
```json
{
  "tasks": [
    {
      "id": 1,
      "task_id": "task-001",
      "title": "部署智能体团队信息看板",
      "description": "...",
      "type": "fullstack",
      "status": "done",
      "priority": "high",
      "assignee": "donatello",
      "progress": 100,
      "source": "loop",
      "sprint": 1,
      "tags": ["看板", "v1"],
      "parent_task_id": null,
      "created_at": "2026-06-24T10:00:00+08:00",
      "updated_at": "2026-06-24T22:28:26+08:00",
      "completed_at": "2026-06-24T22:28:26+08:00",
      "due_date": null,
      "start_date": "2026-06-24T10:00:00+08:00",
      "comment_count": 3
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

#### POST `/api/tasks` — 创建任务

**Headers**: `Authorization: Bearer <token>` (role: admin/agent)

**Request**:
```json
{
  "title": "实现 WebSocket 实时推送",
  "description": "完善 WebSocket 推送逻辑...",
  "type": "backend",
  "priority": "high",
  "assignee": "raphael",
  "sprint": 2,
  "tags": ["实时", "WebSocket"],
  "due_date": "2026-06-27T18:00:00+08:00",
  "parent_task_id": null
}
```

**Response 201**:
```json
{
  "id": 43,
  "task_id": "task-043",
  "title": "实现 WebSocket 实时推送",
  "status": "pending",
  "progress": 0,
  "created_at": "2026-06-25T10:00:00+08:00"
}
```

#### PUT `/api/tasks/{task_id}` — 更新任务

**Headers**: `Authorization: Bearer <token>` (role: assignee 或 admin)

**Request** (部分更新):
```json
{
  "status": "in_progress",
  "progress": 30,
  "assignee": "raphael"
}
```

**Response 200**: 更新后的任务对象

**自动行为**:
- 状态变更 → 自动写入 `task_history`
- 状态 → done → 自动设置 `completed_at`
- 状态变更 → 触发 WebSocket 推送

#### DELETE `/api/tasks/{task_id}` — 删除任务

**Headers**: `Authorization: Bearer <token>` (role: admin only)

**Response 200**: `{"message": "任务已删除", "task_id": "task-043"}`

#### POST `/api/tasks/{task_id}/assign` — 分配任务

**Request**:
```json
{
  "assignee": "raphael",
  "comment": "拉斐尔负责后端部分"
}
```

**Response 200**: 更新后的任务对象

#### POST `/api/tasks/{task_id}/comment` — 添加评论

**Request**:
```json
{
  "content": "已完成数据库迁移部分"
}
```

**Response 201**:
```json
{
  "id": 1,
  "task_id": "task-001",
  "user_id": 1,
  "content": "已完成数据库迁移部分",
  "created_at": "2026-06-25T10:30:00+08:00"
}
```

#### GET `/api/tasks/{task_id}/comments` — 获取评论列表

**Response 200**:
```json
{
  "comments": [
    {
      "id": 1,
      "task_id": "task-001",
      "user": {"id": 1, "username": "admin", "display_name": "管理员"},
      "content": "已完成数据库迁移部分",
      "created_at": "2026-06-25T10:30:00+08:00"
    }
  ],
  "total": 1
}
```

#### GET `/api/tasks/{task_id}` — 任务详情

**Response 200**: 完整任务对象 + 评论列表 + 变更历史

#### GET `/api/tasks/stats` — 任务统计

**Response 200**:
```json
{
  "total": 42,
  "by_status": {
    "pending": 5,
    "assigned": 8,
    "in_progress": 12,
    "review": 3,
    "testing": 4,
    "done": 8,
    "archived": 2
  },
  "by_priority": {
    "critical": 2,
    "high": 10,
    "medium": 20,
    "low": 10
  },
  "by_assignee": {
    "raphael": 15,
    "donatello": 12,
    "michelangelo": 8,
    null: 7
  },
  "completion_rate": 19.0,
  "sprint_progress": {
    "sprint_1": {"total": 10, "done": 10, "rate": 100},
    "sprint_2": {"total": 32, "done": 0, "rate": 0}
  }
}
```

#### GET `/api/tasks/gantt` — 甘特图数据

**Query Params**: `sprint=2` (可选)

**Response 200**:
```json
{
  "tasks": [
    {
      "task_id": "task-002",
      "title": "看板 Sprint 2 核心优化",
      "start_date": "2026-06-25T06:00:00+08:00",
      "due_date": "2026-06-27T18:00:00+08:00",
      "progress": 30,
      "assignee": "raphael",
      "status": "in_progress",
      "subtasks": [
        {"task_id": "task-002-1", "title": "统一数据源", "assignee": "raphael", "status": "done", "start_date": "2026-06-25", "due_date": "2026-06-25"},
        {"task_id": "task-002-2", "title": "WebSocket 推送", "assignee": "raphael", "status": "in_progress", "start_date": "2026-06-25", "due_date": "2026-06-26"}
      ]
    }
  ]
}
```

#### GET/POST `/api/tasks/templates` — 任务模板 CRUD

### 3.3 Agent 监控模块

#### POST `/api/agents/{agent_id}/heartbeat` — 心跳上报

**Headers**: `Authorization: Bearer <token>` (role: agent)

**Request**:
```json
{
  "status": "busy",
  "current_task": "task-002-1",
  "cpu_usage": 45.2,
  "memory_usage": 62.1,
  "task_queue_len": 3,
  "metadata": {"model": "qwen3.6-plus", "thinking": "off"}
}
```

**Response 200**:
```json
{
  "agent_id": "raphael",
  "status": "busy",
  "next_heartbeat_in": 30,
  "message": "心跳已记录"
}
```

#### GET `/api/agents/live` — 实时 Agent 状态

**Response 200**:
```json
{
  "agents": [
    {
      "agent_id": "raphael",
      "agent_name": "拉斐尔",
      "status": "busy",
      "current_task": "task-002-1",
      "last_heartbeat": "2026-06-25T10:00:00+08:00",
      "heartbeat_age_seconds": 15,
      "health": "healthy",  -- healthy | warning | critical | offline
      "cpu_usage": 45.2,
      "memory_usage": 62.1
    }
  ],
  "total": 12,
  "online": 8,
  "busy": 5,
  "idle": 3,
  "offline": 4
}
```

#### GET `/api/agents/{agent_id}/history` — 状态历史

**Query Params**: `limit=50`, `hours=24`

**Response 200**:
```json
{
  "agent_id": "raphael",
  "history": [
    {
      "from_status": "idle",
      "to_status": "busy",
      "current_task": "task-002-1",
      "triggered_by": "leonardo",
      "changed_at": "2026-06-25T09:00:00+08:00"
    }
  ],
  "total": 128
}
```

#### GET `/api/agents/{agent_id}/tasks` — Agent 关联任务

**Response 200**: 该 Agent 所有任务列表（用于甘特图联动）

### 3.4 用户管理模块

#### GET `/api/users` — 用户列表 (admin only)

**Response 200**:
```json
{
  "users": [
    {"id": 1, "username": "admin", "display_name": "管理员", "role": "admin", "is_active": true, "last_login_at": "2026-06-25T08:00:00+08:00"},
    {"id": 2, "username": "leonardo", "display_name": "李奥纳多", "role": "agent", "is_active": true, "last_login_at": null}
  ],
  "total": 2
}
```

#### POST `/api/users` — 创建用户 (admin only)

**Request**:
```json
{
  "username": "raphael",
  "password": "Raphael@2026",
  "display_name": "拉斐尔",
  "role": "agent"
}
```

**Response 201**:
```json
{
  "id": 3,
  "username": "raphael",
  "display_name": "拉斐尔",
  "role": "agent"
}
```

#### PUT `/api/users/{user_id}` — 更新用户 (admin only)

**Request**:
```json
{
  "role": "viewer",
  "is_active": false
}
```

#### POST `/api/users/{user_id}/reset-password` — 重置密码 (admin only)

### 3.5 WebSocket 推送

#### WS `/ws/agents` — Agent 状态实时推送

**连接**: `ws://host:port/ws/agents?token=<jwt>`

**服务器推送消息格式**:

```json
// Agent 状态变更
{
  "type": "agent_status_change",
  "data": {
    "agent_id": "raphael",
    "agent_name": "拉斐尔",
    "from_status": "idle",
    "to_status": "busy",
    "current_task": "task-002-1",
    "timestamp": "2026-06-25T10:00:00+08:00"
  }
}

// 任务状态变更
{
  "type": "task_status_change",
  "data": {
    "task_id": "task-002-1",
    "from_status": "pending",
    "to_status": "in_progress",
    "assignee": "raphael",
    "timestamp": "2026-06-25T10:00:00+08:00"
  }
}

// 心跳更新
{
  "type": "heartbeat_update",
  "data": {
    "agent_id": "raphael",
    "status": "busy",
    "cpu_usage": 45.2,
    "memory_usage": 62.1,
    "heartbeat_age_seconds": 15,
    "timestamp": "2026-06-25T10:00:30+08:00"
  }
}

// 新评论
{
  "type": "task_comment",
  "data": {
    "task_id": "task-001",
    "comment_id": 1,
    "content": "已完成",
    "user": "admin",
    "timestamp": "2026-06-25T10:30:00+08:00"
  }
}
```

---

## 四、前端架构

### 4.1 组件拆分方案

**从单文件 `complete.html` 重构为模块化 Vue 3 组件**:

```
frontend/
├── index.html                    ← SPA 入口
├── src/
│   ├── main.js                   ← Vue 应用入口
│   ├── App.vue                   ← 根组件 (侧边栏 + 顶栏 + router-view)
│   ├── router/
│   │   └── index.js              ← 路由配置 + 权限守卫
│   ├── store/                    ← Pinia 状态管理
│   │   ├── index.js
│   │   ├── auth.js               ← 用户认证状态
│   │   ├── tasks.js              ← 任务状态 + CRUD
│   │   ├── agents.js             ← Agent 实时状态
│   │   └── ui.js                 ← UI 状态 (侧边栏/通知)
│   ├── views/                    ← 页面级组件
│   │   ├── Login.vue             ← 登录页
│   │   ├── Dashboard.vue         ← 仪表盘
│   │   ├── TaskList.vue          ← 任务列表页
│   │   ├── TaskKanban.vue        ← 看板视图
│   │   ├── TaskGantt.vue         ← 甘特图视图
│   │   ├── AgentMonitor.vue      ← Agent 监控面板
│   │   └── UserManagement.vue    ← 用户管理 (admin)
│   ├── components/               ← 可复用组件
│   │   ├── common/
│   │   │   ├── StatCard.vue      ← 统计卡片
│   │   │   ├── StatusBadge.vue   ← 状态标签
│   │   │   ├── ProgressBar.vue   ← 进度条
│   │   │   └── EmptyState.vue    ← 空状态
│   │   ├── tasks/
│   │   │   ├── TaskCard.vue      ← 任务卡片
│   │   │   ├── TaskDetail.vue    ← 任务详情面板 (右侧滑出)
│   │   │   ├── TaskForm.vue      ← 创建/编辑表单
│   │   │   ├── TaskComment.vue   ← 评论组件
│   │   │   ├── KanbanColumn.vue  ← 看板列
│   │   │   └── TaskGanttChart.vue← 甘特图组件 (ECharts)
│   │   ├── agents/
│   │   │   ├── AgentCard.vue     ← Agent 状态卡片
│   │   │   ├── AgentDetail.vue   ← Agent 详情面板
│   │   │   ├── HeartbeatIndicator.vue ← 心跳指示灯
│   │   │   └── AgentTaskTimeline.vue  ← Agent 任务时间线
│   │   └── layout/
│   │       ├── Sidebar.vue       ← 侧边栏导航
│   │       ├── TopBar.vue        ← 顶栏
│   │       └── UserMenu.vue      ← 用户菜单
│   ├── api/
│   │   ├── client.js             ← Axios 实例 (拦截器 + JWT)
│   │   ├── auth.js               ← 认证 API
│   │   ├── tasks.js              ← 任务 API
│   │   ├── agents.js             ← Agent API
│   │   └── users.js              ← 用户 API
│   └── styles/
│       ├── main.css              ← 全局样式
│       └── variables.css         ← CSS 变量 (保持现有主题)
├── package.json
└── vite.config.js                ← Vite 构建配置
```

### 4.2 路由设计

```javascript
// router/index.js
const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: App,
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'dashboard', component: Dashboard },
      { path: 'tasks', name: 'tasks', component: TaskList },
      { path: 'tasks/kanban', name: 'kanban', component: TaskKanban },
      { path: 'tasks/gantt', name: 'gantt', component: TaskGantt },
      { path: 'agents', name: 'agents', component: AgentMonitor },
      { path: 'users', name: 'users', component: UserManagement, meta: { requiresAdmin: true } },
    ]
  }
]

// 路由守卫
router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return next('/login')
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return next('/')  // 无权访问，回首页
  }
  next()
})
```

### 4.3 状态管理 (Pinia)

```javascript
// store/auth.js
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: localStorage.getItem('jwt_token') || null,
    isAuthenticated: false
  }),
  actions: {
    async login(username, password) { ... },
    async logout() { ... },
    async fetchMe() { ... }
  }
})

// store/tasks.js
export const useTasksStore = defineStore('tasks', {
  state: () => ({
    tasks: [],
    total: 0,
    filters: { status: null, priority: null, assignee: null, search: '' },
    pagination: { page: 1, pageSize: 20 },
    selectedTask: null,
    loading: false
  }),
  actions: {
    async fetchTasks() { ... },
    async createTask(data) { ... },
    async updateTask(taskId, data) { ... },
    async deleteTask(taskId) { ... },
    async addComment(taskId, content) { ... },
    applyFilter(filters) { ... }
  }
})

// store/agents.js
export const useAgentsStore = defineStore('agents', {
  state: () => ({
    agents: [],
    wsConnected: false,
    ws: null,
    notifications: []
  }),
  actions: {
    async fetchAgents() { ... },
    connectWebSocket(token) { ... },
    handleWsMessage(data) { ... },
    addNotification(msg) { ... }
  }
})
```

### 4.4 从 HTML 到 Vite 的迁移策略

**渐进式迁移，不破坏现有功能**:

1. **阶段 A**: 保持 `complete.html` 运行，新增 `/v2/` 路由指向 Vue 3 应用
2. **阶段 B**: V2 功能在 Vue 3 中实现，通过 API 与后端交互
3. **阶段 C**: V2 功能成熟后，将 `/v2/` 替换为 `/`
4. **阶段 D**: 归档 `complete.html` 到 `archived/`

---

## 五、甘特图联动设计

### 5.1 甘特图组件

**技术**: ECharts (已有) + 自定义甘特图渲染

**数据格式**: 见 `GET /api/tasks/gantt` API 设计

**交互**:
```
┌─────────────────────────────────────────────────────┐
│ 甘特图 (ECharts)                                     │
│                                                      │
│ 任务A  ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░             │
│ 任务B        ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░              │
│ 任务C                    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓             │
│         │ 6/25 │ 6/26 │ 6/27 │ 6/28 │ 6/29          │
└────────────────────┬────────────────────────────────┘
                     │ 点击任务条
                     ▼
┌─────────────────────────────────────────────────────┐
│ 任务详情面板 (右侧滑出)                               │
│ ┌──────────────────────────────────────────────┐    │
│ │ task-002-1 | 统一数据源 | ✅ done             │    │
│ │ 负责人: 🟥 拉斐尔                              │    │
│ │ 进度: ████████████████████ 100%               │    │
│ │                                              │    │
│ │ ┌─ 关联 Agent ───────────────────────┐       │    │
│ │ │ 🟥 拉斐尔 (raphael)                │       │    │
│ │ │ 状态: busy | 当前任务: task-002-2  │       │    │
│ │ │ 最近心跳: 15 秒前                   │       │    │
│ │ │ [查看完整 Agent 详情 →]            │       │    │
│ │ └──────────────────────────────────────┘       │    │
│ │                                              │    │
│ │ ┌─ 评论 (3) ────────────────────────┐        │    │
│ │ │ 已完成数据库迁移部分 — admin       │        │    │
│ │ │ ...                                │        │    │
│ │ └──────────────────────────────────────┘       │    │
│ └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 5.2 双向联动方案

```
场景 1: 点击甘特图任务 → Agent 详情
  用户点击任务条
  → tasksStore.selectTask(taskId)
  → 右侧滑出 TaskDetail 面板
  → 面板中显示负责人 (assignee)
  → 点击"查看完整 Agent 详情"
  → agentsStore.selectAgent(assignee)
  → 切换到 AgentMonitor 视图，高亮该 Agent
  → 显示该 Agent 的关联任务列表

场景 2: 点击 Agent → 关联任务甘特图
  用户在 AgentMonitor 中点击 Agent 卡片
  → agentsStore.selectAgent(agentId)
  → 展开 Agent 详情面板
  → 点击"查看任务甘特图"
  → 切换到 TaskGantt 视图
  → 自动过滤: assignee = agentId
  → 甘特图只显示该 Agent 的任务
  → 时间线显示该 Agent 的工作负载
```

### 5.3 实现要点

```javascript
// TaskGantt.vue
const tasksStore = useTasksStore()
const agentsStore = useAgentsStore()

// 监听路由中的 assignee 参数
const route = useRoute()
watch(() => route.query.assignee, (agentId) => {
  if (agentId) {
    tasksStore.filters.assignee = agentId
    tasksStore.fetchGanttData()
  }
})

// 点击任务条 → 打开详情 + 关联 Agent
function onGanttClick(params) {
  const task = tasksStore.tasks.find(t => t.task_id === params.data.task_id)
  tasksStore.selectTask(task)
  if (task.assignee) {
    agentsStore.prefetchAgent(task.assignee)
  }
}

// AgentDetail.vue 中查看任务甘特图
function viewAgentTasks() {
  router.push({
    path: '/tasks/gantt',
    query: { assignee: selectedAgent.agent_id }
  })
}
```

---

## 六、WebSocket 推送方案

### 6.1 连接管理

```javascript
// store/agents.js
connectWebSocket(token) {
  const wsUrl = `ws://${window.location.host}/ws/agents?token=${token}`
  this.ws = new WebSocket(wsUrl)
  
  this.ws.onopen = () => {
    this.wsConnected = true
  }
  
  this.ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    this.handleWsMessage(message)
  }
  
  this.ws.onclose = () => {
    this.wsConnected = false
    // 5 秒后自动重连
    setTimeout(() => this.connectWebSocket(token), 5000)
  }
}

handleWsMessage(message) {
  switch (message.type) {
    case 'agent_status_change':
      this.updateAgentStatus(message.data)
      this.addNotification({
        type: 'agent',
        message: `${message.data.agent_name} 状态变更: ${message.data.from_status} → ${message.data.to_status}`,
        timestamp: message.data.timestamp
      })
      break
    case 'task_status_change':
      this.updateTaskStatus(message.data)
      break
    case 'heartbeat_update':
      this.updateHeartbeat(message.data)
      break
    case 'task_comment':
      this.addCommentToTask(message.data)
      break
  }
}
```

### 6.2 后端推送逻辑

```python
# websocket_manager.py (扩展)
class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._last_push_time: Dict[str, float] = {}
        self.rate_limit_seconds: float = 30.0
    
    async def connect(self, websocket: WebSocket, token: str):
        # 验证 JWT Token
        user = decode_jwt(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
        websocket.state.user = user
        await websocket.accept()
        self.active_connections.add(websocket)
        
        # 推送初始状态
        await self.push_initial_state(websocket)
    
    async def push_agent_status_change(self, agent_id, from_status, to_status, current_task):
        """Agent 状态变更推送"""
        await self.broadcast({
            "type": "agent_status_change",
            "data": {
                "agent_id": agent_id,
                "agent_name": get_agent_name(agent_id),
                "from_status": from_status,
                "to_status": to_status,
                "current_task": current_task,
                "timestamp": datetime.now().isoformat()
            }
        })
    
    async def push_task_change(self, task_id, from_status, to_status, assignee):
        """任务状态变更推送"""
        await self.broadcast({
            "type": "task_status_change",
            "data": {
                "task_id": task_id,
                "from_status": from_status,
                "to_status": to_status,
                "assignee": assignee,
                "timestamp": datetime.now().isoformat()
            }
        })
    
    async def push_heartbeat_update(self, agent_data):
        """心跳更新推送（30s 限频）"""
        await self.broadcast_with_ratelimit(
            "heartbeat_update",
            {"data": agent_data, "timestamp": datetime.now().isoformat()}
        )
    
    async def broadcast_with_ratelimit(self, msg_type, data):
        """带限频的广播"""
        now = time.time()
        last = self._last_push_time.get(msg_type, 0)
        if now - last < self.rate_limit_seconds:
            return False
        self._last_push_time[msg_type] = now
        await self.broadcast({"type": msg_type, **data})
        return True
```

### 6.3 心跳机制

```
Agent (OpenClaw) ──每 30s──▶ POST /api/agents/{id}/heartbeat
                                      │
                                      ▼
                              更新 DB (agent_heartbeats)
                                      │
                                      ▼
                              WebSocket Manager ──▶ 前端推送 (限频 30s)
                                      │
                              前端 Agent 状态卡片实时更新
                              心跳指示灯颜色变化
```

**健康度计算**:
| 心跳间隔 | 指示灯 | 说明 |
|---------|--------|------|
| ≤ 30s | 🟢 绿色 | 健康 |
| 30s ~ 120s | 🟡 黄色 | 超时警告 |
| > 120s | 🔴 红色 | 离线告警 |

---

## 七、认证方案

### 7.1 JWT + Session 实现

**技术选型**: JWT (无状态) + Cookie (可选)

```
登录流程:
  1. 用户 POST /api/auth/login {username, password}
  2. 后端验证密码 (bcrypt)
  3. 生成 JWT Token (24h 过期)
  4. 返回 Token + 用户信息
  5. 前端存储 Token 到 localStorage
  6. 后续请求携带 Authorization: Bearer <token>

刷新流程:
  1. Token 即将过期 (剩 5 分钟) 时，前端自动刷新
  2. POST /api/auth/refresh {refresh_token}
  3. 返回新 access_token
```

**JWT Payload**:
```json
{
  "sub": 1,
  "username": "admin",
  "role": "admin",
  "exp": 1719388800,
  "iat": 1719302400
}
```

**依赖安装**:
```bash
pip install python-jose[cryptography] passlib[bcrypt] sqlalchemy[asyncio] asyncpg alembic
```

### 7.2 角色权限设计

| 角色 | 读取 | 创建 | 更新 | 删除 | 用户管理 |
|------|------|------|------|------|---------|
| **admin** | ✅ 全部 | ✅ 全部 | ✅ 全部 | ✅ 全部 | ✅ |
| **agent** | ✅ 全部 | ✅ 任务 | ✅ 自己任务 | ❌ | ❌ |
| **viewer** | ✅ 全部 | ❌ | ❌ | ❌ | ❌ |

**权限中间件**:
```python
def require_role(*roles):
    """依赖注入：检查用户角色"""
    async def check(token: str = Depends(oauth2_scheme)):
        user = decode_jwt(token)
        if user["role"] not in roles:
            raise HTTPException(403, "权限不足")
        return user
    return check

# 使用示例
@app.post("/api/tasks")
async def create_task(data: TaskCreate, user = Depends(require_role("admin", "agent"))):
    ...

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, user = Depends(require_role("admin"))):
    ...
```

### 7.3 与现有 API Key 兼容

**保留现有 API Key 中间件**，作为认证方式之一:

```python
# 认证链: JWT Token 优先，回退到 API Key
async def get_current_user(
    jwt_token: str = Depends(oauth2_scheme, use_cache=False),
    api_key: str = Depends(api_key_header)  # 可选
):
    if jwt_token:
        return decode_jwt(jwt_token)
    if api_key:
        return validate_api_key(api_key)  # 返回虚拟用户对象
    raise HTTPException(401, "需要认证")
```

---

## 八、新增依赖

```txt
# requirements-v2.txt
# 认证
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# 数据库
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
alembic==1.13.1

# 前端 (package.json)
"vue": "^3.4.0",
"vue-router": "^4.3.0",
"pinia": "^2.1.0",
"axios": "^1.7.0",
"element-plus": "^2.5.0",
"echarts": "^5.5.0",
"vite": "^5.0.0",
"@vitejs/plugin-vue": "^5.0.0"
```

---

## 九、开发任务分配

### Phase 1: 基础设施 (2h)

| 任务 | 负责人 | 内容 |
|------|--------|------|
| P1-1 | 🟥 拉斐尔 | PostgreSQL 确认 + SQLAlchemy models + Alembic 初始化 |
| P1-2 | 🟥 拉斐尔 | JWT 认证模块 + 角色权限中间件 |
| P1-3 | 🟪 多纳泰罗 | Vue 3 Vite 项目初始化 + 路由 + Pinia + Axios |
| P1-4 | 🟦 李奥纳多 | Dev Spec 审查 + 架构方案确认 |

### Phase 2: 任务管理 (4h)

| 任务 | 负责人 | 内容 |
|------|--------|------|
| P2-1 | 🟥 拉斐尔 | 任务 CRUD API (6 端点) + 评论 API + 模板 API |
| P2-2 | 🟥 拉斐尔 | 数据迁移: JSON → PostgreSQL |
| P2-3 | 🟪 多纳泰罗 | 任务列表页 (表格 + 筛选 + 分页) |
| P2-4 | 🟪 多纳泰罗 | 任务详情面板 (右侧滑出) + 评论组件 |
| P2-5 | 🟪 多纳泰罗 | 任务创建/编辑对话框 |

### Phase 3: 实时监控 (3h)

| 任务 | 负责人 | 内容 |
|------|--------|------|
| P3-1 | 🟥 拉斐尔 | 心跳 API + 状态采集器 + 告警规则 |
| P3-2 | 🟥 拉斐尔 | WebSocket 推送 (心跳 + 任务变更) |
| P3-3 | 🟪 多纳泰罗 | Agent 状态卡片 + 心跳指示灯 |
| P3-4 | 🟪 多纳泰罗 | Agent 详情面板 + 实时通知 |

### Phase 4: 登录权限 (2h)

| 任务 | 负责人 | 内容 |
|------|--------|------|
| P4-1 | 🟪 多纳泰罗 | 登录页面 |
| P4-2 | 🟪 多纳泰罗 | 权限路由守卫 + 用户菜单 |
| P4-3 | 🟥 拉斐尔 | 用户管理 API |
| P4-4 | 🟦 李奥纳多 | admin 用户初始化 + 默认账号 |

### Phase 5: 甘特图 + 打磨 (2h)

| 任务 | 负责人 | 内容 |
|------|--------|------|
| P5-1 | 🟪 多纳泰罗 | 甘特图视图 (ECharts) + 双向联动 |
| P5-2 | 🟪 多纳泰罗 | 看板视图 (拖拽 Kanban) |
| P5-3 | 🟧 米开朗基罗 | 全量集成测试 + 回归测试 |
| P5-4 | 全员 | Bug 修复 + 文档 |

---

## 十、验收标准

### 功能验收

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 登录 | 用户名密码登录成功，JWT Token 正常签发 |
| 2 | 权限 | viewer 只能查看，agent 可创建/更新自己任务，admin 全权限 |
| 3 | 任务 CRUD | 创建/读取/更新/删除任务全部正常，变更历史自动记录 |
| 4 | 任务筛选 | 按状态/优先级/负责人/关键词筛选正确 |
| 5 | 任务评论 | 可添加/查看评论，实时更新 |
| 6 | 看板视图 | 拖拽任务变更状态正常 |
| 7 | 甘特图 | 正确渲染任务时间线，支持按 Agent 过滤 |
| 8 | 甘特图联动 | 点击任务 → Agent 详情，点击 Agent → 任务甘特图 |
| 9 | 心跳 | Agent 心跳 API 正常，DB 记录正确 |
| 10 | 实时监控 | Agent 状态卡片实时更新，心跳指示灯正常 |
| 11 | WebSocket | 状态变更实时推送，断线自动重连 |
| 12 | 数据迁移 | 现有 tasks.json 数据完整迁移到 DB |
| 13 | API Key 兼容 | 现有 API Key 仍可调用 API |

### 性能验收

| # | 验收项 | 标准 |
|---|--------|------|
| 1 | 任务列表 | 100 条任务加载 < 500ms |
| 2 | WebSocket | 连接延迟 < 100ms |
| 3 | 心跳推送 | 30s 限频正常，无重复推送 |
| 4 | 数据库 | 查询响应时间 < 50ms |

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| PostgreSQL 未安装/未启动 | P1 阻塞 | 先确认服务状态，必要时安装/启动 |
| JWT 与现有 API Key 冲突 | 认证异常 | 认证链设计兼容两者 |
| 前端重构影响现有功能 | 用户中断 | 渐进式迁移，/v2/ 隔离 |
| 数据迁移丢失 | 数据损失 | 迁移前备份，迁移后校验 |
| WebSocket 推送频率过高 | 性能问题 | 30s 限频 + 心跳合并 |

---

## 十二、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/models/*.py` | 新增 | SQLAlchemy ORM models (7 张表) |
| `backend/services/auth_service.py` | 新增 | JWT 认证服务 |
| `backend/routers/auth_router.py` | 新增 | 认证 API 路由 |
| `backend/routers/tasks_v2.py` | 新增 | V2 任务 API |
| `backend/routers/agents_monitor.py` | 新增 | Agent 监控 API |
| `backend/routers/users_router.py` | 新增 | 用户管理 API |
| `backend/middleware/jwt_auth.py` | 新增 | JWT 认证中间件 |
| `backend/main.py` | 修改 | 注册新路由 + WebSocket 端点 |
| `backend/requirements.txt` | 修改 | 新增依赖 |
| `backend/migrations/` | 新增 | Alembic 迁移脚本 |
| `frontend/src/` | 新增 | Vue 3 应用全套源码 |
| `frontend/package.json` | 新增 | 前端依赖 |
| `dev-loop/queue.json` | 修改 | 新增 V2 任务 |

---

*Dev Spec 完成 — 🟦 李奥纳多 2026-06-25*
