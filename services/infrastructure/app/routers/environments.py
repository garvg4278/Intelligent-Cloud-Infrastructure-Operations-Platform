from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..audit_client import record_safely
from ..database import get_db
from ..models import EnvironmentStatus, EnvironmentType
from ..tasks import destroy_environment_task, provision_environment_task

router = APIRouter(prefix="/environments", tags=["environments"])

# Only an environment already up (or stuck in a failed state) is a valid
# destroy target -- one mid-flight in provisioning_infra/configuring_nodes
# would race the provision task's own writes if a destroy task started
# concurrently against the same row.
_DESTROYABLE_STATUSES = (
    EnvironmentStatus.ready,
    EnvironmentStatus.provision_failed,
    EnvironmentStatus.destroy_failed,
)


@router.post("", response_model=schemas.EnvironmentOut, status_code=status.HTTP_202_ACCEPTED)
def create_environment(payload: schemas.EnvironmentCreate, db: Session = Depends(get_db)):
    existing = crud.get_active_environment_by_type(db, payload.environment_type)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"an environment of type '{payload.environment_type.value}' already exists "
                f"(id={existing.id}, status={existing.status.value}) -- destroy it first"
            ),
        )

    environment = crud.create_environment(db, payload)
    # No caller identity is used here yet -- same gap as
    # services/deployment/app/routers/deployments.py's identical comment:
    # the gateway forwards a verified identity as X-ICOP-User (Phase 6),
    # this route just doesn't read it yet.
    record_safely(
        actor="system",
        action="environment.provision_triggered",
        resource_type="environment",
        resource_id=environment.id,
        after_state={"environment_type": environment.environment_type.value},
    )
    # .delay() runs synchronously in tests (Celery's eager mode) and via a
    # real broker/worker in production -- this route doesn't know or care
    # which, same as every other service's POST route in this repo.
    provision_environment_task.delay(environment.id)
    db.refresh(environment)
    return environment


@router.get("/{environment_id}", response_model=schemas.EnvironmentOut)
def get_environment(environment_id: str, db: Session = Depends(get_db)):
    environment = crud.get_environment(db, environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="environment not found")
    return environment


@router.get("", response_model=list[schemas.EnvironmentOut])
def list_environments(environment_type: EnvironmentType | None = None, db: Session = Depends(get_db)):
    return crud.list_environments(db, environment_type=environment_type)


@router.delete("/{environment_id}", response_model=schemas.EnvironmentOut, status_code=status.HTTP_202_ACCEPTED)
def destroy_environment(environment_id: str, db: Session = Depends(get_db)):
    environment = crud.get_environment(db, environment_id)
    if environment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="environment not found")
    if environment.status not in _DESTROYABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot destroy an environment in status '{environment.status.value}'",
        )

    environment = crud.update_status(db, environment, EnvironmentStatus.destroying)
    record_safely(
        actor="system",
        action="environment.destroy_triggered",
        resource_type="environment",
        resource_id=environment.id,
    )
    destroy_environment_task.delay(environment.id)
    db.refresh(environment)
    return environment
