# 第三阶段 C：执行回执的对外接口边界

本次只完善默认关闭代码的 HTTP 投影和错误契约，不开放执行 API，不修改登录或节点权限。
生产现有 writing/genoffice 并发改动不属于本任务，不同步或覆盖。

1. 先用回归锁定 WorkRun detail/list/runner summary/mission run-ledger 的公开字段。
2. 只在对外边界裁剪 cluster WorkRun；内部序列化、审批、恢复仍保留完整 fence。
   集群输入只公开封闭请求；回执公开审批/步骤/结果证据，不公开 lease/binding 控制摘要、
   凭据、文件路径或任意扩展 metadata。普通 WorkRun 保持兼容。
3. 通用 transition 对被保护的集群执行返回明确的 409，不向外泄露内部异常文本，且账本不变。
4. 核对集群 WorkRun 与 canonical mission_run/correlation 关联，确保任务账本能发现回执。
5. 定向 API、服务、恢复及相关原有回归；不写生产验收任务。发布只涉及清单内文件，
   如共享服务有尚未加载的并发改动，不擅自重启以激活它们。
6. 本阶段完成后仍需正式认证接线、受限账户与主机身份、人工批准的单节点 canary，
   不得据此声称第三阶段真实远程执行已完成。
