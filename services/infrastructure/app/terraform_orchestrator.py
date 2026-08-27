"""Talks to the `terraform` CLI. This is the one module in this service
that shells out to real infrastructure-provisioning tooling for the
Terraform half of a provision/destroy -- everything else only ever talks
to this through the TerraformOrchestrator protocol, so executor.py's
state-machine logic is fully testable without a real cloud account.
Mirrors services/deployment/app/orchestrator.py's HelmOrchestrator almost
exactly -- same reasoning, same shape, a different CLI on the other end.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Protocol


class TerraformOrchestratorError(Exception):
    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class TerraformResult:
    outputs: dict[str, str] = field(default_factory=dict)


class TerraformOrchestrator(Protocol):
    def apply(self, environment_dir: str) -> TerraformResult: ...

    def destroy(self, environment_dir: str) -> None: ...


class TerraformCLI:
    """Real implementation: shells out to the `terraform` CLI, which must
    be present on PATH with AWS credentials available in the environment
    (see this service's Dockerfile and docker-compose.yml). `-chdir`
    (rather than `cd`-ing the whole process) is Terraform's own documented
    way to run against a config that isn't the current working directory
    -- `environment_dir` is always one of terraform/environments/staging
    or .../production; see executor.py for how that path gets built.
    """

    def __init__(self, apply_timeout_seconds: int = 1800):
        self.apply_timeout_seconds = apply_timeout_seconds

    def apply(self, environment_dir: str) -> TerraformResult:
        self._run(["terraform", f"-chdir={environment_dir}", "init", "-input=false"], timeout=300)
        self._run(
            ["terraform", f"-chdir={environment_dir}", "apply", "-auto-approve", "-input=false"],
            timeout=self.apply_timeout_seconds,
        )
        result = self._run(["terraform", f"-chdir={environment_dir}", "output", "-json"], timeout=60)
        raw = json.loads(result.stdout)
        # `terraform output -json` wraps every value as
        # {"value": ..., "type": ..., "sensitive": bool} -- flatten to
        # plain {name: value} for callers, same idea as HelmOrchestrator
        # parsing `helm history -o json` down to just a revision number.
        outputs = {name: str(meta.get("value", "")) for name, meta in raw.items()}
        return TerraformResult(outputs=outputs)

    def destroy(self, environment_dir: str) -> None:
        self._run(["terraform", f"-chdir={environment_dir}", "init", "-input=false"], timeout=300)
        self._run(
            ["terraform", f"-chdir={environment_dir}", "destroy", "-auto-approve", "-input=false"],
            timeout=self.apply_timeout_seconds,
        )

    def _run(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise TerraformOrchestratorError(
                f"command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            raise TerraformOrchestratorError(
                f"command not found: {cmd[0]} (is it installed on PATH?)"
            ) from exc

        if result.returncode != 0:
            raise TerraformOrchestratorError(
                f"command failed ({result.returncode}): {' '.join(cmd)}",
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result


_terraform_orchestrator: TerraformOrchestrator | None = None


def get_terraform_orchestrator() -> TerraformOrchestrator:
    global _terraform_orchestrator
    if _terraform_orchestrator is None:
        from .config import settings

        _terraform_orchestrator = TerraformCLI(apply_timeout_seconds=settings.TERRAFORM_APPLY_TIMEOUT_SECONDS)
    return _terraform_orchestrator


def set_terraform_orchestrator(orchestrator: TerraformOrchestrator | None) -> None:
    """Test hook: inject a fake orchestrator instead of the real Terraform one."""
    global _terraform_orchestrator
    _terraform_orchestrator = orchestrator
