"""Read-only SB0 deployment preflight. Never prints DSNs, credentials or source text."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check():
    import sqlalchemy as sa
    from models.knowledge_schema_v1 import metadata
    from models.knowledge_projection_v2 import metadata as projection_metadata
    from models.knowledge_context_v3 import metadata as context_metadata
    from models.knowledge_operations_v4 import metadata as operations_metadata
    result = {"checks": {}, "ready": False}
    checks = result["checks"]
    url = os.getenv("SECOND_BRAIN_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    try:
        checks["postgresql_configured"] = bool(url and sa.engine.make_url(url).get_backend_name() == "postgresql")
    except sa.exc.ArgumentError:
        checks["postgresql_configured"] = False
    result['database_config_key'] = 'SECOND_BRAIN_DATABASE_URL' if os.getenv('SECOND_BRAIN_DATABASE_URL') else 'DATABASE_URL'
    checks["pdf_parser_available"] = importlib.util.find_spec("pypdf") is not None
    root = Path(os.getenv("SECOND_BRAIN_SOURCE_ROOT", "__not_configured__")).expanduser()
    checks["private_source_root"] = bool(root.is_absolute() and root.is_dir() and not root.is_symlink()
        and root.stat().st_uid == os.getuid() and stat.S_IMODE(root.stat().st_mode) & 0o077 == 0)
    if os.getenv("SECOND_BRAIN_PROJECTION_ENABLED", "false").lower() in {"true", "1", "yes", "on"}:
        projected = Path(os.getenv("SECOND_BRAIN_PROJECTION_ROOT", "__not_configured__")).expanduser()
        checks["private_projection_root"] = bool(projected.is_absolute() and projected.is_dir() and not projected.is_symlink()
            and projected.stat().st_uid == os.getuid() and stat.S_IMODE(projected.stat().st_mode) & 0o077 == 0)
        checks["separate_projection_root"] = projected.resolve() != root.resolve() and projected.resolve() not in root.resolve().parents and root.resolve() not in projected.resolve().parents
        from knowledge_manager import knowledge_manager
        vault = knowledge_manager.vault_path.resolve()
        checks["projection_outside_legacy_scan"] = projected.resolve() != vault and projected.resolve() not in vault.parents and vault not in projected.resolve().parents
    checks["knowledge_schema"] = False
    checks["workrun_schema"] = False
    if checks["postgresql_configured"]:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                inspector = sa.inspect(conn)
                existing = set(inspector.get_table_names())
                checks["knowledge_schema"] = all(table.name in existing and
                    {c.name for c in table.columns} == {c["name"] for c in inspector.get_columns(table.name)}
                    for table in [*metadata.tables.values(), *projection_metadata.tables.values(), *context_metadata.tables.values(), *operations_metadata.tables.values()])
            # WorkRun may have a separate authority, so inspect its configured PG independently.
            wr_url = os.getenv("WORK_RUN_DATABASE_URL", "")
            if wr_url and sa.engine.make_url(wr_url).get_backend_name() == "postgresql":
                ledger = sa.create_engine(wr_url, connect_args={"connect_timeout": 3})
                try:
                    with ledger.connect() as conn:
                        names = set(sa.inspect(conn).get_table_names())
                        checks["workrun_schema"] = {"work_runs", "work_run_events", "work_artifacts"} <= names
                finally:
                    ledger.dispose()
            else:
                checks["workrun_schema"] = False
                result["workrun_note"] = "Existing SQLite ledger requires a separately documented compatibility gate; no implicit migration."
        except Exception:
            result["database_error"] = "authority_unavailable_or_schema_mismatch"
        finally:
            engine.dispose()
    result["ready"] = all(checks.values())
    result["feature_enabled"] = os.getenv("SECOND_BRAIN_ENABLED", "false")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            parser.error("environment file does not exist")
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ready"] else 1)
