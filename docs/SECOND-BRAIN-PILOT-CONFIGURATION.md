# 第二大脑试点：实际环境配置记录

**日期**：2026-10-07  
**关联**：[SB-01 分方案](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)、[受控试点执行方案](SECOND-BRAIN-PILOT-PLAN.md)  
**状态**：项目、owner、知识 PostgreSQL、私有来源目录及 Context Pack 路径已配置；基础预检全部通过。服务尚未重启，试点尚未启动。

## 1. 已确定的范围

| 项目 | 配置结果 |
|---|---|
| 试点项目 | 智能体系统工作流验证与优化，`workflow-pilot-20261002` |
| owner | 当前启用的管理员账号 `admin`，用户 ID `1` |
| 知识空间 | 第二大脑 · 工作流研发试点，`ks-089499632d9fb01a8414035daed61f8f` |
| 知识权威 | 本机现有 PostgreSQL 数据库 `team_dashboard`，独立 schema `second_brain` |
| 私有来源目录 | `/Users/apple/工作桌面/Workspace/agent-system/backend/data/second-brain/sources` |
| Context Pack 数据库 | `/Users/apple/工作桌面/Workspace/agent-system/backend/data/unified_dashboard.db` |

项目来自现有项目登记，owner 来自现有启用用户；项目负责 Agent 不作为用户 owner。使用已提出的推荐项目作为本次配置范围。旧项目缺少完整用户 ACL，兼容授权已限定为配置的 owner 和这一项目，空间权限仍由服务端校验。

## 2. 配置与初始化

配置写入 3021 启动定义使用的仓库根 `.env`，文件权限为 `0600`；修改前的私有备份保存在 `backend/data/second-brain/config-before-*.env`。环境文件、来源目录和备份均被 Git 忽略；文档不保存连接凭证。

- `SECOND_BRAIN_DATABASE_URL`：复用现有本机 PostgreSQL 连接，指定 `search_path=second_brain`。运行时和预检优先使用此变量，未设置才回退至 `DATABASE_URL`；拒绝非 PostgreSQL 权威。
- `SECOND_BRAIN_SOURCE_ROOT`、`SECOND_BRAIN_PILOT_CONTEXT_DB`：分别指向上表绝对路径。来源目录及其 `second-brain` 父目录权限均为 `0700`；Context Pack 采集以只读模式打开现有数据库。
- `SECOND_BRAIN_PILOT_OWNER_ID=1`、`SECOND_BRAIN_PILOT_PROJECT_ID=workflow-pilot-20261002`、`SECOND_BRAIN_PILOT_SPACE_ID=ks-089499632d9fb01a8414035daed61f8f`。
- `SECOND_BRAIN_CONTEXT_SPACES`：仅把上述项目映射到上述空间；记录空间 ID 本身不授予访问权限。

保留原全局 `DATABASE_URL` 状态，避免把现有认证、写作等 SQLite 业务重定向到 PostgreSQL。知识域采用独立连接；WorkRun 继续使用原连接。

已运行 [知识 schema 初始化脚本](../backend/scripts/apply_knowledge_schema.py)，仅在 `second_brain` 中应用 SB0–SB4 的四份冻结迁移，并建立独立 `kb_schema_migrations` 哈希账本。脚本拒绝 public schema、外来表及迁移/表结构漂移，重复执行不会重建已登记表；不运行全局历史迁移链，不改变旧 `alembic_version`。随后创建上述空知识空间，来源、页面、发布数均为 0。

本次实际写入了环境配置、知识 schema 和空间元数据。预检报告中的 `production_modified=false` 只表示该次只读预检没有写入，不能理解为整个配置过程没有修改实际环境。

## 3. 验证证据

- [基础预检](review/second-brain-configuration-20261007/preflight.json)：PostgreSQL 配置、PDF 解析器、私有目录、知识 schema、WorkRun schema 五项全部通过，`ready=true`。
- [配置核验](review/second-brain-configuration-20261007/configuration.json)：核实空间 owner/project、四份迁移、目录权限、空知识域及可读取的 121 条既有 Context Pack。既有 Context Pack 数不计为新试点任务。
- [回归日志](review/second-brain-configuration-20261007/backend-tests.txt)：知识域 **148 项通过**，含连接优先级、旧数据库隔离、项目授权边界、真实 PostgreSQL 初始化/重放/漂移拒绝；另有两条既有 SQLAlchemy 弃用提示。
- 临时回归 PostgreSQL（55439 端口）已停止，PID 文件消失。实际知识数据库保持运行。

只读复核命令（从 `backend` 执行）：

```sh
PYTHONPATH=. venv/bin/python scripts/knowledge_pilot.py --env-file ../.env preflight
```

预检验证指定配置，不证明运行中服务已经加载它；本次未重启 3021 服务。

## 4. 下一阶段边界

总开关、写入、worker、投影、维护均保持 `false`，上下文模式为 `disabled`。没有执行试点 `init`，真实任务数和观察天数仍为 0，没有后台观察调度。

本记录完成 P0 的范围与基础配置部分。后续已完成[空基线恢复与来源准备](SECOND-BRAIN-PILOT-READINESS.md)，后续[30 份文档入库与带资料恢复](SECOND-BRAIN-PILOT-INTAKE.md)已完成，候选待审核、保留方式待确定。授权来源、人工金标、备份/撤回恢复及保留政策仍按试点方案补齐；后续开放受控 shadow 试点时再加载配置、检查开关并初始化真实观察账本。正式上下文注入、原生 Memory 桥接、生产质量门禁均未因此通过。
