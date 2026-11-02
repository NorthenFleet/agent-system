# 智能体系统软件测试大纲（初稿）

> **任务编号**: mission-f165257f1043  
> **编写人**: 米开朗基罗 (🟧 测试工程)  
> **编写日期**: 2026-10-02  
> **版本**: v1.0-draft  
> **验收标识**: WF-PILOT-CONTEXT-20261002

---

## 1. 测试范围

### 1.1 覆盖范围

本大纲覆盖智能体系统核心工作流的以下路径：

1. **需求接收**：通过 `/api/v3/command-center/inbox` 或 `MissionCreateRequest` 接收任务
2. **项目背景获取**：`ContextRetrievalService` 从项目 context 中提取 goal、scope、acceptance_marker
3. **计划拆解**：`AutoPlanManager.leonardo_auto_generate()` 为任务生成执行计划
4. **计划审批/退回**：`PlanManager.review_plan()` 支持 approved/rejected 两种决策
5. **多智能体依赖执行**：计划步骤间的 `depends_on` 依赖关系校验
6. **独立质量审核**：`PlanQualityService.enrich_plan()` 对计划进行质量评分和阻断检查
7. **返工**：计划退回后重新生成和审核的循环
8. **产物保存**：`record_artifact()` 将交付物持久化到数据库
9. **版本追溯**：`mission_plan_versions` 表记录计划版本链
10. **证据验收**：`ExecutionEvidenceService` 校验证据完整性和产物质量
11. **交付状态同步**：任务状态变更触发通知和统计更新
12. **失败恢复**：`CompensationService` 生成补偿合约并等待审批
13. **重复提交幂等**：`WorkRunService` 通过 idempotency_key 防止重复执行
14. **速率限制**：`RateLimiterMiddleware` 限制 100 次/分钟/IP

### 1.2 不在范围内

- 生产服务故障注入（后续独立任务）
- 系统代码或配置修改（本阶段仅测试）
- Git 提交（本阶段不提交）
- 外部消息发送（不通知外部系统）
- 全库端点扫描（聚焦工作流核心路径）

---

## 2. 测试环境

### 2.1 硬件环境

| 组件 | 配置 |
|-----|------|
| 服务器 | Apple Mac mini (arm64) |
| 操作系统 | macOS 26.5.2 |
| Node.js | v22.23.2 |
| Python | 3.11+ |

### 2.2 软件环境

| 组件 | 版本/路径 |
|-----|---------|
| 后端框架 | FastAPI |
| 数据库 | SQLite (`unified_dashboard.db`) |
| 仓库路径 | `/Users/apple/工作桌面/Workspace/agent-system` |
| 测试框架 | pytest |
| 测试目录 | `backend/tests/` |

### 2.3 测试数据

- 使用仓库中已有的示例任务（`task_queue.init_sample_tasks()`）
- 测试计划存储在 `data/task_plans.json`
- 工作流历史存储在 `~/.openclaw/workspace/agents/ninja-turtles/dev-loop/queue.json`

### 2.4 环境隔离

- 测试前备份 `data/task_plans.json` 和 `queue.json`
- 测试后恢复原始数据
- 不修改仓库中已有的未提交改动

---

## 3. 正常流程测试

### 3.1 任务创建与计划生成

**测试场景**: WF-001, WF-002

**测试步骤**:
1. 创建任务并携带 context（含 acceptance_marker）
2. 调用 `leonardo_auto_generate()` 生成计划
3. 验证计划状态为 `pending_review`

**预期结果**:
- 任务创建成功，context 完整保留
- 计划生成成功，包含 steps、resources、acceptance_criteria
- 日志记录 `plan_generated` 事件

### 3.2 计划审核通过

**测试场景**: WF-003

**测试步骤**:
1. 调用 `review_plan(plan_id, approved=True)`
2. 验证计划状态变为 `approved`

**预期结果**:
- 计划状态更新为 `approved`
- `reviewer` 字段记录审核人
- `reviewed_at` 时间戳非空

### 3.3 工作流状态机正向转换

**测试场景**: WF-005

**测试步骤**:
1. 从 `pending` 开始，依次转换到 `archived`
2. 每次转换后查询 `workflow_history`

**预期结果**:
- 所有转换成功（HTTP 200）
- `workflow_history` 记录完整转换链
- 无非法跳转

### 3.4 多智能体依赖执行

**测试场景**: WF-007

**测试步骤**:
1. 创建包含依赖关系的计划（步骤 2 依赖步骤 1）
2. 按顺序执行步骤 1 和步骤 2

**预期结果**:
- 步骤 1 完成后步骤 2 可执行
- 步骤执行日志记录 `completed` 状态

### 3.5 产物保存与版本追溯

