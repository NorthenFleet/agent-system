# 第二大脑 SB2：知识维护与投影恢复实施记录

**日期**：2026-10-06（Asia/Shanghai）  
**所属方案**：[SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)；前序：[SB0/SB1](SECOND-BRAIN-PHASE-SB0-SB1.md)  
**状态**：SB2 核心工程实现及隔离验证完成；G-SB2 人工质量金标、正式试点和投影时延门槛尚未验收。SB3/SB4 未实施。正式数据库未迁移、生产投影未开启。

> 本记录保留 SB2 交付时点的状态；后续引用检索与 Context Pack shadow 实现见 [SB3 实施记录](SECOND-BRAIN-PHASE-SB3.md)。

## 1. 本批交付

现有知识页“资料入库与审核”内新增“知识维护”。读用户可检查健康、查看修订；管理员可提交维护候选、重放投影。所有接口仍按登录用户、空间、项目授权，写入须显式启用。

| 能力 | 已实现行为 |
| --- | --- |
| 多来源概念更新 | 在维护页选择概念后追加文件，固定目标基础修订；保留旧来源，再生成候选，冲突不覆盖 |
| 改名 | 稳定 page ID 不变；保留旧名为别名并参与查询；历史修订显示当时标题 |
| 段落编辑 | 在保留固定引用的前提下编辑文字，显式标记来源陈述、推论或待核实；生成新候选 |
| 关系与矛盾 | 固定关系两端基础修订、记录理由；支持关联、支持、矛盾、推导等关系；矛盾双方内容保留；审核同时展示目标固定修订及两侧原文 |
| 合并 | 只合并同类型 concept/entity/synthesis 页；目标保留双方段落、引用、别名及有效出向关系；原页退出当前查询，历史及合并目标保留 |
| 审核 | 改名、编辑、关联、合并均复用原有修改集哈希、原文/旧修订对照、批准、单独发布流程；维护按钮不直接发布 |
| 维护检查 | 来源撤回、不可用关联、旧修订关联、人工标记的矛盾、待审核积压 |
| 投影 | 固定发布清单生成 Markdown、index、log、graph-index、manifest；完整校验后原子切换 current.json |
| 恢复 | 租约与 fencing、最多 8 次指数退避及抖动、死信、同 event ID 人工重放、回执丢失后重建 |
| 外部编辑 | 文件/清单/指针/文件集合漂移检测，停在“外部差异待处理”；明确重新生成后保留旧 generation 和旧指针副本 |

维护检查是结构与访问状态检查。系统没有自动判断语义真假，也没有用模型自动裁决矛盾；用户对编辑内容和合并理由负责审核。当前编译器仍是 `extractive-v1`，人工维护候选标记为 `reviewed-proposal-v1`。查询返回“知识页摘录”并保留陈述/推论/待核实标注，不把人工改写后的段落冒充原文。

## 2. 一致性与恢复约束

### 2.1 PostgreSQL 与投影的关系

- v1 知识 schema 冻结不改；新迁移 `20261006_knowledge_projection`（父版本 `20261006_knowledge_domain`）增量创建 `kb_projection_receipts`，记录事件租约、fence、下一重试时间、脱敏错误和完成回执。
- 复用发布事务写入的 `kb_outbox`。原子发布仍只有一个数据库事务，投影失败不会回滚已审核知识，也不重复生成 release。
- 不另建调度系统。现有知识 worker 可消费投影，或由现有调度器单次调用 `run_knowledge_projection.py --once`。入库仍关联 WorkRun，投影执行以 Outbox/租约回执和 audit 为恢复账本。
- `claim` 使用行锁与 `SKIP LOCKED`；处理时再次校验 fence。共同空间行锁串行化发布、撤回和 current 切换，旧 worker 不得迟到覆盖。
- 消费旧发布事件时，若已有更高发布序号，标记 `superseded`；撤回按最新访问 epoch 过滤固定修订，重放旧事件也不能恢复撤回内容。
- current 切换后、数据库回执提交前发生故障时，下一次租约可重建完整 generation 并补回执。文件和 PG 不宣称跨介质原子提交。
- 每代最多 1,000 页、总输出 10 MiB；执行暴露指针前检查 100 秒预算及租约。超过预算明确失败。大库增量物化另行扩展。

### 2.2 文件格式与读取规则

