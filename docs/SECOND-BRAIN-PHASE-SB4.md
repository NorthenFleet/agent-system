# 第二大脑 SB4：成果回流、记忆提案与运维恢复

**日期**：2026-10-06（Asia/Shanghai）  
**所属方案**：[SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)；前序：[SB3](SECOND-BRAIN-PHASE-SB3.md)  
**状态**：成果登记导入、知识域记忆提案、周期维护、私有逻辑备份及隔离恢复工程已完成验证。记忆桥接采用第 9.1 节允许的 `export_only` 降级，尚未创建原生 Memory Candidate 或外部绑定回执。G-SB4 的 10 个真实研究任务、至少 7 天观察及生产级恢复指标待验收；正式知识上下文注入、自动记忆桥接及周期调度均未启用。

## 1. 本批交付与边界

| 能力 | 已实现行为 |
| --- | --- |
| 登记成果导入 | 根据 Mission/Artifact ID、plan version、SHA-256，由服务端读取登记表和允许目录；核验任务 owner 与空间 project |
| 固定文档导入 | 根据 document ID、version row ID、document revision，从已登记结构化修订读取；校验结构哈希，再确定性转换 Markdown；不采用可能过期的投影缓存 |
| 来源链 | 保留登记标识、版本、上游哈希、导入字节哈希、草稿状态及已有 Artifact metadata / 文档父修订；未登记的上游依据不推断、不补造 |
| 防循环积累 | 同一登记版本只建一个引用；同字节来源复用；默认不提取，明确操作后才进入原入库审核；登记成果不自动算作新的独立证据 |
| 记忆提案 | 知识域保存 proposal ID、固定知识修订、证据、建议范围、记忆键与内容；幂等重试；读取时重新核验完整来源依赖与哈希 |
| 周期维护 | 日/周/月 UTC 周期去重；检查结构问题、待审核、失败入库、投影死信/漂移及失效记忆提案；无变化不重复标记需要关注 |
| WorkRun | 配置驱动的周期执行通过真实 `claim_at_most_once` 接口关联回执；丢失响应后重试关联同一条记录 |
| 运维恢复 | PostgreSQL 一致性逻辑快照 + 固定附件清单；独立较新撤回清单；仅允许恢复到空的隔离 schema；恢复前应用撤回、失效旧上下文并重建投影 |
| 前端 | Vue 3 + Element Plus「成果与运行」页签：登记、明确发起提取、项目记忆提案、重新核验、周期维护记录 |

本批没有修改既有任务、写作和记忆服务的业务状态机；通过读取登记权威及已有 WorkRun 接口接入。没有运行正式迁移、发布知识、启用后台调度、发送通知或改动正式 rollout 配置。

## 2. 成果导入的固定契约

请求只接受：

```json
{
  "kind": "artifact",
  "container_id": "实际 Mission ID（document 时为 document ID）",
  "object_id": "实际 Artifact ID（document 时为版本记录 ID）",
  "version": 2,
  "expected_hash": "登记的 64 位小写 SHA-256",
  "selected": true
}
```

必须绑定已授权项目空间；HTTP 写入还要求管理员、知识写开关及 `Idempotency-Key`。请求禁止 owner、任意绝对路径、客户端产物正文等额外字段。源系统暂不可用或文件变化时不以模型生成内容替代。

Artifact 读取沿用 `mission_artifact_reader` 的授权 roots、路径/符号链接/普通文件检查、5 MiB 上限及字节哈希校验。其默认路径来自原系统，SB4 不扩大允许目录。Artifact 只登记不等于已验收，本批统一要求用户明确选定，并标注 `user_selected_unverified`。文档保留原 `lifecycle_status`，例如 `working` 仍是草稿。

导入使用同一知识 PG 事务完成来源记录、外部引用和请求回执；附件采用已有不可变存储。事务失败可能留下不可见的同哈希附件，不会留下半个可读登记对象。外部登记读取与本域事务不是跨库原子事务：导入的是已固定核验的版本快照，不承诺持续同步源文件；每次显式重试仍重新检查外部授权和文件哈希。

外部身份由 kind、container、object、version 固定；同一身份内容漂移时拒绝复用旧记录。内容完全重复时复用原来源，不增加入库任务。只有用户另行点击“生成待审核候选”才提取，发布继续通过 SB1 审核门禁。审核视图展示外部版本/生命周期和独立证据提示。保留的 lineage 是登记快照，不代表已经核实整个上游证据链，也没有实现不同措辞摘要的语义去重。

## 3. 记忆桥接采用可用的降级路径

核对现有 [MemoryFeedbackService](../backend/services/memory_feedback_service.py) 后确认：

- `create_candidates` 依赖 Mission ID，按任务、版本、内容等生成 fingerprint；没有独立知识 proposal ID 的接入契约。
- 批准和后续执行没有同步核验知识完整来源依赖的接口；仅把知识引用写进 metadata 不能保证撤回后不再生效。

因此执行 SB-01 第 9.1 节的降级策略：**本域提案可保存和按权限导出读取，原生 Memory Candidate 自动桥接暂不启用**。不伪造 Mission，不绕过记忆审核，不创建虚假的 `kb_external_bindings` 成功回执。

提案包括 `proposal_id`、`knowledge_revision_ref`、`evidence_refs`、`requested_scope`、`agent_id`、`memory_key`、`proposed_content`、理由和完整固定知识条目。后端支持 project/profile/agent 的待处理建议，界面提供同项目范围。Agent ID 在此仅是未授权待处理建议，不会授予 Agent 权限；原生桥接开放前仍须校验目标 Profile/Project/Agent 权限。

创建与每次读取都核验当前页修订、block、页面/证据哈希、全部来源字节及访问 epoch。幂等缓存仅保存提案 ID；旧键重放不能返回已撤回正文。页面变化、来源撤回或哈希变化时立即拒绝读取，无需等待周期任务。周期任务另外将记录标记 `needs_review`，供运维查看。旧提案仍受本域审计保留，不静默删除或退役既有正式记忆。

后续原生桥接必须独立交付：Memory 按 proposal ID 幂等创建、审核前及执行前同步来源校验、跨库回执与对账、撤回后原生记忆治理。不能仅切一个配置把当前提案直接发布。

## 4. 周期维护与失败恢复

新表 `kb_maintenance_runs` 以 `(space_id, period_key)` 唯一，同一空间通用锁串行处理并发请求。周期按 UTC 日、ISO 周或月计算，客户端不能回填任意历史时间。报告和审计写入同一事务。报告内容哈希不包含生成时间，以免没有变化时重复提示。

只检查并记录，不自动改正文、裁决矛盾、批准提案或发消息。`attention_required` 仅表示本地页面有新增处理事项；`notification_sent=false`。同一期不会重新扫描，因此期间的新变化在下一期或不同周期检查中出现；来源撤回和权限校验始终实时生效。

默认配置：

```dotenv
SECOND_BRAIN_MAINTENANCE_ENABLED=false
SECOND_BRAIN_MAINTENANCE_SPACES=[]
```

经过试点预检后可明确配置（示例，未执行）：

```dotenv
SECOND_BRAIN_MAINTENANCE_SPACES=[{"actor":"实际 owner","space_id":"实际空间 ID","cadence":"weekly"}]
```

只有总开关、写开关和维护开关均开启才运行。现有知识 worker 开启时，每 60 秒检查配置；每期实际生成一次报告。也提供 `run_knowledge_maintenance.py --once` 给已有调度器，不创建 cron、launchd 或 Codex 自动化。最多配置 20 个 owner/space 条目，配置不授予权限，运行时仍查空间与项目权限。

配置驱动执行把本域回执 ID 用作 WorkRun 幂等键并绑定报告哈希。维护 PG 事务与 WorkRun 不是跨库事务；可能先完成维护、随后 ledger 不可用。下次 tick 可关联同一回执并完成 ledger；响应丢失和已完成重放均不增加执行 attempt。原生终态失败/取消/阻断不自动重新执行，返回需运维处理。

界面手动检查直接产生本域维护回执，未配置调度时 `work_run_id` 为空；不能把这个空值显示成已执行的 WorkRun。恢复演练也不伪造真实任务数。

## 5. 私有备份、恢复与回退

### 5.1 逻辑归档范围

`knowledge_backup.py capture` 在一个 PG `REPEATABLE READ` 事务中读取当前 SB0–SB4 全部知识表，并复制固定原始附件。清单包括 schema revision、捕获时间、空间列表、每表数量/哈希、附件哈希/大小；完成清单最后写入，未完成目录不能作为有效备份。

