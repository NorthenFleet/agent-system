# 受控知识检索评测

`sb3-engineering-v1.json` 是固定的合成工程集：30 份来源（25 中文、5 英文），30 个有答案查询、10 个无答案查询、8 个矛盾查询和 2 个撤回/时效查询。它用于结构回归，**不是人工金标**，不得据此开放正式上下文注入。

运行 `scripts/evaluate_knowledge_retrieval.py --output <报告路径>`，需显式的一次性 PostgreSQL `KNOWLEDGE_TEST_DATABASE_URL`（库名包含 `test`）。脚本创建随机 schema、显式迁移 v1/v2/v3/v4、写入 fixture 审批，运行后清理全部 schema 和原始附件副本，不访问正式库，不改开关。

报告分别计算：有答案查询的来源 Recall@10、10 个无答案问题的拒答率、逐条固定引用解析/哈希一致率、仅 query 方法时延 p95，以及矛盾/撤回逐例结果。时效负例允许返回仍有效的相关来源，但禁止已撤回来源重新出现。引用可解析不表示语义忠实。脚本始终设置 `g_sb3_passed=false`，即使调用者把数据声明为 human_reviewed。

正式金标需由真实用户选择至少 30 份授权来源，人工独立标注至少 50 个查询，中文不少于一半；开发与独立验证集分离。每个 query 增加以下人工记录（不要填写真实凭证或私密正文到仓库）：

```json
{
  "review_status": "pending",
  "split": "validation",
  "query_id": "真实查询的稳定标识",
  "expected_source_version_refs": [],
  "expected_span_refs": [],
  "answerability": "answerable|unanswerable|conflict|temporal",
  "faithfulness_labels": [],
  "major_factual_error": null,
  "reviewed_by": "",
  "reviewed_at": null
}
```

正式退出门禁还需：人工语义忠实率 ≥95%、重大事实错误为 0、Recall@10 ≥90%、无依据拒答率 ≥95%、安全负例全过、真实项目 shadow 对比与 1000 页规模性能记录。现有规则不会自动把评测报告转为批准或切流。当前知识向量保持关闭；先证明词法/关系检索在真实独立集中的缺口，再考虑单独的向量命名空间。
