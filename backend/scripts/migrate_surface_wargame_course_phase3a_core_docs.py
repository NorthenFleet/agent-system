#!/usr/bin/env python3
"""Deepen the four course core documents for classroom-ready delivery."""

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


PHASE_LABEL = "课程开学准备第三阶段A：理论教学核心文档深化"
CONTENT_VERSION = "surface-course-open-ready-v1"
TARGETS = {
    "doc-e811bedd87f9": "教学计划",
    "doc-2a28da7429f0": "教学进度表",
    "doc-3a9dbb65b9a3": "第1讲教案",
    "doc-6085f649c11a": "第2讲教案",
}


def _current_markdown(project: dict[str, Any], document_id: str) -> str:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    working = Path(str(manifest.get("working_markdown") or ""))
    if not working.is_file():
        raise RuntimeError(f"工作稿不存在：{document_id} {working}")
    return working.read_text(encoding="utf-8")


def _set_content_version(markdown: str) -> str:
    if re.search(r"(?m)^content_version:", markdown):
        return re.sub(
            r'(?m)^content_version:\s*.*$',
            f'content_version: "{CONTENT_VERSION}"',
            markdown,
            count=1,
        )
    return markdown.replace("---\n\n# ", f'content_version: "{CONTENT_VERSION}"\n---\n\n# ', 1)


def _course_plan(markdown: str) -> str:
    value = _set_content_version(markdown)
    old_row = "| 第3讲 | 《谋战》组件、地图、棋子与规则查用 | 《谋战》手工兵棋实作 | 2 | 不安排软件操作，重点建立课程框架、规则意识和裁决方法。 |"
    new_row = "| 第3讲 | 《谋战》组件、地图、棋子与规则查用 | 《谋战》手工兵棋实作 | 2 | 不安排软件操作；完成组件清点、版本确认和规则索引卡，为后续事件字段映射建立对象与规则基线。 |"
    if old_row not in value and new_row not in value:
        raise RuntimeError("教学计划未找到第3讲实施表目标行")
    value = value.replace(old_row, new_row)
    marker = "## 八、开学执行准备与应急处置"
    value = value.split(marker, 1)[0].rstrip()
    section = """
## 八、开学执行准备与应急处置

### （一）开课确认表

| 确认事项 | 责任人 | 最迟完成时点 | 验收标准 | 当前状态 |
| --- | --- | --- | --- | --- |
| 日期、班次、场地与课表 | 课程负责人 | 开课前7日 | 与教务排课一致并写入教学进度表 | 待排课确认 |
| 分组与五人席位轮换 | 任课教员 | 开课前3日 | 每组人员、初始席位和轮换次序明确 | 待名单确认 |
| 《谋战》三册规则与登记数据 | 规则管理员 | 开课前3日 | R1.2/D1.2及R1.1/D1.1校验值一致 | 待现场核验 |
| 地图、棋子、标记物和记录表 | 器材管理员 | 每次实作前 | 数量完整、编号清楚、备用件可用 | 逐次确认 |
| one-sim与智能筹划软件 | 软件保障员 | 第4次课前 | 版本、账号、想定包、时间字段和导出路径可用 | 待环境确认 |
| 形成性评价与综合考核材料 | 任课教员、评分员 | 开课前3日 | 过程记录表、统一量规和证据目录齐全 | 待课程组复核 |

### （二）异常处置原则

1. 规则或数据版本不一致时立即停止裁决，冻结当前事件，完成版本核验后再恢复。
2. 软件不可用时继续保留手工推演和原始记录，软件任务转为课后补录与差异复核，不改变手工裁决结果。
3. 器材缺失、关键证据中断或席位职责冲突时暂停计时，由导演部记录原因、恢复点和处置结果。
4. 未确认的历史参数、口述数值和其他想定数据一律标记为“待核验”，不得临时拼接进入0522裁决。
5. 任何补记、勘误和补练均追加保存，不覆盖原始记录；发布、批准和最终成绩确认继续由人工完成。
""".strip()
    return value + "\n\n" + section + "\n"


