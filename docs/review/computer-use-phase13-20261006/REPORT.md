# 第十三阶段：缺失、损坏与不匹配恢复回执

日期：2026-10-06。本阶段完成本地 manual_recovery 回执实质校验，并通过浏览器验证三个负向样本及一个有效回执的重新审批闭环。整体优化仍未全部结束。

## 发现与修复

原补偿结果仅要求成功状态、摘要、非空 receipt_ref 和 evidence_refs；即使引用文件不存在，仍可能判定补偿完成。

现在 manual_recovery 声称 reverted/not_needed 时，后端必须实际完成以下检查，才允许将恢复项更新为 completed：

- receipt_ref 指向允许交付目录中的普通文件，禁止符号链接；复用现有产物读取器及 5MB 上限。
- 文件 SHA256 与执行结果 receipt_sha256 一致，内容可解析为 JSON 对象。
- 回执中的 contract_hash、idempotency_key、resource 与当前恢复合同逐项一致。
- verification.all_passed 必须为布尔 true，证据列表必须包含被验证的回执路径。
- 当前资源实际内容的 SHA256 必须等于回执 post_recovery_sha256，资源也受相同路径与普通文件读取约束。

失败时保存 receipt_validation 及阻断原因，恢复项 failed，原副作用继续 unknown，不会自动重试或替执行器生成回执。成功时保存回执和资源哈希。worker 提示及结构化返回解析已支持新字段。缺失及损坏文件有中文原因提示。

适用范围仅为新恢复方案类型 manual_recovery；verify_effect 及其他既有补偿类型保留原协议。没有专用验证器的远端资源、允许目录外资源及非普通文件不能通过本地恢复门禁。

## 浏览器与数据库验证

使用独立数据库 agent_system_cu_phase13_20261006 和本机 3043 页面。身份、原始失败、核实、恢复方案、恢复响应及 V2 计划为夹具；恢复响应故意声称成功，以证明实际服务会拒绝无效证据。三个样本在测试准备阶段已处于恢复后状态，审批期间不重新写入。

| 样本 | 浏览器操作及结果 | 最终状态 |
| --- | --- | --- |
| 回执缺失，mission-6f67978cafd2 | 批准后因文件不存在拒绝；再审批时引用预先保留的另一份有效回执，通过合同与资源校验；V2 只读验收再审批 | completed，严格门禁 100 |
| 回执损坏，mission-9ca4afe49103 | 实际文件存在且所报 SHA256 正确，但 JSON 损坏，拒绝声称成功的结果 | waiting_feedback，补偿 failed |
| 幂等键不匹配，mission-b0a1fde1f8ae | JSON 和哈希正确，但回执幂等键不属于当前合同，拒绝 | waiting_feedback，补偿 failed |

三个负向样本都无法被自动领取重试。后两个样本故意保持阻塞，属于预期通过的拒绝测试，不代表本阶段遗漏修复。

正向样本的独立只读验收由真实 OpenClaw ratchet 执行，optimus 总验收通过，执行和最终交付门禁 strict/100。浏览器下载 missing-receipt-valid.json，与服务端逐字节一致。

独立审计确认：重新审批与只读验收前后，样本、备份、保护文件、保留副本及已有回执的 SHA256 和修改时间未变；原缺失路径仍不存在，损坏文件未覆盖，旧证据保留；所有原步骤尝试次数仍为 1；通知 sent=0。

## 测试与部署

- 82 项后端测试通过（backend-tests-final.txt），含本阶段 13 种回执输入：有效、缺失、损坏、错误哈希、错误幂等键、错误合同、错误资源、资源内容变化、非布尔通过值、缺少回执证据引用、目录越界、符号链接、未提供哈希。
- 既有恢复审批正向测试更新为真实本地回执，未通过绕过新门禁维持测试通过。
- 仍有 6 条既有弃用提示；git diff --check 通过。
- 前端源码和构建未改动，本阶段沿用已部署页面；不把上一阶段前端测试或构建记作本阶段新结果。
- 生产活跃任务、运行步骤和运行补偿均为 0 后，重启既有 API/worker 使校验生效。浏览器复核门禁就绪、2/2 在线、失联 0、过期租约 0。
- 损坏样本首次运行显示底层 JSON 解析错误，随后将新返回改成中文可读原因。原测试历史保留，不回写更改错误记录。

## 新本地恢复回执约定

执行结果需要 receipt_ref、receipt_sha256、evidence_refs；回执 JSON 至少包含：contract_hash、idempotency_key、resource、post_recovery_sha256、verification: {all_passed: true}。两处哈希都必须由实际文件字节计算，不能填写事件 fingerprint。

目录沿用 COMMAND_CENTER_ARTIFACT_ROOTS，未配置时为仓库 docs/review。此阶段未扩大任何读取目录或工具权限。旧 manual_recovery 执行器如果仍返回描述性引用或不提供回执哈希，将保持阻塞，需要按新约定提交证据；历史已完成任务不会自动重新评估。

## 验证边界与下一阶段

这是回执完整性、合同绑定及当前资源内容的一致性检查，不是签名认证，也不能单凭执行器填写的“恢复后哈希”证明所有业务目标已经恢复。本次由后续只读验收补充检查备份一致性。

本阶段没有模拟新的进程崩溃、文件写到一半或远端工具故障；也没有测试自动重建丢失回执。正向场景使用另一份预先准备且保留的有效回执，没有伪造缺失文件。校验只反映读取时的文件状态，不保证文件未来不变化。

下一阶段建议开展有限时长的持续运行和并发任务验收，同时检查回执验收后发生变更时的交付表现；远端工具需要专用验证器，不能直接套用本地文件结果。

## 证据

- negative-cases.json：三种负向结果及实际校验原因。
- final-missions.json、final-compensations.json、all-plan-steps.json、summary.json：最终状态、合同校验、次数及下载结果。
- file-baseline.json：重新审批前的文件哈希及修改时间。
- *-receipt-invalid.json、*-receipt-valid.json：保留的异常和有效回执；missing-receipt-invalid.json 按设计不存在。
- call-1 至 call-4 为夹具恢复响应；call-5、call-6 为真实 OpenClaw 只读执行与总验收。
- missing-blocked.jpg、completed.jpg、final-ui.txt、corrupt-ui.txt、mismatch-ui.txt：Computer Use 证据。
- production-health.txt、source-final.json：部署健康及源码指纹。
- backend/scripts/run_phase13_receipt_integrity_lab.py：仅限本机的隔离测试入口，不是生产认证服务。
