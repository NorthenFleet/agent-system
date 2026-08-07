import asyncio
import hashlib
import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.writing_collaboration import WritingDocumentState, WritingDocumentVersion, WritingJarvisRun
from services.document_workspace_service import DocumentWorkspaceError
from services.writing_research_service import WritingResearchService, mission_planning_adapter


def _service(compiler=None):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with sessions() as session:
        session.add(WritingDocumentState(
            project_id="project-1",
            document_id="document-1",
            document_revision=2,
            content_json={"type": "doc", "content": []},
            content_sha256="a" * 64,
            source_markdown_sha256="b" * 64,
            projection_revision=2,
            projection_status="current",
            approved_revision=0,
            published_revision=0,
            created_at=now,
            updated_at=now,
        ))
        session.add(WritingDocumentVersion(
            id="version-2",
            project_id="project-1",
            document_id="document-1",
            document_revision=2,
            label="current",
            reason="checkpoint",
            content_json={"type": "doc", "content": []},
            content_sha256="a" * 64,
            markdown_snapshot="正文",
            actor_type="human",
            actor_id="admin",
            parent_revision=1,
            lifecycle_status="working",
            created_at=now,
        ))
        session.commit()
    evidence_root = tempfile.mkdtemp(prefix="writing-evidence-test-")
    service = WritingResearchService(
        session_factory=sessions,
        research_compiler=compiler or (lambda payload: {"compiled": payload}),
        allow_non_postgres_writes=True,
        evidence_root=evidence_root,
    )
    service._test_evidence_root = evidence_root
    return service


def test_claim_requires_immutable_evidence_before_gap_is_resolved(tmp_path):
    service = _service()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "该方法在多约束条件下具有稳定优势。",
        "minimum_evidence_level": "G2",
        "research_matrix": {"question": "验证稳定优势"},
    }, "admin")
    gap_id = service.workspace_summary("project-1", "document-1")["gaps"][0]["id"]

    with pytest.raises(DocumentWorkspaceError, match="RetrievalRef"):
        service.register_evidence("project-1", "document-1", {
            "source_system": "retrieval",
            "artifact_path": "/snapshot/result.json",
            "artifact_sha256": "a" * 64,
            "evidence_level": "G2",
        }, "admin")

    bundle = tmp_path / "bundle-1.json"
    bundle.write_bytes(b"bundle-1")
    evidence = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "bundle-1",
        "artifact_path": str(bundle),
        "artifact_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "evidence_level": "G2",
        "allowed_claim_scope": "claim_type:argument",
    }, "admin")
    assert Path(evidence["artifact_path"]) != bundle
    bundle.unlink()
    binding = service.bind_evidence("project-1", "document-1", {
        "claim_id": claim["id"],
        "evidence_ref_id": evidence["id"],
    }, "admin")

    assert binding["sufficient"] is True
    summary = service.workspace_summary("project-1", "document-1")
    assert summary["claims"][0]["evidence_status"] == "sufficient"
    assert summary["gaps"] == []
    with pytest.raises(DocumentWorkspaceError, match="已解决"):
        service.dispatch_gap("project-1", "document-1", gap_id, {}, "admin")

    diagnostic_bundle = tmp_path / "bundle-diagnostic.json"
    diagnostic_bundle.write_bytes(b"diagnostic")
    diagnostic = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "bundle-diagnostic",
        "artifact_path": str(diagnostic_bundle),
        "artifact_sha256": hashlib.sha256(diagnostic_bundle.read_bytes()).hexdigest(),
        "evidence_level": "diagnostic",
    }, "admin")
    weaker_binding = service.bind_evidence("project-1", "document-1", {
        "claim_id": claim["id"],
        "evidence_ref_id": diagnostic["id"],
    }, "admin")
    assert weaker_binding["strongest_evidence_level"] == "G2"
    assert weaker_binding["sufficient"] is True


def test_structured_evidence_scope_must_match_claim(tmp_path):
    service = _service()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "需要限定作用范围。",
        "claim_type": "argument",
    }, "admin")
    bundle = tmp_path / "bundle-wrong-scope.json"
    bundle.write_bytes(b"wrong-scope")
    evidence = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "bundle-wrong-scope",
        "artifact_path": str(bundle),
        "artifact_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "evidence_level": "G1",
        "allowed_claim_scope": "claim:another-claim",
    }, "admin")

    with pytest.raises(DocumentWorkspaceError, match="范围"):
        service.bind_evidence("project-1", "document-1", {
            "claim_id": claim["id"],
            "evidence_ref_id": evidence["id"],
        }, "admin")


