# 智能体系统软件测试大纲

> **任务编号**: mission-c969c75d628a
> **验收标识**: WF-PILOT-CONTEXT-20261002
> **编写人**: 通天晓 (Ultra Magnus) 🔵
> **编写日期**: 2026-10-03
> **版本**: v1.1-revised
> **状态**: 修订稿，待第二轮独立审核
> **修订说明**: 根据救护车 (Ratchet) 第一轮审核报告 (review-report-round1.md) 修订

---

## 第 1 章 测试概述

### 1.1 测试目的

验证智能体系统 9 大工作流环节的正确性、健壮性和可追溯性，确保从项目建项到反馈闭环的完整链路满足设计要求。

### 1.2 测试范围

覆盖以下 9 个工作流环节：

1. 项目中心建项
2. 擎天柱中心任务下派
3. 计划生成与审批
4. 智能体执行
5. 依赖与状态流转
6. 产物与证据链
7. 独立审核
8. 交付验收
9. 失败重试与反馈闭环

### 1.3 测试标识

- **验收标识**: `WF-PILOT-CONTEXT-20261002`
- **项目标识**: `workflow-pilot-20261002`
- **任务编号**: `mission-c969c75d628a`

### 1.4 参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 调研笔记 | `deliverables/research-notes.md` | 9 环节源码分析 |
| 结构设计 | `deliverables/outline-structure.md` | 7 章 + 3 附录结构 |
| 需求矩阵 | `deliverables/requirements-matrix.md` | 14 场景矩阵 |
| 初稿大纲 | `deliverables/test-outline-draft.md` | 米开朗基罗 v1.0-draft |

### 1.5 术语定义

| 术语 | 定义 |
|------|------|
| MISSION_LIFECYCLE | 任务状态机，定义 10 个任务状态及合法转换 |
| STEP_LIFECYCLE | 步骤状态机，定义 7 个步骤状态及合法转换 |
| TASK_CONTRACT | 步骤执行合约，定义输出、验收、证据、风险等 |
| BUSINESS_FLOW_CONTRACT | 业务流合约，定义阶段、门控、预算、审批策略 |
| idempotency_key | 幂等键，防止步骤重复执行 |
| acceptance_marker | 验收标识，贯穿全链路的质量追溯标记 |
| content_hash | 产物 SHA-256 哈希，用于完整性校验 |

---

## 第 2 章 测试环境

### 2.1 硬件环境

| 机器 | 用途 | 备注 |
|------|------|------|
| Mac mini | 日常办公 + 智能体运行 | OpenClaw 主节点 |
| Mac Pro | 知识库同步副本 + 日常工作 | 主库所在 |
| Linux 仿真服务器 | 仿真计算任务 | 可选测试环境 |
| 大模型服务器 | 模型训练/推理 | 可选测试环境 |

### 2.2 软件环境

| 组件 | 版本要求 | 说明 |
|------|----------|------|
| Python | ≥ 3.11 | 后端运行时 |
| PostgreSQL | ≥ 15 | 主数据库 |
| OpenClaw | 最新稳定版 | 智能体调度框架 |
| FastAPI | ≥ 0.100 | API 框架 |
| LangGraph | 可选 | 可插拔工作流运行时 |

### 2.3 测试数据库

- 使用独立测试数据库，避免污染生产数据
- 测试前备份，测试后可恢复
- 数据库名称建议：`agent_system_test`

### 2.4 测试账号

| 角色 | 账号 | 权限 |
|------|------|------|
| 管理员 | admin_test | 全部权限 |
| 项目经理 | pm_test | 项目建项、任务下派、审批 |
| 执行智能体 | executor_test | 步骤执行、产物提交 |
| 审核智能体 | reviewer_test | 独立审核、质量门控 |

### 2.5 测试数据需求

各测试场景所需的初始数据如下：

| 数据类型 | 说明 | 使用场景 |
|----------|------|----------|
| 项目模板 | 包含 acceptance_marker、design_doc 结构的项目配置 | A-001, C-006 |
| 任务模板 | 预定义的 mission 类型和步骤依赖关系 | A-002, A-003 |
| 智能体配置 | executor_test_1/2、reviewer_test 等测试账号及权限 | B-009, C-007 |
| 验收标准 | WF-PILOT-CONTEXT-20261002 验收标识及 minimum_acceptance 列表 | C-006 |
| 产物样本 | 用于测试上传/中断的小文件（<1MB）和大文件（>10MB） | B-010 |
| 历史任务数据 | 已完成任务记录，用于测试恢复场景 | B-008 |

**数据准备要求**：
- 测试前通过初始化脚本加载基础数据
- 每个场景使用独立的事务，测试后回滚
- 并发测试（B-009）需预创建至少 10 个 ready 状态的步骤

---

## 第 3 章 完整工作流闭环测试（A 类）

### A-001 项目中心建项测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/command_center_service.py`
**风险等级**: L1

#### 1. 目标

验证项目中心能够正确创建项目，并完整保留 context、design_doc、acceptance_marker 等关键信息。

#### 2. 前置条件

- 测试数据库已初始化
- 管理员账号已登录
- 无同名项目存在

#### 3. 测试步骤

1. 调用项目创建接口，传入项目名称、context（含 acceptance_marker、minimum_acceptance）、design_doc
2. 查询新创建的项目记录
3. 验证 context 字段中 acceptance_marker 值为 `WF-PILOT-CONTEXT-20261002`
4. 验证 minimum_acceptance 列表非空
5. 验证 design_doc 结构完整

#### 4. 预期结果

- 项目创建成功，返回项目 ID
- context.acceptance_marker = `WF-PILOT-CONTEXT-20261002`
- context.minimum_acceptance 包含至少 4 项最低验收标准
- design_doc 包含以下必需字段且非空：`system_architecture`（含 components、data_flow、security_boundaries）、`data_structure`（含 entities、relationships、storage）、`api_interfaces`、`frontend_design`、`test_plan`、`deployment_plan`
- enabled_modules 正确记录启用的功能模块

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| API 响应 | 项目创建接口返回的 JSON | API 日志 |
| 数据库记录 | projects 表中新记录的截图 | 数据库查询 |
| context 完整性 | context 字段 JSON 展开截图 | 数据库查询 |
| design_doc 字段校验 | 执行 SQL 验证各字段存在且非空（见下方校验方法） | 数据库查询 |
| enabled_modules 校验 | 执行 SQL 验证模块列表正确性（见下方校验方法） | 数据库查询 |

