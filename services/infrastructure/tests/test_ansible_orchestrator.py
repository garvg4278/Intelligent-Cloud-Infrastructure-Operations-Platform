"""Unit tests for AnsibleRunner's command construction and result handling,
with subprocess.run mocked out. Same reasoning as
test_terraform_orchestrator.py: verifies MY code builds the right
ansible-playbook invocation, not that a real EKS node accepts it.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.ansible_orchestrator import AnsibleOrchestratorError, AnsibleRunner


@pytest.fixture()
def orch():
    return AnsibleRunner(run_timeout_seconds=900)


def test_run_playbook_invokes_ansible_playbook_with_inventory_and_extra_vars(orch):
    with patch("app.ansible_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        orch.run_playbook(
            playbook_path="/ansible/playbooks/site.yml",
            inventory_path="/ansible/inventory/aws_ec2.yml",
            extra_vars={"ssm_transfer_bucket": "icop-staging-icop-ssm-transfer"},
        )

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ansible-playbook"
        assert "-i" in cmd
        assert cmd[cmd.index("-i") + 1] == "/ansible/inventory/aws_ec2.yml"
        assert "/ansible/playbooks/site.yml" in cmd
        assert "--extra-vars" in cmd
        extra_vars_json = cmd[cmd.index("--extra-vars") + 1]
        assert json.loads(extra_vars_json) == {"ssm_transfer_bucket": "icop-staging-icop-ssm-transfer"}


def test_run_playbook_raises_on_nonzero_exit(orch):
    with patch("app.ansible_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=2, stdout="", stderr="ERROR! the playbook could not be found"
        )
        with pytest.raises(AnsibleOrchestratorError) as exc_info:
            orch.run_playbook("/bad/path.yml", "/ansible/inventory/aws_ec2.yml", {})
        assert "could not be found" in exc_info.value.stderr


def test_run_playbook_raises_on_timeout(orch):
    with patch("app.ansible_orchestrator.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ansible-playbook", timeout=900)
        with pytest.raises(AnsibleOrchestratorError, match="timed out after 900s"):
            orch.run_playbook("/ansible/playbooks/site.yml", "/ansible/inventory/aws_ec2.yml", {})


def test_missing_binary_raises_clean_orchestrator_error(orch):
    with (
        patch("app.ansible_orchestrator.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(AnsibleOrchestratorError, match="command not found"),
    ):
        orch.run_playbook("/ansible/playbooks/site.yml", "/ansible/inventory/aws_ec2.yml", {})
