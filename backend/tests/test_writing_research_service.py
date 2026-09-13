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


def _service(
    compiler=None,
    *,
    context_retriever=None,
    external_retriever=None,
    content_json=None,
):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with sessions() as session:
        structured_content = content_json or {"type": "doc", "content": []}
        session.add(WritingDocumentState(
            project_id="project-1",
            document_id="document-1",
            document_revision=2,
            content_json=structured_content,
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
            content_json=structured_content,
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
        context_retriever=context_retriever,
        external_retriever=external_retriever,
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


def test_literature_claim_contract_preserves_source_and_scope_axes():
    service = _service()
    claim = service.create_claim("project-1", "document-1", {
        "claim_text": "2025 年以来，动态授权研究开始同时考虑认知负荷与通信质量。",
        "claim_key": "section-1.3.1:dynamic-authority-trend",
        "claim_type": "argument",
        "rhetorical_role": "trend",
        "evidence_policy": {
            "minimum_independent_sources": 3,
            "required_source_quality": ["peer_reviewed", "official"],
        },
        "temporal_scope": "2025-2026",
        "geographic_scope": "global",
        "document_revision": 2,
        "section_id": "1.3.1",
        "block_id": "block-dynamic-authority",
    }, "admin")

    assert claim["claim_key"] == "section-1.3.1:dynamic-authority-trend"
    assert len(claim["claim_fingerprint"]) == 64
    assert claim["rhetorical_role"] == "trend"
    assert claim["evidence_policy"]["minimum_independent_sources"] == 3
    assert claim["temporal_scope"] == "2025-2026"
    assert claim["geographic_scope"] == "global"


def test_gap_classifier_uses_required_evidence_kinds_without_mixing_axes():
    service = _service()
    service.create_claim("project-1", "document-1", {
        "claim_text": "该综合结论需要双来源约束。",
        "evidence_policy": {
            "required_evidence_kinds": ["literature", "simulation"],
        },
        "research_matrix": {"question": "联合补证"},
    }, "admin")

    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    assert gap["gap_type"] == "mixed"


def test_retrieval_ref_requires_screening_and_snapshot_before_evidence_upgrade(tmp_path):
    service = _service()
    payload = {
        "base_revision": 2,
        "idempotency_key": "retrieval-local-1",
        "provider": "local_knowledge",
        "provider_record_id": "node-2025-dynamic-authority",
        "query_id": "matrix-1.3.1-q1",
        "query_text": "dynamic authority cognitive workload communication quality",
        "rank": 1,
        "retrieval_score": 0.92,
        "title": "Dynamic authority allocation in human-machine command",
        "authors": ["Researcher A", "Researcher B"],
        "year": 2025,
        "venue": "Command and Control Review",
        "doi": "10.1000/example.2025.1",
        "access_status": "metadata_only",
        "abstract_snapshot": "A metadata-only candidate record.",
        "metadata_snapshot": {"source": "team-knowledge", "version": 1},
    }
    retrieval = service.register_retrieval("project-1", "document-1", payload, "admin")
    replay = service.register_retrieval("project-1", "document-1", payload, "admin")

    assert replay["id"] == retrieval["id"]
    assert replay["idempotent_replay"] is True
    assert retrieval["screening_status"] == "pending"
    assert len(retrieval["metadata_sha256"]) == 64
    assert service.workspace_summary("project-1", "document-1")["retrieval_refs"][0]["id"] == retrieval["id"]

    snapshot = tmp_path / "official-metadata.json"
    snapshot.write_text('{"verified": true}', encoding="utf-8")
    evidence_payload = {
        "expected_revision": 2,
        "artifact_path": str(snapshot),
        "artifact_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "source_quality": "peer_reviewed",
        "allowed_claim_scope": "section:1.3.1",
    }
    with pytest.raises(DocumentWorkspaceError, match="已纳入"):
        service.promote_retrieval(
            "project-1", "document-1", retrieval["id"], evidence_payload, "admin"
        )

    screened = service.decide_retrieval("project-1", "document-1", retrieval["id"], {
        "expected_revision": 2,
        "decision": "include",
        "reason": "来源身份已核验",
        "idempotency_key": "screen-local-1",
    }, "admin")
    screening_replay = service.decide_retrieval("project-1", "document-1", retrieval["id"], {
        "expected_revision": 2,
        "decision": "include",
        "reason": "来源身份已核验",
        "idempotency_key": "screen-local-1",
    }, "admin")
    assert screened["screening_status"] == "include"
    assert screening_replay["idempotent_replay"] is True

    evidence = service.promote_retrieval(
        "project-1", "document-1", retrieval["id"], evidence_payload, "admin"
    )
    assert evidence["evidence_kind"] == "literature"
    assert evidence["source_quality"] == "peer_reviewed"
    assert evidence["directness"] == "metadata_only"
    assert evidence["retrieval_ref_id"] == retrieval["id"]
    assert evidence["artifact_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_retrieval_ref_rejects_stale_revision_and_invalid_metadata_hash():
    service = _service()
    payload = {
        "base_revision": 1,
        "idempotency_key": "retrieval-stale",
        "provider": "local_knowledge",
        "provider_record_id": "node-stale",
        "title": "Stale candidate",
    }
    with pytest.raises(DocumentWorkspaceError, match="当前正文修订"):
        service.register_retrieval("project-1", "document-1", payload, "admin")

    payload["base_revision"] = 2
    payload["metadata_sha256"] = "0" * 64
    with pytest.raises(DocumentWorkspaceError, match="元数据哈希"):
        service.register_retrieval("project-1", "document-1", payload, "admin")


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


def test_local_literature_run_builds_audit_without_body_changes(tmp_path):
    local_source = tmp_path / "authority-allocation.md"
    local_source.write_text(
        "动态授权研究讨论任务风险、认知负荷、通信质量与算法置信度之间的关系。"
        "该资料用于说明本地知识检索、来源定位和证据快照流程，不代表已经通过同行评审。"
        "研究结论仍需回到原始论文或官方资料核验。",
        encoding="utf-8",
    )
    command_source = tmp_path / "commands" / "autoresearch.md"
    command_source.parent.mkdir()
    command_source.write_text("Read the `autoresearch` skill. Then run the research loop.", encoding="utf-8")
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-131"},
                "content": [{"type": "text", "text": "1.3.1 战术指挥控制、任务式指挥与人机权责配置研究现状"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "paragraph-1"},
                "content": [{
                    "type": "text",
                    "text": "现有研究借助任务式指挥解释意图传递与授权边界[1]。2025年以来研究开始关注认知负荷和通信质量[2]。仍缺乏统一的人机分歧处置机制。",
                }],
            },
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-132"},
                "content": [{"type": "text", "text": "1.3.2 指挥意图形式化研究现状"}],
            },
            {
                "type": "heading",
                "attrs": {"level": 1, "blockId": "references"},
                "content": [{"type": "text", "text": "参考文献"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "reference-1"},
                "content": [{"type": "text", "text": "[1] 张三. 任务式指挥研究综述[J]. 指挥与控制学报, 2024, 10(1): 1-10."}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "reference-2"},
                "content": [{"type": "text", "text": "[2] Smith J. Dynamic Authority Allocation[J]. Systems, 2025, 13(2): 20-30. DOI: 10.1000/example.2."}],
            },
        ],
    }

    def retrieve_local(**_payload):
        return {
            "id": "context-pack-1",
            "retrieval_health": {"knowledge": {"status": "ready", "results": 2}},
            "items": [
                {
                    "item_type": "knowledge",
                    "source_id": "source-obsidian",
                    "source_ref": "knowledge:authority-allocation.md",
                    "title": "动态授权研究笔记",
                    "content": local_source.read_text(encoding="utf-8"),
                    "score": 0.91,
                    "confidence": 0.8,
                    "rank_index": 1,
                    "metadata": {"path": str(local_source), "node_type": "文档"},
                },
                {
                    "item_type": "knowledge",
                    "source_id": "source-obsidian",
                    "source_ref": "knowledge:commands/autoresearch.md",
                    "title": "autoresearch command",
                    "content": command_source.read_text(encoding="utf-8"),
                    "score": 0.8,
                    "confidence": 0.9,
                    "rank_index": 2,
                    "metadata": {"path": str(command_source), "node_type": "文档"},
                },
            ],
        }

    service = _service(context_retriever=retrieve_local, content_json=content)
    run = service.start_literature_run("project-1", "document-1", {
        "base_revision": 2,
        "idempotency_key": "literature-audit-131-v1",
        "scope_section_ids": ["1.3.1"],
        "evaluator_version": "literature-baseline-v1",
    }, "admin")

    assert run["status"] == "completed"
    assert run["result_payload"]["audit_only"] is True
    assert run["result_payload"]["body_changes"] == 0
    assert len(run["steps"]) == 11
    assert {step["status"] for step in run["steps"]} == {"completed"}
    assert run["result_payload"]["claim_count"] == 3
    assert run["result_payload"]["retrieval_count"] == 4
    assert run["result_payload"]["evidence_count"] == 3
    assert len(run["result_payload"]["retrieval_ref_ids"]) == 4
    assert len(run["result_payload"]["evidence_ref_ids"]) == 3

    summary = service.workspace_summary("project-1", "document-1")
    assert len(summary["claims"]) == 3
    assert {claim["evidence_status"] for claim in summary["claims"]} == {"insufficient", "missing"}
    assert len(summary["gaps"]) == 3
    assert len(summary["retrieval_refs"]) == 4
    excluded = [item for item in summary["retrieval_refs"] if item["screening_status"] == "exclude"]
    assert len(excluded) == 1
    assert "命令" in excluded[0]["screening_reason"]
    bibliography_evidence = [
        item for item in summary["evidence_refs"] if item["source_system"] == "bibliography"
    ]
    assert len(bibliography_evidence) == 2
    assert {item["directness"] for item in bibliography_evidence} == {"metadata_only"}
    assert all(Path(item["artifact_path"]).is_file() for item in summary["evidence_refs"])

    iterations = service.list_research_iterations(
        "project-1", "document-1", run_id=run["id"]
    )
    assert len(iterations) == 1
    assert iterations[0]["evaluation"]["decision"] == "baseline"
    assert iterations[0]["evaluation"]["hard_gates"]["body_write_operations"] == 0
    with service.session_factory() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        assert state.document_revision == 2
        assert state.content_sha256 == "a" * 64
        assert state.source_markdown_sha256 == "b" * 64

    replay = service.start_literature_run("project-1", "document-1", {
        "base_revision": 2,
        "idempotency_key": "literature-audit-131-v1",
        "scope_section_ids": ["1.3.1"],
    }, "admin")
    assert replay["id"] == run["id"]
    assert replay["idempotent_replay"] is True


def test_literature_run_deduplicates_external_metadata_and_preserves_audit_boundary():
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-131"},
                "content": [{"type": "text", "text": "1.3.1 战术指挥控制研究现状"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "paragraph-1"},
                "content": [{"type": "text", "text": "动态授权研究关注认知负荷与通信质量[1]。"}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-132"},
                "content": [{"type": "text", "text": "1.3.2 其他研究"}],
            },
            {
                "type": "heading",
                "attrs": {"level": 1, "blockId": "references"},
                "content": [{"type": "text", "text": "参考文献"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "reference-1"},
                "content": [{
                    "type": "text",
                    "text": "[1] Smith J. Dynamic Authority Allocation[J]. Systems, 2025. DOI: 10.1000/example.1.",
                }],
            },
        ],
    }

    def retrieve_local(**_payload):
        return {"retrieval_health": {"knowledge": {"status": "ready"}}, "items": []}

    def retrieve_external(**_payload):
        base = {
            "title": "Dynamic Authority Allocation",
            "authors": ["Researcher A"],
            "year": 2025,
            "venue": "Systems",
            "doi": "10.1000/example.1",
            "url": "https://doi.org/10.1000/example.1",
            "abstract_snapshot": "Authority changes with workload and communications.",
            "access_status": "abstract",
            "retrieval_score": 0.95,
            "rank": 1,
            "canonical_key": "doi:10.1000/example.1",
        }
        return {
            "candidates": [
                {
                    **base,
                    "provider": "semantic_scholar",
                    "provider_record_id": "paper-1",
                    "metadata_snapshot": {"request_fingerprint": "s2-request"},
                },
                {
                    **base,
                    "provider": "crossref",
                    "provider_record_id": "10.1000/example.1",
                    "metadata_snapshot": {"request_fingerprint": "crossref-request"},
                },
                {
                    **base,
                    "provider": "crossref",
                    "provider_record_id": "10.1000/unrelated.1",
                    "title": "Corporate Liability Allocation in Commercial Law",
                    "doi": "10.1000/unrelated.1",
                    "url": "https://doi.org/10.1000/unrelated.1",
                    "abstract_snapshot": "A study of creditors, debtors, and corporate liability.",
                    "canonical_key": "doi:10.1000/unrelated.1",
                    "rank": 2,
                    "metadata_snapshot": {"request_fingerprint": "crossref-request-unrelated"},
                },
            ],
            "health": {
                "semantic_scholar": {"status": "ready", "results": 1},
                "crossref": {"status": "ready", "results": 1},
            },
            "requests_used": 2,
        }

    service = _service(
        context_retriever=retrieve_local,
        external_retriever=retrieve_external,
        content_json=content,
    )
    run = service.start_literature_run("project-1", "document-1", {
        "base_revision": 2,
        "idempotency_key": "literature-external-131-v1",
        "scope_section_ids": ["1.3.1"],
        "source_whitelist": [
            "local_knowledge", "bibliography", "semantic_scholar", "crossref"
        ],
        "external_request_budget": 2,
    }, "admin")

    assert run["status"] == "completed"
    assert run["result_payload"]["body_changes"] == 0
    assert len(run["steps"]) == 11
    retrievals = service.list_retrievals("project-1", "document-1")
    assert len(retrievals) == 4
    assert sum(item["screening_status"] == "duplicate" for item in retrievals) == 1
    assert sum(item["screening_status"] == "uncertain" for item in retrievals) == 1
    assert sum(item["provider"] in {"semantic_scholar", "crossref"} for item in retrievals) == 3
    unrelated = next(item for item in retrievals if item["doi"] == "10.1000/unrelated.1")
    assert "主题短语" in unrelated["screening_reason"]
    evidence = service.workspace_summary("project-1", "document-1")["evidence_refs"]
    assert len(evidence) == 2
    external_evidence = [item for item in evidence if item["source_system"] != "bibliography"]
    assert len(external_evidence) == 1
    assert external_evidence[0]["directness"] == "indirect"
    assert external_evidence[0]["support_role"] == "contextualizes"


def test_literature_candidate_keeps_safe_qualification_and_discards_scope_violation():
    old_text = "2025年以来，动态授权研究关注认知负荷与通信质量[1]。"
    new_text = "现有研究中，动态授权研究关注认知负荷与通信质量[1]。"
    content = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-131"},
                "content": [{"type": "text", "text": "1.3.1 战术指挥控制研究现状"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "paragraph-1"},
                "content": [{"type": "text", "text": old_text}],
            },
            {
                "type": "heading",
                "attrs": {"level": 3, "blockId": "heading-132"},
                "content": [{"type": "text", "text": "1.3.2 其他研究"}],
            },
            {
                "type": "heading",
                "attrs": {"level": 1, "blockId": "references"},
                "content": [{"type": "text", "text": "参考文献"}],
            },
            {
                "type": "paragraph",
                "attrs": {"blockId": "reference-1"},
                "content": [{
                    "type": "text",
                    "text": "[1] Smith J. Dynamic Authority Allocation[J]. Systems, 2025.",
                }],
            },
        ],
    }
    service = _service(
        context_retriever=lambda **_payload: {"retrieval_health": {}, "items": []},
        content_json=content,
    )
    run = service.start_literature_run("project-1", "document-1", {
        "base_revision": 2,
        "idempotency_key": "candidate-baseline-v1",
        "scope_section_ids": ["1.3.1"],
    }, "admin")
    payload = {
        "base_revision": 2,
        "idempotency_key": "candidate-safe-v1",
        "operations": [{
            "op": "replace_text",
            "block_id": "paragraph-1",
            "old_text": old_text,
            "new_text": new_text,
            "reason": "移除缺少直接证据的时间范围限定",
        }],
        "summary": "限定未经直接证据支持的时间表述",
    }
    candidate = service.evaluate_literature_candidate(
        "project-1", "document-1", run["id"], payload, "admin"
    )
    replay = service.evaluate_literature_candidate(
        "project-1", "document-1", run["id"], payload, "admin"
    )

    assert candidate["status"] == "review_required"
    assert candidate["evaluation"]["decision"] == "kept"
    assert candidate["evaluation"]["baseline_delta"] >= 2
    assert candidate["evaluation"]["hard_gates"]["body_write_operations"] == 0
    assert candidate["change_set"]["risk_level"] == "high"
    assert candidate["change_set"]["approval_policy"] == "research_candidate"
    assert Path(candidate["candidate_artifact_path"]).is_file()
    assert replay["id"] == candidate["id"]
    assert replay["idempotent_replay"] is True

    discarded = service.evaluate_literature_candidate(
        "project-1", "document-1", run["id"], {
            "base_revision": 2,
            "idempotency_key": "candidate-outside-scope-v1",
            "operations": [{
                "op": "replace_text",
                "block_id": "reference-1",
                "old_text": "Smith J.",
                "new_text": "Unknown Author [99].",
            }],
        }, "admin"
    )
    assert discarded["status"] == "discarded"
    assert discarded["evaluation"]["decision"] == "discarded"
    assert discarded["evaluation"]["hard_gates"]["scope_confined_to_section"] is False
    assert discarded["change_set"] is None

    with service.session_factory() as session:
        state = session.query(WritingDocumentState).filter_by(
            project_id="project-1", document_id="document-1"
        ).one()
        assert state.document_revision == 2
        assert state.content_json == content


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


