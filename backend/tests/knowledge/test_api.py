import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
def api(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/auth.db")
    monkeypatch.setenv("SECOND_BRAIN_ENABLED", "true")
    monkeypatch.setenv("SECOND_BRAIN_WRITE_ENABLED", "true")
    from routers import knowledge_v3 as module
    from services.auth_service import get_current_user
    app = FastAPI(); app.include_router(module.router)
    app.dependency_overrides[module.service] = lambda: svc
    identity = {"sub": "owner", "role": "admin"}
    app.dependency_overrides[get_current_user] = lambda: identity
    return app, module, identity


def test_http_auth_role_gates_and_owner_is_not_client_selected(api):
    app, module, identity = api
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            base = "/api/v3/knowledge"
            response = await client.post(base + "/spaces", json={"name": "研究", "owner_user_id": "victim"}, headers={"Idempotency-Key": "space"})
            assert response.status_code == 422
            response = await client.post(base + "/spaces", json={"name": "研究"}, headers={"Idempotency-Key": "space"})
            assert response.status_code == 201
            sid = response.json()["id"]
            identity["role"] = "viewer"
            denied = await client.post(base + "/spaces", json={"name": "研究"}, headers={"Idempotency-Key": "denied"})
            assert denied.status_code == 403
            identity["sub"] = "other"
            assert (await client.post(base + "/query", json={"space_id": sid, "query": "任务"})).status_code == 404
            app.dependency_overrides.pop(module.get_current_user)
            assert (await client.get(base + "/status")).status_code == 401
    asyncio.run(scenario())


def test_http_write_gate_and_schema_boundaries(api, monkeypatch):
    app, _, _ = api
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            base = "/api/v3/knowledge"
            assert (await client.post(base + "/spaces", json={"name": "missing-key"})).status_code == 422
            monkeypatch.setenv("SECOND_BRAIN_WRITE_ENABLED", "false")
            result = await client.post(base + "/spaces", json={"name": "blocked"}, headers={"Idempotency-Key": "key"})
            assert result.status_code == 503 and result.json()["detail"]["code"] == "write_disabled"
            assert (await client.get(base + "/spaces")).status_code == 200
    asyncio.run(scenario())


def test_http_upload_queued_and_no_candidate_body_in_list(api, svc):
    app, _, _ = api
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            base = "/api/v3/knowledge"
            sid = (await client.post(base + "/spaces", json={"name": "研究"}, headers={"Idempotency-Key": "key"})).json()["id"]
            uploaded = await client.post(base + "/sources", data={"space_id": sid}, files={"file": ("note.md", "任务验收需要证据。".encode(), "text/markdown")}, headers={"Idempotency-Key": "upload"})
            assert uploaded.status_code == 201
            queued = await client.post(base + "/ingestions", json={"space_id": sid, "source_version_id": uploaded.json()["version_id"]}, headers={"Idempotency-Key": "ingest"})
            assert queued.status_code == 202
            svc.compile_job(svc.claim_job())
            listing = (await client.get(base + f"/spaces/{sid}/items/changes")).json()
            assert "payload" not in listing["items"][0]
            assert (await client.get(base + "/change-sets/" + listing["items"][0]["id"])).status_code == 200
    asyncio.run(scenario())


def test_existing_knowledge_reads_work_with_new_feature_disabled(api, monkeypatch, tmp_path):
    app, _, _ = api
    from routers.knowledge import router as legacy_router
    from knowledge_manager import knowledge_manager
    index = tmp_path / "graph-index.json"
    index.write_text(json.dumps({"entities": {}, "relations": [], "stats": {"nodes": 0, "edges": 0}}))
    monkeypatch.setattr(knowledge_manager, "vault_path", tmp_path)
    monkeypatch.setattr(knowledge_manager, "index_path", index)
    from knowledge_manager import _Cache
    monkeypatch.setattr(knowledge_manager, "_cache", _Cache())
    monkeypatch.setenv("SECOND_BRAIN_ENABLED", "false")
    app.include_router(legacy_router)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            assert (await client.get("/api/knowledge/stats")).status_code == 200
            assert (await client.get("/api/knowledge/search", params={"q": "任务"})).status_code == 200
            assert (await client.get("/api/v3/knowledge/spaces")).status_code == 503
    asyncio.run(scenario())


def test_maintenance_api_enforces_role_scope_hash_flow_and_projection_gate(api, svc, monkeypatch):
    from .test_domain import prepare, publish
    app, _, identity = api
    sid, _, initial = prepare(svc)
    publish(svc, initial)
    page = initial['payload']['pages'][1]
    monkeypatch.setenv('SECOND_BRAIN_PROJECTION_ENABLED', 'false')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            base = '/api/v3/knowledge'
            path = base + f'/spaces/{sid}/maintenance/candidates'
            body = {'action': 'rename', 'page_id': page['page_id'], 'base_revision': 1, 'title': '新的标题', 'reason': '核对'}
            identity['role'] = 'viewer'
            assert (await client.post(path, json=body, headers={'Idempotency-Key': 'x'})).status_code == 403
            identity['role'] = 'admin'; identity['sub'] = 'other'
            assert (await client.post(path, json=body, headers={'Idempotency-Key': 'x'})).status_code == 404
            assert (await client.get(base + f'/spaces/{sid}/projection')).status_code == 404
            identity['sub'] = 'owner'
            candidate = await client.post(path, json=body, headers={'Idempotency-Key': 'x'})
            assert candidate.status_code == 201
            assert candidate.json()['status'] == 'awaiting_review'
            assert (await client.get(base + '/pages/' + page['page_id'] + '/history')).status_code == 200
            assert (await client.get(base + f'/spaces/{sid}/projection')).json()['status'] == 'disabled'
            assert (await client.post(base + f'/spaces/{sid}/projection/not-an-event/replay', json={'regenerate': True}, headers={'Idempotency-Key': 'k'})).status_code == 503
            monkeypatch.setenv('SECOND_BRAIN_WRITE_ENABLED', 'false')
            assert (await client.post(path, json=body, headers={'Idempotency-Key': 'new'})).status_code == 503
    asyncio.run(scenario())


def test_shadow_preview_capture_and_reread_have_scope_role_and_revocation_gates(api, svc, monkeypatch):
    from .test_domain import prepare, publish
    app, _, identity = api
    sid, source, initial = prepare(svc)
    publish(svc, initial)
    monkeypatch.setenv('SECOND_BRAIN_CONTEXT_MODE','shadow')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            root='/api/v3/knowledge'; base=root+f'/spaces/{sid}/context'
            body={'project_id':'project-a','query':'任务验收'}
            identity['role']='viewer'
            assert (await client.post(base+'/preview',json=body)).status_code==200
            assert (await client.post(base+'/snapshots',json=body,headers={'Idempotency-Key':'snap'})).status_code==403
            identity['role']='admin'
            assert (await client.post(base+'/preview',json={**body,'owner_user_id':'other'})).status_code==422
            capture=await client.post(base+'/snapshots',json=body,headers={'Idempotency-Key':'snap'})
            assert capture.status_code==201
            snapshot=capture.json(); assert snapshot['items'] and not snapshot['injected']
            identity['sub']='other'
            assert (await client.get(root+'/context/snapshots/'+snapshot['id'],params={'project_id':'project-a'})).status_code==404
            identity['sub']='owner'
            assert (await client.get(root+'/context/snapshots/'+snapshot['id'],params={'project_id':'wrong'})).status_code==404
            item=snapshot['items'][0]
            resolved=await client.post(root+f'/spaces/{sid}/citations/resolve',json={'project_id':'project-a','page_id':item['page_id'],'revision':item['revision'],'block_id':item['block_id']})
            assert resolved.status_code==200
            svc.retract_source('owner',source['version_id'],'revoke')
            assert (await client.get(root+'/context/snapshots/'+snapshot['id'],params={'project_id':'project-a'})).status_code==409
            assert (await client.post(base+'/snapshots',json=body,headers={'Idempotency-Key':'snap'})).status_code==409
            monkeypatch.setenv('SECOND_BRAIN_CONTEXT_MODE','enabled')
            assert (await client.post(base+'/preview',json=body)).status_code==503
    asyncio.run(scenario())


def test_sb4_proposal_scope_roles_idempotency_and_retraction(api, svc, monkeypatch):
    from .test_domain import prepare, publish
    from .test_operations import request, ref
    sid, source, change = prepare(svc); publish(svc,change)
    app, _, identity = api
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            base='/api/v3/knowledge'; headers={'Idempotency-Key':'proposal'}
            body=request(change)
            url=base+f'/spaces/{sid}/memory-proposals'
            assert (await client.post(url,json={**body,'owner_user_id':'victim'},headers=headers)).status_code==422
            identity['role']='viewer'
            assert (await client.post(url,json=body,headers=headers)).status_code==403
            identity['role']='admin'
            first=await client.post(url,json=body,headers=headers)
            assert first.status_code==201 and first.json()['mode']=='export_only'
            assert (await client.post(url,json=body,headers=headers)).json()==first.json()
            assert (await client.post(base+f'/spaces/{sid}/external-imports',json={**ref(),'path':'/etc/passwd'},headers=headers)).status_code==422
            identity['sub']='other'
            assert (await client.get(base+'/memory-proposals/'+first.json()['id'])).status_code==404
            assert (await client.get(base+f'/spaces/{sid}/bridges')).status_code==404
            identity['sub']='owner'
            svc.retract_source('owner',source['version_id'],'withdraw')
            assert (await client.get(base+'/memory-proposals/'+first.json()['id'])).status_code==409
            assert (await client.post(url,json=body,headers=headers)).status_code==409
            maintenance=base+f'/spaces/{sid}/maintenance-runs'
            run=await client.post(maintenance,json={'cadence':'daily'})
            assert run.status_code==201
            assert (await client.post(maintenance,json={'cadence':'daily'})).json()['id']==run.json()['id']
            monkeypatch.setenv('SECOND_BRAIN_WRITE_ENABLED','false')
            assert (await client.post(maintenance,json={})).status_code==503
            assert (await client.get(maintenance)).status_code==200
    asyncio.run(scenario())
