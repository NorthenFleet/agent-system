# PRD 驱动流程使用指南

**版本**: 1.0  
**创建日期**: 2026-04-15  
**负责人**: 🐢 李奥纳多

---

## 🚀 快速开始

### 1. 创建 PRD 文档

在以下位置创建 PRD 文档：
```
~/Desktop/Obsidian Vault/09-工具库 -Tools/team-dashboard/PRDs/
```

使用模板：
```bash
cp ~/Desktop/Obsidian\ Vault/09-工具库-Tools/team-dashboard/templates/PRD-TEMPLATE.md \
   ~/Desktop/Obsidian\ Vault/09-工具库-Tools/team-dashboard/PRDs/我的项目.md
```

### 2. 编辑 PRD 内容

使用模板填写：
- 项目概述
- 功能需求
- 技术架构
- 项目计划

### 3. 触发拆解

**方式 A: 自动触发** (推荐)
- 保存 PRD 后，李奥纳多会自动检测并拆解

**方式 B: 手动触发**
```bash
python3 ~/Desktop/Obsidian\ Vault/09-工具库-Tools/team-dashboard/scripts/prd-decomposer.py \
  ~/Desktop/Obsidian\ Vault/09-工具库-Tools/team-dashboard/PRDs/我的项目.md
```

### 4. 查看输出

拆解后生成：
- **Task Spec**: `task-specs/TASK-SPEC-我的项目.md`
- **Dev Spec**: `dev-specs/DEV-SPEC-我的项目.md`

### 5. 任务执行

忍者神龟团队根据 Task Spec 和 Dev Spec 执行开发任务。

---

## 📋 PRD 模板字段说明

### 必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| **项目名称** | 项目标题 | 团队看板二期 |
| **优先级** | P0/P1/P2/P3 | P0 |
| **功能列表** | 功能清单表格 | 见模板 |
| **技术栈** | 技术选型表格 | Vue 3, FastAPI |

### 可选字段

| 字段 | 说明 | 用途 |
|------|------|------|
| 用户故事 | 功能描述格式 | 帮助理解需求 |
| 验收标准 | 功能验收条件 | 测试依据 |
| 性能要求 | 性能指标 | 优化目标 |

---

## 🔧 配置选项

### 李奥纳多配置

位置：`~/Desktop/Obsidian Vault/09-工具库 -Tools/team-dashboard/agents/leonardo.json`

```json
{
  "prd_workflow": {
    "enabled": true,          // 是否启用 PRD 驱动
    "auto_decompose": true,   // 是否自动拆解
    "notify_on_complete": true // 完成后是否通知
  }
}
```

### 目录配置

| 目录 | 用途 | 路径 |
|------|------|------|
| PRDs | PRD 文档存放 | `team-dashboard/PRDs/` |
| task-specs | Task Spec 输出 | `team-dashboard/task-specs/` |
| dev-specs | Dev Spec 输出 | `team-dashboard/dev-specs/` |
| templates | 模板文件 | `team-dashboard/templates/` |

---

## 📊 工作流程详解

### 阶段 1: PRD 提交

```
孙总 → 创建 PRD → 保存到 PRDs 目录
```

### 阶段 2: 擎天柱初审

```
擎天柱检测新 PRD
    ↓
验证格式完整性
    ↓
识别核心功能模块
    ↓
标记优先级
    ↓
转交李奥纳多
```

### 阶段 3: 李奥纳多技术拆解

```
李奥纳多读取 PRD
    ↓
解析功能需求
    ↓
生成 Task Spec (任务规格)
    ↓
生成 Dev Spec (开发规格)
    ↓
分配任务给忍者神龟
```

### 阶段 4: 忍者神龟执行

```
拉斐尔 → 后端开发
多纳泰罗 → 前端开发
米开朗基罗 → 测试
李奥纳多 → 架构审查
```

### 阶段 5: 汇报与审核

```
完成开发 → 提交代码 → 生成报告 → 孙总审核
```

---

## 🎯 最佳实践

### PRD 编写

✅ **推荐**:
- 功能描述具体明确
- 验收标准可衡量
- 优先级清晰标注
- 技术栈提前确定

❌ **避免**:
- 模糊的需求描述
- 无法验证的验收标准
- 优先级全部标 P0
- 技术栈频繁变更

### 任务拆解

✅ **推荐**:
- 任务粒度适中 (2-8 小时)
- 依赖关系明确
- 负责人技能匹配
- 预留缓冲时间

❌ **避免**:
- 任务过大 (>1 天)
- 依赖关系混乱
- 技能不匹配
- 时间估算过于乐观

---

## 🔍 故障排查

### 问题 1: PRD 未自动拆解

**检查**:
1. 李奥纳多配置是否启用 `prd_workflow.enabled`
2. PRD 文件格式是否正确
3. 脚本是否有执行权限

**解决**:
```bash
# 手动触发拆解
python3 ~/Desktop/Obsidian\ Vault/09-工具库-Tools/team-dashboard/scripts/prd-decomposer.py <PRD 文件>
```

### 问题 2: 任务分配错误

**检查**:
- 任务类型识别是否准确
- 忍者神龟技能配置是否正确

**解决**:
- 手动调整任务分配
- 更新 `NINJA_SKILLS` 映射

### 问题 3: 拆解结果不理想

**检查**:
- PRD 内容是否清晰
- 功能描述是否具体

**解决**:
- 优化 PRD 文档
- 手动调整 Task Spec

---

## 📈 效果评估

### 关键指标

| 指标 | 目标值 | 计算方式 |
|------|--------|----------|
| PRD 拆解时间 | < 5 分钟 | 保存到生成完成 |
| 任务分配准确率 | > 90% | 正确分配/总任务数 |
| 开发效率提升 | > 30% | 对比传统方式 |

### 持续优化

- 每周回顾 PRD 质量
- 每月优化拆解算法
- 每季度更新技能映射

---

## 📞 联系方式

如有问题，请联系：
- 🐢 李奥纳多：PRD 分析与拆解
- 🤖 擎天柱：任务统筹

---

*最后更新：2026-04-15*
