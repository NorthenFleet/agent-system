#!/usr/bin/env python3
"""Cross-review the course suite and install the opening-day run package."""

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


PHASE_LABEL = "课程开学准备第四阶段：全套校审与开课运行包"
CONTENT_VERSION = "surface-course-opening-run-v1"
COURSE_PLAN_ID = "doc-e811bedd87f9"
SCHEDULE_ID = "doc-2a28da7429f0"
L01_ID = "doc-3a9dbb65b9a3"
PRACTICE_GUIDE_ID = "doc-e6071aa369ed"


MAIN_ROWS = {
    1: "| 1 | 第1次课 | 兵棋基础与《谋战》体系认识 | 理论讲授与研讨 | 2 |  |  | 2 | 不安排软件操作；建立课程闭环、三级能力模型和资料权威意识。 | 六要素关系图、能力进阶图、术语辨析卡、规则来源登记表、防空事件分析卡 |",
    2: "| 2 | 第2次课 | 水面舰艇编队战术、推演流程与裁决方法 | 理论讲授与研讨 | 2 |  |  | 2 | 不安排软件操作；建立编队行动链、命令闭环和人工裁决流程。 | 协同关系图、裁决流程卡、命令闭环卡、L03预习清单 |",
    3: "| 3 | 第3次课 | 《谋战》组件、地图、棋子与规则查用 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 不安排软件操作；完成组件、版本和规则索引，为软件事件字段映射建立对象与规则基线。 | 组件清点表、版本确认单、八类规则索引卡、组间复核意见 |",
    4: "| 4 | 第4次课 | 单回合操作、态势标绘与裁决记录 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 建立手工事件编号与软件字段映射，核对10秒事件的命令、操作、裁决和状态。 | 事件字段映射表、单回合事件记录、弹药通道变化表、手工—软件一致性检查单、错误纠正单 |",
    5: "| 5 | 第5次课 | 作战想定理解、关键点识别与任务构建 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 录入想定要素并检查事实、未知、规则推断、假设、缺项和冲突。 | 想定要素表、事实—未知—假设清单、关键问题矩阵、数字化想定核对单、初始态势图 |",
    6: "| 6 | 第6次课 | 五人编组、编队部署与行动方案制定 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 编码阶段、触发、席位、授权、预期效果和备用行动，并与纸面方案对照。 | 席位卡、责任矩阵、指挥关系图、编队部署图、行动方案卡、命令交互日志、纸面—软件差异清单 |",
    7: "| 7 | 第7次课 | 侦察预警、电子战与指挥协同专项推演 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 登记航迹来源、质量、电磁状态、干扰条件、共享资格和命令状态，核对连续性。 | 侦察电子战行动表、航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘 |",
    8: "| 8 | 第8次课 | 制空支援、对海打击与防空反导专项推演 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 按事件核对威胁、发射、裁决、通道、弹药、在途武器和能力储备。 | 威胁排序表、火力分配表、发射拦截记录、通道弹药状态表、手工—软件一致性报告、专项复盘 |",
    9: "| 9 | 第9次课 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 《谋战》手工兵棋实作 |  | 2 |  | 2 | 导入不少于五个关键事件，完成时间线、差异分析和第二版方案。 | 考核前行动方案、综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案 |",
    10: "| 10 | 第10次课 | 综合考核：想定分析、对抗推演与复盘答辩 | 综合考核 |  |  | 2 | 2 | 使用冻结软件环境提交事件目录和差异说明；软件不自动评分。 | 个人想定分析表、小组行动方案、推演日志、裁决底稿、最终态势图、软件证据目录、个人贡献单、答辩与评分记录 |",
}


