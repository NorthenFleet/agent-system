# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-08-09
- Primary product surfaces: 3021 文档管理、协同工作台、概念与论证、参考文献、排版与交付、项目中枢、数据管理
- Evidence reviewed: `frontend-v2/src/views/WritingWorkspace.vue`、`frontend-v2/src/components/writing/WritingLinkedWorkspace.vue`、`frontend-v2/src/components/writing/WritingWorkspacePane.vue`、`frontend-v2/src/components/writing/WritingAiPane.vue`、`frontend-v2/src/components/writing/CollaborativeWritingEditor.vue`、`frontend-v2/src/components/writing/PresentationWorkspace.vue`、WorkBuddy 人机双写参考截图

## Brand
- Personality: 严谨、克制、面向研究与交付
- Trust signals: 明确版本、真实数据来源、同步状态、可追溯记录
- Avoid: 装饰性大卡片、低信息密度、用颜色替代文字状态、项目名称特判

## Product goals
- Goals: 让用户快速判断正文、PPT 与图表现状、目标差异、写作进度和交付风险，并在同一工作面完成文档、PPT、结构化画图与 AI 的组合协作
- Non-goals: 浏览器精确复刻 Word 分页；第一阶段不支持多人实时光标或离线合并
- Success signals: 当前结构和写作进展可以逐章对照；人工持续输入时 AI 可处理其他段落；同段变化不会被自动覆盖

## Personas and jobs
- Primary personas: 论文作者、导师、评审与研究团队成员
- User jobs: 核对目录、检查章节进度、编辑正文、制作 PPT、核对章节与页面关系、进入交付检查
- Key contexts of use: 桌面端长时间研究写作，兼容窄屏浏览

## Information architecture
- Primary navigation: 研究总览、协同工作台、概念与论证、参考文献、排版与交付
- Core routes/screens: `/writing`
- Content hierarchy: 文档项目 → 项目内正文/PPT/数据源 → 双窗口协同工作台 → 版本与交付

## Design principles
- 结构事实与写作状态并列，支持逐章比较
- 状态必须同时使用文字、数量和颜色表达
- 先显示摘要，需要时再展开细目
- AI建议分、专家确认分、证据覆盖率和评价新鲜度必须分别展示
- 协同工作台是项目默认编辑入口；不再用文档、PPT、联动三个互斥页面分割同一工作过程
- 工作台提供两个可调窗口，每个窗口独立选择文档、PPT、画图或 AI，并支持写作、PPT 制作、版本比对、文档/PPT校验、图表创作、论文插图与 PPT 配图预设
- 同一论文系列按独立正式文档登记；第一、二版是只读历史基线，第三版结构化 JSON 是唯一可编辑正文权威
- 第二版历史基线的权威源是指定 Word 正式母稿；导入时保留原始 `.docx`、SHA-256、提取 Markdown、图片资源与此前 Obsidian 导入快照，不以章节 Markdown 覆盖 Word 来源
- Word 包存在损坏或悬空 OOXML 关系时，兼容解析器只跳过无效资源并记录警告，仍从 `word/document.xml` 提取章节、正文、表格与有效图片；原始 Word 保持不变
- 历史基线可以单独查看和导出，但 `historical_reference` 不进入项目正式交付包；交付包只包含 `deliverable`
- 版本比对是按文档校验和生成的只读派生结果，先匹配章节编号与规范化标题，再显示段落新增、删除、修改和未变化统计，不回写正文
- 写作预设默认左侧 AI、右侧文档；AI 窗口跟随另一窗口焦点，也可锁定目标文档、章节、段落或 PPT 页
- 同一资源同时出现在两个窗口时执行单写多读，后打开的对照窗口自动只读
- 第一阶段复用既有正文与 PPT 权威，不因窗口切换复制正文、PPTX 或联动清单
- 人工与 AI 以稳定块标识和块修订号协作；并发安全只说明目标块未变化，不代表内容获准进入正文
- 低风险措辞、语法和格式整理可自动进入工作草稿；论点、数字、引用、公式、图表、实验结论和结构变化进入风险审批
- 结构化权威切换必须由管理员显式初始化并通过往返校验；只读访问不得触发迁移或写入
- AI 写作任务由 PostgreSQL 租约队列持久执行，进程重启后可重新领取过期任务
- 主张、不可变证据、证据缺口、修改集、Word 发布和跨系统运行均由 PostgreSQL 对象追溯；检索结果不能直接升级为证据
- One-Sim 只返回不可变仿真记录、证据包和论文证据包，3021 不复制或修改实验事实
- Jarvis 采用至少一次调度、幂等接口、步骤依赖和恢复游标；付费服务、物理设备和实验协议变化停在执行审批门
- 结构化 JSON 是正文权威，Markdown 是兼容投影，DOCX/PDF 是交付产物
- PostgreSQL 图表 JSON 是画图权威，SVG 是可重建矢量投影，PNG/PDF 是交付产物；不以导出文件反向覆盖结构化图表
- 图表引用固定 `diagram_id + diagram_revision + target`，新修订只显示“有更新”，不得静默替换正文或 PPT 已引用版本
- 图表 AI 只返回元素级结构化操作；不同元素可自动合并，同一元素修订冲突必须保留为建议，删除、批量重排和语义变化均需人工确认
- 正式 Word/PDF 只能由当前已审批修订生成；Word 内容修改必须以 ChangeSet 回流
- 不同文档类型根据后端标准包动态展示指标，前端不维护业务评分规则
- Tradeoffs: 桌面端优先同屏对照；窄屏自动回落为纵向阅读

