from app.orchestrator import DeployResult, OrchestratorError


class FakeOrchestrator:
    """Test double standing in for a real cluster. Configure the
    constructor flags to simulate a failing deploy or a failing health
    check; everything else records what was called so tests can assert
    on it.
    """

    def __init__(self, fail_health_check: bool = False, raise_on_deploy: bool = False):
        self.fail_health_check = fail_health_check
        self.raise_on_deploy = raise_on_deploy
        self.deployed: list[tuple[str, dict]] = []
        self.rolled_back: list[tuple[str, int | None]] = []
        self._revision = 0

    def deploy(self, release_name: str, chart_path: str, namespace: str, values: dict) -> DeployResult:
        if self.raise_on_deploy:
            raise OrchestratorError("simulated deploy failure")
        self._revision += 1
        self.deployed.append((release_name, values))
        return DeployResult(revision=self._revision)

    def check_rollout_health(self, release_name: str, namespace: str, timeout_seconds: int) -> bool:
        return not self.fail_health_check

    def rollback(self, release_name: str, namespace: str, to_revision: int | None = None) -> None:
        self.rolled_back.append((release_name, to_revision))


class FakeAuditClient:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.calls: list[dict] = []

    def record(self, actor, action, resource_type, resource_id, before_state=None, after_state=None):
        if self.raise_error:
            from app.audit_client import AuditClientError

            raise AuditClientError("simulated audit service failure")
        self.calls.append(
            {
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "before_state": before_state,
                "after_state": after_state,
            }
        )
