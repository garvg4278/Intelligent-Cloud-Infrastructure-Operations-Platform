from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/audit", tags=["audit"])

# Create and read. That's the whole interface -- there is no route here
# that updates or deletes an event, which is the actual enforcement of
# "immutable history should be preserved," not a comment saying so.


@router.post("/events", response_model=schemas.AuditEventOut, status_code=status.HTTP_201_CREATED)
def create_event(payload: schemas.AuditEventCreate, db: Session = Depends(get_db)):
    event = crud.create_event(db, payload)
    return crud.to_out(event)


@router.get("/events", response_model=list[schemas.AuditEventOut])
def list_events(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    source_service: str | None = None,
    # This is the one list endpoint in the platform where an unbounded
    # query wasn't just a hypothetical -- "retain immutable history" /
    # "stored forever" (this platform's own design principles, see
    # ROADMAP.md's linked design doc) means this table has no natural
    # ceiling at all. Every event this platform has ever recorded, in one
    # response, was one curl command away before this.
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    events = crud.list_events(
        db,
        actor=actor,
        action=action,
        resource_type=resource_type,
        source_service=source_service,
        limit=limit,
        offset=offset,
    )
    return [crud.to_out(e) for e in events]


@router.get("/events/{event_id}", response_model=schemas.AuditEventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = crud.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audit event not found")
    return crud.to_out(event)
