"""Explicit KB-only provisioning in a dedicated schema; no legacy migrations."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from models.knowledge_schema_v1 import metadata as domain
from models.knowledge_projection_v2 import metadata as projection
from models.knowledge_context_v3 import metadata as context
from models.knowledge_operations_v4 import metadata as operations
from services.knowledge.service import KnowledgeError, digest

MIGRATIONS = [('domain', domain), ('projection', projection), ('context', context), ('operations', operations)]


def apply(engine, schema):
    if engine.dialect.name != 'postgresql' or not re.fullmatch(r'second_brain(?:_[a-f0-9]{32})?', schema):
        raise KnowledgeError('unsafe_schema_target', '仅允许独立 second_brain schema')
    with engine.begin() as conn:
        conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        conn.execute(sa.text('SELECT pg_advisory_xact_lock(:key)'), {'key':int(digest(('knowledge-schema', schema))[:15],16)})
        conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
        existing = set(sa.inspect(conn).get_table_names(schema=schema))
        allowed = {'kb_schema_migrations'} | {table.name for _, meta in MIGRATIONS for table in meta.tables.values()}
        if existing - allowed:
            raise KnowledgeError('foreign_schema_objects', '目标 schema 存在非知识域表，拒绝修改', 409)
        conn.exec_driver_sql('''CREATE TABLE IF NOT EXISTS kb_schema_migrations
            (revision varchar(80) PRIMARY KEY, file_sha256 varchar(64) NOT NULL,
             applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        applied = {r['revision']:r['file_sha256'] for r in conn.execute(sa.text('select * from kb_schema_migrations')).mappings()}
        completed = []
        for suffix, metadata in MIGRATIONS:
            name = '20261006_knowledge_' + suffix
            path = Path(__file__).resolve().parents[1] / 'alembic/versions' / (name + '.py')
            checksum = digest(path.read_bytes())
            if name in applied:
                if applied[name] != checksum:
                    raise KnowledgeError('migration_hash_changed', '已执行迁移文件变化，需单独审核', 409)
                inspector = sa.inspect(conn)
                if any(table.name not in inspector.get_table_names(schema=schema) or
                       {c.name for c in table.c} != {c['name'] for c in inspector.get_columns(table.name, schema=schema)}
                       for table in metadata.tables.values()):
                    raise KnowledgeError('migration_schema_drift', '已登记的知识表结构发生漂移', 409)
                continue
            if any(table.name in sa.inspect(conn).get_table_names(schema=schema) for table in metadata.tables.values()):
                raise KnowledgeError('unregistered_knowledge_tables', '存在未登记迁移的知识表，拒绝自动认领', 409)
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
            conn.execute(sa.text('INSERT INTO kb_schema_migrations(revision,file_sha256) VALUES (:revision,:hash)'),
                         {'revision':name,'hash':checksum})
            completed.append(name)
        return {'schema':schema, 'applied':completed, 'revision':'20261006_knowledge_operations',
                'legacy_alembic_version_unchanged':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--schema',default='second_brain')
    parser.add_argument('--apply',action='store_true',required=True)
    args = parser.parse_args()
    if not args.env_file.is_file(): parser.error('environment file does not exist')
    from dotenv import load_dotenv
    load_dotenv(args.env_file,override=True)
    from services.knowledge.runtime import database_url
    engine = sa.create_engine(database_url(),connect_args={'connect_timeout':3})
    try:
        print(json.dumps(apply(engine,args.schema)))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
