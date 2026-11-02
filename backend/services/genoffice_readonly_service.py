"""Bounded GenOffice Phase G1 adapter.

The service deliberately speaks only the small, read-only part of GenOffice's
Streamable HTTP MCP surface.  It never grants the Sidecar a project path: an
already-registered DOCX is uploaded to GenOffice's per-session file store and
the resulting PNG is downloaded before that MCP session is closed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import plistlib
import re
import stat
import threading
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import quote, urlparse
from zipfile import BadZipFile, ZipFile

import httpx

from services.document_workspace_service import DocumentWorkspaceError
from services.multi_document_service import multi_document_service


LOGGER = logging.getLogger(__name__)
ALLOWED_TOOLS = frozenset({"docs_read", "docs_check", "render"})
REQUIRED_TOOLS = frozenset({"docs_read", "docs_check", "render"})
TOOL_COMMANDS = {"docs_read": "docs", "docs_check": "docs", "render": "render"}
REQUIRED_TOOL_PROPERTIES = {
    "docs_read": frozenset({"file", "range", "max_chars"}),
    "docs_check": frozenset({"file"}),
    "render": frozenset({"file", "page", "scale"}),
}
# Tool descriptions and array ordering are presentation details.  The G1.1
# compatibility report fingerprints only the executable part of the pinned
# read-only contract, so an upstream wording edit does not look like a
# protocol migration while a schema change does.
NON_SEMANTIC_TOOL_SCHEMA_KEYS = frozenset({"$comment", "default", "description", "examples", "title"})
UNORDERED_TOOL_SCHEMA_ARRAY_KEYS = frozenset({"allOf", "anyOf", "enum", "oneOf", "required", "type"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG_MIME = "image/png"
EXPECTED_GENOFFICE_BUNDLE_ID = "com.genoffice.app"
SUPPORTED_GENOFFICE_CHANNEL = "stable"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IHDR_LENGTH = 13
PNG_IHDR_TOTAL_BYTES = len(PNG_SIGNATURE) + 4 + 4 + PNG_IHDR_LENGTH + 4
# A render is displayed directly by the browser.  Bounds apply to the decoded
# image rather than its compressed transfer size, which prevents a small PNG
# from requesting an unbounded client-side image allocation.
MAX_PNG_DIMENSION = 8_192
MAX_PNG_PIXELS = 32 * 1024 * 1024
PNG_BIT_DEPTHS_BY_COLOR_TYPE = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}
MAX_DOCX_ENTRIES = 10_000
MAX_DOCX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
# MCP envelopes are control-plane data only.  Bound them independently from
# the DOCX upload and PNG download limits so an exceptional converter result
# cannot make the 3021 worker buffer an unbounded JSON/SSE response.
MAX_MCP_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_TEXT_CHARS = 2_000
MAX_PUBLIC_CONTAINER_ITEMS = 50
MAX_PUBLIC_CONTAINER_KEYS = 30
MAX_PUBLIC_NESTING = 3
# v0.10.1038 has two internal 180-second headless-export budgets.  Do not
# treat a near-boundary conversion failure as a generic document error.
RENDER_TIMEOUT_SIGNAL_SECONDS = 175.0


class GenOfficeReadOnlyError(DocumentWorkspaceError):
    """A safe, user-facing failure from the G1 adapter."""


class GenOfficeUnavailable(GenOfficeReadOnlyError):
    """The integration is disabled, misconfigured, or cannot be reached."""


class GenOfficeBusy(GenOfficeReadOnlyError):
    """The single read-only rendering slot is occupied."""


class GenOfficeProtocolError(GenOfficeUnavailable):
    """The Sidecar did not honor the expected, pinned MCP contract."""


class GenOfficeToolFailure(GenOfficeProtocolError):
    """A safe, structured vendor tool error with no document detail."""

    def __init__(self, tool_name: str, error_code: str) -> None:
        self.tool_name = tool_name
        self.error_code = error_code
        super().__init__(f"GenOffice 只读调用失败（{error_code}）")


@dataclass(frozen=True)
class GenOfficeSettings:
    enabled: bool
    mcp_url: str
    token_file: Path | None
    binary_path: Path
    channel: str
    min_supported_version: str
    max_tested_version: str
    min_supported_mcp_version: str
    max_tested_mcp_version: str
    connect_timeout_seconds: float
    tool_timeout_seconds: float
    max_input_bytes: int
    max_render_bytes: int
    sidecar_home: Path | None = None
    pilot_gate: str = "limited"

    @classmethod
    def from_env(cls) -> "GenOfficeSettings":
        return cls(
            enabled=_truthy(os.environ.get("GENOFFICE_INTEGRATION_ENABLED")),
            mcp_url=str(os.environ.get("GENOFFICE_MCP_URL") or "http://127.0.0.1:3094/mcp"),
            token_file=_optional_path(os.environ.get("GENOFFICE_MCP_TOKEN_FILE")),
            binary_path=Path(
                os.environ.get("GENOFFICE_BINARY_PATH")
                or "/Applications/GenOffice.app/Contents/Resources/cli/genoffice"
            ),
            channel=str(os.environ.get("GENOFFICE_REQUIRED_CHANNEL") or "stable"),
            min_supported_version=str(os.environ.get("GENOFFICE_MIN_SUPPORTED_VERSION") or "0.10.1038"),
            max_tested_version=str(os.environ.get("GENOFFICE_MAX_TESTED_VERSION") or "0.10.1038"),
            min_supported_mcp_version=str(os.environ.get("GENOFFICE_MIN_SUPPORTED_MCP_VERSION") or "0.10.0"),
            max_tested_mcp_version=str(os.environ.get("GENOFFICE_MAX_TESTED_MCP_VERSION") or "0.10.0"),
            connect_timeout_seconds=_positive_float("GENOFFICE_CONNECT_TIMEOUT_SECONDS", 5.0),
            tool_timeout_seconds=_positive_float("GENOFFICE_TOOL_TIMEOUT_SECONDS", 240.0),
            max_input_bytes=_positive_int("GENOFFICE_MAX_INPUT_BYTES", 64 * 1024 * 1024),
            max_render_bytes=_positive_int("GENOFFICE_MAX_RENDER_BYTES", 24 * 1024 * 1024),
            sidecar_home=_optional_path(os.environ.get("GENOFFICE_SIDECAR_HOME")),
            pilot_gate=_pilot_gate(os.environ.get("GENOFFICE_G1_PILOT_GATE")),
        )

    def validate_url(self) -> None:
        parsed = urlparse(self.mcp_url)
        if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.path.rstrip("/") != "/mcp":
            raise GenOfficeUnavailable("GenOffice Sidecar 地址必须是本机 localhost MCP 地址")

    def validate_channel(self) -> None:
        if self.channel.strip().lower() != SUPPORTED_GENOFFICE_CHANNEL:
            raise GenOfficeUnavailable("Phase G1 仅允许官方 stable 渠道的 GenOffice")

    def load_token(self) -> str:
        if not self.token_file:
            raise GenOfficeUnavailable("GenOffice 认证令牌文件尚未配置")
        if self.token_file.is_symlink():
            raise GenOfficeUnavailable("GenOffice 认证令牌文件权限不安全")
        try:
            metadata = self.token_file.stat()
        except OSError as exc:
            raise GenOfficeUnavailable("GenOffice 认证令牌文件不可读") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise GenOfficeUnavailable("GenOffice 认证令牌文件权限不安全")
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise GenOfficeUnavailable("GenOffice 认证令牌文件不可读") from exc
        if len(token) < 32:
            raise GenOfficeUnavailable("GenOffice 认证令牌无效")
        return token

    def release_version(self) -> str:
        """Read the installed app release, not the bundled MCP server version."""

        bundle = next((parent for parent in self.binary_path.parents if parent.suffix == ".app"), None)
        if not bundle:
            raise GenOfficeUnavailable("官方 GenOffice 应用版本信息不可读")
        info_path = bundle / "Contents" / "Info.plist"
        try:
            with info_path.open("rb") as handle:
                metadata = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException) as exc:
            raise GenOfficeUnavailable("官方 GenOffice 应用版本信息不可读") from exc
        if not isinstance(metadata, Mapping) or metadata.get("CFBundleIdentifier") != EXPECTED_GENOFFICE_BUNDLE_ID:
            raise GenOfficeUnavailable("官方 GenOffice 应用标识不匹配")
        version = str(metadata.get("CFBundleShortVersionString") or "").strip()
        if not _version_tuple(version):
            raise GenOfficeUnavailable("官方 GenOffice 应用版本信息无效")
        return version

    def validate_sidecar_home(self) -> Path:
        if not self.sidecar_home or self.sidecar_home.is_symlink():
            raise GenOfficeUnavailable("GenOffice 私有运行目录尚未配置")
        try:
            metadata = self.sidecar_home.stat()
        except OSError as exc:
            raise GenOfficeUnavailable("GenOffice 私有运行目录不可用") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise GenOfficeUnavailable("GenOffice 私有运行目录权限不安全")
        return self.sidecar_home

    def cleanup_headless_source(self, source_sha256: str) -> None:
        """Remove the renderer's private source copy after a page proof."""

        if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
            raise GenOfficeUnavailable("GenOffice 临时副本标识无效")
        home = self.validate_sidecar_home()
        originals = home / "electron-user-data" / "originals"
        if not originals.exists():
            return
        if originals.is_symlink():
            raise GenOfficeUnavailable("GenOffice 临时副本目录权限不安全")
        try:
            root = originals.resolve(strict=True)
            target = originals / f"{source_sha256}.docx"
            if not target.exists():
                return
            if target.is_symlink():
                raise GenOfficeUnavailable("GenOffice 临时副本权限不安全")
            resolved = target.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file():
                raise GenOfficeUnavailable("GenOffice 临时副本权限不安全")
            resolved.unlink()
        except GenOfficeUnavailable:
            raise
        except (OSError, ValueError) as exc:
            raise GenOfficeUnavailable("GenOffice 临时副本清理失败") from exc


