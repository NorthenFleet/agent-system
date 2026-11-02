# 智能体系统工作流调研笔记

> **任务编号**: mission-c969c75d628a
> **调研人**: 通天晓 (Ultra Magnus) 🔵
> **调研日期**: 2026-10-03
> **版本**: v1.0

---

## 一、调研概述

本次调研覆盖智能体系统完整工作流的 9 个核心环节，基于本地源码 `/Users/apple/工作桌面/Workspace/agent-system` 的只读分析，结合已有交付物（test-outline-draft.md、requirements-matrix.md）进行汇总。

---

## 二、9 个工作流环节调研结果

### 环节 1：项目中心建项

**源码依据**: `backend/services/command_center_service.py`
**数据模型**: `projects` 表，含 `context`（JSON）、`design_doc`（JSON）、`enabled_modules`、`product_bindings`

**关键发现**:
- 项目创建时携带 `context.acceptance_marker`（如 `WF-PILOT-CONTEXT-20261002`）
- `context.minimum_acceptance` 定义最低验收标准列表
- `design_doc` 包含系统架构、数据流、API 接口等设计信息
- `enabled_modules` 控制项目启用的功能模块（development/writing/knowledge/products）

**验收标准**: 项目创建后 context 完整保留，acceptance_marker 可被后续环节检索

---

### 环节 2：擎天柱中心任务下派

**源码依据**: `backend/routers/command_center_router.py`、`backend/services/command_center_service.py`
**入口**: `POST /api/v3/command-center/inbox`（InboxRequest）

**关键发现**:
- 任务通过 inbox 接口接收，创建 `orchestration_missions` 记录
- 初始状态为 `received`
- 任务可携带 `project_id` 关联项目背景
- `ContextRetrievalService._project_content()` 渲染项目背景快照注入智能体上下文

**状态流转**: `received → planning → awaiting_approval → dispatching → running → evaluating → completed`

**验收标准**: 任务创建成功，project_id 正确关联，context 完整传递

---

### 环节 3：计划生成与审批

**源码依据**: `backend/auto_plan_manager.py`、`backend/plan_manager.py`、`backend/services/plan_quality_service.py`

**关键发现**:
- `AutoPlanManager.leonardo_auto_generate()` 为任务生成执行计划
- 计划包含 steps（含 depends_on 依赖）、resources、acceptance_criteria
- `PlanQualityService.enrich_plan()` 进行质量评分和阻断检查
- 计划状态：`pending_review → approved/rejected`
- 支持多版本：`mission_plan_versions` 表记录版本链

**审批流程**:
- `review_plan(plan_id, approved=True/False)`
- 批准后触发 dispatching
- 驳回后回到 planning，记录 review_comment

**验收标准**: 计划生成完整，质量评分通过，审批状态正确流转

---

### 环节 4：智能体执行

**源码依据**: `backend/services/command_center_service.py`、`backend/services/work_run_service.py`、`backend/services/mission_run_protocol.py`

**关键发现**:
- 步骤按依赖拓扑序调度：`claim_ready_step()`
- 步骤状态：`draft → ready → running → completed/failed`
- 智能体通过 `task_claims` 认领步骤
- 执行结果包含 artifacts、evidence、side_effects

**执行协议**:
- `mission_run_protocol` 定义执行检查点
- 支持 LangGraph 作为可插拔运行时（`workflow_runtime.py`）
- Command Center 始终是业务事实源

**验收标准**: 步骤按依赖顺序执行，无并发冲突，执行结果完整记录

---

### 环节 5：依赖与状态流转

**源码依据**: `backend/services/business_flow_service.py`

**关键发现**:
- `MISSION_LIFECYCLE` 定义任务状态机（10 个状态）
- `STEP_LIFECYCLE` 定义步骤状态机（7 个状态）
- `CONTRACT_SCHEMAS` 定义 flow 和 step 的必需字段
- `RISK_LEVELS` 定义 L0-L3 四级风险策略

**状态机规则**:
```
received → [planning, cancelled]
planning → [awaiting_approval, waiting_feedback, failed, cancelled]
awaiting_approval → [dispatching, planning, cancelled]
dispatching → [running, waiting_feedback, cancelled]
running → [waiting_feedback, evaluating, cancelled]
waiting_feedback → [planning, dispatching, running, cancelled]
evaluating → [completed, waiting_feedback, failed, cancelled]
completed → []
failed → [planning, cancelled]
cancelled → []
```

**验收标准**: 状态转换符合状态机定义，非法转换返回 409 错误

---

