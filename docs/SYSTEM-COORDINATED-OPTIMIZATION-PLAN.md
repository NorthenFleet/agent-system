# 记忆闭环与 Agent Team 协同优化总纲

> 文档状态：联合阶段 1 已完成（Gate M1、T1 通过）  
> 基线日期：2026-09-20  
> 适用范围：Command Center、Agent Team、WorkRun、Memory、LangGraph、Agent Space  
> 核心原则：领域事实分治、引用契约统一、上下文最小授权、效果全链路可归因。

## 1. 系统中心

系统当前不是要继续堆叠新的数据库、智能体框架或可视化，而是把已经具备的可靠执行底座和记忆闭环组合成一个可证明的多智能体运行系统：

1. Command Center 管理业务意图、计划、审批、证据、验收与交付；
2. Agent Team 管理团队、角色、实例、共享任务、认领与协作事件；
3. WorkRun 管理每一次真实执行尝试、心跳、结果、副作用和补偿；
4. Memory 管理经过审核的长期权威记忆及其生命周期；
5. Context Pack 是记忆进入一次具体执行的不可变证据快照；
6. LangGraph 只组织宏观控制流，不成为第二套业务事实库；
7. Agent Space 只展示能够追溯到后端事实的数据。

记忆生产闭环与 Agent Team 是两条独立演进线。二者通过 Context Pack、执行引用和效果事件协作，不共享状态机，不互相复制事实。

### 1.1 第二大脑知识分方案（设计扩展，2026-10-06）

[第二大脑知识子系统 SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md) 在现有知识域补齐来源快照、概念积累、候选审核和引用问答；[SB0/SB1 基础实现](SECOND-BRAIN-PHASE-SB0-SB1.md)、[SB2 维护/投影](SECOND-BRAIN-PHASE-SB2.md)及 [SB3 引用检索/shadow 核心工程与隔离验证](SECOND-BRAIN-PHASE-SB3.md)已完成；生产试点及人工质量金标待验收，正式上下文注入关闭；[SB4 成果导入、export-only 记忆提案与运维恢复](SECOND-BRAIN-PHASE-SB4.md)工程验证完成，原生记忆桥接与 7 天真实任务观察待验收；[2026-10-07 试点工具与只读预检](SECOND-BRAIN-PILOT-PLAN.md)已完成，[实际配置与基础预检](SECOND-BRAIN-PILOT-CONFIGURATION.md)已通过，[空基线恢复与来源准备](SECOND-BRAIN-PILOT-READINESS.md)完成，[30 份授权文档入库与恢复](SECOND-BRAIN-PILOT-INTAKE.md)完成、候选待审核、观察未开始，不改变本总纲已记录的历史门禁状态。

- 新知识页面及修订由新增 PostgreSQL 知识域管理；Markdown、知识图和知识向量只作投影，不写入既有记忆投影表。
- 知识 `reviewed_knowledge` 与长期记忆 `approved_memory` 分开标识；知识只能提出 Memory Candidate，不直接发布 Profile/Project/Agent 记忆。
- Context Pack 增量记录 `knowledge_refs`、固定修订、来源片段和访问 epoch；不得把知识引用伪装为 `memory_source_ref`。
- 知识进入执行仍须满足本总纲适用的 Claim/WorkRun 绑定及作用域规则；执行前复核撤回和访问授权，旧快照不构成永久授权。
- 与 Memory、Artifact、Writing 的跨库动作通过幂等接口、Outbox 和对账协作，不将不同领域提交描述为一个数据库事务。
- SB3 知识上下文切流独立于 Memory RRF 与 Agent Team 真实认领，不在同一窗口首次启用。详细模型、接口与门禁以 SB-01 为准。

### 1.2 决策路由协同边界（DR-01，2026-10-06）

[DR-01 分方案](DECISION-ROUTING-ARCHITECTURE.md) 为现有 Mission/WorkRun 增加路由观察与后续旁路顾问，不改变本总纲的权威分区及历史门禁结论。

- 决策引用 mission_id、plan_version、step_id、attempt 和策略版本；沿现有事件账本关联 mission_run_id/correlation_id，执行仍引用原 WorkRun。
- DR1 使用现有 mission_events 元数据保存权威观察，步骤 result 中仅附带本次结果观察；不新增 Team 调度器、状态机或 JSON 主数据源。
- 同一步骤、同一计划版本的连续尝试才可累计失败；成功、中断观察或策略版本变化打断连续计数。观察只能在有效租约结果被接受后落账。
- Router 不生成 Context Pack，不修改记忆授权，不消费新的审批；顾问接入后仅持有按检查点裁剪的只读上下文。
- cluster_operation 保持独立受控执行路径，DR1 不接管也不记录其影子判断。关闭开关保留历史审计记录。

DR2 本地实现已完成，见 [实施记录](DECISION-ROUTING-PHASE-2.md)：确定性检查仍使用原 Mission/WorkRun，报告保存在现有结果与产物元数据中；受控恢复产生新计划，不重写旧验收。恢复上下文仅引用原失败事实，顾问及记忆权限不扩展。生产开关保持关闭。

