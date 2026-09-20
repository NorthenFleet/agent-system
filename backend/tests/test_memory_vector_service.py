import json
import sqlite3

from services.context_retrieval_service import ContextRetrievalService
from services.memory_feedback_service import MemoryFeedbackService
from services.memory_retrieval_service import RetrievalScope
from services.memory_vector_service import (
    ApprovedMemoryVectorService,
    MemoryVectorDocument,
    candidate_vector_document,
    enqueue_vector_document,
    normalize_postgres_dsn,
)


def test_profile_candidate_projects_to_canonical_profile_shape():
    document = candidate_vector_document(
        {
            "target_scope": "profile",
            "title": "展示标题",
            "memory_key": "workflow.approval_gate",
            "content": "批准后执行",
            "user_id": "user-1",
            "project_id": "project-should-not-leak",
            "agent_id": "proposer-not-owner",
        },
        "fact:fact-1",
        now="2026-09-20T00:00:00+00:00",
    )

    assert document.title == "workflow.approval_gate"
    assert document.project_id == ""
    assert document.agent_id == ""


class FakeEmbeddingProvider:
    model = "test-embedding"
    dimension = 3

    def __init__(self):
        self.inputs = []

    def embed(self, texts):
        self.inputs.extend(texts)
        return [[0.8, 0.1, 0.1] for _ in texts]


class FailingOnceEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary embedding failure")
        return super().embed(texts)


class FakeVectorStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.upserts = []
        self.search_scopes = []
        self.deletes = []
        self.schema_initialized = False
        self.inventory_rows = []

    def upsert(self, document, embedding, *, model, dimension):
        self.upserts.append(
            {
                "document": document,
                "embedding": embedding,
                "model": model,
                "dimension": dimension,
            }
        )
        self.inventory_rows = [
            row for row in self.inventory_rows
            if row["source_ref"] != document.source_ref
        ]
        self.inventory_rows.append(
            {
                "source_ref": document.source_ref,
                "source_type": document.source_type,
                "content_hash": document.content_hash,
                "embedding_model": model,
                "embedding_dimension": dimension,
            }
        )

    def search(self, embedding, *, scope, limit, model):
        self.search_scopes.append(scope)
        return self.rows[:limit]

    def delete(self, source_ref, *, user_id):
        self.deletes.append({"source_ref": source_ref, "user_id": user_id})
        self.inventory_rows = [
            row for row in self.inventory_rows if row["source_ref"] != source_ref
        ]

    def ensure_schema(self):
        self.schema_initialized = True

    def inventory(self):
        return list(self.inventory_rows)


def test_sqlalchemy_postgres_url_is_normalized_for_psycopg2():
    assert normalize_postgres_dsn(
        "postgresql+psycopg2:///team_dashboard"
    ) == "postgresql:///team_dashboard"
    assert normalize_postgres_dsn(
        "postgresql+psycopg://user:secret@db/memory"
    ) == "postgresql://user:secret@db/memory"


def test_projection_schema_initialization_is_explicit(tmp_path):
    store = FakeVectorStore()
    service = ApprovedMemoryVectorService(
        str(tmp_path / "context.db"),
        provider=FakeEmbeddingProvider(),
        store=store,
        enabled=True,
    )

    result = service.initialize_projection()

    assert result["initialized"] is True
    assert result["status"] == "ready"
    assert store.schema_initialized is True


def test_vector_job_idempotency_changes_with_embedding_identity(
    tmp_path, monkeypatch
):
    database = tmp_path / "context.db"
    document = MemoryVectorDocument(
        source_ref="project-memory:1",
        source_type="project_memory",
        title="release gate",
        content="tests must pass",
        user_id="user-1",
        project_id="project-1",
    )
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "embedding-model-a")
        first = enqueue_vector_document(connection, document)
        monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "embedding-model-b")
        second = enqueue_vector_document(connection, document)
        connection.commit()
        rows = connection.execute(
            "SELECT id, idempotency_key FROM memory_vector_index_jobs ORDER BY created_at, id"
        ).fetchall()
    finally:
        connection.close()

    assert first != second
    assert len(rows) == 2
    assert rows[0]["idempotency_key"] != rows[1]["idempotency_key"]