def _schedule(markdown: str) -> str:
    value = _set_content_version(markdown)
    frontmatter = value.split("---", 2)[1] if value.startswith("---") else ""
    if "rules_version:" not in frontmatter:
        value = value.replace(
            'data_version: "course-baseline-20h-v4"\n',
            'data_version: "course-baseline-20h-v4"\nrules_version: "R1.2/D1.2"\n',
            1,
        )
    old_row = "| 3 | 第3次课 | 《谋战》组件、地图、棋子与规则查用 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 不安排软件操作，重点建立课程框架、规则意识和裁决方法。 | 组件清点表、规则索引卡 |"
    new_row = "| 3 | 第3次课 | 《谋战》组件、地图、棋子与规则查用 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 不安排软件操作；完成组件清点、版本确认和规则索引卡，为后续事件字段映射建立对象与规则基线。 | 组件清点表、规则索引卡 |"
    if old_row not in value and new_row not in value:
        raise RuntimeError("教学进度表未找到第3讲目标行")
    value = value.replace(old_row, new_row)
    marker = "# 第三章 逐讲达成检查与开课运行"
    value = value.split(marker, 1)[0].rstrip()
    section = """
# 第三章 逐讲达成检查与开课运行

## 一、开课运行字段

| 字段 | 内容 |
| --- | --- |
| 学期与起止周 | 待本学期排课确认 |
| 上课日期与节次 | 待本学期排课确认 |
| 班次与人数 | 待学员名单确认 |
| 理论课教室 | 待场地确认 |
| 兵棋实作场地 | 待场地与器材确认 |
| 任课教员、导演与评分员 | 待课程组确认 |
| 软件环境与账号 | 第4次课前完成现场确认 |

## 二、逐讲达成检查

| 讲次 | 课前输入 | 课堂达成关口 | 验收证据 | 未达标处置 |
| --- | --- | --- | --- | --- |
| L01 | 课程说明、术语预习 | 能区分战术原理、规则条文与裁决结果 | 能力进阶图、术语辨析卡 | 依据反例重做术语卡 |
| L02 | L01术语卡、编队行动问题 | 能画出行动链与裁决链并标明责任席位 | 协同关系图、裁决流程卡 | 补做合法性检查节点 |
| L03 | 组件清单、三册规则 | 组件完整、版本一致、规则索引可复核 | 组件清点表、规则索引卡 | 补齐组件或重建索引 |
| L04 | 标准交战事件 | 10秒交战级事件的命令、操作、裁决和状态一致 | 事件记录、字段映射表 | 回溯事件并重做差异检查 |
| L05 | 0522想定摘要 | 能区分给定事实、未知项和指挥员假设 | 想定要素表、缺项清单 | 补做边界与胜负判据检查 |
| L06 | L05想定分析 | 方案阶段、触发条件、席位和备用行动闭合 | 方案编码表、席位矩阵 | 进行限时口令演练后修订 |
| L07 | 侦察与电磁状态卡 | 航迹来源、时效、共享资格和干扰条件可追溯 | 航迹连续性检查单 | 补做失联与接替处置 |
| L08 | 威胁序列、火力资源表 | 火力分配、通道、弹药和释放时点一致 | 火力链核对表 | 重做威胁排序与通道检查 |
| L09 | 完整想定与方案 | 能完成跨域对抗、差异分析和第二版方案 | 时间线、差异清单、优化方案 | 对关键决策组织定向补练 |
| L10 | 冻结想定、统一量规 | 能独立研判、组织推演并定位证据答辩 | 综合证据包、个人贡献单 | 按考核规定记录结果，不临时补证 |

## 三、阶段质量关口

- L02结束：概念、行动链和裁决链达到进入实作的最低要求。
- L04结束：组件查用、单回合操作和事件记录达到连续推演要求。
- L06结束：想定分析、席位分工和行动方案能够进入专项推演。
- L08结束：侦察电子战、火力防护和软件核对形成闭环。
- L09结束：综合证据包满足L10考核准备要求。
- L10结束：按量规形成成绩、证据目录和课程改进清单，原始材料归档。
""".strip()
    return value + "\n\n" + section + "\n"


