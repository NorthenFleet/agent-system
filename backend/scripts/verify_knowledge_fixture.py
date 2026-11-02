"""Run a real-source, disposable PG publication drill and save metadata evidence.

The approval below is a test-fixture action, never a production/user approval.
All test tables and source copies are removed after the drill.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from models import knowledge_schema_v1 as t
    from services.knowledge.service import KnowledgeService, digest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ["KNOWLEDGE_TEST_DATABASE_URL"]
    parsed = sa.engine.make_url(url)
    if parsed.get_backend_name() != "postgresql" or "test" not in (parsed.database or ""):
        parser.error("KNOWLEDGE_TEST_DATABASE_URL must name an explicit PostgreSQL test database")
    schema = "sb_drill_" + uuid.uuid4().hex
    admin = sa.create_engine(url)
    engine = None
    try:
        with admin.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        engine = sa.create_engine(parsed.update_query_dict({"options": f"-csearch_path={schema}"}))
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                for suffix in ['domain', 'projection', 'context', 'operations']:
                    migration_path = Path(__file__).resolve().parents[1] / 'alembic/versions' / ('20261006_knowledge_' + suffix + '.py')
                    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
                    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
                    migration.upgrade()
        with tempfile.TemporaryDirectory(prefix="sb-drill-") as directory:
            service = KnowledgeService(engine, Path(directory) / "sources")
            actor = "isolated-fixture-actor"
            space = service.create_space(actor, "agent-system 设计文档演练", "", "space")
            content = args.source.read_bytes()
            source = service.upload(actor, space["id"], args.source.name, content, "upload")
            job = service.enqueue(actor, space["id"], source["version_id"], {}, "ingest")
            candidate = service.compile_job(service.claim_job())
            change = service.change(actor, candidate["id"])
            spans = service.get_source(actor, source["version_id"])["spans"]
            compact = lambda value: "".join(value.split())
            assert compact("".join(s["text"] for s in spans)) == compact(content.decode("utf-8-sig"))
            assert service.query(actor, space["id"], "原始资料")["citations"] == []
            service.review(actor, candidate["id"], candidate["payload_hash"], "approve", "隔离演练的测试批准，不是用户正式审核", "review")
            release = service.publish(actor, candidate["id"], candidate["payload_hash"], "publish")
            answer = service.query(actor, space["id"], "原始资料")
            assert answer["citations"]
            assert service.download_source(actor, source["version_id"])[0] == content
            duplicate = service.upload(actor, space["id"], args.source.name, content, "duplicate")
            assert duplicate["duplicate"] and duplicate["version_id"] == source["version_id"]
            service.retract_source(actor, source["version_id"], "retract")
            assert service.query(actor, space["id"], "原始资料")["citations"] == []
            report = {"schema_version": "knowledge-drill-v1", "environment": "disposable-postgresql",
                "source_name": args.source.name, "source_sha256": digest(content), "source_bytes": len(content),
                "source_spans": len(spans), "source_text_preserved": True, "unaudited_query_empty": True,
                "approval_kind": "isolated_test_fixture_only", "release_created": True,
                "citation_count": len(answer["citations"]), "original_download_matches": True,
                "duplicate_reuses_version": True, "retraction_blocks_query": True,
                "projection_status": release["projection_status"], "production_modified": False}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if engine:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