def _context_service(tmp_path, *, vector_retriever=None, fusion_mode=None):
    memory_root = tmp_path / "memory"
    workspace_root = tmp_path / "workspace"
    memory_root.mkdir(exist_ok=True)
    workspace_root.mkdir(exist_ok=True)
    return ContextRetrievalService(
        str(tmp_path / "context.db"),
        memory_root=str(memory_root),
        workspace_root=str(workspace_root),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        knowledge_content=lambda _node, _limit: {"content": "", "available": False},
        vector_retriever=vector_retriever,
        fusion_mode=fusion_mode,
    )


def _approved_project_candidate(context, feedback):
    context.upsert_profile(user_id="user-1", display_name="测试用户")
    candidate = feedback.create_candidates(
        user_id="user-1",
        mission_id="mission-vector-1",
        plan_version=1,
        project_id="project-1",
        candidates=[
            {
                "target_scope": "project",
                "memory_type": "decision",
                "memory_key": "decision.release_gate",
                "title": "发布门禁",
                "content": "生产发布必须先通过回归测试。",
                "importance": "critical",
                "confidence": 0.97,
            }
        ],
    )[0]
    return feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )


def test_approval_transaction_enqueues_vector_job(tmp_path):
    context = _context_service(tmp_path)
    feedback = MemoryFeedbackService(context.db_path)

    published = _approved_project_candidate(context, feedback)

    assert published["vector_job_id"].startswith("vector-job-")
    with feedback.connect() as conn:
        row = conn.execute(
            "SELECT * FROM memory_vector_index_jobs WHERE id=?",
            (published["vector_job_id"],),
        ).fetchone()
    payload = json.loads(row["payload"])
    assert row["status"] == "pending"
    assert payload["source_ref"] == published["published_ref"]
    assert payload["metadata"]["authority"] == "approved_memory"


def test_worker_processes_vector_job_idempotently(tmp_path):
    context = _context_service(tmp_path)
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore()
    vector_service = ApprovedMemoryVectorService(
        context.db_path,
        provider=provider,
        store=store,
        enabled=True,
    )
    feedback = MemoryFeedbackService(
        context.db_path,
        vector_index_service=vector_service,
    )
    published = _approved_project_candidate(context, feedback)

    processed = feedback.process_pending_vector_index_jobs(owner="test-worker")

    assert processed == [
        {
            "job_id": published["vector_job_id"],
            "status": "completed",
            "operation": "upsert",
            "source_ref": published["published_ref"],
        }
    ]
    assert provider.inputs == ["发布门禁\n生产发布必须先通过回归测试。"]
    assert store.upserts[0]["model"] == "test-embedding"
    assert store.upserts[0]["document"].project_id == "project-1"
    assert feedback.process_pending_vector_index_jobs(owner="test-worker") == []
    reconciliation = vector_service.reconcile_projection()
    assert reconciliation["consistent"] is True
    assert reconciliation["canonical_count"] == 1
    assert reconciliation["projection_count"] == 1


def test_worker_preserves_immutable_attempt_history_across_retry(tmp_path):
    context = _context_service(tmp_path)
    provider = FailingOnceEmbeddingProvider()
    store = FakeVectorStore()
    vector_service = ApprovedMemoryVectorService(
        context.db_path,
        provider=provider,
        store=store,
        enabled=True,
    )
    feedback = MemoryFeedbackService(
        context.db_path,
        vector_index_service=vector_service,
    )
    published = _approved_project_candidate(context, feedback)

    first = feedback.process_pending_vector_index_jobs(owner="retry-worker")
    assert first[0]["status"] == "retry"
    with feedback.connect() as connection:
        connection.execute(
            "UPDATE memory_vector_index_jobs SET next_attempt_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", published["vector_job_id"]),
        )

    second = feedback.process_pending_vector_index_jobs(owner="retry-worker")

    assert second[0]["status"] == "completed"
    with feedback.connect() as connection:
        attempts = connection.execute(
            """
            SELECT attempt_number, status, error
            FROM memory_vector_index_attempts
            WHERE job_id=? ORDER BY attempt_number
            """,
            (published["vector_job_id"],),
        ).fetchall()
    assert [row["attempt_number"] for row in attempts] == [1, 2]
    assert [row["status"] for row in attempts] == ["failed", "succeeded"]
    assert "temporary embedding failure" in attempts[0]["error"]
    assert attempts[1]["error"] is None
    operations = vector_service.operations_status()
    assert operations["attempt_audit"]["by_status"] == {
        "failed": 1,
        "succeeded": 1,
    }


