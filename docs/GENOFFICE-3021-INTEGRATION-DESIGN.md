# GenOffice × 3021 文档引擎集成详细设计

**版本**: v0.1  
**日期**: 2026-09-25  
**状态**: 已批准；Phase G1 已作为只读试点部署，G1.1 兼容性恢复与重复性验收方案已进入只读准备。官方应用 release 为 `v0.10.1038`，其 bundled CLI/MCP server 报告 `0.10.0`；课程金标已通过读取、检查和第 1 页渲染，论文金标在第 1 页渲染返回 `conversion_failed`。因此正式“双金标”退出条件未通过，G2 候选写入仍被阻断。主机 launchd 环境下已通过严格 `codesign`、Gatekeeper 与 stapled-notarization 校验；此前沙箱内诊断不能替代主机验证。  
**作用域**: 3021 写作工作台、文档候选链、Office 校样、原生 Office 编辑、文档引擎升级治理  
**不包含**: Phase G1 不修改生产数据、不新增数据库迁移、不改变正文权威、不替换现有 Word Add-in；Phase G2 及以后阶段须另行批准

---

## 1. 决策摘要

3021 以 **GenOffice Sidecar 文档引擎 + 可选外部桌面编辑器** 的方式接入 GenOffice，不复制或嵌入 GenOffice 的 Electron/React 界面，不让浏览器直接访问 GenOffice MCP，不让 GenOffice 成为第二个正文权威。

确定以下设计基线：

1. 3021 的 Vue/Tiptap 写作界面继续承担结构化正文编辑、AI 提案、证据、审批和并发控制。
2. GenOffice 通过本机 MCP HTTP/CLI 适配层承担 DOCX/PPTX/XLSX/PDF 的读取、窄修改、检查、渲染与转换。
3. 所有 GenOffice 写操作只作用于候选副本；正式文件和 PostgreSQL 正文均不得被旁路覆盖。
4. 草稿阶段以 PostgreSQL `tiptap-json-v1` 为正文权威；进入正式排版阶段后，DOCX 可以成为版式权威，但正文语义修改仍必须通过 `WritingChangeSet` 回流。
5. 官方版本更新采用“自动发现、隔离验证、人工晋升、可回退”的受控策略，不允许新版本未经金标验证直接获得写权限。
6. Microsoft Word Add-in 保留为 Word 原生对象与最终视觉兼容基准；GenOffice 先作为并行候选内核，不立即替代 Word Add-in。

### 1.1 明确不采用的方案

- 不将 GenOffice 源码复制进 `frontend-v2`。
- 不通过 iframe 嵌入 GenOffice 桌面编辑器。
- 不让前端浏览器直接连接 `127.0.0.1:3093/3094`。
- 不将 GenOffice Git 仓库作为 3021 的 Git subtree/submodule 并跟随 `main` 自动构建生产版本。
- 不执行全量 `DOCX -> Markdown/Tiptap -> DOCX` 往返后覆盖正式文件。
- 不把官方自动更新等同于生产自动启用。

---

## 2. 背景与现状

### 2.1 3021 当前文档能力

当前 3021 已经具备：

- Vue 3 + Tiptap 协同富文本编辑器；
- 稳定 `block_id`、块修订、文档修订和 SHA-256；
- 人工/AI 修改提案、风险分级、证据绑定和审批；
- PostgreSQL 持久化的写作任务与变更记录；
- DOCX 导入、导出、格式校样和版本管理；
- WPS/LibreOffice PDF 预览；
- Word Add-in 候选桥接、短时应用令牌、幂等回执和源文件指纹；
- 两份真实 DOCX 金标及 OOXML 结构审计。

现有关键约束：

- `writing_document_states.schema_version=tiptap-json-v1`；
- 前端保存必须携带 `base_document_revision`；
- 同段变化不得被静默覆盖；
- 正式 Word/PDF 只能从已审批修订生成；
- DOCX 金标要求无操作往返、复杂对象保持、可撤销与可解释。

### 2.2 GenOffice 可利用能力

GenOffice 当前提供三种进程级入口：

| 入口 | 作用 | 3021 用途 |
|---|---|---|
| `genoffice` CLI | 本机文件读取、修改、检查、渲染、转换 | 调试与应急回退 |
| `genoffice mcp` stdio | 由单个客户端管理进程 | 单元测试和本地开发 |
| `genoffice mcp --http` | 独立 Streamable HTTP MCP 服务 | 3021 后端正式接入首选 |
| GenOffice 应用内 `127.0.0.1:3093/mcp` | 控制可见桌面编辑器会话 | 后期“外部原生编辑”能力 |

GenOffice 没有面向 Vue/浏览器的稳定 Web 编辑器 SDK。应用内 HTTP 服务是 MCP 工具接口，不是可嵌入页面。因此 UI 复用和引擎复用必须分开设计。

### 2.3 G1 当前环境事实（2026-09-25）

3021 所在 Mac mini 已完成以下只读试点部署：

- 已安装官方 `/Applications/GenOffice.app` release `v0.10.1038`；bundled CLI/MCP server 的协议版本为 `0.10.0`，两者分别接受版本门管理；
- `127.0.0.1:3094/mcp` 由独立 launchd Sidecar 提供 HTTP MCP，健康端点正常；
- 3021 已有只允许 `docs_read`、`docs_check`、`render` 的 MCP 适配器与写作工作台 Office 校样入口；
- 3093 visible MCP 不属于 G1，也未被浏览器或 3021 作为编辑接口使用。

这些事实只证明 G1 的本机只读试点已部署，不证明复杂 DOCX 的渲染兼容性，也不构成 G2 写入授权。

---

## 3. 目标与非目标

### 3.1 目标

1. 在不改变正文权威的前提下，提高 DOCX/PPTX/XLSX/PDF 的本地处理能力。
2. 在 3021 写作工作台中提供“结构化编辑、Office 校样、原生编辑”连续工作流。
3. 让 3021 的智能体能通过结构化工具读取和窄修改真实 Office 文件。
4. 为每次引擎调用保留版本、输入输出哈希、操作、检查结果和人工决策。
5. 官方版本更新后自动触发兼容验证，并在通过前保持写能力关闭。
6. 保留 Word Add-in 与现有导出链作为独立对照和回退路径。

### 3.2 非目标

1. 不在浏览器中复刻 Word/GenOffice 的精确分页编辑体验。
2. 不在本阶段实现多人实时 Office 协同、实时光标或离线合并。
3. 不承诺 GenOffice 与 Word/WPS 对所有复杂文档完全视觉等价。
4. 不允许 GenOffice 自带 AI 绕开 3021 的证据、风险和审批策略修改正式文档。
5. 不将 Office 二进制文件内容存入 PostgreSQL 大字段。
6. 不把 3021 改造成 GenOffice 的分发器或二次安装器。

---

## 4. 总体架构

```text
┌───────────────────────────────────────────────────────────────┐
│ 3021 Vue 写作工作台                                           │
│                                                               │
│ 结构化编辑 │ Office 校样 │ 外部原生编辑 │ 版本/差异/审批       │
└───────────────────────────────┬───────────────────────────────┘
                                │ 仅访问 3021 API
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ 3021 FastAPI                                                  │
│                                                               │
│ Writing API ─ Candidate Service ─ GenOffice Adapter           │
│     │              │                 │                         │
│     │              │                 ├─ capability/version gate│
│     │              │                 ├─ MCP client             │
│     │              │                 └─ CLI fallback           │
│     │              │                                           │
│     ├─ WritingChangeSet / WordRelease / WorkRun                │
│     └─ gold audit / fidelity audit / visual comparison         │
└───────────────────────────────┬───────────────────────────────┘
                                │ Bearer token + localhost only
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ GenOffice Sidecar                                              │
│                                                               │
│ 3094: headless MCP HTTP（G1 只读；G2+ 才允许候选文件操作）       │
│ 3093: app-visible MCP（可选，仅外部编辑阶段）                   │
│                                                               │
│ docs_read/apply/check/render/convert + sheet/slides tools      │
└───────────────────────────────┬───────────────────────────────┘
                                │ 只读源 + 候选副本
                                ▼
┌───────────────────────────────────────────────────────────────┐
│ Managed Office Workspace                                       │
│ source/ candidate/ render/ audit/ receipt/                     │
└───────────────────────────────────────────────────────────────┘
```

### 4.1 信任边界

