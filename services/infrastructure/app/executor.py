"""The actual environment provisioning/destroy state machine. Pure
business logic -- no Celery import here on purpose, mirroring
services/deployment/app/executor.py's same reasoning: testable by calling
provision_environment()/destroy_environment() directly, with any
orchestrator implementations, no task queue involved at all.
"""

import logging

from . import crud, models
from .ansible_orchestrator import AnsibleOrchestrator, AnsibleOrchestratorError
from .audit_client import record_safely
from .config import settings
from .database import get_db_session
from .terraform_orchestrator import TerraformOrchestrator, TerraformOrchestratorError

logger = logging.getLogger(__name__)


def _audit(
    environment_id: str, action: str, error: str | None = None, after_state: dict | None = None
) -> None:
    record_safely(
        actor="system",
        action=action,
        resource_type="environment",
        resource_id=environment_id,
        after_state=after_state if after_state is not None else ({"error": error} if error else None),
    )


def _environment_dir(environment: models.Environment) -> str:
    return f"{settings.TERRAFORM_ROOT}/environments/{environment.environment_type.value}"


def provision_environment(
    environment_id: str,
    terraform: TerraformOrchestrator,
    ansible: AnsibleOrchestrator,
) -> None:
    with get_db_session() as db:
        environment = crud.get_environment(db, environment_id)
        if environment is None:
            logger.warning("environment %s not found, nothing to provision", environment_id)
            return

        try:
            _run_provision(db, environment, terraform, ansible)
        except Exception as exc:  # noqa: BLE001 -- deliberate last-resort net,
            # same reasoning as services/deployment/app/executor.py's
            # identical pattern: a background job that raises out to its
            # caller leaves this row stuck at "provisioning_infra"/
            # "configuring_nodes" forever, invisible to anyone watching the
            # API. Recording the real error and landing on a terminal
            # status is a better outcome than that, even for a failure
            # mode this code didn't specifically anticipate.
            logger.exception("environment %s provisioning failed unexpectedly", environment_id)
            crud.update_status(
                db, environment, models.EnvironmentStatus.provision_failed, error=f"unexpected error: {exc}"
            )
            _audit(environment.id, "environment.provision_failed", error=f"unexpected error: {exc}")


def _run_provision(
    db, environment: models.Environment, terraform: TerraformOrchestrator, ansible: AnsibleOrchestrator
) -> None:
    environment_dir = _environment_dir(environment)

    crud.update_status(db, environment, models.EnvironmentStatus.provisioning_infra)
    try:
        tf_result = terraform.apply(environment_dir)
    except TerraformOrchestratorError as exc:
        crud.update_status(db, environment, models.EnvironmentStatus.provision_failed, error=str(exc))
        _audit(environment.id, "environment.provision_failed", error=str(exc))
        return

    cluster_name = tf_result.outputs.get("cluster_name")
    crud.update_status(db, environment, models.EnvironmentStatus.configuring_nodes, cluster_name=cluster_name)

    try:
        ansible.run_playbook(
            playbook_path=f"{settings.ANSIBLE_ROOT}/playbooks/site.yml",
            inventory_path=f"{settings.ANSIBLE_ROOT}/inventory/aws_ec2.yml",
            extra_vars={"ssm_transfer_bucket": tf_result.outputs.get("ssm_transfer_bucket", "")},
        )
    except AnsibleOrchestratorError as exc:
        # Infra already exists at this point -- terraform apply already
        # succeeded, only node configuration failed. Landing on
        # provision_failed (rather than inventing a third distinct status)
        # still tells an operator "not usable yet", and cluster_name is
        # already recorded above for them to go debug the partial state
        # directly rather than being forced to destroy and retry from zero.
        error = f"infrastructure provisioned but node configuration failed: {exc}"
        crud.update_status(db, environment, models.EnvironmentStatus.provision_failed, error=error)
        _audit(environment.id, "environment.provision_failed", error=error)
        return

    crud.update_status(db, environment, models.EnvironmentStatus.ready)
    _audit(environment.id, "environment.ready", after_state={"cluster_name": cluster_name})


def destroy_environment(environment_id: str, terraform: TerraformOrchestrator) -> None:
    with get_db_session() as db:
        environment = crud.get_environment(db, environment_id)
        if environment is None:
            logger.warning("environment %s not found, nothing to destroy", environment_id)
            return

        try:
            terraform.destroy(_environment_dir(environment))
        except TerraformOrchestratorError as exc:
            crud.update_status(db, environment, models.EnvironmentStatus.destroy_failed, error=str(exc))
            _audit(environment.id, "environment.destroy_failed", error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- same last-resort reasoning as provision_environment above
            logger.exception("environment %s destroy failed unexpectedly", environment_id)
            crud.update_status(
                db, environment, models.EnvironmentStatus.destroy_failed, error=f"unexpected error: {exc}"
            )
            _audit(environment.id, "environment.destroy_failed", error=f"unexpected error: {exc}")
            return

        crud.update_status(db, environment, models.EnvironmentStatus.destroyed)
        _audit(environment.id, "environment.destroyed")
