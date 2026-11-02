# 第三阶段 A 验收记录

日期：2026-09-25。目标：Mac mini 既有 3021 agent-system。

## 结论与边界

第三阶段 A「默认关闭的受控执行内核与只读准备视图」已发布并通过本次范围内验收。
第三阶段「受控远程执行」整体尚未完成：未启用生产远程执行，没有新增执行 API、
执行按钮或 worker 注册，也没有发放密钥、修改认证策略或数据库结构。

本次程序观测是节点状态来源；准备视图只解释准入条件，不代替真实执行回执。
独立审查结论为允许发布默认关闭的准备视图，禁止据此启用真实远程执行。

## 交付

- 复用 `work_runs` / `work_run_events`，增加显式 opt-in 的原子至多一次领取。
  相同 request_id 跨管理员全局去重，绑定不同请求或主体时冲突；过期、完成后均不重领。
  普通领取不能重试该类保留键。此保证仅为控制端至多一次派发，不是远端 exactly-once。
- 执行请求为封闭契约，仅保留无参数 `host.info`；固定命令、严格主机密钥检查、
  独立凭据绑定、超时/取消、有界输出及清理。未知结果保留为 blocked，不自动重试。
  生产仅调用准备投影；授权回调只是隔离测试接缝，未连接真实审批。
- 既有集群 GET 增加可选 `execution` 投影；前端兼容旧快照，显示全局及逐节点阻塞项，
  陈旧快照不能显示可执行。没有发送执行请求的页面入口。

## 隔离验证

后端使用 Mac mini 既有虚拟环境，在隔离目录执行：

```bash
cd /private/tmp/agent-system-cluster-20260925/backend
PYTHONPATH=. /Users/apple/工作桌面/Workspace/agent-system/backend/venv/bin/python -m pytest \
  tests/test_monitoring_heartbeat_freshness.py \
  tests/test_cluster_readonly_collector.py \
  tests/test_cluster_inventory.py \
  tests/test_cluster_additive_rollout.py \
  tests/test_monitoring_api.py \
  tests/test_cluster_execution.py \
  tests/test_work_run_at_most_once.py \
  tests/test_work_run_service.py \
  tests/test_command_center_service.py \
  tests/test_step_approval_service.py -q --disable-warnings
```

结果：153 passed，7 warnings，9.33 秒。包含 32 并发领取唯一创建、跨管理员重放冲突、
输入/身份/准入拒绝、输出上限及真实本地子进程取消/超时清理。未连接真实执行 SSH。

前端在同一隔离目录的 `frontend-v2` 执行：

```bash
PATH=/opt/homebrew/bin:$PATH npm run test:run -- ClusterMonitoringPanel
PATH=/opt/homebrew/bin:$PATH npm run build
```

结果：11 项测试通过；vue-tsc 与 Vite 构建通过，2988 modules。存在既有大 chunk 提示。
以上是相关定向回归，不代表仓库全量测试通过。

## 生产与浏览器验收

- 已登录 GET `/api/v2/monitoring/cluster` 返回 200；匿名 GET 返回 401。
- `execution.mode=preparation_only`，`enabled=false`，全部七个托管节点 `ready=false`。
- 已登录 POST 同一路径在生产返回 **404**：由既有 `/api/{path:path}` 回退路由处理；
  单独挂载集群路由的测试返回 405。两者均不表示存在执行入口，不混淆这两套证据。
- 使用 Playwright 经临时本地 SSH 隧道打开实际监控页，核验全局条件、七节点准备行、
  无执行按钮。控制台错误 0；有 1 条既有警告。截图已在开发机视觉复核：
  `/Users/sunyi/工作桌面/WorkSpace/one-sim/output/playwright/cluster-phase3a-20260925.png`。
- 发布和浏览器验收前后，生产 PostgreSQL `work_runs=58`、`work_run_events=287`，
  `cluster-readonly-v1` 执行记录为 0；没有因查看准备页创建任务。
- 主 SQLite Alembic revision 仍为 `41670c742a60`，没有运行迁移。
- 仅重启 3021 后端，新 PID 69844；采集器 PID 36543、业务 worker PID 56331 保持不变。
- 2026-09-25 10:01:12 UTC 的采集记录为每轮成功 2 台。Mac mini/MacBook 在线且采集新鲜；
  compute04/05、对外 Windows 当前离线；仿真服务器/Yoga 在线，但身份或采集访问仍待确认。
  这是本次验收快照，不修改前两阶段历史记录，也不宣称七节点硬件验收完成。

## 发布与回退材料

- 基线 HEAD：`bb41970`。未提交或推送；保留原有未跟踪文档
  `docs/SYSTEM-CLOSURE-MASTER-PLAN.md` 及无关改动。
- 发布清单 `cluster-phase3a-release-files.txt` 共 10 个源码/测试/方案文件；
  隔离版本与生产逐一 `cmp` 一致，`git diff --check` 通过。本验收文件随后单独归档。
- 前端使用已验证的隔离构建产物发布，保留旧静态资源；没有使用删除式同步。
- 原六个覆盖文件及旧前端 dist 已备份到 Mac mini：
  `/Users/apple/工作桌面/Workspace/agent-system/backend/data/cluster-phase3a-KUOHcM/source-and-ui.tgz`。
  回退应先停 3021，恢复该备份中原文件和 dist，再启动并验证；本次新增但未挂接的内核
  和测试文件不会单独启用执行。没有需要逆向执行的数据库迁移。

## 已知验证限制与第三阶段 B

1. 并发领取证据来自 SQLite；尚未完成独立 PostgreSQL schema 下的竞争、崩溃与恢复验证。
2. 本次直接只读打开旧 `unified_dashboard.db` 返回无法打开文件，未尝试修复；上述任务账本
   数量来自当前生产 PostgreSQL，而不是该旧文件。主 SQLite revision 单独验证成功。
3. 凭据文件权限与路径检查不能证明真实最小权限；不得把复制操作员密钥视作专用执行身份。
4. 下一阶段需接入 Command Center 权威审批：精确请求/合同绑定、原子消费、权威步骤幂等键、
   审批与合同摘要持久化、租约令牌约束的完成回写，以及未知远端结果对账。
5. 正式登录、独立低权限账户/限制命令密钥及主机身份验收需单独完成；当前开发自动登录仍是
   明确阻塞项。未配置任何生产执行启用开关。
6. 完成上述条件后，仅对选定且已确认的一台节点做真实只读 canary，保存权威审批、执行和
   远端结果证据；通过后再逐台扩展。不得跳到资源调度或批量部署并宣称阶段三已闭环。
