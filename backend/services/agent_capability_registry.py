"""Central registry for command-center agent capabilities and tool contracts.

P1 keeps capability and tool rules deterministic and local. Planning may still be
LLM-assisted, but validation and UI contracts come from this registry so the
system can explain why a step was assigned to an agent and which tools/evidence
are expected.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "optimus": {
        "name": "擎天柱",
        "role": "总项目管理",
        "task_types": ["coordination", "general", "review"],
    },
    "main": {
        "name": "主控",
        "role": "通用协调",
        "task_types": ["general", "coordination"],
    },
    "wheeljack": {
        "name": "千斤顶",
        "role": "架构与方案",
        "task_types": ["architecture", "coordination", "general"],
    },
    "ironhide": {
        "name": "铁皮",
        "role": "仿真与运维方案",
        "task_types": ["architecture", "operations", "coordination"],
    },
    "leonardo": {
        "name": "李奥纳多",
        "role": "架构师",
        "task_types": ["architecture", "coordination", "general"],
    },
    "raphael": {
        "name": "拉斐尔",
        "role": "后端开发",
        "task_types": ["backend", "api", "database", "general"],
    },
    "donatello": {
        "name": "多纳泰罗",
        "role": "前端开发",
        "task_types": ["frontend", "ui", "general"],
    },
    "michelangelo": {
        "name": "米开朗基罗",
        "role": "测试工程",
        "task_types": ["testing", "review", "general"],
    },
    "perceptor": {
        "name": "感知器",
        "role": "资料与情报",
        "task_types": ["research", "knowledge", "general"],
    },
    "ratchet": {
        "name": "救护车",
        "role": "知识库与质量修复",
        "task_types": ["knowledge", "review", "testing", "general"],
    },
    "ultra-magnus": {
        "name": "通天晓",
        "role": "文档与结构",
        "task_types": ["writing", "document", "review", "general"],
    },
    "jazz": {
        "name": "爵士",
        "role": "销售与客户关系",
        "task_types": ["sales", "operations", "general"],
    },
    "shockwave": {
        "name": "声波",
        "role": "质量审查",
        "task_types": ["review", "testing", "research", "general"],
    },
    "soundwave": {
        "name": "声波",
        "role": "财务管理",
        "task_types": ["finance", "operations", "general"],
    },
    "bumblebee": {
        "name": "大黄蜂",
        "role": "运维",
        "task_types": ["operations", "general"],
    },
}

TASK_AGENT_DEFAULTS: dict[str, str] = {
    "architecture": "leonardo",
    "backend": "raphael",
    "api": "raphael",
    "database": "raphael",
    "frontend": "donatello",
    "ui": "donatello",
    "testing": "michelangelo",
    "research": "perceptor",
    "knowledge": "ratchet",
    "writing": "ultra-magnus",
    "document": "ultra-magnus",
    "operations": "bumblebee",
    "finance": "soundwave",
    "sales": "jazz",
    "review": "shockwave",
    "coordination": "optimus",
    "general": "optimus",
}

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "context_search": {
        "name": "背景检索",
        "category": "context",
        "status": "available",
        "description": "检索项目、记忆、会话和文档背景，形成可引用上下文。",
        "evidence_types": ["context_pack", "citations"],
    },
    "agent_run": {
        "name": "智能体执行",
        "category": "agent",
        "status": "available",
        "description": "调用指定智能体完成通用分析、执行或复核。",
        "evidence_types": ["result_summary"],
    },
    "codex": {
        "name": "Coding Agent / Codex",
        "category": "development",
        "status": "available",
        "description": "在代码仓库中完成受控修改。",
        "evidence_types": ["diff_summary"],
    },
    "test_runner": {
        "name": "测试运行器",
        "category": "verification",
        "status": "available",
        "description": "运行后端、单元或集成测试并回传输出。",
        "evidence_types": ["test_output"],
    },
    "build_runner": {
        "name": "前端构建器",
        "category": "verification",
        "status": "available",
        "description": "执行前端类型检查、构建或等价界面验证。",
        "evidence_types": ["build_output"],
    },
    "quality_checker": {
        "name": "质量检查器",
        "category": "review",
        "status": "available",
        "description": "执行计划、结果和风险复核，产出问题清单。",
        "evidence_types": ["review_report"],
    },
    "document_workspace": {
        "name": "文档工作台",
        "category": "document",
        "status": "available",
        "description": "处理文档结构、正文、引用与格式交付。",
        "evidence_types": ["document_diff", "quality_notes"],
    },
    "finance_reconcile": {
        "name": "财务核对工具",
        "category": "finance",
        "status": "available",
        "description": "校验金额、对象、科目、凭证和对账证据链。",
        "evidence_types": ["finance_evidence"],
    },
    "ops_check": {
        "name": "运维检查工具",
        "category": "operations",
        "status": "available",
        "description": "检查服务状态、配置变更和运行回执。",
        "evidence_types": ["ops_log"],
    },
}

TASK_TYPE_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "architecture": {
        "required_tools": ["context_search"],
        "deliverables": ["架构边界与接口契约", "验收标准"],
        "acceptance_criteria": ["覆盖目标范围、依赖、风险和验收口径"],
        "evidence_required": ["architecture_notes"],
    },
    "backend": {
        "required_tools": ["codex", "test_runner"],
        "deliverables": ["后端/API 实现", "测试结果"],
        "acceptance_criteria": ["相关接口或服务行为符合计划", "后端测试或等价验证通过"],
        "evidence_required": ["diff_summary", "test_output"],
    },
    "api": {
        "required_tools": ["codex", "test_runner"],
        "deliverables": ["API 实现", "接口测试结果"],
        "acceptance_criteria": ["接口契约稳定且有验证证据"],
        "evidence_required": ["diff_summary", "test_output"],
    },
    "database": {
        "required_tools": ["codex", "test_runner"],
        "deliverables": ["数据结构或迁移实现", "回归结果"],
        "acceptance_criteria": ["数据读写、迁移和回滚路径可验证"],
        "evidence_required": ["diff_summary", "test_output"],
    },
    "frontend": {
        "required_tools": ["codex", "build_runner"],
        "deliverables": ["前端交互实现", "构建或界面验证结果"],
        "acceptance_criteria": ["页面状态与错误处理完整", "前端构建或等价验证通过"],
        "evidence_required": ["diff_summary", "build_output"],
    },
    "ui": {
        "required_tools": ["codex", "build_runner"],
        "deliverables": ["界面实现", "视觉/交互验证结果"],
        "acceptance_criteria": ["关键状态和响应式布局可验证"],
        "evidence_required": ["diff_summary", "build_output"],
    },
    "testing": {
        "required_tools": ["test_runner"],
        "deliverables": ["测试/回归结果", "问题清单"],
        "acceptance_criteria": ["关键路径有可复现验证证据"],
        "evidence_required": ["test_output"],
    },
    "research": {
        "required_tools": ["context_search"],
        "deliverables": ["资料清单", "证据摘要"],
        "acceptance_criteria": ["关键事实保留来源或引用编号"],
        "evidence_required": ["citations"],
    },
    "knowledge": {
        "required_tools": ["context_search"],
        "deliverables": ["知识整理结果", "待沉淀记忆候选"],
        "acceptance_criteria": ["区分事实、推断和待核验信息"],
        "evidence_required": ["source_refs"],
    },
    "writing": {
        "required_tools": ["document_workspace"],
        "deliverables": ["文档结构或正文", "引用/证据说明"],
        "acceptance_criteria": ["结构、论证、引用和交付目标一致"],
        "evidence_required": ["document_diff", "quality_notes"],
    },
    "document": {
        "required_tools": ["document_workspace"],
        "deliverables": ["文档交付物", "引用/证据说明"],
        "acceptance_criteria": ["结构、事实和格式符合交付目标"],
        "evidence_required": ["document_diff", "quality_notes"],
    },
    "review": {
        "required_tools": ["quality_checker"],
        "deliverables": ["审查结论", "问题与风险清单"],
        "acceptance_criteria": ["明确通过、退回或需补充的判断"],
        "evidence_required": ["review_report"],
    },
    "finance": {
        "required_tools": ["finance_reconcile"],
        "deliverables": ["财务处理结果", "凭证/对账证据"],
        "acceptance_criteria": ["金额、对象、科目和证据链一致"],
        "evidence_required": ["finance_evidence"],
    },
    "operations": {
        "required_tools": ["ops_check"],
        "deliverables": ["运维处理结果", "状态检查证据"],
        "acceptance_criteria": ["服务状态或配置变更有回执"],
        "evidence_required": ["ops_log"],
    },
    "sales": {
        "required_tools": ["context_search"],
        "deliverables": ["客户/销售跟进结果", "风险说明"],
        "acceptance_criteria": ["客户目标、下一步和责任人清晰"],
        "evidence_required": ["coordination_notes"],
    },
    "coordination": {
        "required_tools": ["context_search"],
        "deliverables": ["协调结论", "下一步安排"],
        "acceptance_criteria": ["目标、责任人和完成标准清晰"],
        "evidence_required": ["coordination_notes"],
    },
    "general": {
        "required_tools": ["agent_run"],
        "deliverables": ["任务输出", "风险说明"],
        "acceptance_criteria": ["输出直接回应用户目标"],
        "evidence_required": ["result_summary"],
    },
}


class AgentCapabilityRegistry:
    def agent_ids(self) -> list[str]:
        return sorted(AGENT_PROFILES)

    def known_agent(self, agent_id: str) -> bool:
        return str(agent_id or "").strip() in AGENT_PROFILES

    def agent_profile(self, agent_id: str) -> dict[str, Any]:
        return deepcopy(AGENT_PROFILES.get(str(agent_id or "").strip(), {}))

    def agent_task_types(self, agent_id: str) -> set[str]:
        profile = AGENT_PROFILES.get(str(agent_id or "").strip(), {})
        return {str(item) for item in profile.get("task_types", [])}

    def agent_supports_task(self, agent_id: str, task_type: str) -> bool:
        supported = self.agent_task_types(agent_id)
        clean_task_type = str(task_type or "general").strip().lower()
        return clean_task_type in supported or "general" in supported

    def default_agent_for_task(self, task_type: str) -> str:
        clean_task_type = str(task_type or "general").strip().lower()
        return TASK_AGENT_DEFAULTS.get(clean_task_type, TASK_AGENT_DEFAULTS["general"])

    def task_agent_defaults(self) -> dict[str, str]:
        return dict(TASK_AGENT_DEFAULTS)

    def step_defaults(self, task_type: str) -> dict[str, list[str]]:
        clean_task_type = str(task_type or "general").strip().lower()
        return deepcopy(TASK_TYPE_DEFAULTS.get(clean_task_type, TASK_TYPE_DEFAULTS["general"]))

    def known_tool(self, tool_id: str) -> bool:
        return str(tool_id or "").strip() in TOOL_REGISTRY

    def tool_profile(self, tool_id: str) -> dict[str, Any]:
        clean_tool_id = str(tool_id or "").strip()
        profile = deepcopy(TOOL_REGISTRY.get(clean_tool_id, {}))
        if profile:
            profile["id"] = clean_tool_id
        return profile

    def describe_tools(self, tool_ids: list[Any]) -> list[dict[str, Any]]:
        descriptions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_tool_id in tool_ids:
            tool_id = str(raw_tool_id or "").strip()
            if not tool_id or tool_id in seen:
                continue
            seen.add(tool_id)
            profile = self.tool_profile(tool_id)
            if not profile:
                profile = {
                    "id": tool_id,
                    "name": tool_id,
                    "category": "unknown",
                    "status": "unknown",
                    "description": "未注册工具",
                    "evidence_types": [],
                }
            descriptions.append(profile)
        return descriptions

    def unavailable_required_tools(self, tool_ids: list[Any]) -> list[str]:
        unavailable: list[str] = []
        for profile in self.describe_tools(tool_ids):
            if profile.get("status") not in {"available", "manual"}:
                unavailable.append(str(profile.get("id") or ""))
        return unavailable

    def catalog(self) -> dict[str, Any]:
        return {
            "agents": [
                {"id": agent_id, **deepcopy(profile)}
                for agent_id, profile in sorted(AGENT_PROFILES.items())
            ],
            "tools": [
                {"id": tool_id, **deepcopy(profile)}
                for tool_id, profile in sorted(TOOL_REGISTRY.items())
            ],
            "task_agent_defaults": self.task_agent_defaults(),
            "task_type_defaults": deepcopy(TASK_TYPE_DEFAULTS),
        }


agent_capability_registry = AgentCapabilityRegistry()
