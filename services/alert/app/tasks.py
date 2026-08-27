from celery import Celery

from .config import settings
from .executor import evaluate_all_active_rules, evaluate_rule
from .incident_client import get_incident_client
from .metrics_source import get_metrics_source
from .notifier import get_notifier

celery_app = Celery("icop_alert", broker=settings.CELERY_BROKER_URL)
celery_app.conf.update(
    task_ignore_result=True,
    task_default_queue="alerts",
    beat_schedule={
        "evaluate-all-alert-rules": {
            "task": "alert.evaluate_all",
            "schedule": settings.EVALUATION_INTERVAL_SECONDS,
        },
    },
)


@celery_app.task(name="alert.evaluate_rule")
def evaluate_rule_task(rule_id: str) -> None:
    evaluate_rule(rule_id, get_metrics_source(), get_notifier(), get_incident_client())


@celery_app.task(name="alert.evaluate_all")
def evaluate_all_task() -> None:
    evaluate_all_active_rules(get_metrics_source(), get_notifier(), get_incident_client())
