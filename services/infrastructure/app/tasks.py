from celery import Celery

from .ansible_orchestrator import get_ansible_orchestrator
from .config import settings
from .executor import destroy_environment, provision_environment
from .terraform_orchestrator import get_terraform_orchestrator

celery_app = Celery("icop_infrastructure", broker=settings.CELERY_BROKER_URL)
celery_app.conf.update(
    task_ignore_result=True,  # status lives in Postgres, not Celery's result backend
    task_default_queue="infrastructure",
)


@celery_app.task(name="infrastructure.provision")
def provision_environment_task(environment_id: str) -> None:
    provision_environment(environment_id, get_terraform_orchestrator(), get_ansible_orchestrator())


@celery_app.task(name="infrastructure.destroy")
def destroy_environment_task(environment_id: str) -> None:
    destroy_environment(environment_id, get_terraform_orchestrator())
