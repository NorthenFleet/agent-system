#!/usr/bin/env python3
"""Version-aware deployment and rollback for the 3021 graph-memory bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SOURCE_ROOT = Path(__file__).resolve().parent
DEFAULT_TARGET = Path(os.path.expanduser("~/.openclaw/extensions/graph-memory"))
DEFAULT_BACKUP_ROOT = Path(os.path.expanduser("~/.openclaw/backups/graph-memory-approved-bridge"))
MANIFEST_NAME = ".agent-system-approved-projection.json"
BRIDGE_SCHEMA = "approved-projection.v2"
IMPORT_LINE = 'import { registerApprovedProjectionRoutes } from "./src/http/approved-projection";'
REGISTER_LINE = "    registerApprovedProjectionRoutes(api);"
IMPORT_ANCHOR = 'import { registerDashboardRoutes } from "./src/http/dashboard";'
REGISTER_ANCHOR = "    registerDashboardRoutes(api);"
MAPPINGS = {
    "approved-projection.ts": "src/http/approved-projection.ts",
    "approved-projection.test.ts": "test/approved-projection.test.ts",
    "openclaw-plugin-sdk.d.ts": "src/openclaw-plugin-sdk.d.ts",
}


class DeploymentError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"JSON file must contain an object: {path}")
    return value


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def plugin_metadata(target: Path) -> dict[str, str]:
    package = _read_json(target / "package.json")
    descriptor = _read_json(target / "openclaw.plugin.json")
    if package.get("name") != "graph-memory" or descriptor.get("id") != "graph-memory":
        raise DeploymentError(f"target is not the graph-memory plugin: {target}")
    if not (target / "index.ts").is_file():
        raise DeploymentError(f"graph-memory index.ts is missing: {target}")
    return {
        "package_name": str(package.get("name")),
        "plugin_id": str(descriptor.get("id")),
        "plugin_version": str(package.get("version") or descriptor.get("version") or "unknown"),
    }


def patch_index(source: str) -> str:
    import_count = source.count(IMPORT_LINE)
    register_count = source.count(REGISTER_LINE.strip())
    if import_count > 1 or register_count > 1:
        raise DeploymentError("approved-projection hooks are duplicated in index.ts")
    result = source
    if import_count == 0:
        if result.count(IMPORT_ANCHOR) != 1:
            raise DeploymentError("compatible dashboard import anchor was not found in index.ts")
        result = result.replace(IMPORT_ANCHOR, f"{IMPORT_ANCHOR}\n{IMPORT_LINE}", 1)
    if register_count == 0:
        if result.count(REGISTER_ANCHOR) != 1:
            raise DeploymentError("compatible dashboard registration anchor was not found in index.ts")
        result = result.replace(REGISTER_ANCHOR, f"{REGISTER_ANCHOR}\n{REGISTER_LINE}", 1)
    if result.count(IMPORT_LINE) != 1 or result.count(REGISTER_LINE.strip()) != 1:
        raise DeploymentError("approved-projection hooks could not be installed exactly once")
    return result


def source_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for source_name in MAPPINGS:
        source = SOURCE_ROOT / source_name
        if not source.is_file():
            raise DeploymentError(f"bridge source is missing: {source}")
        hashes[source_name] = _sha256(source)
    return hashes


def inspect_deployment(target: Path) -> dict[str, Any]:
    metadata = plugin_metadata(target)
    expected_hashes = source_hashes()
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    for source_name, relative_target in MAPPINGS.items():
        deployed = target / relative_target
        current_hash = _sha256(deployed) if deployed.is_file() else ""
        checks[f"source:{relative_target}"] = current_hash == expected_hashes[source_name]
        details[f"hash:{relative_target}"] = current_hash

    index_source = (target / "index.ts").read_text(encoding="utf-8")
    checks["index:import_once"] = index_source.count(IMPORT_LINE) == 1
    checks["index:register_once"] = index_source.count(REGISTER_LINE.strip()) == 1

    dist_index = target / "dist" / "index.js"
    dist_bridge = target / "dist" / "src" / "http" / "approved-projection.js"
    dist_index_source = dist_index.read_text(encoding="utf-8") if dist_index.is_file() else ""
    dist_bridge_source = dist_bridge.read_text(encoding="utf-8") if dist_bridge.is_file() else ""
    checks["dist:registered"] = (
        "registerApprovedProjectionRoutes" in dist_index_source
        and "registerApprovedProjectionRoutes(api)" in dist_index_source
    )
    checks["dist:routes"] = (
        "/graph-memory/v1/retrieve-context" in dist_bridge_source
        and "/graph-memory/v1/upsert-projection" in dist_bridge_source
        and "/graph-memory/v1/projection-inventory" in dist_bridge_source
    )

    manifest_path = target / MANIFEST_NAME
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = _read_json(manifest_path)
        except DeploymentError:
            manifest = {}
    checks["manifest:schema"] = manifest.get("bridge_schema") == BRIDGE_SCHEMA
    checks["manifest:plugin_version"] = manifest.get("plugin_version") == metadata["plugin_version"]
    checks["manifest:source_hashes"] = manifest.get("source_hashes") == expected_hashes

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "ready": not failed,
        "target": str(target),
        **metadata,
        "bridge_schema": BRIDGE_SCHEMA,
        "checks": checks,
        "failed_checks": failed,
        "details": details,
        "manifest": manifest,
    }


def _backup(target: Path, backup_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / f"{stamp}-{os.getpid()}"
    backup.mkdir(parents=True, exist_ok=False)
    managed = ["index.ts", MANIFEST_NAME, *MAPPINGS.values()]
    existence: dict[str, bool] = {}
    for relative in managed:
        source = target / relative
        existence[relative] = source.is_file()
        if source.is_file():
            destination = backup / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    dist = target / "dist"
    dist_exists = dist.is_dir()
    if dist_exists:
        shutil.copytree(dist, backup / "dist")
    metadata = {
        "schema_version": "graph-memory-bridge-backup.v1",
        "created_at": _now(),
        "target": str(target.resolve()),
        "managed_files": existence,
        "dist_existed": dist_exists,
    }
    _atomic_text(backup / "backup.json", json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return backup


def restore_backup(target: Path, backup: Path) -> dict[str, Any]:
    plugin_metadata(target)
    metadata = _read_json(backup / "backup.json")
    if Path(str(metadata.get("target") or "")).resolve() != target.resolve():
        raise DeploymentError("backup target does not match requested plugin target")
    managed = metadata.get("managed_files")
    if not isinstance(managed, dict):
        raise DeploymentError("backup manifest has no managed file inventory")
    for relative, existed in managed.items():
        destination = target / str(relative)
        if existed:
            source = backup / "files" / str(relative)
            if not source.is_file():
                raise DeploymentError(f"backup file is missing: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        elif destination.is_file():
            destination.unlink()
    dist = target / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    if metadata.get("dist_existed"):
        backup_dist = backup / "dist"
        if not backup_dist.is_dir():
            raise DeploymentError("backup dist directory is missing")
        shutil.copytree(backup_dist, dist)
    return {"restored": True, "target": str(target), "backup": str(backup)}


CommandRunner = Callable[[list[str], Path], None]


def _run_command(arguments: list[str], cwd: Path) -> None:
    try:
        subprocess.run(arguments, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DeploymentError(f"verification command failed: {' '.join(arguments)}") from exc


def deploy(
    target: Path,
    *,
    backup_root: Path,
    force: bool = False,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    metadata = plugin_metadata(target)
    before = inspect_deployment(target)
    if before["ready"] and not force:
        return {"changed": False, "backup": None, "status": before}

    backup = _backup(target, backup_root)
    try:
        for source_name, relative_target in MAPPINGS.items():
            destination = target / relative_target
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE_ROOT / source_name, destination)
        index_path = target / "index.ts"
        patched = patch_index(index_path.read_text(encoding="utf-8"))
        _atomic_text(index_path, patched)

        command_runner(["npm", "run", "build"], target)
        vitest = target / "node_modules" / ".bin" / "vitest"
        if not vitest.is_file():
            raise DeploymentError(f"local vitest executable is missing: {vitest}")
        command_runner(
            [
                str(vitest),
                "run",
                "test/approved-projection.test.ts",
                "test/dashboard-http.test.ts",
            ],
            target,
        )

        provisional = inspect_deployment(target)
        dist_failures = [name for name in provisional["failed_checks"] if name.startswith("dist:")]
        if dist_failures:
            raise DeploymentError(f"compiled bridge verification failed: {', '.join(dist_failures)}")
        manifest = {
            "bridge_schema": BRIDGE_SCHEMA,
            "deployed_at": _now(),
            "plugin_version": metadata["plugin_version"],
            "source_hashes": source_hashes(),
            "verification": {
                "build": "passed",
                "tests": ["approved-projection.test.ts", "dashboard-http.test.ts"],
            },
        }
        _atomic_text(
            target / MANIFEST_NAME,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        status = inspect_deployment(target)
        if not status["ready"]:
            raise DeploymentError(f"post-deployment checks failed: {', '.join(status['failed_checks'])}")
        return {"changed": True, "backup": str(backup), "status": status}
    except Exception as exc:
        rollback = restore_backup(target, backup)
        raise DeploymentError(f"deployment failed and was rolled back from {rollback['backup']}: {exc}") from exc


def restart_gateway() -> None:
    _run_command(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/ai.openclaw.gateway"],
        Path.cwd(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    deploy_parser.add_argument("--force", action="store_true")
    deploy_parser.add_argument("--restart", action="store_true")
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--backup", type=Path, required=True)
    rollback_parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "check":
            result = inspect_deployment(args.target)
            exit_code = 0 if result["ready"] else 2
        elif args.command == "deploy":
            result = deploy(
                args.target,
                backup_root=args.backup_root,
                force=args.force,
            )
            if args.restart and result["changed"]:
                restart_gateway()
                result["gateway_restarted"] = True
            exit_code = 0
        else:
            result = restore_backup(args.target, args.backup)
            if args.restart:
                restart_gateway()
                result["gateway_restarted"] = True
            result["status"] = inspect_deployment(args.target)
            exit_code = 0
    except DeploymentError as exc:
        result = {"success": False, "error": str(exc)}
        exit_code = 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