## Visual language
- Color: 复用现有主题变量和 Element Plus 状态色
- Typography: 复用现有标题、正文和辅助文字层级
- Spacing/layout rhythm: 14px 页面间距、15px 卡片内边距、6px 圆角
- Shape/radius/elevation: 细边框、低阴影、紧凑研究工具风格
- Motion: 仅保留组件原生过渡
- Imagery/iconography: 使用现有图标体系，不新增装饰图片

## Components
- Existing components to reuse: `DocumentStructureStatus`、`el-tag`、`el-button`、`el-progress`、`el-drawer`
- New/changed components: `WritingWorkspace` 工作区一级导航、`WritingLinkedWorkspace` 双窗状态与布局控制器、`WritingWorkspacePane` 可组合窗口、`WritingAiPane` 独立会话窗口、`DiagramWorkspace` 结构化画图窗口、`DocumentEvaluationPanel`、`CollaborativeWritingEditor`、`PresentationWorkspace`
- Variants and states: saved、dirty、saving、error；queued、running、review_required、partially_applied、applied、conflicted、failed、cancelled；missing、insufficient、sufficient；candidate、ready、approved、published
- Token/component ownership: 主题变量由全局样式维护，页面只负责布局

## Accessibility
- Target standard: 保持现有语义和键盘可用性
- Keyboard/focus behavior: 章节进展继续使用原生 `button`；目录细目继续使用 `details/summary`；分隔线提供可聚焦拖动控制，窗口操作不依赖悬停
- Contrast/readability: 复用现有高对比主题变量
- Screen-reader semantics: 保留标题层级、section、aside 和状态文本
- Reduced motion and sensory considerations: 不新增依赖动画的信息表达

## Responsive behavior
- Supported breakpoints/devices: 桌面与 iPad；人机双写和联动工作台在 1180px 以下切换为单窗口标签页；画图窗口的图形库和属性栏在窄窗中切换为抽屉
- Layout adaptations: 桌面总览为“当前结构 | 写作结构”；协同工作台为两个可调窗口，支持 28%–72% 拖动、交换和单窗最大化；1180px 以下保留两个窗口状态并以左/右标签切换
- Touch/hover differences: 交互不依赖 hover，按钮保持可点击区域

