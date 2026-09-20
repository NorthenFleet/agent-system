# 记忆检索第六阶段：离线标注评测与统一切流门禁

## 目标

将人工标注的期望结果和禁止结果持久化，对同一查询的基线排序与 `weighted-rrf.v1` 候选排序执行可重复对比，再与在线 Shadow 指标合并为唯一的 `promotion_ready` 判定。

系统只给出切流建议，不会自动修改 `MEMORY_HYBRID_FUSION_MODE`。

## 标注用例生命周期

标注用例保存在 `memory_retrieval_eval_cases`，支持：

- `draft`：草稿，不进入门禁；
- `active`：管理员已审核，进入评测数据集；
- `archived`：退役，不进入门禁。

每次修改递增 `version`。活跃用例的 ID、版本、查询、作用域和标签共同生成 `dataset_hash`；任何标签变化都会使旧评测报告变为过期。

用例包含：

- `subject_user_id`：执行检索时的被测用户，用于跨用户隔离测试；
- `project_id` 和 `agent_id`：检索作用域；
- `expected_source_refs`：应被召回的来源；
- `forbidden_source_refs`：绝对不应返回的跨用户、已归档或冲突来源；
- `tags` 和 `notes`：场景分类与人工复核依据。

## 接口

```http
POST /api/v3/context/evaluations/retrieval/cases
PUT  /api/v3/context/evaluations/retrieval/cases/{case_id}
GET  /api/v3/context/evaluations/retrieval/cases?status=active
POST /api/v3/context/evaluations/retrieval/run
GET  /api/v3/context/evaluations/retrieval/latest
GET  /api/v3/context/vector-memory/rollout-gate?window_hours=168
```

所有接口仅限管理员。用例的所有者、审核人和被测用户是独立字段，防止把跨用户安全测试错当成当前管理员的业务查询。

## 评测指标

每次评测使用 Context Pack 已计算的 `baseline_refs` 和 `candidate_refs`，不持久化 Context Pack，分别计算：

- Recall@K；
- Item Recall@K；
- MRR@K；
- NDCG@K；
- Forbidden Hits。

评测运行保存在 `memory_retrieval_eval_runs`，包含数据集哈希、模型版本、排序策略、基线指标、候选指标、逐例结果和门禁决策。

## 离线强制门禁

| 条件 | 默认要求 |
| --- | ---: |
| 已激活人工标注用例 | 至少 30 |
| 候选排序 Forbidden Hits | 0 |
| Recall 下降 | 0 |
| Item Recall 下降 | 0 |
| MRR 下降 | 不超过 0.02 |
| 向量检索降级或评测异常 | 0 个用例 |
| 评测数据集哈希 | 必须与当前活跃标签一致 |

最低用例数可通过以下配置调整，生产默认为 30：

```bash
MEMORY_ROLLOUT_MIN_LABELED_CASES=30
```

## 统一切流决策

`promotion_ready=true` 必须同时满足：

1. 系统仍处于 `shadow` 模式；
2. 第五阶段的在线样本量、可用率和延迟门禁全部通过；
3. 存在最新离线评测；
4. 标注数据集没有在评测后发生变化；
5. 所有离线质量与安全门禁通过。

即使全部通过，返回值中 `automatic_switch_performed` 仍固定为 false，切流仍需要显式的人工决策和配置变更。

## 当前数据边界

`backend/evals/memory_retrieval_phase1.json` 和 `memory_retrieval_phase3.json` 仅有 4–5 条早期受控用例，且包含占位来源引用。本阶段不会自动将它们激活为生产真值，必须经人工核对当前权威记忆后逐条激活。

第七阶段已在此基础上增加从已审核长期记忆生成幂等草稿的能力和管理员审核工作台，详见 `MEMORY-RETRIEVAL-PHASE7-REVIEW-WORKBENCH.md`。自动生成的样本仍保持 `draft`，不会绕过人工审核。