- 浏览器只信任 3021 API，不持有 GenOffice MCP token。
- GenOffice Sidecar 只监听 `127.0.0.1`，不直接暴露到局域网。
- 3021 后端负责文件授权、项目归属、候选隔离、操作限额和结果审计。
- GenOffice 输出永远先进入候选区，不能直接成为正式交付物。
- 正式晋升由 3021 数据库事务记录，不由文件系统移动本身代表。

---

## 5. 部署设计

### 5.1 推荐部署拓扑

3021 与 GenOffice Sidecar 同机运行在 Mac mini：

| 服务 | 监听 | 网络暴露 | 生命周期 |
|---|---:|---|---|
| 3021 FastAPI | `0.0.0.0:3021` | 现有受控网络 | 现有 launchd |
| GenOffice headless MCP | `127.0.0.1:3094` | 仅本机 | 独立 launchd，单实例 |
| GenOffice visible MCP | `127.0.0.1:3093` | 仅本机 | GenOffice 应用打开且用户启用时 |

正式环境不使用 `--host 0.0.0.0`。远端浏览器或其他设备需要 Office 能力时，必须通过 3021 FastAPI 转发业务级请求。

### 5.2 Sidecar 启动契约

G1 已提供不含密钥的 launcher/plist 模板：`backend/scripts/run_genoffice_mcp.sh` 与
`backend/ai.openclaw.genoffice-mcp.plist`。其实际启动命令为：

```bash
GENOFFICE_MCP_TOKEN=<secret-from-protected-environment> \
genoffice mcp --http 3094 \
  --host 127.0.0.1
```

约束：

- token 使用 GenOffice 官方支持的 `GENOFFICE_MCP_TOKEN` 环境变量，来自受限环境文件或系统凭据，不出现在进程参数中，也不写入 Git、日志或数据库明文；
- HTTP 模式首期不设置 `GENOFFICE_ALLOWED_ROOTS`，使工具限制在 Sidecar 自己的会话文件区；3021 通过受认证的文件上传/下载传递输入和接收输出；
- HTTP 模式与适配器不向 Sidecar 传递项目目录、知识库或正式文档路径；G1 的文件工具只接触受认证上传的会话文件。该约束是进程/API 边界而非 macOS 沙箱：同一登录账户下的受损进程仍可读取该账户本身有权限读取的文件；
- Sidecar 使用专用的 `0700` HOME、TMP、Electron user-data 和 `0600` 侧车日志，配合 `umask 077` 与 `env -i` 最小环境，不继承 3021 的数据库 URL、JWT、云端密钥或代理变量；
- 启动前校验实际应用的可执行路径、`CFBundleIdentifier=com.genoffice.app`、签名 `TeamIdentifier=TC7CATC2Z2` 和 stapled notarization ticket。在 `codesign`/`spctl` 已能通过 Apple 系统应用基线的主机上，launcher 还必须同时通过 `codesign --verify --deep --strict` 与 `spctl --assess --type execute`；
- launcher 在宿主 launchd 环境中必须同时通过严格签名、Gatekeeper 和公证票据检查；绝不通过关闭 Gatekeeper、`spctl --master-disable`、移除 quarantine 或手动改签继续；
- 3021 不依赖 shell `PATH` 猜测，优先读取固定配置或 GenOffice launcher record；
- G1 的 3021 launchd 部署固定为单个 Uvicorn worker，并使用一个独立 Sidecar；当前进程内重任务槽仅在此形态下有效，扩为多 worker 前必须改用跨进程租约/队列，且不得让每个 worker 各自启动 Electron/Node 进程；
- G1 的读取、检查、首屏渲染均不创建 WorkRun、候选或持久化产物；幂等/重试语义从 G2 开始由 WorkRun 接管。所有 G1 状态、`check` 和 `proof` 路由在当前没有项目 ACL 的系统中仅向 `admin` 角色开放；任何多用户/多管理员部署前必须接入项目成员 ACL、配额与限流。

### 5.3 进程健康状态

统一暴露以下状态：

```text
not_installed
stopped
starting
ready_read_only
ready_write
version_unverified
degraded
blocked
```

`ready_read_only` 表示可以读取、检查和渲染，但版本或金标门未通过，不可执行写操作。

### 5.4 并发、超时与背压

3021 当前存在受控多 Worker，不能使用 Python 进程内锁保护 Office 文件。锁与队列状态必须由 PostgreSQL/既有 WorkRun 真相层承担。

并发规则：

- 同一个 `candidate_id` 同时最多一个写作业或外部编辑会话；
- 同一个 `document_id` 可以存在多个只读候选，但同时只能有一个候选进入 `promoting`；
- 读取、检查和渲染可以排队，不得越过同候选尚未完成的写操作；
- PDF/页面渲染、格式转换等重任务设置独立全局并发上限，首期默认串行，实测后才能提高；
- Phase G1 的实际 launchd 配置固定为单个 Uvicorn worker，因此当前进程内的单重任务槽只在该部署形态下有效；切换到多 worker 前必须先改为跨进程租约/队列；
- 租约过期后先重新核对输入/输出 SHA 和 Sidecar 会话状态，不盲目重放写操作；
- 队列满时返回明确的 `429/office_engine_busy`，不无限堆积。

超时分为连接、工具执行和业务作业三层。具体秒数在 Phase G1 基准测试后写入运行配置；任何超时都必须保留候选和未知完成状态，不能把“客户端超时”等同于“工具没有写文件”。

---

## 6. 前端交互设计

### 6.1 文档窗口模式

将现有文档窗口的：

```text
编辑视图 | WPS预览
```

演进为：

```text
结构化编辑 | Office校样 | 原生编辑
```

#### 结构化编辑

- 继续渲染 `CollaborativeWritingEditor`；
- 保留当前自动保存、块级冲突、AI 提案、证据和审批；
- 显示当前 `document_revision` 与最近 Office 候选状态；
- 正式排版冻结后，结构化编辑根据文档策略切换为只读或“仅生成提案”。

#### Office 校样

- 不嵌入 GenOffice UI；
- 展示 GenOffice 生成的 PDF 或逐页 PNG；
- 支持页码导航、缩放、联系表和最新/基线对照；
- 显示引擎版本、输入 SHA、输出 SHA、检查告警和生成时间；
- 页面上提供“重新生成校样”“运行结构检查”“查看差异”。

#### 原生编辑

- 首次进入必须说明“将在独立 GenOffice 窗口中编辑候选副本”；
- 生成候选副本后才允许打开；
- 不允许打开正式母稿为可写文件；
- 显示会话状态：未启动、编辑中、已保存、文件变化、待导入、已过期；
- 保存候选后，用户回到 3021 执行“读取变更”；
- 3021 完成差异、审计和渲染后才显示“批准晋升”。

### 6.2 状态文案

必须使用文字与颜色共同表达：

| 状态 | 文案 | 行为 |
|---|---|---|
| `engine_unavailable` | Office 引擎不可用 | 保留 Tiptap 与既有预览 |
| `candidate_generating` | 正在生成候选副本 | 禁止重复提交 |
| `candidate_ready` | 候选已生成，尚未审阅 | 允许校样/打开 |
| `editing_external` | 正在 GenOffice 中编辑 | 3021 不覆盖候选 |
| `audit_required` | 文件已变化，等待检查 | 禁止晋升 |
| `audit_failed` | Office 兼容检查未通过 | 只允许下载/回退 |
| `review_required` | 检查通过，等待人工确认 | 显示差异和证据 |
| `promoted` | 已晋升为指定版本 | 写入 WordRelease/版本记录 |
| `stale` | 正文或源文件已更新 | 候选作废或重基 |

### 6.3 用户操作边界

- 页面离开前必须 flush 当前 Tiptap 草稿。
- 生成 Office 候选时锁定输入修订，不锁定用户继续编辑其他章节。
- 输入修订后续变化时，候选自动标记 `stale`，但不删除。
- 只有管理员/当前单用户显式点击才能晋升。
- “重新生成”创建新候选，不覆盖旧候选及其审计记录。

---

## 7. 后端模块设计

### 7.1 模块职责

#### `GenOfficeClient`

- 封装 MCP Streamable HTTP；
- 完成初始化、会话、工具调用、超时、取消和错误规范化；
- 不理解 3021 项目、文档或审批语义；
- 仅接收受控文件 URL/路径和标准工具参数。

#### `GenOfficeAdapter`

