#!/usr/bin/env python3
"""
Spec 分发器 - 双层 Spec 派发机制核心逻辑
Commander-Architect Protocol Implementation
"""

from enum import Enum
from typing import Optional, Dict, Any
import yaml
from datetime import datetime


class TaskType(Enum):
    DEVELOPMENT = "development"
    RESEARCH = "research"
    SIMULATION = "simulation"
    PAPER = "paper"
    MIXED = "mixed"
    OPS = "ops"


class SpecStatus(Enum):
    DRAFTED = "drafted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"


class SpecDispatcher:
    """Spec 分发器 - 实现双层 Spec 派发机制"""
    
    def __init__(self):
        self.templates_dir = "specs/templates"
        self.active_dir = "specs/active"
    
    def handle_intent(self, intent: str) -> Dict[str, Any]:
        """
        擎天柱入口 - 处理自然语言任务
        
        1. 生成 Task Spec
        2. 判断任务类型
        3. 分发给对应负责人
        """
        # 1. 生成 Task Spec
        task_spec = self.generate_task_spec(intent)
        self.save_spec(task_spec)
        
        # 2. 判断任务类型并分发
        task_type = task_spec.get("task_type", "")
        
        if task_type == TaskType.DEVELOPMENT.value:
            # 开发任务 → 必须派发给李奥纳多
            return self.dispatch_to("leonardo", task_spec)
        elif task_type == TaskType.SIMULATION.value:
            # 仿真任务 → 派发给铁皮
            return self.dispatch_to("ironhide", task_spec)
        elif task_type == TaskType.PAPER.value:
            # 论文任务 → 派发给论文负责人
            return self.dispatch_to("gpt_writer", task_spec)
        elif task_type == TaskType.OPS.value:
            # 运维任务 → 派发给大黄蜂
            return self.dispatch_to("bumblebee", task_spec)
        else:
            # 其他任务 → 通用分发
            return self.dispatch_general(task_spec)
    
    def generate_task_spec(self, intent: str) -> Dict[str, Any]:
        """生成 Task Spec (擎天柱职责)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # TODO: 使用 LLM 解析 intent 生成结构化 Spec
        task_spec = {
            "spec_id": f"task_{timestamp}",
            "type": "task_spec",
            "version": "1.0",
            "title": "",  # 从 intent 提取
            "task_type": "",  # 从 intent 识别
            "intent": intent,
            "priority": "medium",
            "objective": [],
            "deliverables": [],
            "constraints": [],
            "owners": {
                "architect": "leonardo",
                "simulator": "ironhide",
                "analyst": "shockwave",
            },
            "status": "drafted",
            "created_at": datetime.now().isoformat(),
        }
        
        return task_spec
    
    def dispatch_to(self, agent_id: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """分发给指定 Agent"""
        # 强约束：检查 Spec 是否存在
        if not spec.get("spec_id"):
            raise Exception("禁止执行：缺少 spec_id")
        
        # 强约束：开发任务必须检查 Dev Spec
        if spec.get("task_type") == "development":
            if spec.get("type") == "task_spec":
                # Task Spec 只能发给李奥纳多
                if agent_id != "leonardo":
                    raise Exception("开发任务 Task Spec 必须发给李奥纳多")
        
        return {
            "status": "dispatched",
            "agent_id": agent_id,
            "spec_id": spec["spec_id"],
            "timestamp": datetime.now().isoformat(),
        }
    
    def dispatch_general(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """通用分发逻辑"""
        return self.dispatch_to("optimus", spec)
    
    def save_spec(self, spec: Dict[str, Any]) -> str:
        """保存 Spec 到 active 目录"""
        spec_id = spec.get("spec_id", "unknown")
        filepath = f"{self.active_dir}/{spec_id}.yaml"
        
        # TODO: 实际保存文件
        print(f"[INFO] Spec saved: {filepath}")
        return filepath
    
    def load_spec(self, spec_id: str) -> Optional[Dict[str, Any]]:
        """加载 Spec"""
        filepath = f"{self.active_dir}/{spec_id}.yaml"
        # TODO: 实际加载文件
        return None


def leonardo_handle(task_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    李奥纳多入口 - 处理开发任务
    
    1. 生成 Dev Spec
    2. 分发给忍者神龟成员
    """
    # 1. 生成 Dev Spec
    dev_spec = generate_dev_spec(task_spec)
    save_spec(dev_spec)
    
    # 2. 分发给忍者神龟
    results = {
        "raphael": dispatch_to("raphael", dev_spec),
        "donatello": dispatch_to("donatello", dev_spec),
        "michelangelo": dispatch_to("michelangelo", dev_spec),
    }
    
    return {
        "status": "dispatched",
        "dev_spec_id": dev_spec["dev_spec_id"],
        "subtasks": results,
    }


def generate_dev_spec(task_spec: Dict[str, Any]) -> Dict[str, Any]:
    """生成 Dev Spec (李奥纳多职责)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    dev_spec = {
        "dev_spec_id": f"dev_{timestamp}",
        "type": "dev_spec",
        "version": "1.0",
        "parent_spec_id": task_spec["spec_id"],
        "module_scope": [],
        "architecture": {
            "new_modules": [],
            "modified_modules": [],
        },
        "interfaces": [],
        "tasks": {
            "raphael": [],
            "donatello": [],
            "michelangelo": [],
        },
        "constraints": [
            "do_not_break_existing_api",
            "keep_backward_compatibility",
        ],
        "validation": {
            "unit_tests": True,
            "integration_tests": True,
        },
        "status": "drafted",
        "created_at": datetime.now().isoformat(),
    }
    
    return dev_spec


def collect_results(spec_id: str) -> Dict[str, Any]:
    """收集并汇总结果"""
    # TODO: 从各 Agent 收集结果
    results = {
        "spec_id": spec_id,
        "sub_results": [],
        "summary": "",
    }
    return results


# 强约束检查函数
def check_no_spec_execution(spec: Optional[Dict]) -> None:
    """规则 1: 无 Spec 不执行"""
    if not spec:
        raise Exception("禁止执行：缺少 Spec")


def check_dev_spec_required(task_type: str, dev_spec: Optional[Dict]) -> None:
    """规则 2: 开发任务必须二次 Spec"""
    if task_type == "development" and not dev_spec:
        raise Exception("必须先生成 Dev Spec")


def check_agent_level(agent_id: str, spec_type: str) -> None:
    """规则 3: Agent 不得越级"""
    ninja_team = ["raphael", "donatello", "michelangelo"]
    
    if agent_id in ninja_team and spec_type == "task_spec":
        raise Exception("忍者神龟成员不能直接接收 Task Spec")


if __name__ == "__main__":
    # 测试示例
    dispatcher = SpecDispatcher()
    
    # 模拟用户输入
    intent = "为海上无人集群防空系统增加 Q-L-Track 探测模型"
    
    # 处理任务
    result = dispatcher.handle_intent(intent)
    print(f"[INFO] Task dispatched: {result}")