**design_doc 字段校验方法**：
```sql
-- 验证 design_doc 各必需字段存在且非空
SELECT
  id,
  design_doc->>'system_architecture' IS NOT NULL AS has_architecture,
  design_doc->>'data_structure' IS NOT NULL AS has_data_structure,
  design_doc->>'api_interfaces' IS NOT NULL AS has_api_interfaces,
  design_doc->>'frontend_design' IS NOT NULL AS has_frontend,
  design_doc->>'test_plan' IS NOT NULL AS has_test_plan,
  design_doc->>'deployment_plan' IS NOT NULL AS has_deployment
FROM projects
WHERE id = '<project_id>';
-- 预期：所有 has_* 字段均为 true
```

**enabled_modules 校验方法**：
```sql
-- 验证 enabled_modules 包含预期模块
SELECT
  id,
  enabled_modules,
  enabled_modules ? 'command_center' AS has_command_center,
  enabled_modules ? 'auto_plan' AS has_auto_plan,
  enabled_modules ? 'work_run' AS has_work_run,
  jsonb_array_length(enabled_modules) AS module_count
FROM projects
WHERE id = '<project_id>';
-- 预期：所有 has_* 字段为 true，module_count >= 3
```

---

### A-002 中心任务下派测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/routers/command_center_router.py`、`backend/services/command_center_service.py`
**风险等级**: L1

#### 1. 目标

验证擎天柱中心能够通过 inbox 接口正确接收任务，并关联项目背景。

#### 2. 前置条件

- 已创建测试项目（A-001 通过）
- 项目经理账号已登录
- 项目 ID 已知

#### 3. 测试步骤

1. 调用 `POST /api/v3/command-center/inbox`，传入 InboxRequest（含 project_id、objective、description）
2. 查询 `orchestration_missions` 表确认任务记录
3. 验证任务初始状态为 `received`
4. 验证 project_id 正确关联
5. 验证 ContextRetrievalService 能够正确渲染项目背景快照

#### 4. 预期结果

- 任务创建成功，返回 mission_id
- 初始状态 = `received`
- project_id 与测试项目匹配
- 智能体上下文中包含项目背景信息
- 状态可正常流转到 `planning`

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| API 响应 | inbox 接口返回 JSON | API 日志 |
| 任务记录 | orchestration_missions 表记录 | 数据库查询 |
| 上下文快照 | 智能体接收到的 context 内容 | 智能体日志 |

---

### A-003 计划生成与审批测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/auto_plan_manager.py`、`backend/services/plan_quality_service.py`
**风险等级**: L1

#### 1. 目标

验证系统能够自动生成执行计划，质量评分通过，并正确完成审批流程。

#### 2. 前置条件

- 任务已创建并处于 `planning` 状态
- AutoPlanManager 可用
- PlanQualityService 可用

#### 3. 测试步骤

1. 触发 `AutoPlanManager.leonardo_auto_generate()` 生成计划
2. 验证计划包含 steps（含 depends_on 依赖关系）
3. 验证计划包含 acceptance_criteria 和 evidence_required
4. 调用 `PlanQualityService.enrich_plan()` 进行质量评分
5. 验证质量评分 ≥ 阈值
6. 调用 `review_plan(plan_id, approved=True)` 批准计划
7. 验证计划状态变为 `approved`
8. 验证任务状态流转到 `dispatching`

#### 4. 预期结果

- 计划生成成功，包含所有必需步骤
- 步骤依赖关系正确（拓扑排序无环）
- 质量评分通过阻断检查
- 审批后计划状态 = `approved`
- 任务状态 = `dispatching`
- `mission_plan_versions` 表记录版本

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 计划 JSON | 生成的完整计划结构 | API 响应 |
| 质量评分 | enrich_plan 返回的评分结果 | 服务日志 |
| 审批记录 | review_plan 操作日志 | API 日志 |
| 版本记录 | mission_plan_versions 表记录 | 数据库查询 |

---

### A-004 智能体执行测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`、`backend/services/mission_run_protocol.py`
**风险等级**: L1

#### 1. 目标

验证智能体能够按依赖拓扑序正确认领并执行步骤，执行结果完整记录。

#### 2. 前置条件

- 计划已批准，任务处于 `dispatching` 状态
- 执行智能体账号可用
- 步骤状态为 `ready`

#### 3. 测试步骤

1. 调用 `claim_ready_step()` 认领就绪步骤
2. 验证 `task_claims` 表记录认领关系
3. 验证步骤状态变为 `running`
4. 智能体执行步骤逻辑，生成 artifacts 和 evidence
5. 调用 `add_artifact()` 提交产物
6. 验证产物写入 `mission_artifacts` 表
7. 验证步骤状态变为 `completed`
8. 验证下游步骤依赖解除，变为 `ready`

#### 4. 预期结果

- 步骤按依赖拓扑序执行，无并发冲突
- task_claims 记录完整
- 产物 uri 和 content_hash 正确记录
- 步骤状态正确流转
- 下游步骤依赖正确解除

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 认领记录 | task_claims 表记录 | 数据库查询 |
| 产物记录 | mission_artifacts 表记录 | 数据库查询 |
| 执行日志 | 智能体执行过程日志（最低要求见下方） | 智能体日志 |
| 状态流转 | 步骤状态变化日志 | 服务日志 |

**执行日志最低内容要求**：

每条执行日志必须包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| agent_id | string | 执行智能体标识 |
| step_id | string | 步骤标识 |
| started_at | ISO8601 | 执行开始时间 |
| finished_at | ISO8601 | 执行结束时间 |
| artifacts | array | 产物列表（uri + content_hash） |
| status | string | 执行结果状态（success/failed） |
| error_message | string? | 失败时的错误信息 |

---

### A-005 依赖与状态流转测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/business_flow_service.py`
**风险等级**: L2

#### 1. 目标

验证任务状态机和步骤状态机的所有合法转换正确执行，非法转换被拒绝。

#### 2. 前置条件

- MISSION_LIFECYCLE 和 STEP_LIFECYCLE 定义已加载
- 测试数据库已初始化

#### 3. 测试步骤

1. 遍历 MISSION_LIFECYCLE 中所有合法状态转换，逐一验证
2. 尝试非法状态转换（如 `completed → running`），验证返回 409 错误
3. 遍历 STEP_LIFECYCLE 中所有合法状态转换，逐一验证
4. 尝试非法步骤状态转换，验证返回 409 错误
5. 验证 CONTRACT_SCHEMAS 中必需字段校验
6. 验证 RISK_LEVELS 四级风险策略正确应用

