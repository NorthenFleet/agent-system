#!/usr/bin/env python3
"""Complete the first teaching-readiness batch for the 20-hour surface course."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.course_production_service import (  # noqa: E402
    COURSE_PROJECT_ID,
    course_production_service,
)
from services.multi_document_service import multi_document_service  # noqa: E402


CONTENT_VERSION = "surface-course-phase1-v1"
PHASE_LABEL = "课程开学准备第一阶段"


SOFTWARE_TASKS = {
    "L04": {
        "task": "建立手工事件编号与软件事件字段映射，录入一组交战事件并核对时间、平台、目标、动作和结果。",
        "output": "事件字段映射表、单回合事件记录和手工—软件一致性检查单",
        "boundary": "手工规则与裁决记录仍是原始依据；软件只承担结构化登记和一致性检查。",
    },
    "L05": {
        "task": "把任务背景、双方编成、初始态势、边界、情报条件和胜负判据录入结构化想定模板，完成必填项与冲突校验。",
        "output": "数字化想定要素表、缺项清单和初始态势核对单",
        "boundary": "软件不得补造隐藏信息或未给出的想定参数，未知项必须保留为未知或假设。",
    },
    "L06": {
        "task": "将行动方案编码为阶段、触发条件、责任席位、授权边界、预期效果和备用行动，并与纸面方案逐项对照。",
        "output": "方案编码表、席位责任矩阵和纸面—软件差异清单",
        "boundary": "软件用于表达和校验方案，不替代指挥员决策，也不替代裁决席的合法性判断。",
    },
    "L07": {
        "task": "在软件中登记航迹来源、时间戳、电磁状态、干扰位置与共享资格，核对手工态势图的连续性。",
        "output": "侦察电子战状态表、航迹连续性检查单和异常说明",
        "boundary": "探测、干扰与共享效果必须引用当前规则，软件显示不能自动升级为正式裁决。",
    },
    "L08": {
        "task": "对发射平台、武器、目标、通道、弹药、修正、随机结果和释放时点进行结构化复核。",
        "output": "火力链核对表、通道弹药一致性报告和漏项纠正记录",
        "boundary": "不得由软件推算规则中没有给出的不可逃逸区或未核验性能参数。",
    },
    "L09": {
        "task": "导入完整事件时间线，完成回放、统计、关键决策定位和手工—软件差异分析，形成第二版方案。",
        "output": "软件回放包、差异清单、关键决策时间线和优化方案",
        "boundary": "发现差异时保留双方原始证据，以追加说明处理，禁止静默覆盖手工记录。",
    },
    "L10": {
        "task": "提交软件证据目录，在答辩中定位关键事件，并解释软件记录与手工命令、规则和裁决之间的一致或差异。",
        "output": "软件证据目录、手工—软件一致性说明和个人证据定位记录",
        "boundary": "软件证据是复核证据，不以自动评分或仿真结果替代统一量规与人工裁决。",
    },
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mode_label(unit: dict[str, Any]) -> str:
    return {
        "theory": "理论讲授与研讨",
        "practice": "《谋战》手工兵棋实作",
        "assessment": "综合考核",
    }[unit["delivery_mode"]]


def _software_label(unit_id: str) -> str:
    if unit_id in SOFTWARE_TASKS:
        return SOFTWARE_TASKS[unit_id]["task"]
    return "不安排软件操作，重点建立课程框架、规则意识和裁决方法。"


def _course_plan(profile: dict[str, Any]) -> str:
    schedule_rows = []
    for unit in profile["units"]:
        schedule_rows.append(
            f"| 第{unit['order']}讲 | {unit['title']} | {_mode_label(unit)} | "
            f"{unit['hours']} | {_software_label(unit['id'])} |"
        )
    return "\n".join(
        [
            "---",
            'title: "《水面舰艇作战软件与兵棋推演》课程教学计划（20学时稿）"',
            'status: "draft"',
            f'content_version: "{CONTENT_VERSION}"',
            'data_version: "course-baseline-20h-v4"',
            'rules_version: "R1.2/D1.2"',
            "---",
            "",
            "# 《水面舰艇作战软件与兵棋推演》课程教学计划（20学时稿）",
            "",
            "> 本计划是3021课程项目唯一正式教学基线。课程共20学时、10次课，每次2学时；2次理论、7次《谋战》手工兵棋实作、1次综合考核。实际开课日期、班次和场地以本学期排课为准。",
            "",
            "# 第一章 理论基础与裁决方法",
            "",
            "## 一、课程基本信息",
            "",
            "| 项目 | 内容 |",
            "| --- | --- |",
            "| 课程名称 | 水面舰艇作战软件与兵棋推演 |",
            "| 课程编号 | YJZT503 |",
            "| 课程性质 | 选修课 |",
            "| 适用对象 | 本科军兵种作战指挥专业 |",
            "| 总学时 | 20学时 |",
            "| 学时结构 | 理论4学时、实作14学时、考核2学时 |",
            "| 主要兵棋 | 《谋战·水面舰艇编队战术手工兵棋》 |",
            "| 软件环境 | 课程登记的one-sim与智能筹划软件 |",
            "",
            "## 二、课程定位",
            "",
            "课程面向水面舰艇编队作战指挥训练，以《谋战》手工兵棋为裁决与实作主线，以作战软件承担结构化表达、状态核对、过程回放和证据复核。课程不把软件操作与战术训练割裂，也不让软件输出替代手工规则、导演控制或人工裁决，而是形成“想定—方案—推演—裁决—记录—复盘—优化”的完整训练闭环。",
            "",
            "## 三、课程目标",
            "",
            "1. 理解兵棋、想定、规则、算子、裁决和复盘之间的关系，掌握水面舰艇编队作战基本战术与推演流程。",
            "2. 能够依据R1.2/D1.2规则完成规则查用、单回合操作、想定分析、方案制定、专项推演和综合对抗。",
            "3. 能够按事件编号同步维护手工态势、书面日志和软件记录，识别差异并保留可复核证据。",
            "4. 能够在五人编组中履行指挥、行动、侦察电子战、裁决、记录评估等职责，形成闭环协同。",
            "5. 能够依据任务贡献、规则证据和过程数据复盘关键决策，提出具有触发条件、责任席位和验证指标的改进方案。",
            "",
            "## 四、权威边界",
            "",
            "规则引用以关联专业文档项目`proj-c57e28f8e0`的R1.2/D1.2三册规则为准，裁决数据与算子数据使用登记的R1.1/D1.1。知识库教材、口述案例、历史版本及课件中的具体参数必须经过核验矩阵过滤；未核验内容只能用于提问和机制说明，不得进入正式裁决。",
            "",
            "## 五、教学重点、难点与达成判据",
            "",
            "课程重点不是孤立记忆规则数字，而是把任务理解、规则查用、战术决策、操作执行、裁决记录和复盘论证连成闭环。理论课重点建立统一概念、战术行动链和裁决链；实作课重点训练合法性检查、席位协同、状态同步和证据留存；综合考核重点评价学员能否在有限时间内独立研判并用证据解释行动。",
            "",
            "课程难点有三类。第一类是有限信息条件下区分已知事实、基于规则的推断和指挥员假设，防止把未知情报当作确定态势。第二类是在连续事件中同步维护地图、平台状态、航迹、通道、弹药、命令和裁决，防止局部操作正确但全局记录失真。第三类是把软件用于表达、核对和复盘，同时维持手工规则和人工裁决的权威边界。",
            "",
            "| 课程目标 | 主要训练活动 | 达成证据 | 合格判据 |",
            "| --- | --- | --- | --- |",
            "| 理解体系与规则 | 概念辨析、规则定位、裁决流程制图 | 术语卡、规则索引卡、裁决流程图 | 概念关系正确，规则版本与适用条件明确 |",
            "| 完成基础操作 | 单回合操作、态势标绘、合法性检查 | 行动日志、裁决表、弹药通道变化表 | 关键动作可回溯，地图与日志一致 |",
            "| 形成行动方案 | 想定分析、五人编组、方案编码 | 想定要素表、席位卡、部署图、方案卡 | 任务、阶段、触发条件和责任席位完整 |",
            "| 组织战术协同 | 侦察电子战、火力防护、综合对抗 | 航迹表、火力分配表、综合推演证据包 | 行动合法且能够说明对主要任务的贡献 |",
            "| 证据化复盘 | 软件回放、差异分析、答辩 | 时间线、差异清单、优化方案 | 能定位证据、解释偏差并提出可验证改进 |",
            "",
            "教学评价采用形成性反馈和终结性考核结合。形成性反馈在每次课结束前完成，允许学员依据教员意见追加勘误和改进说明，但不允许覆盖原始操作记录。终结性考核使用冻结想定、统一量规和个人证据清单，保证不同小组、不同席位之间的评价可比较、可复核。",
            "",
            "# 第二章 《谋战》兵棋规则与基本操作",
            "",
            "## 一、教学内容",
            "",
            "本章对应第3—4讲。第3讲完成地图、棋子、标记物、规则手册、裁决表和算子表的配套使用，并建立版本化规则索引；第4讲围绕10秒交战级事件完成时间推进、态势标绘、合法性检查、随机裁决、通道弹药更新和证据同步。",
            "",
            "## 二、教学要求",
            "",
            "学员应做到组件完整、版本一致、操作合法、记录同步。第4讲开始建立软件事件字段映射，但手工规则和裁决记录仍是原始依据；软件记录与手工记录不一致时必须形成差异说明，不得覆盖原始证据。",
            "",
            "## 三、教学实施要点",
            "",
            "第3讲采用“问题分类—索引定位—条文复核—算子确认—适用性登记”五步查用法。教员先提供平台状态、传感器、武器、通道、干扰和自动防御等问题卡，学员分组定位规则，再交换卡片进行交叉复核。每张索引卡必须写明版本、条目、适用对象、前置条件和禁止外推事项；仅抄写一个数值而没有适用条件，视为未完成查用。",
            "",
            "第4讲采用连续来袭事件组织实作。学员先冻结事件时间和当前态势，再分配目标与防御层次，逐项检查射程、射界、航迹、通道、弹药、冷却和安全条件，随后实施随机裁决并更新所有状态。地图、行动日志、发射记录和软件事件表使用同一编号，任一载体出现漏项时立即暂停回溯。",
            "",
            "## 四、典型错误与纠偏",
            "",
            "典型错误包括组件缺失仍然开局、把历史平台数据拼接到当前想定、跳过在途武器、多个平台无序重复拦截、自动近防缺少本地航迹、漏记通道释放或弹药余量。教员采用“暂停—定位事件—查规则—恢复前态—重新执行—说明后果”的方式纠偏，并要求学员把错误原因区分为知识错误、操作错误、协同错误和记录错误。",
            "",
            "本章完成后，学员应在规定时间内独立定位常用规则，能够用完整字段记录一次交战事件，并说明最大射程、合法发射条件和最终裁决不是同一概念。只有动作、规则、结果和状态四项能够相互验证，才视为基础操作达标。",
            "",
            "# 第三章 想定构建与行动方案",
            "",
            "## 一、教学内容",
            "",
            "本章对应第5—6讲。第5讲从0522护航想定提取任务、敌我兵力、初始态势、空间边界、情报条件、胜负判据和终止条件；第6讲完成五人编组、指挥关系、编队部署、行动阶段、授权边界、触发条件和备用方案。",
            "",
            "## 二、软件融合要求",
            "",
            "第5讲把想定要素录入结构化模板并完成缺项、冲突和未知项检查；第6讲把纸面方案编码为阶段、触发条件、责任席位、预期效果和备用行动。软件只帮助表达与核对，不补造隐藏信息，不替代指挥员决策。",
            "",
            "## 三、想定分析方法",
            "",
            "想定分析按“任务—敌情—我情—环境—时间—规则—风险”展开。每一项既要记录给定事实，也要记录尚未掌握的信息和需要验证的假设。关键问题应写成能够触发决策的条件，例如威胁进入某方向、运输船暴露于某一防御空隙、关键通道或弹药下降到预设阈值，而不是停留在“加强防空”之类抽象表述。",
            "",
            "学员依据关键问题提出侦察需求、预警条件、阶段目标和风险处置。口述材料中的机场争夺、固定回合数和两波次节奏只用于说明全局筹划方法；当前想定没有相关规则时，应明确标注不适用，不得把课堂案例转写成想定事实。",
            "",
            "## 四、方案形成与检验",
            "",
            "行动方案至少包括任务理解、编队部署、阶段划分、侦察组织、火力与防护协同、授权边界、转换条件、备用行动和证据责任。每个阶段都要回答由谁实施、在什么条件下开始、预期形成什么效果、失败时怎样转换以及为下一阶段保留什么能力。",
            "",
            "方案检验采用桌面预演和限时口令演练。队长下达包含对象、行动和时间或触发条件的命令，接收席位复诵关键要素，执行后报告结果与新状态。裁决席检查合法性但不代替指挥员决策，记录席检查命令、操作、状态和软件编码是否一致。方案通过检验后形成修订版，保留修订原因和责任人。",
            "",
            "本章合格成果应能从想定要素追溯到关键问题，从关键问题追溯到阶段行动，从阶段行动追溯到席位与规则检查点。纸面方案与软件编码存在差异时，必须明确哪一方需要修订；未经指挥员确认的软件字段不能自动成为正式行动命令。",
            "",
            "# 第四章 编队专项与综合对抗推演",
            "",
            "## 一、教学内容",
            "",
            "本章对应第7—9讲。第7讲训练侦察预警、电子战、电磁静默与共享航迹；第8讲训练制空支援、对海打击、分层防空、通道与弹药管理；第9讲组织跨环节综合对抗并完成软件辅助复盘。",
            "",
            "## 二、能力递进",
            "",
            "课程由个人基础操作递进到任务与战术协同，再递进到全局筹划。学员不仅要说明行动是否合法，还要说明行动怎样支援主要任务、如何为下一阶段保留位置、信息、通道与弹药，以及怎样用手工和软件证据验证判断。",
            "",
            "## 三、软件贯穿方式",
            "",
            "第7讲核对航迹来源、电磁状态、干扰位置与共享资格；第8讲核对发射平台、目标、通道、弹药、修正和释放时点；第9讲导入完整事件时间线，完成回放、统计、差异分析和第二版方案。所有软件数据均须与事件编号和规则条目关联。",
            "",
            "## 四、专项推演组织",
            "",
            "侦察预警与电子战专项强调信息的来源、时效、共享资格和暴露代价。学员要说明由什么平台、以何种传感器状态获得航迹，电子战作用是否满足距离和扇区条件，电磁静默对主动探测、数据发送和融合修正产生什么影响，以及失去某一观察节点后由谁接替。评价不以发现目标数量为唯一标准，而以信息是否及时支撑主要任务为核心。",
            "",
            "火力与防空反导专项强调威胁优先级、交战合法性、通道占用、弹药储备和任务持续性。每次发射必须记录平台、武器、目标、航迹、基准概率、距离角度与干扰修正、数量、随机结果和释放时点。多层防御在每一层重新评估威胁，避免为追求单次保险而无序重复开火。",
            "",
            "## 五、综合对抗与行动后复盘",
            "",
            "第9讲开始前，各组提交想定分析、席位分工、部署、侦察计划、火力防护计划和备用方案。导演部冻结规则与数据版本并保管隐藏信息。推演中用事件编号贯通命令、操作、裁决和状态；教员只在安全、规则争议、证据中断或训练控制需要时暂停。",
            "",
            "行动后复盘按“任务目标—关键决策—行动结果—规则依据—偏差原因—改进方案”展开。先用手工日志恢复关键时间线，再用软件核对状态和统计；发现差异时分别检查时间语义、字段含义、数据录入、规则适用和人工裁决，不把任何一方默认视为绝对正确。第二版方案必须写明改变的行动、触发条件、责任席位和验证指标。",
            "",
            "本章达标要求是学员能够把侦察、指挥、火力、防护和记录组织为相互支撑的行动链，并说明每项行动对主要任务的贡献。仅报告胜负、击毁数量或软件统计，不能替代战术与证据评价。",
            "",
            "# 第五章 综合考核与复盘答辩",
            "",
            "## 一、10次课实施表",
            "",
            "| 讲次 | 内容 | 教学方式 | 学时 | 软件融合任务 |",
            "| --- | --- | --- | --- | --- |",
            *schedule_rows,
            "| 合计 | 10次课 | 2次理论、7次实作、1次考核 | 20 | 第4—10讲分级贯穿 |",
            "",
            "## 二、教学组织",
            "",
            "每次课统一按“任务导入—规则确认—方案或操作—推演与裁决—证据核对—复盘改进”组织。实作实行五人编组和席位轮换，教员、导演、裁决和评分职责分离。发生规则争议、软件版本不一致、关键证据丢失或数据越界时立即暂停并留痕。",
            "",
            "## 三、课前准备与课后闭环",
            "",
            "教员课前准备包括核对课程进度、想定包、三册规则、登记数据、器材清单、席位卡、记录模板和软件环境；对本讲将引用的具体性能参数逐项检查核验矩阵。理论课准备问题情境与反例，实作课准备标准事件和停止条件，考核课准备统一量规、异常处置办法和证据目录。",
            "",
            "学员课前阅读对应规则和想定摘要，完成术语、平台或席位预习；进入实作前签署版本确认并清点器材。课后由记录席汇总文件，裁决席核对规则与随机结果，指挥员确认命令含义，个人填写贡献单。教员在下一次课前反馈共性问题，必要时形成勘误，但不得反向覆盖原始材料。",
            "",
            "课程实行阶段性质量检查。第4讲结束检查基础操作和事件记录是否稳定，第6讲结束检查想定与方案能否进入推演，第8讲结束检查专项能力和软件核对是否形成闭环，第9讲结束检查综合证据包是否满足考核准备要求。未达标小组先完成针对性补练和证据补充，再进入下一阶段；补练结果与原始表现分别保存，用于判断改进效果。",
            "",
            "## 四、成绩评定",
            "",
            "课程总评由过程性实作40分和第10讲综合考核60分组成。第3—6讲各4分，共16分；第7—9讲各8分，共24分。第10讲先按100分量规评分，再乘以60%计入课程总评。过程性实作不低于24分且第10讲原始成绩不低于60分，方可判定课程合格。",
            "",
            "## 五、成果与归档",
            "",
            "正式成果包括教学计划、教学进度表、10讲教案、实作指导书、考核方案和两套课件。每次实作归档任务分析、方案、命令、行动、裁决、态势、软件记录和复盘材料；证据编号采用“课次-小组-事件-类型-序号”。补充材料必须追加保存，不得覆盖原始记录。",
            "",
            "## 六、开课前条件",
            "",
            "任课教员在开课前确认本学期日期、班次、场地、分组、器材、规则版本和软件环境。两套课件须完成逐页参数审查与视觉复核后方可进入发布审批；在人工批准前，全套文档保持草稿状态。",
            "",
            "## 七、来源依据",
            "",
            "1. 《谋战·水面舰艇编队战术手工兵棋》0522三册修订版规则稿R1.2/D1.2。",
            "2. 0522裁决与算子数据登记版本R1.1/D1.1。",
            "3. 课程知识库优选底稿与融合说明、讲课材料整理稿和口述材料参数核验矩阵。",
            "4. 课程登记的one-sim与智能筹划软件环境。",
            "",
        ]
    )


def _teaching_schedule(profile: dict[str, Any]) -> str:
    rows = []
    for unit in profile["units"]:
        theory = "2" if unit["delivery_mode"] == "theory" else ""
        practice = "2" if unit["delivery_mode"] == "practice" else ""
        assessment = "2" if unit["delivery_mode"] == "assessment" else ""
        output = {
            "L01": "能力进阶图、术语辨析卡",
            "L02": "协同关系图、裁决流程卡",
            "L03": "组件清点表、规则索引卡",
            "L04": SOFTWARE_TASKS["L04"]["output"],
            "L05": SOFTWARE_TASKS["L05"]["output"],
            "L06": SOFTWARE_TASKS["L06"]["output"],
            "L07": SOFTWARE_TASKS["L07"]["output"],
            "L08": SOFTWARE_TASKS["L08"]["output"],
            "L09": SOFTWARE_TASKS["L09"]["output"],
            "L10": SOFTWARE_TASKS["L10"]["output"],
        }[unit["id"]]
        rows.append(
            f"| {unit['order']} | 第{unit['order']}次课 | {unit['title']} | {_mode_label(unit)} | "
            f"{theory} | {practice} | {assessment} | 2 | {_software_label(unit['id'])} | {output} |"
        )
    return "\n".join(
        [
            "---",
            'title: "水面舰艇作战软件与兵棋推演教学进度表（20学时版）"',
            'status: "draft"',
            f'content_version: "{CONTENT_VERSION}"',
            'data_version: "course-baseline-20h-v4"',
            "---",
            "",
            "# 水面舰艇作战软件与兵棋推演教学进度表（20学时版）",
            "",
            "# 第一章 课程基本信息",
            "",
            "课程编号YJZT503，计划20学时，共10次课，每次2学时。学时结构为理论4学时、7次《谋战》实作14学时、综合考核2学时。开课日期、班次和场地以本学期排课为准。",
            "",
            "# 第二章 教学进度安排",
            "",
            "| 序号 | 教学进度 | 章节专题 | 教学方式 | 理论 | 实作 | 考核 | 小计 | 软件融合任务 | 必交成果 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            *rows,
            "| 合计 | 10次课 | 10讲 |  | 4 | 14 | 2 | 20 | 第4—10讲分级贯穿 | 形成课程证据链 |",
            "",
            "## 实施说明",
            "",
            "第1—2次课完成理论基础、编队战术、推演流程与裁决方法；第3—9次课以《谋战》手工兵棋为实作主线；第4—8次课逐步完成事件、想定、方案、侦察电子战和火力链的结构化表达与核对；第9次课完成完整回放和差异分析；第10次课提交手工与软件双证据并参加综合考核。",
            "",
            "软件贯穿遵守三项边界：不补造想定信息，不推算规则未定义参数，不用软件结果覆盖手工裁决。每次软件操作都必须关联课程事件编号、规则版本和责任席位。",
            "",
        ]
    )


def _practice_guide(profile: dict[str, Any]) -> str:
    markdown = p0._practice_guide(profile)  # noqa: SLF001
    markdown = re.sub(
        r'content_version: "[^"]+"',
        f'content_version: "{CONTENT_VERSION}"',
        markdown,
        count=1,
    )
    markdown = markdown.replace(
        "关联软件仅用于第9次课的数据回放、复盘和方案优化。",
        "关联软件从第4次课开始分级贯穿事件登记、想定录入、方案编码、状态核对、火力链复核、完整回放和考核取证，但不替代手工规则与人工裁决。",
    )
    markdown = markdown.replace(
        "- 第9次课配置one-sim运行环境和智能筹划软件，仅导入允许用于教学的数据。",
        "- 第4—10次课按教学任务配置课程登记的one-sim与智能筹划软件；第4—8次课可采用教员端演示或小组端录入，第9—10次课使用冻结的考核环境。",
    )
    markdown = markdown.replace(
        "6. 软件回放对照及差异说明，仅第9次课必需。",
        "6. 软件融合成果及差异说明：第4—8次课提交对应核对表，第9次课提交完整回放，第10次课纳入考核证据。",
    )
    for unit_id in ["L04", "L05", "L06", "L07", "L08", "L09"]:
        order = int(unit_id[1:])
        task = SOFTWARE_TASKS[unit_id]
        heading_pattern = rf"(## 第{order}次课实作卡：[\s\S]*?- 标准操作步骤：[^\n]+\n)"
        insertion = (
            rf"\1- 软件融合任务：{task['task']}\n"
            f"- 软件融合成果：{task['output']}\n"
            f"- 软件使用边界：{task['boundary']}\n"
        )
        markdown = re.sub(heading_pattern, insertion, markdown, count=1)
    marker = "<!-- SOFTWARE-PROGRESSION:START -->"
    markdown = re.sub(
        r"\n?<!-- SOFTWARE-PROGRESSION:START -->[\s\S]*?<!-- SOFTWARE-PROGRESSION:END -->\n?",
        "\n",
        markdown,
    ).rstrip()
    appendix_rows = [
        f"| 第{int(unit_id[1:])}次课 | {task['task']} | {task['output']} | {task['boundary']} |"
        for unit_id, task in SOFTWARE_TASKS.items()
        if unit_id != "L10"
    ]
    return "\n".join(
        [
            markdown,
            "",
            marker,
            "# 附录A 软件贯穿式实作控制表",
            "",
            "| 课次 | 软件融合任务 | 必交成果 | 权威边界 |",
            "| --- | --- | --- | --- |",
            *appendix_rows,
            "",
            "软件成果与纸质成果使用同一事件编号。每次课结束前，指挥员确认命令含义，裁决席确认规则与结果，记录席确认文件和时间戳，教员确认差异已经说明。任何补充均以追加证据保存。",
            "<!-- SOFTWARE-PROGRESSION:END -->",
            "",
        ]
    )


def _assessment_plan(profile: dict[str, Any]) -> str:
    assessment = next(row for row in profile["units"] if row["id"] == "L10")
    return f"""---
