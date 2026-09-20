# 记忆检索稳定化检查点

## 结论

2026-09-16 已完成语义记忆灰度后的第一个稳定化检查点。当前定位仍为受控 Beta / Shadow，不切换到 `weighted_rrf` 服务排序。

## 已完成的工程收敛

1. Embedding 模型从可变标签 `nomic-embed-text:latest` 固定为 `nomic-embed-text:v1.5`，维度保持 768。
2. 向量任务幂等边界升级到 `approved-memory-vector.v2`，幂等键包含模型和维度，模型切换可触发重新索引。
3. PostgreSQL 投影表纳入 Alembic 迁移 `20260916_memory_vector`，数据库已升级到该 Head。
4. 运行时 DDL 默认关闭；投影表未迁移时显式报错，预检也会阻止向量灰度就绪判定。
5. 新增 `memory_vector_index_attempts` 尝试审计表。每次处理保留独立的成功、失败、租约过期或租约丢失记录，主任务成功后不再丢失先前错误。
6. 语义检索定位为可降级增强：`MEMORY_VECTOR_PREFLIGHT_REQUIRED=false`，基础设施失效时保留结构化和词法检索可用性。

## 环境验收基线

- PostgreSQL: 17.10
- pgvector: 0.8.6
- Alembic Head: `20260916_memory_vector`
- Embedding: `nomic-embed-text:v1.5`, 768 维
- 权威已审核记忆: 9
- pgvector 投影: 9
- 缺失 / 孤儿 / 哈希漂移 / 模型错误: 0 / 0 / 0 / 0
- 模型切换回填任务: 9 成功，0 重试，0 死信
- 尝试审计: 9 成功，0 错误
- 真实 Shadow 查询: 3 条向量候选，177.76ms，服务排序仍为 `score-sort-baseline`
- 相关记忆回归: 52 passed

## 已知边界

- 尝试审计从本检查点开始记录；上线前已被 `last_error=NULL` 覆盖的那次历史瞬时失败无法追溯还原。
- 当前样本仅 9 条记忆，不足以证明排序质量。
- 工作区包含多条未提交功能线；本阶段未擅自创建 Git 提交，避免将用户的其他改动卷入回滚点。
- Context Pack 的 TTL、清理、内容最小化和审计保留策略仍未闭环。

## 下一阶段入口

Shadow 指标持久化与聚合已在第五阶段完成。当前进入样本收集期：最低验收样本为 100 次真实查询和 30 条标注用例，并持续核验禁止越权命中、可用率、P95 延迟、Top-1 变化、Top-K 重合率、MRR 和召回率。详见 `docs/MEMORY-RETRIEVAL-PHASE5-SHADOW-METRICS.md`。