def _lesson_one() -> str:
    return f'''---
title: "第1讲：兵棋基础与《谋战》体系认识"
status: draft
content_version: "{CONTENT_VERSION}"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 第1讲：兵棋基础与《谋战》体系认识

> 本讲2学时（120分钟），属于第1次理论课。教学任务是建立全课程共同语言、能力进阶模型和资料权威意识，不安排软件操作，不使用未经核验的具体参数进行裁决。

# 第一章 教学目标与达成证据

## 一、知识目标

1. 说明兵棋、想定、规则、算子、裁决、记录和复盘之间的关系。
2. 说明《谋战》在“想定—方案—推演—裁决—记录—复盘—优化”训练闭环中的作用。
3. 区分战术原理、课堂经验、历史案例和正式规则的证据效力。

## 二、能力目标

1. 使用“个人基础操作—任务与战术协同—全局筹划”三级模型判断训练问题所在层级。
2. 针对一个编队防空事件写出战术意图、需查规则、应留证据和复盘问题。
3. 在规则索引卡上登记版本、条目、适用对象、前置条件和禁止外推事项。

## 三、达成证据

| 达成事项 | 课堂证据 | 合格表现 |
| --- | --- | --- |
| 概念关系 | 六要素关系图、术语辨析卡 | 术语之间的输入输出关系正确 |
| 能力分层 | 课程能力进阶图 | 能把典型问题放入正确层级并说明理由 |
| 权威意识 | 规则来源登记表 | 能识别权威规则、登记数据和待核验材料 |
| 证据链 | 防空事件分析卡 | 意图、行动、规则、结果和复盘问题相互对应 |

# 第二章 学情分析与教学准备

## 一、学情与先修条件

学员具备基本海军作战与水面舰艇编队知识，但对“兵棋规则是否等同战术规律”“推演胜负是否能够直接证明方案优劣”“口述经验能否进入正式裁决”等问题可能存在混淆。本讲不要求记忆规则数值，重点观察概念边界、查证习惯和证据表达能力。

## 二、教员准备

- 课程教学计划、教学进度表和10讲能力路径图。
- 《谋战》R1.2/D1.2三册规则、R1.1/D1.1登记数据目录和参数核验矩阵。
- 同一防空事件的三类材料卡：战术原理、规则条文、裁决记录。
- 空白能力进阶图、术语辨析卡、规则来源登记表和退出测验。

## 三、学员准备

- 预习兵棋、想定、规则、裁决和复盘五个术语。
- 携带课堂记录工具；按小组领取材料但暂不分配正式推演席位。
- 阅读课程资料使用边界，准备一个“课堂经验可能被误当规则”的例子。

# 第三章 教学重点、难点与关键问题

## 一、教学重点

兵棋体系构成、三级能力模型、《谋战》课程主线以及“先核验、后引用、全过程留证”的基本方法。

## 二、教学难点

避免把一次推演结果当作普遍战术规律，也避免把教师口述中的型号、载荷、射程、干扰等级、回合数和概率直接当作0522当前想定参数。

## 三、课堂关键问题

1. 战术上“应该做”是否等于规则上“允许做”？
2. 一个行动裁决成功，是否能够直接证明原方案正确？
3. 同一条规则在什么情况下会因对象、状态、距离、信息或版本不同而不能使用？
4. 软件记录、手工日志和裁决表不一致时，应先保留什么、核查什么？

# 第四章 教学内容、教学过程与时间分配

| 时间 | 教学环节 | 教员活动 | 学员活动 | 当堂证据与检查点 |
| --- | --- | --- | --- | --- |
| 0—10分钟 | 情境导入与前测 | 展示同一防空事件的三种互相冲突表述，提出“哪个能直接用于裁决” | 独立分类并写出理由 | 前测卡；只记录基线，不计课程成绩 |
| 10—30分钟 | 兵棋体系六要素 | 讲解想定提供问题、规则约束行动、算子表达机制、裁决产生结果、记录保留过程、复盘解释偏差 | 绘制六要素关系图并补充箭头含义 | 关系图必须包含输入、约束、结果和反馈 |
| 30—50分钟 | 三级能力模型 | 用操作失误、协同中断和全局节奏三个案例说明能力层级 | 小组把问题卡放入个人、任务战术、全局层并说明理由 | 能力进阶图；不得只按平台类别分类 |
| 50—70分钟 | 资料权威与规则查用 | 对比权威规则、登记数据、旧课件、口述案例和历史材料，演示规则来源登记 | 完成一张规则来源登记表并交换复核 | 必须写明版本、适用条件和禁止外推事项 |
| 70—95分钟 | 防空事件证据链任务 | 给出不含具体性能数值的编队防空事件，提示从意图、行动、规则、结果、复盘五项展开 | 小组完成事件分析卡和证据链 | 每个结论必须能回指材料或标为假设 |
| 95—110分钟 | 汇报、质询与纠偏 | 按“事实—推断—假设—规则—证据”顺序质询，示范暂停、回溯和修订 | 汇报并根据其他组质询修订 | 保留初稿与修订稿，不覆盖原记录 |
| 110—120分钟 | 退出测验与课后任务 | 发布4题退出测验，归纳全课程主线 | 独立作答并提交个人薄弱环节 | 测验、个人训练目标和课后任务 |
| 合计 | 120分钟 | 完成本讲理论教学与诊断 | 形成四类课堂成果 | 达到进入第2讲的共同语言要求 |

# 第五章 教学方法与组织要点

## 一、概念讲授线索

按照“问题从哪里来—行动受什么约束—结果怎样产生—证据如何保留—经验怎样回到下一轮方案”组织讲授。不要把兵棋介绍成单纯的棋盘操作，也不要把软件模拟结果当作自动裁决。

## 二、纠偏话术

- 当学员直接报出某个参数时，追问“来自哪个版本、哪个对象、什么条件”。
- 当学员用胜负证明方案时，追问“哪些关键决策、规则事件和随机结果共同造成结局”。
- 当学员把未知信息当作事实时，要求改写为“给定事实、规则推断或指挥员假设”。
- 当记录发生差异时，先冻结原始材料，再核查时间语义、字段含义、录入和规则适用。

## 三、板书与课件主线

板书保留两条主线：左侧为“想定→方案→推演→裁决→记录→复盘→优化”，右侧为“个人操作→任务战术→全局筹划”。课件只展示概念、关系和反例，不展示未经核验的装备性能表。

# 第六章 形成性评价与课后任务

## 一、形成性评价

本讲为诊断性评价，不直接计入课程总评40分的实作成绩。教员按“达到、基本达到、需要补强”记录四项表现：概念关系、能力分层、资料权威、证据表达。需要补强者在第2讲前提交修订后的术语辨析卡。

## 二、退出测验

1. 用一句话分别说明规则与裁决的作用。
2. 将“敌目标可能进入某方向”判定为事实、推断或假设，并说明依据。
3. 写出引用一条规则时必须登记的三个以上要素。
4. 说明为什么软件回放不能覆盖原始手工记录。

## 三、课后任务

完善个人能力进阶图，选择一个编队作战事件，提交“战术意图—规则问题—证据设计—复盘问题”四联卡。引用旧版或口述材料时必须标明核验状态，不得使用未核验数值形成裁决结论。

# 第七章 来源依据

1. 《谋战·水面舰艇编队战术手工兵棋》0522三册修订版规则稿R1.2/D1.2。
2. 0522裁决与算子数据登记版本R1.1/D1.1。
3. 《谋战》口述材料参数核验矩阵、讲课材料整理稿和课程知识库优选底稿。
4. 水面舰艇作战软件与兵棋推演课程教学计划、教学进度表和考核方案。

<!-- LECTURE-MATERIAL:START -->
## 既往讲课材料融合

三级能力模型采用“个人基础操作—任务与战术协同—全局筹划”主线。个人操作解决准确与熟练，战术协同解决空中、水面、水下力量如何相互支撑，全局筹划解决关键点、兵力投向和行动节奏。涉及平台载荷、干扰等级、射程、不可逃逸区、刷新次数、续航和补给回合的具体数值，只有经参数核验矩阵确认为当前R1.2/D1.2适用内容后，才能进入0522正式裁决。

<!-- LECTURE-MATERIAL:END -->
'''