title: "课程考核方案与评分量规"
status: "draft"
content_version: "{CONTENT_VERSION}"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 课程考核方案与评分量规

> 适用基线：20学时、10次课；第{assessment['order']}次课“{assessment['title']}”为2学时综合考核。考核统一使用《谋战》规则、登记数据与冻结的软件环境。

# 第一章 考核目标

考核检验学员能否完成水面舰艇编队作战任务分析、行动方案制定、兵棋对抗实施、规则裁决、过程记录和复盘答辩，并从个人基础操作、任务战术协同和全局筹划三个层级评价战术素养、协同能力、规则意识和证据意识。

考核坚持统一想定、统一规则、统一算子、统一软件、统一时间和统一量规。小组任务结果与个人席位贡献分别取证；战术判断必须回溯到命令、操作、规则条目、裁决结果和状态变化。未核验、旧版参考、与当前数据冲突或不适用于0522想定的参数不得作为得分依据。

考核前由主考、导演和裁决员冻结R1.2/D1.2三册规则、R1.1/D1.1登记数据、想定包和软件环境。考核中确需处理异常时，应暂停计时并形成对所有小组一致适用的处置记录。

# 第二章 课程成绩组成与权重

课程总评满分100分，由过程性实作40分和第10讲综合考核60分组成。

