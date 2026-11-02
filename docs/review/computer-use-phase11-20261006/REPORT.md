# 第十一阶段：真实 OpenClaw 恢复与重试闭环

日期：2026-10-06。结果：隔离任务 mission-6ecde497f875 已完成，真实恢复、只读验收和擎天柱总验收通过，严格交付门禁 100 分。首次恢复遇到模型超时，确认未进入工具执行后，经页面重新审批成功；失败历史完整保留。整体优化尚未全部结束，下一阶段应覆盖恢复写入中断与持续稳定性。

## 本阶段修复

1. 恢复 worker 原先读取不存在的 attempt_count，导致恢复会话使用 a0，且没有区分新旧合同。现按合同指纹前 16 位及真实 attempts 构造会话；核实、新合同恢复、同合同重试分别为 a1、a2、a3。相同合同的重试继续保留原幂等键。
2. 已失败的 manual_recovery 在后台可重新审批，页面却没有操作入口。补充管理员“重新审批补偿”，沿用原合同确认弹窗，明确失败不等于未生效、需先核实实际状态及方案可重复执行性。点击入口或取消弹窗均不会执行；确认后才提交审批。
3. 真实核实模型将 original_effect.fingerprint 与内容哈希比较，产生不可靠的“可能被覆盖”推测。已在生产补偿提示中说明它是副作用记录去重标识，不能用来判断文件内容。原始错误说明保留，没有改写历史证据；该提示不能保证模型以后绝不误判。

## 实际浏览器流程

独立 PostgreSQL：agent_system_cu_phase11_20261006；页面端口 3041；恢复项 compensation-689d55d499d3。生产前端配合真实服务类及完整 CommandCenterWorker，OpenClaw 使用 ratchet 执行、optimus 总验收。

| 调用 | 实际结果 |
| --- | --- |
| 1：批准只读核实 | 实际 exec 读取样本，返回 failed，维持阻塞；sample、backup、guard 内容未变 |
| 提交新恢复方案 | 新合同进入 pending_approval，不可领取；样本仍是 changed-by-test |
| 2：批准恢复 | 模型等待 180 秒超时；轨迹显示 timeout → interrupted，无工具调用；未产生副本或回执 |
| 3：重新审批恢复 | 核对会话已结束且文件未变后，测试超时改为 300 秒。新会话约 67 秒返回，实际 exec 保留副本、恢复样本并创建回执 |
| V2 计划提交及批准 | 反馈重新规划为只读验收，批准前不会执行；原 V1 写入保持 failed、尝试次数 1 |
| 4：只读验收 | 实际 exec 核实四份文件及回执，严格执行门禁 100 分；验收前后文件哈希不变 |
| 5：总验收 | optimus 根据已持久化证据判定通过，任务 completed，最终交付门禁 100 分 |
| 下载 | 浏览器下载 recovery-receipt.json，与服务器回执逐字节一致 |

恢复前 sample 为 changed-by-test 加换行，backup 为 before-change 加换行。恢复后 sample 与 backup 一致；before-recovery.txt 保留原改写内容，guard.txt 始终保持 must-stay-unchanged 加换行。独立检查回执的 contract_hash 与 idempotency_key 均与批准合同一致。补偿累计 3 次尝试（核实、超时恢复、成功恢复），原写入步骤没有重放。

## 检查和部署

- 后端 66 项回归通过（backend-tests-final.txt），包含真实 worker 调用接线的不同合同/不同尝试会话隔离测试；有 6 条既有弃用提示。
- 前端治理与生命周期 11 项测试通过；治理用例增加恢复失败后的入口、取消不执行、确认提交原合同的验证。
- 类型检查与构建通过（build.txt），保留既有大资源包提示。git diff --check 通过。
- 在生产活跃任务和运行步骤均为 0 后部署前端并重启原 API/worker；旧入口保存于 previous-production-index.html，未删除历史静态资源。
- 浏览器复核生产：2/2 worker 在线，失联 0，过期租约 0。全局生产证据模式未改变，历史任务及警告未清理。
- 隔离通知发送器禁用外发，数据库 sent 数量为 0。五次模型调用中，成功的核实/恢复/验收回执均记录 exec；总验收没有额外工具调用。

## 边界与下一阶段

初始写入失败、测试身份和 V2 计划为夹具；本阶段没有再次制造原始写入崩溃。恢复、只读验收、最终评估由真实 OpenClaw 完成，未用固定适配器伪造成功。测试环境启动时的数据库配置问题及首次真实模型超时均记录在日志中，未算作成功运行。

本次证明单个本地文件恢复在明确前置条件和幂等合同下可完成，不证明任意外部工具恰好执行一次。第一次超时发生在模型响应阶段，不能替代“写入已发生但回执未落库”的恢复中断测试。页面重新审批要求管理员先核实实际状态；尚无通用的自动核实后安全重放保证。

下一阶段优先测试：恢复写入完成、回执落库前的进程中断；确认不会重复覆盖或丢失副本；将核实证据引用做成可稳定定位的记录，再开展连续运行与并发故障验收。首次只读核实使用的部分证据引用仍是描述性文字，真实工具调用可从执行回执追踪，但引用的可定位性仍需加强。

## 证据索引

- summary.json、final-mission.json、final-compensations.json、all-plan-steps.json：最终结果和旧计划历史。
- call-1 至 call-5 的 invocation/result.json：真实调用与原始返回；调用 2 是保留的超时失败。
- recovery-trajectory.txt、retry-trajectory.txt：超时和重试会话轨迹。
- recovery-proposed.json、recovery-receipt.json、independent-file-check.json：待审批合同、真实恢复回执、独立哈希检查。
- backup.txt、applied-sample.txt、before-recovery.txt、guard.txt：隔离样本及保护文件。
- awaiting-approval.jpg、completed.jpg、final-ui.txt：Computer Use 审批及交付证据。
- production-health.txt、source-final.json：部署健康检查与源码哈希。
- backend/scripts/run_phase11_real_recovery_lab.py：可续跑、保留历次调用文件的隔离实验入口。仅限本机测试，不能作为生产认证服务使用。
