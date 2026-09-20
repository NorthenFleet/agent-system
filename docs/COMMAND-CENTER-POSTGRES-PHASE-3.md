# Command Center PostgreSQL：第三阶段

## 已完成

1. 新增 PostgreSQL Repository，兼容现有 qmark SQL 和字典行访问；
2. 密码不会出现在健康接口的 `source_of_truth` 中；
3. PostgreSQL 禁止运行时建表，启动时缺表会提示先执行 Alembic；
4. 六类竞争领取统一增加 `FOR UPDATE SKIP LOCKED`；
5. 步骤领取只锁定本次配额，避免一个 Worker 锁住全部候选任务；
6. Alembic 创建 19 张 Command Center 事实表及唯一约束、领取索引；
7. SQLite→PostgreSQL 工具默认只读预检，应用时要求目标为空，并在同一事务中迁移；
8. 迁移提交前逐表验证行数和主键 SHA-256；
9. 本机 PostgreSQL 17 完成真实双 Worker 生命周期门禁。

## 实际迁移结果

- Alembic 版本：`20260918_command_center_pg`；
- Mission：11/11；
- Step：30/30；
- Mission Event：137/137；
- Command Message：55/55；
- Context Binding：24/24；
- Notification Outbox/Delivery：20/20；
- 全部 19 张表验证通过。

详细证据：

- `COMMAND-CENTER-POSTGRES-MIGRATION-PREFLIGHT.json`
- `COMMAND-CENTER-POSTGRES-MIGRATION-RESULT.json`

## 当前边界

本节是第三阶段完成时的历史边界。Work Run 与 LangGraph checkpoint 的 PostgreSQL
改造、迁移和真实门禁已在第四阶段完成，以
`COMMAND-CENTER-POSTGRES-PHASE-4.md` 为当前状态。

## 下一阶段

1. 将 Work Run Repository 化并迁移到 PostgreSQL；
2. 将 LangGraph checkpoint 切换到 PostgreSQL Saver；
3. 增加连接池、锁等待、租约过期和重复领取指标；
4. 执行进程终止、数据库重启和主库切换演练；
5. 灰度设置 `COMMAND_CENTER_DATABASE_URL`，进入双读对账后正式切换。