def test_archiving_approved_fact_enqueues_and_processes_vector_delete(tmp_path):
    context = _context_service(tmp_path)
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore()
    vector_service = ApprovedMemoryVectorService(
        context.db_path, provider=provider, store=store, enabled=True
    )
    feedback = MemoryFeedbackService(
        context.db_path, vector_index_service=vector_service
    )
    context.upsert_profile(user_id="user-1", display_name="测试用户")
    candidate = feedback.create_candidates(
        user_id="user-1",
        mission_id="mission-profile-vector",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_type": "preference",
                "memory_key": "preference.language",
                "title": "语言偏好",
                "content": "输出使用中文。",
            }
        ],
    )[0]
    published = feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )
    feedback.process_pending_vector_index_jobs(owner="test-worker")
    fact_id = published["published_ref"].split(":", 1)[1]

    assert context.archive_fact("user-1", fact_id) is True
    deleted = feedback.process_pending_vector_index_jobs(owner="test-worker")

    assert deleted[0]["operation"] == "delete"
    assert store.deletes == [
        {"source_ref": published["published_ref"], "user_id": "user-1"}
    ]


def test_archive_supersedes_pending_upsert_before_delete(tmp_path):
    context = _context_service(tmp_path)
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore()
    vector_service = ApprovedMemoryVectorService(
        context.db_path, provider=provider, store=store, enabled=True
    )
    feedback = MemoryFeedbackService(
        context.db_path, vector_index_service=vector_service
    )
    context.upsert_profile(user_id="user-1", display_name="测试用户")
    candidate = feedback.create_candidates(
        user_id="user-1",
        mission_id="mission-archive-before-index",
        plan_version=1,
        candidates=[
            {
                "target_scope": "profile",
                "memory_key": "preference.output",
                "title": "输出偏好",
                "content": "使用简洁格式。",
            }
        ],
    )[0]
    published = feedback.review_candidate(
        candidate["id"], decision="approve", reviewed_by="admin"
    )
    fact_id = published["published_ref"].split(":", 1)[1]

    assert context.archive_fact("user-1", fact_id) is True
    processed = feedback.process_pending_vector_index_jobs(owner="test-worker")

    assert [item["operation"] for item in processed] == ["delete"]
    assert store.upserts == []
    assert store.deletes[0]["source_ref"] == published["published_ref"]
    with feedback.connect() as conn:
        original = conn.execute(
            "SELECT status FROM memory_vector_index_jobs WHERE id=?",
            (published["vector_job_id"],),
        ).fetchone()
    assert original["status"] == "superseded"


def test_vector_retriever_returns_contract_and_preserves_scope(tmp_path):
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore(
        [
            {
                "source_ref": "project-memory:memory-1",
                "source_type": "project_memory",
                "title": "发布门禁",
                "content": "生产发布必须先通过回归测试。",
                "user_id": "user-1",
                "project_id": "project-1",
                "agent_id": "",
                "importance": "critical",
                "confidence": 0.97,
                "status": "active",
                "content_hash": "hash-1",
                "metadata": {"memory_key": "decision.release_gate"},
                "memory_updated_at": "2026-09-16T00:00:00+00:00",
                "similarity": 0.91,
            }
        ]
    )
    retriever = ApprovedMemoryVectorService(
        str(tmp_path / "context.db"), provider=provider, store=store, enabled=True
    )

    batch = retriever.retrieve_vector(
        query="上线前要做什么",
        scope=RetrievalScope(
            user_id="user-1", project_id="project-1", agent_id="optimus"
        ),
        limit=5,
    )

    assert batch.health["status"] == "ready"
    assert batch.health["results"] == 1
    assert store.search_scopes[0].user_id == "user-1"
    item = batch.items[0].to_context_item()
    assert item["metadata"]["retrieval"]["primary_channel"] == "vector"
    assert item["metadata"]["retrieval"]["scope"]["project_id"] == "project-1"
    assert item["score"] == 0.91