#### 4. 预期结果

- 所有合法转换正常执行
- 所有非法转换返回 409 错误
- 必需字段缺失时返回 422 错误
- 风险等级策略正确应用（L0-L3）

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 状态转换矩阵 | 合法/非法转换测试结果表 | 测试脚本输出 |
| 错误响应 | 非法转换的 409 响应截图 | API 日志 |
| 字段校验 | 必需字段缺失的 422 响应 | API 日志 |

---

### A-006 产物与证据链测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`、`backend/services/execution_evidence_service.py`
**风险等级**: L1

#### 1. 目标

验证产物 URI 可访问、content_hash 校验通过、证据链完整。

#### 2. 前置条件

- 步骤执行完成，产物已提交
- 产物文件实际存在于指定路径

#### 3. 测试步骤

1. 查询 `mission_artifacts` 表获取产物列表
2. 对每个产物，验证 uri 指向的文件存在且可访问
3. 计算文件实际 SHA-256，与 content_hash 比对
4. 调用 `ExecutionEvidenceService.evaluate()` 校验证据完整性
5. 验证所有必需证据类型均已提供
6. 验证验收标识 `WF-PILOT-CONTEXT-20261002` 在证据中可追溯

#### 4. 预期结果

- 所有产物 URI 可访问
- SHA-256 哈希 100% 匹配
- 证据完整性评估通过
- 验收标识全链路可追溯

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 产物清单 | mission_artifacts 表查询结果 | 数据库查询 |
| 哈希比对 | 计算值 vs 存储值比对表 | 测试脚本输出 |
| 文件存在性 | ls -la 或 file 命令输出 | 系统命令 |
| 评估结果 | ExecutionEvidenceService.evaluate() 返回 | 服务日志 |

---

### A-007 独立审核测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/routers/command_center_router.py`、`backend/services/plan_quality_service.py`
**风险等级**: L2

#### 1. 目标

验证独立审核流程正确执行，编写者与审核者不为同一智能体。

#### 2. 前置条件

- 步骤已执行完成，处于 `review` 状态
- 审核智能体账号可用
- 审核智能体与执行智能体不同

#### 3. 测试步骤

1. 验证步骤状态为 `review`
2. 审核智能体调用 `approve_mission_step()` 或 `reject_mission_step()`
3. 验证审核记录写入 `mission_step_approvals` 表
4. 验证审核意见、审核人、审核时间正确记录
5. 批准时验证步骤状态变为 `completed`
6. 打回时验证步骤状态回到 `running`，并记录审核意见
7. 验证编写者与审核者身份不同

#### 4. 预期结果

- 审核记录完整可追溯
- 审核意见关联到项目验收条件
- 编写者 ≠ 审核者
- 状态流转正确

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 审核记录 | mission_step_approvals 表记录 | 数据库查询 |
| 身份比对 | 执行者与审核者 agent_id 比对 | 数据库查询 |
| 状态流转 | 步骤状态变化日志 | 服务日志 |

---

### A-008 交付验收测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/command_center_service.py`
**风险等级**: L2

#### 1. 目标

验证交付质量门控正确执行，所有验收条件满足时任务可进入 `completed` 状态。

#### 2. 前置条件

- 所有步骤已执行完成并通过独立审核
- 产物和证据链完整
- 任务处于 `evaluating` 状态

#### 3. 测试步骤

1. 调用 `evaluate_delivery_quality()` 执行质量门控检查
2. 验证产物完整性检查通过
3. 验证证据充分性检查通过
4. 验证质量评分检查通过
5. 验证项目背景关联性检查通过
6. 查询 `mission_acceptance_gates` 表，验证 `blocked_gates = 0`
7. 验证任务状态流转到 `completed`
8. 验证验收标识 `WF-PILOT-CONTEXT-20261002` 记录在案

#### 4. 预期结果

- 所有质量门控通过
- blocked_gates = 0
- 任务状态 = `completed`
- 验收标识完整记录
- 任务完成时间戳正确

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 门控结果 | mission_acceptance_gates 表记录 | 数据库查询 |
| 质量评分 | evaluate_delivery_quality() 返回 | 服务日志 |
| 完成记录 | 任务完成状态和时间戳 | 数据库查询 |
| 验收标识 | WF-PILOT-CONTEXT-20261002 追溯记录 | 数据库查询 |

---

### A-009 端到端全链路测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: 全链路源码
**风险等级**: L3

#### 1. 目标

验证从项目建项到任务完成的完整 9 环节链路无断点，验收标识全链路传递。

#### 2. 前置条件

- 测试数据库已初始化并备份
- 所有测试账号可用
- 测试环境稳定

#### 3. 测试步骤

1. 执行 A-001 创建测试项目
2. 执行 A-002 创建任务并关联项目
3. 执行 A-003 生成并批准计划
4. 执行 A-004 智能体执行所有步骤
5. 执行 A-005 验证状态流转正确
6. 执行 A-006 验证产物和证据链
7. 执行 A-007 完成独立审核
8. 执行 A-008 完成交付验收
9. 验证任务最终状态为 `completed`
10. 验证 `WF-PILOT-CONTEXT-20261002` 在所有环节可追溯

#### 4. 预期结果

- 9 个环节全部通过
- 无环节中断或异常
- 验收标识全链路传递无丢失
- 产物完整可访问
- 证据链完整无缺失
- 任务成功完成

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 全链路日志 | 9 个环节的完整执行日志 | 系统日志 |
| 状态流转图 | 任务和步骤状态变化时序图（使用 Mermaid sequenceDiagram 语法生成） | 测试脚本生成 |
| 产物清单 | 所有产物的 URI 和哈希 | 数据库查询 |
| 验收报告 | 全链路测试通过证明 | 测试报告 |

---

## 第 4 章 异常与恢复测试（B 类）

### B-001 步骤执行失败与重试测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`、`backend/services/compensation_service.py`
**风险等级**: L2

#### 1. 目标

验证步骤执行失败时能够正确触发重试机制，并在最大尝试次数内恢复执行。

#### 2. 前置条件

- 步骤处于 `running` 状态
- 步骤配置了 `max_attempts > 1`
- 失败原因可恢复（如临时网络错误）

#### 3. 测试步骤

1. 模拟步骤执行失败（抛出可恢复异常）
2. 验证步骤状态变为 `failed`
3. 验证系统检查 `max_attempts` 配置
4. 验证系统自动重试，步骤状态回到 `running`
5. 验证 `attempt_count` 递增
6. 重复失败直到达到 `max_attempts`
7. 验证最终状态为 `failed` 且不再重试

