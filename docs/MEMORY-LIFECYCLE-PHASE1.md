# 真实记忆生命周期第二步：权威账本与受控场景

## 结论

已建立记忆生命周期的权威状态账本，并将审批更新、冲突裁决、到期和遗忘接入统一状态迁移。隔离数据库中的四类受控场景全部通过：旧版、冲突败者、过期记忆和被遗忘记忆均未再被召回。

本步骤没有将受控样本写入生产记忆，也没有自动升级任何临时评测标签。

## 权威模型

权威内容仍由 `profile_facts`、`project_context_memories` 和 `agent_memories` 三类表提供；新增账本不复制可服务内容，而是记录其身份、版本、状态、内容哈希和迁移证据。

- `memory_lifecycle_records`：每个权威记忆的当前生命周期状态；
- `memory_lifecycle_events`：只追加的状态迁移与内容哈希证据；
- `memory_conflict_resolutions`：冲突胜者、败者、裁决人和理由；
- 数据库迁移标识：`020_memory_lifecycle_ledger`。

合法状态为 `active`、`superseded`、`archived`、`expired`、`tombstoned` 和 `purged`。状态机明确禁止已删除或已过期的记忆被直接复活。

## 关闭的执行链路

### 审批更新

同一个 `memory_key` 的新审批内容现在创建新权威记录，不再原地覆盖旧内容。旧版会在同一事务中转为 `superseded`，新版记录 `supersedes_ref`，旧版记录 `replaced_by_ref`。

### 派生投影退役

当审批记忆离开 `active` 状态时，同一事务会：

- 将旧向量 upsert 任务标记为过时，并排入 delete 任务；
- 排入 `memory.superseded` 或 `memory.archived` 图谱投影事件；
- 保留幂等键、任务状态和尝试记录，供重试与审计。

### 到期执行

到期时间写入账本后，指挥中心 worker 的耐久队列循环会自动执行到期迁移。已过期记忆从词法权威源排除，同时进入向量和图谱退役队列。

## 受控验收

| 场景 | 验收结果 | 关键证据 |
| --- | --- | --- |
| 更新 | 通过 | 新版可召回，旧版不可召回，版本链完整 |
| 冲突 | 通过 | 胜者保持 active，败者 superseded，裁决记录存在 |
| 到期 | 通过 | 到期记忆 expired，召回为 0 |
| 遗忘 | 通过 | 记忆 tombstoned，召回为 0 |
| 投影一致性 | 通过 | 5 条账本记录，0 条违规 |

可重复执行：

```bash
backend/venv/bin/python backend/scripts/memory_lifecycle_fixture.py
```

机器可读结果见 `docs/MEMORY-LIFECYCLE-PHASE1-FIXTURE.json`。

## 生产回填与上线核对

- 只读取现有权威内容并生成账本索引，未改动记忆内容或状态；
- 用户 `1` 共观测 15 条权威记忆，新建 15 条账本记录和 15 条初始事件；
- 回填后一致性核对：15 条记录，0 条违规；
- 3021 后端已重启并通过 `/health`；
- 专用 worker 已重启，PostgreSQL 连接恢复后 API 与 dedicated worker 均持续上报实时心跳。
- 记忆、上下文和指挥中心联合回归：173 项通过；
- 系统健康门禁：通过，0 个降级通道；
- 五智能体矩阵：5/5 通过，无作用域不变式失败。

## 边界与下一门禁

本步骤已解决“记忆状态如何变化、旧投影如何退役”，但不代表总体效果门禁已解除。主评测数据集仍有两类独立缺口：

- 80 条基线用例尚未完成人工真值复核；
- 尚未有完整 Top-5 相关性标注，因此 Precision@5 仍不可计算；
- “无相关记忆时克制回答”的 abstention 场景仍未建立。

下一步应将生命周期受控证据合并进统一效果门禁，再建立 abstention 失败模式和人工标注批次。
