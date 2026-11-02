# 第七阶段：完整 worker 故障恢复

日期：2026-10-06（北京时间）。本阶段将第六阶段的服务类测试推进到实际 CommandCenterWorker 的完整主循环，并补强回执字段提示。

## 实现与环境

- 实际执行提示明确要求 tools_used 填原生工具名，不能填 source_ref；risk_notes 为非空字符串，说明风险或验证范围，不能以空数组、null 或空字符串替代。没有自动补造风险说明，也没有放宽严格门禁。
- 新建独立 PostgreSQL 库 `agent_system_cu_phase7_20261006`，只复制前阶段测试库表结构，没有复制任务数据。
- 启动两个真实 CommandCenterWorker 进程，使用其原始调度、领取、步骤心跳、实例心跳、Work Run、验收和最终评估逻辑。
- 执行器调用真实 OpenClaw；故障注入包装器在 A 的真实步骤调用返回后暂停交付回执，随后由测试父进程终止 A。B 使用真实执行器重新执行只读核验。
- 步骤超时配置为 60 秒，worker 按原代码生成 240 秒租约和 60 秒步骤心跳；不改数据库时间，不人为缩短已领取租约。
- 计划是预置夹具；背景检索和记忆服务不启用。通知发送替换为拒绝外发适配器，主循环仍处理通知队列，但不会调用外部消息接口。

## 验证记录

103 项后端回归通过，仍有 6 条既有依赖弃用提示。测试代码首次将环境数据库配置和显式 repository 同时传给 WorkRunService，触发参数冲突；未执行的测试任务已取消，记录保留。修正为显式 database_url 后启动成功。

实际运行目录：`run-7d9e0cd3`。A 的真实回执使用 tools_used=[exec]，risk_notes 非空，离线严格复验通过；故障发生时步骤仍为 running，尚未将该回执提交为完成。

完整恢复通过，任务 `mission-2593e77a4486` 最终状态为 completed。A 被终止后约 201.27 秒，B 在原 240 秒租约自然到期后接管同一步，获得新令牌；201.27 秒是故障后的剩余等待时间，不是新的租约长度。旧令牌回写被拒绝，步骤累计执行两次。

B 的真实执行回执严格验收为 100 分，无警告或阻断项，真实最终评估通过。预检仅将一个有效 evidence ID 归一为已存在的文件引用，归一前后严格验收均通过，没有补造证据。原文件 SHA-256 保持不变，外发通知为 0。测试结束后两个测试 worker 均已退出，数据库与原始记录保留。

确认生产无正在执行的步骤后，已重启现有 API 和独立 worker，加载回执提示补强。通过浏览器点击刷新，10/06 00:23 的页面显示运行门禁就绪、2/2 实例在线、失联 0、过期租约 0、活跃租约 0。没有切换生产全局 strict 模式；截图展示的历史 H 任务仍保留原先 2 条证据警告，它不是本阶段隔离任务的结果。

## 范围限制

本次验证的是在独立 PostgreSQL 中运行的完整 worker 类，不是终止生产服务进程。工作项为无写入副作用的只读任务，因此执行两次可以接受；不能由此推断写入或支付等副作用能自动安全重试。

预置计划、禁用背景/记忆服务和拦截通知都是隔离条件；本次不验收模型规划、生产身份权限、外部消息发送、外部网络中断或长时间无人值守稳定性。两次真实步骤回执即使都合格，也只是小样本，不能证明模型不会再次漏字段。

## 证据

- regression-result.txt：103 项回归。
- run-7d9e0cd3/a-step-invocation.json、a-step-result.json、a-offline-quality.json：首次真实调用与严格复验。
- run-7d9e0cd3/b-step-*、b-evaluation-*：接管执行及最终评估的原始调用和输出。
- run-7d9e0cd3/before-crash.json、final-mission.json、worker-observations.json、summary.json：故障前后状态和租约证据。
- 各 worker 日志及 blocked-notifications.jsonl：主循环运行与通知拦截。
- production-page.txt、production-health.jpg：服务更新后的浏览器健康复核。
- source-final.json：本阶段相关源码的最终 SHA-256。
- 复现入口：`backend/scripts/run_phase7_full_worker_recovery.py`，仅允许指定的独立测试库，拒绝在存在活跃测试任务时启动。
