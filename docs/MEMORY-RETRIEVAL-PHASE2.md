# 记忆检索优化第二阶段：已审核长期记忆向量化

## 范围

本阶段只向量化通过管理员审核后发布的长期记忆：

- `profile_facts`
- `project_context_memories`
- `agent_memories`

未审核候选记忆、原始对话和短期记忆不进入向量库。SQLite 仍是记忆事实的权威数据源，pgvector 是可重建的检索投影。

## 写入链路

1. 管理员批准 `memory_candidate`。
2. 业务事务同时发布权威记忆、图谱 Outbox 事件和 `memory_vector_index_jobs` 任务。
3. Command Center Worker 以带租约的任务队列生成 Embedding，再 upsert 到 pgvector。
4. 失败任务指数退避，最多尝试 8 次；向量服务未启用时任务保留为 pending，不影响记忆发布。
5. `enqueue_approved_memories()` 可对历史已审核记忆进行幂等回填。
6. 已审核用户事实被归档时，同一事务会入队 `delete` 投影任务，防止旧向量形成“幽灵记忆”。

## 读取链路

Context Pack 同时执行原有词法检索和已审核记忆的向量检索。向量查询在数据库层强制应用 `user_id`、`project_id` 和 `agent_id` 边界。同一 `source_ref` 同时被词法和向量通道命中时只输出一条上下文，但保留两个通道的分数与命中证据。

任何 Embedding 或 pgvector 故障只会将 `retrieval_health.vector_memory.status` 置为 `degraded`，Context Pack 会继续使用结构化、词法、图谱和知识库通道。

## 配置

```bash
MEMORY_VECTOR_ENABLED=true
MEMORY_VECTOR_DATABASE_URL=postgresql://user:password@host:5432/database
MEMORY_EMBEDDING_HOST=http://192.168.1.5:11434
MEMORY_EMBEDDING_MODEL=nomic-embed-text:v1.5
MEMORY_EMBEDDING_DIM=768
```

`MEMORY_VECTOR_DATABASE_URL` 未设置时，如果 `DATABASE_URL` 是 PostgreSQL，会复用它。数据库账号需允许使用 `vector` 扩展。`approved_memory_vectors` 由 Alembic 迁移 `20260916_memory_vector` 显式创建；运行时 DDL 默认关闭，仅可在临时兼容旧环境时设置 `MEMORY_VECTOR_RUNTIME_DDL_ENABLED=true`。

## 验收标准

- 只有已审核记忆生成向量任务。
- 审核发布与向量任务入队处于同一 SQLite 事务。
- 重复任务不会重复建立同一内容版本。
- 向量库故障不会阻断 Context Pack。
- Context Pack 可审计每条候选的 lexical/vector 分数和最终分数。