## Interaction states
- Loading: 复用工作区加载状态
- Empty: 缺少当前结构时仍显示写作进展
- Error: 草稿保存失败时禁止卸载窗口或切换资源；布局冲突时载入服务端最新修订并明确提示
- Success: aligned 和有正文状态明确显示
- Disabled: 沿用 Element Plus 组件行为
- Offline/slow network, if applicable: 技术评价继续可用；模型不可用时保留会话和失败状态；窗口布局保存失败时保留当前本地布局

## Content voice
- Tone: 准确、简洁、可核验
- Terminology: “当前目录结构”表示正文事实；“写作结构”表示章节内容进展
- Microcopy rules: 版本、章数、目录项和状态使用明确数值；AI结果必须标注“建议”，不得使用“正式合格”

## Implementation constraints
- Framework/styling system: Vue 3、TypeScript、Element Plus、Tiptap Vue 3、AntV X6、Dagre、页面 scoped CSS
- Design-token constraints: 不新增颜色常量，优先复用现有 CSS 变量
- Performance constraints: 技术评价同步返回，学术评价异步执行；总览只加载最新摘要
- Compatibility constraints: PostgreSQL 结构化文档 JSON 为唯一可写权威；SQLite 默认禁止协作写入。仅允许经显式运维标志执行一次性、可审计的历史权威源迁移；Markdown 投影继续服务 OpenClaw、知识库和质量检查；原始 Markdown 与 Word 永不覆盖
- Compatibility constraints: PPTX 原稿仍是交付文件，第一阶段 PPT 人机双写继续写入结构化联动清单；文档-PPT 关系不得仅依赖前端状态
- Compatibility constraints: 旧 `mode=document|presentation|linked` 链接映射为工作台预设；AI 窗口不得通过隐藏 Tiptap 或 PPT 组件模拟
- Test/screenshot expectations: 相关 Vitest、后端段落并发与往返测试、图表版本/冲突/引用测试、类型检查、生产构建，以及 3021 桌面和 iPad 视觉验收

## Open questions
- [ ] 第二阶段是否引入多人实时协作与离线合并；当前明确限定为一个人工用户与多个 AI 智能体。
- [ ] 第二阶段把章节标题匹配迁移为稳定 `section_id/block_id ↔ slide_id/element_id` 映射，并保留标题匹配作为只读兼容。
- [ ] 第四阶段确定 PPT 元素级编辑模型和 PPTX 回写适配器；第一阶段不承诺浏览器内直接修改 PPTX 视觉元素。

## Doctoral Thesis Three-Edition Governance
- 项目级论文世代仍按第一版、第二版、第三版治理。第三版处于正文升级窗口时，允许同时显示“当前写作稿”和“冻结交付基线”两条记录；v34 完成正式交付冻结后再收拢为单一第三版入口。
- 第一、二版是只读历史基线；第二版 Word 正式母稿只用于结构、过渡与学术叙事风格校准。
- 第三版 v34（`doc-0cdb6e81aebb`）是当前唯一可写正文权威，PostgreSQL 结构化 JSON 修订 5 为当前起点；v33（`doc-15def56e2401`）已转为只读冻结交付基线。
- v25 Word 只选择性向 v34 提供中英文摘要、关键词、封面元数据和排版模板。正文差异保留在审阅报告中，不允许整篇回灌覆盖 v34 的七章重构。
- v34 在人工确认正文冻结前保持 `delivery_role=candidate`，不进入正式交付包；v33/v25 Word/PDF 继续保留为可回退交付物。
- PPT、Word、PDF是对应正文版本的交付材料，不计为新的论文版本；交付材料在独立区域管理。
- 当前答辩 PPT 仍是 v25 内容快照，结构目标已指向 v34，但必须显示 `stale/待同步`，不得标记为与 v34 对齐。
- 第三版内部修订比对以当前权威为基线；章节衔接与第3至第5章接口契约必须围绕 `MissionInput → EvaluationState → PlanSolution → TaskHandoff → TaskPolicySet → PolicyDecision → CommandBundle → ExecutionTrace → EvaluationRecord` 组织。
- 第六章只可引用冻结实验目录中的原始记录。协议、烟测、任务内闭环和系统级统计结论必须分层标注；候选修订转为当前权威及其 Word/PDF/PPT 重新生成均需人工批准。

