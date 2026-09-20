# 业务流第四阶段：高风险步骤授权与副作用防重

## 目标

第四阶段补齐第一阶段风险契约中尚未执行的步骤级控制。计划整体获批不再代表其中的 L3 动作可以直接执行；每个 `approval_required=true` 的步骤都必须在依赖完成后获得一次独立、限时且绑定合同快照的人工授权。

核心不变量：

- 未授权的高风险步骤不能被 worker 领取；
- 审批只对当前 mission、计划版本、步骤和合同哈希有效；
- 已消费的审批不能用于崩溃重试；
- 过期、旧版本或合同不匹配的审批不能恢复执行；
- 副作用重试使用 StepSpec 的稳定幂等键，不使用会变化的租约 token。

## 状态模型

步骤状态增加 `awaiting_approval`：

```text
draft -> ready -> awaiting_approval -> ready -> running
                         |                    |
                         +-> failed           +-> completed / failed
```

当一个需要审批的步骤依赖全部完成时，`claim_ready_steps` 不会领取该步骤，而是：

1. 生成 `mission_step_approvals` 请求；
2. 将步骤置为 `awaiting_approval`；
3. 记录 `step_approval_requested` 事件；
4. 通过现有 outbox 发送审批通知。

管理员批准后步骤回到 `ready`。真正领取步骤时，审批立即变成 `consumed`。如果 worker 在执行期间崩溃，租约恢复只会把步骤放回 `ready`，下次领取前必须生成新的审批请求。

## 审批绑定

每个审批保存不可变 `contract_hash`，覆盖：

- mission、计划版本、步骤、顺序；
- 标题、目标、描述、智能体和任务类型；
- 输入参数、风险等级、副作用标记和影响资源；
- 幂等键、回滚方案和补偿合同。

API 决策必须同时提交 `approval_id` 和 `contract_hash`。审批请求不是当前最新版本、合同哈希不一致、请求过期或步骤不处于等待审批状态时，服务返回冲突，且不会执行步骤。

## 生命周期与时效

默认配置：

```bash
COMMAND_CENTER_STEP_APPROVAL_TTL=1800
COMMAND_CENTER_STEP_APPROVAL_REQUEST_TTL=86400
```

- `STEP_APPROVAL_TTL`：批准后可以被 worker 消费的时间窗口；
- `STEP_APPROVAL_REQUEST_TTL`：未决审批请求的有效期；
- worker 周期性执行 `expire_step_approvals`，把过期请求或授权旋转为新请求，不会把步骤自动变为可执行。

任务取消时，所有未决或尚未消费的步骤审批同步取消。拒绝步骤时，该步骤进入 `failed`，mission 进入 `waiting_feedback`。

## 副作用幂等

此前 WorkRun 使用 `mission-step:{step_id}:{lease_token}`，租约恢复后 token 改变，无法形成跨重试防重。本阶段改为：

```text
dispatch_id    = mission-step:{step_id}
idempotency_key = StepSpec.idempotency_key
```

执行提示明确要求所有写操作和外部副作用原样传递该幂等键，且不得扩大已审批资源、参数或作用域。

## API

- `GET /api/v3/command-center/missions/{mission_id}/step-approvals`
- `POST /api/v3/command-center/missions/{mission_id}/steps/{step_id}/approve`
- `POST /api/v3/command-center/missions/{mission_id}/steps/{step_id}/reject`
- `GET /api/v3/command-center/capabilities` 返回 `step_approval` 策略。
- `GET /api/v3/command-center/summary` 返回 `pending_step_approvals`。

批准和拒绝接口仅允许管理员。Mission 详情包含完整 `step_approvals` 历史；每个步骤包含当前 `step_approval`。

## 前端交互

指挥中心步骤列表会展示高风险动作、影响资源、回滚方案和合同指纹。批准操作使用 Element Plus 二次确认；拒绝必须填写原因。按钮只对管理员显示。

## 本阶段不包含

- 不自动执行补偿合同；补偿编排属于下一阶段；
- 不把 L2 默认升级为人工审批，仍由 FlowSpec 策略决定；
- 不声称 LLM 提示本身能保证外部系统幂等，外部连接器仍必须实现幂等键落库或去重；
- 不在本阶段扩大 LangGraph 到 L2/L3 业务节点。

