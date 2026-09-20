# Command Center PostgreSQL：第四阶段

## 阶段目标

消除多实例生产部署剩余的两个本地状态限制：WorkRun 执行账本和 LangGraph
checkpoint。业务事实仍由 Command Center 管理；WorkRun 记录实际执行尝试，LangGraph
仅保存可恢复的流程检查点，三者不互相替代。

## 已完成

### WorkRun 共享执行账本

1. `WorkRunService` 改为 Repository 驱动，同时保留 SQLite 开发回退；
2. PostgreSQL 启动时只验证 schema，不允许应用进程运行时建表；
3. 新建 Alembic revision `20260919_work_run_pg`，管理 `work_runs`、
   `work_run_events`、`work_artifacts` 及索引；
4. 首次 attempt 创建使用事务级 advisory lock，以幂等键串行化并发创建；
5. SQLite→PostgreSQL 迁移默认 dry-run，apply 要求目标表为空，并在单事务中按
   行数和主键 SHA-256 校验；
6. 本机数据已迁移：24 个 WorkRun、97 条事件、6 个产物，迁移后全部校验一致；
7. 真实双连接并发测试证明同一幂等键只生成一个 attempt，另一领取方收到租约冲突。

### LangGraph PostgreSQL checkpoint

1. 引入 `langgraph-checkpoint-postgres` 3.1.x；
2. 新建 Alembic revision `20260920_langgraph_pg`，管理官方 Saver 所需的
   `checkpoints`、`checkpoint_blobs`、`checkpoint_writes`、
   `checkpoint_migrations`；
3. Worker 不调用 PostgreSQL Saver 的 `setup()`，因此无运行时 DDL；
4. Worker 启动/执行前核对官方 checkpoint migration 版本，缺表或版本落后时故障关闭；
5. PostgreSQL Command Center 默认复用其数据库作为 WorkRun 与 checkpoint 后端，也可用
   独立 URL 覆盖；
6. 真实 PostgreSQL 测试通过审批中断、进程级 Runtime 重建、恢复执行和重复 resume 幂等；
7. Command Center→Workflow Run→LangGraph interrupt→approval resume→Mission 激活的整体链路通过。

## 配置

生产配置：

```dotenv
COMMAND_CENTER_DATABASE_URL=postgresql+psycopg2:///team_dashboard
WORK_RUN_DATABASE_URL=postgresql+psycopg2:///team_dashboard
COMMAND_CENTER_LANGGRAPH_CHECKPOINT_URL=postgresql:///team_dashboard
```

SQLite 路径变量只用于本地开发回退。配置 PostgreSQL 时，必须先执行：

```bash
DATABASE_URL="$COMMAND_CENTER_DATABASE_URL" backend/venv/bin/alembic \
  -c backend/alembic.ini upgrade head
```

## 验证证据

- WorkRun 迁移预检：`WORK-RUN-POSTGRES-MIGRATION-PREFLIGHT.json`；
- WorkRun 迁移结果：`WORK-RUN-POSTGRES-MIGRATION-RESULT.json`；
- 迁移后对账：`WORK-RUN-POSTGRES-POST-MIGRATION-RECONCILIATION.json`；
- PostgreSQL WorkRun 并发门禁：1 passed；
- PostgreSQL Command Center + LangGraph 整体门禁：2 passed；
- LangGraph PostgreSQL checkpoint 门禁：2 passed；
- 后端全量回归：778 passed、84 skipped、2 xfailed。

## 当前边界

两个共享状态限制已经完成代码、迁移和真实 PostgreSQL 验证，但当前 3021 生产进程尚未切换
到这组 PostgreSQL 环境变量。本阶段没有修改正在运行服务，避免未经灰度直接改变事实源。

多实例/高可用仍需完成下一阶段：连接池与容量边界、租约/锁等待指标、数据库重启和连接中断
演练、灰度切流与回退验证。完成这些门禁前，不能宣称系统已经具备完整跨节点高可用能力。

## 下一阶段

1. 引入有界连接池并定义连接耗尽、查询超时和锁等待阈值；
2. 增加 WorkRun 冲突率、租约过期率、checkpoint 失败率和执行恢复率指标；
3. 演练 Worker 进程终止、PostgreSQL 重启、短暂网络中断及恢复；
4. 对 3021 服务执行 5% 灰度切流、双端行数/状态对账和可回退验证；
5. 观察窗口通过后，再停用 SQLite 写入路径。