```text
<private-projection-root>/<space-id>/
  generations/g-<uuid>/
    wiki/{sources,concepts,entities,synthesis}/<page-id>.md
    index.md
    log.md
    graph-index.json
    manifest.json
  current.json
  preserved-g-<uuid>.json  # 仅明确重新生成时保留旧指针
```

generation 目录采用独立 UUID，而不是仅发布序号：同一 release 在撤回 epoch 更新、故障恢复、人工重新生成时也需要独立目录，才能保留外部差异。`current.json` 和 manifest 均记录实际 release sequence、access epoch；目录名不承担版本排序。

- 文件 0600、目录 0700，检查所有权、路径和符号链接。投影根必须与来源根、实际旧知识库扫描根分离，避免旧检索绕过审核/撤回读取导出文件。
- frontmatter 包含稳定 ID、修订、标题、别名、来源版本与权威内容哈希；manifest 含实际文件字节哈希；回执锚定 current 指针哈希。
- 文本转义为静态 Markdown，原文脚本、HTML、图片语法不会成为主动内容；不复制原始 PDF/附件。
- 关系图保留稳定页 ID，合并目标按当前可用页解析，同时标注证据目标 ID/修订与当前修订，避免把历史关系静默描述为针对新内容的判断。
- **消费者必须只读取 current 指向的完整 generation**，先检查序号、epoch 和健康状态，不递归扫描全部历史代。当前未将此投影接到旧检索或 Context Pack。
- 撤回后权威 API 立即拒绝相关内容，当前投影异步更新。已离线复制的文件和本机历史 generation 不具备远程撤销能力；它们保存在私有目录中，本批不自动删除人工差异或历史文件。启用 Obsidian/其他消费者前须落实此边界，不能把整个根目录当实时授权知识库。

### 2.3 维护的修订规则

维护请求包含 `base_revision`，关系/合并另含 `target_revision`。相同幂等键不同请求返回 409。关系目标范围和证据状态在候选创建、批准、发布时重新检查。普通修订继承原出向关系；合并将有效出向关系作为可审阅操作转移到目标；无效旧目标阻止合并并提示复核。

合并不是物理删除。原页变为 `superseded`，可按明确历史修订查看；原始来源撤回仍会阻断相关历史读取。关系移除、合并撤销和矛盾裁决的专用产品流程尚未提供，不能通过修改历史记录实现。

## 3. 文件落点

| 文件 | 用途 |
| --- | --- |
| [maintenance.py](../backend/services/knowledge/maintenance.py) | 维护候选与结构检查 |
| [projection.py](../backend/services/knowledge/projection.py) | 完整代导出、对账、漂移保留、租约与恢复 |
| [contracts.py](../backend/services/knowledge/contracts.py) | 向后兼容的可选别名/合并目标/关系目标及维护契约 |
| [service.py](../backend/services/knowledge/service.py) | 修订历史、审核发布、关系继承、别名检索 |
| [knowledge_projection_v2.py](../backend/models/knowledge_projection_v2.py) | 独立投影回执元数据 |
| [迁移](../backend/alembic/versions/20261006_knowledge_projection.py) | 增量表及外键 |
| [knowledge_v3.py](../backend/routers/knowledge_v3.py) | 维护、历史、投影健康、重放 API |
| [KnowledgeMaintenancePanel.vue](../frontend-v2/src/components/knowledge/KnowledgeMaintenancePanel.vue) | 维护与投影操作界面 |
| [run_knowledge_projection.py](../backend/scripts/run_knowledge_projection.py) | 现有调度器可调用的单步入口 |
| [knowledge_preflight.py](../backend/scripts/knowledge_preflight.py) | 增加投影 schema/私有目录/旧扫描隔离检查 |
| [隔离 UI 预览](../frontend-v2/scripts/preview-knowledge-maintenance.mjs) | 实际 Vue 组件 + 合成 API，无正式写入 |

新增接口：

```text
POST /api/v3/knowledge/spaces/{space_id}/maintenance/candidates
GET  /api/v3/knowledge/spaces/{space_id}/maintenance
GET  /api/v3/knowledge/pages/{page_id}/history
GET  /api/v3/knowledge/spaces/{space_id}/projection
POST /api/v3/knowledge/spaces/{space_id}/projection/{event_id}/replay
```

重放请求为 `{ "regenerate": false }`；只有明确重新生成操作发送 `true`。启用写入不会自动批准维护候选。

## 4. 验证证据与边界

