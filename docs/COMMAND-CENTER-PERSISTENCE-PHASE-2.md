# Command Center 持久化架构：第二阶段

## 阶段目标

将业务状态机与具体数据库连接解耦，建立可测试、可观测、可替换的持久化边界，同时不改变
现有 Mission、Step、Approval、Effect、Compensation API 和生命周期语义。

## 已实现结构

```text
Router / Worker
       |
CommandCenterService（业务状态机与事务用例）
       |
CommandCenterRepository（事务、表结构探测、能力声明）
       |
SQLiteCommandCenterRepository（当前单节点生产试点实现）
```

Repository 对外提供：

- 原子事务及回滚；
- 立即写事务，用于单节点竞争领取；
- 表和字段探测；
- `durable`、`transactional_claims`、`multi_instance`、
  `runtime_schema_management` 能力声明；
- 明确的事实库位置。

## 安全策略

1. 保留 `CommandCenterService(db_path)`，已有调用方无需迁移；
2. 新代码可注入 Repository，便于隔离测试和后续切换；
3. `COMMAND_CENTER_DATABASE_URL` 配置不受支持的数据库时故障关闭；
4. 健康接口公开实际后端能力，禁止以“服务可用”替代“多实例安全”；
5. SQLite 明确标记为 `multi_instance=false`。

## 下一阶段准入门槛

PostgreSQL Repository 只有同时满足以下条件才能启用：

1. Command Center 全部事实表进入 Alembic 迁移；
2. 任务领取使用行锁和 `SKIP LOCKED`，租约更新带条件版本检查；
3. 幂等键、事件序列和 Effect Journal 唯一约束保持一致；
4. 完成双 worker 竞争、连接中断、主库切换和重复消息测试；
5. SQLite 到 PostgreSQL 的校验迁移可以对账并可回滚。

