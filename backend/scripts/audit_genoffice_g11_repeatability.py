#!/usr/bin/env python3
"""Produce one bounded, read-only Phase G1.1 GenOffice evidence report.

The existing G1 gold probe remains the historical single-run record.  This
additive runner is for repeatability evidence: it performs only ``docs_read``,
``docs_check`` and page-one ``render`` calls through the localhost MCP
Sidecar.  It never passes an original filesystem path to GenOffice, never
calls a write tool, and never starts, stops, installs, upgrades or restarts a
Sidecar.  The caller must label the externally prepared test condition.

Reports intentionally contain hashes, counts, timings and PNG metadata only;
they omit source paths, FileStore URLs, token material and document text.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import stat
import struct
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from services.genoffice_readonly_service import (  # noqa: E402
    GenOfficeMcpClient,
    GenOfficeProtocolError,
    GenOfficeReadOnlyError,
    GenOfficeSettings,
    GenOfficeSource,
    GenOfficeToolFailure,
    REQUIRED_TOOLS,
    _first_render_url,
    _public_check,
    _public_read,
    _version_gates,
)


SCHEMA = "openclaw.genoffice-phase-g1.1-repeatability.v1"
CONDITIONS = frozenset({"cold_process", "fresh_profile", "warm"})
MAX_ROUNDS = 3
RUN_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
SHA256_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
REVIEW_ROOT = (PROJECT_ROOT / "docs" / "review").resolve()
PRODUCTION_G1_MCP_PORT = 3094


class G11AuditError(ValueError):
    """A safe, non-document-specific G1.1 audit failure."""


class G11AuditBusy(G11AuditError):
    """Another repeatability audit holds this Sidecar-home lock."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generated_run_id() -> str:
    return "g11-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _time_stage(timings: dict[str, int], stage: str, callback: Callable[[], Any]) -> Any:
    started_at = monotonic()
    try:
        return callback()
    finally:
        timings[stage] = round((monotonic() - started_at) * 1000)


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G11AuditError("manifest_invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise G11AuditError("manifest_invalid")
    return payload


def _selected_documents(manifest: Mapping[str, Any], requested_ids: set[str]) -> list[dict[str, Any]]:
    raw_documents = manifest.get("documents")
    if not isinstance(raw_documents, list) or not all(isinstance(item, dict) for item in raw_documents):
        raise G11AuditError("manifest_invalid")
    documents = [dict(item) for item in raw_documents]
    identifiers = [str(item.get("id") or "") for item in documents]
    if not all(identifiers) or len(set(identifiers)) != len(identifiers):
        raise G11AuditError("manifest_invalid")
    if requested_ids:
        documents = [item for item in documents if str(item.get("id")) in requested_ids]
        if {str(item.get("id")) for item in documents} != requested_ids:
            raise G11AuditError("requested_document_unavailable")
    if not documents:
        raise G11AuditError("no_documents_selected")
    return documents


def _require_label(value: str, *, field: str) -> str:
    if not RUN_LABEL_PATTERN.fullmatch(value):
        raise G11AuditError(f"invalid_{field}")
    return value


def _require_sha256(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise G11AuditError(f"invalid_{field}")
    return normalized


def _validate_options(args: argparse.Namespace) -> None:
    if args.condition not in CONDITIONS:
        raise G11AuditError("invalid_condition")
    _require_label(args.run_id, field="run_id")
    _require_label(args.sidecar_epoch, field="sidecar_epoch")
    if args.rounds < 1 or args.rounds > MAX_ROUNDS:
        raise G11AuditError("invalid_rounds")
    if args.condition != "warm" and args.rounds != 1:
        # This program intentionally does not restart a process or wipe a
        # profile.  Multiple cold/fresh attempts must be separate reports.
        raise G11AuditError("independent_condition_requires_one_round")
    if args.render_target_seconds <= 0 or args.render_limit_seconds <= 0:
        raise G11AuditError("invalid_render_threshold")
    if args.render_target_seconds > args.render_limit_seconds:
        raise G11AuditError("invalid_render_threshold")
    if args.expected_contract_sha256:
        _require_sha256(args.expected_contract_sha256, field="expected_contract_sha256")
    if args.allow_unverified_candidate and not (args.expected_release_version and args.expected_mcp_version):
        raise G11AuditError("candidate_versions_must_be_explicit")
    output_path = args.output.resolve()
    try:
        output_path.relative_to(REVIEW_ROOT)
    except ValueError as exc:
        raise G11AuditError("output_must_be_under_docs_review") from exc
    if output_path.exists():
        raise G11AuditError("output_already_exists")


def _settings_fingerprint(settings: GenOfficeSettings) -> str:
    """Fingerprint only non-secret, behavior-relevant G1 configuration."""

    payload = {
        "channel": settings.channel.strip().lower(),
        "connect_timeout_seconds": settings.connect_timeout_seconds,
        "max_input_bytes": settings.max_input_bytes,
        "max_render_bytes": settings.max_render_bytes,
        "tool_timeout_seconds": settings.tool_timeout_seconds,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical.encode("utf-8"))


def _resource_snapshot(settings: GenOfficeSettings) -> dict[str, Any]:
    home = settings.validate_sidecar_home()
    try:
        filesystem = os.statvfs(home)
        available_bytes = filesystem.f_bavail * filesystem.f_frsize
    except OSError as exc:
        raise G11AuditError("resource_snapshot_unavailable") from exc
    return {
        "machine": platform.machine(),
        "os": f"{platform.system()} {platform.release()}",
        "sidecar_home_available_bytes": available_bytes,
    }


def _require_test_sidecar(settings: GenOfficeSettings) -> None:
    """Prevent formal G1.1 evidence work from competing with the G1 pilot."""

    parsed = urlparse(settings.mcp_url)
    if parsed.port == PRODUCTION_G1_MCP_PORT:
        raise G11AuditError("independent_test_sidecar_required")


@contextmanager
def _audit_lock(settings: GenOfficeSettings) -> Iterator[None]:
    """Keep G1.1 audit invocations from sharing one private Sidecar profile.

    The lock covers this audit program only.  It is not presented as a lock
    for the live 3021 API, which is why the G1.1 protocol still uses an
    independently provisioned test Sidecar for its formal evidence runs.
    """

    home = settings.validate_sidecar_home()
    lock_path = home / ".g11-repeatability.lock"
    if lock_path.is_symlink():
        raise G11AuditError("audit_lock_unsafe")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(lock_path), flags, 0o600)
    except OSError as exc:
        raise G11AuditError("audit_lock_unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
        ):
            raise G11AuditError("audit_lock_unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise G11AuditBusy("audit_lock_busy") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _preflight(
    settings: GenOfficeSettings,
    *,
    expected_contract_sha256: str | None,
    expected_release_version: str | None,
    expected_mcp_version: str | None,
    allow_unverified_candidate: bool,
) -> dict[str, Any]:
    settings.validate_channel()
    settings.validate_url()
    settings.validate_sidecar_home()
    _require_test_sidecar(settings)
    if not settings.enabled:
        raise G11AuditError("integration_disabled")
    if not settings.binary_path.is_file():
        raise G11AuditError("official_app_missing")
    release_version = settings.release_version()
    if expected_release_version and release_version != expected_release_version:
        raise G11AuditError("release_version_mismatch")

    timings: dict[str, int] = {}
    client = GenOfficeMcpClient(settings, settings.load_token())
    connected = False
    try:
        _time_stage(timings, "mcp_initialize", client.__enter__)
        connected = True
        tools = _time_stage(timings, "tools_list", client.list_tools)
        if REQUIRED_TOOLS - tools:
            raise G11AuditError("required_readonly_tool_missing")
        mcp_version = str(client.mcp_version)
        if expected_mcp_version and mcp_version != expected_mcp_version:
            raise G11AuditError("mcp_version_mismatch")
        gates = _version_gates(settings, release_version, mcp_version)
        if gates["version_gate"] == "unsupported":
            raise G11AuditError("version_unsupported")
        if gates["version_gate"] == "unverified" and not allow_unverified_candidate:
            raise G11AuditError("version_unverified")
        fingerprint = str(client.g1_tool_contract_sha256)
        if not SHA256_PATTERN.fullmatch(fingerprint):
            raise G11AuditError("tool_contract_fingerprint_invalid")
        if expected_contract_sha256 and fingerprint != expected_contract_sha256:
            raise G11AuditError("tool_contract_mismatch")
        return {
            "release_version": release_version,
            "mcp_version": mcp_version,
            "g1_tool_contract_sha256": fingerprint,
            "required_readonly_tools": sorted(REQUIRED_TOOLS),
            "version_gates": gates,
            "preflight_elapsed_ms": timings,
        }
    finally:
        if connected:
            _time_stage(timings, "mcp_session_close", client.close)
        else:
            client.close()


def _source_from_manifest_item(item: Mapping[str, Any]) -> tuple[Path, GenOfficeSource, dict[str, Any]]:
    document_id = str(item.get("id") or "")
    source_path = Path(str(item.get("path") or ""))
    expected_sha256 = str(item.get("expected_sha256") or "").lower()
    if not document_id or not source_path.is_file() or not SHA256_PATTERN.fullmatch(expected_sha256):
        raise G11AuditError("gold_source_invalid")
    try:
        source_data = source_path.read_bytes()
    except OSError as exc:
        raise G11AuditError("gold_source_unreadable") from exc
    source_sha256 = _sha256(source_data)
    if source_sha256 != expected_sha256:
        raise G11AuditError("gold_source_hash_mismatch")
    source = GenOfficeSource(data=source_data, sha256=source_sha256, name="original.docx")
    return source_path, source, {"bytes": len(source_data), "sha256": source_sha256}


def _ensure_renderer_source_absent(settings: GenOfficeSettings, source_sha256: str) -> None:
    home = settings.validate_sidecar_home()
    original = home / "electron-user-data" / "originals" / f"{source_sha256}.docx"
    if original.is_symlink() or original.exists():
        raise G11AuditError("renderer_source_cleanup_incomplete")


def _reason_code(exc: Exception) -> str:
    if isinstance(exc, GenOfficeToolFailure):
        return f"tool_{exc.error_code}"
    if isinstance(exc, GenOfficeProtocolError):
        return "mcp_protocol_failure"
    if isinstance(exc, GenOfficeReadOnlyError):
        return "genoffice_readonly_failure"
    if isinstance(exc, G11AuditBusy):
        return "audit_lock_busy"
    if isinstance(exc, G11AuditError):
        return str(exc)
    if isinstance(exc, OSError):
        return "local_io_failure"
    return "unexpected_failure"


def _png_dimensions(png: bytes) -> dict[str, int]:
    if len(png) < 24:
        raise G11AuditError("png_metadata_invalid")
    width, height = struct.unpack(">II", png[16:24])
    return {"height": height, "width": width}


def _semantic_observation_sha256(record: Mapping[str, Any]) -> str:
    """Fingerprint bounded read/check evidence without retaining document text."""

    observation = {"check": record.get("check"), "read": record.get("read")}
    canonical = json.dumps(observation, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _sha256(canonical.encode("utf-8"))


def _audit_document(settings: GenOfficeSettings, item: Mapping[str, Any], engine: Mapping[str, Any]) -> dict[str, Any]:
    started_at = _utc_now()
    operation_started_at = monotonic()
    stage = "source_preflight"
    timings: dict[str, int] = {}
    record: dict[str, Any] = {
        "id": str(item.get("id") or ""),
        "started_at": started_at,
        "status": "failed",
        "stage_elapsed_ms": timings,
    }
    source_path: Path | None = None
    source: GenOfficeSource | None = None
    client: GenOfficeMcpClient | None = None
    connected = False
    error: Exception | None = None
    failed_stage = ""
    try:
        source_path, source, source_public = _time_stage(
            timings,
            stage,
            lambda: _source_from_manifest_item(item),
        )
        record["source"] = source_public
        client = GenOfficeMcpClient(settings, settings.load_token())
        stage = "mcp_initialize"
        _time_stage(timings, stage, client.__enter__)
        connected = True
        stage = "tools_list"
        tools = _time_stage(timings, stage, client.list_tools)
        if REQUIRED_TOOLS - tools:
            raise G11AuditError("required_readonly_tool_missing")
        if str(client.mcp_version) != str(engine["mcp_version"]):
            raise G11AuditError("mcp_version_drift")
        if str(client.g1_tool_contract_sha256) != str(engine["g1_tool_contract_sha256"]):
            raise G11AuditError("tool_contract_drift")

        stage = "upload_source"
        remote_file = _time_stage(timings, stage, lambda: client.upload_docx(source))
        stage = "docs_read"
        read = _time_stage(
            timings,
            stage,
            lambda: client.call_tool("docs_read", {"file": remote_file, "range": "0", "max_chars": 200}),
        )
        public_read = _public_read(read)
        record["read"] = {
            "blocks": public_read["blocks"],
            "item_count": len(public_read["items"]),
            "range": public_read["range"],
        }
        stage = "docs_check"
        check = _time_stage(timings, stage, lambda: client.call_tool("docs_check", {"file": remote_file}))
        public_check = _public_check(check)
        record["check"] = {
            "counts": public_check["counts"],
            "issue_count": len(public_check["issues"]),
            "truncated": public_check["truncated"],
        }
        stage = "render_page_1"
        rendered = _time_stage(
            timings,
            stage,
            lambda: client.call_tool("render", {"file": remote_file, "page": 1, "scale": 1}),
        )
        stage = "download_page_1"
        png = _time_stage(
            timings,
            stage,
            lambda: client.download_png(_first_render_url(rendered), max_bytes=settings.max_render_bytes),
        )
        record["render_page_1"] = {
            "bytes": len(png),
            "dimensions": _png_dimensions(png),
            "sha256": _sha256(png),
        }
    except Exception as exc:  # The report must retain a bounded failure record.
        error = exc
        failed_stage = stage
    finally:
        if source is not None:
            try:
                stage = "cleanup_renderer_source"
                _time_stage(timings, stage, lambda: settings.cleanup_headless_source(source.sha256))
                _ensure_renderer_source_absent(settings, source.sha256)
                record["renderer_source_cleanup"] = "passed"
            except Exception as cleanup_exc:  # preserve the original operation failure where present
                record["renderer_source_cleanup"] = "failed"
                if error is None:
                    error = cleanup_exc
                    failed_stage = "cleanup_renderer_source"
            if source_path is not None:
                try:
                    stage = "source_integrity_after"
                    post_sha256 = _time_stage(timings, stage, lambda: _sha256(source_path.read_bytes()))
                    record["source"]["post_sha256"] = post_sha256
                    if post_sha256 != source.sha256:
                        raise G11AuditError("gold_source_changed_during_audit")
                    record["source"]["integrity"] = "passed"
                except Exception as integrity_exc:
                    record["source"]["integrity"] = "failed"
                    if error is None:
                        error = integrity_exc
                        failed_stage = "source_integrity_after"
        if client is not None:
            try:
                if connected:
                    _time_stage(timings, "mcp_session_close", client.close)
                else:
                    client.close()
            except Exception as close_exc:
                if error is None:
                    error = close_exc
                    failed_stage = "mcp_session_close"

    record["finished_at"] = _utc_now()
    record["total_elapsed_ms"] = round((monotonic() - operation_started_at) * 1000)
    if error is None:
        record["semantic_observation_sha256"] = _semantic_observation_sha256(record)
        record["status"] = "passed"
    else:
        record["failed_stage"] = failed_stage or stage
        record["reason_code"] = _reason_code(error)
    return record


def _percentile_95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * 0.95 + 0.999999)) - 1))
    return round(ordered[index], 3)


