# Company OS v1 数据与执行契约

## 目标

把 OpenClaw 智能体、项目任务和专业产品执行统一到可恢复、可审计、可重试的交付闭环。

## 唯一事实源

`backend/data/unified_dashboard.db` 是 Company OS 的业务事实源。

| 数据 | 权威位置 | 兼容层职责 |
|---|---|---|
| 项目、任务、开发要点、项目日志 | `projects`、`project_tasks`、`development_points`、`project_logs` | V3 文档接口提供兼容视图，使用增量 upsert |
| 执行尝试 | `work_runs` | `agent_runner.json` 仅保留兼容快照 |
| 执行事件 | `work_run_events` | OpenClaw 日志不是权威状态 |
| 执行制品 | `work_artifacts` | 智能体工作区保存原文件 |
| OpenClaw dispatch queue | 非事实源 | 只负责投递，不决定最终完成状态 |
| `dashboard_v2.db` | 旧版兼容 | 不得新增 Company OS v1 业务模型 |
| JSON 文件 | 配置、导入导出、快照 | 不得作为 Run 和任务状态的最终依据 |

## 工作状态机

```text
draft → ready → claimed → running → review → verifying → completed
                  │          │          │          │
                  └──────────┴──────────┴──────────┼→ blocked
                                                  ├→ failed
                                                  └→ cancelled

blocked / failed → ready（显式重试）
```

每次重试创建新的 `attempt`，不得覆盖失败历史。同一幂等键只允许一个有效租约；租约到期后才允许其他执行者接管。

## 执行协议

1. OpenClaw queue 投递任务。
2. Runner 在 `work_runs` 原子创建或续租 Run。
3. Runner 写入 prompt、workspace、executor 和关联项目上下文。
4. 执行器运行任务；当前默认 OpenClaw Agent，Codex CLI 保留为可选后端。
5. 最终回复必须满足结构化完成契约。
6. 执行成功进入 `review`，并归档 stdout/stderr 与结果摘要。
7. 独立验证后进入 `verifying` 或 `completed`；不完整结果进入 `failed`。
8. 完成后才更新组织记忆和队列兼容状态。

## 结构化完成契约

```json
{
  "result_summary": "",
  "decisions": [],
  "blockers": [],
  "next_actions": [],
  "memory_summary": "",
  "verification": []
}
```

缺少字段、返回未来时态的中间消息或无法解析的响应，不得进入 `review`。

## 当前兼容边界

- V3 项目文档接口仍存在，但保存已改为事务内增量 upsert，不再清空全部项目表。
- V2 Task 同步暂时保留，作为旧页面兼容层；后续应改为读取统一库的投影视图。
- OpenClaw queue 和 agent instance JSON 暂时保留，但 Company OS API 必须优先返回 `work_runs`。
- 产品注册表尚待下一阶段合并为单一版本化能力目录。

## 验收基线

- SQLite 外键检查无错误。
- 服务重启后 Run 和制品仍可查询。
- 同一 dispatch 重试生成递增 attempt。
- 不完整执行结果被拒绝，完整结构化结果进入 review。
- 人工或策略审批后才进入 completed。
- 任务执行失败不会覆盖历史记录或清空其他项目数据。
