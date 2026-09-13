"""Course-product baseline, template, provenance and release readiness."""

from __future__ import annotations

import copy
import math
from typing import Any

from project_manager import project_manager
from services.command_center_service import (
    CommandCenterService,
    command_center_service,
)
from services.document_workspace_service import (
    DocumentProductionBlocked,
    DocumentWorkspaceError,
)
from services.multi_document_service import multi_document_service
from services.work_run_service import WorkRunService, work_run_service


COURSE_TEMPLATE_KEY = "surface_wargame_course_v1"
COURSE_PROJECT_ID = "proj-16ca49b862"
MANUAL_PROJECT_ID = "proj-c57e28f8e0"
SIMULATION_PROJECT_ID = "proj-87336865f4"
COURSE_DATA_VERSION = "course-baseline-20h-v4"

MANUAL_RULE_REFS = [
    {
        "ref_type": "project_document",
        "project_id": MANUAL_PROJECT_ID,
        "document_id": "doc-0d2362510580",
        "relation": "authoritative_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": MANUAL_PROJECT_ID,
        "document_id": "doc-0522adjud01",
        "relation": "adjudication_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": MANUAL_PROJECT_ID,
        "document_id": "doc-0522operator",
        "relation": "operator_table",
        "required": True,
        "version": "R1.2/D1.2",
    },
]
MANUAL_DATA_REFS = [
    {
        "ref_type": "project_document",
        "project_id": MANUAL_PROJECT_ID,
        "document_id": "doc-d232b21175a2",
        "relation": "adjudication_data",
        "required": True,
        "version": "R1.1/D1.1",
    },
    {
        "ref_type": "project_document",
        "project_id": MANUAL_PROJECT_ID,
        "document_id": "doc-36c7b8d093b8",
        "relation": "operator_data",
        "required": True,
        "version": "R1.1/D1.1",
    },
]
SIMULATION_REFS = [
    {
        "ref_type": "project_product",
        "project_id": SIMULATION_PROJECT_ID,
        "product_id": "one-sim",
        "relation": "practice_runtime",
        "required": True,
        "version": "",
    },
    {
        "ref_type": "project_product",
        "project_id": SIMULATION_PROJECT_ID,
        "product_id": "ai-planning-5130",
        "relation": "planning_runtime",
        "required": True,
        "version": "",
    },
]


def default_course_profile() -> dict[str, Any]:
    units = [
        ("L01", "兵棋基础与《谋战》体系认识", "theory"),
        ("L02", "水面舰艇编队战术、推演流程与裁决方法", "theory"),
        ("L03", "《谋战》组件、地图、棋子与规则查用", "practice"),
        ("L04", "单回合操作、态势标绘与裁决记录", "practice"),
        ("L05", "作战想定理解、关键点识别与任务构建", "practice"),
        ("L06", "五人编组、编队部署与行动方案制定", "practice"),
        ("L07", "侦察预警、电子战与指挥协同专项推演", "practice"),
        ("L08", "制空支援、对海打击与防空反导专项推演", "practice"),
        ("L09", "关键点争夺、跨域综合对抗与软件辅助复盘", "practice"),
        ("L10", "综合考核：想定分析、对抗推演与复盘答辩", "assessment"),
    ]
    return {
        "template_key": COURSE_TEMPLATE_KEY,
        "version": "1.1",
        "canonical_title": "水面舰艇作战软件与兵棋推演",
        "course_code": "YJZT503",
        "target_audience": "本科军兵种作战指挥专业",
        "course_nature": "选修课",
        "total_hours": 20,
        "unit_hours": 2,
        "theory_hours": 4,
        "practice_hours": 14,
        "assessment_hours": 2,
        "theory_sessions": 2,
        "practice_sessions": 7,
        "assessment_sessions": 1,
        "units": [
            {
                "id": unit_id,
                "order": index,
                "title": title,
                "delivery_mode": delivery_mode,
                "hours": 2,
            }
            for index, (unit_id, title, delivery_mode) in enumerate(units, start=1)
        ],
    }


LESSON_OUTLINE = [
    "第一章 教学目标",
    "第二章 教学重点",
    "第三章 教学难点",
    "第四章 教学内容与时间分配",
    "第五章 教学方法",
    "第六章 考核与作业",
    "第七章 来源依据",
]


