from concurrent.futures import ThreadPoolExecutor
import pytest
from services.command_center_service import CommandCenterService, InvalidMissionTransition


def create(service, key='request-1', owner='u1', **changes):
    return service.create_mission(**{'objective': 'same task', 'requested_by': 'same-name', 'profile_user_id': owner, 'idempotency_key': key, **changes})


def test_retry_reuses_task_and_rejects_different_payload(tmp_path):
    service = CommandCenterService(str(tmp_path/'idempotent.db'))
    first = create(service)
    assert create(service)['id'] == first['id']
    for field, value in [('objective', 'changed'), ('title', 'changed'), ('project_id', 'new-project'), ('context', {'x': 1})]:
        with pytest.raises(InvalidMissionTransition): create(service, **{field: value})
    assert len(service.list_missions(limit=100)) == 1
    assert create(service, owner='u2')['id'] != first['id']
    assert create(service, key='request-2')['id'] != first['id']


def test_concurrent_retry_creates_one_mission(tmp_path):
    service = CommandCenterService(str(tmp_path/'concurrent.db'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: create(service)['id'], range(8)))
    assert len(set(ids)) == 1
    assert len(service.list_missions(limit=100)) == 1


def test_legacy_call_without_key_still_creates_independent_tasks(tmp_path):
    service = CommandCenterService(str(tmp_path/'legacy.db'))
    assert create(service, key='')['id'] != create(service, key='')['id']
