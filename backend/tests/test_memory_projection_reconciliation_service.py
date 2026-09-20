import sqlite3
from contextlib import contextmanager

from services.memory_projection_reconciliation_service import (
    MemoryProjectionReconciliationService,
)
from services.memory_vector_service import MemoryVectorDocument


class _VectorService:
    def __init__(self, db_path, documents, *, consistent=True):
        self.db_path = db_path
        self.documents = documents
        self.consistent = consistent

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def load_approved_documents(self, _conn):
        return list(self.documents)

    def reconcile_projection(self):
        return {
            "status": "ready" if self.consistent else "drifted",
            "consistent": self.consistent,
            "canonical_count": len(self.documents),
            "projection_count": len(self.documents),
        }

    def operations_status(self):
        return {
            "queue": {
                "pending": 0,
                "processing": 0,
                "completed": len(self.documents),
                "dead_letter": 0,
            }
        }


class _GraphClient:
    def __init__(self, inventory):
        self.inventory = inventory

    def projection_inventory(self, *, user_id="", limit=5000):
        assert limit == 5000
        return [
            item for item in self.inventory
            if not user_id or item["owner_user_id"] == user_id
        ]


class _Lifecycle:
    def __init__(self, consistent=True):
        self.consistent = consistent

    def verify(self, *, user_id=""):
        return {"consistent": self.consistent, "records_checked": 1, "violations": []}


def _db(tmp_path):
    path = str(tmp_path / "memory-reconcile.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE memory_graph_outbox (
            id TEXT PRIMARY KEY, status TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return path


def _document():
    return MemoryVectorDocument(
        source_ref="project-memory:memory-1",
        source_type="project_memory",
        title="审批规则",
        content="计划必须批准后执行。",
        user_id="user-1",
        project_id="project-1",
        status="active",
    )


def test_reconciliation_passes_when_all_authorities_and_projections_match(tmp_path):
    db_path = _db(tmp_path)
    document = _document()
    service = MemoryProjectionReconciliationService(
        db_path,
        vector_service=_VectorService(db_path, [document]),
        graph_client=_GraphClient([
            {
                "source_ref": document.source_ref,
                "owner_user_id": document.user_id,
                "project_id": document.project_id,
                "agent_id": "",
                "visibility": "project",
                "content_hash": document.content_hash,
                "status": "active",
            }
        ]),
        lifecycle_service=_Lifecycle(),
    )

    result = service.reconcile()

    assert result["consistent"] is True
    assert result["graph"]["consistent"] is True
    assert result["queues_clear"] is True


def test_reconciliation_reports_hash_scope_orphan_and_queue_drift(tmp_path):
    db_path = _db(tmp_path)
    document = _document()
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO memory_graph_outbox(id,status) VALUES ('event-1','dead_letter')")
    conn.commit()
    conn.close()
    service = MemoryProjectionReconciliationService(
        db_path,
        vector_service=_VectorService(db_path, [document]),
        graph_client=_GraphClient([
            {
                "source_ref": document.source_ref,
                "owner_user_id": document.user_id,
                "project_id": "wrong-project",
                "agent_id": "",
                "visibility": "project",
                "content_hash": "stale",
                "status": "active",
            },
            {
                "source_ref": "project-memory:orphan",
                "owner_user_id": document.user_id,
                "project_id": document.project_id,
                "agent_id": "",
                "visibility": "project",
                "content_hash": "orphan",
                "status": "active",
            },
        ]),
        lifecycle_service=_Lifecycle(),
    )

    result = service.reconcile()

    assert result["consistent"] is False
    assert result["graph"]["stale_refs"] == [document.source_ref]
    assert result["graph"]["scope_drift_refs"] == [document.source_ref]
    assert result["graph"]["orphaned_active_refs"] == ["project-memory:orphan"]
    assert result["queues"]["graph"]["dead_letter"] == 1
