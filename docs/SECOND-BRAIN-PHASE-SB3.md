# 第二大脑 SB3：引用检索与 Context Pack shadow

**日期**：2026-10-06（Asia/Shanghai）  
**所属方案**：[SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)；前序：[SB2](SECOND-BRAIN-PHASE-SB2.md)  
**状态**：SB3 核心工程、隔离检索评测与界面验证完成。G-SB3 的真实人工金标、独立验证集、正式项目观察和 1,000 页性能门槛未验收；正式知识上下文注入保持关闭。本记录完成时 SB4 未实施，后续进展见 [SB4 实施记录](SECOND-BRAIN-PHASE-SB4.md)。

## 1. 本批交付

| 能力 | 行为 |
| --- | --- |
| 受控检索 | `kb-retrieval-v2` 词法、中文片段、别名及已审核关系的一跳扩展；先限定用户/项目/空间，再读取证据 |
| 矛盾展示 | 返回 `conflicts`，保留双方固定引用、理由和旧修订提示；前端可打开双方知识页，不自动裁决 |
| 引用解析 | 核对当前可用页、固定修订 ID、页面/片段哈希、原始来源字节哈希、项目范围和完整页面来源依赖 |
| 独立 shadow 快照 | PostgreSQL `kb_context_snapshots` 固定条目、来源和引用；1 小时有效期；记录基线引用顺序哈希、知识候选数与预算 |
| Context Pack 对照 | 在原有记忆融合、排序、截选完成后观察；原 Pack 仅增加脱敏健康信息和快照 ID，不存新知识正文 |
| 执行边界 | 新知识不加入旧 `items`，不写旧 `context_pack_items`，不进入 Memory Effect 引用；执行渲染器拒绝被误复制进去的 `reviewed_knowledge` / `kb-page:` 条目 |
| 前端 | 知识页新增“上下文对照”：只读预览、保存快照、预算提示、原文核对、重新校验；失效时清除旧正文 |
| 工程评测 | 固定 30 来源 / 50 查询语料及可复现脚本；记录修复前后结果；保留真实人工金标规范 |

新知识向量未启用。当前没有真实独立集证明向量可以改善既有检索缺口，因此不增加向量存储、不写 `approved_memory_vectors`，也不修改原记忆 RRF、Graph Memory 或其 rollout 配置。

## 2. 作用域、版本和预算

### 2.1 明确的项目绑定

自动 shadow 仅在以下条件满足时运行：

```text
SECOND_BRAIN_ENABLED=true
SECOND_BRAIN_CONTEXT_MODE=shadow
SECOND_BRAIN_CONTEXT_SPACES={"实际项目ID":["实际空间ID"]}
```

本批每个项目只配置一个空间，不自动混合个人空间或多个项目。运行时将调用方实际 user_id 与 PG 空间 owner/project 再次匹配；配置表只负责选择空间，不能授予权限。没有匹配配置时记录 `not_configured`，不遍历全部知识空间。

自动保存观察还要求 `SECOND_BRAIN_WRITE_ENABLED=true`。只读 UI 预览不写快照；保存快照要求管理员及写开关。正文读取、引用解析和保存后的重读均按登录主体授权。

### 2.2 固定知识条目

每条记录至少含：`item_type=knowledge`、`authority=reviewed_knowledge`、space/project、page ID、revision、page_revision_id、content_hash、block ID、固定内容和认识状态、`source_version_refs`、来源哈希、`evidence_refs`、片段哈希及定位、access_epoch、relation_path 和检索策略版本。

来源版本引用实际采用 `kb-source-version:<version-id>`，片段采用 `kb-span:<span-id>`，页引用采用 `kb-page:<page-id>@<revision>`；它们不混入仅支持 memory 前缀的既有引用接口。快照独立保存 `knowledge_refs`，旧引用排序只保留摘要哈希用于对照。

读取快照时重新校验：

- actor、project、space 和项目授权仍匹配；个人无项目空间不可作为默认背景。
- 快照没有过期，内容哈希未漂移，空间访问 epoch 未变化。
- 页面仍 active 且是创建时修订；改名、编辑、合并后旧快照需重新生成。
- 页面完整来源依赖仍有效，不仅检查当前摘录关联的一个片段；原始文件、片段和页面哈希都一致。
- 通过关系扩展加入的条目，需要两端固定修订、关系和相关来源依赖再次有效。

来源撤回、授权变化、修订更新或篡改均拒绝返回旧正文。快照不可变不等于永久授权。1 小时 TTL 控制 API 可读期，不代表物理清除；保留/清除运维属于后续阶段。

