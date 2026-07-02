# HEARTBEAT 定时任务管理系统

> **版本**: 2.1  
> **创建**: 2026-04-07 by 震荡波 (🟣 团队优化师)  
> **最后更新**: 2026-04-07 16:15  
> **管理者**: 🟣 震荡波 (团队优化师)

---

## 📋 系统概述

本系统用于统一管理所有智能体的定时任务，避免任务冲突和时间重叠，并提供任务执行监控。

**🟣 所有定时任务由震荡波统一管理**,包括调度、监控、冲突检测和优化。

### 核心功能

1. **统一调度** - 震荡波统一管理所有定时任务的执行时间
2. **冲突检测** - 自动检测并预防任务时间冲突
3. **执行监控** - 追踪任务执行状态和历史
4. **负载均衡** - 避免同一时间过多任务并发执行
5. **API 接口** - 为前端看板提供定时任务状态数据

---

## 🟣 震荡波的管理职责

### 管理范围

**所有定时任务均由震荡波 (🟣 团队优化师) 统一管理**,包括:

1. **任务调度** - 决定每个定时任务的执行时间
2. **冲突协调** - 检测并解决任务时间冲突
3. **执行监控** - 追踪任务执行状态和成功率
4. **性能优化** - 根据执行情况优化任务频率和时间
5. **数据提供** - 为前端看板提供定时任务状态 API

### 管理机制

#### 1. 调度机制

震荡波使用以下策略调度定时任务:

- **时间片分配**: 将每小时划分为多个时间片，避免任务集中
- **优先级调度**: 高优先级任务优先分配黄金时间
- **负载均衡**: 避免同一智能体同时执行多个任务
- **弹性调整**: 根据实际执行情况动态调整时间

#### 2. 监控机制

震荡波监控以下指标:

- **执行成功率**: 任务成功执行次数 / 总执行次数
- **平均执行时长**: 任务平均耗时
- **超时次数**: 超过预设时间的执行次数
- **失败告警**: 失败时是否及时通知负责人

**监控日志位置**: `~/.openclaw/workspace/logs/heartbeat-execution.json`

#### 3. 冲突检测机制

震荡波自动检测以下冲突:

- **时间重叠**: 两个任务在同一时间执行
- **资源竞争**: 两个任务使用相同的设备或 API
- **依赖关系**: 任务 B 依赖任务 A 完成，但调度时间早于 A

**冲突检测工具**:
```python
from task_manager import TaskRecordManager
manager = TaskRecordManager()
conflicts = manager.check_schedule_conflicts()
```

#### 4. 优化机制

震荡波定期优化定时任务:

- **频率优化**: 根据任务重要性调整执行频率
- **时间优化**: 根据执行时长调整时间片分配
- **批量执行**: 将相似任务批量执行减少 API 调用
- **智能跳过**: 如果上次任务未完成，跳过本次执行

---

## ⏰ 完整定时任务清单

> **数据来源**: HEARTBEAT.md  
> **整理时间**: 2026-04-07 16:15  
> **管理者**: 🟣 震荡波

### 任务总览

| 序号 | 任务名称 | 负责人 | 频率 | 执行时间 | 优先级 |
|------|----------|--------|------|----------|--------|
| 1 | 团队工作看板汇报 | 擎天柱 | 每 3 小时 | 09:00/12:00/15:00/18:00/21:00 | 🟡 中 |
| 2 | 邮件检查 | 感知器 | 每 30 分钟 | 08:00-22:00 (:00/:30) | 🔴 高 |
| 3 | 开发任务检查 | 李奥纳多 | 每 1 小时 | 全天 24 小时 (:05) | 🟡 中 |
| 4 | 集群设备心跳检查 | 大黄蜂 | 每 30 分钟 | 全天 24 小时 (:15/:45) | 🟢 低 |
| 5 | Isaac Sim 安装检查 | 铁皮 | 每 3 小时 | 全天 24 小时 (:20) | 🟢 低 |

**总计**: 5 个定时任务

---

### 任务详情

#### 1. 团队工作看板汇报

- **任务 ID**: SCHED-001
- **负责人**: 🤖 擎天柱 (Optimus)
- **频率**: 每 3 小时一次
- **执行时间**: 09:00, 12:00, 15:00, 18:00, 21:00
- **时间片**: :10 分 (避免整点高峰)
- **优先级**: 🟡 中
- **执行时长**: ~2 分钟
- **接收人**: 孙总 (Feishu)