@dataclass(frozen=True)
class GenOfficeSource:
    data: bytes
    sha256: str
    name: str
    source_kind: str = "imported_original_docx"

    def public(self) -> dict[str, Any]:
        return {
            "kind": self.source_kind,
            "sha256": self.sha256,
            "read_only": True,
            "authority": "imported_source_only",
            "notice": "校样仅读取已导入的 Word 原件；不会写回正文或源文件，且原件可能早于当前结构化正文。",
        }


@dataclass(frozen=True)
class GenOfficeProof:
    content: bytes
    media_type: str
    filename: str
    source: dict[str, Any]
    version: str


class GenOfficeMcpClient:
    """Minimal Streamable HTTP MCP client pinned to GenOffice's public contract.

    GenOffice itself verifies this raw JSON-RPC sequence in its end-to-end
    tests.  Keeping it here avoids bringing a second MCP runtime into 3021 and
    makes the G1 allowlist explicit.
    """

    def __init__(
        self,
        settings: GenOfficeSettings,
        token: str,
        *,
        http_client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self.settings = settings
        self._token = token
        self._http_client_factory = http_client_factory
        self._http: httpx.Client | None = None
        self._session_id = ""
        self.mcp_version = ""
        self.g1_tool_contract_sha256 = ""
        self._request_id = 1

    def __enter__(self) -> "GenOfficeMcpClient":
        self.settings.validate_url()
        timeout = httpx.Timeout(
            connect=self.settings.connect_timeout_seconds,
            read=self.settings.tool_timeout_seconds,
            write=self.settings.tool_timeout_seconds,
            pool=self.settings.connect_timeout_seconds,
        )
        self._http = self._http_client_factory(
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json, text/event-stream",
            },
        )
        try:
            result, headers = self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "3021-genoffice-readonly", "version": "0.1"},
                },
                include_id=True,
                include_session=False,
            )
            self._session_id = str(headers.get("mcp-session-id") or "").strip()
            server_info = result.get("serverInfo") if isinstance(result, Mapping) else {}
            self.mcp_version = str((server_info or {}).get("version") or "").strip()
            if not self._session_id or not self.mcp_version:
                raise GenOfficeProtocolError("GenOffice Sidecar 未返回有效会话或版本")
            self._rpc("notifications/initialized", {}, include_id=False, include_session=True)
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        client = self._http
        if not client:
            return
        try:
            if self._session_id:
                client.delete(self.settings.mcp_url, headers={"Mcp-Session-Id": self._session_id})
        except httpx.HTTPError:
            pass
        finally:
            client.close()
            self._http = None
            self._session_id = ""

    def list_tools(self) -> set[str]:
        result, _headers = self._rpc("tools/list", {}, include_id=True, include_session=True)
        tools = result.get("tools") if isinstance(result, Mapping) else []
        if not isinstance(tools, list):
            raise GenOfficeProtocolError("GenOffice Sidecar 工具清单无效")
        definitions = {
            str(item["name"]): item
            for item in tools
            if isinstance(item, Mapping) and isinstance(item.get("name"), str)
        }
        names = set(definitions)
        if REQUIRED_TOOLS <= names:
            _validate_g1_tool_contract(definitions)
            self.g1_tool_contract_sha256 = _g1_tool_contract_sha256(definitions)
        return names

    def upload_docx(self, source: GenOfficeSource) -> str:
        response = self._request(
            "PUT",
            self._files_url(source.name),
            content=source.data,
            headers={"Content-Type": DOCX_MIME},
        )
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise GenOfficeProtocolError("GenOffice Sidecar 上传响应无效") from exc
        url = str(payload.get("url") or "") if isinstance(payload, Mapping) else ""
        if not self._is_own_file_url(url):
            raise GenOfficeProtocolError("GenOffice Sidecar 上传响应无效")
        return url

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in ALLOWED_TOOLS:
            raise GenOfficeProtocolError("3021 未授权该 GenOffice 工具")
        result, _headers = self._rpc(
            "tools/call",
            {"name": name, "arguments": dict(arguments)},
            include_id=True,
            include_session=True,
        )
        if not isinstance(result, Mapping):
            raise GenOfficeProtocolError("GenOffice 只读调用失败")
        if result.get("isError"):
            error_code = _safe_tool_error_code(result)
            LOGGER.info("GenOffice read-only tool %s failed with %s", name, error_code)
            raise GenOfficeToolFailure(name, error_code)
        content = result.get("content")
        if not isinstance(content, list):
            raise GenOfficeProtocolError("GenOffice 只读调用响应无效")
        for item in content:
            if not isinstance(item, Mapping) or item.get("type") != "text":
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            try:
                envelope = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(envelope, dict) and envelope.get("status") in {"ok", "partial"}:
                if envelope.get("command") != TOOL_COMMANDS[name]:
                    raise GenOfficeProtocolError("GenOffice 只读调用响应不匹配")
                return envelope
        raise GenOfficeProtocolError("GenOffice 只读调用响应无效")

    def download_png(self, url: str, *, max_bytes: int) -> bytes:
        if not self._is_own_file_url(url):
            raise GenOfficeProtocolError("GenOffice 校样输出地址无效")
        with self._stream_request("GET", url) as response:
            _validate_declared_response_size(
                response,
                max_bytes=max_bytes,
                too_large_message="GenOffice 校样图片超过安全大小限制",
            )
            media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != PNG_MIME:
                raise GenOfficeProtocolError("GenOffice 校样输出格式无效")
            chunks: list[bytes] = []
            header = bytearray()
            ihdr_validated = False
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise GenOfficeUnavailable("GenOffice 校样图片超过安全大小限制")
                if not ihdr_validated:
                    header.extend(chunk[: PNG_IHDR_TOTAL_BYTES - len(header)])
                    if len(header) >= len(PNG_SIGNATURE) and not header.startswith(PNG_SIGNATURE):
                        raise GenOfficeProtocolError("GenOffice 校样输出格式无效")
                    if len(header) == PNG_IHDR_TOTAL_BYTES:
                        _validate_png_ihdr(bytes(header))
                        ihdr_validated = True
                chunks.append(chunk)
            if not ihdr_validated:
                _validate_png_ihdr(bytes(header))
            return b"".join(chunks)

    @contextmanager
    def _stream_request(self, method: str, url: str, **kwargs: Any) -> Iterator[httpx.Response]:
        """Issue a request without allowing HTTPX to pre-buffer its body."""

        if not self._http:
            raise GenOfficeProtocolError("GenOffice MCP 客户端未初始化")
        response: httpx.Response | None = None
        try:
            request = self._http.build_request(method, url, **kwargs)
            response = self._http.send(request, stream=True)
            response.raise_for_status()
            yield response
        except httpx.HTTPError as exc:
            LOGGER.info("GenOffice Sidecar request failed: %s", type(exc).__name__)
            raise GenOfficeUnavailable("GenOffice Sidecar 不可用或认证失败") from exc
        finally:
            if response is not None:
                response.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        max_bytes: int = MAX_MCP_RESPONSE_BYTES,
        **kwargs: Any,
    ) -> httpx.Response:
        """Read a small MCP response under a hard byte cap."""

        with self._stream_request(method, url, **kwargs) as response:
            content = _read_response_bytes(
                response,
                max_bytes=max_bytes,
                too_large_message="GenOffice MCP 响应超过安全大小限制",
            )
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=content,
                request=response.request,
            )

    def _rpc(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        include_id: bool,
        include_session: bool,
    ) -> tuple[dict[str, Any], Mapping[str, str]]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": dict(params)}
        request_id: int | None = None
        if include_id:
            request_id = self._request_id
            payload["id"] = request_id
            self._request_id += 1
        headers = {"Content-Type": "application/json"}
        if include_session:
            if not self._session_id:
                raise GenOfficeProtocolError("GenOffice MCP 会话尚未初始化")
            headers["Mcp-Session-Id"] = self._session_id
        response = self._request("POST", self.settings.mcp_url, json=payload, headers=headers)
        if not include_id:
            return {}, response.headers
        reply = _parse_mcp_json(response.text)
        if (
            not isinstance(reply, Mapping)
            or reply.get("jsonrpc") != "2.0"
            or reply.get("id") != request_id
            or not isinstance(reply.get("result"), Mapping)
            or reply.get("error")
        ):
            raise GenOfficeProtocolError("GenOffice MCP 响应无效")
        return dict(reply["result"]), response.headers

    def _files_url(self, name: str) -> str:
        parsed = urlparse(self.settings.mcp_url)
        return parsed._replace(path=f"/files/{quote(name, safe='')}", params="", query="", fragment="").geturl()

    def _is_own_file_url(self, value: str) -> bool:
        parsed = urlparse(value)
        configured = urlparse(self.settings.mcp_url)
        return (
            parsed.scheme == configured.scheme
            and parsed.hostname == configured.hostname
            and parsed.port == configured.port
            and not parsed.username
            and not parsed.password
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            # Match the vendor FileStore route rather than merely a prefix, so
            # a malformed URL cannot be normalized into another localhost API.
            and re.fullmatch(r"/files/[a-f0-9]{16}/[^/]+", parsed.path) is not None
        )


