# 第十六阶段：重新交付端到端验收

日期：2026-10-07。结论：本轮隔离场景通过，完成“旧文件下载异常→重新交付草稿→提交新任务→审批→真实创建新文件→验收→浏览器下载”。没有发现需要修改生产代码的新问题。

## 范围

使用独立 PostgreSQL 数据库 agent_system_cu_phase16_20261007、本机 3046 页面和第十五阶段隔离前端构建。旧任务为只读快照，新任务实际入库。身份和固定规划内容是测试夹具；领取、审批、执行、证据门禁、任务验收和下载校验使用现有服务逻辑。规划使用 general 流程，不代表已经验证文档业务流的完整自动规划能力。

真实 CommandCenterWorker 调用 OpenClaw：救护车创建并核实指定新文件，擎天柱进行最终验收。发送器禁止外发，记忆服务未接入。旧任务没有迁入该测试数据库，不能将快照不变扩大解释为生产旧任务数据库的关联更新测试。

## 执行结果

| 环节 | 证据与结果 |
| --- | --- |
| 原交付异常 | 浏览器下载返回 409，显示文件版本不一致 |
| 生成草稿 | 自动带入原任务 phase16-delivery、产物 phase16-artifact、原路径、登记哈希和失败原因 |
| 提交 | 新任务 mission-c872ccc3b49e 入库，待批准，计划质检 100 分 |
| 批准前隔离 | claim_ready_steps 返回空，新文件不存在；before-approval.json 保留该时点状态 |
| 浏览器批准 | 新任务从 awaiting_approval 进入 running |
| 实际执行 | 仅创建 redelivery-v2.txt，内容严格为 Phase 16 redelivery verified 加一个换行 |
| 执行回执 | 1 份文档产物、1 条证据、1 条已生效副作用记录，step attempt_count=1 |
| 严格证据门禁 | execution_evidence：strict、accepted=true、100 分 |
| 最终验收 | 擎天柱 verdict=passed；delivery_evidence：strict、accepted=true、100 分；任务 completed |
| 浏览器下载 | 下载新文件成功，本地下载字节与新文件、登记哈希一致 |
| 刷新后复核旧任务 | 原版本异常仍返回 409，新任务没有覆盖旧任务证据 |
| 最终审计 | 运行中步骤 0，补偿 0，sent 通知 0，执行账本 1 条 |

新文件 SHA256：81958895056ace0081d81ec842a60ef17e69c3501e9a2039637b1e77e139d008。

下载位置：/Users/apple/Downloads/redelivery-v2.txt。

baseline.json 中的本阶段旧文件、旧任务快照、第十五阶段任务快照及第十三阶段最终任务记录，最终 SHA256 和修改时间全部保持不变。旧文件原登记哈希与当前内容哈希的差异被保留，不回写原登记值。

## 质量检查与发布状态

新增测试脚本通过 Python 编译检查；独立审计断言通过；git diff --check 通过。前端相关源码哈希与第十五阶段一致，复用其已通过 13 项测试和构建的隔离产物；本阶段没有重复计入新的前端测试或构建结果。

本轮只新增实验脚本与证据，不修改生产实现。第十五阶段前端变更仍未发布到生产 frontend-v2/dist；当前工作区同时有其他模块改动，尚未完成统一发布范围复核。

这是一次受控本地文件重新交付正向场景，不是任意产物、远端系统、并发重新交付或重复提交的完整保证。原任务与新任务目前通过草稿目标文本保留引用，没有新增结构化版本关系或双向导航。

下一阶段应整理待发布变更范围，补充重新交付入口的组件回归检查，并在隔离预览复核后发布已确认的前端范围；后续再扩展失败分支和结构化版本追溯。

## 证据索引

- submitted-body.json、before-approval.json、before-approval-ui.txt：从草稿到待批准的真实输入和状态。
- call-1-invocation.json、call-1-result.json：真实执行器输入和返回。
- call-2-invocation.json、call-2-result.json：真实最终验收输入和返回。
- final-mission.json、work-runs.json、summary.json：最终门禁、执行账本与断言结果。
- downloads.jsonl：旧文件拒绝、新文件下载成功、旧文件再次拒绝的记录。
- baseline.json、source-hashes.json：旧证据与源码版本基线。
- completed-ui.txt、completed.png、old-task-after-redelivery.txt：Computer Use 页面证据。