**汇报内容**:
1. 当前任务列表
2. 各智能体工作状态
3. 完成情况统计
4. 待办事项

**回复签名**: 🤖 擎天柱 / 汽车人团队

---

#### 2. 邮件检查

- **任务 ID**: SCHED-002
- **负责人**: 🚗 感知器
- **频率**: 每 30 分钟一次
- **执行时间**: 08:00 - 22:00
- **时间片**: :00 和 :30 分
- **优先级**: 🔴 高
- **执行时长**: ~5 分钟
- **邮箱**: 38261135@qq.com

**分发规则**:
- 📧 **发票邮件** → 🚗 感知器 (财务归档) ✅
- 📄 **论文邮件** → 🚗 感知器 (检索并报告孙总) ✅
- ❌ 其他邮件自动忽略

**发票关键词**: 发票、行程单、机票、酒店、淘宝、京东、账单

**论文关键词**: 期刊、论文、投稿、审稿、录用、版面费、期刊社、编辑、学术、会议、征文

---

#### 3. 开发任务检查

- **任务 ID**: SCHED-003
- **负责人**: 🐢 李奥纳多 (Leonardo)
- **频率**: 每 1 小时一次
- **执行时间**: 全天 24 小时
- **时间片**: :05 分
- **优先级**: 🟡 中
- **执行时长**: ~3 分钟
- **团队**: 忍者神龟 (李奥纳多/拉斐尔/多纳泰罗/米开朗基罗)

**检查流程**:
1. 检查当前开发任务状态
2. 有任务 → 继续开发 → 汇报进度
3. 无任务 → 设计方案 → 提交孙总审核

**记录文件**: `~/.openclaw/workspace/memory/ninja-turtle-tasks.json`

---

#### 4. 集群设备心跳检查

- **任务 ID**: SCHED-004
- **负责人**: 🤖 大黄蜂 (Bumblebee)
- **频率**: 每 30 分钟一次
- **执行时间**: 全天 24 小时
- **时间片**: :15 和 :45 分
- **优先级**: 🟢 低
- **执行时长**: ~1 分钟

**检查设备**:
| 设备 | IP | 角色 | 检查方式 |
|------|-----|------|----------|
| 擎天柱-MacMini | 192.168.31.41 | 主服务器 | Ping + 端口 |
| 李奥纳多-MacBookPro | 192.168.31.144 | 开发工作站 | Ping |
| 铁皮-LinuxWS | 192.168.1.4 | AI 训练服务器 | SSH + 端口 |

**告警机制**:
- 🔴 **设备离线** → 立即报告孙总
- 🟡 **端口异常** → 记录到日志
- 🟢 **正常** → 更新心跳记录

**记录文件**: `~/.openclaw/workspace/logs/device-heartbeat.json`

---

#### 5. Isaac Sim 安装检查

- **任务 ID**: SCHED-005
- **负责人**: 🛡️ 铁皮
- **频率**: 每 3 小时一次
- **执行时间**: 全天 24 小时
- **时间片**: :20 分
- **优先级**: 🟢 低
- **执行时长**: ~2 分钟
- **设备**: 192.168.1.4

**检查项目**:
- [ ] Omniverse Launcher 安装状态
- [ ] Isaac Sim 下载进度
- [ ] Isaac Sim 安装状态
- [ ] 验证测试运行

**汇报机制**:
- 🟡 安装中 - 每 3 小时汇报进度
- ✅ 安装完成 - 立即汇报孙总
- ❌ 安装失败 - 立即汇报并说明原因

---

## 🕐 任务调度时间表

### 每小时任务分布

```
分钟  任务                      负责人
:00   邮件检查                  感知器
:05   开发任务检查              李奥纳多
:10   团队工作看板汇报 (3 小时)   擎天柱
:15   集群设备心跳检查          大黄蜂
:20   Isaac Sim 安装检查 (3 小时) 铁皮
:30   邮件检查                  感知器
:45   集群设备心跳检查          大黄蜂
```

### 冲突检查结果

✅ **无冲突** - 所有定时任务已错开执行时间