- 将 3021 业务动作翻译为 GenOffice 工具调用；
- 处理 `docs_read/apply/check/render/convert`；
- 规范化 GenOffice 版本差异和错误；
- 执行能力探测与最小版本检查；
- 禁止未知工具或未批准操作透传。

#### `OfficeCandidateService`

- 创建候选工作区与只读源快照；
- 计算和验证输入、输出 SHA；
- 管理候选状态机；
- 调用既有金标/内容保真/视觉审计；
- 生成差异、收据和晋升记录；
- 与 `WritingChangeSet`、`WritingWordRelease`、WorkRun 关联。

#### `OfficeEngineReleaseGate`

- 保存已发现、已验证、已启用、已阻断版本；
- 运行固定兼容矩阵；
- 控制读/写能力；
- 记录批准人、时间、测试报告和回退版本。

#### `OfficeWorkspaceStore`

- 管理候选文件、预览、审计 JSON 和回执；
- 防止目录穿越与符号链接逃逸；
- 原子写入 manifest；
- 按保留策略清理未晋升候选。

### 7.2 规划文件位置

G2+ 预计新增或修改以下文件；本轮不执行这些变更：

```text
backend/services/genoffice_client.py
backend/services/genoffice_adapter.py
backend/services/office_candidate_service.py
backend/services/office_engine_release_gate.py
backend/routers/genoffice_router.py
backend/models/office_engine.py
backend/alembic/versions/<revision>_office_engine_integration.py
backend/tests/test_genoffice_client.py
backend/tests/test_genoffice_adapter.py
backend/tests/test_office_candidate_service.py
backend/tests/test_office_engine_release_gate.py

frontend-v2/src/api/genoffice.ts
frontend-v2/src/components/writing/OfficeProofView.vue
frontend-v2/src/components/writing/OfficeNativeSession.vue
frontend-v2/src/test/OfficeProofView.spec.ts
frontend-v2/src/test/OfficeNativeSession.spec.ts

backend/ai.openclaw.genoffice-mcp.plist
docs/runbooks/GENOFFICE-OPERATIONS.md
```

### 7.3 Phase G1 实现文件与边界

G1 已实际新增或修改：

```text
backend/services/genoffice_readonly_service.py
backend/routers/writing_workspace.py
backend/scripts/run_genoffice_mcp.sh
backend/ai.openclaw.genoffice-mcp.plist
backend/.env.example
backend/tests/test_genoffice_readonly_service.py
frontend-v2/src/api/writing.ts
frontend-v2/src/components/writing/WritingWorkspacePane.vue
frontend-v2/src/test/WritingWorkspacePaneFidelity.spec.ts
```

G1.1 仅新增本地重复性证据准备：

```text
backend/scripts/audit_genoffice_g11_repeatability.py
backend/scripts/evaluate_genoffice_g11_gate.py
backend/tests/test_audit_genoffice_g11_repeatability.py
docs/review/genoffice-phase-g11-upstream-compatibility.json
```

实现使用 GenOffice 公开端到端测试所覆盖的 Streamable HTTP JSON-RPC
`initialize → notifications/initialized → tools/list → tools/call` 契约（协议版本
`2024-11-05`），避免引入第二个 MCP 运行时。适配器只允许
`docs_read`、`docs_check`、`render` 三个工具；即使 Sidecar 声明
`docs_apply`，3021 也会对前端报告为关闭并在客户端拒绝调用。

G1 仅接受已登记的 `documents/<id>/source/original.docx`：校验其路径、符号链接、
压缩包条目数、未压缩大小和 DOCX 必需部件后，以字节上传至 Sidecar 会话文件区。
校样只下载第 1 页 PNG 至内存响应；不写候选、项目工作区、数据库或正式文件。渲染时，
headless wrapper 仅在私有 `GENOFFICE_SIDECAR_HOME/electron-user-data/originals/` 下创建按输入 SHA 命名的
源文件副本；无论校样成功或失败，服务均在 `finally` 中移除该副本。会话关闭会清除会话 scratch 输出；
官方 HTTP FileStore 中的上传原件可保留约一小时，因此 G1 将其置于专用 `0700` TMP 目录并以 Sidecar
重启作为应急清理手段，不把“关闭会话”描述为立即删除上传原件。上述私有目录降低暴露面，但同一 macOS
登录账户的边界仍不是 OS 级隔离。

既有修改点：

```text
backend/api_registry.py
backend/routers/writing_workspace.py
frontend-v2/src/components/writing/WritingWorkspacePane.vue
frontend-v2/src/api/writing.ts
start.sh
```

---

## 8. 数据权威与候选生命周期

### 8.1 权威划分

| 阶段 | 语义正文权威 | 版式权威 | GenOffice 权限 |
|---|---|---|---|
| 研究/草稿 | PostgreSQL Tiptap JSON | 无或参考模板 | 读、检查、生成候选 |
| 人机双写 | PostgreSQL Tiptap JSON + WritingChangeSet | 候选 DOCX | 仅修改候选 |
| 正式排版 | 已审批正文修订 | 指定 DOCX 候选/母稿 | 窄修改候选，禁止全量重建覆盖 |
| 已发布 | 冻结 WordRelease | 冻结 DOCX/PDF | 只读检查与渲染 |

任何阶段都不存在“GenOffice 内存状态自动成为 3021 权威”的路径。

### 8.2 候选目录

逻辑目录定义：

```text
<managed-office-root>/
  <project_id>/
    <document_id>/
      <candidate_id>/
        manifest.json
        source/input.docx
        candidate/output.docx
        render/pages/*.png
        render/preview.pdf
        audit/genoffice-check.json
        audit/3021-fidelity.json
        audit/gold-baseline.json
        audit/visual-diff.json
        receipt/operations.json
        receipt/result.json
```

约束：

- `source/input.docx` 创建后只读；
- `candidate/output.docx` 只能由一次受控作业或一个外部编辑会话持有写租约；
- manifest 使用临时文件 + rename 原子写入；
- 数据库只保存相对路径、SHA、大小、MIME、状态和关联 ID；
- 默认不将候选目录放入 Git；
- 未晋升候选建议保留 30 天，已晋升候选随版本记录长期保留；最终期限由评审决定。

### 8.3 候选状态机

```text
requested
   │
   ▼
snapshotting ──失败──▶ failed
   │
   ▼
ready ───────────────▶ editing_external
   │                        │
   │ apply ops              │ saved
   ▼                        ▼
mutated ─────────────────▶ audit_required
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
           audit_failed               review_required
                │                           │
                ├─重新生成/放弃              ├─reject──▶ rejected
                │                           └─approve─▶ promoting
                │                                         │
                └─────────────────────────────────────────▶│
                                                          ▼
                                                       promoted
```

任意非终态在输入正文修订或源文件 SHA 变化后转为 `stale`。`stale` 候选不得晋升，只能查看、下载、放弃或在明确操作下重基。

---

## 9. 块映射与并发控制

### 9.1 映射问题

3021 使用稳定 `block_id` 和 `block_revision`；GenOffice 使用 DOCX 块索引、对象 ID、原始 XML 锚点和位置性修订。Office 编辑可能改变索引，因此不能将 `docxIndex` 当作永久主键。

### 9.2 映射清单

每个候选保存一份绑定清单：

```json
{
  "schema": "openclaw.genoffice-block-binding.v1",
  "project_id": "...",
  "document_id": "...",
  "document_revision": 42,
  "source_sha256": "...",
  "engine_version": "0.10.1038",
  "bindings": [
    {
      "block_id": "blk-...",
      "block_revision": 7,
      "block_sha256": "...",
      "section_id": "sec-...",
      "genoffice_locator": {
        "docx_index": 18,
        "kind": "paragraph",
        "text_sha256": "...",
        "style_id": "Heading2",
        "neighbour_before_sha256": "...",
        "neighbour_after_sha256": "..."
      },
      "confidence": "exact"
    }
  ]
}
```

### 9.3 定位规则

按以下优先级定位目标：

1. 同一源 SHA 下的有效 `docx_index` + 文本 SHA；
2. 内容控件/书签/自有稳定标记；
3. 当前节内唯一文本 SHA + 样式；
4. 前后相邻块指纹辅助的唯一匹配；
5. 无唯一匹配时拒绝写入，返回人工复核。

禁止仅凭段落文本模糊匹配执行自动写操作。

### 9.4 并发前置条件

每次写入同时验证：

