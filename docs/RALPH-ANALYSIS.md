# Ralph 源码分析报告

**分析日期**: 2026-04-15  
**分析人**: 🐢 李奥纳多  
**来源**: https://github.com/snarktank/ralph

---

## 🎯 Ralph 核心架构

### 基本理念
> Ralph 是一个自主 AI 代理循环，重复运行直到所有 PRD 项目完成。**每次迭代都是全新的上下文实例**。

### 核心设计模式

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 创建 PRD (tasks/prd-[feature].md)                            │
│     - 使用 /prd skill 生成详细需求文档                            │
│     - 回答澄清问题                                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. 转换为 prd.json                                              │
│     - 使用 /ralph skill 转换 Markdown → JSON                      │
│     - 结构化用户故事，包含 passes 状态                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. 执行循环 (ralph.sh)                                          │
│     - 创建 feature 分支                                          │
│     - 选择最高优先级的未通过故事                                 │
│     - 实现单个故事                                               │
│     - 运行质量检查 (typecheck, tests)                            │
│     - 检查通过则 commit                                          │
│     - 更新 prd.json 标记 passes: true                            │
│     - 追加 learnings 到 progress.txt                             │
│     - 重复直到所有故事通过或达到最大迭代次数                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 核心文件

| 文件 | 用途 | 关键设计 |
|------|------|----------|
| `ralph.sh` | Bash 循环脚本 | 每次迭代启动全新 AI 实例 |
| `prompt.md` | Amp 提示模板 | 项目特定质量检查命令 |
| `CLAUDE.md` | Claude Code 提示 | 支持多 AI 工具 |
| `prd.json` | 任务列表 | 用户故事 + passes 状态 |
| `progress.txt` | 学习日志 | 追加模式，跨迭代持久化 |
| `skills/prd/` | PRD 生成技能 | Amp/Claude Code 通用 |
| `skills/ralph/` | PRD 转换技能 | Markdown → JSON |

---

## 🔑 关键设计亮点

### 1. 上下文隔离 ✅ 强烈推荐借鉴

**问题**: AI 上下文限制导致大任务无法完成

**Ralph 方案**:
- 每次迭代启动全新 AI 实例
- 上下文清空，避免累积
- 只通过文件持久化状态

**OpenClaw 应用**:
```python
# 当前问题：忍者神龟任务可能跨多次对话
# 改进：每次执行都是独立会话，通过 Git 持久化状态

class TaskExecutor:
    def execute(self, task):
        # 每次执行都是全新上下文
        session = create_fresh_session()
        result = session.run(task)
        git_commit(result)  # 持久化
        return result
```

### 2. prd.json 状态管理 ✅ 推荐

**结构**:
```json
{
  "userStories": [
    {
      "id": "story-001",
      "title": "Add database column",
      "passes": false,
      "priority": "P0"
    }
  ]
}
```

**优势**:
- 简单清晰的布尔状态
- 易于查询和过滤
- 支持优先级排序

**OpenClaw 应用**:
```json
{
  "tasks": [
    {
      "id": "T001",
      "name": "效率统计图表",
      "status": "pending|in_progress|completed|failed",
      "priority": "P0",
      "assignee": "多纳泰罗",
      "commit_hash": "abc123"
    }
  ]
}
```

### 3. progress.txt 学习日志 ✅ 强烈推荐

**用途**: 追加模式记录每次迭代的学习

**内容**:
- 发现的代码模式
- 踩过的坑
- 有用的上下文

**OpenClaw 应用**:
```bash
# 每次任务完成后追加到 progress.txt
echo "## $(date) - 任务 T001 完成" >> progress.txt
echo "- 发现：项目使用 Vue 3 Composition API" >> progress.txt
echo "- 注意：修改组件时需要同步更新 types.ts" >> progress.txt
```

### 4. AGENTS.md 自动更新 ✅ 推荐

**用途**: 每次迭代后更新 AGENTS.md 记录学习

**内容**:
- 发现的代码模式
- 注意事项
- 有用的上下文

**为什么有效**:
- AI 工具自动读取 AGENTS.md
- 未来迭代和人类开发者都受益

**OpenClaw 应用**:
```python
def update_agents_md(learnings):
    with open("AGENTS.md", "a") as f:
        f.write(f"\n## {datetime.now()}\n")
        for learning in learnings:
            f.write(f"- {learning}\n")
```

### 5. 反馈循环 🔴 必须实现

**Ralph 的质量检查**:
- Typecheck - 捕获类型错误
- Tests - 验证行为
- CI - 确保代码绿色

**关键洞察**:
> Ralph 只有在有反馈循环时才有效

**OpenClaw 应用**:
```python
def quality_check(task_result):
    checks = [
        ("代码编译", run_compile),
        ("单元测试", run_tests),
        ("代码审查", code_review),
    ]
    
    for name, check_fn in checks:
        if not check_fn():
            return False, f"{name} 失败"
    
    return True, "所有检查通过"
```

