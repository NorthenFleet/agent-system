# DR-01 决策路由与旁路顾问架构

版本：1.3；日期：2026-10-08；范围：agent-system 指挥中心。DR1–DR4 核心实现与本地验证完成，生产未启用；各批边界与未完成项见实施记录。

## 1. 目标与现状

在已有“规划 → 依赖调度 → 专业执行 → 证据检查 → 最终评估”上增加可解释路由、重复失败诊断、旁路顾问和模型消耗观测。主方案见 [闭环总体方案](SYSTEM-CLOSURE-MASTER-PLAN.md)，跨域约束见 [协同总纲](SYSTEM-COORDINATED-OPTIMIZATION-PLAN.md)。

当前 CommandCenterWorker 使用 Optimus 规划和评估，普通步骤通过 OpenClaw agent_run 整轮调用。AgentTeamService 管理协作事实，不派发；LangGraph 当前为审批中断试点，不能视为完整 Agent 执行图。GitWorkspaceService 已支持开发循环的 worktree 隔离，但普通 Mission 不因此自动获得隔离。

## 2. 目标结构

```text
任务 → 主控规划 → 契约校验/既有审批 → Decision Router
                                     ├─ 受限确定性执行器（DR2）
                                     ├─ 专业 Agent（已有）
                                     └─ 升级主控（DR2+）
执行结果 → 证据/副作用门禁 → 最终评估 → 交付
                 └─ 失败诊断 → 受控修复
检查点顾问（DR3）：计划后、重复失败时、交付前；仅返回结构化建议
```

Router 不授予权限、不决定业务终态、不绕过审批。模型名与推理档位未来通过适配器配置，不硬编码截图中的品牌或宣传数字。

## 3. 分批范围

| 批次 | 内容 | 完成门禁 |
| --- | --- | --- |
| DR1 | 步骤级影子路由、事件持久化、连续失败识别、指挥中心展示 | 开关关闭兼容；观察不改执行结果；重启可恢复计数；旧租约无新增记录；页面区分建议/实际 |
| DR2 | 白名单确定性执行器、预算、受控重新规划与修复 | 审批/幂等/租约/证据保持有效；未知副作用先核验；不接受任意模型 shell |
| DR3 | 检查点只读顾问、模型档位、代码工作区隔离和集成 | 顾问工具权限实际只读；产物哈希/版本可追溯；合并后验收；消耗真实可核验 |
| DR4 | 工具执行前后钩子或可控 Agent 循环 | 先验证 OpenClaw 扩展能力；执行前可拦截、执行后有回执；不能用事后日志冒充控制 |

DR1 不启动真实顾问，不自动停止或重试，不改变 Agent，不声称实现确定性执行接管。规则先验证；置信概率和学习型路由不纳入本批。

## 4. DR1 契约与持久化

新增 DecisionRouterService 纯规则服务；模式为 off/shadow，未知值按 off。默认 off。

决策字段：mode、enforced=false、policy_version、mission_id、plan_version、step_id、attempt、phase、action、reason_code、detail、actual_executor、actual_agent_id。结果观察另含 failure_fingerprint、consecutive_failures、repeated_failure。

- 领取步骤通过依赖/审批且成功获取租约后，在同一事务的 step_started 元数据记录 routing_decision。
- 结果通过租约、有效计划和 Mission 状态的条件更新后，在同一事务写入 decision_shadow_observed。事件键为 decision-shadow:{step_id}:{plan_version}:{attempt}。
- 复用 mission_events，无新增表/迁移；事件继续携带既有 mission_run_id/correlation_id。模型返回的 decision_shadow 丢弃，服务端重新生成。
- 本次结果附带 decision_shadow，详情 API 从当前尝试的 step_started 事件投影 routing_decision，不建立第二套事实库。
- cluster_operation 与非 OpenClaw 执行不纳入 DR1。off 不清理既有历史记录。

## 5. 路由与失败规则

