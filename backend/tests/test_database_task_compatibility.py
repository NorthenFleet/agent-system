from sqlalchemy import create_engine, inspect, text

from database import ensure_task_table_ownership_compatibility
from models.v2_models import Base as V2Base


def test_legacy_task_table_is_preserved_before_canonical_ledger_creation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'compat.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE tasks (
                    id VARCHAR(32) PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    active_plan_id VARCHAR(64)
                )
                """
            )
        )
        conn.execute(
            text("INSERT INTO tasks (id,title) VALUES ('legacy-1','Legacy task')")
        )
        conn.execute(
            text(
                """
                CREATE TABLE task_history (
                    id INTEGER PRIMARY KEY,
                    task_id VARCHAR(64)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_task_history_task_id ON task_history(task_id)"))

    assert ensure_task_table_ownership_compatibility(engine) is True
    V2Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert {"tasks", "legacy_plan_tasks", "legacy_incompatible_task_history"}.issubset(
        set(inspector.get_table_names())
    )
    assert "task_id" in {column["name"] for column in inspector.get_columns("tasks")}
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT title FROM legacy_plan_tasks WHERE id='legacy-1'")
        ).scalar_one() == "Legacy task"
