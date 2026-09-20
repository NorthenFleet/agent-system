# OpenClaw 智能体集群系统

OpenClaw 当前统一运行在 3021 端口，采用 Vue 3 前端 + FastAPI 后端 + **双数据库架构**（开发用 SQLite / 生产用 PostgreSQL）。

## 当前入口

```bash
./start.sh
```

访问地址：

```text
http://localhost:3021/
```

远程访问：

```text
http://192.168.31.41:3021/
```

## 架构边界

```text
agent-system/
├── backend/
│   ├── main_slim_v2.py      # FastAPI 应用入口
│   ├── api_registry.py     # API 路由注册中心
│   ├── database.py          # 数据库双轨入口（SQLite/Postgres）
│   ├── routers/             # API 路由
│   ├── services/            # 业务服务（按子域分组）
│   ├── repositories/        # 数据访问层
│   ├── models/              # SQLAlchemy 模型
│   ├── alembic/             # Postgres schema 迁移
│   ├── scripts/             # 运维脚本（迁移/预检/演练）
│   └── data/                # SQLite 与运行时数据
├── frontend-v2/
│   ├── src/
│   └── dist/                # 构建产物，由 FastAPI 托管
├── integrations/            # 外部集成（graph-memory、skills）
├── docs/                    # 按主题组织的阶段/里程碑文档
└── start.sh                 # 统一启动脚本
```

## 业务子域

运行时按子域组织，每个子域默认关闭（在 `.env` 中通过开关启用），由模块权限控制前端可见性：

| 子域 | 关键服务 | 默认开关 |
|---|---|---|
| 用户/权限 | auth_service/user_service/module_permission_service | 默认开启 |
| 项目中枢 | projects_v3 / project_service | 默认开启 |
| 任务调度 | task_service/scheduler | 默认开启 |
| 智能体注册 | agents_router/agent_health_router | 默认开启 |
| 知识/检索 | knowledge_router/context_router/context_retrieval_service | 默认开启 |
| 智能体团队 | agent_team_service/agent_capability_registry | `AGENT_TEAM_ENABLED=false` |
| 指挥中心 | command_center_service/worker/repository（Postgres 多 worker） | 由 `COMMAND_CENTER_DATABASE_URL` 控制 |
| 业务流编排 | business_flow_service/workflow_runtime/compensation_service（LangGraph） | 实验阶段 |
| 执行证据 | execution_evidence_service/plan_quality_service | 实验阶段 |
| 记忆系统 | 完整生命周期（retrieval/lifecycle/release/orchestrator/vector/projection/shadow_metrics/SLO）+ graph_memory 三件套 + memory-evaluation 前端模块 | `MEMORY_VECTOR_ENABLED=false` |
| 产品矩阵 | products_router/product_invocation_router/product_service | 默认开启 |
| 财务 | finance_router | 默认开启 |
| 系统监视 | monitoring_router | 默认开启 |
| 讨论 | discussions_router/discussion_service | 默认开启 |

## 数据存储

当前架构为 **SQLite + PostgreSQL 双轨**：

- **SQLite（开发/回退）**
  - `backend/data/dashboard_v2.db`：用户、权限、业务模型等
  - `backend/data/unified_dashboard.db`：统一数据管理主仓
  - 启动时由 `database.py.ensure_task_table_ownership_compatibility()` 保证旧 planning task 表重命名为 `legacy_plan_tasks`

- **PostgreSQL（生产）**
  - 默认 URL：`postgresql+psycopg2:///team_dashboard`（由 `DATABASE_URL` 环境变量覆盖）
  - Schema 由 Alembic 独占管理（`backend/alembic/versions/`）
  - 各子域独立 DATABASE_URL 配置：
    - `MEMORY_VECTOR_DATABASE_URL`
    - `COMMAND_CENTER_DATABASE_URL`
    - `WORK_RUN_DATABASE_URL`
    - `COMMAND_CENTER_LANGGRAPH_CHECKPOINT_URL`
  - SQLite → Postgres 迁移脚本位于 `backend/scripts/migrate_*_sqlite_to_postgres.py`

- **JSON 文件** 仅作为外部状态快照，不作为新功能主数据源。

## 开发规则

- 新前端页面放在 `frontend-v2/src/views/`。
- 新前端 API 封装放在 `frontend-v2/src/api/`。
- 新后端 API 放在 `backend/routers/`，并通过 `backend/api_registry.py` 注册。
- 新业务逻辑优先放在 `backend/services/`。
- 新持久化逻辑优先使用数据库模型或 repository，不再新增散落 JSON 主数据源。
- 新的 schema 变更必须通过 Alembic 迁移，禁止直接改数据库文件。
- 提交必须按功能主题分批，严禁一次性 `git add .` 或通配符。

## 验证

```bash
cd frontend-v2
npm run build

cd ../backend
./venv/bin/python -m py_compile main_slim_v2.py api_registry.py main.py database.py
```

## 启动依赖

`start.sh` 会自动：

- 启动 pgvector 上线预检（若 `MEMORY_VECTOR_ENABLED=true`）
- 拉起 Crawl4AI 网络采集服务（端口 11235，若环境存在）
- 建立到 ai-planning-5130 的 SSH 隧道（默认 `192.168.31.144:5130`，默认开启）
- 启动 FastAPI 后端（端口 3021，可通过 `API_PORT` 覆盖）

## 当前分支状态

当前处于架构跃迁期：**单机 SQLite → Postgres + 多 worker + 业务流 LangGraph 编排**。

所有新功能默认关闭（通过 `.env` 开关），不影响既有 SQLite 生产环境。
按主题分 6 批渐进式落地（详见 git log）。