# Task-Plan API 开发文档

## 概述

本文档描述任务看板与开发计划整合的后端 API 实现。

**版本**: v1.0  
**作者**: 拉斐尔 (🐢 后端开发)  
**创建日期**: 2026-04-16

---

## 📁 文件结构

```
team-dashboard/backend/
├── api/
│   ├── tasks.py          # 任务管理 API
│   └── plans.py          # 开发计划 API
├── models/
│   └── task_plan.py      # SQLAlchemy 数据模型
├── migrations/
│   └── 001_add_plans.sql # 数据库迁移脚本
├── tests/
│   └── test_task_plans.py # API 测试
├── database.py           # 数据库配置
└── main.py               # FastAPI 应用入口 (已更新)
```

---

## 🗄️ 数据库迁移

### 应用迁移

```bash
# 连接到 PostgreSQL 数据库
psql -U postgres -d team_dashboard

# 应用迁移脚本
\i backend/migrations/001_add_plans.sql
```

或者使用 psql 命令行：

```bash
psql -U postgres -d team_dashboard -f team-dashboard/backend/migrations/001_add_plans.sql
```

### 验证迁移

```sql
-- 检查表是否创建成功
\dt

-- 检查枚举类型
\dT+

-- 检查视图
\dv
```

---

## 🚀 启动 API 服务

### 1. 安装依赖

```bash
cd team-dashboard/backend
pip install -r requirements.txt
```

### 2. 配置数据库连接

创建 `.env` 文件或设置环境变量：

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/team_dashboard"
```

### 3. 初始化数据库

```bash
python database.py
```

### 4. 启动服务

```bash
python main.py
# 或者使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API 文档访问：http://localhost:8000/docs

---

## 📡 API 接口

### 任务管理 API (`/api/v1/tasks`)

#### 创建任务
```http
POST /api/v1/tasks
Content-Type: application/json

{
  "title": "实现用户登录功能",
  "assignee": "拉斐尔",
  "description": "支持邮箱和密码登录",
  "priority": "high",
  "deadline": "2026-04-20T18:00:00Z",
  "tags": ["后端", "认证"]
}
```

#### 获取任务详情
```http
GET /api/v1/tasks/:taskId?include_plans=true&include_active_plan=true
```

#### 更新任务
```http
PUT /api/v1/tasks/:taskId
Content-Type: application/json

{
  "title": "更新后的标题",
  "status": "in_progress",
  "progress": 50
}
```

#### 删除任务
```http
DELETE /api/v1/tasks/:taskId
```

#### 查询任务列表
```http
GET /api/v1/tasks?status=in_progress&assignee=拉斐尔&limit=20&offset=0
```

#### 获取任务的所有计划
```http
GET /api/v1/tasks/:taskId/plans
```

#### 为任务添加新计划
```http
POST /api/v1/tasks/:taskId/plans
Content-Type: application/json

{
  "title": "开发方案 V1",
  "type": "backend",
  "steps": [
    {"index": 0, "name": "需求分析", "estimatedHours": 2},
    {"index": 1, "name": "实现", "estimatedHours": 8}
  ]
}
```

#### 激活指定计划
```http
POST /api/v1/tasks/:taskId/active_plan?plan_id=plan_20260416103000
```

---

### 开发计划 API (`/api/v1/plans`)

#### 创建开发计划
```http
POST /api/v1/plans
Content-Type: application/json

{
  "task_id": "20260416-001",
  "title": "用户登录功能开发方案",
  "type": "backend",
  "steps": [
    {"index": 0, "name": "需求分析", "estimatedHours": 2},
    {"index": 1, "name": "数据库设计", "estimatedHours": 3}
  ]
}
```

#### 获取计划详情
```http
GET /api/v1/plans/:planId?include_task=true
```

#### 更新开发计划
```http
PUT /api/v1/plans/:planId
Content-Type: application/json

{
  "title": "更新后的标题",
  "status": "approved"
}
```