| 验证 | 结果 |
| --- | --- |
| 隔离 PostgreSQL + API 回归 | 60 项通过（原 40 项 + 本阶段 20 项） |
| 前端组件 | 13 项通过（入库/审核 7 项 + 维护 6 项） |
| TypeScript / Vite 生产构建 | 通过；既有大 chunk 提示仍在 |
| Alembic head | `20261006_knowledge_projection`，单一 head |
| 30 来源工程样例 | 生成 60 页；当前投影和固定修订一致，引用有来源及定位，维护检查无未解释差异 |
| 崩溃恢复 | current 切换后注入回执提交失败，重试恢复且 release 不重复 |
| 并发与乱序 | 同一事件一次有效领取；旧 fence 拒绝；旧 release 不倒退；撤回后重放不恢复内容 |
| 漂移与死信 | 外部编辑原字节保留；明确重新生成切换新代；8 次失败后死信；同事件可重放 |
| 浏览器界面 | Chrome 隔离样例完成改名候选；390 × 844 窄屏关系操作可用，文档宽度等于视口宽度，无横向溢出 |
| 正式服务联调 / 人工金标 / p95 时延 | 未执行，不宣称 G-SB2 已通过 |

30 来源为确定性中文工程样例，不是人工标注的真实来源质量金标。测试证明引用、结构及恢复边界，不证明 ≥95% 语义忠实率、真实资料自动理解或投影 p95 ≤60 秒。浏览器使用真实组件与合成接口，不等同于正式鉴权和线上端到端验收。

证据：

- [后端测试日志](review/second-brain-sb2-20261006/backend-tests.txt)
- [前端测试日志](review/second-brain-sb2-20261006/frontend-tests.txt)
- [构建日志](review/second-brain-sb2-20261006/frontend-build.txt)
- [桌面验收截图](review/second-brain-sb2-20261006/maintenance-desktop.png)
- [窄屏健康视图](review/second-brain-sb2-20261006/maintenance-mobile.png)
- [窄屏维护表单](review/second-brain-sb2-20261006/maintenance-mobile-form.png)

复现：在 `backend` 设置一次性 `KNOWLEDGE_TEST_DATABASE_URL`（库名含 `test`），执行：

```bash
PYTHONPATH=. venv/bin/python -m pytest --confcutdir=tests/knowledge tests/knowledge -q
```

在 `frontend-v2` 执行：

```bash
npm run test:run -- src/test/KnowledgeIntakePanel.spec.ts src/test/KnowledgeMaintenancePanel.spec.ts
npm run build
node scripts/preview-knowledge-maintenance.mjs
```

预览仅监听 `127.0.0.1:55142`，使用合成数据；退出后关闭预览服务。本阶段继续使用 `/tmp/agent-system-sb-pg/data` 中的独立测试实例，每个后端用例清理随机 schema。最终验证后临时 PostgreSQL 已正常停止（`server stopped`，PID 文件已消失），隔离预览服务也已退出；测试数据目录与验收证据保留。

## 5. 启用与回退

本节为部署手册，未操作正式服务。

1. 完成 SB1 的生产连接、鉴权和来源目录预检；记录正式迁移链、备份与首批空间。
2. 显式迁移到 `20261006_knowledge_projection`，不可对未知旧库盲目执行整条链。
3. 配置独立 0700 `SECOND_BRAIN_PROJECTION_ROOT`，运行预检。`SECOND_BRAIN_PROJECTION_ENABLED` 默认 false；完成试点质量与对账验收后才在指定环境打开。
4. 后台消费需要既有 `SECOND_BRAIN_ENABLED`、`SECOND_BRAIN_WRITE_ENABLED`、`SECOND_BRAIN_WORKER_ENABLED`；外部调度单步入口仅要求功能、写入、投影三个开关。不创建周期调度任务。
5. 小范围人工发布并验证健康从待处理到同步、撤回后访问 epoch 更新、外部修改阻塞、明确重新生成保留差异。记录真实来源金标和投影时延后才能标 G-SB2 通过。
6. 回退先关闭投影消费开关，必要时关闭知识写入；保留 PG、来源、历史 generation 及回执，不运行破坏性 downgrade。现有知识浏览不依赖新投影。

## 6. 下一阶段

SB3 继续实现受控知识 Context Pack 的 shadow 适配、引用回答质量评测、撤回与跨空间负例。当前未接入 Context Pack、知识向量、Memory Candidate 或 Artifact 回流，也未改变旧记忆排序。模型结构化知识生成和真实语义金标仍需独立验证，不能用本批人工维护及工程样例代替。
