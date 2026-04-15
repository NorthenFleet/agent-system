#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRD 拆解脚本 - 李奥纳多专用
功能：读取 PRD 文档，自动拆解为 Task Spec 和 Dev Spec
负责人：🐢 李奥纳多 (Leonardo)
"""

import re
import json
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================
TEAM_DASHBOARD = Path(__file__).parent.parent
PRD_DIR = TEAM_DASHBOARD / "PRDs"
TASK_SPEC_DIR = TEAM_DASHBOARD / "task-specs"
DEV_SPEC_DIR = TEAM_DASHBOARD / "dev-specs"

# 确保目录存在
PRD_DIR.mkdir(exist_ok=True)
TASK_SPEC_DIR.mkdir(exist_ok=True)
DEV_SPEC_DIR.mkdir(exist_ok=True)

# 忍者神龟团队技能映射
NINJA_SKILLS = {
    "后端": "拉斐尔",
    "前端": "多纳泰罗",
    "测试": "米开朗基罗",
    "架构": "李奥纳多",
    "数据库": "拉斐尔",
    "API": "拉斐尔",
    "UI": "多纳泰罗",
    "可视化": "多纳泰罗",
}


def parse_prd(prd_path):
    """解析 PRD 文档"""
    with open(prd_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取基本信息
    prd_info = {
        "title": extract_title(content),
        "version": extract_field(content, r"\*\*版本\*\*: (.+)"),
        "priority": extract_field(content, r"\*\*优先级\*\*: (.+)"),
        "features": extract_features(content),
        "tech_stack": extract_tech_stack(content),
    }
    
    return prd_info


def extract_title(content):
    """提取 PRD 标题"""
    match = re.search(r"# PRD: (.+)", content)
    return match.group(1).strip() if match else "未命名项目"


def extract_field(content, pattern):
    """提取字段"""
    match = re.search(pattern, content)
    return match.group(1).strip() if match else "未知"


def extract_features(content):
    """提取功能列表"""
    features = []
    
    # 匹配功能表格
    table_match = re.search(
        r"\| 编号 \| 功能名称 \| 描述 \| 优先级 \|.*?\| (F\d+) \| ([^|]+) \| ([^|]+) \| (P\d+) \|",
        content,
        re.DOTALL
    )
    
    if table_match:
        # 提取所有功能行
        feature_rows = re.findall(
            r"\| (F\d+) \| ([^|]+) \| ([^|]+) \| (P\d+) \|",
            content
        )
        
        for row in feature_rows:
            features.append({
                "id": row[0],
                "name": row[1].strip(),
                "description": row[2].strip(),
                "priority": row[3].strip()
            })
    
    return features


def extract_tech_stack(content):
    """提取技术栈"""
    tech_stack = []
    
    # 匹配技术栈表格
    tech_rows = re.findall(
        r"\| (前端 | 后端 | 部署 | 数据库) \| ([^|]+) \|",
        content
    )
    
    for row in tech_rows:
        tech_stack.append({
            "layer": row[0],
            "tech": row[1].strip()
        })
    
    return tech_stack


def generate_task_spec(prd_info, output_path):
    """生成 Task Spec 文档"""
    task_spec = f"""# Task Spec: {prd_info['title']}

**PRD 来源**: {prd_info.get('title', '未知')}  
**创建日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  
**负责人**: 🤖 擎天柱 / 🐢 李奥纳多  
**优先级**: {prd_info.get('priority', 'P1')}

---

## 📋 任务列表

| 编号 | 任务名称 | 类型 | 优先级 | 预计工时 | 负责人 |
|------|----------|------|--------|----------|--------|
"""
    
    # 根据功能生成任务
    for idx, feature in enumerate(prd_info.get('features', []), 1):
        task_type = guess_task_type(feature['description'])
        assignee = NINJA_SKILLS.get(task_type, "待定")
        
        task_spec += f"| T{idx:03d} | {feature['name']} | {task_type} | {feature['priority']} | 4h | {assignee} |\n"
    
    task_spec += f"""
---

## 📝 任务详情

"""
    
    for idx, feature in enumerate(prd_info.get('features', []), 1):
        task_type = guess_task_type(feature['description'])
        assignee = NINJA_SKILLS.get(task_type, "待定")
        
        task_spec += f"""### T{idx:03d}: {feature['name']}

- **描述**: {feature['description']}
- **类型**: {task_type}
- **优先级**: {feature['priority']}
- **预计工时**: 4h
- **负责人**: {assignee}
- **验收标准**:
  - [ ] 功能实现完成
  - [ ] 通过单元测试
  - [ ] 代码审查通过

