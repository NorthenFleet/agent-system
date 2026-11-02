import base64
import json
import os
import plistlib
import struct
import zlib
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.writing_workspace as writing_router
import services.genoffice_readonly_service as genoffice_service
from services.auth_service import get_current_user
from services.genoffice_readonly_service import (
    GenOfficeProof,
    GenOfficeMcpClient,
    GenOfficeProtocolError,
    GenOfficeReadOnlyService,
    GenOfficeSettings,
    GenOfficeSource,
    GenOfficeToolFailure,
    GenOfficeUnavailable,
    MAX_PNG_DIMENSION,
    MAX_PNG_PIXELS,
    MAX_PUBLIC_TEXT_CHARS,
    PNG_IHDR_TOTAL_BYTES,
    PNG_SIGNATURE,
    _public_check,
    _public_read,
)


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZKMcAAAAASUVORK5CYII="
)


def _png_ihdr(width: int, height: int, *, bit_depth: int = 8, color_type: int = 6) -> bytes:
    payload = struct.pack(
        ">IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        0,
        0,
        0,
    )
    chunk = b"IHDR" + payload
    return (
        PNG_SIGNATURE
        + struct.pack(">I", len(payload))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class _StaticHttpClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def build_request(self, method: str, url: str, **kwargs):
        assert method == "GET"
        assert url.endswith("/proof.png")
        return httpx.Request(method, url, **kwargs)

    def send(self, request: httpx.Request, *, stream: bool = False):
        assert stream is True
        self.response._request = request  # noqa: SLF001 - mirrors httpx.Client response binding
        return self.response

    def close(self) -> None:
        return None


class _TrackingByteStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0

    def __iter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    def close(self) -> None:
        return None


class FakeDocuments:
    def __init__(self, root: Path, *, kind: str = "rich_text") -> None:
        self.root = root
        self.kind = kind

    def get_document(self, _project, _document_id):
        return {"id": "document-1", "kind": self.kind, "title": "测试正文"}

    def _document_root(self, _project, _document_id):
        return self.root


class FakeClient:
    def __init__(self, tools=None, *, mcp_version="0.10.0") -> None:
        self.mcp_version = mcp_version
        self.tools = set(tools or {"docs_read", "docs_check", "render", "docs_apply"})
        self.uploads = []
        self.calls = []
        self.downloads = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def list_tools(self):
        return self.tools

    def upload_docx(self, source):
        self.uploads.append(source)
        return "http://127.0.0.1:3094/files/0123456789abcdef/original.docx"

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "docs_read":
            return {
                "status": "ok",
                "summary": "original.docx: 3 blocks",
                "detail": {"blocks": 3, "range": "0-2", "items": [{"index": 0, "text": "标题"}]},
            }
        if name == "docs_check":
            return {
                "status": "ok",
                "summary": "original.docx: 1 issue(s)",
                "detail": {
                    "counts": {"error": 0, "warning": 1, "info": 0},
                    "issues": [{"id": "W1", "level": "warning", "code": "stale_toc", "message": "目录过期"}],
                },
            }
        if name == "render":
            return {
                "status": "ok",
                "summary": "rendered page one",
                "detail": {
                    "files": [{"page": 1, "url": "http://127.0.0.1:3094/files/fedcba9876543210/original-01.png"}]
                },
            }
        raise AssertionError(name)

    def download_png(self, url, *, max_bytes):
        self.downloads.append((url, max_bytes))
        return PNG


def _write_docx(root: Path) -> Path:
    source = root / "source" / "original.docx"
    source.parent.mkdir(parents=True)
    with ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<w:document />")
    return source


def _settings(
    token_file: Path,
    *,
    enabled=True,
    release_version="0.10.1038",
    channel="stable",
    bundle_id="com.genoffice.app",
) -> GenOfficeSettings:
    bundle = token_file.parent / "GenOffice.app"
    binary = bundle / "Contents" / "Resources" / "cli" / "genoffice"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch(exist_ok=True)
    os.chmod(binary, 0o700)
    info_path = bundle / "Contents" / "Info.plist"
    with info_path.open("wb") as handle:
        plistlib.dump(
            {
                "CFBundleShortVersionString": release_version,
                "CFBundleIdentifier": bundle_id,
            },
            handle,
        )
    sidecar_home = token_file.parent / "genoffice-sidecar-home"
    sidecar_home.mkdir(exist_ok=True)
    os.chmod(sidecar_home, 0o700)
    return GenOfficeSettings(
        enabled=enabled,
        mcp_url="http://127.0.0.1:3094/mcp",
        token_file=token_file,
        binary_path=binary,
        channel=channel,
        min_supported_version="0.10.1038",
        max_tested_version="0.10.1038",
        min_supported_mcp_version="0.10.0",
        max_tested_mcp_version="0.10.0",
        connect_timeout_seconds=1,
        tool_timeout_seconds=5,
        max_input_bytes=1024 * 1024,
        max_render_bytes=1024 * 1024,
        sidecar_home=sidecar_home,
    )


def _download_client(tmp_path: Path, response: httpx.Response) -> GenOfficeMcpClient:
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    client = GenOfficeMcpClient(_settings(token), "x" * 64)
    client._http = _StaticHttpClient(response)  # noqa: SLF001 - focused response validation test
    return client


@pytest.fixture()
def readonly_service(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    root = tmp_path / "document-1"
    _write_docx(root)
    client = FakeClient()
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(root),
        settings_factory=lambda: _settings(token),
        client_factory=lambda _settings, _token: client,
    )
    return service, client


def test_disabled_status_never_connects_or_claims_write_capability(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    calls = []
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(tmp_path),
        settings_factory=lambda: _settings(token, enabled=False),
        client_factory=lambda *_args: calls.append(True),
    )

    status = service.status()

    assert status["mode"] == "disabled"
    assert status["reachable"] is False
    assert status["capabilities"] == {
        "docs_read": False,
        "docs_check": False,
        "render": False,
        "docs_apply": False,
        "visible_editor": False,
    }
    assert calls == []


def test_status_exposes_known_release_and_mcp_versions_without_write_capability(readonly_service):
    service, _client = readonly_service

    status = service.status()

    assert status["mode"] == "read_only"
    assert status["version"] == "0.10.1038"
    assert status["mcp_version"] == "0.10.0"
    assert status["pilot_gate"] == "limited"
    assert status["version_gate"] == "tested"
    assert status["release_version_gate"] == "tested"
    assert status["mcp_version_gate"] == "tested"
    assert status["capabilities"]["docs_read"] is True
    assert status["capabilities"]["docs_apply"] is False
    assert status["capabilities"]["visible_editor"] is False


def test_check_uploads_only_registered_docx_and_calls_only_allowlist(readonly_service):
    service, client = readonly_service

    report = service.check({"id": "project-1"}, "document-1")

    assert [name for name, _arguments in client.calls] == ["docs_read", "docs_check"]
    assert client.calls[0][1] == {
        "file": "http://127.0.0.1:3094/files/0123456789abcdef/original.docx",
        "range": "0",
        "max_chars": 200,
    }
    assert client.uploads[0].name == "original.docx"
    assert report["source"]["read_only"] is True
    assert report["source"]["authority"] == "imported_source_only"
    assert report["read"]["blocks"] == 3
    assert report["check"]["issues"] == [
        {"id": "W1", "code": "stale_toc", "level": "warning", "message": "目录过期"}
    ]
    assert "docs_apply" not in [name for name, _arguments in client.calls]


def test_proof_renders_page_one_only_and_never_persists_a_candidate(readonly_service):
    service, client = readonly_service

    proof = service.proof({"id": "project-1"}, "document-1")

    assert proof.content == PNG
    assert proof.media_type == "image/png"
    assert proof.filename == "office-proof-page-1.png"
    assert client.calls == [("render", {"file": "http://127.0.0.1:3094/files/0123456789abcdef/original.docx", "page": 1, "scale": 1})]
    assert client.downloads[0][0].endswith("/original-01.png")


def test_near_budget_render_failure_has_a_safe_timeout_message(readonly_service, monkeypatch):
    service, client = readonly_service
    original_call = client.call_tool

    def fail_render(name, arguments):
        if name == "render":
            client.calls.append((name, arguments))
            raise GenOfficeToolFailure("render", "conversion_failed")
        return original_call(name, arguments)

    moments = iter((100.0, 280.0))
    monkeypatch.setattr(client, "call_tool", fail_render)
    monkeypatch.setattr(genoffice_service, "monotonic", lambda: next(moments))

    with pytest.raises(GenOfficeUnavailable, match="内部 180 秒渲染预算"):
        service.proof({"id": "project-1"}, "document-1")


def test_cleanup_removes_only_the_isolated_renderer_source_copy(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    settings = _settings(token)
    source_sha = "a" * 64
    originals = settings.sidecar_home / "electron-user-data" / "originals"
    originals.mkdir(parents=True)
    original = originals / f"{source_sha}.docx"
    original.write_bytes(b"private source")
    os.chmod(original, 0o600)

    settings.cleanup_headless_source(source_sha)

    assert not original.exists()


def test_unsupported_mcp_version_blocks_check_and_proof(readonly_service):
    service, client = readonly_service
    client.mcp_version = "0.9.9"

    status = service.status()

    assert status["mode"] == "unavailable"
    assert status["version"] == "0.10.1038"
    assert status["mcp_version"] == "0.9.9"
    assert status["version_gate"] == "unsupported"
    assert status["release_version_gate"] == "tested"
    assert status["mcp_version_gate"] == "unsupported"
    with pytest.raises(GenOfficeUnavailable, match="不在已支持范围"):
        service.check({"id": "project-1"}, "document-1")
    with pytest.raises(GenOfficeUnavailable, match="不在已支持范围"):
        service.proof({"id": "project-1"}, "document-1")
    assert client.uploads == []
    assert client.calls == []


def test_unverified_mcp_version_stays_read_only(readonly_service):
    service, client = readonly_service
    client.mcp_version = "0.10.1"

    status = service.status()
    report = service.check({"id": "project-1"}, "document-1")

    assert status["mode"] == "read_only"
    assert status["version_gate"] == "unverified"
    assert status["mcp_version_gate"] == "unverified"
    assert report["engine"]["version"] == "0.10.1038"
    assert report["engine"]["mcp_version"] == "0.10.1"
    assert report["engine"]["version_gate"] == "unverified"


def test_unverified_release_version_stays_read_only(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    root = tmp_path / "document-1"
    _write_docx(root)
    client = FakeClient()
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(root),
        settings_factory=lambda: _settings(token, release_version="0.10.1039"),
        client_factory=lambda _settings, _token: client,
    )

    status = service.status()
    report = service.check({"id": "project-1"}, "document-1")

    assert status["mode"] == "read_only"
    assert status["version"] == "0.10.1039"
    assert status["release_version_gate"] == "unverified"
    assert status["mcp_version_gate"] == "tested"
    assert report["engine"]["version"] == "0.10.1039"
    assert report["engine"]["version_gate"] == "unverified"


def test_invalid_or_missing_source_is_rejected_without_contacting_sidecar(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    client = FakeClient()
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(tmp_path / "missing"),
        settings_factory=lambda: _settings(token),
        client_factory=lambda _settings, _token: client,
    )

    with pytest.raises(GenOfficeUnavailable, match="已导入 Word 原件"):
        service.check({"id": "project-1"}, "document-1")
    assert client.uploads == []


def test_insecure_token_file_stays_unavailable(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o644)
    client = FakeClient()
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(tmp_path),
        settings_factory=lambda: _settings(token),
        client_factory=lambda _settings, _token: client,
    )

    status = service.status()

    assert status["mode"] == "unavailable"
    assert "权限不安全" in status["reason"]
    assert client.uploads == []


@pytest.mark.parametrize(
    ("settings_kwargs", "reason"),
    [
        ({"channel": "beta"}, "stable 渠道"),
        ({"bundle_id": "com.example.repackaged"}, "应用标识不匹配"),
    ],
)
def test_unapproved_channel_or_bundle_identity_never_connects(tmp_path, settings_kwargs, reason):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    calls = []
    service = GenOfficeReadOnlyService(
        documents=FakeDocuments(tmp_path),
        settings_factory=lambda: _settings(token, **settings_kwargs),
        client_factory=lambda *_args: calls.append(True),
    )

    status = service.status()

    assert status["mode"] == "unavailable"
    assert reason in status["reason"]
    assert calls == []


def test_raw_mcp_client_uses_authenticated_session_and_sse_responses(tmp_path):
    token = tmp_path / "genoffice.token"
    token.write_text("x" * 64, encoding="utf-8")
    os.chmod(token, 0o600)
    requests = []

    def reply(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {'x' * 64}"
        if request.method == "PUT":
            return httpx.Response(
                201,
                json={"url": "http://127.0.0.1:3094/files/0123456789abcdef/original.docx"},
            )
        if request.method == "GET":
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        if request.method == "DELETE":
            assert request.headers["mcp-session-id"] == "session-1"
            return httpx.Response(204)
        payload = json.loads(request.content)
        method = payload["method"]
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"version": "0.10.0"}}},
                headers={"mcp-session-id": "session-1"},
            )
        assert request.headers["mcp-session-id"] == "session-1"
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            schemas = {
                "docs_read": {
                    "properties": {"file": {}, "range": {}, "max_chars": {}},
                    "required": ["file"],
                },
                "docs_check": {"properties": {"file": {}}, "required": ["file"]},
                "render": {
                    "properties": {"file": {}, "page": {}, "scale": {}},
                    "required": ["file"],
                },
            }
            body = {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "tools": [
                        {
                            "name": name,
                            "inputSchema": schemas.get(name, {"properties": {}, "required": []}),
                            "annotations": {"readOnlyHint": name != "docs_apply"},
                        }
                        for name in ("docs_read", "docs_check", "render", "docs_apply")
                    ]
                },
            }
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(body)}\n\n", headers={"content-type": "text/event-stream"})
        if method == "tools/call":
            assert payload["params"]["name"] == "docs_read"
            envelope = {
                "status": "ok",
                "command": "docs",
                "summary": "original.docx: 1 blocks",
                "detail": {"blocks": 1},
            }
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": payload["id"], "result": {"content": [{"type": "text", "text": json.dumps(envelope)}]}},
            )
        raise AssertionError(method)

    settings = _settings(token)
    factory_kwargs = {}

    def factory(**kwargs):
        factory_kwargs.update(kwargs)
        return httpx.Client(transport=httpx.MockTransport(reply), **kwargs)

    source = GenOfficeSource(data=b"docx", sha256="a" * 64, name="original.docx")
    with GenOfficeMcpClient(settings, "x" * 64, http_client_factory=factory) as client:
        assert client.mcp_version == "0.10.0"
        assert {"docs_read", "docs_check", "render"}.issubset(client.list_tools())
        uploaded = client.upload_docx(source)
        assert uploaded.endswith("/original.docx")
        assert client.call_tool("docs_read", {"file": uploaded})["detail"]["blocks"] == 1
        with pytest.raises(GenOfficeProtocolError, match="未授权"):
            client.call_tool("docs_apply", {"file": uploaded, "ops": []})
        assert client.download_png("http://127.0.0.1:3094/files/0123456789abcdef/proof.png", max_bytes=1024) == PNG

    assert any(request.method == "DELETE" for request in requests)
    assert factory_kwargs["trust_env"] is False
    assert factory_kwargs["follow_redirects"] is False