## Product Matrix Portfolio Governance
- Status: Draft addition, 2026-09-07.
- Evidence reviewed: `frontend-v2/src/views/Products.vue`, `frontend-v2/src/router/index.ts`, `frontend-v2/src/api/products.ts`, `backend/services/product_service.py`, live 3021 deployment, and local product outputs `知识本体智能筹划系统产品规划书_V2.0_1.9修订版.docx`, `产品规划_思路_V1.0.docx`, `案例-待整理-0901.docx`.
- Product matrix goal: `/products` is the portfolio entry led by `OpenClaw 智能体系统`, not just a registry list. It must show how platform, planning, simulation, wargame offerings, documents, cases, and running links form one product system.
- Portfolio hierarchy: core platform layer (`openclaw-3021`), planning and simulation capability layer (`ai-planning-5130`, `one-sim`), business product layer (`knowledge-ontology-planning-system`, `manual-wargame`, `digital-wargame`, `intelligent-wargame`), and delivery asset layer (plans, cases, reports, demos, screenshots, releases).
- Homepage information architecture: keep top metrics and runtime facts, then add a portfolio leadership band, modular product groups, representative image cards, latest evidence/deliverables, and a roadmap strip. The current side-by-side registry layout can remain as a management mode but should not be the default first impression.
- Product detail route: add a dedicated `/products/:productId` detail page. Product cards should navigate there; selecting in-place may remain as a compact management affordance only where useful.
- Detail page content hierarchy: identity image, one-sentence positioning, status, owner agent, system introduction, target users, scenarios, capabilities, dependencies, runtime links, repository/project links, product planning documents, accepted/pending deliverables, releases, runtime instances, and timeline.
- Evidence boundary: documents and screenshots are product evidence only after registration; `draft`, `pending_review`, `accepted`, and `rejected` states must be visibly distinct. A live URL or running process does not by itself prove product maturity.
- Document placement: local planning documents should be copied into a product asset directory such as `backend/data/product_assets/products/<product_id>/documents/<YYYY-MM-DD>/...`, registered as `document` deliverables with SHA-256 and source path metadata, then promoted through the existing deliverable review flow.
- Representative imagery: prefer real system screenshots, document cover previews, simulation/wargame screen captures, or photographed physical materials. Use generated illustrations only when no real asset exists, and label them as conceptual rather than evidence.
- Data contract extension: extend product payload metadata with `cover_image`, `short_name`, `positioning`, `target_users`, `scenarios`, `value_props`, `system_links`, `document_links`, `portfolio_group`, `display_order`, and `featured`. Prefer JSON payload fields before adding new database tables.
- `knowledge-ontology-planning-system` should be a first-class business product, not an attachment under `openclaw-3021` or `one-sim`. It depends on `openclaw-3021` for orchestration, `ai-planning-5130` for planning, and `one-sim` for simulation verification.
- `ai-planning-5130` and `one-sim` are first-class capability products in the matrix, exposed as `智能筹划系统` and `Wargame 兵棋仿真系统`. Their detail pages should include product positioning, system introduction, scenarios, value propositions, runtime links, dependencies, and authenticated `media_assets` for screenshots or videos.
- Visual language: product cards may use representative images, but the page must remain a dense operational product dashboard. Avoid marketing hero layouts, generic stock images, decorative gradients, nested cards, and one-color palettes.
- Responsive behavior: desktop uses grouped product modules plus a right-side evidence/roadmap area; tablet and narrow screens stack modules and keep card actions accessible without hover.
- Implementation acceptance: verify `/products` renders portfolio groups, `/products/:productId` opens a detail page, registered documents show with review state and hash, system links are clickable, and screenshots at desktop and tablet widths show no text overlap.
