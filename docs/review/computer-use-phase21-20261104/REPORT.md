# 第二十一阶段：构建复验、worker 恢复与前端回退演练

日期：2026-11-04（Asia/Shanghai）。结果：构建阻断解除，第二 worker 恢复，前端文件级发布/回退演练通过；浏览器验收仍受连接不可用影响，新前端未发布。

## 构建与代码

本轮开始时 FinanceReimbursements.vue 已有外部并行修改：移除无用 computed、替换不存在的请求导入为已有 api/client、声明 WorkflowReimbursement 类型并允许空日期。保留这些改动后执行验证，本轮未重复修改或提交该页面。

api/client 的 baseURL 为空，返回 Axios response，与页面现有 /finance/workflow/* 请求路径和 res.data 用法相容。运行 API 已存在对应 workflow 路由。此项是代码契约核对，未执行真实报销创建、审批或付款。

验证结果：

- npm run build -- --outDir /private/tmp/agent-system-phase21-dist 成功，包含入口检查、vue-tsc 和 Vite；仍有既有大包提示。
- 后端相关回归 50 passed，6 条弃用提示（包含 worker 心跳新鲜度、指挥中心和创建去重）。
- 前端相关回归 22 passed，4 个测试文件。
- git diff --check 通过。

## worker 恢复

发现 launchctl 中没有 ai.openclaw.command-center-worker-2 服务，~/Library/LaunchAgents/ 中也没有其配置；没有发现该服务被显式禁用。这解释了当前不运行状态，但不能据此判断历史上是谁或为何移除了配置。旧日志还含历史 SQLite 锁冲突，未将其误当作本轮缺失服务的直接原因。

恢复前只读确认无 received/planning/running/evaluating/dispatching 任务，无 pending/approved/running 步骤，无 approved/running 补偿。随后使用仓库已有 plist bootstrap 当前登录会话，恢复同名登录启动配置。未改 worker 源码、环境文件或数据库任务。

进程 PID 67570，launchd state=running。两次观测相隔约 35 秒，api-3021 与 worker-2 的 last_seen_at 均前进，最终年龄均 4 秒。API /health 返回 ok。没有声称已完成长期稳定性测试，也未实际注销或重启电脑验证登录启动；只核实已安装配置字节与仓库一致。

## 发布与回退演练

当前生产静态资源 575 个文件，候选同为 575 个。对独立临时副本执行：复制当前生产→替换为候选→验证完整文件哈希→回退到原副本→验证完整哈希。演练通过，实际生产静态文件未变。

候选：/private/tmp/agent-system-phase21-dist。
生产静态备份：/private/tmp/agent-system-phase21-production-frontend.tar.gz。

这些路径位于临时目录，系统清理后需要重新生成。rollback-drill.json 记录备份哈希及范围；candidate-manifest.json 和 production-manifest.json 保留文件清单。此演练仅覆盖前端文件，不是后端进程或数据库回退演练，不能据此声称联合发布已完成。

## 未完成项

Computer Use 再次返回 browser access host unavailable，没有可操作浏览器。未尝试绕过该限制控制 UI，未沿用旧截图冒充本轮截图。

需恢复浏览器连接后，复核候选页面的草稿、刷新、响应丢失重试及报销页读取交互，再决定是否发布。报销页当前仍有 applicant_id=1、approver_id=1 的硬编码身份，本轮未触发这些写操作；在发布新的报销入口前应单独验证身份归属与审批权限，编译成功不代表业务验收通过。

本轮只恢复既有 worker 服务，未重启 API、未修改生产静态入口、未执行财务写操作。

## 证据

build.txt、backend-tests.txt、frontend-tests.txt：本轮新鲜验证输出。
worker-heartbeats-first.txt、worker-heartbeats-final.txt、production-health.json：恢复后运行证据。
rollback-drill.json、candidate-manifest.json、production-manifest.json：文件级演练与版本哈希。
