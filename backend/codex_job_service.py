#!/usr/bin/env python3
"""Codex job runner for OpenClaw development agents."""

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "codex_jobs")
INDEX_FILE = os.path.join(DATA_DIR, "jobs.json")
DEFAULT_REPO = os.getenv("CODEX_DEFAULT_REPO", "/Users/apple/.openclaw/workspace/team-dashboard")
CODEX_BIN = os.getenv("CODEX_BIN", "/opt/homebrew/bin/codex")
CODEX_PATH = os.getenv(
    "CODEX_PATH",
    "/opt/homebrew/bin:/opt/homebrew/Cellar/node/25.6.1_1/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
)


DEVELOPMENT_AGENTS = {
    "leonardo": "架构师 / 开发负责人",
    "donatello": "前端开发",
    "raphael": "后端开发",
    "michelangelo": "测试工程",
}


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

    def create_job(self, agent_id: str, instruction: str, repo: Optional[str] = None, task_id: Optional[str] = None) -> Dict[str, Any]:
        if not instruction.strip():
            raise ValueError("instruction is required")
        job_id = f"codex-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        repo_path = os.path.abspath(repo or DEFAULT_REPO)
        now = self._now()
        role = DEVELOPMENT_AGENTS.get(agent_id, "开发智能体")
        final_file = os.path.join(DATA_DIR, f"{job_id}.final.md")
        log_file = os.path.join(DATA_DIR, f"{job_id}.log")
        prompt = self._build_prompt(agent_id, role, instruction, task_id)
        command = [
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
        ]
        job = {
            "id": job_id,
            "agent_id": agent_id,
            "agent_role": role,
            "task_id": task_id,
            "instruction": instruction.strip(),
            "repo": repo_path,
            "status": "queued",
            "command": command,
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
        self._append_job(job)
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return self._public_job(job)

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
        if not os.path.isfile(CODEX_BIN):
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
            proc = subprocess.Popen(
                job["command"],
                cwd=job["repo"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
            self._processes[job_id] = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append_log(job_id, line)
            exit_code = proc.wait()
            job = self._find_job(job_id) or job
            if job.get("status") != "cancelled":
                job["exit_code"] = exit_code
                job["status"] = "succeeded" if exit_code == 0 else "failed"
                job["finished_at"] = self._now()
                job["updated_at"] = job["finished_at"]
                job["summary"] = self._read_final(job.get("final_file"))
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
            f"你现在代表 OpenClaw 智能体 {agent_id}（{role}）执行一次受控开发任务。",
            f"任务编号：{task_id or '未绑定'}",
            "",
            "要求：",
            "1. 先阅读相关代码，再做最小必要修改。",
            "2. 不要提交 git commit，不要推送。",
            "3. 不要回退或覆盖与本任务无关的现有改动。",
            "4. 尽量运行能证明修改正确的构建或测试。",
            "5. 最终反馈必须包含：改了什么、改了哪些文件、验证结果、风险/后续建议。",
            "",
            "用户任务：",
            instruction.strip(),
        ])

    def _public_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        data = {key: value for key, value in job.items() if key not in {"command"}}
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

    def _save_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = f"{INDEX_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, INDEX_FILE)

    def _append_job(self, job: Dict[str, Any]) -> None:
        with self._lock:
            jobs = self._load_jobs()
            jobs.append(job)
            self._save_jobs(jobs)

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

    def _find_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return next((job for job in self._load_jobs() if job.get("id") == job_id), None)

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

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


codex_job_service = CodexJobService()