---

"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(task_spec)
    
    return output_path


def guess_task_type(description):
    """根据描述猜测任务类型"""
    desc_lower = description.lower()
    
    if any(kw in desc_lower for kw in ['api', '后端', '服务器', '数据库']):
        return "后端"
    elif any(kw in desc_lower for kw in ['界面', '前端', 'ui', '页面']):
        return "前端"
    elif any(kw in desc_lower for kw in ['测试', 'quality', 'qa']):
        return "测试"
    elif any(kw in desc_lower for kw in ['架构', '设计', 'review']):
        return "架构"
    else:
        return "后端"  # 默认后端


def generate_dev_spec(prd_info, task_spec_path, output_path):
    """生成 Dev Spec 文档"""
    dev_spec = f"""# Dev Spec: {prd_info['title']}

**Task Spec 来源**: {task_spec_path.name}  
**创建日期**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  
**技术负责人**: 🐢 李奥纳多

---

## 🏗️ 技术方案

### 1. 架构设计

基于 PRD 要求，采用以下架构：

- **前端**: Vue 3 + Element Plus
- **后端**: FastAPI + SQLite
- **部署**: Docker 容器化

### 2. 目录结构

```
project/
├── backend/
│   ├── api/          # API 接口
│   ├── models/       # 数据模型
│   └── main.py       # 入口文件
├── frontend/
│   ├── src/
│   │   ├── views/    # 页面组件
│   │   └── components/ # 通用组件
│   └── package.json
└── docker/
    └── Dockerfile
```

---

## 🔌 接口设计

### API 规范

```python
# 示例 API
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/v1/resource")
async def get_resource():
    return {{"data": []}}
```

---

## 📊 数据模型

```sql
-- 示例表结构
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 📝 实现步骤

### Phase 1: 基础架构 (第 1 周)
1. [ ] 搭建项目骨架
2. [ ] 配置开发环境
3. [ ] 实现基础 API

### Phase 2: 核心功能 (第 2-3 周)
1. [ ] 实现 P0 功能
2. [ ] 实现 P1 功能
3. [ ] 前端页面开发

### Phase 3: 测试优化 (第 4 周)
1. [ ] 单元测试
2. [ ] 集成测试
3. [ ] 性能优化

---

## ✅ 验收标准

### 代码质量
- [ ] 通过代码审查
- [ ] 无严重 Bug
- [ ] 代码覆盖率 > 80%

### 功能验收
- [ ] 所有 P0 功能完成
- [ ] 所有 P1 功能完成
- [ ] 通过验收测试

---

**技术审批**:
- [ ] 李奥纳多审批 (架构设计)
- [ ] 孙总审批 (最终确认)

---

*自动生成 by 李奥纳多 PRD 拆解脚本*
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(dev_spec)
    
    return output_path


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("🐢 李奥纳多 PRD 拆解工具")
        print("用法：python prd-decomposer.py <PRD 文件路径>")
        print("\n示例:")
        print("  python prd-decomposer.py ~/Desktop/Obsidian\\ Vault/09-工具库 -Tools/team-dashboard/PRDs/project.md")
        return
    
    prd_path = Path(sys.argv[1])
    
    if not prd_path.exists():
        print(f"❌ PRD 文件不存在：{prd_path}")
        return
    
    print(f"🐢 李奥纳多开始拆解 PRD: {prd_path.name}")
    
    # 解析 PRD
    prd_info = parse_prd(prd_path)
    print(f"📋 项目名称：{prd_info['title']}")
    print(f"📊 功能数量：{len(prd_info.get('features', []))}")
    
    # 生成 Task Spec
    task_spec_name = f"TASK-SPEC-{prd_info['title'].replace(' ', '-').upper()}.md"
    task_spec_path = TASK_SPEC_DIR / task_spec_name
    generate_task_spec(prd_info, task_spec_path)
    print(f"✅ Task Spec 已生成：{task_spec_path}")
    
    # 生成 Dev Spec
    dev_spec_name = f"DEV-SPEC-{prd_info['title'].replace(' ', '-').upper()}.md"
    dev_spec_path = DEV_SPEC_DIR / dev_spec_name
    generate_dev_spec(prd_info, task_spec_path, dev_spec_path)
    print(f"✅ Dev Spec 已生成：{dev_spec_path}")
    
    print(f"\n🎉 PRD 拆解完成!")
    print(f"📁 Task Spec: {task_spec_path}")
    print(f"📁 Dev Spec: {dev_spec_path}")

if __name__ == "__main__":
    main()