def _template_products() -> list[dict[str, Any]]:
    profile = default_course_profile()
    products: list[dict[str, Any]] = [
        {
            "key": "course-plan",
            "title": "《水面舰艇作战软件与兵棋推演》课程教学计划（20学时稿）",
            "aliases": ["《兵棋推演与智能决策》课程教学计划（16学时稿）"],
            "legacy_id": "doc-e811bedd87f9",
            "kind": "rich_text",
            "product_type": "course_plan",
            "quality_profile": "course_plan_v1",
            "outline": [
                "第一章 理论基础与裁决方法",
                "第二章 《谋战》兵棋规则与基本操作",
                "第三章 想定构建与行动方案",
                "第四章 编队专项与综合对抗推演",
                "第五章 综合考核与复盘答辩",
            ],
            "required_for_release": True,
        },
        {
            "key": "teaching-schedule",
            "title": "水面舰艇作战软件与兵棋推演教学进度表（20学时版）",
            "aliases": ["水面舰艇指挥决策与兵棋推演教学进度表（10学时版）"],
            "legacy_id": "doc-2a28da7429f0",
            "kind": "rich_text",
            "product_type": "teaching_schedule",
            "quality_profile": "teaching_schedule_v1",
            "outline": ["第一章 课程基本信息", "第二章 教学进度安排"],
            "required_for_release": True,
        },
    ]
    legacy_lesson_ids = {
        "L01": "doc-3a9dbb65b9a3",
        "L02": "doc-6085f649c11a",
        "L03": "doc-105f2073f3d9",
        "L07": "doc-60e4858f35af",
        "L08": "doc-8248d6366ec3",
    }
    legacy_aliases = {
        "L01": ["第1讲：兵棋概述"],
        "L02": ["第2讲：兵棋推演流程及运用"],
        "L03": ["第3讲：手工兵棋基本操作"],
        "L07": ["第4讲：兵棋推演实作（上）"],
        "L08": ["第5讲：兵棋推演实作（下）"],
    }
    for unit in profile["units"]:
        products.append(
            {
                "key": f"lesson-{unit['id'].lower()}",
                "title": f"第{unit['order']}讲：{unit['title']}",
                "aliases": legacy_aliases.get(unit["id"], []),
                "legacy_id": legacy_lesson_ids.get(unit["id"], ""),
                "kind": "rich_text",
                "product_type": "lesson_plan",
                "course_unit_ids": [unit["id"]],
                "quality_profile": "lesson_plan_v1",
                "outline": LESSON_OUTLINE,
                "required_for_release": True,
            }
        )
    products.extend(
        [
            {
                "key": "practice-guide",
                "title": "水面舰艇作战软件与兵棋推演实作指导书",
                "aliases": [],
                "legacy_id": "doc-e6071aa369ed",
                "kind": "rich_text",
                "product_type": "practice_guide",
                "course_unit_ids": [f"L{index:02d}" for index in range(3, 10)],
                "quality_profile": "practice_guide_v1",
                "outline": [
                    "第一章 实作目标",
                    "第二章 环境与器材",
                    "第三章 规则版本与软件版本",
                    "第四章 作战想定",
                    "第五章 组织分工",
                    "第六章 操作步骤",
                    "第七章 记录与态势维护",
                    "第八章 复盘讲评",
                    "第九章 纪律与安全要求",
                    "第十章 报告要求",
                ],
                "required_for_release": True,
            },
            {
                "key": "assessment",
                "title": "课程考核方案与评分量规",
                "aliases": [],
                "legacy_id": "doc-f7ff5f8fe4f2",
                "kind": "rich_text",
                "product_type": "assessment",
                "course_unit_ids": ["L10"],
                "quality_profile": "assessment_v1",
                "outline": [
                    "第一章 考核目标",
                    "第二章 考核组成与权重",
                    "第三章 理论与操作评分",
                    "第四章 推演与复盘评分",
                    "第五章 成绩评定与反馈",
                ],
                "required_for_release": True,
            },
            {
                "key": "course-presentation",
                "title": "兵棋推演与智能决策培训课件（88页）",
                "aliases": [],
                "legacy_id": "doc-5b225b46318f",
                "kind": "presentation",
                "product_type": "course_presentation",
                "course_unit_ids": [f"L{index:02d}" for index in range(1, 11)],
                "quality_profile": "presentation_binding_v1",
                "outline": [],
                "required_for_release": True,
            },
            {
                "key": "manual-presentation",
                "title": "水面舰艇编队战术手工兵棋讲解（54页）",
                "aliases": [],
                "legacy_id": "doc-67294b2100be",
                "kind": "presentation",
                "product_type": "manual_wargame_presentation",
                "course_unit_ids": [f"L{index:02d}" for index in range(3, 10)],
                "quality_profile": "presentation_binding_v1",
                "outline": [],
                "required_for_release": True,
            },
            {
                "key": "lecture-material",
                "title": "讲课材料整理：分层推演、协同指挥与制空支援",
                "aliases": [],
                "legacy_id": "",
                "kind": "rich_text",
                "product_type": "lecture_material",
                "quality_profile": "",
                "outline": [
                    "第一章 材料定位与使用边界",
                    "第二章 个人—战术—全局三级能力模型",
                    "第三章 五人编组与指挥关系",
                    "第四章 制空支援与电子战运用",
                    "第五章 火力分配与交战时机",
                    "第六章 基础操作与自动防御",
                    "第七章 侦察预警与电磁管控",
                    "第八章 关键点争夺与全局节奏",
                    "第九章 课程课次映射",
                    "第十章 待规则核验事项",
                ],
                "required_for_release": False,
                "is_output_product": False,
            },
            {
                "key": "rule-verification-matrix",
                "title": "《谋战》口述材料参数核验矩阵",
                "aliases": [],
                "legacy_id": "",
                "kind": "rich_text",
                "product_type": "rule_verification_matrix",
                "quality_profile": "",
                "outline": [
                    "第一章 核验依据与使用边界",
                    "第二章 飞机载荷与武器数量",
                    "第三章 电子战等级范围与修正",
                    "第四章 射程有效杀伤区与不可逃逸区",
                    "第五章 自动防御目标分配与重复拦截",
                    "第六章 传感器调整与探测刷新",
                    "第七章 机炮与近程导弹使用条件",
                    "第八章 续航转场补给与再次出动",
                    "第九章 回合数量与两波次节奏",
                    "第十章 PPT内容适配审查",
                ],
                "required_for_release": False,
                "is_output_product": False,
            },
            {
                "key": "course-knowledge-selection",
                "title": "课程知识库优选底稿与融合说明",
                "aliases": [],
                "legacy_id": "",
                "kind": "rich_text",
                "product_type": "internal_reference",
                "quality_profile": "",
                "outline": [],
                "required_for_release": False,
                "is_output_product": False,
            },
            {
                "key": "internal-practice-template",
                "title": "实作指导书编写模板（反潜专业基础课程参考）",
                "aliases": [],
                "legacy_id": "doc-08b5aa8d383d",
                "kind": "rich_text",
                "product_type": "internal_reference",
                "quality_profile": "",
                "outline": [],
                "required_for_release": False,
                "is_output_product": False,
            },
        ]
    )
    return products


