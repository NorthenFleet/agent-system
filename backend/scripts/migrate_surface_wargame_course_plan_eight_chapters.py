#!/usr/bin/env python3
"""Install the approved eight-chapter course-plan authority."""

from __future__ import annotations

import argparse
import copy
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
DOCUMENT_ID = "doc-e811bedd87f9"
DOCUMENT_TITLE = "《水面舰艇作战软件与兵棋推演》课程教学计划（20学时）"
CONTENT_VERSION = "course-plan-eight-chapter-v1"
ACTOR = "course-plan-eight-chapter-migration"
PHASE_LABEL = "课程教学计划第一阶段：八章结构定稿"

CHAPTER_TITLES = [
    "第一章 教学目标",
    "第二章 课程内容与教学要求",
    "第三章 教学设计",
    "第四章 实施过程",
    "第五章 课程实作教学",
    "第六章 考核评价",
    "第七章 保障条件",
    "第八章 附录与持续改进",
]


COURSE_PLAN = r'''---
title: "《水面舰艇作战软件与兵棋推演》课程教学计划（20学时）"
status: "draft"
content_version: "course-plan-eight-chapter-v1"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
document_role: "course_plan_authority"
---

# 《水面舰艇作战软件与兵棋推演》课程教学计划（20学时）

> 本计划是课程目标、内容、学时、教学组织、实作要求和考核结构的正式工作基线。课程共20学时、10次课，每次2学时；其中理论教学4学时、课程实作14学时、综合考核2学时。实际开课日期、班次、场地和人员以教务排课及审批结果为准。

| 项目 | 内容 |
| --- | --- |
| 课程名称 | 水面舰艇作战软件与兵棋推演 |
| 课程编号 | YJZT503 |
| 课程性质 | 选修课 |
| 适用层次 | 本科 |
| 适用专业 | 军兵种作战指挥专业 |
| 总学时 | 20学时 |
| 学时构成 | 理论4学时、实作14学时、综合考核2学时 |
| 授课单位 | 作战软件与仿真研究所 |
| 编写人 | 孙翼 |
| 审核与签发 | 以课程审批签署结果为准 |
| 执行时间 | 以批准后的学期教学任务为准 |

# 第一章 教学目标

## 一、总体目标

课程面向水面舰艇编队作战指挥训练，以《谋战·水面舰艇编队战术手工兵棋》为规则查用、操作训练和人工裁决主线，以One-Sim仿真平台和AI Planning智能筹划系统承担想定结构化表达、状态核对、过程回放、方案辅助分析和证据复核。通过理论讲授、规则查用、手工兵棋实作、软件辅助复盘和综合考核，使学员形成从任务理解到行动方案、从规则执行到裁决记录、从过程证据到复盘改进的完整能力链。

## 二、知识目标

1. 理解兵棋、作战想定、规则、算子、裁决、记录和复盘之间的关系。
2. 掌握水面舰艇编队作战的基本行动链、兵棋推演流程和人工裁决机制。
3. 熟悉《谋战》地图、棋子、标记物、规则手册、裁决表和算子表的组成与查用方法。
4. 理解手工兵棋、One-Sim仿真平台和AI Planning智能筹划系统在课程中的职责边界。

## 三、能力目标

1. 能够依据R1.2/D1.2规则完成规则定位、适用条件判断、单回合操作和裁决记录。
2. 能够从给定想定中区分事实、未知信息、规则推断和指挥员假设，形成关键问题与行动需求。
3. 能够在五人编组中完成编队部署、行动方案制定、命令交互、专项推演和综合对抗。
4. 能够用统一事件编号维护手工态势、命令日志、裁决记录和软件记录，解释差异并保留原始证据。
5. 能够围绕任务目标、关键决策、行动结果、规则依据和偏差原因完成复盘，提出可验证的改进方案。

## 四、素质目标

1. 形成严谨求实、遵守规则、尊重证据的推演作风。
2. 强化任务意识、协同意识、风险意识和责任意识。
3. 正确认识兵棋和作战软件的辅助作用，既不把推演结果等同于作战规律，也不以软件输出替代指挥决策和人工裁决。
4. 养成保存原始记录、主动复核差异和持续反思改进的专业习惯。

## 五、目标与达成证据

| 目标编号 | 目标领域 | 主要训练活动 | 达成证据 | 基本达成判据 |
| --- | --- | --- | --- | --- |
| CO1 | 体系与规则认知 | 概念辨析、规则定位、裁决流程制图 | 术语卡、规则索引卡、裁决流程图 | 概念关系正确，能够说明规则版本、对象和适用条件 |
| CO2 | 基础操作 | 组件查用、单回合操作、态势标绘 | 组件清单、行动日志、裁决表、状态变化表 | 动作合法，地图、日志、裁决和状态相互一致 |
| CO3 | 想定与方案 | 想定分析、五人编组、部署和方案编码 | 想定要素表、席位卡、部署图、行动方案 | 任务、阶段、触发条件、责任席位和备用行动完整 |
| CO4 | 战术协同 | 侦察电子战、火力防护、专项和综合推演 | 航迹表、火力分配表、综合推演证据包 | 行动合法，能够说明对主要任务和后续阶段的贡献 |
| CO5 | 证据化复盘 | 回放核对、差异分析、方案修订和答辩 | 时间线、差异清单、第二版方案、答辩记录 | 能定位证据、解释偏差并提出具有验证指标的改进 |

# 第二章 课程内容与教学要求

## 一、课程内容体系

课程按照“理论认知—规则查用—基础操作—想定与方案—专项推演—综合对抗—复盘考核”递进，分为四个教学模块。

1. 基础理论模块，对应第1—2讲，建立兵棋体系、水面舰艇编队战术、推演流程和裁决方法的共同认知。
2. 规则与操作模块，对应第3—4讲，完成《谋战》组件查用、规则定位、单回合操作、态势标绘和裁决记录。
3. 想定与方案模块，对应第5—6讲，完成任务分析、关键问题识别、五人编组、编队部署和行动方案制定。
4. 专项与综合模块，对应第7—10讲，完成侦察电子战、火力防护、综合对抗、软件辅助复盘和综合考核。

## 二、10讲内容与学时安排

| 课次 | 教学专题 | 教学方式 | 理论 | 实作 | 考核 | 主要学习产出 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| L01 | 兵棋基础与《谋战》体系认识 | 讲授、研讨 | 2 |  |  | 六要素关系图、能力进阶图、术语辨析卡、规则来源登记表 |
| L02 | 水面舰艇编队战术、推演流程与裁决方法 | 讲授、研讨 | 2 |  |  | 编队协同关系图、裁决流程卡、命令闭环卡 |
| L03 | 《谋战》组件、地图、棋子与规则查用 | 手工兵棋实作 |  | 2 |  | 组件清点表、版本确认单、规则索引卡 |
| L04 | 单回合操作、态势标绘与裁决记录 | 手工兵棋实作 |  | 2 |  | 单回合事件记录、裁决表、状态变化表、手工—软件核对单 |
| L05 | 作战想定理解、关键点识别与任务构建 | 手工兵棋实作 |  | 2 |  | 想定要素表、事实—未知—假设清单、关键问题矩阵 |
| L06 | 五人编组、编队部署与行动方案制定 | 手工兵棋实作 |  | 2 |  | 席位卡、责任矩阵、部署图、行动方案卡、命令日志 |
| L07 | 侦察预警、电子战与指挥协同专项推演 | 手工兵棋实作 |  | 2 |  | 航迹连续性表、电磁活动日志、命令协同记录、专项复盘 |
| L08 | 制空支援、对海打击与防空反导专项推演 | 手工兵棋实作 |  | 2 |  | 威胁排序表、火力分配表、发射裁决记录、资源状态表 |
| L09 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 手工兵棋实作 |  | 2 |  | 综合推演日志、证据包、关键决策时间线、第二版方案 |
| L10 | 综合考核：想定分析、对抗推演与复盘答辩 | 综合考核 |  |  | 2 | 综合考核证据包、个人贡献单、复盘答辩和评分记录 |
| 合计 | 10次课 | 2次理论、7次实作、1次考核 | 4 | 14 | 2 | 20学时 |

## 三、教学要求

1. 理论学习必须形成概念、流程和规则边界的可检查成果，不以单纯记忆术语和数值作为达成标准。
2. 实作开始前必须确认组件、规则和数据版本；动作执行前检查合法性，执行后同步更新态势、状态和证据。
3. 想定分析必须区分给定事实、未知项、规则推断和指挥员假设，不得补造隐藏信息。
4. 行动方案必须包含任务理解、阶段划分、责任席位、触发条件、授权边界、预期效果和备用行动。
5. 复盘必须能够从结论回溯到事件、命令、行动、规则和裁决，不以胜负或单一统计量替代战术分析。

## 四、内容边界

规则引用以《谋战·水面舰艇编队战术手工兵棋》R1.2/D1.2为准，裁决数据与算子数据使用登记版本R1.1/D1.1。历史课件、口述材料、其他兵棋规则和未经核验的具体参数只能用于比较、提问或机制说明，不得拼接进入当前想定的正式裁决。

# 第三章 教学设计

## 一、总体设计思路

课程坚持任务牵引、能力递进、规则约束和证据闭环。教学过程不是把理论、兵棋操作和软件使用分成彼此独立的三条线，而是围绕同一作战任务逐步增加规则复杂度、协同要求和证据责任，使学员从“能够操作”发展到“能够解释行动为什么合法、为什么有效以及如何改进”。

## 二、教学策略

1. 案例导入：使用不含未核验参数的典型作战问题，引导学员识别任务、约束和关键决策。
2. 示范与操练：教员先示范规则查用、单回合操作和证据登记，再由学员独立或分组完成同类任务。
3. 问题导向：以航迹中断、规则冲突、资源受限和记录差异等问题推动学员查证、判断和协同。
4. 分组对抗：通过五人编组、席位轮换和红蓝对抗训练指挥关系、命令闭环和团队责任。
5. 复盘改进：保留初始方案和原始记录，在证据基础上形成差异说明和第二版方案。

## 三、手工兵棋与软件融合设计

《谋战》手工兵棋承担规则查用、操作实施和人工裁决的原始依据。One-Sim仿真平台用于想定与状态的结构化表达、事件记录、过程回放和统计核对；AI Planning智能筹划系统用于行动方案的结构化表达、约束检查、方案比较和复盘辅助。软件不得自动补造隐藏信息，不得越过规则适用条件生成正式裁决，不得覆盖手工原始记录，也不得直接生成课程成绩。

## 四、课程思政与职业素养

课程思政融入任务责任、规则意识、证据意识、协同意识和复盘作风。通过海军作战问题和推演案例，引导学员认识严密筹划、规范执行、尊重事实和敢于纠错对履行使命的重要意义。相关内容必须与具体教学任务和学员行为要求结合，不以脱离教学内容的口号替代能力培养。

## 五、重点难点与解决方法

| 类型 | 主要内容 | 解决方法 |
| --- | --- | --- |
| 教学重点 | 规则查用、行动合法性、想定分析、方案形成、席位协同和证据化复盘 | 流程图、索引卡、标准事件、限时口令、事件编号和复盘模板 |
| 教学难点 | 有限信息下区分事实与假设 | 事实—未知—推断—假设分类表和组间复核 |
| 教学难点 | 连续事件中同步维护态势与资源状态 | 暂停—定位事件—恢复前态—重新执行—说明后果 |
| 教学难点 | 软件记录与手工记录出现差异 | 同时保留原始材料，逐项检查时间语义、字段、录入和规则适用 |

# 第四章 实施过程

## 一、开课条件与先修要求

课程宜安排在学员具备舰艇作战装备组成、基本战术运用和作战指挥基础之后。开课前确认教学任务、班次人数、场地、分组、器材、规则数据版本、One-Sim仿真平台和AI Planning智能筹划系统运行环境。尚未确认的学期字段不得写成既定事实。

## 二、课堂实施基本流程

每次课按照“任务导入—规则确认—方案或操作—推演与裁决—证据核对—复盘改进”组织。理论课突出概念建构、案例分析和诊断反馈；实作课突出任务分工、操作执行、人工裁决和证据同步；考核课使用冻结想定、统一量规和个人证据目录。

## 三、教学组织

实作课原则上采用五人编组，并根据人数和任务调整席位：指挥席负责任务理解、方案决断和命令确认；行动席负责机动、火力与防护行动；侦察电子战席负责航迹、电磁和信息协同；裁决席负责规则定位、合法性检查和随机裁决；记录评估席负责任务、命令、行动、状态、证据和复盘材料。席位在课程中轮换，但每次事件的责任人必须明确。

## 四、课前准备与课后闭环

教员课前核对教学进度、教案、想定包、规则数据、器材、记录模板和软件环境；学员完成对应规则、平台或席位预习。课后由记录评估席汇总原始材料，裁决席核对规则和随机结果，指挥席确认命令含义，个人提交贡献记录。勘误和补练必须追加保存，不得覆盖原始表现。

## 五、阶段质量关口

| 关口 | 检查内容 | 未达标处置 |
| --- | --- | --- |
| L02结束 | 概念、行动链、命令链和裁决链 | 完成针对性概念与流程补练 |
| L04结束 | 组件查用、单回合操作和事件记录 | 回溯标准事件并重新完成一致性检查 |
| L06结束 | 想定分析、席位分工、部署和方案 | 限时口令演练后修订方案 |
| L08结束 | 侦察电子战、火力防护和软件核对 | 针对中断环节组织专项补练 |
| L09结束 | 综合对抗证据包和第二版方案 | 补齐缺项后方可进入综合考核 |

# 第五章 课程实作教学

## 一、实作目标

课程实作覆盖L03—L09，共14学时。目标是使学员能够在规则约束和有限信息条件下完成组件查用、单回合操作、想定分析、方案制定、专项推演、综合对抗和证据化复盘，并把个人操作、席位协同和全局筹划连接为完整行动链。

## 二、实作项目与必交成果

| 课次 | 实作项目 | 必交成果 | 主要检查点 |
| --- | --- | --- | --- |
| L03 | 组件、地图、棋子与规则查用 | 组件清点表、版本确认单、规则索引卡 | 组件完整、版本一致、索引可复核 |
| L04 | 单回合操作与裁决记录 | 事件记录、裁决表、状态变化表、差异检查单 | 动作、规则、结果和状态相互验证 |
| L05 | 想定理解与任务构建 | 想定要素表、信息分类表、关键问题矩阵 | 事实、未知、推断和假设边界清楚 |
| L06 | 五人编组与行动方案 | 席位卡、责任矩阵、部署图、方案卡、命令日志 | 阶段、触发、授权和备用行动闭合 |
| L07 | 侦察电子战专项推演 | 航迹表、电磁日志、协同记录、专项复盘 | 信息来源、时效、共享资格和接替关系可追溯 |
| L08 | 火力防护专项推演 | 威胁表、火力表、发射裁决记录、资源状态表 | 交战合法性、通道、弹药和任务持续性一致 |
| L09 | 跨域综合对抗与软件复盘 | 综合日志、证据包、时间线、差异清单、第二版方案 | 行动链完整，关键判断能够回指证据 |

## 三、实作实施要求

1. 实作前完成器材、规则、数据和想定版本确认，缺少关键条件时不得启动正式裁决。
2. 推演中使用统一事件编号贯通命令、行动、裁决、状态和软件记录。
3. 导演控制、人工裁决、评分和隐藏信息管理由不同职责承担；学员不得通过软件越权获取隐藏态势。
4. 软件不可用时保留手工推演和原始记录，软件任务转为课后补录与差异复核，不改变既有人工裁决。
5. 规则争议、版本不一致、关键证据丢失、器材关键缺项或信息越权时立即冻结事件并登记恢复点。

## 四、软件应用要求

L04开始建立手工事件与软件字段映射；L05—L06使用One-Sim仿真平台和AI Planning智能筹划系统表达想定、阶段、触发条件、责任席位和备用行动；L07—L08核对航迹、电磁状态、发射事件、通道和资源状态；L09—L10完成时间线回放、统计核对、差异分析和答辩证据定位。所有软件数据均须关联事件编号、来源和规则依据。

# 第六章 考核评价

## 一、考核原则

考核坚持目标、活动、证据和评分一致，兼顾知识理解、操作规范、战术协同、证据质量和复盘能力。形成性评价用于发现问题和指导改进，综合考核用于检验学员在统一条件下的独立研判、协同推演和证据答辩能力。

## 二、成绩构成

课程总评100分，由过程性实作40分和L10综合考核60分组成。

| 组成 | 课次 | 分值 | 主要评价内容 |
| --- | --- | ---: | --- |
| 基础实作 | L03—L06 | 16分，每讲4分 | 规则查用、基础操作、想定分析和方案形成 |
| 专项与综合实作 | L07—L09 | 24分，每讲8分 | 侦察电子战、火力防护、综合对抗和软件复盘 |
| 综合考核 | L10 | 原始100分乘以60% | 想定分析、方案、推演履职、证据质量、复盘答辩 |
| 合计 | L03—L10 | 100分 | 过程与终结相结合 |

过程性实作成绩不低于24分，且L10综合考核原始成绩不低于60分，方可判定课程合格。任一门槛未达到，课程总分即使达到60分也不能直接判定合格。

## 三、目标与考核映射

| 课程目标 | 主要评价课次 | 主要证据 |
| --- | --- | --- |
| CO1 体系与规则认知 | L01—L04、L10 | 术语卡、规则索引、裁决流程和答辩定位 |
| CO2 基础操作 | L03—L04、L10 | 组件、行动、裁决和状态记录 |
| CO3 想定与方案 | L05—L06、L10 | 想定分析、部署图、方案卡和命令日志 |
| CO4 战术协同 | L07—L09、L10 | 航迹、火力、综合日志和个人贡献记录 |
| CO5 证据化复盘 | L09—L10 | 时间线、差异清单、第二版方案和答辩记录 |

## 四、评价与复核要求

过程评分必须关联课次、任务、证据编号、评分项、评语和评分人。综合考核使用冻结想定、统一规则数据、统一量规和个人证据目录。One-Sim仿真平台和AI Planning智能筹划系统只提供证据与辅助分析，不自动生成成绩。成绩异议和规则争议按照原始材料、版本记录和人工复核结果处理。

# 第七章 保障条件

## 一、教材与规则资料

1. 基本教学资料：《谋战·水面舰艇编队战术手工兵棋》R1.2/D1.2三册规则。
2. 裁决与算子资料：课程登记的R1.1/D1.1数据版本。
3. 配套资料：课程教学计划、教学进度表、10讲教案、实作指导书、考核方案和经批准的课程课件。
4. 辅助参考：历史课件、口述材料和其他兵棋资料，经核验后用于比较与研讨，不直接作为当前想定裁决依据。

## 二、场地与器材

理论课使用具备投影、白板和分组研讨条件的教室；实作课使用能够布设地图、棋子、标记物、裁决表和记录表的推演场地。器材按组编号，建立发放、清点、回收、缺损和备用件记录。

## 三、软件与数据环境

课程使用One-Sim仿真平台和AI Planning智能筹划系统。开课前确认软件版本、账号权限、想定包、时间语义、数据字段、导入导出路径和手工备用流程。软件环境必须遵守想定视角与权限边界，不得向学员泄露隐藏信息。

## 四、人员与职责

课程负责人负责课程基线、进度和审批；任课教员负责教学实施；规则管理员负责规则数据版本；导演与裁决人员负责想定控制和人工裁决；评分人员负责量规一致性；记录与证据人员负责原始材料和目录；软件保障人员负责环境可用性和故障记录。关键职责不得由软件自动替代。

## 五、安全、保密与发布

课程材料按照适用的安全保密要求使用和归档。未批准的材料保持草稿状态；Word、PDF和课件发布件必须经过内容复核、版式检查和人工批准。程序检查、课堂试用或软件运行成功不等同于正式发布。

# 第八章 附录与持续改进

## 一、课程文件体系

| 层级 | 文件 | 作用 |
| --- | --- | --- |
| 课程级 | 教学计划 | 确定目标、内容、学时、实施、实作、考核和保障基线 |
| 课程级 | 教学进度表 | 将教学计划投影为10次课的时间与专题安排 |
| 讲次级 | L01—L10教案 | 细化每讲目标、过程、时间、活动、评价和现场脚本 |
| 实作级 | 实作指导书 | 统一L03—L09任务、表单、操作和证据要求 |
| 评价级 | 考核方案与评分量规 | 统一过程评分、综合考核和复核规则 |
| 资源级 | 课件、规则、数据与软件环境 | 为教学实施提供内容、规则和运行保障 |

上述文件按照“教学计划—教学进度表—10讲教案—实作指导书与考核方案—课件与发布件”依次派生。下位文件不得自行改变课程名称、总学时、课次、规则版本、成绩结构和课程目标；需要调整时先修订教学计划并保留变更记录。

## 二、主要术语

| 术语 | 课程内涵 |
| --- | --- |
| 作战想定 | 给定任务、兵力、初始态势、环境、边界、情报和判据的课程问题环境 |
| 规则 | 约束行动合法性和裁决过程的正式依据 |
| 算子 | 对作战对象、行动或效果进行结构化表达和计算的登记数据或模型 |
| 裁决 | 依据规则、状态和随机过程确定事件结果并更新态势的过程 |
| 证据包 | 能够从结论回溯到任务、命令、行动、规则、裁决和状态的原始材料集合 |
| 差异说明 | 手工记录与软件记录不一致时，对来源、原因、影响和处理结果的追加记录 |

## 三、本学期运行字段

| 字段 | 填写内容 | 确认人 | 确认日期 |
| --- | --- | --- | --- |
| 开课日期与周次 |  |  |  |
| 班次与人数 |  |  |  |
| 教室与推演场地 |  |  |  |
| 任课教员与保障人员 |  |  |  |
| 分组数量与席位轮换 |  |  |  |
| 器材套数与备用件 |  |  |  |
| 软件终端、账号与网络 |  |  |  |
| 成果提交与归档位置 |  |  |  |

## 四、变更控制

课程名称、总学时、10讲结构、规则数据版本、成绩结构和合格门槛属于受控基线。调整这些内容时必须记录变更原因、影响范围、批准人和生效时间，并同步检查教学进度表、10讲教案、实作指导书、考核方案和课件。课次内的措辞、案例和活动调整不得越过课程目标、规则权威和考核边界。

## 五、持续改进

每次开课后汇总目标达成、规则争议、操作错误、软件差异、证据缺项、评分一致性和学员反馈。课程组区分内容问题、教学问题、器材问题、软件问题和组织问题，形成改进项、责任人、验证方式和下一轮课程的复查结果。补练和修订材料追加保存，不覆盖原始表现和历史版本。

## 六、执行与审批

本计划在课程负责人、审核人和签发人完成审批后执行。审批前正文、Word、PDF和课件均保持草稿状态；正式发布件必须能够回溯到已批准的教学计划修订。
'''


