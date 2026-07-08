#!/usr/bin/env python3
"""Codex job runner for OpenClaw development agents."""

import json
import os
import shlex
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "codex_jobs")
INDEX_FILE = os.path.join(DATA_DIR, "jobs.json")
LOOP_INDEX_FILE = os.path.join(DATA_DIR, "loops.json")
DEFAULT_REPO = os.getenv("CODEX_DEFAULT_REPO", "/Users/apple/.openclaw/workspace/team-dashboard")
CODEX_BIN = os.getenv("CODEX_BIN", "/opt/homebrew/bin/codex")
CODEX_PATH = os.getenv(
    "CODEX_PATH",
    "/opt/homebrew/bin:/opt/homebrew/Cellar/node/25.6.1_1/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
)
CODEX_RUNNER_MODE = os.getenv("CODEX_RUNNER_MODE", "local").strip().lower()
CODEX_REMOTE_HOST = os.getenv("CODEX_REMOTE_HOST", "").strip()
CODEX_REMOTE_USER = os.getenv("CODEX_REMOTE_USER", "").strip()
CODEX_REMOTE_PORT = os.getenv("CODEX_REMOTE_PORT", "").strip()
CODEX_REMOTE_REPO = os.getenv("CODEX_REMOTE_REPO", "").strip()
CODEX_REMOTE_CODEX_BIN = os.getenv("CODEX_REMOTE_CODEX_BIN", "/opt/homebrew/bin/codex").strip()
CODEX_REMOTE_PATH = os.getenv("CODEX_REMOTE_PATH", CODEX_PATH).strip()
CODEX_REMOTE_SSH_KEY = os.getenv("CODEX_REMOTE_SSH_KEY", "").strip()


