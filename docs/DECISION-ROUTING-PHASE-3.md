# DR3：检查点顾问、模型档位与隔离代码候选

日期：2026-10-08。状态：核心实现与本地隔离验证完成，生产默认关闭。正式源仓库合并、真实模型试点、PostgreSQL 并发演练及浏览器视觉验收尚未完成。

对应 [DR-01 架构](DECISION-ROUTING-ARCHITECTURE.md)。DR3 本批交付到可审查代码候选，不把候选生成标成源仓库集成完成。既有 GitWorkspaceService 集成分支功能仍属于原开发循环，本批没有添加绕过审批的自动合并入口。

## 1. 检查点顾问

接入计划保存后、连续失败后和最终评估前三个检查点。每个 Mission/计划版本/检查点只领取一次；在 Mission 行上串行化领取，再用唯一事件键持久化请求与结果，复用现有 mission_events，不新增事实库。

顾问输入只包含目标、最多 12 个步骤、裁剪后的验收项、结果摘要、阻断、证据引用和候选提交。输入最多 50 KB，输出最多 16 KB/8 个发现；引用必须来自输入。顾问无法自动批准计划、改写代码或宣布正式验收。无效结果、未配置模型、超时和执行失败记录 unavailable；取消时 interrupted；原计划过期或任务终结后返回的意见 discarded。

顾问使用独立 `openclaw agent exec --config ... --cwd ...`：配置禁用全部工具 `deny=["*"]`、禁用插件、关闭 shell 环境导入、跳过工作区 bootstrap；使用临时空目录，不继承常规 Agent 的工作目录及工具配置。提示词走 stdin。CLI Agent 类型的模型后端被拒绝，避免其独立工具执行绕过 OpenClaw 策略。凭据仍由运行环境或 OpenClaw 已支持的凭据发现提供，本批不复制凭据。

意见通过现有事件进入页面，同时作为只读参考传给最终评估和后续重新规划；不能代替证据门禁。当前意见不阻止用户在顾问完成前审批计划。

故障边界：进程硬崩溃可能留下 advisor_requested 而没有结果；重启不自动重复调用该检查点，以防重复费用。记录保留供检查，后续重新规划版本可重新审查；本批未做自动重放界面。

## 2. 模型档位

配置角色为 planner、worker、advisor；每个角色可设置 model/thinking。任务输入不能覆盖工具策略或角色配置。普通规划、执行、评估通过 OpenClaw CLI 原生参数传递；配置明确档位而 CLI 不可用时，不悄悄回退到不能保证该档位的 HTTP 路径。

请求模型与实际回执分开：requested_model/requested_thinking、actual_model/actual_provider、usage/cost_usd。隔离 exec 使用其 JSON envelope 的原始实际回执，未提供即 null；普通 Agent 路径当前实际模型与费用仍为未知，不据此宣称消耗或节省。规划/评估记录模型档位事件，步骤结果和顾问结果分别携带回执。

模型名称不写死。隔离角色必须显式配置 `provider/model`；缺失时拒绝执行或记录顾问不可用，不借用未指定的模型。

## 3. 隔离代码候选

批准计划明确选择 `executor=isolated-code-v1`，仅用于 backend/frontend/api/database/ui。输入严格为 `repository_id` 与完整 `base_commit`。仓库 ID 到路径的映射和工作树根目录由运维配置；模型不能任意指定工作目录。

执行前验证仓库 HEAD 与批准基线一致，创建 `codex/mission-{step_id}-attempt-{attempt}` 工作树并记录受租约保护的 code_workspace_prepared 事件。目录或分支已存在时不重用，防止重启后重复执行遗留候选。源目录的未提交修改不会复制到新工作树。

代码角色只开放 read/write/edit，fs.workspaceOnly=true，显式禁用 apply_patch 的隐式别名、插件与 shell。Git 管理操作由服务端执行，关闭 hooks、fsmonitor 和提交签名。工作树修改通过服务端 checkpoint 形成候选提交，保存基线、分支、提交、差异 SHA-256、摘要和是否截断；源工作分支不被合并或覆盖。下游交接携带候选路径、分支、基线、提交和差异哈希，使独立测试能定位到候选而非误测源工作区。