class CourseProductionService:
    def __init__(
        self,
        command_service: CommandCenterService | None = None,
        work_runs: WorkRunService | None = None,
    ):
        self.command_service = command_service or command_center_service
        self.work_runs = work_runs or work_run_service

    def _profile(self, project: dict[str, Any]) -> dict[str, Any]:
        spec = project.get("document_spec") if isinstance(project.get("document_spec"), dict) else {}
        profile = spec.get("course_profile")
        return copy.deepcopy(profile) if isinstance(profile, dict) else {}

    def validate_baseline(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        blockers = []
        if profile.get("template_key") != COURSE_TEMPLATE_KEY:
            blockers.append({"code": "course_baseline_missing", "message": "未应用水面舰艇兵棋课程产品模板"})
            return blockers
        units = profile.get("units") if isinstance(profile.get("units"), list) else []
        theory = sum(int(row.get("hours") or 0) for row in units if row.get("delivery_mode") == "theory")
        practice = sum(int(row.get("hours") or 0) for row in units if row.get("delivery_mode") == "practice")
        assessment = sum(int(row.get("hours") or 0) for row in units if row.get("delivery_mode") == "assessment")
        theory_sessions = sum(1 for row in units if row.get("delivery_mode") == "theory")
        practice_sessions = sum(1 for row in units if row.get("delivery_mode") == "practice")
        assessment_sessions = sum(1 for row in units if row.get("delivery_mode") == "assessment")
        total = sum(int(row.get("hours") or 0) for row in units)
        if (
            len(units) != 10
            or total != 20
            or int(profile.get("total_hours") or 0) != 20
            or int(profile.get("unit_hours") or 0) != 2
            or any(int(row.get("hours") or 0) != 2 for row in units)
        ):
            blockers.append({"code": "hour_total_mismatch", "message": "课程必须由10讲构成并合计20学时"})
        if (
            theory != 4
            or practice != 14
            or assessment != 2
            or theory_sessions != 2
            or practice_sessions != 7
            or assessment_sessions != 1
            or int(profile.get("theory_hours") or 0) != 4
            or int(profile.get("practice_hours") or 0) != 14
            or int(profile.get("assessment_hours") or 0) != 2
            or int(profile.get("theory_sessions") or 0) != 2
            or int(profile.get("practice_sessions") or 0) != 7
            or int(profile.get("assessment_sessions") or 0) != 1
        ):
            blockers.append(
                {
                    "code": "hour_split_mismatch",
                    "message": "课程必须采用2次理论、7次《谋战》兵棋实作、1次综合考核",
                }
            )
        if len({str(row.get("id") or "") for row in units}) != len(units):
            blockers.append({"code": "course_unit_duplicate", "message": "课程讲次ID存在重复"})
        return blockers

    def set_baseline(self, project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        profile = default_course_profile()
        profile.update(
            {
                key: value
                for key, value in payload.items()
                if value is not None and not (key == "units" and not value)
            }
        )
        blockers = self.validate_baseline(profile)
        if blockers:
            raise DocumentWorkspaceError("；".join(row["message"] for row in blockers))
        spec = copy.deepcopy(project.get("document_spec") or {})
        spec["course_profile"] = profile
        spec["edition"] = "20学时正式基线"
        spec["current_edition_label"] = "20学时"
        spec["updated_at"] = profile.get("updated_at") or ""
        updated = project_manager.update_project(str(project["id"]), {"document_spec": spec})
        if not updated:
            raise DocumentWorkspaceError("课程项目不存在")
        return copy.deepcopy(updated["document_spec"]["course_profile"])

    def _source_refs_for(self, product: dict[str, Any]) -> list[dict[str, Any]]:
        product_type = product["product_type"]
        units = set(product.get("course_unit_ids") or [])
        if product_type in {"course_plan", "teaching_schedule", "course_presentation"}:
            return copy.deepcopy([*MANUAL_RULE_REFS, *SIMULATION_REFS])
        if product_type == "lesson_plan" and units & {"L09", "L10"}:
            return copy.deepcopy([*MANUAL_RULE_REFS, *SIMULATION_REFS])
        if product_type == "lesson_plan" and units & {
            "L01",
            "L02",
            "L03",
            "L04",
            "L05",
            "L06",
            "L07",
            "L08",
        }:
            return copy.deepcopy(MANUAL_RULE_REFS)
        if product_type == "practice_guide":
            return copy.deepcopy([*MANUAL_RULE_REFS, *MANUAL_DATA_REFS, *SIMULATION_REFS])
        if product_type == "assessment":
            return copy.deepcopy([*MANUAL_RULE_REFS, *SIMULATION_REFS])
        if product_type == "manual_wargame_presentation":
            return copy.deepcopy(MANUAL_RULE_REFS)
        if product_type == "rule_verification_matrix":
            return copy.deepcopy([*MANUAL_RULE_REFS, *MANUAL_DATA_REFS])
        return []

    def _find_document(self, documents: list[dict[str, Any]], product: dict[str, Any]) -> dict[str, Any] | None:
        unit_ids = set(product.get("course_unit_ids") or [])
        legacy_id = product.get("legacy_id")
        if legacy_id:
            found = next((row for row in documents if row.get("id") == legacy_id), None)
            if found:
                return found
        names = {product["title"], *(product.get("aliases") or [])}
        found = next((row for row in documents if row.get("title") in names), None)
        if found:
            return found
        if product["product_type"] == "internal_reference":
            return None
        for row in documents:
            if row.get("product_type") == product["product_type"]:
                if not unit_ids or unit_ids == set(row.get("course_unit_ids") or []):
                    return row
        return None

    def apply_template(self, project: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        if str(project.get("project_type") or "") != "document":
            raise DocumentWorkspaceError("课程产品模板只能应用于文档项目")
        products = _template_products()
        documents = multi_document_service.list_documents(project)["documents"]
        actions = []
        resolved: dict[str, dict[str, Any]] = {}
        for order, product in enumerate(products):
            found = self._find_document(documents, product)
            if found:
                actions.append({"action": "update", "key": product["key"], "document_id": found["id"], "title": product["title"]})
                resolved[product["key"]] = found
            else:
                actions.append({"action": "create", "key": product["key"], "document_id": "", "title": product["title"]})
        if dry_run:
            return {"dry_run": True, "actions": actions, "summary": self._action_summary(actions)}

        self.set_baseline(project, default_course_profile())
        project = project_manager.get_project(str(project["id"])) or project
        documents = multi_document_service.list_documents(project)["documents"]
        for order, product in enumerate(products):
            found = self._find_document(documents, product)
            patch = {
                "title": product["title"],
                "sort_order": order,
                "is_output_product": product.get("is_output_product", True),
                "product_type": product["product_type"],
                "course_unit_ids": product.get("course_unit_ids", []),
                "quality_profile": product["quality_profile"],
                "required_for_release": product["required_for_release"],
                "source_refs": self._source_refs_for(product),
                "rules_version": "R1.2" if self._source_refs_for(product) and any(ref["project_id"] == MANUAL_PROJECT_ID for ref in self._source_refs_for(product)) else "",
                "data_version": COURSE_DATA_VERSION,
                "expected_chapters": (
                    len(product["outline"])
                    if product["kind"] == "rich_text" and product["outline"]
                    else 0
                ),
            }
            if found:
                updated = multi_document_service.update_document(project, str(found["id"]), patch)
            else:
                updated = multi_document_service.create_document(
                    project,
                    product["title"],
                    product["kind"],
                    outline=product["outline"],
                    is_output_product=product.get("is_output_product", True),
                    product_type=product["product_type"],
                    course_unit_ids=product.get("course_unit_ids", []),
                    quality_profile=product["quality_profile"],
                    required_for_release=product["required_for_release"],
                    source_refs=self._source_refs_for(product),
                    publication_status="draft" if product.get("is_output_product", True) else "internal",
                    rules_version=patch["rules_version"],
                    data_version=patch["data_version"],
                )
                if patch["expected_chapters"]:
                    updated = multi_document_service.update_document(
                        project,
                        str(updated["id"]),
                        {"expected_chapters": patch["expected_chapters"]},
                    )
            resolved[product["key"]] = updated
            documents = multi_document_service.list_documents(project)["documents"]

        internal_sources = [
            resolved["lecture-material"],
            resolved["rule-verification-matrix"],
            resolved["course-knowledge-selection"],
        ]
        for key, row in list(resolved.items()):
            if not row.get("is_output_product", True):
                continue
            data_source_ids = list(
                dict.fromkeys(
                    [
                        *(row.get("data_source_ids") or []),
                        *(str(source["id"]) for source in internal_sources),
                    ]
                )
            )
            resolved[key] = multi_document_service.update_document(
                project,
                str(row["id"]),
                {"data_source_ids": data_source_ids},
            )

        plan = resolved["course-plan"]
        for key, row in resolved.items():
            if key == "course-plan" or not row.get("is_output_product", True):
                continue
            source = resolved["lesson-l03"] if key == "manual-presentation" else plan
            manifest = None
            if row.get("kind") == "presentation":
                slide_count = int((row.get("stats") or {}).get("slide_count") or 0)
                if slide_count <= 0:
                    continue
                checksum = multi_document_service._record_checksum(project, row)  # noqa: SLF001
                manifest = {
                    "schema": "openclaw.course-presentation-mapping",
                    "contract_version": "course-v1",
                    "authority": {
                        "presentation_output": {
                            "sha256": checksum,
                            "slide_count": slide_count,
                            "main_slide_count": slide_count,
                            "appendix_slide_count": 0,
                            "notes_count": 0,
                        }
                    },
                    "slides": [
                        {
                            "slide": number,
                            "title": f"第{number}页",
                            "thesis_sections": source.get("course_unit_ids") or ["course-plan"],
                            "notes": "",
                        }
                        for number in range(1, slide_count + 1)
                    ],
                }
            multi_document_service.set_structure_binding(
                project,
                str(row["id"]),
                {
                    "mode": "mapped" if row.get("kind") == "presentation" else "derived",
                    "source_document_id": str(source["id"]),
                    "status": "aligned",
                    "mapped_items": int((row.get("stats") or {}).get("slide_count") or 1),
                    "unmapped_items": [],
                    "changed_sections": [],
                },
                manifest,
            )
        return {
            "dry_run": False,
            "actions": actions,
            "summary": self._action_summary(actions),
            "course_profile": self._profile(project_manager.get_project(str(project["id"])) or project),
        }

    def _action_summary(self, actions: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total": len(actions),
            "create": sum(1 for row in actions if row["action"] == "create"),
            "update": sum(1 for row in actions if row["action"] == "update"),
        }

    def _workstream_specs(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        products = {
            product["key"]: self._find_document(documents, product)
            for product in _template_products()
        }

        def document_ids(*keys: str) -> list[str]:
            return [
                str(products[key]["id"])
                for key in keys
                if products.get(key)
            ]

        lesson_keys = [f"lesson-l{index:02d}" for index in range(1, 11)]
        release_keys = [
            "course-plan",
            "teaching-schedule",
            *lesson_keys,
            "practice-guide",
            "assessment",
            "course-presentation",
            "manual-presentation",
        ]
        return [
            {
                "key": "baseline",
                "title": "编制课程教学计划",
                "description": "统一20学时课程基线，完成教学计划与进度表的内容对齐、来源映射和审定信息。",
                "assignee_agent": "ultra-magnus",
                "document_ids": document_ids("course-plan", "teaching-schedule"),
                "product_types": ["course_plan", "teaching_schedule"],
                "dependencies": [],
                "acceptance_criteria": [
                    "课程统一采用20学时、10讲的正式口径",
                    "教学计划与进度表的讲次、学时和考核安排一致",
                    "规则手册与one-sim实作环境来源可追溯",
                    "审定与签发信息完整",
                ],
                "points": [
                    {
                        "key": "baseline-normalize",
                        "title": "统一20学时课程口径",
                        "description": "消除原16学时、10学时并行版本与20课时文件名之间的口径差异。",
                        "assigned_agent": "ultra-magnus",
                        "document_ids": document_ids("course-plan", "teaching-schedule"),
                    },
                    {
                        "key": "baseline-sources",
                        "title": "核对规则与软件来源映射",
                        "description": "核对《谋战》规则文档和one-sim产品引用、版本及用途。",
                        "assigned_agent": "ratchet",
                        "document_ids": document_ids("course-plan", "teaching-schedule"),
                    },
                    {
                        "key": "baseline-review",
                        "title": "完成教学计划一致性审校",
                        "description": "检查课程目标、讲次、学时、考核与成果要求是否闭合。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids("course-plan", "teaching-schedule"),
                    },
                ],
            },
            {
                "key": "lessons",
                "title": "编写课程教案",
                "description": "按20学时基线完善10讲七章式教案，并完成规则、软件实作和考核内容的跨讲次一致性审校。",
                "assignee_agent": "ultra-magnus",
                "document_ids": document_ids(*lesson_keys),
                "product_types": ["lesson_plan"],
                "dependencies": ["baseline"],
                "acceptance_criteria": [
                    "10讲教案均包含目标、重点、难点、教学过程、方法、考核与来源依据",
                    "每讲按2学时组织并与教学进度表一致",
                    "第3至第9讲覆盖《谋战》规则与软件实作",
                    "第10讲与课程考核方案一致",
                ],
                "points": [
                    {
                        "key": "lessons-l01-l03",
                        "title": "复核第1至第3讲理论与规则基础",
                        "description": "校核基础概念、规则查用及原教案内容适配性。",
                        "assigned_agent": "ratchet",
                        "document_ids": document_ids(*lesson_keys[:3]),
                        "course_unit_ids": ["L01", "L02", "L03"],
                    },
                    {
                        "key": "lessons-l04-l06",
                        "title": "完善第4至第6讲基础实作教案",
                        "description": "完善单回合操作、想定分析和五人编组方案制定教学流程。",
                        "assigned_agent": "wheeljack",
                        "document_ids": document_ids(*lesson_keys[3:6]),
                        "course_unit_ids": ["L04", "L05", "L06"],
                    },
                    {
                        "key": "lessons-l07-l09",
                        "title": "完善第7至第9讲综合推演教案",
                        "description": "完善侦察预警、电子战、火力协同和跨域综合对抗教学流程。",
                        "assigned_agent": "ironhide",
                        "document_ids": document_ids(*lesson_keys[6:9]),
                        "course_unit_ids": ["L07", "L08", "L09"],
                    },
                    {
                        "key": "lessons-l10",
                        "title": "完善第10讲综合考核教案",
                        "description": "对齐想定分析、对抗推演、复盘答辩与评分量规。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids("lesson-l10"),
                        "course_unit_ids": ["L10"],
                    },
                    {
                        "key": "lessons-cross-review",
                        "title": "完成10讲教案套件一致性审校",
                        "description": "检查术语、规则版本、学时和前后讲次依赖。",
                        "assigned_agent": "ultra-magnus",
                        "document_ids": document_ids(*lesson_keys),
                    },
                ],
            },
            {
                "key": "practice",
                "title": "编写课程实作指导书",
                "description": "形成覆盖《谋战》手工兵棋与one-sim软件环境的七次实作指导、记录和复盘要求。",
                "assignee_agent": "wheeljack",
                "document_ids": document_ids("practice-guide"),
                "product_types": ["practice_guide"],
                "dependencies": ["baseline", "lessons"],
                "acceptance_criteria": [
                    "明确环境、软件、规则和数据版本",
                    "覆盖七次实作的组织、步骤、记录与复盘",
                    "说明one-sim与手工兵棋之间的使用边界",
                    "提交物、安全要求和验收标准完整",
                ],
                "points": [
                    {
                        "key": "practice-environment",
                        "title": "固化实作环境与版本基线",
                        "description": "记录设备、账号、one-sim产品、规则和数据版本。",
                        "assigned_agent": "wheeljack",
                        "document_ids": document_ids("practice-guide"),
                    },
                    {
                        "key": "practice-manual",
                        "title": "完善《谋战》手工兵棋实作流程",
                        "description": "核对组件、想定、行动、裁决和记录步骤。",
                        "assigned_agent": "ratchet",
                        "document_ids": document_ids("practice-guide"),
                    },
                    {
                        "key": "practice-software",
                        "title": "完善one-sim软件辅助实作流程",
                        "description": "明确软件加载、态势维护、推演执行和复盘证据。",
                        "assigned_agent": "ironhide",
                        "document_ids": document_ids("practice-guide"),
                    },
                    {
                        "key": "practice-acceptance",
                        "title": "补齐实作提交物与验收检查表",
                        "description": "定义记录表、复盘报告、安全要求和验收证据。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids("practice-guide"),
                    },
                ],
            },
            {
                "key": "assessment",
                "title": "设计课程考核与评分量规",
                "description": "形成与课程目标、软件实作、对抗推演和复盘答辩相对应的可执行评分量规。",
                "assignee_agent": "michelangelo",
                "document_ids": document_ids("assessment"),
                "product_types": ["assessment"],
                "dependencies": ["baseline", "practice"],
                "acceptance_criteria": [
                    "考核目标与课程能力指标对应",
                    "理论、操作、推演和复盘评分标准可观察",
                    "权重、扣分条件和证据要求明确",
                    "与第10讲教案和实作指导书一致",
                ],
                "points": [
                    {
                        "key": "assessment-objectives",
                        "title": "对齐考核目标与课程能力指标",
                        "description": "建立课程目标、考核环节和成果证据映射。",
                        "assigned_agent": "ultra-magnus",
                        "document_ids": document_ids("assessment"),
                    },
                    {
                        "key": "assessment-rubric",
                        "title": "完善可观察评分量规",
                        "description": "细化理论、操作、推演、协同和复盘评分等级。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids("assessment"),
                    },
                    {
                        "key": "assessment-evidence",
                        "title": "核对软件与兵棋考核证据",
                        "description": "明确系统日志、裁决记录、态势图和复盘报告的取证方式。",
                        "assigned_agent": "ironhide",
                        "document_ids": document_ids("assessment"),
                    },
                ],
            },
            {
                "key": "courseware",
                "title": "对齐课程课件与讲次结构",
                "description": "逐页复核两套既有PPT，使内容、讲次和规则版本与20学时课程基线一致。",
                "assignee_agent": "donatello",
                "document_ids": document_ids("course-presentation", "manual-presentation"),
                "product_types": ["course_presentation", "manual_wargame_presentation"],
                "dependencies": ["baseline", "lessons"],
                "acceptance_criteria": [
                    "88页课程课件映射到10讲课程结构",
                    "54页兵棋课件映射到《谋战》实作讲次",
                    "过时学时、规则和术语已修订或标注",
                    "关键页具备授课提示与来源依据",
                ],
                "points": [
                    {
                        "key": "courseware-88",
                        "title": "复核88页课程课件",
                        "description": "按10讲结构逐页核对内容归属、学时口径和授课提示。",
                        "assigned_agent": "donatello",
                        "document_ids": document_ids("course-presentation"),
                    },
                    {
                        "key": "courseware-54",
                        "title": "复核54页《谋战》兵棋课件",
                        "description": "核对规则、组件、实作步骤和来源版本。",
                        "assigned_agent": "ratchet",
                        "document_ids": document_ids("manual-presentation"),
                    },
                    {
                        "key": "courseware-visual",
                        "title": "统一课件视觉与讲次导航",
                        "description": "统一标题、页脚、讲次标识和关键内容层级。",
                        "assigned_agent": "donatello",
                        "document_ids": document_ids("course-presentation", "manual-presentation"),
                    },
                    {
                        "key": "courseware-qa",
                        "title": "完成课件交付检查",
                        "description": "检查结构绑定、缺页、过时内容和展示可读性。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids("course-presentation", "manual-presentation"),
                    },
                ],
            },
            {
                "key": "release",
                "title": "课程成果统一审校与发布",
                "description": "对16项必需课程成果执行来源、质量、版本和审批门禁，形成正式交付包。",
                "assignee_agent": "ultra-magnus",
                "document_ids": document_ids(*release_keys),
                "product_types": [
                    "course_plan",
                    "teaching_schedule",
                    "lesson_plan",
                    "practice_guide",
                    "assessment",
                    "course_presentation",
                    "manual_wargame_presentation",
                ],
                "dependencies": ["baseline", "lessons", "practice", "assessment", "courseware"],
                "acceptance_criteria": [
                    "16项必需成果均通过质量门禁",
                    "跨项目来源与规则、数据、软件版本可追溯",
                    "所有文档完成审批或发布",
                    "正式交付包可生成且内容完整",
                ],
                "points": [
                    {
                        "key": "release-provenance",
                        "title": "核验跨项目来源与版本",
                        "description": "检查规则文档、数据表和one-sim产品引用是否有效。",
                        "assigned_agent": "ratchet",
                        "document_ids": document_ids(*release_keys),
                    },
                    {
                        "key": "release-quality",
                        "title": "执行课程成果质量门禁",
                        "description": "汇总正文、课件、结构绑定和引用检查结果。",
                        "assigned_agent": "michelangelo",
                        "document_ids": document_ids(*release_keys),
                    },
                    {
                        "key": "release-approval",
                        "title": "完成审批并生成正式交付包",
                        "description": "确认阻断项清零，批准成果并生成统一交付包。",
                        "assigned_agent": "ultra-magnus",
                        "document_ids": document_ids(*release_keys),
                    },
                ],
            },
        ]

    def _find_workstream_task(
        self, tasks: list[dict[str, Any]], spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        return next(
            (
                task
                for task in tasks
                if (task.get("context") or {}).get("workstream_key") == spec["key"]
                or task.get("title") == spec["title"]
            ),
            None,
        )

    def _task_payload(
        self,
        spec: dict[str, Any],
        dependency_ids: list[str],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = copy.deepcopy((existing or {}).get("context") or {})
        context.update(
            {
                "workstream_key": spec["key"],
                "document_ids": spec["document_ids"],
                "product_types": spec["product_types"],
                "course_baseline_version": "1.1",
                "iteration": int(context.get("iteration") or 1),
                "source_project_ids": [MANUAL_PROJECT_ID, SIMULATION_PROJECT_ID],
            }
        )
        return {
            "type": "writing",
            "title": spec["title"],
            "description": spec["description"],
            "assignee_agent": spec["assignee_agent"],
            "assignee_agent_id": spec["assignee_agent"],
            "priority": "high",
            "dependencies": dependency_ids,
            "acceptance_criteria": spec["acceptance_criteria"],
            "context": context,
        }

    def apply_work_plan(
        self, project: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        baseline_blockers = self.validate_baseline(self._profile(project))
        if baseline_blockers:
            raise DocumentWorkspaceError("；".join(row["message"] for row in baseline_blockers))
        documents = multi_document_service.list_documents(project)["documents"]
        specs = self._workstream_specs(documents)
        tasks = list(project.get("tasks") or [])
        actions = []
        for spec in specs:
            existing = self._find_workstream_task(tasks, spec)
            existing_point_keys = {
                str((point.get("context") or {}).get("work_point_key") or point.get("title") or "")
                for point in (existing or {}).get("development_points") or []
            }
            missing_points = [
                point
                for point in spec["points"]
                if point["key"] not in existing_point_keys
                and point["title"] not in existing_point_keys
            ]
            actions.append(
                {
                    "action": "update" if existing else "create",
                    "key": spec["key"],
                    "task_id": str((existing or {}).get("id") or ""),
                    "title": spec["title"],
                    "points_to_add": len(missing_points),
                }
            )
        if dry_run:
            return {
                "dry_run": True,
                "actions": actions,
                "summary": self._work_plan_action_summary(actions),
            }

        resolved: dict[str, dict[str, Any]] = {}
        for spec in specs:
            refreshed = project_manager.get_project(str(project["id"])) or project
            tasks = list(refreshed.get("tasks") or [])
            existing = self._find_workstream_task(tasks, spec)
            dependency_ids = [
                str(resolved[key]["id"])
                for key in spec["dependencies"]
                if key in resolved
            ]
            payload = self._task_payload(spec, dependency_ids, existing)
            if existing:
                task = project_manager.update_task(str(existing["id"]), payload)
            else:
                payload.update({"status": "todo", "progress": 0})
                task = project_manager.add_task(str(project["id"]), payload)
            if not task:
                raise DocumentWorkspaceError(f"课程任务同步失败：{spec['title']}")

            existing_point_keys = {
                str((point.get("context") or {}).get("work_point_key") or point.get("title") or "")
                for point in task.get("development_points") or []
            }
            for point in spec["points"]:
                if point["key"] in existing_point_keys or point["title"] in existing_point_keys:
                    continue
                point_context = {
                    "work_point_key": point["key"],
                    "workstream_key": spec["key"],
                    "document_ids": point["document_ids"],
                    "course_unit_ids": point.get("course_unit_ids", []),
                    "iteration": 0,
                }
                created = project_manager.add_point(
                    str(task["id"]),
                    {
                        "title": point["title"],
                        "description": point["description"],
                        "status": "todo",
                        "weight": 1,
                        "assigned_agent": point["assigned_agent"],
                        "context": point_context,
                        "checklist": [
                            "读取绑定文档与来源上下文",
                            "完成工作并记录可验证证据",
                            "提交项目经理或质量负责人复核",
                        ],
                    },
                )
                if not created:
                    raise DocumentWorkspaceError(f"课程任务要点同步失败：{point['title']}")
            refreshed = project_manager.get_project(str(project["id"])) or project
            task = self._find_workstream_task(list(refreshed.get("tasks") or []), spec) or task
            resolved[spec["key"]] = task

        updated = project_manager.get_project(str(project["id"])) or project
        status = self.work_plan_status(updated, documents)
        return {
            "dry_run": False,
            "actions": actions,
            "summary": self._work_plan_action_summary(actions),
            "work_plan": status,
        }

    def _work_plan_action_summary(
        self, actions: list[dict[str, Any]]
    ) -> dict[str, int]:
        return {
            "total": len(actions),
            "create": sum(1 for row in actions if row["action"] == "create"),
            "update": sum(1 for row in actions if row["action"] == "update"),
            "points_added": sum(int(row["points_to_add"]) for row in actions),
        }

    def _course_missions(self, project_id: str) -> list[dict[str, Any]]:
        try:
            rows = self.command_service.list_missions(limit=500)
        except Exception:
            return []
        missions = []
        for mission in rows:
            context = mission.get("context") if isinstance(mission.get("context"), dict) else {}
            user_context = (
                context.get("user_context")
                if isinstance(context.get("user_context"), dict)
                else {}
            )
            if (
                str(mission.get("project_id") or "") == project_id
                and user_context.get("course_execution") is True
            ):
                missions.append(mission)
        return missions

    def _latest_runs_by_point(self, project_id: str) -> dict[str, dict[str, Any]]:
        try:
            runs = self.work_runs.list(project_id=project_id, limit=500)
        except Exception:
            return {}
        latest: dict[str, dict[str, Any]] = {}
        for run in runs:
            point_id = str(run.get("development_point_id") or "")
            if point_id and point_id not in latest:
                latest[point_id] = run
        return latest

    @staticmethod
    def _task_is_complete(task: dict[str, Any] | None) -> bool:
        if not task:
            return False
        points = list(task.get("development_points") or [])
        return str(task.get("status") or "") in {"done", "completed"} or (
            bool(points)
            and all(
                str(point.get("status") or "") in {"done", "completed"}
                for point in points
            )
        )

    def start_iteration(
        self,
        project: dict[str, Any],
        *,
        rounds: int = 1,
        parallelism: int = 3,
        requested_by: str = "project-manager",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        rounds = max(1, min(int(rounds), 10))
        parallelism = max(1, min(int(parallelism), 4))
        status = self.work_plan_status(project)
        if not status["summary"]["ready"]:
            raise DocumentWorkspaceError("课程任务结构尚未同步完整")

        eligible = [
            point
            for workstream in status["workstreams"]
            for point in workstream["point_items"]
            if point["eligible"]
        ]
        if not eligible:
            execution = status["execution"]
            if execution["review_points"]:
                raise DocumentWorkspaceError("当前没有可释放要点，请先处理待评审结果")
            if execution["active_points"] or execution["queued_points"]:
                raise DocumentWorkspaceError("当前迭代仍在执行或排队，请等待本批次结束")
            if execution["blocked_points"]:
                raise DocumentWorkspaceError("当前没有可释放要点，请先处理阻塞项")
            raise DocumentWorkspaceError("当前没有满足依赖条件的课程要点")

        selected = eligible[: rounds * parallelism]
        iteration_start = int(status["execution"]["current_iteration"] or 0) + 1
        steps = []
        previous_round_indexes: list[int] = []
        for offset, point in enumerate(selected):
            round_offset = offset // parallelism
            order_index = offset + 1
            if offset % parallelism == 0:
                previous_round_indexes = list(
                    range(
                        max(1, order_index - parallelism),
                        order_index,
                    )
                ) if round_offset else []
            iteration = iteration_start + round_offset
            acceptance = "；".join(point.get("acceptance_criteria") or [])
            checklist = "；".join(point.get("checklist") or [])
            steps.append(
                {
                    "order_index": order_index,
                    "title": point["title"],
                    "description": (
                        f"课程工作流：{point['task_title']}。"
                        f"{point.get('description') or ''}"
                        f" 验收标准：{acceptance or '按绑定任务验收'}。"
                        f" 执行检查：{checklist or '记录实际证据并提交评审'}。"
                    ),
                    "task_type": "writing",
                    "agent_id": point["assigned_agent"],
                    "executor": "openclaw",
                    "depends_on": previous_round_indexes,
                    "input": {
                        "course_execution": True,
                        "course_iteration": iteration,
                        "project_id": str(project["id"]),
                        "task_id": point["task_id"],
                        "task_title": point["task_title"],
                        "development_point_id": point["id"],
                        "workstream_key": point["workstream_key"],
                        "document_ids": point["document_ids"],
                        "course_unit_ids": point["course_unit_ids"],
                        "acceptance_criteria": point.get("acceptance_criteria") or [],
                        "checklist": point.get("checklist") or [],
                    },
                }
            )

        actual_rounds = max(1, math.ceil(len(selected) / parallelism))
        iteration_end = iteration_start + actual_rounds - 1
        preview = {
            "iteration_start": iteration_start,
            "iteration_end": iteration_end,
            "requested_rounds": rounds,
            "actual_rounds": actual_rounds,
            "parallelism": parallelism,
            "point_count": len(selected),
        }
        selected_points = [
            {
                "id": point["id"],
                "title": point["title"],
                "task_id": point["task_id"],
                "task_title": point["task_title"],
                "assigned_agent": point["assigned_agent"],
                "iteration": iteration_start + index // parallelism,
            }
            for index, point in enumerate(selected)
        ]
        if dry_run:
            return {
                "dry_run": True,
                "iteration": preview,
                "selected_points": selected_points,
                "plan": {"summary": f"{actual_rounds} 轮课程执行", "steps": steps},
            }

        plan = {
            "summary": (
                f"执行课程项目第 {iteration_start}"
                f"{f' 至 {iteration_end}' if iteration_end > iteration_start else ''} 轮，"
                f"共 {len(selected)} 个要点"
            ),
            "rationale": "仅释放任务依赖已完成且当前未运行的课程开发要点。",
            "risk_level": "medium",
            "steps": steps,
        }
        mission = self.command_service.create_preplanned_mission(
            objective=(
                f"推进“{project.get('name') or project['id']}”课程生产，"
                f"执行第 {iteration_start} 至 {iteration_end} 轮并提交可验证结果。"
            ),
            requested_by=requested_by,
            project_id=str(project["id"]),
            title=f"课程生产迭代 {iteration_start}-{iteration_end}",
            context={
                "course_execution": True,
                "course_iteration_start": iteration_start,
                "course_iteration_end": iteration_end,
                "selected_point_ids": [point["id"] for point in selected],
            },
            plan=plan,
            auto_approve=False,
        )
        try:
            for index, point in enumerate(selected):
                point_context = copy.deepcopy(point.get("context") or {})
                point_context.update(
                    {
                        "iteration": iteration_start + index // parallelism,
                        "mission_id": mission["id"],
                    }
                )
                updated = project_manager.update_point(
                    point["id"],
                    {"status": "ready", "context": point_context},
                )
                if not updated:
                    raise DocumentWorkspaceError(
                        f"无法将课程要点加入执行队列：{point['title']}"
                    )
            mission = self.command_service.approve(
                mission["id"],
                decided_by=requested_by,
                comment="项目经理面板已批准本轮课程执行",
            )
        except Exception:
            try:
                self.command_service.cancel(
                    mission["id"],
                    actor=requested_by,
                    comment="课程迭代入队失败，已撤销 mission",
                )
            except Exception:
                pass
            for point in selected:
                project_manager.update_point(point["id"], {"status": "todo"})
            raise

        refreshed = project_manager.get_project(str(project["id"])) or project
        return {
            "dry_run": False,
            "iteration": preview,
            "selected_points": selected_points,
            "mission": {
                "id": mission["id"],
                "status": mission["status"],
                "approval_status": mission.get("approval_status"),
            },
            "work_plan": self.work_plan_status(refreshed),
        }

    def review_point(
        self,
        project: dict[str, Any],
        point_id: str,
        *,
        decision: str,
        reviewer: str,
        comment: str = "",
    ) -> dict[str, Any]:
        refreshed = project_manager.get_project(str(project["id"])) or project
        found = next(
            (
                (task, point)
                for task in refreshed.get("tasks") or []
                for point in task.get("development_points") or []
                if str(point.get("id") or "") == point_id
            ),
            None,
        )
        if not found:
            raise DocumentWorkspaceError("课程开发要点不存在")
        _task, point = found
        point_status = str(point.get("status") or "")
        runs = self._latest_runs_by_point(str(project["id"]))
        run = runs.get(point_id)

        if decision == "approve":
            if point_status != "review":
                raise DocumentWorkspaceError("只有待评审要点可以通过")
            result = project_manager.complete_point(
                point_id,
                reviewer,
                comment or "项目经理评审通过",
                comment,
            )
            if run and run.get("status") == "review":
                run = self.work_runs.transition(
                    run["id"],
                    "completed",
                    actor=reviewer,
                    detail=comment or "课程要点评审通过",
                    result_summary=comment or run.get("result_summary") or "",
                )
        elif decision == "reject":
            if point_status != "review":
                raise DocumentWorkspaceError("只有待评审要点可以退回")
            result = project_manager.transition_point(
                point_id,
                "reject_review",
                reviewer,
                comment or "项目经理退回修改",
            )
            if run and run.get("status") == "review":
                run = self.work_runs.transition(
                    run["id"],
                    "blocked",
                    actor=reviewer,
                    detail=comment or "课程要点退回修改",
                )
        elif decision == "retry":
            if point_status != "blocked":
                raise DocumentWorkspaceError("只有阻塞要点可以重新排队")
            result = project_manager.transition_point(
                point_id,
                "retry",
                reviewer,
                comment or "项目经理允许重新执行",
            )
        else:
            raise DocumentWorkspaceError("未知评审决定")
        if not result:
            raise DocumentWorkspaceError("课程开发要点状态更新失败")

        updated = project_manager.get_project(str(project["id"])) or project
        return {
            "decision": decision,
            "point": result["point"] if isinstance(result, dict) and result.get("point") else result,
            "work_run": run,
            "work_plan": self.work_plan_status(updated),
        }

    def work_plan_status(
        self,
        project: dict[str, Any],
        documents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        documents = documents or multi_document_service.list_documents(project)["documents"]
        specs = self._workstream_specs(documents)
        tasks = list(project.get("tasks") or [])
        tasks_by_id = {
            str(task.get("id") or ""): task
            for task in tasks
            if task.get("id")
        }
        latest_runs = self._latest_runs_by_point(str(project["id"]))
        missions = self._course_missions(str(project["id"]))
        workstreams = []
        for spec in specs:
            task = self._find_workstream_task(tasks, spec)
            points = list((task or {}).get("development_points") or [])
            blocked_by = [
                str((tasks_by_id.get(str(task_id)) or {}).get("title") or task_id)
                for task_id in (task or {}).get("dependencies") or []
                if not self._task_is_complete(tasks_by_id.get(str(task_id)))
            ]
            dependency_ready = bool(task) and not blocked_by
            point_items = []
            for point in points:
                point_id = str(point.get("id") or "")
                run = latest_runs.get(point_id) or {}
                point_status = str(point.get("status") or "todo")
                context = point.get("context") if isinstance(point.get("context"), dict) else {}
                run_context = run.get("input_context") if isinstance(run.get("input_context"), dict) else {}
                point_iteration = int(
                    context.get("iteration")
                    or run_context.get("course_iteration")
                    or 0
                )
                if (
                    point_status == "todo"
                    and not context.get("mission_id")
                    and not run
                ):
                    point_iteration = 0
                point_items.append(
                    {
                        "id": point_id,
                        "title": str(point.get("title") or ""),
                        "description": str(point.get("description") or ""),
                        "task_id": str((task or {}).get("id") or ""),
                        "task_title": str((task or {}).get("title") or spec["title"]),
                        "workstream_key": spec["key"],
                        "status": point_status,
                        "assigned_agent": str(
                            point.get("assigned_agent")
                            or (task or {}).get("assignee_agent")
                            or spec["assignee_agent"]
                        ),
                        "document_ids": list(context.get("document_ids") or []),
                        "course_unit_ids": list(context.get("course_unit_ids") or []),
                        "acceptance_criteria": list(
                            (task or {}).get("acceptance_criteria") or []
                        ),
                        "checklist": list(point.get("checklist") or []),
                        "context": context,
                        "iteration": point_iteration,
                        "work_run_id": str(run.get("id") or ""),
                        "work_run_status": str(run.get("status") or ""),
                        "eligible": dependency_ready
                        and point_status == "todo"
                        and str(run.get("status") or "")
                        not in {"claimed", "running", "review", "verifying"},
                    }
                )
            done_points = sum(
                1
                for point in points
                if str(point.get("status") or "") in {"done", "completed"}
            )
            workstreams.append(
                {
                    "key": spec["key"],
                    "title": spec["title"],
                    "task_id": str((task or {}).get("id") or ""),
                    "assignee_agent": str((task or {}).get("assignee_agent") or spec["assignee_agent"]),
                    "status": str((task or {}).get("status") or "missing"),
                    "progress": float((task or {}).get("progress") or 0),
                    "document_ids": spec["document_ids"],
                    "points": len(points),
                    "completed_points": done_points,
                    "dependency_ready": dependency_ready,
                    "blocked_by": blocked_by,
                    "point_items": point_items,
                    "ready": bool(task) and len(points) >= len(spec["points"]),
                }
            )
        tracked = sum(1 for row in workstreams if row["task_id"])
        completed = sum(
            1
            for row in workstreams
            if row["status"] in {"done", "completed"}
        )
        total_points = sum(row["points"] for row in workstreams)
        completed_points = sum(row["completed_points"] for row in workstreams)
        all_points = [
            point
            for workstream in workstreams
            for point in workstream["point_items"]
        ]
        current_iteration = max(
            [
                int(
                    (
                        (mission.get("context") or {}).get("user_context") or {}
                    ).get("course_iteration_end")
                    or 0
                )
                for mission in missions
            ]
            + [int(point.get("iteration") or 0) for point in all_points]
            + [0]
        )
        return {
            "workstreams": workstreams,
            "summary": {
                "required": len(workstreams),
                "tracked": tracked,
                "completed": completed,
                "active": sum(
                    1
                    for row in workstreams
                    if row["status"] in {"in_progress", "review", "blocked"}
                ),
                "points": total_points,
                "completed_points": completed_points,
                "ready": tracked == len(workstreams)
                and all(row["ready"] for row in workstreams),
            },
            "execution": {
                "current_iteration": current_iteration,
                "eligible_points": sum(1 for point in all_points if point["eligible"]),
                "queued_points": sum(
                    1 for point in all_points if point["status"] == "ready"
                ),
                "active_points": sum(
                    1
                    for point in all_points
                    if point["status"] in {"in_progress", "running"}
                ),
                "review_points": sum(
                    1 for point in all_points if point["status"] == "review"
                ),
                "blocked_points": sum(
                    1 for point in all_points if point["status"] == "blocked"
                ),
                "completed_points": completed_points,
                "missions": [
                    {
                        "id": str(mission.get("id") or ""),
                        "title": str(mission.get("title") or ""),
                        "status": str(mission.get("status") or ""),
                        "approval_status": str(
                            mission.get("approval_status") or ""
                        ),
                        "iteration_start": int(
                            (
                                (mission.get("context") or {}).get("user_context")
                                or {}
                            ).get("course_iteration_start")
                            or 0
                        ),
                        "iteration_end": int(
                            (
                                (mission.get("context") or {}).get("user_context")
                                or {}
                            ).get("course_iteration_end")
                            or 0
                        ),
                        "updated_at": str(mission.get("updated_at") or ""),
                    }
                    for mission in missions[:20]
                ],
            },
        }

    def validate_source_refs(self, project: dict[str, Any], source_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relationship = project_manager.get_project_relationship_context(str(project["id"])) or {}
        related_ids = {
            str((row.get("counterpart") or {}).get("id") or "")
            for row in relationship.get("relations") or []
        }
        blockers = []
        for ref in source_refs:
            target_id = str(ref.get("project_id") or "")
            if target_id not in related_ids:
                blockers.append({"code": "source_project_unrelated", "message": f"来源项目未与课程关联：{target_id}", "source_ref": ref})
                continue
            target = project_manager.get_project(target_id)
            if not target:
                blockers.append({"code": "source_project_missing", "message": f"来源项目不存在：{target_id}", "source_ref": ref})
                continue
            if ref.get("ref_type") == "project_document":
                try:
                    document = multi_document_service.get_document(target, str(ref.get("document_id") or ""))
                except DocumentWorkspaceError:
                    document = None
                if not document or document.get("status") != "active":
                    blockers.append({"code": "source_document_missing", "message": f"来源文档不可用：{ref.get('document_id')}", "source_ref": ref})
                    continue
                expected_version = str(ref.get("version") or "").strip()
                if expected_version:
                    actual_version = "/".join(
                        value
                        for value in [
                            str(document.get("rules_version") or "").strip(),
                            str(document.get("data_version") or "").strip(),
                        ]
                        if value
                    )
                    if actual_version != expected_version:
                        blockers.append(
                            {
                                "code": "source_version_mismatch",
                                "message": (
                                    f"来源文档版本不一致：{ref.get('document_id')} "
                                    f"要求 {expected_version}，当前 {actual_version or '未标注'}"
                                ),
                                "source_ref": ref,
                            }
                        )
            elif ref.get("ref_type") == "project_product":
                product_ids = {
                    str(row.get("product_id") or "")
                    for row in target.get("product_bindings") or []
                    if str(row.get("status") or "bound") == "bound"
                }
                if str(ref.get("product_id") or "") not in product_ids:
                    blockers.append({"code": "source_product_missing", "message": f"来源产品未绑定：{ref.get('product_id')}", "source_ref": ref})
            else:
                blockers.append({"code": "source_ref_invalid", "message": "来源引用类型无效", "source_ref": ref})
        return blockers

    def production_status(self, project: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(project)
        baseline_blockers = self.validate_baseline(profile)
        documents = multi_document_service.list_documents(project)["documents"]
        products = []
        blockers = [dict(row, scope="baseline") for row in baseline_blockers]
        for product in _template_products():
            if not product["required_for_release"]:
                continue
            row = self._find_document(documents, product)
            item_blockers = []
            if not row:
                item_blockers.append({"code": "required_product_missing", "message": f"缺少正式产品：{product['title']}"})
                products.append({"key": product["key"], "title": product["title"], "document_id": "", "ready": False, "blockers": item_blockers})
                blockers.extend(dict(value, scope=product["key"]) for value in item_blockers)
                continue
            if row.get("publication_status") not in {"approved", "published"}:
                item_blockers.append({"code": "publication_not_approved", "message": "文档尚未批准或发布"})
            if row.get("kind") == "rich_text":
                quality = multi_document_service.rich_call(project, str(row["id"]), "quality")
                item_blockers.extend(
                    {"code": issue["type"], "message": issue["message"]}
                    for issue in quality["issues"]
                    if issue["severity"] == "blocker"
                )
            if row.get("kind") == "presentation":
                binding = row.get("structure_binding") or {}
                if int((row.get("stats") or {}).get("slide_count") or 0) <= 0:
                    item_blockers.append({"code": "presentation_content_missing", "message": "课件源文件尚未上传"})
                if binding.get("status") != "aligned":
                    item_blockers.append({"code": "structure_binding_not_aligned", "message": "课件结构绑定未对齐"})
            required_refs = [ref for ref in row.get("source_refs") or [] if ref.get("required", True)]
            if self._source_refs_for(product) and not required_refs:
                item_blockers.append({"code": "source_ref_missing", "message": "缺少必需的跨项目来源"})
            item_blockers.extend(self.validate_source_refs(project, required_refs))
            products.append(
                {
                    "key": product["key"],
                    "title": row["title"],
                    "document_id": row["id"],
                    "product_type": row.get("product_type"),
                    "publication_status": row.get("publication_status"),
                    "ready": not item_blockers,
                    "blockers": item_blockers,
                }
            )
            blockers.extend(dict(value, scope=product["key"]) for value in item_blockers)
        return {
            "course_profile": profile,
            "products": products,
            "blockers": blockers,
            "work_plan": self.work_plan_status(project, documents),
            "summary": {
                "required": len(products),
                "ready": sum(1 for row in products if row["ready"]),
                "blocked": sum(1 for row in products if not row["ready"]),
                "can_export": not blockers,
            },
        }

    def require_export_ready(self, project: dict[str, Any]) -> dict[str, Any]:
        status = self.production_status(project)
        if not status["summary"]["can_export"]:
            raise DocumentProductionBlocked("课程正式交付包尚未满足发布条件", status["blockers"])
        return status


course_production_service = CourseProductionService()