def test_literature_gap_dispatch_never_compiles_or_creates_one_sim_plan(monkeypatch):
    compile_calls = []
    literature_calls = []
    service = _service(lambda payload: compile_calls.append(payload) or {})
    service.start_literature_run = lambda *args: (
        literature_calls.append(args) or {"id": "literature-child-1", "status": "completed"}
    )
    service.create_claim("project-1", "document-1", {
        "claim_text": "该研究现状表述需要补充可核验文献来源。",
        "section_id": "1.3.1",
        "gap_type": "literature",
        "research_matrix": {
            "schema": "writing.literature_research_matrix.v1",
            "section_id": "1.3.1",
            "directions": [{"source_types": ["local_knowledge", "bibliography"]}],
        },
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]

    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "literature-only-gap",
    }, "admin")

    assert gap["gap_type"] == "literature"
    assert dispatched["run_type"] == "literature_gap_dispatch"
    assert dispatched["recovery_cursor"]["next_step"] == "run_literature_research"
    assert [step["step_key"] for step in dispatched["steps"]] == ["run_literature_research"]

    claimed = service.claim_next_run("worker-literature")
    asyncio.run(service.process_run(claimed["id"], "worker-literature"))
    completed = service.get_run("project-1", "document-1", dispatched["id"])

    assert completed["status"] == "completed"
    assert completed["result_payload"]["literature_run_id"] == "literature-child-1"
    assert "training_plan_id" not in completed["result_payload"]
    assert len(literature_calls) == 1
    assert compile_calls == []


