# 擎天柱—李奥纳多双层 Spec 派发机制

**版本**: 1.0  
**创建日期**: 2026-03-27 10:50  
**作者**: 震荡波 (团队优化师)  
**审核**: 孙总

---

## 🎯 核心原则

> **擎天柱做任务级 Spec，李奥纳多做开发级 Spec**
> 
> 前者负责把任务说清楚，后者负责把工程做清楚

---

## 🏗️ 双层 Spec 架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户 / 飞书入口                        │
│         "把 Q-L-Track 模型接进防空仿真"                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              第一层：擎天柱 (战役级指挥)                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Task Spec (任务级规格书)                        │    │
│  │  • 任务目标                                      │    │
│  │  • 交付物清单                                    │    │
│  │  • 团队归属                                      │    │
│  │  • 约束条件                                      │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          ↓  (task_type = development)
┌─────────────────────────────────────────────────────────┐
│            第二层：李奥纳多 (战术级指挥/技术参谋)         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Dev Spec (开发级规格书)                         │    │
│  │  • 模块范围                                      │    │
│  │  • 类/接口设计                                   │    │
│  │  • 任务拆解 (拉斐尔/多纳泰罗/米开朗基罗)          │    │
│  │  • 技术约束                                      │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              忍者神龟团队 (执行层)                        │
│  ┌─────────────┬─────────────┬─────────────┐           │
│  │   拉斐尔    │  多纳泰罗   │  米开朗基罗  │           │
│  │  后端实现   │  前端/工具  │  测试验证    │           │
│  └─────────────┴─────────────┴─────────────┘           │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 第一层：Task Spec (擎天柱)

### 职责

| 项目 | 说明 |
|------|------|
| 任务识别 | 判断任务类型 (development/simulation/paper/data) |
| 目标定义 | 清晰描述任务要达成什么 |
| 交付物定义 | 列出可验证的交付清单 |
| 团队指派 | 指定主责团队/负责人 |
| 约束说明 | 全局约束条件 |

### YAML 模板

```yaml
# Task Spec - 任务级规格书
spec_id: task_spec_001
version: 1.0
created_at: 2026-03-27T10:50:00+08:00
created_by: optimus

# 任务基本信息
title: 为海上无人集群防空系统增加 Q-L-Track 探测模型
task_type: development  # development | simulation | paper | data | ops
priority: high

# 任务目标 (必须清晰可验证)
objective:
  - 完成 Q-L-Track 探测模型接入
  - 跑通基础仿真测试
  - 输出实验结果文档

# 交付物清单 (必须可验证)
deliverables:
  - type: code_patch
    description: 探测模型集成代码
    location: sim/detection/
  - type: sim_result
    description: 仿真运行结果
    location: results/ql_track_test/
  - type: experiment_note
    description: 实验记录
    location: obsidian/06-项目库/

# 团队归属
owners:
  architect: leonardo      # 架构负责人 (开发任务必填)
  coding_team: ninja_team  # 开发团队
  simulator: ironhide      # 仿真负责人 (如涉及仿真)

# 约束条件
constraints:
  - must_follow_existing_ecs: true
  - must_keep_api_compatible: true
  - do_not_break_existing_tests: true

# 截止时间 (可选)
deadline: 2026-03-27T18:00:00+08:00

# 状态追踪
status: pending  # pending → in_progress → review → completed
```

### 擎天柱校验规则

**Task Spec 必须满足**:
- [ ] 任务目标清晰 (至少 1 条)
- [ ] 交付物可验证 (至少 1 项)
- [ ] 负责人明确 (开发任务必须有 architect)
- [ ] 约束条件完整

**任一不满足 → 返回用户确认，不分发**

---

## 📋 第二层：Dev Spec (李奥纳多)

### 职责

| 项目 | 说明 |
|------|------|
| 模块范围 | 确定改动涉及哪些文件/目录 |
| 技术设计 | 类/接口设计、数据流 |
| 任务拆解 | 分配给拉斐尔/多纳泰罗/米开朗基罗 |
| 技术约束 | 接口兼容性、代码规范等 |

### YAML 模板

```yaml
# Dev Spec - 开发级规格书
dev_spec_id: dev_spec_001
version: 1.0
parent_spec_id: task_spec_001
created_at: 2026-03-27T11:00:00+08:00
created_by: leonardo

# 模块范围 (精确到文件/目录)
module_scope:
  - sim/detection/
  - ecs/systems/detection_system.py
  - tests/test_detection.py

# 技术设计
design:
  new_classes:
    - name: QLTrackDetector
      base_class: IDetectionModel
      methods:
        - detect(frame) -> DetectionResult
        - load_model(path) -> bool
  
  modified_interfaces:
    - IDetectionModel.detect()
      change: extend parameters
  
  data_flow: |
    Camera Input → QLTrackDetector → Detection Result → Task Planner

# 任务拆解 (按忍者神龟成员)
tasks:
  raphael:
    - id: task_r001
      description: 实现 Q-L-Track 模型核心逻辑
      files:
        - sim/detection/ql_track_detector.py
      estimated_hours: 2
  
  donatello:
    - id: task_d001
      description: 更新调试面板 (如需要)
      files:
        - ui/debug_panel.py
      estimated_hours: 1
  
  michelangelo:
    - id: task_m001
      description: 添加单元测试和回归测试
      files:
        - tests/test_ql_track.py
      estimated_hours: 1

# 技术约束
constraints:
  - do_not_change_task_planner_interface
  - keep_baseline_model_available
  - follow_pep8_style
  - test_coverage_minimum: 80%

# 依赖关系
dependencies:
  - task_spec_001  # 依赖父任务 Spec
  - external:
      - Q-L-Track 模型文件就绪

# 状态追踪
status: draft  # draft → approved → in_progress → review → completed
approved_by: optimus  # 需擎天柱批准
```

