from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import models, schemas


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_rule(db: Session, payload: schemas.AlertRuleCreate) -> models.AlertRule:
    rule = models.AlertRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def get_rule(db: Session, rule_id: str) -> models.AlertRule | None:
    return db.query(models.AlertRule).filter(models.AlertRule.id == rule_id).first()


def list_rules(db: Session, service_name: str | None = None) -> list[models.AlertRule]:
    query = db.query(models.AlertRule)
    if service_name:
        query = query.filter(models.AlertRule.service_name == service_name)
    return query.order_by(models.AlertRule.created_at.desc()).all()


def list_active_rule_ids(db: Session) -> list[str]:
    rows = db.query(models.AlertRule.id).filter(models.AlertRule.is_active.is_(True)).all()
    return [row[0] for row in rows]


def get_firing_alert_for_rule(db: Session, rule_id: str) -> models.Alert | None:
    return (
        db.query(models.Alert)
        .filter(models.Alert.rule_id == rule_id, models.Alert.status == models.AlertStatus.firing)
        .first()
    )


def create_alert(db: Session, rule: models.AlertRule, observed_value: float) -> models.Alert:
    alert = models.Alert(
        rule_id=rule.id,
        status=models.AlertStatus.firing,
        severity=rule.severity,
        message=(
            f"{rule.name}: {rule.metric_query} {rule.comparison.value} "
            f"{rule.threshold} (observed {observed_value})"
        ),
        observed_value=observed_value,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def resolve_alert(db: Session, alert: models.Alert) -> models.Alert:
    alert.status = models.AlertStatus.resolved
    alert.resolved_at = _utcnow()
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def acknowledge_alert(db: Session, alert: models.Alert) -> models.Alert:
    alert.acknowledged_at = _utcnow()
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def link_incident(db: Session, alert: models.Alert, incident_id: str) -> None:
    alert.incident_id = incident_id
    db.add(alert)
    db.commit()


def get_alert(db: Session, alert_id: str) -> models.Alert | None:
    return db.query(models.Alert).filter(models.Alert.id == alert_id).first()


def list_alerts(
    db: Session,
    status: models.AlertStatus | None = None,
    severity: models.AlertSeverity | None = None,
    service_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[models.Alert]:
    query = db.query(models.Alert)
    if service_name:
        # Filter in SQL via the rule: clients (analytics, aiops) used to
        # download EVERY service's alerts and join against rule ids in
        # memory, which silently dropped this service's alerts once other
        # services' alerts pushed them past the first page.
        query = query.join(models.AlertRule, models.Alert.rule_id == models.AlertRule.id).filter(
            models.AlertRule.service_name == service_name
        )
    if status:
        query = query.filter(models.Alert.status == status)
    if severity:
        query = query.filter(models.Alert.severity == severity)
    return query.order_by(models.Alert.fired_at.desc()).offset(offset).limit(limit).all()