### 环节 6：产物与证据链

**源码依据**: `backend/services/work_run_service.py`、`backend/services/execution_evidence_service.py`

**关键发现**:
- `add_artifact()` 将交付物持久化到 `mission_artifacts` 表
- 必需字段：`uri`、`content_hash`（SHA-256）
- `ExecutionEvidenceService.evaluate()` 校验证据完整性
- 支持 artifact 类型：document、code、test_report、screenshot 等

**证据类型**:
- `test_output`：测试执行日志
- `build_output`：构建日志
- `diff_summary`：代码变更摘要
- `citations`：引用来源

**验收标准**: 产物 uri 可访问，content_hash 校验通过，证据完整无缺失

---

### 环节 7：独立审核

**源码依据**: `backend/routers/command_center_router.py`、`backend/services/plan_quality_service.py`

**关键发现**:
- 步骤完成后进入 `review` 状态
- `approve_mission_step()` / `reject_mission_step()` 进行独立审核
- 审核记录写入 `mission_step_approvals` 表
- 审核标准来自项目验收条件（acceptance_marker）

**审核流程**:
1. 智能体提交产物 → 步骤进入 review
2. 独立审核智能体（如 ratchet）评估质量
3. 批准 → 步骤 completed
4. 打回 → 步骤回到 running，记录审核意见

**验收标准**: 审核意见可追溯到项目需求，审核状态正确流转

---

### 环节 8：交付验收

**源码依据**: `backend/services/command_center_service.py`

**关键发现**:
- `evaluate_delivery_quality()` 执行质量门控检查
- `mission_acceptance_gates` 表记录门控结果
- `blocked_gates > 0` 时阻止任务完成
- 验收标识 `WF-PILOT-CONTEXT-20261002` 贯穿全链路

**验收门控**:
- 产物完整性检查
- 证据充分性检查
- 质量评分检查
- 项目背景关联性检查

**验收标准**: 所有门控通过，blocked_gates=0，任务可进入 completed

---

### 环节 9：失败重试与反馈闭环

**源码依据**: `backend/services/compensation_service.py`、`backend/services/command_center_service.py`

**关键发现**:
- `CompensationService.compensation_contract()` 生成补偿合约
- `reopen_for_recovery()` 支持从 completed 恢复
- `mission_compensations` 表记录补偿状态
- 补偿状态：`pending_approval → running → completed/failed`

**失败恢复流程**:
1. 步骤失败 → 触发补偿
2. 生成补偿合约（含 contract_hash）
3. 等待审批
4. 审批通过后执行补偿
5. 任务恢复到 waiting_feedback 状态

**幂等性**:
- `idempotency_key` 防止重复执行
- `WorkRunService` 通过唯一约束检查重复

**验收标准**: 补偿正确创建，任务可恢复，幂等键防止重复

---

## 三、现有工作流规范汇总

### 3.1 TASK_CONTRACT 结构

**来源**: `backend/services/command_center_worker.py`

```
<TASK_CONTRACT>
- step 定义（order_index, title, objective, phase）
- 依赖关系（depends_on）
- 输出合约（output_contract）
- 验收标准（acceptance_criteria）
- 证据要求（evidence_required）
- 风险等级（risk_class）
- 超时设置（timeout_seconds）
- 最大尝试次数（max_attempts）
- 幂等键（idempotency_key）
- 回滚计划（rollback_plan）
</TASK_CONTRACT>
```

### 3.2 BUSINESS_FLOW_CONTRACT 结构

**来源**: `backend/services/business_flow_service.py`

```
<BUSINESS_FLOW_CONTRACT>
- flow_key（业务流标识）
- version（版本号）
- business_type（业务类型）
- phases（阶段定义）
- required_gates（必需门控）
- budgets（预算限制）
- approval_policy（审批策略）
</BUSINESS_FLOW_CONTRACT>
```

### 3.3 风险等级策略

| 等级 | 名称 | 步骤审批 | 最大尝试 | 说明 |
|------|------|----------|----------|------|
| L0 | 只读分析 | 否 | 3 | 不改变系统状态 |
| L1 | 可逆内部变更 | 否 | 2 | 受控内部写入 |
| L2 | 重要业务变更 | 否 | 2 | 需证据和补偿路径 |
| L3 | 不可逆或外部动作 | 是 | 1 | 需步骤级审批 |

---

## 四、已有交付物参考

### 4.1 test-outline-draft.md

**路径**: `docs/review/workflow-pilot-20261002/deliverables/test-outline-draft.md`
**作者**: 米开朗基罗 (Mikey)
**版本**: v1.0-draft

