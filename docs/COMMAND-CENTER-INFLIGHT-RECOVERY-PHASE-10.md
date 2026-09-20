# Command Center 第十阶段：在途任务故障恢复与幂等续跑

## 结论

已完成隔离 PostgreSQL 实演，结果为 **PASS**。任务在 Worker 已领取、WorkRun 已进入
`running`、受控副作用已经落地后发生心跳丢失；新的 Worker 成功接管并完成任务，未创建第二个
WorkRun，未重复执行副作用，也未重复生成步骤完成或任务完成事件。

本阶段同时补齐了任务终态幂等：`complete_mission` 对已完成任务直接返回持久化结果。这样即使
评估 Worker 已提交完成事务、但在收到确认前崩溃，恢复后重放完成命令也不会再次写入完成事件
或最终交付通知。

## 故障模型

1. `worker-a` 领取步骤和 WorkRun，持久化租约；
2. 受控适配器以步骤固定幂等键写入一次回执；
3. 注入 Worker 心跳丢失，使步骤租约与 WorkRun 租约过期；
4. 重建 Command Center 与 WorkRun 服务实例，模拟新进程恢复；
5. `worker-b` 重排并接管同一步骤、同一个 WorkRun；
6. 使用相同幂等键再次调用适配器，只读取首次回执；
7. 验证旧租约 token 无法完成步骤；
8. 完成步骤、评估任务，并重放一次任务完成命令；
9. 重建 LangGraph PostgreSQL runtime，从 approval checkpoint 恢复并重复 resume。

演练使用从生产库导出的**仅结构快照**创建临时 PostgreSQL 数据库。没有复制生产业务数据，
没有调用真实外部写入适配器，也没有给在线 Worker 暴露可领取任务。

## 验收结果

| 验收项 | 结果 | 机器证据 |
| --- | --- | --- |
| 过期步骤只重排一次 | 通过 | `step_requeued=1` |
| WorkRun 原位接管 | 通过 | 同一 `work_run_id`，总数 1，`lease_reclaims=1` |
| 旧 Worker 围栏 | 通过 | 旧 `lease_token` 完成请求被拒绝 |
| 副作用幂等 | 通过 | 第二次调用返回首次回执，`apply_count=1` |
| 步骤完成幂等 | 通过 | `step_completed=1` |
| 执行记录去重 | 通过 | artifact/evidence/effect 总数均等于唯一 fingerprint 数 |
| 任务终态幂等 | 通过 | 重放后 `updated_at` 不变，`mission_completed=1` |
| checkpoint 续跑 | 通过 | `awaiting_approval -> ready`，重复 resume 仍为 `ready` |

本次通过样本：

- Mission：`mission-0f0ab95e6af4`
- Mission Run：`mrun-ab392626829f4a2f`
- Step：`step-2784917b10ed`
- WorkRun：`wrun-a373f0220a284164`
- 演练耗时：0.532 秒（租约过期为故障注入，不包含真实等待窗口）

完整机器证据见 `COMMAND-CENTER-INFLIGHT-RECOVERY-DRILL.json`。

## 发现并处理的问题

### 1. 任务完成命令原先可重复落账

此前 `complete_mission` 缺少终态短路，恢复中的 evaluator 重放命令可能生成第二条
`mission_completed` 事件和新的最终通知。现在已将 `completed` 设为幂等终态，并加入端到端
回归测试。

### 2. checkpoint 迁移版本必须显式存在

首次结构克隆不包含 `checkpoint_migrations` 数据。运行时检测到版本 `-1`，按设计拒绝启动，
没有静默创建表或降级到非持久化 checkpoint。隔离库按 Alembic 迁移定义补齐版本 0–9 后，
checkpoint 重启恢复通过。这验证了生产“迁移不完整即失败关闭”的边界。

### 3. 多产物不等于重复产物

计划合同要求两个 artifact 类型，因此正常产生两条 artifact。最终验收改为比较总记录数与
唯一 fingerprint 数，验证每个合同产物只持久化一次，而不是错误地要求任务只能有一个产物。

## 自动化覆盖

新增测试 `test_inflight_recovery_reuses_work_run_and_delivers_once`，覆盖：

- 服务重建后的步骤重排；
- 同幂等键 WorkRun 原位接管；
- 旧 token fencing；
- artifact、evidence、effect 唯一持久化；
- Mission 完成命令重放；
- 最终完成事件和通知只生成一次。

可重复演练脚本：

```bash
backend/venv/bin/python backend/scripts/command_center_inflight_recovery_drill.py \
  --database-url postgresql:///isolated_drill_database \
  --report docs/COMMAND-CENTER-INFLIGHT-RECOVERY-DRILL.json
```

## 边界与后续

本阶段证明的是任务系统在 PostgreSQL 事实库和 checkpoint 可用时的在途故障恢复语义。它不等于
跨节点基础设施高可用，也不替代真实第三方 API 的幂等能力。接入业务适配器时仍必须满足：

- 将步骤 `idempotency_key` 透传给外部系统或本地 adapter ledger；
- 写入成功后持久化稳定 receipt；
- 超时结果不明时不得盲目重试，先查询 receipt/业务对象；
- 不支持幂等的外部操作必须进入补偿或人工确认流程。

