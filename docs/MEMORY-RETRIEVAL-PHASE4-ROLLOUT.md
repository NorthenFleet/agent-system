# 记忆检索第四阶段：生产灰度与验收

## 第 1 步：上线前置检查（已完成）

2026-09-16 对当前运行环境进行了只读检查：

- PostgreSQL 17.10 正在运行，数据库为 `team_dashboard`。
- Ollama 在 `http://127.0.0.1:11434` 正在运行；原默认地址 `http://192.168.1.5:11434` 当前超时，上线配置应显式使用本机地址。
- `nomic-embed-text:latest` 与 `nomic-embed-text:v1.5` 已安装；生产配置已固定为 `nomic-embed-text:v1.5`，实际 Embedding 探测为 768 维，与索引配置一致。
- PostgreSQL 当前没有可用或已安装的 `vector` 扩展，因此尚不能启用向量索引。
- 根目录 `.env` 尚未配置记忆向量参数，系统仍保持安全的未启用状态。
- 向量索引队列可读且当前为 0 条，未发现历史失败任务。

本步新增了只读预检工具：

```bash
backend/venv/bin/python backend/scripts/memory_vector_preflight.py \
  --probe-embedding
```

严格验收基础设施：

```bash
backend/venv/bin/python backend/scripts/memory_vector_preflight.py \
  --probe-embedding --require-infrastructure
```

工具仅执行只读检查，不创建扩展、不建表、不修改队列，输出不包含数据库密码。

`start.sh` 在 `MEMORY_VECTOR_ENABLED=true` 时会自动运行预检。默认预检失败时继续启动且降级到原有检索通道；设置 `MEMORY_VECTOR_PREFLIGHT_REQUIRED=true` 可改为严格阻断启动。

## 第 2 步：pgvector 安装与验收（已完成）

2026-09-16 已完成：

- 通过 Homebrew 安装 `pgvector 0.8.6`，与当前 PostgreSQL 17 配套。
- 在 `team_dashboard` 数据库中幂等创建 `vector` 扩展。
- 使用临时表验证 `vector(768)` 类型，临时数据已回滚。
- 平行向量余弦距离为 `0.000000`，正交向量为 `1.000000`。
- 严格预检结果 `infrastructure_ready=true`。
- 尚未创建 `approved_memory_vectors` 投影表；该表将在下一步启用服务时幂等创建。

其他环境可使用以下命令重复数据库操作：

```bash
psql -d team_dashboard -f backend/scripts/setup_memory_vector_postgres.sql
```

## 第 3 步：Shadow 启用与空投影验收（已完成）

2026-09-16 已完成：

- 配置 `MEMORY_VECTOR_ENABLED=true`。
- 配置 `MEMORY_VECTOR_PREFLIGHT_REQUIRED=true`，基础设施失效时阻止带病启动。
- 配置 `MEMORY_EMBEDDING_HOST=http://127.0.0.1:11434`。
- 配置 `MEMORY_HYBRID_FUSION_MODE=shadow`，继续输出基线排序，只记录 RRF 对比。
- 严格预检结果 `ready_for_vector_rollout=true`，无阻塞项。
- 显式初始化 `approved_memory_vectors`，字段类型为 `vector(768)`。
- 投影表当前为 0 条，未执行历史记忆回填。
- 3021 后端已重启，根路由与 OpenAPI 可用。
- 使用隔离用户作用域执行零结果向量查询，链路状态为 `ready`，实测延迟 88.37ms。

投影表初始化命令：

```bash
backend/venv/bin/python backend/scripts/initialize_memory_vector_projection.py
```

## 第 4 步：历史记忆回填与一致性核验（已完成）

2026-09-16 已完成：

- 扫描 9 条已审核活跃记忆：用户事实 2 条、项目记忆 4 条、智能体记忆 3 条。
- 9 条任务全部完成，队列 `pending=0`、`processing=0`、`dead_letter=0`。
- 其中 1 条曾发生一次瞬时重试，第二次成功，未留下错误或死信。
- PostgreSQL 投影为 9 条，与 SQLite 权威记忆数一致。
- 缺失、孤儿、内容哈希漂移、模型/维度错误均为 0。
- 重复执行回填后任务仍为 9 条、投影仍为 9 条，没有重复写入，幂等性通过。
- 真实 Shadow 查询召回 3 条向量候选，向量通道延迟 122.2ms。
- Context Pack 仍使用 `score-sort-baseline`输出，同时生成 `weighted-rrf.v1` 对比，检测到 3 个多通道候选。

可重复回填与对账命令：

```bash
backend/venv/bin/python backend/scripts/backfill_memory_vectors.py \
  --max-wait-seconds 120 --batch-size 20
```

命令会在以下任一情况下返回非零状态：队列未清空、存在死信、缺失投影、孤儿投影、内容哈希不一致或模型维度错误。

## 后续执行顺序

1. 连续收集 Shadow 检索事件与新旧排序差异。
2. 建立可查询的灰度指标汇总，包括延迟、降级率、Top-1 变化和 Top-K 重合率。
3. 观察 3–7 天，通过评估门禁后切换为 `weighted_rrf`。

## 稳定化检查点（已完成）

2026-09-16 已完成模型版本固定、显式数据库迁移、可降级启动策略和不可覆盖的重试审计。详见 `docs/MEMORY-RETRIEVAL-STABILIZATION-CHECKPOINT.md`。
