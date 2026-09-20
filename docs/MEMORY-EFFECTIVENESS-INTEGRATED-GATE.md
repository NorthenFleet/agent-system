# 真实记忆效果第三步：统一门禁与克制判定

## 结论

已将真实记忆召回基线、作用域隔离、生命周期和 abstention 合并到同一效果门禁。统一数据集共 85 条用例，85/85 通过，九类必需场景全部覆盖。

自动发布门禁仍保持关闭。这不是因为检索、生命周期或克制判定失败，而是剩下两个独立证据缺口：

1. 80 条真实基线尚未达到人工复核要求；
2. 没有完整 Top-5 相关性标注，Precision@5 仍不可计算。

## 克制判定设计

检索系统现在区分两个概念：

- **一般背景**：用户档案、全局偏好、高优先级约束等，可以存在于 Context Pack；
- **回答依据**：必须与当前查询存在词法重合，或达到经校准的向量/图谱相关性阈值。

Context Pack 新增 `retrieval_decision`：

- `supported`：至少有一条记忆可以支撑当前回答；
- `abstain`：只有一般背景，没有与当前问题相关的已确认记忆。

判定同时记录支持来源、背景来源、最高支持分数和语义阈值。指挥中心渲染提示词时，如果判定为 `abstain`，会明确要求模型说明“记忆依据不足”，禁止把一般背景声称为已记得的答案。

## 统一门禁方法

`memory_effectiveness_integrated_gate.py` 使用 SQLite Backup API 创建生产权威库的临时一致性副本，然后仅在副本中创建更新、冲突、到期、遗忘和 abstention 场景。

受控场景标记为 `verification_method=controlled_fixture`，与人工真值分开计数。因此 5 条机器可验证的受控用例不会被错报为 5 条人工标注。

## 统一结果

| 指标 | 结果 |
| --- | ---: |
| 用例数 | 85 |
| 通过率 | 100% |
| Recall | 100% |
| 重要记忆 Recall | 100% |
| Top-5 命中率 | 100% |
| Abstention 准确率 | 100% |
| False support | 0 |
| 禁止来源命中 | 0 |
| 过期记忆命中 | 0 |
| 删除投影残留 | 0 |
| 跨作用域泄漏 | 0 |
| 检索降级 | 0 |
| 生命周账本违规 | 0/6 |

九类场景为：`recall`、`abstention`、`update`、`conflict`、`expiry`、`forget`、`user_isolation`、`project_isolation` 和 `agent_isolation`。

## 上线冒烟

生产权威记忆上执行了两个只读、不持久化查询：

- 未知主题 `controlled-online-unknown-zephyr-9173`：`abstain`，0 条支持记忆，7 条一般背景；
- 已知主题 `workflow.memory_review_gate`：`supported`，3 条支持记忆。

3021 后端健康检查通过，API worker 与 dedicated worker 均持续上报实时心跳。
记忆、上下文和指挥中心联合回归 174 项通过；系统健康门禁通过，五智能体矩阵 5/5 通过。

## 可重复执行

```bash
backend/venv/bin/python backend/scripts/memory_effectiveness_integrated_gate.py --summary-only
```

固化产物：

- `backend/evals/memory_effectiveness_integrated.json`；
- `docs/MEMORY-EFFECTIVENESS-INTEGRATED-GATE.json`。

## 下一步

当前不应继续扩展检索算法或增加存储层。下一中心工作是人工标注与证据闭环：

1. 从 80 条临时基线中建立可审核批次；
2. 对每条查询标注期望来源、禁止来源和 Top-5 相关性；
3. 只有人工签署的标签计入 `minimum_80_verified_cases`；
4. 可计算 Precision@5 且达到阈值后，再考虑解除自动发布门禁。
