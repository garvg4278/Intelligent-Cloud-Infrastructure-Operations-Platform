from app.ansible_orchestrator import AnsibleOrchestratorError
from app.terraform_orchestrator import TerraformOrchestratorError, TerraformResult


class FakeTerraformOrchestrator:
    """Test double standing in for a real AWS account. Configure the
    constructor flags to simulate a failing apply/destroy; everything else
    records what was called so tests can assert on it.
    """

    def __init__(
        self,
        raise_on_apply: bool = False,
        raise_on_destroy: bool = False,
        outputs: dict | None = None,
    ):
        self.raise_on_apply = raise_on_apply
        self.raise_on_destroy = raise_on_destroy
        self.outputs = outputs if outputs is not None else {
            "cluster_name": "icop-staging",
            "ssm_transfer_bucket": "icop-staging-icop-ssm-transfer",
        }
        self.applied: list[str] = []
        self.destroyed: list[str] = []

    def apply(self, environment_dir: str) -> TerraformResult:
        if self.raise_on_apply:
            raise TerraformOrchestratorError("simulated terraform apply failure")
        self.applied.append(environment_dir)
        return TerraformResult(outputs=self.outputs)

    def destroy(self, environment_dir: str) -> None:
        if self.raise_on_destroy:
            raise TerraformOrchestratorError("simulated terraform destroy failure")
        self.destroyed.append(environment_dir)


class FakeAnsibleOrchestrator:
    def __init__(self, raise_on_run: bool = False):
        self.raise_on_run = raise_on_run
        self.runs: list[tuple[str, str, dict]] = []

    def run_playbook(self, playbook_path: str, inventory_path: str, extra_vars: dict) -> None:
        if self.raise_on_run:
            raise AnsibleOrchestratorError("simulated ansible-playbook failure")
        self.runs.append((playbook_path, inventory_path, extra_vars))


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