CHECK_ROWS = {
    "L01": "| L01 | 课程说明、术语预习 | 能区分体系要素、能力层级与资料权威 | 六要素关系图、能力进阶图、术语辨析卡、规则来源登记表 | 修订术语卡和来源登记 |",
    "L02": "| L02 | L01诊断成果、编队问题 | 能画出行动链、命令链和裁决链 | 协同关系图、裁决流程卡、命令闭环卡 | 补做合法性与责任节点 |",
    "L03": "| L03 | L02流程卡、组件与三册规则 | 组件完整、版本一致、八类索引可复核 | 组件清点表、版本确认单、八类规则索引卡 | 补齐组件或重建索引 |",
    "L04": "| L04 | L03规则索引、标准事件 | 10秒事件的命令、操作、裁决和状态一致 | 事件记录、弹药通道变化表、手工—软件检查单 | 回溯事件并重做差异检查 |",
    "L05": "| L05 | 0522公开想定、L04事件基线 | 事实、未知、规则推断和假设边界清楚 | 想定要素表、关键问题矩阵、初始态势图 | 补做边界与判据检查 |",
    "L06": "| L06 | L05想定分析与关键问题 | 席位、部署、阶段、触发和备用行动闭合 | 责任矩阵、部署图、行动方案卡、命令日志 | 限时口令演练后修订 |",
    "L07": "| L07 | L06行动方案、侦察与电磁状态卡 | 航迹、电子战、电磁状态和命令协同可追溯 | 侦察电子战行动表、航迹连续性表、差异单 | 补做中断与接替处置 |",
    "L08": "| L08 | L07有效航迹、威胁与火力资源 | 威胁排序、发射裁决和资源状态一致 | 火力分配表、发射记录、通道弹药状态表 | 重做排序与资源检查 |",
    "L09": "| L09 | L05—L08合格成果与完整想定 | 能完成跨域对抗、证据核对和第二版方案 | 综合日志、裁决证据包、时间线、软件回放与差异清单 | 对关键决策定向补练 |",
    "L10": "| L10 | 冻结想定、统一量规、个人证据目录 | 能独立研判、履职推演并定位证据答辩 | 综合考核证据包、个人评分与答辩记录 | 按考核规定复核，不临时补造证据 |",
}


PRACTICE_SUMMARY_ROWS = {
    3: "| 第3次课 | 《谋战》组件、地图、棋子与规则查用 | 组件清点表、版本确认单、八类规则索引卡、组间复核意见 |",
    4: "| 第4次课 | 单回合操作、态势标绘与裁决记录 | 事件字段映射表、单回合事件记录、弹药通道变化表、手工—软件一致性检查单、错误纠正单 |",
    5: "| 第5次课 | 作战想定理解、关键点识别与任务构建 | 想定要素表、事实—未知—假设清单、关键问题矩阵、数字化想定核对单、初始态势图 |",
    6: "| 第6次课 | 五人编组、编队部署与行动方案制定 | 席位卡、责任矩阵、指挥关系图、编队部署图、行动方案卡、命令交互日志、纸面—软件差异清单 |",
    7: "| 第7次课 | 侦察预警、电子战与指挥协同专项推演 | 侦察电子战行动表、航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘 |",
    8: "| 第8次课 | 制空支援、对海打击与防空反导专项推演 | 威胁排序表、火力分配表、发射拦截记录、通道弹药状态表、手工—软件一致性报告、专项复盘 |",
    9: "| 第9次课 | 关键点争夺、跨域综合对抗与软件辅助复盘 | 考核前行动方案、综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案 |",
}


def _current_markdown(project: dict[str, Any], document_id: str) -> str:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    working = Path(str(manifest.get("working_markdown") or ""))
    if not working.is_file():
        raise RuntimeError(f"工作稿不存在：{document_id} {working}")
    return working.read_text(encoding="utf-8")


def _set_content_version(markdown: str) -> str:
    return re.sub(
        r'(?m)^content_version:\s*.*$',
        f'content_version: "{CONTENT_VERSION}"',
        markdown,
        count=1,
    )


def _replace_tail(markdown: str, marker: str, appendix: str) -> str:
    return markdown.split(marker, 1)[0].rstrip() + "\n\n" + appendix.strip() + "\n"


