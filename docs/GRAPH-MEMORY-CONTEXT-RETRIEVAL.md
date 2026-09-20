# 图谱记忆上下文检索契约（第一阶段）

## 目的

3021 在创建规划或执行 Context Pack 时，可将图谱记忆作为只读的关系扩展来源。图谱不是长期事实主库：只有已审核记忆的图谱投影可以进入上下文，正式事实仍以统一数据库中的 `profile_facts`、`project_context_memories` 与 `agent_memories` 为准。

## 网关接口

```http
POST /graph-memory/v1/retrieve-context
```

请求体：

```json
{
  "user_id": "1",
  "project_id": "project-123",
  "agent_id": "optimus",
  "mission_id": "mission-123",
  "query": "审批与任务规划约束",
  "limit": 8,
  "include_neighbors": true,
  "allowed_scopes": ["profile", "project", "agent"],
  "include_unreviewed": false
}
```

服务端必须以已认证的服务身份为准，而非只信任请求体：校验租户/用户、项目、智能体和可见性边界。`include_unreviewed` 必须保持为 `false`；未审核会话线索不能进入此接口的结果。

## 签名

请求使用与现有 Graph Memory 桥接相同的 HMAC-SHA256 密钥，并要求以下请求头：

```text
X-GM-Timestamp
X-GM-Nonce
X-GM-Request-Id
X-GM-Actor-Id
X-GM-Actor-Role: service
X-GM-Permissions: memory.retrieve.context
X-GM-Body-SHA256
X-GM-Signature
```

签名原文按换行拼接：

```text
POST
/graph-memory/v1/retrieve-context
{timestamp}
{nonce}
{request_id}
{actor_id}
service
memory.retrieve.context
{sha256(request_body)}
```

网关应校验时间窗口、nonce 重放、服务角色、权限、请求体摘要和签名。密钥文件权限必须为 `0600`。

## 响应

```json
{
  "retrieval_mode": "hybrid",
  "items": [
    {
      "node_id": "node-approval",
      "source_ref": "project-memory:project-memory-abc",
      "title": "计划须经批准",
      "content": "任务计划须由用户批准后执行。",
      "authority": "approved_projection",
      "visibility": "project",
      "owner_user_id": "1",
      "project_id": "project-123",
      "score": 0.92,
      "confidence": 0.95,
      "freshness_score": 0.80,
      "relation_relevance": 0.90,
      "freshness_at": "2026-09-16T00:00:00Z",
      "evidence_refs": ["mission:mission-123"],
      "relations": [
        {"type": "APPLIES_TO", "label": "任务规划"}
      ]
    }
  ]
}
```

3021 客户端会再次丢弃以下结果：

- `authority` 不是 `approved_memory` 或 `approved_projection`；
- 缺少 `source_ref` 或正文；
- `owner_user_id` 不匹配；
- 项目级节点的 `project_id` 不匹配；
- `visibility` 不属于 `private`、`profile`、`project`、`agent`。

## 运行配置

```text
GRAPH_MEMORY_CONTEXT_ENABLED=true
GRAPH_MEMORY_CONTEXT_GATEWAY_URL=http://127.0.0.1:18789
GRAPH_MEMORY_CONTEXT_SECRET_PATH=~/.openclaw/graph-memory-bridge.key
GRAPH_MEMORY_CONTEXT_RETRIEVAL_PATH=/graph-memory/v1/retrieve-context
GRAPH_MEMORY_CONTEXT_TIMEOUT=1.2
GRAPH_MEMORY_CONTEXT_ACTOR_ID=3021-context
GRAPH_MEMORY_CONTEXT_ACTOR_ROLE=service
```

当网关、凭证或响应不可用时，3021 将 `graph_memory` 标记为 `degraded`，保留其他来源继续生成 Context Pack；不会阻断规划和执行。

## 第二阶段：审核记忆投影

管理员审核发布长期记忆时，3021 会在同一个 SQLite 事务内写入
`memory_graph_outbox`。因此正式记忆发布不会依赖图谱网关在线；后台命令中心 worker
用租约领取事件、指数退避重试，最多 8 次后进入 `dead_letter`。