#### 4. 预期结果

- 失败后自动重试，不超过 `max_attempts`
- 每次重试 `attempt_count` 正确递增
- 达到最大尝试次数后停止重试
- 步骤最终状态正确记录
- 重试日志完整可追溯

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 失败日志 | 每次失败的异常堆栈 | 系统日志 |
| 重试记录 | attempt_count 变化日志 | 服务日志 |
| 最终状态 | 步骤最终状态记录 | 数据库查询 |

---

### B-002 补偿合约生成与执行测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/compensation_service.py`
**风险等级**: L2

#### 1. 目标

验证步骤失败后能够正确生成补偿合约，并在审批后执行补偿逻辑。

#### 2. 前置条件

- 步骤执行失败且无法重试
- 步骤配置了 `rollback_plan`
- 补偿合约生成服务可用

#### 3. 测试步骤

1. 步骤执行失败，触发补偿流程
2. 调用 `CompensationService.compensation_contract()` 生成补偿合约
3. 验证补偿合约包含 `contract_hash`、`compensation_type`、`target_state`
4. 验证补偿状态为 `pending_approval`
5. 审批补偿合约
6. 验证补偿状态变为 `running`
7. 执行补偿逻辑
8. 验证补偿完成后状态变为 `completed`
9. 验证任务状态恢复到 `waiting_feedback`

#### 4. 预期结果

- 补偿合约正确生成
- contract_hash 唯一且可验证
- 补偿状态正确流转
- 任务状态正确恢复
- 补偿执行日志完整

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 补偿合约 | compensation_contract() 返回的合约 JSON | 服务日志 |
| 合约哈希 | contract_hash 计算验证 | 测试脚本 |
| 状态流转 | 补偿状态变化日志 | 数据库查询 |
| 执行日志 | 补偿执行过程日志 | 系统日志 |

---

### B-003 任务状态非法转换测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/business_flow_service.py`
**风险等级**: L2

#### 1. 目标

验证任务状态机拒绝所有非法状态转换，返回 409 错误。

#### 2. 前置条件

- MISSION_LIFECYCLE 状态机已加载
- 任务处于特定状态

#### 3. 测试步骤

1. 任务处于 `completed` 状态，尝试转换到 `running`，验证返回 409
2. 任务处于 `cancelled` 状态，尝试转换到任何状态，验证返回 409
3. 任务处于 `received` 状态，尝试转换到 `dispatching`（跳过 planning），验证返回 409
4. 任务处于 `running` 状态，尝试转换到 `received`，验证返回 409
5. 验证所有非法转换均被拒绝

#### 4. 预期结果

- 所有非法转换返回 409 Conflict
- 错误消息明确说明非法转换
- 任务状态保持不变
- 审计日志记录非法尝试

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 错误响应 | 409 响应 JSON | API 日志 |
| 状态不变 | 转换前后任务状态比对 | 数据库查询 |
| 审计日志 | 非法转换尝试记录 | 系统日志 |

---

### B-004 计划驳回与重新规划测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/auto_plan_manager.py`、`backend/plan_manager.py`
**风险等级**: L1

#### 1. 目标

验证计划被驳回后能够正确回到 planning 状态，并支持重新生成计划。

#### 2. 前置条件

- 计划处于 `awaiting_approval` 状态
- 审批人有驳回权限

#### 3. 测试步骤

1. 调用 `review_plan(plan_id, approved=False, review_comment="质量不达标")`
2. 验证计划状态变为 `rejected`
3. 验证任务状态回到 `planning`
4. 验证 `review_comment` 正确记录
5. 触发重新生成计划
6. 验证新计划版本号递增
7. 验证 `mission_plan_versions` 表记录版本链

#### 4. 预期结果

- 驳回后计划状态 = `rejected`
- 任务状态 = `planning`
- 审核意见正确记录
- 新计划版本号正确递增
- 版本链完整可追溯

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 驳回记录 | review_comment 和状态变化 | API 日志 |
| 版本链 | mission_plan_versions 表记录 | 数据库查询 |
| 新计划 | 重新生成的计划 JSON | API 响应 |

---

### B-005 审核打回与返工测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/routers/command_center_router.py`
**风险等级**: L2

#### 1. 目标

验证独立审核打回后步骤能够正确回到 running 状态，并支持返工重新提交。

#### 2. 前置条件

- 步骤处于 `review` 状态
- 审核智能体与执行智能体不同
- 审核智能体有驳回权限

#### 3. 测试步骤

1. 审核智能体调用 `reject_mission_step(step_id, reason="产物质量不达标")`
2. 验证步骤状态变为 `running`
3. 验证审核意见正确记录到 `mission_step_approvals` 表
4. 验证 `rejection_count` 递增
5. 执行智能体根据审核意见返工
6. 重新提交产物
7. 验证步骤状态再次进入 `review`
8. 验证返工产物与原产物版本可区分

#### 4. 预期结果

- 打回后步骤状态 = `running`
- 审核意见完整记录
- rejection_count 正确递增
- 返工产物可追溯
- 版本历史清晰可查

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 打回记录 | rejection reason 和状态变化 | API 日志 |
| 审核记录 | mission_step_approvals 表记录 | 数据库查询 |
| 返工产物 | 新旧产物对比 | 数据库查询 |
| 版本历史 | 产物版本链 | 数据库查询 |

---

### B-006 幂等性重复执行防护测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`
**风险等级**: L2

#### 1. 目标

验证幂等键能够正确防止步骤重复执行，相同 idempotency_key 的请求被拒绝。

#### 2. 前置条件

- 步骤已使用特定 idempotency_key 执行过
- 相同 idempotency_key 的请求再次到达

#### 3. 测试步骤

1. 使用 idempotency_key = "test-key-001" 执行步骤
2. 验证步骤成功执行并记录
3. 使用相同 idempotency_key 再次请求执行
4. 验证系统检测到重复，拒绝执行
5. 验证返回 409 Conflict 或幂等响应
6. 验证数据库中无重复记录

#### 4. 预期结果

- 相同 idempotency_key 不产生重复执行
- 重复请求返回 409 或幂等响应
- 数据库中只有一条执行记录
- 幂等键唯一约束生效

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 重复检测 | 重复请求的响应 | API 日志 |
| 数据库记录 | 执行记录数量查询 | 数据库查询 |
| 幂等键唯一性 | 唯一约束触发记录 | 数据库日志 |

---

