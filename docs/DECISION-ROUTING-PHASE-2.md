# DR2：受限确定性执行与受控修复

日期：2026-10-06；状态：代码及本地隔离验证完成，生产未启用。分方案：[DR-01](DECISION-ROUTING-ARCHITECTURE.md)。

## 1. 本批交付

### 确定性执行

批准计划显式指定 `executor=deterministic-v1`，普通 Worker 才会进入纯代码分支；默认 OpenClaw 路径保持原样，不根据提示词猜测执行器。规划归一化保留该执行器，计划质量门禁校验完整契约；规划提示仅在开关启用时提供操作目录。

首批白名单只有：

- `sha256_text`：对内联 UTF-8 文本计算 SHA-256，并与计划中的预期值比较。
- `json_required_keys`：解析内联 JSON，校验顶层对象包含计划指定的键。不是完整 JSON Schema 校验。

不执行 shell、网络、任意文件读取或写入。校验内联输入不能证明外部文件实际内容。未知操作、额外参数、替换验收目标、错误输出契约均被拒绝；关闭执行器后不能降级为模型执行。

示例步骤（缺省契约由服务端补齐，最终批准的是完整契约）：

```json
{
  "title": "检查内联 JSON 的必要字段",
  "task_type": "general",
  "agent_id": "optimus",
  "executor": "deterministic-v1",
  "side_effect": false,
  "max_attempts": 1,
  "input": {
    "operation": "json_required_keys",
    "text": "{\"name\":\"demo\"}",
    "required_keys": ["name"]
  }
}
```

依赖、审批、租约、WorkRun 和结果回写沿用既有主链。WorkRun 记录真实执行器，确定性分支不调用模型或上下文检索。证据强制使用 strict 门禁，不依赖全局证据观察模式。

检查报告保存到既有结果与 artifact metadata；`canonical_content` 的 UTF-8 SHA-256 为产物校验和。`mission-result://{step_id}/attempt/{attempt}` 是账本引用标识，可通过既有 Mission 详情/交付证据 API 的 artifact metadata 读取，不是文件下载地址。失败不能填成通过验收。

### 预算

- 每步 UTF-8 文本最多 65,536 字节。
- JSON 最多 4,096 个值节点、深度 32，必需键最多 64 个，每键最多 128 字符；重复键和非法 JSON 拒绝。
- 确定性步骤默认 1 次、最多 3 次尝试；运行等待上限 5 秒。超时纯计算线程可能完成计算，但不能写入外部状态，结果仍受租约约束。
- 受控恢复使用最多 3 个计划版本（初始版 + 最多两版修复）。这是保守版本上限，已有普通计划修订也计入，不宣称按模型调用费计量。
- 领取前检查尝试预算，过期租约重新排队不能无限消耗执行次数。

### 受控修复

独立恢复开关启用后，普通 OpenClaw 步骤遇到连续两次相同失败、副作用需要核验或尝试预算耗尽，会结束该步骤并保存服务端 `recovery_control`。确定性步骤始终执行自身预算与恢复控制。

现有评估循环将失败任务置为 waiting_feedback。用户从现有反馈入口继续时，带恢复标记的任务强制进入 planning，不能清空失败结果后直接重跑。现有未解决副作用补偿仍先阻断恢复；新计划按原流程重新审批。达到计划版本上限拒绝继续恢复。

重新规划提示携带受控失败的步骤、版本、WorkRun、错误、门禁阻断及证据引用，并把它们标明为历史事实；要求新方案解释怎样消除原失败原因。没有自动启动模型顾问，也不自动批准新计划。

页面分别展示“确定性检查 · 无模型调用”“受控修复 · 已停止原步骤重试”。DR1 的影子建议仍标为建议，实际控制由独立 recovery_control 字段表达。

## 2. 配置与回退

```text
COMMAND_CENTER_DETERMINISTIC_ENABLED=false
COMMAND_CENTER_RECOVERY_CONTROL_ENABLED=false
COMMAND_CENTER_DECISION_ROUTER_MODE=off
```

默认全部关闭。确定性与恢复控制是独立开关；shadow 仍只负责观察。启用恢复控制或执行确定性步骤时，完成检查点仍保存诊断事件，以支持跨重启的连续计数。

关闭确定性开关后，已有待执行确定性步骤停止领取；不会转交 OpenClaw。已领取步骤也会在执行函数入口复核开关，关闭时返回拒绝。关闭恢复开关不清除已经记录的受控恢复标记，也不解锁预算门禁；历史阻断仍需重新规划。

本次没有生产配置修改、主动服务重启或数据库迁移。没有新增领域表，复用 mission_events、mission_steps、WorkRun、artifact/evidence 记录。

## 3. 修改落点

- `backend/services/deterministic_executor_service.py`：白名单、契约、预算、检查报告。
- `backend/services/agent_capability_registry.py`、`plan_quality_service.py`：能力与计划校验。
- `backend/services/command_center_worker.py`：归一化、规划目录、纯代码分支、恢复上下文。
- `backend/services/command_center_service.py`：受控领取、严格证据、预算和重新规划约束。
- `backend/services/decision_router_service.py`：明确确定性执行的观察建议。
- 前端指挥中心/API 类型、`.env.example`、新增后端测试及既有前端治理测试。

## 4. 验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| DR2/DR1、执行证据、审批、Command Center、集群增量兼容、WorkRun at-most-once | 104 passed | [后端日志](review/decision-routing-phase2-20261006/backend-tests.log) |
| 指挥中心展示/生命周期 | 11 passed | [前端日志](review/decision-routing-phase2-20261006/frontend-tests.log) |
| 完整构建：入口检查、vue-tsc、Vite | 通过；大 chunk 提示 | [构建日志](review/decision-routing-phase2-20261006/frontend-build.log) |
| 服务 py_compile 与涉及文件 diff --check | 通过 | 本地命令检查 |

整链测试覆盖两种操作通过 Worker/WorkRun 完成，执行期间模型和检索调用会令测试失败；报告哈希与持久内容一致；重复回写拒绝；关闭后不降级；未知操作、越界输入、深层 JSON、重复键和错误验收契约拒绝。恢复测试覆盖第二次相同失败停止、次数预算、三版计划上限、新计划审批和失败上下文传递。

未执行生产 PostgreSQL 多 worker 演练、真实浏览器视觉验收和真实任务上线试点。未宣称端到端费用下降：任务规划/最终评估仍可能调用模型。

## 5. 后续边界

DR3 增加检查点只读顾问、模型档位和代码工作区隔离。扩展外部文件校验、JSON Schema 或写操作前，必须新增对应白名单契约、资源授权及回执验证，不能把本批内联检查泛化为任意工具权限。
