# Command Center 数据库连接恢复：第八阶段

## 阶段结论

2026-09-18，3021 完成应用级 PostgreSQL 连接中断演练。演练只终止
`team_dashboard` 中 `application_name=agent-system-command-center` 的 6 条连接，未重启
PostgreSQL，也未终止其他应用会话。

结果通过：接口在采样中始终可用，连接池自动识别并丢弃失效连接，连续 3 次功能健康确认的
RTO 为 1.217 秒；Mission、Step、事件、Workflow、WorkRun、WorkRun 事件和产物的记录数及
主键 SHA-256 前后一致，RPO 为 0；双 Worker 保持 2/2 在线，活动过期租约为 0。

## 实现内容

### 连接检出预检

PostgreSQL 连接池默认启用 `COMMAND_CENTER_DB_POOL_PRE_PING=true`。每次检出连接时先执行
`SELECT 1`：

1. 连接可用时进入业务事务；
2. 连接失效时关闭并从池中丢弃；
3. 透明创建新连接并仅重试一次；
4. 第二次仍失败则故障关闭，不降级写入其他存储。

健康指标新增：

- `pre_ping`：是否启用检出预检；
- `stale_connections_discarded_total`：被丢弃的失效连接数；
- `reconnects_total`：成功重连数；
- `connection_failures_total`：连接失败数。

前端生产门禁同步展示重连次数，便于管理员区分“当前不可用”和“已恢复但近期发生过故障”。

### Worker 双数据存储心跳

Worker 注册和周期心跳同时探测 WorkRun 事实库，再更新 Command Center Worker 心跳。若
WorkRun 账本不可用，该 Worker 不会继续被误报为完整健康实例。

### 故障可见窗口

功能恢复后，生产状态保留 5 分钟 `degraded` 事件窗口。这不是持续故障：业务端点、数据库、
checkpoint、Worker 和租约均可已经健康，但近期连接失败仍对前端和监控可见。窗口结束且没有
新增失败后，状态自动回到 `ready`。

## 演练保护措施

- 演练前拒绝在 Step、Workflow、Compensation 或 Outbox 存在活动租约时注入故障；
- 演练前创建逻辑备份
  `backups/command-center-db-fault-phase8-20260918/team_dashboard.before-fault-drill.dump`；
- 备份大小 19 MB，SHA-256：
  `c0dd6d3aedd21ee49a2ec3758ecef8db811efa9c323a6dc7e39e9d205b918f3d`；
- 只按数据库名与 `application_name` 精确选择连接，不操作 PostgreSQL 服务；
- 演练后对 7 类业务事实做记录数与主键摘要对账。

## 实测结果

证据文件：`COMMAND-CENTER-DATABASE-FAULT-DRILL.json`。

| 指标 | 结果 |
| --- | --- |
| 演练范围 | 仅 agent-system 连接 |
| 被终止连接 | 6 |
| HTTP/功能恢复 | 1.217 秒，连续 3 次健康 |
| RPO | 0 |
| 双 Worker | 2/2 在线 |
| 活动租约 | 演练前 0，演练后 0 |
| 失效连接丢弃 | 1 |
| 自动重连 | 1 |
| 获取超时 | 0 |
| Checkpoint | ready |

演练结束时 `production_status=degraded` 属于预期的 5 分钟事件可见窗口。冷却期后完成 6/6
连续健康样本，均为 `production_status=ready`、Worker 2/2、过期租约 0、checkpoint ready，
累计连接失败和重连计数稳定在 1，没有新增故障。恢复观察另存为
`COMMAND-CENTER-DATABASE-FAULT-RECOVERY-OBSERVATION.json`。

## 验证与边界

- Repository、健康门禁及路由定向测试通过；
- Worker/WorkRun/Workflow 定向测试通过；
- 前端生产门禁测试和生产构建通过；
- 后端全量回归 782 passed、84 skipped、2 xfailed；
- 前端全量 24 个文件、107 passed、3 expected fail；TypeScript 与生产构建通过；
- 3021 实页可见 PostgreSQL、重连 1、Worker 2/2、过期租约 0 和 checkpoint ready。

本阶段证明的是应用连接被服务端断开后的自愈能力，不等于数据库高可用。两个 Worker 仍在同一
主机，PostgreSQL 仍是单实例。真实 PostgreSQL 重启、主库切换、网络分区以及跨主机 Worker
演练需要独立维护窗口、通知负责人和回退授权；在这些完成前，多实例/数据库高可用仍为 NO-GO。
