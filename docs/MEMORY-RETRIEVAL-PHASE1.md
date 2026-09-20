# 记忆检索优化第一阶段

## 目标

在不改变现有召回行为、不引入向量数据库的前提下，建立后续混合检索需要的稳定契约、观测数据和离线评测基线。

## 已实现

- `MemoryCandidate`：统一结构化、关键词、向量和图谱候选的数据契约。
- `RetrievalScope`：统一用户、项目、智能体和可见性范围。
- `LexicalRetriever`、`VectorRetriever`、`GraphRetriever`：存储无关的检索接口。
- Context Pack中的每条记忆记录：
  - 候选ID与内容哈希；
  - 主召回通道；
  - 分通道分数和最终分数；
  - 权威度、重要度、状态和作用域；
  - 检索契约版本。
- Context Pack顶层记录 `retrieval_strategy`，明确当前已启用通道和向量通道的 `not_configured` 状态。
- `retrieval_events`记录实际检索引擎、选中来源、分数范围和策略快照。
- 离线基线数据集及 Recall@K、MRR@K、禁止来源命中统计。

## 兼容性

原有 Context Pack字段和排序逻辑保持不变。新增数据存放在条目 `metadata.retrieval` 和 `retrieval_health.retrieval_strategy` 中；旧消费者可以忽略它们。

## 当前边界

- `vector`通道只完成契约和健康状态，尚未连接embedding服务或向量索引。
- 当前融合仍是既有分数排序，尚未启用RRF。
- 图谱只执行已有的受控策略重排。

## 第二阶段入口

下一阶段只对已审核的 `profile_facts`、`project_context_memories` 和 `agent_memories` 建立向量投影，并实现 `VectorRetriever`。在离线评测达到门槛前，关键词结果继续作为生产主路径。