### 2.3 保留既有上下文

预算以 Unicode 字符计，不宣称是模型 token。新知识预算为：

```text
max(0, min(总字符预算 × 25%, 总字符预算 − 已有背景占用))
```

计算知识占用包含条目序列化后的正文、引用和元数据；整块加入，超预算跳过，不截掉来源或静默挤出旧背景。最多 5 个知识条目。

自动 shadow 使用 12,000 字符的比较窗口，并按旧条目正文、标题及逐项开销估算已有占用。UI 可显式设置总预算及已有占用。**这只是 shadow 对照预算，不表示已有执行器的真实 token 预算已经接入**；正式注入前还需要按规划/执行各自窗口固定实际预算。

## 3. 接入与失败行为

`ContextRetrievalService.retrieve` 在原有 `selected`、summary、content_hash、retrieval_strategy 和 retrieval_decision 已产生后调用 shadow observer。它不修改这些字段，不参与 `rank_hybrid_items`。

- disabled：不调用知识权威，不新增观察字段，原行为保持。
- shadow：可产生独立 PG 快照；Pack 的 `retrieval_health.reviewed_knowledge_shadow` 只保存数量、预算、哈希、模式、是否注入和快照 ID。
- PG 不可用、范围不匹配或配置错误：只记录脱敏的不可用原因，原 Pack 仍返回；不记录 DSN、原文或异常堆栈到该字段。
- configured enabled：返回 `quality_gate_not_approved`，不会绕过 shadow 自动注入。执行渲染器另有拒绝门禁，防止误把 shadow 条目复制成正式条目。

PG 快照和旧 SQLite Context Pack 不宣称跨库原子提交。先创建快照、随后旧 Pack 持久化失败时，可能留下未绑定观察记录；该记录仍受独立授权、TTL 和审计控制，不能被执行器消费。没有将旧记忆库迁移到 PG。

## 4. 检索修复与评测

### 4.1 去重不能丢掉矛盾

首轮固定工程集有 4 个矛盾用例失败：相同来源摘录同时出现在来源页和概念页，文本去重保留来源页时可能丢掉概念页的关系。

已修复为：同分优先保留概念等知识页；同时保留等价摘录对应的全部页 ID 作为关系查找起点。去重后仍有矛盾线索，关系扩展继续验证空间、当前修订及来源状态。修复前后的语料版本和哈希相同。

### 4.2 实测结果与适用范围

| 检查 | 本批结果 |
| --- | --- |
| 后端回归 | 101 项通过：含旧 60 项、shadow/引用/权限/恢复及 20 条注入负例 |
| 前端组件 | 19 项通过：入库/审核 7、维护 6、上下文 6 |
| TypeScript / Vite 生产构建 | 通过；已有大 chunk 警告仍在 |
| 数据库迁移 | 单一 head：`20261006_knowledge_context` |
| 工程语料 | 30 份合成来源（25 中文、5 英文），生成 60 页 |
| 查询集 | 30 有答案、10 无答案、8 矛盾、2 撤回/时效，共 50 项通过 |
| 来源 Recall@10 | 工程集 100% |
| 无答案拒答率 | 工程集 10/10 |
| 固定引用解析/哈希一致 | 59/59，100% |
| query p95 | 87.49 ms；本机隔离 PG、60 页工程集，仅 query 调用，非 1,000 页端到端性能门槛 |
| 原记忆行为 | 实际 ContextRetrievalService 对照确认 items、顺序、content_hash、检索策略、执行提示词一致；知识权威故障时仍保留基线 |
| 浏览器 | Chrome 隔离真实组件；保存状态、预算、推论与引用可见；390×844 无横向溢出；撤回失败后清除旧内容 |

工程集不替代真实人工金标：尚未评价人工语义忠实率、真实任务收益或独立验证集召回；报告明确 `human_reviewed=false`、`g_sb3_passed=false`。20 条注入负例覆盖 5 类要求自动批准/泄露密钥/运行命令/上传私有文件/切换用户的原文，全部只作为资料，未改变发布数量或执行状态。

工程评测没有调用 LLM 或 embedding 服务，没有创建正式审核批准。固定输入和脚本见 [评测说明](../backend/evals/knowledge/README.md)、[语料](../backend/evals/knowledge/sb3-engineering-v1.json)。

## 5. 文件与接口

