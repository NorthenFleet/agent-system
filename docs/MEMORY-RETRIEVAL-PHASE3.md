# 记忆检索优化第三阶段：混合融合与策略重排

## 目标

第二阶段已具备结构化、词法、向量和图谱四路召回，但不同通道的原始分数不在同一标尺上。本阶段用通道内排名而非原始分数进行融合，并保留可审计、可回滚的排序证据。

## 排序流程

1. 各检索通道独立生成候选集和通道内排名。
2. 图谱冲突治理先压制与权威记忆冲突的陈旧投影。
3. 按 `source_ref` 去重，同一记忆的多通道命中被合并。
4. 执行 Weighted Reciprocal Rank Fusion：

   ```text
   rrf = Σ channel_weight / (60 + channel_rank)
   ```

5. RRF 归一化后与以下有界特征组合：

   - RRF 相关性：50%
   - 通道最佳原始分：20%
   - 来源权威性：15%
   - 置信度：10%
   - 记忆重要度：5%

默认通道权重为：`structured=1.25`、`lexical=1.0`、`vector=1.1`、`graph=0.75`。图谱用于扩展关系上下文，不应只凭不可比较的原始高分超越已审核权威记忆。

## 可审计证据

每个 Context Pack 条目的 `metadata.retrieval.fusion` 保存：

- 每个通道的排名与 RRF 贡献。
- RRF 归一化分。
- 融合前最佳原始分。
- 权威性、置信度和重要度特征。
- 最终分数和排序策略版本。

`retrieval_health.hybrid_fusion.comparison` 保存旧排序与 RRF 排序的 Top-K 重合率、Top-1 变化和平均位移。

## 上线模式

```bash
# 保持旧的原始分排序
MEMORY_HYBRID_FUSION_MODE=baseline

# 继续输出旧排序，但计算并记录 RRF 对比
MEMORY_HYBRID_FUSION_MODE=shadow

# 正式输出 RRF + 策略重排
MEMORY_HYBRID_FUSION_MODE=weighted_rrf
```

当前默认为 `weighted_rrf`。紧急回滚只需将配置改为 `baseline` 并重启后端，不需要改变记忆数据或向量索引。

## 评估门禁

评估集位于 `backend/evals/memory_retrieval_phase3.json`，指标包括：

- Hit Rate / Recall@K
- Item Recall@K
- MRR@K
- NDCG@K
- Forbidden Hits

候选排序只有在以下条件全部满足时才能通过门禁：越权/过期记忆命中不增加、Recall 不下降、MRR 下降不超过 0.02。

## 本阶段边界

本阶段不引入在线 LLM 或 Cross-Encoder 重排，避免将网络延迟、额外费用和不稳定性带入 Context Pack 主路径。后续可在离线评估达标后，以可选重排器接口进行灰度。
