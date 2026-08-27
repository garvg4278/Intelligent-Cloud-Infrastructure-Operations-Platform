import uuid

from sqlalchemy.orm import Session

from . import models, schemas

# Any status other than "destroyed" counts as an existing environment of
# that type for the purposes of blocking a duplicate create -- including
# provision_failed/destroy_failed, since retrying those goes through
# destroy-then-recreate (see routers/environments.py), not a second
# concurrent create.
_INACTIVE_STATUSES = (models.EnvironmentStatus.destroyed,)


def create_environment(db: Session, payload: schemas.EnvironmentCreate) -> models.Environment:
    # `environments.name` is intentionally unique so audit and operational
    # views always have an unambiguous label. A destroyed environment stays
    # in the database as lifecycle history, therefore a later provision of
    # the same Terraform target needs a fresh, stable name rather than
    # colliding with `icop-staging` / `icop-production` from the old row.
    environment_id = str(uuid.uuid4())
    environment = models.Environment(
        id=environment_id,
        name=f"icop-{payload.environment_type.value}-{environment_id[:8]}",
        environment_type=payload.environment_type,
        status=models.EnvironmentStatus.pending,
    )
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment


def get_environment(db: Session, environment_id: str) -> models.Environment | None:
    return db.query(models.Environment).filter(models.Environment.id == environment_id).first()


def get_active_environment_by_type(
    db: Session, environment_type: models.EnvironmentType
) -> models.Environment | None:
    return (
        db.query(models.Environment)
        .filter(
            models.Environment.environment_type == environment_type,
            models.Environment.status.notin_(_INACTIVE_STATUSES),
        )
        .first()
    )


def list_environments(
    db: Session, environment_type: models.EnvironmentType | None = None
) -> list[models.Environment]:
    query = db.query(models.Environment)
    if environment_type:
        query = query.filter(models.Environment.environment_type == environment_type)
    return query.order_by(models.Environment.created_at.desc()).all()


def update_status(
    db: Session,
    environment: models.Environment,
    status: models.EnvironmentStatus,
    error: str | None = None,
    cluster_name: str | None = None,
) -> models.Environment:
    environment.status = status
    if error is not None:
        environment.error_message = error
    if cluster_name is not None:
        environment.cluster_name = cluster_name
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment
