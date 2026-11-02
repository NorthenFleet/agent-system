# 第二大脑 SB0 / SB1 实施与验证记录

**日期**：2026-10-06（Asia/Shanghai）  
**所属方案**：[SB-01 第二大脑知识子系统](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)  
**状态**：首批代码及隔离工程验证完成；生产预检、真实用户审阅与试点启用尚未完成。SB2–SB4 未实施，不能视为整个分方案完成。

> 本记录保留 SB1 交付时点的范围与结果。后续维护/投影实现与当前门禁状态见 [SB2 实施记录](SECOND-BRAIN-PHASE-SB2.md)。

## 1. 本批交付

在现有 `/knowledge` 页面增加“资料入库与审核”标签，实现以下流程：

```text
选择授权空间/项目 → 上传 Markdown、TXT 或文本 PDF → 持久入库任务
→ WorkRun 执行 → 原文定位与候选 → 人工核对具体修改集
→ 批准 → 单独发布 → 查看固定修订 → 查询原文摘录与引用
```

代码默认关闭功能、写入和后台处理，不连接生产库执行迁移，不生成正式知识批准记录。

### 1.1 已落实的边界

- PostgreSQL 是新增知识域的唯一权威；SQLite 不作为静默回退。
- 新增独立 `kb_*` 元数据，不进入旧应用启动时自动 `create_all` 的共享模型集合；表结构只由显式 Alembic 迁移创建。
- 空间归属从登录主体解析；所有来源、候选、页面、查询、下载和发布操作校验空间所有者。
- 旧项目缺少统一 owner 元数据，因此只对显式配置的试点用户开放此类项目；不能把“项目存在”当作“有权访问”。
- 资料存储在专用 0700 目录，文件 0600，固定哈希、受限大小，拒绝符号链接目录和内容哈希漂移。
- 发布绑定 `payload_hash`、基础修订、来源访问 epoch；页修订、引用、关系、发布清单、审计及 Outbox 同事务提交。
- 同空间写入通过行锁串行化；不同空间独立。幂等请求重放、并发发布和相同来源重复导入有数据库级约束及测试。
- 候选生成的租约/fencing token 与取消状态在提交前重新检查；过期 worker 无法提交。
- WorkRun 跨存储更新以阶段对账恢复，未假装和知识事务同时提交。
- 来源撤回立刻阻断依赖页面的查询、旧修订读取和候选审核；不等待将来的投影删除。
- UI 分别显示候选、批准、发布和投影状态；失败或过期审核会清除可操作的旧预览。

### 1.2 实际实现路径

| 位置 | 作用 |
| --- | --- |
| [knowledge_schema_v1.py](../backend/models/knowledge_schema_v1.py) | 首批冻结表结构、外键、唯一约束和索引 |
| [20261006_knowledge_domain.py](../backend/alembic/versions/20261006_knowledge_domain.py) | PostgreSQL 增量迁移，禁止无审查的破坏性降级 |
| [service.py](../backend/services/knowledge/service.py) | 来源、入库、审核、发布、读取、引用查询和撤回 |
| [contracts.py](../backend/services/knowledge/contracts.py) | Pydantic 页面/关系/修改集契约 |
| [parse_pdf.py](../backend/services/knowledge/parse_pdf.py) | 受限子进程中的 pypdf 文本提取 |
| [worker.py](../backend/services/knowledge/worker.py) | 持久任务领取、WorkRun 关联与状态修复 |
| [knowledge_v3.py](../backend/routers/knowledge_v3.py) | 认证与管理员写入 API |
| [KnowledgeIntakePanel.vue](../frontend-v2/src/components/knowledge/KnowledgeIntakePanel.vue) | 导入、审阅、知识页与引用查询界面 |
| [knowledgeV3.ts](../frontend-v2/src/api/knowledgeV3.ts) | 独立 API 客户端和稳定请求键 |
| [knowledge_preflight.py](../backend/scripts/knowledge_preflight.py) | 无写入、无敏感连接串输出的启用前预检 |
| [run_knowledge_ingest.py](../backend/scripts/run_knowledge_ingest.py) | 可由现有调度器调用的单次处理入口 |

