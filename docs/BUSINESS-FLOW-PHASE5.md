# 业务流第五阶段：补偿执行与故障恢复编排

## 目标

第五阶段把 StepSpec 中的 `rollback_plan` 和 `compensation` 从计划说明升级为可执行、可审批、可恢复、可验收的故障处理流程。

系统遵守以下安全不变量：

- 补偿永不自动执行；
- 原步骤失败后，如果副作用已落地或状态未知，必须先处理补偿，原步骤才能重试；
- 补偿审批绑定合同哈希，执行时只能作用于合同指定资源；
- 补偿使用独立且稳定的幂等键；
- 中断的补偿不会自动重跑，必须重新审批；
- 没有补偿回执和验证证据，不能把补偿标记为完成。

## Effect Journal

所有 `side_effect=true` 的执行步骤必须返回：

```json
{
  "side_effects": [
    {
      "effect_key": "production-config-update",
      "resource": "production-config",
      "action": "更新生产配置",
      "status": "applied|not_applied|unknown",
      "idempotency_key": "必须与 StepSpec 一致",
      "receipt_ref": "可定位执行回执",
      "evidence_refs": ["验证日志或状态引用"]
    }
  ]
}
```

`mission_effects` 保存不可变动作身份和最新落地状态。副作用步骤未返回 journal 时，系统会生成 `unknown` 记录并硬阻断步骤完成，不受 evidence shadow/pilot 模式影响。

以下情况会创建补偿任务：

- 执行器失败，但 effect 为 `applied`；
- 执行结果无法确认 effect 是否落地；
- 证据门禁拒绝已产生副作用的结果。

`not_applied` 不创建补偿。

## 补偿状态机

```text
pending_approval -> ready -> running -> completed
       |                         |
       +-> rejected              +-> failed
                                  
ready --authorization expired--> pending_approval
running --lease expired-------> pending_approval
```

补偿合同包含：

- 补偿类型与明确指令；
- 目标资源与原 effect；
- 原操作幂等键；
- 独立补偿幂等键 `compensate:{original_key}:{effect_key}`；
- SHA-256 合同指纹。

管理员批准只会把补偿放入 `ready`。授权默认 1800 秒有效，可通过 `COMMAND_CENTER_COMPENSATION_APPROVAL_TTL` 调整（下限 60 秒）；超时未领取会回到 `pending_approval`。worker 通过租约领取，执行中持续续租。租约过期时清除旧授权并返回 `pending_approval`。

## 补偿验收

恢复执行器必须返回：

```json
{
  "summary": "补偿结果摘要",
  "status": "reverted|not_needed|failed",
  "receipt_ref": "补偿回执",
  "evidence_refs": ["恢复后的验证证据"],
  "risk_notes": "剩余风险"
}
```

只有 `reverted/not_needed + summary + receipt_ref + evidence_refs` 同时存在时，补偿进入 `completed`，原 effect 更新为 `reverted`。

## 原流程阻断

- `add_feedback` 在存在未完成补偿时只记录反馈，不会重试失败步骤；
- delivery gate 将未完成补偿作为强制 blocker，即使证据门禁运行在 shadow 模式；
- 任务取消会取消尚未完成的补偿任务；
- 补偿失败或被拒绝后，任务保持阻塞，等待新的人工处理方案。

## API 与界面

- `GET /api/v3/command-center/missions/{mission_id}/compensations`
- `POST /api/v3/command-center/missions/{mission_id}/compensations/{id}/approve`
- `POST /api/v3/command-center/missions/{mission_id}/compensations/{id}/reject`
- capabilities 新增 `compensation`；
- summary 新增 `pending_compensations`；
- mission/step 详情包含 `effects` 和 `compensations`。

指挥中心显示补偿资源、说明、稳定幂等键和合同指纹。批准使用二次确认，拒绝必须填写原因；操作仅对管理员开放。

## 本阶段不包含

- 不自动推断业务系统专属的逆操作；具体补偿指令仍由 FlowSpec/StepSpec 提供；
- 不绕过外部系统权限、事务或审批机制；
- 不自动重试失败补偿；需要人工确认失败原因后重新规划或创建新补偿；
- 不把补偿状态放入 LangGraph checkpoint，Command Center 仍是事实主库。
