# Command Center PostgreSQL 服务重启：第九阶段

## 阶段结论

2026-09-18，在备份完成、无其他数据库使用者且四类活动租约均为 0 的维护条件下，执行了真实
Homebrew PostgreSQL 17 服务重启。PostgreSQL postmaster 启动时间由
`2026-09-13T20:02:41.350562+08:00` 变为
`2026-09-18T23:43:29.786824+08:00`，证明不是连接级模拟，而是数据库服务产生了新代次。

演练通过：数据库在 7.254 秒内恢复连接，3021 数据库相关功能在 8.467 秒内连续 3 次健康；
Command Center、WorkRun 和 LangGraph checkpoint 自动恢复。7 类关键事实记录数和主键摘要
前后一致，RPO=0；双 Worker 恢复为 2/2；活动租约前后均为 0。

## 维护前保护

演练脚本 `backend/scripts/command_center_postgres_restart_drill.py` 会在重启前强制检查：

1. 服务名必须精确为 `postgresql@17`；
2. 除 `team_dashboard` 外存在任何已连接数据库时拒绝执行；
3. Step、Workflow、Compensation 或通知 Outbox 存在活动租约时拒绝执行；
4. PostgreSQL、checkpoint、双 Worker 和生产门禁基线必须为 ready；
5. 事实摘要必须在重启前完成冻结。

本阶段备份位于 `backups/command-center-postgres-restart-phase9-20260918/`：

- `team_dashboard.before-restart.dump`：19,707,574 字节，已通过 `pg_restore --list` 解析；
  SHA-256 `6e822349c927791efe132f17504ee93e61f8a21432fb04cdd5a35d03d6a9cba2`；
- `postgres-globals.before-restart.sql`：787 字节；
  SHA-256 `54d4acbaacf919ad8e128194653688422def0d279981f7d4e0f597e89c9594cf`。

## 故障与恢复时间线

| 时点 | 结果 |
| --- | --- |
| 重启前 | PostgreSQL ready，Worker 2/2，租约 0 |
| 服务停止阶段 | `/health` 保持 200，数据库相关端点短暂返回 500 |
| 约 6.6 秒 | PostgreSQL 处于 starting up |
| 7.254 秒 | 新 postmaster 可连接，数据库恢复 |
| 8.467 秒 | 3021 连续 3 次功能健康，Worker 2/2，checkpoint ready |
| 5 分钟事件窗口 | 前端保留 degraded 和累计连接失败，功能已经恢复 |
| 冷却期后 | 6/6 连续样本 ready，累计失败 17、重连 1，未出现新增故障 |

连接池在停机窗口中累计识别并丢弃 17 条失效检出连接，获取超时仍为 0。累计计数不会在恢复后
清零，用于保留故障证据；前端连接池行已同时显示峰值、超时、失败和重连计数。生产状态在五
分钟窗口结束且没有新增失败后自动回到 ready。

## 数据一致性

以下 7 类事实的记录数与按主键计算的 SHA-256 前后一致：

- orchestration missions：11；
- mission steps：30；
- mission events：137；
- workflow runs：0；
- work runs：24；
- work run events：100；
- work artifacts：6。

四类活动租约在演练前后均为 0，没有出现重复领取、遗留租约或补偿误触发。

## 证据与边界

- 机器证据：`COMMAND-CENTER-POSTGRES-RESTART-DRILL.json`；
- 冷却期恢复证据：`COMMAND-CENTER-POSTGRES-RESTART-RECOVERY-OBSERVATION.json`；
- 生产化总报告：`BUSINESS-FLOW-PRODUCTION-VALIDATION.md`。

回归结果：后端全量 782 passed、84 skipped、2 xfailed；前端全量 24 个文件、107 passed、
3 expected fail；前端 TypeScript 与生产构建通过。3021 实页最终显示“就绪”、PostgreSQL、
失败 17、重连 1、过期租约 0、checkpoint ready 和 Worker 2/2。

本阶段证明单机 PostgreSQL 服务重启能够自动恢复，但不代表主库切换或跨节点高可用。当前两个
Worker 与数据库仍在同一主机。后续仍需验证网络分区、连接风暴/退避、跨主机 Worker、真实
主从或托管数据库 failover，并将 development session 替换为正式身份鉴权。