**覆盖内容**:
- 14 个核心测试场景（WF-001 ~ WF-014）
- 正常流程测试（3.1-3.6）
- 异常流程测试（4.1-4.7）
- 产物质量要求（5.1-5.3）
- 缺陷分级（S1-S4）
- 退出条件（7.1-7.3）

### 4.2 requirements-matrix.md

**路径**: `docs/review/workflow-pilot-20261002/deliverables/requirements-matrix.md`
**作者**: 米开朗基罗 (Mikey)
**版本**: v1.0

**覆盖内容**:
- 14 个测试场景（TC-001 ~ TC-014）
- 每个场景含：目标、前置条件、步骤、预期结果、证据要求、优先级
- 验收标识 WF-PILOT-CONTEXT-20261002 全场景覆盖
- 源码引用索引

---

## 五、风险与注意事项

### 5.1 已识别风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 产物路径不可访问 | 无法验证产物 | 提前验证路径可访问性 |
| 测试数据污染 | 测试结果不准确 | 测试前备份，测试后恢复 |
| 数据库锁冲突 | 测试中断 | 使用独立测试数据库 |
| 上下文传递丢失 | 项目背景缺失 | 验证 acceptance_marker 传递链 |

### 5.2 人工介入点

> ⚠️ **重要**：覆盖矩阵中的"产物实际可打开"检查必须由人工完成。
> 系统无法自动验证文件是否可正常打开、内容是否完整。
> 此字段由 feedback 人工补传，非自动传递。

---

## 六、调研结论

### 6.1 工作流完整性评估

智能体系统工作流覆盖完整，9 个核心环节均有明确源码实现：

1. ✅ 项目中心建项 — context、design_doc、acceptance_marker
2. ✅ 擎天柱中心任务下派 — inbox 接口、状态流转
3. ✅ 计划生成与审批 — auto_plan、plan_quality、版本控制
4. ✅ 智能体执行 — 依赖调度、task_claims、执行协议
5. ✅ 依赖与状态流转 — MISSION_LIFECYCLE、STEP_LIFECYCLE
6. ✅ 产物与证据链 — artifacts、evidence、content_hash
7. ✅ 独立审核 — step_approvals、质量门控
8. ✅ 交付验收 — acceptance_gates、blocked_gates
9. ✅ 失败重试与反馈闭环 — compensation、reopen_for_recovery

### 6.2 大纲编写建议

基于调研，软件测试大纲应：

1. **复用已有交付物** — test-outline-draft.md 和 requirements-matrix.md 已覆盖核心场景
2. **补充独立审核章节** — 明确编写与审核分离机制
3. **强化产物验收** — 增加"产物实际可打开"的人工验证环节
4. **完善反馈闭环** — 明确返工证据保留和版本追溯要求

### 6.3 关键源码文件清单

| 文件路径 | 说明 |
|----------|------|
| `backend/services/command_center_service.py` | 指挥中心核心服务 |
| `backend/services/business_flow_service.py` | 业务流合约定义 |
| `backend/services/workflow_runtime.py` | 可插拔工作流运行时 |
| `backend/services/plan_quality_service.py` | 计划质量服务 |
| `backend/services/execution_evidence_service.py` | 执行证据服务 |
| `backend/services/compensation_service.py` | 补偿服务 |
| `backend/services/context_retrieval_service.py` | 上下文检索服务 |
| `backend/services/work_run_service.py` | 工作执行服务 |
| `backend/auto_plan_manager.py` | 自动计划管理器 |
| `backend/plan_manager.py` | 计划管理器 |

---

## 七、证据引用索引

| 调研项 | 来源 | 说明 |
|--------|------|------|
| 项目建项 | [C3] workflow-pilot-20261002 | 项目 context 结构 |
| 任务下派 | created-project.json | 项目创建记录 |
| 计划审批 | plan-v4-approval.json | 计划审批流程 |
| 状态机 | business_flow_service.py | MISSION_LIFECYCLE 定义 |
| 补偿机制 | compensation_service.py | 补偿合约生成 |
| 证据验收 | execution_evidence_service.py | 证据完整性校验 |
| 已有交付物 | test-outline-draft.md | 米开朗基罗初稿 |
| 需求矩阵 | requirements-matrix.md | 14 场景覆盖 |

---

*调研完成时间: 2026-10-03 21:09 CST*
*调研人: 通天晓 (Ultra Magnus) 🔵*
*任务ID: mission-c969c75d628a*
