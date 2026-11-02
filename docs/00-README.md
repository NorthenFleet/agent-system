# 🤖 智能体团队状态看板 - 完整文档

**版本**: 1.0  
**创建**: 2026-03-18  
**运行位置**: Mac mini (192.168.31.41:3020)  
**代码位置**: `/Users/apple/WorkSpace/team-dashboard/`

---

## 📁 文档目录

### 当前总体设计与分方案

以下为当前设计导航；本页后半部分的地址和设备信息保留为 2026-03-18 历史记录，不代表当前部署状态。

- [系统产品设计](../DESIGN.md)
- [决策路由与旁路顾问分方案 DR-01](DECISION-ROUTING-ARCHITECTURE.md)及 [DR1 影子路由](DECISION-ROUTING-PHASE-1.md)、[DR2 确定性执行与受控修复](DECISION-ROUTING-PHASE-2.md)、[DR3 顾问与隔离代码候选](DECISION-ROUTING-PHASE-3.md)、[DR4 工具调用控制与回执](DECISION-ROUTING-PHASE-4.md)
- [系统闭环补强总体方案](SYSTEM-CLOSURE-MASTER-PLAN.md)
- [记忆与 Agent Team 协同总纲](SYSTEM-COORDINATED-OPTIMIZATION-PLAN.md)
- [第二大脑知识子系统分方案 SB-01](SECOND-BRAIN-KNOWLEDGE-SUBSYSTEM-DESIGN.md)（v1.0，实施中）及 [SB0/SB1 实施记录](SECOND-BRAIN-PHASE-SB0-SB1.md)、[SB2 知识维护与投影恢复](SECOND-BRAIN-PHASE-SB2.md)、[SB3 引用检索与上下文对照](SECOND-BRAIN-PHASE-SB3.md)、[SB4 成果回流与运维恢复](SECOND-BRAIN-PHASE-SB4.md)、[受控试点准备与验收](SECOND-BRAIN-PILOT-PLAN.md)及[实际环境配置记录](SECOND-BRAIN-PILOT-CONFIGURATION.md)及[备份基线与来源准备](SECOND-BRAIN-PILOT-READINESS.md)及[30 份授权文档入库](SECOND-BRAIN-PILOT-INTAKE.md)（候选待审核，真实观察未开始）
- [GenOffice 文档引擎集成分方案](GENOFFICE-3021-INTEGRATION-DESIGN.md)

### 历史基础文档

1. [集群架构设计](01-集群架构设计.md)
2. [智能体团队划分](02-智能体划分.md)
3. [汽车人团队](03-汽车人团队.md)
4. [忍者神龟团队](04-忍者神龟团队.md)
5. [设备配置清单](05-设备配置.md)
6. [API 接口文档](06-API 接口文档.md)

---

## 🌐 访问地址

**后端 API**: http://192.168.31.41:3020

| 接口 | 地址 |
|------|------|
| API 根路径 | http://192.168.31.41:3020/ |
| 智能体列表 | http://192.168.31.41:3020/api/agents |
| 任务列表 | http://192.168.31.41:3020/api/tasks |
| 团队状态 | http://192.168.31.41:3020/api/team/status |

---

*创建：2026-03-18*

### 7. [协作机制设计](07-协作机制设计.md) ← 新增
- OpenClaw 现有机制
- 消息队列方案
- WebSocket 实时推送
- 心跳检查机制