| 组成 | 课次 | 计分办法 | 课程总评分值 |
| --- | --- | --- | --- |
| 基础实作 | 第3—6讲 | 每讲4分，按规则查用、操作规范、成果完整和纠错表现评分 | 16 |
| 专项与综合实作 | 第7—9讲 | 每讲8分，按战术协同、任务贡献、证据一致和复盘改进评分 | 24 |
| 综合考核 | 第10讲 | 先按100分量规评分，再乘以60%计入课程总评 | 60 |
| 合计 | 第3—10讲 | 过程性实作40分＋综合考核60分 | 100 |

课程总评计算公式为：课程总评＝第3—6讲过程得分＋第7—9讲过程得分＋第10讲原始成绩×60%。过程性实作得分不得低于24分，第10讲原始成绩不得低于60分；两项均达到门槛且课程总评不低于60分，方可判定课程合格。

过程性实作评分必须引用各讲必交成果和事件证据。迟交、补交或纠错材料应保留原件与时间戳；补充说明可以改善证据完整性，但不得覆盖已发生的操作和裁决错误。

# 第三章 第10讲综合考核实施与量规

| 阶段 | 时间 | 考核活动 | 原始分值 |
| --- | --- | --- | --- |
| 规则说明 | 10分钟 | 席位抽签、纪律、版本和材料确认 | 不计分 |
| 想定分析 | 20分钟 | 判断任务、敌情、我情、环境与约束 | 20 |
| 方案制定 | 20分钟 | 编队部署、行动阶段、协同关系与预案 | 20 |
| 对抗推演 | 40分钟 | 指挥决策、规则操作、临机处置与协同 | 35 |
| 裁决与证据 | 全过程 | 规则查用、态势维护、手工与软件证据一致性 | 10 |
| 复盘答辩 | 20分钟 | 结果解释、关键决策反思与方案优化 | 15 |
| 反馈归档 | 10分钟 | 反馈、成绩确认与材料移交 | 不计分 |
| 合计 | 120分钟 |  | 100 |

