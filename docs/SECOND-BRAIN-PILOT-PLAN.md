# 第二大脑受控试点：准备、证据采集与验收

**日期**：2026-10-07（Asia/Shanghai）  
**所属方案**：[SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)，接续 [SB4](SECOND-BRAIN-PHASE-SB4.md)  
**状态**：试点证据采集 CLI 与隔离验证已完成；2026-10-07 已完成实际范围与基础配置，预检通过，详见[配置记录](SECOND-BRAIN-PILOT-CONFIGURATION.md)。真实项目试点尚未初始化，观察时钟未开始；正式上下文注入、原生记忆桥接及自动调度保持关闭。

## 1. 首次预检（配置前，历史记录）

对工作区根 `.env`、3021 启动定义和本次 shell 的相关配置进行脱敏检查；随后对根 `.env` 执行只读预检，结果见 [preflight.json](review/second-brain-pilot-20261007/preflight.json)。没有读取/输出凭证值，没有修改环境文件或运行生产迁移。

| 项目 | 结果与含义 |
| --- | --- |
| 知识权威 `DATABASE_URL` | 所检查配置中未提供 PostgreSQL URL，预检不通过 |
| 私有来源根目录 | 未配置，预检不通过 |
| 试点 owner | 未配置；现有项目与实际 owner 尚未选定 |
| 旧 Context Pack SQLite 路径 | 尚未显式配置，任务证据采集不能启动 |
| PDF 解析依赖 | 可用 |
| 知识/WorkRun schema | 因知识权威配置前置条件未满足而**未检查**；不表示已证实数据库或表不存在 |
| WorkRun 连接类型 | 根 `.env` 提供 PostgreSQL 配置；本批未探测其实际连通性和表结构 |

以上为配置前的历史结果。后续已选定 `workflow-pilot-20261002` / owner `1`，配置实际 PostgreSQL `team_dashboard.second_brain`、私有来源目录及既有 Context Pack 数据库，并重新预检通过；见[实际配置记录](SECOND-BRAIN-PILOT-CONFIGURATION.md)及[新预检报告](review/second-brain-configuration-20261007/preflight.json)。服务未重启，报告不证明运行中进程已经加载新配置，真实观察未开始。

## 2. 本批工具

- [knowledge_pilot.py](../backend/scripts/knowledge_pilot.py)：`preflight / init / observe / task / review / report`。
- [pilot.py](../backend/services/knowledge/pilot.py)：私有证据账本、任务/快照关联校验、时间窗口和评估。
- [test_pilot.py](../backend/tests/knowledge/test_pilot.py)：23 个新增用例；全知识域 **144 项通过**，见 [测试日志](review/second-brain-pilot-20261007/backend-tests.txt)。

没有数据库迁移或前端改动。沿用 SB4 界面、知识权威和审核流程；本批没有重新运行与改动无关的前端构建。

### 2.1 私有证据账本

试点初始化要求基础预检通过，并实时确认 owner/space/project 授权、知识总开关/写开关、`shadow` 模式及项目到空间的准确映射；当前存在失败入库或投影死信/漂移时不能开始。初始化失败不创建试点目录，不开始计时。

账本在运维明确选定的私有目录中保存，目录 0700、文件 0600；拒绝符号链接和不安全权限。配置包含试点范围、实际初始化时间和预检哈希；事件保存采集时间、序号、前一条哈希及自身哈希。并发写入使用文件锁，整份事件文件通过 fsync + 原子替换更新；最多 1,000 条、10 MiB。

记录包含内部标识和评审指标，依然是私有数据，**不应提交仓库**。不复制资料正文、任务目标、Context Pack 查询、完整执行上下文或 DSN。哈希链校验用于检测损坏和意外漂移，不是数字签名，也不能抵抗能重写全部文件的运维人员；最终验收仍需独立确认。

### 2.2 任务证据必须来自现有权威

一次任务采集必须同时满足：

