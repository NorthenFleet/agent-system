"""Canonical cluster step integration; not registered with a production worker.

No second approval store, cross-database transaction, or remote exactly-once
claim. A CommandCenter lease and its consumed approval authorize one dispatch.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from services.cluster_execution import ExecutionBlocked, OperationRequest


class ClusterStepAuthority:
    def __init__(self, *, command_center, work_runs, step_id: str,
                 lease_token: str, worker_id: str):
        if command_center.repository is not work_runs.repository:
            raise ExecutionBlocked("shared_repository_required")
        if not step_id or not lease_token or not worker_id:
            raise ExecutionBlocked("step_lease_required")
        self.command_center, self.work_runs = command_center, work_runs
        self.step_id, self.lease_token, self.worker_id = step_id, lease_token, worker_id
        self.lease_sha256 = hashlib.sha256(lease_token.encode()).hexdigest()

    def _locked(self, conn):
        cc = self.command_center
        first = conn.execute("SELECT mission_id FROM mission_steps WHERE id=?", (self.step_id,)).fetchone()
        if not first:
            raise ExecutionBlocked("step_not_found")
        suffix = " FOR UPDATE" if cc.repository.backend == "postgresql" else ""
        # Match mission cancellation's lock order; never hold locks during SSH.
        mission = conn.execute("SELECT * FROM orchestration_missions WHERE id=?" + suffix,
                               (first["mission_id"],)).fetchone()
        row = conn.execute("SELECT * FROM mission_steps WHERE id=?" + suffix, (self.step_id,)).fetchone()
        if not mission or not row:
            raise ExecutionBlocked("step_not_found")
        step = cc._serialize_step(row)
        conn.execute("SELECT id FROM mission_plan_versions WHERE mission_id=? AND version=?" + suffix,
                     (mission["id"], step["plan_version"])).fetchone()
        cc._attach_plan_step_contract(conn, step)
        return mission, step

    @staticmethod
    def _future(value: str) -> bool:
        try:
            expiry = datetime.fromisoformat(value)
            return expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return False

    def _validate(self, conn, mission, step, request, actor):
        if (mission["status"] != "running" or mission["approval_status"] != "approved"
                or mission["plan_version"] != step["plan_version"]
                or str(mission["owner_user_id"] or "") != actor):
            raise ExecutionBlocked("mission_authority_changed")
        if (step["status"] != "running" or step["lease_token"] != self.lease_token
                or step["lease_owner"] != self.worker_id or not self._future(step["lease_expires_at"])):
            raise ExecutionBlocked("step_lease_lost")
        if (step["task_type"] != "cluster_operation" or step["executor"] != "cluster-readonly-v1"
                or step.get("approval_required") is not True or step.get("side_effect") is not False
                or step.get("max_attempts") != 1
                or not isinstance(step.get("idempotency_key"), str) or not step["idempotency_key"].strip()
                or step["input"] != {"cluster_operation": request.model_dump()}):
            raise ExecutionBlocked("cluster_contract_mismatch")
        approval = conn.execute(
            "SELECT * FROM mission_step_approvals WHERE step_id=? ORDER BY request_version DESC LIMIT 1",
            (self.step_id,),
        ).fetchone()
        if (not approval or approval["status"] != "consumed" or not approval["consumed_at"]
                or not approval["decided_by"] or approval["mission_id"] != mission["id"]
                or approval["plan_version"] != step["plan_version"]
                or approval["contract_hash"] != self.command_center._step_contract_hash(step)):
            raise ExecutionBlocked("consumed_approval_required")
        # A consumed grant must have been used before its expiry. Completion may
        # occur after approval expiry, but never after the live step lease expires.
        if approval["consumed_at"] >= approval["expires_at"]:
            raise ExecutionBlocked("approval_consumed_after_expiry")
        return approval

    def claim(self, request: OperationRequest, principal: dict, credential_user: str):
        if principal.get("role") != "admin" or principal.get("auth_mode") == "development":
            raise ExecutionBlocked("formal_administrator_required")
        actor = str(principal.get("sub", ""))
        with self.command_center.connect(immediate=True) as conn:
            mission, step = self._locked(conn)
            approval = self._validate(conn, mission, step, request, actor)
            proof = {"mission_id": mission["id"], "plan_version": step["plan_version"],
                     "step_id": self.step_id, "approval_id": approval["id"],
                     "contract_hash": approval["contract_hash"],
                     "step_idempotency_key": step["idempotency_key"]}
            fence = {**proof, "lease_sha256": self.lease_sha256, "actor": actor}
            mission_run = self.command_center._ensure_mission_run(conn, mission["id"])
            run, created = self.work_runs.claim_at_most_once(
                dispatch_id=f"mission-step:{self.step_id}", idempotency_key=step["idempotency_key"],
                request_binding={**{k: v for k, v in proof.items() if k != "approval_id"},
                                 "request": request.model_dump(), "actor": actor,
                                 "credential_user": credential_user},
                agent_id=self.worker_id, executor="cluster-readonly-v1", mission_id=mission["id"],
                mission_run_id=mission_run["id"], correlation_id=mission_run["correlation_id"],
                input_context={"request": request.model_dump(), "_cluster_step_fence": fence},
                lease_seconds=60, _connection=conn,
            )
            if created:
                conn.execute("UPDATE mission_steps SET work_run_id=? WHERE id=?", (run["id"], self.step_id))
                run = self.work_runs.transition(run["id"], "running", actor=self.worker_id,
                    detail="Canonical approved cluster dispatch", _connection=conn, _step_fence=self.lease_sha256)
            elif run["input_context"].get("_cluster_step_fence", {}).get("lease_sha256") != self.lease_sha256:
                # A fresh approval may resolve an old attempt, never dispatch it
                # again. Close the newly claimed step in this same transaction.
                old_fence = run["input_context"].get("_cluster_step_fence") or {}
                if old_fence.get("step_id") != self.step_id or not old_fence.get("lease_sha256"):
                    raise ExecutionBlocked("work_run_fence_mismatch")
                receipt = dict(run.get("execution_result") or {})
                confirmed = (run["status"] == "completed" and receipt.get("status") == "succeeded"
                             and receipt.get("remote_outcome") == "confirmed")
                if not confirmed:
                    receipt = {"schema_version": "cluster-execution-receipt.v1", "run_id": run["id"],
                               "status": "reconciliation_required", "remote_outcome": "unknown",
                               "exit_code": None, "log": "", **{k: request.model_dump()[k]
                               for k in ("request_id", "node_id", "tailscale_id", "operation")}}
                    if run["status"] in {"claimed", "running"}:
                        run = self.work_runs.transition(run["id"], "blocked", actor=self.worker_id,
                            detail="New lease found unresolved old attempt; no redispatch",
                            execution_result={**receipt, **{k: old_fence[k] for k in proof}},
                            failure_code="remote_outcome_unknown", _connection=conn,
                            _step_fence=old_fence["lease_sha256"])
                replay = {**receipt, **proof, "replayed": True,
                          "previous_approval_id": old_fence["approval_id"]}
                conn.execute("UPDATE mission_steps SET work_run_id=? WHERE id=?", (run["id"], self.step_id))
                self._complete(conn, replay, confirmed)
                # The WorkRun retains its original immutable receipt. This return
                # value describes the new step's recovery and fresh authorization.
                run = {**run, "execution_result": replay}
            return run, created

    def _complete(self, conn, receipt, success):
        result = {"outcome": "succeeded" if success else "blocked", "summary": "Controlled host.info receipt",
                  "cluster_receipt": receipt, "tools_used": ["host.info"],
                  "evidence": [{"evidence_type": "cluster_receipt", "source_ref": f"work-run:{receipt['run_id']}",
                                "summary": receipt.get("log") or "Remote outcome unknown"}],
                  "risk_notes": "" if success else "Unknown remote outcome; do not retry"}
        return self.command_center.complete_step(self.step_id, result=result, success=success,
            actor=self.worker_id, lease_token=self.lease_token, _connection=conn)

    def finish(self, run_id: str, receipt: dict) -> dict:
        with self.command_center.connect(immediate=True) as conn:
            mission, step = self._locked(conn)
            run = self.work_runs._get_run(conn, run_id)
            fence = run["input_context"].get("_cluster_step_fence") or {}
            if (fence.get("step_id") != self.step_id or fence.get("lease_sha256") != self.lease_sha256
                    or step.get("work_run_id") != run_id or run["status"] != "running"):
                raise ExecutionBlocked("work_run_fence_mismatch")
            request = OperationRequest.model_validate(run["input_context"]["request"])
            approval = self._validate(conn, mission, step, request, fence["actor"])
            if approval["id"] != fence["approval_id"] or approval["contract_hash"] != fence["contract_hash"]:
                raise ExecutionBlocked("approval_binding_changed")
            proof = {k: fence[k] for k in ("mission_id", "plan_version", "step_id", "approval_id",
                                          "contract_hash", "step_idempotency_key")}
            receipt = {**receipt, **proof, "run_id": run_id}
            success = receipt.get("status") == "succeeded" and receipt.get("remote_outcome") == "confirmed"
            completed = self._complete(conn, receipt, success)
            accepted = completed["status"] == "completed"
            if not accepted:
                receipt = {**receipt, "acceptance": "blocked"}
            self.work_runs.transition(run_id, "review" if accepted else "blocked", actor=self.worker_id,
                detail="Canonical fenced cluster receipt", execution_result=receipt,
                failure_code=None if accepted else "cluster_acceptance_blocked",
                _connection=conn, _step_fence=self.lease_sha256)
            if accepted:
                self.work_runs.transition(run_id, "completed", actor=self.worker_id,
                    detail="Canonical step accepted", _connection=conn, _step_fence=self.lease_sha256)
            return receipt

    def reconcile(self, run_id: str) -> dict:
        """Explicit conservative reconciliation, never retry or accept a late result."""
        with self.command_center.connect(immediate=True) as conn:
            mission, step = self._locked(conn)
            run = self.work_runs._get_run(conn, run_id)
            fence = run["input_context"].get("_cluster_step_fence") or {}
            if fence.get("step_id") != self.step_id or not fence.get("lease_sha256"):
                raise ExecutionBlocked("work_run_fence_mismatch")
            if run["status"] not in {"claimed", "running"}:
                return run
            if (mission["status"] == "running" and mission["plan_version"] == step["plan_version"]
                    and step["status"] == "running"
                    and hashlib.sha256(str(step["lease_token"] or "").encode()).hexdigest() == fence["lease_sha256"]
                    and self._future(step["lease_expires_at"])):
                raise ExecutionBlocked("live_lease_not_reconcilable")
            receipt = {"schema_version": "cluster-execution-receipt.v1", "run_id": run_id,
                       "step_id": self.step_id, "approval_id": fence["approval_id"],
                       "contract_hash": fence["contract_hash"], "status": "lease_lost",
                       "remote_outcome": "unknown", "exit_code": None, "log": "",
                       "ended_at": datetime.now(timezone.utc).isoformat(), "replayed": False}
            return self.work_runs.transition(run_id, "blocked", actor="cluster-reconciler",
                detail="Lost lease; remote outcome unknown; no retry", execution_result=receipt,
                failure_code="remote_outcome_unknown", _connection=conn, _step_fence=fence["lease_sha256"])