- 想定分析20分：任务理解5分、态势判断5分、关键问题识别5分、约束与风险识别5分。
- 行动方案20分：编队部署5分、阶段设计5分、兵力火力协同5分、预案与可执行性5分。
- 推演实施35分：指挥决策10分、规则操作8分、协同控制7分、临机处置5分、目标达成5分。
- 裁决与证据10分：规则依据3分、手工态势与日志一致性3分、软件证据定位与差异说明4分。
- 复盘答辩15分：结果解释4分、关键决策因果分析4分、规则与数据引用3分、改进方案4分。

## 理论与操作综合判定

理论知识不单独设置脱离情境的闭卷分值，而是嵌入想定分析、规则查用、方案说明和复盘答辩。学员必须能够解释兵棋、想定、规则、算子与裁决的关系，区分战术原理、规则条文和课堂经验，并在关键决策处定位适用条目。只会操作但不能说明规则依据，或只会背诵条文但不能完成合法操作，均不能获得相应分项满分。

| 等级 | 理论与想定分析 | 规则与操作 | 推演与协同 | 证据与复盘 |
| --- | --- | --- | --- | --- |
| 优秀 | 能区分事实、推断和假设，关键问题直接支撑方案 | 主动核对版本、对象和前置条件，操作无实质遗漏 | 决策及时，席位协同闭环，并为下一阶段保存能力 | 手工与软件证据可互证，能完成反事实分析 | 
| 良好 | 主要要素正确，少量风险分析不充分 | 能按提示完成规则检查，个别记录需要补正 | 能完成主要行动，协同存在可恢复延迟 | 关键事件可复核，次要附件存在缺漏 |
| 合格 | 能说明基本任务，但关键问题与方案联系较弱 | 基本操作合法，查用速度较慢或需要提醒 | 能在教员控制下完成推演，临机处置一般 | 保留主要记录，证据关联不够清晰 |
| 不合格 | 混淆公开事实和个人假设，任务理解明显错误 | 使用错误版本、跳过必要条件或擅改裁决 | 行动不能形成闭环并严重影响任务 | 关键命令、裁决或状态无法回溯 |