class GenOfficeReadOnlyService:
    """3021-facing Phase G1 service; all source and output IO stays in memory."""

    def __init__(
        self,
        *,
        documents: Any = multi_document_service,
        settings_factory: Callable[[], GenOfficeSettings] = GenOfficeSettings.from_env,
        client_factory: Callable[[GenOfficeSettings, str], Any] = GenOfficeMcpClient,
    ) -> None:
        self.documents = documents
        self._settings_factory = settings_factory
        self._client_factory = client_factory
        self._heavy_slot = threading.BoundedSemaphore(value=1)

    def status(self) -> dict[str, Any]:
        settings = self._settings_factory()
        base = self._status_base(settings)
        if not settings.enabled:
            return {**base, "mode": "disabled", "reason": "GenOffice 集成尚未启用"}
        try:
            settings.validate_channel()
            if not settings.binary_path.is_file():
                raise GenOfficeUnavailable("官方 GenOffice 应用尚未安装")
            settings.validate_url()
            settings.validate_sidecar_home()
            release_version = settings.release_version()
            with self._readonly_client(settings) as client:
                tools = client.list_tools()
                capabilities = _capabilities(tools)
                missing = sorted(REQUIRED_TOOLS - tools)
                mcp_version = str(client.mcp_version)
                version_gates = _version_gates(settings, release_version, mcp_version)
                version_status = {
                    "version": release_version,
                    "mcp_version": mcp_version,
                    **version_gates,
                }
                if version_gates["version_gate"] == "unsupported":
                    return {
                        **base,
                        "reachable": True,
                        "capabilities": capabilities,
                        "mode": "unavailable",
                        "reason": _version_notice(settings, release_version, mcp_version),
                        **version_status,
                    }
                if missing:
                    return {
                        **base,
                        "reachable": True,
                        "capabilities": capabilities,
                        "mode": "unavailable",
                        "reason": "GenOffice Sidecar 缺少 G1 所需只读能力",
                        **version_status,
                    }
                return {
                    **base,
                    "reachable": True,
                    "capabilities": capabilities,
                    "mode": "read_only",
                    "reason": _version_notice(settings, release_version, mcp_version),
                    **version_status,
                }
        except GenOfficeUnavailable as exc:
            return {**base, "mode": "unavailable", "reason": str(exc)}

    def check(self, project: dict[str, Any], document_id: str) -> dict[str, Any]:
        with self._heavy_operation():
            settings = self._enabled_settings()
            release_version = settings.release_version()
            self._require_supported_release_version(settings, release_version)
            source = self._source(project, document_id)
            with self._readonly_client(settings) as client:
                mcp_version = str(client.mcp_version)
                self._require_supported_versions(settings, release_version, mcp_version)
                self._require_capabilities(client.list_tools())
                remote_file = client.upload_docx(source)
                read = client.call_tool("docs_read", {"file": remote_file, "range": "0", "max_chars": 200})
                check = client.call_tool("docs_check", {"file": remote_file})
                return {
                    "schema": "openclaw.genoffice-readonly-check.v1",
                    "engine": self._engine_public(settings, release_version, mcp_version),
                    "source": source.public(),
                    "read": _public_read(read),
                    "check": _public_check(check),
                }

    def proof(self, project: dict[str, Any], document_id: str) -> GenOfficeProof:
        with self._heavy_operation():
            settings = self._enabled_settings()
            release_version = settings.release_version()
            self._require_supported_release_version(settings, release_version)
            source = self._source(project, document_id)
            with self._readonly_client(settings) as client:
                mcp_version = str(client.mcp_version)
                self._require_supported_versions(settings, release_version, mcp_version)
                self._require_capabilities(client.list_tools())
                remote_file = client.upload_docx(source)
                try:
                    render_started_at = monotonic()
                    try:
                        rendered = client.call_tool("render", {"file": remote_file, "page": 1, "scale": 1})
                    except GenOfficeToolFailure as exc:
                        elapsed_seconds = monotonic() - render_started_at
                        if _looks_like_render_timeout(exc, elapsed_seconds):
                            raise GenOfficeUnavailable(
                                "GenOffice 校样未在其内部 180 秒渲染预算内完成；该复杂 Word 原件暂不能生成第 1 页校样"
                            ) from exc
                        raise
                    output_url = _first_render_url(rendered)
                    content = client.download_png(output_url, max_bytes=settings.max_render_bytes)
                    return GenOfficeProof(
                        content=content,
                        media_type=PNG_MIME,
                        filename="office-proof-page-1.png",
                        source=source.public(),
                        version=release_version,
                    )
                finally:
                    settings.cleanup_headless_source(source.sha256)

    @contextmanager
    def _readonly_client(self, settings: GenOfficeSettings) -> Iterator[Any]:
        token = settings.load_token()
        with self._client_factory(settings, token) as client:
            yield client

    @contextmanager
    def _heavy_operation(self) -> Iterator[None]:
        if not self._heavy_slot.acquire(blocking=False):
            raise GenOfficeBusy("GenOffice 正在生成另一份只读校样，请稍后重试")
        try:
            yield
        finally:
            self._heavy_slot.release()

    def _enabled_settings(self) -> GenOfficeSettings:
        settings = self._settings_factory()
        if not settings.enabled:
            raise GenOfficeUnavailable("GenOffice 集成尚未启用")
        settings.validate_channel()
        settings.validate_url()
        settings.validate_sidecar_home()
        if not settings.binary_path.is_file():
            raise GenOfficeUnavailable("官方 GenOffice 应用尚未安装")
        return settings

    def _source(self, project: dict[str, Any], document_id: str) -> GenOfficeSource:
        record = self.documents.get_document(project, document_id)
        if str(record.get("kind") or "") != "rich_text":
            raise GenOfficeUnavailable("Office 校样目前仅支持已导入的 Word 正文")
        root = self.documents._document_root(project, document_id)  # noqa: SLF001
        source = root / "source" / "original.docx"
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(root.resolve())
        except (OSError, ValueError) as exc:
            raise GenOfficeUnavailable("当前正文没有可用于只读校样的已导入 Word 原件") from exc
        if source.is_symlink() or not resolved.is_file():
            raise GenOfficeUnavailable("当前正文没有可用于只读校样的已导入 Word 原件")
        settings = self._settings_factory()
        size = resolved.stat().st_size
        if size <= 0 or size > settings.max_input_bytes:
            raise GenOfficeUnavailable("Word 原件大小不符合 Office 校样限制")
        try:
            with ZipFile(resolved) as archive:
                members = archive.infolist()
                if (
                    len(members) > MAX_DOCX_ENTRIES
                    or sum(member.file_size for member in members) > MAX_DOCX_UNCOMPRESSED_BYTES
                ):
                    raise GenOfficeUnavailable("Word 原件的压缩内容超过 Office 校样限制")
                names = {member.filename for member in members}
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise GenOfficeUnavailable("已导入文件不是有效的 Word DOCX 原件")
        except (BadZipFile, OSError) as exc:
            raise GenOfficeUnavailable("已导入文件不是有效的 Word DOCX 原件") from exc
        data = resolved.read_bytes()
        return GenOfficeSource(data=data, sha256=hashlib.sha256(data).hexdigest(), name="original.docx")

    def _require_capabilities(self, tools: set[str]) -> None:
        if REQUIRED_TOOLS - tools:
            raise GenOfficeUnavailable("GenOffice Sidecar 缺少 G1 所需只读能力")

    def _require_supported_release_version(self, settings: GenOfficeSettings, release_version: str) -> None:
        if _release_version_gate(settings, release_version) == "unsupported":
            raise GenOfficeUnavailable(_version_notice(settings, release_version, ""))

    def _require_supported_versions(
        self,
        settings: GenOfficeSettings,
        release_version: str,
        mcp_version: str,
    ) -> None:
        if _combined_version_gate(settings, release_version, mcp_version) == "unsupported":
            raise GenOfficeUnavailable(_version_notice(settings, release_version, mcp_version))

    def _status_base(self, settings: GenOfficeSettings) -> dict[str, Any]:
        return {
            "installed": settings.binary_path.is_file(),
            "reachable": False,
            "version": "",
            "mcp_version": "",
            "channel": settings.channel,
            "pilot_gate": _pilot_gate(settings.pilot_gate),
            "capabilities": _capabilities(set()),
            "last_checked_at": _now(),
        }

    def _engine_public(
        self,
        settings: GenOfficeSettings,
        release_version: str,
        mcp_version: str,
    ) -> dict[str, Any]:
        return {
            "version": release_version,
            "mcp_version": mcp_version,
            "channel": settings.channel,
            "pilot_gate": _pilot_gate(settings.pilot_gate),
            "mode": "read_only",
            **_version_gates(settings, release_version, mcp_version),
            "notice": _version_notice(settings, release_version, mcp_version),
        }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_path(value: str | None) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _pilot_gate(value: str | None) -> str:
    """G1 is limited until the approved real-document exit gate passes."""

    return "accepted" if str(value or "").strip().lower() == "accepted" else "limited"


