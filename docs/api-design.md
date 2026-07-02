# Task-Plan API 接口设计文档

> **版本**: v1.0  
> **作者**: 李奥纳多 (🐢 架构师)  
> **创建日期**: 2026-04-16  
> **状态**: 设计完成，待开发

---

## 📋 目录

1. [概述](#概述)
2. [任务管理 API (增强版)](#任务管理 API-增强版)
3. [开发计划 CRUD 接口](#开发计划 CRUD 接口)
4. [从属关系管理接口](#从属关系管理接口)
5. [错误处理](#错误处理)
6. [示例](#示例)

---

## 概述

### 设计原则

- **RESTful 风格**: 使用标准 HTTP 方法和状态码
- **嵌套查询**: 支持任务与其开发计划的联合查询
- **版本控制**: API 路径包含版本号 `/api/v1/`
- **认证授权**: 所有写操作需要 JWT 认证

### 基础路径

```
Base URL: /api/v1
```

### 通用响应格式

**成功响应**:
```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功",
  "timestamp": "2026-04-16T10:30:00Z"
}
```

**错误响应**:
```json
{
  "success": false,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "任务不存在",
    "details": { ... }
  },
  "timestamp": "2026-04-16T10:30:00Z"
}
```

---

## 任务管理 API (增强版)

### 1.1 创建任务

**请求**:
```http
POST /api/v1/tasks
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体**:
```json
{
  "title": "实现用户登录功能",
  "description": "支持邮箱和密码登录，包含验证码机制",
  "priority": "high",
  "assignee": "拉斐尔",
  "deadline": "2026-04-20T18:00:00Z",
  "context": {
    "background": "当前系统缺少用户认证模块",
    "requirements": [
      "支持邮箱注册",
      "密码加密存储",
      "登录失败次数限制"
    ],
    "resources": [
      {
        "title": "设计规范",
        "url": "https://design.example.com/login",
        "type": "design"
      }
    ],
    "acceptanceCriteria": [
      "用户能成功登录",
      "错误密码有明确提示"
    ],
    "dependencies": [],
    "techStack": ["FastAPI", "JWT", "Redis"],
    "notes": "注意安全性"
  },
  "tags": ["后端", "认证", "安全"]
}
```

**响应** (201 Created):
```json
{
  "success": true,
  "data": {
    "id": "20260416-001",
    "title": "实现用户登录功能",
    "status": "pending",
    "priority": "high",
    "assignee": "拉斐尔",
    "creator": "擎天柱",
    "createdAt": "2026-04-16T10:30:00Z",
    "updatedAt": "2026-04-16T10:30:00Z",
    "progress": 0,
    "planIds": [],
    "activePlanId": null,
    "context": { ... },
    "subtasks": [],
    "tags": ["后端", "认证", "安全"]
  },
  "timestamp": "2026-04-16T10:30:00Z"
}
```

---

### 1.2 获取任务详情

**请求**:
```http
GET /api/v1/tasks/:taskId?includePlans=true&includeActivePlan=true
Authorization: Bearer <token>
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `includePlans` | boolean | 否 | 是否包含所有计划 (默认 false) |
| `includeActivePlan` | boolean | 否 | 是否包含激活计划详情 (默认 false) |

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": "20260416-001",
    "title": "实现用户登录功能",
    "status": "in_progress",
    "priority": "high",
    "assignee": "拉斐尔",
    "creator": "擎天柱",
    "createdAt": "2026-04-16T10:30:00Z",
    "updatedAt": "2026-04-16T14:20:00Z",
    "startedAt": "2026-04-16T11:00:00Z",
    "deadline": "2026-04-20T18:00:00Z",
    "progress": 35,
    "planIds": ["plan_20260416103500", "plan_20260416142000"],
    "activePlanId": "plan_20260416142000",
    "context": { ... },
    "subtasks": [
      {
        "id": "20260416-001-1",
        "title": "设计数据库表结构",
        "assignee": "拉斐尔",
        "completed": true,
        "completedAt": "2026-04-16T12:00:00Z",
        "createdAt": "2026-04-16T10:30:00Z"
      }
    ],
    "tags": ["后端", "认证", "安全"],
    "activePlan": {
      "id": "plan_20260416142000",
      "taskId": "20260416-001",
      "version": 2,
      "status": "approved",
      "steps": [ ... ],
      "estimatedTotalHours": 16
    },
    "plans": [
      {
        "id": "plan_20260416103500",
        "version": 1,
        "status": "rejected",
        "createdAt": "2026-04-16T10:35:00Z"
      },
      {
        "id": "plan_20260416142000",
        "version": 2,
        "status": "approved",
        "createdAt": "2026-04-16T14:20:00Z"
      }
    ]
  },
  "timestamp": "2026-04-16T14:30:00Z"
}
```

---

### 1.3 更新任务

**请求**:
```http
PUT /api/v1/tasks/:taskId
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体** (所有字段可选):
```json
{
  "title": "实现用户登录和注册功能",
  "status": "in_progress",
  "progress": 50,
  "deadline": "2026-04-22T18:00:00Z",
  "tags": ["后端", "认证", "安全", "用户管理"]
}
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-04-16T15:00:00Z"
}
```

---

### 1.4 删除任务

**请求**:
```http
DELETE /api/v1/tasks/:taskId
Authorization: Bearer <token>
```

**响应** (204 No Content):
```
(无内容)
```

---

### 1.5 查询任务列表

**请求**:
```http
GET /api/v1/tasks?status=in_progress&assignee=拉斐尔&hasActivePlan=true&sortBy=deadline&sortOrder=asc&limit=20&offset=0
Authorization: Bearer <token>
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string\|string[] | 否 | 任务状态过滤 |
| `priority` | string\|string[] | 否 | 优先级过滤 |
| `assignee` | string\|string[] | 否 | 负责人过滤 |
| `creator` | string | 否 | 创建人过滤 |
| `tags` | string[] | 否 | 标签过滤 |
| `hasActivePlan` | boolean | 否 | 是否有激活计划 |
| `createdAfter` | string | 否 | 创建时间起点 (ISO 8601) |
| `createdBefore` | string | 否 | 创建时间终点 (ISO 8601) |
| `deadlineAfter` | string | 否 | 截止时间起点 |
| `deadlineBefore` | string | 否 | 截止时间终点 |
| `sortBy` | string | 否 | 排序字段 (createdAt/updateAt/deadline/priority) |
| `sortOrder` | string | 否 | 排序方向 (asc/desc) |
| `limit` | number | 否 | 每页数量 (默认 20, 最大 100) |
| `offset` | number | 否 | 偏移量 |

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "tasks": [ ... ],
    "pagination": {
      "total": 45,
      "limit": 20,
      "offset": 0,
      "hasMore": true
    }
  },
  "timestamp": "2026-04-16T15:00:00Z"
}
```

---

## 开发计划 CRUD 接口

### 2.1 创建开发计划

**请求**:
```http
POST /api/v1/plans
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体**:
```json
{
  "taskId": "20260416-001",
  "title": "用户登录功能开发方案 V1",
  "type": "backend",
  "steps": [
    {
      "index": 0,
      "name": "需求分析",
      "description": "分析登录功能需求，确定技术选型",
      "estimatedHours": 2,
      "executor": "拉斐尔",
      "dependencies": []
    },
    {
      "index": 1,
      "name": "数据库设计",
      "description": "设计用户表和会话表结构",
      "estimatedHours": 3,
      "executor": "拉斐尔",
      "dependencies": [0]
    },
    {
      "index": 2,
      "name": "API 实现",
      "description": "实现登录、登出、验证码 API",
      "estimatedHours": 8,
      "executor": "拉斐尔",
      "dependencies": [1]
    },
    {
      "index": 3,
      "name": "单元测试",
      "description": "编写 API 测试用例",
      "estimatedHours": 3,
      "executor": "米开朗基罗",
      "dependencies": [2]
    }
  ],
  "metadata": {
    "riskLevel": "medium",
    "confidence": 0.85,
    "alternatives": ["使用 OAuth2 第三方登录"]
  }
}
```

**响应** (201 Created):
```json
{
  "success": true,
  "data": {
    "id": "plan_20260416153000",
    "taskId": "20260416-001",
    "title": "用户登录功能开发方案 V1",
    "version": 1,
    "status": "pending_review",
    "type": "backend",
    "creator": "李奥纳多",
    "createdAt": "2026-04-16T15:30:00Z",
    "steps": [ ... ],
    "estimatedTotalHours": 16,
    "metadata": {
      "riskLevel": "medium",
      "confidence": 0.85
    }
  },
  "timestamp": "2026-04-16T15:30:00Z"
}
```

---

### 2.2 获取计划详情

**请求**:
```http
GET /api/v1/plans/:planId?includeTask=true
Authorization: Bearer <token>
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `includeTask` | boolean | 否 | 是否包含所属任务详情 |

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": "plan_20260416153000",
    "taskId": "20260416-001",
    "title": "用户登录功能开发方案 V1",
    "version": 1,
    "status": "approved",
    "type": "backend",
    "creator": "李奥纳多",
    "reviewer": "擎天柱",
    "executors": ["拉斐尔", "米开朗基罗"],
    "createdAt": "2026-04-16T15:30:00Z",
    "reviewedAt": "2026-04-16T16:00:00Z",
    "startedAt": "2026-04-16T16:30:00Z",
    "steps": [
      {
        "index": 0,
        "name": "需求分析",
        "status": "completed",
        "executor": "拉斐尔",
        "completedAt": "2026-04-16T17:00:00Z"
      },
      {
        "index": 1,
        "name": "数据库设计",
        "status": "in_progress",
        "executor": "拉斐尔",
        "startedAt": "2026-04-16T17:00:00Z"
      }
    ],
    "estimatedTotalHours": 16,
    "reviewComment": "方案合理，注意密码加密强度",
    "task": {
      "id": "20260416-001",
      "title": "实现用户登录功能",
      "status": "in_progress",
      "assignee": "拉斐尔"
    }
  },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

### 2.3 更新开发计划

**请求**:
```http
PUT /api/v1/plans/:planId
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体** (所有字段可选):
```json
{
  "title": "用户登录功能开发方案 V1 (修订)",
  "steps": [ ... ],
  "metadata": {
    "riskLevel": "low",
    "confidence": 0.9
  }
}
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

### 2.4 删除开发计划

**请求**:
```http
DELETE /api/v1/plans/:planId
Authorization: Bearer <token>
```

**响应** (204 No Content):
```
(无内容)
```

---

### 2.5 查询计划列表

**请求**:
```http
GET /api/v1/plans?taskId=20260416-001&status=approved&type=backend&sortBy=createdAt&sortOrder=desc&limit=20
Authorization: Bearer <token>
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `taskId` | string | 否 | 所属任务 ID |
| `status` | string\|string[] | 否 | 计划状态过滤 |
| `type` | string\|string[] | 否 | 计划类型过滤 |
| `creator` | string | 否 | 创建人过滤 |
| `reviewer` | string | 否 | 审核人过滤 |
| `createdAfter` | string | 否 | 创建时间起点 |
| `createdBefore` | string | 否 | 创建时间终点 |
| `sortBy` | string | 否 | 排序字段 |
| `sortOrder` | string | 否 | 排序方向 |
| `limit` | number | 否 | 每页数量 |
| `offset` | number | 否 | 偏移量 |

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "plans": [ ... ],
    "pagination": {
      "total": 12,
      "limit": 20,
      "offset": 0,
      "hasMore": false
    }
  },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

## 从属关系管理接口

### 3.1 设置激活计划

**请求**:
```http
POST /api/v1/tasks/:taskId/plans/:planId/activate
Content-Type: application/json
Authorization: Bearer <token>
```

**说明**: 将指定计划设置为任务的激活计划，原激活计划自动失效。

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "taskId": "20260416-001",
    "activePlanId": "plan_20260416153000",
    "previousActivePlanId": "plan_20260416103500",
    "updatedAt": "2026-04-16T16:30:00Z"
  },
  "message": "激活计划已更新",
  "timestamp": "2026-04-16T16:30:00Z"
}
```

---

### 3.2 审核开发计划

**请求**:
```http
POST /api/v1/plans/:planId/review
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体**:
```json
{
  "approved": true,
  "comment": "方案合理，注意以下几点：1. 密码加密使用 bcrypt 2. 添加登录失败限流"
}
```

或 (拒绝时):
```json
{
  "approved": false,
  "comment": "需要补充异常处理方案",
  "rejectionReason": "缺少错误处理机制"
}
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": "plan_20260416153000",
    "status": "approved",
    "reviewer": "擎天柱",
    "reviewedAt": "2026-04-16T16:00:00Z",
    "reviewComment": "方案合理，注意以下几点：1. 密码加密使用 bcrypt 2. 添加登录失败限流"
  },
  "message": "计划已通过审核",
  "timestamp": "2026-04-16T16:00:00Z"
}
```

---

### 3.3 获取任务 - 计划关系摘要

**请求**:
```http
GET /api/v1/tasks/:taskId/plans/relation
Authorization: Bearer <token>
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "taskId": "20260416-001",
    "taskTitle": "实现用户登录功能",
    "taskStatus": "in_progress",
    "activePlanId": "plan_20260416153000",
    "activePlanStatus": "approved",
    "totalPlans": 2,
    "approvedPlans": 1,
    "lastPlanCreatedAt": "2026-04-16T15:30:00Z"
  },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

