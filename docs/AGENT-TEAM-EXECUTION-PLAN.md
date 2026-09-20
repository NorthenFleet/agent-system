# 擎天柱 Agent Team 分阶段实施方案

> 文档状态：执行中（联合阶段 1 已完成，下一阶段为阶段 2 Shadow）  
> 协同契约：`SYSTEM-COORDINATED-OPTIMIZATION-PLAN.md`  
> 当前边界：已有表结构草案，不代表领域服务、约束、API 和测试已经验收。

## 1. 背景与结论

华为云码道 CodeArts Agent Team 公开描述了“Team Leader 智能编排 + Teammate 自主执行”的协作方式，核心能力包括共享任务池、自主认领、动态组队、成员双向通信、持续上下文、故障成员替换和执行拓扑可视化。公开 GitHub 检索未发现华为官方开放 Agent Team 调度内核，因此本方案只参考可验证的产品语义，不复制未经证实的内部实现。

擎天柱系统已经具备 Mission、Plan、Step、WorkRun、审批、证据、租约、心跳、幂等续跑和补偿能力。本轮不重建执行底座，而是在现有可靠性基础上，将“固定智能体中央派发”升级为“动态团队 + 共享任务池 + 可审计协作”。

## 2. 目标架构

```text
用户/业务入口
    |
    v
Optimus / Team Leader
    |-- 识别业务场景与约束
    |-- 生成、校验和审批任务计划
    |-- 组建 Agent Team
    v
共享任务池 SharedTask
    |-- 能力、工具、权限、风险硬约束
    |-- 优先级、依赖、资源和并发约束
    v
Role -> AgentInstance x N
    |-- 动态候选过滤和评分
    |-- 原子认领、租约、Fencing Token
    |-- 成员消息、产物和上下文引用
    v
WorkRun / Worker
    |-- 真实执行、心跳、超时、重试
    |-- 证据、验收、副作用和补偿
    v
Mission / Command Center 事实库
```

职责边界：

- 大模型负责理解目标、提出任务分解、分析依赖和建议角色。
- 确定性规则负责计划编译、风险、权限、能力、工具、DAG、幂等和验收门禁。
- Agent Team 负责团队、角色、实例、共享任务、认领、通信和协作事件。
- WorkRun 负责单次真实执行事实；Agent Team 不复制执行器状态。
- Command Center 继续是 Mission、Plan、Approval、Evidence 和 Delivery 的业务事实源。
- LangGraph 只负责组队、规划、审批、监控、恢复、验收等宏观控制流，其 Checkpoint 只保存业务对象引用。
- Memory 只提供经过作用域过滤的 Context Pack 和长期记忆候选治理，不保存 Agent Team 调度状态。
- Agent Team 不建立第二套 Artifact 正文库，统一引用 Command Center 的 `mission_artifacts`。

## 3. 核心领域模型

### 3.1 AgentTeam

一次 Mission 对应至多一个活动团队，记录 Leader、团队策略、容量预算和生命周期。

状态：`forming -> active -> draining -> completed|failed|cancelled`。

### 3.2 TeamRole

Role 是能力需求，不等于固定智能体。记录能力标签、必需工具、最小/最大实例数和运行策略。同一 Role 可以生成多个 AgentInstance。

### 3.3 AgentInstance

AgentInstance 是本次团队中的可调度运行成员，关联基础智能体和 Role，具有独立实例标识、容量、心跳、上下文线程和熔断状态。AgentInstance 不持有可无限复用的长期 Context Pack；Context Pack 按 TaskClaim/WorkRun 冻结。

状态：`starting -> idle <-> busy -> draining -> stopped|failed`。

### 3.4 SharedTask

SharedTask 是团队任务池中的可认领工作单元。它声明能力与工具要求、依赖、优先级、风险、最大认领次数、输入输出契约和验收证据，但不预先绑定固定智能体。

状态：`draft -> ready -> claimed -> running -> verifying -> completed|failed|blocked|cancelled`。

### 3.5 TaskClaim

TaskClaim 是一次调度决策和租约记录，保存候选评分、选择理由、attempt、租约令牌、超时、WorkRun 引用和结束原因。一个 SharedTask 可以有多次历史 Claim，但同时只能有一个有效 Claim。

### 3.6 AgentMessage 与 TeamEvent

AgentMessage 是绑定 Team、Task 和 Artifact 引用的结构化成员通信；TeamEvent 是仅追加的协作审计流。自由文本不能代替状态更新，任务状态只能通过受控命令改变。

## 4. 不变量