def test_evidence_snapshot_must_exist_and_match_hash(tmp_path):
    service = _service()
    snapshot = tmp_path / "evidence.json"
    snapshot.write_bytes(b"verified")

    with pytest.raises(DocumentWorkspaceError, match="SHA-256"):
        service.register_evidence("project-1", "document-1", {
            "source_system": "one-sim",
            "artifact_path": str(snapshot),
            "artifact_sha256": "0" * 64,
            "evidence_level": "G1",
        }, "admin")

    with pytest.raises(DocumentWorkspaceError, match="key:value"):
        service.register_evidence("project-1", "document-1", {
            "source_system": "one-sim",
            "artifact_path": str(snapshot),
            "artifact_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "evidence_level": "G1",
            "allowed_claim_scope": "free form scope",
        }, "admin")


def test_gap_dispatch_is_idempotent_and_compiles_research_matrix_once():
    calls = []
    service = _service(lambda payload: calls.append(payload) or {"matrix_id": "matrix-1"})
    service.create_claim("project-1", "document-1", {
        "claim_text": "需要补充对照实验。",
        "minimum_evidence_level": "G1",
        "research_matrix": {"question": "对照实验", "factors": ["policy"]},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]

    first = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "dispatch-1",
        "execution_policy": {"estimated_cost": 0, "preauthorized_cost_limit": 0},
    }, "admin")
    replay = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "dispatch-1",
    }, "admin")

    assert first["status"] == "queued"
    assert replay["id"] == first["id"]
    assert replay["idempotent_replay"] is True
    assert calls == []
    with pytest.raises(DocumentWorkspaceError, match="活跃运行"):
        service.dispatch_gap("project-1", "document-1", gap["id"], {
            "idempotency_key": "dispatch-2",
        }, "admin")
    claimed = service.claim_next_run("worker-compile")
    assert service.workspace_summary("project-1", "document-1")["gaps"][0]["status"] == "running"
    asyncio.run(service.process_run(claimed["id"], "worker-compile"))
    assert len(calls) == 1
    assert service.get_run("project-1", "document-1", first["id"])["recovery_cursor"]["next_step"] == "queue_experiment_plan"


def test_failed_gap_dispatch_requires_explicit_retry_and_creates_new_run():
    service = _service()
    service.create_claim("project-1", "document-1", {
        "claim_text": "需要重试补证。",
        "research_matrix": {"question": "重试"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    first = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "retryable-gap",
    }, "admin")
    with service.session_factory() as session:
        row = session.get(WritingJarvisRun, first["id"])
        row.status = "failed"
        session.commit()

    replay = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "retryable-gap",
    }, "admin")
    retried = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "retryable-gap",
        "retry": True,
        "retry_request_id": "retry-request-1",
    }, "admin")
    retried_replay = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "retryable-gap",
        "retry": True,
        "retry_request_id": "retry-request-1",
    }, "admin")
    with pytest.raises(DocumentWorkspaceError, match="活跃运行"):
        service.dispatch_gap("project-1", "document-1", gap["id"], {
            "idempotency_key": "retryable-gap",
            "retry": True,
            "retry_request_id": "retry-request-2",
        }, "admin")

    assert replay["id"] == first["id"]
    assert retried["id"] != first["id"]
    assert retried["status"] == "queued"
    assert retried_replay["id"] == retried["id"]
    assert retried_replay["idempotent_replay"] is True


