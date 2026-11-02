# 智能体系统软件测试需求覆盖矩阵

**任务编号**: mission-f165257f1043  
**版本**: v1.0  
**创建日期**: 2026-10-02  
**创建者**: 米开朗基罗 (测试工程师)  
**验收标识**: WF-PILOT-CONTEXT-20261002

---

## 一、覆盖矩阵说明

本矩阵覆盖智能体系统工作流核心路径，基于本地源码 `/Users/apple/工作桌面/Workspace/agent-system` 只读分析。所有测试场景的**实际结果**字段统一填写"未执行"，待后续测试阶段填充。

**验收标识说明**: `WF-PILOT-CONTEXT-20261002` 标记项表示该场景需验证项目背景上下文是否正确传递，此字段由 feedback 人工补传，非自动传递。

---

## 二、核心测试场景覆盖矩阵

### 场景 TC-001: 需求接收与任务创建

| 字段 | 内容 |
|------|------|
| **编号** | TC-001 |
| **目标** | 验证通过飞书/看板接入需求后，系统正确创建 mission 并进入 received 状态 |
| **前置条件** | 1. 后端服务运行正常<br>2. 用户已认证<br>3. COMMAND_CENTER_INGRESS_TOKEN 已配置 |
| **步骤** | 1. POST /api/v3/command-center/inbox 提交需求<br>2. 检查 orchestration_missions 表新增记录<br>3. 验证 status='received' |
| **预期结果** | mission 创建成功，status='received'，conversation_id 和 owner_user_id 正确绑定 |
| **证据要求** | 1. API 响应 JSON<br>2. 数据库记录截图<br>3. mission_events 表插入记录 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证 project_id 是否正确关联到项目背景 |

---

### 场景 TC-002: 计划拆解与版本控制

| 字段 | 内容 |
|------|------|
| **编号** | TC-002 |
| **目标** | 验证擎天柱拆解计划后，mission_plan_versions 正确记录版本号，mission_steps 按依赖关系创建 |
| **前置条件** | 1. mission 处于 planning 状态<br>2. 计划包含至少 1 个步骤 |
| **步骤** | 1. 调用 save_plan() 提交计划<br>2. 查询 mission_plan_versions 表<br>3. 查询 mission_steps 表验证依赖关系 |
| **预期结果** | plan_version 递增，steps 的 dependencies_json 正确引用前置步骤 ID |
| **证据要求** | 1. plan_versions 记录<br>2. steps 列表及依赖关系 JSON<br>3. plan_quality 质量评分 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证 plan.context 是否包含项目背景快照 |

---

### 场景 TC-003: 计划审批通过流程

| 字段 | 内容 |
|------|------|
| **编号** | TC-003 |
| **目标** | 验证用户批准后 mission 从 awaiting_approval 转入 dispatching，workflow_runs 状态更新 |
| **前置条件** | 1. mission 处于 awaiting_approval 状态<br>2. plan_version 已生成 |
| **步骤** | 1. POST /api/v3/command-center/missions/{id}/approve<br>2. 检查 mission_approvals.decision='approved'<br>3. 验证 orchestration_missions.status='dispatching' |
| **预期结果** | 审批记录写入，mission 状态流转，workflow_runs.resume_payload_json 包含批准信息 |
| **证据要求** | 1. API 响应<br>2. mission_approvals 记录<br>3. mission_events 中 plan_approved 事件 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证审批意见是否可追溯到项目设计文档 |

---

### 场景 TC-004: 计划驳回与重新规划