1. Mission、Step、WorkRun 仍是现有执行事实，Agent Team 只增加协作语义。
2. 一个 Mission 同时最多有一个非终态 AgentTeam。
3. Team Leader 默认是 Optimus，但必须以字段保存，不能写死到调度逻辑。
4. Role 只声明能力，AgentInstance 才代表本次团队中的实际成员。
5. SharedTask 未满足依赖、风险审批、工具和权限要求时不能进入 `ready`。
6. Claim 必须原子创建，必须包含租约和 Fencing Token。
7. 只有当前有效 Claim 可以创建或绑定 WorkRun。
8. 失效 Claim 的迟到结果不能回写 SharedTask。
9. 成员消息必须限定 Team 范围，并绑定发送方、接收方或接收角色。
10. 动态扩缩容、重派、重试、熔断和人工干预必须写入 TeamEvent。
11. LangGraph Checkpoint 不保存完整任务、日志和产物正文，只保存 ID、版本和下一控制节点。
12. Team、Role、Instance、Task、Claim、Message 和 Event 的跨表引用必须属于同一 Team。
13. Context Pack 必须绑定 SharedTask、当前有效 Claim 和 WorkRun；换人时重新授权，不复制旧实例私有线程。
14. AgentMessage 只能生成记忆候选，不能直接写入 Profile、Project 或 Agent 长期记忆。
15. Team 产物必须引用 `mission_artifacts` 的稳定 ID、版本和哈希，不复制正文事实。

## 5. 分阶段执行

### 阶段0：跨域权威与上下文契约（已完成）

目标：在实现共享任务池前，冻结 Command Center、Agent Team、WorkRun、Memory 和 LangGraph 的事实边界。

完成项：

1. 明确 `mission_id -> team_id -> shared_task_id -> claim_id -> work_run_id -> context_pack_id -> memory_source_ref` 追踪链；
2. 明确长期记忆仍只有 Profile、Project、Agent 三种作用域；
3. 明确 Context Pack 按 Claim/WorkRun 生成不可变快照；
4. 明确 Artifact 复用 Command Center 权威对象；
5. 建立 Gate M1、T1、X1、Q1，全部通过前禁止真实共享任务认领。

验收记录：`SYSTEM-COORDINATED-PHASE-0.md`。

### 阶段1：领域模型与持久化契约（已完成）

目标：建立不影响现有执行主链的 Agent Team 数据基础。

步骤：

1. 新增 AgentTeam、TeamRole、AgentInstance、SharedTask、TaskClaim、AgentMessage、TeamEvent 表。
   - 增加 SharedTaskDependency 关系表；`dependencies_json` 只可作为兼容快照，不作为依赖权威；
   - TaskClaim 增加单调 `fencing_token`，并用部分唯一约束保证一个任务同时最多一个有效 Claim；
   - AgentMessage 强制接收实例或接收角色二选一；
   - 跨表引用必须校验 Team 一致性。
2. 同时支持本地 SQLite 自动建表和生产 PostgreSQL Alembic 迁移。
3. 建立状态常量、输入校验和生命周期规则。
4. 提供创建团队、定义角色、注册实例、投放任务、发送消息和读取团队快照的领域服务。
5. 所有创建操作具备业务唯一性或显式幂等键。
6. 增加单元测试，证明重启可恢复、跨团队隔离、非法状态和非法引用被拒绝。
7. 明确 `active_claims` 等派生计数的事务更新和对账策略，禁止把可能漂移的缓存当作唯一调度事实。
8. AgentInstance 只保存上下文线程；Context Pack 使用记录绑定 SharedTask、TaskClaim 和 WorkRun。

验收条件：

- 现有 Mission/WorkRun 行为不变。
- PostgreSQL 必须先迁移后启动，禁止运行时建表。
- SQLite 与 PostgreSQL 具有同构字段和索引。
- 团队快照可以完整返回角色、实例、任务、Claim、消息和事件。
- 同一 SharedTask 不可能并存两个有效 Claim，迟到 fencing token 无法回写。
- 跨 Team 引用、非法消息路由和依赖环被拒绝。

回滚：关闭 Agent Team 功能开关；新增表尚未承载真实任务时可执行迁移 downgrade。

验收记录：`SYSTEM-COORDINATED-PHASE-1.md`。当前生产库未承载真实 Agent Team 数据，写功能开关保持默认关闭。

### 阶段2：共享任务池与原子认领

目标：从固定 `agent_id` 派发升级为能力驱动的任务认领。

步骤：

1. 将已批准 Plan 的 Step 投影为 SharedTask，保留 Step ID 和计划版本引用。
2. 建立依赖就绪计算、优先级排序、风险和资源门禁。
3. 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 实现竞争认领。
4. Claim 写入候选、评分、理由、租约、令牌和 idempotency key。
5. Claim 成功后才创建 WorkRun；WorkRun ID 回绑 Claim。
6. 租约过期后安全释放，旧令牌结果拒绝回写。

验收条件：并发认领无重复；依赖未完成不能认领；租约过期可接管；副作用任务不会重复执行。

### 阶段3：动态团队与调度评分

目标：根据任务需求和实时状态动态生成、扩缩 AgentInstance。

步骤：

1. Planner 输出 `required_capabilities`，不直接指定最终 AgentInstance。
2. 建立硬过滤：能力、工具、权限、在线、熔断、容量、风险授权。
3. 建立可版本化评分：能力30%、可用性20%、工具15%、负载15%、成功率10%、时限5%、上下文连续性5%。
4. 保存候选集合、各项得分和最终选择理由。
5. 根据 ready 队列、关键路径和预算扩缩同 Role 实例。
6. 设置单实例、单 Role、单 Team 和全局并发上限。

