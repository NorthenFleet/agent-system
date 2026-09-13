#!/usr/bin/env python3
"""Upgrade L03-L06 lesson plans and the matching practice guide sections."""

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


PHASE_LABEL = "课程开学准备第三阶段B：基础实作教案与指导书深化"
CONTENT_VERSION = "surface-course-practice-ready-v1"
PRACTICE_GUIDE_ID = "doc-e6071aa369ed"


LESSONS: dict[str, dict[str, Any]] = {
    "doc-105f2073f3d9": {
        "unit": "L03",
        "number": 3,
        "title": "《谋战》组件、地图、棋子与规则查用",
        "position": "第1次实作课",
        "mission": "建立器材、版本和规则查用基线；本讲不安排软件操作。",
        "objectives": [
            "按清单完成地图、棋子、标记物、三册规则和记录表的编号核对。",
            "使用“问题分类—索引定位—条文复核—数据确认—适用性登记”方法完成规则查用。",
            "区分R1.2/D1.2规则、R1.1/D1.1登记数据与旧课件、口述案例、历史材料。",
        ],
        "outputs": "组件清点表、版本确认单、八类规则索引卡、组间复核意见",
        "focus": "组件完整性、版本冻结、规则索引和适用条件登记。",
        "difficulty": "同名对象、旧版材料和课堂案例同时出现时，仍能选用当前权威来源并说明禁止外推边界。",
        "teacher_prep": "准备两套完整组件、一套含人为缺项的组件、R1.2/D1.2规则目录、R1.1/D1.1登记数据目录、八类问题卡和核验矩阵。",
        "student_prep": "带回L02裁决流程卡，预习地图、棋子、标记物、规则手册、裁决数据和算子数据各自用途。",
        "key_questions": [
            "一个数值能够被找到，是否意味着它适用于当前对象和当前状态？",
            "规则条文、裁决数据和算子数据分别回答什么问题？",
            "为什么只抄数值而不记录版本、对象和前置条件不能视为完成规则查用？",
        ],
        "rows": [
            ("0—10分钟", "任务简报与规则冻结", "发布缺项组件情境，说明本讲停止条件和4分评分点", "签署版本确认，领取组件与问题卡", "版本确认单；版本不一致不得开始"),
            ("10—25分钟", "组件清点与功能辨识", "示范按编号、数量、用途和状态检查组件", "完成组件清点并标记缺项、破损和含义不明项", "清点表；缺项必须先处置"),
            ("25—45分钟", "规则查用示范", "用一个不含敏感数值的问题演示五步查用法", "记录问题分类、索引入口、条文、数据和适用条件", "示范索引卡；不得跨版本拼接"),
            ("45—70分钟", "分组规则定位", "分发平台状态、传感器、武器、通道、干扰等问题卡", "分工定位并填写首批索引卡", "每张卡含版本、对象、条件和禁止外推"),
            ("70—95分钟", "八类索引卡完善", "巡回检查，针对只抄数值和引用口述材料进行暂停纠偏", "完成八类索引卡并标记已核验、待核验、不适用", "八类索引卡；待核验内容不得给裁决结论"),
            ("95—110分钟", "组间交叉复核", "组织相邻小组交换问题卡和来源", "复核对方条目并写出同意、退回或边界意见", "复核意见必须定位到具体字段"),
            ("110—120分钟", "评分、归档与L04衔接", "按4分量规评分并发布单回合预习任务", "修正索引卡、归还组件、提交证据目录", "形成L04可使用的规则与对象基线"),
        ],
        "score": [
            ("组件与版本核对", "1.0", "清点完整，版本与缺项记录准确"),
            ("规则查用正确性", "1.5", "索引、条目、数据和适用条件相互一致"),
            ("证据与边界", "1.0", "来源可定位，待核验和禁止外推标记清楚"),
            ("组间复核", "0.5", "能发现问题并提出可执行修订"),
        ],
        "software": "本讲不安排软件操作。组件名称、对象标识、规则版本和索引字段将作为L04建立事件字段映射的输入。",
        "homework": "补齐被退回的规则索引卡；选择一个口述参数，说明其核验状态、不能直接使用的原因以及需要补充的权威证据。",
        "legacy": "围绕载荷数量、电子战等级、射程、不可逃逸区、刷新次数、续航和补给回合等口述示例训练查证方法，不把示例数值直接带入0522裁决。",
    },
    "doc-9c47a19819ed": {
        "unit": "L04",
        "number": 4,
        "title": "单回合操作、态势标绘与裁决记录",
        "position": "第2次实作课",
        "mission": "围绕10秒交战级事件形成命令、操作、裁决、状态和软件登记闭环。",
        "objectives": [
            "按10秒交战级事件顺序完成态势冻结、合法性检查、裁决和状态更新。",
            "在连续来袭条件下同步维护航迹、通道、弹药、在途武器、冷却和平台状态。",
            "使用同一事件编号连接手工记录与软件字段，形成差异说明而不覆盖原始证据。",
        ],
        "outputs": "事件字段映射表、单回合事件记录、弹药通道变化表、手工—软件一致性检查单、错误纠正单",
        "focus": "10秒事件闭环、分层防空合法性、状态同步和事件编号。",
        "difficulty": "多目标连续来袭时仍保持地图、日志、平台状态、通道弹药和软件记录一致。",
        "teacher_prep": "准备冻结的初始态势、连续来袭事件包、三层防御资源卡、空白事件记录、D100工具和软件字段映射模板。",
        "student_prep": "携带L03通过复核的规则索引卡，预习事件编号、航迹状态、通道占用、弹药变化和在途武器记录字段。",
        "key_questions": [
            "最大射程、合法发射条件、基础概率和最终裁决结果为什么不是同一概念？",
            "同一威胁进入下一防御层时，哪些状态必须重新检查？",
            "软件记录与手工日志不一致时，怎样保存原始证据并定位差异？",
        ],
        "rows": [
            ("0—10分钟", "任务简报与初态冻结", "发布初始态势和停止条件，核对版本", "复核L03索引卡并冻结地图、平台和资源状态", "初态确认单；不一致不得计时"),
            ("10—25分钟", "单事件完整示范", "示范事件编号、合法性、裁决、通道释放和状态更新", "逐字段跟记并指出每一步输入输出", "标准事件记录作为本讲基准"),
            ("25—40分钟", "手工—软件字段映射", "说明软件只登记和核对，不替代规则裁决", "建立时间、平台、目标、动作、规则、结果和状态字段映射", "映射表必须保留原事件编号"),
            ("40—55分钟", "小组处置方案与目标分配", "发布多目标来袭序列，检查威胁排序和防御层次", "形成目标分配、开火顺序和弹药保留方案", "不得无序重复拦截"),
            ("55—90分钟", "连续事件实作", "按时间步释放事件，只在安全、规则争议或证据中断时暂停", "执行命令、操作、裁决、状态更新和记录", "逐事件核对在途武器、通道、弹药和冷却"),
            ("90—105分钟", "软件录入与差异检查", "组织录入一组事件并生成字段对照", "比对手工与软件记录，追加差异说明", "禁止静默修改原始记录"),
            ("105—115分钟", "行动后复盘", "围绕重复拦截、漏记状态和越序裁决讲评", "选择一个错误事件完成回溯和重做", "保留错误前后两套证据"),
            ("115—120分钟", "评分与归档", "按4分量规评分并发布L05预习", "提交证据目录和个人贡献记录", "事件链完整方可归档"),
        ],
        "score": [
            ("操作与时间顺序", "1.0", "10秒事件推进、命令和操作顺序正确"),
            ("规则与裁决", "1.0", "合法性、修正、随机结果和依据完整"),
            ("状态同步", "1.0", "地图、日志、通道、弹药和平台状态一致"),
            ("软件差异检查", "0.5", "字段映射正确且差异追加保存"),
            ("复盘纠正", "0.5", "能定位错误原因并完成可验证重做"),
        ],
        "software": "建立手工事件编号与软件事件字段映射，只录入登记字段并检查一致性；软件不得补造航迹、参数或裁决结果。",
        "homework": "完善错误纠正单，说明错误属于规则、操作、协同还是记录问题，并列出防止再次发生的检查点。",
        "legacy": "保留自动防御、目标分配和弹药保留的操作经验，但固定分配比例只有在当前规则明确时才能使用。",
    },
    "doc-e542cf30905a": {
        "unit": "L05",
        "number": 5,
        "title": "作战想定理解、关键点识别与任务构建",
        "position": "第3次实作课",
        "mission": "从0522护航想定提取任务条件，形成可观察、可触发、可验证的关键问题。",
        "objectives": [
            "从想定提取任务、双方编成、初始态势、边界、情报条件、胜负判据和终止条件。",
            "把材料分为给定事实、未知信息、规则推断和指挥员假设。",
            "将关键问题转化为侦察需求、决策触发条件、风险处置和证据要求。",
        ],
        "outputs": "想定要素表、事实—未知—假设清单、关键问题矩阵、数字化想定核对单、初始态势图",
        "focus": "想定边界、信息分类、关键问题和任务构建。",
        "difficulty": "不把机场、12回合、两波次等课堂案例写成0522想定固定条件，也不把未知信息自动补成事实。",
        "teacher_prep": "准备0522公开想定包、导演部隐藏信息清单、想定字段模板、三张含缺项或冲突的样例表和软件录入模板。",
        "student_prep": "带回L04标准事件记录，预习任务、敌情、我情、环境、时间、规则和风险七类分析框架。",
        "key_questions": [
            "想定给定事实、基于规则的推断和指挥员假设怎样分别记录？",
            "关键点为什么不一定是地图上的固定地点？",
            "一个关键问题怎样写成能够触发侦察、机动、火力或备用行动的条件？",
        ],
        "rows": [
            ("0—10分钟", "想定发布与资料边界", "区分公开材料、隐藏信息和导演底稿，说明保密与停止条件", "签收想定包并登记材料版本", "材料边界清单；禁止越权读取隐藏信息"),
            ("10—25分钟", "任务与约束提取", "示范从任务目的反推兵力、时间、空间和胜负条件", "填写任务、双方编成、边界和判据字段", "想定要素表首轮完成"),
            ("25—45分钟", "事实—未知—推断—假设分类", "用冲突样例示范不得自动补全的信息", "逐条分类并登记依据、责任人和验证方式", "未知项保持未知，假设必须显式标注"),
            ("45—65分钟", "关键问题与触发条件", "示范把“加强防空”改写为可观察的条件", "提出不少于3个关键问题和对应触发条件", "关键问题必须关联主要任务"),
            ("65—90分钟", "小组任务构建与软件录入", "检查字段完整性和冲突，不提供隐藏答案", "形成侦察需求、阶段目标、风险处置并录入结构化模板", "软件只校验缺项和冲突"),
            ("90—105分钟", "组间红队复核", "组织小组交换公开成果，检查越界和逻辑跳步", "对其他组提出一项事实边界和一项任务链质疑", "复核意见必须可定位"),
            ("105—115分钟", "任务简报与修订", "按任务—关键问题—触发—行动—证据顺序质询", "3分钟简报并形成修订版", "初稿、质询和修订稿同时保留"),
            ("115—120分钟", "评分与L06衔接", "按4分量规评分并发布编组方案任务", "提交证据目录和待验证问题", "形成L06行动方案输入"),
        ],
        "score": [
            ("想定要素提取", "1.0", "任务、编成、初态、边界和判据完整"),
            ("信息分类", "1.0", "事实、未知、推断和假设边界清楚"),
            ("关键问题与触发", "1.0", "问题可观察、可触发且服务主要任务"),
            ("软件与证据", "1.0", "字段录入准确，缺项冲突和来源可追溯"),
        ],
        "software": "录入任务背景、双方编成、初始态势、边界、情报条件和胜负判据；软件只检查字段完整性和冲突，不补造隐藏信息。",
        "homework": "完善一个关键问题矩阵，写出观察指标、触发阈值、责任席位、首选行动、备用行动和所需证据。",
        "legacy": "机场争夺、转场、12回合和两波次节奏只用于说明全局筹划方法；当前想定没有对应条件时必须标为不适用。",
    },
    "doc-9df3ab46770c": {
        "unit": "L06",
        "number": 6,
        "title": "五人编组、编队部署与行动方案制定",
        "position": "第4次实作课",
        "mission": "把L05想定分析转化为五人指挥闭环、编队部署和能够进入专项推演的行动方案。",
        "objectives": [
            "依据想定而不是固定模板设置五人席位、授权边界和交接条件。",
            "形成包含部署、阶段、触发条件、火力防护、备用行动和证据责任的方案。",
            "通过限时口令演练验证命令、复诵、执行、状态回报和冲突处置。",
        ],
        "outputs": "席位卡、责任矩阵、指挥关系图、编队部署图、行动方案卡、命令交互日志、纸面—软件差异清单",
        "focus": "五人编组、指挥关系、方案阶段和命令闭环。",
        "difficulty": "队长保持全局态势而不包办操作，各席位在统一意图下行动，裁决席不越权替代指挥决策。",
        "teacher_prep": "准备L05合格想定分析样例、五人席位卡、部署底图、方案卡、模糊命令反例、限时事件脚本和软件方案编码模板。",
        "student_prep": "完成L05关键问题矩阵，带齐想定要素表、初始态势图和待验证问题。",
        "key_questions": [
            "五人席位为什么应随想定调整，而不是机械照搬空中或水下编组？",
            "一个阶段行动必须回答哪些对象、条件、效果、责任和转换问题？",
            "裁决席怎样检查合法性而不替代指挥员作战术决策？",
        ],
        "rows": [
            ("0—10分钟", "输入核对与任务重述", "检查L05成果是否达到方案设计条件", "队长候选人用2分钟重述任务和关键问题", "任务表述、边界和待验证问题一致"),
            ("10—25分钟", "五人席位与授权设计", "示范队长、行动、侦察电子战、裁决、记录评估的职责边界", "填写席位卡、责任矩阵和交接条件", "裁决与指挥职责必须分离"),
            ("25—45分钟", "编队部署与风险检查", "引导从任务、威胁轴和能力保存检验部署", "完成部署图并标注重点方向、相互支援和风险", "部署必须能回指L05关键问题"),
            ("45—65分钟", "阶段方案与备用行动", "示范阶段目标、触发条件、预期效果和转换条件", "形成阶段行动卡、火力防护协同和备用方案", "每阶段明确责任席位与证据责任"),
            ("65—90分钟", "限时命令闭环演练", "按脚本注入态势变化，观察命令、复诵、执行和状态回报", "完成两轮口令演练和一次席位交接", "命令含对象、行动、时间/触发和报告要求"),
            ("90—105分钟", "软件方案编码与对照", "说明软件只表达和校验方案", "录入阶段、触发、席位、授权、效果和备用行动", "形成纸面—软件差异清单"),
            ("105—115分钟", "行动方案修订与评审", "按任务贡献、闭环协同和可执行性组织评审", "修订席位、部署和行动方案", "保留修订原因和责任人"),
            ("115—120分钟", "评分与专项推演准入", "按4分量规评分并判断是否进入L07", "提交完整方案包和个人贡献记录", "未达到闭环要求先补练"),
        ],
        "score": [
            ("席位与指挥关系", "1.0", "职责、授权、交接和冲突处置明确"),
            ("部署与阶段方案", "1.0", "部署服务任务，阶段行动完整可执行"),
            ("触发与备用行动", "1.0", "转换条件、风险处置和能力储备明确"),
            ("演练与差异修订", "1.0", "命令闭环有效，纸面软件差异已处理"),
        ],
        "software": "将方案编码为阶段、触发条件、责任席位、授权边界、预期效果和备用行动；软件用于表达和校验，不替代指挥决策与合法性判断。",
        "homework": "根据评审意见提交第二版行动方案，逐项说明修改内容、触发依据、责任席位和将在L07验证的指标。",
        "legacy": "保留五人协同和队长维持全局态势的思想，但不机械照搬“两名空战席、独立水下席”等不适用于当前想定的固定编组。",
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
    return f'''---
title: "第{spec['number']}讲：{spec['title']}"
status: draft
content_version: "{CONTENT_VERSION}"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 第{spec['number']}讲：{spec['title']}

> 本讲2学时（120分钟），属于{spec['position']}。{spec['mission']}规则以R1.2/D1.2为准，裁决与算子数据使用登记的R1.1/D1.1；旧课件、口述案例和历史材料未经核验不得进入正式裁决。

# 第一章 教学目标与达成证据

{objectives}

| 达成事项 | 必交成果 | 合格表现 |
| --- | --- | --- |
| 本讲核心任务 | {spec['outputs']} | 成果能够回指任务、规则、责任席位和证据编号 |
| 规则与数据边界 | 版本确认及来源登记 | R1.2/D1.2规则与R1.1/D1.1登记数据使用正确 |
| 复盘改进 | 初稿、问题记录和修订稿 | 原始记录保留，修订原因和验证方式明确 |

# 第二章 学情分析与教学准备

## 一、学情与先修条件

本讲建立在前序课程合格成果基础上。未完成前序必交成果或无法说明资料版本与事件编号的学员，先完成针对性补练，再进入主要实作。

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
| 合计 | 120分钟 | 完成本讲教学控制与评分 | 形成规定成果和个人证据 | 达到下一讲准入要求 |

# 第五章 教学方法与组织要点

采用任务驱动、教员示范、五人编组、组间复核、限时实作和行动后复盘。关键操作执行前检查资料版本、想定权限、行动合法性和证据条件；执行后同步更新地图、日志、状态与软件记录。出现版本不一致、隐藏信息越权、规则争议、关键证据丢失或安全保密风险时立即暂停。

教员按“暂停—定位事件—冻结原态—查权威来源—重做—说明影响”纠偏。学员必须保留初始成果、错误记录、复核意见和修订版；不得以最终胜负、软件输出或教师口头意见覆盖原始证据。

# 第六章 软件融合任务与权威边界

{spec['software']}

所有软件成果与纸质成果使用同一课程单元、小组和事件编号。软件与手工记录存在差异时，分别保留原始材料，以追加说明记录差异类型、定位过程、处理决定和责任人。

# 第七章 过程评分与课后任务

本讲计入课程总评的过程性实作4分，不使用百分比观察框架重复折算。

| 评分维度 | 分值 | 评分依据 |
| --- | ---: | --- |
{score_rows}
| 合计 | 4.0 | 原始证据完整且能够定位个人贡献 |

任何使用未核验参数形成裁决、越权读取隐藏信息、覆盖原始记录或无法提供关键规则依据的行为，该项证据不得计分，并按课程规定完成纠正记录。

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
        value = value.replace(f'content_version: "{CONTENT_VERSION}"\n', f'content_version: "{CONTENT_VERSION}"\ndata_version: "course-baseline-20h-v4"\n', 1)
    frontmatter = value.split("---", 2)[1] if value.startswith("---") else ""
    if "rules_version:" not in frontmatter:
        value = value.replace('data_version: "course-baseline-20h-v4"\n', 'data_version: "course-baseline-20h-v4"\nrules_version: "R1.2/D1.2"\n', 1)
    return value


def _practice_guide(markdown: str) -> str:
    value = _set_frontmatter(markdown)
    value = value.replace(
        "第4—10次课按教学任务配置课程登记的one-sim与智能筹划软件；第4—8次课可采用教员端演示或小组端录入，第9—10次课使用冻结的考核环境。",
        "第4—9次课按实作任务配置课程登记的one-sim与智能筹划软件；第4—8次课可采用教员端演示或小组端录入，第9次课使用冻结的综合对抗环境，第10次课另按考核方案使用冻结环境。",
    )
    marker = "# 附录B 第3—6次课标准任务书与记录模板"
    value = value.split(marker, 1)[0].rstrip()
    appendix = r'''
# 附录B 第3—6次课标准任务书与记录模板

> 本附录可直接复制或打印使用。所有空白表均须填写课程单元、小组、席位、版本和证据编号；电子表与纸质表使用同一事件编号。

## B.1 第3次课组件与版本清点表

| 类别 | 名称/编号 | 应有数量 | 实有数量 | 版本/状态 | 缺项与处置 | 复核人 |
| --- | --- | ---: | ---: | --- | --- | --- |
| 地图 |  |  |  |  |  |  |
| 棋子 |  |  |  |  |  |  |
| 标记物 |  |  |  |  |  |  |
| 规则手册 |  |  |  | R1.2/D1.2 |  |  |
| 裁决数据 |  |  |  | R1.1/D1.1 |  |  |
| 算子数据 |  |  |  | R1.1/D1.1 |  |  |
| 记录表 |  |  |  |  |  |  |

### 规则索引卡

| 问题编号 | 问题类别 | 对象与状态 | 规则版本及条目 | 登记数据条目 | 适用条件 | 结论 | 核验状态 | 禁止外推事项 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  | 已核验/待核验/不适用 |  |

## B.2 第4次课单回合事件记录表

| 事件编号 | 时间步 | 命令席位 | 平台/目标 | 航迹来源 | 行动 | 合法性检查 | 规则与数据条目 | 修正与随机结果 | 状态更新 | 证据编号 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  | 射程/射界/通道/弹药/安全 |  |  |  |  |

### 通道、弹药与在途武器变化表

| 事件编号 | 平台 | 武器/通道 | 事件前状态 | 发射/占用数量 | 在途或冷却状态 | 释放时点 | 事件后余量 | 复核人 |
| --- | --- | --- | --- | ---: | --- | --- | ---: | --- |
|  |  |  |  |  |  |  |  |  |

### 手工—软件一致性检查单

| 事件编号 | 核对字段 | 手工记录 | 软件记录 | 一致/差异 | 差异类型 | 处理决定 | 责任人 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  | 时间/平台/目标/行动/结果/状态 |  |  |  |  |  |  |

## B.3 第5次课想定分析与关键问题矩阵

### 想定要素表

| 要素 | 给定事实 | 未知信息 | 规则推断 | 指挥员假设 | 来源/依据 | 验证责任 |
| --- | --- | --- | --- | --- | --- | --- |
| 任务 |  |  |  |  |  |  |
| 敌情 |  |  |  |  |  |  |
| 我情 |  |  |  |  |  |  |
| 环境与空间边界 |  |  |  |  |  |  |
| 时间条件 |  |  |  |  |  |  |
| 胜负与终止条件 |  |  |  |  |  |  |

### 关键问题矩阵

| 关键问题 | 与主要任务关系 | 观察指标 | 触发条件 | 侦察需求 | 首选行动 | 备用行动 | 责任席位 | 所需证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

## B.4 第6次课五人席位与行动方案模板

### 席位责任矩阵

| 席位 | 主要职责 | 授权边界 | 输入信息 | 输出成果 | 交接条件 | 禁止事项 |
| --- | --- | --- | --- | --- | --- | --- |
| 队长/指挥员 |  |  |  |  |  | 不包办全部具体操作 |
| 行动席 |  |  |  |  |  |  |
| 侦察与电子战席 |  |  |  |  |  |  |
| 裁决席 |  |  |  |  |  | 不替代指挥员决策 |
| 记录与评估席 |  |  |  |  |  | 不覆盖原始记录 |

### 阶段行动方案卡

| 阶段 | 阶段目标 | 开始触发 | 主要行动 | 责任席位 | 规则检查点 | 预期效果 | 转换条件 | 备用行动 | 证据责任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |

### 命令闭环与席位交接记录

| 事件编号 | 发令席位 | 对象 | 行动 | 时间/触发条件 | 接收复诵 | 执行结果 | 新状态报告 | 交接确认 | 证据编号 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |

## B.5 第3—6次课评分汇总

| 课次 | 本讲分值 | 小组/学员得分 | 关键扣分证据 | 纠正或补练要求 | 评分员 |
| --- | ---: | ---: | --- | --- | --- |
| L03 | 4 |  |  |  |  |
| L04 | 4 |  |  |  |  |
| L05 | 4 |  |  |  |  |
| L06 | 4 |  |  |  |  |
| 合计 | 16 |  |  |  |  |

评分只依据可定位的课堂原始证据。补练可以证明改进，但不覆盖原始表现；是否调整成绩按课程考核方案和教员统一规定执行。
'''.strip()
    return value + "\n\n" + appendix + "\n"


def _replace(project: dict[str, Any], document_id: str, markdown: str) -> None:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    if manifest.get("content_authority") == "structured_json":
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            document_id,
            markdown,
            label="课程第三阶段B基础实作教案与指导书",
            actor="course-phase3b-practice-docs",
        )
        return
    multi_document_service.replace_rich_text_markdown(
        project,
        document_id,
        markdown,
        actor="course-phase3b-practice-docs",
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
        "data_version": "R1.1/D1.1" in markdown,
        "banned_hits": [token for token in banned if token in markdown],
    }
    if document_id in LESSONS:
        result.update(
            {
                "minutes_120": "| 合计 | 120分钟" in markdown,
                "teacher_student_actions": "教员活动" in markdown and "学员活动" in markdown,
                "required_sections": all(token in markdown for token in ["教学内容", "教学方法", "时间分配"]),
                "score_4": "本讲计入课程总评的过程性实作4分" in markdown and "| 合计 | 4.0 |" in markdown,
                "outputs": "必交成果" in markdown,
            }
        )
    else:
        result.update(
            {
                "covers_l03_l09": "第3—9次课" in markdown,
                "template_appendix": "# 附录B 第3—6次课标准任务书与记录模板" in markdown,
                "four_templates": all(token in markdown for token in ["规则索引卡", "单回合事件记录表", "关键问题矩阵", "席位责任矩阵"]),
                "score_16": "| 合计 | 16 |" in markdown,
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
            "phase3b_summary": "L03—L06四讲已形成独立120分钟实作流程和每讲4分量规；实作指导书已补齐四类可打印标准记录模板。",
            "next_step": "继续深化L07—L09专项与综合推演教案，并同步补齐考核前综合证据包模板；PPTX二进制修订仍等待合规编辑通道。",
        }
    )
    project_manager.update_project(project_id, {"context": context, "current_phase": "course_phase3b_practice_docs"})

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
