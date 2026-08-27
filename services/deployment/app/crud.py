from sqlalchemy.orm import Session

from . import models, schemas


def create_deployment(db: Session, payload: schemas.DeploymentCreate) -> models.Deployment:
    deployment = models.Deployment(
        service_name=payload.service_name,
        environment=payload.environment,
        image_tag=payload.image_tag,
        status=models.DeploymentStatus.pending,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def get_deployment(db: Session, deployment_id: str) -> models.Deployment | None:
    return db.query(models.Deployment).filter(models.Deployment.id == deployment_id).first()


def list_deployments(
    db: Session,
    service_name: str | None = None,
    environment: models.Environment | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[models.Deployment]:
    query = db.query(models.Deployment)
    if service_name:
        query = query.filter(models.Deployment.service_name == service_name)
    if environment:
        query = query.filter(models.Deployment.environment == environment)
    return query.order_by(models.Deployment.created_at.desc()).offset(offset).limit(limit).all()


def update_status(
    db: Session, deployment: models.Deployment, status: models.DeploymentStatus, error: str | None = None
) -> models.Deployment:
    deployment.status = status
    if error is not None:
        deployment.error_message = error
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def mark_as_last_successful(db: Session, deployment: models.Deployment) -> None:
    db.query(models.Deployment).filter(
        models.Deployment.service_name == deployment.service_name,
        models.Deployment.environment == deployment.environment,
        models.Deployment.id != deployment.id,
    ).update({"is_last_successful": False})
    deployment.is_last_successful = True
    db.add(deployment)
    db.commit()


def get_last_successful_deployment(
    db: Session, service_name: str, environment: models.Environment
) -> models.Deployment | None:
    return (
        db.query(models.Deployment)
        .filter(
            models.Deployment.service_name == service_name,
            models.Deployment.environment == environment,
            models.Deployment.is_last_successful.is_(True),
        )
        .first()
    )
