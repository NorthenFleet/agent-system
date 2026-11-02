"""HTTP download must revalidate bytes after artifact registration."""
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize('mutation', ['changed', 'missing', 'symlink'])
def test_download_rechecks_registered_artifact(tmp_path, monkeypatch, mutation):
    from routers import command_center_router as router

    delivery = tmp_path / 'delivery'
    delivery.mkdir()
    artifact_file = delivery / 'receipt.json'
    original = b'{"verified":true}'
    artifact_file.write_bytes(original)
    artifact = {'id': 'receipt', 'uri': str(artifact_file),
                'content_hash': hashlib.sha256(original).hexdigest()}
    monkeypatch.setenv('COMMAND_CENTER_ARTIFACT_ROOTS', str(delivery))
    scopes = []

    def mission(mid, **kwargs):
        assert mid == 'owned'
        scopes.append(kwargs['owner_user_id'])
        return {'id': mid, 'artifacts': [artifact]}

    monkeypatch.setattr(router.command_center_service, 'get_mission', mission)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.get_current_user] = lambda: {'sub': '999', 'role': 'user'}
    url = '/api/v3/command-center/missions/owned/artifacts/receipt/download'
    with TestClient(app) as client:
        good = client.get(url)
        assert good.status_code == 200
        assert good.content == original
        assert good.headers['cache-control'] == 'no-store'
        assert good.headers['x-content-type-options'] == 'nosniff'
        assert 'attachment' in good.headers['content-disposition']
        artifact_file.rename(delivery / 'receipt-original.json')
        if mutation == 'changed':
            artifact_file.write_bytes(b'altered-private-content')
        elif mutation == 'symlink':
            secret = tmp_path / 'private.json'
            secret.write_bytes(b'altered-private-content')
            artifact_file.symlink_to(secret)
        rejected = client.get(url)
        assert rejected.status_code == 409
        assert b'altered-private-content' not in rejected.content
        assert client.get(url.replace('/receipt/', '/unregistered/')).status_code == 404
    assert scopes == ['999', '999', '999']
