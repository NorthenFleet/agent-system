from scripts.migrate_command_center_sqlite_to_postgres import _checksum


def test_primary_key_checksum_is_order_independent_and_detects_changes():
    first = _checksum([{"id": "b"}, {"id": "a"}])
    second = _checksum([{"id": "a"}, {"id": "b"}])
    changed = _checksum([{"id": "a"}, {"id": "c"}])

    assert first == second
    assert changed != first

