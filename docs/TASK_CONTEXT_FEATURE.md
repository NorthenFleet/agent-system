# 任务上下文功能文档

**创建日期**: 2026-04-05  
**版本**: 1.0  
**状态**: ✅ 已完成

---

## 📋 功能概述

为每个开发任务添加完整的上下文信息，帮助智能体更好地理解和执行任务。

---

## 🎯 核心功能

### 1. 任务上下文字段

每个任务现在包含以下上下文信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| `background` | string | 任务背景和来源 |
| `requirements` | array | 需求列表 |
| `resources` | array | 相关资源链接 |
| `acceptance_criteria` | array | 验收标准 |
| `dependencies` | array | 依赖任务 ID |
| `tech_stack` | array | 技术栈 |
| `notes` | string | 备注说明 |

### 2. 子任务系统

- 支持任务拆解为多个子任务
- 每个子任务可独立标记完成状态
- 子任务可分配给不同负责人

### 3. 任务日志

- 自动记录状态变更
- 支持手动添加备注
- 最多保留 100 条日志

---

## 🔌 API 端点

### 获取任务完整详情
```bash
GET /api/tasks/{task_id}/details
```

**响应示例**:
```json
{
  "task": {
    "id": "001",
    "title": "团队看板架构设计",
    "context": {
      "background": "...",
      "requirements": [...],
      "acceptance_criteria": [...]
    },
    "subtasks": [...]
  },
  "logs": [...],
  "subtasks_count": 5,
  "completed_subtasks": 3
}
```

### 更新任务上下文
```bash
PUT /api/tasks/{task_id}/context
Content-Type: application/json

{
  "background": "新背景",
  "requirements": ["需求 1", "需求 2"]
}
```

### 获取/添加子任务
```bash
GET /api/tasks/{task_id}/subtasks
POST /api/tasks/{task_id}/subtasks
PUT /api/tasks/{task_id}/subtasks/{subtask_id}
```

### 任务日志
```bash
GET /api/tasks/{task_id}/logs
POST /api/tasks/{task_id}/logs
```

### 按负责人获取任务
```bash
GET /api/tasks/assignee/{assignee}
```

---

## 🎨 前端功能

### 任务上下文弹窗

点击任务列表中的"📖 上下文"按钮，打开弹窗查看：

1. **任务基本信息** - 标题、描述、负责人、状态
2. **背景说明** - 任务来源和背景
3. **需求列表** - 详细需求清单
4. **验收标准** - 完成标准
5. **技术栈** - 使用的技术
6. **子任务** - 可勾选完成状态
7. **日志/备注** - 历史记录和新增备注

---

## 📝 使用示例

### 创建带上下文的任务

```python
from task_queue import task_manager

task_manager.create_task(
    title="新功能开发",
    assignee="拉斐尔",
    priority="high",
    description="实现用户管理模块",
    context={
        "background": "需要为用户管理系统添加 CRUD 功能",
        "requirements": [
            "用户列表展示",
            "用户创建/编辑/删除",
            "权限控制"
        ],
        "acceptance_criteria": [
            "所有 API 端点测试通过",
            "前端界面完成",
            "权限验证正常"
        ],
        "tech_stack": ["FastAPI", "Vue 3", "SQLite"],
        "notes": "优先完成核心功能"
    }
)
```

### 添加子任务

```python
task_manager.add_subtask("001", "设计数据库表结构", "拉斐尔")
task_manager.add_subtask("001", "实现 API 端点", "拉斐尔")
task_manager.add_subtask("001", "前端界面开发", "多纳泰罗")
```

### 添加日志备注

```python
task_manager.add_task_log("001", "已完成数据库设计，开始实现 API", "note")
```

---

## 📊 数据结构

### 任务对象
```json
{
  "id": "001",
  "title": "任务标题",
  "description": "任务描述",
  "assignee": "负责人",
  "status": "in_progress",
  "priority": "high",
  "progress": 30,
  "context": { ... },
  "subtasks": [ ... ],
  "tags": []
}
```

### 子任务对象
```json
{
  "id": "001-1",
  "title": "子任务标题",
  "assignee": "负责人",
  "completed": false,
  "created_at": "2026-04-05T10:00:00"
}
```

### 日志对象
```json
{
  "timestamp": "2026-04-05T10:00:00",
  "action": "note",
  "content": "日志内容"
}
```

---

## ✅ 已完成

- [x] 后端任务管理器升级
- [x] 上下文 API 端点
- [x] 子任务管理 API
- [x] 任务日志 API
- [x] 前端上下文弹窗
- [x] 示例任务数据

---

## 🚀 后续优化

- [ ] 上下文编辑功能
- [ ] 任务依赖关系可视化
- [ ] 子任务进度自动计算
- [ ] 任务模板功能
- [ ] 导出任务文档

---

*最后更新：2026-04-05*
