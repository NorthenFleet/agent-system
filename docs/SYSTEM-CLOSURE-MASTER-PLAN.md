# OpenClaw 智能体集群系统 · 闭环补强总体方案

**版本**: v1.0
**日期**: 2026-09-22
**作者**: sunyi + 战略助手
**状态**: 战略评审中（Phase 0 待裁决）
**作用域**: agent-system（本仓库），不覆盖 one-sim / ai-planning / zk 内部

---

## 0. 一句话说清楚这是什么

> **agent-system = 给 sunyi 本人用的单用户运营控制台**
> 它**不是**多用户 SaaS / 不是多团队协作平台 / 不是通用 AI 助手产品。
> 它的价值边界：让 sunyi 在**一个人同时运作论文 / 竞赛 / 多产品 portfolio / 研究项目**的高并发状态下，通过统一平台看清全局状态、调度任务、沉淀证据、驱动智能体协作。

---

## 1. 战略定位与边界

### 1.1 是什么

- **个人运营控制台**：统一看 sunyi 的多条业务线（论文第六章 / 智空竞赛 / OpenClaw / ai-planning-5130 / one-sim / zk / 知识本体智能筹划系统）的状态、任务、证据。
- **论文三版治理的执行环境**：v1/v2 冻结基线 + v34 活跃正文权威。
- **产品矩阵的展示门面**：把 7+ 关联产品作为 portfolio 组织（`/products`）。
- **未来跨系统证据回流中心**：从 one-sim / ai-planning / zk 收不可变仿真记录 → 沉淀为可检索证据 → 喂给论文第六章产出证据包。

### 1.2 不是什么

- ❌ 不是多用户 SaaS（不做权限分层/多租户/用户管理）
- ❌ 不是通用 AI 助手（不对外服务、不做聊天机器人产品）
- ❌ 不是 one-sim / ai-planning 的替代品（它们有各自独立价值）
- ❌ 不是 10 个真实独立 agent 的"集群"（详见决策 4）

### 1.3 用户画像（决策 1 已裁决）

**唯一目标用户 = sunyi 本人**（博士研究者，同时跑论文 / 竞赛 / 多产品 portfolio）。

**这意味着**：
- 后端 39 个 active router 中面向"团队管理"、"用户管理"的 service 都是**历史包袱**
- `user_service` / `auth_service` / `module_permission_service` 保留最简形态（单用户默认登录即可），不做权限矩阵
- `agent_team_service` 不需要真正的"团队分工"，只需要"sunyi 的 N 个工作分组 + 可选的几个真 LLM agent 助手"
- 前端一切设计以**单用户桌面工作流**优先，不做多用户冲突处理

---

### 1.4 配套设计分方案（2026-10-06 增补）

总体路线下按业务边界维护分方案，详细数据模型、接口与验收以各分方案为准。本节登记分方案与独立实施记录，不改写既有主阶段的历史完成状态，不将 2026-09-22 的现状评估当作新的生产复测。

| 编号 | 分方案 | 总体路线归属 | 状态与边界 |
| --- | --- | --- | --- |
| SB-01 | [第二大脑知识子系统](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md) | Phase 2 知识/记忆产品化配套；Phase 3 上下文；Phase 4/5 成果回流 | 实施中；[SB0/SB1](SECOND-BRAIN-PHASE-SB0-SB1.md)、[SB2](SECOND-BRAIN-PHASE-SB2.md)及 [SB3 引用检索/shadow](SECOND-BRAIN-PHASE-SB3.md)核心工程与隔离验证完成；真实质量门禁待验收，正式注入关闭；[SB4 成果与运维恢复](SECOND-BRAIN-PHASE-SB4.md)工程验证完成，Memory 采用 export-only 降级，原生桥接/7 天试点待验收；[试点准备](SECOND-BRAIN-PILOT-PLAN.md)工具验证完成，[实际配置与基础预检](SECOND-BRAIN-PILOT-CONFIGURATION.md)通过，[空基线恢复与来源准备](SECOND-BRAIN-PILOT-READINESS.md)完成，[30 份文档入库与恢复](SECOND-BRAIN-PILOT-INTAKE.md)完成，候选待审核，试点尚未启动 |

SB-01 形成“原始来源 → 候选知识 → 审核发布 → 引用检索 → 项目产出 → 成果回流”的闭环，补齐本总体方案 G2 的知识使用价值，并为 G1 跨系统证据回流提供来源治理。新增知识域使用 PostgreSQL 权威修订，Markdown/图谱/向量作为投影；现有外部笔记、长期记忆、写作正文和实验记录保持各自权威。

实施分为 SB0 契约基线、SB1 单资料闭环、SB2 知识维护、SB3 查询与上下文、SB4 成果和记忆桥接。基础工作量初估 18–27 人日，独立于下文历史排期，不包含网页/OCR/音视频连接器等扩展；首个小范围可用结果在 SB1 验收。完整门禁、回退和文件落点见分方案第 16–17 节。

知识上下文先 shadow，知识发布不自动晋升长期记忆；自动发布默认关闭。不以既有记忆全库迁移、Agent Team 重建或外部系统全部接通作为首版前提。上线继续遵守 [跨域协同总纲](SYSTEM-COORDINATED-OPTIMIZATION-PLAN.md) 的引用与作用域边界。

