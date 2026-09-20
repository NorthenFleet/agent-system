# Command Center 生产可靠性：第五阶段

## 阶段目标

在 PostgreSQL 事实库、WorkRun 和 LangGraph checkpoint 已共享持久化的基础上，补齐有界连接、
容量门禁和可观测性。第五阶段不修改当前 3021 服务的事实源，不进行不可控的生产数据库重启。

## 已完成

### 有界连接池

`PostgresCommandCenterRepository` 已使用线程安全连接池，并提供以下配置：

```dotenv
COMMAND_CENTER_DB_POOL_MIN=1
COMMAND_CENTER_DB_POOL_MAX=10
COMMAND_CENTER_DB_POOL_ACQUIRE_TIMEOUT=5
```

连接总预算按“进程数 × 每进程池上限”计算。当前 PostgreSQL `max_connections=100`，观测时
总连接为 7、`team_dashboard` 连接为 2；若部署 2 个 Worker 且每进程上限为 10，Command
Center 连接预算为 20，仍需为 LangGraph、迁移、管理和其他服务保留余量。

连接池具有以下行为：

1. 达到上限后等待固定超时，不无限阻塞；
2. 超时抛出明确的 `CommandCenterPoolExhausted`，不会绕过池创建额外连接；
3. 事务成功归还连接，异常先回滚，失效连接关闭而不重新入池；
4. 进程关闭时释放 Command Center 与 WorkRun 的所有连接池；
5. 密码和 DSN 不进入运行指标。

### 运行指标与前端呈现

新增管理员接口：`GET /api/v3/command-center/production-health`。

接口聚合：

- 连接池当前使用量、峰值、等待时间、获取超时和连接失败；
- WorkRun 总数、活跃数、过期租约、重试、失败和租约重领；
- LangGraph checkpoint 表完整性、已安装/要求版本和运行时 DDL 状态；
- 事实库后端与多实例能力。

最近五分钟出现连接获取超时或连接失败时，连接池状态为 `degraded`；历史累计计数仍保留，
但不会造成永久降级。指挥中心前端已增加“生产运行门禁”栏，管理员可直接看到上述关键状态。

### 容量与故障关闭门禁

脚本：`backend/scripts/command_center_postgres_capacity_gate.py`。

本机真实 PostgreSQL 结果：

| 检查 | 结果 |
| --- | --- |
| 24 个并发查询全部完成 | 通过 |
| 连接池上限 4、峰值 4 | 通过 |
| 正常负载获取超时 | 0 |
| 正常负载连接失败 | 0 |
| 平均连接等待 | 51.906 ms |
| 最大连接等待 | 173.901 ms |
| 池耗尽时 50 ms 内故障关闭 | 通过 |
| 释放占用后连接池恢复 | 通过 |
| 数据库不可达模拟快速失败 | 171.18 ms，OperationalError |
| checkpoint schema/version | 4/4 表存在，9/9 |

完整机器可读证据：`COMMAND-CENTER-POSTGRES-CAPACITY-GATE.json`。

## 回归结果

- 后端全量：780 passed、84 skipped、2 xfailed；
- PostgreSQL Command Center、WorkRun、LangGraph 门禁：5 passed；
- 前端全量：24 个文件，107 passed、3 expected fail；
- 前端 `vue-tsc -b` 与生产构建：通过；
- `git diff --check`：通过。

## 尚未执行的破坏性演练

真实 PostgreSQL 服务重启、主库切换和网络分区会影响当前数据库的其他使用者，本阶段只执行了
隔离的不可达端口模拟，没有擅自中断本机 PostgreSQL。正式演练需要维护窗口、数据库快照、
明确的 RTO/RPO 和回退负责人。

## 下一阶段：灰度切流

1. 固化 3021 当前环境和 SQLite 快照；
2. 将三个 PostgreSQL URL 与连接池配置写入 3021 的受控环境；
3. 重启单个 3021 实例，执行健康、读取、创建/审批/执行测试；
4. 在观察窗口内持续对账 SQLite 与 PostgreSQL 的核心状态；
5. 验证一键回退到旧配置；
6. 通过后再增加第二 Worker，并安排数据库重启/主库切换维护窗口。

当前判定：第五阶段技术门禁通过；正式灰度切流尚未执行。