| 字段 | 内容 |
|------|------|
| **编号** | TC-004 |
| **目标** | 验证用户驳回后 mission 回到 planning 状态，plan_rejected 事件记录，支持重新提交计划 |
| **前置条件** | 1. mission 处于 awaiting_approval 状态 |
| **步骤** | 1. POST /api/v3/command-center/missions/{id}/reject 附带驳回意见<br>2. 验证 status='planning'<br>3. 检查 mission_events 中 plan_rejected 事件<br>4. 重新调用 save_plan() 提交新版本 |
| **预期结果** | mission 回到 planning，plan_version 递增，驳回意见写入 command_messages |
| **证据要求** | 1. API 响应<br>2. plan_rejected 事件记录<br>3. 新版本 plan_version 记录 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证驳回意见是否引用项目需求 |

---

### 场景 TC-005: 多智能体依赖执行

| 字段 | 内容 |
|------|------|
| **编号** | TC-005 |
| **目标** | 验证步骤按依赖顺序调度，前置步骤未完成时后续步骤不启动 |
| **前置条件** | 1. mission 处于 dispatching 状态<br>2. 计划包含 step A → step B 依赖关系 |
| **步骤** | 1. 触发调度<br>2. 验证 step A 被 claim<br>3. 验证 step B 状态仍为 draft<br>4. 完成 step A 后验证 step B 转为 ready |
| **预期结果** | 步骤按依赖拓扑序执行，无并发冲突 |
| **证据要求** | 1. mission_steps 状态变更日志<br>2. task_claims 记录<br>3. mission_events 中 step 流转事件 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证步骤输入是否包含项目上下文 |

---

### 场景 TC-006: 独立质量审核

| 字段 | 内容 |
|------|------|
| **编号** | TC-006 |
| **目标** | 验证步骤完成后进入 review 状态，独立审核智能体可批准或打回 |
| **前置条件** | 1. step 状态为 running<br>2. 产物已提交 |
| **步骤** | 1. 调用 complete_step() 提交产物<br>2. 验证 step 进入 review<br>3. 调用 approve_mission_step() 或 reject_mission_step()<br>4. 检查审核记录 |
| **预期结果** | 审核意见写入 mission_step_approvals，step 状态正确流转 |
| **证据要求** | 1. mission_step_approvals 记录<br>2. 审核意见内容<br>3. step 状态变更事件 |
| **优先级** | P1 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证审核标准是否来自项目验收条件 |

---

### 场景 TC-007: 返工与重提

| 字段 | 内容 |
|------|------|
| **编号** | TC-007 |
| **目标** | 验证审核打回后步骤可返工重提，版本追溯正确 |
| **前置条件** | 1. step 处于 review 状态<br>2. 审核意见为 reject |
| **步骤** | 1. 调用 reject_mission_step() 打回<br>2. 验证 step 回到 running<br>3. 重新提交产物<br>4. 检查 plan_version 不变，step 更新 |
| **预期结果** | step 可多次返工，产物版本可追溯 |
| **证据要求** | 1. mission_artifacts 多版本记录<br>2. step 状态流转历史<br>3. 审核意见链 |
| **优先级** | P1 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证返工原因是否关联项目需求变更 |

---

### 场景 TC-008: 产物保存与版本追溯

| 字段 | 内容 |
|------|------|
| **编号** | TC-008 |
| **目标** | 验证产物写入 mission_artifacts，content_hash 和 uri 正确记录 |
| **前置条件** | 1. step 执行完成<br>2. 产物文件已生成 |
| **步骤** | 1. 调用 add_artifact() 提交产物<br>2. 查询 mission_artifacts 表<br>3. 验证 content_hash 为 SHA-256<br>4. 验证 uri 可访问 |
| **预期结果** | 产物记录完整，hash 校验通过，uri 指向持久化存储 |
| **证据要求** | 1. mission_artifacts 记录<br>2. 文件实际存在性验证<br>3. hash 计算比对 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证产物是否包含项目专属标识 |

---

### 场景 TC-009: 证据验收与质量门控