评分人员应在量规上同时记录分值、事件编号和简短评语。理论判断错误若直接导致非法行动或错误裁决，只在最主要的对应分项扣分，避免同一错误机械重复扣分；但由该错误造成的后续证据缺失或任务失败，可以在相应分项如实评价并说明因果关系。

个人证据至少包括一次规则定位、一次关键命令或复诵、一次平台或态势操作、一项记录成果和一次软件证据定位。队长重点评价任务判断、授权、冲突处置和阶段控制；裁决席重点评价合法性检查和记录一致；其他席位按照侦察、行动、电子战、记录或评估责任评分。

# 第四章 推演复盘、软件证据与违规处理

复盘采用“陈述—追问—证据定位—反事实分析”流程。每组选择一个有效决策和一个失效决策，说明当时信息、指挥意图、适用规则、具体行动、裁决结果及其任务影响。主考可要求学员在地图、日志、规则稿或软件回放中定位证据；不能定位的结论不得按完整回答计分。

软件证据目录必须列明事件编号、数据来源、导入时间、软件版本、责任人和对应手工材料。软件用于还原时间线、核对状态和支持答辩，不自动生成最终成绩。软件与手工记录不一致时，应同时保留原始材料并提交差异说明；没有规则依据的软件结果不得反向改写裁决。

