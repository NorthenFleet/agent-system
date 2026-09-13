#!/usr/bin/env python3
"""Upgrade L07-L10, the advanced-practice templates, and assessment package."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.course_production_service import COURSE_PROJECT_ID  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PHASE_LABEL = "课程开学准备第三阶段C：专项实作与综合考核深化"
CONTENT_VERSION = "surface-course-assessment-ready-v1"
PRACTICE_GUIDE_ID = "doc-e6071aa369ed"
ASSESSMENT_ID = "doc-f7ff5f8fe4f2"


LESSONS: dict[str, dict[str, Any]] = {
    "doc-60e4858f35af": {
        "unit": "L07",
        "number": 7,
        "title": "侦察预警、电子战与指挥协同专项推演",
        "position": "第5次实作课",
        "mission": "建立贯穿任务全过程的侦察、航迹、电子战、电磁管控和指挥协同闭环。",
        "objectives": [
            "依据任务和风险设计侦察方向、平台、时机、情报回传和替补方案。",
            "按当前规则核验探测、共享航迹、电子战作用和电磁状态，不把软件显示直接当作裁决。",
            "通过命令、复诵、状态回报和授权转换协调侦察、干扰、防护与主要任务。",
        ],
        "outputs": "侦察电子战行动表、航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘",
        "focus": "持续侦察、航迹质量、电子战有效条件、电磁暴露代价和指挥闭环。",
        "difficulty": "在获取信息、保持共享航迹、降低暴露和保存关键平台之间作出可解释取舍。",
        "teacher_prep": "准备冻结的公开态势、侦察与干扰事件包、电磁状态卡、航迹连续性模板、授权冲突脚本和软件登记环境。",
        "student_prep": "携带L06通过评审的行动方案、席位卡和规则索引，完成侦察重点方向与关键情报需求预判。",
        "key_questions": [
            "侦察计划怎样证明其服务主要任务，而不是单纯扩大可见范围？",
            "主动探测、共享航迹、电子战和电磁静默之间有哪些互相制约条件？",
            "队长在何种条件下授权前出、改变干扰位置或启用替补侦察节点？",
        ],
        "rows": [
            ("0—10分钟", "任务发布与状态冻结", "发布情报需求、评分点和停止条件，核对规则与软件版本", "签收事件包，冻结初态、席位和电磁状态", "版本冻结单；不一致不得开始"),
            ("10—25分钟", "规则定位与协同检查", "组织定位探测、共享、干扰和电磁管控条目", "填写条件清单并完成命令回路试通", "条件不明或授权冲突先纠正"),
            ("25—40分钟", "对比示范", "示范两种侦察位置和两种电磁状态下的证据记录", "记录可见信息、暴露代价、共享资格和任务影响", "示范记录不得直接套用未核验参数"),
            ("40—55分钟", "侦察电子战计划", "审查重点方向、替补节点、干扰位置和转换条件", "形成阶段计划、责任席位和状态回报要求", "每项行动必须关联关键情报需求"),
            ("55—90分钟", "专项连续推演", "按阶段释放航迹中断、干扰失效和授权冲突事件", "执行侦察、干扰、电磁管控、命令和状态维护", "出现证据断链、越权或规则争议立即暂停"),
            ("90—105分钟", "软件登记与连续性核对", "组织按事件编号核对手工航迹和软件状态", "填写差异单并恢复不少于一条中断航迹", "保留原记录，禁止静默覆盖"),
            ("105—115分钟", "专项复盘", "围绕信息收益、暴露代价和协同延迟追问", "完成一项有效决策和一项失效决策的因果分析", "复盘必须引用事件和规则证据"),
            ("115—120分钟", "8分评分与归档", "按量规登记分值、事件编号和补练要求", "提交成果包与个人贡献记录", "证据完整方可进入L08"),
        ],
        "score": [
            ("侦察与航迹连续性", "2.0", "情报需求、来源、时间、质量和替补方案完整"),
            ("电子战与电磁管控", "2.0", "作用条件、状态转换和规则适用正确"),
            ("指挥协同与任务贡献", "2.0", "授权、复诵、回报闭环并服务主要任务"),
            ("证据一致与复盘", "2.0", "手工软件可互证，差异和改进能够定位"),
        ],
        "software": "登记航迹来源、时间戳、质量、电磁状态、干扰位置、共享资格和命令状态；软件用于时间线核对和异常定位，不生成隐藏信息或裁决结论。",
        "homework": "根据评分反馈修订侦察电子战计划，写明触发条件、替补节点、暴露风险和将在L08保留的支援能力。",
        "legacy": "保留持续侦察、电子战支援位置、雷达静默和可控暴露的战术思想；平台性能、干扰等级和探测次数必须经核验后才能引用。",
        "max_score": "8.0",
        "score_statement": "本讲计入课程总评的专项实作8分，不再使用百分比观察框架二次折算。",
    },
    "doc-8248d6366ec3": {
        "unit": "L08",
        "number": 8,
        "title": "制空支援、对海打击与防空反导专项推演",
        "position": "第6次实作课",
        "mission": "在有限航迹、通道、弹药和支援条件下形成合法、分层、可持续的火力闭环。",
        "objectives": [
            "依据主要任务、威胁优先级和任务贡献制定对海打击与防空反导火力计划。",
            "逐事件完成发射合法性、修正、随机裁决、通道占用、在途武器和弹药状态更新。",
            "通过波次控制、目标分配和能力储备避免重复开火与后续防御失能。",
        ],
        "outputs": "威胁排序表、火力分配表、发射拦截记录、通道弹药状态表、手工—软件一致性报告、专项复盘",
        "focus": "目标优先、合法发射、分层拦截、火力协同和持续作战能力。",
        "difficulty": "多方向连续来袭时兼顾当前拦截、主要任务贡献和后续通道弹药储备。",
        "teacher_prep": "准备多方向来袭序列、不同质量航迹、三层防御资源卡、发射裁决表、通道弹药模板和软件核对环境。",
        "student_prep": "带齐L07合格的航迹与电子战状态表，复核武器适用、射程射界、通道、弹药、干扰和安全限制。",
        "key_questions": [
            "最大射程、合法发射、基础概率和最终裁决为什么必须分别记录？",
            "同一目标进入下一防御层时，哪些信息和资源条件必须重新核验？",
            "何时应保留弹药或通道，而不是继续追求当前单一目标的最高拦截概率？",
        ],
        "rows": [
            ("0—10分钟", "任务发布与资源冻结", "发布护航任务、来袭方向和停止条件，冻结航迹与资源", "核对L07输入，登记初始通道、弹药和在途状态", "初态不一致不得开始"),
            ("10—25分钟", "合法性与裁决链复核", "组织定位武器适用、射程射界、修正和通道规则", "完成发射前检查清单和字段映射", "缺少规则依据不得列入计划"),
            ("25—40分钟", "分层拦截示范", "演示威胁排序、单层发射、状态更新与下层再评估", "逐字段记录命令、裁决、在途、释放和余量", "示范强调不重复计算和不越序"),
            ("40—55分钟", "火力计划与能力储备", "审查目标分配、波次、支援关系和保留量", "形成火力分配表和备用处置条件", "每次发射说明任务贡献与机会成本"),
            ("55—90分钟", "多方向连续推演", "按10秒事件释放威胁和航迹变化", "执行命令、发射、裁决、状态维护和分层再评估", "非法发射、资源负数或证据断链立即暂停"),
            ("90—105分钟", "状态与软件核对", "组织核对不少于五个关键火力事件", "比对通道、弹药、在途武器和结果，形成差异说明", "不得用软件结果覆盖手工裁决"),
            ("105—115分钟", "专项复盘", "围绕重复开火、过早发射和能力耗尽讲评", "完成一项火力决策的反事实重算", "保留原方案、实际结果和改进方案"),
            ("115—120分钟", "8分评分与归档", "登记分值、关键证据和L09准入结论", "提交成果包与个人贡献记录", "资源状态可复核方可归档"),
        ],
        "score": [
            ("威胁排序与火力计划", "2.0", "目标优先、波次和支援关系服务主要任务"),
            ("规则操作与裁决", "2.0", "合法性、修正、随机结果和通道释放正确"),
            ("资源持续与临机处置", "2.0", "弹药通道状态准确并保留后续能力"),
            ("证据一致与复盘", "2.0", "关键火力事件可互证并提出可验证改进"),
        ],
        "software": "按事件编号登记航迹、发射平台、武器目标、修正、随机结果、通道、弹药和在途状态；软件用于一致性核对，不替代发射合法性判断与人工裁决。",
        "homework": "完成一项关键火力决策的资源敏感性分析，说明目标排序、发射时机或保留量改变后的任务影响。",
        "legacy": "保留局部火力优势、电子战支援、有效交战时机和弹药管理的思路；通用挂载与不可逃逸区示例不得代替0522算子与规则。",
        "max_score": "8.0",
        "score_statement": "本讲计入课程总评的专项实作8分，不再使用百分比观察框架二次折算。",
    },
    "doc-729fe58abb5a": {
        "unit": "L09",
        "number": 9,
        "title": "关键点争夺、跨域综合对抗与软件辅助复盘",
        "position": "第7次实作课",
        "mission": "综合前序能力完成考核前全流程对抗，并形成手工—软件可互证的第二版行动方案。",
        "objectives": [
            "围绕主要任务识别关键问题、阶段目标、转换条件和能力储备。",
            "综合组织侦察、电子战、机动、火力、防护和指挥协同完成对抗。",
            "以事件编号连接手工日志和软件回放，完成差异分析、关键决策复盘和方案优化。",
        ],
        "outputs": "考核前行动方案、综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案",
        "focus": "阶段控制、跨域协同、关键决策证据和软件辅助复盘。",
        "difficulty": "在时间受限的完整对抗中保持手工态势、命令日志、裁决底稿和软件回放的同一事件语义。",
        "teacher_prep": "准备考核同构但不同内容的公开想定、隐藏事件包、导演底稿、综合评分表、软件回放环境和差异样例。",
        "student_prep": "整合L05—L08合格成果，形成任务、席位、部署、侦察电子战、火力防护和备用行动的一页方案。",
        "key_questions": [
            "关键点怎样由主要任务、威胁和阶段条件共同决定，而不是固定等同于某个地理点？",
            "阶段转换前必须确认哪些任务效果、风险和能力储备？",
            "软件回放与手工记录不一致时，怎样判断差异来源并形成第二版方案？",
        ],
        "rows": [
            ("0—10分钟", "想定发布与考核前冻结", "发布公开想定、评分点和权限边界", "签收材料，冻结版本、席位和初始状态", "越权读取隐藏信息停止推演"),
            ("10—25分钟", "关键问题与阶段方案", "检查任务、关键问题、阶段、转换和备用行动", "提交一页方案和个人证据责任", "方案缺少触发或责任先补正"),
            ("25—40分钟", "预演与命令链检查", "组织一次无裁决口令预演并检查软件事件编号", "完成席位复诵、交接和证据目录初始化", "命令链与事件字段一致"),
            ("40—75分钟", "跨域综合对抗", "按导演脚本释放态势和约束，不作一般性提示", "综合执行侦察、干扰、机动、火力、防护和状态维护", "只在安全、规则争议、证据断链时暂停"),
            ("75—90分钟", "软件回放与事件导入", "指定不少于五个关键事件进行核对", "导入时间线并保留原始软件输出", "事件编号缺失不得进入差异分析"),
            ("90—105分钟", "差异与因果分析", "追问信息、命令、规则、裁决和状态各环节", "形成差异清单和关键决策时间线", "区分录入、同步、规则与操作差异"),
            ("105—115分钟", "第二版方案与答辩演练", "按L10答辩方式抽取个人证据", "提交第二版方案并完成个人证据定位", "改进含责任、触发和验证指标"),
            ("115—120分钟", "8分评分与考核准入", "登记分值、薄弱项和L10准入结论", "提交完整成果包与补练计划", "关键证据缺失者先补练"),
        ],
        "score": [
            ("全局筹划与阶段控制", "2.0", "关键问题、阶段转换和能力储备清楚"),
            ("跨域协同与任务贡献", "2.0", "侦察、电子战、机动火力和指挥形成闭环"),
            ("证据一致与软件核对", "2.0", "关键事件手工软件可互证，差异分类准确"),
            ("复盘优化与考核准备", "2.0", "因果分析充分，第二版方案可执行可验证"),
        ],
        "software": "导入不少于五个关键事件，完成时间线、状态、裁决和责任席位核对；软件仅作回放、统计和对照，原始手工证据与原始软件输出均须保留。",
        "homework": "按L10证据目录整理个人考核包，确保至少包含规则定位、关键命令或复诵、平台或态势操作、记录成果和软件证据定位各一项。",
        "legacy": "关键点和两波次材料用于训练阶段筹划、转换条件和能力储备，不把机场、12回合或固定两波次写成0522想定事实。",
        "max_score": "8.0",
        "score_statement": "本讲计入课程总评的专项实作8分，不再使用百分比观察框架二次折算。",
    },
    "doc-dab8a79a74dc": {
        "unit": "L10",
        "number": 10,
        "title": "综合考核：想定分析、对抗推演与复盘答辩",
        "position": "综合考核课",
        "mission": "在统一想定、规则、数据、软件和时间条件下完成可复核的个人与小组综合考核。",
        "objectives": [
            "独立完成想定研判并参与形成可执行的编队行动方案。",
            "在综合对抗中依法依规履行席位职责，以事件证据证明个人贡献。",
            "通过复盘答辩解释关键决策、规则依据、结果偏差和可验证改进。",
        ],
        "outputs": "个人想定分析表、小组行动方案、推演日志、裁决底稿、最终态势图、软件证据目录、个人贡献单、答辩与评分记录",
        "focus": "统一条件、职责分离、个人可评价、证据可回溯和人工量规评分。",
        "difficulty": "在有限时间内兼顾小组任务完成和个人证据完整，避免以胜负、软件自动结果或印象替代量规。",
        "teacher_prep": "主考冻结想定与版本；导演保管隐藏信息；裁决员准备裁决底稿；证据员建立目录；评分员使用同一100分量规并完成回避声明。",
        "student_prep": "完成L09补练，携带个人证据目录模板，考核开始前不得接触隐藏事件和他组材料。",
        "key_questions": [
            "小组结果和个人成绩分别需要什么证据？",
            "规则争议、软件异常或关键记录中断时怎样暂停、处置和恢复计时？",
            "答辩怎样从当时信息和规则出发解释决策，而不是用结果倒推理由？",
        ],
        "rows": [
            ("0—10分钟", "规则说明、抽签与冻结", "主考说明纪律、量规和申诉渠道；完成席位抽签与版本冻结", "核对材料、签署纪律与版本确认", "本阶段不计分；条件不一致暂停"),
            ("10—30分钟", "个人想定分析", "统一发放材料并计时，不提供战术提示", "独立填写任务、态势、关键问题、约束和风险", "原始20分；个人独立成果"),
            ("30—50分钟", "小组行动方案", "观察方案形成，不替代小组决策", "完成部署、阶段、协同、预案并标注个人贡献", "原始20分；到时冻结第一版"),
            ("50—90分钟", "综合对抗推演", "导演、裁决、证据、评分职责分离；仅按规则注入", "履行席位职责，形成命令、操作、裁决和状态证据", "推演35分；裁决与证据10分贯穿全程"),
            ("90—110分钟", "复盘答辩", "抽取关键事件和个人证据，实施统一追问", "完成结果解释、因果分析、规则定位和改进说明", "原始15分；不得事后补造证据"),
            ("110—120分钟", "初评、封存与移交", "核对分项、事件编号和签名，封存材料", "核对本人材料清单并签收缺项通知", "不当场自动发布；异常进入复核"),
            ("合计", "120分钟", "完成统一组织、评分与证据封存", "形成完整综合考核包", "原始100分，乘60%计入课程总评"),
        ],
        "score": [
            ("想定分析", "20", "任务、态势、关键问题、约束与风险"),
            ("行动方案", "20", "部署、阶段、协同、预案与可执行性"),
            ("推演实施", "35", "指挥决策、规则操作、协同控制、临机处置与任务贡献"),
            ("裁决与证据", "10", "规则依据、态势日志一致和软件证据定位"),
            ("复盘答辩", "15", "结果解释、因果分析、规则引用和改进方案"),
        ],
        "software": "使用冻结的软件环境提交事件目录、回放文件和手工—软件差异说明。软件证据只支持时间线、状态和答辩复核，不自动评分，也不得反向改写人工裁决。",
        "homework": "本讲无常规课后作业。收到材料缺项通知或复核要求的学员，只能补充说明与来源，不得覆盖或重做已经完成的随机裁决和原始记录。",
        "legacy": "讲课材料中的关键点、席位分工、侦察电子战、火力分配和阶段节奏用于设置答辩追问；具体参数必须定位到当前权威条目。",
        "max_score": "100",
        "score_statement": "本讲按100分量规形成原始成绩，再乘以60%计入课程总评；不采用一般实作课过程分。",
    },
}


def _current_markdown(project: dict[str, Any], document_id: str) -> str:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    working = Path(str(manifest.get("working_markdown") or ""))
    if not working.is_file():
        raise RuntimeError(f"工作稿不存在：{document_id} {working}")
    return working.read_text(encoding="utf-8")


def _lesson_markdown(spec: dict[str, Any]) -> str:
    objectives = "\n".join(f"{index}. {item}" for index, item in enumerate(spec["objectives"], 1))
    questions = "\n".join(f"{index}. {item}" for index, item in enumerate(spec["key_questions"], 1))
    process_rows = "\n".join(f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in spec["rows"])
    score_rows = "\n".join(f"| {a} | {b} | {c} |" for a, b, c in spec["score"])
    is_assessment = spec["unit"] == "L10"
    if not is_assessment:
        process_rows += "\n| 合计 | 120分钟 | 完成本讲教学控制与评分 | 形成规定成果和个人证据 | 达到下一讲准入要求 |"
    organization = (
        "采用统一想定下的个人研判与小组对抗。主考、导演、裁决、证据和评分职责分离；除安全、保密、规则争议、软件异常或证据中断外，考核中不作一般性提示。暂停和恢复均记录时间、原因、影响范围、处置与签名。"
        if is_assessment
        else "采用任务驱动、五人编组、规则查用、限时推演、软件核对和行动后复盘。教员按导演脚本控制事件，不替代学员决策；每个关键动作前检查合法性，执行后同步更新手工态势、日志、状态和软件记录。"
    )
    return f'''---
title: "第{spec['number']}讲：{spec['title']}"
status: draft
content_version: "{CONTENT_VERSION}"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 第{spec['number']}讲：{spec['title']}

> 本讲2学时（120分钟），属于{spec['position']}。{spec['mission']}规则以R1.2/D1.2为准，裁决与算子数据使用登记的R1.1/D1.1；软件、旧课件、口述案例和历史材料不得越过权威边界。

# 第一章 教学目标与达成证据

{objectives}

| 达成事项 | 必交成果 | 合格表现 |
| --- | --- | --- |
| 本讲核心任务 | {spec['outputs']} | 成果能够回指任务、规则、责任席位和事件编号 |
| 规则与数据边界 | 版本冻结与来源登记 | R1.2/D1.2规则与R1.1/D1.1登记数据使用正确 |
| 个人贡献 | 命令、操作、记录或答辩证据 | 至少一项关键行为能够定位到本人和事件 |

# 第二章 学情分析与教学准备

## 一、学情与先修条件

本讲以此前合格成果为输入。未完成规定成果、无法说明资料版本或不能建立事件编号的学员，须先完成补练；L10开始后不得补造考核前应提交的材料。

## 二、教员准备

{spec['teacher_prep']}

## 三、学员准备

{spec['student_prep']}

# 第三章 教学重点、难点与关键问题

## 一、教学重点

{spec['focus']}

## 二、教学难点

{spec['difficulty']}

## 三、课堂关键问题

{questions}

# 第四章 教学内容、教学过程与时间分配

| 时间 | 教学环节 | 教员活动 | 学员活动 | 当堂证据与停止条件 |
| --- | --- | --- | --- | --- |
{process_rows}

# 第五章 教学方法与组织要点

{organization}

出现版本不一致、隐藏信息越权、非法行动、规则争议、关键证据丢失、安全保密风险或软件状态无法解释时，立即冻结当前状态。教学实作按“定位事件—保存原态—查权威来源—纠正—说明影响”处理；综合考核按异常记录决定恢复、改用手工流程或终止。

# 第六章 软件融合任务与权威边界

{spec['software']}

所有软件成果与纸质成果使用同一课程单元、小组、席位和事件编号。差异须同时保留两侧原始材料，并登记差异类型、定位过程、处理决定与责任人。

# 第七章 评分、成果与课后任务

{spec['score_statement']}

| 评分维度 | 分值 | 评分依据 |
| --- | ---: | --- |
{score_rows}
| 合计 | {spec['max_score']} | 分值、事件编号、评语和评分员同时登记 |

必交成果：{spec['outputs']}。

使用未核验参数形成裁决、越权读取隐藏信息、覆盖原始记录、无法提供关键规则依据或补造证据的，相应证据不得计分，并按考核方案处理。

课后任务：{spec['homework']}

# 第八章 来源依据

1. 《谋战·水面舰艇编队战术手工兵棋》0522三册修订版规则稿R1.2/D1.2。
2. 0522裁决与算子数据登记版本R1.1/D1.1。
3. 《谋战》口述材料参数核验矩阵、讲课材料整理稿和课程知识库优选底稿。
4. 水面舰艇作战软件与兵棋推演课程教学计划、教学进度表、实作指导书和考核方案。

<!-- LECTURE-MATERIAL:START -->
## 既往讲课材料融合

{spec['legacy']}

<!-- LECTURE-MATERIAL:END -->
'''


def _set_frontmatter(markdown: str) -> str:
    value = re.sub(r'(?m)^content_version:\s*.*$', f'content_version: "{CONTENT_VERSION}"', markdown, count=1)
    frontmatter = value.split("---", 2)[1] if value.startswith("---") else ""
    if "data_version:" not in frontmatter:
        value = value.replace(
            f'content_version: "{CONTENT_VERSION}"\n',
            f'content_version: "{CONTENT_VERSION}"\ndata_version: "course-baseline-20h-v4"\n',
            1,
        )
    frontmatter = value.split("---", 2)[1] if value.startswith("---") else ""
    if "rules_version:" not in frontmatter:
        value = value.replace(
            'data_version: "course-baseline-20h-v4"\n',
            'data_version: "course-baseline-20h-v4"\nrules_version: "R1.2/D1.2"\n',
            1,
        )
    return value


def _practice_guide(markdown: str) -> str:
    value = _set_frontmatter(markdown)
    marker = "# 附录C 第7—9次课专项实作任务书与证据模板"
    value = value.split(marker, 1)[0].rstrip()
    appendix = r'''
# 附录C 第7—9次课专项实作任务书与证据模板

> 本附录与附录B连续使用。所有表单均填写课程单元、小组、席位、R1.2/D1.2规则版本、R1.1/D1.1数据版本和事件编号；软件字段不能替代纸面命令与人工裁决。

## C.1 第7次课侦察、电子战与协同记录

### 侦察电子战行动表

| 阶段/事件 | 关键情报需求 | 侦察平台与方向 | 信息来源与时间 | 航迹质量 | 电磁状态 | 干扰位置/条件 | 暴露代价 | 替补节点 | 责任席位 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |

### 航迹连续性与命令协同表

| 事件编号 | 航迹标识 | 上次有效时间 | 当前来源 | 共享资格 | 发令与授权 | 接收复诵 | 状态回报 | 中断原因 | 恢复措施 | 证据编号 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |

## C.2 第8次课火力链与资源持续记录

### 威胁排序与火力分配表

| 事件编号 | 目标/航迹 | 威胁依据 | 任务影响 | 交战优先级 | 发射平台/武器 | 合法性检查 | 波次与数量 | 保留能力 | 备用处置 | 批准席位 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |

### 发射裁决、通道与弹药状态表

| 事件编号 | 距离/角度/干扰 | 基础值与修正 | 随机结果 | 裁决结果 | 通道占用/释放 | 在途状态 | 事件前弹药 | 事件后弹药 | 下层再评估 | 证据编号 |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |

## C.3 第9次课综合对抗与软件辅助复盘

### 关键决策时间线

| 事件编号 | 当时信息 | 指挥意图 | 关键命令/行动 | 适用规则 | 裁决与状态变化 | 任务影响 | 责任席位 | 手工证据 | 软件证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |

### 手工—软件差异与第二版方案表

| 事件编号 | 差异字段 | 手工原记录 | 软件原记录 | 差异类型 | 原因定位 | 处理决定 | 第二版行动 | 触发条件 | 验证指标 | 责任席位 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |  |

## C.4 第7—9次课评分汇总

| 课次 | 本讲分值 | 学员得分 | 关键得分证据 | 关键扣分证据 | 补练要求 | 评分员 |
| --- | ---: | ---: | --- | --- | --- | --- |
| L07 | 8 |  |  |  |  |  |
| L08 | 8 |  |  |  |  |  |
| L09 | 8 |  |  |  |  |  |
| 合计 | 24 |  |  |  |  |  |

每讲按对应教案的四个维度各2分评分。分值必须关联事件编号或可定位成果；补练保留原表现和补练结果两套记录，不静默覆盖原分依据。
'''.strip()
    return value + "\n\n" + appendix + "\n"


def _assessment_markdown() -> str:
    return r'''---
title: "课程考核方案与评分量规"
status: "draft"
content_version: "surface-course-assessment-ready-v1"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 课程考核方案与评分量规

> 适用基线：20学时、10次课，2次理论、7次实作、1次综合考核；课程成绩由过程性实作40分和第10讲综合考核60分组成。正式裁决使用R1.2/D1.2规则与R1.1/D1.1登记数据，软件环境在考核前冻结。

# 第一章 考核目标、原则与职责

考核检验学员能否完成水面舰艇编队任务分析、行动方案制定、兵棋对抗、规则裁决、过程记录、软件核对和复盘答辩，并分别评价个人基础操作、专项战术协同和全局筹划能力。

考核坚持统一想定、统一规则、统一数据、统一软件、统一时间、统一量规和证据可回溯。胜负只作为任务结果证据之一，不直接等同个人成绩；软件只支持时间线、状态和证据复核，不自动评分。

| 角色 | 主要职责 | 禁止事项 |
| --- | --- | --- |
| 主考 | 冻结条件、说明量规、处理申诉、批准最终成绩 | 不凭印象或胜负替代分项证据 |
| 导演 | 保管隐藏信息、按脚本释放事件、记录训练控制 | 不临时偏向某组增加或删减难度 |
| 裁决员 | 检查合法性、执行规则裁决、保存底稿 | 不替代指挥员作战术决策 |
| 证据员 | 管理事件编号、材料目录、暂停与封存记录 | 不补造、删改或覆盖原始材料 |
| 评分员 | 按统一量规记录分值、证据编号和评语 | 不对同一根本错误机械重复扣分 |

考核前完成想定、R1.2/D1.2规则、R1.1/D1.1数据、软件版本、设备时间、席位与材料清单冻结。条件异常时暂停计时，填写异常记录后统一决定恢复、改用手工流程或终止。

# 第二章 课程成绩组成与过程评分

| 组成 | 课次 | 计分办法 | 课程总评分值 |
| --- | --- | --- | ---: |
| 基础实作 | 第3—6讲 | 每讲4分 | 16 |
| 专项与综合实作 | 第7—9讲 | 每讲8分 | 24 |
| 综合考核 | 第10讲 | 原始100分乘以60% | 60 |
| 合计 | 第3—10讲 | 过程40分＋综合考核60分 | 100 |

课程总评＝L03—L06得分＋L07—L09得分＋L10原始成绩×60%。过程性实作低于24分或L10原始成绩低于60分，均不能判定课程合格；两项达到门槛且课程总评不低于60分，方为合格。

## 一、第7讲专项实作8分

| 维度 | 分值 | 证据 |
| --- | ---: | --- |
| 侦察与航迹连续性 | 2 | 侦察计划、航迹连续性和替补节点记录 |
| 电子战与电磁管控 | 2 | 作用条件、电磁状态和风险记录 |
| 指挥协同与任务贡献 | 2 | 授权、复诵、状态回报和任务影响 |
| 证据一致与复盘 | 2 | 手工软件差异、因果分析和修订稿 |
| 合计 | 8 | 分值关联事件编号 |

## 二、第8讲专项实作8分

| 维度 | 分值 | 证据 |
| --- | ---: | --- |
| 威胁排序与火力计划 | 2 | 威胁排序、波次与保留能力 |
| 规则操作与裁决 | 2 | 合法性、修正、随机结果和通道释放 |
| 资源持续与临机处置 | 2 | 通道、弹药、在途状态和备用处置 |
| 证据一致与复盘 | 2 | 火力事件核对、反事实分析和修订稿 |
| 合计 | 8 | 分值关联事件编号 |

## 三、第9讲综合实作8分

| 维度 | 分值 | 证据 |
| --- | ---: | --- |
| 全局筹划与阶段控制 | 2 | 关键问题、阶段转换和能力储备 |
| 跨域协同与任务贡献 | 2 | 侦察、电子战、机动火力和指挥闭环 |
| 证据一致与软件核对 | 2 | 关键事件时间线和差异分类 |
| 复盘优化与考核准备 | 2 | 因果分析、第二版方案和个人证据目录 |
| 合计 | 8 | 分值关联事件编号 |

过程分依据当堂原始成果评分。补交和补练可以证明改进，但必须保留原表现、时间戳、补练内容和调整依据；不得覆盖已发生的操作、裁决与证据错误。

# 第三章 第10讲综合考核组织与时间

| 阶段 | 时间 | 考核活动 | 评分覆盖 | 停止/封存要求 |
| --- | ---: | --- | --- | --- |
| 规则说明与抽签 | 10分钟 | 纪律、版本、材料、席位确认 | 不计分 | 条件不一致暂停 |
| 个人想定分析 | 20分钟 | 任务、态势、关键问题、约束与风险 | 想定分析20分 | 到时封存个人原稿 |
| 小组方案制定 | 20分钟 | 部署、阶段、协同、预案 | 行动方案20分 | 到时冻结第一版 |
| 综合对抗推演 | 40分钟 | 指挥、操作、裁决、临机协同 | 推演35分；证据10分贯穿全程 | 规则争议或证据断链暂停 |
| 复盘答辩 | 20分钟 | 结果解释、因果分析、规则定位与改进 | 复盘答辩15分 | 不得事后补造证据 |
| 初评与材料移交 | 10分钟 | 核对分项、签名、缺项和封存 | 不计分 | 不自动发布成绩 |
| 合计 | 120分钟 | 形成综合考核证据包 | 原始100分 | 进入人工复核 |

# 第四章 第10讲100分量规

| 一级指标 | 分值 | 二级指标与分值 | 满分表现 |
| --- | ---: | --- | --- |
| 想定分析 | 20 | 任务5、态势5、关键问题5、约束风险5 | 区分事实、未知、规则推断和假设，判断直接支撑方案 |
| 行动方案 | 20 | 部署5、阶段5、协同5、预案与可执行性5 | 目标、触发、责任、转换、备用和证据责任完整 |
| 推演实施 | 35 | 指挥决策10、规则操作8、协同控制7、临机处置5、任务贡献与能力保存5 | 决策合法及时，席位闭环，资源和阶段状态持续可控 |
| 裁决与证据 | 10 | 规则依据3、手工态势日志一致3、软件证据与差异说明4 | 关键事件可从命令追溯到状态，原始证据完整 |
| 复盘答辩 | 15 | 结果解释4、因果分析4、规则数据引用3、改进方案4 | 基于当时信息解释决策，改进含责任、触发和验证指标 |
| 合计 | 100 | 原始成绩乘以60%计入课程总评 | 分值、证据编号、评语和评分员完整 |

理论知识嵌入想定分析、规则查用、方案说明和复盘答辩。只会操作但不能说明规则依据，或只会背诵条文但不能完成合法操作，均不能获得对应分项满分。

同一根本错误只在最主要分项扣分，避免机械重复；该错误造成的独立后果，如证据缺失、资源失控或任务链中断，可在相应分项如实评价并说明因果关系。使用错误版本、越权获取隐藏信息、擅改裁决或补造证据，按课程纪律处理。

# 第五章 综合考核表单与证据包

## 一、综合考核个人评分表

| 学员 | 小组 | 席位 | 想定分析/20 | 行动方案/20 | 推演实施/35 | 裁决证据/10 | 复盘答辩/15 | 原始总分/100 | 课程折算/60 | 评分员 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |  |  |  |  |

| 分项 | 关键得分证据编号 | 关键扣分证据编号 | 评语 | 复核意见 |
| --- | --- | --- | --- | --- |
| 想定分析 |  |  |  |  |
| 行动方案 |  |  |  |  |
| 推演实施 |  |  |  |  |
| 裁决与证据 |  |  |  |  |
| 复盘答辩 |  |  |  |  |

## 二、考核证据包目录

| 序号 | 材料 | 责任人 | 版本/时间 | 事件范围 | 文件或纸质编号 | 完整/缺项 | 封存签名 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 想定发布包与版本冻结单 |  |  |  |  |  |  |
| 2 | 个人想定分析表 |  |  |  |  |  |  |
| 3 | 小组行动方案与席位表 |  |  |  |  |  |  |
| 4 | 命令、行动与状态日志 |  |  |  |  |  |  |
| 5 | 发射拦截与裁决底稿 |  |  |  |  |  |  |
| 6 | 最终态势图 |  |  |  |  |  |  |
| 7 | 软件回放包与差异清单 |  |  |  |  |  |  |
| 8 | 个人贡献单与答辩记录 |  |  |  |  |  |  |
| 9 | 评分表、异常记录与复核单 |  |  |  |  |  |  |

个人证据至少包含一次规则定位、一次关键命令或复诵、一次平台或态势操作、一项记录成果和一次软件证据定位。小组共同材料不能自动证明所有成员贡献相同。

## 三、异常暂停与恢复记录

| 异常编号 | 发生时间 | 影响小组/事件 | 异常类型 | 冻结状态 | 暂停时长 | 处置决定 | 恢复条件 | 主考/裁决/证据员签名 |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
|  |  |  | 规则/软件/设备/证据/安全保密 |  |  |  |  |  |

软件不可用但不影响规则裁决时，可切换到手工流程并记录缺失的软件证据；软件异常影响公平或导致状态无法恢复时，由主考决定重置到共同冻结点或终止相应阶段，禁止只对单组私下补偿。

# 第六章 复盘、复核、换算与归档

复盘按“陈述—追问—证据定位—反事实分析”进行。每组选择一个有效决策和一个失效决策，说明当时信息、指挥意图、适用规则、行动、裁决、状态变化和任务影响。不能定位证据的结论不得按完整回答计分。

| 项目 | 分值 | 门槛/换算 | 复核人 |
| --- | ---: | --- | --- |
| L03—L06基础实作 | /16 | 纳入过程分 |  |
| L07—L09专项实作 | /24 | 纳入过程分 |  |
| 过程分合计 | /40 | 不低于24 |  |
| L10原始成绩 | /100 | 不低于60 |  |
| L10课程折算 | /60 | 原始成绩×60% |  |
| 课程总评 | /100 | 过程分＋L10折算；不低于60 |  |

成绩复核检查评分表、原始日志、裁决底稿、规则版本、软件证据和答辩记录；可以重新计算分值，但不重新进行已完成的随机裁决。复核结论记录原分、调整分、依据与签字。

正式归档包括想定发布包、版本冻结、分析表、行动方案、席位表、命令行动日志、裁决底稿、态势图、软件回放、差异清单、个人贡献、答辩、评分、异常和复核记录。全套材料在人工批准与发布前保持草稿状态。
'''


def _replace(project: dict[str, Any], document_id: str, markdown: str) -> None:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    if manifest.get("content_authority") == "structured_json":
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            document_id,
            markdown,
            label="课程第三阶段C专项实作与综合考核",
            actor="course-phase3c-advanced-assessment",
        )
        return
    multi_document_service.replace_rich_text_markdown(
        project,
        document_id,
        markdown,
        actor="course-phase3c-advanced-assessment",
    )


def _stale_bindings(project: dict[str, Any]) -> list[str]:
    return [
        row["id"]
        for row in multi_document_service.list_documents(project)["documents"]
        if (row.get("structure_binding") or {}).get("status") == "stale"
    ]


def _refresh_stale_bindings(project: dict[str, Any]) -> list[str]:
    refreshed: list[str] = []
    for document_id in _stale_bindings(project):
        record = multi_document_service.get_document(project, document_id)
        binding = copy.deepcopy(record.get("structure_binding") or {})
        if not binding.get("source_document_id"):
            continue
        binding["source_sha256"] = ""
        if record.get("kind") == "presentation":
            manifest = multi_document_service.presentation_manifest(project, document_id)
            manifest.pop("document", None)
            manifest.pop("structure_binding", None)
            multi_document_service.set_structure_binding(project, document_id, binding, manifest=manifest)
        else:
            multi_document_service.set_structure_binding(project, document_id, binding)
        refreshed.append(document_id)
    return refreshed


def _checks(markdown: str, document_id: str) -> dict[str, Any]:
    banned = ["共10学时", "合计16学时", "理论10＋实作10", "第11讲", "谋战谋战"]
    result = {
        "content_version": CONTENT_VERSION in markdown,
        "course_baseline": "course-baseline-20h-v4" in markdown,
        "rules_version": "R1.2/D1.2" in markdown,
        "rule_data_version": "R1.1/D1.1" in markdown,
        "banned_hits": [token for token in banned if token in markdown],
    }
    if document_id in LESSONS:
        is_assessment = document_id == "doc-dab8a79a74dc"
        result.update(
            {
                "minutes_120": "| 合计 | 120分钟 |" in markdown,
                "teacher_student_actions": "教员活动" in markdown and "学员活动" in markdown,
                "required_sections": all(token in markdown for token in ["教学内容", "教学方法", "时间分配"]),
                "outputs": "必交成果" in markdown,
                "score_aligned": (
                    "原始100分" in markdown and "60%" in markdown and "| 合计 | 100 |" in markdown
                    if is_assessment
                    else "专项实作8分" in markdown and "| 合计 | 8.0 |" in markdown
                ),
                "stop_conditions": "停止条件" in markdown and "证据" in markdown,
            }
        )
    elif document_id == PRACTICE_GUIDE_ID:
        result.update(
            {
                "advanced_appendix": "# 附录C 第7—9次课专项实作任务书与证据模板" in markdown,
                "three_templates": all(token in markdown for token in ["侦察电子战行动表", "威胁排序与火力分配表", "关键决策时间线"]),
                "score_24": "| 合计 | 24 |" in markdown,
            }
        )
    else:
        result.update(
            {
                "score_40_60": "过程40分＋综合考核60分" in markdown and "| 合计 | 第3—10讲" in markdown,
                "l07_l09_rubrics": all(token in markdown for token in ["第7讲专项实作8分", "第8讲专项实作8分", "第9讲综合实作8分"]),
                "l10_100": "第10讲100分量规" in markdown and "| 合计 | 100 |" in markdown,
                "double_gate": "过程性实作低于24分" in markdown and "L10原始成绩低于60分" in markdown,
                "forms": all(token in markdown for token in ["综合考核个人评分表", "考核证据包目录", "异常暂停与恢复记录"]),
                "draft_gate": "人工批准与发布前保持草稿状态" in markdown,
            }
        )
    return result


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")
    documents_before = multi_document_service.list_documents(project)["documents"]
    targets = {document_id: _lesson_markdown(spec) for document_id, spec in LESSONS.items()}
    targets[PRACTICE_GUIDE_ID] = _practice_guide(_current_markdown(project, PRACTICE_GUIDE_ID))
    targets[ASSESSMENT_ID] = _assessment_markdown()
    current = {document_id: _current_markdown(project, document_id) for document_id in targets}
    changed = [document_id for document_id in targets if targets[document_id] != current[document_id]]
    preview = {
        document_id: {
            "changed": document_id in changed,
            "before_chars": len(current[document_id]),
            "after_chars": len(targets[document_id]),
            "checks": _checks(targets[document_id], document_id),
        }
        for document_id in targets
    }
    if dry_run:
        return {
            "phase": PHASE_LABEL,
            "dry_run": True,
            "document_count": len(documents_before),
            "changed_document_count": len(changed),
            "changed_document_ids": changed,
            "stale_binding_ids": _stale_bindings(project),
            "preview": preview,
        }

    snapshot = p0._snapshot(project)  # noqa: SLF001
    for document_id in changed:
        _replace(project, document_id, targets[document_id])

    binding_project = project_manager.get_project(project_id) or project
    refreshed_bindings = _refresh_stale_bindings(binding_project)
    context = copy.deepcopy(binding_project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "phase3c_summary": "L07—L09已形成每讲8分的专项流程与打印模板；L10教案和考核方案已统一100分原始量规、60%折算、双门槛、证据目录和异常记录。",
            "next_step": "开展全套开课材料交叉校审与授课运行包整理；PPTX二进制修订仍等待合规编辑通道。",
        }
    )
    project_manager.update_project(project_id, {"context": context, "current_phase": "course_phase3c_advanced_assessment"})

    refreshed = project_manager.get_project(project_id) or project
    verification = {}
    for document_id in targets:
        markdown = _current_markdown(refreshed, document_id)
        verification[document_id] = {
            "revision": multi_document_service.get_document(refreshed, document_id)["revision"],
            "checks": _checks(markdown, document_id),
        }
    return {
        "phase": PHASE_LABEL,
        "dry_run": False,
        "snapshot": str(snapshot),
        "document_count_before": len(documents_before),
        "document_count_after": len(multi_document_service.list_documents(refreshed)["documents"]),
        "updated_document_ids": changed,
        "refreshed_structure_binding_ids": refreshed_bindings,
        "stale_binding_count_after": len(_stale_bindings(refreshed)),
        "verification": verification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=COURSE_PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.project_id, dry_run=not args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