旧知识图与旧检索服务未被替换；新代码不修改 Memory RRF、Graph Memory 或写作正文权威。

## 2. 明确的实现范围与设计差异

这是分阶段的 SB1 基础闭环，以下能力没有被假定为完成：

1. **编译模式为 `extractive-v1`**：保留可核验原文摘录；用户可指定概念分组。没有调用 LLM 自动提炼实体、生成综合判断或识别矛盾。前端和响应明确标注摘录，不能把该基线描述为 AI 知识理解已完成。
2. **每个入库请求处理一份来源**，空间内允许多个任务；资料不超过 5 MiB、50,000 文本字符，PDF 不超过 50 页；不满足限制明确失败，不丢弃尾部内容。
3. **文本 PDF 可解析，扫描 PDF 停在 `needs_ocr`**。解析器固定 pypdf 6.19.0，有 20 秒进程超时、CPU/输出限制；Linux 另加地址空间上限，macOS 不宣称已具备强制内存沙箱。
4. **Outbox 已与发布一起持久化，但导出消费者尚未实现**。数据库知识页可读；Markdown、图谱、向量导出均保持待后续阶段，UI 不误报完成。
5. **查询为可解释的词法原文检索**，最大 1,000 页；超限明确报错。没有宣称达到方案的 Recall、拒答率或语义忠实度金标门槛。
6. **未接正式 Context Pack**，也未创建 Memory Candidate、Artifact 回流、自动知识发布或维护通知。SB3/SB4 的边界保持关闭。
7. 首版概念更新已有后端基础修订检查；前端尚未提供合并、改名、结构化手工编辑或矛盾裁决工作台，这些属于 SB2。

## 3. 隔离验证

### 3.1 环境

使用 `/tmp` 下新建的独立 PostgreSQL 17 实例、独立端口和 `knowledge_test` 数据库；每个测试创建随机 schema，结束后清理。没有使用生产数据库或既有知识目录。测试批准均为 `isolated_test_fixture_only`，不表示用户正式审核。

清理状态：测试 schema 和来源副本已清理；2026-10-06 经用户明确授权，临时 PostgreSQL 实例已正常停止，`pg_ctl` 返回 `server stopped`。测试数据目录 `/tmp/agent-system-sb-pg/data` 保留，实例原使用端口 55439；未涉及正式数据库。

测试运行刻意使用 `--confcutdir=tests/knowledge`，隔离仓库旧的、会导入整套应用的全局测试 fixture。WorkRun 接入使用真实 PostgreSQL 账本和真实服务类，仅隔离其旧模块的默认数据库常量，避免 import-time 写入生产路径。

### 3.2 结果

| 检查 | 结果 |
| --- | --- |
| PostgreSQL / API / worker / PDF /隔离与恢复测试 | 40 项通过 |
| 前端组件行为测试 | 6 项通过 |
| TypeScript 检查及 Vite 生产构建 | 通过 |
| Alembic head | `20261006_knowledge_domain`，单一 head |
| 真实来源闭环演练 | 通过，见下节 |
| 生产数据库迁移 / 生产启用 | 未执行 |
| 浏览器人工审阅、桌面/窄屏视觉验收 | 待试点执行 |
| 人工质量金标、线上观察与恢复演练 | 未完成，不能据此开放后续切流 |

后端测试覆盖：授权与角色、伪造 owner、跨用户/空间/项目访问、必需幂等键、功能开关、原文重复、并发上传/发布、审核哈希、基础修订冲突、多页事务故障注入、来源撤回、文件篡改、旧租约回执、取消与显式重试、关闭新功能后的旧知识读取、PDF 页码/扫描件、长资料全文保留、提示注入数据和真实 WorkRun 对账。

前端测试覆盖：功能关闭时不调用受控接口；审阅来源且不执行来源脚本；批准和发布分离；过期批准停止；无依据结果；切换文件后重新生成上传幂等键；失败任务重新入库且不触发发布。

