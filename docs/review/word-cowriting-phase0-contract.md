# 3021 Word 人机双写阶段 0：金标与验收契约

## 目标

本阶段只建立真实 DOCX 金标、自动化结构审计和后续编辑内核 PoC 的验收门。不替换编辑器，不迁移正文权威，不修改生产 DOCX、PostgreSQL 或 3021 文档状态。

## 金标边界

1. `course-plan-original-20h` 是课程教学计划的内容与版式参考。其路径和 SHA 已由项目 manifest、`documents.json` 和恢复脚本共同登记。
2. `thesis-v25-r4.1-layout-reference` 只冻结博士论文 Word 版式和复杂对象基线。它不是当前博士论文结构化正文权威。
3. 同名但 SHA 不同的教学库副本，以及论文 `_workspace/layout/staging` 候选，均不得自动替换金标。

权威路径和哈希集中存放在：

`specs/active/word-cowriting-phase0-gold-documents.json`

## 自动化指标

`backend/services/docx_gold_baseline.py` 直接读取 DOCX ZIP/OOXML，不调用 `/workspace`、不导入正文、不生成预览。审计包括：

- 文件 SHA、ZIP CRC、必要 OOXML parts；
- 正文文本哈希和结构哈希；
- 标题层级与顺序、段落样式使用；
- 表格、行列、横向/纵向合并；
- 图片、浮动/行内对象、OLE/embedding；
- 公式、题注、书签、内容控件、超链接；
- TOC/REF/SEQ/PAGE 等字段；
- 公式内容、字段指令、页眉页脚、脚尾注、样式、编号、关系和内容控件的语义哈希；
- 脚注、尾注、批注、修订；
- 分节、页面尺寸、页边距、页眉页脚；
- Word/WPS 保存的页数、字数和应用信息。

## 后续编辑内核必须通过的场景

1. **无操作往返**：打开并保存，不允许丢对象、改变可见正文或出现 Word/WPS 修复提示。
2. **选区文字修改**：仅改变选区，保留段落样式、编号、题注与引用关系。
3. **表格单元格修改**：AI 获得原生单元格对象，不把整表降级为 Markdown。
4. **标题与段落插入**：插入后目录结构、分页控制和样式 ID 正确。
5. **图片与题注**：图片关系、锚定方式、题注和交叉引用保持可用。
6. **公式邻接编辑**：修改公式前后文字时，OMML/嵌入公式不得被文本化。
7. **撤销与审阅**：AI 修改进入编辑器原生撤销栈，并能映射到 `WritingChangeSet`。
8. **人机并发**：旧选区不能静默覆盖人工新修改，必须拒绝、重基或进入审阅。

## 验证命令

```bash
cd /Users/apple/工作桌面/Workspace/agent-system/backend
venv/bin/python -m pytest -q tests/test_docx_gold_baseline.py
venv/bin/python scripts/audit_docx_gold_baseline.py \
  --manifest ../specs/active/word-cowriting-phase0-gold-documents.json \
  --output ../docs/review/word-cowriting-phase0-baseline.json \
  --verify
```

只读 LibreOffice 渲染对照记录在：

`docs/review/word-cowriting-phase0-render-observation.json`

## 阶段 0 通过条件

- 新增单元测试全部通过；
- 两个金标文件哈希和 OOXML 包完整性通过；
- 基线 JSON 可重复生成，输入未变时 `report_sha256` 不变；
- 缺失或格式错误的期望 SHA 必须失败，验证失败不得覆盖上一份有效基线；
- 没有生产正文、数据库、manifest 或 Office 文件被修改；
- 阶段 1 只在该契约上评估腾讯文档/WebOffice、ONLYOFFICE 或 Word Add-in，不再以 Tiptap 页面相似度替代 DOCX 保真。

## 尚未证明的能力

阶段 0 的 OOXML 结构审计不等于 Microsoft Word/WPS 视觉一致，也不证明编辑器能可靠保存复杂对象。原生 Word/WPS 重开、页面渲染差异和选区操作属于阶段 1 PoC 的硬门。

本次受限的 LibreOffice 26.2.0.3 对照中，课程原版由 WPS 记录的 23 页仍渲染为 23 页；论文 R4.1 由 WPS 记录的 121 页被渲染为 148 页，且字体探测显示多种请求字体发生替换。该观察不证明字体替换是唯一原因，但足以表明这次 LibreOffice 结果不能作为论文级版式权威或视觉验收依据。