def test_expired_worker_cannot_overwrite_new_lease_owner():
    service = _service()
    service.create_claim("project-1", "document-1", {
        "claim_text": "验证租约隔离。",
        "research_matrix": {"question": "租约"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    run = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")
    claimed = service.claim_next_run("worker-old")

    def compiler(_payload):
        with service.session_factory() as session:
            row = session.get(WritingJarvisRun, run["id"])
            row.lease_owner = "worker-new"
            session.commit()
        return {"compiled": {}}

    service.research_compiler = compiler
    asyncio.run(service.process_run(claimed["id"], "worker-old"))

    current = service.get_run("project-1", "document-1", run["id"])
    assert current["status"] == "running"
    assert current["lease_owner"] == "worker-new"
    assert "compiled_matrix" not in current["result_payload"]


def test_paid_or_physical_gap_dispatch_waits_for_approval_without_calling_one_sim():
    calls = []
    service = _service(lambda payload: calls.append(payload) or {})
    service.create_claim("project-1", "document-1", {
        "claim_text": "需要物理设备复核。",
        "research_matrix": {"question": "设备复核"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]

    run = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "execution_policy": {"physical_device": True},
    }, "admin")

    assert run["status"] == "awaiting_approval"
    assert "物理设备" in run["approval_reason"]
    assert calls == []
    service.decide_run("project-1", "document-1", run["id"], "reject", "admin")
    assert service.workspace_summary("project-1", "document-1")["gaps"][0]["status"] == "open"


def test_word_import_persists_immutable_source_and_creates_review_changeset(tmp_path, monkeypatch):
    service = _service()
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    monkeypatch.setenv("WRITING_IMPORT_ROOT", str(tmp_path / "imports"))

    result = service.register_word_import(
        "project-1",
        "document-1",
        filename="review.docx",
        content=buffer.getvalue(),
        base_revision=2,
        actor="admin",
        idempotency_key="word-import-1",
    )

    assert result["mapping_status"] == "manual_review"
    assert Path(result["artifact_path"]).read_bytes() == buffer.getvalue()
    change_set = service.get_change_set("project-1", "document-1", result["change_set_id"])
    assert change_set["status"] == "review_required"
    assert change_set["operations"][0]["artifact_path"] == result["artifact_path"]
    replay = service.register_word_import(
        "project-1",
        "document-1",
        filename="review.docx",
        content=buffer.getvalue(),
        base_revision=2,
        actor="admin",
        idempotency_key="word-import-1",
    )
    assert replay["id"] == result["id"]
    assert replay["idempotent_replay"] is True

    with pytest.raises(DocumentWorkspaceError, match="有效 DOCX"):
        service.register_word_import(
            "project-1",
            "document-1",
            filename="broken.docx",
            content=b"not-a-zip",
            base_revision=2,
            actor="admin",
            idempotency_key="word-import-broken",
        )


def test_word_release_requires_approved_revision_and_full_release_checks(tmp_path):
    service = _service()
    payload = {
        "document_revision": 2,
        "template_sha256": "d" * 64,
        "idempotency_key": "release-2",
    }
    with pytest.raises(DocumentWorkspaceError, match="已审批修订"):
        service.create_release("project-1", "document-1", payload, "admin")

    service.approve_revision("project-1", "document-1", 2, "admin")
    release = service.create_release("project-1", "document-1", payload, "admin")
    stale = service.create_release("project-1", "document-1", {
        **payload,
        "idempotency_key": "release-stale",
    }, "admin")
    with pytest.raises(DocumentWorkspaceError, match="哈希"):
        service.update_release("project-1", "document-1", release["id"], {
            "status": "approved",
        }, "admin")

    docx = tmp_path / "thesis.docx"
    pdf = tmp_path / "thesis.pdf"
    docx.write_bytes(b"docx")
    pdf.write_bytes(b"pdf")
    approved = service.update_release("project-1", "document-1", release["id"], {
        "docx_path": str(docx),
        "docx_sha256": hashlib.sha256(b"docx").hexdigest(),
        "pdf_path": str(pdf),
        "pdf_sha256": hashlib.sha256(b"pdf").hexdigest(),
        "field_refresh_status": "completed",
        "page_check": {"passed": True, "pages": 132},
        "status": "approved",
    }, "admin")
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "admin"
    assert service.require_formal_release("project-1", "document-1", "docx")["id"] == release["id"]
    with service.session_factory() as session:
        session.add(WritingJarvisRun(
            id="active-release-run",
            project_id="project-1",
            document_id="document-1",
            run_type="evidence_gap_dispatch",
            status="queued",
            idempotency_key="active-release-run",
            input_payload={},
            result_payload={},
            recovery_cursor={},
            requested_by="admin",
        ))
        session.commit()
    with pytest.raises(DocumentWorkspaceError, match="Jarvis"):
        service.require_formal_release("project-1", "document-1", "docx")
    with service.session_factory() as session:
        session.get(WritingJarvisRun, "active-release-run").status = "cancelled"
        session.commit()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "正式发布前仍需补证。",
        "minimum_evidence_level": "G1",
    }, "admin")
    with pytest.raises(DocumentWorkspaceError, match="证据缺口"):
        service.require_formal_release("project-1", "document-1", "docx")
    source = tmp_path / "release-evidence.json"
    source.write_bytes(b"release-evidence")
    evidence = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "release-evidence",
        "artifact_path": str(source),
        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evidence_level": "G1",
        "allowed_claim_scope": f"claim:{claim['id']}",
    }, "admin")
    service.bind_evidence("project-1", "document-1", {
        "claim_id": claim["id"],
        "evidence_ref_id": evidence["id"],
    }, "admin")
    immutable_snapshot = Path(evidence["artifact_path"])
    immutable_snapshot.chmod(0o644)
    immutable_snapshot.write_bytes(b"tampered")
    with pytest.raises(DocumentWorkspaceError, match="内容寻址快照"):
        service.require_formal_release("project-1", "document-1", "docx")
    with pytest.raises(DocumentWorkspaceError, match="不可修改"):
        service.update_release("project-1", "document-1", release["id"], {
            "page_check": {"passed": False},
        }, "admin")
    with service.session_factory() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        state.approved_revision = 3
        state.published_revision = 3
        session.commit()
    with pytest.raises(DocumentWorkspaceError, match="当前已审批"):
        service.update_release("project-1", "document-1", stale["id"], {
            "docx_path": str(docx),
            "docx_sha256": hashlib.sha256(b"docx").hexdigest(),
            "pdf_path": str(pdf),
            "pdf_sha256": hashlib.sha256(b"pdf").hexdigest(),
            "field_refresh_status": "completed",
            "page_check": {"passed": True},
            "status": "approved",
        }, "admin")