派发观察：已注册 Agent 支持任务类型且必需工具可用 → delegate；能力/工具缺口 → escalate。实际仍执行当前已批准计划。

结果观察：现有门禁通过 → continue；失败且副作用声明不明确或回执含 applied/unknown → inspect；其余连续相同失败至少两次 → escalate；第一次失败 → review。这里的 action 是建议，不改变原 completion_decision。

指纹由错误类别、任务类型、工具、资源、协议错误及门禁阻断信息的规范化值生成 SHA-256。只规范空白，不抹去数字/路径，避免不同错误误归并；观察记录不重复存原始报错。只累计同一步骤/计划、相邻 attempt、同策略版本的记录；成功、观察缺口、错误变化均重置。第一版不识别语义相似报错或跨步骤循环。

## 6. 展示与运行

现有指挥中心增加路由观察区：明确“仅建议，未接管执行”；展示实际执行 Agent/执行器、建议原因、连续相同失败次数。继续使用现有时间线，不新增虚假进度或成本面板。

配置 COMMAND_CENTER_DECISION_ROUTER_MODE=shadow 可开启观察；默认 off。上线前在隔离环境回放典型任务，核对建议与实际结果；生产启用/进程重启独立于本批代码实现。回退为 off 后不再生成新记录，原执行链继续，历史记录仍可读。

## 7. 验证与后续指标

DR1 覆盖开关、重启、重复领取、迟到/重复结果、连续失败与成功重置、副作用不明、前端标识及构建。复用现有审批、证据和 Command Center 回归。生产 PostgreSQL 并发演练另行记录，不以 SQLite 隔离测试代替上线结论。

后续衡量路由覆盖率、升级建议准确率、重复失败次数和质量验收通过率；DR2 后比较实际模型调用量与耗时。没有模型用量回执时标未知，不声明已省多少费用。

## 8. DR2 实施增补（2026-10-06）

详细契约、示例、预算、回退与证据见 [DR2 实施记录](DECISION-ROUTING-PHASE-2.md)。本批确定性白名单为内联文本哈希对比和 JSON 顶层必需键检查；显式计划绑定执行器，不依赖模型自由路由。保留既有审批与租约，严格验收，使用既有账本持久化报告。

新增独立配置 `COMMAND_CENTER_DETERMINISTIC_ENABLED` 和 `COMMAND_CENTER_RECOVERY_CONTROL_ENABLED`，默认 false。恢复控制可阻止重复失败或耗尽预算后的原步骤重试，经反馈进入新计划审批。最多三个计划版本；未接入顾问、任意 shell/文件工具或模型成本预算。第 4–6 节继续描述 DR1 的纯观察语义；DR2 实际阻断以独立 `recovery_control` 表达，关闭功能不删除历史控制记录。

## 9. DR3 实施增补（2026-10-08）

[DR3 检查点顾问、模型档位与隔离代码候选](DECISION-ROUTING-PHASE-3.md) 核心实现与本地验证完成。顾问通过工具禁用配置审查计划、重复失败和交付检查点；请求模型与实际回执分别记录。显式代码执行器只在批准基线上创建工作树，通过 Git 事实生成候选回执，不能承诺未执行的测试或自动合并。

生产仍关闭。源仓库集成与合并后验证、真实模型试点、PostgreSQL 并发演练和浏览器视觉验收尚未完成；本批没有用候选生成代替正式交付。完整契约、开关、权限依赖与故障边界以 DR3 实施记录为准。

## 10. DR4 实施增补（2026-10-08）

[DR4 工具调用控制与持久化回执](DECISION-ROUTING-PHASE-4.md) 在隔离代码执行器内引入四个受控文件工具。调用前复核租约、工作区与预算并持久化意图，调用后保存回执；缺失回执或未知副作用阻止候选通过。实际安装的 OpenClaw 插件加载与工具策略已本地验证，插件缺失不开放原生工具。开关默认关闭；真实模型、生产并发、视觉验收和源仓库集成仍待验证。
