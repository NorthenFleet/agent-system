# 第三阶段 C 验收与待发布交接

日期：2026-09-25。目标：Mac mini agent-system / 3021。

## 状态

代码实现、隔离回归及独立审查完成；生产发布尚未执行。
共享服务有启动后新增的 writing/genoffice 修改，不能未经协调通过重启顺带激活。
第三阶段真实远程执行仍未完成，本次没有开放执行 API、增加 worker、修改登录策略或节点权限。

## 交付

- 在既有 WorkRun 服务内复用纯 `public_work_run` 投影，不增加新服务、表或依赖。
  只对集群执行使用公开字段白名单；普通智能体返回深拷贝并保持既有字段。
- HTTP list/detail/transition、runner live/cached summary、tick、instance release/complete，
  以及 Command Center run-ledger.step_runs 均通过公开投影。
- 隐藏 fence、lease、binding hash、工作目录、凭据扩展、任意 metadata 和文件产物；
  保留请求、审批 ID、合同 hash、步骤幂等标识和执行回执。当前 host.info 不接受远端参数，
  parameters_summary 固定为空。后续新增操作须显式扩展此公开合同。
- 内部 get/list/serializer/transition 完整性不变，审批、完成、恢复仍读取完整 fence。
- 外部绕过执行权威的状态切换返回固定文本 HTTP 409，不修改 WorkRun、任务或审批账本。
- ClusterStepAuthority 在既有事务中复用 canonical mission_run_id/correlation_id，
  修复集群执行未被任务总账查询到的问题；不新增账本或历史回填。

## 新鲜验证证据

- 最终联合后端回归：260 passed，18 warnings，14.44 秒，无 skip。
  包含 14 项公开 API/DTO 测试及 12 项真实隔离 PostgreSQL 测试。
- 409 覆盖 running/review/completed/blocked/failed/cancelled 六种外部切换，
  直接比较数据库快照，证明拒绝前后持久化内容完全不变。
- 回执完整性测试使用本地受控测试子进程，不是真实节点 SSH。
- 32 路 PostgreSQL 并发及重放保持单 WorkRun，全部结果关联相同 canonical mission_run 和
  correlation；完成后的持久化记录与任务总账一致。原审批竞争、恢复与故障回滚测试保留。
- 独立审查 GO / CLEAR；四份生产源码、两份测试 py_compile 通过。
  未修改前端，本阶段没有浏览器验收，也未声称全仓测试或真实远程执行通过。
- PostgreSQL 测试实例 /private/tmp/cluster-phase3b-pg.LrOFs0，仅私有 Unix socket，
  TCP 55432 无监听；测试 schema 残留 0，已停止，pg_ctl status 为 no server running。
- 增强测试中曾错误地用会刷新投影时间戳的 get_mission 比较“无写入”，产生 6 项断言失败；
  改为只读原始数据库快照后，最终 260 项通过。没有因此改动生产业务语义。

解释器：/Users/apple/工作桌面/Workspace/agent-system/backend/venv/bin/python。
测试 cwd：/private/tmp/agent-system-cluster-20260925/backend。
最终命令：PYTHONPATH=. <上述解释器> -m pytest -q --tb=short --disable-warnings，文件为：

```text
tests/test_cluster_work_run_public_api.py
tests/test_cluster_step_authority.py
tests/test_cluster_execution.py
tests/test_cluster_inventory.py
tests/test_cluster_readonly_collector.py
tests/test_cluster_additive_rollout.py
tests/test_monitoring_heartbeat_freshness.py
tests/test_monitoring_api.py
tests/test_work_run_at_most_once.py
tests/test_work_run_service.py
tests/test_command_center_service.py
tests/test_command_center_repository.py
tests/test_command_center_router.py
tests/test_step_approval_service.py
tests/test_compensation_service.py
tests/test_command_center_production_readiness.py
tests/test_projects_v3.py
tests/test_cluster_work_run_postgres.py
tests/test_cluster_authority_postgres.py
tests/test_runner_result_contract.py
```

PG 仅使用 WORK_RUN_POSTGRES_TEST_URL 指向 agent_system_test 的私有 socket，
并显式 WORK_RUN_POSTGRES_TEST_ISOLATED_SCHEMA=true；不得替换成生产连接。

## 生产检查与发布门

- 3021 PID 76238 启动于 2026-09-25 18:27:23 +0800。
  writing_workspace.py 修改于 18:45:45，genoffice_readonly_service.py 修改于 19:05:44。
  这些并发改动均不属于本阶段，未覆盖、未通过服务重启激活。
- /health 正常；当前正式登录仍关闭，监控 execution.mode=preparation_only、enabled=false，
  7 个托管节点全部 ready=false。发现列表合计 14 条，不能把发现节点全算作已托管节点。
- 线上 runner summary 明确 source_of_truth=postgresql:work_runs；总数 58、无 active run，
  列表中 cluster-readonly-v1 为 0。此前的生产 58 条口径对应此 PostgreSQL 权威账本。
  本地历史 SQLite 文件只读检查为 24 条、100 events、0 cluster，不能用它代替线上账本。
- 第三阶段 B 验收文档已同步到生产 docs，并核对 SHA256 一致。
- 本次不改生产源码、不迁移数据库、不重启服务、不 commit/push；发布包仅供协调后受控部署。

待发布清单：cluster-phase3c-release-files.txt（4 源码、2 测试、2 文档）。
生产基线 hash：cluster-phase3c-production-baseline.sha256；部署前须重新校验，任何漂移先评审。

后续发布顺序：

1. 确认并发 writing/genoffice 的发布状态和共享服务重启窗口；不由本任务默认批准其上线。
2. 校验基线 hash、任务空闲和发布包完整性；备份清单中的现有源码及已存在的测试/文档。
3. 只部署清单内文件；受控重启需要加载新模块的现有服务，不新增集群 worker。
4. 验证 health、认证读接口、仍默认关闭、无生产测试任务；失败恢复备份，不做数据库逆迁移。
5. 再单独落实正式登录、真实管理员授权链、受限 SSH 身份和主机身份确认；先单节点人工批准
   host.info canary，具备审批、步骤、WorkRun、远端结果四类证据后再考虑自动调度。

本阶段交付不等于整个集群管理目标完成，也不等于当前生产已具有 3C 行为。

## 后续状态（2026-09-27）

3C 后续已完成生产部署；本文件保留 9 月 25 日历史证据。
新的测试、上线及边界记录见 [生产发布验收](CLUSTER-EXECUTION-PHASE3C-DEPLOYMENT.md)。
