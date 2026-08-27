from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..audit_client import record_safely
from ..database import get_db
from ..models import IncidentSeverity, IncidentStatus

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=schemas.IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(payload: schemas.IncidentCreate, db: Session = Depends(get_db)):
    incident = crud.create_incident(db, payload)
    # No caller identity available -- see the equivalent note in the
    # deployment and alert services' routers.
    record_safely(
        actor="system",
        action="incident.created",
        resource_type="incident",
        resource_id=incident.id,
        after_state={"title": incident.title, "severity": incident.severity.value},
    )
    return incident


@router.get("", response_model=list[schemas.IncidentOut])
def list_incidents(
    status_filter: IncidentStatus | None = None,
    service_name: str | None = None,
    severity: IncidentSeverity | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return crud.list_incidents(
        db, status=status_filter, service_name=service_name, severity=severity, limit=limit, offset=offset
    )


@router.get("/{incident_id}", response_model=schemas.IncidentDetailOut)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = crud.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")
    events = crud.get_events(db, incident_id)
    detail = schemas.IncidentOut.model_validate(incident).model_dump()
    return schemas.IncidentDetailOut(**detail, events=events)


@router.post("/{incident_id}/transition", response_model=schemas.IncidentOut)
def transition_incident(incident_id: str, payload: schemas.TransitionRequest, db: Session = Depends(get_db)):
    incident = crud.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")
    previous_status = incident.status.value  # captured before transition_status mutates it
    try:
        updated = crud.transition_status(db, incident, payload.status)
    except crud.InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    record_safely(
        actor="system",
        action="incident.status_changed",
        resource_type="incident",
        resource_id=incident.id,
        before_state={"status": previous_status},
        after_state={"status": updated.status.value},
    )
    return updated


@router.post("/{incident_id}/comments", response_model=schemas.IncidentEventOut, status_code=201)
def comment_on_incident(incident_id: str, payload: schemas.CommentRequest, db: Session = Depends(get_db)):
    incident = crud.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")
    # Comments aren't audited -- they're discussion, not a state change or
    # access-control-relevant action. The transition above is.
    return crud.add_comment(db, incident, payload.message)
