import sqlite3

from services.context_retrieval_service import ContextRetrievalService
from services.memory_awareness_service import MemoryAwarenessService


class _GraphClient:
    def health(self):
        return {"status": "configured", "enabled": True}

    def retrieve_context(self, **_kwargs):
        return {
            "items": [],
            "health": {
                "status": "degraded",
                "engine": "graph-memory",
                "results": 0,
                "reason": "projection endpoint unavailable",
            },
        }


def _graph(path, *, nodes=0, messages=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE gm_nodes (id TEXT PRIMARY KEY);
        CREATE TABLE gm_edges (id TEXT PRIMARY KEY);
        CREATE TABLE gm_messages (id TEXT PRIMARY KEY);
        """
    )
    conn.executemany("INSERT INTO gm_nodes (id) VALUES (?)", [(f"n-{i}",) for i in range(nodes)])
    conn.executemany("INSERT INTO gm_messages (id) VALUES (?)", [(f"m-{i}",) for i in range(messages)])
    conn.commit()
    conn.close()


def test_introspection_keeps_canonical_memory_separate_from_private_graph(tmp_path):
    workspace = tmp_path / "agents" / "optimus" / "workspace"
    (workspace / "memory" / "short-term").mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Long memory\n", encoding="utf-8")
    (workspace / "memory" / "short-term" / "2026-09-16.md").write_text(
        "# Today\n", encoding="utf-8"
    )
    service = ContextRetrievalService(
        str(tmp_path / "unified.db"),
        memory_root=str(tmp_path / "lexical"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        graph_memory_client_instance=_GraphClient(),
    )
    service.upsert_profile(user_id="user-1", display_name="测试用户")
    service.upsert_fact(
        user_id="user-1",
        fact_type="decision",
        fact_key="decision.single_entry",
        fact_value="擎天柱是唯一任务入口。",
        importance="critical",
        source_ref="test-fact",
    )
    with service.connect() as conn:
        conn.execute(
            """
            INSERT INTO project_context_memories
            (id,user_id,project_id,memory_key,title,content,importance,confidence,
             source_type,source_ref,status,metadata,created_at,updated_at)
            VALUES ('pm-1','user-1','project-1','project.rule','项目规则',
                    '计划需审批。','high',1.0,'mission_result','mission:1','active','{}','now','now')
            """
        )
        conn.execute(
            """
            INSERT INTO agent_memories
            (id,agent_id,user_id,project_id,memory_key,memory_type,title,content,
             source,status,created_at,updated_at,metadata)
            VALUES ('am-1','optimus','user-1','project-1','agent.lesson','lesson',
                    '协作经验','先确认再执行。','mission:1','active','now','now',
                    '{"importance":"normal","confidence":0.9}')
            """
        )

    graph_root = tmp_path / "graph-memory.db"
    _graph(graph_root, nodes=2, messages=3)
    _graph(tmp_path / "graph-memory.db.agents" / "optimus.sqlite", nodes=0, messages=15)

    result = MemoryAwarenessService(
        service, graph_db_path=str(graph_root)
    ).inspect(
        user_id="user-1",
        query="你记住了什么",
        agent_id="optimus",
        project_id="project-1",
    )

    assert result["status"] == "ready"
    assert result["counts"]["profile_facts"] == 1
    assert result["counts"]["project_memories"] == 1
    assert result["counts"]["agent_memories"] == 1
    assert result["channels"]["native_private_graph"]["nodes"] == 0
    assert result["channels"]["native_global_graph"]["nodes"] == 2
    assert result["interpretation"]["private_graph_empty_means_system_empty"] is False
    assert {item["scope"] for item in result["remembered_items"]} == {
        "profile",
        "project",
        "agent",
    }
    assert result["retrieval"]["pack_id"].startswith("context-")
    assert any(
        item["channel"] == "approved_graph_projection"
        for item in result["degraded_channels"]
    )


def test_introspection_counts_are_not_truncated_by_preview_limit(tmp_path):
    service = ContextRetrievalService(
        str(tmp_path / "unified.db"),
        memory_root=str(tmp_path / "lexical"),
        workspace_root=str(tmp_path / "agents"),
        knowledge_search=lambda _query, _limit: {"nodes": [], "total": 0},
        graph_memory_client_instance=_GraphClient(),
    )
    service.upsert_profile(user_id="user-1", display_name="测试用户")
    for index in range(3):
        service.upsert_fact(
            user_id="user-1",
            fact_type="general",
            fact_key=f"fact.{index}",
            fact_value=f"value-{index}",
        )

    result = MemoryAwarenessService(
        service, graph_db_path=str(tmp_path / "missing.db")
    ).inspect(user_id="user-1", query="记忆", limit=1, persist=False)

    assert result["counts"]["profile_facts"] == 3
    assert len(result["remembered_items"]) == 1

