from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..audit_client import record_safely
from ..database import get_db
from ..models import AlertSeverity, AlertStatus
from ..tasks import evaluate_all_task, evaluate_rule_task

router = APIRouter(prefix="/alerts", tags=["alerts"])

# NOTE on ordering: /rules and /rules/{rule_id}/evaluate are registered
# BEFORE /{alert_id} on purpose. FastAPI/Starlette match routes in
# registration order, and /{alert_id} is a catch-all path parameter -- if
# it were registered first, a request to /alerts/rules would match it with
# alert_id="rules" instead of ever reaching the rules routes below.


@router.post("/rules", response_model=schemas.AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: schemas.AlertRuleCreate, db: Session = Depends(get_db)):
    rule = crud.create_rule(db, payload)
    record_safely(
        actor="system",
        action="alert_rule.created",
        resource_type="alert_rule",
        resource_id=rule.id,
        after_state={
            "name": rule.name,
            "service_name": rule.service_name,
            "severity": rule.severity.value,
        },
    )
    return rule


@router.get("/rules", response_model=list[schemas.AlertRuleOut])
def list_rules(service_name: str | None = None, db: Session = Depends(get_db)):
    return crud.list_rules(db, service_name=service_name)


@router.get("/rules/{rule_id}", response_model=schemas.AlertRuleOut)
def get_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = crud.get_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule not found")
    return rule


@router.post("/rules/{rule_id}/evaluate", status_code=status.HTTP_202_ACCEPTED)
def evaluate_rule_now(rule_id: str, db: Session = Depends(get_db)):
    if crud.get_rule(db, rule_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule not found")
    evaluate_rule_task.delay(rule_id)
    return {"status": "evaluation triggered"}


@router.post("/evaluate-all", status_code=status.HTTP_202_ACCEPTED)
def evaluate_all_now():
    evaluate_all_task.delay()
    return {"status": "evaluation triggered for all active rules"}


@router.get("", response_model=list[schemas.AlertOut])
def list_alerts(
    status_filter: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return crud.list_alerts(db, status=status_filter, severity=severity, limit=limit, offset=offset)


@router.get("/{alert_id}", response_model=schemas.AlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = crud.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    return alert


@router.post("/{alert_id}/acknowledge", response_model=schemas.AlertOut)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = crud.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    updated = crud.acknowledge_alert(db, alert)
    # No caller identity available here either -- see the equivalent note
    # in the deployment service's create_deployment.
    record_safely(
        actor="system",
        action="alert.acknowledged",
        resource_type="alert",
        resource_id=alert.id,
        after_state={"acknowledged_at": updated.acknowledged_at.isoformat()},
    )
    return updated
