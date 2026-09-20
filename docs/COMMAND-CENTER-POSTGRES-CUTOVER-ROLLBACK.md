# Command Center PostgreSQL 灰度切换回退手册

## 核心原则

回退的事实源只能有一个。切换后只要 PostgreSQL 产生了新的业务写入，就不得仅通过修改配置
直接回到 SQLite；否则会丢失任务、事件、审批或副作用记录。必须先冻结写入、完成增量反向同步
和一致性验证，再切换事实源。

## 回退触发条件

- PostgreSQL 连续不可用且超过约定 RTO；
- 连接池持续耗尽，释放后仍不能恢复；
- 出现重复领取、重复副作用或数据一致性错误；
- checkpoint 无法恢复且阻断核心任务；
- 生产健康门禁持续为 `not_ready`。

## 回退前门禁

1. 暂停新任务入口和 Worker 领取，记录冻结时间；
2. 确认是否存在切换后新增或变更的 Mission、Step、WorkRun、事件、审批、Effect 和 checkpoint；
3. 若有增量，先从 PostgreSQL 反向同步到 SQLite，并按行数、主键摘要和业务状态对账；
4. 确认所有外部副作用都有已知状态，不把数据库回退误当作外部操作回滚；
5. 由回退负责人确认允许重启单实例 3021。

## 两种恢复点

### 当前 SQLite 回退库

`backend/data/unified_dashboard.db` 已同步 3 个历史过期 WorkRun 的阻塞状态和审计事件。它适合
作为切换时点的回退基线，但不自动包含切换后新增的 PostgreSQL 写入。

### 原始只读快照

`backups/command-center-cutover-20260918-phase6/unified_dashboard.before-cutover.db` 保留切换前原貌，
SHA-256 为 `c6bcdc608d01a2c772ebbcb79c3eed2a4c236579d1dde06030cdadcba477c561`。
恢复该快照会丢弃切换时点后的所有变更，只能用于灾难恢复或取证，不能作为常规一键回退。

## 配置回退步骤

以下操作只能在“写入已冻结、增量已同步、回退负责人已批准”后执行：

```bash
cp -p backups/command-center-cutover-20260918-phase6/env.before-cutover .env
launchctl kickstart -k gui/501/ai.openclaw.agent-system-3021
```

重启后必须依次验证：

1. `/health` 返回 `status=ok`；
2. `/api/v3/command-center/health` 的事实库后端符合回退目标；
3. Mission、Step、WorkRun、事件和 artifact 计数、主键摘要一致；
4. 过期活跃租约为 0；
5. 随机抽查审批、事件序列和外部副作用状态；
6. 确认无误后再恢复新任务入口。

## 回退失败处理

若 SQLite 对账失败，不继续开放写入。恢复 PostgreSQL 配置并重启 3021，保持 PostgreSQL 为唯一
事实源；随后从快照和审计事件中修复回退库。任何时候都禁止两个事实源同时接收业务写入。