验收条件：离线或超载实例不获新任务；分配可解释；扩缩容受预算约束；策略版本可回放。

### 阶段4：成员通信与持续上下文

目标：支持可审计的成员双向协作，而不是无边界自由聊天。

步骤：

1. 实现实例到实例、实例到 Role、实例到 Leader 的消息路由。
2. 支持 `contract_changed`、`artifact_ready`、`help_requested`、`review_requested`、`blocked` 等消息类型。
3. 消息绑定任务、产物、计划版本和确认状态。
4. 每个 AgentInstance 建立独立上下文线程；Profile/Project/Agent 三层记忆必须经作用域过滤后冻结为当前 TaskClaim/WorkRun 的 Context Pack，实例不得绕过该快照直接扩大检索范围。
5. 将确认后的协作结论沉淀为任务事件或候选记忆，原始聊天不直接进入长期记忆。
6. 增加消息风暴、循环请求、跨团队读取和敏感内容限制。

验收条件：跨团队隔离；消息可追踪；上下文可恢复；未经确认的模型推断不进入长期记忆。

### 阶段5：自动恢复、替换与局部重规划

目标：Leader 能识别失败类型并选择重试、换人、重规划、补偿或人工升级。

步骤：

1. 分类 transient、rate_limited、tool_unavailable、agent_unavailable、invalid_input、acceptance_failed、side_effect_partial、policy_blocked、permanent。
2. 临时故障指数退避；实例故障重新分配；工具故障切换工具或等待。
3. 连续失败触发 AgentInstance 熔断。
4. 局部重规划只替换失败步骤及未开始的受影响下游任务。
5. 已完成且验收通过的结果保持不可变。
6. 有副作用的失败先判断补偿和人工审批，不自动盲目重试。

验收条件：永久失败不无限重试；故障实例可替换；局部重规划不破坏已完成成果；补偿全程可审计。

### 阶段6：实时监控与 Agent Space

目标：让前端显示真实团队运行状态，而不是用固定百分比模拟执行进度。

步骤：

1. 使用 Transactional Outbox 发布 TeamEvent。
2. 通过 WebSocket/SSE 推送，轮询只作为断线兜底。
3. 展示 Team -> Role -> Instance -> Task/Claim/WorkRun 拓扑。
4. 展示候选评分、分配理由、attempt、租约、心跳、排队和运行耗时。
5. 区分模型估计进度、调度状态和执行器真实上报进度。
6. 增加关键路径、瓶颈、预计完成时间、重派和恢复轨迹。

验收条件：界面状态可以追溯到后端事实；断线重连不丢事件；过期实例和Claim可明确识别。

### 阶段7：LangGraph宏观编排

目标：在数据契约稳定后，用 LangGraph 组织可恢复的团队控制流。

建议图：

```text
intake -> context -> plan -> compile -> validate
                         ^               |
                         |---- repair ---|
                              |
                         approval interrupt
                              |
                         form_team -> dispatch
                              |
                         monitor/recover
                              |
                         evidence -> delivery
```

实施约束：

- 先以 document/research、L0/L1 Shadow 模式运行。
- Command Center 和 WorkRun 继续是事实源。
- 图节点只能通过领域服务改变业务状态。
- 每个有副作用的节点必须可幂等恢复。
- 对比 Legacy 与 LangGraph 决策差异后再扩大流量。

### 阶段8：灰度与生产化

步骤：

1. Shadow：只计算团队和分配建议，不改变真实执行。
2. 5%低风险任务：共享池真实认领，Legacy可回退。
3. 25%低风险任务：启用动态实例和自动替换。
4. 逐步开放软件和运营任务；L2需加强审批。
5. L3始终保留独立审批、补偿授权和人工接管。
6. 进行多Worker、数据库重启、租约过期、消息积压和局部网络故障演练。

生产门禁：任务重复率为0；迟到写入为0；无审计分配为0；未授权副作用为0；故障恢复、事件延迟和人工接管时间满足SLO。

## 6. 功能开关与兼容策略

建议开关：

- `AGENT_TEAM_ENABLED=false`
- `AGENT_TEAM_SHADOW=true`
- `AGENT_TEAM_DYNAMIC_ASSIGNMENT=false`
- `AGENT_TEAM_PEER_MESSAGING=false`
- `AGENT_TEAM_LANGGRAPH=false`

旧计划继续使用 `mission_steps.agent_id`。Agent Team 开启后，该字段保存兼容性的基础智能体或最终选中实例的基础 Agent；真实分配详情以 TaskClaim 为准。任何阶段出现异常均可停止生成新 Team，已存在 Mission 回退到现有 Worker 主链。

## 7. 实施顺序和完成定义

阶段 0 已冻结跨域契约；后续严格按阶段 1 到阶段 8 执行。每个阶段必须完成：实现、单元测试、集成测试、故障路径验证、文档、前端契约或运维说明；不得仅凭界面演示宣布完成。若质量门禁失败，停留在当前阶段修复，不提前扩展范围。
