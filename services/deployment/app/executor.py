"""The actual deployment state machine. Pure business logic -- no Celery
import here on purpose, so it's testable by calling execute_deployment()
directly, with any Orchestrator implementation, with no task queue
involved at all.
"""

import logging

from . import crud, models
from .audit_client import record_safely
from .config import settings
from .database import get_db_session
from .orchestrator import Orchestrator, OrchestratorError

logger = logging.getLogger(__name__)


def _audit_terminal(deployment_id: str, action: str, error: str | None = None) -> None:
    record_safely(
        actor="system",
        action=action,
        resource_type="deployment",
        resource_id=deployment_id,
        after_state={"error": error} if error else None,
    )


def execute_deployment(deployment_id: str, orchestrator: Orchestrator) -> None:
    with get_db_session() as db:
        deployment = crud.get_deployment(db, deployment_id)
        if deployment is None:
            logger.warning("deployment %s not found, nothing to execute", deployment_id)
            return

        try:
            _run(db, deployment, orchestrator)
        except Exception as exc:  # noqa: BLE001 -- deliberate last-resort net,
            # see the comment inside the except block for why.
            # A background job that raises out to its caller leaves this row
            # stuck at "deploying"/"health_checking" forever, invisible to
            # anyone watching the API. Recording the real error and landing
            # on a terminal status is a better outcome than that, even for a
            # failure mode this code didn't specifically anticipate.
            logger.exception("deployment %s failed unexpectedly", deployment_id)
            crud.update_status(
                db, deployment, models.DeploymentStatus.failed, error=f"unexpected error: {exc}"
            )
            _audit_terminal(deployment.id, "deployment.failed", error=f"unexpected error: {exc}")


def _run(db, deployment: models.Deployment, orchestrator: Orchestrator) -> None:
    release_name = deployment.service_name
    namespace = deployment.environment.value
    values = {"image": {"repository": deployment.service_name, "tag": deployment.image_tag}}

    crud.update_status(db, deployment, models.DeploymentStatus.deploying)
    try:
        result = orchestrator.deploy(release_name, settings.CHART_PATH, namespace, values)
    except OrchestratorError as exc:
        crud.update_status(db, deployment, models.DeploymentStatus.failed, error=str(exc))
        _audit_terminal(deployment.id, "deployment.failed", error=str(exc))
        return

    deployment.revision = result.revision
    db.add(deployment)
    db.commit()

    crud.update_status(db, deployment, models.DeploymentStatus.health_checking)
    timeout = settings.HEALTH_CHECK_TIMEOUT_SECONDS
    healthy = orchestrator.check_rollout_health(release_name, namespace, timeout)

    if healthy:
        crud.update_status(db, deployment, models.DeploymentStatus.succeeded)
        crud.mark_as_last_successful(db, deployment)
        _audit_terminal(deployment.id, "deployment.succeeded")
        return

    _roll_back(db, deployment, orchestrator, release_name, namespace)


def _roll_back(db, deployment, orchestrator: Orchestrator, release_name: str, namespace: str) -> None:
    crud.update_status(db, deployment, models.DeploymentStatus.rolling_back)
    previous = crud.get_last_successful_deployment(db, deployment.service_name, deployment.environment)

    try:
        orchestrator.rollback(release_name, namespace, to_revision=previous.revision if previous else None)
        crud.update_status(
            db,
            deployment,
            models.DeploymentStatus.rolled_back,
            error="health check failed after deploy; rolled back automatically",
        )
        record_safely(
            actor="system",
            action="deployment.rolled_back",
            resource_type="deployment",
            resource_id=deployment.id,
            before_state={"image_tag": deployment.image_tag},
            after_state={"rolled_back_to_revision": previous.revision if previous else None},
        )
    except OrchestratorError as exc:
        error_msg = f"health check failed AND automatic rollback also failed: {exc}"
        crud.update_status(db, deployment, models.DeploymentStatus.failed, error=error_msg)
        _audit_terminal(deployment.id, "deployment.failed", error=error_msg)
