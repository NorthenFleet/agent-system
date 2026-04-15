#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码审查检查器 - 自动检查常见代码问题
负责人：🐢 李奥纳多
"""

import re
from pathlib import Path

TEAM_DASHBOARD = Path(__file__).parent.parent

# 代码审查规则
REVIEW_RULES = [
    {
        "name": "TODO 注释检查",
        "pattern": r"#\s*TODO|#\s*FIXME|#\s*XXX",
        "severity": "warning",
        "message": "发现 TODO/FIXME 注释，建议完成或移除"
    },
    {
        "name": "硬编码检查",
        "pattern": r"['\"](http|https)://[^'\"]+['\"]",
        "severity": "info",
        "message": "发现硬编码 URL，建议使用配置文件"
    },
    {
        "name": "密码硬编码检查",
        "pattern": r"(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
        "severity": "error",
        "message": "⚠️ 发现硬编码密码，必须移除！"
    },
    {
        "name": "空 except 检查",
        "pattern": r"except\s*:",
        "severity": "warning",
        "message": "发现空 except，建议指定具体异常类型"
    },
    {
        "name": "print 调试检查",
        "pattern": r"print\s*\([^)]*\)",
        "severity": "info",
        "message": "发现 print 语句，确认是否为调试代码"
    }
]


def scan_file(file_path):
    """扫描单个文件"""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return [{"rule": "文件读取", "severity": "error", "message": str(e), "line": 0}]
    
    for rule in REVIEW_RULES:
        for line_num, line in enumerate(lines, 1):
            if re.search(rule["pattern"], line, re.IGNORECASE):
                issues.append({
                    "rule": rule["name"],
                    "severity": rule["severity"],
                    "message": rule["message"],
                    "line": line_num,
                    "content": line.strip()[:80]
                })
    
    return issues


def scan_directory(dir_path, extensions=None):
    """扫描目录下所有文件"""
    if extensions is None:
        extensions = ['.py', '.js', '.ts', '.vue', '.md']
    
    all_issues = []
    
    for ext in extensions:
        for file_path in dir_path.glob(f"**/*{ext}"):
            # 跳过虚拟环境和 node_modules
            if 'venv' in str(file_path) or 'node_modules' in str(file_path):
                continue
            
            issues = scan_file(file_path)
            for issue in issues:
                issue["file"] = str(file_path.relative_to(dir_path))
            all_issues.extend(issues)
    
    return all_issues


def generate_report(issues):
    """生成审查报告"""
    if not issues:
        return "✅ 代码审查通过 - 未发现问题"
    
    # 按严重程度分类
    errors = [i for i in issues if i['severity'] == 'error']
    warnings = [i for i in issues if i['severity'] == 'warning']
    infos = [i for i in issues if i['severity'] == 'info']
    
    report = f"# 代码审查报告\n\n"
    report += f"**扫描文件数**: 去重后 {len(set(i.get('file', '') for i in issues))} 个\n"
    report += f"**发现问题**: {len(issues)} 个\n\n"
    
    if errors:
        report += f"## 🔴 错误 ({len(errors)})\n\n"
        for issue in errors[:10]:  # 只显示前 10 个
            report += f"- **{issue['file']}:{issue['line']}** - {issue['rule']}\n"
            report += f"  `{issue['content']}`\n"
            report += f"  {issue['message']}\n\n"
    
    if warnings:
        report += f"## ⚠️ 警告 ({len(warnings)})\n\n"
        for issue in warnings[:10]:
            report += f"- **{issue['file']}:{issue['line']}** - {issue['rule']}\n"
            report += f"  `{issue['content']}`\n"
            report += f"  {issue['message']}\n\n"
    
    if infos:
        report += f"## ℹ️ 提示 ({len(infos)})\n\n"
        report += f"发现 {len(infos)} 个提示信息，不影响提交\n\n"
    
    # 总结
    report += f"## 总结\n\n"
    if errors:
        report += f"❌ 发现 {len(errors)} 个错误，必须修复后才能提交\n"
    elif warnings:
        report += f"⚠️ 发现 {len(warnings)} 个警告，建议修复\n"
    else:
        report += f"✅ 代码质量良好，可以提交\n"
    
    return report


def main():
    """主函数"""
    import sys
    
    print("🔍 开始代码审查...")
    
    # 扫描 team-dashboard 目录
    issues = scan_directory(TEAM_DASHBOARD)
    
    # 生成报告
    report = generate_report(issues)
    print(report)
    
    # 保存报告
    report_path = TEAM_DASHBOARD / "logs" / f"code-review-{Path(__file__).name}.md"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📄 完整报告已保存：{report_path}")
    
    # 返回状态码
    errors = [i for i in issues if i['severity'] == 'error']
    if errors:
        print(f"\n❌ 代码审查失败：{len(errors)} 个错误")
        sys.exit(1)
    else:
        print(f"\n✅ 代码审查通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