1. Mission 属于指定 owner/project，状态 completed，完成时间在本次试点开始之后且不来自未来。
2. WorkRun 属于同一 Mission/project，状态 completed，结束时间也在试点期间。
3. 读取真实 WorkRun `input_context.context_binding`，并核对 Mission 的 `mission_context_bindings`：绑定 ID、Context Pack ID、计划版本、step ID 和 `mission-step:<step>` dispatch 一致；绑定状态 ready/empty。
4. Context Pack 的 user/project/mission 一致，shadow 元数据确实 captured、未注入、旧记忆顺序未改变。
5. 独立知识快照属于同一空间、哈希与基线引用摘要匹配，且通过原 SB3 当前授权、TTL、修订和完整来源依赖检查。

Mission/WorkRun 采用显式 PostgreSQL 连接，只执行只读事务，设置查询超时；旧 Context Pack SQLite 使用明确路径与 `mode=ro`，不导入会自动建表的旧服务单例，不创建缺失数据库。不同权威之间没有跨库原子快照承诺，采集记录只证明采集时所核对的状态。

同一 Mission 只计一次，即使重试或提供多个执行步骤也不能凑成多个真实任务；重复同一证据返回原回执，内容不一致则拒绝覆盖。计数名为 `verified_tasks`，表示权威关联已核验，**不自动证明任务具有真实研究价值**；后者需要人工明确评审。

现有 shadow 快照 TTL 为 1 小时，采集必须在快照仍有效时完成。长任务错过窗口会被拒绝，不能通过手动补一个未绑定旧 WorkRun 的快照冒充原证据。需要支持长任务时应另做观察快照归档契约，当前不放宽执行或读取权限。

### 2.3 人工评审只记录明确的人工输入

评审必须绑定已采集任务事件的精确哈希，并提供 reviewer、是否真实研究任务、旧流程/试点资料定位耗时、核对/支持/采用引用数、人工纠错数、重大事实错误。数字必须有限且非负（定位耗时 >0），支持/采用数不能超过核对数。

CLI 要求显式 `--attest-human-review`；本批没有代填真实人工评价或运行此命令。此标志记录操作者的声明，不是登录身份签名或生产批准。评审不可无痕覆盖；错误记录需要保留原账本并由运维处理，不通过编辑文件“修好”指标。

### 2.4 7 天观察不能用循环或回填替代

每次 `observe` 使用采集主机的实际时钟；CLI 不提供日期回填参数。查询权威失败或总开关关闭也记录失败事件，错误只保留脱敏 code。以下条件全部满足，才会显示 `collection_criteria_met=true`：

- 至少 10 个独立、权威关联有效的任务，全部有绑定证据的人工评审，且均被人工确认是实际研究任务。
- 首末观察跨度至少 168 小时，至少 7 个不同 UTC 日期，任意相邻观察间隔不超过 36 小时，最新观察不超过 24 小时。
- 没有失败观察；任何失败都保留为待处理问题，后续单次成功不会静默清除。处理完成后可新建一个完整观察窗口，原失败账本保留。
- 任务层面的人工引用支持比例 ≥95%，重大事实错误为 0。

这些是试点采集检查，不能替代独立质量门禁。即使全部满足，报告仍输出 `g_sb4_passed=false`、`rollout_enabled=false`，并列出人工金标/安全、1,000 页性能、生产恢复与保留政策、最终授权验收等独立签核要求。脚本不更改任何生产开关，也不自动创建记忆候选或调度任务。

## 3. 试点执行步骤

### P0：先补齐实际范围和环境

实际 project、owner、space、知识 PG、私有来源目录及 Context Pack 路径已在[配置记录](SECOND-BRAIN-PILOT-CONFIGURATION.md)中落实，基础预检通过；使用现有实际数据库，不复用临时测试库。

完成 SB0–SB4 的真实环境迁移/备份预检，确认实际 project 授权；选择至少 30 份用户授权来源，按现有审核流程逐项核对。人工 gold 与独立验证集按 [评测规范](../backend/evals/knowledge/README.md) 建立，数据保存在私有目录。

