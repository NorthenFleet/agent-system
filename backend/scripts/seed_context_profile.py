#!/usr/bin/env python3
"""Seed the initial operator profile without creating duplicate versions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.context_retrieval_service import context_retrieval_service


PROFILE = {
    "display_name": "孙总",
    "preferred_name": "孙总",
    "timezone_name": "Asia/Shanghai",
    "summary": "负责智能体协作系统、One-Sim 仿真与规划、软件系统和博士论文/技术文档的统筹。",
    "work_context": {
        "roles": ["项目负责人", "研究与产品决策者"],
        "active_workstreams": [
            "OpenClaw 智能体集群与 3021 看板",
            "One-Sim 仿真与 AI Planning",
            "程序开发自动化",
            "博士论文与技术文档",
        ],
        "tools": ["飞书", "Obsidian", "Codex", "OpenClaw"],
    },
    "business_context": {
        "domains": [
            "多智能体协作",
            "仿真与兵棋推演",
            "AI 规划",
            "软件研发自动化",
            "知识管理",
            "文档生产",
        ],
        "operating_model": "擎天柱作为唯一任务入口，专业智能体分工执行。",
    },
    "preferences": {
        "language": "中文",
        "interaction": "先给方案和计划，关键任务经本人批准后执行。",
        "evidence": "必须提供测试、执行记录和可追踪来源。",
        "ui": "统一使用 3021 系统和一致的深色界面风格。",
    },
    "constraints": {
        "rules": [
            "不破坏 OpenClaw 现有逻辑。",
            "任务、计划、审批和证据以 3021 统一数据库为事实源。",
            "智能体不得越权执行不可逆操作。",
            "不同用户按模块权限和数据权限协作。",
        ]
    },
    "source": "phase1-bootstrap",
}


FACTS = (
    (
        "decision",
        "decision.single_entry",
        "擎天柱是用户下达任务、接收进度和反馈结果的唯一智能体入口。",
        "critical",
    ),
    (
        "system",
        "system.source_of_truth",
        "3021 统一数据库是项目、任务、计划、审批、执行状态和证据的事实源。",
        "critical",
    ),
    (
        "workflow",
        "workflow.approval",
        "计划由智能体系统评估生成，孙总批准后才进入执行。",
        "critical",
    ),
    (
        "knowledge",
        "knowledge.authority",
        "Obsidian 知识库目录 /Users/apple/工作桌面/knowledge 是长期业务知识的主要原始来源。",
        "high",
    ),
    (
        "infrastructure",
        "infrastructure.mac_mini",
        "OpenClaw 和 3021 看板运行在 Mac mini 192.168.31.41。",
        "high",
    ),
    (
        "infrastructure",
        "infrastructure.model_server",
        "大模型服务器地址为 192.168.1.5；不可达时必须降级且不得阻断基础检索。",
        "high",
    ),
    (
        "preference",
        "preference.language",
        "界面、方案、任务反馈和交付说明默认使用中文。",
        "high",
    ),
    (
        "preference",
        "preference.delivery",
        "采用先方案、再批准、后执行、最终附测试与证据的交付方式。",
        "high",
    ),
)


def _profile_matches(existing: dict | None) -> bool:
    if not existing:
        return False
    mapping = {
        "display_name": "display_name",
        "preferred_name": "preferred_name",
        "timezone_name": "timezone",
        "summary": "summary",
        "work_context": "work_context",
        "business_context": "business_context",
        "preferences": "preferences",
        "constraints": "constraints",
        "source": "source",
    }
    return all(existing.get(target) == PROFILE[source] for source, target in mapping.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="1")
    args = parser.parse_args()

    existing = context_retrieval_service.get_profile(args.user_id)
    if _profile_matches(existing):
        profile = existing
        profile_changed = False
    else:
        profile = context_retrieval_service.upsert_profile(
            user_id=args.user_id,
            **PROFILE,
        )
        profile_changed = True

    facts = []
    for fact_type, fact_key, fact_value, importance in FACTS:
        facts.append(
            context_retrieval_service.upsert_fact(
                user_id=args.user_id,
                fact_type=fact_type,
                fact_key=fact_key,
                fact_value=fact_value,
                importance=importance,
                source_type="migration",
                source_ref="phase1-bootstrap-v1",
                metadata={"managed_by": "seed_context_profile.py"},
            )
        )

    print(
        json.dumps(
            {
                "profile_id": profile["id"],
                "user_id": profile["user_id"],
                "version": profile["version"],
                "profile_changed": profile_changed,
                "facts": len(facts),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
