# 记忆检索第五阶段：Shadow 指标持久化与聚合

## 目标

在不改变在线排序结果的前提下，持久化基线排序与 `weighted-rrf.v1` 候选排序的差异指标，并将性能、可用性与样本量转换为可查询的灰度门禁输入。

本阶段不会自动将 `MEMORY_HYBRID_FUSION_MODE` 从 `shadow` 切换到 `weighted_rrf`。

## 数据设计

新增 SQLite 表 `memory_retrieval_shadow_events`，只保存：

- 用户、项目和查询的 SHA-256 指纹；
- 服务排序与候选排序版本；
- 向量通道状态与延迟；
- 整体 Context Pack 延迟和结果数；
- Top-1 是否变化、Top-K 重合率和平均位移；
- 多通道候选数和事件时间。

该表不保存查询正文、记忆内容、基线候选引用或 RRF 候选引用。默认保留 30 天，每次写入时幂等清理过期指标。

`persist=false` 的调试或隐私查询不写入 Context Pack，也不写入 Shadow 指标。

## 汇总接口

```http
GET /api/v3/context/vector-memory/shadow-metrics?window_hours=168
```

该接口仅限管理员，支持 1 小时到 90 天时间窗口，返回：

- 总查询数、不同查询指纹数和距最低样本量的差距；
- 向量可用率及各状态分布；
- 向量与整体延迟的 P50 / P95 / P99；
- Top-1 变化率、平均 Top-K 重合率和平均位移；
- 当前在线观测门禁和离线评测缺口。

## 在线观测门禁

| 指标 | 默认门槛 |
| --- | ---: |
| Shadow 查询数 | 至少 100 |
| 向量通道可用率 | 至少 99% |
| 向量检索 P95 | 不高于 300ms |
| Context Pack 总延迟 P95 | 不高于 800ms |

环境变量：

```bash
MEMORY_SHADOW_METRICS_RETENTION_DAYS=30
MEMORY_SHADOW_MIN_QUERIES=100
MEMORY_SHADOW_VECTOR_AVAILABILITY_TARGET=0.99
MEMORY_SHADOW_VECTOR_P95_MS=300
MEMORY_SHADOW_TOTAL_P95_MS=800
```

## 切流边界

在线门禁全部通过后，`online_observation_passed=true`，但 `promotion_ready` 仍为 false。正式切流还必须完成至少 30 条标注用例，并满足：

- 禁止结果命中为 0；
- Recall 不回退；
- MRR 下降不超过 0.02。

候选排序的 Top-1 变化率和 Top-K 重合率当前只作为诊断指标，不在缺少标注真值时单独决定切流。

离线标注评测和统一切流判定已在第六阶段实现，详见 `docs/MEMORY-RETRIEVAL-PHASE6-LABELED-EVALUATION.md`。