def _current_markdown(project: dict[str, Any]) -> str:
    context = multi_document_service.rich_project_context(project, DOCUMENT_ID)
    manifest = document_workspace_service.ensure_workspace(context)
    working = Path(str(manifest.get("working_markdown") or ""))
    if not working.is_file():
        raise RuntimeError(f"工作稿不存在：{working}")
    return working.read_text(encoding="utf-8")


def _state(project: dict[str, Any]) -> dict[str, Any]:
    return writing_collaboration_service.get_state(project, DOCUMENT_ID)


def _checks(markdown: str) -> dict[str, Any]:
    top_level = [
        line[2:].strip()
        for line in markdown.splitlines()
        if line.startswith("# ")
    ]
    chapters = [title for title in top_level if title in CHAPTER_TITLES]
    banned = [
        "共10学时",
        "合计16学时",
        "学 时：16",
        "第11讲",
        "兵棋推演与智能决策",
        "水面舰艇指挥决策与兵棋推演",
        "谋战谋战",
    ]
    lesson_rows = [f"| L{number:02d} |" for number in range(1, 11)]
    return {
        "content_version": CONTENT_VERSION in markdown,
        "document_title": DOCUMENT_TITLE in markdown,
        "chapter_count": len(chapters),
        "chapter_order": chapters,
        "chapter_order_valid": chapters == CHAPTER_TITLES,
        "ten_lesson_rows": all(row in markdown for row in lesson_rows),
        "hours_valid": all(
            token in markdown
            for token in ["理论教学4学时", "课程实作14学时", "综合考核2学时"]
        ),
        "score_valid": all(
            token in markdown
            for token in ["过程性实作40分", "L10综合考核60分", "不低于24分", "不低于60分"]
        ),
        "authority_valid": all(
            token in markdown
            for token in ["R1.2/D1.2", "R1.1/D1.1", "One-Sim仿真平台", "AI Planning智能筹划系统"]
        ),
        "banned_hits": [token for token in banned if token in markdown],
    }


