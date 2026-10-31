from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..audit_client import record_safely
from ..database import get_db
from ..models import Environment
from ..tasks import execute_deployment_task

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.post("", response_model=schemas.DeploymentOut, status_code=status.HTTP_202_ACCEPTED)
def create_deployment(payload: schemas.DeploymentCreate, db: Session = Depends(get_db)):
    deployment = crud.create_deployment(db, payload)
    # No caller identity is used here yet -- the gateway verifies every
    # request's identity now (Phase 6) and forwards it as an X-ICOP-User
    # header, but this route doesn't read that header yet, so this
    # service still has no user to attribute the trigger to.
    record_safely(
        actor="system",
        action="deployment.triggered",
        resource_type="deployment",
        resource_id=deployment.id,
        after_state={"service_name": deployment.service_name, "image_tag": deployment.image_tag},
    )
    # .delay() runs synchronously in tests (Celery's eager mode) and via a
    # real broker/worker in production -- the route doesn't know or care
    # which. By the time this returns in eager mode the deployment has
    # already reached a terminal status; in production it's still "pending"
    # and the caller polls GET /deployments/{id}.
    execute_deployment_task.delay(deployment.id)
    db.refresh(deployment)
    return deployment


@router.get("/{deployment_id}", response_model=schemas.DeploymentOut)
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = crud.get_deployment(db, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deployment not found")
    return deployment


@router.get("", response_model=list[schemas.DeploymentOut])
def list_deployments(
    service_name: str | None = None,
    environment: Environment | None = None,
    # Real gap this closes: this endpoint had no limit at all -- under
    # real usage (a service that's been deploying for months) that's an
    # unbounded query and an unbounded response, not a hypothetical
    # concern. le=200 caps it even for a caller that tries to ask for
    # more; ge=1 keeps someone from asking for 0 and being confused when
    # they get an empty list back for no apparent reason.
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return crud.list_deployments(
        db, service_name=service_name, environment=environment, limit=limit, offset=offset
    )
