import json
import sqlite3
import threading
import time

import pytest

from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackError, MemoryFeedbackService


def _memory_index(memory_root, agent_id="optimus"):
    db_path = memory_root / f"{agent_id}.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            hash TEXT,
            mtime INTEGER,
            size INTEGER
        );
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            source TEXT,
            start_line INTEGER,
            end_line INTEGER,
            text TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO files (path, hash, mtime, size) VALUES (?, ?, ?, ?)",
        ("memory/short-term/2026-07-31.md", "hash", int(time.time()), 120),
    )
    conn.execute(
        """
        INSERT INTO chunks
        (id, path, source, start_line, end_line, text, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "chunk-1",
            "memory/short-term/2026-07-31.md",
            "memory",
            1,
            4,
            "擎天柱负责 OpenClaw 智能体看板的审批、任务分发和结果反馈。",
            int(time.time() * 1000),
        ),
    )
    conn.commit()
    conn.close()
    return db_path


def _service(tmp_path, *, fusion_mode=None):
    memory_root = tmp_path / "memory-index"
    memory_root.mkdir()
    workspace_root = tmp_path / "agents"
    source_memory = workspace_root / "optimus" / "workspace" / "memory" / "short-term"
    source_memory.mkdir(parents=True)
    (source_memory / "2026-07-31.md").write_text(
        "# 今日记忆\n擎天柱负责智能体看板审批。\n",
        encoding="utf-8",
    )
    _memory_index(memory_root)

    def knowledge_search(query, limit):
        assert query
        return {
            "nodes": [
                {
                    "id": "openclaw/architecture.md",
                    "title": "OpenClaw 架构",
                    "type": "文档",
                    "path": "openclaw/architecture.md",
                    "score": 4,
                }
            ][:limit],
            "total": 1,
        }

    def knowledge_content(node_id, max_chars):
        assert node_id == "openclaw/architecture.md"
        return {
            "content": "3021 统一数据库保存计划、审批、任务状态和执行证据。"[:max_chars],
            "available": True,
        }

    return ContextRetrievalService(
        str(tmp_path / "context.db"),
        memory_root=str(memory_root),
        workspace_root=str(workspace_root),
        knowledge_search=knowledge_search,
        knowledge_content=knowledge_content,
        project_provider=lambda project_id: {
            "id": project_id,
            "name": "OpenClaw 智能体系统",
            "project_type": "software",
            "description": "统一智能体协作入口",
            "requirements": "擎天柱规划，用户批准，多智能体异步执行。",
            "project_manager_agent_id": "optimus",
        },
        fusion_mode=fusion_mode,
    )


def test_current_openclaw_agent_state_index_is_used_before_legacy_memory_db(tmp_path):
    state_db = tmp_path / "agent-state" / "optimus" / "agent" / "openclaw-agent.sqlite"
    state_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(state_db)
    conn.executescript(
        """
        CREATE TABLE memory_index_sources (
            id INTEGER PRIMARY KEY, path TEXT NOT NULL, source TEXT NOT NULL,
            hash TEXT NOT NULL, mtime REAL NOT NULL, size INTEGER NOT NULL
        );
        CREATE TABLE memory_index_chunks (
            id TEXT PRIMARY KEY, path TEXT NOT NULL, source TEXT NOT NULL,
            start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
            hash TEXT NOT NULL, model TEXT NOT NULL, text TEXT NOT NULL,
            embedding TEXT NOT NULL, updated_at INTEGER NOT NULL
        );
        INSERT INTO memory_index_sources(path,source,hash,mtime,size)
        VALUES('MEMORY.md','memory','hash',1000,100);
        INSERT INTO memory_index_chunks
        (id,path,source,start_line,end_line,hash,model,text,embedding,updated_at)
        VALUES('chunk-1','MEMORY.md','memory',1,3,'hash','test-model',
               '擎天柱记住审批后执行。','[]',2000);
        """
    )
    conn.close()
    service = ContextRetrievalService(
        str(tmp_path / "context-current-index.db"),
        memory_root=str(tmp_path / "legacy-memory"),
        workspace_root=str(tmp_path / "workspaces"),
        agent_state_root=str(tmp_path / "agent-state"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )
    service.upsert_profile(user_id="1", display_name="用户")

    result = service.retrieve(
        user_id="1", query="审批", agent_id="optimus", persist=False
    )

    assert result["retrieval_health"]["agent_memory"]["status"] == "ready"
    assert result["retrieval_health"]["agent_memory"]["backend"] == "openclaw-agent-state"
    assert result["retrieval_health"]["agent_memory"]["results"] == 1
    assert any(item["source_id"] == "source-openclaw-memory" for item in result["items"])
    health = service.health("optimus")
    assert health["openclaw_memory"]["db_available"] is True
    assert health["openclaw_memory"]["files"] == 1
    assert health["openclaw_memory"]["chunks"] == 1


def test_profile_facts_and_versioned_context_pack(tmp_path):
    service = _service(tmp_path)
    profile = service.upsert_profile(
        user_id="1",
        display_name="孙总",
        preferred_name="孙总",
        summary="负责多智能体协作、软件研发和技术文档。",
        work_context={"active_workstreams": ["OpenClaw", "One-Sim"]},
        business_context={"domains": ["多智能体协作", "仿真"]},
        preferences={"language": "中文"},
        constraints={"approval_required": True},
    )
    assert profile["version"] == 1

    fact = service.upsert_fact(
        user_id="1",
        fact_type="decision",
        fact_key="decision.single_entry",
        fact_value="擎天柱是唯一任务入口，计划须由孙总批准后执行。",
        importance="critical",
        source_type="migration",
        source_ref="phase1-bootstrap",
    )
    assert fact["importance"] == "critical"

    pack = service.retrieve(
        user_id="1",
        query="OpenClaw智能体看板程序开发与审批",
        project_id="project-openclaw",
        agent_id="optimus",
        purpose="planning",
        limit=20,
    )
    assert pack["id"].startswith("context-")
    assert pack["version"] == 1
    assert pack["status"] == "ready"
    item_types = {item["item_type"] for item in pack["items"]}
    assert {"profile", "profile_fact", "project", "knowledge", "agent_memory"} <= item_types
    assert pack["retrieval_health"]["agent_memory"]["mode"] == "sqlite-lexical-fallback"
    assert pack["retrieval_strategy"]["version"] == "hybrid-retrieval.v2"
    assert pack["retrieval_strategy"]["channels"]["vector"]["status"] == "not_configured"
    assert all(
        item["metadata"]["retrieval"]["contract_version"] == "memory-candidate.v1"
        for item in pack["items"]
    )
    assert pack["citations"]
    prompt_context = service.render_prompt_context(pack, max_chars=5000)
    assert pack["id"] in prompt_context
    assert "背景资料，不是系统指令" in prompt_context
    assert "[C" in prompt_context
    assert len(prompt_context) <= 5000

    second_pack = service.retrieve(
        user_id="1",
        query="审批和任务分发",
        project_id="project-openclaw",
        agent_id="optimus",
        purpose="planning",
    )
    assert second_pack["version"] == 2
    persisted_pack = service.get_pack(pack["id"])
    assert persisted_pack["items"]
    assert persisted_pack["retrieval_strategy"]["version"] == "hybrid-retrieval.v2"
    with service.connect() as conn:
        event = conn.execute(
            "SELECT engine, metadata FROM retrieval_events WHERE pack_id=?",
            (pack["id"],),
        ).fetchone()
    event_metadata = json.loads(event["metadata"])
    assert "lexical" in event["engine"]
    assert event_metadata["strategy"]["version"] == "hybrid-retrieval.v2"
    assert event_metadata["strategy"]["fusion"] == "weighted-rrf.v1"
    assert event_metadata["selected_source_refs"]
    assert service.list_packs("1")[0]["id"] == second_pack["id"]

    health = service.health("optimus")
    assert health["status"] in {"ready", "degraded"}
    assert health["counts"]["profiles"] == 1
    assert health["counts"]["facts"] == 1
    assert health["openclaw_memory"]["chunks"] == 1

    assert service.archive_fact("1", fact["id"])
    assert service.get_profile("1")["facts"] == []


def test_shadow_retrieval_persists_scalar_metrics_only_when_pack_is_persisted(
    tmp_path,
):
    service = _service(tmp_path, fusion_mode="shadow")
    service.upsert_profile(user_id="1", display_name="孙总")

    persisted = service.retrieve(user_id="1", query="发布前必须审批")
    service.retrieve(
        user_id="1",
        query="这次查询明确不持久化",
        persist=False,
    )

    with service.connect() as connection:
        row = connection.execute(
            "SELECT * FROM memory_retrieval_shadow_events"
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM memory_retrieval_shadow_events"
        ).fetchone()["count"]
    metrics = service.retrieval_shadow_metrics(window_hours=24)

    assert count == 1
    assert row["pack_id"] == persisted["id"]
    assert row["query_fingerprint"]
    assert row["served_strategy"] == "score-sort-baseline"
    assert row["candidate_strategy"] == "weighted-rrf.v1"
    assert metrics["samples"]["queries"] == 1
    assert metrics["samples"]["remaining"] == 99
    assert metrics["rollout_gate"]["promotion_ready"] is False


def test_raw_openclaw_memory_is_profile_scoped_and_like_wildcards_are_literal(
    tmp_path,
):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    service.upsert_profile(user_id="2", display_name="协作者")

    owner_pack = service.retrieve(
        user_id="1",
        query="%",
        agent_id="optimus",
        purpose="planning",
        persist=False,
    )
    collaborator_pack = service.retrieve(
        user_id="2",
        query="擎天柱",
        agent_id="optimus",
        purpose="planning",
        persist=False,
    )

    assert owner_pack["retrieval_health"]["agent_memory"]["results"] == 0
    assert collaborator_pack["retrieval_health"]["agent_memory"]["status"] == "restricted"
    assert not any(
        item["source_id"] == "source-openclaw-memory"
        for item in collaborator_pack["items"]
    )


def test_approved_graph_memory_is_persisted_and_rendered_as_context(tmp_path):
    class GraphMemoryClient:
        def retrieve_context(self, **kwargs):
            assert kwargs["user_id"] == "1"
            assert kwargs["project_id"] == "project-openclaw"
            assert kwargs["agent_id"] == "optimus"
            return {
                "items": [
                    {
                        "node_id": "node-approval",
                        "source_ref": "project-memory:approval-rule",
                        "title": "审批执行约束",
                        "content": "任务计划只有在用户批准后才能执行。",
                        "authority": "approved_projection",
                        "visibility": "project",
                        "score": 0.94,
                        "confidence": 0.95,
                        "freshness_score": 0.8,
                        "relation_relevance": 0.9,
                        "freshness_at": "2026-09-16T00:00:00Z",
                        "relations": [{"type": "APPLIES_TO", "label": "任务规划"}],
                        "evidence_refs": ["mission:approval-rule"],
                    }
                ],
                "health": {"status": "ready", "engine": "graph-memory", "results": 1},
            }

        def health(self):
            return {"status": "configured", "engine": "graph-memory"}

    service = _service(tmp_path)
    service._graph_memory_client = GraphMemoryClient()
    service.upsert_profile(user_id="1", display_name="孙总")

    pack = service.retrieve(
        user_id="1",
        query="审批任务规划",
        project_id="project-openclaw",
        agent_id="optimus",
        purpose="planning",
    )

    graph_item = next(item for item in pack["items"] if item["item_type"] == "graph_memory")
    assert graph_item["source_id"] == "source-graph-memory"
    assert graph_item["source_ref"] == "project-memory:approval-rule"
    assert graph_item["metadata"]["relations"][0]["type"] == "APPLIES_TO"
    assert graph_item["score"] < 0.94
    assert pack["retrieval_health"]["graph_memory"]["status"] == "ready"
    assert "graph_memory" in pack["summary"]
    assert "审批执行约束 (graph_memory)" in service.render_prompt_context(pack, max_chars=5000)


def test_graph_memory_failure_degrades_only_that_source(tmp_path):
    class FailingGraphMemoryClient:
        def retrieve_context(self, **_kwargs):
            raise RuntimeError("gateway offline")

        def health(self):
            return {"status": "configured", "engine": "graph-memory"}

    service = _service(tmp_path)
    service._graph_memory_client = FailingGraphMemoryClient()
    service.upsert_profile(user_id="1", display_name="孙总")

    pack = service.retrieve(user_id="1", query="审批", agent_id="optimus")

    assert pack["status"] == "ready"
    assert pack["retrieval_health"]["graph_memory"]["status"] == "degraded"
    assert "graph_memory" in pack["summary"]


def test_canonical_memory_suppresses_conflicting_graph_projection(tmp_path):
    class GraphMemoryClient:
        def retrieve_context(self, **_kwargs):
            return {
                "items": [
                    {
                        "node_id": "stale-graph-node",
                        "source_ref": "graph:stale-approval-rule",
                        "title": "旧审批规则",
                        "content": "所有任务可以不经批准直接执行。",
                        "authority": "approved_projection",
                        "visibility": "profile",
                        "memory_key": "decision.approval_gate",
                        "score": 0.99,
                        "confidence": 0.99,
                        "freshness_score": 0.99,
                        "relation_relevance": 0.99,
                        "relations": [],
                    }
                ],
                "health": {"status": "ready", "engine": "graph-memory", "results": 1},
            }

        def health(self):
            return {"status": "configured", "engine": "graph-memory"}

    service = _service(tmp_path)
    service._graph_memory_client = GraphMemoryClient()
    service.upsert_profile(user_id="1", display_name="孙总")
    fact = service.upsert_fact(
        user_id="1",
        fact_type="decision",
        fact_key="decision.approval_gate",
        fact_value="所有任务计划必须经管理员批准后执行。",
        importance="critical",
    )

    pack = service.retrieve(user_id="1", query="审批规则", purpose="planning")

    assert not any(item["item_type"] == "graph_memory" for item in pack["items"])
    assert pack["retrieval_health"]["graph_memory"]["conflicts"] == 1
    assert pack["memory_conflicts"] == [
        {
            "memory_key": "decision.approval_gate",
            "scope": "profile",
            "canonical_source_ref": f"fact:{fact['id']}",
            "conflicting_source_ref": "graph:stale-approval-rule",
            "action": "graph_suppressed",
        }
    ]


def test_profile_updates_are_versioned_and_fact_upsert_is_idempotent(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="孙总", summary="初始档案")
    updated = service.upsert_profile(
        user_id="1",
        display_name="孙总",
        summary="更新后的工作档案",
        preferences={"language": "中文"},
    )
    assert updated["version"] == 2
    assert updated["summary"] == "更新后的工作档案"

    first = service.upsert_fact(
        user_id="1",
        fact_type="preference",
        fact_key="preference.language",
        fact_value="中文",
        source_ref="bootstrap",
    )
    second = service.upsert_fact(
        user_id="1",
        fact_type="preference",
        fact_key="preference.language",
        fact_value="中文优先",
        importance="high",
        source_ref="bootstrap",
    )
    assert first["id"] == second["id"]
    assert second["fact_value"] == "中文优先"
    assert second["importance"] == "high"


def test_long_chinese_instruction_falls_back_to_search_terms(tmp_path):
    service = _service(tmp_path)
    calls = []

    def keyword_only_search(query, limit):
        calls.append(query)
        if query != "擎天柱":
            return {"query": query, "nodes": [], "total": 0}
        return {
            "query": query,
            "nodes": [
                {
                    "id": "openclaw/optimus.md",
                    "title": "擎天柱任务入口",
                    "type": "文档",
                    "path": "openclaw/optimus.md",
                    "content": "擎天柱负责规划、审批门禁、任务分发和结果反馈。",
                    "score": 60,
                }
            ][:limit],
            "total": 1,
        }

    service._knowledge_search = keyword_only_search
    service.upsert_profile(user_id="1", display_name="孙总")

    pack = service.retrieve(
        user_id="1",
        query="请让擎天柱统一规划任务，批准后执行并返回测试证据",
        agent_id="optimus",
        purpose="planning",
        limit=20,
    )

    knowledge_items = [
        item for item in pack["items"] if item["item_type"] == "knowledge"
    ]
    assert knowledge_items
    assert knowledge_items[0]["metadata"]["matched_query"] == "擎天柱"
    assert "擎天柱" in calls
    assert pack["retrieval_health"]["knowledge"]["strategy"] == "query-with-term-fallback"


def test_memory_candidates_require_review_and_feed_future_retrieval(tmp_path):
    service = _service(tmp_path)
    feedback = MemoryFeedbackService(service.db_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    old_pack = service.retrieve(
        user_id="1",
        query="统一审批规则",
        project_id="project-openclaw",
        agent_id="optimus",
        purpose="planning",
        limit=20,
    )

    proposed = [
        {
            "target_scope": "profile",
            "memory_type": "decision",
            "memory_key": "decision.approval_gate",
            "title": "统一审批规则",
            "content": "所有智能体计划必须经管理员批准后执行。",
            "importance": "critical",
            "confidence": 0.98,
            "evidence_refs": ["step-1", "[C1]"],
        },
        {
            "target_scope": "project",
            "memory_type": "knowledge",
            "memory_key": "project.context_snapshot",
            "title": "项目上下文快照规则",
            "content": "OpenClaw 项目每个计划版本必须冻结独立上下文快照。",
            "importance": "high",
            "confidence": 0.92,
        },
        {
            "target_scope": "agent",
            "memory_type": "lesson",
            "memory_key": "agent.verify_before_report",
            "title": "擎天柱验收经验",
            "content": "擎天柱在反馈完成前必须核验执行证据和引用。",
            "agent_id": "optimus",
            "importance": "high",
            "confidence": 0.9,
        },
    ]
    candidates = feedback.create_candidates(
        user_id="1",
        mission_id="mission-memory-1",
        plan_version=2,
        project_id="project-openclaw",
        candidates=proposed,
        source_snapshot={"summary": "任务完成"},
    )

    assert len(candidates) == 3
    assert {item["status"] for item in candidates} == {"pending_review"}
    assert service.get_profile("1")["facts"] == []
    assert feedback.stats()["pending_review"] == 3

    duplicate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-memory-1",
        plan_version=2,
        project_id="project-openclaw",
        candidates=proposed,
    )
    assert [item["id"] for item in duplicate] == [item["id"] for item in candidates]
    assert feedback.stats()["total"] == 3

    published = [
        feedback.review_candidate(
            item["id"],
            decision="approve",
            reviewed_by="admin",
            comment="证据充分",
        )
        for item in candidates
    ]
    assert {item["status"] for item in published} == {"published"}
    assert all(item["published_ref"] for item in published)
    assert feedback.stats()["published"] == 3
    assert service.get_profile("1")["facts"][0]["source_type"] == "mission_result"

    new_pack = service.retrieve(
        user_id="1",
        query="统一审批规则 项目上下文快照 擎天柱验收经验",
        project_id="project-openclaw",
        agent_id="optimus",
        purpose="planning",
        limit=30,
    )
    source_refs = {item["source_ref"] for item in new_pack["items"]}
    assert any(ref.startswith("fact:") for ref in source_refs)
    assert any(ref.startswith("project-memory:") for ref in source_refs)
    assert any(ref.startswith("agent-memory:") for ref in source_refs)
    assert not any(
        item["source_id"] == "source-approved-memory"
        for item in service.get_pack(old_pack["id"])["items"]
    )

    with feedback.connect() as conn:
        audits = conn.execute(
            """
            SELECT action, COUNT(*) AS count FROM audit_logs
            WHERE target_type='memory_candidate'
            GROUP BY action
            """
        ).fetchall()
    audit_counts = {row["action"]: row["count"] for row in audits}
    assert audit_counts["memory_candidate_created"] == 3
    assert audit_counts["memory_candidate_published"] == 3


def test_rejected_memory_candidate_is_not_published(tmp_path):
    service = _service(tmp_path)
    feedback = MemoryFeedbackService(service.db_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    candidate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-memory-reject",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "preference",
                "memory_key": "preference.temporary",
                "title": "临时偏好",
                "content": "本次任务临时使用红色。",
            }
        ],
    )[0]

    rejected = feedback.review_candidate(
        candidate["id"],
        decision="reject",
        reviewed_by="admin",
        comment="一次性状态，不进入长期记忆",
    )

    assert rejected["status"] == "rejected"
    assert rejected["published_ref"] is None
    assert service.get_profile("1")["facts"] == []


def test_unrelated_high_facts_do_not_crowd_scoped_approved_memory(tmp_path):
    service = _service(tmp_path, fusion_mode="weighted_rrf")
    service.upsert_profile(user_id="1", display_name="孙总")
    for index in range(8):
        service.upsert_fact(
            user_id="1",
            fact_type="infrastructure",
            fact_key=f"infrastructure.unrelated_{index}",
            fact_value=f"无关基础设施事实 {index}",
            importance="high",
        )
    critical = service.upsert_fact(
        user_id="1",
        fact_type="workflow_rule",
        fact_key="workflow.approval",
        fact_value="所有计划必须批准后执行。",
        importance="critical",
    )
    preference = service.upsert_fact(
        user_id="1",
        fact_type="preference",
        fact_key="preference.language",
        fact_value="默认使用中文。",
        importance="high",
    )
    for index in range(8):
        service.upsert_fact(
            user_id="1",
            fact_type="constraint",
            fact_key=f"constraint.ambient_{index}",
            fact_value=f"默认背景约束 {index}",
            importance="normal",
        )
    feedback = MemoryFeedbackService(service.db_path)
    candidates = feedback.create_candidates(
        user_id="1",
        mission_id="mission-scoped-memory",
        plan_version=1,
        project_id="project-openclaw",
        candidates=[
            {
                "target_scope": "project",
                "memory_type": "knowledge",
                "memory_key": "project.api_contract",
                "title": "项目专属 API 契约",
                "content": "项目使用五个只读记忆 API。",
                "importance": "high",
                "confidence": 0.95,
            },
            {
                "target_scope": "project",
                "memory_type": "knowledge",
                "memory_key": "project.office_color",
                "title": "办公室墙面颜色",
                "content": "办公室墙面采用深灰色。",
                "importance": "high",
                "confidence": 0.99,
            }
        ],
    )
    published = feedback.review_candidate(
        candidates[0]["id"], decision="approve", reviewed_by="admin"
    )
    unrelated = feedback.review_candidate(
        candidates[1]["id"], decision="approve", reviewed_by="admin"
    )

    pack = service.retrieve(
        user_id="1",
        query="项目专属 API 契约有哪些要求？",
        project_id="project-openclaw",
        agent_id="optimus",
        limit=10,
        persist=False,
        graph_mode="disabled",
    )
    refs = [item["source_ref"] for item in pack["items"]]

    assert published["published_ref"] in refs
    assert unrelated["published_ref"] not in refs
    assert f"fact:{critical['id']}" in refs
    assert f"fact:{preference['id']}" in refs
    assert not any(
        item["source_ref"].startswith("fact:")
        and item["title"].startswith("infrastructure.unrelated_")
        for item in pack["items"]
    )
    profile_items = [item for item in pack["items"] if item["item_type"] == "profile_fact"]
    assert len(profile_items) <= 6
    assert refs.index(published["published_ref"]) < refs.index(f"fact:{critical['id']}")
    assert refs.index(published["published_ref"]) < refs.index(f"fact:{preference['id']}")
    assert {item["metadata"]["selection_reason"] for item in profile_items} == {
        "critical_default",
        "ambient_fact_type",
    }


def test_retrieval_decision_abstains_on_background_only_and_supports_overlap(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="测试用户")
    fact = service.upsert_fact(
        user_id="1",
        fact_type="constraint",
        fact_key="constraint.release_gate",
        fact_value="发布前必须完成回归测试。",
        importance="critical",
        source_ref="abstention-test",
    )

    unsupported = service.retrieve(
        user_id="1",
        query="zephyr-quartz-9173 的观测结果是什么",
        persist=False,
        graph_mode="disabled",
    )
    assert unsupported["items"]
    assert unsupported["retrieval_decision"]["status"] == "abstain"
    assert unsupported["retrieval_decision"]["supporting_source_refs"] == []
    assert f"fact:{fact['id']}" in unsupported["retrieval_decision"][
        "background_source_refs"
    ]
    assert "记忆支持判定：不足" in service.render_prompt_context(unsupported)

    supported = service.retrieve(
        user_id="1",
        query="发布前需要完成什么回归测试？",
        persist=True,
        graph_mode="disabled",
    )
    assert supported["retrieval_decision"]["status"] == "supported"
    assert f"fact:{fact['id']}" in supported["retrieval_decision"][
        "supporting_source_refs"
    ]
    restored = service.get_pack(supported["id"])
    assert restored["retrieval_decision"] == supported["retrieval_decision"]
    assert "记忆支持判定：有依据" in service.render_prompt_context(restored)

    empty = {
        "items": [],
        "retrieval_decision": {"status": "abstain"},
    }
    assert "记忆支持判定：不足" in service.render_prompt_context(empty)


def test_approved_memory_creates_and_delivers_durable_graph_projection(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    feedback = MemoryFeedbackService(service.db_path)
    candidate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-graph-projection",
        plan_version=1,
        project_id="project-openclaw",
        candidates=[
            {
                "target_scope": "project",
                "memory_type": "decision",
                "memory_key": "decision.approval_gate",
                "title": "审批执行约束",
                "content": "项目计划必须在用户批准后执行。",
                "importance": "critical",
                "confidence": 0.97,
                "agent_id": "optimus",
                "evidence_refs": ["step-approval"],
            }
        ],
    )[0]

    published = feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )
    assert published["graph_outbox_id"].startswith("graph-event-")

    with feedback.connect() as conn:
        job = conn.execute(
            "SELECT * FROM memory_graph_outbox WHERE id=?",
            (published["graph_outbox_id"],),
        ).fetchone()
    assert job["status"] == "pending"
    assert job["agent_id"] == ""
    payload = json.loads(job["payload"])
    assert payload["source_ref"] == published["published_ref"]
    assert payload["event_type"] == "memory.published"
    assert payload["visibility"] == "project"
    assert payload["agent_id"] == ""

    class FakeGraphSyncClient:
        def __init__(self):
            self.payloads = []

        def upsert_projection(self, payload):
            self.payloads.append(payload)
            return {"status": "upserted", "projection_id": "graph-node-1"}

    client = FakeGraphSyncClient()
    delivered = feedback.process_graph_sync_job(
        published["graph_outbox_id"], sync_client=client, owner="test-worker"
    )
    assert delivered["job"]["status"] == "delivered"
    assert delivered["result"]["projection_id"] == "graph-node-1"
    assert client.payloads[0]["event_id"] == published["graph_outbox_id"]
    assert feedback.process_graph_sync_job(
        published["graph_outbox_id"], sync_client=client, owner="test-worker"
    )["delivered"] is False
    assert len(client.payloads) == 1


def test_graph_projection_failure_retries_without_rolling_back_published_memory(tmp_path):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    feedback = MemoryFeedbackService(service.db_path)
    candidate = feedback.create_candidates(
        user_id="1",
        mission_id="mission-graph-retry",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "constraint",
                "memory_key": "constraint.approval",
                "title": "审批约束",
                "content": "未经批准不得执行不可逆操作。",
            }
        ],
    )[0]
    published = feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )

    class FailingGraphSyncClient:
        def upsert_projection(self, _payload):
            raise RuntimeError("graph gateway offline")

    with pytest.raises(RuntimeError, match="graph gateway offline"):
        feedback.process_graph_sync_job(
            published["graph_outbox_id"], sync_client=FailingGraphSyncClient()
        )
    with feedback.connect() as conn:
        job = conn.execute(
            "SELECT status, attempts, last_error FROM memory_graph_outbox WHERE id=?",
            (published["graph_outbox_id"],),
        ).fetchone()
    assert job["status"] == "retry"
    assert job["attempts"] == 1
    assert "gateway offline" in job["last_error"]
    assert service.get_profile("1")["facts"][0]["fact_key"] == "constraint.approval"


def test_candidate_job_is_durable_and_same_key_supersedes_active_memory(tmp_path):
    service = _service(tmp_path)
    profile = service.upsert_profile(user_id="1", display_name="孙总")
    with service.connect() as conn:
        conn.execute("DROP INDEX idx_profile_facts_active_key")
        for fact_id, value, source_ref in (
            ("fact-old-a", "old-a", "legacy-a"),
            ("fact-old-b", "old-b", "legacy-b"),
        ):
            conn.execute(
                """
                INSERT INTO profile_facts
                (id, profile_id, fact_type, fact_key, fact_value, importance,
                 confidence, source_type, source_ref, status, metadata,
                 created_at, updated_at)
                VALUES (?, ?, 'decision', 'decision.single_entry', ?, 'high',
                        1.0, 'legacy', ?, 'active', '{}', ?, ?)
                """,
                (
                    fact_id,
                    profile["id"],
                    value,
                    source_ref,
                    "2026-07-01T00:00:00+00:00",
                    "2026-07-01T00:00:00+00:00",
                ),
            )
    feedback = MemoryFeedbackService(service.db_path)
    with feedback.connect() as conn:
        assert conn.execute(
            """
            SELECT COUNT(*) FROM profile_facts
            WHERE profile_id=? AND fact_key='decision.single_entry'
              AND status='active'
            """,
            (profile["id"],),
        ).fetchone()[0] == 1
    base = {
        "target_scope": "profile",
        "memory_type": "decision",
        "memory_key": "decision.single_entry",
        "title": "统一入口",
        "importance": "critical",
        "confidence": 0.95,
    }
    first_job = feedback.enqueue_candidate_job(
        user_id="1",
        mission_id="mission-job-1",
        plan_version=1,
        candidates=[{**base, "content": "擎天柱是唯一任务入口。"}],
    )
    first_result = feedback.process_candidate_job(first_job["id"], owner="test")
    first_candidate = first_result["candidates"][0]
    first_review = feedback.review_candidate(
        first_candidate["id"],
        decision="approve",
        reviewed_by="admin",
    )
    repeated_review = feedback.review_candidate(
        first_candidate["id"],
        decision="approve",
        reviewed_by="admin",
    )

    second_job = feedback.enqueue_candidate_job(
        user_id="1",
        mission_id="mission-job-2",
        plan_version=1,
        candidates=[{**base, "content": "擎天柱统一接收任务并先提交计划审批。"}],
    )
    second_result = feedback.process_candidate_job(second_job["id"], owner="test")
    feedback.review_candidate(
        second_result["candidates"][0]["id"],
        decision="approve",
        reviewed_by="admin",
    )

    facts = [
        fact
        for fact in service.get_profile("1")["facts"]
        if fact["fact_key"] == "decision.single_entry"
    ]
    assert first_review["review_changed"] is True
    assert repeated_review["review_changed"] is False
    assert len(facts) == 1
    assert facts[0]["fact_value"] == "擎天柱统一接收任务并先提交计划审批。"
    assert feedback.process_candidate_job(first_job["id"])["job"]["status"] == "completed"


def test_candidate_job_lease_prevents_concurrent_processing_and_startup_reset(
    tmp_path,
):
    service = _service(tmp_path)
    service.upsert_profile(user_id="1", display_name="孙总")
    first = MemoryFeedbackService(service.db_path)
    second = MemoryFeedbackService(service.db_path)
    job = first.enqueue_candidate_job(
        user_id="1",
        mission_id="mission-concurrent-memory",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "lesson",
                "memory_key": "lesson.concurrent",
                "title": "并发提炼",
                "content": "同一提炼任务只允许一个 worker 处理。",
            }
        ],
    )
    started = threading.Event()
    release = threading.Event()
    original_create = first.create_candidates

    def slow_create(**kwargs):
        started.set()
        assert release.wait(timeout=3)
        return original_create(**kwargs)

    first.create_candidates = slow_create
    result = {}

    def run_first():
        result.update(first.process_candidate_job(job["id"], owner="worker-1"))

    thread = threading.Thread(target=run_first)
    thread.start()
    assert started.wait(timeout=3)
    with pytest.raises(MemoryFeedbackError, match="already leased"):
        second.process_candidate_job(job["id"], owner="worker-2")

    restarted = MemoryFeedbackService(service.db_path)
    with restarted.connect() as conn:
        live = conn.execute(
            "SELECT status, attempts FROM memory_candidate_jobs WHERE id=?",
            (job["id"],),
        ).fetchone()
    assert live["status"] == "processing"
    assert live["attempts"] == 1

    release.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert result["job"]["status"] == "completed"

    legacy_job = first.enqueue_candidate_job(
        user_id="1",
        mission_id="mission-legacy-memory-job",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "lesson",
                "memory_key": "lesson.legacy_job",
                "title": "旧任务恢复",
                "content": "无租约字段的旧处理任务必须恢复。",
            }
        ],
    )
    with first.connect() as conn:
        conn.execute(
            """
            UPDATE memory_candidate_jobs
            SET status='processing', lock_token=NULL, lease_expires_at=NULL
            WHERE id=?
            """,
            (legacy_job["id"],),
        )
    migrated = MemoryFeedbackService(service.db_path)
    with migrated.connect() as conn:
        recovered = conn.execute(
            "SELECT status FROM memory_candidate_jobs WHERE id=?",
            (legacy_job["id"],),
        ).fetchone()
    assert recovered["status"] == "retry"
    assert migrated.process_candidate_job(legacy_job["id"])["job"]["status"] == "completed"


def test_profile_active_key_index_is_independent_of_service_import_order(tmp_path):
    db_path = str(tmp_path / "reverse-init.db")
    MemoryFeedbackService(db_path)
    ContextRetrievalService(
        db_path,
        memory_root=str(tmp_path / "reverse-memory"),
        workspace_root=str(tmp_path / "reverse-agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
    )

    conn = sqlite3.connect(db_path)
    index = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='index' AND name='idx_profile_facts_active_key'
        """
    ).fetchone()
    conn.close()
    assert index == ("idx_profile_facts_active_key",)
