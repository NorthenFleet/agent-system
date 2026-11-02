# 需求覆盖矩阵 — 智能体系统工作流验证试点

> **任务编号**: mission-f165257f1043  
> **编写人**: 米开朗基罗 (🟧 测试工程)  
> **编写日期**: 2026-10-02  
> **版本**: v1.0-draft  
> **验收标识**: WF-PILOT-CONTEXT-20261002

---

## 1. 矩阵说明

本矩阵覆盖智能体系统核心工作流的 14 个测试场景，对应源码中的关键接口与状态转换。
每个场景包含编号、目标、前置条件、步骤、预期结果、证据要求、优先级。
**所有"实际结果"字段统一填写"未执行"**。

### 验收标识 WF-PILOT-CONTEXT-20261002 说明

> ⚠️ **人工介入字段**：覆盖矩阵必须包含"产物实际可打开"的检查。
> 此字段由 feedback 人工补传（即人工确认文件可正常打开、内容完整），非自动传递。
> 本矩阵在备注列如实标注该标识，表示此场景需人工验证产物可访问性。

---

## 2. 需求覆盖矩阵

| 场景编号 | 目标 | 前置条件 | 步骤 | 预期结果 | 证据要求 | 优先级 | 实际结果 | 验收标识备注 |
|---------|------|---------|------|---------|---------|-------|---------|-------------|
| WF-001 | 验证任务创建与上下文传递 | 系统已启动，数据库已初始化 | 1. 调用 `POST /api/v3/command-center/missions` 创建任务，携带 context 字段（含 goal、scope、acceptance_marker）<br>2. 查询任务详情 | 任务创建成功，context 完整保留，acceptance_marker=`WF-PILOT-CONTEXT-20261002` 可被后续检索 | 任务 ID、context JSON 截图、数据库记录 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-002 | 验证计划自动生成（李奥纳多角色） | 存在 pending/in_progress 状态的任务 | 1. 调用 `AutoPlanManager.leonardo_auto_generate()`<br>2. 检查 task_plans.json | 为每个无计划的任务生成 plan，状态为 pending_review，记录日志 | plan_id、日志条目、task_plans.json 内容 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-003 | 验证计划审核通过（擎天柱角色） | 存在 pending_review 状态的计划 | 1. 调用 `PlanManager.review_plan(plan_id, approved=True)`<br>2. 检查计划状态 | 计划状态变为 approved，reviewer=擎天柱，reviewed_at 非空 | 计划状态变更日志、reviewed_at 时间戳 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-004 | 验证计划退回（plan_rejected 事件） | 存在 pending_review 状态的计划 | 1. 调用 `PlanManager.review_plan(plan_id, approved=False, comment="需要修改")`<br>2. 检查计划状态和事件日志 | 计划状态变为 rejected，review_comment 记录退回原因，触发 plan_rejected 事件 | 计划状态、review_comment、事件日志 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-005 | 验证工作流状态机转换 | 任务处于 pending 状态 | 1. 依次执行 pending→assigned→in_progress→review→testing→done→archived<br>2. 每次转换后查询任务历史 | 每次转换成功，workflow_history 记录完整转换链，无非法跳转 | 每次转换的 HTTP 响应、workflow_history 数组 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-006 | 验证非法状态转换拒绝 | 任务处于 pending 状态 | 1. 尝试从 pending 直接跳转到 testing<br>2. 检查响应 | 返回 409 错误，状态未变更，错误信息说明允许的转换 | HTTP 409 响应、错误消息 | P1 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-007 | 验证多智能体依赖执行 | 计划包含 3 个步骤，步骤 2 依赖步骤 1 | 1. 执行步骤 1（research 类型）<br>2. 尝试跳过步骤 1 直接执行步骤 2<br>3. 按顺序执行步骤 2 | 步骤 1 完成后步骤 2 可执行；跳过依赖时返回错误 | 步骤执行日志、依赖校验错误 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-008 | 验证独立质量审核（PlanQualityService） | 计划包含至少 1 个步骤 | 1. 调用 `PlanQualityService.enrich_plan(plan, mission)`<br>2. 检查 plan_quality 字段 | 返回 score、blockers、warnings、suggestions；若 blockers 非空则 status=blocked | plan_quality JSON、score 值、blockers 列表 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-009 | 验证产物保存与版本追溯 | 步骤执行完成并返回 artifacts | 1. 执行步骤并返回 artifacts（含 uri、content_hash）<br>2. 查询 mission_artifacts 表<br>3. 修改计划并重新执行，检查版本 | artifacts 持久化到数据库，mission_plan_versions 记录版本链，content_hash 可校验 | artifact URI、SHA-256 哈希、版本号 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-010 | 验证证据验收（ExecutionEvidenceService） | 步骤配置 evidence_required 字段 | 1. 执行步骤但缺少要求的证据类型<br>2. 执行步骤并提供完整证据 | 缺少证据时 execution_quality.status=blocked；完整证据时 status=pass | execution_quality JSON、missing_evidence 列表 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-011 | 验证交付状态同步 | 任务处于 running 状态 | 1. 更新任务状态为 completed<br>2. 查询任务统计<br>3. 检查 notification_outbox | 任务状态更新成功，统计数据反映变更，通知事件写入 outbox | 状态变更日志、统计快照、outbox 记录 | P1 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-012 | 验证失败恢复与补偿（CompensationService） | 步骤配置 side_effect=true 且执行失败 | 1. 执行副作用步骤并模拟失败<br>2. 检查 effect journal<br>3. 触发补偿流程 | effect journal 记录 status=applied/unknown，补偿合约生成 contract_hash，等待审批 | effect journal JSON、contract_hash、补偿状态 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-013 | 验证重复提交幂等性 | 步骤配置 idempotency_key | 1. 使用相同 idempotency_key 提交两次<br>2. 检查 work_runs 表 | 第二次提交返回幂等冲突错误或重放上次结果，不产生重复执行 | work_run 记录数、idempotency_key 唯一性约束 | P0 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |
| WF-014 | 验证速率限制防重复 | 系统启用 RateLimiterMiddleware | 1. 在 1 秒内发送 150 次相同请求<br>2. 检查响应 | 前 100 次正常返回，后续返回 429 Too Many Requests，Retry-After=60 | HTTP 429 响应、Retry-After 头、限流日志 | P1 | 未执行 | WF-PILOT-CONTEXT-20261002：需人工确认产物文件可打开 |

