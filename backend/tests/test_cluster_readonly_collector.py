"""Read-only collection does not accept commands from discovered peers."""
import json
from pathlib import Path
import plistlib
import subprocess
from unittest.mock import Mock

import pytest

from services.cluster_collector import (
    collection_target, collect_node, discover, probe_service, validate_config,
)


def config():
    return {"nodes": [{"node_id": "mini", "tailscale_id": "nMini", "managed": True,
                       "collector": {"transport": "ssh", "user": "apple"}}]}


def test_target_uses_stable_identity_not_configured_or_advertised_hostname():
    status = {"Self": {}, "Peer": {"key": {"ID": "nMini", "HostName": "host; touch /tmp/bad",
              "Online": True, "TailscaleIPs": ["192.168.1.1", "100.81.208.50"]}}}
    assert collection_target(config()["nodes"][0], status) == "100.81.208.50"
    status["Peer"]["key"]["Expired"] = True
    assert collection_target(config()["nodes"][0], status) is None


@pytest.mark.parametrize("user", ["-oProxyCommand=bad", "a;bad", "a b", "root\ncmd"])
def test_unsafe_ssh_user_is_rejected(user):
    value = config()
    value["nodes"][0]["collector"]["user"] = user
    with pytest.raises(ValueError):
        validate_config(value)


def test_discovery_failure_not_empty_success():
    runner = Mock(side_effect=subprocess.TimeoutExpired("tailscale", 10))
    with pytest.raises(RuntimeError, match="discovery_timeout"):
        discover("/trusted/tailscale", runner=runner)


def test_launchd_explicitly_selects_tailscale_cli_mode():
    # LaunchAgents lack terminal-mode hints. Force the documented CLI mode
    # instead of letting the macOS app executable try to start its GUI.
    plist = Path(__file__).resolve().parents[1] / "ai.openclaw.cluster-monitor.plist"
    with plist.open("rb") as stream:
        launch_agent = plistlib.load(stream)
    assert launch_agent["EnvironmentVariables"]["TAILSCALE_BE_CLI"] == "1"


def test_discovery_requires_running_and_self_identity():
    for payload in [{"BackendState": "Stopped"}, {"BackendState": "Running", "Self": {}}]:
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps(payload)))
        with pytest.raises(RuntimeError, match="discovery_not_ready"):
            discover("/trusted/tailscale", runner=runner)


def test_ssh_is_fixed_read_only_and_noninteractive():
    runner = Mock(return_value=Mock(returncode=0, stdout='{"cpu_logical_count":8,"memory_percent":42}'))
    node = config()["nodes"][0]
    result = collect_node(node, "100.81.208.50", runner=runner)
    argv = runner.call_args.args[0]
    assert argv[0] == "/usr/bin/ssh"
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert "IdentitiesOnly=yes" in argv and argv[1:3] == ["-F", "/dev/null"]
    assert argv[-2:] == ["apple@100.81.208.50", "python3 -"]
    assert runner.call_args.kwargs.get("shell", False) is False
    assert result["metrics"]["cpu_logical_count"] == 8
    assert result["observed_at"].tzinfo is not None


@pytest.mark.parametrize("patch", [
    {"managed": "false"}, {"maintenance": 1}, {"collector": []},
    {"services": {}}, {"services": [None]}, {"tailscale_id": "bad;id"},
])
def test_invalid_declarative_config_cannot_trigger_probes(patch):
    value = config()
    value["nodes"][0].update(patch)
    with pytest.raises(ValueError):
        validate_config(value)


@pytest.mark.parametrize("count", [True, "8", 0, -1, None, 999999])
def test_invalid_hardware_count_is_not_a_fresh_receipt(count):
    runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps({"cpu_logical_count": count})))
    result = collect_node(config()["nodes"][0], "100.81.208.50", runner=runner)
    assert result["error"] == "probe_unavailable"
    assert result["metrics"] == {}


def test_failed_collection_never_becomes_zero_metrics_or_leaks_stderr():
    runner = Mock(return_value=Mock(returncode=255, stdout="", stderr="secret=password"))
    result = collect_node(config()["nodes"][0], "100.81.208.50", runner=runner)
    assert result["metrics"] == {}
    assert result["error"] == "ssh_unavailable"
    assert "password" not in str(result)


def test_service_probe_requires_tailnet_target_not_arbitrary_urls():
    with pytest.raises(ValueError):
        probe_service("8.8.8.8", {"name": "bad", "port": 80, "path": "/"})
    with pytest.raises(ValueError):
        probe_service("100.81.208.50", {"name": "bad", "port": 3021, "path": "//other/"})