def _course_plan(markdown: str) -> str:
    value = _set_content_version(markdown)
    appendix = r'''
# 附录A 开课运行包组成与责任界面

> 本附录是开课执行索引，不替代各正式文档。实际日期、班次、场地、任课教员和学员名单确认后，只填写运行字段，不改变20学时、10次课、规则版本和成绩结构。

## 一、运行包目录

| 类别 | 权威文档或材料 | 使用时点 | 责任人 | 完成标志 |
| --- | --- | --- | --- | --- |
| 课程基线 | 教学计划、教学进度表 | 开课前与每次课前 | 课程负责人 | 课次、学时、成果、评分一致 |
| 授课组织 | 10讲教案、首课实施脚本 | 每次课前 | 任课教员 | 教学活动、停止条件和课后移交明确 |
| 实作运行 | 实作指导书附录B—D | 第3—9讲 | 教员、器材员、记录员 | 表单、器材、席位和证据编号齐全 |
| 规则与数据 | R1.2/D1.2规则、R1.1/D1.1登记数据 | 裁决前 | 规则管理员、裁决员 | 版本冻结并完成校验 |
| 软件环境 | one-sim、智能筹划软件及导出目录 | 第4—10讲 | 软件保障员 | 账号、版本、时间语义、想定和导出路径可用 |
| 评价考核 | 过程量规、综合考核表单与证据目录 | 第3—10讲 | 评分员、证据员 | 分值、事件编号、评语和签名完整 |
| 归档发布 | 课堂证据包、差异单、复核记录 | 每次课后 | 记录员、课程负责人 | 原始材料与追加说明分别保存；保持草稿 |

## 二、本学期运行字段

| 字段 | 填写内容 | 确认人 | 确认日期 |
| --- | --- | --- | --- |
| 开课日期与周次 |  |  |  |
| 班次与人数 |  |  |  |
| 教室与兵棋场地 |  |  |  |
| 任课教员、助教、规则管理员 |  |  |  |
| 分组数量与席位轮换 |  |  |  |
| 器材套数与备用件 |  |  |  |
| 软件终端、账号和网络 |  |  |  |
| 成果提交与归档位置 |  |  |  |

## 三、三级开课门

| 时点 | 必须完成 | 未完成时处置 |
| --- | --- | --- |
| 开课前7日 | 排课、名单、场地、规则数据版本和总体资源确认 | 课程负责人登记缺口并确定补齐责任 |
| 每次课前1日 | 教案、想定、器材、表单、软件或手工备用流程确认 | 不满足准入条件的任务改为补练或延期 |
| 上课前30分钟 | 现场器材、设备时间、文件版本、板书课件、分组与材料包复核 | 冻结异常，未排除前不发布隐藏信息、不启动裁决 |

开课运行包仅在课程组内部使用。两套课件仍须完成二进制逐页复核和人工批准后才能发布；填写运行表、完成课堂试用或通过程序检查均不等同正式发布。
'''
    return _replace_tail(value, "# 附录A 开课运行包组成与责任界面", appendix)


