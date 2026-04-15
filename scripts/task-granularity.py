#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务粒度验证器 - 自动评估任务大小并建议拆分
灵感来源：Ralph (snarktank/ralph)
负责人：🐢 李奥纳多
"""

import re
import json
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================
TEAM_DASHBOARD = Path(__file__).parent.parent

# 任务粒度阈值 (小时)
GRANULARITY_THRESHOLDS = {
    "太小": (0, 1),      # < 1 小时，建议合并
    "合适": (1, 8),      # 1-8 小时，理想粒度
    "偏大": (8, 16),     # 8-16 小时，可以接受但建议拆分
    "太大": (16, float('inf'))  # > 16 小时，必须拆分
}

# 任务类型基准工时 (小时)
BASE_ESTIMATES = {
    "API 开发": 4,
    "数据库变更": 2,
    "前端页面": 6,
    "UI 组件": 3,
    "单元测试": 2,
    "集成测试": 4,
    "文档编写": 2,
    "代码审查": 2,
    "Bug 修复": 3,
    "性能优化": 6,
    "配置修改": 1,
    "重构": 8,
}

# 复杂度系数
COMPLEXITY_MULTIPLIERS = {
    "简单": 0.8,      # 常规实现
    "中等": 1.0,      # 需要思考
    "复杂": 1.5,      # 技术难点
    "未知": 1.2,      # 不确定因素
}


def estimate_task_hours(task_description, task_type="未知", complexity="中等"):
    """估算任务工时"""
    
    # 1. 基于任务类型的基准工时
    base_hours = BASE_ESTIMATES.get(task_type, 4)  # 默认 4 小时
    
    # 2. 复杂度调整
    multiplier = COMPLEXITY_MULTIPLIERS.get(complexity, 1.0)
    
    # 3. 关键词分析
    keywords_analysis = analyze_keywords(task_description)
    keyword_adjustment = keywords_analysis.get('adjustment', 0)
    
    # 4. 计算总工时
    estimated_hours = (base_hours + keyword_adjustment) * multiplier
    
    return round(estimated_hours, 1)


def analyze_keywords(description):
    """分析描述中的关键词，调整工时估算"""
    desc_lower = description.lower()
    
    adjustment = 0
    flags = []
    
    # 增加工时的关键词
    if any(kw in desc_lower for kw in ['集成', '整合', '对接', 'api', '第三方']):
        adjustment += 2
        flags.append("涉及外部集成")
    
    if any(kw in desc_lower for kw in ['迁移', '转换', '兼容']):
        adjustment += 3
        flags.append("涉及数据迁移")
    
    if any(kw in desc_lower for kw in ['优化', '性能', '并发', '缓存']):
        adjustment += 2
        flags.append("涉及性能优化")
    
    if any(kw in desc_lower for kw in ['安全', '认证', '权限', '加密']):
        adjustment += 2
        flags.append("涉及安全功能")
    
    # 减少工时的关键词
    if any(kw in desc_lower for kw in ['简单', '直接', '基础', '模板']):
        adjustment -= 1
        flags.append("实现较简单")
    
    if any(kw in desc_lower for kw in ['修复', '修正', '调整']):
        adjustment -= 1
        flags.append("小幅度修改")
    
    return {
        "adjustment": adjustment,
        "flags": flags
    }


def evaluate_granularity(estimated_hours):
    """评估任务粒度"""
    for level, (min_h, max_h) in GRANULARITY_THRESHOLDS.items():
        if min_h <= estimated_hours < max_h:
            return level
    return "未知"


def suggest_split(task_info):
    """建议任务拆分方案"""
    task_name = task_info.get('name', '未知任务')
    description = task_info.get('description', '')
    task_type = task_info.get('type', '未知')
    
    estimated_hours = estimate_task_hours(description, task_type)
    granularity = evaluate_granularity(estimated_hours)
    
    suggestions = {
        "太小": "考虑与其他小任务合并",
        "合适": "✅ 粒度合适，无需调整",
        "偏大": "建议拆分为 2-3 个子任务",
        "太大": "⚠️ 必须拆分！建议拆分为 4+ 个子任务"
    }
    
    split_plan = None
    if granularity in ["偏大", "太大"]:
        split_plan = generate_split_plan(task_info, estimated_hours)
    
    return {
        "task_name": task_name,
        "estimated_hours": estimated_hours,
        "granularity": granularity,
        "suggestion": suggestions.get(granularity, "需要人工评估"),
        "split_plan": split_plan
    }


def generate_split_plan(task_info, total_hours):
    """生成拆分计划"""
    task_name = task_info.get('name', '未知任务')
    description = task_info.get('description', '')
    task_type = task_info.get('type', '未知')
    
    # 根据任务类型生成拆分建议
    split_suggestions = {
        "API 开发": [
            "定义 API 接口和数据结构",
            "实现核心业务逻辑",
            "编写单元测试",
            "API 文档和集成测试"
        ],
        "前端页面": [
            "页面布局和基础样式",
            "数据绑定和交互逻辑",
            "表单验证和错误处理",
            "响应式适配和优化"
        ],
        "数据库变更": [
            "设计数据模型和迁移方案",
            "编写迁移脚本",
            "更新相关 API 和查询",
            "数据验证和回滚测试"
        ],
        "单元测试": [
            "编写核心功能测试",
            "编写边界条件测试",
            "编写集成测试",
            "测试覆盖率检查和补充"
        ],
        "默认": [
            "需求分析和设计",
            "核心功能实现",
            "测试和优化",
            "文档和部署"
        ]
    }
    
    subtasks = split_suggestions.get(task_type, split_suggestions["默认"])
    
    # 估算每个子任务的工时
    subtask_hours = total_hours / len(subtasks)
    
    split_plan = {
        "original_task": task_name,
        "original_hours": total_hours,
        "subtasks": []
    }
    
    for idx, subtask_desc in enumerate(subtasks, 1):
        split_plan["subtasks"].append({
            "id": f"T{idx:03d}",
            "name": f"{task_name} - 子任务{idx}",
            "description": subtask_desc,
            "estimated_hours": round(subtask_hours, 1),
            "granularity": evaluate_granularity(subtask_hours)
        })
    
    return split_plan


def validate_prd_tasks(prd_path):
    """验证 PRD 中的所有任务"""
    from pathlib import Path
    
    if not Path(prd_path).exists():
        return {"error": f"PRD 文件不存在：{prd_path}"}
    
    with open(prd_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取功能列表
    features = re.findall(
        r'\|\s*(F\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(P\d+)\s*\|',
        content
    )
    
    results = []
    for feature in features:
        task_info = {
            "id": feature[0],
            "name": feature[1].strip(),
            "description": feature[2].strip(),
            "priority": feature[3].strip(),
            "type": guess_task_type(feature[2])
        }
        
        suggestion = suggest_split(task_info)
        results.append({
            "task": task_info,
            "suggestion": suggestion
        })
    
    return {
        "prd_file": prd_path,
        "total_tasks": len(results),
        "tasks": results,
        "summary": generate_summary(results)
    }


def guess_task_type(description):
    """猜测任务类型"""
    desc_lower = description.lower()
    
    if any(kw in desc_lower for kw in ['api', '接口', '后端', '服务器']):
        return "API 开发"
    elif any(kw in desc_lower for kw in ['页面', '前端', 'ui', '界面']):
        return "前端页面"
    elif any(kw in desc_lower for kw in ['数据库', '表', '迁移', 'model']):
        return "数据库变更"
    elif any(kw in desc_lower for kw in ['测试', 'unit', 'integration']):
        return "单元测试"
    else:
        return "默认"


def generate_summary(results):
    """生成汇总报告"""
    total = len(results)
    too_large = sum(1 for r in results if r['suggestion']['granularity'] == '太大')
    too_small = sum(1 for r in results if r['suggestion']['granularity'] == '太小')
    appropriate = sum(1 for r in results if r['suggestion']['granularity'] == '合适')
    
    return {
        "total": total,
        "too_large": too_large,
        "too_small": too_small,
        "appropriate": appropriate,
        "needs_split": too_large + too_small,
        "split_ratio": round((too_large + too_small) / total * 100, 1) if total > 0 else 0
    }


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("📏 任务粒度验证器")
        print("用法：python task-granularity.py <命令> [参数]")
        print("\n可用命令:")
        print("  estimate <描述>     - 估算单个任务工时")
        print("  validate <PRD 文件>  - 验证 PRD 中所有任务")
        print("  split <任务描述>    - 生成拆分建议")
        print("\n示例:")
        print("  python task-granularity.py estimate '实现用户登录 API'")
        print("  python task-granularity.py validate PRDs/项目.md")
        print("  python task-granularity.py split '构建完整的用户管理系统'")
        return
    
    command = sys.argv[1]
    
    if command == "estimate":
        if len(sys.argv) < 3:
            print("❌ 请提供任务描述")
            return
        description = " ".join(sys.argv[2:])
        hours = estimate_task_hours(description)
        granularity = evaluate_granularity(hours)
        print(f"📊 估算结果:")
        print(f"   工时：{hours} 小时")
        print(f"   粒度：{granularity}")
        print(f"   建议：{suggest_split({'name': '任务', 'description': description, 'type': '未知'})['suggestion']}")
    
    elif command == "validate":
        if len(sys.argv) < 3:
            print("❌ 请提供 PRD 文件路径")
            return
        prd_path = sys.argv[2]
        result = validate_prd_tasks(prd_path)
        
        if "error" in result:
            print(f"❌ {result['error']}")
            return
        
        print(f"\n📊 PRD 任务粒度验证报告")
        print(f"{'='*60}")
        print(f"PRD 文件：{result['prd_file']}")
        print(f"任务总数：{result['summary']['total']}")
        print(f"✅ 粒度合适：{result['summary']['appropriate']}")
        print(f"⚠️  需要拆分：{result['summary']['needs_split']} ({result['summary']['split_ratio']}%)")
        print(f"   - 太大：{result['summary']['too_large']}")
        print(f"   - 太小：{result['summary']['too_small']}")
        print(f"{'='*60}\n")
        
        # 打印需要拆分的任务
        needs_attention = [r for r in result['tasks'] if r['suggestion']['granularity'] in ['太大', '偏大']]
        if needs_attention:
            print("⚠️  需要关注的任务:")
            for item in needs_attention:
                print(f"  - {item['task']['name']}: {item['suggestion']['estimated_hours']}h ({item['suggestion']['granularity']})")
                print(f"    建议：{item['suggestion']['suggestion']}")
    
    elif command == "split":
        if len(sys.argv) < 3:
            print("❌ 请提供任务描述")
            return
        description = " ".join(sys.argv[2:])
        task_info = {"name": "任务", "description": description, "type": "未知"}
        result = suggest_split(task_info)
        
        print(f"\n📋 任务拆分建议")
        print(f"{'='*60}")
        print(f"任务：{result['task_name']}")
        print(f"估算工时：{result['estimated_hours']}小时")
        print(f"粒度评估：{result['granularity']}")
        print(f"建议：{result['suggestion']}")
        
        if result['split_plan']:
            print(f"\n拆分方案:")
            for subtask in result['split_plan']['subtasks']:
                print(f"  {subtask['id']}: {subtask['name']} ({subtask['estimated_hours']}h)")
                print(f"      {subtask['description']}")
        
        print(f"{'='*60}\n")
    
    else:
        print(f"❌ 未知命令：{command}")


if __name__ == "__main__":
    main()