**测试场景**: WF-009

**测试步骤**:
1. 执行步骤并返回 artifacts（含 uri、content_hash）
2. 查询 `mission_artifacts` 表
3. 修改计划并重新执行

**预期结果**:
- artifacts 持久化到数据库
- `mission_plan_versions` 记录版本链
- content_hash 可校验文件完整性

### 3.6 证据验收通过

**测试场景**: WF-010（成功路径）

**测试步骤**:
1. 执行步骤并提供完整证据（满足 `evidence_required`）

**预期结果**:
- `execution_quality.status` = `pass`
- 无 missing_evidence 警告

---

## 4. 异常流程测试

### 4.1 计划退回（plan_rejected 事件）

**测试场景**: WF-004

**测试步骤**:
1. 调用 `review_plan(plan_id, approved=False, comment="需要修改")`
2. 验证计划状态和事件日志

**预期结果**:
- 计划状态变为 `rejected`
- `review_comment` 记录退回原因
- 触发 `plan_rejected` 事件

### 4.2 非法状态转换拒绝

**测试场景**: WF-006

**测试步骤**:
1. 尝试从 `pending` 直接跳转到 `testing`

**预期结果**:
- 返回 HTTP 409 错误
- 状态未变更
- 错误信息说明允许的转换规则

### 4.3 质量审核阻断

**测试场景**: WF-008（阻断路径）

**测试步骤**:
1. 创建包含未知智能体或缺少必要字段的计划
2. 调用 `enrich_plan()`

**预期结果**:
- `plan_quality.status` = `blocked`
- `blockers` 列表非空
- `score` < 60

### 4.4 证据缺失阻断

**测试场景**: WF-010（失败路径）

**测试步骤**:
1. 执行步骤但缺少要求的证据类型

**预期结果**:
- `execution_quality.status` = `blocked`
- `missing_evidence` 列表非空

### 4.5 失败恢复与补偿

**测试场景**: WF-012

**测试步骤**:
1. 执行副作用步骤并模拟失败
2. 检查 effect journal
3. 触发补偿流程

**预期结果**:
- effect journal 记录 `status=applied/unknown`
- 补偿合约生成 `contract_hash`
- 补偿状态为 `pending_approval`

### 4.6 重复提交幂等冲突

**测试场景**: WF-013

**测试步骤**:
1. 使用相同 `idempotency_key` 提交两次

**预期结果**:
- 第二次返回幂等冲突错误或重放上次结果
- `work_runs` 表中只有一条记录

### 4.7 速率限制触发

**测试场景**: WF-014

**测试步骤**:
1. 在 1 秒内发送 150 次相同请求

**预期结果**:
- 前 100 次正常返回
- 后续返回 HTTP 429，`Retry-After=60`

---

## 5. 产物质量要求

### 5.1 交付物完整性

| 交付物类型 | 必需字段 | 质量要求 |
|-----------|---------|---------|
| 文档 | uri, content_hash | 文件可打开，内容完整 |
| 代码 | uri, content_hash | 通过 lint 和单元测试 |
| 测试报告 | uri, content_hash | 包含测试用例数和通过率 |
| 截图 | uri, content_hash | 分辨率 ≥ 1440×900 |

### 5.2 证据要求

| 证据类型 | 说明 | 必需性 |
|---------|------|-------|
| test_output | 测试执行日志 | P0 步骤必需 |
| build_output | 构建日志 | P0 步骤必需 |
| diff_summary | 代码变更摘要 | 代码修改必需 |
| citations | 引用来源 | 研究任务必需 |

### 5.3 验收标准

- 所有 P0 场景必须通过
- P1 场景通过率 ≥ 80%
- 无 blockers 级别的质量问题
- 产物 content_hash 可校验

---

## 6. 缺陷分级

### 6.1 缺陷等级定义

| 等级 | 名称 | 定义 | 修复时限 |
|-----|------|------|---------|
| S1 | 阻断 | 核心工作流无法执行，如状态机崩溃、计划无法生成 | 24 小时 |
| S2 | 严重 | 重要功能异常，如计划审核失败、产物无法保存 | 48 小时 |
| S3 | 一般 | 非核心功能异常，如统计不准确、通知延迟 | 1 周 |
| S4 | 建议 | 体验优化，如错误信息不清晰、日志不完整 | 2 周 |

### 6.2 缺陷处理流程

```
发现缺陷 → 记录到测试报告 → 分级（S1-S4）→ 通知李奥纳多 → 修复 → 回归测试 → 关闭
```

### 6.3 缺陷升级机制

- S1 缺陷：直接报告孙总
- S2 缺陷：报告李奥纳多，抄送项目经理
- S3/S4 缺陷：记录到测试报告，按排期修复

