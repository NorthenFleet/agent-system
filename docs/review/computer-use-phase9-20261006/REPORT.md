# 第九阶段：只读核实与再次审批闭环

日期：2026-10-06。完成未写入分支的人工恢复闭环，以及已写入分支的防绕过验证。整体优化尚未完成，不能将本次结果外推为所有副作用都能安全恢复。

## 修复

1. verify_effect 审批按钮与确认框改为“批准只读核实”，明确不允许写入、覆盖、删除，也不自动重试原步骤。控制点区分核实待审批和核实未通过，恢复事件使用中文名称。
2. 只读核实确认未生效后，副作用状态记为 not_applied，不再误记为 reverted（已回滚）。
3. 恢复执行回执必须持有未过期租约；即使尚未运行过期扫描，也拒绝过期令牌。数据库更新同样检查到期时间与受影响行数，竞争失败时不继续记录成功。

## Computer Use 实测

使用独立 PostgreSQL 库 agent_system_cu_phase9_20261006、本机 3039 测试页和本次前端构建。身份、初始失败任务、规划与最终评估为受控夹具；文件核实适配器实际检查测试文件，不使用 OpenClaw 模型，不连接外部消息通道。

未写入分支 mission-315d1b800336：

- 浏览器点击批准只读核实，并在明确只读范围的弹窗中确认。
- 实际检查 absent-sample.txt 不存在，恢复项完成，记录 not_applied；原任务仍等待反馈，没有自动重试。
- 浏览器提交“反馈并重新规划”，生成 V2 只读复核方案；界面显示等待计划审批。测试适配器断言此时没有步骤可领取。
- 浏览器再次批准 V2，受控执行器启动真实 Python 子进程检查文件不存在，形成复核记录，严格执行验收和交付门禁均通过，任务 completed。
- 浏览器点击下载记录，落盘文件 /Users/apple/Downloads/step-3cedee07db16-verification.txt 与服务端字节一致。

已写入分支 mission-475d314c45d1：

- 浏览器批准只读核实，适配器确认 applied-sample.txt 已存在；不删除、不覆盖，恢复项 failed，任务保持 waiting_feedback。
- 浏览器提交重新规划意见，系统提示先处理未解决恢复项，未生成新执行计划，未重新执行写入。
- 文件最终仍为原始的一行 preserve-original-once。该分支只证明能正确阻断，未证明能完成已生效操作的补偿。

## 自动验证与加载

- 后端 60 项测试通过，1 个前阶段长等待用例按范围排除；6 条既有依赖弃用提示。新增测试覆盖未生效状态、重新审批前不能派发、过期核实回执拒绝及重新授权要求。
- 前端治理与生命周期 11 项测试通过。
- TypeScript 检查及生产构建通过；有既有大资源包提示。
- git diff --check 通过。
- 确认生产活跃任务、运行步骤均为 0 后，加载前后端更新并重启现有 API 和 worker。浏览器复核运行门禁就绪、2/2 在线、失联 0、过期租约 0。
- 生产旧入口文件已保留为 previous-production-index.html；部署没有删除旧静态资源，也没有改写历史任务或切换全局严格模式。

## 剩余范围

已写入后，现有 verify_effect 合同只能核实，不能直接转为恢复写入授权；失败恢复项也阻止普通反馈重新规划。这保障了不误执行，但“提出新的恢复合同、再次审批、执行并核验”的产品入口与闭环仍需下一阶段完善。不得以放行普通反馈或伪造完成状态绕过。

尚未验收生产身份权限下的完整恢复操作、真实 OpenClaw 补偿执行和长时间稳定性。3039 仅为本机隔离测试适配器，不能作为生产 API 验收。

## 证据

- fixtures.json、absent-verified.json、absent-feedback.json：初始夹具、真实核实与再次审批状态。
- applied-verified.json、applied-feedback.json：已写入分支的阻断记录。
- execution-result.json、final-mission.json、summary.json：严格验收、最终结果和下载校验。
- reapproval.jpg、completed.jpg、applied-blocked.jpg、final-ui.txt：浏览器实测证据。
- backend-tests.txt、frontend-tests.txt、build.txt：自动检查结果。
- production-health.txt、source-final.json：更新后健康状态和源码校验值。
- backend/scripts/run_phase9_recovery_lab.py：隔离测试适配器；backend/tests/test_phase9_recovery_verification.py：新增回归。