验收契约固定为“已形成可审查的隔离代码候选”，产物 code_diff，证据 diff_summary，默认且仅允许一次尝试。它不承诺运行测试或完成源仓库集成。模型返回内容不作为候选验收证据；服务端根据 Git 提交与干净工作树生成结果及副作用回执。无新提交或工作树不干净不能声称候选通过。

候选使用独立 isolated_code_candidate 能力回执，不冒充 Codex CLI 调用；仍走 WorkRun、strict 证据门禁及当前租约的结果回写。失败/崩溃后的工作树保留，供人工检查；不会自动删除、推送、合并、部署。若用户目标要求正式交付，规划提示要求另设独立验证与获准集成，不得以候选替代最终目标。

## 4. 配置

```text
COMMAND_CENTER_ADVISOR_ENABLED=false
COMMAND_CENTER_CODE_WORKSPACE_ENABLED=false
COMMAND_CENTER_PLANNER_MODEL=
COMMAND_CENTER_PLANNER_THINKING=
COMMAND_CENTER_WORKER_MODEL=
COMMAND_CENTER_WORKER_THINKING=
COMMAND_CENTER_ADVISOR_MODEL=
COMMAND_CENTER_ADVISOR_THINKING=
COMMAND_CENTER_CODE_REPOSITORIES={}
COMMAND_CENTER_CODE_WORKTREE_ROOT=
```

顾问 90 秒 deadline，隔离代码执行最多 900 秒，通用隔离输入上限 100 KB、返回 envelope 事后大小检查上限 2 MB。取消/超时终止直接子进程；本批不声称提供完整容器级隔离。权限依赖经过验证的 OpenClaw 工具策略与工作目录约束，升级运行时必须重新验收。

关掉顾问开关后不再领取新检查点；已开始调用可能完成。关掉代码开关后停止领取新候选，执行函数入口也复核配置；已运行的调用由原租约和取消机制管理。回退不删除既有意见、候选提交或事件，不把待执行候选改派到普通 Agent。

## 5. 文件落点

新增：

- `backend/services/agent_execution_profile_service.py`
- `backend/services/isolated_agent_executor.py`
- `backend/services/checkpoint_advisor_service.py`
- `backend/services/mission_code_workspace_service.py`
- 三个对应测试模块。

接入：CommandCenterService/Worker、OpenClawTaskExecutor、PlanQualityService、指挥中心/API 类型与 .env.example。页面显示检查点意见、请求/实际模型，以及“隔离代码候选 · 尚未合并”。已有 DR1/DR2 行为在默认关闭时保持兼容。

## 6. 验证记录

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| DR3、DR1/DR2、证据、审批、Command Center、Git 工作区、集群兼容和 WorkRun | 122 passed | [后端日志](review/decision-routing-phase3-20261008/backend-tests.log) |
| 指挥中心治理展示、生命周期 | 11 passed | [前端日志](review/decision-routing-phase3-20261008/frontend-tests.log) |
| 完整构建：入口检查、vue-tsc、Vite | 通过；大 chunk 提示 | [构建日志](review/decision-routing-phase3-20261008/frontend-build.log) |
| 本机 OpenClaw 2026.8.2 配置 schema 校验 | 顾问/代码配置有效，无警告 | [运行时策略检查](review/decision-routing-phase3-20261008/runtime-policy-check.log) |
| 本机 OpenClaw 实际 policy matcher | 顾问 deny-all；代码只允许 read/write/edit | 同上 |
| 相关服务 py_compile、修改文件 diff --check | 通过 | 本地检查 |

整链测试确认代码修改仅发生在临时 Git 工作树，WorkRun/产物持久化成功，源文件保持原内容；模型“已运行测试”的自述不会进入验收事实。顾问覆盖重复领取/重启幂等、取消和换版丢弃、虚构引用拒绝、不可用不改业务状态；执行器覆盖模型档位不静默降级及超时终止。

运行时策略检查未调用真实模型，测试中的模型执行使用替身。上述结果不是生产 PostgreSQL 并发验收，也不是恶意模型端到端攻击测试。正式源分支合并及合并后验证仍须在单独批准的集成流程中完成。
