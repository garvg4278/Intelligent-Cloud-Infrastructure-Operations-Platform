"""Talks to the `ansible-playbook` CLI. Same reasoning and shape as
terraform_orchestrator.py in this service and
services/deployment/app/orchestrator.py in the deployment service -- one
real subprocess-shelling module, everything else talks to it through the
AnsibleOrchestrator protocol.
"""

from __future__ import annotations

import json
import subprocess
from typing import Protocol


class AnsibleOrchestratorError(Exception):
    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class AnsibleOrchestrator(Protocol):
    def run_playbook(self, playbook_path: str, inventory_path: str, extra_vars: dict) -> None: ...


class AnsibleRunner:
    """Real implementation: shells out to `ansible-playbook`, which must be
    on PATH along with the amazon.aws collection (see
    ansible/requirements.yml) and the AWS Session Manager plugin -- see
    ansible/README.md for why: every host this ever actually reaches is
    over SSM, not SSH, so both are baked into this service's Dockerfile
    rather than assumed to already be on the machine running this code.
    """

    def __init__(self, run_timeout_seconds: int = 900):
        self.run_timeout_seconds = run_timeout_seconds

    def run_playbook(self, playbook_path: str, inventory_path: str, extra_vars: dict) -> None:
        cmd = [
            "ansible-playbook",
            "-i", inventory_path,
            playbook_path,
            "--extra-vars", json.dumps(extra_vars),
        ]
        self._run(cmd, timeout=self.run_timeout_seconds)

    def _run(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise AnsibleOrchestratorError(
                f"command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            raise AnsibleOrchestratorError(
                f"command not found: {cmd[0]} (is it installed on PATH?)"
            ) from exc

        if result.returncode != 0:
            raise AnsibleOrchestratorError(
                f"command failed ({result.returncode}): {' '.join(cmd)}",
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result


_ansible_orchestrator: AnsibleOrchestrator | None = None


def get_ansible_orchestrator() -> AnsibleOrchestrator:
    global _ansible_orchestrator
    if _ansible_orchestrator is None:
        from .config import settings

        _ansible_orchestrator = AnsibleRunner(run_timeout_seconds=settings.ANSIBLE_RUN_TIMEOUT_SECONDS)
    return _ansible_orchestrator


def set_ansible_orchestrator(orchestrator: AnsibleOrchestrator | None) -> None:
    """Test hook: inject a fake orchestrator instead of the real Ansible one."""
    global _ansible_orchestrator
    _ansible_orchestrator = orchestrator