def test_g1_tool_contract_fingerprint_ignores_prose_and_order_but_detects_schema_change():
    baseline = {
        "docs_read": {
            "inputSchema": {
                "description": "read a document",
                "properties": {"file": {"type": "string"}, "range": {}, "max_chars": {}},
                "required": ["range", "file"],
            },
            "annotations": {"readOnlyHint": True},
        },
        "docs_check": {
            "inputSchema": {"properties": {"file": {"type": "string"}}, "required": ["file"]},
            "annotations": {"readOnlyHint": True},
        },
        "render": {
            "inputSchema": {
                "properties": {"file": {"type": "string"}, "page": {"type": "number"}, "scale": {}},
                "required": ["file", "page"],
            },
            "annotations": {"readOnlyHint": True},
        },
    }
    presentation_only = {
        **baseline,
        "docs_read": {
            "inputSchema": {
                "title": "new title",
                "properties": {"max_chars": {}, "range": {}, "file": {"description": "path", "type": "string"}},
                "required": ["file", "range"],
            },
            "annotations": {"readOnlyHint": True},
        },
    }
    changed = {
        **baseline,
        "render": {
            "inputSchema": {
                "properties": {"file": {"type": "string"}, "page": {"type": "string"}, "scale": {}},
                "required": ["file", "page"],
            },
            "annotations": {"readOnlyHint": True},
        },
    }

    fingerprint = genoffice_service._g1_tool_contract_sha256(baseline)

    assert fingerprint == genoffice_service._g1_tool_contract_sha256(presentation_only)
    assert fingerprint != genoffice_service._g1_tool_contract_sha256(changed)