### B-007 超时与自动取消测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`、`backend/services/command_center_service.py`
**风险等级**: L2

#### 1. 目标

验证步骤执行超时后能够自动取消，并触发相应的补偿流程。

#### 2. 前置条件

- 步骤配置了 `timeout_seconds`
- 步骤处于 `running` 状态
- 超时时间可配置为较短值用于测试

#### 3. 测试步骤

1. 设置步骤 timeout_seconds = 5（测试用）
2. 开始执行步骤，模拟长时间运行
3. 等待超过超时时间
4. 验证系统检测到超时
5. 验证步骤状态变为 `failed` 或 `cancelled`
6. 验证超时原因记录到日志
7. 验证是否触发补偿流程（根据配置）
8. 验证任务状态正确更新

#### 4. 预期结果

- 超时后步骤状态 = `failed` 或 `cancelled`
- 超时原因明确记录
- 补偿流程正确触发（如配置）
- 任务状态正确更新
- 超时日志完整

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 超时检测 | 超时触发日志 | 系统日志 |
| 状态变化 | 步骤状态从 running 到 failed | 数据库查询 |
| 补偿触发 | 补偿合约生成记录 | 服务日志 |
| 时间戳 | 开始时间和超时时间比对 | 数据库查询 |

---

### B-008 已完成任务恢复测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/command_center_service.py`
**风险等级**: L3

#### 1. 目标

验证已完成的任务能够通过 `reopen_for_recovery()` 恢复到可编辑状态。

#### 2. 前置条件

- 任务处于 `completed` 状态
- 有恢复权限的管理员账号
- 恢复原因明确

#### 3. 测试步骤

1. 确认任务状态为 `completed`
2. 调用 `reopen_for_recovery(mission_id, reason="发现遗漏产物")`
3. 验证任务状态变为 `waiting_feedback` 或 `evaluating`
4. 验证恢复原因记录到审计日志
5. 验证任务可重新编辑和补充产物
6. 补充遗漏产物后重新提交验收
7. 验证任务可再次进入 `completed` 状态
8. 验证恢复历史可追溯

#### 4. 预期结果

- 恢复后任务状态正确
- 恢复原因完整记录
- 可重新编辑和补充
- 恢复历史可追溯
- 最终状态正确

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 恢复记录 | reopen_for_recovery 调用日志 | API 日志 |
| 审计日志 | 恢复原因和操作记录 | 系统日志 |
| 状态变化 | 任务状态从 completed 到 waiting_feedback | 数据库查询 |
| 补充产物 | 新补充的产物记录 | 数据库查询 |

---

### B-009 并发步骤认领冲突测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`
**风险等级**: L2

#### 1. 目标

验证当两个智能体同时尝试认领同一个就绪步骤时，系统能够正确处理并发冲突，确保只有一个智能体成功认领。

#### 2. 前置条件

- 步骤处于 `ready` 状态
- 两个执行智能体账号可用（executor_test_1, executor_test_2）
- 两个智能体同时发起认领请求

#### 3. 测试步骤

1. 确认目标步骤状态为 `ready`
2. 智能体 A 调用 `claim_ready_step(step_id)` 发起认领
3. 智能体 B 在 A 认领完成前同时调用 `claim_ready_step(step_id)`
4. 验证其中一个智能体成功认领（返回 200）
5. 验证另一个智能体认领失败（返回 409 Conflict）
6. 验证 `task_claims` 表中只有一条认领记录
7. 验证步骤状态变为 `running` 且关联到成功认领的智能体
8. 验证失败方收到明确的冲突错误信息

#### 4. 预期结果

- 只有一个智能体成功认领步骤
- 另一个智能体收到 409 Conflict 响应
- task_claims 表中只有一条有效认领记录
- 步骤状态正确流转到 `running`
- 无数据不一致或重复认领

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 并发请求日志 | 两个智能体的认领请求时间戳 | API 日志 |
| 冲突响应 | 失败方的 409 响应 JSON | API 日志 |
| 认领记录 | task_claims 表查询结果（仅一条） | 数据库查询 |
| 步骤状态 | 步骤最终状态和关联 agent_id | 数据库查询 |

---

### B-010 产物提交中断与数据一致性测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`、`backend/services/execution_evidence_service.py`
**风险等级**: L2

#### 1. 目标

验证产物提交过程中发生中断（如网络断开、进程崩溃）时，系统能够正确回滚事务，确保数据一致性。

#### 2. 前置条件

- 步骤处于 `running` 状态
- 产物文件正在上传/写入过程中
- 可模拟中断（如杀死进程、断开连接）

#### 3. 测试步骤

1. 开始提交产物（调用 `add_artifact()`）
2. 在产物写入过程中模拟中断（如中断文件传输）
3. 验证事务回滚，`mission_artifacts` 表中无部分写入记录
4. 验证步骤状态保持 `running`，未变为 `completed`
5. 验证文件系统无残留的不完整产物
6. 重新提交完整产物
7. 验证产物正确写入 `mission_artifacts` 表
8. 验证 content_hash 与实际文件匹配

#### 4. 预期结果

- 中断后事务正确回滚
- mission_artifacts 表中无部分记录
- 文件系统无残留不完整文件
- 步骤状态保持 `running`
- 重新提交后产物完整正确

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 中断日志 | 中断发生的系统日志 | 系统日志 |
| 回滚记录 | 事务回滚的数据库日志 | 数据库日志 |
| 产物表查询 | 中断后 mission_artifacts 表查询（应为空） | 数据库查询 |
| 文件系统检查 | 产物目录 ls 检查（无残留文件） | 系统命令 |
| 重新提交记录 | 重新提交后的产物记录 | 数据库查询 |

---

## 第 5 章 证据与验收测试（C 类）

### C-001 产物 URI 可访问性测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/work_run_service.py`
**风险等级**: L1

#### 1. 目标

验证所有产物的 URI 指向的文件实际存在且可访问。

#### 2. 前置条件

- 产物已提交到 `mission_artifacts` 表
- 产物 URI 为本地文件路径或可访问的 URL

#### 3. 测试步骤

1. 查询 `mission_artifacts` 表获取所有产物 URI
2. 对每个 URI，检查文件是否存在（本地路径使用 `os.path.exists()`）
3. 对 URL 类型 URI，发送 HTTP HEAD 请求验证可访问性
4. 验证文件权限允许读取
5. 记录不可访问的 URI 列表

#### 4. 预期结果