以下材料不得作为得分依据：来源不明的截图或数字、未登记版本生成的数据、事后覆盖原始日志的记录、缺少规则条目或裁决过程的结果、把历史版本或口述案例标成当前规则的材料。伪造、删改或授意他人补造证据，按课程纪律处理。

改进方案必须说明改变什么行动、由哪个席位负责、在何种条件下触发、需要哪条规则支持以及用什么指标验证。“加强协同”“提高警惕”等没有责任主体和验证条件的表述不能获得改进方案满分。

# 第五章 成绩复核、反馈与归档

主考不得仅依据小组胜负给出个人成绩。若同组成员贡献差异明显，应引用事件编号、席位记录和答辩证据说明调整原因。成绩发布前，主考复核过程分、第10讲原始分、60%换算、双门槛和总分计算。

学员提出复核时，应指明具体分项和证据编号。复核人员检查评分表、原始日志、裁决底稿、规则版本、软件证据和答辩记录；必要时重新计算分值，但不重新进行已经完成的随机裁决。复核结论记录原分、调整分、依据和签字。

归档材料包括想定发布包、版本冻结记录、想定分析表、行动方案卡、席位表、命令与行动日志、发射拦截记录、裁决底稿、最终态势图、软件回放包、差异清单、复盘报告、个人贡献单、答辩记录、评分量规和异常处置记录。成绩进入人工批准与发布流程前，全套材料保持草稿状态。
"""


def _lesson_with_software(markdown: str, unit: dict[str, Any]) -> str:
    unit_id = unit["id"]
    task = SOFTWARE_TASKS[unit_id]
    markdown = re.sub(
        r'content_version: "[^"]+"',
        f'content_version: "{CONTENT_VERSION}"',
        markdown,
        count=1,
    )
    start = "<!-- SOFTWARE-INTEGRATION:START -->"
    end = "<!-- SOFTWARE-INTEGRATION:END -->"
    markdown = re.sub(
        rf"\n?{re.escape(start)}[\s\S]*?{re.escape(end)}\n?",
        "\n",
        markdown,
    ).rstrip()
    block = "\n".join(
        [
            start,
            "## 软件融合任务与证据要求",
            "",
            f"- 本讲任务：{task['task']}",
            f"- 必交成果：{task['output']}。",
            f"- 权威边界：{task['boundary']}",
            "- 核对方法：使用同一事件编号连接纸面方案、命令、操作、规则条目、裁决、状态和软件文件；差异以追加说明保存。",
            end,
        ]
    )
    marker = "# 第七章 来源依据"
    if marker in markdown:
        markdown = markdown.replace(marker, f"{block}\n\n{marker}", 1)
    else:
        markdown = f"{markdown}\n\n{block}\n"
    if unit_id == "L10":
        markdown = re.sub(
            r"本讲过程考核采用操作规范30%、规则引用25%、协同质量20%、证据完整性15%、复盘改进10%的观察框架；第10讲另按综合考核量规正式计分。",
            "本讲不采用一般实作课的过程观察百分比，统一按照《课程考核方案与评分量规》的100分量规评分，再按60%计入课程总评。",
            markdown,
        )
    markdown = markdown.replace(
        "第9—10讲使用的one-sim与智能筹划软件",
        "第4—10讲按任务使用的one-sim与智能筹划软件",
    )
    return markdown


def _verification_matrix(project: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    audit = p0._presentation_content_audit(project, documents)  # noqa: SLF001
    base = p0._rule_verification_matrix(audit)  # noqa: SLF001
    base = re.sub(
        r'content_version: "[^"]+"',
        f'content_version: "{CONTENT_VERSION}"',
        base,
        count=1,
    )
    return base.rstrip() + """

