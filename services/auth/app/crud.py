from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas, security


def get_user_by_email(db: Session, email: str) -> models.User | None:
    # Case-insensitive: Alice@x.com and alice@x.com are one mailbox. New
    # accounts are stored lower-cased (create_user), so this also finds them
    # by their stored form with no extra normalisation by callers.
    return db.query(models.User).filter(func.lower(models.User.email) == email.strip().lower()).first()


def get_user_by_id(db: Session, user_id: str) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(
    db: Session, user_in: schemas.UserCreate, role: models.Role = models.Role.viewer
) -> models.User:
    user = models.User(
        email=str(user_in.email).strip().lower(),
        hashed_password=security.hash_password(user_in.password),
        full_name=user_in.full_name,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.created_at).all()


def set_role(db: Session, user: models.User, role: models.Role) -> models.User:
    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