- `document_revision`；
- `block_revision`；
- 3021 `block_sha256`；
- DOCX `source_sha256`；
- GenOffice 目标块 `text_sha256`；
- 候选当前写租约；
- engine version gate。

任一不满足即失败关闭，不自动覆盖、不隐式 rebase。

---

## 10. 操作翻译策略

### 10.1 支持等级

| 3021 操作 | GenOffice 目标操作 | 首期策略 |
|---|---|---|
| 普通段落替换 | `replace_blocks`/`docs apply` | 自动候选，需哈希匹配 |
| 标题下插入段落 | `insert_content` | 中风险，人工审批 |
| 删除段落 | `docs apply` 删除操作 | 高风险，人工审批 |
| 表格单元格文字修改 | 原生表格块操作 | PoC 通过后开放 |
| 图片/题注附近文字 | 精确范围或块替换 | 默认只生成提案 |
| 插入图片 | `insert_image`/`insert_picture` | 资源 SHA + 人工审批 |
| 页眉页脚 | `set_header_footer` | 高风险，正式排版阶段 |
| 页面/分节设置 | `set_page_setup` | 高风险，仅版式管理员 |
| 批注/修订 | comments/revisions ops | 通过映射测试后开放 |
| 公式对象修改 | 不直接自动修改 | 首期只读保护 |

### 10.2 事务边界

- 一个 `WritingChangeSet` 对应一个候选批次；
- GenOffice 原子拒绝的批次不得拆分后静默部分应用；
- 允许显式重新生成只包含安全子集的新 ChangeSet；
- 成功调用后必须重新 `docs read` 并核对目标块；
- 校验成功才可生成 `mutated` 收据。

### 10.3 禁止操作

- 对正式母稿原地 `--force`；
- 对 GenOffice GUI 正在打开的文件从 Sidecar 强制覆写；
- 对未知复杂对象附近执行范围不明的 find/replace；
- 在版本未验证状态下执行任何写工具；
- 将 GenOffice 自带云端搜索/图片/AI 工具默认暴露给 3021；首期只开放本地文档工具。

---

## 11. API 设计

G2+ API 前缀建议：

```text
/api/v3/integrations/genoffice
/api/v3/writing/projects/{project_id}/documents/{document_id}/office
```

### 11.1 Phase G1 已实现只读 API

```http
GET  /api/v3/writing/genoffice/status
POST /api/v3/writing/projects/{project_id}/documents/{document_id}/genoffice/check
GET  /api/v3/writing/projects/{project_id}/documents/{document_id}/genoffice/proof.png
```

- 三个端点均复用既有 3021 登录鉴权，不暴露 Sidecar URL、本机路径或 token；
- status 始终返回 `disabled`、`unavailable` 或 `read_only`，且能力对象固定把
  `docs_apply`、`visible_editor` 置为 `false`；
- check 在一次受认证会话中依次调用 `docs_read` 和 `docs_check`，仅返回受限的块摘要、
  findings 和输入 SHA；
- proof 调用 `render --page 1`，仅内存转发 PNG，响应 `Cache-Control: no-store`；
- G1 不提供候选、应用修改、外部编辑、PDF 持久化或任何正式发布端点。

### 11.2 G2+ 集成状态（规划）

```http
GET /api/v3/integrations/genoffice/status
```

响应：

```json
{
  "installed": true,
  "reachable": true,
  "version": "0.10.1038",
  "channel": "stable",
  "gate": "approved",
  "mode": "ready_write",
  "capabilities": {
    "docs_read": true,
    "docs_apply": true,
    "docs_check": true,
    "render": true,
    "visible_editor": false
  },
  "last_checked_at": "2026-09-25T00:00:00Z"
}
```

### 11.3 创建候选（G2+）

```http
POST /api/v3/writing/projects/{project_id}/documents/{document_id}/office/candidates
```

请求：

```json
{
  "base_document_revision": 42,
  "source_kind": "approved_export",
  "purpose": "proof",
  "idempotency_key": "uuid"
}
```

返回 `202` 与 WorkRun/candidate ID。相同幂等键和相同输入返回既有作业；参数不同则返回冲突。

候选查询与控制：

```http
GET  /api/v3/writing/projects/{project_id}/documents/{document_id}/office/candidates
GET  /api/v3/writing/projects/{project_id}/documents/{document_id}/office/candidates/{candidate_id}
POST /api/v3/writing/projects/{project_id}/documents/{document_id}/office/candidates/{candidate_id}/cancel
```

- 列表默认只返回元数据和最新审计摘要，不返回 Office 文件内容；
- `GET candidate` 返回关联 WorkRun、版本门、源/候选 SHA、状态、findings 和可用操作；
- `cancel` 只取消尚未进入不可中断写阶段的作业；写调用已发出时转为 `cancellation_requested`，等待 SHA 复核后再确定最终状态；
- 状态更新复用现有 SSE/任务事件通道，前端轮询只作为降级路径。

### 11.4 校样与检查（G2+）

```http
POST /office/candidates/{candidate_id}/render
POST /office/candidates/{candidate_id}/check
GET  /office/candidates/{candidate_id}/artifacts
GET  /office/candidates/{candidate_id}/preview.pdf
GET  /office/candidates/{candidate_id}/pages/{page}.png
```

检查返回统一 findings：

```json
{
  "status": "completed",
  "engine_version": "0.10.1038",
  "input_sha256": "...",
  "output_sha256": "...",
  "findings": [
    {
      "source": "genoffice.docs_check",
      "severity": "warning",
      "code": "stale_toc",
      "message": "目录字段需要在 Word 中刷新",
      "location": { "block_index": 3 }
    }
  ]
}
```

### 11.5 应用修改（G3+）

```http
POST /office/candidates/{candidate_id}/apply
```

请求：

```json
{
  "base_document_revision": 42,
  "source_sha256": "...",
  "candidate_sha256": "...",
  "change_set_id": "change-set-...",
  "client_change_id": "uuid",
  "operations": []
}
```

响应必须包含：

- 新候选 SHA；
- GenOffice 原始/规范化结果；
- 实际应用操作；
- 重读后的目标块摘要；
- 下一步 `audit_required`；
- 完整 WorkRun/审计关联 ID。

### 11.6 外部编辑会话（G4+）

```http
POST /office/candidates/{candidate_id}/native-sessions
GET  /office/candidates/{candidate_id}/native-sessions/{session_id}
POST /office/candidates/{candidate_id}/native-sessions/{session_id}/finish
```

首期如果 visible MCP 不可用，可降级为调用 `genoffice open <candidate>`，但必须继续通过文件 SHA 轮询识别变化，且不得假装具备实时会话控制。

### 11.7 晋升与拒绝（G2+）

```http
POST /office/candidates/{candidate_id}/decision
```

请求：

```json
{
  "decision": "approve",
  "expected_candidate_sha256": "...",
  "expected_document_revision": 42,
  "release_mode": "candidate",
  "comment": "通过 Office 校样与金标检查"
}
```

`approve` 只生成新的受管版本或 `WritingWordRelease`，不得覆盖历史版本；正式发布仍使用现有发布审批。

---

## 12. 持久化设计

### 12.1 优先复用现有对象

- `WritingChangeSet`：语义修改与审批；
- `WritingWordImport`：Office 文件导入谱系；
- `WritingWordRelease`：DOCX/PDF 发布记录；
- WorkRun / WorkArtifact：长任务、重试、产物和执行证据；
- `WritingChangeEvent`：已进入结构化正文的变更事件。

### 12.2 建议新增最小对象

#### `office_engine_releases`

```text
engine
version
channel
binary_path
binary_sha256
signature_status
capability_fingerprint
gate_status
test_report_path
approved_by
approved_at
blocked_reason
created_at / updated_at
```

唯一键：`engine + version + binary_sha256`。

#### `office_candidates`

```text
id
project_id
document_id
base_document_revision
change_set_id
engine
engine_version
adapter_schema_version
source_sha256
candidate_sha256
status
purpose
workspace_relpath
write_lease_owner / write_lease_expires_at
audit_summary
created_by
created_at / updated_at / decided_at
```

#### `office_block_bindings`

```text
candidate_id
document_revision
source_sha256
binding_schema
bindings_json
bindings_sha256
created_at
```

不建议为每个块建立独立数据库行；绑定清单是候选版本级不可变快照，便于整体哈希和回放。

### 12.3 配置契约

规划配置项如下，默认值以安全关闭为原则：

