# 3021 Word 人机双写阶段 1：编辑内核 PoC 入口

## 决策

首选 Microsoft Word Add-in 作为 PoC 编辑内核。Word 继续负责 DOCX 原生对象、排版、分页、字段和最终渲染；3021 负责项目上下文、AI 提案、证据、风险判断、修订和审批。

ONLYOFFICE 作为浏览器协作对照组，不在阶段 1 开始前宣称与 Word/WPS 视觉等价。WorkBuddy 的内部实现未经公开证据确认，不作为技术契约。

## 选择理由

- Microsoft 官方 Word JavaScript API 可直接操作 `Document`、`Range`、`ContentControl`、`Table` 等 Word 原生对象。
- 内容控件可承载 3021 稳定块 ID；选区和范围可用于最小粒度读取、插入和替换。
- Word API 提供内容变化事件与修订相关对象，但部分事件或桌面能力属于特定 requirement set 或 preview，PoC 必须运行时探测，不得假设所有客户端都支持。
- 阶段 0 的一次受限对照中，LibreOffice 对论文金标产生 `121 -> 148` 页差异，且多种请求字体发生替换；该结果不能作为论文级视觉权威，也不单独证明字体替换是唯一原因。

官方依据：

- https://learn.microsoft.com/en-us/office/dev/add-ins/word/word-add-ins-core-concepts
- https://learn.microsoft.com/en-us/office/dev/add-ins/word/word-add-ins-events
- https://learn.microsoft.com/en-us/javascript/api/word/word.document?view=word-js-preview
- https://api.onlyoffice.com/docs/plugins/interacting-with-editors/document-api/Methods/

## 最小架构

```text
Microsoft Word DOCX
  -> Word Add-in task pane
  -> selection/range/content-control adapter
  -> 3021 context + evidence + WritingChangeSet API
  -> preview proposal in task pane
  -> user accepts/rejects
  -> Word native operation + tracked review metadata
  -> save candidate copy
  -> Phase 0 structural audit + Word-native PDF visual audit
```

## PoC 只做四件事

1. 读取当前选区、所在段落、样式、内容控件 ID 和文档指纹。
2. 请求 3021 生成带基础修订、幂等键和证据引用的最小 `WritingChangeSet`。
3. 在任务窗格显示原文、建议、证据和风险；经人工接受后只修改目标 Range。
4. 将结果保存到候选副本，运行阶段 0 审计和 Word 原生 PDF 对照，原始金标保持只读。

## 硬门

- 不依赖全量 DOCX -> Markdown -> DOCX 往返。
- 旧选区或基础修订变化时拒绝静默写入。
- 公式、图片、题注、交叉引用、浮动对象附近的修改失败时必须回退为只读提案。
- AI 修改必须可撤销，并能映射到 3021 `WritingChangeSet`。
- 课程金标和论文金标的无操作打开/保存均不得出现 Word 修复提示。
- 论文候选的 Word 原生 PDF 页数必须保持 121；仅页数相同仍不代表通过，还要做全页渲染差异检查。

## 首轮验收场景

1. 普通段落中替换一句话。
2. 标题下插入一段并保持样式和分页控制。
3. 表格单元格内修改文本，不重建表格。
4. 公式前后修改文字，OMML 数量和哈希保持。
5. 图片题注附近修改文字，图片关系、题注与字段保持。
6. 人工先改同一段后再接受旧 AI 提案，系统必须报冲突。
7. 接受后执行 Word 撤销，正文和 3021 状态能够解释该撤销。

## 停止条件

任一金标出现 Word 修复提示、复杂对象丢失、不可解释分页变化、旧提案覆盖新人工内容，或修改无法进入原生撤销/审阅链，则阶段 1 不进入生产集成，转为对照 ONLYOFFICE 或收窄可编辑对象范围。

## 2026-08-24 执行状态

已完成候选模式后端桥接、Word任务窗格、HTTPS开发服务、旁加载清单、唯一块匹配、段落/文档指纹、短时应用令牌和幂等回执。候选回执不推进结构化正文修订。

自动验收结果和可验证哈希见 `docs/review/word-cowriting-phase1-poc-result.json`。真实Word交互验收仍停在开发证书信任和Word安全重启门，未强制修改钥匙串或结束当前Word进程。