def test_mixed_gap_runs_literature_before_one_sim_compile():
    compile_calls = []
    service = _service(lambda payload: compile_calls.append(payload) or {
        "compiled": {"training_plan_request": {"id": "mixed-plan"}},
    })
    service.start_literature_run = lambda *args: {"id": "literature-child-mixed", "status": "completed"}
    service.create_claim("project-1", "document-1", {
        "claim_text": "文献结论与仿真实验结果需要联合补证。",
        "section_id": "1.3.7",
        "gap_type": "mixed",
        "research_matrix": {
            "literature_matrix": {
                "schema": "writing.literature_research_matrix.v1",
                "section_id": "1.3.7",
            },
            "experiment_matrix": {
                "schema": "one_sim.research_experiment_matrix",
                "question": "验证任务规划效果",
            },
        },
    }, "admin")
    gap = service.workspace_summary("project-1", "document-1")["gaps"][0]
    dispatched = service.dispatch_gap("project-1", "document-1", gap["id"], {
        "idempotency_key": "mixed-gap",
    }, "admin")

    first = service.claim_next_run("worker-mixed-literature")
    asyncio.run(service.process_run(first["id"], "worker-mixed-literature"))
    after_literature = service.get_run("project-1", "document-1", dispatched["id"])
    assert after_literature["recovery_cursor"]["next_step"] == "compile_research_matrix"
    assert compile_calls == []

    second = service.claim_next_run("worker-mixed-experiment")
    asyncio.run(service.process_run(second["id"], "worker-mixed-experiment"))
    after_compile = service.get_run("project-1", "document-1", dispatched["id"])
    assert after_compile["recovery_cursor"]["next_step"] == "queue_experiment_plan"
    assert len(compile_calls) == 1
    assert compile_calls[0]["matrix"]["schema"] == "one_sim.research_experiment_matrix"