```text
GENOFFICE_INTEGRATION_ENABLED=false
GENOFFICE_MCP_URL=http://127.0.0.1:3094/mcp
GENOFFICE_MCP_TOKEN_FILE=<absolute chmod-0600 token file>
GENOFFICE_BINARY_PATH=/Applications/GenOffice.app/Contents/Resources/cli/genoffice
GENOFFICE_REQUIRED_CHANNEL=stable
GENOFFICE_MIN_SUPPORTED_VERSION=<approved minimum>
GENOFFICE_MAX_TESTED_VERSION=<last approved version>
GENOFFICE_MIN_SUPPORTED_MCP_VERSION=<approved MCP minimum>
GENOFFICE_MAX_TESTED_MCP_VERSION=<last approved MCP version>
GENOFFICE_CONNECT_TIMEOUT_SECONDS=<benchmark value>
GENOFFICE_TOOL_TIMEOUT_SECONDS=<benchmark value>
GENOFFICE_G1_PILOT_GATE=limited|accepted
GENOFFICE_RUNTIME_ENV_FILE=<dedicated non-secret local config>
GENOFFICE_SIDECAR_HOME=<absolute 0700 runtime home>
GENOFFICE_SIDECAR_TMPDIR=<absolute 0700 runtime temporary directory>
GENOFFICE_HEAVY_JOB_CONCURRENCY=1
OFFICE_CANDIDATE_ROOT=<managed absolute path>
OFFICE_CANDIDATE_RETENTION_DAYS=30
```

规则：

- `GENOFFICE_INTEGRATION_ENABLED` 未显式开启时，路由只返回不可用状态，不启动进程、不创建候选；
- token 不进入 `.env`、`/status`、前端构建变量、数据库、普通日志或启动参数；后台与 Sidecar 从同一个非符号链接、group/other 无权限的 token 文件读取；
- G1 仅接受 `stable` 渠道，且实际应用必须匹配固定 Bundle ID 与 Team ID；环境里的 `GENOFFICE_REQUIRED_CHANNEL` 不能自行放宽该门禁；
- `GENOFFICE_G1_PILOT_GATE` 在双金标未通过时必须为 `limited`；仅在人工确认正式验收后才可改为 `accepted`，且无论该值为何都不会开启 G2 写入；
- `OFFICE_CANDIDATE_ROOT` 必须是明确绝对路径，不允许 `$HOME`、`~`、工作区根或知识库根；
- 启动时检测 URL 必须是 loopback，除非未来有单独的远程 Sidecar 安全设计；
- Sidecar 的 MCP JSON/SSE 和 PNG 下载均使用流式总字节上限；返回给浏览器的读取项、问题字段和嵌套容器也必须截断，避免异常 DOCX/转换器结果耗尽 3021 内存；
- 环境中声明的版本范围不能自行授予写权限，数据库 release gate 仍是最终判断。

---

## 13. 更新与兼容治理

### 13.1 原则

官方应用负责下载和安装官方版本；3021 负责决定该版本是否获得业务读写权限。二者解耦。

版本状态：

```text
discovered
installed_unverified
testing
approved_read_only
approved_write
blocked
superseded
rolled_back
```

### 13.2 更新流程

```text
发现新版本
  ↓
记录版本、二进制路径、签名、SHA、能力指纹
  ↓
默认只读（docs_read/check/render）
  ↓
运行适配器契约测试
  ↓
运行两份真实 DOCX 金标无操作往返
  ↓
运行选区、表格、公式邻接、图片题注、并发冲突测试
  ↓
运行 PDF 页数和全页视觉差异测试
  ↓
生成版本门报告
  ↓
人工批准写能力
```

### 13.3 版本策略

- 生产只跟踪 stable 通道；beta 仅允许独立测试环境。
- 不以仓库 `main` 提交作为生产更新源。
- 适配器声明 `min_supported_version`、`max_tested_version` 和能力指纹。
- 高于 `max_tested_version` 的版本自动进入 `installed_unverified`。
- 工具缺失、参数 schema 变化或返回 envelope 变化时，立即降级为只读。
- 记录最近一个通过写门的版本和安装包/下载地址；回退过程必须人工执行并重新校验签名。
- GenOffice updater 禁止降级不代表 3021 不能业务回退；3021 可以立即停止新版本写调用，继续使用既有产物和 Word/旧导出链。

### 13.4 兼容矩阵

每个版本至少验证：

| 能力 | 测试 |
|---|---|
| 版本/能力 | `--version`、MCP initialize、工具清单 fingerprint |
| DOCX 读取 | 标题、段落、表格、批注、修订、页眉页脚 |
| 无操作往返 | ZIP/OOXML parts、正文/结构语义哈希、Word/WPS 无修复提示 |
| 窄修改 | 普通段落、标题插入、表格单元格 |
| 复杂对象保护 | OMML、图片关系、题注、REF/SEQ/TOC、浮动对象 |
| 并发 | 旧修订、旧 SHA、GUI 文件占用、重复幂等键 |
| 渲染 | 课程 23 页、论文 121 页目标及像素差异阈值 |
| 错误契约 | 稳定错误码、原子失败、未知操作拒绝 |
| 安全 | 路径逃逸、符号链接、未授权 token、超大输入、超时 |

能力指纹由 MCP initialize 信息、工具名称、工具 input schema 的规范化 JSON 和关键 guide/resource 版本共同计算。工具顺序、说明文字或非语义字段变化不应误触发阻断；工具缺失、必填参数、参数类型和结果 envelope 变化必须触发重新验证。

### 13.5 G1.1 上游兼容与升级验证门（v0.2 只读方案）

G1.1 的目标不是“再试一次直到成功”，而是判定复杂 DOCX 首屏校样是否能在可复现、可审计的条件下稳定完成。它的最高结论是 `verified_read_only`；即使通过，也**不**产生 G2 候选写入、正文权威变更、外部原生编辑或 Word Add-in 替代授权。

#### 当前上游结论（2026-09-25）

