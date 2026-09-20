import importlib.util
import sqlite3
from pathlib import Path

from services.memory_feedback_service import MemoryFeedbackService


SCRIPT = Path(__file__).parents[1] / "scripts" / "backfill_approved_graph_projections.py"


def _module():
    spec = importlib.util.spec_from_file_location("backfill_graph", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _Client:
    def __init__(self):
        self.payloads = []

    def upsert_projection(self, payload):
        self.payloads.append(payload)
        return {"status": "accepted", "projection_id": "projection-1"}


def test_backfill_projects_published_candidates_with_stable_scope(tmp_path):
    db_path = str(tmp_path / "unified.db")
    MemoryFeedbackService(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO memory_candidates
        (id,user_id,mission_id,plan_version,project_id,agent_id,target_scope,
         memory_type,memory_key,title,content,rationale,importance,confidence,
         evidence_refs,source_ref,source_snapshot,fingerprint,status,proposed_by,
         reviewed_by,reviewed_at,published_ref,published_at,created_at,updated_at)
        VALUES ('candidate-1','user-1','mission-1',2,'project-1','optimus','project',
                'decision','decision.approval','审批规则','批准后执行','','critical',
                0.98,'["evidence-1"]','mission:1','{}','fingerprint-1','published',
                'optimus','admin','now','project-memory:memory-1','now','now','now')
        """
    )
    conn.commit()
    conn.close()
    client = _Client()

    result = _module().backfill(db_path=db_path, client=client)

    assert result["projected"] == 1
    assert result["failed"] == 0
    assert client.payloads[0]["user_id"] == "user-1"
    assert client.payloads[0]["project_id"] == "project-1"
    assert client.payloads[0]["agent_id"] == ""
    assert client.payloads[0]["visibility"] == "project"
    assert client.payloads[0]["source_ref"] == "project-memory:memory-1"
    assert len(client.payloads[0]["content_hash"]) == 64
    assert client.payloads[0]["event_id"].startswith("graph-backfill-")
    second_client = _Client()
    second_result = _module().backfill(db_path=db_path, client=second_client)
    assert second_result["failed"] == 0
    assert second_client.payloads[0]["event_id"] == client.payloads[0]["event_id"]