def _validate_declared_response_size(
    response: httpx.Response,
    *,
    max_bytes: int,
    too_large_message: str,
) -> None:
    """Reject an oversized response before reading its body when possible."""

    raw_size = response.headers.get("content-length")
    if raw_size is None or not raw_size.strip():
        return
    try:
        declared = int(raw_size)
    except ValueError as exc:
        raise GenOfficeProtocolError("GenOffice 响应大小无效") from exc
    if declared < 0:
        raise GenOfficeProtocolError("GenOffice 响应大小无效")
    if declared > max_bytes:
        raise GenOfficeUnavailable(too_large_message)


def _read_response_bytes(
    response: httpx.Response,
    *,
    max_bytes: int,
    too_large_message: str,
) -> bytes:
    """Consume a streamed localhost response while enforcing a total cap."""

    _validate_declared_response_size(
        response,
        max_bytes=max_bytes,
        too_large_message=too_large_message,
    )
    content = bytearray()
    for chunk in response.iter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise GenOfficeUnavailable(too_large_message)
        content.extend(chunk)
    return bytes(content)


def _validate_png_ihdr(header: bytes) -> None:
    """Validate the fixed PNG preamble before returning a render to a browser."""

    if len(header) != PNG_IHDR_TOTAL_BYTES or not header.startswith(PNG_SIGNATURE):
        raise GenOfficeProtocolError("GenOffice 校样输出格式无效")

    chunk_length = int.from_bytes(header[8:12], "big")
    chunk_type = header[12:16]
    if chunk_length != PNG_IHDR_LENGTH or chunk_type != b"IHDR":
        raise GenOfficeProtocolError("GenOffice 校样输出格式无效")

    ihdr = header[16:29]
    expected_crc = int.from_bytes(header[29:33], "big")
    if (zlib.crc32(chunk_type + ihdr) & 0xFFFFFFFF) != expected_crc:
        raise GenOfficeProtocolError("GenOffice 校样输出格式无效")

    width = int.from_bytes(ihdr[0:4], "big")
    height = int.from_bytes(ihdr[4:8], "big")
    bit_depth, color_type, compression, filter_method, interlace = ihdr[8:13]
    if (
        width == 0
        or height == 0
        or bit_depth not in PNG_BIT_DEPTHS_BY_COLOR_TYPE.get(color_type, frozenset())
        or compression != 0
        or filter_method != 0
        or interlace not in {0, 1}
    ):
        raise GenOfficeProtocolError("GenOffice 校样输出格式无效")
    if width > MAX_PNG_DIMENSION or height > MAX_PNG_DIMENSION or width * height > MAX_PNG_PIXELS:
        raise GenOfficeUnavailable("GenOffice 校样图片尺寸超过安全限制")