DR3 增补（2026-10-08）：[检查点顾问与隔离代码候选](DECISION-ROUTING-PHASE-3.md) 复用 Mission 行锁和事件键领取顾问检查点，意见只读；工作树与模型回执继续绑定步骤/尝试/WorkRun，不新增执行权威。候选提交不代表源分支集成或验收完成；生产试点与独立集成门禁待执行。

## 2. 权威事实分区

| 领域 | 权威对象 | 唯一事实源 | 禁止行为 |
| --- | --- | --- | --- |
| 业务控制 | Mission、Plan、Step、Approval、Evidence、Acceptance、Delivery | Command Center | Agent Team 或 LangGraph 复制业务状态 |
| 团队协作 | AgentTeam、TeamRole、AgentInstance、SharedTask、TaskClaim、AgentMessage、TeamEvent | Agent Team 领域表 | 用消息文本代替受控状态迁移 |
| 真实执行 | WorkRun、attempt、heartbeat、result、effect、compensation | WorkRun/执行账本 | SharedTask 复制执行器日志和结果事实 |
| 长期记忆 | Profile、Project、Agent 已审核记忆及生命周期 | Memory 权威表 | 临时实例、原始聊天直接写入长期记忆 |
| 检索投影 | pgvector、Graph Memory | 可重建投影 | 反向覆盖权威记忆 |
| 宏观编排 | checkpoint、interrupt、next node | LangGraph Checkpoint | 保存任务正文、产物正文或成为事实数据库 |
| 展示 | 团队拓扑、进度、瓶颈、恢复轨迹 | 上述事实的只读投影 | 前端模拟真实执行进度 |

## 3. 跨域引用契约

一次团队任务的最小可追踪链必须保留：

```text
mission_id
  -> team_id
  -> role_id / agent_instance_id
  -> shared_task_id
  -> claim_id
  -> work_run_id
  -> context_pack_id
  -> memory_source_ref[]
  -> evidence_id[] / artifact_id[]
  -> acceptance_id / effect_event_id[]
```

### 3.1 写入规则

1. 每个领域只写自己的权威对象，跨域只保存稳定 ID 和版本；
2. 跨数据库操作不得假装成单一事务，使用 Outbox、幂等键和对账任务保证最终一致；
3. Context Pack 必须在 Claim 创建后、WorkRun 启动前生成或冻结；
4. WorkRun 只接受当前有效 Claim 的 fencing token；
5. 任务完成后，Acceptance 和 Effect Event 必须能够反查实际使用的 Context Pack 和记忆来源；
6. 所有引用必须包含 `owner_user_id`、`project_id` 或能通过 Mission 不歧义地解析这两个作用域；
7. 跨 Team 引用默认拒绝，任何共享必须通过显式、可审计的 Artifact 或 Context Binding。

### 3.2 版本规则

- Plan、SharedTask input/output contract、Context Pack 和调度策略必须保存版本；
- 重新规划生成新版本，不原地改写已执行版本；
- Claim、WorkRun、Context Pack 和验收记录共同构成一次执行的不可变证据链；
- LangGraph Checkpoint 只保存对象 ID、对象版本和下一控制节点。

## 4. 记忆与团队上下文边界

长期记忆模型保持不变：

```text
memory = lifecycle × scope(Profile/Project/Agent) × authority_state
```

Team、Role、AgentInstance、SharedTask 和 AgentMessage 是运行上下文，不增加新的长期记忆作用域。

### 4.1 Context Pack 绑定

1. AgentInstance 只有独立 `context_thread_id`，不持有可无限复用的长期 Context Pack；
2. Context Pack 按 SharedTask/TaskClaim/WorkRun 生成不可变快照；
3. 快照记录查询、允许作用域、选中 `source_ref`、检索策略、健康状态和生成时间；
4. 换人时只继承已确认的任务事实、Artifact、事件和重新授权的 Context Pack；
5. 旧 Claim 失效后，其 Context Pack 不得授权新的工具调用或结果回写；
6. 实例停止后，临时线程按保留策略退役，不能自动提升为长期记忆。

### 4.2 消息与产物

- AgentMessage 是结构化协作信号，不是记忆事实；
- `contract_changed`、`artifact_ready`、`help_requested`、`review_requested`、`blocked` 等消息必须绑定 Team 和任务；
- 原始消息只能生成 Memory Candidate，经过证据、敏感信息过滤和人工审核后才可发布；
- Team 不建立第二套 Artifact 正文库，统一引用 Command Center 的 `mission_artifacts`；
- Artifact 的版本、哈希、创建者和关联 Claim/WorkRun 必须可追溯。

## 5. 联合不变量