def test_download_png_rejects_malformed_ihdr_before_reading_later_chunks(tmp_path):
    malformed_header = bytearray(_png_ihdr(1, 1)[:PNG_IHDR_TOTAL_BYTES])
    malformed_header[-1] ^= 0x01
    stream = _TrackingByteStream([bytes(malformed_header), b"browser-must-not-receive-this"])
    response = httpx.Response(200, stream=stream, headers={"content-type": "image/png"})
    client = _download_client(tmp_path, response)

    with pytest.raises(GenOfficeProtocolError, match="输出格式无效"):
        client.download_png("http://127.0.0.1:3094/files/0123456789abcdef/proof.png", max_bytes=1024)

    assert stream.yielded == 1


def test_download_png_rejects_oversized_png_dimensions(tmp_path):
    response = httpx.Response(
        200,
        content=_png_ihdr(MAX_PNG_DIMENSION + 1, 1),
        headers={"content-type": "image/png"},
    )
    client = _download_client(tmp_path, response)

    with pytest.raises(GenOfficeUnavailable, match="尺寸超过安全限制"):
        client.download_png("http://127.0.0.1:3094/files/0123456789abcdef/proof.png", max_bytes=1024)


def test_download_png_rejects_oversized_png_pixel_count(tmp_path):
    height = MAX_PNG_PIXELS // MAX_PNG_DIMENSION + 1
    assert height <= MAX_PNG_DIMENSION
    response = httpx.Response(
        200,
        content=_png_ihdr(MAX_PNG_DIMENSION, height),
        headers={"content-type": "image/png"},
    )
    client = _download_client(tmp_path, response)

    with pytest.raises(GenOfficeUnavailable, match="尺寸超过安全限制"):
        client.download_png("http://127.0.0.1:3094/files/0123456789abcdef/proof.png", max_bytes=1024)