**优化措施**:
- 邮件检查在 `:00` 和 `:30` 分执行
- 开发任务检查在 `:05` 分执行 (避免整点高峰)
- 团队汇报在 `:10` 分执行 (给其他任务留出时间)
- 设备心跳在 `:15` 和 `:45` 分执行 (错开邮件检查)
- Isaac Sim 检查在 `:20` 分执行 (在团队汇报后)

---

## 📊 执行监控

### 监控指标

震荡波监控以下指标:

- **执行成功率**: 任务成功执行次数 / 总执行次数
- **平均执行时长**: 任务平均耗时
- **超时次数**: 超过预设时间的执行次数
- **失败告警**: 失败时是否及时通知负责人

### 监控日志位置

```
~/.openclaw/workspace/logs/heartbeat-execution.json
```

### 日志格式

```json
{
  "task_id": "SCHED-001",
  "task_name": "团队工作看板汇报",
  "scheduled_time": "2026-04-07T09:00:00+08:00",
  "actual_start": "2026-04-07T09:00:03+08:00",
  "actual_end": "2026-04-07T09:02:15+08:00",
  "duration_seconds": 132,
  "status": "success",
  "owner": "擎天柱",
  "managed_by": "震荡波",
  "error_message": null,
  "retry_count": 0
}
```

---

## 🔌 前端 API 接口

### 接口地址

```
GET /api/scheduled-tasks
```

### 接口描述

获取所有定时任务的状态信息，用于前端看板展示。

**管理者**: 🟣 震荡波  
**数据更新**: 实时  
**缓存策略**: 1 分钟

### 请求参数

无

### 响应格式

```json
{
  "managed_by": "震荡波",
  "last_updated": "2026-04-07T16:15:00+08:00",
  "total_tasks": 5,
  "active_tasks": 5,
  "tasks": [
    {
      "id": "SCHED-001",
      "name": "团队工作看板汇报",
      "owner": "擎天柱",
      "schedule": "每 3 小时",
      "time_slot": "09:00/12:00/15:00/18:00/21:00",
      "status": "active",
      "priority": "medium",
      "last_run": "2026-04-07T15:10:00+08:00",
      "next_run": "2026-04-07T18:10:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 120,
      "execution_count": 15
    },
    {
      "id": "SCHED-002",
      "name": "邮件检查",
      "owner": "感知器",
      "schedule": "每 30 分钟",
      "time_slot": "08:00-22:00 (:00/:30)",
      "status": "active",
      "priority": "high",
      "last_run": "2026-04-07T16:00:00+08:00",
      "next_run": "2026-04-07T16:30:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 300,
      "execution_count": 28
    },
    {
      "id": "SCHED-003",
      "name": "开发任务检查",
      "owner": "李奥纳多",
      "schedule": "每 1 小时",
      "time_slot": "全天 24 小时 (:05)",
      "status": "active",
      "priority": "medium",
      "last_run": "2026-04-07T16:05:00+08:00",
      "next_run": "2026-04-07T17:05:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 180,
      "execution_count": 24
    },
    {
      "id": "SCHED-004",
      "name": "集群设备心跳检查",
      "owner": "大黄蜂",
      "schedule": "每 30 分钟",
      "time_slot": "全天 24 小时 (:15/:45)",
      "status": "active",
      "priority": "low",
      "last_run": "2026-04-07T15:45:00+08:00",
      "next_run": "2026-04-07T16:15:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 60,
      "execution_count": 48
    },
    {
      "id": "SCHED-005",
      "name": "Isaac Sim 安装检查",
      "owner": "铁皮",
      "schedule": "每 3 小时",
      "time_slot": "全天 24 小时 (:20)",
      "status": "active",
      "priority": "low",
      "last_run": "2026-04-07T15:20:00+08:00",
      "next_run": "2026-04-07T18:20:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 120,
      "execution_count": 8
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| managed_by | string | 管理者 (固定为"震荡波") |
| last_updated | string | 最后更新时间 (ISO 8601) |
| total_tasks | number | 总任务数 |
| active_tasks | number | 活跃任务数 |
| tasks | array | 任务列表 |
| tasks[].id | string | 任务 ID |
| tasks[].name | string | 任务名称 |
| tasks[].owner | string | 负责人 |
| tasks[].schedule | string | 执行频率 |
| tasks[].time_slot | string | 执行时间片 |
| tasks[].status | string | 状态 (active/inactive/suspended) |
| tasks[].priority | string | 优先级 (high/medium/low) |
| tasks[].last_run | string | 上次执行时间 |
| tasks[].next_run | string | 下次执行时间 |
| tasks[].success_rate | number | 成功率 (0-100) |
| tasks[].avg_duration_seconds | number | 平均执行时长 (秒) |
| tasks[].execution_count | number | 执行次数 |

### 使用示例

```javascript
// 获取定时任务列表
fetch('/api/scheduled-tasks')
  .then(response => response.json())
  .then(data => {
    console.log(`管理者：${data.managed_by}`);
    console.log(`总任务数：${data.total_tasks}`);
    
    data.tasks.forEach(task => {
      console.log(`${task.name} - 下次执行：${task.next_run}`);
    });
  });
