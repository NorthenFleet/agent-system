# 记忆闭环与 Agent Team 协同优化：阶段 0 验收记录

> 完成日期：2026-09-20  
> 阶段结论：通过 Gate C0，可以进入联合阶段 1  
> 运行影响：无；未改变检索排序、Mission/WorkRun 主链或 Agent Team 功能开关

## 1. 阶段目标

在继续记忆阶段 B 和 Agent Team 阶段 1 前，冻结跨域事实边界、引用链、Context Pack 授权方式、Artifact 归属及联合门禁，防止两个正确的子系统形成双重事实源或跨实例上下文泄漏。

## 2. 已完成

1. 新增 `SYSTEM-COORDINATED-OPTIMIZATION-PLAN.md`，定义系统中心和联合路线；
2. 明确 Command Center、Agent Team、WorkRun、Memory、LangGraph、Agent Space 的权威分区；
3. 冻结 `mission -> team -> task -> claim -> work_run -> context_pack -> memory/evidence/effect` 引用链；
4. 明确 Team、Role、AgentInstance、SharedTask、AgentMessage 不增加长期记忆作用域；
5. Context Pack 改为按 TaskClaim/WorkRun 冻结的不可变执行快照；
6. 明确换人时不得继承旧实例私有线程或失效 Claim 的授权；
7. 明确 AgentMessage 只能生成候选记忆，不能直接发布长期记忆；
8. 明确 Team Artifact 复用 Command Center `mission_artifacts`，不复制正文事实；
9. 建立 Gate M1、T1、X1、Q1；全部通过前禁止真实共享任务认领；
10. 修订记忆与 Agent Team 两份主方案，使其引用同一协同契约。

## 3. 当前实现审计

Agent Team 当前可见实现只有 SQLite/PostgreSQL 表结构草案，尚未满足阶段 1 完成条件。进入 Gate T1 前至少需要处理：

- SharedTaskDependency 关系权威；
- 每任务单一有效 Claim 的数据库约束；
- 单调 fencing token 与迟到写拒绝；
- 跨 Team 引用一致性；
- AgentMessage 接收目标二选一；
- `active_claims` 派生计数对账；
- Context Pack 使用记录与 TaskClaim/WorkRun 绑定；
- 领域服务、API、重启恢复与非法引用测试。

记忆路线已经完成阶段 A，但 Gate M1 尚未通过：阶段 B 的权威记忆、生命周期账本、pgvector 和 Graph Memory 全量对账仍待执行。

## 4. 验收结果

| 检查项 | 结果 |
| --- | --- |
| 权威事实分区唯一 | 通过 |
| 跨域引用链完整 | 通过 |
| 长期记忆作用域未扩张 | 通过 |
| Context Pack 授权边界明确 | 通过 |
| Artifact 无第二正文事实源 | 通过 |
| LangGraph 未升级为事实库 | 通过 |
| 真实执行主链未切换 | 通过 |
| 记忆排序未切换 | 通过 |
| 联合门禁和下一阶段入口明确 | 通过 |

## 5. 下一阶段

联合阶段 1 包含两个独立工作包：

1. Memory Gate M1：完成权威记忆与双投影对账及退役隔离演练；
2. Agent Team Gate T1：加固 schema，完成领域服务、API 和专项测试。

两个工作包可以并行实施，但只有 Gate M1、T1、X1、Q1 全部通过后，才允许进入真实共享任务认领。
