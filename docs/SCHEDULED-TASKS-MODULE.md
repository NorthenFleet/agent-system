# 定时任务管理模块

## 概述

定时任务管理模块由 **🟣 震荡波 (团队优化师)** 统一管理，提供团队所有定时任务的可视化监控。

## 功能特性

### 1. 任务清单展示
- 任务名称与描述
- 负责人 (智能体)
- 执行频率
- 时间窗口

### 2. 状态监控
- 实时状态 (🟢正常 🟡延迟/暂停 🔴失败)
- 下次执行时间 (倒计时)
- 上次执行时间
- 成功率统计

### 3. 筛选功能
- 按负责人筛选
- 任务搜索

### 4. 可视化设计
- 状态颜色标识
- 成功率进度条
- 响应式布局

## 数据格式

### API: `GET /api/scheduled-tasks`

**响应示例**:
```json
{
  "managed_by": "震荡波",
  "manager_role": "团队优化师 - 定时任务总调度",
  "last_updated": "2026-04-07T16:11:00+08:00",
  "total_tasks": 5,
  "active_tasks": 5,
  "tasks": [
    {
      "id": "TASK-001",
      "name": "邮件检查",
      "owner": "感知器",
      "owner_emoji": "🚗",
      "schedule": "每 30 分钟",
      "time_slot": "08:00-22:00",
      "status": "active",
      "last_run": "2026-04-07T15:54:00+08:00",
      "next_run": "2026-04-07T16:24:00+08:00",
      "success_rate": 100,
      "description": "检查 QQ 邮箱，分发发票/论文邮件"
    }
  ]
}
```

### 数据文件
`~/WorkSpace/team-dashboard/data/scheduled-tasks.json`

## 当前任务列表

| ID | 任务名称 | 负责人 | 频率 | 状态 | 成功率 |
|----|----------|--------|------|------|--------|
| TASK-001 | 邮件检查 | 感知器 🚗 | 每 30 分钟 | 🟢 正常 | 100% |
| TASK-002 | 团队工作看板汇报 | 擎天柱 🤖 | 每 3 小时 | 🟢 正常 | 100% |
| TASK-003 | 开发任务检查 | 李奥纳多 🟦 | 每 1 小时 | 🟢 正常 | 100% |
| TASK-004 | 设备心跳检查 | 大黄蜂 🐝 | 每 30 分钟 | 🟢 正常 | 100% |
| TASK-005 | Isaac Sim 检查 | 铁皮 🛡️ | 每 3 小时 | 🟢 正常 | 100% |

## 状态说明

| 状态 | 标识 | 说明 |
|------|------|------|
| active | 🟢 正常 | 任务正常运行中 |
| delayed | 🟡 延迟 | 任务执行延迟 |
| paused | 🟡 暂停 | 任务已暂停 |
| failed | 🔴 失败 | 任务执行失败 |

## 成功率计算

- **≥95%**: 🟢 优秀 (绿色)
- **80-94%**: 🟡 良好 (黄色)
- **<80%**: 🔴 需改进 (红色)

## 前端实现

### 文件位置
`frontend/index-old.html`

### 关键代码

**导航入口**:
```html
<div class="nav-item" :class="{ active: currentView === 'scheduled' }" 
     @click="switchView('scheduled')">⏰ 定时任务</div>
```

**数据加载**:
```javascript
async loadScheduledTasks() {
  const res = await fetch('/api/scheduled-tasks');
  const data = await res.json();
  this.scheduledTasks = data.tasks || [];
  this.scheduledTasksMeta = { ... };
}
```

**状态显示**:
```javascript
getTaskStatusText(status) {
  return {
    'active': '🟢 正常',
    'paused': '🟡 暂停',
    'failed': '🔴 失败',
    'delayed': '🟡 延迟'
  }[status];
}
```

## 后端实现

### API 端点
`GET /api/scheduled-tasks`

### 代码位置
`backend/main.py` (第 114-135 行)

### 管理者
🟣 震荡波 (团队优化师)

## 使用指南

### 查看定时任务
1. 打开看板：http://localhost:3020
2. 点击侧边栏 **⏰ 定时任务**
3. 查看所有定时任务状态

### 筛选任务
1. 使用负责人下拉框筛选
2. 查看特定智能体的任务

### 刷新数据
点击页面右上角 **🔄 刷新** 按钮

## 扩展建议

### 短期
1. **任务控制**: 添加暂停/启动任务功能
2. **执行历史**: 显示最近执行记录
3. **告警通知**: 失败任务自动通知

### 中期
1. **任务编辑**: 修改任务频率和时间
2. **统计分析**: 成功率趋势图
3. **依赖管理**: 任务间依赖关系

### 长期
1. **智能调度**: 基于负载自动调整
2. **预测分析**: 预测执行时间
3. **自动化修复**: 失败任务自动重试

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/main.py` | API 端点 |
| `frontend/index-old.html` | 前端展示 |
| `data/scheduled-tasks.json` | 任务数据 |
| `docs/SCHEDULED-TASKS-MODULE.md` | 本文档 |

---

**版本**: 1.0  
**创建日期**: 2026-04-07  
**管理者**: 震荡波 (团队优化师 🟣)  
**前端实现**: 多纳泰罗 (前端开发 🟪)
