# 双层 Spec 派发机制 (Commander-Architect Protocol)

**版本**: 1.0  
**创建日期**: 2026-03-27  
**状态**: ✅ 已就绪

---

## 🎯 核心原则

> **擎天柱做任务级 Spec，李奥纳多做开发级 Spec**
> 
> 前者负责把任务说清楚，后者负责把工程做清楚

---

## 🏗️ 整体架构

```
Intent (自然语言任务)
        ↓
【擎天柱】生成 Task Spec
        ↓
【李奥纳多】生成 Dev Spec / Paper Spec / Sim Spec
        ↓
子 Agent 执行 (忍者神龟 / 仿真 / 写作)
        ↓
结果回流
        ↓
Spec 更新 + 归档
```

---

## 📁 目录结构

```
specs/
├── README.md              # 本文档
├── templates/             # Spec 模板
│   ├── task_spec.yaml     # 任务级 Spec (擎天柱)
│   ├── dev_spec.yaml      # 开发级 Spec (李奥纳多)
│   └── sim_spec.yaml      # 仿真级 Spec (铁皮)
├── active/                # 进行中的 Spec
│   └── task_*.yaml
└── archive/               # 已完成的 Spec (按日期归档)
```

---

## 📋 Spec 类型

| 类型 | 负责人 | 模板 | 用途 |
|------|--------|------|------|
| Task Spec | 擎天柱 | task_spec.yaml | 任务级规格书 |
| Dev Spec | 李奥纳多 | dev_spec.yaml | 开发级规格书 |
| Sim Spec | 铁皮 | sim_spec.yaml | 仿真级规格书 |
| Paper Spec | 论文负责人 | (待创建) | 论文级规格书 |
| Ops Spec | 大黄蜂 | (待创建) | 运维级规格书 |

---

## 🔧 使用示例

### 1. 创建 Task Spec

```python
from spec_dispatcher import SpecDispatcher

dispatcher = SpecDispatcher()
intent = "为海上无人集群防空系统增加 Q-L-Track 探测模型"
result = dispatcher.handle_intent(intent)
```

### 2. 李奥纳多处理开发任务

```python
task_spec = load_spec("task_20260327_105500")
dev_spec = leonardo_handle(task_spec)
```

### 3. 忍者神龟执行

```python
# 拉斐尔接收 Dev Spec 中的任务
raphael_tasks = dev_spec["tasks"]["raphael"]
for task in raphael_tasks:
    implement(task)
```

---

## 🚨 强约束规则

### 规则 1: 无 Spec 不执行
```python
if not spec_id:
    raise Exception("禁止执行")
```

### 规则 2: 开发任务必须二次 Spec
```python
if task_type == "development" and not dev_spec:
    raise Exception("必须先生成 Dev Spec")
```

### 规则 3: Agent 不得越级
```
忍者神龟成员：
❌ 不允许直接接收 Task Spec
✅ 只能接收 Dev Spec
```

---

## 📊 状态流转

```
drafted → approved → in_progress → review → completed
   ↓          ↓           ↓           ↓          ↓
 创建       批准        执行        审查        完成
```

---

## 🔗 相关文档

- [../docs/OPTIMUS-SPEC-OFFICER.md](../docs/OPTIMUS-SPEC-OFFICER.md) - 擎天柱职责
- [../docs/OPTIMUS-LEONARDO-SPEC-MECHANISM.md](../docs/OPTIMUS-LEONARDO-SPEC-MECHANISM.md) - 双层 Spec 机制
- [../rules/commander_rules.md](../rules/commander_rules.md) - 擎天柱规则
- [../rules/leonardo_rules.md](../rules/leonardo_rules.md) - 李奥纳多规则

---

*Spec 在控制 Agent，而不是 Agent 在决定系统*