---

## 7. 退出条件

### 7.1 测试完成条件

- 所有 P0 场景执行完毕且通过率 100%
- P1 场景通过率 ≥ 80%
- 无 S1/S2 级别未修复缺陷
- 产物质量满足 5.1 要求

### 7.2 测试终止条件

- 发现 S1 缺陷且无法在 24 小时内修复
- 测试环境损坏无法恢复
- 孙总决定终止测试

### 7.3 测试暂停条件

- 发现多个 S2 缺陷需要集中修复
- 等待外部依赖（如数据库迁移）
- 李奥纳多决定暂停测试

---

## 8. 测试执行计划

### 8.1 执行顺序

1. **第一轮（P0 场景）**: WF-001 ~ WF-005, WF-007 ~ WF-010, WF-012 ~ WF-013
2. **第二轮（P1 场景）**: WF-006, WF-011, WF-014
3. **回归测试**: 修复缺陷后重新执行失败场景

### 8.2 时间安排

| 阶段 | 预计时间 | 负责人 |
|-----|---------|-------|
| 测试准备 | 2 小时 | 米开朗基罗 |
| P0 场景执行 | 4 小时 | 米开朗基罗 |
| P1 场景执行 | 2 小时 | 米开朗基罗 |
| 缺陷修复 | 视缺陷数量 | 拉斐尔/多纳泰罗 |
| 回归测试 | 2 小时 | 米开朗基罗 |
| 测试报告 | 1 小时 | 米开朗基罗 |

### 8.3 交付物

- 测试执行报告（包含每个场景的实际结果）
- 缺陷清单（包含分级和修复状态）
- 测试覆盖率报告（场景覆盖率、代码覆盖率）

---

## 9. 风险与缓解

### 9.1 已识别风险

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| 测试数据污染 | 测试结果不准确 | 中 | 测试前备份，测试后恢复 |
| 数据库锁冲突 | 测试中断 | 低 | 使用独立测试数据库 |
| 未提交改动被覆盖 | 丢失其他开发工作 | 低 | 测试前检查 git status，不修改系统文件 |
| 产物路径不可访问 | 无法验证产物 | 中 | 提前验证路径可访问性，失败时报告阻塞 |

### 9.2 应急计划

- 测试环境损坏：从备份恢复数据库和配置文件
- 测试数据丢失：从 `init_sample_tasks()` 重新初始化
- 产物无法保存：检查目录权限，必要时切换到临时目录

---

## 10. 验收标识验证

### 10.1 WF-PILOT-CONTEXT-20261002 传递链

1. **项目 context** → `project.context.acceptance_marker`
2. **智能体上下文** → `ContextRetrievalService._project_content()` 渲染结果
3. **测试场景** → 每个场景的"验收标识备注"列标注需人工确认产物可打开
4. **人工验证** → feedback 补传产物可访问性检查结果

### 10.2 人工介入点

> ⚠️ **重要**：覆盖矩阵中的"产物实际可打开"检查必须由人工完成。
> 系统无法自动验证文件是否可正常打开、内容是否完整。
> 此字段由 feedback 人工补传，非自动传递。

---

## 11. 变更日志

| 版本 | 日期 | 修改人 | 修改内容 |
|-----|------|-------|---------|
| v1.0-draft | 2026-10-02 | 米开朗基罗 | 初稿，包含 14 个核心场景 |

---

## 12. 附录

### 12.1 关键源码文件清单

| 文件路径 | 说明 |
|---------|------|
| `backend/routers/command_center_router.py` | 指挥中心 API |
| `backend/routers/workflow.py` | 工作流状态机 API |
| `backend/routers/mission_planning.py` | 任务规划 API |
| `backend/auto_plan_manager.py` | 自动计划管理器 |
| `backend/plan_manager.py` | 计划管理器 |
| `backend/task_queue.py` | 任务队列管理器 |
| `backend/task_dispatcher.py` | 任务派发器 |
| `backend/services/command_center_service.py` | 指挥中心服务 |
| `backend/services/plan_quality_service.py` | 计划质量服务 |
| `backend/services/execution_evidence_service.py` | 执行证据服务 |
| `backend/services/compensation_service.py` | 补偿服务 |
| `backend/services/work_run_service.py` | 工作执行服务 |
| `backend/services/mission_run_protocol.py` | 任务执行协议 |
| `backend/services/context_retrieval_service.py` | 上下文检索服务 |
| `backend/middleware/rate_limiter.py` | 速率限制中间件 |

### 12.2 测试工具

- **pytest**: 后端单元测试和集成测试
- **httpx**: API 测试客户端
- **sqlite3**: 数据库查询验证

---

*END OF DOCUMENT*