def test_changeset_without_executor_cannot_be_marked_applied():
    service = _service()
    change_set = service.create_change_set("project-1", "document-1", {
        "operations": [{"op": "word_import_compare"}],
        "idempotency_key": "manual-only",
    }, "admin")

    with pytest.raises(DocumentWorkspaceError, match="无可执行映射"):
        service.decide_change_set(
            "project-1", "document-1", change_set["id"], "approve", "admin"
        )
    rejected = service.decide_change_set(
        "project-1", "document-1", change_set["id"], "reject", "admin"
    )
    assert rejected["status"] == "rejected"


def test_jarvis_worker_creates_draft_then_waits_for_explicit_start_approval(monkeypatch, tmp_path):
    compiled = {
        "compiled": {
            "training_plan_request": {
                "id": "plan-1",
                "name": "补证计划",
                "definition": {"schema": "one_sim.training_plan"},
            }
        }
    }
    service = _service(lambda _payload: compiled)
    service.create_claim("project-1", "document-1", {
        "claim_text": "需要自动补证。",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "execution_policy": {"estimated_cost": 0, "preauthorized_cost_limit": 0},
    }, "admin")

    async def create_plan(payload):
        return {"id": payload["id"], "revision": 1, "status": "draft"}

    monkeypatch.setattr(mission_planning_adapter, "create_training_plan", create_plan)
    claimed = service.claim_next_run("worker-1")
    asyncio.run(service.process_run(claimed["id"], "worker-1"))
    compiled_run = service.get_run("project-1", "document-1", dispatched["id"])
    assert compiled_run["status"] == "queued"
    assert compiled_run["recovery_cursor"]["next_step"] == "queue_experiment_plan"
    claimed = service.claim_next_run("worker-1-plan")
    asyncio.run(service.process_run(claimed["id"], "worker-1-plan"))
    waiting = service.get_run("project-1", "document-1", dispatched["id"])

    assert waiting["status"] == "awaiting_approval"
    assert service.workspace_summary("project-1", "document-1")["gaps"][0]["status"] == "awaiting_approval"
    assert waiting["recovery_cursor"]["next_step"] == "publish_and_start"
    assert waiting["result_payload"]["training_plan_id"] == "plan-1"

    calls = []

    async def publish(plan_id, **payload):
        calls.append(("publish", plan_id, payload["expected_revision"]))
        return {"revision": 1}

    async def synchronize(plan_id, **payload):
        calls.append(("sync", plan_id, payload["idempotency_key"]))
        return {"tasks": 1, "revision": 1}

    async def start(plan_id, **payload):
        calls.append(("start", plan_id, payload["idempotency_key"]))
        return {"started": [{"train_id": "run-1"}], "skipped": []}

    monkeypatch.setattr(mission_planning_adapter, "publish_training_plan", publish)
    monkeypatch.setattr(mission_planning_adapter, "synchronize_training_plan", synchronize)
    monkeypatch.setattr(mission_planning_adapter, "start_training_plan", start)
    service.decide_run("project-1", "document-1", dispatched["id"], "approve", "admin")
    assert service.workspace_summary("project-1", "document-1")["gaps"][0]["status"] == "queued"
    claimed = service.claim_next_run("worker-2")
    asyncio.run(service.process_run(claimed["id"], "worker-2"))
    running = service.get_run("project-1", "document-1", dispatched["id"])

    assert running["status"] == "waiting_evidence"
    assert service.workspace_summary("project-1", "document-1")["gaps"][0]["status"] == "running"
    assert running["recovery_cursor"]["next_step"] == "wait_for_evidence_bundle"
    assert [row[0] for row in calls] == ["publish", "sync", "start"]

    bundle = tmp_path / "bundle-1.json"
    bundle.write_bytes(b"immutable-bundle")
    completed = service.ingest_evidence_bundle("project-1", "document-1", dispatched["id"], {
        "bundle_id": "bundle-1",
        "simulation_record_id": "simulation-1",
        "artifact_path": str(bundle),
        "artifact_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "perspective_scope": "project",
        "evidence_level": "G1",
        "paper_evidence_packet": {"packet_id": "packet-1"},
    }, "admin")

    assert completed["status"] == "completed"
    assert completed["evidence"]["evidence_level"] == "G1"
    assert completed["binding"]["sufficient"] is True