| 文件 | 作用 |
| --- | --- |
| [retrieval.py](../backend/services/knowledge/retrieval.py) | 作用域检索、去重、矛盾与一跳扩展 |
| [context.py](../backend/services/knowledge/context.py) | 快照、引用解析、读取校验与 shadow observer |
| [ContextRetrievalService](../backend/services/context_retrieval_service.py) | 两处小范围接入：排序后观察、渲染前禁止新知识注入 |
| [context schema](../backend/models/knowledge_context_v3.py) / [迁移](../backend/alembic/versions/20261006_knowledge_context.py) | 独立 PG 快照表及增量迁移 |
| [knowledge_v3.py](../backend/routers/knowledge_v3.py) | 使用现有身份与角色的上下文/引用 API |
| [KnowledgeContextPanel.vue](../frontend-v2/src/components/knowledge/KnowledgeContextPanel.vue) | 对照预览、保存及重新校验 |
| [evaluate_knowledge_retrieval.py](../backend/scripts/evaluate_knowledge_retrieval.py) | 随机测试 schema 中的可复现评测 |

```text
POST /api/v3/knowledge/spaces/{space_id}/context/preview
POST /api/v3/knowledge/spaces/{space_id}/context/snapshots
GET  /api/v3/knowledge/context/snapshots/{snapshot_id}?project_id=...
POST /api/v3/knowledge/spaces/{space_id}/citations/resolve
```

保存请求使用 Idempotency-Key，重放只取已保存 ID 后重新校验，不能从请求缓存返回失效正文。界面在丢失响应时复用键；明确保存成功后再次生成使用新键，支持过期后生成新快照。

## 6. 证据与复现

- [后端测试日志](review/second-brain-sb3-20261006/backend-tests.txt)
- [前端测试日志](review/second-brain-sb3-20261006/frontend-tests.txt) / [构建日志](review/second-brain-sb3-20261006/frontend-build.txt)
- [修复前工程评测](review/second-brain-sb3-20261006/retrieval-before-relation-fix.json)
- [修复后工程评测](review/second-brain-sb3-20261006/retrieval-evaluation.json)
- [桌面截图](review/second-brain-sb3-20261006/context-desktop.png) / [窄屏截图](review/second-brain-sb3-20261006/context-mobile.png) / [撤回后清除](review/second-brain-sb3-20261006/context-invalidated.png)

在 `backend` 注入一次性 `KNOWLEDGE_TEST_DATABASE_URL` 后：

```bash
PYTHONPATH=. venv/bin/python -m pytest --confcutdir=tests/knowledge tests/knowledge -q
PYTHONPATH=. venv/bin/python scripts/evaluate_knowledge_retrieval.py \
  --output ../docs/review/second-brain-sb3-20261006/retrieval-evaluation.json
```

在 `frontend-v2`：

```bash
npm run test:run -- src/test/KnowledgeIntakePanel.spec.ts src/test/KnowledgeMaintenancePanel.spec.ts src/test/KnowledgeContextPanel.spec.ts
npm run build
node scripts/preview-knowledge-maintenance.mjs --context
```

浏览器预览所有 API 都是合成 fixture，不连接正式后端。每个 PG 用例/评测清理随机 schema，原始附件副本随临时目录清理。最终验收后隔离预览服务已退出，临时 PostgreSQL 正常停止（`server stopped`，PID 文件已消失）；验收日志、截图和评测结果保留。

## 7. 试点启用与后续门禁

以下是手册，未对正式环境执行：

1. 确认前序生产预检、备份、来源目录和真实项目权限，显式迁移至 `20261006_knowledge_context`。
2. 选择一个已授权项目/空间，先开启 shadow 配置及必要写开关；不要同时更改 Memory RRF rollout。
3. 在任务 Context Pack 中核对只有 observer 元数据，执行提示词和旧引用集合未增加新知识；用界面检查固定快照及撤回。
4. 按评测说明建立真实来源人工金标与独立验证集，评价语义忠实、拒答、跨空间负例和 1,000 页性能；记录真实项目 shadow 结果。
5. **G-SB3 未通过前不得切为正式注入**。目前即使误设 enabled 也保持阻断；正式注入需要另一个可审阅实现，接入实际执行预算、运行前授权再校验及明确项目 rollout。
6. 回退将 context mode 设为 disabled；停止产生新观察，原知识查询/旧记忆执行保持。保留快照和审计，不做破坏性 downgrade。

下一阶段 SB4 为 Artifact/文档引用导入、Memory Candidate 幂等桥接、周期维护和备份/回退演练。现有真实项目门禁与人工质量验证继续独立跟踪，不能以工程集代替。
