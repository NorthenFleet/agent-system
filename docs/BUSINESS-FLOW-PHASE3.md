# 业务流第三阶段：证据与交付门禁

## 目标

第三阶段把第一阶段定义的 Artifact、Evidence 和 Acceptance 契约落到持久化数据与确定性门禁中。核心原则是：“执行器返回 success”不再等于“业务已完成”。

步骤只有同时满足以下条件才能进入 `completed`：

- 有结果摘要；
- 返回输出合同要求的所有交付物类型；
- 交付物包含可定位 URI 和内容哈希；
- 覆盖要求的证据类型；
- 每条验收标准都有显式 `pass` 结果；
- 能证明必需工具的实际使用；
- 包含契约要求的输出字段。

## 结构化执行结果

执行智能体被要求只返回 JSON：

```json
{
  "summary": "结果摘要",
  "tools_used": ["tool-id"],
  "artifacts": [
    {
      "artifact_key": "a1",
      "artifact_type": "contract-defined-type",
      "title": "交付物",
      "uri": "/path/or/uri",
      "content_hash": "sha256"
    }
  ],
  "evidence": [
    {
      "evidence_type": "contract-defined-type",
      "source_ref": "reproducible-reference",
      "summary": "证据摘要",
      "artifact_key": "a1",
      "confidence": 1.0
    }
  ],
  "acceptance_results": [
    {
      "criterion": "原样复制计划中的验收标准",
      "status": "pass",
      "evidence_refs": ["reproducible-reference"]
    }
  ],
  "risk_notes": "剩余风险或无"
}
```

系统可从纯 JSON 或 JSON code fence 中提取结构。如果 artifact 提供内联 `content` 但未提供哈希，系统会计算 SHA-256；仅有 URI 时不会伪造内容哈希。

## 持久化模型

Command Center 数据库新增：

- `mission_artifacts`：不可变交付物引用，使用内容指纹去重；
- `mission_evidence`：证据类型、来源、摘要、采集者和置信度；
- `mission_acceptance_gates`：步骤门禁和任务交付门禁的决策快照；
- `mission_steps.attempt_count`：证据门禁重试计数。

Artifact 与 Evidence 使用稳定指纹 `INSERT OR IGNORE`，因此 worker 重放不会制造重复记录。

## 门禁模式

```bash
COMMAND_CENTER_EVIDENCE_ENFORCEMENT=pilot
```

- `shadow`：记录问题，不改变步骤结果；
- `pilot`（默认）：只对使用 LangGraph 的 L0/L1 `document/research` 试点强制；
- `strict`：对所有新任务强制。

强制模式下，执行器成功但证据不合格时：

1. 如果未用尽 StepSpec `max_attempts`，步骤返回 `ready` 重试；
2. 用尽预算后进入 `failed`；
3. mission 按现有状态机进入 `waiting_feedback`；
4. 每次决策都保存 blocker、score、attempt 和契约快照。

## 交付级门禁

所有步骤完成后，在 mission 进入 `evaluating` 之前再检查：

- 每个步骤都有执行验收记录；
- 所有强制步骤门禁通过；
- mission 至少有持久化 artifact 和 evidence。

门禁未通过时不会调用最终评估智能体，mission 直接进入 `waiting_feedback`。

## API 与可观测性

- `GET /api/v3/command-center/capabilities` 新增 `execution_evidence`。
- `GET /api/v3/command-center/missions/{mission_id}/delivery-evidence` 返回当前计划版本的 artifact、evidence、gate 和汇总。
- mission 详情直接包含 `artifacts`、`evidence`、`acceptance_gates` 和 `delivery_gate`。
- step 详情包含自身的 artifact、evidence 和 acceptance gate。

## 总账表兼容迁移

历史上旧计划模型和 V2 任务总账曾同时声明 `tasks` 表。SQLite 启动顺序会导致旧模型先创建不兼容表。本阶段修正为：

- 旧计划任务模型专用 `legacy_plan_tasks`；
- 检测到旧 `tasks` 时做无损改名；
- 旧的不兼容审计表改名保留，不删除数据；
- 清理改名表占用的 SQLite 索引名；
- 由 `models.v2_models.Task` 重新创建唯一的 `tasks` 总账表。

迁移可重入，已是正确 V2 结构时不做任何改动。

## 第三阶段不包含

- 不对 L2/L3 业务自动放开强制执行；
- 不把外部副作用移入可重放的 LangGraph 节点；
- 不以证据表代替文档领域现有的专用引用与实验证据模型；
- 不在 SQLite 多实例环境下扩大 LangGraph 试点。

