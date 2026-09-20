# 规范业务流生产化验证报告

## 验证范围

本次验证覆盖任务接收、背景冻结、规范拆解、计划审批、高风险步骤授权、
依赖调度、幂等与租约、产物/证据门禁、Effect Journal、补偿执行和交付闭环。

验证日期：2026-09-19。

## 验证结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 前端生命周期映射 | 通过 | 8 阶段状态映射、控制点优先级和补偿阻断单测 |
| 前端真实组件呈现 | 通过 | 组件渲染验证流程、门禁、Effect Journal 和补偿交互 |
| TypeScript 与生产构建 | 通过 | `vue-tsc -b` 和 `vite build` |
| 前端全量 Vitest | 通过 | 24 个测试文件通过，107 passed、3 expected fail，进程正常退出 |
| 单节点并发领取 | 通过 | 32 个并发请求只有 1 个 worker 获得执行租约 |
| 持久化 Repository 边界 | 通过 | 事务、回滚、重启恢复、存储能力声明和错误后端故障关闭均通过 |
| PostgreSQL 事实表迁移 | 通过 | Alembic `20260918_command_center_pg`，19 张事实表及关键唯一索引已落库 |
| SQLite 数据迁移 | 通过 | 19/19 表行数与主键 SHA-256 校验一致，整体事务提交 |
| PostgreSQL 双 Worker | 通过 | `SKIP LOCKED` 下规划唯一领取、两个步骤并行领取且 Mission 完整闭环 |
| WorkRun PostgreSQL | 通过 | 24 runs、97 events、6 artifacts 单事务迁移并完成双连接幂等领取门禁 |
| LangGraph PostgreSQL checkpoint | 通过 | Alembic 管理 schema，真实中断、重建、resume 及重复 resume 通过 |
| Command Center + LangGraph 整体链路 | 通过 | 计划审批、checkpoint 中断/恢复、Mission 激活在 PostgreSQL 上闭环 |
| PostgreSQL 有界连接池 | 通过 | 上限、获取超时、失效连接关闭、优雅释放与运行指标已落地 |
| 容量与耗尽门禁 | 通过 | 24/24 请求完成，池上限 4/峰值 4，耗尽时故障关闭且释放后恢复 |
| 数据库不可达演练 | 通过 | 隔离端口模拟在 171.18 ms 内失败，无降级写入或无限等待 |
| 生产健康可视化 | 通过 | 管理端展示连接池、过期租约、WorkRun 重试和 checkpoint 完整性 |
| 3021 PostgreSQL 灰度切换 | 通过 | 单实例已切流，在线读写冒烟、19 表对账、WorkRun 对账及 6/6 观察样本通过 |
| SQLite 回退基线 | 通过 | 1.1 GB 在线快照完整，3 个历史过期 WorkRun 的阻塞状态和事件已同步至回退库 |
| 前端生产门禁实页 | 通过 | 当前实页显示 PostgreSQL、连接池 0/5、超时 0、过期租约 0、checkpoint ready |
| 双 Worker 心跳门禁 | 通过 | 2/2 实例在线；20 秒心跳窗口，实例不足时整体生产状态自动降级 |
| Worker 卡死与恢复 | 通过 | 第二 Worker 无租约暂停后门禁降至 1/2，恢复后自动回到 2/2 |
| 双 Worker 恢复观察 | 通过 | 6/6 样本健康，连接池峰值 2、超时 0、连接失败 0、过期租约 0 |
| 数据库连接预检与重连 | 通过 | 每次检出执行 pre-ping，失效连接自动丢弃并透明重连一次，前端展示重连指标 |
| 应用连接中断演练 | 通过 | 精确终止本系统 6 条连接，1.217 秒连续恢复确认，RPO=0、双 Worker 2/2、租约 0 |
| PostgreSQL 服务重启 | 通过 | 新 postmaster 代次，数据库 7.254 秒恢复、功能 8.467 秒恢复，RPO=0、Worker 2/2 |
| 在途任务故障恢复 | 通过 | 过期步骤重排 1 次、同一 WorkRun 接管、旧 token 围栏、副作用/完成/交付均无重复 |
| checkpoint 幂等续跑 | 通过 | PostgreSQL checkpoint 重建后 `awaiting_approval -> ready`，重复 resume 状态不变 |
| 审批及重试安全 | 通过 | 合同指纹、单次消费、授权过期、中断后重新审批 |
| 副作用恢复 | 通过 | 补偿审批、租约、回执和恢复证据闭环 |
| Mission Run 追踪 | 通过 | run ID、correlation ID、单调事件序列和历史回填 |
| 实际数据库完整性 | 通过 | `PRAGMA integrity_check=ok`，WAL 已开启，9/9 关键表存在 |
| 后端回归 | 通过 | 全量测试 787 passed、84 skipped、2 xfailed；PostgreSQL 门禁额外显式开启并通过 |

