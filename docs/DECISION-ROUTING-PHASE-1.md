# DR1：影子路由与连续失败观察

日期：2026-10-06；状态：首批代码与本地隔离验证完成，生产影子观察未启用，PostgreSQL 并发演练未执行。

分方案：[DR-01](DECISION-ROUTING-ARCHITECTURE.md)。本次只交付观察层；自动执行接管和顾问调用不属于本批。

## 已实现

- DecisionRouterService：版本化能力匹配建议、连续失败指纹、副作用优先核验建议。
- 步骤成功领取时，在既有 step_started 事件元数据中写入建议；建议不修改 Agent/执行器。
- 结果通过有效租约、当前计划和 Mission 状态校验后，事务内记录 decision_shadow_observed；重复结果不重复记录，模型伪造的 decision_shadow 字段丢弃。
- 从上一相邻尝试的事件恢复失败计数；重启保留记录，关闭观察造成的间隔不会累计为连续失败。
- 复用已有事件与结果 JSON，无新数据库表、迁移或调度状态机。
- 指挥中心详情展示“路由观察 · 仅建议，未接管执行”、实际 Agent/执行器、失败建议及连续次数。
- 主方案、协同总纲、产品设计和文档目录同步登记 DR-01。

## 修改落点

- `backend/services/decision_router_service.py`
- `backend/services/command_center_service.py`：领取、结果回写、详情投影
- `backend/.env.example`
- `frontend-v2/src/api/commandCenter.ts`
- `frontend-v2/src/views/CommandCenter.vue`
- `backend/tests/test_decision_router_service.py`
- `frontend-v2/src/test/CommandCenterGovernance.spec.ts`

工作区原有多项未提交修改；本批在现有文件上增量接入，未清理或撤销其他改动。

## 验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Router + 证据 + 步骤审批 + Command Center 回归 | 65 passed | [后端日志](review/decision-routing-phase1-20261006/backend-tests.log) |
| 指挥中心治理展示与生命周期 | 11 passed | [前端日志](review/decision-routing-phase1-20261006/frontend-tests.log) |
| 完整前端构建（入口检查、vue-tsc、Vite） | 通过；产物大小提示 | [构建日志](review/decision-routing-phase1-20261006/frontend-build.log) |
| 两个涉及服务的 py_compile | 通过 | 本地命令检查 |
| 本批涉及已跟踪文件 diff --check | 通过 | 本地命令检查 |

后端用例覆盖：重复领取、重启后连续失败、影子升级建议不改变原重试行为、迟到/重复结果拒绝、取消后结果拒绝、未知模式默认关闭、伪造观察丢弃、资源区分、成功重置、未知副作用优先核验及开关切换后的计数间隔。前端验证建议标识、实际执行信息与重复失败次数。

未完成的验证：真实浏览器视觉验收、生产 PostgreSQL 多 worker 并发演练、真实任务长期 shadow 数据。已有测试通过不等于生产接管验收。

## 启用与回退

默认 `COMMAND_CENTER_DECISION_ROUTER_MODE=off`；部署后显式设为 `shadow` 并使运行进程加载配置才会生成新观察。本次未修改生产环境配置、未主动重启服务、未运行数据库迁移。

回退设为 `off`，停止新观察，历史事件保留可读；无活动路由模式。现有执行、审批、证据与副作用规则始终生效。

## 后续

先使用隔离/试点任务检查能力缺口与重复失败建议的准确性，再进入 DR2 的白名单执行器与受控修复。DR1 不声称降低实际模型费用；费用、token、耗时比较需后续真实回执与对照数据。