已观察到现有 SQLAlchemy `declarative_base` 弃用提示和 Vite 大 chunk 警告，均不影响本批检查通过；本批不顺带重构这些无关模块。

### 3.3 可复现命令

从 `backend` 目录运行（连接串由测试环境注入；数据库名必须包含 `test`）：

```bash
PYTHONPATH=. venv/bin/python -m pytest \
  --confcutdir=tests/knowledge tests/knowledge -q

PYTHONPATH=. venv/bin/python scripts/verify_knowledge_fixture.py \
  --source ../docs/review/second-brain-20261006/fixtures/design-source.txt \
  --output ../docs/review/second-brain-20261006/source-drill.json
```

以上要求 `KNOWLEDGE_TEST_DATABASE_URL` 指向一次性 PostgreSQL 测试库，不从生产 `DATABASE_URL` 猜测测试目标。

从 `frontend-v2` 目录运行：

```bash
npm run test:run -- src/test/KnowledgeIntakePanel.spec.ts
npm run build
```

### 3.4 真实来源证据

使用本项目分方案的固定文本快照，共 49,242 字节，生成 16 个有行号定位的片段。验证全文非空白字符完整保留、未审核查询为空、测试批准后可引用、原文下载逐字节一致、重复上传复用版本、撤回后不再召回。

- [固定输入快照](review/second-brain-20261006/fixtures/design-source.txt)
- [机器可读演练结果](review/second-brain-20261006/source-drill.json)
- [后端测试日志](review/second-brain-20261006/backend-tests.txt)
- [前端测试日志](review/second-brain-20261006/frontend-tests.txt)
- [前端构建日志](review/second-brain-20261006/frontend-build.txt)

快照记录的是实施前设计文本；本分方案后续更新不改写这份输入。演练结束清理测试 schema 和来源副本，报告不含生产 ID 或凭证。

## 4. 试点启用步骤

以下为操作手册，不表示已经执行。

1. 确认生产 `DATABASE_URL` 指向正确 PostgreSQL、当前迁移链已知且已备份；为新资料建立专用当前用户所有的 0700 目录，安装更新后的 `requirements.txt`。
2. 在目标环境显式执行 Alembic 升级至 `20261006_knowledge_domain`；不能对未检查的旧库盲目补整条迁移链。迁移不会从 SQLite 或旧 Obsidian 自动搬运数据。
3. 配置 `SECOND_BRAIN_SOURCE_ROOT`；如使用无 owner 的旧项目，明确设置 `SECOND_BRAIN_PILOT_OWNER_ID` 为实际登录用户 ID。
4. 运行只读预检：`venv/bin/python scripts/knowledge_preflight.py --env-file <实际配置文件>`。该脚本要求明确的 PostgreSQL WorkRun 账本；仍用旧 SQLite 账本的环境需单独验证兼容，不隐式迁移。
5. 预检通过后，在单个试点环境开启 `SECOND_BRAIN_ENABLED=true`、`SECOND_BRAIN_WRITE_ENABLED=true`；使用后台模式时再启用 `SECOND_BRAIN_WORKER_ENABLED=true` 并按现有服务流程重启。也可由既有调度器执行 `run_knowledge_ingest.py --once`，无需另建调度产品。
6. 用户从知识页选择试点项目，导入一份资料，在界面核对原文及候选内容后自行批准和发布，再验证引用跳转、无依据查询和任务恢复。
7. 记录真实 UI/用户验收后才能把 G-SB1 标为试点通过。SB2 的维护与投影、SB3 上下文、SB4 跨域回流按原方案独立推进。

回退时先关闭 worker、写入和功能入口，保留已写入的 PostgreSQL 数据及原始附件；不执行破坏性 downgrade。原知识浏览、记忆和写作流程不依赖这些开关。

## 5. 下一阶段工作

SB2 首先完成带固定 release manifest 的投影消费者、重试/死信/对账和知识维护 UI，再接模型结构化候选及语义审核。语义质量需要真实来源和人工标注，不能以本批确定性摘录测试替代。待选定首批真实项目并完成 G-SB1 用户验收后，更新本记录的试点状态。
