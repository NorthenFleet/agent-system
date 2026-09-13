#!/usr/bin/env python3
"""Derive the 20-hour teaching schedule from course-plan revision 14."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = "proj-16ca49b862"
COURSE_PLAN_ID = "doc-e811bedd87f9"
SCHEDULE_ID = "doc-2a28da7429f0"
COURSE_PLAN_REVISION = 14
COURSE_PLAN_CONTENT_SHA256 = "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"
COURSE_PLAN_WORKING_SHA256 = "e681c44bff1f5be27b4a124b4601f7825cab5e6861258b6cf7c365c33d712114"
DOCUMENT_TITLE = "《水面舰艇作战软件与兵棋推演》教学进度表（20学时）"
CONTENT_VERSION = "course-schedule-derived-from-plan-r14-v1"
ACTOR = "course-schedule-plan-r14-migration"
PHASE_LABEL = "课程教学计划第二阶段：教学进度表派生定稿"

CHAPTER_TITLES = [
    "第一章 课程基线与派生关系",
    "第二章 10讲教学进度与成果链",
    "第三章 目标、评价与阶段关口",
    "第四章 运行字段与变更控制",
]

LESSON_ROWS = {
    "L01": "| 1 | L01 | 兵棋基础与《谋战》体系认识 | 理论2 | 课程计划、术语预习 | CO1 | 概念辨析、关系建模、来源登记 | 六要素关系图、能力进阶图、术语辨析卡、规则来源登记表 | 诊断，不计分 | L02行动链与裁决链 |",
    "L02": "| 2 | L02 | 水面舰艇编队战术、推演流程与裁决方法 | 理论2 | L01诊断成果、编队作战问题 | CO1 | 编队行动链、命令闭环与人工裁决流程分析 | 编队协同关系图、裁决流程卡、命令闭环卡、L03预习清单 | 诊断，不计分 | L03组件与规则查用 |",
    "L03": "| 3 | L03 | 《谋战》组件、地图、棋子与规则查用 | 实作2 | L02流程卡、《谋战》组件与R1.2/D1.2规则 | CO1、CO2 | 组件清点、版本确认、八类规则索引与组间复核 | 组件清点表、版本确认单、规则索引卡、组间复核意见 | 4分 | L04对象与规则基线 |",
    "L04": "| 4 | L04 | 单回合操作、态势标绘与裁决记录 | 实作2 | L03规则索引、标准事件 | CO1、CO2 | 完成命令、操作、人工裁决、状态更新和手工—软件字段核对 | 单回合事件记录、裁决表、状态变化表、手工—软件核对单、错误纠正单 | 4分 | L05标准事件字段 |",
    "L05": "| 5 | L05 | 作战想定理解、关键点识别与任务构建 | 实作2 | 课程登记想定、L04事件基线 | CO3 | 区分事实、未知、规则推断和指挥员假设，形成关键问题 | 想定要素表、事实—未知—推断—假设清单、关键问题矩阵、初始态势图 | 4分 | L06方案输入 |",
    "L06": "| 6 | L06 | 五人编组、编队部署与行动方案制定 | 实作2 | L05想定分析与关键问题 | CO3 | 明确席位责任，设计阶段、触发、授权、预期效果和备用行动 | 席位卡、责任矩阵、部署图、行动方案卡、命令日志、纸面—软件差异清单 | 4分 | L07专项行动方案 |",
    "L07": "| 7 | L07 | 侦察预警、电子战与指挥协同专项推演 | 实作2 | L06行动方案、侦察与电磁状态资料 | CO4 | 组织航迹、电磁、电子战和命令协同，检查信息连续性 | 航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘 | 8分 | L08有效航迹与支援状态 |",
    "L08": "| 8 | L08 | 制空支援、对海打击与防空反导专项推演 | 实作2 | L07有效航迹、威胁与火力资源 | CO4 | 完成威胁排序、火力分配、发射裁决和资源持续性检查 | 威胁排序表、火力分配表、发射裁决记录、资源状态表、差异单、专项复盘 | 8分 | L09综合能力输入 |",
    "L09": "| 9 | L09 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 实作2 | L05—L08合格成果、完整想定 | CO4、CO5 | 完成综合对抗、关键事件回放、差异分析和方案修订 | 综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案 | 8分 | L10个人证据目录 |",
    "L10": "| 10 | L10 | 综合考核：想定分析、对抗推演与复盘答辩 | 考核2 | 冻结想定、统一规则数据、统一量规、个人证据目录 | CO1—CO5 | 独立研判、履职推演、证据定位、复盘答辩和人工复核 | 综合考核证据包、个人贡献单、复盘答辩和评分记录 | 原始100分×60% | 课程人工复核与归档 |",
}


SCHEDULE = r'''---
title: "《水面舰艇作战软件与兵棋推演》教学进度表（20学时）"
status: "draft"
content_version: "course-schedule-derived-from-plan-r14-v1"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
document_role: "course_schedule_projection"
parent_document_id: "doc-e811bedd87f9"
parent_revision: 14
parent_content_sha256: "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"
---

# 《水面舰艇作战软件与兵棋推演》教学进度表（20学时）

> 本进度表由《水面舰艇作战软件与兵棋推演》课程教学计划修订14派生，是10次课的实施投影，不另行改变课程目标、总学时、规则数据版本、成绩结构和合格门槛。实际开课日期、班次、场地和人员以教务排课及审批结果为准。

# 第一章 课程基线与派生关系

## 一、基本信息

| 项目 | 内容 |
| --- | --- |
| 课程名称 | 水面舰艇作战软件与兵棋推演 |
| 课程编号 | YJZT503 |
| 课程性质 | 选修课 |
| 适用层次与专业 | 本科，军兵种作战指挥专业 |
| 总学时与课次 | 20学时，10次课，每次2学时 |
| 学时构成 | 理论4学时、实作14学时、综合考核2学时 |
| 课程计划权威 | doc-e811bedd87f9，修订14 |
| 规则与数据 | R1.2/D1.2规则；课程登记的R1.1/D1.1裁决与算子数据 |
| 软件环境 | One-Sim仿真平台、AI Planning智能筹划系统 |
| 当前状态 | 工作草稿，审批前不得作为正式发布件 |

## 二、派生边界

1. 教学计划拥有课程目标、课程内容、学时、考核和保障条件的权威；本进度表只把这些要求展开为L01—L10的顺序、输入、活动、成果、评价和移交。
2. 下位教案必须按本表的讲次编号和必交成果细化课堂流程，不得自行改变20学时、10次课、规则数据版本、40分过程性实作和60分综合考核结构。
3. 学期日期、班次、场地、人员、器材和软件账号属于运行字段，未确认前保持待定，不写成既定事实。
4. 教学计划修订后，本进度表应显示父文档已更新并进入复核；未完成重新派生前不得继续向10讲教案扩散变更。

# 第二章 10讲教学进度与成果链

## 一、唯一讲次矩阵

下表是L01—L10的唯一课程级映射。各教案可以扩展时间脚本、教学方法和现场表单，但不得另建与本表冲突的课次名称、必交成果或计分口径。

| 序号 | 讲次 | 教学专题 | 类别/学时 | 课前输入 | 对应目标 | 核心活动 | 必交成果 | 评价 | 移交下一讲 |
| ---: | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| 1 | L01 | 兵棋基础与《谋战》体系认识 | 理论2 | 课程计划、术语预习 | CO1 | 概念辨析、关系建模、来源登记 | 六要素关系图、能力进阶图、术语辨析卡、规则来源登记表 | 诊断，不计分 | L02行动链与裁决链 |
| 2 | L02 | 水面舰艇编队战术、推演流程与裁决方法 | 理论2 | L01诊断成果、编队作战问题 | CO1 | 编队行动链、命令闭环与人工裁决流程分析 | 编队协同关系图、裁决流程卡、命令闭环卡、L03预习清单 | 诊断，不计分 | L03组件与规则查用 |
| 3 | L03 | 《谋战》组件、地图、棋子与规则查用 | 实作2 | L02流程卡、《谋战》组件与R1.2/D1.2规则 | CO1、CO2 | 组件清点、版本确认、八类规则索引与组间复核 | 组件清点表、版本确认单、规则索引卡、组间复核意见 | 4分 | L04对象与规则基线 |
| 4 | L04 | 单回合操作、态势标绘与裁决记录 | 实作2 | L03规则索引、标准事件 | CO1、CO2 | 完成命令、操作、人工裁决、状态更新和手工—软件字段核对 | 单回合事件记录、裁决表、状态变化表、手工—软件核对单、错误纠正单 | 4分 | L05标准事件字段 |
| 5 | L05 | 作战想定理解、关键点识别与任务构建 | 实作2 | 课程登记想定、L04事件基线 | CO3 | 区分事实、未知、规则推断和指挥员假设，形成关键问题 | 想定要素表、事实—未知—推断—假设清单、关键问题矩阵、初始态势图 | 4分 | L06方案输入 |
| 6 | L06 | 五人编组、编队部署与行动方案制定 | 实作2 | L05想定分析与关键问题 | CO3 | 明确席位责任，设计阶段、触发、授权、预期效果和备用行动 | 席位卡、责任矩阵、部署图、行动方案卡、命令日志、纸面—软件差异清单 | 4分 | L07专项行动方案 |
| 7 | L07 | 侦察预警、电子战与指挥协同专项推演 | 实作2 | L06行动方案、侦察与电磁状态资料 | CO4 | 组织航迹、电磁、电子战和命令协同，检查信息连续性 | 航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘 | 8分 | L08有效航迹与支援状态 |
| 8 | L08 | 制空支援、对海打击与防空反导专项推演 | 实作2 | L07有效航迹、威胁与火力资源 | CO4 | 完成威胁排序、火力分配、发射裁决和资源持续性检查 | 威胁排序表、火力分配表、发射裁决记录、资源状态表、差异单、专项复盘 | 8分 | L09综合能力输入 |
| 9 | L09 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 实作2 | L05—L08合格成果、完整想定 | CO4、CO5 | 完成综合对抗、关键事件回放、差异分析和方案修订 | 综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案 | 8分 | L10个人证据目录 |
| 10 | L10 | 综合考核：想定分析、对抗推演与复盘答辩 | 考核2 | 冻结想定、统一规则数据、统一量规、个人证据目录 | CO1—CO5 | 独立研判、履职推演、证据定位、复盘答辩和人工复核 | 综合考核证据包、个人贡献单、复盘答辩和评分记录 | 原始100分×60% | 课程人工复核与归档 |
|  | 合计 | 10次课 | 理论4、实作14、考核2 |  | CO1—CO5 | 理论认知—规则操作—想定方案—专项综合—考核复盘 | 形成可追溯课程证据链 | 100分 | 课程改进清单 |

## 二、实施递进

1. L01—L02建立概念、行动链、命令链和裁决链，不安排正式软件操作。
2. L03完成组件和规则查用，L04开始以统一事件编号连接手工记录与软件字段。
3. L05—L06完成想定分析、五人编组、编队部署和行动方案，形成进入专项推演的完整输入。
4. L07—L08分别训练侦察电子战协同和火力防护协同，保留手工记录、软件记录和差异说明。
5. L09完成跨域综合对抗与第二版方案，L10在冻结条件下完成综合考核和人工复核。

# 第三章 目标、评价与阶段关口

## 一、课程目标映射

| 目标 | 主要课次 | 主要达成证据 | 基本判据 |
| --- | --- | --- | --- |
| CO1 体系与规则认知 | L01—L04、L10 | 术语卡、来源登记、规则索引、裁决流程、答辩定位 | 概念关系正确，能够说明规则版本、对象和适用条件 |
| CO2 基础操作 | L03—L04、L10 | 组件清单、事件记录、裁决表、状态变化表 | 动作合法，地图、日志、裁决和状态相互一致 |
| CO3 想定与方案 | L05—L06、L10 | 想定要素表、信息分类、部署图、方案卡、命令日志 | 任务、阶段、触发、责任、授权和备用行动完整 |
| CO4 战术协同 | L07—L09、L10 | 航迹表、电磁日志、火力表、综合日志、个人贡献单 | 行动合法，能够说明行动对任务和后续阶段的贡献 |
| CO5 证据化复盘 | L09—L10 | 时间线、差异清单、第二版方案、证据目录、答辩记录 | 能定位证据、解释偏差并提出可验证的改进 |

## 二、成绩结构与合格门槛

| 组成 | 课次 | 分值 | 评价依据 |
| --- | --- | ---: | --- |
| 诊断评价 | L01—L02 | 不计分 | 概念、行动链、命令链和裁决链的诊断成果 |
| 基础实作 | L03—L06 | 16分，每讲4分 | 规则查用、基础操作、想定分析和方案形成 |
| 专项与综合实作 | L07—L09 | 24分，每讲8分 | 侦察电子战、火力防护、综合对抗和软件复盘 |
| 综合考核 | L10 | 原始100分乘以60% | 想定分析、方案、推演履职、证据质量和复盘答辩 |
| 合计 | L03—L10 | 100分 | 过程性实作40分、综合考核60分 |

过程性实作成绩不低于24分，且L10综合考核原始成绩不低于60分，方可判定课程合格。软件只提供记录、回放、核对和辅助分析，不自动生成成绩。

## 三、阶段质量关口

| 关口 | 准入检查 | 未达标处置 |
| --- | --- | --- |
| L02结束 | 概念、行动链、命令链和裁决链达到实作最低要求 | 完成针对性概念与流程补练 |
| L04结束 | 组件查用、单回合操作、裁决和事件记录能够相互核对 | 回溯标准事件并重做一致性检查 |
| L06结束 | 想定分析、席位责任、部署和行动方案闭合 | 完成限时口令演练并修订方案 |
| L08结束 | 侦察电子战、火力防护和软件核对形成证据闭环 | 针对中断环节组织专项补练 |
| L09结束 | 综合证据包、差异说明和第二版方案满足考核准备要求 | 补齐缺项后方可进入L10 |
| L10结束 | 成绩、证据目录、人工复核和课程改进清单完整 | 按考核规定复核，不临时补造证据 |

# 第四章 运行字段与变更控制

## 一、本学期运行字段

| 字段 | 当前值 | 确认责任 |
| --- | --- | --- |
| 学期、起止周和日期节次 | 待教务排课确认 | 课程负责人 |
| 班次、人数和分组 | 待学员名单确认 | 任课教员 |
| 理论教室与推演场地 | 待场地确认 | 教学保障人员 |
| 任课教员、导演、裁决与评分人员 | 待课程组确认 | 课程负责人 |
| 《谋战》器材套数与备用件 | 待开课前清点 | 规则与器材管理员 |
| One-Sim与AI Planning版本、账号和网络 | L04前完成现场确认 | 软件保障人员 |
| 成果提交与归档位置 | 待课程组确认 | 记录与证据人员 |

## 二、开课运行时点

| 时点 | 必须完成的事项 | 形成证据 |
| --- | --- | --- |
| 开课前7日 | 确认排课、名单、场地、规则数据、器材和软件资源 | 课程运行目录、问题清单 |
| 每次课前1日 | 冻结本讲教案、任务、材料、停止条件和备用流程 | 本讲运行包、证据编号范围 |
| 上课前30分钟 | 校验器材、规则版本、软件环境、分组和导出路径 | 现场检查表、异常登记 |
| 下课前5分钟 | 完成讲评、准入判定、成果提交和原始材料封存 | 成果目录、缺项单、移交记录 |
| 课后1日内 | 完成反馈、补练通知、差异说明和归档 | 反馈记录、追加说明、下一讲输入包 |

## 三、软件与证据边界

1. 《谋战》手工兵棋是规则查用、操作实施和人工裁决的原始依据；One-Sim仿真平台用于想定与状态表达、事件记录、过程回放和统计核对；AI Planning智能筹划系统用于方案结构化表达、约束检查、方案比较和复盘辅助。
2. 软件不得补造想定信息，不得推算规则未定义参数，不得泄露隐藏态势，不得覆盖手工原始记录和人工裁决，不得直接生成课程成绩。
3. 软件不可用时以手工事件编号、态势图和裁决日志继续课堂核心任务；课后只允许补录和追加差异说明，不改写既有裁决。
4. 规则争议、版本不一致、隐藏信息越权、关键证据丢失或器材关键缺项时冻结事件，登记恢复点并由人工决定处置。

## 四、向10讲教案的移交规则

1. 每份教案必须采用L01—L10正式讲次名称，并保留本表对应的课前输入、课程目标、必交成果、评价方式和下一讲移交。
2. 教案可细化为八章结构，增加学情分析、教学重点难点、时间脚本、教学活动、板书课件、表单和课后反思，但不得用通用占位内容替代本讲任务。
3. 教案引用具体规则、数据、想定和软件字段时必须标明来源与版本；没有依据的参数、战例结论和软件能力不得写入正式要求。
4. 先完成每讲基线核对，再逐讲修订和审批；不得一次性用同一模板覆盖10讲的差异化内容。

## 五、变更控制

课程名称、总学时、10讲结构、课程目标、规则数据版本、成绩结构和合格门槛发生变化时，先修订教学计划，再重新派生本进度表，最后评估L01—L10教案影响。措辞和现场组织调整可以在教案层处理，但不得悄然改变课程级基线。所有下位修订保持草稿，直至完成课程负责人审核和正式发布审批。
'''


def _working_path(project: dict[str, Any], document_id: str) -> Path:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    path = Path(str(manifest.get("working_markdown") or ""))
    if not path.is_file():
        raise RuntimeError(f"工作稿不存在：{path}")
    return path


def _current_markdown(project: dict[str, Any], document_id: str) -> str:
    return _working_path(project, document_id).read_text(encoding="utf-8")


def _state(project: dict[str, Any], document_id: str) -> dict[str, Any]:
    return writing_collaboration_service.get_state(project, document_id)


def _validate_parent(project: dict[str, Any]) -> dict[str, Any]:
    state = _state(project, COURSE_PLAN_ID)
    revision = int(state.get("document_revision") or 0)
    content_sha = writing_collaboration_service.codec.document_sha256(state["document"])
    working_path = _working_path(project, COURSE_PLAN_ID)
    working_sha = hashlib.sha256(working_path.read_bytes()).hexdigest()
    evidence = {
        "document_id": COURSE_PLAN_ID,
        "revision": revision,
        "content_sha256": content_sha,
        "working_markdown": str(working_path),
        "working_sha256": working_sha,
        "projection_revision": (state.get("projection") or {}).get("revision"),
        "projection_status": (state.get("projection") or {}).get("status"),
        "approved_revision": state.get("approved_revision"),
        "published_revision": state.get("published_revision"),
    }
    if revision != COURSE_PLAN_REVISION or content_sha != COURSE_PLAN_CONTENT_SHA256:
        raise RuntimeError(f"教学计划权威已变化，停止派生：{evidence}")
    if working_sha != COURSE_PLAN_WORKING_SHA256:
        raise RuntimeError(f"教学计划投影哈希已变化，停止派生：{evidence}")
    if evidence["projection_revision"] != COURSE_PLAN_REVISION or evidence["projection_status"] != "current":
        raise RuntimeError(f"教学计划投影不是当前修订，停止派生：{evidence}")
    return evidence


def _lineage(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": "surface-wargame-course-plan-projections",
        "edition_label": "course-plan-r14",
        "sequence": 1,
        "source_type": "structured_authority",
        "parent_document_id": COURSE_PLAN_ID,
        "source_checksum": parent["content_sha256"],
        "generated_at": "2026-08-23T06:52:52.908473+00:00",
        "source_paths": [parent["working_markdown"]],
    }


def _structure_metadata(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "openclaw.course-schedule-structure.v1",
        "content_version": CONTENT_VERSION,
        "parent_document_id": COURSE_PLAN_ID,
        "parent_revision": parent["revision"],
        "parent_content_sha256": parent["content_sha256"],
        "parent_working_sha256": parent["working_sha256"],
        "chapter_count": 4,
        "chapter_titles": CHAPTER_TITLES,
        "course_name": "水面舰艇作战软件与兵棋推演",
        "lesson_count": 10,
        "total_hours": 20,
        "theory_hours": 4,
        "practice_hours": 14,
        "assessment_hours": 2,
        "process_score": 40,
        "final_score": 60,
    }


def _checks(markdown: str) -> dict[str, Any]:
    top_level = [line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")]
    chapters = [title for title in top_level if title in CHAPTER_TITLES]
    exact_rows = {
        lesson: sum(1 for line in markdown.splitlines() if line == row)
        for lesson, row in LESSON_ROWS.items()
    }
    banned = [
        "共10学时",
        "合计16学时",
        "理论10＋实作10",
        "第11讲",
        "兵棋推演与智能决策",
        "水面舰艇指挥决策与兵棋推演",
        "0522公开想定",
        "软件不自动评分",
    ]
    return {
        "content_version": CONTENT_VERSION in markdown,
        "document_title": DOCUMENT_TITLE in markdown,
        "parent_id": COURSE_PLAN_ID in markdown,
        "parent_revision": "parent_revision: 14" in markdown and "教学计划修订14" in markdown,
        "parent_sha256": COURSE_PLAN_CONTENT_SHA256 in markdown,
        "chapter_count": len(chapters),
        "chapter_order": chapters,
        "chapter_order_valid": chapters == CHAPTER_TITLES,
        "lesson_row_counts": exact_rows,
        "lesson_rows_unique": all(count == 1 for count in exact_rows.values()),
        "hours_valid": all(token in markdown for token in ["理论4学时", "实作14学时", "综合考核2学时"]),
        "score_valid": all(token in markdown for token in ["过程性实作40分", "综合考核60分", "不低于24分", "不低于60分"]),
        "authority_valid": all(token in markdown for token in ["R1.2/D1.2", "R1.1/D1.1", "One-Sim仿真平台", "AI Planning智能筹划系统"]),
        "handoff_valid": all(token in markdown for token in ["课前输入", "必交成果", "移交下一讲", "向10讲教案的移交规则"]),
        "banned_hits": [token for token in banned if token in markdown],
    }


def _checks_pass(checks: dict[str, Any]) -> bool:
    return all(
        [
            checks["content_version"],
            checks["document_title"],
            checks["parent_id"],
            checks["parent_revision"],
            checks["parent_sha256"],
            checks["chapter_count"] == 4,
            checks["chapter_order_valid"],
            checks["lesson_rows_unique"],
            checks["hours_valid"],
            checks["score_valid"],
            checks["authority_valid"],
            checks["handoff_valid"],
            not checks["banned_hits"],
        ]
    )


def _binding_is_current(binding: dict[str, Any]) -> bool:
    return all(
        [
            binding.get("mode") == "derived",
            binding.get("source_document_id") == COURSE_PLAN_ID,
            binding.get("referenced_document_revision") == f"v{COURSE_PLAN_REVISION}",
            binding.get("referenced_document_sha256") == COURSE_PLAN_WORKING_SHA256,
            binding.get("reference_status") == "current",
            binding.get("status") == "aligned",
            binding.get("integrity_status") == "aligned",
            not binding.get("unmapped_items"),
            not binding.get("changed_sections"),
        ]
    )


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{project_id}")
    parent = _validate_parent(project)
    before = _current_markdown(project, SCHEDULE_ID)
    before_state = _state(project, SCHEDULE_ID)
    before_document = multi_document_service.get_document(project, SCHEDULE_ID)
    before_binding = multi_document_service.structure_binding(project, SCHEDULE_ID)
    target = SCHEDULE.strip() + "\n"
    checks = _checks(target)
    if not _checks_pass(checks):
        raise RuntimeError(f"目标进度表自检未通过：{checks}")

    lineage = _lineage(parent)
    structure_metadata = _structure_metadata(parent)
    metadata = before_document.get("metadata") or {}
    content_changed = before != target
    catalog_changed = any(
        [
            before_document.get("title") != DOCUMENT_TITLE,
            int(before_document.get("expected_chapters") or 0) != 4,
            before_document.get("rules_version") != "R1.2",
            before_document.get("data_version") != "course-baseline-20h-v4",
            before_document.get("publication_status") != "draft",
            before_document.get("lineage") != lineage,
        ]
    )
    metadata_changed = metadata.get("course_schedule_structure") != structure_metadata or metadata.get("last_actor") != ACTOR
    binding_changed = not _binding_is_current(before_binding)
    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "document_id": SCHEDULE_ID,
        "parent": parent,
        "before_revision": before_state.get("document_revision"),
        "before_content_sha256": writing_collaboration_service.codec.document_sha256(before_state["document"]),
        "before_chars": len(before),
        "after_chars": len(target),
        "content_changed": content_changed,
        "catalog_changed": catalog_changed,
        "metadata_changed": metadata_changed,
        "binding_changed": binding_changed,
        "before_binding": before_binding,
        "checks": checks,
    }
    if dry_run or not (content_changed or catalog_changed or metadata_changed or binding_changed):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if content_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            SCHEDULE_ID,
            target,
            label=PHASE_LABEL,
            actor=ACTOR,
        )
        project = project_manager.get_project(project_id) or project

    _validate_parent(project)
    multi_document_service.update_document(
        project,
        SCHEDULE_ID,
        {
            "title": DOCUMENT_TITLE,
            "expected_chapters": 4,
            "rules_version": "R1.2",
            "data_version": "course-baseline-20h-v4",
            "publication_status": "draft",
            "lineage": lineage,
        },
    )
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(
        project,
        SCHEDULE_ID,
        {
            "last_actor": ACTOR,
            "course_schedule_structure": structure_metadata,
        },
    )
    project = project_manager.get_project(project_id) or project
    after_binding = multi_document_service.set_structure_binding(
        project,
        SCHEDULE_ID,
        {
            "mode": "derived",
            "source_document_id": COURSE_PLAN_ID,
            "status": "aligned",
            "integrity_status": "aligned",
            "reference_status": "current",
            "mapped_items": 10,
            "unmapped_items": [],
            "changed_sections": [],
        },
    )

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "course_schedule_status": "derived_from_course_plan_r14_ready_for_review",
            "next_step": "只读核对L01—L10教案与本进度表的输入、目标、成果、评价和移交差异，再确定逐讲修订顺序。",
        }
    )
    project_manager.update_project(
        project_id,
        {"context": context, "current_phase": "course_schedule_from_plan_r14"},
    )

    refreshed = project_manager.get_project(project_id) or project
    document_workspace_service.ensure_workspace(
        multi_document_service.rich_project_context(refreshed, SCHEDULE_ID)
    )
    after = _current_markdown(refreshed, SCHEDULE_ID)
    after_state = _state(refreshed, SCHEDULE_ID)
    after_document = multi_document_service.get_document(refreshed, SCHEDULE_ID)
    final_binding = multi_document_service.structure_binding(refreshed, SCHEDULE_ID)
    after_checks = _checks(after)
    if not _checks_pass(after_checks):
        raise RuntimeError(f"写入后内容自检未通过：{after_checks}")
    if not _binding_is_current(final_binding):
        raise RuntimeError(f"写入后结构绑定未对齐：{final_binding}")
    if after_document.get("lineage") != lineage:
        raise RuntimeError(f"写入后lineage不一致：{after_document.get('lineage')}")

    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "after_revision": after_state.get("document_revision"),
        "after_content_sha256": writing_collaboration_service.codec.document_sha256(after_state["document"]),
        "projection_revision": (after_state.get("projection") or {}).get("revision"),
        "projection_status": (after_state.get("projection") or {}).get("status"),
        "approved_revision": after_state.get("approved_revision"),
        "published_revision": after_state.get("published_revision"),
        "catalog_title": after_document.get("title"),
        "expected_chapters": after_document.get("expected_chapters"),
        "publication_status": after_document.get("publication_status"),
        "lineage": after_document.get("lineage"),
        "binding": final_binding,
        "binding_write_result": after_binding,
        "checks": after_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
