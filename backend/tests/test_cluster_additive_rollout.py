import sqlite3

import pytest

from scripts.apply_cluster_inventory_schema import apply_additive
from scripts import apply_cluster_inventory_schema as rollout


def database(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        db.execute("INSERT INTO alembic_version VALUES ('41670c742a60')")
        db.execute("CREATE TABLE business (id TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO business VALUES ('keep', 'untouched')")


def test_additive_rollout_preserves_revision_and_business_and_is_repeatable(tmp_path):
    path = tmp_path / "app.db"
    database(path)
    receipt = apply_additive(path, tmp_path / "backup.db", "41670c742a60")
    assert receipt["global_revision_unchanged"] == "41670c742a60"
    apply_additive(path, tmp_path / "backup2.db", "41670c742a60")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM business").fetchall() == [("keep", "untouched")]
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [("41670c742a60",)]
        assert db.execute("SELECT count(*) FROM cluster_nodes").fetchone() == (0,)
    with sqlite3.connect(tmp_path / "backup.db") as db:
        assert db.execute("SELECT * FROM business").fetchall() == [("keep", "untouched")]


def test_wrong_revision_or_existing_backup_fails_closed(tmp_path):
    path = tmp_path / "app.db"
    database(path)
    with pytest.raises(ValueError, match="unexpected_alembic_revision"):
        apply_additive(path, tmp_path / "wrong.db", "wrong")
    assert not (tmp_path / "wrong.db").exists()
    with pytest.raises(ValueError, match="backup_must_be_a_new_path"):
        apply_additive(path, path, "41670c742a60")


def test_backup_and_migration_hold_one_writer_lock(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    database(path)
    original = rollout._backup_locked_database
    attempts = []

    def assert_locked(source, backup):
        with sqlite3.connect(source, timeout=0.01) as other:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("INSERT INTO business VALUES ('racing', 'not allowed')")
            attempts.append(True)
        original(source, backup)

    monkeypatch.setattr(rollout, "_backup_locked_database", assert_locked)
    apply_additive(path, tmp_path / "backup.db", "41670c742a60")
    assert attempts == [True]
