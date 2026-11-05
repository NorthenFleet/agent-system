# 第二十阶段：联合版本核对与发布门禁

日期：2026-11-04（Asia/Shanghai）。状态：完成当前版本核对和可执行的回归检查；发布门禁未通过，联合发布及回退演练尚未完成。

## 相比上次的变化

第十九阶段报告描述的是 2026-10-08 当时未发布的状态。本轮实际读取 3021：健康接口 status=ok；生产入口引用 main-h0UpVYlq.js 和 CommandCenter-B5LNeMTj.js，后者与磁盘字节一致，含提交标识持久化和 idempotency_key；运行中的 OpenAPI 已接收该字段。因此不能继续把线上描述为第十八阶段，也没有必要按旧计划盲目重发旧资源。

这只能证明运行接口和实际分发资源具备对应能力，不等同于在生产创建请求上完成端到端去重验证。本轮未向生产发送创建或审批请求。

检查开始时 HEAD 为 6787208；检查期间外部工作新增 df7fef8，提交了 workflow 外键修正。本轮没有修改或提交该文件，company-website/ 亦未处理。上次大部分修改已有提交记录；这里的测试结果对应本轮实际运行时点，未声称冻结了并行变化中的整个仓库。最终复核生产 575 个静态文件仍与清单一致。

## 新鲜验证结果

- 后端：47 passed，6 条弃用警告。
- 前端：4 个测试文件、22 passed。
- 当前源码的隔离 PostgreSQL 探针：8 并发→1 任务，随后重试返回相同任务，同标识不同内容拒绝，不同用户独立创建。复用既有隔离数据库、使用全新 phase20 随机账号；不改第十九阶段证据，不启动 worker。
- git diff --check 通过。
- 整站构建失败：18 条 TypeScript 错误，集中在 FinanceReimbursements.vue。verify:entry 已通过，vue-tsc 阻断，未生成可发布候选包。
- 生产 API 心跳新鲜，worker-2 数据库记录虽为 running，last_seen_at 仍是 2026-10-20T01:11:44.355368+00:00，不能计为在线。生产任务记录为 cancelled 10、completed 11、waiting_feedback 6。

## 阻断定位

1. 报销页第 191 行导入不存在的 @/utils/request；第 265 行 currentReimbursement = ref(null) 无类型，导致详情模板和后续赋值访问推断为 never；另有 computed 未使用。该页面由最新财务重构提交引入。应先明确新 workflow 页的请求客户端和响应类型，再修复、回归。不能直接替换为旧 financeApi：运行 API 同时存在 /finance/workflow/* 与 /api/finance/*，二者契约不同。
2. worker-2 心跳过期，尚未完成 launchd/进程/日志根因诊断。API 健康不能替代多 worker 运行健康。
3. Computer Use 当前不可用：浏览器访问 host unavailable；原生 Edge 和 Chrome 都返回 cgWindowNotFound。故本轮没有新的浏览器截图或 UI 验收，不复用旧截图作为本轮证据。

## 发布与回退

本轮未修改生产静态入口，未重启 API/worker，未迁移生产数据库。保存了生产实际入口及资源哈希、API 契约、静态资源完整哈希清单。尚无通过构建的候选版本，因此未执行联合发布或回退演练；哈希清单不冒充可运行的回退备份。

下一步顺序：修复报销页构建和请求契约→诊断并恢复第二 worker→恢复 Computer Use 连接→冻结联合候选与可运行回退副本→隔离验证及回退演练→空闲窗口发布及生产冒烟。保留当前生产版本，避免用未通过构建与运行健康检查的候选覆盖它。

## 证据

- production-interface-audit.json：实际 HTTP 入口、资源哈希与接口字段。
- production-static-manifest.json：生产磁盘静态文件哈希。
- production-workers.txt：生产心跳及任务状态。
- backend-tests.txt、frontend-tests.txt、build.txt：本轮完整测试与构建输出。
- pg-audit.json、pg-probe.py：本轮隔离并发探针结果及可复核脚本。
- finance-route-audit.json：当前运行的两套财务接口路径，支持契约差异判断。