def _parse_mcp_json(body: str) -> Mapping[str, Any]:
    candidates = [body.strip()]
    candidates.extend(
        line[6:].strip()
        for line in body.splitlines()
        if line.startswith("data: ") and line[6:].strip()
    )
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    raise GenOfficeProtocolError("GenOffice MCP 响应无效")


def _validate_g1_tool_contract(definitions: Mapping[str, Mapping[str, Any]]) -> None:
    """Pin the small read-only surface needed by this adapter.

    Extra vendor tools/properties are fine; missing required inputs or a tool
    no longer advertised as read-only is a compatibility failure.
    """

    for name, required_properties in REQUIRED_TOOL_PROPERTIES.items():
        definition = definitions.get(name)
        if not isinstance(definition, Mapping):
            raise GenOfficeProtocolError("GenOffice Sidecar 工具清单无效")
        schema = definition.get("inputSchema")
        annotations = definition.get("annotations")
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        required = schema.get("required") if isinstance(schema, Mapping) else None
        if (
            not isinstance(properties, Mapping)
            or not required_properties <= set(properties)
            or not isinstance(required, list)
            or "file" not in required
            or not isinstance(annotations, Mapping)
            or annotations.get("readOnlyHint") is not True
        ):
            raise GenOfficeProtocolError("GenOffice Sidecar 只读工具契约不兼容")