def test_download_png_enforces_stream_limit_without_content_length(tmp_path):
    valid_header = _png_ihdr(1, 1)[:PNG_IHDR_TOTAL_BYTES]
    stream = _TrackingByteStream([valid_header, b"overflow"])
    response = httpx.Response(200, stream=stream, headers={"content-type": "image/png"})
    client = _download_client(tmp_path, response)

    with pytest.raises(GenOfficeUnavailable, match="图片超过安全大小限制"):
        client.download_png(
            "http://127.0.0.1:3094/files/0123456789abcdef/proof.png",
            max_bytes=len(valid_header) + 1,
        )

    assert stream.yielded == 2


def test_mcp_response_enforces_stream_limit_without_content_length(tmp_path):
    stream = _TrackingByteStream([b"ok", b"overflow"])
    response = httpx.Response(200, stream=stream)
    client = _download_client(tmp_path, response)

    with pytest.raises(GenOfficeUnavailable, match="MCP 响应超过安全大小限制"):
        client._request(  # noqa: SLF001 - verifies the transport boundary itself
            "GET",
            "http://127.0.0.1:3094/files/0123456789abcdef/proof.png",
            max_bytes=2,
        )

    assert stream.yielded == 2


def test_public_read_and_check_values_are_bounded():
    oversized = "x" * (MAX_PUBLIC_TEXT_CHARS + 100)
    read = _public_read(
        {
            "summary": oversized,
            "detail": {
                "blocks": 1,
                "range": oversized,
                "items": [{"text": oversized, "nested": [oversized] * 60}],
            },
        }
    )
    check = _public_check(
        {
            "summary": oversized,
            "detail": {
                "counts": {"error": 0, "warning": 1, "info": 0},
                "issues": [{"message": oversized, "context": {"text": oversized}}],
            },
        }
    )

    assert len(read["summary"]) == 1000
    assert len(read["range"]) == 128
    assert len(read["items"][0]["text"]) == MAX_PUBLIC_TEXT_CHARS
    assert len(read["items"][0]["nested"]) == 50
    assert len(check["issues"][0]["message"]) == MAX_PUBLIC_TEXT_CHARS
    assert len(check["issues"][0]["context"]["text"]) == MAX_PUBLIC_TEXT_CHARS


