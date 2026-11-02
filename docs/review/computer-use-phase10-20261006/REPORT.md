# 第十阶段：已写入后的新恢复方案审批

日期：2026-10-06。本阶段完成新恢复方案入口、独立审批约束和受控文件恢复的浏览器闭环。整体优化仍需真实执行器恢复验证及长时间稳定性验收。

## 功能与约束

- 管理员可以对已有核实证据、状态为 failed 的 verify_effect 恢复项提出新方案；不能跳过核实直接改变待执行合同。
- 新方案固定关联原任务、原步骤和原资源，生成新的合同指纹与幂等键，清空旧批准和租约，回到 pending_approval。提交不会执行；普通反馈也不能代替审批。
- 原合同、批准记录、核实回执和新合同写入持久化事件。当前卡片显示已有核实结果，审批弹窗展示完整恢复说明。
- PostgreSQL 对方案变更及审批锁定恢复项；更新同时匹配原合同及状态。旧指纹、旧执行令牌不能授权新方案。
- 新 API 使用现有管理员角色检查及任务访问检查，不新增角色权限，不改变全局严格模式。

## 浏览器闭环

独立 PostgreSQL：agent_system_cu_phase10_20261006；本机页面：3040；任务：mission-c41a10573374。

1. 测试夹具建立被改写文件 applied-sample.txt（changed-by-test）及备份 backup.txt（before-change），原写入回执未知。
2. 浏览器批准只读核实，实际检查确认样本已存在，恢复项进入 failed。
3. 浏览器点击“提出恢复方案”，填写前置条件、备份来源、保留改写副本及逐字节核验要求。提交后测试适配器确认恢复项不可领取，文件仍为 changed-by-test。
4. 浏览器点击“批准补偿”，确认弹窗中的完整方案。受控适配器先验证前置内容，保存 before-recovery.txt，再从备份恢复，逐字节核验后提交真实文件回执。恢复项 completed，副作用 reverted。重复领取探测无可执行恢复项。
5. 浏览器提交恢复后的只读验收计划，界面再次进入待审批。批准 V2 后运行真实 Python 子进程复核恢复内容，严格执行验收及最终交付门禁通过，任务 completed、100 分。
6. 浏览器下载复核记录，文件 /Users/apple/Downloads/step-4b131883dd50-verification.txt 与服务端字节一致。恢复后的样本等于备份，改写副本完整保留，原写入未被重试。

## 检查与部署

- backend-tests.txt：64 项后端回归通过。
- endpoint-tests.txt：7 项新功能测试通过，其中 6 项与上述回归重叠，另 1 项验证真实路由的角色依赖；后端合计 65 个不同用例。普通用户提交返回 403，旧指纹返回 409，管理员有效提交后仍不可执行。
- frontend-tests.txt：11 项前端治理与生命周期测试通过。
- build.txt：类型检查与构建通过，仍有既有大资源包提示；后端仍有 6 条既有弃用提示。
- git diff --check 通过。
- 确认生产活跃任务及运行步骤为 0 后部署前端并重启现有 API、worker。浏览器刷新后：门禁就绪，2/2 在线，失联 0，过期租约 0，活跃租约 0。旧入口文件保存在 previous-production-index.html，没有删除历史静态资源和任务数据。

## 验证边界

本阶段的浏览器页面使用生产前端和真实服务类，身份、初始失败、规划及最终评估为隔离夹具；文件恢复使用固定资源、固定备份和前置条件检查的受控适配器，没有使用真实 OpenClaw 模型执行恢复。新生产路由的角色限制通过隔离 TestClient 验证，并非真实登录会话的权限渗透测试。

新合同仅支持从失败的只读核实进入人工恢复。此次没有验收恢复动作再次中断后的完整用户体验，也不证明所有外部工具能恰好执行一次。生产恢复执行仍依赖执行器遵守审批范围、正确提交回执；需要下一阶段用真实执行器和隔离文件继续验证，然后开展持续稳定性检查。

## 证据

- recovery-proposed.json：新合同、旧核实记录及待审批状态。
- compensation-d7e3a0d1f134-1-receipt.json、compensation-d7e3a0d1f134-2-receipt.json：核实与恢复回执。
- applied-verified.json、applied-feedback.json、execution-result.json、final-mission.json、summary.json：恢复完成、再次审批、独立验收及下载校验。
- backup.txt、before-recovery.txt、applied-sample.txt：原内容、改写副本、恢复后的文件。
- recovery-awaiting-approval.jpg、completed.jpg、final-ui.txt：Computer Use 证据。
- production-health.txt、source-final.json：部署后复核和源码哈希。
- backend/scripts/run_phase10_recovery_lab.py：本阶段隔离适配器；backend/tests/test_phase10_recovery_proposal.py：新功能回归。