| 字段 | 内容 |
|------|------|
| **编号** | TC-009 |
| **目标** | 验证 mission_acceptance_gates 记录质量检查，blocked 门控阻止完成 |
| **前置条件** | 1. 所有步骤完成<br>2. 产物和证据已提交 |
| **步骤** | 1. 调用 evaluate_delivery_quality()<br>2. 检查 acceptance_gates 记录<br>3. 验证 blocked_gates=0 时允许完成<br>4. 验证 blocked_gates>0 时阻止完成 |
| **预期结果** | 质量门控正确计算，blocked 门控阻止 mission 进入 completed |
| **证据要求** | 1. mission_acceptance_gates 记录<br>2. quality.score 和 blockers 列表<br>3. mission 状态流转 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证门控规则是否来自项目验收标准 |

---

### 场景 TC-010: 交付状态同步

| 字段 | 内容 |
|------|------|
| **编号** | TC-010 |
| **目标** | 验证 mission 完成后通知 outbox 正确推送，状态同步到看板 |
| **前置条件** | 1. mission 进入 completed 状态<br>2. 所有门控通过 |
| **步骤** | 1. 调用 complete_mission()<br>2. 检查 notification_outbox 记录<br>3. 验证 WebSocket 推送<br>4. 检查看板状态更新 |
| **预期结果** | 通知正确入队，WebSocket 推送成功，看板状态一致 |
| **证据要求** | 1. notification_outbox 记录<br>2. WebSocket 推送日志<br>3. 看板 API 响应 |
| **优先级** | P1 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证通知内容是否包含项目背景摘要 |

---

### 场景 TC-011: 失败恢复与补偿

| 字段 | 内容 |
|------|------|
| **编号** | TC-011 |
| **目标** | 验证步骤失败后补偿机制触发，reopen_for_recovery 支持从 completed 恢复 |
| **前置条件** | 1. step 执行失败<br>2. 副作用已报告 |
| **步骤** | 1. 调用 fail_step() 触发补偿<br>2. 检查 mission_compensations 记录<br>3. 调用 reopen_for_recovery() 恢复 mission<br>4. 验证 mission 回到 waiting_feedback |
| **预期结果** | 补偿案例正确创建，mission 可恢复继续执行 |
| **证据要求** | 1. mission_compensations 记录<br>2. mission_reopened_for_recovery 事件<br>3. mission 状态变更 |
| **优先级** | P1 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证补偿路径是否考虑项目数据一致性 |

---

### 场景 TC-012: 重复提交与幂等性

| 字段 | 内容 |
|------|------|
| **编号** | TC-012 |
| **目标** | 验证相同 idempotency_key 的重复请求不会创建重复记录 |
| **前置条件** | 1. 首次请求已处理 |
| **步骤** | 1. 首次提交产物附带 idempotency_key<br>2. 使用相同 key 再次提交<br>3. 检查 mission_artifacts 表仅一条记录<br>4. 验证返回幂等响应 |
| **预期结果** | 重复请求被识别，不创建重复记录，返回一致结果 |
| **证据要求** | 1. 数据库唯一约束验证<br>2. API 响应一致性<br>3. 幂等键比对 |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证幂等键是否包含项目上下文哈希 |

---

### 场景 TC-013: 项目背景上下文传递

| 字段 | 内容 |
|------|------|
| **编号** | TC-013 |
| **目标** | 验证项目背景（design_doc、context_snapshot）在整个工作流中正确传递 |
| **前置条件** | 1. 项目已创建并关联 design_doc<br>2. mission 已绑定 project_id |
| **步骤** | 1. 创建 mission 时传入 project_id<br>2. 检查 mission_context_bindings 记录<br>3. 验证步骤输入包含项目背景<br>4. 验证产物包含项目标识 |
| **预期结果** | 项目背景在计划、执行、产物全链路可追溯 |
| **证据要求** | 1. mission_context_bindings 记录<br>2. 步骤 input_json 包含项目信息<br>3. 产物元数据包含 project_id |
| **优先级** | P0 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：此场景专门验证验收标识传递机制 |