def _checks_pass(checks: dict[str, Any]) -> bool:
    return all(
        [
            checks["content_version"],
            checks["document_title"],
            checks["chapter_count"] == 8,
            checks["chapter_order_valid"],
            checks["ten_lesson_rows"],
            checks["hours_valid"],
            checks["score_valid"],
            checks["authority_valid"],
            not checks["banned_hits"],
        ]
    )


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{project_id}")
    before = _current_markdown(project)
    before_state = _state(project)
    target = COURSE_PLAN.strip() + "\n"
    checks = _checks(target)
    if not _checks_pass(checks):
        raise RuntimeError(f"目标教学计划自检未通过：{checks}")
    document_before = multi_document_service.get_document(project, DOCUMENT_ID)
    metadata_changed = any(
        [
            document_before.get("title") != DOCUMENT_TITLE,
            int(document_before.get("expected_chapters") or 0) != 8,
            document_before.get("rules_version") != "R1.2",
            document_before.get("data_version") != "course-baseline-20h-v4",
        ]
    )
    content_changed = before != target
    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "document_id": DOCUMENT_ID,
        "before_revision": before_state.get("document_revision"),
        "before_content_sha256": writing_collaboration_service.codec.document_sha256(
            before_state["document"]
        ),
        "before_chars": len(before),
        "after_chars": len(target),
        "content_changed": content_changed,
        "metadata_changed": metadata_changed,
        "checks": checks,
    }
    if dry_run or not (content_changed or metadata_changed):
        return preview

    snapshot = p0._snapshot(project)  # noqa: SLF001
    if content_changed:
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            DOCUMENT_ID,
            target,
            label=PHASE_LABEL,
            actor=ACTOR,
        )
        project = project_manager.get_project(project_id) or project

    multi_document_service.update_document(
        project,
        DOCUMENT_ID,
        {
            "title": DOCUMENT_TITLE,
            "expected_chapters": 8,
            "rules_version": "R1.2",
            "data_version": "course-baseline-20h-v4",
            "publication_status": "draft",
        },
    )
    project = project_manager.get_project(project_id) or project
    multi_document_service.update_document_metadata(
        project,
        DOCUMENT_ID,
        {
            "last_actor": ACTOR,
            "course_plan_structure": {
                "schema": "openclaw.course-plan-structure.v1",
                "content_version": CONTENT_VERSION,
                "chapter_count": 8,
                "chapter_titles": CHAPTER_TITLES,
                "course_name": "水面舰艇作战软件与兵棋推演",
                "lesson_count": 10,
                "total_hours": 20,
                "theory_hours": 4,
                "practice_hours": 14,
                "assessment_hours": 2,
            },
        },
    )

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "course_plan_status": "eight_chapter_draft_ready_for_review",
            "next_step": "核对教学进度表与教学计划的10讲映射；教学计划审批前不批量改写10讲教案。",
        }
    )
    project_manager.update_project(
        project_id,
        {"context": context, "current_phase": "course_plan_eight_chapter"},
    )

    refreshed = project_manager.get_project(project_id) or project
    document_workspace_service.ensure_workspace(
        multi_document_service.rich_project_context(refreshed, DOCUMENT_ID)
    )
    after = _current_markdown(refreshed)
    after_state = _state(refreshed)
    document_after = multi_document_service.get_document(refreshed, DOCUMENT_ID)
    after_checks = _checks(after)
    if not _checks_pass(after_checks):
        raise RuntimeError(f"写入后自检未通过：{after_checks}")
    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "after_revision": after_state.get("document_revision"),
        "after_content_sha256": writing_collaboration_service.codec.document_sha256(
            after_state["document"]
        ),
        "projection_revision": (after_state.get("projection") or {}).get("revision"),
        "projection_status": (after_state.get("projection") or {}).get("status"),
        "approved_revision": after_state.get("approved_revision"),
        "published_revision": after_state.get("published_revision"),
        "catalog_title": document_after.get("title"),
        "expected_chapters": document_after.get("expected_chapters"),
        "publication_status": document_after.get("publication_status"),
        "checks": after_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            migrate(args.project_id, dry_run=not args.apply),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