def _schedule(markdown: str) -> str:
    value = _set_content_version(markdown)
    for lesson, row in MAIN_ROWS.items():
        value = re.sub(
            rf"(?m)^\| {lesson} \| 第{lesson}次课 \|.*$",
            lambda _match, replacement=row: replacement,
            value,
            count=1,
        )
    for unit, row in CHECK_ROWS.items():
        value = re.sub(
            rf"(?m)^\| {unit} \|.*$",
            lambda _match, replacement=row: replacement,
            value,
            count=1,
        )
    appendix_rows = "\n".join(
        [
            "| L01 | 课程计划、术语预习 | 概念辨析与诊断 | 六要素关系图、能力进阶图、术语卡、来源登记 | 诊断，不计分 | L02行动链与裁决链 |",
            "| L02 | L01诊断成果 | 编队战术、命令与裁决流程 | 协同图、流程卡、命令卡、预习单 | 诊断，不计分 | L03组件与规则查用 |",
            "| L03 | L02流程卡、组件与规则 | 组件清点和八类规则索引 | 清点表、版本单、索引卡、复核意见 | 4分 | L04对象与规则基线 |",
            "| L04 | L03索引卡、标准事件 | 10秒事件闭环与软件映射 | 事件、弹药通道、软件检查与纠错表 | 4分 | L05标准事件字段 |",
            "| L05 | 0522公开想定 | 想定要素和关键问题构建 | 想定、信息分类、问题矩阵、初态图 | 4分 | L06方案输入 |",
            "| L06 | L05想定成果 | 五人编组、部署与方案演练 | 席位、部署、方案、命令与差异材料 | 4分 | L07专项方案 |",
            "| L07 | L06行动方案 | 侦察、电子战、电磁与协同 | 侦察行动、航迹、电磁、命令、差异与复盘 | 8分 | L08有效航迹与支援状态 |",
            "| L08 | L07航迹与支援状态 | 火力、分层防御与资源持续 | 威胁、火力、发射、资源、差异与复盘 | 8分 | L09综合能力输入 |",
            "| L09 | L05—L08合格成果 | 跨域综合对抗与软件复盘 | 行动方案、综合日志、证据、时间线、回放与第二版方案 | 8分 | L10个人证据目录 |",
            "| L10 | 冻结想定、量规和证据目录 | 独立研判、对抗、复盘答辩 | 综合考核证据包和个人评分记录 | 原始100分×60% | 人工复核与草稿归档 |",
        ]
    )
    appendix = f'''
# 第四章 10次课输入—活动—产出—移交总表

> 全套课程保持20学时、10次课。规则使用R1.2/D1.2，裁决与算子数据使用登记的R1.1/D1.1；实际日期、班次、场地和人员名单在本学期排课确认后填写。

| 课次 | 主要输入 | 核心活动 | 必交产出 | 课程计分 | 移交下一环节 |
| --- | --- | --- | --- | ---: | --- |
{appendix_rows}

## 开课运行时点

| 时点 | 任课教员 | 器材/软件保障 | 学员 | 记录与证据 |
| --- | --- | --- | --- | --- |
| 开课前7日 | 确认排课、名单和总体资源 | 核对规则数据、器材套数和终端 | 接收课程说明 | 建立课程运行目录 |
| 每次课前1日 | 冻结教案、任务和停止条件 | 准备材料包、软件或手工备用流程 | 完成先修任务 | 生成本讲证据编号范围 |
| 上课前30分钟 | 现场复核板书、课件和分组 | 校验器材、时间、版本和导出路径 | 签到并领取材料 | 登记异常和发放记录 |
| 下课前5分钟 | 完成讲评与下讲准入判定 | 回收器材、导出原始文件 | 提交成果和个人贡献 | 封存原始材料与缺项单 |
| 课后1日内 | 完成反馈与补练通知 | 归档软件包和差异记录 | 按要求追加说明 | 更新成果目录，不覆盖原件 |
'''
    return _replace_tail(value, "# 第四章 10次课输入—活动—产出—移交总表", appendix)


def _l01(markdown: str) -> str:
    value = _set_content_version(markdown)
    appendix = r'''
# 第八章 首课实施脚本与现场检查卡

## 一、课前30分钟检查

| 时点 | 教员动作 | 助教/保障动作 | 完成标志 |
| --- | --- | --- | --- |
| T−30分钟 | 核对教学计划、进度表、L01教案和课程说明 | 核对教室、投影、白板、计时和签到表 | 文件与现场信息一致 |
| T−20分钟 | 摆放三类材料卡和前测卡，隐藏答案与后续想定 | 按人数准备关系图、能力图、术语卡和来源登记表 | 每名学员有一套基础材料 |
| T−10分钟 | 板书两条课程主线，打开不含未核验参数的课件页 | 按临时学习组摆放材料，登记缺席和临时加入人员 | 可按手工板书方案独立开课 |
| T−5分钟 | 确认本讲不操作软件、不作正式裁决、不计过程分 | 关闭无关软件和外部资料入口 | 权威边界已向学员可见 |

## 二、首课现场实施脚本

| 时间 | 教员口令/控制点 | 学员任务 | 当堂检查 |
| --- | --- | --- | --- |
| 0—10分钟 | “先独立判断三类表述，写理由，不讨论答案。” | 完成前测卡 | 记录基线，不排名、不计分 |
| 10—30分钟 | “为六要素补上输入、约束、结果和反馈箭头。” | 绘制关系图 | 术语关系完整 |
| 30—50分钟 | “不要按平台分类，判断问题发生在哪一能力层。” | 完成三级能力图 | 能解释归类依据 |
| 50—70分钟 | “每个参数都回答版本、对象、条件和禁止外推。” | 填写规则来源登记表 | 不把口述材料当权威规则 |
| 70—95分钟 | “按意图—行动—规则—结果—复盘建立证据链。” | 完成防空事件分析卡 | 结论有来源或显式标为假设 |
| 95—110分钟 | “先保留原稿，再根据质询追加修订。” | 汇报、质询、修订 | 初稿和修订稿同时保留 |
| 110—120分钟 | “独立完成退出测验，写出个人薄弱项。” | 提交测验和四联卡任务 | 形成L02分层辅导名单 |

## 三、首课成果与移交

| 材料 | 数量/责任 | 状态 | 移交用途 |
| --- | --- | --- | --- |
| 签到与临时分组表 | 助教1份 |  | 确认班次、人数和分组需求 |
| 前测与退出测验 | 每人各1份 |  | 形成L02诊断名单 |
| 六要素关系图、能力进阶图 | 每组各1份 |  | L02行动链和裁决链导入 |
| 术语辨析卡、规则来源登记表 | 每人各1份 |  | L03规则查用先修检查 |
| 异常与缺项记录 | 记录员1份 |  | 课后1日内闭环 |

若投影不可用，按白板两条主线和纸质材料继续授课；若规则材料版本不一致，只进行资料权威辨析，不展示冲突参数；若学员临时加入，先补签课程边界和前测，不追溯性补造课堂表现。
'''
    return _replace_tail(value, "# 第八章 首课实施脚本与现场检查卡", appendix)


