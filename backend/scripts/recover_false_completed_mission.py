#!/usr/bin/env python3
"""Create an auditable recovery plan after a mission was falsely completed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.command_center_service import (  # noqa: E402
    CommandCenterError,
    command_center_service,
)


def _artifact_manifest(steps: list[dict[str, Any]], resume_order: int) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for step in steps:
        if int(step.get("order_index") or 0) >= resume_order:
            continue
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        for artifact in result.get("artifacts") or []:
            if not isinstance(artifact, dict) or not artifact.get("uri"):
                continue
            artifacts.append(
                {
                    "source_step_order": int(step.get("order_index") or 0),
                    "source_step_id": str(step.get("id") or ""),
                    "artifact_key": str(artifact.get("artifact_key") or ""),
                    "artifact_type": str(artifact.get("artifact_type") or ""),
                    "title": str(artifact.get("title") or ""),
                    "uri": str(artifact.get("uri") or ""),
                    "content_hash": str(artifact.get("content_hash") or ""),
                }
            )
    return artifacts


def build_recovery_plan(
    mission: dict[str, Any],
    *,
    source_plan_version: int,
    resume_order: int,
    artifact_steps: list[dict[str, Any]] | None = None,
    artifact_before_order: int | None = None,
    durable_workspace: str = "",
    durable_uri_prefix: str = "",
) -> dict[str, Any]:
    plan = mission.get("plan") or {}
    raw_plan = plan.get("raw_plan") if isinstance(plan.get("raw_plan"), dict) else {}
    if int(plan.get("version") or 0) != source_plan_version:
        raise CommandCenterError(
            f"current plan version is {plan.get('version')}, expected {source_plan_version}"
        )
    raw_steps = [item for item in raw_plan.get("steps") or [] if isinstance(item, dict)]
    selected = [
        item for item in raw_steps if int(item.get("order_index") or 0) >= resume_order
    ]
    if not selected:
        raise CommandCenterError("source plan has no steps at or after resume order")

    old_orders = [int(item.get("order_index") or 0) for item in selected]
    order_map = {old_order: index for index, old_order in enumerate(old_orders, start=1)}
    artifacts = _artifact_manifest(
        list(artifact_steps if artifact_steps is not None else mission.get("steps") or []),
        artifact_before_order if artifact_before_order is not None else resume_order,
    )
    if not artifacts:
        raise CommandCenterError("no reusable artifacts were found before the resume point")

    recovery_steps: list[dict[str, Any]] = []
    for new_order, raw_step in enumerate(selected, start=1):
        old_order = int(raw_step.get("order_index") or 0)
        step = dict(raw_step)
        step["order_index"] = new_order
        step["depends_on"] = [
            order_map[int(dependency)]
            for dependency in raw_step.get("depends_on") or []
            if int(dependency) in order_map
        ]
        step["input"] = {
            **(raw_step.get("input") if isinstance(raw_step.get("input"), dict) else {}),
            "recovery": {
                "source_plan_version": source_plan_version,
                "source_step_order": old_order,
                "resume_reason": "repair false completion while preserving prior artifacts",
                "upstream_artifacts": artifacts,
            },
        }
        if durable_workspace:
            step["input"]["durable_workspace"] = {
                "repository": durable_workspace,
                "artifact_uri_prefix": durable_uri_prefix or durable_workspace,
                "ephemeral_paths_forbidden": True,
                "required_hash": "sha256",
            }
        step["description"] = (
            f"恢复执行：复用恢复输入中的已验证交付物，"
            f"重新执行源计划 V{source_plan_version} 的对应步骤。"
            + (
                f"必须在持久仓库 {durable_workspace} 中执行并交付，"
                "不得使用 /workspace 等临时沙箱路径。"
                if durable_workspace
                else ""
            )
            + str(raw_step.get("description") or "")
        )
        step.pop("idempotency_key", None)
        step.pop("idempotency_key_generated", None)
        recovery_steps.append(step)

    return {
        "schema_version": "2.0",
        "summary": (
            f"从计划 V{source_plan_version} 恢复，复用已验证上游交付物并重新执行"
            f"源计划步骤 {resume_order} 及之后的任务"
        ),
        "rationale": (
            "原计划的上游交付物真实存在，失败位于交接包装和假完成门禁。"
            "保留原计划为事故证据，通过新计划版本恢复执行。"
        ),
        "risk_level": str(raw_plan.get("risk_level") or "medium"),
        "steps": recovery_steps,
        "recovery": {
            "source_plan_version": source_plan_version,
            "resume_order": resume_order,
            "artifact_count": len(artifacts),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mission_id")
    parser.add_argument("--source-plan-version", type=int, required=True)
    parser.add_argument("--resume-order", type=int, required=True)
    parser.add_argument("--artifact-plan-version", type=int)
    parser.add_argument("--artifact-before-order", type=int)
    parser.add_argument("--durable-workspace", default="")
    parser.add_argument("--durable-uri-prefix", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--actor", default="admin:recovery")
    args = parser.parse_args()

    mission = command_center_service.get_mission(args.mission_id)
    artifact_steps = None
    artifact_plan_version = args.artifact_plan_version or args.source_plan_version
    if artifact_plan_version != args.source_plan_version:
        with command_center_service.connect() as conn:
            artifact_rows = conn.execute(
                "SELECT * FROM mission_steps WHERE mission_id=? AND plan_version=? "
                "ORDER BY order_index",
                (args.mission_id, artifact_plan_version),
            ).fetchall()
        artifact_steps = [
            command_center_service._serialize_step(row) for row in artifact_rows
        ]
    plan = build_recovery_plan(
        mission,
        source_plan_version=args.source_plan_version,
        resume_order=args.resume_order,
        artifact_steps=artifact_steps,
        artifact_before_order=args.artifact_before_order,
        durable_workspace=args.durable_workspace,
        durable_uri_prefix=args.durable_uri_prefix,
    )
    preview = {
        "mission_id": args.mission_id,
        "source_plan_version": args.source_plan_version,
        "next_plan_version": int(mission.get("plan_version") or 0) + 1,
        "resume_order": args.resume_order,
        "artifact_count": plan["recovery"]["artifact_count"],
        "artifact_plan_version": artifact_plan_version,
        "durable_workspace": args.durable_workspace,
        "step_count": len(plan["steps"]),
        "steps": [
            {
                "order_index": item["order_index"],
                "title": item.get("title"),
                "depends_on": item.get("depends_on") or [],
            }
            for item in plan["steps"]
        ],
        "applied": False,
        "approved": False,
    }
    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    if mission.get("status") == "completed":
        command_center_service.reopen_for_recovery(
            args.mission_id,
            actor=args.actor,
            reason=(
                f"修复计划 V{args.source_plan_version} 的假完成："
                "保留历史记录，用新计划版本恢复执行"
            ),
        )
    elif mission.get("status") != "waiting_feedback":
        raise CommandCenterError(
            f"mission must be completed or waiting_feedback, got {mission.get('status')}"
        )

    planned = command_center_service.save_plan(
        args.mission_id,
        plan,
        created_by_agent_id=args.actor,
    )
    preview["applied"] = True
    preview["next_plan_version"] = planned["plan_version"]
    if args.approve:
        planned = command_center_service.approve(
            args.mission_id,
            decided_by=args.actor,
            comment="用户已授权按修复方案恢复执行",
        )
        preview["approved"] = planned["approval_status"] == "approved"
        preview["status"] = planned["status"]
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