def test_evidence_bound_during_start_is_compensated_before_release(monkeypatch, tmp_path):
    compiled = {
        "compiled": {
            "training_plan_request": {
                "id": "plan-cancel",
                "name": "可取消补证计划",
                "definition": {"schema": "one_sim.training_plan"},
            }
        }
    }
    service = _service(lambda _payload: compiled)
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "需要可取消的补证运行。",
        "minimum_evidence_level": "G1",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")

    async def create_plan(payload):
        return {"id": payload["id"], "revision": 1, "status": "draft"}

    monkeypatch.setattr(mission_planning_adapter, "create_training_plan", create_plan)
    claimed = service.claim_next_run("worker-compile")
    asyncio.run(service.process_run(claimed["id"], "worker-compile"))
    claimed = service.claim_next_run("worker-plan")
    asyncio.run(service.process_run(claimed["id"], "worker-plan"))
    service.decide_run("project-1", "document-1", dispatched["id"], "approve", "admin")
    claimed = service.claim_next_run("worker-start")

    calls = []
    source = tmp_path / "manual-evidence.json"
    source.write_bytes(b"manual-evidence")

    async def publish(_plan_id, **_payload):
        calls.append("publish")
        return {"revision": 1}

    async def synchronize(_plan_id, **_payload):
        calls.append("sync")
        return {"revision": 1}

    async def start(_plan_id, **_payload):
        calls.append("start")
        evidence = service.register_evidence("project-1", "document-1", {
            "source_system": "one-sim",
            "source_record_id": "manual-evidence",
            "artifact_path": str(source),
            "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "evidence_level": "G1",
            "allowed_claim_scope": f"claim:{claim['id']}",
        }, "admin")
        service.bind_evidence("project-1", "document-1", {
            "claim_id": claim["id"],
            "evidence_ref_id": evidence["id"],
        }, "admin")
        return {
            "started": [
                {"train_id": "remote-run-cancel-1"},
                {"train_id": "remote-run-cancel-2"},
            ],
            "skipped": [],
        }

    async def cancel(remote_run_id):
        calls.append(f"cancel:{remote_run_id}")
        return {"train_id": remote_run_id, "status": "stopping"}

    async def get_run(remote_run_id):
        calls.append(f"get:{remote_run_id}")
        return {"train_id": remote_run_id, "status": "cancelled"}

    monkeypatch.setattr(mission_planning_adapter, "publish_training_plan", publish)
    monkeypatch.setattr(mission_planning_adapter, "synchronize_training_plan", synchronize)
    monkeypatch.setattr(mission_planning_adapter, "start_training_plan", start)
    monkeypatch.setattr(mission_planning_adapter, "cancel_training_run", cancel)
    monkeypatch.setattr(mission_planning_adapter, "get_training_run", get_run)

    asyncio.run(service.process_run(claimed["id"], "worker-start"))

    run = service.get_run("project-1", "document-1", dispatched["id"])
    assert calls == [
        "publish",
        "sync",
        "start",
        "cancel:remote-run-cancel-1",
        "get:remote-run-cancel-1",
        "cancel:remote-run-cancel-2",
        "get:remote-run-cancel-2",
    ]
    assert run["status"] == "cancelled"
    assert run["result_payload"]["compensation"]["remote_run_ids"] == [
        "remote-run-cancel-1",
        "remote-run-cancel-2",
    ]
    assert run["result_payload"]["compensation"]["confirmed"] is True
    assert service.workspace_summary("project-1", "document-1")["gaps"] == []