def _lesson_two() -> str:
    return f'''---
title: "第2讲：水面舰艇编队战术、推演流程与裁决方法"
status: draft
content_version: "{CONTENT_VERSION}"
data_version: "course-baseline-20h-v4"
rules_version: "R1.2/D1.2"
---

# 第2讲：水面舰艇编队战术、推演流程与裁决方法

> 本讲2学时（120分钟），属于第2次理论课。教学任务是把编队战术行动链、指挥协同链和规则裁决链连接起来，为第3讲进入《谋战》组件与规则实作建立方法基础；本讲不安排软件操作。

# 第一章 教学目标与达成证据

## 一、知识目标

1. 说明侦察预警、指挥控制、机动、打击、防护和保障对编队主要任务的作用。
2. 说明事件触发、态势冻结、合法性检查、修正计算、随机裁决、状态更新和证据归档的顺序。
3. 说明有限信息、通道弹药、阶段转换和跨域支援对指挥决策的约束。

## 二、能力目标

1. 把指挥员意图转化为包含对象、行动、时间或触发条件的可执行命令。
2. 针对一次来袭目标处置绘制编队行动链和裁决链，并标明输入、输出、责任席位与暂停条件。
3. 区分已经确认的态势、基于规则的推断和指挥员假设，避免越权补造信息。

## 三、达成证据

| 达成事项 | 课堂证据 | 合格表现 |
| --- | --- | --- |
| 战术行动链 | 编队协同关系图 | 各行动说明对主要任务的贡献和相互依赖 |
| 命令表达 | 指挥命令卡 | 对象、行动、时间或触发条件完整 |
| 裁决链 | 裁决流程卡 | 合法性检查先于修正与随机裁决 |
| 信息边界 | 事实—推断—假设清单 | 不把未知情报改写为确定态势 |

# 第二章 学情分析与教学准备

## 一、学情与先修条件

学员已完成L01概念与权威边界训练，能够识别规则和裁决的不同作用。本讲可能出现的典型问题是：只按平台分类理解协同、把直接得分等同任务贡献、先计算命中再检查合法性、以及命令缺少触发条件或责任席位。

## 二、教员准备

- 一份不含未核验性能数值的编队防空来袭事件卡。
- 编队协同关系图、命令卡、合法性检查卡、裁决流程卡和事件记录样表。
- 《谋战》R1.2/D1.2三册规则目录、R1.1/D1.1登记数据目录和参数核验矩阵。
- 两组反例：支援行动未直接得分但支撑主要任务；动作算出结果但因条件不合法而不得执行。

## 三、学员准备

- 带回L01术语辨析卡和个人能力进阶图。
- 预习侦察、指挥、机动、打击、防护五类行动之间的关系。
- 准备一个“命令表述不完整导致执行歧义”的例子。

# 第三章 教学重点、难点与关键问题

## 一、教学重点

编队战术行动链、指挥协同链、裁决链以及跨域支援对主要任务的贡献。

## 二、教学难点

在有限信息条件下保持事实、推断和假设分离；在连续事件中坚持“先冻结态势、再查合法性、后计算裁决、同步更新状态”的顺序。

## 三、课堂关键问题

1. 为什么侦察、电子战或制空支援即使不直接得分，也可能是主要任务成功的必要条件？
2. 一个动作进入裁决前必须通过哪些合法性检查？
3. 命令只写“加强防空”为什么不能直接执行？
4. 多个平台面对同一威胁时，如何避免无序重复拦截和弹药快速耗尽？
5. 什么时候应暂停推演并回到上一个可复核状态？

# 第四章 教学内容、教学过程与时间分配

| 时间 | 教学环节 | 教员活动 | 学员活动 | 当堂证据与检查点 |
| --- | --- | --- | --- | --- |
| 0—10分钟 | L01回顾与情境导入 | 用来袭目标事件检查术语、资料边界和事实—推断—假设分类 | 完成3题快速回顾并标注已知与未知信息 | 回顾卡；错误当堂纠正 |
| 10—30分钟 | 编队战术行动链 | 以主要任务为中心讲解侦察、指挥、机动、打击、防护和保障的因果关系 | 补全行动链并写出每个节点的任务贡献 | 协同关系图不能只列平台名称 |
| 30—50分钟 | 指挥协同与命令表达 | 示范“对象—行动—时间/触发条件—报告要求”命令结构和复诵机制 | 把三条模糊口令改写为可执行命令 | 指挥命令卡；责任与触发条件完整 |
| 50—75分钟 | 裁决流程与合法性检查 | 讲解态势冻结、事件编号、平台与航迹状态、射界距离、通道弹药、安全条件、修正、随机结果和状态更新 | 排列裁决步骤并找出反例中的越序操作 | 裁决流程卡；合法性必须先于结果计算 |
| 75—95分钟 | 来袭目标小组推演 | 发布不含具体性能数值的事件卡，控制信息逐步披露 | 分工完成命令、合法性清单、裁决流程和记录设计 | 形成完整事件包，不实际引用未核验参数 |
| 95—110分钟 | 汇报、交叉质询与纠偏 | 从任务贡献、信息边界、命令完整性和裁决顺序四方面质询 | 汇报并对其他组提出一项证据性质询 | 保留初稿、质询记录和修订稿 |
| 110—120分钟 | 退出测验与实作衔接 | 总结进入L03需要的组件、规则和记录意识 | 完成退出测验并提交L03预习清单 | 协同图、流程卡、命令卡和预习单 |
| 合计 | 120分钟 | 完成本讲理论教学与实作准备 | 建立行动链与裁决链 | 达到进入《谋战》规则实作要求 |

# 第五章 教学方法与组织要点

## 一、战术讲授线索

所有行动都回到主要任务评价。侦察回答“能否形成可用信息”，指挥回答“信息和命令如何流动”，机动回答“位置如何改变机会与风险”，火力回答“如何形成效果并消耗资源”，防护回答“如何保存持续完成任务的能力”。

## 二、裁决讲授线索

固定使用“事件触发→冻结时间与态势→确认信息来源→检查行动合法性→查算子与修正→实施随机裁决→更新平台、航迹、通道与弹药→归档证据”的顺序。最大射程、合法发射条件、基础概率和最终裁决结果必须明确区分。

## 三、软件衔接边界

本讲只介绍未来需要结构化记录的事件字段，不进行软件操作。第4讲开始建立手工事件编号与软件字段映射；软件不能补造隐藏信息、推算规则未定义参数或覆盖手工裁决。

## 四、板书与课件主线

板书左侧绘制“主要任务—侦察—指挥—机动—火力—防护”行动链，右侧绘制“触发—冻结—合法—修正—随机—更新—归档”裁决链，中间用责任席位和事件编号连接。课件不展示未经核验的具体武器性能和历史想定数据。

# 第六章 形成性评价与课后任务

## 一、形成性评价

本讲为进入实作前的诊断性评价，不直接计入课程总评40分的实作成绩。教员按“达到、基本达到、需要补强”记录四项表现：任务贡献解释、命令完整性、裁决顺序、信息边界。未达到者在L03开始前完成指定反例重做。

## 二、退出测验

1. 写出一个可执行命令必须包含的三个以上要素。
2. 为什么要在裁决前冻结事件时间和当前态势？
3. 列出至少四项行动合法性检查内容。
4. 说明支援行动应怎样按任务贡献而不是直接得分评价。

## 三、课后任务

修订编队协同关系图和裁决流程卡；按L03预习清单熟悉地图、棋子、标记物、三册规则、裁决表和算子表的名称与用途，不预先抄录未经核验的具体数值。

# 第七章 来源依据

1. 《谋战·水面舰艇编队战术手工兵棋》0522三册修订版规则稿R1.2/D1.2。
2. 0522裁决与算子数据登记版本R1.1/D1.1。
3. 《谋战》口述材料参数核验矩阵、讲课材料整理稿和课程知识库优选底稿。
4. 水面舰艇作战软件与兵棋推演课程教学计划、教学进度表、实作指导书和考核方案。

<!-- LECTURE-MATERIAL:START -->
## 既往讲课材料融合

保留“跨域协同与制空支援服务主要任务”的教学思想：空中、水面和水下行动不孤立评价，电子战、侦察与制空支援应说明怎样改善信息、位置、火力条件或任务持续性。涉及载荷、干扰等级、射程、不可逃逸区、刷新次数、续航和补给回合的具体数值，只有经参数核验矩阵确认为当前R1.2/D1.2适用内容后，才能进入0522正式裁决。

<!-- LECTURE-MATERIAL:END -->
'''


