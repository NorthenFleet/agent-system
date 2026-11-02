# 第三阶段 B：权威步骤审批与受控执行账本接入

## 本次边界

实现默认关闭的程序接入并做隔离数据库/本地子进程验收；不启用生产远程执行、
不新增 HTTP 执行端点、不修改登录策略、不发放 SSH 凭据、不注册自动执行 worker。
真实节点 canary 仍以正式认证、专用受限身份和节点访问验收为前提。

## 复用与实现

1. 复用 `mission_step_approvals` 的合同哈希和 claim 时单次消费，桥接器仅接受当前
   running 任务、当前计划、未过期且匹配的步骤 lease、当前 consumed 审批。
2. 集群专用 task_type/executor 由普通领取默认排除。专用程序必须显式指定步骤领取；
   合同 input 精确绑定封闭 `OperationRequest`，不接受客户端替换主机/命令/参数。
3. 请求主体必须为正式登录的任务所属管理员。使用权威 step idempotency_key，
   不能通过更换客户端 request_id、管理员或审批记录创建第二次派发。
4. 指挥中心和 WorkRun 必须共用同一个 repository/事务；不同存储直接拒绝。
   步骤领取与审批消费是既有的第一笔事务；派发 WorkRun 领取、步骤关联、running 回执
   是第二笔事务。中间崩溃尚未启动 SSH，恢复必须重新审批，不能声称两笔事务全原子。
   完成时在同一事务校验当前 lease/
   合同/审批，写任务证据和 WorkRun 回执，失败全部回滚。事务内不运行 SSH。
5. 未知结果保留 blocked，不自动重试；过期/取消/换租约后的迟到完成拒绝写入。
   独立旧执行对账只标记旧 run，不改新 lease；而新审批/lease 的恢复领取会在同一事务
   收敛当前步骤：旧 completed+confirmed 回执继承成功，否则当前步骤 failed/unknown、
   旧 active run blocked。两条路径都不重新派发，旧终态原始回执不改。

## 验证顺序

- 先补绑定、拒绝、过期租约、重放及事务回滚回归，再实现。
- 相关 SQLite 回归 + 本地假 transport；PostgreSQL 使用临时独立实例/随机 schema，
  复用 canonical migration，不指向生产任务表。
- 独立审查后仅发布默认关闭代码，验收 3021 健康、执行关闭、生产账本未增。
  既有业务 worker 需受控重启以加载通用领取分流保护；不注册集群执行 worker，采集器不重启。
- 本阶段不改 UI；保持准备视图的“审批适配器未连接”生产阻塞项，不能把测试可用
  错写为生产已接通。第三阶段整体未完成，需另行满足真实启用条件后做单节点 canary。

## 调用边界与兼容性

- 当前是面向未来真实认证调用端的服务接缝；principal 必须由真实认证层提供。
  本次没有实现后台 cluster worker，不能让后台程序伪造管理员 principal。
- 普通 worker 仅领取 executor=openclaw 且非集群类型的步骤；未知 executor 不再误派给
  OpenClaw。集群步骤必须显式指定 step_id、匹配专用 executor/type，并有独立审批。
- 既有 generic 审批 hash 保持兼容；仅集群合同额外绑定 executor、操作目录版本与验收字段。
- 普通步骤 attach/renew/complete 增加当前计划和租约期限检查；过期 Worker 不允许复活租约。
- 对账不依赖失联进程的旧 token；从权威账本读取旧 fence，只把失去租约的旧执行记作 unknown。
  新租约/新审批发现旧 WorkRun 时不再次派发；已完成且确认成功的旧回执可在新授权下收敛
  当前步骤为 completed，其余当前步骤为 failed/unknown，旧 active WorkRun 为 blocked。
  此恢复同事务提交/回滚，不留下新步骤一直 running。未知远端事实仍须人工核实。
- 上线真实入口前，还应核验对外回执字段裁剪与冲突 HTTP 409 映射；当前没有集群执行 HTTP
  接线，不能将内部服务接缝当作可供外部调用的完整 API。
