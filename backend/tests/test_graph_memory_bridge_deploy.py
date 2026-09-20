import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).parents[2]
    / "integrations"
    / "openclaw"
    / "graph-memory"
    / "deploy.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("graph_memory_bridge_deploy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _plugin(tmp_path):
    target = tmp_path / "graph-memory"
    target.mkdir()
    (target / "package.json").write_text(
        json.dumps({"name": "graph-memory", "version": "9.9.9"}),
        encoding="utf-8",
    )
    (target / "openclaw.plugin.json").write_text(
        json.dumps({"id": "graph-memory", "version": "9.9.9"}),
        encoding="utf-8",
    )
    (target / "index.ts").write_text(
        '\n'.join([
            'import { registerDashboardRoutes } from "./src/http/dashboard";',
            "const plugin = {",
            "  register(api: unknown) {",
            "    registerDashboardRoutes(api);",
            "  },",
            "};",
        ]) + "\n",
        encoding="utf-8",
    )
    vitest = target / "node_modules" / ".bin" / "vitest"
    vitest.parent.mkdir(parents=True)
    vitest.write_text("fixture", encoding="utf-8")
    return target


def test_patch_index_is_idempotent_and_requires_compatible_anchors():
    module = _module()
    source = (
        'import { registerDashboardRoutes } from "./src/http/dashboard";\n'
        "    registerDashboardRoutes(api);\n"
    )
    patched = module.patch_index(source)

    assert module.patch_index(patched) == patched
    assert patched.count("registerApprovedProjectionRoutes") == 2
    with pytest.raises(module.DeploymentError, match="anchor"):
        module.patch_index("export default {};\n")


def test_deploy_builds_tests_records_version_and_becomes_noop(tmp_path):
    module = _module()
    target = _plugin(tmp_path)
    commands = []

    def runner(arguments, cwd):
        commands.append(arguments)
        dist_bridge = cwd / "dist" / "src" / "http" / "approved-projection.js"
        dist_bridge.parent.mkdir(parents=True, exist_ok=True)
        dist_bridge.write_text(
            'const a = "/graph-memory/v1/retrieve-context";\n'
            'const b = "/graph-memory/v1/upsert-projection";\n',
            encoding="utf-8",
        )
        (cwd / "dist" / "index.js").write_text(
            "registerApprovedProjectionRoutes(api);\n",
            encoding="utf-8",
        )

    result = module.deploy(
        target,
        backup_root=tmp_path / "backups",
        command_runner=runner,
    )

    assert result["changed"] is True
    assert result["status"]["ready"] is True
    assert len(commands) == 2
    manifest = json.loads((target / module.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["plugin_version"] == "9.9.9"
    assert module.deploy(
        target,
        backup_root=tmp_path / "backups",
        command_runner=runner,
    )["changed"] is False


def test_failed_verification_restores_original_plugin(tmp_path):
    module = _module()
    target = _plugin(tmp_path)
    original = (target / "index.ts").read_text(encoding="utf-8")

    def fail(_arguments, _cwd):
        raise module.DeploymentError("synthetic failure")

    with pytest.raises(module.DeploymentError, match="rolled back"):
        module.deploy(
            target,
            backup_root=tmp_path / "backups",
            command_runner=fail,
        )

    assert (target / "index.ts").read_text(encoding="utf-8") == original
    assert not (target / "src" / "http" / "approved-projection.ts").exists()
    assert not (target / module.MANIFEST_NAME).exists()


def test_plugin_version_change_invalidates_verified_manifest(tmp_path):
    module = _module()
    target = _plugin(tmp_path)

    def runner(_arguments, cwd):
        dist_bridge = cwd / "dist" / "src" / "http" / "approved-projection.js"
        dist_bridge.parent.mkdir(parents=True, exist_ok=True)
        dist_bridge.write_text(
            'const a = "/graph-memory/v1/retrieve-context";\n'
            'const b = "/graph-memory/v1/upsert-projection";\n',
            encoding="utf-8",
        )
        (cwd / "dist" / "index.js").write_text(
            "registerApprovedProjectionRoutes(api);\n",
            encoding="utf-8",
        )

    module.deploy(target, backup_root=tmp_path / "backups", command_runner=runner)
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    package["version"] = "10.0.0"
    (target / "package.json").write_text(json.dumps(package), encoding="utf-8")

    status = module.inspect_deployment(target)

    assert status["ready"] is False
    assert "manifest:plugin_version" in status["failed_checks"]