- 100% 的本地文件 URI 存在且可读
- 100% 的 URL URI 返回 200 状态码
- 无权限拒绝错误
- 不可访问 URI 列表为空

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| URI 清单 | 所有产物 URI 列表 | 数据库查询 |
| 可访问性检查 | 文件存在性和 URL 可访问性检查结果 | 测试脚本输出 |
| 失败列表 | 不可访问的 URI 列表（应为空） | 测试脚本输出 |

---

### C-002 SHA-256 哈希校验测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/execution_evidence_service.py`
**风险等级**: L1

#### 1. 目标

验证所有产物的实际 SHA-256 哈希与数据库中存储的 content_hash 完全匹配。

#### 2. 前置条件

- 产物文件实际存在
- 数据库中有对应的 content_hash 记录

#### 3. 测试步骤

1. 查询 `mission_artifacts` 表获取所有产物的 uri 和 content_hash
2. 对每个产物，读取文件内容并计算 SHA-256 哈希
3. 比对计算值与数据库存储值
4. 记录不匹配的产物列表
5. 验证哈希算法一致性（统一使用 SHA-256）

#### 4. 预期结果

- 100% 的产物哈希匹配
- 无不一致记录
- 哈希算法统一为 SHA-256
- 不匹配列表为空

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 哈希比对表 | 计算值 vs 存储值比对结果 | 测试脚本输出 |
| 不匹配列表 | 哈希不匹配的产物列表（应为空） | 测试脚本输出 |
| 算法验证 | 哈希算法统一性检查 | 测试脚本输出 |

---

### C-003 证据完整性门控测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/execution_evidence_service.py`
**风险等级**: L2

#### 1. 目标

验证 `ExecutionEvidenceService.evaluate()` 能够正确校验证据完整性，缺失必需证据时阻断任务完成。

#### 2. 前置条件

- 步骤执行完成
- 证据提交不完整（故意缺失某些必需证据）

#### 3. 测试步骤

1. 提交步骤产物，但故意缺失某些必需证据类型
2. 调用 `ExecutionEvidenceService.evaluate(step_id)`
3. 验证评估结果标记为不完整
4. 验证 `blocked_gates > 0`
5. 验证任务无法进入 `completed` 状态
6. 补充缺失证据后重新评估
7. 验证评估结果标记为完整
8. 验证 `blocked_gates = 0`

#### 4. 预期结果

- 证据不完整时评估失败
- blocked_gates > 0 阻止任务完成
- 补充证据后评估通过
- blocked_gates = 0 允许任务完成
- 评估日志完整可追溯

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 评估结果 | evaluate() 返回的完整性评估 | 服务日志 |
| 门控状态 | blocked_gates 数量变化 | 数据库查询 |
| 补充记录 | 证据补充前后对比 | 数据库查询 |

---

### C-004 质量评分与阻断测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/services/plan_quality_service.py`
**风险等级**: L2

#### 1. 目标

验证 `PlanQualityService` 能够正确评分并阻断低质量计划。

#### 2. 前置条件

- 计划已生成
- 质量评分阈值已配置

#### 3. 测试步骤

1. 生成一个低质量计划（缺少关键步骤或证据要求）
2. 调用 `PlanQualityService.enrich_plan(plan_id)`
3. 验证质量评分低于阈值
4. 验证阻断检查失败
5. 验证计划无法提交审批
6. 生成一个高质量计划（完整步骤和证据）
7. 重新调用质量评分
8. 验证评分高于阈值，阻断检查通过

#### 4. 预期结果

- 低质量计划评分低于阈值，被阻断
- 高质量计划评分高于阈值，通过
- 评分标准一致可重复
- 阻断日志明确说明原因

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 评分结果 | enrich_plan() 返回的评分 | 服务日志 |
| 阻断记录 | 阻断原因和阈值比对 | 服务日志 |
| 计划对比 | 低质量和高质量计划对比 | 数据库查询 |

---

### C-005 产物实际可打开人工验证

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: 人工验证环节
**风险等级**: L3

#### 1. 目标

验证产物文件能够被人工正常打开，内容完整无损坏。

> ⚠️ **重要**：本测试必须由人工完成，系统无法自动验证文件是否可正常打开。

#### 2. 前置条件

- 产物文件实际存在
- 人工验证员已指定
- 验证工具可用（如文本编辑器、PDF 阅读器等）

#### 3. 测试步骤

1. 人工验证员打开产物文件
2. 检查文件是否能够正常打开
3. 检查文件内容是否完整
4. 检查文件格式是否正确
5. 在反馈系统中补传验证结果
6. 记录不可打开的产物列表

#### 4. 预期结果

- 100% 的产物可正常打开
- 内容完整无损坏
- 格式正确可读
- 人工验证记录完整

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 人工验证记录 | 验证员补传的验证结果 | 反馈系统 |
| 打开截图 | 产物文件打开后的截图 | 人工提供 |
| 失败列表 | 不可打开的产物列表（应为空） | 人工记录 |

---

### C-006 验收标识全链路传递测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: 全链路
**风险等级**: L2

#### 1. 目标

验证验收标识 `WF-PILOT-CONTEXT-20261002` 在 9 个工作流环节中完整传递，无丢失。

#### 2. 前置条件

- 项目创建时设置了 acceptance_marker
- 全链路测试已执行

#### 3. 测试步骤

1. 验证项目 context.acceptance_marker 存在
2. 验证任务记录中可追溯到项目
3. 验证计划中关联了项目背景
4. 验证步骤执行上下文中包含验收标识
5. 验证产物记录中可追溯到任务
6. 验证审核记录中关联到验收标准
7. 验证验收门控中检查了验收标识
8. 验证最终验收报告中包含验收标识

**各环节追溯查询方法**：

| 环节 | 查询方式 | SQL/API 示例 |
|------|----------|--------------|
| 1. 项目建项 | SQL 查询 projects 表 | `SELECT context->>'acceptance_marker' FROM projects WHERE id = '<project_id>';` |
| 2. 任务下派 | SQL 查询 orchestration_missions 表 | `SELECT project_id FROM orchestration_missions WHERE id = '<mission_id>';` 然后关联 projects 表 |
| 3. 计划生成 | API 调用 | `GET /api/v3/missions/<mission_id>/plan` 检查 plan.context_snapshot.acceptance_marker |
| 4. 智能体执行 | SQL 查询 task_claims 表 | `SELECT step_id, context_snapshot FROM task_claims WHERE mission_id = '<mission_id>';` |
| 5. 状态流转 | SQL 查询 mission_steps 表 | `SELECT id, status, mission_id FROM mission_steps WHERE mission_id = '<mission_id>';` |
| 6. 产物证据 | SQL 查询 mission_artifacts 表 | `SELECT uri, content_hash FROM mission_artifacts WHERE step_id IN (SELECT id FROM mission_steps WHERE mission_id = '<mission_id>');` |
| 7. 独立审核 | SQL 查询 mission_step_approvals 表 | `SELECT step_id, reviewer_agent_id, review_comment FROM mission_step_approvals WHERE step_id IN (SELECT id FROM mission_steps WHERE mission_id = '<mission_id>');` |
| 8. 交付验收 | SQL 查询 mission_acceptance_gates 表 | `SELECT mission_id, blocked_gates FROM mission_acceptance_gates WHERE mission_id = '<mission_id>';` |
| 9. 反馈闭环 | SQL 查询 mission_feedback 表 | `SELECT mission_id, feedback_type FROM mission_feedback WHERE mission_id = '<mission_id>';` |