# 附录A 第一阶段课件发布门

两套课件在本阶段只完成来源绑定和文本扫描，不视为内容已经适配。54页手工兵棋课件中出现的30秒ENGAGE表述必须与当前10秒交战级规则逐页核对并修订；88页课程课件中的历史课程名称、历史学时结构、平台性能和未核验参数必须逐项标注来源或删除。

在完成逐页视觉复核、讲者备注复核、参数核验和课程10讲映射前，两套课件保持草稿状态，不得进入发布审批。结构绑定显示一致只证明文档关系已刷新，不能替代课件内容验收。
"""


def _knowledge_selection_with_chapters(markdown: str) -> str:
    """Promote internal-source sections so the document workspace can edit them."""
    markdown = re.sub(
        r'content_version: "[^"]+"',
        f'content_version: "{CONTENT_VERSION}"',
        markdown,
        count=1,
    )
    heading_map = {
        "## 一、底稿定位与使用边界": "# 第一章 底稿定位与使用边界",
        "## 二、优选来源、哈希与快照": "# 第二章 优选来源、哈希与快照",
        "## 三、正式主版本与冲突处理": "# 第三章 正式主版本与冲突处理",
        "## 四、10讲融合映射": "# 第四章 10讲融合映射",
        "## 五、后续修订规则": "# 第五章 后续修订规则",
    }
    for before, after in heading_map.items():
        markdown = markdown.replace(before, after)
    markdown = markdown.replace(
        "教学计划主版本：`doc-e811bedd87f9`；本次仅修复旧10/16学时实施表和明显重复错误。",
        "教学计划主版本：`doc-e811bedd87f9`；已按20学时唯一基线整体重构，历史学时稿只保留为来源证据。",
    )
    return markdown


def _documents_by_type(documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in documents:
        grouped.setdefault(str(row.get("product_type") or ""), []).append(row)
    return grouped


def _read_markdown(project: dict[str, Any], document: dict[str, Any]) -> str:
    return str(
        multi_document_service.rich_call(
            project,
            str(document["id"]),
            "fulltext",
        )["content"]
    )


def _replace(project: dict[str, Any], document: dict[str, Any], markdown: str) -> None:
    p0._replace_course_markdown(  # noqa: SLF001
        project,
        str(document["id"]),
        markdown,
        "course-teaching-readiness-phase1",
    )


def _formal_scan(project: dict[str, Any]) -> dict[str, Any]:
    documents = multi_document_service.list_documents(project)["documents"]
    banned = {
        "共10学时": re.compile(r"共\s*10\s*学时"),
        "16学时": re.compile(r"16\s*学时"),
        "合计16": re.compile(r"合计[^\n|]*\|?[^\n]*\b16\b"),
        "重复课程名": re.compile(r"谋战谋战"),
        "第11讲": re.compile(r"第\s*11\s*讲"),
    }
    hits = []
    for row in documents:
        if not row.get("is_output_product") or row.get("kind") != "rich_text":
            continue
        text = _read_markdown(project, row)
        for name, pattern in banned.items():
            if pattern.search(text):
                hits.append({"document_id": row["id"], "title": row["title"], "marker": name})
    return {"checked": sum(1 for row in documents if row.get("is_output_product") and row.get("kind") == "rich_text"), "hits": hits}


def _verification(project: dict[str, Any]) -> dict[str, Any]:
    documents = multi_document_service.list_documents(project)["documents"]
    grouped = _documents_by_type(documents)
    plan = _read_markdown(project, grouped["course_plan"][0])
    schedule = _read_markdown(project, grouped["teaching_schedule"][0])
    practice = _read_markdown(project, grouped["practice_guide"][0])
    assessment = _read_markdown(project, grouped["assessment"][0])
    knowledge = _read_markdown(
        project,
        next(
            row
            for row in grouped["internal_reference"]
            if row.get("title") == "课程知识库优选底稿与融合说明"
        ),
    )
    lessons = {
        row["course_unit_ids"][0]: _read_markdown(project, row)
        for row in grouped["lesson_plan"]
        if row.get("course_unit_ids")
    }
    internal_ids = {
        row["id"]
        for row in documents
        if not row.get("is_output_product")
        and row.get("title") in {
            "讲课材料整理：分层推演、协同指挥与制空支援",
            "《谋战》口述材料参数核验矩阵",
            "课程知识库优选底稿与融合说明",
        }
    }
    formal = [row for row in documents if row.get("is_output_product")]
    status = course_production_service.production_status(project)
    return {
        "formal_scan": _formal_scan(project),
        "plan_chapters": len(re.findall(r"(?m)^# 第[一二三四五]+章", plan)),
        "plan_has_20h_split": all(term in plan for term in ["理论4学时", "实作14学时", "考核2学时"]),
        "schedule_has_10x2": "| 合计 | 10次课 | 10讲 |  | 4 | 14 | 2 | 20 |" in schedule,
        "practice_covers_l03_l09": all(f"第{order}次课实作卡" in practice for order in range(3, 10)),
        "software_progression": {
            unit_id: (
                SOFTWARE_TASKS[unit_id]["output"] in lessons[unit_id]
                or SOFTWARE_TASKS[unit_id]["output"] in practice
                or SOFTWARE_TASKS[unit_id]["output"] in assessment
            )
            for unit_id in SOFTWARE_TASKS
        },
        "assessment_formula": all(
            term in assessment
            for term in ["过程性实作40分", "综合考核60分", "原始成绩×60%", "不得低于24分"]
        ),
        "knowledge_selection_chapters": len(
            re.findall(r"(?m)^# 第[一二三四五]+章", knowledge)
        ),
        "formal_count": len(formal),
        "internal_count": len(documents) - len(formal),
        "formal_internal_sources_bound": all(internal_ids <= set(row.get("data_source_ids") or []) for row in formal),
        "all_data_versions": sorted({str(row.get("data_version") or "") for row in documents}),
        "production_summary": status["summary"],
        "blockers": status["blockers"],
        "hashes": {
            "course_plan": _sha256_text(plan),
            "teaching_schedule": _sha256_text(schedule),
            "practice_guide": _sha256_text(practice),
            "assessment": _sha256_text(assessment),
        },
    }


def _target_preview(project: dict[str, Any]) -> dict[str, Any]:
    documents = multi_document_service.list_documents(project)["documents"]
    targets = []
    for row in documents:
        product_type = row.get("product_type")
        units = row.get("course_unit_ids") or []
        selected = product_type in {
            "course_plan",
            "teaching_schedule",
            "practice_guide",
            "assessment",
            "rule_verification_matrix",
        } or (
            product_type == "internal_reference"
            and row.get("title") == "课程知识库优选底稿与融合说明"
        ) or (product_type == "lesson_plan" and units and units[0] in SOFTWARE_TASKS)
        if selected:
            text = _read_markdown(project, row) if row.get("kind") == "rich_text" else ""
            targets.append(
                {
                    "document_id": row["id"],
                    "title": row["title"],
                    "product_type": product_type,
                    "course_unit_ids": units,
                    "current_sha256": _sha256_text(text) if text else "",
                }
            )
    return {
        "phase": PHASE_LABEL,
        "dry_run": True,
        "target_count": len(targets),
        "targets": targets,
        "current_formal_scan": _formal_scan(project),
        "template_preview": course_production_service.apply_template(project, dry_run=True),
    }


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")
    if dry_run:
        return _target_preview(project)

    snapshot = p0._snapshot(project)  # noqa: SLF001
    course_production_service.apply_template(project, dry_run=False)
    project = project_manager.get_project(project_id) or project
    documents = multi_document_service.list_documents(project)["documents"]
    grouped = _documents_by_type(documents)
    profile = (project.get("document_spec") or {}).get("course_profile") or {}

    plan = grouped["course_plan"][0]
    _replace(project, plan, _course_plan(profile))
    _replace(project, grouped["teaching_schedule"][0], _teaching_schedule(profile))
    _replace(project, grouped["practice_guide"][0], _practice_guide(profile))
    _replace(project, grouped["assessment"][0], _assessment_plan(profile))

    lessons = {
        row["course_unit_ids"][0]: row
        for row in grouped["lesson_plan"]
        if row.get("course_unit_ids")
    }
    for unit in profile["units"]:
        if unit["id"] not in SOFTWARE_TASKS:
            continue
        row = lessons[unit["id"]]
        _replace(project, row, _lesson_with_software(_read_markdown(project, row), unit))

    refreshed_documents = multi_document_service.list_documents(project)["documents"]
    refreshed_grouped = _documents_by_type(refreshed_documents)
    verification_matrix = refreshed_grouped["rule_verification_matrix"][0]
    _replace(project, verification_matrix, _verification_matrix(project, refreshed_documents))
    knowledge_selection = next(
        row
        for row in refreshed_grouped["internal_reference"]
        if row.get("title") == "课程知识库优选底稿与融合说明"
    )
    _replace(
        project,
        knowledge_selection,
        _knowledge_selection_with_chapters(_read_markdown(project, knowledge_selection)),
    )

    refreshed_plan = multi_document_service.get_document(project, str(plan["id"]))
    project = project_manager.get_project(project_id) or project
    spec = copy.deepcopy(project.get("document_spec") or {})
    spec.update(
        {
            "edition": "20学时正式基线",
            "current_edition_label": "20学时",
            "publication_edition_label": "",
            "obsidian_edition_label": "",
            "version_role_note": "20学时、10讲为唯一正式基线；知识库历史学时版本仅作来源参考，不得覆盖正式成果。",
            "expected_chapters": 5,
            "writing_goal": "形成可用于开学授课的20学时水面舰艇作战软件与兵棋推演课程教学产品",
            "working_markdown": {
                "path": refreshed_plan["source_path"],
                "chapter_count": 5,
                "edition": "20学时",
            },
        }
    )
    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "course_baseline_summary": "20学时、10次课：2次理论、7次《谋战》手工兵棋实作、1次综合考核",
            "software_integration_summary": "第4—10讲按事件登记、想定录入、方案编码、状态核对、火力链复核、完整回放和考核取证分级贯穿",
            "assessment_summary": "过程性实作40分＋第10讲综合考核60分，采用过程与终结双门槛",
            "current_delivery_phase": PHASE_LABEL,
            "next_step": "第二阶段逐页修订两套PPT，随后完善开学信息并生成Word成品；批准前保持草稿状态",
        }
    )
    project_manager.update_project(
        project_id,
        {
            "document_spec": spec,
            "context": context,
            "current_phase": "course_teaching_readiness_phase1",
        },
    )

    final_project = project_manager.get_project(project_id) or project
    course_production_service.apply_template(final_project, dry_run=False)
    final_project = project_manager.get_project(project_id) or final_project
    multi_document_service.update_document(
        final_project,
        str(knowledge_selection["id"]),
        {"expected_chapters": 5},
    )
    final_project = project_manager.get_project(project_id) or final_project
    verification = _verification(final_project)
    return {
        "phase": PHASE_LABEL,
        "dry_run": False,
        "snapshot": str(snapshot),
        "updated_documents": {
            "core": [
                {"document_id": plan["id"], "title": plan["title"]},
                {"document_id": grouped["teaching_schedule"][0]["id"], "title": grouped["teaching_schedule"][0]["title"]},
                {"document_id": grouped["practice_guide"][0]["id"], "title": grouped["practice_guide"][0]["title"]},
                {"document_id": grouped["assessment"][0]["id"], "title": grouped["assessment"][0]["title"]},
            ],
            "lessons": [
                {"document_id": lessons[unit_id]["id"], "unit_id": unit_id, "title": lessons[unit_id]["title"]}
                for unit_id in SOFTWARE_TASKS
            ],
            "internal": [
                {"document_id": verification_matrix["id"], "title": verification_matrix["title"]},
                {"document_id": knowledge_selection["id"], "title": knowledge_selection["title"]},
            ],
        },
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