---

### 场景 TC-014: 记忆审核门控

| 字段 | 内容 |
|------|------|
| **编号** | TC-014 |
| **目标** | 验证任务产出的长期记忆候选需管理员审核后才进入上下文检索 |
| **前置条件** | 1. 任务完成并产出记忆候选<br>2. 记忆审核门控启用 |
| **步骤** | 1. 提交记忆候选<br>2. 验证 memory_candidates 记录 status='pending'<br>3. 验证未审核前不被检索命中<br>4. 调用 approve_memory_candidate() 审核<br>5. 验证审核后可被检索 |
| **预期结果** | 记忆候选需审核批准后方可进入上下文 |
| **证据要求** | 1. memory_candidates 状态变更<br>2. 检索结果比对<br>3. 审核记录 |
| **优先级** | P1 |
| **实际结果** | 未执行 |
| **验收标识** | WF-PILOT-CONTEXT-20261002：需验证记忆内容是否包含项目验收标识 |

---

## 三、需求覆盖统计

| 维度 | 覆盖数 | 说明 |
|------|--------|------|
| 核心场景 | 14 | 超过最低要求 12 个 |
| P0 优先级 | 8 | 关键路径必测 |
| P1 优先级 | 6 | 重要功能 |
| 验收标识覆盖 | 14/14 | 全部场景标注 WF-PILOT-CONTEXT-20261002 |
| 正常流程 | 10 | TC-001~TC-003, TC-005~TC-006, TC-008~TC-010, TC-013 |
| 异常流程 | 4 | TC-004, TC-007, TC-011, TC-012 |

---

## 四、源码引用索引

| 场景 | 关键源码位置 |
|------|-------------|
| TC-001 | backend/routers/command_center_router.py:InboxRequest, backend/services/command_center_service.py:create_mission() |
| TC-002 | backend/services/command_center_service.py:save_plan() L2915-3050 |
| TC-003 | backend/routers/command_center_router.py:approve_mission() L950-967 |
| TC-004 | backend/services/command_center_service.py:_decide_approval() L6345-6500, plan_rejected 事件 |
| TC-005 | backend/services/command_center_service.py:claim_ready_step(), mission_steps.dependencies_json |
| TC-006 | backend/routers/command_center_router.py:approve_mission_step() L844-868 |
| TC-007 | backend/routers/command_center_router.py:reject_mission_step() L868-906 |
| TC-008 | backend/services/work_run_service.py:add_artifact() L723 |
| TC-009 | backend/services/command_center_service.py:evaluate_delivery_quality() L5500-5650 |
| TC-010 | backend/services/command_center_service.py:_queue_dispatch_notification() |
| TC-011 | backend/services/command_center_service.py:reopen_for_recovery() L3790-3900, compensation_service.py |
| TC-012 | backend/services/command_center_service.py: mission_artifacts/compensations 表 UNIQUE(idempotency_key) 约束 |
| TC-013 | backend/services/context_retrieval_service.py:retrieve() L853, mission_context_bindings 表 |
| TC-014 | backend/routers/command_center_router.py:approve_memory_candidate() L651-665, workflow.memory_review_gate |

---

## 五、验收标识专项说明

**标识名称**: WF-PILOT-CONTEXT-20261002  
**用途**: 验证项目背景上下文在工作流中的传递完整性  
**传递方式**: 人工补传（feedback 阶段由测试人员手动验证并填写）  
**验证要点**:
1. 项目 design_doc 是否关联到 mission
2. 步骤输入是否包含项目背景快照
3. 产物是否包含项目专属标识
4. 审核意见是否可追溯到项目需求

**备注**: 此标识非自动传递，需测试执行时人工确认每个场景的上下文完整性。

---

*文档生成时间: 2026-10-02 21:30 CST*  
*生成者: 米开朗基罗 (michelangelo)*  
*任务ID: mission-f165257f1043*
