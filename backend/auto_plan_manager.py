# -*- coding: utf-8 -*-
"""
自动任务计划管理 - 李奥纳多和擎天柱后台自动工作
"""
from datetime import datetime
from typing import List, Dict
import json
import os

from task_queue import task_manager
from plan_manager import plan_manager

class AutoPlanManager:
    """自动计划管理器"""
    
    def __init__(self):
        self.log_file = "data/auto_plan_log.json"
        self.logs = self._load_logs()
    
    def _load_logs(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def _save_logs(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)
    
    def _add_log(self, action, details, actor="system"):
        self.logs.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "actor": actor,
            "details": details
        })
        self._save_logs()
    
    def leonardo_auto_generate(self):
        tasks = task_manager.get_all_tasks()
        generated = []
        skipped = []
        
        for task in tasks:
            if task["status"] in ["pending", "in_progress"]:
                existing_plan = plan_manager.get_plan_by_task(task["id"])
                if not existing_plan:
                    plan_template = plan_manager.generate_plan_template(task)
                    plan = plan_manager.create_plan(task["id"], plan_template, "李奥纳多")
                    generated.append({
                        "task_id": task["id"],
                        "task_title": task["title"],
                        "plan_id": plan["id"],
                        "plan_type": plan["type"]
                    })
                    msg = "task_id=" + task["id"] + ", plan_id=" + plan["id"]
                    self._add_log("plan_generated", msg, actor="李奥纳多")
                else:
                    skipped.append({"task_id": task["id"], "reason": "计划已存在"})
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "actor": "李奥纳多",
            "action": "自动生成计划",
            "generated": generated,
            "skipped": skipped
        }
        
        print("[Auto] 李奥纳多自动生成计划：", len(generated), "个新计划，", len(skipped), "个跳过")
        return result
    
    def optimus_auto_review(self, auto_approve=True):
        pending_plans = plan_manager.get_pending_plans()
        approved = []
        rejected = []
        
        for plan in pending_plans:
            should_approve = auto_approve
            
            if should_approve:
                plan_manager.review_plan(plan["id"], True, "擎天柱", "自动审核通过")
                approved.append({
                    "plan_id": plan["id"],
                    "task_id": plan["task_id"],
                    "type": plan.get("type", "unknown")
                })
                msg = "plan_id=" + plan["id"] + ", task_id=" + plan["task_id"]
                self._add_log("plan_approved", msg, actor="擎天柱")
            else:
                plan_manager.review_plan(plan["id"], False, "擎天柱", "需要人工审核")
                rejected.append({
                    "plan_id": plan["id"],
                    "task_id": plan["task_id"],
                    "reason": "需要人工审核"
                })
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "actor": "擎天柱",
            "action": "自动审核计划",
            "approved": approved,
            "rejected": rejected,
            "auto_approve": auto_approve
        }
        
        print("[Auto] 擎天柱自动审核：", len(approved), "个通过，", len(rejected), "个拒绝")
        return result
    
    def run_full_auto(self):
        print("[Auto] 开始全自动流程...")
        generate_result = self.leonardo_auto_generate()
        review_result = self.optimus_auto_review(auto_approve=True)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "generate": generate_result,
            "review": review_result
        }
    
    def get_auto_logs(self, limit=50):
        return sorted(self.logs, key=lambda x: x["timestamp"], reverse=True)[:limit]

auto_plan_manager = AutoPlanManager()