#### 4. 预期结果

- 9 个环节中均可追溯到 `WF-PILOT-CONTEXT-20261002`
- 无环节丢失验收标识
- 全链路追溯完整
- 验收报告明确标识

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 追溯链 | 9 个环节的验收标识追溯记录（使用上方 SQL 查询结果） | 数据库查询 |
| 传递日志 | 验收标识传递的系统日志 | 系统日志 |
| 最终报告 | 包含验收标识的验收报告 | 测试报告 |
| 追溯查询结果 | 每个环节的 SQL 查询截图或导出 | 数据库查询 |

---

### C-007 编写与审核分离验证测试

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: `backend/routers/command_center_router.py`
**风险等级**: L2

#### 1. 目标

验证编写者与审核者不为同一智能体，审核分离原则得到执行。

#### 2. 前置条件

- 步骤已执行并提交审核
- 执行智能体和审核智能体身份明确

#### 3. 测试步骤

1. 记录执行智能体的 agent_id
2. 尝试让同一智能体执行审核操作
3. 验证系统拒绝同一智能体的审核请求
4. 验证返回 403 Forbidden 或类似错误
5. 由不同的审核智能体执行审核
6. 验证审核成功
7. 验证审核记录中编写者和审核者身份不同

#### 4. 预期结果

- 同一智能体无法同时担任编写者和审核者
- 系统拒绝违规审核请求
- 审核记录中身份分离
- 审核分离原则得到执行

#### 5. 证据要求

| 证据类型 | 说明 | 来源 |
|----------|------|------|
| 拒绝记录 | 同一智能体审核被拒绝的日志 | API 日志 |
| 身份比对 | 编写者 vs 审核者 agent_id 比对 | 数据库查询 |
| 审核记录 | 成功审核的身份记录 | 数据库查询 |

---

## 第 6 章 缺陷分级与退出条件

### 6.1 缺陷分级

| 等级 | 名称 | 定义 | 处理要求 |
|------|------|------|----------|
| S1 | 阻塞 | 导致工作流完全中断，无法继续执行 | 立即修复，阻塞所有后续测试 |
| S2 | 严重 | 核心功能异常，但有临时绕行方案 | 24 小时内修复，阻塞相关场景 |
| S3 | 一般 | 非核心功能异常，不影响主流程 | 纳入修复计划，不阻塞测试 |
| S4 | 建议 | 优化建议，不影响功能正确性 | 酌情处理 |

### 6.2 退出条件

测试完成的退出条件（全部满足方可结束）：

| 条件 | 说明 |
|------|------|
| S1 缺陷数 = 0 | 无阻塞级缺陷 |
| S2 缺陷数 = 0 | 无严重级缺陷 |
| S3 缺陷数 ≤ 3 | 一般缺陷不超过 3 个 |
| S3 有修复计划 | 每个 S3 缺陷有明确修复计划和时间表 |
| A-009 全链路通过 | 端到端全链路测试 100% 通过 |
| C-005 人工验证完成 | 产物可打开人工验证 100% 完成 |

### 6.3 暂停与恢复

#### 暂停条件

- 发现 S1 级缺陷
- 测试数据库损坏
- 测试环境不可用
- 安全事件发生

#### 恢复流程

1. 记录暂停原因和时间
2. 修复问题或恢复环境
3. 验证测试环境完整性
4. 从断点继续测试
5. 记录恢复时间和影响评估

---

## 第 7 章 独立审核机制

### 7.1 审核分离原则

| 原则 | 说明 |
|------|------|
| 编写者 ≠ 审核者 | 大纲编写者和独立审核者不得为同一智能体 |
| 利益冲突回避 | 参与开发的智能体不得审核自己负责的模块 |
| 审核资质 | 审核者需具备相关模块的测试资质 |
| 审核记录可追溯 | 所有审核意见和操作记录完整保存 |

### 7.2 审核流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  提交审核   │ ──▶ │  独立审核   │ ──▶ │  批准/打回  │ ──▶ │  记录归档   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

1. **提交审核**：编写者完成大纲后提交审核请求
2. **独立审核**：审核者独立评审大纲内容
3. **批准/打回**：审核者给出批准或打回决定及意见
4. **记录归档**：审核记录归档保存

### 7.3 审核记录

| 字段 | 说明 |
|------|------|
| 审核人 | 审核智能体的 agent_id |
| 审核时间 | 审核操作的 UTC 时间戳 |
| 审核意见 | 审核者的具体意见和建议 |
| 审核结果 | approved / rejected |
| 关联验收标准 | 审核依据的验收标准列表 |
| 审核轮次 | 第几轮审核 |

---

## 附录 A 测试场景汇总表

