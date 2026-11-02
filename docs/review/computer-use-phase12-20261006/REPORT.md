# 第十二阶段：恢复写入后中断与重新审批

日期：2026-10-06。结论：隔离任务 mission-a458581a0d71 完成，严格交付门禁 100 分。完整 worker 在恢复文件及本地回执已落地、成功结果尚未写入数据库时被 SIGKILL；替代 worker 等待租约自然过期，保持暂停，经页面重新审批后只读复用回执，没有重复恢复写入。

## 修复内容

- 过期恢复扫描现在同时匹配扫描时的租约令牌、到期时间和仍已过期状态。只在条件更新成功时记录重新审批事件并计数，避免覆盖较新的租约或重复报告恢复中断。
- 已过期的恢复租约不能再通过迟到心跳续期。原有过期/旧令牌完成回执拒绝规则继续生效。
- 页面在中断恢复项上明确说明“实际操作可能已生效”，要求先核实资源与回执。重新批准弹窗也显示实际状态核实及原合同幂等要求；不会自动重放。

## 故障注入与浏览器闭环

独立主测试库 agent_system_cu_phase12_20261006，页面 3042；恢复项 compensation-5976242a7f3d。UI 与 worker 使用不同进程，故障只终止本次实验 worker，页面保持可用。

1. 夹具建立改写样本、备份和保护文件，记录原写入失败、只读核实结果及待审批恢复合同。此部分不声称由模型生成。
2. 浏览器批准恢复，完整 CommandCenterWorker 调用固定文件适配器。它保留 before-recovery.txt，从 backup.txt 恢复 applied-sample.txt，创建带合同指纹和幂等键的 recovery-receipt.json。文件均 flush/fsync；此时不向服务提交成功结果。
3. 故障探针核对目标进程命令后 SIGKILL worker 80260，保存崩溃边界及五份文件的 SHA256 和纳秒修改时间。替代 worker 81190 启动；租约未过期时不可领取恢复。
4. 60.64 秒后，60 秒租约自然过期，恢复项回到 pending_approval，旧批准信息和授权到期时间清空。未更改数据库时间来加速此次故障测试。旧令牌的心跳和完成请求均被拒绝，未批准时不可领取。
5. 页面显示中断与重新审批提示。独立检查确认文件已经恢复，回执与合同相符，五份文件未变，才通过页面重新批准。
6. 替代 worker 检查同键回执、样本、备份、保留副本及保护文件，直接复用原回执。没有第二次文件恢复；数据库补偿 completed、副作用 reverted。
7. 浏览器反馈重新规划 V2 只读验收，单独批准后，真实 OpenClaw ratchet 检查文件和回执，optimus 做总验收；任务 completed，执行及最终交付门禁均为 strict、100 分。
8. 浏览器下载回执，/Users/apple/Downloads/recovery-receipt (1).json 与服务器逐字节一致。

独立最终审计：实际恢复写入记录 1 条；原 V1 写入尝试 1 次；V2 只读验收尝试 1 次；补偿累计 3 次（夹具核实、被终止的恢复、只读复用）。五份测试文件自崩溃边界起到最终验收后，哈希和修改时间均一致；外发通知 sent=0。原失败、中断、重新审批记录均保留。

## 并发与回归检查

- 后端 69 项测试通过（backend-tests-final.txt），含过期租约拒绝续期、扫描后令牌变化和扫描后到期时间变化的回归。6 条既有弃用提示保留。
- 前端 11 项治理和生命周期测试通过（frontend-tests-final.txt），增加中断提示与取消确认不提交审批的检查。首次新增用例因复用同一模拟响应对象未触发刷新而失败，修正为新响应快照后通过，首次日志保留。
- 独立并发库 agent_system_cu_phase12_race_20261006 上，使用两条真实 PostgreSQL 连接，将已提交的租约时间或令牌变化插入扫描与更新之间。两种交错均更新 0 行，较新租约保留、错误重新审批事件 0。这里为确定性竞争测试，时间/令牌由夹具直接更新，并非真实心跳时间线。
- 类型检查和生产构建通过（build.txt），仍有既有大资源包提示；git diff --check 通过。
- 生产活跃任务、运行步骤均为 0 后部署前端并重启 API/worker。浏览器复核：运行门禁就绪，2/2 在线，失联 0，过期租约 0。旧入口保存，历史资源和任务未删除。

## 验证范围与剩余工作

此次恢复适配器是固定资源、可核对的测试实现，用于精确定位完整 worker 崩溃点；恢复动作本身没有使用 LLM。后续只读验收和总评估使用真实 OpenClaw。上一阶段真实模型恢复验证与本阶段进程故障验证互为补充，不能合并宣称模型可安全处理任意恢复中断。

本次覆盖“本地回执已经落盘、数据库尚未记录成功”的进程崩溃窗口；不覆盖恢复文件写到一半、本地回执尚未创建、机器断电、远端工具请求未明等窗口。幂等复用依赖本次合同和适配器实现，不能保证通用外部工具 exactly-once。并发库及全部旧记录保留，不用于生产执行。

整体优化尚未全部完成。下一阶段应验证缺失/损坏回执的恢复分支，补齐可稳定定位的核实证据，再开展持续运行与并发任务稳定性测试。

## 复现与证据

- backend/scripts/run_phase12_recovery_crash_lab.py：隔离 UI、完整子进程 worker、固定文件适配器和真实只读验收。仅限本机测试，不能作为生产认证入口。
- backend/scripts/run_phase12_crash_probe.py：一次性崩溃注入及租约/文件检查；已有 crash-observed.json 时拒绝再次执行，防止误伤或改写证据。
- backend/scripts/run_phase12_pg_lease_race.py：独立空库上的两连接竞争检查，保留记录。
- crash-boundary.json、crash-observed.json、interruption-check.json、interrupted-mission.json：崩溃时刻、真实等待时间、旧令牌拒绝和暂停状态。
- physical-writes.jsonl、receipt-reused.json、recovery-receipt.json：实际写入次数及只读复用证据。
- call-1-invocation.json 没有 result 文件，这是故意终止的调用；call-2 是适配器复用回执，call-3/4 是真实 OpenClaw 只读验收/总验收。
- final-mission.json、final-compensations.json、all-plan-steps.json、summary.json：最终和历史状态、下载校验。
- pg-race.json、reapproval-dialog.jpg、completed.jpg、final-ui.txt、production-health.txt、source-final.json：并发、页面、部署及源码证据。