## 上线判定

### 受控单节点试点：GO WITH CONDITIONS

可以用于单节点、单主 worker、管理员在环的受控生产试点，条件如下：

1. 生产环境开启登录和角色权限，禁用 development session；
2. 首批业务保持证据门禁 `pilot`，核对误拒绝率后切换 `strict`；
3. 高风险步骤和补偿必须由管理员审批；
4. 已完成 1.1 GB SQLite 数据库快照，后续定期验证恢复；
5. 保持当前双 Worker 连接预算；扩大实例数前重新计算所有 Command Center 与 WorkRun 池。
6. 持续将全量 Vitest 与生产构建作为前端发布强制门禁。

### 多实例/高可用生产：NO-GO

Command Center、Work Run 和 LangGraph checkpoint 已完成 PostgreSQL 改造、真实链路验证、
3021 灰度切流、双 Worker 卡死恢复以及应用连接中断自愈演练，但两个 Worker 仍位于同一主机，
单机数据库服务重启已经通过，但尚未完成主库切换和跨节点演练。在完成以下工作前，
不应宣称具备跨节点高可用能力：

- 对数据库主库切换、网络分区和连接池耗尽执行压测；
- 在维护窗口验证 PostgreSQL 主库切换和网络分区恢复；
- 将当前 development session 切换为正式登录和角色授权；
- 建立任务成功率、门禁拒绝率、租约过期率、补偿率和 P95 耗时告警；
- 对外部业务适配器进行沙箱、限流、超时和灾备验证。

## 第二阶段落地状态

Command Center 已通过 `CommandCenterRepository` 接口获得独立的事务和存储能力边界，
现有 SQLite 实现声明 `durable=true`、`transactional_claims=true`、
`multi_instance=false`。健康接口会返回该能力矩阵，部署系统可以据此阻止把单节点存储
误当作高可用存储。

`COMMAND_CENTER_DATABASE_URL` 已支持 SQLite 和 PostgreSQL；未知后端仍会明确启动失败。
PostgreSQL Repository 使用 `FOR UPDATE SKIP LOCKED`，并声明 `multi_instance=true`。
该能力仅描述 Command Center 事实库和领取事务，不代表 Work Run、LangGraph 检查点及
整个部署拓扑已经达到跨节点高可用。

## 建议发布策略

1. 选择低风险内部业务，按 5% 任务量灰度；
2. 每日检查交付门禁误拒绝、未知副作用和补偿失败；
3. 一周内无 P0/P1 故障后扩大到 25%；
4. 在证据结构化合格率稳定后再开启 `strict`；
5. 发现租约冲突、重复副作用或补偿误执行时立即回退到人工调度。

## 第六阶段灰度切换状态

3021 已于 2026-09-18 受控切换至 PostgreSQL。切换前快照、环境备份、历史过期租约处置、
SQLite 回退同步、在线临时写入清理、19 表/WorkRun 对账、6/6 健康观察和前端实页核验均通过。
详细记录见 `COMMAND-CENTER-POSTGRES-CUTOVER-PHASE-6.md`，回退边界见
`COMMAND-CENTER-POSTGRES-CUTOVER-ROLLBACK.md`。

第六阶段当时判定为：单实例受控灰度通过；多实例/高可用仍为 NO-GO。