def test_delayed_evidence_does_not_overwrite_compensation_state(tmp_path):
    service = _service()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "迟到证据必须保留停止中的运行状态。",
        "minimum_evidence_level": "G1",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")
    with service.session_factory() as session:
        run = session.get(WritingJarvisRun, dispatched["id"])
        run.status = "compensating"
        run.result_payload = {
            "start_result": {"started": [{"train_id": "remote-race-run"}], "skipped": []}
        }
        run.recovery_cursor = {
            "next_step": "compensate_remote_runs",
            "remote_run_ids": ["remote-race-run"],
        }
        session.commit()
    source = tmp_path / "delayed-evidence.json"
    source.write_bytes(b"delayed-evidence")
    ingested = service.ingest_evidence_bundle("project-1", "document-1", dispatched["id"], {
        "bundle_id": "delayed-evidence",
        "artifact_path": str(source),
        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evidence_level": "G1",
        "allowed_claim_scope": f"claim:{claim['id']}",
    }, "admin")

    assert ingested["status"] == "compensating"
    assert ingested["recovery_cursor"] == {
        "next_step": "compensate_remote_runs",
        "remote_run_ids": ["remote-race-run"],
    }
    assert ingested["result_payload"]["evidence_ref_id"] == ingested["evidence"]["id"]