def _practice_guide(markdown: str) -> str:
    value = _set_content_version(markdown)
    for lesson, row in PRACTICE_SUMMARY_ROWS.items():
        value = re.sub(
            rf"(?m)^\| 第{lesson}次课 \|[^\n]*\|$",
            lambda _match, replacement=row: replacement,
            value,
            count=1,
        )
    replacements = {
        "- 必交成果：组件清点表、八类规则索引卡、版本登记表、组间复核意见。": "- 必交成果：组件清点表、版本确认单、八类规则索引卡、组间复核意见。",
        "- 必交成果：行动日志、发射与拦截记录、弹药变化表、最终态势图、错误纠正单。": "- 必交成果：事件字段映射表、单回合事件记录、弹药通道变化表、手工—软件一致性检查单、错误纠正单。",
        "- 必交成果：想定要素表、关键问题清单、任务分析表、风险假设登记和初始态势图。": "- 必交成果：想定要素表、事实—未知—假设清单、关键问题矩阵、数字化想定核对单、初始态势图。",
        "- 必交成果：席位卡、指挥关系图、编队部署图、行动方案卡、命令交互日志。": "- 必交成果：席位卡、责任矩阵、指挥关系图、编队部署图、行动方案卡、命令交互日志、纸面—软件差异清单。",
        "- 必交成果：侦察计划、航迹维护表、干扰效果表、电磁活动日志、协同复盘记录。": "- 必交成果：侦察电子战行动表、航迹连续性表、电磁活动日志、命令协同记录、手工—软件差异单、专项复盘。",
        "- 必交成果：火力分配表、完整发射记录、弹药余量表、任务贡献说明、专项复盘。": "- 必交成果：威胁排序表、火力分配表、发射拦截记录、通道弹药状态表、手工—软件一致性报告、专项复盘。",
        "- 必交成果：综合推演日志、裁决证据包、软件回放数据、差异清单、优化方案。": "- 必交成果：考核前行动方案、综合推演日志、裁决证据包、关键决策时间线、软件回放包、差异清单、第二版方案。",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    appendix = r'''
# 附录D 开课运行包

> 本附录供课程组现场使用，不新增发布成果。空白字段在排课、名单和场地确认后填写；规则与数据版本固定为R1.2/D1.2和R1.1/D1.1，任何临时变化均通过异常记录追加保存。

## D.1 课程运行信息卡

| 项目 | 内容 | 确认人 | 日期 |
| --- | --- | --- | --- |
| 开课日期、周次、班次 |  |  |  |
| 教室、兵棋场地、备用场地 |  |  |  |
| 任课教员、助教、规则管理员、软件保障员 |  |  |  |
| 学员人数、分组数量 |  |  |  |
| 规则与数据校验信息 | R1.2/D1.2；R1.1/D1.1 |  |  |
| 软件版本、账号、终端与导出目录 |  |  |  |
| 课堂成果与归档位置 |  |  |  |

## D.2 学员分组、席位与轮换表

| 小组 | 学员 | L03初始分工 | L04—L06席位 | L07席位 | L08席位 | L09席位 | L10抽签席位 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

五人标准席位为队长/指挥、行动、侦察电子战、裁决、记录评估。可依据实际人数合并辅助职责，但裁决与指挥、证据与成绩批准不得由同一人无监督兼任。

## D.3 器材、版本与软件检查表

| 类别 | 名称/编号 | 计划数量 | 实有数量 | 版本/状态 | 备用方案 | 检查人 | 复核人 |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| 地图与底图 |  |  |  |  |  |  |  |
| 棋子与标记物 |  |  |  |  |  |  |  |
| 规则三册 |  |  |  | R1.2/D1.2 |  |  |  |
| 裁决与算子数据 |  |  |  | R1.1/D1.1 |  |  |  |
| D100与记录工具 |  |  |  |  |  |  |  |
| 软件终端与账号 |  |  |  |  | 手工流程 |  |  |
| 投影、白板与计时 |  |  |  |  | 纸质/板书 |  |  |

## D.4 材料发放与回收表

| 课次 | 小组/学员 | 发放材料及编号 | 发放时间 | 回收材料及编号 | 缺项/损坏 | 经手人 | 处置结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |

## D.5 课堂运行记录

| 课次 | 实到/应到 | 开始/结束 | 使用想定与版本 | 主要活动完成情况 | 暂停与异常编号 | 必交成果状态 | 下讲准入/补练 | 教员签名 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

## D.6 10次课表单目录

| 课次 | 现场表单 | 归档责任 | 移交对象 |
| --- | --- | --- | --- |
| L01 | 签到、前测、关系图、能力图、术语卡、来源登记、退出测验 | 助教 | L02诊断名单 |
| L02 | 协同关系图、裁决流程卡、命令闭环卡、预习单 | 任课教员 | L03先修检查 |
| L03 | 组件清点、版本确认、规则索引、复核意见、4分表 | 规则管理员 | L04字段基线 |
| L04 | 事件记录、弹药通道、软件检查、纠错单、4分表 | 裁决/记录席 | L05标准事件 |
| L05 | 想定要素、信息分类、关键问题、数字核对、4分表 | 记录席 | L06方案输入 |
| L06 | 席位、责任、部署、方案、命令、差异、4分表 | 队长/记录席 | L07行动方案 |
| L07 | 侦察行动、航迹、电磁、命令、差异、复盘、8分表 | 侦察/记录席 | L08航迹与支援状态 |
| L08 | 威胁、火力、发射、资源、差异、复盘、8分表 | 行动/裁决席 | L09综合输入 |
| L09 | 行动方案、日志、证据、时间线、回放、差异、第二版方案、8分表 | 全组/证据员 | L10个人证据目录 |
| L10 | 个人分析、行动方案、日志、裁决、态势、软件目录、贡献、答辩与评分 | 主考/证据员 | 人工复核与归档 |

## D.7 软件不可用与课堂异常备用流程

1. 第1—3讲不依赖软件，投影不可用时使用板书和纸质材料继续。
2. 第4—9讲软件不可用时，以手工事件编号、态势图和裁决日志完成课堂核心任务；课后只允许补录和差异说明，不改写裁决。
3. 软件故障导致时间、状态或公平性无法恢复时，冻结事件并登记异常；由教员或主考决定恢复点、统一重置或终止。
4. 规则或数据版本不一致、隐藏信息越权、器材关键缺项、证据断链和安全保密风险均触发暂停。

## D.8 课后归档与闭环清单

| 检查项 | 完成 | 缺项/异常 | 责任人 | 完成时限 |
| --- | --- | --- | --- | --- |
| 原始纸质成果已编号并封存 | □ |  |  | 课后当日 |
| 软件原始导出与截图来源可定位 | □ |  |  | 课后当日 |
| 手工—软件差异已追加说明 | □ |  |  | 课后1日内 |
| 分值关联事件编号、评语和评分员 | □ |  |  | 下次课前 |
| 补练通知保留原表现与补练要求 | □ |  |  | 下次课前 |
| 器材归还、缺损和版本异常已登记 | □ |  |  | 课后当日 |
| 下一讲输入包和准入名单已形成 | □ |  |  | 下次课前1日 |
'''
    return _replace_tail(value, "# 附录D 开课运行包", appendix)


def _replace(project: dict[str, Any], document_id: str, markdown: str) -> None:
    context = multi_document_service.rich_project_context(project, document_id)
    manifest = document_workspace_service.ensure_workspace(context)
    if manifest.get("content_authority") == "structured_json":
        writing_collaboration_service.replace_authority_from_markdown(
            project,
            document_id,
            markdown,
            label="课程第四阶段全套校审与开课运行包",
            actor="course-phase4-opening-package",
        )
        return
    multi_document_service.replace_rich_text_markdown(
        project,
        document_id,
        markdown,
        actor="course-phase4-opening-package",
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
    if document_id == COURSE_PLAN_ID:
        result.update(
            {
                "opening_index": "# 附录A 开课运行包组成与责任界面" in markdown,
                "semester_fields": "本学期运行字段" in markdown,
                "three_gates": all(token in markdown for token in ["开课前7日", "每次课前1日", "上课前30分钟"]),
                "keeps_20h": "20学时" in markdown and "10次课" in markdown,
            }
        )
    elif document_id == SCHEDULE_ID:
        result.update(
            {
                "ten_rows": all(MAIN_ROWS[lesson] in markdown for lesson in MAIN_ROWS),
                "ten_check_rows": all(CHECK_ROWS[unit] in markdown for unit in CHECK_ROWS),
                "handoff_table": "# 第四章 10次课输入—活动—产出—移交总表" in markdown,
                "score_map": all(token in markdown for token in ["4分", "8分", "原始100分×60%"]),
            }
        )
    elif document_id == L01_ID:
        result.update(
            {
                "first_lesson_script": "# 第八章 首课实施脚本与现场检查卡" in markdown,
                "preclass_check": "课前30分钟检查" in markdown,
                "minutes_120": all(token in markdown for token in ["0—10分钟", "10—30分钟", "110—120分钟"]),
                "manual_fallback": "投影不可用" in markdown and "白板" in markdown,
            }
        )
    else:
        result.update(
            {
                "canonical_summary_rows": all(row in markdown for row in PRACTICE_SUMMARY_ROWS.values()),
                "opening_package": "# 附录D 开课运行包" in markdown,
                "run_forms": all(token in markdown for token in ["学员分组、席位与轮换表", "器材、版本与软件检查表", "材料发放与回收表", "课堂运行记录"]),
                "ten_form_rows": all(f"| L{lesson:02d} |" in markdown for lesson in range(1, 11)),
                "fallback_and_archive": "软件不可用与课堂异常备用流程" in markdown and "课后归档与闭环清单" in markdown,
            }
        )
    return result


def migrate(project_id: str, dry_run: bool) -> dict[str, Any]:
    project = project_manager.get_project(project_id)
    if not project:
        raise SystemExit(f"Project not found: {project_id}")
    documents_before = multi_document_service.list_documents(project)["documents"]
    targets = {
        COURSE_PLAN_ID: _course_plan(_current_markdown(project, COURSE_PLAN_ID)),
        SCHEDULE_ID: _schedule(_current_markdown(project, SCHEDULE_ID)),
        L01_ID: _l01(_current_markdown(project, L01_ID)),
        PRACTICE_GUIDE_ID: _practice_guide(_current_markdown(project, PRACTICE_GUIDE_ID)),
    }
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
            "phase4_summary": "14份正式文本完成交叉校审；教学进度表成果链、首课实施脚本和实作指导书开课运行包已统一，项目仍为20份文档。",
            "opening_package_status": "content_ready_pending_semester_fields",
            "next_step": "填写本学期排课、名单、场地和软件环境字段，随后生成开学用Word并进行逐页渲染复核；PPTX二进制修订仍等待合规编辑通道。",
        }
    )
    project_manager.update_project(project_id, {"context": context, "current_phase": "course_phase4_opening_package"})

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