```

---

## 🔧 任务配置管理

### 添加新定时任务

1. 在 `task-records/scheduled-tasks.json` 中添加任务配置
2. 运行冲突检测确保无时间冲突
3. 更新本文档的任务时间表
4. 通知相关智能体负责人
5. 更新数据文件 `~/WorkSpace/team-dashboard/data/scheduled-tasks.json`

### 任务配置模板

```yaml
task_id: "SCHED-XXX-001"
name: "任务名称"
owner: "负责人"
schedule:
  type: "interval"  # cron / interval / specific_time
  interval_minutes: 30
  time_of_day: "09:00"  # 如果是 specific_time
  cron_expression: "0 */3 * * *"  # 如果是 cron
timeout_minutes: 30
retry_count: 3
alert_on_failure: true
notify_channel: "feishu"
managed_by: "震荡波"
```

---

## 📈 效率优化建议

### 当前优化状态

✅ **已优化**:
- 邮件检查和设备心跳已错开执行时间
- 团队汇报时间间隔合理 (3 小时)
- 开发任务检查频率适中 (每小时)
- 所有任务由震荡波统一管理

⚠️ **待优化**:
- 考虑在夜间 (23:00-07:00) 降低检查频率
- 为长时间任务添加进度追踪
- 添加任务执行失败自动重试机制

### 建议改进

1. **动态调整频率**: 根据任务重要性动态调整检查频率
2. **批量执行**: 将相似任务批量执行减少 API 调用
3. **智能跳过**: 如果上次任务未完成，跳过本次执行
4. **负载均衡**: 避免同一智能体同时执行多个任务

---

## 🛠️ 使用指南

### 查看定时任务状态

```bash
cd ~/.openclaw/workspace/task-records
python3 task_manager.py
```

### 检查任务冲突

```python
from task_manager import TaskRecordManager
manager = TaskRecordManager()
conflicts = manager.check_schedule_conflicts()
print(conflicts)
```

### 生成执行报告

```python
report = manager.generate_efficiency_report(days=7)
print(report)
```

### 访问前端 API

```bash
curl http://localhost:3010/api/scheduled-tasks
```

---

## 📝 更新日志

### v2.1 (2026-04-07 16:15) - 震荡波

- ✅ 明确所有定时任务由震荡波统一管理
- ✅ 列出完整的定时任务清单 (5 个任务)
- ✅ 添加管理机制说明 (调度/监控/冲突检测/优化)
- ✅ 提供前端 API 接口文档 (`GET /api/scheduled-tasks`)
- ✅ 创建数据文件 `~/WorkSpace/team-dashboard/data/scheduled-tasks.json`

### v2.0 (2026-04-07) - 震荡波

- ✅ 建立统一的任务记录系统
- ✅ 实现定时任务冲突检测
- ✅ 添加任务执行监控机制
- ✅ 生成团队效率分析报告

### v1.0 (2026-03-17) - 初始版本

- 基础 HEARTBEAT.md 定时任务清单
- 邮件检查、团队汇报、开发任务检查

---

## 📞 联系方式

**管理者**: 🟣 震荡波 (团队优化师)

**文档位置**: 
- 管理文档：`~/WorkSpace/team-dashboard/HEARTBEAT-MANAGEMENT.md`
- 数据文件：`~/WorkSpace/team-dashboard/data/scheduled-tasks.json`
- 任务系统：`~/.openclaw/workspace/task-records/`

**问题反馈**:
- 在任务系统中创建改进任务
- Feishu 私信震荡波

---

*最后更新：2026-04-07 16:15*  
*管理者：🟣 震荡波*
