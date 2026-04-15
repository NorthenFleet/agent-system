#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 状态管理器 - 自动 commit 任务状态和进度
灵感来源：Ralph (snarktank/ralph)
负责人：🐢 李奥纳多
"""

import subprocess
import json
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================
TEAM_DASHBOARD = Path(__file__).parent.parent
GIT_DIR = TEAM_DASHBOARD
PROGRESS_FILE = TEAM_DASHBOARD / "progress.txt"
AGENTS_MD = TEAM_DASHBOARD / "AGENTS.md"

# 需要自动 commit 的目录
WATCHED_DIRS = [
    "PRDs",
    "task-specs",
    "dev-specs",
    "docs",
    "agents",
]


def run_git_command(args, cwd=None):
    """运行 Git 命令"""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or GIT_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def get_git_status():
    """获取 Git 状态"""
    success, stdout, stderr = run_git_command(["status", "--porcelain"])
    if not success:
        return []
    
    changes = []
    for line in stdout.strip().split('\n'):
        if line:
            status = line[:3].strip()
            file_path = line[3:].strip()
            changes.append({"status": status, "file": file_path})
    
    return changes


def stage_changes(files=None):
    """暂存更改"""
    if files:
        for f in files:
            run_git_command(["add", str(f)])
    else:
        # 暂存所有 watched dirs
        for dir_name in WATCHED_DIRS:
            dir_path = GIT_DIR / dir_name
            if dir_path.exists():
                run_git_command(["add", str(dir_path)])


def commit_changes(message, author=None):
    """提交更改"""
    if author:
        run_git_command(["commit", "-m", message, "--author", author])
    else:
        run_git_command(["commit", "-m", message])


def create_branch(branch_name, from_branch="main"):
    """创建新分支"""
    run_git_command(["checkout", from_branch])
    run_git_command(["checkout", "-b", branch_name])


def get_current_branch():
    """获取当前分支"""
    success, stdout, stderr = run_git_command(["branch", "--show-current"])
    return stdout.strip() if success else "unknown"


def tag_commit(tag_name, message=""):
    """给 commit 打标签"""
    run_git_command(["tag", "-a", tag_name, "-m", message])


def log_progress(entry):
    """追加进度到 progress.txt"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {entry}\n"
    
    with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    
    print(f"📝 进度已记录：{entry}")


def update_agents_md(learnings):
    """更新 AGENTS.md 添加学习"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    content = f"\n## 📚 学习记录 - {timestamp}\n\n"
    
    for learning in learnings:
        content += f"- {learning}\n"
    
    content += "\n---\n"
    
    if AGENTS_MD.exists():
        with open(AGENTS_MD, 'a', encoding='utf-8') as f:
            f.write(content)
    else:
        with open(AGENTS_MD, 'w', encoding='utf-8') as f:
            f.write(f"# AGENTS.md - 团队学习笔记\n\n{content}")
    
    print(f"📖 AGENTS.md 已更新")


def auto_commit_task_completion(task_info):
    """任务完成时自动 commit"""
    task_name = task_info.get('name', '未知任务')
    assignee = task_info.get('assignee', '未知')
    status = task_info.get('status', 'completed')
    
    # 1. 记录进度
    log_progress(f"任务完成：{task_name} (负责人：{assignee}, 状态：{status})")
    
    # 2. 暂存更改
    stage_changes()
    
    # 3. 检查是否有更改
    changes = get_git_status()
    if not changes:
        print("⏸️ 无更改需要提交")
        return
    
    # 4. 提交
    commit_message = f"✅ 任务完成：{task_name}\n\n负责人：{assignee}\n状态：{status}"
    commit_changes(commit_message)
    
    # 5. 打标签
    tag_name = f"task-{task_name.replace(' ', '-').lower()}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    tag_commit(tag_name, f"任务 {task_name} 完成")
    
    # 6. 更新 AGENTS.md
    learnings = task_info.get('learnings', [])
    if learnings:
        update_agents_md(learnings)
    
    print(f"✅ Git 提交完成：{commit_message[:50]}...")


def auto_commit_phase_completion(phase_info):
    """阶段完成时自动 commit"""
    phase_name = phase_info.get('name', '未知阶段')
    completed_tasks = phase_info.get('completed_tasks', [])
    
    # 1. 记录进度
    log_progress(f"阶段完成：{phase_name} (完成任务数：{len(completed_tasks)})")
    
    # 2. 暂存更改
    stage_changes()
    
    # 3. 提交
    task_list = "\n".join([f"- {t}" for t in completed_tasks])
    commit_message = f"🎉 阶段完成：{phase_name}\n\n完成任务:\n{task_list}"
    commit_changes(commit_message)
    
    # 4. 打标签
    tag_name = f"phase-{phase_name.replace(' ', '-').lower()}-{datetime.now().strftime('%Y%m%d')}"
    tag_commit(tag_name, f"阶段 {phase_name} 完成")
    
    print(f"✅ 阶段提交完成")


def create_archive(feature_name):
    """归档当前运行"""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    archive_name = f"{timestamp}-{feature_name}"
    archive_dir = GIT_DIR / "archive" / archive_name
    
    # 创建归档目录
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制当前状态文件
    files_to_archive = ["prd.json", "progress.txt", "AGENTS.md"]
    for file_name in files_to_archive:
        src = GIT_DIR / file_name
        if src.exists():
            import shutil
            shutil.copy2(src, archive_dir / file_name)
    
    print(f"📦 已归档到：{archive_dir}")


def main():
    """主函数 - 演示用法"""
    import sys
    
    if len(sys.argv) < 2:
        print("🔧 Git 状态管理器")
        print("用法：python git-state-manager.py <命令> [参数]")
        print("\n可用命令:")
        print("  status              - 查看 Git 状态")
        print("  commit <消息>       - 提交更改")
        print("  log <进度消息>      - 记录进度")
        print("  learn <学习内容>    - 更新 AGENTS.md")
        print("  archive <特性名>    - 归档当前运行")
        print("\n示例:")
        print("  python git-state-manager.py status")
        print("  python git-state-manager.py commit '完成 PRD 拆解'")
        print("  python git-state-manager.py log '任务 T001 完成'")
        return
    
    command = sys.argv[1]
    
    if command == "status":
        changes = get_git_status()
        if changes:
            print("📊 当前更改:")
            for change in changes:
                print(f"  {change['status']} {change['file']}")
        else:
            print("✅ 工作区干净")
    
    elif command == "commit":
        if len(sys.argv) < 3:
            print("❌ 请提供提交消息")
            return
        message = " ".join(sys.argv[2:])
        stage_changes()
        commit_changes(message)
        print(f"✅ 提交成功：{message}")
    
    elif command == "log":
        if len(sys.argv) < 3:
            print("❌ 请提供进度消息")
            return
        entry = " ".join(sys.argv[2:])
        log_progress(entry)
    
    elif command == "learn":
        if len(sys.argv) < 3:
            print("❌ 请提供学习内容")
            return
        learning = " ".join(sys.argv[2:])
        update_agents_md([learning])
    
    elif command == "archive":
        if len(sys.argv) < 3:
            print("❌ 请提供特性名称")
            return
        feature_name = sys.argv[2]
        create_archive(feature_name)
    
    else:
        print(f"❌ 未知命令：{command}")


if __name__ == "__main__":
    main()