---

## 3. 源码引用索引

| 场景编号 | 主要源码文件 | 关键函数/类 |
|---------|------------|-----------|
| WF-001 | `routers/command_center_router.py` | `MissionCreateRequest`, `ingest_command()` |
| WF-002 | `auto_plan_manager.py` | `AutoPlanManager.leonardo_auto_generate()` |
| WF-003 | `plan_manager.py`, `auto_plan_manager.py` | `PlanManager.review_plan()`, `optimus_auto_review()` |
| WF-004 | `plan_manager.py`, `routers/command_center_router.py` | `review_plan(approved=False)`, `REJECT_PATTERN` |
| WF-005 | `routers/workflow.py` | `TRANSITIONS`, `get_task_history()` |
| WF-006 | `routers/workflow.py`, `services/command_center_service.py` | `TRANSITIONS`, `InvalidMissionTransition` |
| WF-007 | `plan_manager.py`, `services/plan_quality_service.py` | `execute_plan_step()`, `enrich_plan()` |
| WF-008 | `services/plan_quality_service.py` | `PlanQualityService.enrich_plan()`, `evaluate()` |
| WF-009 | `services/mission_run_protocol.py`, `services/work_run_service.py` | `record_artifact()`, `WorkRunService` |
| WF-010 | `services/execution_evidence_service.py` | `ExecutionEvidenceService.enrich_result()`, `evaluate()` |
| WF-011 | `services/command_center_service.py`, `task_queue.py` | `CommandCenterService`, `TaskManager.update_task_status()` |
| WF-012 | `services/compensation_service.py` | `CompensationService.compensation_contract()`, `normalize_effects()` |
| WF-013 | `services/work_run_service.py` | `WorkRunIdempotencyConflict`, `AT_MOST_ONCE_SCHEMA_VERSION` |
| WF-014 | `middleware/rate_limiter.py` | `RateLimiterMiddleware.dispatch()` |

---

## 4. 验收标识传递验证

| 检查项 | 验证方式 | 责任方 | 状态 |
|-------|---------|-------|------|
| WF-PILOT-CONTEXT-20261002 出现在项目 context | 查询 project.context.acceptance_marker | 系统自动 | 待验证 |
| 验收标识传递到智能体上下文 | ContextRetrievalService._project_content() 渲染结果包含标识 | 系统自动 | 待验证 |
| 产物实际可打开检查 | **人工确认**文件可正常打开、内容完整 | feedback 人工补传 | 待人工介入 |
| 覆盖矩阵包含所有 14 个场景 | 本矩阵已列出 WF-001 ~ WF-014 | 米开朗基罗 | ✅ 已完成 |

---

## 5. 变更日志

| 版本 | 日期 | 修改人 | 修改内容 |
|-----|------|-------|---------|
| v1.0-draft | 2026-10-02 | 米开朗基罗 | 初稿，14 个核心场景 |

---

*END OF DOCUMENT*