## 第七阶段双 Worker 状态

3021 API 内嵌 Worker 与独立 Worker 已同时运行，生产健康门禁要求 2/2 在线。受控暂停第二
Worker 后，门禁在心跳窗口内从 ready 降为 degraded，恢复进程后自动回到 ready；恢复后
6/6 连续样本健康。前端实页已显示“执行实例 2/2 在线、失联 0”。详细记录见
`COMMAND-CENTER-MULTI-WORKER-PHASE-7.md`。

当前发布判定更新为：同主机双 Worker 灰度通过；跨主机/数据库高可用仍为 NO-GO。

## 第八阶段数据库连接恢复状态

在零活动租约前提下，演练精确终止了 `team_dashboard` 中仅属于 Command Center 的 6 条连接，
未重启 PostgreSQL、未影响其他应用会话。连接池 pre-ping 丢弃 1 条失效连接并完成 1 次透明
重连；业务端点连续 3 次功能健康的确认 RTO 为 1.217 秒。7 类业务事实记录数和主键摘要前后
完全一致（RPO=0），Worker 保持 2/2 在线，活动租约保持 0，checkpoint ready。

恢复后的 5 分钟内生产状态按设计保留 `degraded` 事件可见窗口，窗口结束且无新增失败时自动
回到 `ready`；冷却期后 6/6 连续样本健康。详细记录见
`COMMAND-CENTER-DATABASE-FAULT-PHASE-8.md`，机器证据见
`COMMAND-CENTER-DATABASE-FAULT-DRILL.json` 和
`COMMAND-CENTER-DATABASE-FAULT-RECOVERY-OBSERVATION.json`。

第八阶段结束时发布判定保持不变：应用连接中断自愈已通过；当时跨主机 Worker、数据库服务
重启/主库切换、网络分区与正式身份鉴权尚未完成，因此跨主机/数据库高可用仍为 NO-GO。

## 第九阶段 PostgreSQL 服务重启状态

在独立数据库与全局对象备份完成、无其他数据库连接、四类活动租约均为 0 的维护条件下，已真实
重启 Homebrew `postgresql@17`。postmaster 启动时间发生变化；数据库 7.254 秒恢复连接，3021
在 8.467 秒内连续 3 次功能健康。7 类事实摘要完全一致（RPO=0），双 Worker 恢复 2/2，
checkpoint ready，活动租约前后均为 0；冷却期后 6/6 连续样本 ready，累计故障计数没有新增。
前端最终显示“就绪”、失败 17、重连 1。详细记录见
`COMMAND-CENTER-POSTGRES-RESTART-PHASE-9.md` 和
`COMMAND-CENTER-POSTGRES-RESTART-DRILL.json`，恢复观察见
`COMMAND-CENTER-POSTGRES-RESTART-RECOVERY-OBSERVATION.json`。

当前发布判定更新为：单机 PostgreSQL 服务重启自愈通过；真实主库切换、网络分区、跨主机
Worker 和正式身份鉴权仍未完成，因此跨节点高可用仍为 NO-GO。

## 第十阶段在途任务恢复状态

已在隔离 PostgreSQL 演练库注入“Worker 在副作用落地后丢失心跳”。新 Worker 对过期步骤仅重排
一次，复用原 WorkRun 和固定幂等键续跑；旧 lease token 被 fencing，受控副作用 apply_count
保持 1。步骤完成和 Mission 完成事件各 1 条，任务完成命令重放不再生成重复终态或最终交付。
LangGraph PostgreSQL checkpoint 在 runtime 重建后从 `awaiting_approval` 恢复到 `ready`，重复
resume 保持相同状态。详细记录见 `COMMAND-CENTER-INFLIGHT-RECOVERY-PHASE-10.md`，机器证据见
`COMMAND-CENTER-INFLIGHT-RECOVERY-DRILL.json`。

当前任务系统核心可靠性验证已闭环；跨节点高可用判定仍为 NO-GO，剩余项属于部署拓扑、网络、
身份鉴权和真实外部适配器的生产工程，不应继续扩张任务系统核心范围。
