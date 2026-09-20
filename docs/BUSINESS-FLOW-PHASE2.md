# 业务流第二阶段：LangGraph 最小试点

## 阶段目标

第二阶段将 LangGraph 作为可选的、可持久化的工作流运行时接入指挥中心，但不改变业务主数据的归属：

- Command Center 继续负责 mission、plan、step、approval、event 和 evidence 的业务状态。
- LangGraph 只负责执行检查点、审批中断和恢复位置。
- 长期记忆仍由现有 memory service 负责，不写入 LangGraph checkpoint。
- 原有 worker 和步骤执行器继续执行真正的业务任务。

## 架构边界

```text
Plan Quality Gate
       |
       v
Command Center (business source of truth)
       |
       +--> workflow_runs (runtime mapping, lease, retry, health)
       |          |
       |          v
       |     WorkflowRuntime Router
       |          |
       |          +--> Legacy: immediately ready
       |          |
       |          +--> LangGraph: prepare -> interrupt -> resume -> ready
       |
       v
Existing mission steps / OpenClaw executors
```

LangGraph 运行时达到 `ready` 前，即使计划已在 Command Center 中批准，mission 也不会从 `dispatching` 进入 `running`。这使 checkpoint 恢复真正成为派发闸门，而不是旁路日志。

## 试点范围

默认关闭。启用后仍需同时满足：

1. `flow_key` 为 `document` 或 `research`；
2. 计划最高风险是 `L0` 或 `L1`；
3. `langgraph` 与 `langgraph-checkpoint-sqlite` 均可用。

任一条件不满足时自动选择 `legacy` 运行时，并在 `selection_reason` 中记录原因。

## 配置

```bash
COMMAND_CENTER_LANGGRAPH_ENABLED=true
COMMAND_CENTER_LANGGRAPH_FLOWS=document,research
COMMAND_CENTER_WORKFLOW_MAX_ATTEMPTS=3
```

SQLite checkpoint 默认位置为：

```text
<command-center-db>.langgraph.sqlite3
```

生产扩容到多实例前，需在后续阶段把 checkpoint backend 换为 PostgreSQL；`WorkflowRuntime` 接口保证这一替换不会改变业务表和 API。

## 持久化状态

`workflow_runs` 对每个 `(mission_id, plan_version)` 保存一条记录：

- `start_pending -> running_start -> awaiting_approval`
- 审批后：`awaiting_approval -> resume_pending -> running_resume -> ready`
- 如果审批早于中断点，完成 start 时直接进入 `resume_pending`
- 运行时失败使用租约、指数延迟和最大重试次数
- 终止失败前不改动 mission；终止失败后将 mission 转入可恢复状态

LangGraph 节点不执行外部副作用，因此节点重放是安全的。后续把业务节点迁入图时，必须继续使用第一阶段产生的 `idempotency_key`、证据合同和补偿合同。

## 可观测性

- `GET /api/v3/command-center/workflow-runtime`：查看功能开关、依赖可用性、试点范围和运行状态统计。
- `GET /api/v3/command-center/capabilities`：同时返回业务流合同与运行时能力。
- mission 详情的 `workflow_run` 字段：查看当前计划版本的运行时、状态、检查点、重试次数和错误。
- mission event 会记录 `workflow_runtime_checkpointed`、`workflow_runtime_retrying` 和 `workflow_runtime_failed`。

## 启用顺序

1. 先在测试环境安装 `backend/requirements.txt`。
2. 保持开关关闭，通过 runtime API 确认 `available=true`。
3. 打开开关，只提交 L0/L1 的 document/research 任务。
4. 验证执行前后重启 worker，同一 `thread_id` 能从审批中断点恢复。
5. 观测重试率、审批到恢复延迟和卡在 `dispatching` 的数量。

## 本阶段不包含

- 不把所有业务步骤迁入 LangGraph。
- 不对财务、生产发布、外部发送等 L2/L3 任务开放试点。
- 不用 checkpoint 代替长期记忆或证据库。
- 不引入 LangGraph Platform/Cloud 依赖。