def _build(project: dict[str, Any]) -> dict[str, str]:
    current_plan = _current_markdown(project, "doc-e811bedd87f9")
    current_schedule = _current_markdown(project, "doc-2a28da7429f0")
    return {
        "doc-e811bedd87f9": _course_plan(current_plan),
        "doc-2a28da7429f0": _schedule(current_schedule),
        "doc-3a9dbb65b9a3": _lesson_one(),
        "doc-6085f649c11a": _lesson_two(),
    }


def _replace(project: dict[str, Any], document_id: str, markdown: str) -> None:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    if manifest.get("content_authority") == "structured_json":
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            document_id,
            markdown,
            label="课程第三阶段A理论教学核心文档",
            actor="course-phase3a-core-docs",
        )
        return
    multi_document_service.replace_rich_text_markdown(
        project,
        document_id,
        markdown,
        actor="course-phase3a-core-docs",
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
            multi_document_service.set_structure_binding(
                project,
                document_id,
                binding,
                manifest=manifest,
            )
        else:
            multi_document_service.set_structure_binding(project, document_id, binding)
        refreshed.append(document_id)
    return refreshed


def _checks(markdown: str, document_id: str) -> dict[str, Any]:
    banned = ["共10学时", "合计16学时", "理论10＋实作10", "第11讲", "谋战谋战"]
    base = {
        "content_version": CONTENT_VERSION in markdown,
        "banned_hits": [token for token in banned if token in markdown],
        "rules_boundary": "R1.2/D1.2" in markdown,
        "course_baseline": "course-baseline-20h-v4" in markdown,
    }
    if document_id == "doc-e811bedd87f9":
        base.update(
            {
                "hours_20": "总学时 | 20学时" in markdown,
                "structure_2_7_1": "2次理论、7次实作、1次考核" in markdown,
                "l03_task_fixed": "为后续事件字段映射建立对象与规则基线" in markdown,
                "opening_checklist": "## 八、开学执行准备与应急处置" in markdown,
            }
        )
    elif document_id == "doc-2a28da7429f0":
        base.update(
            {
                "schedule_10": markdown.count("| L") >= 10,
                "hours_total": "| 合计 | 10次课" in markdown and "| 4 | 14 | 2 | 20 |" in markdown,
                "run_fields": "## 一、开课运行字段" in markdown,
                "stage_gates": "## 三、阶段质量关口" in markdown,
            }
        )
    else:
        base.update(
            {
                "minutes_120": "| 合计 | 120分钟" in markdown,
                "teacher_student_actions": "教员活动" in markdown and "学员活动" in markdown,
                "diagnostic_not_scored": "不直接计入课程总评40分的实作成绩" in markdown,
                "exit_ticket": "## 二、退出测验" in markdown,
                "sources": "# 第七章 来源依据" in markdown,
            }
        )
    return base


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")
    before_documents = multi_document_service.list_documents(project)["documents"]
    stale_before = _stale_bindings(project)
    built = _build(project)
    current = {document_id: _current_markdown(project, document_id) for document_id in TARGETS}
    changed = [document_id for document_id in TARGETS if built[document_id] != current[document_id]]
    preview = {
        document_id: {
            "label": TARGETS[document_id],
            "changed": document_id in changed,
            "before_chars": len(current[document_id]),
            "after_chars": len(built[document_id]),
            "checks": _checks(built[document_id], document_id),
        }
        for document_id in TARGETS
    }
    if dry_run:
        return {
            "phase": PHASE_LABEL,
            "dry_run": True,
            "document_count": len(before_documents),
            "changed_document_count": len(changed),
            "changed_document_ids": changed,
            "stale_binding_count": len(stale_before),
            "stale_binding_ids": stale_before,
            "preview": preview,
        }

    snapshot = p0._snapshot(project)  # noqa: SLF001
    for document_id in changed:
        _replace(project, document_id, built[document_id])

    binding_project = project_manager.get_project(project_id) or project
    refreshed_bindings = _refresh_stale_bindings(binding_project)

    context = copy.deepcopy(project.get("context") or {})
    context.update(
        {
            "current_delivery_phase": PHASE_LABEL,
            "phase3a_summary": "教学计划、教学进度表和第1—2讲教案已完成开学授课级深化；补齐开课确认、逐讲达成检查、具体师生活动、诊断评价和课后闭环。",
            "next_step": "继续完善L03—L06基础实作教案与实作指导书对应章节；PPTX二进制修订等待合规演示文稿编辑通道。",
        }
    )
    project_manager.update_project(
        project_id,
        {"context": context, "current_phase": "course_phase3a_core_docs"},
    )

    refreshed = project_manager.get_project(project_id) or project
    after_documents = multi_document_service.list_documents(refreshed)["documents"]
    verification = {}
    for document_id in TARGETS:
        markdown = _current_markdown(refreshed, document_id)
        verification[document_id] = {
            "label": TARGETS[document_id],
            "revision": multi_document_service.get_document(refreshed, document_id)["revision"],
            "checks": _checks(markdown, document_id),
        }
    return {
        "phase": PHASE_LABEL,
        "dry_run": False,
        "snapshot": str(snapshot),
        "document_count_before": len(before_documents),
        "document_count_after": len(after_documents),
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