1. 一个 Mission 同时最多一个非终态 AgentTeam；
2. 一个 SharedTask 同时最多一个有效 Claim；
3. Claim 必须具有单调 fencing token，失效 Claim 的迟到结果必须被拒绝；
4. AgentInstance、Role、SharedTask、Message 和 Event 的 Team 必须一致；
5. 未通过依赖、风险、权限、工具和计划审批的任务不得进入 `ready`；
6. 动态换人不能扩大记忆、工具或项目权限；
7. 未审核候选、临时推理、原始对话不得进入长期记忆或正式检索投影；
8. 自动调度和自动恢复不能绕过 blocker、审批或补偿门禁；
9. 任何自动建议只产生候选或受控命令，不直接篡改权威事实；
10. 前端所有状态必须能够回溯到事件、Claim、WorkRun 或健康探测证据。

## 6. 联合门禁

### Gate C0：契约冻结

- 权威分区、跨域 ID、Context Pack 和 Artifact 规则完成评审；
- 两条主计划引用本总纲；
- 不改变线上排序和现有 Mission/WorkRun 主链。

状态：通过。验收记录：`SYSTEM-COORDINATED-PHASE-0.md`。

### Gate M1：记忆投影可信

- active 权威记忆与向量、图谱投影零差异；
- 非 active 记忆无可服务残留；
- Context Pack 包含可审计 source_ref 和作用域快照。

状态：通过。验收记录：`SYSTEM-COORDINATED-PHASE-1.md`。

### Gate T1：Agent Team 领域可信

- SQLite/PostgreSQL 同构；
- 原子有效 Claim、fencing token、依赖关系和跨 Team 约束成立；
- 重启恢复、非法引用、幂等和事件序列测试通过；
- 现有 Mission/WorkRun 行为不变。

状态：通过。验收记录：`SYSTEM-COORDINATED-PHASE-1.md`。

### Gate X1：跨域安全

- 跨用户、跨项目、跨 Agent、跨 Team、跨实例私有线程泄漏均为 0；
- 失效 Claim 不能继续使用上下文或回写结果；
- 原始成员消息不能自动进入长期记忆；
- 换人只继承允许的任务事实和重新授权上下文。

### Gate Q1：质量阻断

- 用户硬约束、安全、隐私、作用域泄漏、必需工件缺失均为 blocker；
- 总分不得覆盖 blocker；
- 修复生成新验收版本，不修改历史结论。

Gate M1、T1、X1、Q1 全部通过前，禁止进入真实共享任务认领。

## 7. 协同执行路线

| 联合阶段 | 记忆路线 | Agent Team 路线 | 进入条件 |
| --- | --- | --- | --- |
| 0 契约冻结 | 增加团队上下文边界 | 增加跨域权威与上下文契约 | 已完成 |
| 1 基础可信 | 阶段 B：权威与双投影对账（已完成） | 阶段 1：领域服务、约束、测试（已完成） | Gate C0 |
| 2 联合隔离 | 阶段 C：人工真值及团队安全负例 | 阶段 2 Shadow：共享池与认领建议 | Gate M1、T1 |
| 3 效果证据 | 阶段 D：离线评测与真实 Shadow | 阶段 3 Shadow：动态实例与评分 | Gate X1、Q1 |
| 4 受控启用 | 阶段 E：显式 RRF 切流 | 5% 低风险真实认领 | 两条路线各自独立批准 |
| 5 生命周期 | 阶段 F：效果归因、保留、退役 | 消息、恢复、替换、局部重规划 | 稳定观察通过 |
| 6 宏观编排 | 提供 Context/Effect 接口 | LangGraph 宏观生命周期 | 领域事实稳定 |
| 7 展示生产化 | 记忆证据与健康状态 | 真实团队拓扑与恢复轨迹 | 后端事实完整 |

记忆 RRF 切流和 Agent Team 真实认领是两个独立变更，不得互相作为默认前置条件，也不得在同一维护窗口同时首次启用。

## 8. 当前状态与下一步

### 已完成

- 记忆阶段 A：诊断一致性与基线冻结；
- Agent Team 总体分层设计；
- Agent Team SQLite/PostgreSQL 表结构草案；
- 本阶段跨域权威、Context Pack、Artifact 和联合门禁契约。
- 记忆阶段 B：权威记忆、生命周期、pgvector、Graph Memory 和队列零漂移对账；
- Agent Team 阶段 1：SQLite/PostgreSQL 契约、领域服务、受控 API 和并发门禁；
- Gate M1、Gate T1 验收。

### 尚未完成

- 联合隔离测试与 blocker 执行器；
- 任何真实共享任务认领或动态实例调度。

### 下一阶段

进入联合阶段 2（仅 Shadow）：

1. 执行记忆阶段 C，建立人工真值和跨域安全负例；
2. 生成不可执行的 SharedTask 投影和认领建议，不创建真实 WorkRun；
3. 完成 Gate X1、Gate Q1；
4. 两个 Gate 未通过时继续禁止真实共享任务认领。

DR4 增补（2026-10-08）：[工具调用控制与持久化回执](DECISION-ROUTING-PHASE-4.md) 复用步骤租约与 Mission 事件权威，先提交意图再执行有界文件操作；崩溃后未闭合意图不重放。仅隔离代码执行器开放四个专用工具，其他原生工具不在白名单。核心实现及本地测试完成，开关默认关闭；真实模型与生产验证待执行。