@pytest.mark.parametrize("remote_status", ["cancelled", "done", "error"])
def test_expired_compensation_is_reclaimed_after_restart(monkeypatch, remote_status):
    service = _service()
    service.create_claim("project-1", "document-1", {
        "claim_text": "补偿步骤必须能够重启恢复。",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")
    with service.session_factory() as session:
        run = session.get(WritingJarvisRun, dispatched["id"])
        run.status = "compensating"
        run.recovery_cursor = {
            "next_step": "compensate_remote_runs",
            "remote_run_ids": ["remote-recovered-run"],
        }
        run.lease_owner = ""
        run.lease_expires_at = None
        session.commit()

    async def cancel(remote_run_id):
        return {"train_id": remote_run_id, "status": "stopping"}

    async def get_run(remote_run_id):
        return {"train_id": remote_run_id, "status": remote_status}

    monkeypatch.setattr(mission_planning_adapter, "cancel_training_run", cancel)
    monkeypatch.setattr(mission_planning_adapter, "get_training_run", get_run)
    claimed = service.claim_next_run("worker-after-restart")
    assert claimed["id"] == dispatched["id"]
    asyncio.run(service.process_run(claimed["id"], "worker-after-restart"))

    recovered = service.get_run("project-1", "document-1", dispatched["id"])
    assert recovered["status"] == "cancelled"
    assert recovered["result_payload"]["compensation"]["confirmed"] is True


def test_remote_start_reconciles_before_cancel_after_pre_persist_failure(monkeypatch, tmp_path):
    compiled = {
        "compiled": {
            "training_plan_request": {
                "id": "plan-replay",
                "name": "可恢复启动计划",
                "definition": {"schema": "one_sim.training_plan"},
            }
        }
    }
    service = _service(lambda _payload: compiled)
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "远端启动必须可幂等恢复。",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")

    async def create_plan(payload):
        return {"id": payload["id"], "revision": 1, "status": "draft"}

    async def publish(_plan_id, **_payload):
        return {"revision": 1}

    async def synchronize(_plan_id, **_payload):
        return {"revision": 1}

    start_keys = []

    async def start(_plan_id, **payload):
        start_keys.append(payload["idempotency_key"])
        return {"started": [{"train_id": "remote-replayed-run"}], "skipped": []}

    async def cancel(remote_run_id):
        return {"train_id": remote_run_id, "status": "stopping"}

    async def get_run(remote_run_id):
        return {"train_id": remote_run_id, "status": "cancelled"}

    monkeypatch.setattr(mission_planning_adapter, "create_training_plan", create_plan)
    monkeypatch.setattr(mission_planning_adapter, "publish_training_plan", publish)
    monkeypatch.setattr(mission_planning_adapter, "synchronize_training_plan", synchronize)
    monkeypatch.setattr(mission_planning_adapter, "start_training_plan", start)
    monkeypatch.setattr(mission_planning_adapter, "cancel_training_run", cancel)
    monkeypatch.setattr(mission_planning_adapter, "get_training_run", get_run)

    claimed = service.claim_next_run("worker-compile")
    asyncio.run(service.process_run(claimed["id"], "worker-compile"))
    claimed = service.claim_next_run("worker-plan")
    asyncio.run(service.process_run(claimed["id"], "worker-plan"))
    service.decide_run("project-1", "document-1", dispatched["id"], "approve", "admin")

    original_remote_run_ids = service._remote_run_ids
    extraction_attempts = 0

    def fail_once(start_result):
        nonlocal extraction_attempts
        extraction_attempts += 1
        if extraction_attempts == 1:
            raise RuntimeError("simulated crash before local run-id persistence")
        return original_remote_run_ids(start_result)

    monkeypatch.setattr(service, "_remote_run_ids", fail_once)
    claimed = service.claim_next_run("worker-start")
    asyncio.run(service.process_run(claimed["id"], "worker-start"))
    uncertain = service.get_run("project-1", "document-1", dispatched["id"])
    assert uncertain["status"] == "queued"
    assert uncertain["recovery_cursor"]["next_step"] == "starting_remote"

    source = tmp_path / "interleaved-evidence.json"
    source.write_bytes(b"interleaved-evidence")
    evidence = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "interleaved-evidence",
        "artifact_path": str(source),
        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evidence_level": "G1",
        "allowed_claim_scope": f"claim:{claim['id']}",
    }, "admin")
    service.bind_evidence("project-1", "document-1", {
        "claim_id": claim["id"],
        "evidence_ref_id": evidence["id"],
    }, "admin")
    cancellation_pending = service.get_run("project-1", "document-1", dispatched["id"])
    assert cancellation_pending["status"] == "cancellation_requested"
    assert cancellation_pending["recovery_cursor"]["next_step"] == "starting_remote"
    with pytest.raises(DocumentWorkspaceError, match="Jarvis"):
        service.require_formal_release("project-1", "document-1", "docx")

    claimed = service.claim_next_run("worker-recover")
    asyncio.run(service.process_run(claimed["id"], "worker-recover"))
    recovered = service.get_run("project-1", "document-1", dispatched["id"])
    assert recovered["status"] == "cancelled"
    assert recovered["result_payload"]["start_result"]["started"][0]["train_id"] == "remote-replayed-run"
    assert recovered["result_payload"]["compensation"]["confirmed"] is True
    assert start_keys == [
        f"jarvis:{dispatched['id']}:start",
        f"jarvis:{dispatched['id']}:start",
    ]


def test_all_skipped_start_requires_no_compensation_calls(tmp_path):
    service = _service()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "全量跳过时不应进入补偿循环。",
        "minimum_evidence_level": "G1",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {}, "admin")
    with service.session_factory() as session:
        run = session.get(WritingJarvisRun, dispatched["id"])
        run.status = "waiting_evidence"
        run.result_payload = {
            "start_result": {
                "started": [],
                "skipped": [{"train_id": "already-finished", "reason": "terminal"}],
            }
        }
        session.commit()

    source = tmp_path / "skipped-evidence.json"
    source.write_bytes(b"skipped-evidence")
    evidence = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "skipped-evidence",
        "artifact_path": str(source),
        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evidence_level": "G1",
        "allowed_claim_scope": f"claim:{claim['id']}",
    }, "admin")
    service.bind_evidence("project-1", "document-1", {
        "claim_id": claim["id"],
        "evidence_ref_id": evidence["id"],
    }, "admin")

    run = service.get_run("project-1", "document-1", dispatched["id"])
    assert run["status"] == "cancelled"
    assert run["result_payload"]["compensation"]["remote_run_ids"] == []
    assert run["result_payload"]["compensation"]["confirmed"] is True
    assert run["result_payload"]["compensation"]["reason"] == "no_remote_runs_created"