### 3.4 获取计划执行进度

**请求**:
```http
GET /api/v1/plans/:planId/progress
Authorization: Bearer <token>
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "planId": "plan_20260416153000",
    "taskId": "20260416-001",
    "totalSteps": 4,
    "completedSteps": 1,
    "progressPercentage": 25,
    "currentStepIndex": 1,
    "nextStepName": "数据库设计",
    "estimatedRemainingHours": 14
  },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

### 3.5 执行计划步骤

**请求**:
```http
POST /api/v1/plans/:planId/steps/:stepIndex/execute
Content-Type: application/json
Authorization: Bearer <token>
```

**请求体**:
```json
{
  "status": "completed",
  "output": "已完成数据库表结构设计，包括 users 表和 sessions 表"
}
```

**响应** (200 OK):
```json
{
  "success": true,
  "data": {
    "planId": "plan_20260416153000",
    "stepIndex": 0,
    "stepName": "需求分析",
    "status": "completed",
    "completedAt": "2026-04-16T17:00:00Z",
    "output": "已完成数据库表结构设计，包括 users 表和 sessions 表"
  },
  "message": "步骤执行完成",
  "timestamp": "2026-04-16T17:00:00Z"
}
```

---

### 3.6 自动生成计划

**请求**:
```http
POST /api/v1/tasks/:taskId/plans/generate
Content-Type: application/json
Authorization: Bearer <token>
```

**说明**: 李奥纳多根据任务类型自动生成开发计划模板。

**响应** (201 Created):
```json
{
  "success": true,
  "data": {
    "id": "plan_20260416180000",
    "taskId": "20260416-001",
    "title": "后端开发计划 (自动生成)",
    "version": 1,
    "status": "pending_review",
    "type": "backend",
    "creator": "李奥纳多",
    "createdAt": "2026-04-16T18:00:00Z",
    "steps": [ ... ],
    "estimatedTotalHours": 16
  },
  "message": "计划已自动生成，待审核",
  "timestamp": "2026-04-16T18:00:00Z"
}
```

---

## 错误处理

### 错误码定义

| 错误码 | HTTP 状态码 | 说明 |
|--------|-----------|------|
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `PLAN_NOT_FOUND` | 404 | 计划不存在 |
| `TASK_ALREADY_HAS_ACTIVE_PLAN` | 400 | 任务已有激活计划 |
| `PLAN_NOT_APPROVED` | 400 | 计划未通过审核 |
| `PLAN_STEP_DEPENDENCY_NOT_MET` | 400 | 计划步骤依赖未满足 |
| `INVALID_PLAN_STATUS_TRANSITION` | 400 | 无效的计划状态转换 |
| `TASK_DELETE_HAS_ACTIVE_PLAN` | 400 | 任务有激活计划，无法删除 |
| `UNAUTHORIZED` | 401 | 未授权 |
| `FORBIDDEN` | 403 | 无权限 |
| `VALIDATION_ERROR` | 400 | 参数验证失败 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

### 错误响应示例

```json
{
  "success": false,
  "error": {
    "code": "PLAN_NOT_APPROVED",
    "message": "无法执行未通过审核的计划",
    "details": {
      "planId": "plan_20260416153000",
      "currentStatus": "pending_review",
      "requiredStatus": "approved"
    }
  },
  "timestamp": "2026-04-16T17:30:00Z"
}
```

---

## 示例

### 完整工作流示例

**1. 创建任务**:
```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "title": "实现用户登录功能",
    "assignee": "拉斐尔",
    "priority": "high"
  }'
