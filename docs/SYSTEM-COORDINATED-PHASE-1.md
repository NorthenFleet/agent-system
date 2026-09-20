# 记忆闭环与 Agent Team 协同优化：联合阶段 1 验收记录

> 完成日期：2026-09-20  
> 阶段结论：Gate M1、Gate T1 通过；允许进入联合阶段 2 的 Shadow/隔离验证  
> 生产边界：`AGENT_TEAM_ENABLED` 保持默认关闭，未创建或认领任何真实共享任务，未改变线上检索排序

## 1. 阶段目标

联合阶段 1 同时完成两个相互独立、但共享跨域契约的基础工作包：

1. Memory M1：证明已审核权威记忆、生命周期账本、pgvector 和 Graph Memory 投影一致；
2. Agent Team T1：建立不接管现有 Mission/WorkRun 主链的领域持久化契约、服务入口和并发约束。

## 2. Memory Gate M1

### 2.1 实现

1. Graph Memory Bridge 新增只返回元数据的 `/graph-memory/v1/projection-inventory`，使用独立读取权限；
2. 图投影增加 `content_hash`，并兼容升级已有 SQLite Bridge 数据库；
3. 新增 `MemoryProjectionReconciliationService` 和 `memory_projection_reconcile.py`，统一对账权威记录、生命周期、pgvector、Graph Memory 与两个异步队列；
4. Graph 发布、生命周期事件和历史回填统一携带规范内容哈希；
5. Profile/Project/Agent 作用域统一由 `MemoryVectorDocument` 规范化，避免“提议智能体”被误当作记忆归属智能体；
6. Profile 记忆统一使用规范 `memory_key` 作为投影标题，并清除不属于 Profile 作用域的 `project_id/agent_id`；
7. 历史回填事件采用 `approved-projection.v2` 版本指纹，使投影契约升级能够绕过旧事件的幂等短路，同时保持同一 v2 载荷幂等；
8. Bridge v2 已部署并由受管 OpenClaw Gateway 加载，历史 17 条已审核记忆完成幂等回填。

### 2.2 真实数据对账

最终只读对账结果：

| 检查项 | 结果 |
| --- | ---: |
| 总体状态 | `ready / consistent=true` |
| pgvector 权威/投影 | 17 / 17 |
| pgvector 缺失、孤儿、陈旧、错误模型 | 0 / 0 / 0 / 0 |
| 用户 1 Graph 权威/活动投影 | 15 / 15 |
| Graph 缺失、孤儿、陈旧、作用域漂移 | 0 / 0 / 0 / 0 |
| 生命周期检查 | 23 条，0 违规 |
| Graph 队列 | pending/retry/processing/dead-letter 均为 0 |
| Vector 队列 | pending/processing/dead-letter 均为 0 |

`pgvector=17` 与用户 1 的 `Graph=15` 不矛盾：前者执行更强的全局对账，后者按 `user_id=1` 做所有权过滤。

### 2.3 修复过程中的关键发现

1. 老 Gateway 一度占用端口并关闭准入；受管服务随后完成正常接管，没有执行强制杀进程；
2. 第一轮回填发现旧 `event_id` 会把投影协议升级误判为重复事件，已通过版本化事件指纹修复；
3. 第二轮对账发现 Profile 候选形态与发布后的权威形态不一致，已改为由同一个规范文档同时驱动向量和图投影。

## 3. Agent Team Gate T1

### 3.1 数据与迁移

1. SQLite/PostgreSQL 均具备 AgentTeam、TeamRole、AgentInstance、SharedTask、TaskClaim、AgentMessage、TeamEvent；
2. 增加权威依赖表 `shared_task_dependencies`，`dependencies_json` 仅保留兼容快照；
3. 增加 `agent_task_context_bindings`，Context Pack 绑定 Team、SharedTask、当前 Claim、可选 WorkRun、作用域和 source refs；
4. `task_claims` 增加 `team_id`、单调 `fencing_token` 与单一活动 Claim 部分唯一索引；
5. PostgreSQL 增加复合唯一键与跨 Team 外键，AgentMessage 强制实例/角色接收者二选一；
6. 新增迁移 `20260923_agent_team_contract_hardening`，真实数据库已处于该版本；历史迁移未被改写；
7. PostgreSQL 测试临时数据已清理，当前 `agent_teams=0`、`task_claims=0`。