目录要求当前用户所有、0700；文件 0600；拒绝符号链接/非普通文件。单表最多 100,000 行，整个包最多 100 MiB，每个来源沿用 5 MiB 限制；超过限制需要专用运维方案。校验检出表/附件损坏、缺失、路径清单不一致或 schema 版本不匹配。

备份为**包含私有正文的明文归档**，SHA-256 只校验损坏，不提供加密或抵抗管理员重写整份清单的真实性证明。保存在可信私有目录；跨机器复制、加密密钥管理及保留/销毁策略由生产运维另行配置。本批不自动删除备份或源数据，不声称已实现敏感资料物理清除。恢复支持当前逻辑撤回，新增清除语义必须先扩展独立清单与恢复门禁。

该归档不包含完整 PG 集群、Mission/Artifact/文档权威或旧 Memory/WorkRun 数据库；恢复出的外部引用仅是历史证据记录，不代表外部系统已恢复可用。

### 5.2 独立撤回清单

`knowledge_backup.py revocations` 导出当前空间 owner/project/status/epoch 和非 active 来源 ID，单独保存。恢复要求清单晚于备份、覆盖所有备份空间；缺少/过期/哈希损坏时拒绝恢复。空间归属已经改变时也拒绝自动恢复。

这需要可信运维提供足够新的完整清单；当前工具不能证明离线文件是世界上最新的记录。生产事故中若撤回日志不完整，应保持服务关闭，先完成清除/撤回对账再开放查询，不能以“哈希正确”替代完整性判断。

### 5.3 空目标恢复与验证

`restore_isolated` 仅允许当前 schema 为 `sb_restore_<32位hex>`、所有知识表为空、来源目录不存在。它不能覆盖运行中的知识库。每个空间提升 epoch，先应用较新撤回记录，旧 Context/记忆提案因此失效；恢复时清除机器相关的投影回执，把投影 Outbox 置 pending；未完成入库任务变为需要手动重试，清除旧 WorkRun 关联，防止自动续跑。

恢复脚本只接受数据库名含 `test` 的显式 PostgreSQL 测试 URL，自动创建/删除两个随机 schema 和临时附件目录。生产恢复需先在隔离环境验证、重新核对 project 权限和外部来源，再单独制定切换步骤；此工具没有生产切换命令。

2026-10-06 的实际隔离演练：两份合成来源，备份后撤回其中一份，再从旧备份加较新撤回清单恢复。

| 检查 | 结果 |
| --- | --- |
| 仍有效的固定证据 | 恢复后可查询 |
| 备份后才撤回的来源 | 恢复后查询拒绝 |
| 旧 Context 快照 | epoch 变化后拒绝 |
| 私有投影 | 重建为 `ready` |
| Context 回退 | disabled 后 observer 返回空，不注入 |
| 归档规模 | 19,076 bytes，2 份合成来源 |
| 备份 / 恢复并验证耗时 | 0.007 / 0.029 秒，仅该本机小规模演练 |

这些数字不证明生产 RPO ≤24h / RTO ≤4h，也不代替全系统灾备演练。报告明确 `g_sb4_passed=false`、真实任务数 0、观察天数 0。

回退顺序：维护开关关闭 → 根据需求关闭 worker/projection/write → context mode 保持或改为 disabled → 保留 PG、来源、提案、审计与备份。禁止破坏性 Alembic downgrade。没有执行正式环境的任何开关修改。

## 6. 文件、接口与复现

| 文件 | 用途 |
| --- | --- |
| [bridges.py](../backend/services/knowledge/bridges.py) | 登记成果读取、原子导入、记忆提案与读取校验 |
| [operations.py](../backend/services/knowledge/operations.py) | 周期报告、提案失效标记、WorkRun 对账 |
| [backup.py](../backend/services/knowledge/backup.py) | 私有逻辑归档、校验、独立撤回清单和隔离恢复 |
| [v4 schema](../backend/models/knowledge_operations_v4.py) / [迁移](../backend/alembic/versions/20261006_knowledge_operations.py) | 3 个新增知识域表；不改冻结 v1–v3 模型 |
| [KnowledgeOperationsPanel.vue](../frontend-v2/src/components/knowledge/KnowledgeOperationsPanel.vue) | 成果与运行页签 |
| [恢复演练脚本](../backend/scripts/run_knowledge_recovery_drill.py) | 可复现的真实 PG 逻辑恢复演练 |