### 李奥纳多校验规则

**Dev Spec 必须满足**:
- [ ] 模块范围精确 (到文件/目录)
- [ ] 技术设计完整 (类/接口清晰)
- [ ] 任务拆解合理 (每人任务明确)
- [ ] 技术约束完整

**任一不满足 → 返回擎天柱，不分发**

---

## 🔄 完整工作流程

### 开发任务标准链路

```
1. 用户/飞书
   ↓
2. 擎天柱接收任务
   ↓
3. 擎天柱生成 Task Spec
   ↓
4. 擎天柱校验 Task Spec ✅
   ↓
5. 擎天柱派发给李奥纳多 (architect)
   ↓
6. 李奥纳多生成 Dev Spec
   ↓
7. 李奥纳多校验 Dev Spec ✅
   ↓
8. 李奥纳多派发给忍者神龟成员
   ↓
9. 成员执行 (拉斐尔/多纳泰罗/米开朗基罗)
   ↓
10. 成员回报给李奥纳多
    ↓
11. 李奥纳多汇总 → 回报擎天柱
    ↓
12. 擎天柱全局汇总 → 归档 → 回复用户
```

### 硬规则

> **凡 task_type = development**
> 
> **必须先由李奥纳多生成 Dev Spec**
> 
> **未经 Dev Spec，不得直接派发给忍者神龟成员**

---

## 🎯 其他任务类型的 Spec 路径

### 仿真任务 (task_type = simulation)

```
擎天柱 → Task Spec → 铁皮 → Sim Spec → 执行
```

**Sim Spec 由铁皮生成**，包含:
- 仿真场景配置
- 机器人模型
- 训练参数
- 验证标准

### 论文任务 (task_type = paper)

```
擎天柱 → Task Spec → 论文负责人 → Paper Spec → 执行
```

**Paper Spec 包含**:
- 论文结构
- 实验设计
- 数据需求
- 投稿目标

### 运维任务 (task_type = ops)

```
擎天柱 → Task Spec → 大黄蜂 → Ops Spec → 执行
```

**Ops Spec 由大黄蜂生成**，包含:
- 操作步骤
- 风险评估
- 回滚方案
- 验证方法

---

## 📊 职责对比表

| 维度 | 擎天柱 | 李奥纳多 |
|------|--------|----------|
| **层级** | 战役级 | 战术级 |
| **Spec 类型** | Task Spec | Dev Spec |
| **关注点** | What & Who | How |
| **粒度** | 任务级 | 模块/文件级 |
| **决策** | 任务分配 | 技术设计 |
| **汇报** | 向孙总汇报 | 向擎天柱汇报 |
| **不做的** | 不写代码 | 不直接接单 |

---

## 🚨 常见错误与避免

### ❌ 错误 1: 擎天柱直接派给忍者神龟

```
飞书 → 擎天柱 → 拉斐尔 (❌ 跳过李奥纳多)
```

**问题**: 任务描述太粗，工程边界不清

**正确**:
```
飞书 → 擎天柱 → 李奥纳多 → 拉斐尔 (✅)
```

### ❌ 错误 2: 李奥纳多直接接收用户任务

```
飞书 → 李奥纳多 (❌ 跳过擎天柱)
```

**问题**: 缺乏全局视角，可能与其他任务冲突

**正确**:
```
飞书 → 擎天柱 → 李奥纳多 (✅)
```

### ❌ 错误 3: 没有 Spec 直接执行

```
飞书 → 擎天柱 → 执行 (❌ 没有 Spec)
```

**问题**: 目标不清，交付物不明，无法验收

**正确**:
```
飞书 → 擎天柱 → Task Spec → 执行 (✅)
```

---

## 📝 示例：完整开发任务流程

### 用户输入
> 把 Q-L-Track 模型接进当前防空仿真，并形成论文实验部分

### 步骤 1: 擎天柱生成 Task Spec

```yaml
spec_id: task_spec_002
title: Q-L-Track 模型集成与实验
task_type: development
objective:
  - 完成模型集成
  - 跑通仿真
  - 输出实验数据
deliverables:
  - code_patch
  - sim_result
  - experiment_data
owners:
  architect: leonardo
  simulator: ironhide
constraints:
  - keep_api_compatible: true
```

### 步骤 2: 李奥纳多生成 Dev Spec

```yaml
dev_spec_id: dev_spec_002
parent_spec_id: task_spec_002
module_scope:
  - sim/detection/
  - sim/integration/
design:
  new_classes:
    - QLTrackDetector
tasks:
  raphael:
    - implement_ql_track_core
  michelangelo:
    - add_tests
dependencies:
  - ironhide: prepare_sim_environment
```

### 步骤 3: 执行与汇报

```
拉斐尔 → 代码完成 → 李奥纳多
米开朗基罗 → 测试完成 → 李奥纳多
李奥纳多 → 汇总 → 擎天柱
铁皮 → 仿真结果 → 擎天柱
擎天柱 → 全局汇总 → 孙总
```

---

## 📌 版本历史

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| 1.0 | 2026-03-27 | 初始版本 | 震荡波 |

---

## 🔗 相关文档

- [OPTIMUS-SPEC-OFFICER.md](./OPTIMUS-SPEC-OFFICER.md) - 擎天柱职责说明
- [04-忍者神龟团队.md](./04-忍者神龟团队.md) - 忍者神龟团队详情
- [07-协作机制设计.md](./07-协作机制设计.md) - 团队协作流程

---

*本文档由震荡波 (团队优化师) 创建，用于规范双层 Spec 派发机制*

**震荡波** 🟣 逻辑至上
