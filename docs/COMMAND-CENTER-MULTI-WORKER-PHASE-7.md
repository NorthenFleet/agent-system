# Command Center 双 Worker 灰度：第七阶段

## 阶段结论

2026-09-18，3021 已从单 Worker PostgreSQL 灰度升级为双 Worker 受控运行：

- `command-center:api-3021`：嵌入 3021 API 进程；
- `command-center:worker-2`：独立 LaunchAgent Worker，不启动第二套 HTTP、调度器或其他后台服务。

两个实例共享 PostgreSQL 事实库、WorkRun 和 LangGraph checkpoint。生产门禁要求至少 2 个
Worker 心跳在线；任意一个实例超过 20 秒未报告心跳，门禁自动降级。

## 实现内容

### Worker 运行态注册表

新增 Alembic revision `20260921_worker_registry` 和表 `command_center_workers`，记录：

- 稳定 Worker ID 与角色；
- running/stopped 状态；
- 启动时间、最后心跳和停止时间；
- PID、主机名、并行度和轮询周期等管理员运行元数据。

运行态表不属于业务事实，不参与 SQLite 到 PostgreSQL 的业务数据迁移和摘要对账。

### 心跳与故障关闭

Worker 启动时注册，默认每 5 秒续约心跳，正常停止时标记 `stopped`。生产健康接口聚合：

- `required`：要求实例数；
- `live`：20 秒窗口内在线实例数；
- `stale`：状态仍为 running、但心跳过期的实例数；
- `status`：`live >= required` 时为 ready，否则 degraded。

Worker 数不足会使整个 `/api/v3/command-center/production-health` 降级，不会被 PostgreSQL、
连接池或 checkpoint 的局部健康掩盖。

### 独立 Worker 入口

新增 `backend/scripts/run_command_center_worker.py`，只启动 Command Center Worker，不重复启动
HTTP 服务、设备监控、通用调度器和其他后台任务。LaunchAgent 配置为
`ai.openclaw.command-center-worker-2`，KeepAlive 开启。

### 连接预算

双进程中每个进程都可能创建 Command Center 与 WorkRun 连接池。为防止理论预算从约 20 条
放大到约 40 条，单池上限由 10 收紧为 5：

```dotenv
COMMAND_CENTER_DB_POOL_MIN=1
COMMAND_CENTER_DB_POOL_MAX=5
COMMAND_CENTER_REQUIRED_WORKERS=2
COMMAND_CENTER_WORKER_STALE_SECONDS=20
COMMAND_CENTER_WORKER_HEARTBEAT_SECONDS=5
```

按 2 个进程 × 2 个池 × 5 估算，最大连接预算约 20，仍为 PostgreSQL 管理、迁移、LangGraph
和其他服务保留余量。

## 上线验证

### 在线冒烟

`COMMAND-CENTER-MULTI-WORKER-SMOKE.json` 全部通过：

- PostgreSQL 事实库和 checkpoint ready；
- 2/2 Worker 在线、失联 0；
- 连接池 ready，上限 5；
- 活跃过期租约 0；
- 临时 WorkRun 插入、读取和清理成功，无残留。

### Worker 卡死演练

演练前确认第二 Worker 未持有 Step、Workflow、Compensation 或 Outbox 租约。随后向第二 Worker
发送 `SIGSTOP`：

1. 演练前：生产状态 ready，Worker 2/2，失联 0；
2. 心跳超时后：生产状态 degraded，Worker 1/2，失联 1；
3. `finally` 恢复 `SIGCONT` 后：生产状态 ready，Worker 2/2，失联 0。

完整证据见 `COMMAND-CENTER-WORKER-FAILOVER-DRILL.json`。演练未中断 3021 API，主 Worker
持续运行，也未暂停 PostgreSQL。

### 恢复后观察

恢复后执行 6 次、间隔 5 秒的在线观察，6/6 健康：

- Worker 始终 2/2，失联 0；
- 连接池峰值 2，获取超时 0，连接失败 0；
- 过期租约 0；
- checkpoint ready；
- Mission 总数稳定为 11。

证据见 `COMMAND-CENTER-MULTI-WORKER-OBSERVATION.json`。

### 前端实页

实际 3021 指挥中心已显示：

- 事实库 POSTGRESQL；
- 连接池 0/5，峰值 2，超时 0；
- 执行租约 0 个过期；
- 流程检查点 postgresql / ready；
- 执行实例 2/2 在线，失联 0 / ready。

### 回归

- 后端全量：781 passed、84 skipped、2 xfailed；
- 前端全量：24 个文件，107 passed、3 expected fail；
- 前端 TypeScript 与生产构建：通过；
- 新增脚本 `py_compile` 与 JSON 证据解析：通过。

## 回退

若第二 Worker 导致异常：

1. 先确认它没有持有活跃租约；
2. `launchctl bootout gui/501/ai.openclaw.command-center-worker-2`；
3. 将 `COMMAND_CENTER_REQUIRED_WORKERS` 临时降为 1；
4. 重启 3021 并验证单 Worker 健康；
5. `command_center_workers` 表可以保留，无需破坏性降级数据库。

当前环境备份位于 `backups/command-center-worker-phase7-20260918/env.before-phase7`，该目录被
Git 忽略且不得提交。

## 剩余边界与下一阶段

双 Worker 目前位于同一台主机，共享同一 PostgreSQL 实例，因此能够抵御单 Worker 卡死，不能
抵御主机或数据库故障。下一阶段需要在维护窗口内定义 RTO/RPO 和通知负责人，然后执行真实
PostgreSQL 重启、连接中断、恢复重连与任务续跑演练。正式对外生产前仍需关闭 development
session，启用正式登录和角色授权。
