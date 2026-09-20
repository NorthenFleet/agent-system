# 业务流第五阶段：Mission Run 总账与交付证据闭环

## 目标

本阶段完成两个系统级不变量：

1. 一个任务从接收、规划、审批、工作流恢复、步骤执行到最终交付，共享同一个
   `mission_run_id` 和 `correlation_id`；
2. 执行器返回 `success` 不能单独完成任务，Artifact、Evidence 和 Acceptance Gate
   必须被结构化记录，并在启用强制门禁时决定步骤与任务是否可以完成。

## Mission Run 事实主表

`mission_runs` 是任务级运行总账。每个 `orchestration_missions` 只有一个 Mission Run，
记录当前任务状态、活动计划版本、当前 workflow run、最终结果和稳定关联 ID。

各层标识的职责如下：

| 标识 | 生命周期 | 用途 |
| --- | --- | --- |
| `mission_id` | 业务任务 | 任务、权限与业务状态 |
| `mission_run_id` | 本次任务运行 | 串联规划、审批、执行、证据和交付 |
| `correlation_id` | 全链路追踪 | 日志、运行时、步骤执行和外部调用关联 |
| `workflow_run_id` | 每个计划版本 | checkpoint、中断和恢复 |
| `work_run_id` | 单步骤单次尝试 | 租约、重试、执行结果和局部产物 |

`mission_events.run_sequence` 为每个 Mission Run 提供单调递增的事件序号。历史 mission
会在数据库初始化时无损补建 Mission Run，并把原有事件、workflow、Artifact、Evidence
和 Acceptance Gate 回填到同一关联链路。

## 执行与证据关联

Command Center worker 创建 `work_runs` 时显式传入 Mission Run 的 ID 和 correlation ID，
不再为步骤执行生成互不关联的追踪 ID。结构化 Artifact、Evidence 和 Acceptance Gate
也保存这两个字段，因此可以从一次步骤尝试追溯到任务、审批、交付证据和最终结果。

证据门禁继续支持渐进发布：

- `shadow`：持久化与评估，但不改变业务结果；
- `pilot`：默认只强制 LangGraph 的低风险 document/research 试点；
- `strict`：对所有任务强制。

在强制范围内，缺少交付物、来源证据、逐项验收结果、必需工具证明或输出合同字段时，
步骤会按预算重试；预算耗尽后失败。所有步骤完成后还会执行任务级交付门禁。

## API

```http
GET /api/v3/command-center/missions/{mission_id}/run-ledger
```

该接口返回 Mission Run、顺序事件、各计划版本 workflow run、步骤 work run，以及当前
计划版本的 Artifact、Evidence 和 Acceptance Gate。权限范围沿用 mission 所有者校验。

已有证据接口继续保留：

```http
GET /api/v3/command-center/missions/{mission_id}/delivery-evidence
```

## 生产启用建议

先保持 `pilot`，用真实 document/research 任务核对证据合格率和误拒绝率；当主要执行器
均能稳定返回结构化结果后，再将 `COMMAND_CENTER_EVIDENCE_ENFORCEMENT` 切换为
`strict`。模式变化不改变已持久化的历史门禁快照。