---

### 1.5 决策路由与旁路顾问分方案（2026-10-06）

新增 [DR-01 决策路由与旁路顾问](DECISION-ROUTING-ARCHITECTURE.md)，归属 Phase 3 指挥中心可解释性与 Phase 4 真实执行闭环。实施记录见 [DR1](DECISION-ROUTING-PHASE-1.md)、[DR2](DECISION-ROUTING-PHASE-2.md)及 [DR3](DECISION-ROUTING-PHASE-3.md)。2026-10-08 DR3 顾问/模型档位/代码候选核心实现与本地验证完成；生产未启用，源仓库集成仍需单独审批与验证。DR1、DR2 本地实现及隔离验证已完成；DR2 增加两种内联确定性检查、执行预算与反馈后强制重新规划，生产未启用。本增补以当前代码为基线，不把下文 2026-09-22 历史评估视为当前线上状态。

当前已具备 Optimus 规划、依赖调度、并行步骤、执行租约、证据门禁和最终评估；Agent Team 仍为协作事实域，LangGraph 为审批流程试点。新增 Router 只提供版本化决策，Mission/WorkRun 保持执行权威；模型顾问不替代规则门禁。

实施路线：DR1 影子路由及重复失败观察 → DR2 受限确定性执行与受控修复 → DR3 检查点顾问、隔离工作区和模型档位 → DR4 工具级受控适配器与回执。角色标签不等于已启动的真实模型实例；是否可用以执行器回执为准，不固定模型品牌或照搬截图性能数字。

DR1 默认关闭；启用 shadow 后只新增观察记录与展示，不自动改派、停止重试、调用顾问或扩大权限。不新增调度事实库，不触发生产迁移或自动部署。后续接管需通过既有审批、幂等、副作用回执、租约和证据回归验证。

---

## 2. 当前现状诚实评估

### 2.1 技术栈真实规模