def test_router_exposes_only_status_check_and_png_proof(monkeypatch):
    class RouterService:
        def status(self):
            return {"mode": "read_only", "capabilities": {"docs_apply": False}}

        def check(self, project, document_id):
            assert project["id"] == "project-1"
            assert document_id == "document-1"
            return {"schema": "openclaw.genoffice-readonly-check.v1"}

        def proof(self, _project, _document_id):
            return GenOfficeProof(PNG, "image/png", "office-proof-page-1.png", {}, "0.10.1038")

    monkeypatch.setattr(writing_router, "genoffice_readonly_service", RouterService())
    monkeypatch.setattr(writing_router, "_project", lambda project_id: {"id": project_id})
    app = FastAPI()
    app.include_router(writing_router.router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-1", "role": "admin"}
    client = TestClient(app)

    status = client.get("/api/v3/writing/genoffice/status")
    check = client.post("/api/v3/writing/projects/project-1/documents/document-1/genoffice/check")
    proof = client.get("/api/v3/writing/projects/project-1/documents/document-1/genoffice/proof.png")

    assert status.status_code == 200
    assert status.json()["capabilities"]["docs_apply"] is False
    assert check.status_code == 200
    assert proof.status_code == 200
    assert proof.headers["content-type"].startswith("image/png")
    assert proof.headers["cache-control"] == "no-store"
    assert proof.content == PNG

    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-2", "role": "user"}
    assert client.get("/api/v3/writing/genoffice/status").status_code == 403
    assert client.post("/api/v3/writing/projects/project-1/documents/document-1/genoffice/check").status_code == 403
    assert client.get("/api/v3/writing/projects/project-1/documents/document-1/genoffice/proof.png").status_code == 403