def _g1_tool_contract_sha256(definitions: Mapping[str, Mapping[str, Any]]) -> str:
    """Return a stable fingerprint of the executable G1 MCP contract.

    The report deliberately excludes vendor prose such as descriptions and
    examples.  It includes the input schema and read-only assertion for the
    three tools that 3021 can actually invoke, which makes a material protocol
    change visible to the update gate without exposing a whole MCP transcript.
    """

    contract: dict[str, Any] = {}
    for name in sorted(REQUIRED_TOOLS):
        definition = definitions.get(name)
        if not isinstance(definition, Mapping):
            raise GenOfficeProtocolError("GenOffice Sidecar 工具清单无效")
        annotations = definition.get("annotations")
        contract[name] = {
            "inputSchema": _semantic_tool_schema(definition.get("inputSchema")),
            "readOnlyHint": bool(isinstance(annotations, Mapping) and annotations.get("readOnlyHint") is True),
        }
    canonical = json.dumps(contract, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _semantic_tool_schema(value: Any, *, parent_key: str = "") -> Any:
    """Canonicalize JSON Schema while ignoring non-executable presentation."""

    if isinstance(value, Mapping):
        return {
            str(key): _semantic_tool_schema(item, parent_key=str(key))
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if str(key) not in NON_SEMANTIC_TOOL_SCHEMA_KEYS
        }
    if isinstance(value, list):
        normalized = [_semantic_tool_schema(item) for item in value]
        if parent_key in UNORDERED_TOOL_SCHEMA_ARRAY_KEYS:
            return sorted(
                normalized,
                key=lambda item: json.dumps(item, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            )
        return normalized
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # MCP JSON is JSON-serializable.  Preserve an explicit sentinel rather
    # than accidentally stringifying an unexpected Python object into a
    # machine-dependent fingerprint.
    return {"unexpected_type": type(value).__name__}


def _safe_tool_error_code(result: Mapping[str, Any]) -> str:
    """Extract only a vendor error code, never a path or document message."""

    content = result.get("content")
    if not isinstance(content, list):
        return "unknown"
    for item in content:
        if not isinstance(item, Mapping) or item.get("type") != "text" or not isinstance(item.get("text"), str):
            continue
        try:
            envelope = json.loads(item["text"])
        except json.JSONDecodeError:
            continue
        code = str(envelope.get("error") or "") if isinstance(envelope, Mapping) else ""
        if re.fullmatch(r"[a-z0-9_-]{1,64}", code):
            return code
    return "unknown"


def _looks_like_render_timeout(error: GenOfficeToolFailure, elapsed_seconds: float) -> bool:
    """Classify only the documented, near-budget headless render failure."""

    return (
        error.tool_name == "render"
        and error.error_code == "conversion_failed"
        and elapsed_seconds >= RENDER_TIMEOUT_SIGNAL_SECONDS
    )


def _capabilities(tools: set[str]) -> dict[str, bool]:
    return {
        "docs_read": "docs_read" in tools,
        "docs_check": "docs_check" in tools,
        "render": "render" in tools,
        "docs_apply": False,
        "visible_editor": False,
    }


def _public_read(envelope: Mapping[str, Any]) -> dict[str, Any]:
    detail = envelope.get("detail") if isinstance(envelope.get("detail"), Mapping) else {}
    items = detail.get("items") if isinstance(detail, Mapping) else []
    public_items = [
        _bounded_public_value(item)
        for item in items[:250]
        if isinstance(item, Mapping)
    ] if isinstance(items, list) else []
    return {
        "summary": str(envelope.get("summary") or "")[:1000],
        "blocks": _safe_nonnegative_int(detail.get("blocks") or 0) if isinstance(detail, Mapping) else 0,
        "range": str(detail.get("range") or "")[:128] if isinstance(detail, Mapping) else "",
        "items": public_items,
    }


def _public_check(envelope: Mapping[str, Any]) -> dict[str, Any]:
    detail = envelope.get("detail") if isinstance(envelope.get("detail"), Mapping) else {}
    issues = detail.get("issues") if isinstance(detail, Mapping) else []
    public_issues: list[dict[str, Any]] = []
    if isinstance(issues, list):
        for issue in issues[:200]:
            if not isinstance(issue, Mapping):
                continue
            public_issues.append(
                {
                    key: _bounded_public_value(issue.get(key))
                    for key in ("id", "code", "level", "path", "message", "context", "blockIndex", "part")
                    if issue.get(key) is not None
                }
            )
    counts = detail.get("counts") if isinstance(detail, Mapping) and isinstance(detail.get("counts"), Mapping) else {}
    return {
        "summary": str(envelope.get("summary") or "")[:1000],
        "counts": {key: _safe_nonnegative_int(counts.get(key) or 0) for key in ("error", "warning", "info")},
        "issues": public_issues,
        "truncated": bool(detail.get("truncated")) if isinstance(detail, Mapping) else False,
    }


def _bounded_public_value(value: Any, *, depth: int = 0) -> Any:
    """Make vendor result snippets safe to retain in the 3021 API response."""

    if isinstance(value, str):
        return value[:MAX_PUBLIC_TEXT_CHARS]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= MAX_PUBLIC_NESTING:
        return str(value)[:MAX_PUBLIC_TEXT_CHARS]
    if isinstance(value, Mapping):
        return {
            str(key)[:128]: _bounded_public_value(item, depth=depth + 1)
            for key, item in list(value.items())[:MAX_PUBLIC_CONTAINER_KEYS]
        }
    if isinstance(value, (list, tuple)):
        return [
            _bounded_public_value(item, depth=depth + 1)
            for item in value[:MAX_PUBLIC_CONTAINER_ITEMS]
        ]
    return str(value)[:MAX_PUBLIC_TEXT_CHARS]


def _first_render_url(envelope: Mapping[str, Any]) -> str:
    detail = envelope.get("detail") if isinstance(envelope.get("detail"), Mapping) else {}
    files = detail.get("files") if isinstance(detail, Mapping) else []
    if not isinstance(files, list):
        raise GenOfficeProtocolError("GenOffice 校样输出缺失")
    for item in files:
        if isinstance(item, Mapping) and _safe_nonnegative_int(item.get("page") or 0) == 1 and isinstance(item.get("url"), str):
            return item["url"]
    raise GenOfficeProtocolError("GenOffice 校样输出缺失")


def _safe_nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GenOfficeProtocolError("GenOffice 只读调用响应无效") from exc
    if parsed < 0:
        raise GenOfficeProtocolError("GenOffice 只读调用响应无效")
    return parsed


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = str(value or "").strip().lstrip("v").split(".")
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return ()


def _range_version_gate(version: str, minimum_version: str, maximum_version: str) -> str:
    current = _version_tuple(version)
    minimum = _version_tuple(minimum_version)
    maximum = _version_tuple(maximum_version)
    if not current or not minimum or not maximum or current < minimum:
        return "unsupported"
    if current > maximum:
        return "unverified"
    return "tested"


def _release_version_gate(settings: GenOfficeSettings, release_version: str) -> str:
    return _range_version_gate(
        release_version,
        settings.min_supported_version,
        settings.max_tested_version,
    )


def _mcp_version_gate(settings: GenOfficeSettings, mcp_version: str) -> str:
    return _range_version_gate(
        mcp_version,
        settings.min_supported_mcp_version,
        settings.max_tested_mcp_version,
    )


def _combined_version_gate(settings: GenOfficeSettings, release_version: str, mcp_version: str) -> str:
    gates = (_release_version_gate(settings, release_version), _mcp_version_gate(settings, mcp_version))
    if "unsupported" in gates:
        return "unsupported"
    if "unverified" in gates:
        return "unverified"
    return "tested"


def _version_gates(settings: GenOfficeSettings, release_version: str, mcp_version: str) -> dict[str, str]:
    return {
        "version_gate": _combined_version_gate(settings, release_version, mcp_version),
        "release_version_gate": _release_version_gate(settings, release_version),
        "mcp_version_gate": _mcp_version_gate(settings, mcp_version),
    }


def _version_notice(settings: GenOfficeSettings, release_version: str, mcp_version: str) -> str:
    gates = _version_gates(settings, release_version, mcp_version)
    if gates["version_gate"] == "tested":
        return "已通过 G1 只读版本门；写入能力在本阶段始终关闭。"
    if gates["version_gate"] == "unverified":
        return "官方应用或 MCP 版本尚未完成 3021 金标验证；仅保留 G1 只读能力。"
    return "当前 GenOffice 应用或 MCP 版本不在已支持范围；G1 只读调用已关闭。"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


genoffice_readonly_service = GenOfficeReadOnlyService()