def test_evidence_kind_and_strength_axes_are_not_interchangeable(tmp_path):
    service = _service()
    mixed_claim = service.create_claim("project-1", "document-1", {
        "claim_text": "研究脉络和仿真效果都需要证据。",
        "minimum_evidence_level": "G1",
        "gap_type": "mixed",
        "section_id": "1.3.7",
        "research_matrix": {"schema": "one_sim.research_experiment_matrix"},
    }, "admin")
    literature_file = tmp_path / "literature.json"
    literature_file.write_bytes(b"peer-reviewed-source")
    literature = service.register_evidence("project-1", "document-1", {
        "source_system": "journal",
        "source_record_id": "paper-1",
        "artifact_path": str(literature_file),
        "artifact_sha256": hashlib.sha256(literature_file.read_bytes()).hexdigest(),
        "evidence_kind": "literature",
        "source_quality": "peer_reviewed",
        "evidence_level": "A",
        "allowed_claim_scope": f"claim:{mixed_claim['id']}",
    }, "admin")
    literature_binding = service.bind_evidence("project-1", "document-1", {
        "claim_id": mixed_claim["id"],
        "evidence_ref_id": literature["id"],
    }, "admin")
    assert literature_binding["satisfied_evidence_categories"] == ["literature"]
    assert literature_binding["strongest_evidence_level"] == "diagnostic"
    assert literature_binding["sufficient"] is False

    simulation_file = tmp_path / "simulation.json"
    simulation_file.write_bytes(b"one-sim-bundle")
    simulation = service.register_evidence("project-1", "document-1", {
        "source_system": "one-sim",
        "source_record_id": "bundle-1",
        "artifact_path": str(simulation_file),
        "artifact_sha256": hashlib.sha256(simulation_file.read_bytes()).hexdigest(),
        "evidence_kind": "simulation",
        "source_quality": "internal",
        "evidence_level": "G1",
        "allowed_claim_scope": f"claim:{mixed_claim['id']}",
    }, "admin")
    simulation_binding = service.bind_evidence("project-1", "document-1", {
        "claim_id": mixed_claim["id"],
        "evidence_ref_id": simulation["id"],
    }, "admin")
    assert simulation_binding["required_evidence_categories"] == ["experiment", "literature"]
    assert simulation_binding["satisfied_evidence_categories"] == ["experiment", "literature"]
    assert simulation_binding["strongest_evidence_level"] == "G1"
    assert simulation_binding["sufficient"] is True


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