```text
POST /api/v3/knowledge/spaces/{id}/external-imports
POST /api/v3/knowledge/spaces/{id}/memory-proposals
GET  /api/v3/knowledge/memory-proposals/{id}
GET  /api/v3/knowledge/spaces/{id}/bridges
POST /api/v3/knowledge/spaces/{id}/maintenance-runs
GET  /api/v3/knowledge/spaces/{id}/maintenance-runs
```

详情读取按主体/空间/项目校验；写接口管理员限定。桥接概览最多返回最近 100 条、维护历史 30 条，正文通过独立核验接口读取。

在 `backend` 配置临时 `KNOWLEDGE_TEST_DATABASE_URL` 后：

```bash
PYTHONPATH=. venv/bin/python -m pytest --confcutdir=tests/knowledge tests/knowledge -q
PYTHONPATH=. venv/bin/python scripts/run_knowledge_recovery_drill.py \
  --output ../docs/review/second-brain-sb4-20261006/recovery-drill.json
```

本机私有运维示例（路径必须先由运维明确选择）：

```bash
PYTHONPATH=. venv/bin/python scripts/knowledge_backup.py capture /private/备份根目录/新备份目录
PYTHONPATH=. venv/bin/python scripts/knowledge_backup.py verify /private/备份根目录/新备份目录
PYTHONPATH=. venv/bin/python scripts/knowledge_backup.py revocations /private/撤回清单目录/新检查点.json
```

在 `frontend-v2`：

```bash
npm run test:run -- src/test/KnowledgeIntakePanel.spec.ts src/test/KnowledgeMaintenancePanel.spec.ts src/test/KnowledgeContextPanel.spec.ts src/test/KnowledgeOperationsPanel.spec.ts
npm run build
node scripts/preview-knowledge-maintenance.mjs --operations
```

## 7. 验收证据与剩余门禁

- 后端知识域 **121 项通过**，包含实际 PG 并发去重、登记 Artifact reader、固定文档哈希/投影、权限/角色、提案撤回/篡改、周期去重、实际 WorkRun 丢失回执、私有备份/恢复及前序回归：[日志](review/second-brain-sb4-20261006/backend-tests.txt)。
- 前端 **24 项通过**，含 SB4 5 项；TypeScript/Vite 生产构建通过：[测试](review/second-brain-sb4-20261006/frontend-tests.txt)、[构建](review/second-brain-sb4-20261006/frontend-build.txt)。原有 SQLAlchemy 弃用、大 chunk 提示保留。
- 恢复演练全项通过：[机器可读报告](review/second-brain-sb4-20261006/recovery-drill.json)。
- Chrome 合成 API 预览，真实 Vue/Element Plus 组件；390×844 宽度无横向溢出，旧提案正文在撤回后清除：[桌面](review/second-brain-sb4-20261006/operations-desktop.png)、[窄屏](review/second-brain-sb4-20261006/operations-mobile.png)、[清除后](review/second-brain-sb4-20261006/operations-invalidated.png)。
- 新迁移单一 head 为 `20261006_knowledge_operations`。测试未使用正式审核或生产数据，没有调用 LLM/embedding。

验收清理：随机 PG schema 和临时附件随测试/演练清理；本机合成预览已退出，临时 PostgreSQL 已正常停止（PID 文件已消失）。仅保留源码、文档、截图和验收报告。

尚未完成的验收：

1. SB0 生产预检、可信备份/撤回日志保管与保留政策，以及前序真实人工金标、独立验证集和生产性能门槛。
2. 10 个真实研究任务的收益/引用质量记录，至少 7 天持续观察。
3. 真实环境规模下的备份恢复、RPO/RTO 与整体切换演练。
4. Memory proposal-ID 接口、同步来源撤回校验和外部绑定对账接入；之后才能启用原生候选桥接。
5. SB3 正式上下文注入仍需独立实现和验收；当前即使 mode 设 enabled 仍保持阻断。

后续应进入受控试点和上述缺口收敛，不能把 SB0–SB4 工程完成表述为所有生产门禁已通过。

后续进展（2026-10-07）：[受控试点准备与验收](SECOND-BRAIN-PILOT-PLAN.md)已交付证据采集工具；[实际配置与基础预检](SECOND-BRAIN-PILOT-CONFIGURATION.md)已通过，服务未重启、真实观察未开始。
