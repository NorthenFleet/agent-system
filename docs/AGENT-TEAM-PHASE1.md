# Agent Team 第一阶段：领域模型与持久化契约

日期：2026-09-20

状态：已完成

## 1. 本阶段范围

本阶段只建立 Agent Team 的持久化事实与领域服务，不接管现有 Mission、Step、WorkRun 和 Worker 主链。功能开关默认关闭，新表可以在不改变现有任务行为的前提下随版本部署。

已完成：

- `AgentTeam`：Mission 下的团队、Leader、容量和生命周期。
- `TeamRole`：能力与工具需求、实例上下限。
- `AgentInstance`：基础智能体、上下文线程、容量、心跳和熔断预留字段。
- `SharedTask`：任务能力、工具、依赖、风险、输入输出、验收和证据契约。
- `TaskClaim`：为第二阶段原子认领预留 attempt、评分、租约、令牌和 WorkRun 绑定。
- `AgentMessage`：跨成员结构化通信和确认信息。
- `TeamEvent`：团队内严格递增、仅追加的审计事件流。

## 2. 关键约束

- 一个 Mission 同时只能有一个非终态团队。
- Role 必须至少声明一种能力。
- 实例必须属于本团队的 Role，并受 Role 和 Team 容量限制。
- SharedTask 的依赖必须已经存在于同一个团队。
- SharedTask、消息和团队创建都具备稳定幂等键。
- AgentMessage 发送方、目标实例、目标角色和任务必须属于同一团队。
- 终态团队不能再增加 Role、Instance、Task 或 Message。
- 团队状态只允许按规定生命周期前进，不能从终态恢复。
- 每个领域写操作同步生成 TeamEvent。

## 3. 持久化兼容

- SQLite：Command Center 开发模式自动创建七张 Agent Team 表和必要索引。
- PostgreSQL：通过 Alembic `20260922_agent_team` 迁移，运行时不建表。
- 本机 `team_dashboard` 已从 `20260921_worker_registry` 升级到 `20260922_agent_team`，七张表均已核验存在。

## 4. 功能开关

默认值：

```dotenv
AGENT_TEAM_ENABLED=false
AGENT_TEAM_SHADOW=true
AGENT_TEAM_DYNAMIC_ASSIGNMENT=false
AGENT_TEAM_PEER_MESSAGING=false
AGENT_TEAM_LANGGRAPH=false
```

第一阶段没有读取这些开关改变生产行为；它们作为后续接入点，确保第二阶段可以先以 Shadow 方式投影任务而不触发真实认领。

## 5. 验证结果

- Agent Team与Repository定向测试：11项通过。
- Command Center、Router和Workflow Runtime回归：65项通过、1项按条件跳过。
- 完整后端回归：812项通过、84项按环境跳过、2项预期失败。
- Alembic迁移链：单一Head为`20260922_agent_team`。
- PostgreSQL迁移：成功。
- 编译和差异空白检查：通过。

覆盖场景：

- 重复创建的幂等返回。
- 进程重启后团队快照恢复。
- 角色能力与工具去重。
- Role实例容量和Team总容量约束。
- 未知任务依赖拒绝。
- 跨团队Role、Instance和Message引用拒绝。
- 团队状态合法转换与终态保护。
- TeamEvent序列连续且顺序可重放。

## 6. 尚未启用的能力

以下内容明确属于后续阶段：

- Plan Step自动投影到SharedTask。
- SharedTask从`draft`释放为`ready`。
- 多Worker竞争认领和租约续期。
- 动态候选评分与实例扩缩容。
- 成员消息消费和上下文注入。
- 自动重派、熔断、局部重规划。
- API与前端团队拓扑。
- LangGraph宏观控制图。

## 7. 下一阶段入口

第二阶段首先实现只读Shadow投影：将已批准计划转换为SharedTask并验证依赖、能力和工具契约；确认投影稳定后，再启用PostgreSQL原子认领和WorkRun绑定。旧Worker路径必须始终可以通过功能开关回退。
