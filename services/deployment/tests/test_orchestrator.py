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


def test_deploy_invokes_helm_upgrade_install_with_flattened_values(orch):
    with patch("app.orchestrator.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # helm upgrade --install
            MagicMock(returncode=0, stdout=json.dumps([{"revision": 1}, {"revision": 2}]), stderr=""),
        ]

        result = orch.deploy(
            "auth", "/charts/service-chart", "local", {"image": {"tag": "v2", "repository": "auth"}}
        )

        assert result.revision == 2
        upgrade_cmd = mock_run.call_args_list[0][0][0]
        assert upgrade_cmd[:3] == ["helm", "upgrade", "--install"]
        assert upgrade_cmd[3] == "auth"
        assert upgrade_cmd[4] == "/charts/service-chart"
        assert "--namespace" in upgrade_cmd and "local" in upgrade_cmd
        assert "--set" in upgrade_cmd
        assert "image.tag=v2" in upgrade_cmd
        assert "image.repository=auth" in upgrade_cmd


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
