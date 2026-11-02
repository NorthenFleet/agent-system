# 第三阶段 B 验收记录

日期：2026-09-25。目标：Mac mini 原有 agent-system / 3021。

## 结论

默认关闭的审批、租约、执行账本和恢复接入代码已发布，独立审查 GO / CLEAR。
第三阶段整体尚未完成：没有集群执行 HTTP 入口、集群执行 worker 或真实节点 canary。
正式登录、独立受限 SSH 凭据及主机身份仍是启用门槛；不得声称生产远程执行已完成。

## 交付

- 复用 mission_step_approvals，不另建审批表；集群审批绑定封闭请求、executor、目录版本、
  步骤幂等键及验收字段。通用审批 hash 保持兼容。
- 审批决定/过期使用一致的 mission → step 锁顺序，决定/消费/过期均检查条件更新结果。
- 普通 worker 只领取非集群类型的 openclaw 步骤；集群领取需显式步骤 ID 和专用 executor。
- ClusterStepAuthority 强制共享 repository，原子建立 WorkRun、关联步骤并写 running；
  当前计划、未过期 lease 和已消费审批均通过后，原子写步骤证据与完成回执。
- attach/renew/complete 拒绝旧计划或过期 lease；陈旧恢复不能清除新 token/expiry。
- 新审批遇到旧 WorkRun 不重发：已完成且确认成功的回执可复用，其余新步骤 failed/unknown、
  旧 active run blocked；故障回滚二者。通用 transition/heartbeat/artifact 不能绕过 fence。

步骤领取+审批消费与 WorkRun 建立仍是两笔事务；中间崩溃尚未启动 SSH，恢复必须重新审批。
这是控制端至多一次派发，不是远端 exactly-once。后台程序不得伪造管理员 principal。

## 验证

- 最终后端定向回归：232 passed，7 warnings，13.21 秒；包含 12 项独立 PostgreSQL 测试。
- PostgreSQL 覆盖 32 路审批竞争、步骤领取、WorkRun 领取、审批过期竞争、陈旧恢复与续租/
  换 token 竞争、完成与恢复的事务提交/故障回滚。单独 PG 套件另验 12 passed。
- 独立 PG 位于 /private/tmp/cluster-phase3b-pg.LrOFs0，数据库 agent_system_test，
  仅私有 Unix socket，TCP 监听关闭；复用既有 Alembic migration，随机 schema 残留 0。
  实例已停止，pg_ctl status 确认 no server running，未向生产数据库写测试数据。
- 四个服务 py_compile 通过；前端监控面板 11 项测试通过，entry、vue-tsc、Vite 构建通过，
  2988 modules，有既有大 chunk 提示。未修改或重新发布前端产物。
- 补偿扩展回归发现的一处 SQL 条件位置错误已修正，未发布失败版本；最终套件包含其回归。
- 本次是定向验收，不代表全仓测试通过；没有新的浏览器交互验收或真实节点执行验收。

测试目录：/private/tmp/agent-system-cluster-20260925/backend。
解释器：/Users/apple/工作桌面/Workspace/agent-system/backend/venv/bin/python。
最终执行 pytest -q --tb=short --disable-warnings，覆盖 cluster_step_authority、cluster_execution、
cluster_inventory、cluster_readonly_collector、cluster_additive_rollout、monitoring_heartbeat_freshness、
monitoring_api、work_run_at_most_once、work_run_service、command_center_service/repository/router、
step_approval_service、compensation_service、command_center_production_readiness，以及两份 cluster PG 测试。
PG 测试须同时指定独立测试库 WORK_RUN_POSTGRES_TEST_URL 和
WORK_RUN_POSTGRES_TEST_ISOLATED_SCHEMA=true，不得指向生产库。

## 发布证据

- 发布清单 cluster-phase3b-release-files.txt：4 服务、3 测试、1 方案；本地/隔离目录/生产
  SHA256 一致，逐文件 cmp 和 git diff --check 通过。未 commit/push，无数据库迁移。
- 发布前无在途任务；114 个既有步骤均为 openclaw，步骤审批表为空。保留用户无关改动。
- 为加载分流保护，重启既有 3021（PID 76238）与业务 worker（PID 76230）；未新增 worker。
  采集器 PID 36543 不变。初始约 13 秒健康窗口未就绪，随后健康与接口均正常；未回退。
- /health、/monitoring、认证 GET /api/v2/monitoring/cluster 返回 200；匿名 GET 401；
  POST 同路径 404，由既有 catch-all 处理，没有执行入口。
- execution.mode=preparation_only、enabled=false，7 个节点均 ready=false。
  仍有未启用、审批未生产接线、无专用凭据、未启用正式登录四项阻塞。
- 10:28:05 UTC 发现快照 fresh，业务 worker running 且心跳新鲜。
- 生产账本前后 work_runs=58、work_run_events=287、cluster-readonly-v1 runs=0。
  主 SQLite Alembic revision 仍为 41670c742a60。

备份：Mac mini
/Users/apple/工作桌面/Workspace/agent-system/backend/data/cluster-phase3b-Nfy85q/source.tgz。
需要回退时先确认任务空闲，恢复备份内三份服务源码，受控重启上述两个既有进程并重新验收；
无需数据库逆向迁移。新增但未挂接的 authority/测试/文档不会自行启用执行。

## 下一阶段门槛

先补齐对外回执字段裁剪与 HTTP 409 冲突映射，再落实真实认证调用端、正式登录、独立受限
账户/密钥及主机身份。登录和节点访问权限变更须单独明确授权。选择一台已确认在线节点，
人工审批只读 host.info，保存审批、步骤、WorkRun、远端回执后，才考虑自动 worker 与批量调度。

本验收文件在上轮归档被工具额度中断后补写；是否已同步到 Mac mini 必须以实际传输结果为准。