DEVELOPMENT_AGENTS = {
    "optimus": "总项目管理 / Loop 控制者",
    "wheeljack": "方案设计 / 技术架构",
    "leonardo": "架构师 / 开发负责人",
    "donatello": "前端开发",
    "raphael": "后端开发",
    "michelangelo": "测试工程",
}

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class CodexJobService:
    def __init__(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        self._processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def list_jobs(self, agent_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        self._reconcile_interrupted_jobs()
        jobs = self._load_jobs()
        if agent_id:
            jobs = [job for job in jobs if job.get("agent_id") == agent_id]
        jobs.sort(key=lambda job: job.get("created_at") or "", reverse=True)
        return [self._public_job(job) for job in jobs[:limit]]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._reconcile_interrupted_jobs()
        job = self._find_job(job_id)
        return self._public_job(job) if job else None

    def get_logs(self, job_id: str, tail: int = 400) -> Dict[str, Any]:
        self._reconcile_interrupted_jobs()
        job = self._find_job(job_id)
        if not job:
            raise KeyError(job_id)
        logs = self._read_log(job_id)
        return {"job": self._public_job(job), "logs": logs[-tail:]}

    def list_loops(self, task_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        loops = self._load_loops()
        if task_id:
            loops = [loop for loop in loops if loop.get("task_id") == task_id]
        loops.sort(key=lambda loop: loop.get("created_at") or "", reverse=True)
        return loops[:limit]

    def get_loop(self, loop_id: str) -> Optional[Dict[str, Any]]:
        return self._find_loop(loop_id)

    def create_loop(
        self,
        task_id: str,
        instruction: str,
        title: str = "",
        repo: Optional[str] = None,
        developer_agent_id: str = "leonardo",
        planner_agent_id: str = "leonardo",
        evaluator_agent_id: str = "michelangelo",
        max_rounds: int = 2,
    ) -> Dict[str, Any]:
        if not instruction.strip():
            raise ValueError("instruction is required")
        loop_id = f"loop-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = self._now()
        loop = {
            "id": loop_id,
            "task_id": task_id,
            "title": title or task_id,
            "instruction": instruction.strip(),
            "repo": os.path.abspath(repo or DEFAULT_REPO),
            "status": "queued",
            "current_round": 0,
            "current_stage": "queued",
            "max_rounds": max(1, min(int(max_rounds or 2), 5)),
            "planner_agent_id": planner_agent_id,
            "developer_agent_id": developer_agent_id,
            "evaluator_agent_id": evaluator_agent_id,
            "rounds": [],
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "summary": "",
            "error": None,
        }
        self._append_loop(loop)
        thread = threading.Thread(target=self._run_loop, args=(loop_id,), daemon=True)
        thread.start()
        return loop

    def create_job(
        self,
        agent_id: str,
        instruction: str,
        repo: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not instruction.strip():
            raise ValueError("instruction is required")
        job_id = f"codex-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        repo_path = os.path.abspath(repo or DEFAULT_REPO)
        now = self._now()
        role = DEVELOPMENT_AGENTS.get(agent_id, "开发智能体")
        final_file = os.path.join(DATA_DIR, f"{job_id}.final.md")
        log_file = os.path.join(DATA_DIR, f"{job_id}.log")
        prompt = self._build_prompt(agent_id, role, instruction, task_id)
        command, stdin_prompt, runner_mode = self._build_job_command(job_id, repo_path, final_file, prompt)
        job = {
            "id": job_id,
            "agent_id": agent_id,
            "agent_role": role,
            "task_id": task_id,
            "instruction": instruction.strip(),
            "repo": repo_path,
            "status": "queued",
            "command": command,
            "stdin_prompt": stdin_prompt,
            "runner_mode": runner_mode,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "error": None,
            "log_file": log_file,
            "final_file": final_file,
            "summary": "",
        }
        if metadata:
            job.update(metadata)
        self._append_job(job)
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return self._public_job(job)

    def _run_loop(self, loop_id: str) -> None:
        loop = self._find_loop(loop_id)
        if not loop:
            return
        try:
            previous_feedback = ""
            loop["status"] = "running"
            loop["updated_at"] = self._now()
            self._replace_loop(loop)
            for round_index in range(1, int(loop.get("max_rounds") or 1) + 1):
                loop = self._find_loop(loop_id) or loop
                loop["current_round"] = round_index
                loop["current_stage"] = "plan"
                round_data = {"round": round_index, "stage": "plan", "jobs": []}
                loop.setdefault("rounds", []).append(round_data)
                self._replace_loop(loop)

                plan_job = self.create_job(
                    loop.get("planner_agent_id") or "leonardo",
                    self._build_loop_stage_instruction(loop, round_index, "plan", previous_feedback),
                    repo=loop.get("repo"),
                    task_id=loop.get("task_id"),
                    metadata=self._loop_job_metadata(loop_id, round_index, "plan", loop.get("task_id")),
                )
                self._append_loop_round_job(loop_id, round_index, plan_job.get("id"))
                plan_job = self._wait_for_job(plan_job["id"])
                if plan_job.get("status") != "succeeded":
                    self._finish_loop(loop_id, "failed", f"方案阶段失败：{plan_job.get('error') or plan_job.get('status')}")
                    return

                loop = self._find_loop(loop_id) or loop
                loop["current_stage"] = "develop"
                self._replace_loop(loop)
                develop_job = self.create_job(
                    loop.get("developer_agent_id") or "leonardo",
                    self._build_loop_stage_instruction(loop, round_index, "develop", self._job_feedback(plan_job)),
                    repo=loop.get("repo"),
                    task_id=loop.get("task_id"),
                    metadata=self._loop_job_metadata(loop_id, round_index, "develop", loop.get("task_id")),
                )
                self._append_loop_round_job(loop_id, round_index, develop_job.get("id"))
                develop_job = self._wait_for_job(develop_job["id"])
                if develop_job.get("status") != "succeeded":
                    previous_feedback = self._job_feedback(develop_job)
                    if round_index >= loop.get("max_rounds", 1):
                        self._finish_loop(loop_id, "failed", f"开发阶段失败：{develop_job.get('error') or develop_job.get('status')}")
                        return
                    continue

                loop = self._find_loop(loop_id) or loop
                loop["current_stage"] = "evaluate"
                self._replace_loop(loop)
                evaluate_job = self.create_job(
                    loop.get("evaluator_agent_id") or "michelangelo",
                    self._build_loop_stage_instruction(loop, round_index, "evaluate", self._job_feedback(develop_job)),
                    repo=loop.get("repo"),
                    task_id=loop.get("task_id"),
                    metadata=self._loop_job_metadata(loop_id, round_index, "evaluate", loop.get("task_id")),
                )
                self._append_loop_round_job(loop_id, round_index, evaluate_job.get("id"))
                evaluate_job = self._wait_for_job(evaluate_job["id"])
                previous_feedback = self._job_feedback(evaluate_job)
                if evaluate_job.get("status") == "succeeded" and self._evaluation_passed(previous_feedback):
                    self._finish_loop(loop_id, "succeeded", previous_feedback)
                    return

            self._finish_loop(loop_id, "failed", previous_feedback or "达到最大轮次，评估仍未通过。")
        except Exception as exc:
            self._finish_loop(loop_id, "failed", str(exc))

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        job = self._find_job(job_id)
        if not job:
            raise KeyError(job_id)
        proc = self._processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        job["status"] = "cancelled"
        job["finished_at"] = self._now()
        job["updated_at"] = job["finished_at"]
        self._replace_job(job)
        self._append_log(job_id, "[codex-runner] job cancelled\n")
        return self._public_job(job)

    def _run_job(self, job_id: str) -> None:
        job = self._find_job(job_id)
        if not job:
            return
        if self._runner_mode() == "local" and not os.path.isfile(CODEX_BIN):
            job.update({
                "status": "failed",
                "error": f"Codex CLI 不存在：{CODEX_BIN}",
                "finished_at": self._now(),
                "updated_at": self._now(),
                "exit_code": 127,
            })
            self._replace_job(job)
            self._append_log(job_id, f"[codex-runner] {job['error']}\n")
            return

        os.makedirs(os.path.dirname(job["log_file"]), exist_ok=True)
        env = os.environ.copy()
        env["PATH"] = CODEX_PATH
        job["status"] = "running"
        job["started_at"] = self._now()
        job["updated_at"] = job["started_at"]
        self._replace_job(job)
        self._append_log(job_id, f"[codex-runner] start {job_id}\n[codex-runner] repo={job['repo']}\n")

        try:
            process_cwd = job["repo"]
            if job.get("runner_mode") == "ssh":
                process_cwd = DEFAULT_REPO if os.path.isdir(DEFAULT_REPO) else os.path.dirname(__file__)
            proc = subprocess.Popen(
                job["command"],
                cwd=process_cwd,
                stdin=subprocess.PIPE if job.get("stdin_prompt") else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
            self._processes[job_id] = proc
            assert proc.stdout is not None
            if job.get("stdin_prompt") and proc.stdin:
                proc.stdin.write(str(job["stdin_prompt"]))
                proc.stdin.close()
            for line in proc.stdout:
                self._append_log(job_id, line)
            exit_code = proc.wait()
            job = self._find_job(job_id) or job
            if job.get("status") != "cancelled":
                job["exit_code"] = exit_code
                job["status"] = "succeeded" if exit_code == 0 else "failed"
                job["finished_at"] = self._now()
                job["updated_at"] = job["finished_at"]
                job["summary"] = self._read_final(job.get("final_file")) or self._read_remote_final_from_log(job_id)
                if exit_code != 0 and not job["error"]:
                    job["error"] = f"Codex CLI exited with {exit_code}"
                self._replace_job(job)
        except Exception as exc:
            job = self._find_job(job_id) or job
            job.update({
                "status": "failed",
                "error": str(exc),
                "finished_at": self._now(),
                "updated_at": self._now(),
            })
            self._replace_job(job)
            self._append_log(job_id, f"[codex-runner] failed: {exc}\n")
        finally:
            self._processes.pop(job_id, None)

    def _build_prompt(self, agent_id: str, role: str, instruction: str, task_id: Optional[str]) -> str:
        return "\n".join([
            f"你现在代表 OpenClaw 智能体 {agent_id}（{role}）执行一次程序开发 Loop。",
            f"任务编号：{task_id or '未绑定'}",
            "",
            "Loop 要求：",
            "1. 先阅读相关代码，再做最小必要修改。",
            "2. 不要提交 git commit，不要推送。",
            "3. 不要回退或覆盖与本任务无关的现有改动。",
            "4. 修改后必须优先运行最贴近任务的构建、测试或接口验证。",
            "5. 如果验证失败，基于错误信息继续修正一轮；仍失败则停止扩大改动并清楚记录阻塞点。",
            "6. 最终反馈必须包含：改了什么、改了哪些文件、验证结果、失败/风险、下一轮建议。",
            "",
            "用户任务：",
            instruction.strip(),
        ])

    def _runner_mode(self) -> str:
        return "ssh" if CODEX_RUNNER_MODE in {"ssh", "remote"} else "local"

    def _remote_target(self) -> str:
        if not CODEX_REMOTE_HOST:
            raise ValueError("CODEX_REMOTE_HOST is required when CODEX_RUNNER_MODE=ssh")
        return f"{CODEX_REMOTE_USER}@{CODEX_REMOTE_HOST}" if CODEX_REMOTE_USER else CODEX_REMOTE_HOST

    def _build_job_command(self, job_id: str, repo_path: str, final_file: str, prompt: str) -> tuple[List[str], Optional[str], str]:
        if self._runner_mode() != "ssh":
            return [
                CODEX_BIN,
                "--ask-for-approval",
                "never",
                "exec",
                "--cd",
                repo_path,
                "--sandbox",
                "workspace-write",
                "--output-last-message",
                final_file,
                prompt,
            ], None, "local"

        remote_repo = os.path.abspath(os.path.expanduser(CODEX_REMOTE_REPO or repo_path))
        remote_final = f"/tmp/openclaw-codex/{job_id}.final.md"
        ssh_command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
        if CODEX_REMOTE_PORT:
            ssh_command.extend(["-p", CODEX_REMOTE_PORT])
        if CODEX_REMOTE_SSH_KEY:
            ssh_command.extend(["-i", os.path.expanduser(CODEX_REMOTE_SSH_KEY)])

        script = "\n".join([
            "set +e",
            "mkdir -p /tmp/openclaw-codex",
            f"cd {shlex.quote(remote_repo)}",
            f"export PATH={shlex.quote(CODEX_REMOTE_PATH)}",
            (
                f"{shlex.quote(CODEX_REMOTE_CODEX_BIN)} --ask-for-approval never exec "
                f"--cd {shlex.quote(remote_repo)} --sandbox workspace-write "
                f"--output-last-message {shlex.quote(remote_final)}"
            ),
            "rc=$?",
            f"printf '\\n[openclaw-remote-final] {shlex.quote(remote_final)}\\n'",
            f"if [ -f {shlex.quote(remote_final)} ]; then",
            "  printf '\\n__OPENCLAW_FINAL_BEGIN__\\n'",
            f"  cat {shlex.quote(remote_final)}",
            "  printf '\\n__OPENCLAW_FINAL_END__\\n'",
            "fi",
            "exit $rc",
        ])
        ssh_command.extend([self._remote_target(), "bash", "-lc", shlex.quote(script)])
        return ssh_command, prompt, "ssh"

    def _build_loop_stage_instruction(self, loop: Dict[str, Any], round_index: int, stage: str, feedback: str) -> str:
        stage_name = {
            "plan": "方案编写",
            "develop": "开发实现",
            "evaluate": "测试评估",
        }[stage]
        common = [
            f"协同 Loop：{loop.get('title') or loop.get('task_id')}",
            f"Loop ID：{loop.get('id')}",
            f"第 {round_index} 轮 / 阶段：{stage_name}",
            f"任务编号：{loop.get('task_id') or '未绑定'}",
            "",
            "原始目标：",
            loop.get("instruction", ""),
        ]
        if feedback:
            common.extend(["", "上一阶段反馈：", feedback[:4000]])
        if stage == "plan":
            common.extend([
                "",
                "你的角色：方案编写者。请输出本轮开发方案。",
                "必须包含：目标边界、涉及文件/模块、实现步骤、验收标准、风险和交给开发者的明确指令。",
                "不要直接修改代码，除非发现方案所需的极小配置错误。",
            ])
        elif stage == "develop":
            common.extend([
                "",
                "你的角色：开发执行者。请按方案完成最小闭环开发。",
                "必须执行：阅读相关代码 -> 实现最小修改 -> 运行最贴近的构建/测试/接口验证。",
                "验证失败时基于错误修正一轮；仍失败则停止扩大范围并记录阻塞点。",
            ])
        else:
            common.extend([
                "",
                "你的角色：测试评估者。请评估本轮开发是否满足验收标准。",
                "必须执行：检查改动、运行或说明最贴近的验证方式、判断是否通过。",
                "最终第一行必须写：评估结论：通过 或 评估结论：不通过。",
                "如果不通过，请给出下一轮需要修复的问题清单。",
            ])
        return "\n".join(common)

    def _loop_job_metadata(self, loop_id: str, round_index: int, stage: str, parent_task_id: Optional[str]) -> Dict[str, Any]:
        return {
            "loop_id": loop_id,
            "loop_round": round_index,
            "loop_stage": stage,
            "parent_task_id": parent_task_id,
        }

    def _wait_for_job(self, job_id: str, timeout_seconds: int = 60 * 60) -> Dict[str, Any]:
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            job = self._find_job(job_id)
            if job and job.get("status") in TERMINAL_STATUSES:
                return self._public_job(job)
            time.sleep(2)
        job = self._find_job(job_id) or {"id": job_id}
        job["status"] = "failed"
        job["error"] = "Loop 等待 Codex Job 超时"
        job["finished_at"] = self._now()
        job["updated_at"] = job["finished_at"]
        self._replace_job(job)
        return self._public_job(job)

    def _job_feedback(self, job: Dict[str, Any]) -> str:
        parts = [
            f"Job：{job.get('id')}",
            f"状态：{job.get('status')}",
        ]
        if job.get("error"):
            parts.append(f"错误：{job.get('error')}")
        if job.get("summary"):
            parts.append(str(job.get("summary"))[:6000])
        elif job.get("id"):
            parts.append("".join(self._read_log(job["id"])[-120:])[:6000])
        return "\n".join(parts)

    def _evaluation_passed(self, feedback: str) -> bool:
        text = (feedback or "").lower()
        if "评估结论：不通过" in feedback or "评估结论: 不通过" in feedback:
            return False
        if "不通过" in feedback[:500] or "未通过" in feedback[:500]:
            return False
        if any(word in text[:1000] for word in ["failed", "failure", "error", "阻塞"]):
            return False
        return True

    def _finish_loop(self, loop_id: str, status: str, summary: str = "") -> None:
        loop = self._find_loop(loop_id)
        if not loop:
            return
        loop["status"] = status
        loop["current_stage"] = "done" if status == "succeeded" else "failed"
        loop["summary"] = summary[:12000] if summary else ""
        loop["error"] = "" if status == "succeeded" else (summary[:1200] if summary else "Loop 执行失败")
        loop["finished_at"] = self._now()
        loop["updated_at"] = loop["finished_at"]
        self._replace_loop(loop)

    def _append_loop_round_job(self, loop_id: str, round_index: int, job_id: Optional[str]) -> None:
        if not job_id:
            return
        loop = self._find_loop(loop_id)
        if not loop:
            return
        rounds = loop.setdefault("rounds", [])
        target = next((item for item in rounds if item.get("round") == round_index), None)
        if not target:
            target = {"round": round_index, "stage": loop.get("current_stage", ""), "jobs": []}
            rounds.append(target)
        jobs = target.setdefault("jobs", [])
        if job_id not in jobs:
            jobs.append(job_id)
        loop["updated_at"] = self._now()
        self._replace_loop(loop)

    def _public_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        data = {key: value for key, value in job.items() if key not in {"command", "stdin_prompt"}}
        data["running"] = job.get("id") in self._processes
        return data

    def _reconcile_interrupted_jobs(self) -> None:
        """Mark jobs lost by a backend restart as failed so the UI never shows endless running."""
        with self._lock:
            jobs = self._load_jobs()
            changed = False
            now = self._now()
            for job in jobs:
                job_id = job.get("id")
                if not job_id:
                    continue
                if job.get("status") not in {"queued", "running"} or job_id in self._processes:
                    continue
                if self._age_seconds(job.get("updated_at") or job.get("created_at")) < 15:
                    continue
                job["status"] = "failed"
                job["exit_code"] = job.get("exit_code") if job.get("exit_code") is not None else -1
                job["finished_at"] = job.get("finished_at") or now
                job["updated_at"] = now
                job["error"] = job.get("error") or "Codex 任务已中断：服务重启或执行进程已退出，请重新派发。"
                self._append_log(job_id, f"[codex-runner] interrupted: {job['error']}\n")
                changed = True
            if changed:
                self._save_jobs(jobs)

    def _age_seconds(self, value: Optional[str]) -> float:
        if not value:
            return 999999
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds()
        except Exception:
            return 999999

    def _load_jobs(self) -> List[Dict[str, Any]]:
        if not os.path.exists(INDEX_FILE):
            return []
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _load_loops(self) -> List[Dict[str, Any]]:
        if not os.path.exists(LOOP_INDEX_FILE):
            return []
        with open(LOOP_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = f"{INDEX_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, INDEX_FILE)

    def _save_loops(self, loops: List[Dict[str, Any]]) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = f"{LOOP_INDEX_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(loops, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LOOP_INDEX_FILE)

    def _append_job(self, job: Dict[str, Any]) -> None:
        with self._lock:
            jobs = self._load_jobs()
            jobs.append(job)
            self._save_jobs(jobs)

    def _append_loop(self, loop: Dict[str, Any]) -> None:
        with self._lock:
            loops = self._load_loops()
            loops.append(loop)
            self._save_loops(loops)

    def _replace_job(self, job: Dict[str, Any]) -> None:
        with self._lock:
            jobs = self._load_jobs()
            for idx, item in enumerate(jobs):
                if item.get("id") == job.get("id"):
                    jobs[idx] = job
                    break
            else:
                jobs.append(job)
            self._save_jobs(jobs)

    def _replace_loop(self, loop: Dict[str, Any]) -> None:
        with self._lock:
            loops = self._load_loops()
            for idx, item in enumerate(loops):
                if item.get("id") == loop.get("id"):
                    loops[idx] = loop
                    break
            else:
                loops.append(loop)
            self._save_loops(loops)

    def _find_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return next((job for job in self._load_jobs() if job.get("id") == job_id), None)

    def _find_loop(self, loop_id: str) -> Optional[Dict[str, Any]]:
        return next((loop for loop in self._load_loops() if loop.get("id") == loop_id), None)

    def _append_log(self, job_id: str, text: str) -> None:
        with open(os.path.join(DATA_DIR, f"{job_id}.log"), "a", encoding="utf-8") as f:
            f.write(text)

    def _read_log(self, job_id: str) -> List[str]:
        path = os.path.join(DATA_DIR, f"{job_id}.log")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()

    def _read_final(self, path: Optional[str]) -> str:
        if not path or not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:12000]

    def _read_remote_final_from_log(self, job_id: str) -> str:
        text = "".join(self._read_log(job_id))
        start = text.rfind("__OPENCLAW_FINAL_BEGIN__")
        end = text.rfind("__OPENCLAW_FINAL_END__")
        if start == -1 or end == -1 or end <= start:
            return ""
        return text[start + len("__OPENCLAW_FINAL_BEGIN__"):end].strip()[:12000]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


codex_job_service = CodexJobService()