#### 删除开发计划
```http
DELETE /api/v1/plans/:planId
```

#### 查询计划列表
```http
GET /api/v1/plans?task_id=20260416-001&status=approved&limit=20
```

#### 审核计划
```http
POST /api/v1/plans/:planId/review
Content-Type: application/json

{
  "approved": true,
  "comment": "方案合理，注意密码加密强度"
}
```

#### 获取计划进度
```http
GET /api/v1/plans/:planId/progress
```

#### 执行计划步骤
```http
POST /api/v1/plans/:planId/steps/:stepIndex/execute
Content-Type: application/json

{
  "status": "completed",
  "output": "已完成数据库表结构设计"
}
```

---

## 🧪 运行测试

```bash
cd team-dashboard/backend
pytest tests/test_task_plans.py -v
```

### 测试覆盖率

```bash
pytest tests/test_task_plans.py -v --cov=api --cov=models --cov-report=html
```

---

## 📊 数据模型

### Task (任务)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(32) | 任务 ID (YYYYMMDD-XXX) |
| title | VARCHAR(500) | 任务标题 |
| status | ENUM | pending/in_progress/testing/completed/failed/blocked |
| priority | ENUM | low/normal/high/critical |
| assignee | VARCHAR(100) | 负责人 |
| active_plan_id | VARCHAR(64) | 当前激活的计划 ID |
| context | JSONB | 任务上下文 |
| progress | INTEGER | 进度百分比 (0-100) |

### DevelopmentPlan (开发计划)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) | 计划 ID (plan_YYYYMMDDHHMMSS) |
| task_id | VARCHAR(32) | 所属任务 ID (外键) |
| version | INTEGER | 版本号 |
| status | ENUM | draft/pending_review/approved/rejected/in_progress/completed/archived |
| type | ENUM | frontend/backend/testing/design/research/general |
| steps | JSONB | 执行步骤列表 |
| estimated_total_hours | NUMERIC | 总预估工时 |

---

## ⚠️ 错误处理

### 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `PLAN_NOT_FOUND` | 404 | 计划不存在 |
| `PLAN_NOT_APPROVED` | 400 | 计划未通过审核 |
| `INVALID_STATUS_TRANSITION` | 400 | 无效的状态转换 |
| `VALIDATION_ERROR` | 400/422 | 参数验证失败 |

### 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "任务不存在",
    "details": {
      "task_id": "20260416-001"
    }
  },
  "timestamp": "2026-04-16T10:30:00Z"
}
```

---

## 🔐 状态转换规则

### 任务状态转换

```
pending → in_progress → testing → completed
                 ↓
               blocked
                 ↓
               failed
```

### 计划状态转换

```
draft → pending_review → approved → in_progress → completed
                      ↓
                   rejected
```

---

## 📝 开发注意事项

1. **事务处理**: 所有写操作都使用事务，确保数据一致性
2. **外键约束**: 删除任务时自动级联删除关联计划
3. **触发器**: 自动维护 `updated_at` 字段和 `task_plans` 关联表
4. **索引优化**: 关键查询字段已建立索引
5. **JSONB 查询**: 支持灵活的扩展字段查询

---

## ✅ 完成检查清单

- [x] 数据库迁移脚本 (`migrations/001_add_plans.sql`)
- [x] 数据模型 (`models/task_plan.py`)
- [x] 任务 API (`api/tasks.py`)
- [x] 计划 API (`api/plans.py`)
- [x] API 测试 (`tests/test_task_plans.py`)
- [x] 数据库配置 (`database.py`)
- [x] 路由注册 (`main.py`)
- [x] 依赖更新 (`requirements.txt`)

---

## 🎯 下一步

1. **多纳泰罗** 可开始前端开发
2. 集成测试验证完整工作流
3. 性能优化和压力测试
4. 添加认证和授权机制

---

**开发完成时间**: 2026-04-16  
**负责人**: 拉斐尔 (🐢 后端开发)
