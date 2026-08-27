"""The actual alert evaluation logic. Pure business logic -- no Celery
import, testable directly with any combination of MetricsSource/Notifier/
IncidentClient, same separation as the deployment service's executor.py.
"""

import logging

from . import crud, models
from .database import get_db_session
from .incident_client import IncidentClient, IncidentClientError
from .metrics_source import MetricsQueryError, MetricsSource
from .notifier import Notifier, NotifierError

logger = logging.getLogger(__name__)


def _breached(value: float, comparison: models.Comparison, threshold: float) -> bool:
    if comparison == models.Comparison.gt:
        return value > threshold
    if comparison == models.Comparison.gte:
        return value >= threshold
    if comparison == models.Comparison.lt:
        return value < threshold
    if comparison == models.Comparison.lte:
        return value <= threshold
    raise ValueError(f"unknown comparison: {comparison}")  # pragma: no cover -- exhaustive enum


def evaluate_rule(
    rule_id: str, metrics_source: MetricsSource, notifier: Notifier, incident_client: IncidentClient
) -> None:
    try:
        _evaluate_rule_inner(rule_id, metrics_source, notifier, incident_client)
    except Exception:  # noqa: BLE001 -- last-resort safety net, same
        # reasoning as the deployment service's executor.py: this runs as
        # one iteration of a batch evaluation (see evaluate_all_active_
        # rules below), and one rule's unexpected bug must not abort every
        # other rule's evaluation for the rest of that batch.
        logger.exception("unexpected error evaluating alert rule %s", rule_id)


def _evaluate_rule_inner(
    rule_id: str, metrics_source: MetricsSource, notifier: Notifier, incident_client: IncidentClient
) -> None:
    with get_db_session() as db:
        rule = crud.get_rule(db, rule_id)
        if rule is None or not rule.is_active:
            return

        try:
            value = metrics_source.query(rule.metric_query)
        except MetricsQueryError:
            logger.exception("metrics query failed for rule %s", rule_id)
            return

        breached = _breached(value, rule.comparison, rule.threshold)
        existing = crud.get_firing_alert_for_rule(db, rule.id)

        if breached and existing is None:
            _fire_new_alert(db, rule, value, notifier, incident_client)
        elif not breached and existing is not None:
            crud.resolve_alert(db, existing)
        # breached and existing already firing -> dedup, intentionally a no-op
        # not breached and nothing firing -> nothing to do


def _fire_new_alert(
    db, rule: models.AlertRule, value: float, notifier: Notifier, incident_client: IncidentClient
) -> None:
    alert = crud.create_alert(db, rule, value)

    if rule.webhook_url:
        try:
            notifier.send(
                rule.webhook_url,
                {
                    "alert_id": alert.id,
                    "rule_name": rule.name,
                    "service_name": rule.service_name,
                    "severity": rule.severity.value,
                    "message": alert.message,
                    "observed_value": value,
                },
            )
        except NotifierError:
            # The alert is already recorded either way -- a failed
            # notification shouldn't mean a lost alert, just a logged gap.
            logger.exception("webhook delivery failed for alert %s", alert.id)

    try:
        incident_id = incident_client.create_incident_for_alert(alert.id, rule, value)
        crud.link_incident(db, alert, incident_id)
    except IncidentClientError:
        logger.exception("incident creation failed for alert %s", alert.id)


def evaluate_all_active_rules(
    metrics_source: MetricsSource, notifier: Notifier, incident_client: IncidentClient
) -> None:
    with get_db_session() as db:
        rule_ids = crud.list_active_rule_ids(db)
    for rule_id in rule_ids:
        evaluate_rule(rule_id, metrics_source, notifier, incident_client)