- 官方最新 stable 仍是已安装的 [`v0.10.1038`](https://github.com/genspark-ai/genoffice/releases/tag/v0.10.1038)，没有可进入隔离升级验证的新版安装包；发行说明虽提到大文档打开/输入更快，但没有承诺解决 headless render 超时；
- `main` 相比该 tag 前进 52 个提交，但 CLI 导出、Docs headless renderer 和共用 headless helper 的关键文件与 tag 的 blob 相同，内部 `180_000 ms` 预算也未变化；不得把 `main` 快照、修改 bundle 或放宽外层 HTTP 超时当作修复；
- [Issue #526](https://github.com/genspark-ai/genoffice/issues/526) 仍为 open。它说明大文档分页/渲染存在性能问题，能作为相关风险证据，但不能证明与本论文是同一根因，也不能替代本机 MCP 金标；
- 只读核验的机器可读记录见 [`genoffice-phase-g11-upstream-compatibility.json`](review/genoffice-phase-g11-upstream-compatibility.json)。

因此当前决策为：保持 `GENOFFICE_G1_PILOT_GATE=limited`、不安装 `main`、不修改供应商 180 秒预算、不以一次直连 CLI 成功覆盖 MCP 失败证据，继续由 Word Add-in/既有导出链承担高保真工作流。

#### G1.1 允许与禁止的动作

允许的实现仅是新增证据采集器 `backend/scripts/audit_genoffice_g11_repeatability.py`、本地报告汇总器 `backend/scripts/evaluate_genoffice_g11_gate.py` 与 MCP 工具契约指纹：前者使用现有 localhost Sidecar 认证方式，只调用 `docs_read`、`docs_check`、`render(page=1)`；后者不连接 GenOffice，只验证已脱敏报告的一致性。它们只记录哈希、计数、耗时、PNG 元数据和清理结果，不含 token、原始路径、FileStore URL、正文或原始日志，且拒绝覆盖既有证据文件。

禁止的动作包括：安装/替换 GenOffice、启动/停止/重启生产 Sidecar、修改官方 bundle、打开 `docs_apply`、创建候选、创建 WorkRun、写数据库正文、使用 3093 visible MCP、向 GitHub 发帖或上传文档样本。正式的冷启动/新 profile 验证必须在**独立的测试 Sidecar**上进行：独立 loopback 端口、独立 `0700` HOME/TMP 和不与 3094 在线试点共享 profile；该测试 Sidecar 的部署或任何应用更新仍须单独获得用户批准。

`--condition` 和 `--sidecar-epoch` 是操作员提供的证据标签；审计器不会伪造“冷启动”，也不会自行重启服务。它只对同一 G1.1 审计进程施加私有 profile 锁，不能被描述成对在线 3021 API 的跨进程排他锁。

#### 升级决策树

```text
官方 stable 新版出现
  ↓
发行说明或官方 Issue 是否明确涉及 headless / large DOCX / render timeout？
  ├─ 否：记录发现；维持 current limited，不下载、不安装
  └─ 是：人工批准下载与独立测试 Sidecar
           ↓
       SHA-256、DMG、签名、Gatekeeper、公证、Bundle ID/Team ID 复核
           ↓
       G1.1 只读重复金标 + 视觉签收
           ├─ 任一失败/漂移：blocked，保持 Word 基准与 G1 limited
           └─ 全部通过：人工裁决 verified_read_only（仍非 G2）
```

若没有官方修复，保留 G1 `limited` 并准备只含版本、哈希、阶段、耗时和结构统计的脱敏复现包；对外提交 Issue、提供文档或日志之前必须取得单独授权。

---

## 14. 安全设计

### 14.1 网络与认证

- Sidecar 只监听 localhost；
- 使用至少 32 字节随机 Bearer token；
- token 只在后端进程环境中可见；
- 前端 API 永不返回 token、Sidecar 原始 URL或本机路径；
- 所有业务 API 使用现有 3021 身份和权限链；
- 记录调用人、项目、文档、候选、工具和结果，但不记录密钥。

### 14.2 文件系统

- 所有输入路径先 `resolve()`，必须落在配置根目录；
- 拒绝符号链接跳出根目录；
- 上传文件使用随机目录和清洗后的展示文件名；
- 3021 Managed Office Workspace 与 Sidecar 会话文件区分离，二者只通过受认证的上传/下载交换带 SHA 的文件；
- Office ZIP 解压和远程媒体沿用大小、条目数量和总展开量上限；
- 禁止用户提供任意 MCP URL或工具名；
- G1 禁止通过 MCP 参数、`GENOFFICE_ALLOWED_ROOTS` 或继承环境向 Sidecar 授予项目源码、SSH 密钥、用户主目录和数据库目录；这不等于同一 macOS 用户下的 OS 级拒绝访问。需要该强度时，后续阶段必须使用独立受限服务账户/沙箱。

### 14.3 AI 与联网能力

首期只开放本地工具白名单：

```text
info
docs_read
docs_apply
docs_check
render
convert（受限格式）
```

默认禁用或不注册：

```text
search
image
media
open（headless HTTP）
```

如果后期使用 GenOffice 云能力，必须单独设计数据出境、密钥归属、引用证据和费用审批，不复用本文授权。

---

## 15. 可观测性与审计

### 15.1 指标

```text
genoffice_up
genoffice_version_info
genoffice_gate_status
genoffice_request_total{tool,status}
genoffice_request_duration_seconds{tool}
genoffice_request_timeout_total{tool}
office_candidate_total{status,purpose}
office_candidate_stale_total
office_audit_failure_total{gate,code}
office_promotion_total{decision}
```

### 15.2 日志字段

```text
correlation_id
work_run_id
candidate_id
project_id
document_id
document_revision
change_set_id
engine_version
tool
input_sha256
output_sha256
duration_ms
status
error_code
```

禁止记录正文全文、API key、MCP token、用户主目录绝对路径。

### 15.3 审计产物

每次晋升必须可追溯到：

- 源修订与源文件 SHA；
- GenOffice 版本和能力指纹；
- 实际操作列表；
- 修改前后文件 SHA；
- `docs check` 结果；
- 3021 内容保真和金标报告；
- PDF/PNG 渲染与视觉差异；
- 人工决定和时间；
- 最终 WordRelease/版本 ID。

---

## 16. 故障与降级

| 故障 | 系统行为 | 用户可继续做什么 |
|---|---|---|
| GenOffice 未安装 | 标记 `not_installed` | Tiptap、既有导出、WPS预览 |
| Sidecar 不可达 | 熔断并标记 `degraded` | 编辑正文、查看旧校样 |
| 新版本未验证 | 禁止写工具 | 读取、检查、渲染 |
| MCP schema 变化 | 适配器拒绝未知响应 | 使用 CLI诊断或旧链 |
| 操作超时 | 保留候选，状态待复核 | 重查 SHA 后决定重试 |
| 输出 SHA 不稳定 | 阻断晋升 | 下载候选、转 Word 基准检查 |
| 金标失败 | 版本写门全局阻断 | 回退 Word Add-in/既有导出 |
| GUI 正在打开同一文件 | 不强制覆盖 | 完成外部会话后重新审计 |
| 3021 正文已更新 | 候选标记 `stale` | 重新生成或人工重基 |
| PostgreSQL 暂时不可用 | 不启动新作业、不晋升 | 保留文件与本地只读预览 |

任何降级都不能自动切换正文权威。

---

## 17. 测试与验收

### 17.1 自动测试层级

1. **客户端契约测试**：MCP 初始化、认证、超时、取消、错误转换。
2. **适配器测试**：工具白名单、参数转换、返回 envelope、版本 gate。
3. **候选服务测试**：幂等、租约、SHA、状态机、stale、晋升事务。
4. **安全测试**：路径穿越、符号链接、越权、超大文件、恶意 ZIP。
5. **金标测试**：复用 `test_docx_gold_baseline.py` 和真实金标。
6. **端到端测试**：3021 创建候选、渲染、修改、审计、拒绝/晋升。
7. **视觉测试**：桌面/iPad 工作台；DOCX 页面 PNG 对照。

### 17.2 首轮 DOCX 硬门

必须覆盖既有阶段 0/1 场景：

1. 无操作打开保存，不出现 Word/WPS 修复提示；
2. 普通段落替换只改变目标范围；
3. 标题下插入段落保持样式和分页控制；
4. 表格单元格修改不重建整表；
5. 公式邻接编辑不改变 OMML 数量和语义哈希；
6. 图片题注附近编辑不破坏关系和字段；
7. AI 操作可映射到 `WritingChangeSet`；
8. 旧修订、旧块 SHA 或旧文件 SHA 必须拒绝；
9. 课程文件维持 23 页目标；
10. 论文文件维持 121 页目标并通过全页差异阈值；
11. 文件被 GUI 打开时 Sidecar 不强制覆盖；
12. 重复幂等键不重复产生修改。

“页数相同”不是单独通过条件。

### 17.3 前端验收

- 工作台能在三个文档模式间切换，切换前完成草稿 flush；
- Office 引擎不可用时不影响结构化编辑；
- 候选、版本、引擎和审计状态始终可见；
- 外部编辑不会让 3021 窗口错误显示“已保存到正式版本”；
- 1180px 以下保留模式状态并使用单窗口切换；
- 错误、过期和阻断状态不只依赖颜色；
- 桌面和 iPad 截图无重叠、截断或不可访问操作。

### 17.4 G1.1 重复金标协议（只读）

G1.1 的正式证据不是复用现有单次 G1 报告，而是由新审计器生成不可覆盖的 `openclaw.genoffice-phase-g1.1-repeatability.v1` 报告。每份报告必须固定并记录：manifest SHA、两份源 DOCX SHA/字节数、应用 release、MCP version、规范化三工具契约 SHA、非敏感运行配置 SHA、主机/磁盘可用量快照、条件标签、epoch、逐阶段耗时、读/检摘要指标、PNG SHA/尺寸/字节数和 renderer 原件清理结果。

报告不得记录源路径、正文、检查文本、token、FileStore URL 或原始日志；HTTP FileStore 上传仍按供应商 TTL 管理，关闭 MCP 会话不能被描述为立即删除上传原件。

正式矩阵必须在同一已验证的官方 release/MCP 组合上完成：

| 条件 | 次数 | 必须满足的环境事实 |
|---|---:|---|
| `cold_process` | 3 | 每次为独立测试 Sidecar 进程 epoch；每份报告只允许 1 round，两个金标均走 MCP + headless wrapper |
| `warm` | 3 | 同一测试 Sidecar 保持存活、每 round 建立新的 MCP 会话；可用 1 份 `--rounds 3` 报告表示 |
| `fresh_profile` | 1 | 新建的独立 `0700` HOME/TMP，不能复用生产 3094 或历史测试 profile |

每个 round 的两份金标均须通过 `docs_read`、`docs_check` 和 `render(page=1)`；不得出现 `conversion_failed`、MCP 版本/契约漂移、Sidecar 非预期重启、原件 SHA 漂移、遗留 renderer 原件或任何写工具调用。直连 CLI 的诊断结果不计入本矩阵。

功能门要求每次都在配置的工具期限内完成。体验门暂定为 P95 首屏渲染 `≤ 150 s`、任一次 `≤ 170 s`；超过目标但未越过上限标记 `attention`，越过上限或任何工具失败标记 `failed`。二者均不能作为 G1.1 退出通过。PNG hash 只作取证；必须由人工与 Word/WPS 基准并排检查论文首屏的公式、页眉页脚、图片/题注、裁剪与分页，无明显异常后才可形成视觉签收。

执行示例只适用于已获批准、且已准备好独立测试 Sidecar 的环境：

```bash
backend/venv/bin/python backend/scripts/audit_genoffice_g11_repeatability.py \
  --condition cold_process --sidecar-epoch test-sidecar-epoch-1 \
  --run-id g11-cold-1 \
  --output docs/review/genoffice-g11-cold-1.json
```

三份 cold、三轮 warm 和一份 fresh-profile 证据齐备后，可用纯本地汇总器检查跨报告的 release/MCP/契约/配置/源哈希/读检摘要一致性：

```bash
backend/venv/bin/python backend/scripts/evaluate_genoffice_g11_gate.py \
  --cold-report docs/review/genoffice-g11-cold-1.json \
  --cold-report docs/review/genoffice-g11-cold-2.json \
  --cold-report docs/review/genoffice-g11-cold-3.json \
  --warm-report docs/review/genoffice-g11-warm.json \
  --fresh-profile-report docs/review/genoffice-g11-fresh.json \
  --output docs/review/genoffice-g11-machine-gate.json
```

该汇总器只会给出 `machine_gate=passed` 与“等待人工视觉签收/`verified_read_only` 裁决”的状态；它不能、也不会修改 `pilot_gate` 或推进 G2。

工具不会创建或管理该 Sidecar，并会拒绝当前生产试点端口 `3094`；若输出文件已存在、条件标签不合理、环境不是 stable/private/受支持的 release/MCP，或同一 profile 已有另一 G1.1 审计占用，它也会拒绝产生“通过”证据。

**G1.1 退出语句**：仅当上述完整矩阵、视觉签收与安全证据均通过时，才可由人工把指定版本标记为 `verified_read_only`。这只证明该主机上的指定官方版本可重复完成两份 DOCX 的只读首屏校样；不构成 G2 候选写入、任何正文权威变更或 GenOffice 替代 Word Add-in 的授权。

---

## 18. 分阶段实施方案

除已批准的 Phase G1 及其不改变运行服务的 G1.1 证据准备外，其余阶段均为计划，不是执行指令。

### Phase G0：设计冻结

交付：

- 本设计评审通过；
- 五个待决策项获得明确裁决；
- 禁止开发标记解除；
- 建立正式任务规格和回滚计划。

退出条件：用户明确回复批准的设计版本。

### Phase G1：安装与只读接入

范围：

- 安装官方签名 GenOffice；
- 配置 localhost Sidecar；
- 实现状态、版本、能力和只读工具；
- 接入 `docs_read/check/render`；
- 不实现任何写操作和外部编辑。

退出条件：健康、认证、路径边界、两份金标只读检查和前端 Office 校样通过。当前仅作为只读试点运行；在两份金标均通过前，不得进入 G2 或启用任何写入能力。

#### G1 实施记录（2026-09-25）

- [x] 官方 Release `v0.10.1038` ARM64 DMG 的发布摘要已核对：
  `sha256:28756f6c073195a7c8fbc40add259d3522062310702cb61001e8e244aa267f5f`；
- [x] 下载文件 SHA-256 与官方发布摘要一致，`hdiutil verify` 通过；
- [x] 后端只读 MCP 适配、`status/check/proof.png` API、前端 Office 校样及定向测试已完成；
- [x] launcher/plist 模板已加入；其使用独立最小环境、token 文件权限检查、专用 `0700` HOME/TMP、流式响应字节上限，以及实际 bundle 的 `com.genoffice.app` / `TC7CATC2Z2` 身份、公证票据检查；
- [x] 已安装官方应用；安装前官方 SHA-256 与本地文件一致、`hdiutil verify` 通过，且 DMG 与已安装 `GenOffice.app` 的 `xcrun stapler validate` 均通过；
- [x] 在宿主 launchd 环境和独立主机复核中，`codesign --verify --deep --strict`、`spctl --assess --type execute` 与 `xcrun stapler validate` 均通过；此前沙箱诊断失败未被用作部署门的结论；
- [x] 已创建受限运行配置并 bootstrap localhost Sidecar；健康端点正常，专用 HOME/TMP 均为 `0700`；
- [x] 真实 MCP 认证、`initialize`/`tools/list` 能力契约和只读工具白名单已核验；应用 release `0.10.1038` 与 MCP `0.10.0` 分别通过当前 G1 版本门；
- [x] 课程金标 `course-plan-original-20h`（源 SHA-256 `625c5adc0d113828d4fa64b3bd7f6ee477cbc1f3335a67af6e9190c9b1347bc4`）已通过 `docs_read`、`docs_check` 和第 1 页 `render`；证据见 [`genoffice-phase-g1-readonly-course-probe.json`](review/genoffice-phase-g1-readonly-course-probe.json)；
- [ ] 论文金标 `thesis-v25-r4.1-layout-reference`（源 SHA-256 `7664c57c0f784ab9666bcdb76c1be6dac938d53e41638cbe0e77fa78a1410ecf`）的 `docs_read`（9.388 s）与 `docs_check`（7.341 s）成功，但正式重测的第 1 页 `render` 在 180.456 s 后以 CLI exit `3` / `conversion_failed` 失败；此前一次失败为 180.518 s。证据见 [`genoffice-phase-g1-readonly-thesis-probe.json`](review/genoffice-phase-g1-readonly-thesis-probe.json)。该时长精确贴近 v0.10.1038 的内部 180 秒 headless-export 预算，故 3021 将其以脱敏 timeout 提示呈现；不能据此猜测具体字体或 OOXML 根因。这不是可忽略的告警，正式双金标 G1 验收未通过；
- [ ] 在论文渲染兼容性恢复并重新完成双金标前，G1 保持只读试点，禁止进入 G2 候选写入、外部编辑、正式文档晋升或正文权威变更。

不得以关闭 Gatekeeper、`spctl --master-disable`、移除 `xattr` quarantine 或手动改签的方式继续。

### Phase G1.1：兼容性恢复与重复性验证（只读）

范围：

- 核验官方 stable release、关键 headless-render 路径和公开性能 Issue；
- 生成不可覆盖的 G1.1 重复金标证据，记录工具契约指纹、阶段耗时、哈希与清理结果；
- 在获单独批准后，使用独立测试 Sidecar 完成 cold-process、warm 与 fresh-profile 矩阵；
- 只验证 `docs_read/check/render(page=1)`，不接触候选或正式文档权威。

实施记录（2026-09-25）：

- [x] 已核验上游最新 stable 仍为当前 `v0.10.1038`；没有可安全安装的更新，`main` 关键 headless export 代码和 180 秒预算亦未变化；
- [x] 已记录上游判断，并新增只读的 `audit_genoffice_g11_repeatability.py`、`evaluate_genoffice_g11_gate.py` 与 G1 三工具 schema fingerprint；它们不安装应用、不管理 Sidecar、不会覆盖历史报告，也不会推进 `pilot_gate` 或 G2；
- [ ] 尚未部署独立测试 Sidecar，也尚未运行正式 cold/warm/fresh-profile 矩阵；生产 3094 试点没有被重启或替换；
- [ ] 尚未获得任何 `verified_read_only` 人工签收，`GENOFFICE_G1_PILOT_GATE` 继续为 `limited`。

退出条件：§17.4 的全矩阵、视觉签收、签名/公证与安全证据均通过，并由人工做出 `verified_read_only` 裁决。即使达到该结论，也必须另行批准 G2；不得把它解释为写权限、外部编辑权限或版本晋升。

### Phase G2：候选副本与审计

范围：

- 候选状态机和工作区；
- WorkRun、产物、SHA、审计关联；
- 校样、检查、下载、拒绝；
- 仍不晋升正式版本。

退出条件：候选可完整回放，失败不会影响正文权威或正式 DOCX。

### Phase G3：受控窄修改

范围：

- 块绑定清单；
- 段落替换和标题下插入；
- WritingChangeSet 映射；
- stale/并发/幂等处理；
- 人工审批后的候选晋升。

退出条件：两份金标全部通过，且 Word 原生重开无修复提示。

### Phase G4：外部原生编辑

范围：

- 3093 visible MCP 或受控 `genoffice open`；
- 外部会话与写租约；
- 保存检测、差异、回收、审计；
- 不在浏览器内嵌 UI。

退出条件：外部编辑与 3021 状态可解释，任意中断均可恢复或放弃。

### Phase G5：版本更新门自动化

范围：

- 版本发现；
- 自动兼容矩阵；
- 只读/写门；
- 人工晋升和回退运行手册；
- 管理员状态面板。

退出条件：模拟新版本、失败版本、回退版本三条路径均通过。

---

## 19. 与 Word Add-in 的共存与裁决

### 19.1 共存定位

| 能力 | 3021 Tiptap | Word Add-in | GenOffice |
|---|---|---|---|
| 结构化正文权威 | 是 | 否 | 否 |
| 项目上下文/证据/审批 | 是 | 通过 3021 | 通过 3021 |
| Word 原生最终基准 | 否 | 是 | 候选 |
| 跨平台 Office 编辑 | 否 | 弱 | 是 |
| Agent CLI/MCP | 3021 API | 否 | 是 |
| 无界面渲染/检查 | 部分 | 否 | 是 |

### 19.2 后续替代条件

只有同时满足以下条件，才允许另行决策是否用 GenOffice 替代部分 Word Add-in 场景：

- 连续三个 stable GenOffice 版本通过完整金标；
- 真实 Word/WPS 重开无修复提示；
- 论文与课程金标视觉差异处于批准阈值；
- 表格、公式、题注、交叉引用和浮动对象场景通过；
- 变更能进入可撤销、可追溯、可审批链；
- 外部编辑中断和升级回退均有实测证据。

未满足前，Word Add-in 继续作为高保真基准。

---

## 20. 风险登记

| 风险 | 可能性 | 影响 | 处理 |
|---|---|---|---|
| GenOffice MCP/CLI 在 0.x 版本发生不兼容变化 | 高 | 高 | 适配器、防腐层、版本门 |
| Electron 渲染和 Word/WPS 页面不一致 | 中 | 高 | Word 基准、全页视觉门 |
| 双权威导致正文和 DOCX 分叉 | 高 | 高 | 阶段权威、候选链、禁止旁路写 |
| docxIndex 在修改后变化 | 高 | 高 | 多重指纹、每次写后重读 |
| 官方自动更新使生产突然变化 | 中 | 高 | 未验证版本默认只读 |
| Sidecar 单实例成为瓶颈 | 中 | 中 | 队列、并发上限、超时与指标 |
| 外部编辑窗口与后台写冲突 | 中 | 高 | 写租约、GUI 占用拒绝 |
| 本地文件路径泄露 | 低 | 中 | 相对路径、日志脱敏 |
| 云端工具意外发送文档数据 | 低 | 高 | 首期不注册联网工具 |
| 开源镜像与私有主开发树差异影响可预期性 | 中 | 中 | 只依赖发布包和公开契约 |

---

## 21. 待评审决策

以下推荐值已由用户在 2026-09-25 以“批准 v0.1，按推荐方案进入 Phase G1 只读接入”裁决；其授权覆盖本节推荐方案及 Phase G1。随后“继续下一阶段”只用于 G1.1 的只读上游核验、设计和证据采集器准备，不授权安装/替换应用、部署测试 Sidecar 或进入 G2。

1. **集成形态**：批准“Sidecar 引擎 + 外部桌面编辑器”，不做 UI 源码嵌入。推荐：批准。
2. **正文权威**：草稿阶段继续以 PostgreSQL Tiptap JSON 为唯一可写正文权威。推荐：批准。
3. **更新策略**：stable 自动发现，未知版本只读，完整金标通过后人工开放写能力。推荐：批准。
4. **Word Add-in 地位**：保留为高保真基准，GenOffice 并行验证。推荐：批准。
5. **候选保留期**：未晋升候选默认保留 30 天；已晋升候选长期保留。推荐：批准，可调整。
6. **首期范围**：只做 DOCX 的读取、检查、渲染；PPTX/XLSX 在 DOCX 写门通过后再启用。推荐：批准。
7. **外部编辑阶段**：G4 前不启用 3093 visible MCP。推荐：批准。

---

## 22. 开发准入条件

Phase G1 的准入与执行记录如下：

- [x] 用户批准本文 v0.1；
- [x] 上述七项待评审决策按推荐值裁决；
- [x] 确认官方发布包来源、SHA-256、DMG 校验与实际应用 stapled-notarization 检查方式；
- [x] 官方 SHA-256、DMG 校验、严格 `codesign`、Gatekeeper 与安装后 stapled-notarization 校验均通过；
- [x] 确认只读会话使用 GenOffice HTTP 文件存储；Phase G1 不创建候选工作区或授予项目路径；
- [x] 未晋升候选保留期采用推荐值 30 天（G2 才开始生效）；
- [x] 建立开发任务规格，不夹带 Word Add-in 删除或正文迁移；
- [x] 已记录当前两份金标报告及汇总 [`genoffice-phase-g1-readonly-summary.json`](review/genoffice-phase-g1-readonly-summary.json)：二者均使用 manifest SHA-256 `b121d3f1a237efbf498315919dfc1bdee16ea7c23de3745b907deab965dc0ba4`；课程报告通过，论文报告在第 1 页渲染以 `conversion_failed` 失败；
- [x] Phase G1 无数据库 schema 或关键正文状态写入，故不触发数据库备份前置条件；
- [x] 用户已授权在 Phase G1 安装官方应用并配置 localhost Sidecar/launchd。
- [x] G1.1 已完成无外部变更的上游核验、重复性协议和本地证据采集器准备；尚未执行正式测试 Sidecar 或更新安装包的动作。

**边界重申：本批准不构成 G2+ 的候选写入、外部原生编辑、数据库迁移、正式文档晋升或正文权威变更授权。**

**当前验收结论：G1 可作为受限只读试点保留，不能声明为正式完成；双金标退出条件未满足前，禁止进入 G2 写入。**

**G1.1 边界重申：准备和运行只读证据不授予应用升级、生产 Sidecar 重启、独立测试环境部署、对外 Issue 提交或任何 G2+ 权限；这些动作需要相应的单独批准。**

---

## 23. 参考

### 3021 内部依据

- `DESIGN.md`
- `docs/review/word-cowriting-phase0-contract.md`
- `docs/review/word-cowriting-phase0-baseline.json`
- `docs/review/word-cowriting-phase1-poc-entry.md`
- `docs/review/word-cowriting-phase1-poc-result.json`
- `frontend-v2/src/components/writing/CollaborativeWritingEditor.vue`
- `frontend-v2/src/components/writing/WritingWorkspacePane.vue`
- `backend/models/writing_collaboration.py`
- `backend/services/word_addin_bridge_service.py`

### GenOffice 官方依据

- 仓库与总览：https://github.com/genspark-ai/genoffice
- CLI/MCP：https://github.com/genspark-ai/genoffice/blob/main/packages/cli/README.md
- MCP 接入：https://github.com/genspark-ai/genoffice/blob/main/README.md#mcp-server
- 更新器：https://github.com/genspark-ai/genoffice/blob/main/apps/shell/src/main/updater.ts
- 当前 stable release：https://github.com/genspark-ai/genoffice/releases/tag/v0.10.1038
- G1.1 headless-export 对照：
  - CLI：https://github.com/genspark-ai/genoffice/blob/main/packages/cli/src/formats/app-export.ts
  - Docs renderer：https://github.com/genspark-ai/genoffice/blob/main/apps/docs/src/renderer/headless-export.ts
  - common helper：https://github.com/genspark-ai/genoffice/blob/main/packages/electron-utils/src/headless-export.ts
  - large-document performance Issue：https://github.com/genspark-ai/genoffice/issues/526
- 安全策略：https://github.com/genspark-ai/genoffice/blob/main/SECURITY.md
- 贡献与公开镜像说明：https://github.com/genspark-ai/genoffice/blob/main/CONTRIBUTING.md
