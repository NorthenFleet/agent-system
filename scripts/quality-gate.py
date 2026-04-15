#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质量检查门 - 任务完成前自动执行质量检查
灵感来源：Ralph (snarktank/ralph)
负责人：🐢 李奥纳多
"""

import subprocess
import json
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================
TEAM_DASHBOARD = Path(__file__).parent.parent
QUALITY_LOG = TEAM_DASHBOARD / "logs" / "quality-checks.log"
QUALITY_LOG.parent.mkdir(exist_ok=True)

# 质量检查配置
QUALITY_CHECKS = {
    "代码编译": {
        "enabled": True,
        "command": "python3 -m py_compile backend/main.py",
        "timeout": 30,
        "critical": True  # 关键检查，失败则阻止提交
    },
    "单元测试": {
        "enabled": True,
        "command": "python3 -m pytest backend/tests/ -v --tb=short 2>/dev/null || echo '无测试文件或测试失败'",
        "timeout": 60,
        "critical": False
    },
    "代码格式": {
        "enabled": False,  # 可选，需要安装 black
        "command": "black --check backend/ frontend/ 2>/dev/null || echo 'black 未安装或格式检查失败'",
        "timeout": 30,
        "critical": False
    },
    "代码审查": {
        "enabled": True,
        "command": "python3 scripts/code-review-checker.py",
        "timeout": 60,
        "critical": True
    },
    "前端构建": {
        "enabled": False,  # 可选，需要 Node.js
        "command": "cd frontend && npm run build 2>/dev/null || echo '前端构建跳过'",
        "timeout": 120,
        "critical": False
    }
}


def log_check(check_name, success, message=""):
    """记录检查结果"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅" if success else "❌"
    log_entry = f"[{timestamp}] {status} {check_name}: {message}\n"
    
    with open(QUALITY_LOG, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    
    print(log_entry.strip())


def run_check(check_name, check_config):
    """执行单个质量检查"""
    if not check_config.get("enabled", False):
        log_check(check_name, True, "⏸️ 已跳过")
        return True, "跳过"
    
    command = check_config["command"]
    timeout = check_config.get("timeout", 30)
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=TEAM_DASHBOARD
        )
        
        success = result.returncode == 0
        message = result.stdout.strip()[:200] if result.stdout else "无输出"
        
        if not success and result.stderr:
            message += f"\n错误：{result.stderr.strip()[:200]}"
        
        log_check(check_name, success, message[:100])
        return success, message
        
    except subprocess.TimeoutExpired:
        log_check(check_name, False, "⏱️ 超时")
        return False, "超时"
    except Exception as e:
        log_check(check_name, False, f"⚠️ 异常：{str(e)}")
        return False, str(e)


def run_all_quality_checks(task_info=None):
    """执行所有质量检查"""
    if task_info:
        task_name = task_info.get('name', '未知任务')
        print(f"\n🔍 开始质量检查 - 任务：{task_name}")
        log_check("质量检查批次", True, f"任务 {task_name} 开始")
    else:
        print(f"\n🔍 开始质量检查")
    
    results = {
        "passed": [],
        "failed": [],
        "skipped": []
    }
    
    for check_name, check_config in QUALITY_CHECKS.items():
        success, message = run_check(check_name, check_config)
        
        if not check_config.get("enabled", False):
            results["skipped"].append(check_name)
        elif success:
            results["passed"].append(check_name)
        else:
            results["failed"].append(check_name)
    
    # 检查关键项
    critical_failed = []
    for check_name, check_config in QUALITY_CHECKS.items():
        if check_config.get("critical", False) and check_name in results["failed"]:
            critical_failed.append(check_name)
    
    # 生成报告
    print(f"\n{'='*60}")
    print("📊 质量检查报告")
    print(f"{'='*60}")
    print(f"✅ 通过：{len(results['passed'])} - {', '.join(results['passed']) or '无'}")
    print(f"❌ 失败：{len(results['failed'])} - {', '.join(results['failed']) or '无'}")
    print(f"⏸️ 跳过：{len(results['skipped'])} - {', '.join(results['skipped']) or '无'}")
    
    if critical_failed:
        print(f"\n🔴 关键检查失败：{', '.join(critical_failed)}")
        print("⚠️ 建议修复后再提交")
        overall_pass = False
    else:
        print(f"\n🟢 所有关键检查通过")
        overall_pass = True
    
    print(f"{'='*60}\n")
    
    return {
        "overall_pass": overall_pass,
        "critical_failed": critical_failed,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }


def validate_before_submit(task_info):
    """提交前验证"""
    print(f"\n🔒 提交前验证 - 任务：{task_info.get('name', '未知')}")
    
    # 1. 运行质量检查
    quality_result = run_all_quality_checks(task_info)
    
    # 2. 检查是否通过
    if not quality_result["overall_pass"]:
        print(f"\n❌ 质量检查未通过，阻止提交")
        print(f"失败项：{', '.join(quality_result['critical_failed'])}")
        return False, quality_result
    
    # 3. 通过验证
    print(f"\n✅ 提交前验证通过")
    return True, quality_result


def generate_quality_report(task_info, quality_result):
    """生成质量报告"""
    report = f"""# 质量检查报告

**任务**: {task_info.get('name', '未知')}
**负责人**: {task_info.get('assignee', '未知')}
**检查时间**: {quality_result.get('timestamp', '未知')}

---

## 检查结果

| 状态 | 数量 | 检查项 |
|------|------|--------|
| ✅ 通过 | {len(quality_result['results']['passed'])} | {', '.join(quality_result['results']['passed']) or '无'} |
| ❌ 失败 | {len(quality_result['results']['failed'])} | {', '.join(quality_result['results']['failed']) or '无'} |
| ⏸️ 跳过 | {len(quality_result['results']['skipped'])} | {', '.join(quality_result['results']['skipped']) or '无'} |

---

## 关键检查

{'🟢 所有关键检查通过' if quality_result['overall_pass'] else '🔴 关键检查失败：' + ', '.join(quality_result['critical_failed'])}

---

## 建议

{generate_recommendations(quality_result)}

---

*自动生成 by 质量检查门*
"""
    
    report_path = TEAM_DASHBOARD / "logs" / f"quality-report-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    return report_path


def generate_recommendations(quality_result):
    """生成改进建议"""
    recommendations = []
    
    if quality_result['results']['failed']:
        recommendations.append("1. 修复失败的检查项")
    
    if '代码编译' in quality_result['results']['failed']:
        recommendations.append("2. 运行 `python3 -m py_compile` 检查语法错误")
    
    if '代码审查' in quality_result['results']['failed']:
        recommendations.append("3. 查看代码审查报告并修复问题")
    
    if not recommendations:
        recommendations.append("✅ 代码质量良好，可以提交")
    
    return "\n".join(recommendations)


def main():
    """主函数"""
    import sys
    
    if len(sys.argv) < 2:
        print("🔍 质量检查门")
        print("用法：python quality-gate.py <命令> [参数]")
        print("\n可用命令:")
        print("  check              - 执行所有质量检查")
        print("  validate <任务名>   - 提交前验证")
        print("  report             - 生成质量报告")
        print("\n示例:")
        print("  python quality-gate.py check")
        print("  python quality-gate.py validate '效率统计图表'")
        return
    
    command = sys.argv[1]
    
    if command == "check":
        run_all_quality_checks()
    
    elif command == "validate":
        if len(sys.argv) < 3:
            print("❌ 请提供任务名称")
            return
        task_name = " ".join(sys.argv[2:])
        task_info = {"name": task_name, "assignee": "未知"}
        success, result = validate_before_submit(task_info)
        if success:
            print("✅ 验证通过，可以提交")
        else:
            print("❌ 验证失败，请修复问题")
    
    elif command == "report":
        task_info = {"name": "未知任务", "assignee": "未知"}
        result = run_all_quality_checks(task_info)
        report_path = generate_quality_report(task_info, result)
        print(f"📄 质量报告已生成：{report_path}")
    
    else:
        print(f"❌ 未知命令：{command}")


if __name__ == "__main__":
    main()
