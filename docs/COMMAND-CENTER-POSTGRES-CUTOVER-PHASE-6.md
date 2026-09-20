# Command Center PostgreSQL 灰度切换：第六阶段

## 阶段结论

2026-09-18，单实例 3021 已从 SQLite 事实源切换到 PostgreSQL。Command Center、WorkRun
和 LangGraph checkpoint 当前均使用 `team_dashboard` PostgreSQL；本阶段完成了切换前快照、
受控重启、在线读写冒烟、切换后对账、短周期观察和前端实页核验。

本结论只覆盖“单实例受控灰度”。第二 Worker、真实 PostgreSQL 重启/主库切换和网络分区演练
尚未执行，因此不宣称已经具备跨节点高可用能力。

## 切换前保护

- SQLite 在线快照：`backups/command-center-cutover-20260918-phase6/unified_dashboard.before-cutover.db`
- 快照 SHA-256：`c6bcdc608d01a2c772ebbcb79c3eed2a4c236579d1dde06030cdadcba477c561`
- 快照完整性：`PRAGMA integrity_check=ok`
- 快照核心计数：11 missions、30 steps、24 work runs、97 work-run events、6 artifacts
- 原环境文件已单独备份；文档不记录其中的密钥或完整 DSN。

3021 受控环境启用了以下无密码配置：

```dotenv
COMMAND_CENTER_DATABASE_URL=postgresql+psycopg2:///team_dashboard
WORK_RUN_DATABASE_URL=postgresql+psycopg2:///team_dashboard
COMMAND_CENTER_LANGGRAPH_CHECKPOINT_URL=postgresql:///team_dashboard
COMMAND_CENTER_DB_POOL_MIN=1
COMMAND_CENTER_DB_POOL_MAX=10
COMMAND_CENTER_DB_POOL_ACQUIRE_TIMEOUT=5
```

## 切换执行与数据处置

LaunchAgent 从旧进程 PID 7287 平滑重启到 PID 20333，当前处于 running/listening 状态。

切换前发现 3 个无 Mission/Step 绑定、租约已在 2026 年 7—8 月过期的历史 WorkRun。它们没有
继续执行的合法上下文，因此通过正式状态迁移接口标记为 `blocked`，失败码为
`stale_legacy_lease`，操作者为 `command-center-cutover`。对应事件随后同步到 SQLite 回退库，
保证回退不会重新激活历史租约；原始状态仍保留在切换前快照中。

处置后的核心计数为：24 work runs、100 work-run events、6 artifacts，过期活跃租约为 0。

## 在线验证

在线冒烟报告：`COMMAND-CENTER-POSTGRES-CUTOVER-SMOKE.json`。

验证通过项：

1. 公共 `/health` 正常；
2. Command Center 事实库为 PostgreSQL；
3. 生产健康聚合状态为 `ready`；
4. 连接池状态为 `ready`，无获取超时和连接失败；
5. 过期活跃租约为 0；
6. LangGraph checkpoint 状态为 `ready`，后端为 PostgreSQL；
7. 临时 WorkRun 写入成功，并在同一事务中清理，无残留数据。

切换后执行了 6 次、间隔 5 秒的在线观察，6/6 样本健康。观察期间任务总数稳定为 11，
连接池峰值为 1，获取超时、连接失败和过期租约均为 0。机器可读证据见
`COMMAND-CENTER-POSTGRES-CUTOVER-OBSERVATION.json`。

## 一致性验证

- Command Center：19/19 表行数和主键 SHA-256 一致；
- WorkRun：24 runs、100 events、6 artifacts 行数和主键 SHA-256 一致；
- Alembic 目标版本：`20260920_langgraph_pg`；
- SQLite 回退同步：3 个历史 WorkRun 状态及 3 条审计事件已同步并验证。

证据文件：

- `COMMAND-CENTER-POSTGRES-CUTOVER-RECONCILIATION.json`
- `WORK-RUN-POSTGRES-CUTOVER-RECONCILIATION.json`
- `COMMAND-CENTER-CUTOVER-FALLBACK-SYNC.json`

## 前端实页核验

在实际 `http://127.0.0.1:3021/command-center` 页面刷新后，管理员可见：

- 生产运行门禁：就绪；
- 事实库：POSTGRESQL；
- 连接池：2/10，峰值 3，超时 0；
- 执行租约：0 个过期；
- 流程检查点：postgresql / ready / 禁止运行时建表。

这证明前端展示来自重启后的实时生产健康接口，不是静态占位数据。

## 当前发布边界

当前状态为“单实例 PostgreSQL 受控灰度通过”。仍有以下生产限制：

1. 冒烟环境的认证模式仍为 development session，不能直接对公网开放；
2. 尚未加入第二 Worker，也未完成真实数据库故障切换演练；
3. 切换后若产生新的 PostgreSQL 业务写入，不能直接改回 SQLite，必须先停止入口并反向同步；
4. 外部业务适配器仍需分别完成沙箱、限流、超时和补偿验证。

详细回退步骤见 `COMMAND-CENTER-POSTGRES-CUTOVER-ROLLBACK.md`。

## 下一阶段

在维护窗口内增加第二 Worker，验证跨进程任务领取、幂等和租约恢复；随后以明确 RTO/RPO、
负责人和通知机制执行 PostgreSQL 重启/故障切换演练。完成前保持单实例运行。