### 3.2 领域服务与 API

1. 新增 AgentTeam 领域服务：建队、定义角色、注册实例、创建任务、记录 Claim、绑定 Context Pack、发送结构化消息和读取完整快照；
2. 所有入口执行 owner 作用域、同 Team 引用与显式幂等校验；
3. TeamEvent 使用 Team 内单调序列；`active_claims` 从活动 Claim 事务内重算，不作为唯一事实；
4. Claim 关闭入口必须同时匹配当前 Claim ID 与 fencing token；旧 token 在新 Claim 产生后无法改变状态；
5. Claim 关闭时撤销其活动 Context Binding，避免失效 Claim 继续授权；
6. `/api/v3/agent-teams` 路由已注册；写入口受 `AGENT_TEAM_ENABLED=true` 控制，默认关闭；
7. 3021 后端已受管重启并恢复健康，OpenAPI 已显示 6 条 Agent Team 路径；环境未设置 `AGENT_TEAM_ENABLED`，因此写入口仍关闭；
8. 本阶段只建立持久化契约，不派发 WorkRun，不接管既有执行主链。

### 3.3 验证证据

| 验证 | 结果 |
| --- | --- |
| Agent Team SQLite/API 专项 | 6 passed |
| Agent Team PostgreSQL 并发门禁 | 1 passed |
| 并发双 Claim | 仅 1 个成功 |
| fencing token | 1 → 2 单调；旧 token 写入被拒绝 |
| 阶段 1 Python 联合回归（含 Agent Team） | 56 passed |
| Graph Bridge Vitest | 7 passed |
| Python 编译检查 | 通过 |
| `git diff --check` | 通过 |

测试仅出现现有 SQLAlchemy、Pydantic 和 FastAPI 弃用告警，没有失败。

## 4. Gate 结论

### Gate M1：通过

- active 权威记忆与双投影零差异；
- 生命周期无违规，异步队列无积压和死信；
- 投影库存只暴露对账元数据，不返回记忆正文；
- Context Pack 继续保存可审计 source refs 和作用域快照。

### Gate T1：通过

- SQLite/PostgreSQL 关键字段和约束同构；
- 单一活动 Claim、单调 fencing token、跨 Team 引用、接收者二选一和 Context Binding 成立；
- 幂等、重启可恢复数据、团队快照、并发竞争和迟到 token 拒绝均有测试；
- 现有 Mission/WorkRun 主链保持不变。

## 5. 尚未授权的能力

联合阶段 1 完成不等于 Agent Team 已可生产认领。以下仍被明确禁止：

1. 自动把已批准 Plan Step 投影为真实 SharedTask；
2. 真实 WorkRun 创建、任务自主认领或动态实例扩缩；
3. 失效 Claim 的真实执行结果回写；
4. 成员消息自动发布为长期记忆；
5. 将记忆融合从 Shadow 切换到线上 served 排序。

## 6. 下一阶段

进入联合阶段 2，但只运行 Shadow 和安全隔离验证：

1. Memory C：建立人工真值集及跨用户/项目/Agent/Team/Instance 安全负例；
2. Agent Team 阶段 2 Shadow：把计划步骤投影为不可执行的 SharedTask 候选，计算依赖就绪与认领建议；
3. X1：验证跨域泄漏为 0、失效 Claim 不能继续使用 Context Pack、换人不继承私有线程；
4. Q1：把用户硬约束、安全、隐私和必需工件缺失固化为不可被总分覆盖的 blocker；
5. Gate X1、Q1 通过前，继续保持真实共享任务认领关闭。