```

**2. 自动生成计划**:
```bash
curl -X POST http://localhost:8000/api/v1/tasks/20260416-001/plans/generate \
  -H "Authorization: Bearer <token>"
```

**3. 审核计划**:
```bash
curl -X POST http://localhost:8000/api/v1/plans/plan_20260416180000/review \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"approved": true, "comment": "通过"}'
```

**4. 激活计划**:
```bash
curl -X POST http://localhost:8000/api/v1/tasks/20260416-001/plans/plan_20260416180000/activate \
  -H "Authorization: Bearer <token>"
```

**5. 执行计划步骤**:
```bash
curl -X POST http://localhost:8000/api/v1/plans/plan_20260416180000/steps/0/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"status": "completed", "output": "完成"}'
```

**6. 查询任务进度**:
```bash
curl http://localhost:8000/api/v1/tasks/20260416-001?includeActivePlan=true \
  -H "Authorization: Bearer <token>"
```

---

## 附录

### A. 任务类型与计划模板映射

| 任务类型 | 计划类型 | 默认步骤 |
|----------|----------|----------|
| 前端开发 | frontend | 需求分析 → 组件设计 → 实现 → 测试 |
| 后端开发 | backend | 需求分析 → 数据库设计 → API 实现 → 测试 |
| 测试任务 | testing | 测试用例设计 → 自动化脚本 → 执行测试 → 报告 |
| 设计任务 | design | 需求分析 → 草图 → 高保真 → 评审 |
| 研究任务 | research | 文献调研 → 方案对比 → 技术选型 → 报告 |

### B. 状态转换图

**任务状态转换**:
```
pending → in_progress → testing → completed
                 ↓
               blocked
                 ↓
               failed
```

**计划状态转换**:
```
draft → pending_review → approved → in_progress → completed
                      ↓
                   rejected
```

### C. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-04-16 | 初始版本，李奥纳多设计 |

---

**文档结束**
