"""Unit tests for TerraformCLI's command construction and result handling,
with subprocess.run mocked out. These verify MY code builds the right
terraform invocations and interprets their results correctly -- they do
not verify that a real AWS account accepts those commands, since no cloud
account is available here. See terraform/README.md for what is and isn't
validated for the HCL itself.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.terraform_orchestrator import TerraformCLI, TerraformOrchestratorError


@pytest.fixture()
def orch():
    return TerraformCLI(apply_timeout_seconds=1800)


def test_apply_runs_init_then_apply_then_reads_outputs(orch):
    with patch("app.terraform_orchestrator.subprocess.run") as mock_run:
        outputs_json = json.dumps({
            "cluster_name": {"value": "icop-staging", "type": "string", "sensitive": False},
            "ssm_transfer_bucket": {"value": "icop-staging-icop-ssm-transfer", "type": "string", "sensitive": False},
        })
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # init
            MagicMock(returncode=0, stdout="", stderr=""),  # apply
            MagicMock(returncode=0, stdout=outputs_json, stderr=""),  # output -json
        ]

        result = orch.apply("/terraform/environments/staging")

        assert result.outputs["cluster_name"] == "icop-staging"
        assert result.outputs["ssm_transfer_bucket"] == "icop-staging-icop-ssm-transfer"

        init_cmd = mock_run.call_args_list[0][0][0]
        apply_cmd = mock_run.call_args_list[1][0][0]
        output_cmd = mock_run.call_args_list[2][0][0]

        assert init_cmd == ["terraform", "-chdir=/terraform/environments/staging", "init", "-input=false"]
        assert apply_cmd == [
            "terraform", "-chdir=/terraform/environments/staging", "apply", "-auto-approve", "-input=false",
        ]
        assert output_cmd == ["terraform", "-chdir=/terraform/environments/staging", "output", "-json"]


def test_apply_raises_on_init_failure_without_attempting_apply(orch):
    with patch("app.terraform_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: no valid credential sources")
        with pytest.raises(TerraformOrchestratorError) as exc_info:
            orch.apply("/terraform/environments/staging")
        assert "no valid credential sources" in exc_info.value.stderr
        assert mock_run.call_count == 1  # never reached apply


def test_apply_raises_on_apply_failure(orch):
    with patch("app.terraform_orchestrator.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # init succeeds
            MagicMock(returncode=1, stdout="", stderr="Error: creating EKS Cluster: quota exceeded"),
        ]
        with pytest.raises(TerraformOrchestratorError) as exc_info:
            orch.apply("/terraform/environments/staging")
        assert "quota exceeded" in exc_info.value.stderr


def test_destroy_runs_init_then_destroy(orch):
    with patch("app.terraform_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        orch.destroy("/terraform/environments/staging")

        destroy_cmd = mock_run.call_args_list[1][0][0]
        assert destroy_cmd == [
            "terraform", "-chdir=/terraform/environments/staging", "destroy", "-auto-approve", "-input=false",
        ]


def test_apply_uses_configured_timeout(orch):
    short_orch = TerraformCLI(apply_timeout_seconds=42)
    with patch("app.terraform_orchestrator.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="terraform", timeout=42)
        with pytest.raises(TerraformOrchestratorError, match="timed out after 42s"):
            short_orch._run(["terraform", "apply"], timeout=42)


def test_missing_binary_raises_clean_orchestrator_error(orch):
    with (
        patch("app.terraform_orchestrator.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(TerraformOrchestratorError, match="command not found"),
    ):
        orch.destroy("/terraform/environments/staging")
