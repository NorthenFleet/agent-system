# 记忆检索第八阶段：可信标注数据集

## 目标

在不自动制造“人工真值”的前提下，为每条已审核长期记忆准备多种问法草稿，用强制审核清单保证只有人工核对后的样本才能进入活跃评测集。

本阶段仍不自动激活用例，不运行未经审核的离线评测，不切换线上检索策略。

## 多问法数据模型

`memory_retrieval_eval_cases` 新增：

- `variant_key`：问法类型；
- `review_checks`：人工审核清单。

唯一约束从“用户 + 记忆来源”扩展为“用户 + 记忆来源 + 问法类型”，允许同一条记忆存储多个独立评测问法，同时保持幂等。

| `variant_key` | 用途 |
| --- | --- |
| `canonical` | 标准问法草稿 |
| `natural` | 自然会话表达 |
| `terse` | 简短、省略上下文的表达 |
| `contextual` | 带项目、用户或智能体上下文的表达 |
| `boundary` | 限制、例外和注意事项类表达 |

自动问法是可编辑草稿，不是已标注真值。

## 生成与覆盖度接口

```http
POST /api/v3/context/evaluations/retrieval/cases/generate-variants
GET  /api/v3/context/evaluations/retrieval/coverage
```

变体生成器对每条权威记忆准备 4 种附加问法，确定性 ID 包含 `source_memory_ref` 和 `variant_key`。重复执行只返回跳过数，不会新建重复数据。

覆盖度接口返回：

- 权威记忆数与已建立用例的记忆数；
- 草稿、激活、归档数量；
- 各问法类型的分布；
- 已完成审核清单、但尚未激活的草稿数；
- 距离最低激活样本数的差额；
- 尚未覆盖的权威记忆来源。

## 不可绕过的审核门禁

自动草稿从 `draft` 切换为 `active` 时，前后端同时要求：

1. `query_rewritten`：已改写为真实业务问法；
2. `scope_verified`：已核对被测用户、项目和智能体；
3. `labels_verified`：已核对期望与禁止来源。

后端把 `origin`、`source_memory_ref` 和 `variant_key` 视为已有用例的不可变溯源字段。即使客户端尝试把自动草稿伪装成手工用例，后端仍会使用原始溯源并执行审核门禁。

## 评测版本

数据集哈希已纳入 `variant_key`，评测版本升级为 `memory-retrieval-eval.v2`。任何变体、问法、标签或审核后再编辑都会改变用例版本和数据集哈希，使旧评测失效。

## 人工审核策略

不建议为了达到 30 条而批量激活模板问法。应对每条草稿执行：

1. 删除工程化标题或内部标识，改写为业务人员的表达；
2. 对同一条记忆保留有明显语义差异的问法，重复句式应归档；
3. 项目记忆必须核对 `project_id`，智能体记忆必须核对 `agent_id`；
4. 补充跨用户、已归档、过期和冲突来源为 `forbidden_source_refs`；
5. 不确定的用例保持 `draft`，明确无价值的用例进入 `archived`。

## 完成标准

- 至少 30 条人工审核且已激活用例；
- 每个权威记忆至少有 1 条激活用例；
- 存在跨用户、已归档或冲突来源的安全反例；
- 运行 `memory-retrieval-eval.v2` 离线评测；
- 数据集哈希与最新评测一致；
- 统一门禁仍仅给出建议，不自动切流。

## 初始化快照

2026-09-17 已对用户 `1` 的 7 条权威记忆执行变体生成：

- 新增 28 条变体草稿；
- 加上原有 7 条标准草稿，共 35 条；
- 5 种问法类型各 7 条；
- 第二次执行新增 0 条、跳过 28 条；
- 已激活 0 条，已完成人工审核清单 0 条；
- `promotion_ready=false`，`automatic_switch_performed=false`。

这35条仅表示“可供审核的候选池”，不表示已达到 30 条人工真值的完成标准。

## 部署校验

后端由 `ai.openclaw.agent-system-3021` launchd 服务托管。启动命令必须先加载仓库根目录 `.env`，再启动 Uvicorn；否则 `MEMORY_HYBRID_FUSION_MODE=shadow`、`MEMORY_VECTOR_ENABLED=true` 等检索配置不会进入服务进程，评测工作台会错误显示 `shadow_mode_not_active`。

2026-09-17 已完成以下运行态校验：

- launchd 服务重新加载后处于运行状态，端口 `3021` 正常监听；
- `/health` 返回 `status=ok`；
- OpenAPI 已暴露用例、变体生成、覆盖度、运行评测等 7 个接口；
- `/memory-evaluation` 可访问，页面不再显示 `shadow_mode_not_active`；
- 页面显示 7 条权威记忆、35 条草稿、5 种问法各 7 条、0 条自动激活。

后续的来源证据、审核置信度、漂移失效和不可变审计能力见《记忆检索第九阶段：标注完整性与证据审核》。