def test_context_pack_uses_vector_channel_and_merges_duplicate_evidence(tmp_path):
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore(
        [
            {
                "source_ref": "project-memory:shared-1",
                "source_type": "project_memory",
                "title": "发布门禁",
                "content": "生产发布必须先通过回归测试。",
                "user_id": "user-1",
                "project_id": "project-1",
                "agent_id": "",
                "importance": "critical",
                "confidence": 0.97,
                "status": "active",
                "metadata": {"memory_key": "decision.release_gate"},
                "similarity": 0.91,
            }
        ]
    )
    retriever = ApprovedMemoryVectorService(
        str(tmp_path / "context.db"), provider=provider, store=store, enabled=True
    )
    context = _context_service(tmp_path, vector_retriever=retriever)
    context.upsert_profile(user_id="user-1", display_name="测试用户")
    with sqlite3.connect(context.db_path) as conn:
        now = "2026-09-16T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO project_context_memories
            (id, user_id, project_id, memory_key, title, content, importance,
             confidence, source_type, source_ref, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                "shared-1", "user-1", "project-1", "decision.release_gate",
                "发布门禁", "生产发布必须先通过回归测试。", "critical", 0.97,
                "mission_result", "mission:1", '{}', now, now,
            ),
        )

    pack = context.retrieve(
        user_id="user-1",
        project_id="project-1",
        agent_id="optimus",
        query="生产发布回归测试",
        limit=20,
        graph_mode="disabled",
    )

    item = next(
        item for item in pack["items"]
        if item["source_ref"] == "project-memory:shared-1"
    )
    assert item["metadata"]["retrieval"]["channels"] == ["lexical", "vector"]
    assert set(item["metadata"]["retrieval"]["scores"]) >= {"lexical", "vector", "final"}
    assert pack["retrieval_strategy"]["channels"]["vector"]["selected"] == 1
    assert pack["retrieval_strategy"]["fusion"] == "weighted-rrf.v1"
    assert pack["retrieval_health"]["hybrid_fusion"]["multi_channel_candidates"] == 1


def test_shadow_mode_serves_baseline_and_records_rrf_comparison(tmp_path):
    provider = FakeEmbeddingProvider()
    store = FakeVectorStore()
    retriever = ApprovedMemoryVectorService(
        str(tmp_path / "context.db"), provider=provider, store=store, enabled=True
    )
    context = _context_service(
        tmp_path, vector_retriever=retriever, fusion_mode="shadow"
    )
    context.upsert_profile(user_id="user-1", display_name="测试用户")

    pack = context.retrieve(
        user_id="user-1",
        query="测试排序影子模式",
        graph_mode="disabled",
        persist=False,
    )

    fusion = pack["retrieval_health"]["hybrid_fusion"]
    assert pack["retrieval_strategy"]["fusion"] == "score-sort-baseline"
    assert pack["retrieval_strategy"]["fusion_rollout_mode"] == "shadow"
    assert fusion["candidate_strategy"] == "weighted-rrf.v1"
    assert "comparison" in fusion


def test_disabled_vector_backend_is_a_non_blocking_degradation(tmp_path):
    retriever = ApprovedMemoryVectorService(str(tmp_path / "context.db"), enabled=False)

    batch = retriever.retrieve_vector(
        query="任意查询",
        scope=RetrievalScope(user_id="user-1"),
        limit=5,
    )

    assert batch.items == []
    assert batch.health["status"] == "disabled"
