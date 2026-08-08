# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-08-08
- Primary product surfaces: 3021 文档管理、协同工作台、概念与论证、参考文献、排版与交付、项目中枢、数据管理
- Evidence reviewed: `frontend-v2/src/views/WritingWorkspace.vue`、`frontend-v2/src/components/writing/WritingLinkedWorkspace.vue`、`frontend-v2/src/components/writing/WritingWorkspacePane.vue`、`frontend-v2/src/components/writing/WritingAiPane.vue`、`frontend-v2/src/components/writing/CollaborativeWritingEditor.vue`、`frontend-v2/src/components/writing/PresentationWorkspace.vue`、WorkBuddy 人机双写参考截图

## Brand
- Personality: 严谨、克制、面向研究与交付
- Trust signals: 明确版本、真实数据来源、同步状态、可追溯记录
- Avoid: 装饰性大卡片、低信息密度、用颜色替代文字状态、项目名称特判

## Product goals
- Goals: 让用户快速判断正文与 PPT 现状、目标差异、写作进度和交付风险，并在同一工作面完成文档、PPT 与 AI 的组合协作
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
- 工作台提供两个可调窗口，每个窗口独立选择文档、PPT 或 AI，并支持写作、PPT 制作、文档校验三种预设
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
- New/changed components: `WritingWorkspace` 工作区一级导航、`WritingLinkedWorkspace` 双窗状态与布局控制器、`WritingWorkspacePane` 可组合窗口、`WritingAiPane` 独立会话窗口、`DocumentEvaluationPanel`、`CollaborativeWritingEditor`、`PresentationWorkspace`
- Variants and states: saved、dirty、saving、error；queued、running、review_required、partially_applied、applied、conflicted、failed、cancelled；missing、insufficient、sufficient；candidate、ready、approved、published
- Token/component ownership: 主题变量由全局样式维护，页面只负责布局

## Accessibility
- Target standard: 保持现有语义和键盘可用性
- Keyboard/focus behavior: 章节进展继续使用原生 `button`；目录细目继续使用 `details/summary`；分隔线提供可聚焦拖动控制，窗口操作不依赖悬停
- Contrast/readability: 复用现有高对比主题变量
- Screen-reader semantics: 保留标题层级、section、aside 和状态文本
- Reduced motion and sensory considerations: 不新增依赖动画的信息表达

## Responsive behavior
- Supported breakpoints/devices: 桌面与 iPad；人机双写和联动工作台在 1180px 以下切换为单窗口标签页
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
- Framework/styling system: Vue 3、TypeScript、Element Plus、Tiptap Vue 3、页面 scoped CSS
- Design-token constraints: 不新增颜色常量，优先复用现有 CSS 变量
- Performance constraints: 技术评价同步返回，学术评价异步执行；总览只加载最新摘要
- Compatibility constraints: PostgreSQL 结构化文档 JSON 为唯一可写权威；SQLite 仅在显式测试模式允许协作写入；Markdown 投影继续服务 OpenClaw、知识库和质量检查；原始 Markdown 与 Word 永不覆盖
- Compatibility constraints: PPTX 原稿仍是交付文件，第一阶段 PPT 人机双写继续写入结构化联动清单；文档-PPT 关系不得仅依赖前端状态
- Compatibility constraints: 旧 `mode=document|presentation|linked` 链接映射为工作台预设；AI 窗口不得通过隐藏 Tiptap 或 PPT 组件模拟
- Test/screenshot expectations: 相关 Vitest、后端段落并发与往返测试、类型检查、生产构建，以及 3021 桌面和 iPad 视觉验收

## Open questions
- [ ] 第二阶段是否引入多人实时协作与离线合并；当前明确限定为一个人工用户与多个 AI 智能体。
- [ ] 第二阶段把章节标题匹配迁移为稳定 `section_id/block_id ↔ slide_id/element_id` 映射，并保留标题匹配作为只读兼容。
- [ ] 第四阶段确定 PPT 元素级编辑模型和 PPTX 回写适配器；第一阶段不承诺浏览器内直接修改 PPTX 视觉元素。