```http
POST /graph-memory/v1/upsert-projection
```

该接口使用同一签名格式，但权限必须为 `memory.write.projection`。请求体包含：

```json
{
  "event_id": "graph-event-...",
  "event_type": "memory.published",
  "aggregate_type": "project_memory",
  "aggregate_id": "project-memory-...",
  "source_ref": "project-memory:project-memory-...",
  "user_id": "1",
  "project_id": "project-123",
  "agent_id": "optimus",
  "memory_key": "decision.approval_gate",
  "memory_type": "decision",
  "title": "审批执行约束",
  "content": "项目计划必须在用户批准后执行。",
  "importance": "critical",
  "confidence": 0.97,
  "visibility": "project",
  "status": "active",
  "evidence_refs": ["step-approval"]
}
```

网关必须按 `event_id` 幂等处理，并返回 `accepted`、`upserted` 或
`already_applied` 之一。它应将 `source_ref` 作为可回溯的规范引用，并且不得把该接口
用于写入未审核会话内容。

## 第三阶段：关系扩展与冲突治理

上下文检索请求固定为 `max_hops: 1`，并仅允许以下关系类型。3021 使用本地固定权重，
不信任网关返回的任意权重：

| 关系 | 权重 |
| --- | ---: |
| `CONSTRAINS` | 1.00 |
| `APPLIES_TO` | 0.95 |
| `SUPPORTED_BY` | 0.90 |
| `DERIVED_FROM` | 0.85 |
| `SUPERSEDES` | 0.80 |
| `RELATED_TO` | 0.65 |

图谱节点可额外返回 `memory_key`、`version`、`supersedes_ref` 和 `valid_until`。
`valid_until` 过期、没有时区或格式无效的节点会在 3021 客户端被拒绝。审核记忆投影会
携带计划版本，方便网关建立版本链。

在写入 Context Pack 前，3021 以 `(visibility, memory_key)` 比对图谱节点与已审核的
规范记忆。正文不一致时，规范记忆优先，冲突的图谱节点不会注入提示词；冲突的来源引用
和压制动作会写入该 Context Pack 的 `retrieval_health.graph_memory.conflict_actions`，
可用于后续人工核查与图谱修复。

## 第四阶段：离线质量评估

管理员可调用：

```http
POST /api/v3/context/evaluations/graph-memory
```

评测会在不写入普通 Context Pack 的前提下，对同一组查询运行三个模式：

- `disabled`：不使用图谱记忆；
- `retrieval`：直接使用图谱语义分数；
- `rerank`：使用关系、可信度与时效性重排。

每个样例可以提供期望引用、禁止引用，以及来自真实任务验收的各模式完成结果。评测报告
输出并可持久化以下指标：命中率、错误引用率、平均估算上下文 token、任务完成率、图谱
降级次数和冲突数。它不调用智能体执行任务；任务完成率仅汇总已提供的验收标签，避免把
离线检索评测伪装成端到端任务实验。

## 第五阶段：灰度与运维治理

图谱模式可由管理员按用户默认值或项目覆盖配置：

```http
PUT /api/v3/context/graph-memory/rollout
{"graph_mode":"disabled|retrieval|rerank","project_id":"可选"}
```

优先级为“项目覆盖 → 用户默认 → `GRAPH_MEMORY_DEFAULT_MODE` 环境变量 → `rerank`”。
普通任务检索会自动使用解析后的模式；评测请求始终显式指定模式，不受灰度配置影响。

管理员可通过以下接口查看运行状态：

```http
GET /api/v3/context/graph-memory/operations?project_id=可选
```

状态包含投影 Outbox 的待处理/重试/已投递/死信数量，近 24 小时图谱检索降级率、冲突数、
图谱召回数、最新评测摘要和配置列表。死信为 critical；积压、降级率超过 20% 或存在冲突为
warning。该接口不返回图谱正文、原始会话或密钥。
