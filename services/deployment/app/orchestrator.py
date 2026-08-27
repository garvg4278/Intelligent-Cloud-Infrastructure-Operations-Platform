"""Talks to Helm/kubectl. This is the one module in this service that
shells out to real infrastructure tooling -- everything else in the
service only ever talks to this through the Orchestrator protocol, so the
state-machine logic in executor.py is fully testable without a cluster.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Protocol


class OrchestratorError(Exception):
    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class DeployResult:
    revision: int


class Orchestrator(Protocol):
    def deploy(self, release_name: str, chart_path: str, namespace: str, values: dict) -> DeployResult: ...

    def check_rollout_health(self, release_name: str, namespace: str, timeout_seconds: int) -> bool: ...

    def rollback(self, release_name: str, namespace: str, to_revision: int | None = None) -> None: ...


def _flatten(values: dict, prefix: str = "") -> dict[str, str]:
    """helm --set uses dotted paths, e.g. --set image.tag=v2 -- flatten a
    nested dict of values into that form."""
    out: dict[str, str] = {}
    for key, value in values.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_flatten(value, full_key))
        else:
            out[full_key] = str(value)
    return out


class HelmOrchestrator:
    """Real implementation: shells out to the `helm` and `kubectl` CLIs,
    which must be present on PATH and configured with a working kubeconfig
    (see the deployment service's Dockerfile and docker-compose.yml).
    """

    def deploy(self, release_name: str, chart_path: str, namespace: str, values: dict) -> DeployResult:
        set_args: list[str] = []
        for key, value in _flatten(values).items():
            set_args += ["--set", f"{key}={value}"]

        self._run(
            [
                "helm", "upgrade", "--install", release_name, chart_path,
                "--namespace", namespace, "--create-namespace",
                *set_args,
            ]
        )
        return DeployResult(revision=self._current_revision(release_name, namespace))

    def check_rollout_health(self, release_name: str, namespace: str, timeout_seconds: int) -> bool:
        try:
            self._run(
                [
                    "kubectl", "rollout", "status", f"deployment/{release_name}",
                    "--namespace", namespace, f"--timeout={timeout_seconds}s",
                ],
                timeout=timeout_seconds + 10,
            )
            return True
        except OrchestratorError:
            return False

    def rollback(self, release_name: str, namespace: str, to_revision: int | None = None) -> None:
        cmd = ["helm", "rollback", release_name]
        if to_revision is not None:
            cmd.append(str(to_revision))
        cmd += ["--namespace", namespace]
        self._run(cmd)

    def _current_revision(self, release_name: str, namespace: str) -> int:
        result = self._run(["helm", "history", release_name, "--namespace", namespace, "-o", "json"])
        history = json.loads(result.stdout)
        return max(item["revision"] for item in history)

    def _run(self, cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OrchestratorError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
        except FileNotFoundError as exc:
            raise OrchestratorError(f"command not found: {cmd[0]} (is it installed on PATH?)") from exc

        if result.returncode != 0:
            raise OrchestratorError(
                f"command failed ({result.returncode}): {' '.join(cmd)}",
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = HelmOrchestrator()
    return _orchestrator


def set_orchestrator(orchestrator: Orchestrator | None) -> None:
    """Test hook: inject a fake orchestrator instead of the real Helm one."""
    global _orchestrator
    _orchestrator = orchestrator
