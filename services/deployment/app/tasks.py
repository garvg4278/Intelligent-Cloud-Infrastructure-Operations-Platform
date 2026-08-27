from celery import Celery

from .config import settings
from .executor import execute_deployment
from .orchestrator import get_orchestrator

celery_app = Celery("icop_deployment", broker=settings.CELERY_BROKER_URL)
celery_app.conf.update(
    task_ignore_result=True,  # status lives in Postgres, not Celery's result backend
    task_default_queue="deployments",
)


@celery_app.task(name="deployment.execute")
def execute_deployment_task(deployment_id: str) -> None:
    execute_deployment(deployment_id, get_orchestrator())