def _round_summary(
    documents: list[dict[str, Any]],
    *,
    render_target_seconds: float,
    render_limit_seconds: float,
) -> dict[str, Any]:
    render_seconds = [
        round(float(item["stage_elapsed_ms"]["render_page_1"]) / 1000, 3)
        for item in documents
        if "render_page_1" in item.get("stage_elapsed_ms", {})
    ]
    p95 = _percentile_95(render_seconds)
    maximum = max(render_seconds) if render_seconds else None
    operation_status = "passed" if all(item.get("status") == "passed" for item in documents) else "failed"
    if maximum is None or maximum > render_limit_seconds:
        performance_status = "failed"
    elif p95 is not None and p95 > render_target_seconds:
        performance_status = "attention"
    else:
        performance_status = "passed"
    return {
        "operation_status": operation_status,
        "performance": {
            "max_render_seconds": maximum,
            "p95_render_seconds": p95,
            "status": performance_status,
        },
        "status": (
            "passed"
            if operation_status == "passed" and performance_status == "passed"
            else "attention"
            if operation_status == "passed" and performance_status == "attention"
            else "failed"
        ),
    }


def _mark_semantic_consistency(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Reject read/check metric drift between warm attempts in one report."""

    baselines: dict[str, str] = {}
    drifted_ids: set[str] = set()
    for round_record in rounds:
        drifted_this_round = False
        for document in round_record.get("documents", []):
            if not isinstance(document, dict) or document.get("status") != "passed":
                continue
            document_id = str(document.get("id") or "")
            observation = str(document.get("semantic_observation_sha256") or "")
            if not document_id or not SHA256_PATTERN.fullmatch(observation):
                document["semantic_observation_status"] = "invalid"
                drifted_this_round = True
                drifted_ids.add(document_id or "unknown")
                continue
            baseline = baselines.setdefault(document_id, observation)
            if baseline != observation:
                document["semantic_observation_status"] = "drift"
                drifted_this_round = True
                drifted_ids.add(document_id)
            else:
                document["semantic_observation_status"] = "matched"
        if drifted_this_round:
            round_record["semantic_observation_status"] = "drift"
            round_record["status"] = "failed"
        else:
            round_record["semantic_observation_status"] = "matched"
    return {
        "baseline_by_document": baselines,
        "drifted_document_ids": sorted(drifted_ids),
        "status": "failed" if drifted_ids else "passed",
    }


def _new_report(args: argparse.Namespace, manifest_path: Path, manifest: Mapping[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "created_at": _utc_now(),
        "scope": "docs_read/docs_check/render page 1 only; no source, candidate, database, or formal-document write",
        "run": {
            "allow_unverified_candidate": bool(args.allow_unverified_candidate),
            "condition": args.condition,
            "lock_scope": "g11_audit_process_only",
            "rounds_requested": args.rounds,
            "run_id": args.run_id,
            "sidecar_epoch": args.sidecar_epoch,
            "sidecar_management": "external; this script never installs, starts, stops, upgrades, or restarts GenOffice",
        },
        "manifest": {
            "document_ids": [str(item["id"]) for item in documents],
            "sha256": _sha256(manifest_path.read_bytes()),
        },
        "thresholds": {
            "render_limit_seconds": args.render_limit_seconds,
            "render_target_p95_seconds": args.render_target_seconds,
        },
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    _validate_options(args)
    manifest_path = args.manifest.resolve()
    manifest = _load_manifest(manifest_path)
    documents = _selected_documents(manifest, set(args.document_ids or []))
    report = _new_report(args, manifest_path, manifest, documents)
    settings = GenOfficeSettings.from_env()
    settings.validate_url()
    _require_test_sidecar(settings)
    report["resource_snapshot_before"] = _resource_snapshot(settings)

    with _audit_lock(settings):
        engine = _preflight(
            settings,
            expected_contract_sha256=args.expected_contract_sha256 or None,
            expected_release_version=args.expected_release_version or None,
            expected_mcp_version=args.expected_mcp_version or None,
            allow_unverified_candidate=bool(args.allow_unverified_candidate),
        )
        report["engine"] = engine
        report["configuration_sha256"] = _settings_fingerprint(settings)
        rounds = []
        for index in range(1, args.rounds + 1):
            records = [_audit_document(settings, item, engine) for item in documents]
            summary = _round_summary(
                records,
                render_target_seconds=args.render_target_seconds,
                render_limit_seconds=args.render_limit_seconds,
            )
            rounds.append({"attempt": index, "documents": records, **summary})
        report["rounds"] = rounds
        report["semantic_consistency"] = _mark_semantic_consistency(rounds)

    report["resource_snapshot_after"] = _resource_snapshot(settings)
    round_statuses = {str(item["status"]) for item in report["rounds"]}
    report["status"] = (
        "passed" if round_statuses == {"passed"} else "attention" if "failed" not in round_statuses else "failed"
    )
    return report


def _write_report(output_path: Path, report: Mapping[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise G11AuditError("output_already_exists") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "specs/active/word-cowriting-phase0-gold-documents.json",
    )
    parser.add_argument("--document-id", action="append", dest="document_ids")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default=_generated_run_id())
    parser.add_argument("--sidecar-epoch", required=True)
    parser.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--render-target-seconds", type=float, default=150.0)
    parser.add_argument("--render-limit-seconds", type=float, default=170.0)
    parser.add_argument("--expected-contract-sha256")
    parser.add_argument("--expected-release-version")
    parser.add_argument("--expected-mcp-version")
    parser.add_argument("--allow-unverified-candidate", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = _run(args)
        _write_report(args.output.resolve(), report)
    except (G11AuditError, GenOfficeReadOnlyError, OSError, ValueError) as exc:
        print(json.dumps({"reason_code": _reason_code(exc), "status": "failed"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