| 编号 | 测试主题 | 类别 | 章节 | 风险等级 | 对应环节 |
|------|----------|------|------|----------|----------|
| A-001 | 项目中心建项测试 | A | 3.1 | L1 | 环节 1 |
| A-002 | 中心任务下派测试 | A | 3.2 | L1 | 环节 2 |
| A-003 | 计划生成与审批测试 | A | 3.3 | L1 | 环节 3 |
| A-004 | 智能体执行测试 | A | 3.4 | L1 | 环节 4 |
| A-005 | 依赖与状态流转测试 | A | 3.5 | L2 | 环节 5 |
| A-006 | 产物与证据链测试 | A | 3.6 | L1 | 环节 6 |
| A-007 | 独立审核测试 | A | 3.7 | L2 | 环节 7 |
| A-008 | 交付验收测试 | A | 3.8 | L2 | 环节 8 |
| A-009 | 端到端全链路测试 | A | 3.9 | L3 | 环节 1-9 |
| B-001 | 步骤执行失败与重试测试 | B | 4.1 | L2 | 环节 4/9 |
| B-002 | 补偿合约生成与执行测试 | B | 4.2 | L2 | 环节 9 |
| B-003 | 任务状态非法转换测试 | B | 4.3 | L2 | 环节 5 |
| B-004 | 计划驳回与重新规划测试 | B | 4.4 | L1 | 环节 3 |
| B-005 | 审核打回与返工测试 | B | 4.5 | L2 | 环节 7 |
| B-006 | 幂等性重复执行防护测试 | B | 4.6 | L2 | 环节 4/9 |
| B-007 | 超时与自动取消测试 | B | 4.7 | L2 | 环节 4/5 |
| B-008 | 已完成任务恢复测试 | B | 4.8 | L3 | 环节 9 |
| C-001 | 产物 URI 可访问性测试 | C | 5.1 | L1 | 环节 6 |
| C-002 | SHA-256 哈希校验测试 | C | 5.2 | L1 | 环节 6 |
| C-003 | 证据完整性门控测试 | C | 5.3 | L2 | 环节 8 |
| C-004 | 质量评分与阻断测试 | C | 5.4 | L2 | 环节 8 |
| C-005 | 产物实际可打开人工验证 | C | 5.5 | L3 | 环节 8 |
| C-006 | 验收标识全链路传递测试 | C | 5.6 | L2 | 环节 1-9 |
| C-007 | 编写与审核分离验证测试 | C | 5.7 | L2 | 环节 7 |

| B-009 | 并发步骤认领冲突测试 | B | 4.9 | L2 | 环节 4 |
| B-010 | 产物提交中断与数据一致性测试 | B | 4.10 | L2 | 环节 4/6 |

**统计**：A 类 9 个 + B 类 10 个 + C 类 7 个 = **26 个测试场景**

---

## 附录 B 源码引用索引

| 测试场景 | 源码文件 | 关键函数/类 |
|----------|----------|-------------|
| A-001 | `command_center_service.py` | `create_project()` |
| A-002 | `command_center_router.py`, `command_center_service.py` | `POST /inbox`, `ContextRetrievalService._project_content()` |
| A-003 | `auto_plan_manager.py`, `plan_quality_service.py` | `leonardo_auto_generate()`, `enrich_plan()`, `review_plan()` |
| A-004 | `work_run_service.py`, `mission_run_protocol.py` | `claim_ready_step()`, `add_artifact()` |
| A-005 | `business_flow_service.py` | `MISSION_LIFECYCLE`, `STEP_LIFECYCLE`, `CONTRACT_SCHEMAS` |
| A-006 | `work_run_service.py`, `execution_evidence_service.py` | `add_artifact()`, `evaluate()` |
| A-007 | `command_center_router.py`, `plan_quality_service.py` | `approve_mission_step()`, `reject_mission_step()` |
| A-008 | `command_center_service.py` | `evaluate_delivery_quality()` |
| A-009 | 全链路 | 全部 |
| B-001 | `work_run_service.py`, `compensation_service.py` | 重试逻辑 |
| B-002 | `compensation_service.py` | `compensation_contract()` |
| B-003 | `business_flow_service.py` | 状态机校验 |
| B-004 | `auto_plan_manager.py`, `plan_manager.py` | `review_plan(approved=False)` |
| B-005 | `command_center_router.py` | `reject_mission_step()` |
| B-006 | `work_run_service.py` | 幂等键唯一约束 |
| B-007 | `work_run_service.py`, `command_center_service.py` | 超时检测 |
| B-008 | `command_center_service.py` | `reopen_for_recovery()` |
| B-009 | `work_run_service.py` | `claim_ready_step()` 并发控制 |
| B-010 | `work_run_service.py`, `execution_evidence_service.py` | `add_artifact()` 事务回滚 |
| C-001 | `work_run_service.py` | 产物 URI 校验 |
| C-002 | `execution_evidence_service.py` | SHA-256 校验 |
| C-003 | `execution_evidence_service.py` | `evaluate()` |
| C-004 | `plan_quality_service.py` | `enrich_plan()` |
| C-005 | 人工验证 | — |
| C-006 | 全链路 | acceptance_marker 传递 |
| C-007 | `command_center_router.py` | 审核身份校验 |

---

## 附录 C 标准化测试主题模板

每个测试主题按以下五要素模板编写：

```markdown
### [场景编号] [测试主题名称]

**验收标识**: WF-PILOT-CONTEXT-20261002
**源码依据**: [相关文件路径]
**风险等级**: L0/L1/L2/L3

#### 1. 目标
[一句话说明本测试验证什么]

#### 2. 前置条件
- [条件 1]
- [条件 2]
- [条件 N]

#### 3. 测试步骤
1. [步骤 1：操作描述]
2. [步骤 2：操作描述]
3. [步骤 N：操作描述]

#### 4. 预期结果
- [结果 1：可验证的断言]
- [结果 2：可验证的断言]
- [结果 N：可验证的断言]

#### 5. 证据要求
| 证据类型 | 说明 | 来源 |
|----------|------|------|
| [类型] | [说明] | [API/日志/文件] |
```

---

## 环节覆盖矩阵

| 工作流环节 | A 类场景 | B 类场景 | C 类场景 | 合计 |
|------------|----------|----------|----------|------|
| 1. 项目中心建项 | A-001 | — | C-006 | 2 |
| 2. 擎天柱中心任务下派 | A-002 | — | C-006 | 2 |
| 3. 计划生成与审批 | A-003 | B-004 | C-006 | 3 |
| 4. 智能体执行 | A-004 | B-001, B-006, B-007, B-009, B-010 | C-006 | 7 |
| 5. 依赖与状态流转 | A-005 | B-003, B-007 | C-006 | 4 |
| 6. 产物与证据链 | A-006 | B-010 | C-001, C-002, C-006 | 5 |
| 7. 独立审核 | A-007 | B-005 | C-006, C-007 | 4 |
| 8. 交付验收 | A-008 | — | C-003, C-004, C-005, C-006 | 5 |
| 9. 失败重试与反馈闭环 | A-009 | B-001, B-002, B-006, B-008 | C-006 | 5 |

> 注：A-009 和 C-006 为跨环节场景，在多个环节重复计数。

---

*修订完成时间: 2026-10-03 21:30 CST*
*编写人: 通天晓 (Ultra Magnus) 🔵*
*任务ID: mission-c969c75d628a*
*幂等键: mission-c969c75d628a:plan:2:step:5*