| 层级 | 数量 | 评估 |
|---|---|---|
| 后端 service | 100+ | **严重过胖**，至少 30% 是实验/未上线 |
| FastAPI router | 39 active + 9 legacy | **legacy 9 个是纯历史包袱** |
| 前端 Vue 视图 | 30 个 | 用户真正在用的 ~7 个 |
| PostgreSQL 迁移 | 19 个 alembic 文件 | 健康，但真相层不清 |
| SQLite 数据库 | 2 个（dashboard_v2 + unified_dashboard） | 真相分层不清 |
| 文档 | 92 个 docs/*.md/json + 17 个顶层 md | **严重臃肿** |
| 启动端口 | 1 个（3021） | ✅ 清晰 |

### 2.2 业务子域成熟度全景（14 个子域 × 4 维度）

| 子域 | 后端 | 前端 | 用户感知 | 闭环 |
|---|---|---|---|---|
| ① 用户/权限 | 🟢 过胖 | 🟢 | 🟡 单用户下不需要 | 🟡 **待瘦身** |
| ② 项目中枢 | 🟢 | 🟢 | 🟢 在用 | ✅ |
| ③ 任务调度 | 🟢 | 🟢 | 🟢 在用 | ✅ |
| ④ 智能体注册 | 🟡 名义 | 🟡 | 🟡 名义 | ❌ **决策 4 已裁决** |
| ⑤ 知识/检索 | 🟢 | 🟢 | 🟡 轻度用 | 🟡 |
| ⑥ 智能体团队 | 🟡 contract 厚 | 🟡 半成品 | ❌ 名义 | ❌ **决策 4 已裁决** |
| ⑦ 指挥中心 | 🔥 巨大 | 🔥 演练态 | ❌ 不可用 | ❌ **Phase 3** |
| ⑧ 业务流编排 | 🟡 实验 | ❌ 0 页 | ❌ | ❌ **Phase 4** |
| ⑨ 执行证据 | 🟡 实验 | ❌ 0 页 | ❌ | ❌ 随⑧一起 |
| ⑩ 记忆系统 | 🔥 巨大 | 🔥 1 页 | ❌ 价值不可见 | ❌ **Phase 2** |
| ⑪ 产品矩阵 | 🟢 | 🟡 半成品 | 🟡 | ❌ **Phase 1** |
| ⑫ 财务 | 🟢 | 🟢 | 🟢 在用 | ✅ |
| ⑬ 系统监视 | 🟢 | 🟢 | 🟢 在用 | ✅ |
| ⑭ 讨论 | 🟢 | 🟢 | 🟢 在用 | ✅ |

**统计**：
- ✅ 已闭环：6 个（②③⑫⑬⑭ + 部分①）
- 🟡 半成品：3 个（①⑤⑪）
- ❌ 严重断层：5 个（④⑥⑦⑧⑩）—— 这是补强重点

### 2.3 诚实自我批判（用户偏好的"不美化"）

1. **"架构过度，产品不足"**：栈很先进（PG 双轨 + LangGraph + 20+ memory service + 4600 行指挥中心），但用户每天打开的页面不超过 7 个。**中间地带几乎是空转**。
2. **"文档过度，闭环不足"**：92 docs + 17 md 全是"内部里程碑"文档（COMMAND-CENTER phase 1-18 + MEMORY phase 1-11），但这些 phase 跑出来的指标用户一个都看不到——**黑箱给黑箱做记录**。
3. **"角色叙事，虚构成分"**：10 个智能体角色（擎天柱/李奥纳多/铁皮/感知器/大黄蜂/千斤顶/震荡波 + 4 龟）只存在于 `agents/` DB 表 + HEARTBEAT.md 叙述，代码层没有任何一个真 LLM agent 实例。**"智能体集群系统"这个名字本身有点过度承诺**。
4. **"跨系统孤岛"**：one-sim / ai-planning / zk / 论文是 sunyi **真正在做的事**，但 3021 平台与它们**零真实集成代码**。DESIGN.md 写着"One-Sim 只返回不可变仿真记录、证据包和论文证据包，3021 不复制或修改实验事实"——这只停留在纸面。
5. **"DB 真相分层不清"**：SQLite 里两个 db（dashboard_v2 + unified_dashboard）+ PG 多 schema，谁是谁的真相、哪些 model 写哪个库、为什么有些 service 坚持用 SQLite——没有清晰规则。
6. **"实验阶段标签过多"**：business_flow / workflow_runtime / compensation / execution_evidence / plan_quality_service 全部标"实验"，但实验了 1+ 月还没用户入口，等于**实验即空转**。

---

## 3. 缺口分类（7 类）

| 编号 | 类型 | 缺口描述 | 性质 |
|---|---|---|---|
| **G1 战略** | 跨系统集成缺失 | 3021 ↔ one-sim ↔ ai-planning ↔ zk ↔ 论文 **0 真实集成** | 🔴 必修 |
| **G2 战略** | 记忆系统价值不可见 | 20+ service 后端厚但前端 1 页，22 个 phase 文档跑出指标却无人看 | 🔴 必修 |
| **G3 战略** | 指挥中心在演练不在 UI | 28 个 phase drill.json 是内部记录，对 sunyi 不可用 | 🔴 必修 |
| **G4 战略** | 业务流编排 0 用户入口 | LangGraph + workflow_runtime 是实验阶段，无前端 | 🟡 次修 |
| **G5 战略** | 产品矩阵 Portfolio 未闭环 | Products.vue + ProductDetail.vue 半成品，B 轨核心业务不落地 | 🟡 次修 |
| **G6 战略** | 10 个智能体角色 = DB 数据 | 没有真 agent，是虚构的团队叙事 | 🟡 决策 4 已裁决 |
| **G7 工程** | 代码/文档臃肿 | 9 legacy router + 92 docs + 17 顶层 md 混杂 | 🟡 清理 |

---

## 4. 总体路线图（5 阶段）

```
Phase 0 战略收口 ──▶ Phase 1 用户面收口 ──▶ Phase 2 记忆系统落地
       │                    │                       │
       │                    │                       ▼
       │                    │               Phase 3 指挥中心产品化
       │                    │                       │
       │                    └───────────────────────┤
       │                                            ▼
       │                                   Phase 4 业务流 + 智能体真做
       │                                            │
       │                                            ▼
       └──────────────────────────────────▶ Phase 5 跨系统集成
```

| 阶段 | 主题 | 工作量 | 核心交付 | 前置决策 |
|---|---|---|---|---|
| **Phase 0** | 战略收口 | 0.5 天 | 本方案定稿 + 用户裁决 | ✅ 进行中 |
| **Phase 1** | 用户面收口 | 1 周 | 产品矩阵闭环 + legacy 9 router 删除 + docs 分区归档 + 顶层 md 整理 | 无 |
| **Phase 2** | 记忆系统前端落地 | 3-5 天 | Memory dashboards（评估/检索/SLO/shadow）+ phase 文档归档 | 指标对外口径 |
| **Phase 3** | 指挥中心产品化 | 1-2 周 | 任务调度 UI + 失败恢复 + 多 worker 监控面板 | drill.json 去留 |
| **Phase 4** | 业务流 + 智能体真做 | 3-4 周 | workflow 编辑器 + 擎天柱/李奥纳多为真 LLM agent | 决策 4 已裁决（C 部分做成） |
| **Phase 5** | 跨系统集成 | 3-4 周 | one-sim / ai-planning / zk / 论文 证据回流链路 | 集成形态 |

**决策优先级**：
- Phase 1-3：按顺序执行，互相不阻塞
- Phase 4：决策 4 已裁决 = (C) 部分做成（擎天柱/李奥纳多真做，其余分组标签）
- Phase 5：依赖跨系统契约（one-sim / ai-planning / zk 那边也要配合）

---

## 5. 每阶段详案

### 5.1 Phase 0 · 战略收口（0.5 天，本次评审）

**目标**：裁决 5 个战略决策点，锁定后续全部 Phase 形态。

**决策点清单（5/5 全部裁决 ✅）**：
1. ✅ **决策 1**（已裁决）：用户画像 = 你本人（单用户控制台）
2. ✅ **决策 2**（已裁决）：子域保留 vs 归档 → 保留核心 7 个，legacy 9 router 删除
3. ✅ **决策 3**（已裁决）：跨系统优先级 → 论文 → one-sim → ai-planning → zk
4. ✅ **决策 4**（已裁决 2026-09-22）：智能体角色真实化 → **(C) 部分做成**（擎天柱/李奥纳多为真 LLM agent，其余 8 个为工作分组标签）
5. ✅ **决策 5**（已裁决 2026-09-22）：文档整理策略 → 顶层只留 README/DESIGN/CONTRIBUTING/CHANGELOG 4 文件，docs/ 分 4 个区（`_archive/` `_design/` `_phases/` `_integration/`）

**交付物**：
- 本方案文档（`docs/SYSTEM-CLOSURE-MASTER-PLAN.md`）
- memory 持久化：`project/agent-system-closure-master-plan.md`（记录战略方向 + 用户决策）

**验收**：
- ✅ 用户已裁决决策 4 / 5（2026-09-22："按你推荐执行"）

---

### 5.2 Phase 1 · 用户面收口（1 周）

**目标**：把**在用 7 个页面 + 产品矩阵半成品**做扎实，清理 legacy 包袱。

#### 5.2.1 范围

| 工作 | 文件/模块 | 验收 |
|---|---|---|
| **① 产品矩阵闭环** | `frontend-v2/src/views/Products.vue` + `ProductDetail.vue` + `backend/services/product_service.py` + `api/products.ts` | `/products` 渲染 portfolio groups；`/products/:productId` detail 页能打开；register 的 document 显示 review state + SHA-256；截图 3021 桌面/iPad 无重叠 |
| **② 删除 legacy 9 router** | `backend/routers/legacy_*.py`（9 个）+ `backend/api_registry.py` 中对应 import 与 wire | 应用启动无错；`/api/health` 200；39 个 active router 不变 |
| **③ 顶层 md 整理** | 17 个顶层 md → 保留 4 个（README/DESIGN/CONTRIBUTING/CHANGELOG）；其余 13 个下放到 `docs/_archive/` 或 `docs/_design/` | 顶层清爽 |
| **④ docs 分区整理** | 92 docs → 分区：`_archive/` `_design/` `_phases/` `_integration/`；JSON drill 归 `_archive/` | 结构清晰 |
| **⑤ 清理无用 service** | 待清单（约 20 个实验阶段且未上线的：`q_learning_service` / `rss_scraper` / `web_crawler_service` 等候选） | 应用启动无错 |

#### 5.2.2 关键文件

**产品矩阵**（DESIGN.md 已规划未落地）：
- `frontend-v2/src/views/Products.vue`：添加 portfolio 分组视图
- `frontend-v2/src/views/ProductDetail.vue`：detail 页（identity / positioning / scenarios / dependencies / deliverables / media assets）
- `backend/services/product_service.py`：payload 加元数据字段（`cover_image` / `positioning` / `portfolio_group` 等）
- 产品卡片点击导航到 `/products/:id`（不只是 in-place 选中）

**legacy 清理**清单（9 个 router 全删）：
```
backend/routers/legacy_tasks_router.py
backend/routers/legacy_agents_router.py
backend/routers/legacy_bar_router.py
backend/routers/legacy_idle_agents_router.py
backend/routers/legacy_agent_docs_router.py
backend/routers/legacy_community_router.py
backend/routers/legacy_news_router.py
backend/routers/legacy_plans_auto_router.py
backend/routers/legacy_scheduled_tasks_router.py
```

**文档分区**设计：
```
docs/
├── _archive/         # 历史报告、演练 JSON、已完成里程碑（92 个文件中约 70 个）
│   ├── command-center-phases/
│   ├── memory-phases/
│   └── business-flow-phases/
├── _design/          # 活跃设计文档（DESIGN 子集 + PRD-GUIDE + COMPANY-OS-V1）
│   ├── DESIGN.md（软链或拷贝）
│   └── prd/
├── _phases/          # 正在执行中的演进记录（保留少量活跃 phase）
└── _integration/     # 后续 Phase 5 跨系统集成设计（Phase 0 产出）
```

#### 5.2.3 工作量评估

| 子项 | 工作量 | 风险 |
|---|---|---|
| 产品矩阵闭环 | 3 天 | 低 |
| legacy router 删除 | 1 天（含回归测试） | 中（可能触发 hidden dependency） |
| 顶层 md 整理 | 0.5 天（纯 mv） | 低 |
| docs 分区 | 0.5 天（纯 mv） | 低 |
| 无用 service 清理 | 2 天（含 import 分析） | 中 |
| **总计** | **7 个工作日** | — |

#### 5.2.4 依赖

无外部依赖。纯内部重构。

#### 5.2.5 风险与对策

| 风险 | 对策 |
|---|---|
| legacy router 删完后有 hidden dependency | 删除前跑全 pytest；删后手动 smoke 3021 启动 + 关键路径 |
| 产品 detail 页改动影响既有 Products 视图 | feature branch 隔离，合并前回归 |
| 文档 mv 破坏既有的 markdown 链接 | mv 后用 grep 验证所有引用更新 |

---

### 5.3 Phase 2 · 记忆系统前端落地（3-5 天）

> **配套分方案增补（2026-10-06）**：[SB-01 第二大脑知识子系统](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md) 增加资料入库、知识审核与引用问答，按 SB0–SB4 独立验收。下述 3–5 天为原记忆前端范围的历史估算，不包含 SB-01 新增工作量。

**目标**：把 20+ 个 memory service 后端已经产出的价值**暴露给前端**。

#### 5.3.1 现状诚实评估

后端建成：
- `memory_retrieval_service` + 11 phase 评估文档（phase1-baseline → phase11-ai-review-proposals）
- `memory_effectiveness_service` / `memory_shadow_metrics_service` / `memory_system_slo`
- `memory_lifecycle_service` / `memory_release_orchestrator` / `memory_release_governance`
- `memory_vector_service` / `memory_awareness_service`
- `memory_system_health_status` / `memory_system_matrix`
- `memory_projection_reconciliation_service` / `memory_feedback_service`

前端：
- **只有 1 个页面**：`MemoryEvaluation.vue`（仅评估数据集管理）

**问题**：
- 20+ service 后端厚但前端 1 页，**用户看不到记忆系统到底跑得多好**
- 22 个 phase 文档（MEMORY-*.md/json）跑出大量指标，但全在文档里，不在 UI 上
- "厚后端薄前端"意味着**投资了代码但没产生用户体验**

#### 5.3.2 范围

分 3 个新页面/面板：

**① Memory 评估仪表盘**（扩展现有 MemoryEvaluation.vue）
- 指标：precision@k / recall@k / MRR / NDCG（按 retrieval phase 演进）
- 数据源：`memory_retrieval_evaluation_service`
- 时间维度：按 phase 演进（phase 1 → 11 的指标变化曲线）
- 数据集：当前标注数据集（`memory_*` JSON）的样本分布

**② Memory 健康与 SLO 仪表盘**（新建）
- 指标：retrieval latency P50/P95 / recall@5 / shadow vs production 一致性
- 数据源：`memory_shadow_metrics_service` / `memory_system_slo` / `memory_system_health_status`
- 关键告警：SLO 违规项（红色）/ 接近阈值（黄色）

**③ Memory 生命周期仪表盘**（新建）
- 指标：memory 数量按状态分布（active / shadow / reconciled / released）
- 数据源：`memory_lifecycle_service` / `memory_release_orchestrator`
- 操作入口：手动 trigger reconciliation / release（已有 API 但没 UI）

#### 5.3.3 关键文件

```
frontend-v2/src/views/MemoryEvaluation.vue           # 扩展
frontend-v2/src/views/MemoryHealth.vue              # 新建
frontend-v2/src/views/MemoryLifecycle.vue           # 新建
frontend-v2/src/api/memoryHealth.ts                # 新建
frontend-v2/src/api/memoryLifecycle.ts             # 新建
frontend-v2/src/router/index.ts                    # 添加路由
backend/routers/memory_router.py                   # 已有，可能需扩展
```

#### 5.3.4 工作量评估

| 子项 | 工作量 | 风险 |
|---|---|---|
| MemoryEvaluation.vue 扩展 | 1.5 天 | 低 |
| MemoryHealth.vue | 1.5 天 | 中（SLO 指标口径需对齐） |
| MemoryLifecycle.vue | 1 天 | 低 |
| 22 个 phase 文档归档到 `_archive/` | 0.5 天 | 低 |
| **总计** | **4.5 个工作日** | — |

#### 5.3.5 依赖

- Phase 1 完成（docs 分区整理）
- 需要用户裁决"哪些 SLO 指标对外可见"

---

### 5.4 Phase 3 · 指挥中心产品化（1-2 周）

**目标**：把 28 个 phase drill.json 内部记录**产品化**为 sunyi 实际可用的任务调度 UI。

#### 5.4.1 现状

后端：
- `command_center_service.py` 4600+ 行（系统心脏）
- `command_center_worker.py`（多 worker）
- `repositories/command_center_repository.py`
- 7 个 alembic PG 迁移（20260916 → 20260923）
- 28 个文档（10 md + 18 json drill）

前端：
- 1 个 `CommandCenter.vue`（停留在演练界面层级）

**问题**：
- 28 个 phase drill 文档都是"内部演练记录"，对 sunyi 不可用
- "失败恢复 / 多 worker / PG cutover" 是技术里程碑，**不是用户价值**
- 用户真正需要的是："sunyi 看得到任务状态、失败原因、恢复进度"

#### 5.4.2 范围

**① 任务调度可视化面板**（扩展现有 CommandCenter.vue 或新建子组件）
- 任务列表：ID / 状态 / 进度 / 失败原因 / 重试次数
- 状态分布：pending / running / succeeded / failed / recovered
- 时序图：任务吞吐量（每小时完成数）
- 数据源：`command_center_service` + `command_center_repository`

**② 多 worker 健康监控**
- worker 列表：ID / 状态 / 当前负载 / 最近心跳
- worker 失败事件流
- 数据源：`command_center_worker.py`（已有表 `command_center_workers`）

**③ 失败恢复入口**
- 失败任务列表 + 一键恢复按钮
- 恢复历史（恢复耗时、恢复成功率）
- 数据源：`command_center_service.recover_inflight_tasks()`

#### 5.4.3 关键文件

```
frontend-v2/src/views/CommandCenter.vue              # 重构
frontend-v2/src/views/components/command/            # 新建
│   ├── TaskList.vue                                 # 新建
│   ├── TaskTimeSeries.vue                           # 新建
│   ├── WorkerHealth.vue                             # 新建
│   └── FailoverPanel.vue                            # 新建
frontend-v2/src/api/commandCenter.ts                 # 已有，需扩展
backend/routers/command_center_router.py             # 已有，需扩展（任务列表 API + worker 列表 API + recover API）
```

#### 5.4.4 工作量评估

| 子项 | 工作量 | 风险 |
|---|---|---|
| 后端 API 扩展 | 2 天 | 中（command_center 已经复杂） |
| 任务可视化 | 3 天 | 低 |
| worker 健康监控 | 2 天 | 低 |
| 失败恢复入口 | 1 天 | 中（恢复幂等性） |
| 28 个 drill 文档归档 | 0.5 天 | 低 |
| **总计** | **8.5 个工作日** | — |

#### 5.4.5 依赖

- Phase 1 完成
- 需要用户裁决"28 个 drill 文档是归档还是继续作为活跃设计"

---

### 5.5 Phase 4 · 业务流 + 智能体真做（3-4 周）

**目标**：把"实验阶段"的业务流 + 智能体角色落地成用户可用产品。

#### 5.5.1 业务流编排

**后端已有**：
- `business_flow_service.py` / `workflow_runtime.py` / `compensation_service.py` / `execution_evidence_service.py` / `plan_quality_service.py`
- LangGraph checkpoint PG

**前端已有**：**0 个页面**

**范围**：
- 新建 WorkflowEditor.vue（基于 LangGraph 图结构的可视化编排器）
- 新建 WorkflowInstance.vue（运行实例监控/补偿/replay）
- 新建 ExecutionEvidence.vue（证据可视化）

**工作量**：3 周（含后端 API 扩展 + 前端 3 个页面 + LangGraph 集成可视化）

#### 5.5.2 智能体真做（决策 4 推荐：C 部分做成）

**现状**：
- `agent_team_service.py` + `agent_capability_registry.py` + contract 硬契约
- 10 个 agent 角色（擎天柱/铁皮/感知器/大黄蜂/千斤顶/震荡波 + 4 龟）
- **但**：没有真 LLM 实例，只是 DB 记录 + HEARTBEAT.md 叙事

**方案 C**（我的推荐）：
- **擎天柱 = 真 LLM agent**（sunyi 的个人 AI 参谋/秘书）
  - 接 OpenAI / Claude / 本地 LLM
  - 入口：顶部导航"与擎天柱对话"抽屉
  - 能力：帮 sunyi 看当前任务状态、汇总今日进展、建议下一步优先级
- **李奥纳多 = 真 LLM agent**（与 ai-planning 协同的规划助手）
  - 帮 sunyi 在 ai-planning 侧设计任务、检查任务依赖、生成任务描述
  - 入口：ai-planning 5130 控制台内嵌
- **其余 8 个 = 工作分组标签**（不再扮演"独立 agent"）
  - 汽车人组 = 研究/运营/监控类工作
  - 忍者神龟组 = DEV/代码类工作
  - 分组纯粹是 UI 上的分类，不再需要"心跳 / 任务汇报"叙事

**范围**：
- 真做擎天柱（LLM agent + 工具绑定 3021 API）
- 真做李奥纳多（LLM agent + 工具绑定 ai-planning 5130）
- 简化其余 8 个为分组标签
- 删除 HEARTBEAT.md 叙事（已被 dashboard 取代）
- 删除 agents/ 目录的"心跳汇报"机制（已经是历史包袱）

**工作量**：1-2 周（含 LLM 集成 + 工具绑定 + UI + 叙事清理）

#### 5.5.3 总计

业务流 3 周 + 智能体 2 周 = **5 周**（但可并行，实际 3-4 周）

#### 5.5.4 依赖

- Phase 1-3 完成
- 需要用户裁决决策 4（C 部分做成 vs 完全放弃叙事 vs 全部真做）
- 需要 OpenAI / Claude API key（已配置？需验证）

---

### 5.6 Phase 5 · 跨系统集成（3-4 周）

**目标**：让 agent-system 与 one-sim / ai-planning / zk / 论文 **产生真实数据流**。

#### 5.6.1 优先级（决策 3 已裁决）

1. 🥇 **论文第六章 ↔ agent-system**（最紧，已有 bridge 设计未落地）
2. 🥈 **one-sim ↔ agent-system**（推演记录回流到 3021 产品页）
3. 🥉 **ai-planning ↔ agent-system**（规划结果回流）
4. ⚪ **zk ↔ agent-system**（训练 run 证据入库）

#### 5.6.2 各链路详细设计

**① 论文第六章 → 3021**（Phase 5.1）

**当前缺口**：
- 论文 evidence bundle 由 ai-planning `ResearchWorkbench.build_paper_evidence_packet()` 生成
- 但 3021 没有地方"展示"这些证据（产品 portfolio / 写作三版治理都没有接入点）

**集成方案**：
- 3021 新建 `Evidence Packet` 页面（路由 `/evidence/:bundle_id`）
- 通过 HTTP API 从 ai-planning 5130 拉 evidence bundle（ai-planning side 已实现 `/api/research/workbench/evidence-packets/{bundle_id}`）
- 在 v34 活跃正文权威的 `delivery_role=candidate` 阶段，可以"附加" evidence bundle 作为证据支撑
- 用户在 3021 编辑 v34 时可"引用" evidence bundle 段落（形成"正文 ↔ 证据"双向链接）

**工作量**：1 周

**② one-sim wargame → 3021**（Phase 5.2）

**当前缺口**：
- wargame 5120 推演产生的"运行会话"无回流到 3021
- 3021 的"产品矩阵"里 manual-wargame/digital-wargame 是独立产品卡，但没有"推演历史"

**集成方案**：
- 3021 新建 Session Replay 视图（路由 `/wargame/sessions/:id`）
- 5120 推演结束生成 manifest + 事件流 JSON，POST 到 3021 `/api/evidence/wargame-sessions`
- 3021 产品 detail 页（manual-wargame）能看到历史推演

**工作量**：1 周

**③ ai-planning → 3021**（Phase 5.3）

**当前缺口**：
- ai-planning `BluePlannerAgent` 跑出的 HTN/MRTA 规划结果，3021 看不到

**集成方案**：
- 3021 Planning Result 视图
- ai-planning `/api/planning/results` webhook 回调
- 3021 任务调度可"引用" ai-planning 产出的 plan（形成任务 ↔ 方案链接）

**工作量**：0.5 周

**④ zk PPO run → 3021**（Phase 5.4）

**当前缺口**：
- Yoga PPO smoke 跑出 checkpoint + reward 历史，但 3021 看不到

**集成方案**：
- 3021  Training Run 视图（路由 `/training/:id`）
- Yoga 端 checkpoint 上传到 3021（或 3021 pull from Yoga via Tailscale）
- 产品 detail 页（intelligent-wargame）能看到 run 历史

**工作量**：0.5 周

#### 5.6.3 总计

4 条链路 = **3 周**（串行执行）

#### 5.6.4 依赖

- Phase 1-4 完成
- ai-planning / one-sim 那边要配合加 API（**外部依赖**，可能延迟）

---

## 6. 技术债务清理策略

### 6.1 Legacy Router 清理（Phase 1.2 已纳入）

9 个全删：
```
legacy_tasks_router
legacy_agents_router
legacy_bar_router
legacy_idle_agents_router
legacy_agent_docs_router
legacy_community_router
legacy_news_router
legacy_plans_auto_router
legacy_scheduled_tasks_router
```

### 6.2 实验 Service 清理（Phase 1.5 候选）

经评估，以下 service 可能是实验阶段且无真实用户，建议归档（不删除，改放到 `services/_archive/`）：
- `q_learning_service.py`
- `rss_scraper.py` / `rss_scheduler.py`
- `web_crawler_service.py`
- `news_scraper.py`
- `cloud_session_monitor.py`（如果不在 topology 内）
- （详细清单需 grep 验证 active 路由引用）

### 6.3 文档清理（Phase 1.3 / 1.4 已纳入）

- 92 docs 文件 → 分 4 个区（`_archive/` `_design/` `_phases/` `_integration/`）
- 17 顶层 md → 仅保留 4 个（README/DESIGN/CONTRIBUTING/CHANGELOG）
- 新增顶层 CONTRIBUTING.md（说明如何加新 phase 文档，避免再膨胀）
- 新增顶层 CHANGELOG.md（记录栈升级 / Phase 演进的关键里程碑）

### 6.4 Agent 叙事清理（Phase 4.2 已纳入）

- HEARTBEAT.md（震荡波管理定时任务叙事）—— 如决策 4 选 C，删除这份历史文档
- agents/ 目录（如果有 agent 配置文件）—— 简化为分组标签
- architecture/team-structure.md —— 重写为"分组说明"而非"团队架构"

### 6.5 DB 真相分层规则（建议加入 CONTRIBUTING.md）

- **SQLite**：仅用于开发/回退/单机演示；不用于生产数据
- **PostgreSQL**：唯一生产真相层
  - public schema：通用业务（users / tasks / products / ...）
  - custom schema：按子域独立（command_center / memory / workflow / agent_team）
- **规则**：新增 service 默认写 PG；如必须用 SQLite（特殊原因）需在 PR 中显式说明

---

## 7. 工作量与排期

| 阶段 | 工作量 | 累计 | 关键依赖 |
|---|---|---|---|
| Phase 0 战略收口 | 0.5 天 | 0.5 天 | ✅ 已裁决决策 4/5（2026-09-22） |
| Phase 1 用户面收口 | 7 天 | 1.5 周 | 无 |
| Phase 2 记忆系统前端落地 | 4.5 天 | 2.5 周 | Phase 1 |
| Phase 3 指挥中心产品化 | 8.5 天 | 4.5 周 | Phase 1 |
| Phase 4 业务流 + 智能体真做 | 21 天 | 9.5 周 | Phase 1-3 + 决策 4 |
| Phase 5 跨系统集成 | 15 天 | 13 周（~3 个月）| Phase 4 + 外部依赖 |

**总工作量**：约 **3 个月**（按 1 人全职投入），实际按用户业余投入约 **6 个月**。

**优先级建议**：
- 立即做：Phase 0（本次评审）
- 本月内完成：Phase 1（清理 legacy，产品矩阵闭环）
- 下月完成：Phase 2 + Phase 3（暴露后端价值）
- 第三个月：Phase 4（业务流 + 智能体真做）
- 第四个月起：Phase 5（跨系统，看外部依赖）

---

## 8. 决策点汇总（5/5 已裁决 ✅）

### 已裁决 ✅（2026-09-22）
- **决策 1**：用户画像 = 你本人（单用户控制台）
- **决策 2**：子域保留 vs 归档 → 保留核心 7 个，legacy 9 router 删除
- **决策 3**：跨系统优先级 → 论文 → one-sim → ai-planning → zk
- **决策 4**：智能体角色 → **(C) 部分做成**：
  - 擎天柱 = 真 LLM agent（sunyi 的个人 AI 参谋/秘书）
  - 李奥纳多 = 真 LLM agent（与 ai-planning 协同的规划助手）
  - 其余 8 个（铁皮/感知器/大黄蜂/千斤顶/震荡波 + 4 龟）= 工作分组标签
  - 删除 HEARTBEAT.md 叙事 + agents/ 心跳机制
- **决策 5**：文档整理 → **顶层只留 4 文件 + docs 分区**：
  - 顶层：README.md / DESIGN.md / CONTRIBUTING.md / CHANGELOG.md
  - docs/ 分区：`_archive/` `_design/` `_phases/` `_integration/`

### 后续需裁决（Phase 2/3/4 启动前）
- Phase 2：哪些 SLO 指标对外可见？
- Phase 3：28 个 drill.json 是归档还是保留？
- Phase 4：OpenAI / Claude 的 API key 在哪里（是否已配置）？

---

## 9. 关键约束

1. **用户是博士研究者**：时间有限，必须分阶段交付，不能一次性大重构
2. **已有 12000+ 行改动积累**：重构要小心，不能破坏既有业务
3. **跨系统依赖**：Phase 5 依赖 one-sim / ai-planning / zk 配合，可能延迟
4. **用户偏好**：
   - 先讨论再实施
   - 结构化技术报告（表格 + 合规清单 + diff 摘要）
   - 严格 commit 隔离
   - 中文沟通混合英文术语
5. **单用户前提下**：许多"团队管理"功能都是历史包袱，可大幅瘦身

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| Phase 1 legacy 删除触发 hidden dep | 中 | 中 | 删前跑全 pytest；删后 3021 启动 + 关键路径 smoke |
| Phase 4 LLM 集成遇 API 限制 | 中 | 中 | 先验证 API key；准备本地 LLM 兜底 |
| Phase 5 跨系统依赖外部配合 | 高 | 高 | 每条链路独立可拆；外部阻塞的不阻塞内部 |
| 文档整理破坏既有链接 | 低 | 低 | mv 后 grep 全引用 |
| 3 个月期间用户优先级变化 | 高 | 高 | 每 Phase 启动前用户再次确认优先级 |

---

## 11. 附录

### 11.1 当前 service 全部清单（100+ 个）

见远程 `backend/services/` 目录（100+ 文件）

### 11.2 当前 active router 全部清单（39 个）

```
loop_queue
workflow
openclaw_status
system_status
projects_v3
writing_workspace
mission_planning
knowledge
knowledge_stack
data_admin
discussions_router
products_router
product_invocation_router
agent_os
finance
finance.health
intelligence
web_crawler
auth_router
users_router
tasks_v2_router
agents_router
customers_router
v2_chat_router
codex_jobs_router
command_center_router
context_router
development_automation_router
task_recommend_router
agent_health_router
agent_team_router
monitoring_router
modules_router
task_webhook_router
templates_router
notification_router
automation_router
analytics_router
scheduler_router
```

### 11.3 当前 legacy router 全部清单（9 个，Phase 1 删除）

```
legacy_tasks_router
legacy_agents_router
legacy_bar_router
legacy_idle_agents_router
legacy_agent_docs_router
legacy_community_router
legacy_news_router
legacy_plans_auto_router
legacy_scheduled_tasks_router
```

### 11.4 14 子域 × 关键文件索引

见 2.2 节业务子域成熟度全景表

---

**文档结束**。

决策 4 / 5 已裁决（2026-09-22），Phase 0 收官、Phase 1 开工。
DR4 增补（2026-10-08）：[工具调用控制与持久化回执](DECISION-ROUTING-PHASE-4.md) 核心实现和本地验证完成。逐调用复核租约、路径与预算，意图先提交、操作后留存回执；未闭合或未知副作用阻止隔离候选通过。开关默认关闭，真实模型、生产 PostgreSQL 并发、视觉验收与源仓库集成未执行。