### 6. 任务粒度控制 ⚠️ 需要注意

**Ralph 经验**:
> 每个 PRD 项目应该小到能在一个上下文窗口内完成

**合适的粒度**:
- ✅ 添加数据库列和迁移
- ✅ 向现有页面添加 UI 组件
- ✅ 更新 server action 的新逻辑

**过大的粒度** (需要拆分):
- ❌ "构建整个仪表板"
- ❌ "添加认证"
- ❌ "重构 API"

**OpenClaw 应用**:
```python
def validate_task_granularity(task):
    # 估算任务工时
    estimated_hours = estimate(task)
    
    if estimated_hours > 4:  # 超过 4 小时需要拆分
        return split_task(task)
    
    return task
```

### 7. 自动归档 🟡 可选

**Ralph 方案**:
- 开始新 feature 时自动归档之前的运行
- 归档到 `archive/YYYY-MM-DD-feature-name/`

**OpenClaw 应用**:
```python
def archive_previous_run():
    archive_dir = f"archive/{datetime.now().strftime('%Y-%m-%d')}-{feature_name}"
    shutil.copytree("current_run", archive_dir)
```

---

## 📊 Ralph vs OpenClaw 对比

| 特性 | Ralph | OpenClaw 现状 | OpenClaw 改进 |
|------|-------|-------------|--------------|
| **上下文管理** | 每次迭代全新实例 | 会话可能累积上下文 | ✅ 引入会话隔离 |
| **状态持久化** | prd.json + git | JSON 文件 | ✅ 引入 Git 版本管理 |
| **学习记录** | progress.txt | MEMORY.md | ✅ 引入 progress.txt |
| **质量检查** | typecheck + tests | 部分实现 | 🔴 需要加强 |
| **任务粒度** | 小粒度 (单故事) | 中等粒度 | ✅ 引入粒度验证 |
| **协作能力** | 单 AI | 多智能体 | 🟢 保持优势 |
| **知识库** | AGENTS.md | Obsidian + MEMORY.md | 🟢 保持优势 |

---

## 🚀 OpenClaw 改进计划

### 立即实施 (本周)

**1. Git 状态集成** 🔴
```python
# 创建 git-state-manager.py
- 任务状态自动 commit
- 每次迭代生成进度报告
- 支持历史追溯
```

**2. progress.txt 学习日志** ✅
```python
# 创建 progress-logger.py
- 追加模式记录学习
- 任务完成后自动记录
- 包含发现的模式和注意事项
```

**3. 任务粒度验证** 🟡
```python
# 创建 task-granularity-checker.py
- 估算任务工时
- 超过阈值自动拆分
- 生成子任务
```

### 中期实施 (本月)

**4. 质量检查加强** 🔴
```python
# 创建 quality-gate.py
- 代码编译检查
- 单元测试运行
- 代码审查自动化
```

**5. AGENTS.md 自动更新** ✅
```python
# 创建 agents-md-updater.py
- 任务完成后更新 AGENTS.md
- 记录代码模式和注意事项
- 支持查询和检索
```

**6. 会话隔离** 🟡
```python
# 优化 session 管理
- 每次任务执行创建新会话
- 避免上下文累积
- 通过文件持久化状态
```

---

## 📋 实施优先级

| 改进项 | 优先级 | 预计工时 | 依赖 |
|--------|--------|----------|------|
| Git 状态集成 | P0 | 4h | 无 |
| progress.txt | P0 | 2h | 无 |
| 质量检查加强 | P1 | 6h | 无 |
| AGENTS.md 更新 | P1 | 2h | 无 |
| 任务粒度验证 | P2 | 4h | 无 |
| 会话隔离 | P2 | 4h | Git 集成 |

---

## 💡 关键洞察

### Ralph 成功的核心因素

1. **简单性** - Bash 脚本 + JSON + Git，无复杂依赖
2. **反馈循环** - 必须有质量检查，否则失败
3. **小粒度** - 任务必须小到单上下文可完成
4. **持久化** - 状态通过文件而非内存管理
5. **自动化** - 人工干预最小化

### OpenClaw 的差异化优势

1. **多智能体协作** - Ralph 是单 AI，我们是团队
2. **知识库管理** - Obsidian + MEMORY.md 更强大
3. **专业分工** - 忍者神龟各有专长
4. **定时任务** - 心跳系统支持自动化

---

## 🎯 下一步行动

1. **立即**: 实现 Git 状态集成 (优先级 P0)
2. **今天**: 创建 progress.txt 学习日志 (优先级 P0)
3. **本周**: 加强质量检查机制 (优先级 P1)
4. **下周**: 实现任务粒度验证 (优先级 P2)

---

*分析完成时间：2026-04-15 21:20*  
*🐢 李奥纳多 / 汽车人团队*
