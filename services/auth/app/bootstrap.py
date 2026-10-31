"""First-admin bootstrap. See Settings.BOOTSTRAP_ADMIN_EMAIL for why this exists."""

import logging

from sqlalchemy.orm import Session

from . import crud, models, schemas
from .audit_client import record_safely
from .config import settings

logger = logging.getLogger(__name__)


def bootstrap_email() -> str:
    return settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower()


def ensure_bootstrap_admin(db: Session) -> str:
    """Create the configured admin if absent. Returns what happened:
    "disabled", "created", or "exists" (left completely untouched -- an
    existing account is never promoted, so this can't be used to escalate
    a user who merely shares the configured email).
    """
    email = bootstrap_email()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD
    if not email or not password:
        return "disabled"

    if crud.get_user_by_email(db, email) is not None:
        logger.info("bootstrap admin %s already exists; leaving it unchanged", email)
        return "exists"

    # Goes through the same schema as public registration, so a weak or
    # over-long bootstrap password fails loudly at boot instead of creating
    # an admin account that can never log in.
    user_in = schemas.UserCreate(email=email, password=password, full_name="Bootstrap Admin")
    user = crud.create_user(db, user_in, role=models.Role.admin)
    record_safely(
        actor="system", action="user.bootstrap_admin_created", resource_type="user", resource_id=user.id,
        after_state={"email": user.email, "role": user.role.value},
    )
    logger.warning("created bootstrap admin %s -- rotate its password and unset BOOTSTRAP_ADMIN_*", email)
    return "created"
