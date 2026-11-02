# 第三阶段 C 生产发布验收

日期：2026-09-27。对应本轮“继续下一阶段”。

## 结论与边界

3C 已部署至 Mac mini 3021，并完成隔离回归、源码校验和生产只读验收。
此前 CLUSTER-EXECUTION-PHASE3C-ACCEPTANCE.md 的“待发布”是 9 月 25 日历史状态；
本文件记录后续发布事实。

这不是整个集群管理目标完成：正式认证调用端、独立受限 SSH 身份及真实单节点 canary
仍未完成。执行 API/专用 worker 未开放，生产 execution.enabled=false。

## 发布内容

只同步下列 6 个文件：

```text
backend/services/work_run_service.py
backend/services/cluster_step_authority.py
backend/routers/projects_v3.py
backend/routers/command_center_router.py
backend/tests/test_cluster_work_run_public_api.py
backend/tests/test_cluster_authority_postgres.py
```

功能包括集群 WorkRun 公开字段裁剪、受执行权威保护的状态切换返回 409、
canonical mission_run/correlation 关联；普通智能体内部账本结构不变。
未新增依赖、数据库迁移、权限点或远程执行接口。未修改前端，未 commit/push。

已归档发布包 SHA256：
`c0c07aace5cea531f0fbb7f379b76c6ed61fdd7566269bc1b5faba95ac87feb1`。

Mac mini 持久归档：
`/Users/apple/工作桌面/Workspace/agent-system/backend/data/cluster-phase3c-pending-LAl7Vq/cluster-phase3c-release.tgz`。

## 新鲜验证

- 隔离联合回归：282 passed，18 warnings，15.42 秒，无 skip。
  组成：上一轮 260 项（含 12 项真实 PostgreSQL 测试）加当前 GenOffice 22 项只读兼容测试。
- 解释器：/Users/apple/工作桌面/Workspace/agent-system/backend/venv/bin/python。
  cwd：/private/tmp/agent-system-cluster-20260925/backend。
  测试文件为前份验收文档列出的 20 份，加 tests/test_genoffice_readonly_service.py；
  命令参数为 pytest -q --tb=short --disable-warnings。
- 运行测试时清除 DATABASE_URL、WORK_RUN_DATABASE_URL、COMMAND_CENTER_DATABASE_URL，
  不引用生产连接；PG 只指向 /private/tmp/cluster-phase3b-pg.LrOFs0/socket 的
  agent_system_test，端口 55432、listen_addresses 为空，并要求独立 schema 标志。
- 所有测试 schema 残留 0，私有测试实例已停止；pg_ctl status 返回 no server running
  （该状态命令的正常退出码为 3）。
- 测试目录、归档包及生产 6 个文件 SHA256 一致；4 份生产源码 py_compile 通过，
  git diff --check 通过。
- 未创建生产测试任务。因此 409 与集群回执裁剪的行为证据来自隔离 API/PG 测试；
  生产证据是已核验源码加载、服务健康和普通记录兼容，不伪称真实集群执行验收。
- 无新的浏览器或前端构建验收，前端未改动；上述结果不是全仓测试结论。

## 在线结果

- 3021 从 PID 2091 受控重载为 PID 93603，启动于 2026-09-27 21:44:39 +0800；
  /health 返回 ok。重载存在短暂中断，不声明零停机。
- 现有业务 worker PID 76230、采集器 PID 36543、GenOffice Sidecar PID 2042 均未重启。
- canonical source_of_truth=postgresql:work_runs，前后总数均为 58：
  completed 41、blocked 3、failed 13、cancelled 1；active 0、cluster-readonly-v1 0。
- 认证 runner/status 与 work-runs 列表正常；不存在的 WorkRun 返回 404；
  匿名 cluster GET 返回 401；cluster POST 仍无执行入口。
- 7 个托管节点全部 ready=false，execution.mode=preparation_only，enabled=false。
- 正式登录仍关闭。本次使用既有开发会话做只读监控验证，令牌未输出或落盘；
  没有伪造正式管理员 principal，没有启用节点操作。

## 并发模块保护与独立问题

写作路由已在 9 月 25 日 20:10:05 的既有启动后加载。后续 GenOffice 源码保持受限只读，
本轮用其现有回归做了兼容验证，但不接管该模块的功能验收。
writing_workspace.py、genoffice_readonly_service.py、3021 plist、genoffice-runtime.env
发布前后 hash 均一致。未覆盖其他 dirty 文件，未执行 launchctl bootstrap/bootout，
未改变 Sidecar、登录设置、受限账户或节点访问策略。

补充在线检查最初把 GenOffice 状态写成“必须 read_only”，断言未通过。
当前实际为 mode=disabled、reachable=false，故该模块不计入功能通过项；
集群烟测只核对它不进入写模式，并显式输出 functional_acceptance=not_claimed。
进一步只读检查发现：磁盘 genoffice-runtime.env 声明启用，但当前已加载 launchd
任务参数不读取该文件，也不包含 GENOFFICE_INTEGRATION_ENABLED。
kickstart 现有任务没有重新安装任务定义，本轮未通过重装任务定义激活该独立功能。
此配置差异应由 GenOffice 发布流程单独处理，不借本次集群发布顺带修复。

## 备份与回退

回退源码包：
`/Users/apple/工作桌面/Workspace/agent-system/backend/data/cluster-phase3c-deploy-TCSLtM/source.tgz`。
SHA256：`e063ae85403ba80d136bc4d20f4579f91bf5918291142d0c34ea8523cd95544e`。
它包含发布前 4 份生产源码和既有 PG 测试；新建 public API 测试不参与运行时。
同目录保存发布清单、候选 hash、保护文件 hash 和本轮在线只读验收脚本。

需要回退时，先重新确认任务空闲与文件未被后续任务修改，再恢复该备份中的文件并受控重载
现有 3021；重新检查 health、认证读接口、PG 账本及 execution.enabled=false。
不需要数据库逆迁移，不删除用户文件，也不替换其他并发模块。

## 下一阶段

按“正式管理员认证 → 受限 SSH 身份和主机身份 → 单节点人工审批 host.info → 回执验收”推进。
切换登录策略、创建或授权节点账户必须单独明确授权；先验证管理员确实可登录并有恢复路径，
再考虑关闭开发会话。保持 Windows 执行不支持、操作白名单单一、默认关闭、无自动重试。
未取得审批、步骤、WorkRun 与远端结果四类一致证据前，不启动自动批量调度。
