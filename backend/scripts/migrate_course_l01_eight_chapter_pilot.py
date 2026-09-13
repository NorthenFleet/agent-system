#!/usr/bin/env python3
"""Install the L01 eight-chapter lesson-plan pilot from frozen authorities."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path("/Users/apple/工作桌面/Workspace/agent-system/backend")
sys.path.insert(0, str(BACKEND))

from project_manager import project_manager  # noqa: E402
from scripts import migrate_surface_wargame_course_p0 as p0  # noqa: E402
from services.document_workspace_service import document_workspace_service  # noqa: E402
from services.multi_document_service import multi_document_service  # noqa: E402
from services.writing_collaboration_service import writing_collaboration_service  # noqa: E402


PROJECT_ID = "proj-16ca49b862"
COURSE_PLAN_ID = "doc-e811bedd87f9"
SCHEDULE_ID = "doc-2a28da7429f0"
DOCUMENT_ID = "doc-3a9dbb65b9a3"
DOCUMENT_TITLE = "第1讲：兵棋基础与《谋战》体系认识"
COURSE_PLAN_REVISION = 14
COURSE_PLAN_CONTENT_SHA256 = "f315d92c7a21a5ba89503f3dbb2420fb382ef4eff547f590ef5dc8de7bfb5623"
COURSE_PLAN_WORKING_SHA256 = "e681c44bff1f5be27b4a124b4601f7825cab5e6861258b6cf7c365c33d712114"
SCHEDULE_REVISION = 16
SCHEDULE_CONTENT_SHA256 = "b35fd5152f2b25ac119e5d38fc01672a54c044950ce3026cf43fa1f128bbda19"
SCHEDULE_WORKING_SHA256 = "cd3937fe98b3c8b95b358957213ba6505b336ebb1e2f681d7065b730a423cdbf"
L01_BASE_REVISION = 62
L01_BASE_CONTENT_SHA256 = "586a4022923833465494704ffbb6f681d496f1383917dbc16e659b3353865b5e"
L01_BASE_WORKING_SHA256 = "f728e096c835b223fce92185c42f806e03126b73c60686cdd501ef7f5f6f590b"
L01_INTERIM_REVISION = 63
L01_INTERIM_CONTENT_SHA256 = "7106c8a49cba2dad7bd0cfa8b879d900124df2bbf6ab49543594f72c8c373428"
L01_INTERIM_WORKING_SHA256 = "a8f11e26b1d812221065391cac601a3de37cd1f178d7969a32bdd180fcca8047"
SOURCE_WORD = Path(
    "/Users/apple/工作桌面/knowledge/06-项目库-Projects/"
    "水面舰艇作战软件与兵棋推演课程--proj-16ca49b862/教案/第1讲-兵棋概述.docx"
)
SOURCE_WORD_SHA256 = "7fadadc4a05f67bff1cb1ebb62c85a9bc4712644d75bd04c7a8a4b4e708dadb2"
CONTENT_VERSION = "course-lesson-l01-eight-chapter-pilot-v1"
ACTOR = "course-l01-eight-chapter-pilot"
PHASE_LABEL = "课程教案第四阶段：L01八章样板"
GENERATED_AT = "2026-08-23T08:15:00+00:00"

OTHER_LESSONS = {
    "L02": ("doc-6085f649c11a", 12, "cf59ca0e586f46ff6d6281aa7a55a2105e48250899bcd41732fabe1a26b0b0b0"),
    "L03": ("doc-105f2073f3d9", 10, "31e2d785937fc8a8377c8370ebc081b8d8be03c0728d3b6333b3403a562ce858"),
    "L04": ("doc-9c47a19819ed", 12, "fb53099ea49c040568a13bad8476115dc32a33c2ede5c910a7ee975339cefdca"),
    "L05": ("doc-e542cf30905a", 12, "ff2a3f37a28a34612eb9539872e0429d1ca3784bd0c3451fb2011a0c3c45a973"),
    "L06": ("doc-9df3ab46770c", 12, "f7e6c1af4b30267c9f79406405600c48a6219d10e240902d3176477462898dc3"),
    "L07": ("doc-60e4858f35af", 12, "72836823c3c1500e4f19054252fc70d80f046e0450a67b3915a9b43727245673"),
    "L08": ("doc-8248d6366ec3", 12, "1f71c3163532096563d645fcd7b0f54460d93ae5a4dc02d791697861cf2201cb"),
    "L09": ("doc-729fe58abb5a", 12, "4ea207564e324dbeee3db16f789ea5309e5bcf105e954ff07f5224e2868ace5f"),
    "L10": ("doc-dab8a79a74dc", 12, "0ef36d1d977e56970b6d18fe4a6dbf0b22ef2ee94f2b83598279833c259c6caf"),
}

CHAPTER_TITLES = [
    "第一章 教学定位、目标与达成证据",
    "第二章 学情分析、先修条件与教学准备",
    "第三章 教学重点、难点与关键问题",
    "第四章 教学内容体系与教员讲授提纲",
    "第五章 课堂过程、师生活动与120分钟脚本",
    "第六章 教学方法、组织实施与人机协同边界",
    "第七章 学习成果、评价量规、课后任务与下讲移交",
    "第八章 来源依据、配套材料与课后反思",
]

SOURCE_REFS = [
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0d2362510580",
        "product_id": "",
        "relation": "authoritative_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0522adjud01",
        "product_id": "",
        "relation": "adjudication_rule",
        "required": True,
        "version": "R1.2/D1.2",
    },
    {
        "ref_type": "project_document",
        "project_id": "proj-c57e28f8e0",
        "document_id": "doc-0522operator",
        "product_id": "",
        "relation": "operator_table",
        "required": True,
        "version": "R1.2/D1.2",
    },
]


LESSON = r'''---
title: "第1讲：兵棋基础与《谋战》体系认识"
status: "draft"
content_version: "course-lesson-l01-eight-chapter-pilot-v1"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
document_role: "course_lesson_plan"
lesson_id: "L01"
parent_document_id: "doc-2a28da7429f0"
parent_revision: 16
parent_content_sha256: "b35fd5152f2b25ac119e5d38fc01672a54c044950ce3026cf43fa1f128bbda19"
upstream_course_plan_id: "doc-e811bedd87f9"
upstream_course_plan_revision: 14
source_word_sha256: "7fadadc4a05f67bff1cb1ebb62c85a9bc4712644d75bd04c7a8a4b4e708dadb2"
---

# 第1讲：兵棋基础与《谋战》体系认识

> 本讲为L01理论课，共2学时（120分钟），直接执行教学进度表修订16中的L01行，主要对应CO1。课堂不登录、不操作One-Sim仿真平台和AI Planning智能筹划系统，不进行正式推演或裁决；教学重点是建立兵棋概念、课程能力路径、资料权威层级和证据表达习惯。

# 第一章 教学定位、目标与达成证据

## 一、教学定位与课前输入

L01是全课程的共同语言课，也是后续规则查用、想定分析、行动方案和专项推演的概念入口。课前输入包括课程教学计划、教学进度表和学员完成的术语预习。课堂不以记忆装备参数、历史案例结论或规则数值为目标，而是要求学员回答四个基础问题：兵棋在研究什么问题，行动受什么约束，结果如何产生，结论凭什么可以复核。

本讲结束后，学员应能够把“想定—规则—算子—裁决—记录—复盘”连接成闭环，并理解这一课程闭环与兵棋的地图、棋子、规则和随机机制等实体组成之间的区别。前者用于解释课程活动如何运行，后者用于识别一套兵棋由什么构成，两者不得混为同一分类。

## 二、教学目标

### （一）知识目标

1. 说明兵棋是以想定和战场表示为载体，在规则约束下组织决策对抗、行动实施、结果裁决与复盘分析的工具，而不是自动预测战争结局的装置。
2. 区分兵棋的实体组成视角与课程运行视角：实体组成关注想定、地图、棋子、规则和随机机制，课程运行关注想定、规则、算子、裁决、记录和复盘。
3. 说明决策、任务规划、指挥和控制在推演中的基本关系，理解计划形成、命令传递、行动执行、状态反馈和方案调整构成闭环。
4. 理解《谋战》手工兵棋、One-Sim仿真平台和AI Planning智能筹划系统在课程中的不同职责。

### （二）能力目标

1. 绘制六要素关系图，标明问题输入、行动约束、机制表达、结果生成、过程留痕和反馈改进。
2. 使用“个人基础操作—任务与战术协同—全局筹划”能力进阶模型，对典型训练问题进行分层并说明理由。
3. 使用术语辨析卡区分事实、判断、规则、裁决结果和复盘结论。
4. 使用规则来源登记表记录来源、版本、适用对象、前置条件、核验状态和禁止外推事项。

### （三）素质目标

1. 形成先查来源、再作判断，先保留原始材料、再追加修订的证据意识。
2. 认识推演结论的条件性，避免以单次胜负、软件输出或教师口述替代规则查证和专业判断。
3. 建立任务责任、协同沟通和主动纠错意识，为后续五人编组实作奠定基础。

## 三、达成证据与基本判据

| 达成事项 | 必交成果 | 基本达成判据 | 后续用途 |
| --- | --- | --- | --- |
| 概念关系 | 六要素关系图 | 六个要素齐全，箭头能够表达输入、约束、结果和反馈 | L02行动链与裁决链导入 |
| 能力递进 | 能力进阶图 | 能区分个人操作、任务战术协同和全局筹划，并说明相互依赖 | L02协同问题分析 |
| 术语边界 | 术语辨析卡 | 能区分规则、算子、裁决、记录和复盘，不用胜负替代原因分析 | L02命令链和裁决链训练 |
| 来源意识 | 规则来源登记表 | 来源、版本、对象、条件和核验状态完整；待核验内容不进入正式结论 | L03规则查用先修检查 |

本讲采用诊断性评价，不计入课程过程性实作40分。未达到基本判据不等于课程不合格，但必须在L02开始前完成针对性修订。

# 第二章 学情分析、先修条件与教学准备

## 一、学情分析

学员已经具备水面舰艇作战装备组成、基本战术运用和作战指挥常识，但可能从三个方向误解兵棋：一是把兵棋等同于棋盘和棋子的操作；二是把规则允许等同于战术合理；三是把一次推演胜负或一个软件结果等同于普遍规律。部分学员能够复述术语，却不能说明术语之间的因果和证据关系；也可能直接引用课堂经验、旧课件或口述参数，而没有确认版本、对象和适用条件。

本讲通过前测识别这些差异，不预设所有学员处于同一水平。教员应记录学员的概念薄弱项，用于L02分组提问和补练，不在课堂上按前测结果排名。

## 二、先修条件

1. 完成课程说明和兵棋、想定、规则、裁决、复盘五个术语的课前预习。
2. 能够阅读基础态势示意、理解任务、行动、结果和反馈的日常含义。
3. 知道课程资料存在正式规则、登记数据、教学参考和待核验材料等不同层级。
4. 不要求预先掌握R1.2/D1.2中的具体条目，也不要求登录任何软件系统。

## 三、教员准备

| 类别 | 准备材料 | 使用要求 |
| --- | --- | --- |
| 课程基线 | 教学计划修订14、教学进度表修订16、L01教案 | 课次名称、目标、成果和评价保持一致 |
| 规则资料 | R1.2/D1.2规则目录、R1.1/D1.1登记数据目录 | 只展示来源和结构，不进行具体参数裁决 |
| 概念材料 | 原Word教案中的兵棋定义、组成、作用、决策与指挥控制讲授线索 | 删除旧课程名称和旧学时口径；历史人物、日期和案例在引用前另行核验 |
| 课堂任务 | 三类冲突表述卡、六要素关系图、能力进阶图、术语辨析卡、来源登记表 | 不包含未经核验的武器性能和想定数据 |
| 现场保障 | 投影、白板、计时、签到、纸质备用材料 | 投影故障时可以完整转入板书和纸质流程 |

## 四、学员准备

1. 携带课堂记录工具，独立完成前测后再进入小组讨论。
2. 准备一个“经验判断可能被误当作规则”的例子，并说明自己原先依据什么作出判断。
3. 按临时学习组领取材料，本讲不分配正式推演席位，不接触后续想定隐藏信息。

## 五、预判问题与处置

| 典型问题 | 课堂表现 | 教员处置 |
| --- | --- | --- |
| 术语堆叠 | 能背概念，不能画出关系 | 要求补充箭头含义和输入输出 |
| 胜负替代分析 | 以结果好坏直接证明方案正确 | 追问关键决策、规则事件、随机因素和证据 |
| 经验替代规则 | 直接引用旧课件或口述数值 | 要求填写来源、版本、对象、条件和核验状态 |
| 软件权威化 | 认为软件显示即为正式裁决 | 回到手工规则、人工裁决和原始记录边界 |

# 第三章 教学重点、难点与关键问题

## 一、教学重点

1. 兵棋的基本含义、实体组成和运行闭环。
2. 决策、任务规划、指挥、控制与推演活动的关系。
3. 《谋战》课程中的规则权威、数据权威和证据责任。
4. 从个人操作到任务战术协同，再到全局筹划的能力递进。

## 二、教学难点

1. 理解“规则上允许”只是行动合法性的必要条件，不自动等于“战术上合理”或“任务上有效”。
2. 理解推演结果受想定、规则、决策、行动、信息条件和随机机制共同影响，不能从一次结果直接外推普遍结论。
3. 在事实、规则、推断、假设和裁决结果之间保持清楚边界。
4. 面对手工记录、软件记录和口述说明不一致时，能够先保存原态，再定位差异来源。

## 三、课堂关键问题

1. 一套兵棋需要哪些实体组成，为什么只有棋子和地图还不能形成可复核推演？
2. 课程运行六要素与兵棋实体组成分别回答什么问题？
3. 决策、任务规划、指挥和控制如何连接为一个闭环？
4. 战术上“应该做”、规则上“可以做”和裁决上“是否成功”之间是什么关系？
5. 何种材料可以直接进入正式规则查用，何种材料只能用于导入、讨论或提出待核验问题？
6. 如果软件状态与手工日志不一致，为什么不能直接选择看起来更完整的一方覆盖另一方？

# 第四章 教学内容体系与教员讲授提纲

## 一、兵棋是什么

兵棋用于在规定问题、战场表示和规则条件下组织决策对抗。参与者根据获得的信息理解任务、选择行动并承担结果；规则规定行动的适用条件、执行次序和裁决方法；记录保存命令、行动、裁决与状态变化；复盘再把结果回溯到当时的信息、判断和行动。由此，兵棋的核心不只是“模拟一个结果”，而是把决策过程置于可重复、可质询、可复核的条件中。

讲授时必须同时说明兵棋的边界。推演不是对现实战争的完整复制，推演结论只在给定想定、规则、数据、参与者和运行条件下成立。兵棋可以帮助暴露方案中的假设、冲突和薄弱环节，却不能用一次胜负直接证明某一战法普遍正确，更不能把随机裁决结果解释为确定性规律。

原Word教案以古代图上筹划、手工兵棋和计算机兵棋等线索说明兵棋形态的演进，并列出Kriegsspiel等历史材料。L01保留“兵棋从手工表示和规则对抗逐步发展到计算机辅助”的教学线索；具体人物、年代和战例只有完成来源核验后才进入课件正文，未核验时不得作为知识考查点。

## 二、兵棋的实体组成

从实体和运行载体看，可以用五类组成帮助学员建立直观认识。

1. 作战想定：规定研究或训练的问题，给出任务背景、双方条件、初始态势、时间空间边界和结束条件。想定不是完整答案，也不等于把所有隐藏信息交给参与者。
2. 兵棋地图：表示作战空间、位置关系、通行条件和需要保持一致的态势。地图形式可以不同，但必须与规则的空间语义一致。
3. 兵棋棋子与标记物：表示平台、编组、状态、事件和必要注记。棋子是对象载体，不是对象全部能力的替代说明。
4. 兵棋规则：规定组织方式、行动条件、事件顺序和裁决办法，是参与者共同遵守的约束。课程中还要区分推演规则、裁决规则及其配套数据。
5. 随机机制：在规则允许的范围内表达不确定性。随机结果只能回答本次规则事件的结果，不能替代合法性检查，也不能自行说明战术原因。

教员应通过反例说明：只有地图和棋子而没有规则，无法保证不同小组按同一条件推演；只有规则而没有记录，事后无法判断某项结果来自哪条命令和哪次裁决；只有软件画面而没有来源与版本，也不能证明数据可用于当前课程。

## 三、课程运行六要素

课程使用“想定—规则—算子—裁决—记录—复盘”六要素关系图解释一次训练如何形成闭环。

| 要素 | 主要回答的问题 | 典型输入 | 典型输出 |
| --- | --- | --- | --- |
| 想定 | 要研究或训练什么问题 | 任务、环境、编成、初态、边界 | 参与者能够理解的任务条件 |
| 规则 | 哪些行动允许、何时执行 | 规则版本、对象、状态和前置条件 | 合法行动范围和事件顺序 |
| 算子 | 机制如何被结构化表达 | 登记数据、修正条件、对象属性 | 可供人工查用和核对的机制数据 |
| 裁决 | 本次事件结果如何确定 | 合法行动、规则条目、算子和随机结果 | 事件结果及裁决依据 |
| 记录 | 过程如何留下证据 | 命令、操作、时间、状态和裁决 | 日志、态势、表单和证据编号 |
| 复盘 | 为什么形成该结果、怎样改进 | 任务、决策、行动、裁决和结果 | 差异解释、经验边界和下一版方案 |

六要素之间不是单向流水线。复盘发现的问题可能要求重新核对想定、规则或记录；规则争议可能要求冻结事件并回到裁决前状态；记录缺失可能使本来合理的结论无法复核。关系图必须画出反馈箭头，而不是只列六个名词。

## 四、决策、任务规划、指挥和控制

原Word教案把兵棋的作用与战争中的决策活动联系起来。L01将相关内容整理为四个相互联系但不能互相替代的概念。

1. 决策：决策主体根据任务、观测信息、既有知识和约束，从可选行动中作出选择。决策必须说明目标、依据和承担的风险。
2. 任务规划：在行动发生前或阶段转换时，把多个决策组织为有顺序、有条件、有责任主体的行动方案。方案不能只列动作，还要说明触发条件、预期效果和备用行动。
3. 指挥：通过权责关系和命令表达，把意图转化为组织行动。完整命令至少需要明确对象、任务、时机或触发、约束和反馈要求。
4. 控制：在行动过程中持续获得状态和结果反馈，判断行动是否偏离意图，并在授权范围内调整。控制不是替代下级决策，而是维持任务、行动和结果之间的闭环。

兵棋把上述活动置于可观察的过程之中：想定提出问题，任务规划形成方案，指挥把方案转化为命令，行动在规则约束下实施，控制根据状态反馈调整，复盘再解释关键决策与结果之间的关系。这一链条将直接进入L02的编队行动链、命令闭环和裁决流程学习。

## 五、兵棋在课程中的作用

1. 概念建构：把抽象的任务、规则、行动、裁决和证据关系转化为可视化对象和流程。
2. 方案研讨：在执行前暴露任务理解、阶段设计、责任分配和备用行动中的矛盾。
3. 协同训练：使不同席位在同一事件编号下交换信息、传递命令、执行行动和维护状态。
4. 规则训练：要求参与者在行动前查明适用条件，在行动后保存裁决依据，而不是凭经验直接报出结果。
5. 复盘改进：保存初始方案和原始表现，通过关键事件时间线说明有效决策、失效决策及其条件。

讲授时应把“教学培训、方案研讨、行动复盘”作为主要应用场景，不展开未经核验的历史战例结论。历史材料可以用于提出问题，但不能替代当前课程规则、数据和想定。

## 六、《谋战》课程能力进阶

### （一）个人基础操作

这一层解决“能否准确完成单项任务”。主要包括识别组件、查找规则、维护地图与标记、填写日志、执行随机裁决和保存证据。个人操作不熟练会造成事件遗漏、状态冲突和规则查用错误，是后续协同训练的基础。

### （二）任务与战术协同

这一层解决“不同力量和席位如何围绕同一任务相互支撑”。重点不是把问题按平台类型分开，而是识别侦察、指挥、机动、火力、防护、裁决和记录之间的依赖关系。一个席位完成自身动作，并不自动代表编队任务得到推进。

### （三）全局筹划

这一层解决“如何围绕主要任务配置力量、安排阶段、控制节奏并保留后续能力”。学员需要识别关键问题、设计触发条件、比较方案风险并形成备用行动。全局筹划依赖个人操作和任务协同提供可靠状态与证据，不能脱离前两层单独存在。

能力进阶图应同时画出向上的支撑关系和向下的约束关系：全局方案规定任务和阶段，任务协同把方案转化为席位责任，个人操作提供准确执行和记录；任何一层的错误都可能通过事件链影响最终结果。

## 七、规则、数据与材料的权威层级

| 层级 | 材料 | 允许用途 | 禁止事项 |
| --- | --- | --- | --- |
| 课程权威 | 教学计划修订14、教学进度表修订16 | 确定课程目标、课次、成果、评价和移交 | 下位教案自行改变课程基线 |
| 规则与数据权威 | R1.2/D1.2规则、课程登记的R1.1/D1.1数据 | 规则查用、人工裁决和数据核对 | 用旧版本或口述数值覆盖登记版本 |
| 原始教案参考 | 第1讲原Word教案及其内嵌图示 | 恢复兵棋定义、组成、作用和决策活动的讲授线索 | 带回旧课程名称、旧学时或未核验历史结论 |
| 教学参考 | 既往课件、讲解稿、历史案例 | 导入、比较、提出问题 | 直接进入正式裁决或考核答案 |
| 待核验材料 | 口述参数、来源不清的图表和数值 | 登记问题和安排查证 | 作为事实、规则或裁决依据 |

## 八、推演结论的解释边界

面对一个推演结果，至少从六个方面追问：任务是否理解一致，信息是否完整且权限合规，行动是否符合规则，裁决是否按正确条目和数据执行，随机因素影响了什么，记录是否足以复核。只有把这些条件说清楚，才能讨论方案在本次想定中的表现。

因此，本讲要求学员把结论写成有条件的表达。例如，“在给定想定和规则条件下，该方案在某事件中保持了行动连续性”，而不是“该方案一定更优”。如果证据不足，应明确写为待核验问题，不得补造解释。

# 第五章 课堂过程、师生活动与120分钟脚本

## 一、时间分配与课堂脚本

| 时间 | 教学环节 | 教员活动 | 学员活动 | 当堂成果与检查点 |
| --- | --- | --- | --- | --- |
| 0—8分钟 | 情境导入与前测 | 展示同一事件的事实描述、经验判断和规则表述，说明本讲诊断规则 | 独立分类并写出依据 | 前测卡；记录基线，不排名、不计分 |
| 8—25分钟 | 兵棋含义与实体组成 | 结合原Word讲授线索说明兵棋边界和五类实体组成，使用“只有棋子没有规则”等反例 | 完成实体组成速记图，提出一个缺失要素造成的问题 | 能区分对象载体、规则和结果 |
| 25—42分钟 | 课程运行六要素 | 逐项说明想定、规则、算子、裁决、记录和复盘，示范反馈箭头 | 绘制六要素关系图并说明两条反馈关系 | 关系图包含输入、约束、结果和反馈 |
| 42—58分钟 | 决策活动与能力进阶 | 讲解决策、任务规划、指挥、控制，映射个人操作、任务战术和全局筹划 | 把三类问题卡放入能力进阶图并说明理由 | 不按平台名称简单分类 |
| 58—75分钟 | 权威层级与来源登记 | 对比课程权威、规则数据权威、原始教案参考、教学参考和待核验材料 | 完成术语辨析卡和一条规则来源登记 | 写明版本、对象、条件、核验状态和禁止外推 |
| 75—95分钟 | 编队事件概念任务 | 发布不含具体性能数值的事件，要求从任务、行动、规则、证据和复盘组织回答 | 小组形成概念分析卡，标记事实、规则、推断和假设 | 每项结论可回指材料或显式标记待核验 |
| 95—110分钟 | 汇报、质询与修订 | 按“依据是什么—适用条件是什么—缺少什么证据”组织交叉质询 | 展示关系图和辨析卡，保留初稿并追加修订 | 初稿、质询意见和修订痕迹同时保留 |
| 110—120分钟 | 退出测验与L02移交 | 发布退出测验，归纳L02行动链、命令链和裁决链入口 | 独立作答，提交四项必交成果和个人薄弱项 | 形成L02诊断名单和输入包 |
| 合计 | 120分钟 | 完成理论讲授、诊断与移交 | 形成四项必交成果 | 达到L02共同语言要求 |

## 二、时间控制原则

1. 讲授与任务交替进行，单次连续讲授不超过20分钟。
2. 历史线索只承担导入功能，不挤占关系建模和来源登记时间。
3. 75分钟后进入同一概念任务，不临时增加装备参数计算或软件演示。
4. 110分钟必须停止小组讨论，保留10分钟完成个人退出测验和成果移交。

## 三、板书主线

左侧板书“实体组成：想定—地图—棋子—规则—随机机制”；中部板书“课程运行：想定→规则→算子→裁决→记录→复盘↺”；右侧板书“能力进阶：个人基础操作→任务与战术协同→全局筹划”。三部分用“对象、活动、能力”三个标签区分，防止学员把不同分类混为一谈。

# 第六章 教学方法、组织实施与人机协同边界

## 一、教学方法

1. 概念图法：通过实体组成图、六要素关系图和能力进阶图建立多个概念之间的结构关系。
2. 反例辨析法：使用“规则允许但任务无效”“结果成功但证据不足”“软件有记录但来源不明”等反例纠正简单化理解。
3. 来源对照法：让学员比较正式规则、登记数据、原Word教案、既往课件和口述材料，判断其允许用途。
4. 任务驱动法：围绕一个不含具体性能数值的编队事件，要求学员建立任务、规则、证据和复盘问题之间的联系。
5. 形成性诊断：用前测、课堂观察、成果卡和退出测验形成L02分层辅导依据，不把诊断结果直接换算为课程成绩。

## 二、课堂组织

本讲采用个人作答、临时学习组讨论和全班质询三种组织形式。临时学习组只用于概念交流，不等同后续实作中的正式五人席位。教员负责控制来源边界和概念纠偏，助教或记录人员负责收集成果、登记缺项和形成L02诊断名单。

## 三、人机协同边界

1. 《谋战》手工兵棋是后续规则查用、操作实施和人工裁决的原始依据；L01只认识其体系位置，不进行规则数值查算。
2. One-Sim仿真平台在后续课程中用于想定与状态的结构化表达、事件记录、过程回放和统计核对。它不是规则权威，不得补造想定信息、泄露隐藏态势或覆盖手工原始记录。
3. AI Planning智能筹划系统在后续课程中用于方案结构化表达、约束检查、方案比较和复盘辅助。它不得代替指挥员作出课程要求的决策，不得把缺失信息写成事实，也不得直接生成课程成绩。
4. L01不登录、不操作上述系统。可以在课程能力路径图中标明其后续用途，但不展示未经确认的系统版本、账号、界面能力或自动化结论。
5. 软件与手工记录发生差异时，后续课程统一执行“冻结事件—保留双方原始材料—核对时间、字段、录入和规则适用—追加差异说明—人工决定处置”，任何一方都不得静默覆盖另一方。

## 四、异常与备用流程

投影不可用时，使用白板三条主线和纸质材料继续全部教学任务；规则目录版本不一致时，只进行来源与版本辨析，不展示冲突条目；材料不足时优先保证每名学员完成术语卡和来源登记表，小组关系图可共用；发现隐藏信息误发或来源不明的具体参数时立即收回材料并登记，不继续围绕该信息讨论。

# 第七章 学习成果、评价量规、课后任务与下讲移交

## 一、必交成果

| 成果 | 责任单位 | 最低要求 | 保存方式 |
| --- | --- | --- | --- |
| 六要素关系图 | 每组1份 | 六要素齐全，至少包含输入、约束、结果和反馈箭头 | 保留初稿和质询后修订稿 |
| 能力进阶图 | 每组1份 | 三个能力层级边界清楚，能够说明上下层依赖 | 与L02协同问题卡一并移交 |
| 术语辨析卡 | 每人1份 | 规则、算子、裁决、记录、复盘的区别准确 | 个人课程档案 |
| 规则来源登记表 | 每人1份 | 来源、版本、对象、条件、核验状态和禁止外推完整 | L03先修检查资料 |

课堂中的编队事件概念分析卡属于辅助练习，不新增为进度表之外的必交成果，其观察结果写入教员诊断记录。

## 二、诊断量规

| 维度 | 达到 | 基本达到 | 需要补强 |
| --- | --- | --- | --- |
| 概念关系 | 能解释六要素及反馈关系 | 要素基本齐全，部分关系不清 | 只列术语或混淆实体组成与运行要素 |
| 能力分层 | 能按问题层级分类并说明依赖 | 分类基本正确，理由不充分 | 只按平台或专业类别分类 |
| 来源权威 | 能说明材料层级、版本和适用条件 | 能识别权威与参考，但登记不完整 | 把旧课件、口述或软件显示当正式依据 |
| 证据表达 | 结论可回指来源，未知项显式标记 | 大部分结论有依据 | 用胜负、直觉或完整表述掩盖证据缺口 |

需要补强者在L02开始前修订对应成果；修订件作为追加证据保存，不覆盖L01原始表现。

## 三、退出测验

1. 分别说明兵棋实体组成视角和课程运行六要素视角回答什么问题。
2. 为什么规则上允许并不自动等于战术上合理？
3. 写出引用一条规则或数据时至少需要登记的五项信息。
4. 说明推演结果为什么必须与想定、规则、决策、行动、随机机制和记录条件一起解释。
5. 说明One-Sim仿真平台和AI Planning智能筹划系统在课程中的职责边界。

## 四、课后任务

每名学员选择一个编队作战问题，完成“任务目的—关键行动—需查规则—应留证据—复盘问题”五联卡。不得填入未经核验的具体性能数值；引用历史案例、旧课件或口述材料时，必须标记为教学参考或待核验材料。

## 五、向L02移交

L01向L02移交六要素关系图、能力进阶图、术语辨析卡、规则来源登记表、退出测验结果和教员诊断名单，形成教学进度表规定的“L02行动链与裁决链”输入。L02据此组织编队行动链、命令闭环与人工裁决流程分析。移交只说明学员需要补强的概念和证据能力，不公开个人排名，不改变L02“诊断、不计分”的评价口径。

# 第八章 来源依据、配套材料与课后反思

## 一、来源依据与使用范围

| 来源 | 版本或哈希 | 本讲允许使用的内容 | 使用限制 |
| --- | --- | --- | --- |
| 课程教学计划 `doc-e811bedd87f9` | 修订14；`f315d92c…bfb5623` | 课程目标、20学时结构、平台职责、评价边界 | 上游课程权威，不由L01修改 |
| 教学进度表 `doc-2a28da7429f0` | 修订16；`b35fd515…28bbda19` | L01输入、CO1、活动、四项成果、诊断评价和L02移交 | L01直接父文档 |
| 原Word《第1讲-兵棋概述》 | `7fadadc4…708dadb2` | 兵棋含义、组成、作用、决策、任务规划、指挥控制和讲授线索 | 旧课程名称、旧学时、未核验历史结论和版式不回写 |
| 《谋战》规则文档 | R1.2/D1.2 | 规则结构、对象和适用条件意识 | L01不进行具体条目裁决 |
| 课程登记裁决与算子数据 | R1.1/D1.1 | 数据版本和登记意识 | L01不展示或记忆具体参数 |

原Word是本讲知识内容的重要参考，但不是课程目标、课次和评价口径的当前权威。课程计划和进度表负责“本讲必须教到什么、形成什么成果”；原Word负责提供已有讲授积累；规则和登记数据负责约束后续正式查用。四类来源的职责必须分开记录。

## 二、配套材料清单

1. 前测卡与退出测验。
2. 兵棋实体组成速记图、六要素关系图和能力进阶图。
3. 术语辨析卡、规则来源登记表和编队事件概念分析卡。
4. 课程能力路径图、L02行动链与裁决链预告页。
5. 原Word内嵌图片候选清单和图源核验记录。

## 三、插图锚点

| 编号 | 拟表达内容 | 来源与处理 | 写入条件 |
| --- | --- | --- | --- |
| L01-F01 | 兵棋实体组成五类要素 | 从原Word内嵌图片中筛选，必要时按当前术语重绘 | 图源、文字和课程口径核验通过 |
| L01-F02 | 课程运行六要素闭环 | 依据本讲第四章重新绘制 | 六要素和反馈箭头与正文一致 |
| L01-F03 | 三级能力进阶模型 | 依据教学计划和本讲正文重新绘制 | 不按平台简单分类，包含上下层依赖 |

本阶段只登记插图锚点，不把未经检查的旧图直接嵌入结构化正文。图示进入正式教案前应形成图题、来源、替代文本和逐页渲染检查记录。

## 四、课后反思记录

| 反思项 | 记录问题 |
| --- | --- |
| 概念达成 | 哪两个概念最容易混淆，错误来自术语、关系还是例子？ |
| 时间执行 | 哪一环节超时或不足，是否影响四项成果提交？ |
| 来源边界 | 是否出现把旧材料、口述或软件显示当作正式依据的情况？ |
| 学员差异 | 哪些学员需要在L02前补强概念关系、来源登记或证据表达？ |
| 材料改进 | 哪张图、卡片或反例需要修改，修改是否会影响教学计划或进度表？ |

教员课后只追加反思和勘误，不覆盖前测、课堂成果和退出测验原件。涉及课程目标、学时、成果或评价口径的变化，必须回到教学计划和进度表履行变更控制，不在L01中悄然修改。
'''


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _working_path(project: dict[str, Any], document_id: str) -> Path:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    path = Path(str(manifest.get("working_markdown") or ""))
    if not path.is_file():
        raise RuntimeError(f"工作稿不存在：{document_id} {path}")
    return path


def _state_evidence(project: dict[str, Any], document_id: str) -> dict[str, Any]:
    state = writing_collaboration_service.get_state(project, document_id)
    path = _working_path(project, document_id)
    return {
        "document_id": document_id,
        "revision": int(state.get("document_revision") or 0),
        "content_sha256": writing_collaboration_service.codec.document_sha256(state["document"]),
        "working_markdown": str(path),
        "working_sha256": _sha256(path),
        "projection_revision": int((state.get("projection") or {}).get("revision") or 0),
        "projection_status": str((state.get("projection") or {}).get("status") or ""),
        "approved_revision": int(state.get("approved_revision") or 0),
        "published_revision": int(state.get("published_revision") or 0),
    }


def _assert_state(evidence: dict[str, Any], revision: int, content_sha: str, working_sha: str) -> None:
    expected = {
        "revision": revision,
        "content_sha256": content_sha,
        "working_sha256": working_sha,
        "projection_revision": revision,
        "projection_status": "current",
        "approved_revision": 0,
        "published_revision": 0,
    }
    mismatches = {key: (evidence.get(key), value) for key, value in expected.items() if evidence.get(key) != value}
    if mismatches:
        raise RuntimeError(f"生产基线已变化，停止迁移：{evidence['document_id']} {mismatches}")


def _validate_frozen_inputs(
    project: dict[str, Any],
    target_content_sha: str,
    target_working_sha: str,
) -> dict[str, Any]:
    plan = _state_evidence(project, COURSE_PLAN_ID)
    schedule = _state_evidence(project, SCHEDULE_ID)
    l01 = _state_evidence(project, DOCUMENT_ID)
    _assert_state(plan, COURSE_PLAN_REVISION, COURSE_PLAN_CONTENT_SHA256, COURSE_PLAN_WORKING_SHA256)
    _assert_state(schedule, SCHEDULE_REVISION, SCHEDULE_CONTENT_SHA256, SCHEDULE_WORKING_SHA256)
    if l01["revision"] == L01_BASE_REVISION:
        _assert_state(l01, L01_BASE_REVISION, L01_BASE_CONTENT_SHA256, L01_BASE_WORKING_SHA256)
    elif l01["revision"] == L01_INTERIM_REVISION:
        _assert_state(
            l01,
            L01_INTERIM_REVISION,
            L01_INTERIM_CONTENT_SHA256,
            L01_INTERIM_WORKING_SHA256,
        )
    elif not all(
        [
            l01["content_sha256"] == target_content_sha,
            l01["working_sha256"] == target_working_sha,
            l01["projection_revision"] == l01["revision"],
            l01["projection_status"] == "current",
            l01["approved_revision"] == 0,
            l01["published_revision"] == 0,
        ]
    ):
        raise RuntimeError(f"L01不是冻结基线或本脚本目标修订，停止迁移：{l01}")
    if not SOURCE_WORD.is_file() or _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError(f"L01原Word来源已变化：{SOURCE_WORD}")
    return {"course_plan": plan, "schedule": schedule, "l01": l01, "source_word_sha256": SOURCE_WORD_SHA256}


def _other_lesson_states(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for lesson, (document_id, revision, content_sha) in OTHER_LESSONS.items():
        state = writing_collaboration_service.get_state(project, document_id)
        current_revision = int(state.get("document_revision") or 0)
        current_sha = writing_collaboration_service.codec.document_sha256(state["document"])
        if current_revision != revision or current_sha != content_sha:
            raise RuntimeError(
                f"{lesson}基线已变化，停止L01单文档迁移："
                f"revision={current_revision}, sha={current_sha}"
            )
        result[lesson] = {"document_id": document_id, "revision": revision, "content_sha256": content_sha}
    return result


def _chapter_body(markdown: str, title: str) -> str:
    marker = f"# {title}\n"
    if marker not in markdown:
        return ""
    tail = markdown.split(marker, 1)[1]
    next_heading = re.search(r"(?m)^# ", tail)
    return tail[: next_heading.start()] if next_heading else tail


def _checks(markdown: str) -> dict[str, Any]:
    h1 = [line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")]
    chapters = [title for title in h1 if title in CHAPTER_TITLES]
    intervals = [
        (int(start), int(end))
        for start, end in re.findall(r"(?m)^\| (\d+)—(\d+)分钟 \|", markdown)
    ]
    banned = [
        "0522",
        "水面舰艇指挥决策与兵棋推演",
        "兵棋推演与智能决策",
        "共10学时",
        "合计16学时",
        "理论10＋实作10",
        "第11讲",
        "12回合",
        "固定两波次",
        "机场",
    ]
    required_outputs = ["六要素关系图", "能力进阶图", "术语辨析卡", "规则来源登记表"]
    chapter4 = _chapter_body(markdown, CHAPTER_TITLES[3])
    chapter5 = _chapter_body(markdown, CHAPTER_TITLES[4])
    chapter6 = _chapter_body(markdown, CHAPTER_TITLES[5])
    chapter7 = _chapter_body(markdown, CHAPTER_TITLES[6])
    chapter8 = _chapter_body(markdown, CHAPTER_TITLES[7])
    return {
        "content_version": CONTENT_VERSION in markdown,
        "document_title": DOCUMENT_TITLE in markdown,
        "parent_schedule": all(
            token in markdown
            for token in [SCHEDULE_ID, "parent_revision: 16", SCHEDULE_CONTENT_SHA256]
        ),
        "upstream_plan": COURSE_PLAN_ID in markdown and "upstream_course_plan_revision: 14" in markdown,
        "source_word": SOURCE_WORD_SHA256 in markdown,
        "chapter_count": len(chapters),
        "chapter_order": chapters,
        "chapter_order_valid": chapters == CHAPTER_TITLES,
        "intervals": intervals,
        "intervals_valid": intervals == [(0, 8), (8, 25), (25, 42), (42, 58), (58, 75), (75, 95), (95, 110), (110, 120)],
        "minutes_total": sum(end - start for start, end in intervals),
        "required_outputs": {token: markdown.count(token) for token in required_outputs},
        "schedule_outputs_present": all(markdown.count(token) >= 3 for token in required_outputs),
        "diagnostic_not_scored": all(token in markdown for token in ["诊断性评价", "不计入课程过程性实作40分", "诊断、不计分"]),
        "quality_sections": all(token in markdown for token in ["教学目标", "学情分析", "教学重点", "教学难点", "教学内容", "教学方法", "时间分配", "课后任务", "来源依据"]),
        "handoff_l02": all(token in chapter7 for token in ["向L02移交", "L02行动链", "命令闭环", "人工裁决流程"]),
        "platform_boundary": all(
            token in chapter6
            for token in [
                "One-Sim仿真平台",
                "AI Planning智能筹划系统",
                "L01不登录、不操作上述系统",
                "不得补造想定信息",
                "不得直接生成课程成绩",
            ]
        ),
        "content_depth": {
            "total_chars": len(markdown),
            "chapter4_chars": len(chapter4),
            "chapter5_chars": len(chapter5),
            "chapter6_chars": len(chapter6),
            "chapter7_chars": len(chapter7),
            "chapter8_chars": len(chapter8),
        },
        "content_depth_valid": len(markdown) >= 10000 and len(chapter4) >= 3000 and len(chapter5) >= 1000,
        "source_scope": all(token in chapter8 for token in ["修订14", "修订16", "原Word", "插图锚点", "课后反思"]),
        "banned_hits": [token for token in banned if token in markdown],
    }


def _checks_pass(checks: dict[str, Any]) -> bool:
    return all(
        [
            checks["content_version"],
            checks["document_title"],
            checks["parent_schedule"],
            checks["upstream_plan"],
            checks["source_word"],
            checks["chapter_count"] == 8,
            checks["chapter_order_valid"],
            checks["intervals_valid"],
            checks["minutes_total"] == 120,
            checks["schedule_outputs_present"],
            checks["diagnostic_not_scored"],
            checks["quality_sections"],
            checks["handoff_l02"],
            checks["platform_boundary"],
            checks["content_depth_valid"],
            checks["source_scope"],
            not checks["banned_hits"],
        ]
    )


def _target_hashes(markdown: str) -> tuple[str, str]:
    document = writing_collaboration_service.codec.from_markdown(
        markdown,
        namespace=f"{PROJECT_ID}/{DOCUMENT_ID}/authority-import",
    )
    canonical_markdown = writing_collaboration_service.codec.to_markdown(document)
    return (
        writing_collaboration_service.codec.document_sha256(document),
        hashlib.sha256(canonical_markdown.encode("utf-8")).hexdigest(),
    )


def _lineage(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": "surface-wargame-course-lessons",
        "edition_label": "schedule-r16",
        "sequence": 1,
        "source_type": "structured_authority",
        "parent_document_id": SCHEDULE_ID,
        "source_checksum": schedule["content_sha256"],
        "generated_at": GENERATED_AT,
        "source_paths": [schedule["working_markdown"]],
    }


def _structure_metadata(inputs: dict[str, Any], target_sha: str) -> dict[str, Any]:
    return {
        "schema": "openclaw.course-lesson-structure.v1",
        "content_version": CONTENT_VERSION,
        "lesson_id": "L01",
        "chapter_count": 8,
        "chapter_titles": CHAPTER_TITLES,
        "direct_parent": {
            "document_id": SCHEDULE_ID,
            "revision": SCHEDULE_REVISION,
            "content_sha256": SCHEDULE_CONTENT_SHA256,
            "working_sha256": SCHEDULE_WORKING_SHA256,
        },
        "upstream_course_plan": {
            "document_id": COURSE_PLAN_ID,
            "revision": COURSE_PLAN_REVISION,
            "content_sha256": COURSE_PLAN_CONTENT_SHA256,
        },
        "source_word": {
            "path": str(SOURCE_WORD),
            "sha256": SOURCE_WORD_SHA256,
            "use_mode": "curated_content_reference",
            "excluded": ["old_course_name", "old_hours", "unverified_history", "legacy_layout"],
        },
        "schedule_contract": {
            "input": ["课程计划", "术语预习"],
            "objective": ["CO1"],
            "outputs": ["六要素关系图", "能力进阶图", "术语辨析卡", "规则来源登记表"],
            "evaluation": "diagnostic_not_scored",
            "handoff": "L02行动链与裁决链",
        },
        "target_content_sha256": target_sha,
        "generated_at": GENERATED_AT,
        "validated_parent_revision": inputs["schedule"]["revision"],
    }


def _binding_is_current(binding: dict[str, Any]) -> bool:
    return all(
        [
            binding.get("mode") == "derived",
            binding.get("source_document_id") == SCHEDULE_ID,
            binding.get("referenced_document_revision") == f"v{SCHEDULE_REVISION}",
            binding.get("referenced_document_sha256") == SCHEDULE_WORKING_SHA256,
            binding.get("reference_status") == "current",
            binding.get("status") == "aligned",
            binding.get("integrity_status") == "aligned",
            binding.get("mapped_items") == 1,
            not binding.get("unmapped_items"),
            not binding.get("changed_sections"),
        ]
    )


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise RuntimeError(f"项目不存在：{project_id}")

    target = LESSON.strip() + "\n"
    checks = _checks(target)
    if not _checks_pass(checks):
        raise RuntimeError(f"L01目标正文自检未通过：{checks}")
    target_sha, target_working_sha = _target_hashes(target)
    inputs = _validate_frozen_inputs(project, target_sha, target_working_sha)
    other_before = _other_lesson_states(project)

    current_path = _working_path(project, DOCUMENT_ID)
    before = current_path.read_text(encoding="utf-8")
    before_state = writing_collaboration_service.get_state(project, DOCUMENT_ID)
    before_document = multi_document_service.get_document(project, DOCUMENT_ID)
    before_binding = multi_document_service.structure_binding(project, DOCUMENT_ID)
    lineage = _lineage(inputs["schedule"])
    structure_metadata = _structure_metadata(inputs, target_sha)
    metadata = before_document.get("metadata") or {}

    before_content_sha = writing_collaboration_service.codec.document_sha256(before_state["document"])
    content_changed = before_content_sha != target_sha
    catalog_changed = any(
        [
            before_document.get("title") != DOCUMENT_TITLE,
            int(before_document.get("expected_chapters") or 0) != 8,
            before_document.get("rules_version") != "R1.2",
            before_document.get("data_version") != "course-baseline-20h-v4",
            before_document.get("publication_status") != "draft",
            before_document.get("source_refs") != SOURCE_REFS,
            before_document.get("lineage") != lineage,
        ]
    )
    metadata_changed = any(
        [
            metadata.get("last_actor") != ACTOR,
            metadata.get("course_lesson_structure") != structure_metadata,
            metadata.get("content_fidelity_current_status") != "curated_revision_requires_docx_release_qa",
        ]
    )
    binding_changed = not _binding_is_current(before_binding)
    context = copy.deepcopy(project.get("context") or {})
    desired_context = {
        "current_delivery_phase": PHASE_LABEL,
        "course_lesson_pilot_status": "L01_draft_ready_for_review",
        "next_step": "只读评审L01八章样板的浏览器呈现、内容边界和来源说明；通过后按同一契约修订L02，L03继续隔离错配Word正文。",
    }
    context_changed = any(context.get(key) != value for key, value in desired_context.items())

    preview = {
        "phase": PHASE_LABEL,
        "dry_run": dry_run,
        "document_id": DOCUMENT_ID,
        "frozen_inputs": inputs,
        "before_revision": int(before_state.get("document_revision") or 0),
        "before_content_sha256": before_content_sha,
        "before_working_sha256": _sha256(current_path),
        "before_chars": len(before),
        "after_chars": len(target),
        "target_content_sha256": target_sha,
        "content_changed": content_changed,
        "catalog_changed": catalog_changed,
        "metadata_changed": metadata_changed,
        "binding_changed": binding_changed,
        "context_changed": context_changed,
        "before_binding": before_binding,
        "other_lessons": other_before,
        "checks": checks,
    }
    if dry_run or not any([content_changed, catalog_changed, metadata_changed, binding_changed, context_changed]):
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

    _validate_frozen_inputs(project, target_sha, target_working_sha)
    if catalog_changed:
        multi_document_service.update_document(
            project,
            DOCUMENT_ID,
            {
                "title": DOCUMENT_TITLE,
                "expected_chapters": 8,
                "rules_version": "R1.2",
                "data_version": "course-baseline-20h-v4",
                "publication_status": "draft",
                "source_refs": SOURCE_REFS,
                "lineage": lineage,
            },
        )
        project = project_manager.get_project(project_id) or project
    if metadata_changed:
        multi_document_service.update_document_metadata(
            project,
            DOCUMENT_ID,
            {
                "last_actor": ACTOR,
                "course_lesson_structure": structure_metadata,
                "content_fidelity_current_status": "curated_revision_requires_docx_release_qa",
            },
        )
        project = project_manager.get_project(project_id) or project
    if binding_changed:
        multi_document_service.set_structure_binding(
            project,
            DOCUMENT_ID,
            {
                "mode": "derived",
                "source_document_id": SCHEDULE_ID,
                "status": "aligned",
                "integrity_status": "aligned",
                "reference_status": "current",
                "mapped_items": 1,
                "unmapped_items": [],
                "changed_sections": [],
            },
        )
        project = project_manager.get_project(project_id) or project
    if context_changed:
        context.update(desired_context)
        project_manager.update_project(
            project_id,
            {"context": context, "current_phase": "course_lesson_l01_eight_chapter_pilot"},
        )

    refreshed = project_manager.get_project(project_id) or project
    document_workspace_service.ensure_workspace(
        multi_document_service.rich_project_context(refreshed, DOCUMENT_ID)
    )
    after_path = _working_path(refreshed, DOCUMENT_ID)
    after = after_path.read_text(encoding="utf-8")
    after_state = writing_collaboration_service.get_state(refreshed, DOCUMENT_ID)
    after_document = multi_document_service.get_document(refreshed, DOCUMENT_ID)
    final_binding = multi_document_service.structure_binding(refreshed, DOCUMENT_ID)
    after_checks = _checks(after)
    other_after = _other_lesson_states(refreshed)

    if not _checks_pass(after_checks):
        raise RuntimeError(f"写入后内容自检未通过：{after_checks}")
    if writing_collaboration_service.codec.document_sha256(after_state["document"]) != target_sha:
        raise RuntimeError("写入后结构化正文SHA与dry-run目标不一致")
    if not _binding_is_current(final_binding):
        raise RuntimeError(f"写入后结构绑定未对齐：{final_binding}")
    if after_document.get("lineage") != lineage:
        raise RuntimeError(f"写入后lineage不一致：{after_document.get('lineage')}")
    if other_after != other_before:
        raise RuntimeError("L02—L10状态发生变化，违反单文档迁移边界")
    if _sha256(SOURCE_WORD) != SOURCE_WORD_SHA256:
        raise RuntimeError("L01原Word在迁移期间发生变化")

    return {
        **preview,
        "dry_run": False,
        "snapshot": str(snapshot),
        "after_revision": int(after_state.get("document_revision") or 0),
        "after_content_sha256": writing_collaboration_service.codec.document_sha256(after_state["document"]),
        "after_working_sha256": _sha256(after_path),
        "projection_revision": (after_state.get("projection") or {}).get("revision"),
        "projection_status": (after_state.get("projection") or {}).get("status"),
        "approved_revision": after_state.get("approved_revision"),
        "published_revision": after_state.get("published_revision"),
        "expected_chapters": after_document.get("expected_chapters"),
        "publication_status": after_document.get("publication_status"),
        "lineage": after_document.get("lineage"),
        "binding": final_binding,
        "other_lessons_unchanged": other_after == other_before,
        "source_word_unchanged": _sha256(SOURCE_WORD) == SOURCE_WORD_SHA256,
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
