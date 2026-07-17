# OpenClaw 智能体集群系统

OpenClaw 当前统一运行在 3021 端口，采用 Vue 3 前端 + FastAPI 后端 + SQLite 数据存储。

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
│   ├── main_slim_v2.py      # 当前 FastAPI 应用入口
│   ├── main.py              # 兼容入口，导出 main_slim_v2.app
│   ├── api_registry.py      # API 路由注册中心
│   ├── routers/             # API 路由
│   ├── services/            # 业务服务
│   ├── repositories/        # 数据访问
│   ├── models/              # SQLAlchemy 模型
│   └── data/                # SQLite 与运行数据
├── frontend-v2/
│   ├── src/                 # 当前 Vue 3 前端源码
│   └── dist/                # 构建产物，由 FastAPI 托管
├── docs/                    # 项目文档
└── start.sh                 # 统一启动脚本
```

## 当前模块

- 仪表盘
- 项目中枢
- 程序开发
- 文档撰写
- 数据管理
- 产品矩阵
- 智能体团队
- 知识库
- 系统监视
- 用户管理

模块显示由后端用户权限控制，管理员可在用户管理中配置用户可见模块。

## 数据存储

- `backend/data/dashboard_v2.db`：用户、权限、业务模型等 SQLAlchemy 数据。
- `backend/data/unified_dashboard.db`：统一数据管理、项目、智能体、设备等迁移后的主数据。
- JSON 文件只作为兼容导入或外部状态快照，不应作为新功能主数据源。

## 开发规则

- 新前端页面放在 `frontend-v2/src/views/`。
- 新前端 API 封装放在 `frontend-v2/src/api/`。
- 新后端 API 放在 `backend/routers/`，并通过 `backend/api_registry.py` 注册。
- 新业务逻辑优先放在 `backend/services/`。
- 新持久化逻辑优先使用数据库模型或 repository，不再新增散落 JSON 主数据源。

## 验证

```bash
cd frontend-v2
npm run build

cd ../backend
./venv/bin/python -m py_compile main_slim_v2.py api_registry.py main.py
```