P0 的范围与基础配置已完成；[实际空基线恢复及来源准备](SECOND-BRAIN-PILOT-READINESS.md)已完成验证。[30 份授权来源入库及带资料恢复](SECOND-BRAIN-PILOT-INTAKE.md)已完成，候选审核、保留方式和人工质量准备仍待完成，不能据此宣称整个 P0 已通过。下面为后续开放试点的操作手册，尚未执行真实 `init`。

### P1：初始化、逐日采集和逐任务核验

在 `backend` 中，`--env-file` 应为实际试点配置文件：

```bash
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py --env-file /实际私有配置文件 preflight
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py --env-file /实际私有配置文件 init \
  --root /实际私有目录/新试点 --owner 实际owner --project-id 实际project --space-id 实际space
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py --env-file /实际私有配置文件 observe \
  --root /实际私有目录/新试点
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py --env-file /实际私有配置文件 task \
  --root /实际私有目录/新试点 --task-id 实际Mission --work-run-id 实际WorkRun --context-pack-id 实际ContextPack
```

新增配置 `SECOND_BRAIN_PILOT_CONTEXT_DB` 只供采集器指定现有 SQLite 权威文件；不会替换业务数据库。Mission 和 WorkRun 分别读取 `COMMAND_CENTER_DATABASE_URL`、`WORK_RUN_DATABASE_URL`，两者都必须显式为 PostgreSQL。知识源/总开关/空间映射仍沿用原方案。

每天至少一次观察，每项任务完成后及时采集。当前工具不自动安排未来调用，也没有开始后台 7 天监测；本地时钟和机器可用性需要运维保证。需要接入已有调度器时应另行明确运行范围，失败结果应保留，不能只运行成功时的采集。

人工完成检查后，按 [待填写模板](review/second-brain-pilot-20261007/human-review-template.json) 在私有目录填写实际数据。模板中的 null 值和空标识故意不能通过校验。

```bash
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py review \
  --root /实际私有目录/新试点 --file /实际私有目录/人工评审.json --attest-human-review
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py report --root /实际私有目录/新试点
```

`preflight/report` 不满足条件时退出码 1，输入/权威错误为 2；report 的 0 只表示采集条件满足，绝不等于 G-SB4 批准。输出数据应按私有证据保管。

### P2：独立验收与逐项开放

将任务收益/纠错记录、真实人工金标、安全负例、1,000 页性能、生产备份/撤回恢复、保留政策放到同一验收清单逐项确认。不得用本机小规模恢复耗时代替生产 RPO/RTO。

SB3 正式上下文注入和 SB4 原生记忆桥接仍是独立缺口：前者需要实际执行预算与再次授权检查；后者需要 proposal-ID 幂等接口、批准/执行前来源核验及跨库回执对账。本工具不实现或开放这两个功能。

## 4. 试点工具批次验证与清理（配置前历史记录）

- 全知识域 144 项通过（前序 121 + 新增 23），包含真实 PG 知识快照与权限验证；任务权威使用隔离表 fixture，不算真实研究任务。
- 时间窗口单元测试通过可控时钟模拟 8 个日期，仅证明评估算法；没有将其归档为真实 7 天观察。
- 验证重复任务、并发写入、错误证据哈希、未完成任务、错绑计划/步骤、跨用户/项目、撤回引用、同日刷样本、采集断档、过期末次观察、重大错误、文件篡改及符号链接。
- 工具批次真实试点任务数 **0**、真实观察天数 **0**；当时没有真实账本或生产迁移。后续配置批次已初始化实际知识 schema，仍未启动试点或后台观察，详见[配置记录](SECOND-BRAIN-PILOT-CONFIGURATION.md)。
- 预检 [报告](review/second-brain-pilot-20261007/preflight.json) 和 [测试日志](review/second-brain-pilot-20261007/backend-tests.txt) 为本批证据。没有前端改动，不重复宣称本批做了 UI 验收。

清理完成：隔离测试 schema 与临时附件随 fixture 清理；本次临时 PostgreSQL 已正常停止，PID 文件已消失。未启动后台观察或留下试点服务。
