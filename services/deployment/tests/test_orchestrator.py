"""Unit tests for HelmOrchestrator's command construction and result
handling, with subprocess.run mocked out. These verify MY code builds the
right helm/kubectl invocations and interprets their results correctly --
they do not verify that a real cluster accepts those commands, since no
cluster is available here. See infra/helm/service-chart/README.md for
what is and isn't validated for the chart itself.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.orchestrator import HelmOrchestrator, OrchestratorError


@pytest.fixture()
def orch():
    return HelmOrchestrator()


def _capture_deploy(orch, values):
    """Run deploy() with subprocess mocked; returns (argv, parsed values-file
    contents). The file is deleted when deploy() returns, so it has to be read
    from inside the mocked call."""
    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["helm", "upgrade", "--install"]:
            captured["argv"] = cmd
            path = cmd[cmd.index("-f") + 1]
            captured["path"] = path
            with open(path) as handle:
                captured["values"] = json.load(handle)
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout=json.dumps([{"revision": 1}, {"revision": 2}]), stderr="")

    with patch("app.orchestrator.subprocess.run", side_effect=fake_run):
        result = orch.deploy("auth", "/charts/service-chart", "local", values)
    return result, captured


def test_deploy_invokes_helm_upgrade_install_with_a_values_file(orch):
    result, captured = _capture_deploy(orch, {"image": {"tag": "v2", "repository": "auth"}})

    assert result.revision == 2
    argv = captured["argv"]
    assert argv[:3] == ["helm", "upgrade", "--install"]
    assert argv[3] == "auth"
    assert argv[4] == "/charts/service-chart"
    assert "--namespace" in argv and "local" in argv
    assert captured["values"] == {"image": {"tag": "v2", "repository": "auth"}}
    assert "--set" not in argv and "--set-string" not in argv


def test_hostile_tag_is_data_not_helm_arguments(orch):
    """Before the fix this value became FOUR `--set` assignments (the later
    image.repository overriding the real one). In a values file it is just
    one string."""
    evil = "v1,image.repository=docker.io/attacker/miner,serviceAccount.name=privileged-sa"
    _, captured = _capture_deploy(orch, {"image": {"repository": "payments", "tag": evil}})

    assert captured["values"]["image"] == {"repository": "payments", "tag": evil}
    assert not any("attacker" in arg for arg in captured["argv"])  # never reaches the command line


def test_values_file_is_private_and_removed_after_deploy(orch):
    import os
    import stat

    seen = {}

    def fake_run(cmd, **kwargs):
        if "-f" in cmd:
            path = cmd[cmd.index("-f") + 1]
            seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
            seen["path"] = path
        return MagicMock(returncode=0, stdout=json.dumps([{"revision": 1}]), stderr="")

    with patch("app.orchestrator.subprocess.run", side_effect=fake_run):
        orch.deploy("auth", "/c", "local", {"image": {"tag": "v1"}})

    assert seen["mode"] == 0o600
    assert not os.path.exists(seen["path"])


def test_values_file_is_removed_even_when_helm_fails(orch):
    import os

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["path"] = cmd[cmd.index("-f") + 1]
        return MagicMock(returncode=1, stdout="", stderr="boom")

    with patch("app.orchestrator.subprocess.run", side_effect=fake_run), pytest.raises(OrchestratorError):
        orch.deploy("auth", "/c", "local", {"image": {"tag": "v1"}})
    assert not os.path.exists(seen["path"])


def test_deploy_raises_orchestrator_error_on_nonzero_exit(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: chart not found")
        with pytest.raises(OrchestratorError) as exc_info:
            orch.deploy("auth", "/bad/path", "local", {})
        assert "chart not found" in exc_info.value.stderr


def test_check_rollout_health_true_on_success(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="deployment successfully rolled out", stderr=""
        )
        assert orch.check_rollout_health("auth", "local", 30) is True
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "kubectl", "rollout", "status", "deployment/auth",
            "--namespace", "local", "--timeout=30s",
        ]


def test_check_rollout_health_false_on_nonzero_exit(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="timed out waiting for rollout")
        assert orch.check_rollout_health("auth", "local", 30) is False


def test_check_rollout_health_false_on_timeout(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=30)
        assert orch.check_rollout_health("auth", "local", 30) is False


def test_rollback_with_explicit_revision(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        orch.rollback("auth", "local", to_revision=3)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["helm", "rollback", "auth", "3", "--namespace", "local"]


def test_rollback_without_revision_omits_it(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        orch.rollback("auth", "local", to_revision=None)
        cmd = mock_run.call_args[0][0]
        assert cmd == ["helm", "rollback", "auth", "--namespace", "local"]


def test_missing_binary_raises_clean_orchestrator_error(orch):
    with (
        patch("app.orchestrator.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(OrchestratorError, match="command not found"),
    ):
        orch.rollback("auth", "local")
